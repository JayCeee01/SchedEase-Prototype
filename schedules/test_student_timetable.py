"""T5 student login, timetable details and read-only published visibility."""
from datetime import time
from django.contrib.auth.models import User
from django.urls import reverse
from . import models as m
from .services.publication import publish
from .test_known_defects import SchedulingDefectFixture


class StudentTimetableTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('student-test-admin')
        self.user = User.objects.create_user('student-test', password='fixture-only')
        m.Profile.objects.create(user=self.user, role=m.Role.STUDENT)
        m.Student.objects.create(user=self.user, section=self.section, student_number='T5', full_name='Test Student')
        self.schedule = m.Schedule.objects.create(term=self.term, name='Official timetable')
        self.entries = [self.schedule.entries.create(assignment=a, room=self.room,
            day=0, start_time=time(8+i), end_time=time(9+i)) for i, a in enumerate(self.meetings)]

    def login(self):
        response = self.client.post('/', {'username': self.user.username, 'password': 'fixture-only'})
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_real_login_and_visible_timetable_details(self):
        publish(self.schedule, self.admin)
        self.login()
        response = self.client.get(reverse('dashboard'))
        for value in (self.subject.code, self.subject.title, self.room.name, self.term.name,
                      self.term.school_year, 'Monday', '8:00 AM', '9:00 AM'):
            self.assertContains(response, value)
        self.assertContains(response, f'<span class="personal-class-faculty">{self.faculty.full_name}</span>', html=True)
        self.assertEqual({e.pk for e in response.context['entries']}, {e.pk for e in self.entries})

    def test_draft_and_empty_state_and_direct_exports(self):
        self.login()
        self.assertContains(self.client.get(reverse('dashboard')), 'No published classes yet')
        self.assertNotContains(self.client.get(reverse('dashboard')), self.subject.code)
        for name in ('schedule_detail', 'export_csv', 'export_pdf'):
            self.assertEqual(self.client.get(reverse(name, args=[self.schedule.pk])).status_code, 404)
        self.assertFalse(list(self.client.get(reverse('browse_schedules')).context['entries']))

    def test_student_mutation_routes_do_not_change_entries_or_audits(self):
        publish(self.schedule, self.admin)
        self.login()
        before = list(m.ScheduleEntry.objects.values())
        audits = m.ScheduleEntryAudit.objects.count()
        routes = [('entry_create', [self.schedule.pk]),
            ('entry_update', [self.schedule.pk, self.entries[0].pk]),
            ('entry_remove', [self.schedule.pk, self.entries[0].pk]),
            ('entry_apply_suggestion', [self.schedule.pk, self.entries[0].pk]),
            ('publish_schedule', [self.schedule.pk]), ('copy_schedule_to_draft', [self.schedule.pk]),
            ('resource_update', ['schedules', self.schedule.pk]),
            ('resource_create', ['availability'])]
        for name, args in routes:
            with self.subTest(route=name):
                response = self.client.post(reverse(name, args=args), {'day': 1, 'confirmed': 'yes'})
                self.assertEqual(response.status_code, 302)
                self.assertIn('/accounts/login/', response.url)
        self.assertEqual(list(m.ScheduleEntry.objects.values()), before)
        self.assertEqual(m.ScheduleEntryAudit.objects.count(), audits)
        self.assertEqual(m.Schedule.objects.count(), 1)
        self.assertFalse(m.Availability.objects.exists())

    def test_missing_student_profile_is_empty_and_cannot_access_published_schedule(self):
        publish(self.schedule, self.admin)
        m.Student.objects.filter(user=self.user).delete()
        self.login()
        self.assertContains(self.client.get(reverse('dashboard')), 'No published classes yet')
        self.assertEqual(self.client.get(reverse('schedule_detail', args=[self.schedule.pk])).status_code, 404)
