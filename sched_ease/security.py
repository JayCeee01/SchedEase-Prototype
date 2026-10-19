"""Strict environment parsing shared by startup and isolated security tests."""
import ipaddress
import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def boolean(env, name, default):
    value = env.get(name, str(default)).strip().lower()
    if value not in ('true', 'false'):
        raise ImproperlyConfigured(f'{name} must be true or false.')
    return value == 'true'


def environment_mode(env):
    mode = env.get('SCHED_EASE_ENV', 'development').strip().lower()
    if mode not in ('development', 'production'):
        raise ImproperlyConfigured('SCHED_EASE_ENV must be development or production.')
    return mode


def valid_host(host):
    if host.startswith('[') and host.endswith(']'):
        try:
            return ipaddress.ip_address(host[1:-1]).version == 6
        except ValueError:
            return False
    if len(host) > 253:
        return False
    return all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
               for label in host.split('.'))


def csv_values(env, name, default=''):
    raw = env.get(name, default).strip()
    if not raw:
        return []
    values = [value.strip() for value in raw.split(',')]
    if any(not value for value in values):
        raise ImproperlyConfigured(f'{name} contains an empty item.')
    return list(dict.fromkeys(values))


def security_settings(env):
    production = environment_mode(env) == 'production'
    debug = boolean(env, 'SCHED_EASE_DEBUG', not production)
    if production and debug:
        raise ImproperlyConfigured('SCHED_EASE_DEBUG must be false in production.')
    secret = env.get('SCHED_EASE_SECRET_KEY', '' if production else
                     env.get('SECRET_KEY', 'dev-only-sched-ease-secret-key'))
    if production and (len(secret) < 50 or len(set(secret)) < 5 or
                       any(c.isspace() for c in secret) or
                       any(marker in secret.lower() for marker in
                           ('django-insecure-', 'change-me', 'replace-me', 'dev-only', '<', '>'))):
        raise ImproperlyConfigured('SCHED_EASE_SECRET_KEY must be a private random key of at least 50 characters; placeholders are not allowed.')
    hosts = csv_values(env, 'SCHED_EASE_ALLOWED_HOSTS', '' if production else '127.0.0.1,localhost')
    if production and (not hosts or any(not valid_host(host) for host in hosts)):
        raise ImproperlyConfigured('SCHED_EASE_ALLOWED_HOSTS requires explicit hostnames or IP addresses without schemes, ports or wildcards.')
    origins = csv_values(env, 'SCHED_EASE_CSRF_TRUSTED_ORIGINS')
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            host = parsed.hostname or ''
            valid = (parsed.scheme in (('https',) if production else ('http', 'https'))
                     and valid_host(f'[{host}]' if ':' in host else host)
                     and not parsed.username and not parsed.password
                     and not parsed.path and not parsed.query and not parsed.fragment
                     and origin == f'{parsed.scheme}://{parsed.netloc}'
                     and not parsed.netloc.endswith(':')
                     and (parsed.port is None or 1 <= parsed.port <= 65535))
        except ValueError:
            valid = False
        if not valid:
            raise ImproperlyConfigured('SCHED_EASE_CSRF_TRUSTED_ORIGINS requires exact origins with an allowed scheme, optional port and no path, credentials or wildcards; production requires HTTPS.')
    proxy = boolean(env, 'SCHED_EASE_TRUST_PROXY', False)
    raw_hsts = env.get('SCHED_EASE_HSTS_SECONDS', '0').strip()
    if not re.fullmatch(r'\d{1,8}', raw_hsts) or int(raw_hsts) > 31536000:
        raise ImproperlyConfigured('SCHED_EASE_HSTS_SECONDS must be an integer from 0 to 31536000.')
    return {
        'DEBUG': debug, 'SECRET_KEY': secret, 'ALLOWED_HOSTS': hosts,
        'CSRF_TRUSTED_ORIGINS': origins,
        'SECURE_SSL_REDIRECT': production, 'SECURE_REDIRECT_EXEMPT': [],
        'SECURE_PROXY_SSL_HEADER': ('HTTP_X_FORWARDED_PROTO', 'https') if production and proxy else None,
        'USE_X_FORWARDED_HOST': False,
        'SESSION_COOKIE_SECURE': production, 'CSRF_COOKIE_SECURE': production,
        'SESSION_COOKIE_HTTPONLY': True, 'CSRF_COOKIE_HTTPONLY': production,
        'SESSION_COOKIE_SAMESITE': 'Lax', 'CSRF_COOKIE_SAMESITE': 'Lax',
        'SECURE_HSTS_SECONDS': int(raw_hsts) if production else 0,
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': False, 'SECURE_HSTS_PRELOAD': False,
        'SECURE_CONTENT_TYPE_NOSNIFF': True, 'X_FRAME_OPTIONS': 'DENY',
        'SECURE_REFERRER_POLICY': 'same-origin',
    }
