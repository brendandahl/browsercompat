"""webplatformcompat incoming data parsers"""

from rest_framework.parsers import JSONParser
from rest_framework.relations import HyperlinkedRelatedField

from .utils import model_from_obj, snakecase


class JsonApiParser(JSONParser):
    media_type = 'application/vnd.api+json'

    def parse(self, stream, media_type=None, parser_context=None):
        """Parse JSON API representation into DRF native format."""
        data = super(JsonApiParser, self).parse(
            stream, media_type=media_type, parser_context=parser_context)

        view = parser_context.get("view", None)

        model = self.model_from_obj(view)
        resource_type = self.model_to_resource_type(model)

        resource = {}

        if resource_type in data:
            resource = data[resource_type]

        if isinstance(resource, list):  # pragma: nocover
            resource = [self.convert_resource(r, view) for r in resource]
        else:
            resource = self.convert_resource(resource, view)

        # Add extra data to _view_extra
        # This should mirror .renderers.JsonApiRenderer.wrap_view_extra
        view_extra = {}
        if 'meta' in data:
            view_extra['meta'] = data['meta']
        if 'linked' in data:
            assert 'meta' not in data['linked']
            view_extra.update(data['linked'])
        if view_extra:
            resource['_view_extra'] = view_extra

        return resource

    def convert_resource(self, resource, view):
        serializer_data = view.get_serializer(instance=None)
        fields = serializer_data.fields

        links = {}

        if "links" in resource:
            links = resource["links"]

            del resource["links"]

        for field_name, field in fields.items():
            if field_name not in links:
                continue
            if isinstance(field, HyperlinkedRelatedField):

                if field.many:
                    pks = links[field_name]
                    model = field.queryset.model

                    resource[field_name] = []

                    for pk in pks:
                        obj = model(pk=pk)
                        url = field.to_native(obj)

                        resource[field_name].append(url)
                else:
                    pk = links[field_name]
                    model = field.queryset.model

                    obj = model(pk=pk)

                    url = field.to_native(obj)

                    resource[field_name] = url
            else:
                resource[field_name] = links[field_name]

        return resource

    def model_from_obj(self, obj):
        return model_from_obj(obj)

    def model_to_resource_type(self, model):
        if model:
            return snakecase(model._meta.verbose_name_plural)
        else:
            return 'data'
