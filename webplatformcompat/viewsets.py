# -*- coding: utf-8 -*-

from django.contrib.auth.models import User
from django.http import Http404
from rest_framework.decorators import detail_route
from rest_framework.generics import ListAPIView
from rest_framework.mixins import UpdateModelMixin
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.viewsets import ModelViewSet as BaseModelViewSet
from rest_framework.viewsets import ReadOnlyModelViewSet as BaseROModelViewSet
from rest_framework.response import Response

from drf_cached_instances.mixins import CachedViewMixin as BaseCacheViewMixin

from .cache import Cache
from .history import Changeset
from .mixins import PartialPutMixin
from .models import (
    Browser, Feature, Maturity, Section, Specification, Support, Version)
from .parsers import JsonApiParser
from .renderers import JsonApiV10Renderer, JsonApiV10TemplateHTMLRenderer
from .serializers import (
    BrowserSerializer, FeatureSerializer, MaturitySerializer,
    SectionSerializer, SpecificationSerializer, SupportSerializer,
    VersionSerializer,
    ChangesetSerializer, UserSerializer,
    HistoricalBrowserSerializer, HistoricalFeatureSerializer,
    HistoricalMaturitySerializer, HistoricalSectionSerializer,
    HistoricalSpecificationSerializer, HistoricalSupportSerializer,
    HistoricalVersionSerializer)
from .view_serializers import (
    ViewFeatureListSerializer, ViewFeatureSerializer)


#
# Base classes
#

class CachedViewMixin(BaseCacheViewMixin):
    cache_class = Cache

    def perform_create(self, serializer):
        kwargs = {}
        if getattr(self.request, 'delay_cache', False):
            kwargs['_delay_cache'] = True
        serializer.save(**kwargs)

    def perform_update(self, serializer):
        kwargs = {}
        if getattr(self.request, 'delay_cache', False):
            kwargs['_delay_cache'] = True
        serializer.save(**kwargs)

    def perform_destroy(self, instance):
        if getattr(self.request, 'delay_cache', False):
            instance._delay_cache = True
        instance.delete()


class RelatedActionMixin(object):
    """Add related actions used in JSON API v1.0"""
    def related_list(self, request, pk, viewset, related_name):
        """Return a list of related items."""
        related_view = viewset.as_view({'get': 'list'})
        return related_view(request, apply_filter={related_name: pk})

    def related_item(self, request, pk, viewset, pattern, id_name):
        """Return a related item."""
        obj = self.get_object()
        related_id = getattr(obj, id_name)
        return self.related_generic_item(
            request, pk, viewset, pattern, related_id)

    def current_historical_item(self, request, pk, viewset, pattern):
        obj = self.get_object()
        related_id = getattr(obj, 'history').latest().id
        return self.related_generic_item(
            request, pk, viewset, pattern, related_id)

    def related_generic_item(self, request, pk, viewset, pattern, related_id):
        """Return a related item."""
        related_view = viewset.as_view({'get': 'retrieve'})
        self.override_path = '/api/v2/{}/{}'.format(pattern, related_id)
        return related_view(request, pk=related_id)

    def get_renderer_context(self):
        renderer_context = super(RelatedActionMixin, self).get_renderer_context()
        if hasattr(self, 'override_path'):
            renderer_context['override_path'] = self.override_path
        return renderer_context


class ModelViewSet(
        PartialPutMixin, CachedViewMixin, RelatedActionMixin, BaseModelViewSet):
    renderer_classes = (JsonApiV10Renderer, BrowsableAPIRenderer)
    parser_classes = (JsonApiParser, FormParser, MultiPartParser)


class ReadOnlyModelViewSet(RelatedActionMixin, BaseROModelViewSet):
    renderer_classes = (JsonApiV10Renderer, BrowsableAPIRenderer)


class UpdateOnlyModelViewSet(
        PartialPutMixin, CachedViewMixin, UpdateModelMixin,
        ReadOnlyModelViewSet):
    renderer_classes = (JsonApiV10Renderer, BrowsableAPIRenderer)
    parser_classes = (JsonApiParser, FormParser, MultiPartParser)


#
# 'Regular' viewsets
#

class BrowserViewSet(ModelViewSet):
    queryset = Browser.objects.order_by('id')
    serializer_class = BrowserSerializer
    filter_fields = ('slug',)

    @detail_route()
    def versions(self, request, pk=None):
        return self.related_list(request, pk, VersionViewSet, 'browser')

    @detail_route()
    def historical_browsers(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalBrowserViewSet, 'id')

    @detail_route()
    def historical_browser(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalBrowserViewSet, 'historicalbrowsers')


