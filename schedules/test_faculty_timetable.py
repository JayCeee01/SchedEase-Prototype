"""T6 faculty published workload and ownership contracts."""
from datetime import time
from django.contrib.auth.models import User
from django.urls import reverse
from . import models as m
from .services.publication import publish
from .test_known_defects import SchedulingDefectFixture

class FacultyTimetableTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('faculty-admin')
        self.user = User.objects.create_user('faculty-test', password='fixture-only')
        m.Profile.objects.create(user=self.user, role=m.Role.FACULTY)
        self.faculty.user = self.user
        self.faculty.save()
        self.schedule = m.Schedule.objects.create(term=self.term, name='Official teaching')
        self.entries = [self.schedule.entries.create(assignment=a, room=self.room, day=0,
            start_time=time(8+i), end_time=time(9+i)) for i,a in enumerate(self.meetings)]

    def login(self):
        response = self.client.post('/', {'username': self.user.username, 'password': 'fixture-only'})
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_login_published_details_and_workload(self):
        publish(self.schedule, self.admin)
        self.login()
        response = self.client.get(reverse('dashboard'))
        for value in (self.subject.code, str(self.section), self.room.name, self.term.name,
                      self.term.school_year, 'Monday', '8:00 AM', '2.00 hours', '120 minutes',
                      '2 meetings', '1 section', '24 hours'):
            self.assertContains(response, value)
        group = response.context['workloads'][0]
        self.assertEqual((group['minutes'],group['meetings'],group['sections']), (120,2,1))

    def test_drafts_missing_profile_and_empty_workload(self):
        self.login()
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'No published teaching workload yet')
        self.assertEqual(response.context['workloads'], [])
        for route in ('schedule_detail','export_csv','export_pdf'):
            self.assertEqual(self.client.get(reverse(route,args=[self.schedule.pk])).status_code,404)
        self.faculty.user = None
        self.faculty.save()
        self.assertEqual(self.client.get(reverse('dashboard')).context['workloads'], [])
        self.assertEqual(self.client.get(reverse('my_availability')).status_code,404)

    def test_effective_faculty_scope_and_read_only_routes(self):
        other=m.Faculty.objects.create(department=self.department,employee_id='OTHER',full_name='Private Teacher')
        self.entries[1].faculty_override=other
        self.entries[1].save()
        publish(self.schedule,self.admin)
        self.login()
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['workloads'][0]['minutes'],60)
        self.assertNotContains(response,'Private Teacher')
        self.assertNotContains(self.client.get(reverse('export_csv',args=[self.schedule.pk])),'Private Teacher')
        for route,args in [('entry_update',[self.schedule.pk,self.entries[0].pk]),
                           ('entry_create',[self.schedule.pk]),('publish_schedule',[self.schedule.pk]),
                           ('copy_schedule_to_draft',[self.schedule.pk]),
                           ('entry_remove',[self.schedule.pk,self.entries[0].pk])]:
            response=self.client.post(reverse(route,args=args),{'day':1})
            self.assertEqual(response.status_code,302)
            self.assertIn('/accounts/login/',response.url)
        self.assertEqual(m.Schedule.objects.count(),1)
        self.entries[0].refresh_from_db()
        self.assertEqual(self.entries[0].day,0)

    def test_availability_ownership_invalid_times_and_permitted_update(self):
        other=m.Faculty.objects.create(department=self.department,employee_id='OTHER',full_name='Private Teacher')
        foreign=m.Availability.objects.create(faculty=other,day=0,start_time=time(8),end_time=time(9),kind='UNAVAILABLE')
        self.login()
        payload={'faculty':other.pk,'room':self.room.pk,'section':self.section.pk,'day':1,
                 'start_time':'08:00','end_time':'09:00','kind':'UNAVAILABLE'}
        self.assertEqual(self.client.post(reverse('my_availability_create'),payload).status_code,302)
        own=m.Availability.objects.get(faculty=self.faculty)
        self.assertIsNone(own.room_id)
        self.assertIsNone(own.section_id)
        self.assertContains(self.client.get(reverse('my_availability')),'Unavailable')
        for method in (self.client.get,self.client.post):
            self.assertEqual(method(reverse('my_availability_update',args=[foreign.pk]),payload).status_code,404)
        response=self.client.post(reverse('my_availability_update',args=[own.pk]),{**payload,'end_time':'07:00'})
        self.assertContains(response,'Start time must be earlier')
        own.refresh_from_db()
        self.assertEqual(own.end_time,time(9))
        self.assertEqual(self.client.post(reverse('my_availability_update',args=[own.pk]),{**payload,'end_time':'10:00'}).status_code,302)
        own.refresh_from_db()
        self.assertEqual(own.end_time,time(10))
        foreign.refresh_from_db()
        self.assertEqual(foreign.end_time,time(9))

    def test_workload_keeps_schedule_groups_and_fractional_minutes(self):
        from types import SimpleNamespace as V
        from .services.faculty_workload import published_workload
        entries=[V(schedule_id=s, schedule=V(pk=s), assignment=V(required_duration_minutes=minutes),
                   effective_section=V(pk=section)) for s,minutes,section in [(1,45,1),(1,30,1),(2,90,2)]]
        groups=published_workload(entries)
        self.assertEqual([(g['minutes'],g['hours'],g['meetings'],g['sections']) for g in groups],
                         [(75,1.25,2,1),(90,1.5,1,1)])
