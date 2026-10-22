"""M3: approvals, entry writes, audits and revisions commit as one operation."""
from datetime import time
from threading import Event, Thread
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import OperationalError, connections
from django.test import TransactionTestCase
from . import models as m
from .services.manual_edits import FIELDS, revision_token, save_manual_entry
from .test_known_defects import SchedulingDefectFixture


class ManualTransactionTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='manual', password='test')
        self.client.force_login(self.admin)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Draft')
        self.entry = self.schedule.entries.create(assignment=self.meetings[0], room=self.room,
                         day=0, start_time=time(8), end_time=time(9))
        self.url = f'/schedules/{self.schedule.pk}/entry/{self.entry.pk}/edit/'
        self.baseline = self.schedule.updated_at

    def payload(self):
        return {'revision': self.client.get(self.url).context['form'].initial['revision'],
                'assignment': self.meetings[0].pk, 'room': self.room.pk, 'day': 1,
                'start_time': '08:00', 'end_time': '09:00'}

    def require_override(self):
        credential = m.Credential.objects.create(name='License')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)

    def assert_unchanged(self):
        self.entry.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertEqual(self.entry.day, 0)
        self.assertEqual(self.schedule.updated_at, self.baseline)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())
        self.assertFalse(m.CredentialOverride.objects.exists())

    def test_successful_edit_has_exact_audit_and_new_revision(self):
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        audit = m.ScheduleEntryAudit.objects.get()
        self.assertEqual(audit.previous_values['day'], '0')
        self.assertEqual(audit.new_values['day'], '1')
        self.assertEqual(audit.user_id, self.admin.pk)
        self.schedule.refresh_from_db()
        self.assertNotEqual(self.schedule.updated_at, self.baseline)

    def test_two_editors_with_same_revision_cannot_overwrite(self):
        first, second = self.payload(), self.payload()
        self.assertEqual(self.client.post(self.url, first).status_code, 302)
        second['day'] = 2
        self.assertContains(self.client.post(self.url, second), 'changed while you were editing')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.day, 1)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)

    def test_direct_update_without_timestamp_change_is_detected(self):
        payload = self.payload()
        m.ScheduleEntry.objects.filter(pk=self.entry.pk).update(day=3)
        self.assertContains(self.client.post(self.url, payload), 'changed while you were editing')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.day, 3)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.updated_at, self.baseline)

    def test_override_and_entry_rollback_when_audit_save_fails(self):
        self.require_override()
        payload = {**self.payload(), 'credential_override_confirm': 'yes', 'credential_override_reason': 'Approved'}
        with patch.object(m.ScheduleEntryAudit.objects, 'create', side_effect=RuntimeError('private detail')):
            response = self.client.post(self.url, payload)
        self.assertContains(response, 'Nothing was changed')
        self.assertNotContains(response, 'private detail')
        self.assert_unchanged()

    def test_override_rollback_when_final_validation_fails(self):
        self.require_override()
        proposed = {field: getattr(self.entry, field) for field in FIELDS}
        proposed.update(start_time=time(19), end_time=time(20))
        with self.assertRaises(ValidationError):
            save_manual_entry(schedule_id=self.schedule.pk, entry_id=self.entry.pk, actor=self.admin,
                revision=revision_token(self.schedule, self.admin, self.entry), proposed=proposed,
                confirmed=True, reason='Approved')
        self.assert_unchanged()

    def test_missing_reason_leaves_no_override_or_audit(self):
        self.require_override()
        payload = {**self.payload(), 'credential_override_confirm': 'yes', 'credential_override_reason': ' '}
        self.assertContains(self.client.post(self.url, payload), 'Override reason is required')
        self.assert_unchanged()

    def test_stale_override_confirmation_cannot_commit(self):
        self.require_override()
        payload = self.payload()
        self.assertContains(self.client.post(self.url, payload), 'Credential Override Required')
        m.ScheduleEntry.objects.filter(pk=self.entry.pk).update(day=2)
        payload.update(credential_override_confirm='yes', credential_override_reason='Approved')
        self.assertContains(self.client.post(self.url, payload), 'changed while you were editing')
        self.assertFalse(m.CredentialOverride.objects.exists())
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())

    def test_status_is_rechecked_after_outer_form_validation(self):
        payload = self.payload()
        from .services.manual_edits import save_manual_entry as real_save
        def finalize_then_save(**kwargs):
            m.Schedule.objects.filter(pk=self.schedule.pk).update(status='PUBLISHED')
            return real_save(**kwargs)
        with patch('schedules.services.manual_edits.save_manual_entry', side_effect=finalize_then_save):
            self.assertContains(self.client.post(self.url, payload), 'changed while you were editing')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.day, 0)
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())

    def test_token_is_required_and_cannot_be_tampered_with(self):
        payload = self.payload()
        payload.pop('revision')
        self.assertContains(self.client.post(self.url, payload), 'edit revision is missing')
        payload['revision'] = 'tampered'
        self.assertContains(self.client.post(self.url, payload), 'missing or expired')
        self.assert_unchanged()

    def test_lock_error_is_actionable_and_changes_nothing(self):
        payload = self.payload()
        with patch('schedules.services.manual_edits.Schedule.objects.filter', side_effect=OperationalError('database is locked')):
            self.assertContains(self.client.post(self.url, payload), 'schedule changed or is busy')
        self.assert_unchanged()

    def test_service_rechecks_administrator_permission(self):
        token = revision_token(self.schedule, self.admin, self.entry)
        User.objects.filter(pk=self.admin.pk).update(is_superuser=False)
        proposed = {field: getattr(self.entry, field) for field in FIELDS}
        with self.assertRaisesMessage(ValidationError, 'authorized administrator'):
            save_manual_entry(schedule_id=self.schedule.pk, entry_id=self.entry.pk, actor=self.admin,
                              revision=token, proposed=proposed)
        self.assert_unchanged()

    def test_new_entry_and_approval_receive_audit_together(self):
        self.require_override()
        url = f'/schedules/{self.schedule.pk}/entry/new/'
        token = self.client.get(url).context['form'].initial['revision']
        response = self.client.post(url, {'revision': token, 'assignment': self.meetings[1].pk,
            'room': self.room.pk, 'day': 0, 'start_time': '09:00', 'end_time': '10:00',
            'credential_override_confirm': 'yes', 'credential_override_reason': 'Approved second meeting'})
        self.assertEqual(response.status_code, 302)
        audit = m.ScheduleEntryAudit.objects.get()
        self.assertEqual(audit.previous_values, {})
        self.assertEqual(audit.new_values['assignment_id'], str(self.meetings[1].pk))
        self.assertEqual(m.CredentialOverride.objects.get().assignment_id, self.meetings[1].pk)


