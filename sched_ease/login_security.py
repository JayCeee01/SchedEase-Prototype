"""Environment configuration for the isolated login limiter (no academic DB)."""
import ipaddress
from django.core.exceptions import ImproperlyConfigured
from .security import environment_mode
from django.core.checks import Error, Warning, Tags, register
from django.conf import settings
from urllib.parse import urlsplit


@register(Tags.security, deploy=True)
def check_login_storage(app_configs, **kwargs):
    if settings.LOGIN_STORAGE == 'memory':
        return [Warning('Login limits use development-only process memory. Configure shared Redis before deployment.', id='schedease.W001')]
    try:
        parsed = urlsplit(settings.LOGIN_REDIS_URL)
        valid = parsed.scheme in ('redis', 'rediss') and bool(parsed.hostname)
    except ValueError:
        valid = False
    if not valid:
        return [Error('Configure a private Redis URL for login protection.', id='schedease.E001')]
    return []


def login_settings(env):
    production = environment_mode(env) == 'production'
    backend = env.get('SCHED_EASE_LOGIN_STORAGE', 'redis' if production else 'memory')
    if backend not in ('memory', 'redis') or (production and backend != 'redis'):
        raise ImproperlyConfigured('Production login protection requires redis storage.')
    result = {'LOGIN_STORAGE': backend, 'LOGIN_REDIS_URL': env.get('SCHED_EASE_LOGIN_REDIS_URL', ''),
              'LOGIN_MEMORY_ALLOWED': not production}
    for suffix, default in [('MAX_FAILURES', 5), ('SOURCE_MAX_FAILURES', 50), ('WINDOW_SECONDS', 900), ('BLOCK_SECONDS', 900)]:
        try:
            value = int(env.get('SCHED_EASE_LOGIN_' + suffix, default))
        except (ValueError, TypeError):
            raise ImproperlyConfigured('Login limit settings must be positive integers.') from None
        if not 1 <= value <= 86400:
            raise ImproperlyConfigured('Login limit settings must be between 1 and 86400.')
        result['LOGIN_' + suffix] = value
    try:
        result['LOGIN_TRUSTED_PROXIES'] = [str(ipaddress.ip_network(v.strip())) for v in
            env.get('SCHED_EASE_LOGIN_TRUSTED_PROXIES', '').split(',') if v.strip()]
    except ValueError:
        raise ImproperlyConfigured('Login trusted proxies must be IP addresses or CIDR networks.') from None
    return result
