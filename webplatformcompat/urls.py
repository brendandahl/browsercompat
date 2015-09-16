from django.conf.urls import include, patterns, url
from django.views.generic.base import RedirectView
from mdn.urls import mdn_urlpatterns
from webplatformcompat.routers import routerv1, routerv2

from .views import RequestView, ViewFeature
from .viewsets import VersionsByBrowserView


webplatformcompat_urlpatterns = patterns(
    '',
    url(r'^$', RequestView.as_view(
        template_name='webplatformcompat/home.jinja2'),
        name='home'),
    url(r'^about/', RequestView.as_view(
        template_name='webplatformcompat/about.jinja2'),
        name='about'),
    url(r'^browse/', RequestView.as_view(
        template_name='webplatformcompat/browse.jinja2'),
        name='browse'),
    url(r'^api-auth/', include('rest_framework.urls',
        namespace='rest_framework')),
    url(r'^api/$', RedirectView.as_view(url='/api/v1/', permanent=False),
        name='api_root'),
    url(r'^api/v1/', include(routerv1.urls)),
    url(r'^api/v2/', include(routerv2.urls)),
    url(r'^importer$', RedirectView.as_view(
        url='/importer/', permanent=False)),
    url(r'^importer/', include(mdn_urlpatterns)),
    url(r'^view_feature/(?P<feature_id>\d+)(.html)?$', ViewFeature.as_view(
        template_name='webplatformcompat/feature.js.jinja2'),
        name='view_feature'),
    url(r'^api/v2/browsers/(?P<pk>\d+)/versions',
        VersionsByBrowserView.as_view()),
)