class FeatureViewSet(ModelViewSet):
    queryset = Feature.objects.order_by('id')
    serializer_class = FeatureSerializer
    filter_fields = ('slug', 'parent')

    def filter_queryset(self, queryset):
        qs = super(FeatureViewSet, self).filter_queryset(queryset)
        if 'parent' in self.request.QUERY_PARAMS:
            filter_value = self.request.QUERY_PARAMS['parent']
            if not filter_value:
                qs = qs.filter(parent=None)
        return qs

    @detail_route()
    def sections(self, request, pk=None):
        return self.related_list(request, pk, SectionViewSet, 'features')

    @detail_route()
    def supports(self, request, pk=None):
        return self.related_list(request, pk, SupportViewSet, 'feature')

    @detail_route()
    def historical_features(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalFeatureViewSet, 'id')

    @detail_route()
    def historical_feature(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalFeatureViewSet, 'historicalfeatures')


class MaturityViewSet(ModelViewSet):
    queryset = Maturity.objects.order_by('id')
    serializer_class = MaturitySerializer
    filter_fields = ('slug',)

    @detail_route()
    def specifications(self, request, pk=None):
        return self.related_list(request, pk, SpecificationViewSet, 'maturity')

    @detail_route()
    def historical_maturities(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalMaturityViewSet, 'id')

    @detail_route()
    def historical_maturity(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalMaturityViewSet, 'historicalmaturities')


class SectionViewSet(ModelViewSet):
    queryset = Section.objects.order_by('id')
    serializer_class = SectionSerializer
    filter_fields = ('features',)

    @detail_route()
    def specification(self, request, pk=None):
        obj = self.get_object()
        related_view = SpecificationViewSet.as_view({'get': 'retrieve'})
        self.override_path = '/api/v2/specifications/{}'.format(
            obj.specification_id)
        return related_view(request, pk=obj.specification_id)

    @detail_route()
    def specification(self, request, pk=None):
        return self.related_item(
            request, pk, SpecificationViewSet, 'specifications',
            'specification_id')

    @detail_route()
    def historical_sections(self, request, pk=None):
        return self.related_list(request, pk, HistoricalSectionViewSet, 'id')

    @detail_route()
    def historical_section(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalSectionViewSet, 'historicalsections')


class SpecificationViewSet(ModelViewSet):
    queryset = Specification.objects.order_by('id')
    serializer_class = SpecificationSerializer
    filter_fields = ('slug', 'mdn_key')

    @detail_route()
    def maturity(self, request, pk=None):
        return self.related_item(
            request, pk, MaturityViewSet, 'maturities', 'maturity_id')

    @detail_route()
    def historical_specifications(self, request, pk=None):
        return self.related_list(request, pk, HistoricalSpecificationViewSet, 'id')

    @detail_route()
    def historical_specification(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalSpecificationViewSet, 'historicalspecifications')


class SupportViewSet(ModelViewSet):
    queryset = Support.objects.order_by('id')
    serializer_class = SupportSerializer
    filter_fields = ('version', 'feature')

    @detail_route()
    def version(self, request, pk=None):
        return self.related_item(
            request, pk, VersionViewSet, 'versions', 'version_id')

    @detail_route()
    def feature(self, request, pk=None):
        return self.related_item(
            request, pk, FeatureViewSet, 'features', 'feature_id')

    @detail_route()
    def historical_supports(self, request, pk=None):
        return self.related_list(request, pk, HistoricalSupportViewSet, 'id')

    @detail_route()
    def historical_support(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalSupportViewSet, 'historicalsupport')


class VersionViewSet(ModelViewSet):
    queryset = Version.objects.order_by('id')
    serializer_class = VersionSerializer
    filter_fields = ('browser', 'browser__slug', 'version', 'status')

    @detail_route()
    def browser(self, request, pk=None):
        return self.related_item(
            request, pk, BrowserViewSet, 'browsers', 'browser_id')

    @detail_route()
    def supports(self, request, pk=None):
        return self.related_list(request, pk, SupportViewSet, 'version')

    @detail_route()
    def historical_versions(self, request, pk=None):
        return self.related_list(request, pk, HistoricalVersionViewSet, 'id')

    @detail_route()
    def historical_version(self, request, pk=None):
        return self.current_historical_item(
            request, pk, HistoricalVersionViewSet, 'historicalversion')


#
# Change control viewsets
#

