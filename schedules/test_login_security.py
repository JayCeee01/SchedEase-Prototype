"""Synthetic login tests; no live Redis service or academic database is used."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch, Mock

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, TestCase, SimpleTestCase, RequestFactory, override_settings
from django.contrib.auth.forms import AuthenticationForm

from sched_ease.login_security import login_settings, check_login_storage
from .auth_forms import INVALID
from .models import Profile, Role
from .services import login_limit as limit


@override_settings(LOGIN_MAX_FAILURES=5, LOGIN_SOURCE_MAX_FAILURES=50,
                   LOGIN_WINDOW_SECONDS=900, LOGIN_BLOCK_SECONDS=900, LOGIN_TRUSTED_PROXIES=[])
class LoginSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='login-test', email='login@example.invalid', password='synthetic-password')
        Profile.objects.create(user=cls.user, role=Role.STUDENT)
        cls.admin = User.objects.create_superuser(username='login-admin', password='synthetic-password')

    def setUp(self):
        self.store = limit.MemoryStore()
        self.patch = patch.object(limit, 'get_store', return_value=self.store)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.clock = patch.object(limit, 'monotonic', return_value=1000)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)

    def post(self, identifier='login-test', password='wrong', path='/', client=None, **extra):
        return (client or self.client).post(path, {'username': identifier, 'password': password}, **extra)

    def fail_five(self):
        for _ in range(5):
            response = self.post()
            self.assertContains(response, INVALID)

    def test_success_and_session_rotation(self):
        session = self.client.session
        session['sentinel'] = True
        session.save()
        old_key = session.session_key
        response = self.post(password='synthetic-password')
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))
        self.assertNotEqual(old_key, self.client.session.session_key)

    def test_wrong_password_keeps_popup_open(self):
        response = self.post()
        self.assertContains(response, INVALID)
        self.assertContains(response, 'login-modal-shell is-open')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_threshold_blocks_correct_password_and_new_sessions(self):
        self.fail_five()
        response = self.post(password='synthetic-password', client=Client())
        self.assertContains(response, limit.BUSY)
        self.assertContains(response, 'login-modal-shell is-open')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_block_expiry_is_not_extended_by_rejected_requests(self):
        self.fail_five()
        self.now.return_value = 1899
        self.assertContains(self.post(), limit.BUSY)
        self.now.return_value = 1900
        self.assertEqual(self.post(password='synthetic-password').status_code, 302)

    def test_rolling_window_discards_old_failures(self):
        for _ in range(4): self.post()
        self.now.return_value = 1900
        self.assertContains(self.post(), INVALID)
        self.assertEqual(self.post(password='synthetic-password').status_code, 302)

    def test_email_alias_shares_username_budget(self):
        self.fail_five()
        self.assertContains(self.post('LOGIN@EXAMPLE.INVALID', 'synthetic-password'), limit.BUSY)

    def test_email_login_success(self):
        self.assertEqual(self.post('LOGIN@EXAMPLE.INVALID', 'synthetic-password').status_code, 302)

    def test_unknown_and_inactive_have_same_errors(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        for identifier in ('login-test', 'missing-user', 'missing@example.invalid'):
            with self.subTest(identifier=identifier):
                response = self.post(identifier, 'synthetic-password')
                self.assertEqual(list(response.context['login_form'].non_field_errors()), [INVALID])
                self.assertNotIn('_auth_user_id', self.client.session)

    def test_unknown_user_uses_django_dummy_password_hash(self):
        with patch('django.contrib.auth.models.User.set_password') as dummy:
            self.post('not-a-real-user')
        dummy.assert_called_once()

    def test_remember_me(self):
        for remember in (False, True):
            self.client.logout()
            payload = {'username': 'login-test', 'password': 'synthetic-password'}
            if remember: payload['remember_me'] = 'on'
            self.assertEqual(self.client.post('/', payload).status_code, 302)
            self.assertEqual(self.client.session.get_expire_at_browser_close(), not remember)

    def test_roles_and_account_login_redirects(self):
        for role in (Role.ADMIN, Role.FACULTY, Role.STUDENT):
            Profile.objects.filter(user=self.user).update(role=role)
            self.client.logout()
            self.assertEqual(self.post(password='synthetic-password', path='/accounts/login/').status_code, 302)
            self.assertEqual(self.client.get('/dashboard/').status_code, 200)

    def test_admin_and_account_endpoints_share_failure_budget(self):
        for path in ('/admin/login/', '/accounts/login/', '/', '/accounts/login/', '/admin/login/'):
            self.post('login-admin', path=path)
        for path in ('/', '/accounts/login/', '/admin/login/'):
            self.assertContains(self.post('login-admin', 'synthetic-password', path), limit.BUSY)

    def test_admin_login_retains_staff_requirement(self):
        self.assertContains(self.post(password='synthetic-password', path='/admin/login/'), INVALID)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.post('login-admin', 'synthetic-password', '/admin/login/').status_code, 302)

    def test_one_source_cannot_lock_account_at_other_source(self):
        self.fail_five()
        self.assertEqual(self.post(password='synthetic-password', REMOTE_ADDR='192.0.2.2').status_code, 302)

    @override_settings(LOGIN_SOURCE_MAX_FAILURES=3)
    def test_source_budget_prevents_identifier_rotation(self):
        for identifier in ('missing1', 'missing2', 'missing3'): self.post(identifier)
        self.assertContains(self.post(password='synthetic-password'), limit.BUSY)

    @override_settings(LOGIN_MAX_FAILURES=2)
    def test_threshold_override_and_success_reset(self):
        self.post()
        self.assertEqual(self.post(password='synthetic-password').status_code, 302)
        self.client.logout()
        self.post()
        self.assertContains(self.post(), INVALID)
        self.assertContains(self.post(), limit.BUSY)

    def test_storage_failure_before_authentication_fails_closed(self):
        with patch.object(limit, 'get_store', side_effect=RuntimeError('private-redis-credential')):
            with patch.object(AuthenticationForm, 'clean') as authentication:
                response = self.post(password='synthetic-password')
        authentication.assert_not_called()
        self.assertContains(response, limit.UNAVAILABLE)
        self.assertNotContains(response, 'private-redis-credential')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_storage_failure_after_authentication_fails_closed(self):
        original = self.store.operation
        def operation(action, *args):
            if action == 'success': raise RuntimeError('private-error')
            return original(action, *args)
        with patch.object(self.store, 'operation', side_effect=operation):
            response = self.post(password='synthetic-password')
        self.assertContains(response, limit.UNAVAILABLE)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_csrf_all_login_routes(self):
        for path in ('/', '/accounts/login/', '/admin/login/'):
            client = Client(enforce_csrf_checks=True)
            with patch.object(limit, 'begin') as begin:
                self.assertEqual(self.post(path=path, client=client).status_code, 403)
            begin.assert_not_called()

    def test_logging_never_contains_identifiers_or_credentials(self):
        with self.assertLogs('schedease.authentication', level='INFO') as captured:
            self.post()
            self.post(password='synthetic-password')
        log = '\n'.join(captured.output)
        for value in ('login-test', 'synthetic-password', '127.0.0.1', 'login@example.invalid'):
            self.assertNotIn(value, log)

    def test_spoofed_forwarded_headers_do_not_bypass_limits(self):
        self.fail_five()
        self.assertContains(self.post(HTTP_X_FORWARDED_FOR='192.0.2.2', HTTP_X_REAL_IP='192.0.2.2'), limit.BUSY)

    @override_settings(LOGIN_TRUSTED_PROXIES=['192.0.2.0/24'])
    def test_trusted_proxy_accepts_only_single_valid_real_ip(self):
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_REAL_IP='198.51.100.1')
        self.assertEqual(limit.client_source(request), '198.51.100.1')
        self.assertContains(self.post(REMOTE_ADDR='192.0.2.1', HTTP_X_REAL_IP='a,b'), limit.UNAVAILABLE)


@override_settings(LOGIN_MAX_FAILURES=5, LOGIN_SOURCE_MAX_FAILURES=50,
                   LOGIN_WINDOW_SECONDS=900, LOGIN_BLOCK_SECONDS=900)
class LoginStorageTests(SimpleTestCase):
    def test_concurrent_source_admission_and_stale_owner(self):
        store, barrier = limit.MemoryStore(), Barrier(2)
        def attempt(token):
            barrier.wait()
            try:
                store.operation('begin', 'source', 'pair', token)
                return token
            except limit.Restricted: return None
        with patch.object(limit, 'monotonic', return_value=10):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, ['one', 'two']))
        owner = next(token for token in results if token)
        self.assertEqual(sum(token is not None for token in results), 1)
        with patch.object(limit, 'monotonic', return_value=71):
            store.operation('begin', 'source', 'pair', 'replacement')
            with self.assertRaises(RuntimeError): store.operation('success', 'source', 'pair', owner)
            store.operation('success', 'source', 'pair', 'replacement')

    @override_settings(LOGIN_REDIS_URL='redis://localhost:6379/15')
    def test_redis_contract_uses_atomic_script_shared_keys_and_timeouts(self):
        with patch('redis.Redis.from_url') as constructor:
            constructor.return_value.eval.return_value = 1
            a, b = limit.RedisStore(), limit.RedisStore()
            a.operation('begin', 'source-hash', 'pair-hash', 'one')
            b.operation('failure', 'source-hash', 'pair-hash', 'one')
            args = constructor.return_value.eval.call_args.args
            self.assertEqual(args[1], 5)
            self.assertTrue(all('{source-hash}' in key for key in args[2:7]))
            self.assertEqual(constructor.call_args.kwargs['socket_timeout'], 2)
            constructor.return_value.eval.return_value = 0
            with self.assertRaises(limit.Restricted): a.operation('begin', 's', 'p', 't')
            constructor.return_value.eval.return_value = -1
            with self.assertRaises(RuntimeError): a.operation('success', 's', 'p', 't')

    def test_configuration_defaults_and_invalid_values(self):
        config = login_settings({})
        self.assertEqual(config['LOGIN_MAX_FAILURES'], 5)
        self.assertEqual(config['LOGIN_STORAGE'], 'memory')
        self.assertEqual(login_settings({'SCHED_EASE_ENV': 'production'})['LOGIN_STORAGE'], 'redis')
        for env in ({'SCHED_EASE_ENV': 'production', 'SCHED_EASE_LOGIN_STORAGE': 'memory'},
                    {'SCHED_EASE_LOGIN_MAX_FAILURES': '0'}, {'SCHED_EASE_LOGIN_WINDOW_SECONDS': 'invalid'},
                    {'SCHED_EASE_LOGIN_TRUSTED_PROXIES': 'not-a-proxy'}, {'SCHED_EASE_LOGIN_STORAGE': 'unknown'}):
            with self.assertRaises(ImproperlyConfigured): login_settings(env)

    @override_settings(LOGIN_STORAGE='memory', LOGIN_MEMORY_ALLOWED=False)
    def test_memory_cannot_be_used_when_disallowed(self):
        with self.assertRaises(RuntimeError): limit.get_store()

    def test_deployment_configuration_check(self):
        with override_settings(LOGIN_STORAGE='redis', LOGIN_REDIS_URL=''):
            self.assertEqual(check_login_storage(None)[0].id, 'schedease.E001')
        with override_settings(LOGIN_STORAGE='redis', LOGIN_REDIS_URL='rediss://redis.example.invalid:6379/0'):
            self.assertEqual(check_login_storage(None), [])
