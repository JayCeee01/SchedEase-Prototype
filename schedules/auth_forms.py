"""Shared form-level enforcement for every password login endpoint."""
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables
from .services import login_limit

INVALID = 'Please check your sign-in details and try again.'


class LimitedLoginMixin:
    @sensitive_variables()
    def clean(self):
        if not self.cleaned_data.get('username') or not self.cleaned_data.get('password'):
            return super().clean()
        try:
            ticket = login_limit.begin(self.request, self.cleaned_data['username'])
            try:
                result = super().clean()
            except ValidationError:
                login_limit.finish(ticket, False)
                raise ValidationError(INVALID, code='invalid_login') from None
            except Exception:
                login_limit.finish(ticket, False)
                raise login_limit.Restricted(login_limit.UNAVAILABLE) from None
            login_limit.finish(ticket, True)
            return result
        except login_limit.Restricted as exc:
            self.user_cache = None
            raise ValidationError(str(exc), code='login_restricted') from None


class LimitedAuthenticationForm(LimitedLoginMixin, AuthenticationForm):
    pass


class LimitedAdminAuthenticationForm(LimitedLoginMixin, AdminAuthenticationForm):
    pass
