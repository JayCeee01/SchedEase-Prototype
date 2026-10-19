"""Production configuration tests use public fixtures, never deployment secrets."""
import os
import subprocess
import sys

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from sched_ease.security import security_settings
from .models import Profile, Role


def production(**changes):
    env = {'SCHED_EASE_ENV': 'production',
           'SCHED_EASE_SECRET_KEY': 'public-test-fixture-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh',
           'SCHED_EASE_ALLOWED_HOSTS': 'school.test'}
    env.update(changes)
    return env


def broken_view(request):
    raise RuntimeError('PRIVATE_EXCEPTION_SENTINEL')


urlpatterns = [path('broken/', broken_view), path('', lambda request: HttpResponse('ok'))]


class SecurityConfigurationTests(SimpleTestCase):
    def test_production_defaults_and_security_headers(self):
        config = security_settings(production())
        self.assertFalse(config['DEBUG'])
        for name in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
                     'SESSION_COOKIE_HTTPONLY', 'CSRF_COOKIE_HTTPONLY', 'SECURE_CONTENT_TYPE_NOSNIFF'):
            self.assertTrue(config[name], name)
        self.assertEqual(config['X_FRAME_OPTIONS'], 'DENY')
        self.assertEqual(config['SECURE_REFERRER_POLICY'], 'same-origin')
        self.assertEqual(config['SESSION_COOKIE_SAMESITE'], 'Lax')
        self.assertEqual(config['CSRF_COOKIE_SAMESITE'], 'Lax')
        self.assertEqual(config['SECURE_REDIRECT_EXEMPT'], [])
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], [])
        self.assertFalse(config['USE_X_FORWARDED_HOST'])

    def test_debug_and_invalid_booleans_fail_closed(self):
        for name in ('SCHED_EASE_DEBUG', 'SCHED_EASE_TRUST_PROXY'):
            for value in ('', 'yes', '1', 'tru', 'false-ish'):
                with self.subTest(name=name, value=value), self.assertRaises(ImproperlyConfigured):
                    security_settings(production(**{name: value}))
        with self.assertRaises(ImproperlyConfigured):
            security_settings(production(SCHED_EASE_DEBUG='true'))
        self.assertFalse(security_settings(production(SCHED_EASE_DEBUG=' FALSE '))['DEBUG'])

    def test_invalid_mode_rejected(self):
        for mode in ('', 'prod', 'staging', 'productionn'):
            with self.subTest(mode=mode), self.assertRaises(ImproperlyConfigured):
                security_settings(production(SCHED_EASE_ENV=mode))

    def test_missing_secret_has_no_legacy_fallback(self):
        env = production()
        del env['SCHED_EASE_SECRET_KEY']
        env['SECRET_KEY'] = production()['SCHED_EASE_SECRET_KEY']
        with self.assertRaises(ImproperlyConfigured):
            security_settings(env)

    def test_invalid_secrets_are_not_disclosed(self):
        for secret in ('', 'short-private-sentinel', 'x' * 60, 'change-me-' * 8,
                       'django-insecure-' + '0123456789' * 6, 'space sentinel ' * 6):
            with self.subTest(length=len(secret)):
                with self.assertRaises(ImproperlyConfigured) as error:
                    security_settings(production(SCHED_EASE_SECRET_KEY=secret))
                if secret:
                    self.assertNotIn(secret, str(error.exception))

    def test_hosts_reject_unsafe_or_malformed_values(self):
        for value in ('', '*', '*.school.test', '.school.test', 'https://school.test',
                      'school.test:443', 'school.test/path', 'a,,b', 'a,', '-bad.test',
                      'a..test', 'bad_host', 'school.test?x', '[not-ipv6]'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                security_settings(production(SCHED_EASE_ALLOWED_HOSTS=value))

    def test_hosts_accept_explicit_dns_and_ips(self):
        config = security_settings(production(SCHED_EASE_ALLOWED_HOSTS='school.test, 127.0.0.1, [::1],school.test'))
        self.assertEqual(config['ALLOWED_HOSTS'], ['school.test', '127.0.0.1', '[::1]'])

    def test_origins_reject_http_wildcards_and_non_origins(self):
        for value in ('http://school.test', 'school.test', 'https://*.school.test',
                      'https://user:secret@school.test', 'https://school.test/',
                      'https://school.test/path', 'https://school.test?x',
                      'https://school.test#x', 'https://school.test:',
                      'https://school.test:65536', 'https://school.test:0', 'https://school.test,'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                security_settings(production(SCHED_EASE_CSRF_TRUSTED_ORIGINS=value))

    def test_explicit_https_origins_with_ports(self):
        values = ['https://school.test', 'https://portal.test:8443', 'https://[::1]:443']
        config = security_settings(production(SCHED_EASE_CSRF_TRUSTED_ORIGINS=','.join(values)))
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], values)

    def test_hsts_is_opt_in_bounded_and_no_subdomain_or_preload_assumption(self):
        config = security_settings(production())
        self.assertEqual(config['SECURE_HSTS_SECONDS'], 0)
        self.assertFalse(config['SECURE_HSTS_INCLUDE_SUBDOMAINS'])
        self.assertFalse(config['SECURE_HSTS_PRELOAD'])
        self.assertEqual(security_settings(production(SCHED_EASE_HSTS_SECONDS='300'))['SECURE_HSTS_SECONDS'], 300)
        for value in ('', '-1', '1.5', 'abc', '31536001'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                security_settings(production(SCHED_EASE_HSTS_SECONDS=value))

    def test_http_redirect_and_no_forwarded_header_trust_by_default(self):
        with override_settings(**security_settings(production()), ROOT_URLCONF=__name__):
            response = self.client.get('/?x=1', HTTP_HOST='school.test', HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response['Location'], 'https://school.test/?x=1')
            self.assertNotIn('Strict-Transport-Security', response)
            self.assertEqual(self.client.get('/', HTTP_HOST='unapproved.test').status_code, 400)

    def test_trusted_proxy_opt_in_prevents_redirect_loop(self):
        config = security_settings(production(SCHED_EASE_TRUST_PROXY='true', SCHED_EASE_HSTS_SECONDS='300'))
        with override_settings(**config, ROOT_URLCONF=__name__):
            response = self.client.get('/', HTTP_HOST='school.test', HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Strict-Transport-Security'], 'max-age=300')
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(response['X-Frame-Options'], 'DENY')
            self.assertEqual(response['Referrer-Policy'], 'same-origin')

    def test_native_https_and_private_error_response(self):
        with override_settings(**security_settings(production()), ROOT_URLCONF=__name__):
            response = Client(raise_request_exception=False).get('/broken/', secure=True, HTTP_HOST='school.test')
            self.assertEqual(response.status_code, 500)
            for private in (b'PRIVATE_EXCEPTION_SENTINEL', b'Traceback', b'SECRET_KEY'):
                self.assertNotIn(private, response.content)

    def test_development_http_remains_available(self):
        config = security_settings({})
        self.assertTrue(config['DEBUG'])
        self.assertFalse(config['SESSION_COOKIE_SECURE'])
        self.assertFalse(config['CSRF_COOKIE_SECURE'])
        self.assertFalse(config['CSRF_COOKIE_HTTPONLY'])
        self.assertIsNone(config['SECURE_PROXY_SSL_HEADER'])
        self.assertEqual(config['SECURE_HSTS_SECONDS'], 0)
        with override_settings(**config, ROOT_URLCONF=__name__):
            response = self.client.get('/', HTTP_HOST='localhost')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Strict-Transport-Security', response)

    def test_production_module_does_not_load_local_dotenv(self):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith('SCHED_EASE_') and key not in ('SECRET_KEY', 'DATABASE_URL')}
        env.update(production())
        script = ('from unittest.mock import patch; '
                  'from django.conf import settings; '
                  'from dotenv import load_dotenv; '
                  'guard=patch("dotenv.load_dotenv", side_effect=AssertionError("dotenv loaded")); '
                  'guard.start(); import sched_ease.settings as s; '
                  'assert s.DEBUG is False and s.SECURE_SSL_REDIRECT; '
                  'assert s.STATIC_ROOT != s.STATICFILES_DIRS[0]')
        result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, 'Production module startup failed; output withheld.')
        del env['SCHED_EASE_SECRET_KEY']
        result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'ImproperlyConfigured', result.stderr)


