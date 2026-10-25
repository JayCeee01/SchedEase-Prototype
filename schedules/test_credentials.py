from datetime import date, timedelta, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.credentials import faculty_qualification, teaching_eligibility


class CredentialValidityTests(SchedulingDefectFixture):
    def setUp(self):
        self.credential = m.Credential.objects.create(name='Teaching license')
        self.requirement = m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=self.credential)
        self.held = m.FacultyCredential.objects.create(faculty=self.faculty, credential=self.credential,
                                                     issued_on=self.term.starts_on, expires_on=self.term.ends_on)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Credential checks')
        self.admin = User.objects.create_superuser(username='credential-admin', password='test-password')

    def entry(self):
        return m.ScheduleEntry(schedule=self.schedule, assignment=m.TeachingAssignment.objects.get(pk=self.meetings[0].pk),
                               room=self.room, day=0, start_time=time(8), end_time=time(9))

    def assert_eligibility(self, expected):
        self.assertEqual(faculty_qualification(self.faculty, self.subject, self.term)['qualified'], expected)
        self.assertEqual(set(self.scheduler().qualification_cache.values()), {expected})
        if expected:
            self.entry().full_clean()
        else:
            with self.assertRaisesMessage(ValidationError, 'does not meet the credential requirements'):
                self.entry().full_clean()

    def test_term_boundaries_missing_dates_and_no_expiry(self):
        for issued, expires, expected in [
            (self.term.starts_on, self.term.ends_on, True),
            (self.term.starts_on, None, True),
            (self.term.starts_on - timedelta(days=1), self.term.ends_on + timedelta(days=1), True),
            (date(2024, 1, 1), self.term.starts_on - timedelta(days=1), False),
            (date(2024, 1, 1), self.term.ends_on - timedelta(days=1), False),
            (self.term.starts_on + timedelta(days=1), None, True),
            (self.term.ends_on, None, True),
            (self.term.ends_on + timedelta(days=1), None, False),
            (None, None, False), (None, self.term.ends_on, False),
        ]:
            with self.subTest(issued=issued, expires=expires):
                self.held.issued_on, self.held.expires_on = issued, expires
                self.held.save()
                self.assert_eligibility(expected)

    def test_missing_or_invalid_term_dates_fail_closed(self):
        self.assertFalse(faculty_qualification(self.faculty, self.subject)['qualified'])
        for start, end in [(None, self.term.ends_on), (self.term.starts_on, None),
                           (self.term.ends_on, self.term.starts_on), (self.term.starts_on, self.term.starts_on)]:
            with self.subTest(start=start, end=end):
                term = m.AcademicTerm(starts_on=start, ends_on=end)
                self.assertFalse(faculty_qualification(self.faculty, self.subject, term)['qualified'])

    def test_equivalents_obey_same_dates(self):
        equivalent = m.Credential.objects.create(name='Approved equivalent')
        self.held.credential = equivalent
        self.held.save()
        self.assert_eligibility(False)
        self.requirement.acceptable_equivalents.add(equivalent)
        self.assert_eligibility(True)
        self.held.expires_on = self.term.ends_on - timedelta(days=1)
        self.held.save()
        self.assert_eligibility(False)

    def override(self, **changes):
        values = dict(assignment=self.meetings[0], faculty=self.faculty, subject=self.subject,
                      admin_user=self.admin, reason='Dean approved exception', missing_credentials='Teaching license not valid for term')
        values.update(changes)
        return m.CredentialOverride.objects.create(**values)

    def test_overrides_match_meeting_faculty_course_and_preserve_audit(self):
        self.held.delete()
        other_faculty = m.Faculty.objects.create(department=self.department, employee_id='OTHER', full_name='Other teacher')
        other_subject = m.Subject.objects.create(department=self.department, code='OTHER', title='Other course')
        for change in ({'faculty': other_faculty}, {'subject': other_subject}, {'assignment': self.meetings[1]},
                       {'assignment': None}, {'reason': ' '}, {'missing_credentials': ''}):
            with self.subTest(change=change):
                override = self.override(**change)
                self.assertFalse(teaching_eligibility(self.faculty, self.subject, self.term, self.meetings[0])['eligible'])
                self.assertFalse(self.scheduler().qualification_cache[self.meetings[0].pk])
                with self.assertRaises(ValidationError):
                    self.entry().full_clean()
                override.delete()
        override = self.override()
        self.entry().full_clean()
        self.assertTrue(self.scheduler().qualification_cache[self.meetings[0].pk])
        self.assertFalse(self.scheduler().qualification_cache[self.meetings[1].pk])
        self.parent.faculty = other_faculty
        self.parent.save()
        self.assertFalse(self.scheduler().qualification_cache[self.meetings[0].pk])
        with self.assertRaises(ValidationError):
            self.entry().full_clean()
        override.refresh_from_db()
        self.assertEqual(override.faculty_id, self.faculty.pk)
        self.assertEqual(override.admin_user_id, self.admin.pk)
        self.assertEqual(override.reason, 'Dean approved exception')

    def payload(self):
        return {'assignment': self.meetings[0].pk, 'room': self.room.pk, 'day': 0,
                'start_time': '08:00', 'end_time': '09:00'}

    def test_manual_override_confirmation_and_failed_save_are_atomic(self):
        self.held.delete()
        self.client.force_login(self.admin)
        url = f'/schedules/{self.schedule.pk}/entry/new/'
        payload = {**self.payload(), "revision": self.client.get(url).context["form"].initial["revision"]}
        self.assertContains(self.client.post(url, payload), 'Credential Override Required')
        self.assertFalse(m.CredentialOverride.objects.exists())
        payload.update(credential_override_confirm='yes', credential_override_reason='Approved for this term')
        # Failure after override creation must roll back both records.
        with patch.object(m.ScheduleEntry, 'save', side_effect=ValidationError('Simulated save validation failure')):
            self.assertContains(self.client.post(url, payload), 'Simulated save validation failure')
        self.assertFalse(m.CredentialOverride.objects.exists())
        self.assertFalse(self.schedule.entries.exists())
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        override = m.CredentialOverride.objects.get()
        self.assertEqual((override.faculty_id, override.subject_id, override.assignment_id),
                         (self.faculty.pk, self.subject.pk, self.meetings[0].pk))
        self.assertEqual(override.admin_user_id, self.admin.pk)
        self.assertIn('credential requirements', override.missing_credentials)
        entry = self.schedule.entries.get()
        edit_url = f'/schedules/{self.schedule.pk}/entry/{entry.pk}/edit/'
        edit_payload = {**self.payload(), 'revision': self.client.get(edit_url).context['form'].initial['revision']}
        self.assertEqual(self.client.post(edit_url, edit_payload).status_code, 302)
        self.assertEqual(m.CredentialOverride.objects.count(), 1)

    def test_non_admin_cannot_authorize_override(self):
        self.held.delete()
        user = User.objects.create_user(username='student')
        m.Profile.objects.create(user=user, role=m.Role.STUDENT)
        self.client.force_login(user)
        response = self.client.post(f'/schedules/{self.schedule.pk}/entry/new/', {
            **self.payload(), 'credential_override_confirm': 'yes', 'credential_override_reason': 'Forged approval'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(m.CredentialOverride.objects.exists())
        self.assertFalse(self.schedule.entries.exists())

    def test_course_change_does_not_reuse_old_override(self):
        self.held.delete()
        override = self.override()
        other = m.Subject.objects.create(department=self.department, code='NEW', title='New course', lecture_hours=2)
        m.SubjectCredentialRequirement.objects.create(subject=other, required_credential=self.credential)
        self.parent.subject = other
        self.parent.save()
        self.assertFalse(self.scheduler().qualification_cache[self.meetings[0].pk])
        with self.assertRaises(ValidationError):
            self.entry().full_clean()
        override.refresh_from_db()
        self.assertEqual(override.subject_id, self.subject.pk)

    def test_manual_faculty_override_requires_approval_for_effective_faculty(self):
        self.held.delete()
        self.override()
        entry = self.entry()
        entry.full_clean()
        entry.save()
        other = m.Faculty.objects.create(department=self.department, employee_id='OTHER', full_name='Replacement Teacher')
        self.client.force_login(self.admin)
        url = f'/schedules/{self.schedule.pk}/entry/{entry.pk}/edit/'
        payload = {**self.payload(), 'faculty_override': other.pk, 'revision': self.client.get(url).context['form'].initial['revision']}
        response = self.client.post(url, payload)
        self.assertContains(response, 'Replacement Teacher is not qualified')
        entry.refresh_from_db()
        self.assertIsNone(entry.faculty_override_id)
        payload.update(credential_override_confirm='yes', credential_override_reason='Approved replacement')
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        entry.refresh_from_db()
        entry.full_clean()
        self.assertEqual(entry.faculty_override_id, other.pk)
        self.assertEqual(m.CredentialOverride.objects.count(), 2)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), 1)

    def test_assignment_edit_reuses_only_matching_approved_overrides(self):
        self.held.delete()
        self.client.force_login(self.admin)
        data = {'term': self.term.pk, 'subject': self.subject.pk, 'section': self.section.pk, 'faculty': self.faculty.pk,
                'meetings-TOTAL_FORMS': 2, 'meetings-INITIAL_FORMS': 2, 'meetings-MIN_NUM_FORMS': 1, 'meetings-MAX_NUM_FORMS': 1000}
        for index, meeting in enumerate(self.meetings):
            for field in ('id', 'component', 'meeting_index', 'duration_minutes', 'required_room_type_override'):
                data[f'meetings-{index}-{field}'] = getattr(meeting, field)
        url = f'/schedules/manage/assignments/{self.parent.pk}/edit/'
        self.assertContains(self.client.post(url, data), 'Unqualified faculty assignment')
        data.update(credential_override_confirm='yes', credential_override_reason='Approved teaching exception')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(m.CredentialOverride.objects.count(), 2)
        data.pop('credential_override_confirm')
        data.pop('credential_override_reason')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(m.CredentialOverride.objects.count(), 2)
