"""Views for bcauth."""

from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.views.generic.base import RedirectView

from webplatformcompat.views import RequestView


class AccountView(RedirectView):
    """Redirect to login or profile page."""
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        if self.request.user.is_anonymous():
            self.url = settings.LOGIN_URL
        else:
            self.url = reverse('account_profile')
        return super(AccountView, self).get_redirect_url(*args, **kwargs)


class ProfileView(RequestView):
    template_name = 'account/profile.jinja2'


account = AccountView.as_view()
profile = login_required(ProfileView.as_view())