@override_settings(**security_settings(production()))
class ProductionAuthenticationTests(TestCase):
    def test_https_login_csrf_roles_and_logout(self):
        for role in (Role.ADMIN, Role.FACULTY, Role.STUDENT):
            with self.subTest(role=role):
                user = User.objects.create_user(username=role, password='test-password-only')
                Profile.objects.create(user=user, role=role)
                client = Client(enforce_csrf_checks=True, HTTP_HOST='school.test')
                page = client.get('/accounts/login/', secure=True)
                self.assertEqual(page.status_code, 200)
                cookie = page.cookies['csrftoken']
                self.assertTrue(cookie['secure'])
                self.assertTrue(cookie['httponly'])
                self.assertEqual(cookie['samesite'], 'Lax')
                payload = {'username': role, 'password': 'test-password-only'}
                self.assertEqual(client.post('/accounts/login/', payload, secure=True).status_code, 403)
                payload['csrfmiddlewaretoken'] = cookie.value
                response = client.post('/accounts/login/', payload, secure=True, HTTP_ORIGIN='https://school.test')
                self.assertEqual(response.status_code, 302)
                session = response.cookies['sessionid']
                self.assertTrue(session['secure'])
                self.assertTrue(session['httponly'])
                self.assertEqual(session['samesite'], 'Lax')
                self.assertEqual(client.get('/dashboard/', secure=True).status_code, 200)
                response = client.post('/accounts/logout/', {'csrfmiddlewaretoken': client.cookies['csrftoken'].value},
                                       secure=True, HTTP_ORIGIN='https://school.test')
                self.assertEqual(response.status_code, 302)
                self.assertNotIn('_auth_user_id', client.session)

    def test_cross_origin_login_is_not_implicitly_trusted(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST='school.test')
        client.get('/accounts/login/', secure=True)
        response = client.post('/accounts/login/', {'csrfmiddlewaretoken': client.cookies['csrftoken'].value},
                               secure=True, HTTP_ORIGIN='https://unapproved.test')
        self.assertEqual(response.status_code, 403)
