from datetime import timedelta
from django.contrib.auth.models import User
from django.urls import reverse

from . import models as m
from .test_known_defects import SchedulingDefectFixture


class FacultySuggestionTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('suggest-admin', password='test')
        self.client.force_login(self.admin)
        self.url = reverse('qualified_faculty')
        self.credential = m.Credential.objects.create(name='Teaching license')
        self.requirement = m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=self.credential)

    def statuses(self, **extra):
        response = self.client.get(self.url, {'subject': self.subject.pk, 'term': self.term.pk, **extra})
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        return {row['id']: row for row in response.json()['faculty']}

    def test_term_dates_and_equivalents(self):
        equivalent = m.Credential.objects.create(name='Equivalent license')
        self.requirement.acceptable_equivalents.add(equivalent)
        cases = [(self.term.starts_on, self.term.ends_on, 'qualified'),
                 (self.term.starts_on, None, 'qualified'),
                 (self.term.starts_on + timedelta(days=1), None, 'qualified'),
                 (self.term.ends_on + timedelta(days=1), None, 'unqualified'),
                 (self.term.starts_on, self.term.ends_on - timedelta(days=1), 'unqualified'),
                 (None, None, 'unqualified')]
        expected = {}
        for index, (issued, expires, status) in enumerate(cases):
            faculty = m.Faculty.objects.create(department=self.department, employee_id=f'SUG{index}', full_name=f'Faculty {index}')
            m.FacultyCredential.objects.create(faculty=faculty, credential=equivalent, issued_on=issued, expires_on=expires)
            expected[faculty.pk] = status
        rows = self.statuses()
        self.assertEqual(rows[self.faculty.pk]['status'], 'unqualified')
        self.assertEqual(rows[self.faculty.pk]['missing'], ['Teaching license'])
        for pk, status in expected.items():
            self.assertEqual(rows[pk]['status'], status)

    def test_qualification_does_not_claim_availability(self):
        m.FacultyCredential.objects.create(faculty=self.faculty, credential=self.credential, issued_on=self.term.starts_on)
        m.Availability.objects.create(faculty=self.faculty, day=0, start_time='07:00', end_time='19:00', kind='UNAVAILABLE')
        row = self.statuses()[self.faculty.pk]
        self.assertEqual(row['status'], 'qualified')
        self.assertNotIn('available', row)

    def test_saved_meeting_overrides_are_distinct_and_require_complete_coverage(self):
        self.assertEqual(self.statuses(assignment=self.parent.pk)[self.faculty.pk]['status'], 'unqualified')
        for index, meeting in enumerate(self.meetings):
            m.CredentialOverride.objects.create(assignment=meeting, faculty=self.faculty, subject=self.subject,
                admin_user=self.admin, reason='Authorized exception', missing_credentials='Teaching license')
            expected = 'override' if index == len(self.meetings) - 1 else 'unqualified'
            self.assertEqual(self.statuses(assignment=self.parent.pk)[self.faculty.pk]['status'], expected)
        self.assertEqual(self.statuses()[self.faculty.pk]['status'], 'unqualified')
        other = m.AcademicTerm.objects.create(name='Other', school_year='2027', starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        self.assertEqual(self.statuses(assignment=self.parent.pk, term=other.pk)[self.faculty.pk]['status'], 'unqualified')
        m.CredentialOverride.objects.filter(assignment=self.meetings[0]).update(reason='')
        self.assertEqual(self.statuses(assignment=self.parent.pk)[self.faculty.pk]['status'], 'unqualified')

    def test_mismatched_override_is_not_suggested(self):
        other = m.Faculty.objects.create(department=self.department, employee_id='OTHER', full_name='Other')
        for meeting in self.meetings:
            m.CredentialOverride.objects.create(assignment=meeting, faculty=other, subject=self.subject,
                admin_user=self.admin, reason='Example', missing_credentials='Example')
        rows = self.statuses(assignment=self.parent.pk)
        self.assertEqual(rows[self.faculty.pk]['status'], 'unqualified')
        self.assertEqual(rows[other.pk]['status'], 'unqualified')

    def test_missing_invalid_and_unknown_context(self):
        self.assertEqual(self.client.get(self.url).json()['faculty'], [])
        for invalid in ('bad', '0', '-1', '9' * 100):
            self.assertEqual(self.client.get(self.url, {'subject': invalid, 'term': self.term.pk}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {'subject': 99999, 'term': self.term.pk}).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_no_requirements_and_no_faculty(self):
        self.requirement.delete()
        self.assertEqual(self.statuses()[self.faculty.pk]['status'], 'qualified')
        # Use an empty queryset without altering related scheduling fixtures.
        from unittest.mock import patch
        with patch('schedules.faculty_suggestions.Faculty.objects.all', return_value=m.Faculty.objects.none()):
            self.assertEqual(self.statuses(), {})

    def test_administrator_only(self):
        for role in (m.Role.FACULTY, m.Role.STUDENT):
            user = User.objects.create_user('suggest-' + role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            self.assertIn(self.client.get(self.url, {'subject': self.subject.pk, 'term': self.term.pk}).status_code, (302, 403))
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_edit_and_draft_selection_are_preserved(self):
        url = reverse('resource_update', args=['assignments', self.parent.pk])
        response = self.client.get(url)
        self.assertContains(response, 'data-faculty-suggestions')
        self.assertContains(response, 'Credential guidance only')
        self.assertEqual(response.context['form']['faculty'].value(), self.faculty.pk)
        m.FormDraft.objects.create(user=self.admin, resource='assignments', object_pk=str(self.parent.pk),
            payload={'faculty': str(self.faculty.pk), 'subject': str(self.subject.pk), 'term': str(self.term.pk), 'section': str(self.section.pk)})
        response = self.client.get(url)
        self.assertEqual(str(response.context['form']['faculty'].value()), str(self.faculty.pk))
        self.statuses(assignment=self.parent.pk)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.faculty_id, self.faculty.pk)
        self.assertEqual(self.parent.meetings.count(), 2)
        self.assertFalse(m.CredentialOverride.objects.exists())