class ChangesetViewSet(ModelViewSet):
    queryset = Changeset.objects.order_by('id')
    serializer_class = ChangesetSerializer

    @detail_route()
    def user(self, request, pk=None):
        return self.related_item(request, pk, UserViewSet, 'users', 'user_id')

    @detail_route()
    def historical_browsers(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalBrowserViewSet, 'changeset_id')

    @detail_route()
    def historical_features(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalFeatureViewSet, 'changeset_id')

    @detail_route()
    def historical_maturities(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalMaturityViewSet, 'changeset_id')

    @detail_route()
    def historical_sections(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalSectionViewSet, 'changeset_id')

    @detail_route()
    def historical_specifications(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalSpecificationViewSet, 'changeset_id')

    @detail_route()
    def historical_supports(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalSupportViewSet, 'changeset_id')

    @detail_route()
    def historical_versions(self, request, pk=None):
        return self.related_list(
            request, pk, HistoricalVersionViewSet, 'changeset_id')


class UserViewSet(CachedViewMixin, ReadOnlyModelViewSet):
    queryset = User.objects.order_by('id')
    serializer_class = UserSerializer
    filter_fields = ('username',)

    @detail_route()
    def changesets(self, request, pk=None):
        return self.related_list(request, pk, ChangesetViewSet, 'changesets')

#
# Historical object viewsets
#

class RelatedChangesetMixin(object):
    @detail_route()
    def changeset(self, request, pk=None):
        return self.related_item(
            request, pk, ChangesetViewSet, 'changesets', 'history_changeset_id')


class HistoricalBrowserViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Browser.history.model.objects.order_by('id')
    serializer_class = HistoricalBrowserSerializer
    filter_fields = ('id', 'slug')

    @detail_route()
    def browser(self, request, pk=None):
        return self.related_item(
            request, pk, BrowserViewSet, 'browsers', 'id')


class HistoricalFeatureViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Feature.history.model.objects.order_by('id')
    serializer_class = HistoricalFeatureSerializer
    filter_fields = ('id', 'slug')

    @detail_route()
    def feature(self, request, pk=None):
        return self.related_item(
            request, pk, FeatureViewSet, 'features', 'id')


class HistoricalMaturityViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Maturity.history.model.objects.order_by('id')
    serializer_class = HistoricalMaturitySerializer
    filter_fields = ('id', 'slug')

    @detail_route()
    def maturity(self, request, pk=None):
        return self.related_item(
            request, pk, MaturityViewSet, 'maturities', 'id')


class HistoricalSectionViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Section.history.model.objects.order_by('id')
    serializer_class = HistoricalSectionSerializer
    filter_fields = ('id',)

    @detail_route()
    def section(self, request, pk=None):
        return self.related_item(
            request, pk, SectionViewSet, 'sections', 'id')


class HistoricalSpecificationViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Specification.history.model.objects.order_by('id')
    serializer_class = HistoricalSpecificationSerializer
    filter_fields = ('id', 'slug', 'mdn_key')

    @detail_route()
    def specification(self, request, pk=None):
        return self.related_item(
            request, pk, SpecificationViewSet, 'specifications', 'id')


class HistoricalSupportViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Support.history.model.objects.order_by('id')
    serializer_class = HistoricalSupportSerializer
    filter_fields = ('id',)

    @detail_route()
    def support(self, request, pk=None):
        return self.related_item(
            request, pk, SupportViewSet, 'supports', 'id')


class HistoricalVersionViewSet(RelatedChangesetMixin, ReadOnlyModelViewSet):
    queryset = Version.history.model.objects.order_by('id')
    serializer_class = HistoricalVersionSerializer
    filter_fields = ('id',)

    @detail_route()
    def version(self, request, pk=None):
        return self.related_item(
            request, pk, VersionViewSet, 'versions', 'id')

#
# Views
#

class ViewFeaturesViewSet(UpdateOnlyModelViewSet):
    queryset = Feature.objects.order_by('id')
    serializer_class = ViewFeatureSerializer
    filter_fields = ('slug',)
    parser_classes = (JsonApiParser, FormParser, MultiPartParser)
    renderer_classes = (
        JsonApiV10Renderer, BrowsableAPIRenderer,
        JsonApiV10TemplateHTMLRenderer)
    template_name = 'webplatformcompat/feature.basic.jinja2'

    def get_serializer_class(self):
        """Return the list serializer when needed."""
        if self.action == 'list':
            return ViewFeatureListSerializer
        else:
            return super(ViewFeaturesViewSet, self).get_serializer_class()

    def get_object_or_404(self, queryset, *filter_args, **filter_kwargs):
        """The feature can be accessed by primary key or by feature slug."""
        pk_or_slug = filter_kwargs['pk']
        try:
            pk = int(pk_or_slug)
        except ValueError:
            try:
                pk = Feature.objects.only('pk').get(slug=pk_or_slug).pk
            except queryset.model.DoesNotExist:
                raise Http404(
                    'No %s matches the given query.' % queryset.model)
        return super(ViewFeaturesViewSet, self).get_object_or_404(
            queryset, pk=pk)