class ConcurrentManualSaveTests(TransactionTestCase):
    def test_sqlite_competing_writers_cannot_both_commit(self):
        # Real independent connections, outside TestCase's enclosing transaction.
        SchedulingDefectFixture.setUpTestData.__func__(type(self))
        admin = User.objects.create_superuser(username='concurrent', password='test')
        schedule = m.Schedule.objects.create(term=self.term, name='Concurrent draft')
        entry = schedule.entries.create(assignment=self.meetings[0], room=self.room, day=0,
                                        start_time=time(8), end_time=time(9))
        token = revision_token(schedule, admin, entry)
        original = {field: getattr(entry, field) for field in FIELDS}
        locked, release, second_started = Event(), Event(), Event()
        outcomes = []
        clean = m.ScheduleEntry.full_clean

        def paused_clean(obj, *args, **kwargs):
            if obj.day == 1:
                locked.set()
                if not release.wait(10):
                    raise RuntimeError('Test writer was not released')
            return clean(obj, *args, **kwargs)

        def save(day):
            try:
                if day == 2:
                    second_started.set()
                save_manual_entry(schedule_id=schedule.pk, entry_id=entry.pk, actor=admin,
                    revision=token, proposed={**original, 'day': day})
                outcomes.append(('saved', day))
            except (ValidationError, OperationalError) as exc:
                outcomes.append(('rejected', type(exc).__name__))
            except Exception as exc:
                outcomes.append(('unexpected', repr(exc)))
            finally:
                connections.close_all()

        first = Thread(target=save, args=(1,))
        second = Thread(target=save, args=(2,))
        with patch.object(m.ScheduleEntry, 'full_clean', paused_clean):
            first.start()
            try:
                self.assertTrue(locked.wait(10))
                second.start()
                self.assertTrue(second_started.wait(10))
            finally:
                release.set()
                first.join(10)
                if second.ident is not None:
                    second.join(10)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(sorted(item[0] for item in outcomes), ['rejected', 'saved'], outcomes)
        entry.refresh_from_db()
        self.assertEqual(entry.day, 1)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)
