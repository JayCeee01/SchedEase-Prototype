"""Task 6.3: diagnostic access at HTTP boundaries, including alternate admin URLs."""
from datetime import time
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission, User
from django.test import override_settings
from django.urls import reverse

from . import models as m
from .test_known_defects import SchedulingDefectFixture


class DiagnosticAccessTests(SchedulingDefectFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser('diagnostic-root', password='test')
        cls.role_admin = User.objects.create_user('diagnostic-role-admin')
        m.Profile.objects.create(user=cls.role_admin, role=m.Role.ADMIN)
        cls.faculty_user = User.objects.create_user('diagnostic-faculty')
        m.Profile.objects.create(user=cls.faculty_user, role=m.Role.FACULTY)
        cls.faculty.user = cls.faculty_user
        cls.faculty.save()
        cls.student_user = User.objects.create_user('diagnostic-student')
        m.Profile.objects.create(user=cls.student_user, role=m.Role.STUDENT)
        m.Student.objects.create(user=cls.student_user, student_number='ACCESS', full_name='Student', section=cls.section)
        cls.plain_user = User.objects.create_user('diagnostic-no-role')
        cls.generation_run = m.GenerationRun.objects.create(term=cls.term, requested_name='INTERNAL-RUN', status='FAILED',
            reproducibility={'seed': 456, 'inputs': {'schema': 'v1', 'sha256': 'PRIVATE-FINGERPRINT', 'counts': {'meetings': 2}}})
        cls.issue = m.GenerationIssue.objects.create(run=cls.generation_run, category='INVALID_DATA',
            short_description='PRIVATE-DIAGNOSTIC', reason='PRIVATE-REASON',
            details={'meeting_ids': [cls.meetings[0].pk], 'constraint': {'private': 'PRIVATE-CONSTRAINT'}},
            assignment=cls.meetings[0])
        cls.draft = m.Schedule.objects.create(term=cls.term, name='Internal draft')
        cls.entry = cls.draft.entries.create(assignment=cls.meetings[0], room=cls.room,
            day=0, start_time=time(8), end_time=time(9))
        cls.audit = m.ScheduleEntryAudit.objects.create(schedule=cls.draft, entry=cls.entry,
            user=cls.admin, previous_values={'reason': 'PRIVATE-AUDIT'}, new_values={})
        cls.override = m.CredentialOverride.objects.create(subject=cls.subject, faculty=cls.faculty,
            admin_user=cls.admin, reason='PRIVATE-OVERRIDE', missing_credentials='Internal license')
        cls.published = m.Schedule.objects.create(term=cls.term, name='Permitted timetable')
        for i, meeting in enumerate(cls.meetings):
            cls.published.entries.create(assignment=meeting, room=cls.room, day=0,
                start_time=time(8+i), end_time=time(9+i))
        cls.published.status = 'PUBLISHED'
        cls.published.save(update_fields=['status'])
        cls.batch = m.AcademicImport.objects.create(user=cls.admin, payload={})

    def setUp(self):
        self.client.force_login(self.admin)

    def assert_private_absent(self, response):
        for text in ('PRIVATE-DIAGNOSTIC', 'PRIVATE-REASON', 'PRIVATE-FINGERPRINT', 'PRIVATE-CONSTRAINT',
                     'PRIVATE-AUDIT', 'PRIVATE-OVERRIDE', 'Traceback (most recent call last)', 'private-server-path'):
            self.assertNotIn(text.encode(), response.content)

    def restricted_urls(self):
        return [reverse('generation_error_log') + '?page=2&run_page=2&severity=ERROR&sort=reason&q=PRIVATE',
                reverse('generation_error_detail', args=[self.issue.pk]),
                reverse('generation_error_detail', args=[999999]),
                reverse('generation_run_detail', args=[self.generation_run.pk]),
                reverse('generation_run_detail', args=[uuid4()]), reverse('generate_schedule'),
                reverse('resource_list', args=['credential-overrides']),
                reverse('entry_create', args=[self.draft.pk]),
                reverse('entry_update', args=[self.draft.pk, self.entry.pk])]

    def test_non_admin_roles_and_anonymous_cannot_read_or_post_diagnostics(self):
        for user in (self.faculty_user, self.student_user, self.plain_user, None):
            self.client.force_login(user) if user else self.client.logout()
            for url in self.restricted_urls():
                for method in (self.client.get, self.client.post):
                    with self.subTest(user=user, url=url, method=method.__name__):
                        response = method(url, {'status': 'RESOLVED'}, HTTP_ACCEPT='application/json',
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
                        self.assertEqual(response.status_code, 302)
                        self.assert_private_absent(response)
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, 'OPEN')

    def test_access_denied_before_recovery_or_record_lookup(self):
        self.client.force_login(self.plain_user)
        with patch('schedules.views.recover_stale_runs') as recovery, patch('schedules.views.get_object_or_404') as lookup:
            for url in self.restricted_urls()[:5]:
                self.client.get(url)
            recovery.assert_not_called()
            lookup.assert_not_called()

    def test_admin_and_role_admin_can_read_history_issues_and_metadata(self):
        for user in (self.admin, self.role_admin):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse('generation_error_log')), 'PRIVATE-DIAGNOSTIC')
            self.assertContains(self.client.get(reverse('generation_error_detail', args=[self.issue.pk])), 'PRIVATE-REASON')
            self.assertContains(self.client.get(reverse('generation_run_detail', args=[self.generation_run.pk])), 'PRIVATE-FINGERPRINT')
            self.assertEqual(self.client.get(reverse('generation_error_detail', args=[999999])).status_code, 404)
            self.assertEqual(self.client.get(reverse('generation_run_detail', args=[uuid4()])).status_code, 404)

    def test_admin_issue_status_update(self):
        self.client.force_login(self.role_admin)
        response = self.client.post(reverse('generation_error_detail', args=[self.issue.pk]), {'status': 'REVIEWED'})
        self.assertEqual(response.status_code, 302)
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, 'REVIEWED')
        self.assertEqual(self.issue.reason, 'PRIVATE-REASON')

    def test_admin_filtered_pagination_and_history_remain_available(self):
        for i in range(23):
            m.GenerationIssue.objects.create(run=self.generation_run, category='INVALID_DATA', short_description=f'Match {i}', reason='Matched')
        response = self.client.get(reverse('generation_error_log'), {'run': self.generation_run.pk, 'term': self.term.pk,
            'severity': 'ERROR', 'q': 'Match', 'page': 2, 'run_q': 'INTERNAL'})
        self.assertEqual(response.context['summary']['total'], 23)
        self.assertEqual(len(response.context['issues']), 3)
        self.assertEqual(len(response.context['runs']), 1)
        self.assertIn('severity=ERROR', response.context['issue_pagination']['previous'])

    @override_settings(DEBUG=True)
    def test_invalid_filters_cannot_trigger_debug_tracebacks(self):
        for key, value in [('run', 'not-a-uuid'), ('term', 'abc'), ('subject', '9'*100),
                           ('section', '-1'), ('faculty', '1 OR 1=1'), ('room', 'abc'),
                           ('date', '2026-99-99'), ('category', 'FAKE'), ('severity', 'FAKE'), ('status', 'FAKE')]:
            with self.subTest(filter=key):
                response = self.client.get(reverse('generation_error_log'), {key: value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['summary']['total'], 0)
                self.assertContains(response, 'Check this filter or clear it')
                self.assertNotContains(response, 'Traceback')
                self.assertNotContains(response, 'site-packages')

    def test_unknown_valid_filter_ids_return_no_issues(self):
        for key, value in [('run', uuid4()), ('term', 999999), ('subject', 999999)]:
            response = self.client.get(reverse('generation_error_log'), {key: value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['summary']['total'], 0)

    def test_json_draft_endpoint_and_correction_posts_are_admin_only(self):
        for user in (self.faculty_user, self.student_user, self.plain_user, None):
            self.client.force_login(user) if user else self.client.logout()
            for url in (reverse('save_form_draft'), reverse('entry_apply_suggestion', args=[self.draft.pk, self.entry.pk]),
                        reverse('entry_remove', args=[self.draft.pk, self.entry.pk])):
                response = self.client.post(url, '{}', content_type='application/json')
                self.assertEqual(response.status_code, 302)
                self.assert_private_absent(response)
        self.assertTrue(m.ScheduleEntry.objects.filter(pk=self.entry.pk).exists())

    def test_import_diagnostic_download_is_role_and_owner_scoped(self):
        url = reverse('academic_import_errors', args=[self.batch.pk])
        for user in (self.faculty_user, self.student_user, self.plain_user):
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assert_private_absent(response)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.role_admin)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_faculty_student_timetables_exports_and_hidden_content(self):
        for user in (self.faculty_user, self.student_user):
            self.client.force_login(user)
            for name, args in [('dashboard', []), ('browse_schedules', []), ('schedule_detail', [self.published.pk]),
                               ('export_csv', [self.published.pk]), ('export_pdf', [self.published.pk])]:
                with self.subTest(user=user, endpoint=name):
                    response = self.client.get(reverse(name, args=args), {'check': '1', 'run': self.generation_run.pk})
                    self.assertEqual(response.status_code, 200)
                    self.assert_private_absent(response)
                    self.assertNotIn(reverse('generation_error_log').encode(), response.content)
            for name in ('schedule_detail', 'export_csv', 'export_pdf'):
                response = self.client.get(reverse(name, args=[self.draft.pk]))
                self.assertEqual(response.status_code, 404)
                self.assert_private_absent(response)

    def test_faculty_retains_own_availability_validation(self):
        self.client.force_login(self.faculty_user)
        response = self.client.post(reverse('my_availability_create'),
            {'day': 0, 'start_time': '12:00', 'end_time': '09:00', 'kind': 'AVAILABLE'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assert_private_absent(response)

    def test_admin_retains_draft_conflict_feedback(self):
        response = self.client.get(reverse('schedule_detail', args=[self.draft.pk]), {'check': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_manage'])
        self.assertTrue(response.context['conflicts'])  # One required meeting is missing.

    def test_staff_model_permissions_do_not_bypass_diagnostic_role(self):
        for user in (self.faculty_user, self.student_user, self.plain_user):
            user.is_staff = True
            user.save(update_fields=['is_staff'])
            user.user_permissions.add(*Permission.objects.filter(content_type__app_label='schedules',
                content_type__model__in=['scheduleentryaudit', 'credentialoverride']))
            self.client.force_login(user)
            for model, pk in [('scheduleentryaudit', self.audit.pk), ('credentialoverride', self.override.pk)]:
                for action, args in [('changelist', []), ('change', [pk]), ('history', [pk]), ('delete', [pk]), ('add', [])]:
                    url = reverse(f'admin:schedules_{model}_{action}', args=args)
                    for method in (self.client.get, self.client.post):
                        response = method(url)
                        self.assertEqual(response.status_code, 403)
                        self.assert_private_absent(response)
            self.assertTrue(m.ScheduleEntryAudit.objects.filter(pk=self.audit.pk).exists())
            self.assertTrue(m.CredentialOverride.objects.filter(pk=self.override.pk).exists())

    def test_django_admin_still_requires_model_permission_and_allows_authorized_admin(self):
        url = reverse('admin:schedules_scheduleentryaudit_change', args=[self.audit.pk])
        self.role_admin.is_staff = True
        self.role_admin.save(update_fields=['is_staff'])
        self.client.force_login(self.role_admin)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.role_admin.user_permissions.add(Permission.objects.get(codename='view_scheduleentryaudit'))
        self.assertContains(self.client.get(url), 'PRIVATE-AUDIT')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), 'PRIVATE-AUDIT')

    def test_unexpected_generation_failure_is_logged_not_disclosed(self):
        settings = m.GASettings.objects.create(name='Privacy')
        with (patch('schedules.views.GeneticScheduler.generate', side_effect=RuntimeError('private-server-path')),
              patch('schedules.views.logger.exception') as logged):
            response = self.client.post(reverse('generate_schedule'),
                {'term': self.term.pk, 'settings': settings.pk, 'name': 'Failure'})
        logged.assert_called()
        self.assert_private_absent(response)
        self.assertFalse(m.GenerationIssue.objects.filter(reason__contains='private-server-path').exists())
