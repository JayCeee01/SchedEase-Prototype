"""Exercise batch credentials through suggestions and the real assignment editor."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse

from . import models as m
from .test_known_defects import SchedulingDefectFixture


class CredentialRecognitionTests(SchedulingDefectFixture):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('recognition-admin', password='test'))
        self.required = m.Credential.objects.create(name='Required license')
        self.equivalent = m.Credential.objects.create(name='Equivalent license')
        requirement = m.SubjectCredentialRequirement.objects.create(
            subject=self.subject, required_credential=self.required)
        requirement.acceptable_equivalents.add(self.equivalent)

    def batch(self, credential, issued, expires=''):
        response = self.client.post(reverse('resource_create', args=['faculty-credentials']), {
            'faculty': self.faculty.pk, 'credential': [credential.pk],
            'issued_on': issued, 'expires_on': expires})
        self.assertEqual(response.status_code, 302)

    def payload(self):
        return {'faculty': self.faculty.pk, 'subject': self.subject.pk,
                'section': self.section.pk, 'term': self.term.pk,
                'meetings-TOTAL_FORMS': '1', 'meetings-INITIAL_FORMS': '0',
                'meetings-MIN_NUM_FORMS': '1', 'meetings-MAX_NUM_FORMS': '1000',
                'meetings-0-component': 'LECTURE', 'meetings-0-meeting_index': '1',
                'meetings-0-duration_minutes': '120'}

    def status(self):
        response = self.client.get(reverse('qualified_faculty'), {
            'subject': self.subject.pk, 'term': self.term.pk})
        self.assertEqual(response.status_code, 200)
        return next(row['status'] for row in response.json()['faculty'] if row['id'] == self.faculty.pk)

    def test_batch_credentials_recognized_on_create_and_edit(self):
        self.batch(self.required, self.term.ends_on, self.term.ends_on)
        self.assertEqual(self.status(), 'qualified')
        self.parent.delete()
        data = self.payload()
        response = self.client.post(reverse('resource_create', args=['assignments']), data)
        self.assertEqual(response.status_code, 302)
        parent = m.Assignment.objects.get()
        meeting = parent.meetings.get()
        data.update({'meetings-INITIAL_FORMS': '1', 'meetings-0-id': meeting.pk})
        response = self.client.post(reverse('resource_update', args=['assignments', parent.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(m.CredentialOverride.objects.exists())

    def test_batch_equivalent_without_expiry_recognized(self):
        self.batch(self.equivalent, self.term.starts_on + timedelta(days=1))
        self.assertEqual(self.status(), 'qualified')
        self.parent.delete()
        response = self.client.post(reverse('resource_create', args=['assignments']), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.Assignment.objects.count(), 1)
        self.assertFalse(m.CredentialOverride.objects.exists())

    def test_missing_late_or_expired_dates_rejected_consistently(self):
        self.parent.delete()
        for issued, expires in [('', ''), (self.term.ends_on + timedelta(days=1), ''),
                                (self.term.starts_on, self.term.ends_on - timedelta(days=1))]:
            with self.subTest(issued=issued, expires=expires):
                m.FacultyCredential.objects.all().delete()
                self.batch(self.required, issued, expires)
                self.assertEqual(self.status(), 'unqualified')
                guidance = self.client.get(reverse('qualified_faculty'), {
                    'subject': self.subject.pk, 'term': self.term.pk}).json()
                reasons = next(row['reasons'] for row in guidance['faculty'] if row['id'] == self.faculty.pk)
                expected = 'issue date is missing' if not issued else 'after the term ends' if issued > self.term.ends_on else 'before the term ends'
                self.assertIn(expected, ' '.join(reasons))
                response = self.client.post(reverse('resource_create', args=['assignments']), self.payload())
                self.assertContains(response, 'Unqualified faculty assignment')
                self.assertContains(response, expected)
                self.assertFalse(response.context['credential_result']['qualified'])
                self.assertFalse(m.Assignment.objects.exists())
                self.assertFalse(m.CredentialOverride.objects.exists())
