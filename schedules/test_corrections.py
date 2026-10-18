"""M2 correction links, validated alternatives and atomic application."""
from datetime import time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.corrections import placement_suggestions, apply_suggestion
from .services.conflicts import schedule_validation_issues, schedule_validation_messages


class CorrectionTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='corrector', password='test')
        self.client.force_login(self.admin)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Correction draft')
        self.entry = self.schedule.entries.create(assignment=self.meetings[0], room=self.room,
                                                   day=0, start_time=time(8), end_time=time(9))
        self.other = self.schedule.entries.create(assignment=self.meetings[1], room=self.room,
                                                   day=0, start_time=time(8), end_time=time(9))
        self.url = f'/schedules/{self.schedule.pk}/entry/{self.entry.pk}/apply-suggestion/'
        self.edit = f'/schedules/{self.schedule.pk}/entry/{self.entry.pk}/edit/'

    def suggestions(self):
        return placement_suggestions(m.ScheduleEntry.objects.get(pk=self.entry.pk), self.admin)

    def apply(self, token):
        return apply_suggestion(schedule_id=self.schedule.pk, entry_id=self.entry.pk, actor=self.admin, token=token)

    def unchanged(self, version):
        self.entry.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertEqual((self.entry.day, self.entry.start_time, self.entry.room_id), (0, time(8), self.room.pk))
        self.assertEqual(self.schedule.updated_at, version)
        self.assertEqual(self.schedule.edit_audits.count(), 0)

    def test_identification_links_and_explanations(self):
        issues = schedule_validation_issues(self.schedule)
        self.assertEqual({i['entry'].pk for i in issues if i['entry']}, {self.entry.pk, self.other.pk})
        self.assertTrue(any('Faculty conflict' in i['message'] for i in issues))
        self.assertEqual(schedule_validation_messages(self.schedule), list(dict.fromkeys(i['message'] for i in issues)))
        page = self.client.get(f'/schedules/{self.schedule.pk}/')
        self.assertContains(page, self.edit)
        self.assertContains(page, 'Fix Conflict')
        self.assertContains(page, self.faculty.full_name)
        self.assertContains(page, self.room.name)

    def test_unplaced_requirements_have_no_invalid_links(self):
        self.other.delete()
        issues = schedule_validation_issues(self.schedule)
        missing = [i for i in issues if 'Unscheduled class' in i['message']]
        self.assertEqual(len(missing), 1)
        self.assertIsNone(missing[0]['entry'])

    def test_alternative_times_are_valid_and_leave_database_unchanged(self):
        results = self.suggestions()
        self.assertEqual(len(results), 3)
        for result in results:
            candidate = result['entry']
            candidate.full_clean()
            self.assertEqual(candidate.assignment_id, self.entry.assignment_id)
            self.assertEqual(candidate.effective_component, 'LECTURE')
            self.assertNotEqual(candidate.start_time, time(8))
            self.assertEqual(candidate.end_time.hour * 60 + candidate.end_time.minute - candidate.start_time.hour * 60 - candidate.start_time.minute, 60)
        self.unchanged(self.schedule.updated_at)

    def test_same_time_room_alternative_prioritized(self):
        self.other.delete()
        self.room.is_active = False
        self.room.save()
        alternative = m.Room.objects.create(name='Suitable', room_type='LECTURE', capacity=25)
        first = self.suggestions()[0]['entry']
        self.assertEqual((first.day, first.start_time, first.room_id), (0, time(8), alternative.pk))
        first.full_clean()

    def test_availability_capacity_room_type_and_inactive_exclusions(self):
        m.Room.objects.create(name='Small', room_type='LECTURE', capacity=1)
        m.Room.objects.create(name='Inactive', room_type='LECTURE', capacity=50, is_active=False)
        m.Room.objects.create(name='Wrong type', room_type='LABORATORY', capacity=50)
        for resource in ({'faculty': self.faculty}, {'room': self.room}):
            m.Availability.objects.create(**resource, day=2, start_time=time(10), end_time=time(14), kind='AVAILABLE')
        results = self.suggestions()
        self.assertTrue(results)
        for result in results:
            candidate = result['entry']
            self.assertEqual((candidate.day, candidate.room_id), (2, self.room.pk))
            self.assertGreaterEqual(candidate.start_time, time(10))
            self.assertLessEqual(candidate.end_time, time(14))
            candidate.full_clean()

    def test_no_qualified_alternative_or_component_bypass(self):
        credential = m.Credential.objects.create(name='Required')
        requirement = m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        self.assertEqual(self.suggestions(), [])
        requirement.delete()
        self.entry.component_override = 'LABORATORY'
        self.entry.save()
        self.assertEqual(self.suggestions(), [])

    def test_no_suggestions_message(self):
        self.room.is_active = False
        self.room.save()
        self.assertContains(self.client.get(self.edit), 'No valid alternatives were found')

    def test_successful_apply_is_audited_and_revised(self):
        result = self.suggestions()[0]
        version = self.schedule.updated_at
        response = self.client.post(self.url, {'suggestion': result['token']})
        self.assertEqual(response.status_code, 302)
        self.entry.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertEqual(self.entry.start_time, result['entry'].start_time)
        self.assertNotEqual(self.schedule.updated_at, version)
        audit = self.schedule.edit_audits.get()
        self.assertEqual(audit.previous_values['start_time'], '08:00:00')
        self.assertEqual(audit.new_values['start_time'], str(result['entry'].start_time))

    def test_current_availability_revalidated(self):
        result = self.suggestions()[0]
        m.Availability.objects.create(room=self.room, day=result['entry'].day,
            start_time=result['entry'].start_time, end_time=result['entry'].end_time, kind='UNAVAILABLE')
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        self.unchanged(self.schedule.updated_at)

    def test_new_conflict_revalidated_without_revision_change(self):
        result = self.suggestions()[0]
        m.ScheduleEntry.objects.filter(pk=self.other.pk).update(day=result['entry'].day,
            start_time=result['entry'].start_time, end_time=result['entry'].end_time)
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        self.unchanged(self.schedule.updated_at)

    def test_stale_revision_and_tampering_rejected(self):
        result = self.suggestions()[0]
        self.apply(result['token'])
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        with self.assertRaises(ValidationError):
            self.apply(result['token'] + 'tampered')
        self.assertEqual(self.schedule.edit_audits.count(), 1)

    def test_audit_failure_rolls_back(self):
        result = self.suggestions()[0]
        with patch.object(m.ScheduleEntryAudit.objects, 'create', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.apply(result['token'])
        self.unchanged(self.schedule.updated_at)

    def test_permissions_csrf_and_post_only(self):
        result = self.suggestions()[0]
        self.assertEqual(self.client.get(self.url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url, {'suggestion': result['token']}).status_code, 403)
        page = client.get(self.edit)
        self.assertContains(page, 'Apply Suggestion')
        response = client.post(self.url, {'suggestion': result['token'], 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.schedule.edit_audits.count(), 1)
        student = User.objects.create_user(username='student')
        m.Profile.objects.create(user=student, role='STUDENT')
        self.client.force_login(student)
        self.assertEqual(self.client.get(self.edit).status_code, 302)
        self.assertEqual(self.client.post(self.url, {'suggestion': result['token']}).status_code, 302)
        with self.assertRaises(ValidationError):
            placement_suggestions(self.entry, student)

    def test_finalized_status_rechecked_and_links_hidden(self):
        for status in ('PUBLISHED', 'ARCHIVED'):
            with self.subTest(status=status):
                result = self.suggestions()[0] if status == 'PUBLISHED' else result
                if status == 'PUBLISHED':
                    self.schedule.status = status
                    self.schedule.save(update_fields=['status'])
                else:
                    from .protection import archive_transition
                    self.schedule.status = status
                    with archive_transition():
                        self.schedule.save(update_fields=['status'])
                self.assertEqual(self.suggestions(), [])
                with self.assertRaises(ValidationError):
                    self.apply(result['token'])
                self.assertNotContains(self.client.get(f'/schedules/{self.schedule.pk}/'), 'Fix Conflict')
        self.unchanged(self.schedule.updated_at)

    def test_changed_credentials_revalidated_without_creating_override(self):
        result = self.suggestions()[0]
        credential = m.Credential.objects.create(name='New requirement')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        self.assertEqual(m.CredentialOverride.objects.count(), 0)
        self.unchanged(self.schedule.updated_at)

    def test_changed_duration_and_inactive_room_revalidated(self):
        result = self.suggestions()[0]
        m.TeachingAssignment.objects.filter(pk=self.entry.assignment_id).update(duration_minutes=90)
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        m.TeachingAssignment.objects.filter(pk=self.entry.assignment_id).update(duration_minutes=60)
        m.Room.objects.filter(pk=self.room.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        self.unchanged(self.schedule.updated_at)

    def test_suggestion_bound_to_user_and_meeting_and_permission_rechecked(self):
        result = self.suggestions()[0]
        second_admin = User.objects.create_superuser(username='second', password='test')
        with self.assertRaises(ValidationError):
            apply_suggestion(schedule_id=self.schedule.pk, entry_id=self.entry.pk, actor=second_admin, token=result['token'])
        with self.assertRaises(ValidationError):
            apply_suggestion(schedule_id=self.schedule.pk, entry_id=self.other.pk, actor=self.admin, token=result['token'])
        User.objects.filter(pk=self.admin.pk).update(is_superuser=False)
        with self.assertRaises(ValidationError):
            self.apply(result['token'])
        self.unchanged(self.schedule.updated_at)

    def test_required_duration_corrects_bad_span_within_operating_hours(self):
        self.entry.start_time, self.entry.end_time = time(18, 30), time(19)
        self.entry.save()
        results = self.suggestions()
        self.assertTrue(results)
        for result in results:
            candidate = result['entry']
            candidate.full_clean()
            self.assertGreaterEqual(candidate.start_time, time(7))
            self.assertLessEqual(candidate.end_time, time(19))
            self.assertEqual(candidate.end_time.hour * 60 + candidate.end_time.minute - candidate.start_time.hour * 60 - candidate.start_time.minute, 60)
