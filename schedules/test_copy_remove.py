"""M2: independent placements, transactional removal and finalized history."""
from datetime import time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.manual_edits import copy_to_draft, remove_manual_entry, revision_token, FIELDS


class CopyRemoveTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='copy-admin', password='test')
        self.client.force_login(self.admin)
        self.source = m.Schedule.objects.create(term=self.term, name='Official')
        for i, meeting in enumerate(self.meetings):
            self.source.entries.create(assignment=meeting, room=self.room, day=0,
                                       start_time=time(8+i), end_time=time(9+i))
        self.source_audit = m.ScheduleEntryAudit.objects.create(schedule=self.source, entry=self.source.entries.first(),
                           user=self.admin, previous_values={'day': 1}, new_values={'day': 0})
        self.source.status = 'PUBLISHED'
        self.source.save(update_fields=['status'])
        self.original = list(self.source.entries.order_by('pk').values())
        self.version = self.source.updated_at

    def copy(self):
        return copy_to_draft(source_id=self.source.pk, actor=self.admin)

    def removal(self, draft):
        entry = draft.entries.order_by('pk').first()
        url = f'/schedules/{draft.pk}/entry/{entry.pk}/remove/'
        page = self.client.get(url)
        return entry, url, {'revision': page.context['revision'], 'confirm_remove': 'yes'}

    def assert_source_unchanged(self):
        self.source.refresh_from_db()
        self.source_audit.refresh_from_db()
        self.assertEqual(self.source.updated_at, self.version)
        self.assertEqual(list(self.source.entries.order_by('pk').values()), self.original)
        self.assertEqual(self.source.edit_audits.count(), 1)
        self.assertEqual(self.source_audit.previous_values, {'day': 1})
        self.assertEqual(self.source_audit.new_values, {'day': 0})

    def test_copy_preserves_fields_with_independent_entry_identities(self):
        draft = self.copy()
        self.assertNotEqual(draft.pk, self.source.pk)
        self.assertEqual(draft.status, 'DRAFT')
        self.assertEqual(draft.term_id, self.source.term_id)
        self.assertIsNone(draft.published_at)
        self.assertIsNone(draft.archived_at)
        self.assertIsNone(draft.replaced_by_id)
        for original, copied in zip(self.source.entries.order_by('pk'), draft.entries.order_by('pk')):
            self.assertNotEqual(original.pk, copied.pk)
            self.assertEqual([getattr(original, field) for field in FIELDS], [getattr(copied, field) for field in FIELDS])
        self.assertEqual(draft.edit_audits.get().new_values['source_schedule_id'], self.source.pk)
        self.assertEqual(m.Assignment.objects.count(), 1)
        self.assertEqual(m.TeachingAssignment.objects.count(), 2)
        self.assert_source_unchanged()

    def test_archived_copy_and_ui(self):
        from .protection import archive_transition
        self.source.status = 'ARCHIVED'
        with archive_transition():
            self.source.save(update_fields=['status'])
        response = self.client.get(f'/schedules/{self.source.pk}/')
        self.assertContains(response, 'Copy to Draft')
        self.assertNotContains(response, 'Restore &amp; Publish')
        self.assertNotContains(response, 'Remove Meeting')
        result = self.client.post(f'/schedules/{self.source.pk}/copy-to-draft/')
        draft = m.Schedule.objects.get(status='DRAFT')
        self.assertRedirects(result, f'/schedules/{draft.pk}/', fetch_redirect_response=False)
        self.assertContains(self.client.get(f'/schedules/{draft.pk}/'), 'Remove Meeting')
        self.assert_source_unchanged()

    def test_edit_copy_does_not_edit_source_or_definitions(self):
        draft = self.copy()
        entry = draft.entries.first()
        room = m.Room.objects.create(name='Alternative', room_type='LECTURE', capacity=30)
        faculty = m.Faculty.objects.create(department=self.department, employee_id='ALT', full_name='Alternative teacher')
        url = f'/schedules/{draft.pk}/entry/{entry.pk}/edit/'
        token = self.client.get(url).context['form'].initial['revision']
        response = self.client.post(url, {'revision': token, 'assignment': entry.assignment_id, 'room': room.pk,
              'faculty_override': faculty.pk, 'day': 1, 'start_time': '10:00', 'end_time': '11:00'})
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual((entry.day, entry.room_id, entry.effective_faculty.pk), (1, room.pk, faculty.pk))
        self.assertEqual(entry.assignment.faculty_id, self.faculty.pk)
        self.assert_source_unchanged()

    def test_copy_failure_rolls_back_new_schedule_and_entries(self):
        with patch.object(m.ScheduleEntryAudit.objects, 'create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.copy()
        self.assertEqual(m.Schedule.objects.count(), 1)
        self.assertEqual(m.ScheduleEntry.objects.count(), 2)
        self.assert_source_unchanged()

    def test_copy_is_admin_post_only_and_rejects_draft_sources(self):
        url = f'/schedules/{self.source.pk}/copy-to-draft/'
        self.assertEqual(self.client.get(url).status_code, 405)
        student = User.objects.create_user(username='student')
        m.Profile.objects.create(user=student, role='STUDENT')
        self.client.force_login(student)
        self.assertEqual(self.client.post(url).status_code, 302)
        with self.assertRaises(ValidationError):
            copy_to_draft(source_id=self.source.pk, actor=student)
        self.assertEqual(m.Schedule.objects.count(), 1)
        draft = self.copy()
        with self.assertRaises(ValidationError):
            copy_to_draft(source_id=draft.pk, actor=self.admin)

    def test_removal_preserves_definitions_history_and_source(self):
        draft = self.copy()
        entry, url, data = self.removal(draft)
        audit = m.ScheduleEntryAudit.objects.create(schedule=draft, entry=entry, user=self.admin,
                                                   previous_values={'day': 2}, new_values={'day': 0})
        before_version = draft.updated_at
        response = self.client.post(url, data)
        self.assertRedirects(response, f'/schedules/{draft.pk}/', fetch_redirect_response=False)
        self.assertFalse(m.ScheduleEntry.objects.filter(pk=entry.pk).exists())
        self.assertEqual(m.TeachingAssignment.objects.count(), 2)
        self.assertEqual(m.Assignment.objects.count(), 1)
        audit.refresh_from_db()
        self.assertIsNone(audit.entry_id)
        self.assertEqual(audit.previous_values, {'day': 2})
        removal = draft.edit_audits.get(new_values__action='remove_meeting')
        self.assertEqual(removal.previous_values['entry_id'], entry.pk)
        self.assertEqual(removal.previous_values['assignment_id'], str(entry.assignment_id))
        draft.refresh_from_db()
        self.assertNotEqual(draft.updated_at, before_version)
        self.assert_source_unchanged()

    def test_removal_requires_confirmation_and_current_revision(self):
        draft = self.copy()
        entry, url, data = self.removal(draft)
        before_version = draft.updated_at
        self.assertContains(self.client.post(url, {'revision': data['revision']}), 'Confirm removal')
        self.assertEqual(draft.entries.count(), 2)
        m.ScheduleEntry.objects.filter(pk=entry.pk).update(day=2)
        self.assertContains(self.client.post(url, data), 'changed while you were editing')
        self.assertEqual(draft.entries.count(), 2)
        self.assertEqual(draft.edit_audits.count(), 1)
        draft.refresh_from_db()
        self.assertEqual(draft.updated_at, before_version)

    def test_removal_failure_restores_entry_revision_and_audit_links(self):
        draft = self.copy()
        entry, url, data = self.removal(draft)
        before_version = draft.updated_at
        audit = m.ScheduleEntryAudit.objects.create(schedule=draft, entry=entry, user=self.admin, previous_values={'day': 1})
        with patch.object(m.ScheduleEntryAudit.objects, 'create', side_effect=RuntimeError('private detail')):
            self.assertContains(self.client.post(url, data), 'Nothing was changed')
        self.assertTrue(m.ScheduleEntry.objects.filter(pk=entry.pk).exists())
        audit.refresh_from_db()
        self.assertEqual(audit.entry_id, entry.pk)
        self.assertEqual(audit.previous_values, {'day': 1})
        draft.refresh_from_db()
        self.assertEqual(draft.updated_at, before_version)
        self.assertEqual(draft.edit_audits.count(), 2)
        self.assert_source_unchanged()

    def test_finalized_and_approved_removal_is_rejected(self):
        for status in ('PUBLISHED', 'ARCHIVED', 'APPROVED'):
            with self.subTest(status=status):
                if status == 'PUBLISHED':
                    schedule = self.source
                else:
                    schedule = self.copy()
                    schedule.status = status
                    schedule.save(update_fields=['status'])
                entry = schedule.entries.first()
                token = revision_token(schedule, self.admin, entry)
                with self.assertRaises(ValidationError):
                    remove_manual_entry(schedule_id=schedule.pk, entry_id=entry.pk, actor=self.admin, revision=token, confirmed=True)
                self.assertTrue(schedule.entries.filter(pk=entry.pk).exists())

    def test_removed_meeting_blocks_publication(self):
        draft = self.copy()
        _, url, data = self.removal(draft)
        self.client.post(url, data)
        self.client.post(f'/schedules/{draft.pk}/publish/', {'replace_confirm': 'yes'})
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'DRAFT')
        self.assert_source_unchanged()

    def test_csrf_enforced_for_copy_and_removal(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(f'/schedules/{self.source.pk}/copy-to-draft/').status_code, 403)
        draft = self.copy()
        entry = draft.entries.first()
        url = f'/schedules/{draft.pk}/entry/{entry.pk}/remove/'
        self.assertEqual(client.post(url, {'confirm_remove': 'yes'}).status_code, 403)
        page = client.get(url)
        response = client.post(url, {'confirm_remove': 'yes', 'revision': page.context['revision'],
                                    'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(draft.entries.count(), 1)

    def test_removal_permission_rechecked_in_service(self):
        draft = self.copy()
        entry, url, data = self.removal(draft)
        User.objects.filter(pk=self.admin.pk).update(is_superuser=False)
        with self.assertRaises(ValidationError):
            remove_manual_entry(schedule_id=draft.pk, entry_id=entry.pk, actor=self.admin, revision=data['revision'], confirmed=True)
        self.assertEqual(draft.entries.count(), 2)
        self.assertEqual(draft.edit_audits.count(), 1)

    def test_copy_preserves_effective_overrides(self):
        history = self.copy()
        faculty = m.Faculty.objects.create(department=self.department, employee_id='OVR', full_name='Override teacher')
        section = m.Section.objects.create(program=self.section.program, year_level=self.section.year_level, name='B', size=20)
        item = history.entries.first()
        item.faculty_override = faculty
        item.section_override = section
        item.subject_override = self.subject
        item.component_override = 'LECTURE'
        item.save()
        history.status = 'ARCHIVED'
        history.save(update_fields=['status'])
        draft = copy_to_draft(source_id=history.pk, actor=self.admin)
        copied = draft.entries.get(assignment=item.assignment)
        self.assertEqual(copied.faculty_override_id, faculty.pk)
        self.assertEqual(copied.section_override_id, section.pk)
        self.assertEqual(copied.subject_override_id, self.subject.pk)
        self.assertEqual(copied.component_override, 'LECTURE')
        self.assert_source_unchanged()

    def test_removal_rechecks_status_after_confirmation(self):
        draft = self.copy()
        entry, _, data = self.removal(draft)
        draft.status = 'ARCHIVED'
        draft.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            remove_manual_entry(schedule_id=draft.pk, entry_id=entry.pk, actor=self.admin,
                                revision=data['revision'], confirmed=True)
        self.assertEqual(draft.entries.count(), 2)
        self.assertEqual(draft.edit_audits.count(), 1)
