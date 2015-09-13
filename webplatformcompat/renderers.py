from collections import OrderedDict
from json import loads

from django.core.exceptions import NON_FIELD_ERRORS
from django.core.urlresolvers import get_resolver
from django.utils.encoding import force_text
from django.utils.six import string_types
from django.utils.six.moves.urllib.parse import urlparse, urlunparse
from django.utils.translation import get_language
from rest_framework.relations import (
    HyperlinkedRelatedField, ManyRelatedField, PrimaryKeyRelatedField)
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework.serializers import ListSerializer
from rest_framework.settings import api_settings
from rest_framework.status import is_client_error, is_server_error
from rest_framework.utils.encoders import JSONEncoder
from rest_framework.utils.serializer_helpers import ReturnList

from .utils import model_from_obj, snakecase


class WrapperNotApplicable(ValueError):
    def __init__(self, *args, **kwargs):
        self.data = kwargs.pop('data', None)
        self.renderer_context = kwargs.pop('renderer_context', None)
        return super(WrapperNotApplicable, self).__init__(*args, **kwargs)


class JsonApiRC2Renderer(JSONRenderer):
    convert_by_name = {
        'id': 'convert_to_text',
        api_settings.URL_FIELD_NAME: 'rename_to_href',
        'meta': 'add_meta',
    }

    convert_by_type = {
        PrimaryKeyRelatedField: 'handle_related_field',
        HyperlinkedRelatedField: 'handle_url_field',
        ManyRelatedField: 'handle_related_field',
        ListSerializer: 'handle_list_serializer',
    }
    dict_class = OrderedDict
    encoder_class = JSONEncoder
    media_type = 'application/vnd.api+json'
    wrappers = [
        'wrap_view_extra',
        'wrap_view_extra_error',
        'wrap_empty_response',
        'wrap_parser_error',
        'wrap_field_error',
        'wrap_generic_error',
        'wrap_options',
        'wrap_paginated',
        'wrap_default'
    ]

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Convert native data to JSON API

        Tries each of the methods in `wrappers`, using the first successful
        one, or raises `WrapperNotApplicable`.
        """
        wrapper = None
        success = False
        for wrapper_name in self.wrappers:
            wrapper_method = getattr(self, wrapper_name)
            try:
                wrapper = wrapper_method(data, renderer_context)
            except WrapperNotApplicable:
                pass
            else:
                success = True
                break
        if not success:  # pragma nocover
            raise WrapperNotApplicable(
                'No acceptable wrappers found for response.',
                data=data, renderer_context=renderer_context)

        renderer_context["indent"] = 4
        return super(JsonApiRC2Renderer, self).render(
            data=wrapper,
            accepted_media_type=accepted_media_type,
            renderer_context=renderer_context)

    def wrap_view_extra(self, data, renderer_context):
        """Add nested data w/o adding links to main resource."""
        if not (data and '_view_extra' in data):
            raise WrapperNotApplicable('Not linked results')
        response = renderer_context.get("response", None)
        status_code = response and response.status_code
        if status_code == 400:
            raise WrapperNotApplicable('Status code must not be 400.')

        linked = data.pop('_view_extra')
        data.serializer.fields.pop('_view_extra')
        wrapper = self.wrap_default(data, renderer_context)
        assert 'linked' not in wrapper

        wrapper_linked = self.wrap_default(linked, renderer_context)
        to_transfer = ('links', 'linked', 'meta')
        for key, value in wrapper_linked.items():
            if key in to_transfer:
                wrapper.setdefault(key, self.dict_class()).update(value)
        return wrapper

    def wrap_view_extra_error(self, data, renderer_context):
        """Convert field errors involving _view_extra"""
        response = renderer_context.get("response", None)
        status_code = response and response.status_code
        if status_code != 400:
            raise WrapperNotApplicable('Status code must be 400.')
        if not (data and '_view_extra' in data):
            raise WrapperNotApplicable('Not linked results')

        view_extra = data.pop('_view_extra')
        assert isinstance(view_extra, dict)
        converted = {}
        for rname, error_dict in view_extra.items():
            assert rname != 'meta'
            for seq, errors in error_dict.items():
                for fieldname, error in errors.items():
                    name = 'linked.%s.%d.%s' % (rname, seq, fieldname)
                    converted[name] = error
        data.update(converted)

        return self.wrap_error(
            data, renderer_context, keys_are_fields=True, issue_is_title=False)

    def wrap_empty_response(self, data, renderer_context):
        """Pass-through empty responses

        204 No Content includes an empty response
        """
        if data is not None:
            raise WrapperNotApplicable('Data must be empty.')

        return data

    def wrap_parser_error(self, data, renderer_context):
        """
        Convert parser errors to the JSON API Error format

        Parser errors have a status code of 400, like field errors, but have
        the same native format as generic errors.  Also, the detail message is
        often specific to the input, so the error is listed as a 'detail'
        rather than a 'title'.
        """
        response = renderer_context.get("response", None)
        status_code = response and response.status_code
        if status_code != 400:
            raise WrapperNotApplicable('Status code must be 400.')
        if list(data.keys()) != ['detail']:
            raise WrapperNotApplicable('Data must only have "detail" key.')

        return self.wrap_error(
            data, renderer_context, keys_are_fields=False,
            issue_is_title=False)

    def wrap_field_error(self, data, renderer_context):
        """
        Convert field error native data to the JSON API Error format

        See the note about the JSON API Error format on `wrap_error`.

        The native format for field errors is a dictionary where the keys are
        field names (or 'non_field_errors' for additional errors) and the
        values are a list of error strings:

        {
            "min": [
                "min must be greater than 0.",
                "min must be an even number."
            ],
            "max": ["max must be a positive number."],
            "non_field_errors": [
                "Select either a range or an enumeration, not both."]
        }

        It is rendered into this JSON API error format:

        {
            "errors": [{
                "status": "400",
                "path": "/min",
                "detail": "min must be greater than 0."
            },{
                "status": "400",
                "path": "/min",
                "detail": "min must be an even number."
            },{
                "status": "400",
                "path": "/max",
                "detail": "max must be a positive number."
            },{
                "status": "400",
                "path": "/-",
                "detail": "Select either a range or an enumeration, not both."
            }]
        }
        """
        response = renderer_context.get("response", None)
        status_code = response and response.status_code
        if status_code != 400:
            raise WrapperNotApplicable('Status code must be 400.')

        return self.wrap_error(
            data, renderer_context, keys_are_fields=True, issue_is_title=False)

    def wrap_generic_error(self, data, renderer_context):
        """
        Convert generic error native data using the JSON API Error format

        See the note about the JSON API Error format on `wrap_error`.

        The native format for errors that are not bad requests, such as
        authentication issues or missing content, is a dictionary with a
        'detail' key and a string value:

        {
            "detail": "Authentication credentials were not provided."
        }

        This is rendered into this JSON API error format:

        {
            "errors": [{
                "status": "403",
                "title": "Authentication credentials were not provided"
            }]
        }
        """
        response = renderer_context.get("response", None)
        status_code = response and response.status_code
        is_error = is_client_error(status_code) or is_server_error(status_code)
        if not is_error:
            raise WrapperNotApplicable("Status code must be 4xx or 5xx.")

        return self.wrap_error(
            data, renderer_context, keys_are_fields=False, issue_is_title=True)

    def wrap_error(
            self, data, renderer_context, keys_are_fields, issue_is_title):
        """Convert error native data to the JSON API Error format

        JSON API has a different format for errors, but Django REST Framework
        doesn't have a separate rendering path for errors.  This results in
        some guesswork to determine if data is an error, what kind, and how
        to handle it.

        As of August 2014, there is not a consensus about the error format in
        JSON API.  The format documentation defines an "errors" collection, and
        some possible fields for that collection, but without examples for
        common cases.  If and when consensus is reached, this format will
        probably change.
        """
        response = renderer_context.get("response", None)
        status_code = str(response and response.status_code)

        errors = []
        for field, issues in data.items():
            if isinstance(issues, string_types):
                issues = [issues]
            for issue in issues:
                error = self.dict_class()
                error["status"] = status_code

                if issue_is_title:
                    error["title"] = issue
                else:
                    error["detail"] = issue

                if keys_are_fields:
                    non_field_names = ('non_field_errors', NON_FIELD_ERRORS)
                    if field in non_field_names:  # pragma nocover
                        error["path"] = '/-'
                    else:
                        error["path"] = '/' + field

                errors.append(error)
        wrapper = self.dict_class()
        wrapper["errors"] = errors
        return wrapper

    def wrap_options(self, data, renderer_context):
        """Wrap OPTIONS data as JSON API meta value"""
        request = renderer_context.get("request", None)
        method = request and getattr(request, 'method')
        if method != 'OPTIONS':
            raise WrapperNotApplicable("Request method must be OPTIONS")

        wrapper = self.dict_class()
        wrapper["meta"] = data
        return wrapper

    def wrap_paginated(self, data, renderer_context):
        """Convert paginated data to JSON API with meta"""
        pagination_keys = ['count', 'next', 'previous', 'results']
        for key in pagination_keys:
            if not (data and key in data):
                raise WrapperNotApplicable('Not paginated results')

        view = renderer_context.get("view", None)
        model = self.model_from_obj(view)
        resource_type = self.model_to_resource_type(model)

        # Use default wrapper for results
        # DRF 3.x - data['results'] is ReturnList
        assert isinstance(data['results'], ReturnList)
        results = []
        fields = self.fields_from_resource(data['results'].serializer.child)
        assert fields
        for result in data['results']:
            result.fields = fields
            results.append(result)
        wrapper = self.wrap_default(results, renderer_context)

        # Add pagination metadata
        pagination = self.dict_class()
        pagination['previous'] = data['previous']
        pagination['next'] = data['next']
        pagination['count'] = data['count']
        wrapper.setdefault('meta', self.dict_class())
        wrapper['meta'].setdefault('pagination', self.dict_class())
        wrapper['meta']['pagination'].setdefault(
            resource_type, self.dict_class()).update(pagination)
        return wrapper

    def wrap_default(self, data, renderer_context):
        """Convert native data to a JSON API resource collection

        This wrapper expects a standard DRF data object (a dict-like
        object with a `fields` dict-like attribute), or a list of
        such data objects.
        """
        wrapper = self.dict_class()
        view = renderer_context.get("view", None)
        request = renderer_context.get("request", None)

        model = self.model_from_obj(view)
        resource_type = self.model_to_resource_type(model)

        if isinstance(data, list):
            many = True
            resources = data
        else:
            many = False
            resources = [data]

        items = []
        links = self.dict_class()
        linked = self.dict_class()
        meta = self.dict_class()
        for resource in resources:
            converted = self.convert_resource(resource, request)
            item = converted.get('data', {})
            linked_ids = converted.get('linked_ids', {})
            if linked_ids:
                item["links"] = linked_ids
            items.append(item)

            links.update(converted.get('links', {}))
            linked.update(converted.get('linked', {}))
            meta.update(converted.get('meta', {}))

        if many:
            wrapper[resource_type] = items
        else:
            wrapper[resource_type] = items[0]

        if links:
            links = self.prepend_links_with_name(links, resource_type)
            wrapper["links"] = links

        if linked:
            wrapper["linked"] = linked

        if meta:
            wrapper["meta"] = meta

        return wrapper

    def convert_resource(self, resource, request):
        fields = self.fields_from_resource(resource)
        if not fields:  # pragma nocover
            raise WrapperNotApplicable('Items must have a fields attribute.')

        data = self.dict_class()
        linked_ids = self.dict_class()
        links = self.dict_class()
        linked = self.dict_class()
        meta = self.dict_class()

        for field_name, field in fields.items():
            converted = None
            if field_name in self.convert_by_name:
                converter_name = self.convert_by_name[field_name]
                converter = getattr(self, converter_name)
                converted = converter(resource, field, field_name, request)
            else:
                for field_type, converter_name in self.convert_by_type.items():
                    if isinstance(field, field_type):
                        converter = getattr(self, converter_name)
                        converted = converter(
                            resource, field, field_name, request)
                        break
            if converted:
                data.update(converted.pop("data", {}))
                linked_ids.update(converted.pop("linked_ids", {}))
                links.update(converted.get("links", {}))
                linked.update(converted.get("linked", {}))
                meta.update(converted.get("meta", {}))
            else:
                data[field_name] = resource[field_name]

        return {
            'data': data,
            'linked_ids': linked_ids,
            'links': links,
            'linked': linked,
            'meta': meta,
        }

    def convert_to_text(self, resource, field, field_name, request):
        data = self.dict_class()
        data[field_name] = force_text(resource[field_name])
        return {"data": data}

    def rename_to_href(self, resource, field, field_name, request):
        data = self.dict_class()
        data['href'] = resource[field_name]
        return {"data": data}

    def add_meta(self, resource, field, field_name, request):
        """Add metadata."""
        data = resource[field_name]
        return {'meta': data}

    def prepend_links_with_name(self, links, name):
        changed_links = links.copy()

        for link_name, link_obj in links.items():
            if '.' in link_name:
                # Link was already prepended with a resource name
                continue
            prepended_name = "%s.%s" % (name, link_name)
            link_template = "{%s}" % link_name
            prepended_template = "{%s}" % prepended_name

            updated_obj = changed_links[link_name]
            assert 'href' in link_obj
            updated_obj["href"] = link_obj["href"].replace(
                link_template, prepended_template)
            changed_links[prepended_name] = changed_links[link_name]
            del changed_links[link_name]

        return changed_links

    def handle_related_field(self, resource, field, field_name, request):
        """Handle PrimaryKeyRelatedField

        Same as base handle_related_field, but:
        - adds href to links, using DRF default name
        - doesn't handle data not in fields
        - uses presence of child_relation attribute to signify "many"
        """
        links = self.dict_class()
        linked_ids = self.dict_class()

        many = hasattr(field, 'child_relation')
        model = self.model_from_obj(field)
        if model:
            resource_type = self.model_to_resource_type(model)

            format_kwargs = {
                'model_name': model._meta.object_name.lower()
            }
            view_name = '%(model_name)s-detail' % format_kwargs

            links[field_name] = self.dict_class((
                ("type", resource_type),
                ("href", self.url_to_template(view_name, request, field_name)),
            ))

        assert field_name in resource
        if many:
            pks = resource[field_name]
        else:
            pks = [resource[field_name]]

        link_data = []
        for pk in pks:
            if pk is None:
                link_data.append(None)
            else:
                link_data.append(force_text(pk))

        if many:
            linked_ids[field_name] = link_data
        else:
            linked_ids[field_name] = link_data[0]

        return {"linked_ids": linked_ids, "links": links}

    def handle_list_serializer(self, resource, field, field_name, request):
        serializer = field.child
        model = serializer.Meta.model
        resource_type = self.model_to_resource_type(model)

        linked_ids = self.dict_class()
        links = self.dict_class()
        linked = self.dict_class()
        linked[resource_type] = []

        many = field.many
        assert many
        items = resource[field_name]

        obj_ids = []
        for item in items:
            item.serializer = serializer
            item.serializer.model = model
            converted = self.convert_resource(item, request)
            linked_obj = converted["data"]
            converted_ids = converted.pop("linked_ids", {})
            assert converted_ids
            linked_obj["links"] = converted_ids
            obj_ids.append(converted["data"]["id"])

            field_links = self.prepend_links_with_name(
                converted.get("links", {}), resource_type)
            links.update(field_links)

            linked[resource_type].append(linked_obj)

        linked_ids[field_name] = obj_ids
        return {"linked_ids": linked_ids, "links": links, "linked": linked}

    def url_to_template(self, view_name, request, template_name):
        resolver = get_resolver(None)
        info = resolver.reverse_dict[view_name]

        path_template = info[0][0][0]
        # FIXME: what happens when URL has more than one dynamic values?
        # e.g. nested relations: manufacturer/%(id)s/cars/%(card_id)s
        path = path_template % {info[0][0][1][0]: '{%s}' % template_name}

        parsed_url = urlparse(request.build_absolute_uri())

        return urlunparse(
            [parsed_url.scheme, parsed_url.netloc, path, '', '', '']
        )

    def fields_from_resource(self, resource):
        if hasattr(resource, 'serializer'):
            return getattr(resource.serializer, 'fields', None)
        else:
            return getattr(resource, 'fields', None)

    def model_to_resource_type(self, model):
        if model:
            return snakecase(model._meta.verbose_name_plural)
        else:
            return 'data'

    def model_from_obj(self, obj):
        model = model_from_obj(obj)
        if not model and hasattr(obj, 'child_relation'):
            model = model_from_obj(obj.child_relation)
        if (not model and hasattr(obj, 'parent') and
                hasattr(obj.parent, 'instance') and hasattr(obj, 'source')):
            instance = obj.parent.instance
            if instance:
                if isinstance(instance, list):
                    instance = instance[0]
                model = model_from_obj(getattr(instance, obj.source))
                if not model:
                    model = type(getattr(instance, obj.source))
        return model


class JsonApiRC2TemplateHTMLRenderer(TemplateHTMLRenderer):
    """Render to a template, but use JSON API format as context."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Generate JSON API representation, as well as collection."""
        # Set the context to the JSON API represention
        json_api_renderer = JsonApiRC2Renderer()
        json_api = json_api_renderer.render(
            data, accepted_media_type, renderer_context)
        context = loads(
            json_api.decode('utf-8'), object_pairs_hook=OrderedDict)

        # Copy main item to generic 'data' key
        other_keys = ('linked', 'links', 'meta')
        main_keys = [m for m in context.keys() if m not in other_keys]
        assert len(main_keys) == 1
        main_type = main_keys[0]
        main_obj = context[main_type].copy()
        main_id = main_obj['id']
        context['data'] = main_obj
        context['data']['type'] = main_type

        # Add a collection of types and IDs
        collection = {}
        for resource_type, resources in context.get('linked', {}).items():
            assert resource_type not in collection
            collection[resource_type] = {}
            for resource in resources:
                resource_id = resource['id']
                assert resource_id not in collection[resource_type]
                collection[resource_type][resource_id] = resource
        collection.setdefault(main_type, {})[main_id] = main_obj
        context['collection'] = collection

        # Add language
        request = renderer_context['request']
        lang = request.GET.get('lang', get_language())
        context['lang'] = lang

        # Render HTML template w/ context
        return super(JsonApiRC2TemplateHTMLRenderer, self).render(
            context, accepted_media_type, renderer_context)
