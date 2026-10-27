from datetime import time
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction, connection
from django.test import RequestFactory
from django.urls import reverse
from . import models as m
from .forms import MODEL_FORMS
from .test_known_defects import SchedulingDefectFixture
from .protection import archive_transition


class FacultyAccountLinkTests(SchedulingDefectFixture):
    def setUp(self):
        self.actor=User.objects.create_superuser('synthetic-admin',password='test')
        self.account=User.objects.create_user('synthetic-faculty',password='test')
        m.Profile.objects.create(user=self.account,role='FACULTY')
        self.schedule=m.Schedule.objects.create(term=self.term,name='Historical')
        for i,meeting in enumerate(self.meetings):
            self.schedule.entries.create(assignment=meeting,room=self.room,day=0,
                start_time=time(8+i),end_time=time(9+i))
        self.schedule.status='PUBLISHED'
        self.schedule.save()
        self.original_snapshot=m.ScheduleSnapshot.objects.get(schedule=self.schedule).data
        self.original_entries=list(self.schedule.entries.values())
        self.original_meetings=list(m.TeachingAssignment.objects.values())

    def assert_history(self):
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data,self.original_snapshot)
        self.assertEqual(list(self.schedule.entries.values()),self.original_entries)
        self.assertEqual(list(m.TeachingAssignment.objects.values()),self.original_meetings)

    def test_link_and_unlink_finalized_faculty(self):
        for status in ('PUBLISHED','ARCHIVED'):
            if status=='ARCHIVED':
                with archive_transition():
                    self.schedule.status=status
                    self.schedule.save()
            for account in (self.account,None):
                self.faculty.user=account
                self.faculty.full_clean()
                self.faculty.save(update_fields=['user'])
                self.faculty.refresh_from_db()
                self.assertEqual(self.faculty.user_id,account.pk if account else None)
                self.assert_history()

    def payload(self,user):
        return dict(user=user,department=self.department.pk,employee_id=self.faculty.employee_id,
            full_name=self.faculty.full_name,max_weekly_hours=self.faculty.max_weekly_hours)

    def test_admin_ui_link_and_unlink(self):
        self.client.force_login(self.actor)
        for user in (self.account.pk,''):
            response=self.client.post(reverse('resource_update',args=['faculty',self.faculty.pk]),self.payload(user))
            self.assertEqual(response.status_code,302)
            self.faculty.refresh_from_db()
            self.assertEqual(self.faculty.user_id,user or None)
            self.assert_history()

    def test_django_admin_exposes_only_account_field(self):
        request=RequestFactory().get('/')
        request.user=self.actor
        controller=admin.site._registry[m.Faculty]
        form_class=controller.get_form(request,self.faculty)
        self.assertEqual(set(form_class.base_fields),{'user'})
        form=form_class({'user':self.account.pk},instance=self.faculty)
        self.assertTrue(form.is_valid(),form.errors)
        form.save()
        self.assert_history()

    def test_uniqueness_and_existing_content_guards(self):
        m.Faculty.objects.create(department=self.department,employee_id='OTHER',full_name='Other',user=self.account)
        form=MODEL_FORMS['faculty'](self.payload(self.account.pk),instance=self.faculty)
        self.assertFalse(form.is_valid())
        self.assertIn('user',form.errors)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.Faculty.objects.filter(pk=self.faculty.pk).update(user=self.account)
        self.faculty.full_name='Changed'
        with self.assertRaises(ValidationError): self.faculty.save()
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.Faculty.objects.filter(pk=self.faculty.pk).update(full_name='Changed')
        self.assert_history()

    def test_sql_link_preserves_uniqueness_and_history(self):
        m.Faculty.objects.filter(pk=self.faculty.pk).update(user=self.account)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.user_id,self.account.pk)
        self.assert_history()

    def test_faculty_and_student_cannot_link_accounts(self):
        student=User.objects.create_user('synthetic-student',password='test')
        m.Profile.objects.create(user=student,role='STUDENT')
        for user in (self.account,student):
            self.client.force_login(user)
            response=self.client.post(reverse('resource_update',args=['faculty',self.faculty.pk]),self.payload(user.pk))
            self.assertIn(response.status_code,(302,403))
            self.faculty.refresh_from_db()
            self.assertIsNone(self.faculty.user_id)
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_staff or self.account.is_superuser)
        self.assertEqual(self.account.profile.role,'FACULTY')


from django.test import SimpleTestCase


class FacultyAccountLinkMigrationTests(SimpleTestCase):
    def test_populated_upgrade_and_reverse_preserve_other_guards(self):
        import subprocess, sys
        script = r"""
import os
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection, IntegrityError
from schedules import models as m
from django.contrib.auth.models import User
from schedules.test_known_defects import SchedulingDefectFixture
from datetime import time
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0026_shs_meeting_snapshots',verbosity=0)
SchedulingDefectFixture.setUpTestData.__func__(SchedulingDefectFixture)
f=SchedulingDefectFixture
account=User.objects.create_user('synthetic-link')
schedule=m.Schedule.objects.create(term=f.term,name='Protected fixture')
schedule.entries.create(assignment=f.meetings[0],room=f.room,day=0,start_time=time(8),end_time=time(9))
schedule.status='PUBLISHED'
schedule.save()
snapshot=m.ScheduleSnapshot.objects.get(schedule=schedule).data
with connection.cursor() as cursor:
    cursor.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
    before=dict(cursor.fetchall())
try:
    m.Faculty.objects.filter(pk=f.faculty.pk).update(user=account)
except IntegrityError:
    pass
else:
    raise AssertionError('Old trigger should reject linking')
call_command('migrate','schedules','0027_faculty_account_link',verbosity=0)
m.Faculty.objects.filter(pk=f.faculty.pk).update(user=account)
assert m.ScheduleSnapshot.objects.get(schedule=schedule).data==snapshot
with connection.cursor() as cursor:
    cursor.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
    after=dict(cursor.fetchall())
    assert before.keys()==after.keys()
    assert all(sql==after[name] for name,sql in before.items() if name!='h2_faculty_update')
    cursor.execute('PRAGMA integrity_check')
    assert cursor.fetchall()==[('ok',)]
    cursor.execute('PRAGMA foreign_key_check')
    assert not cursor.fetchall()
call_command('migrate','schedules','0026_shs_meeting_snapshots',verbosity=0)
try:
    m.Faculty.objects.filter(pk=f.faculty.pk).update(user=None)
except IntegrityError:
    pass
else:
    raise AssertionError('Reverse migration must restore the original guard')
assert m.ScheduleSnapshot.objects.get(schedule=schedule).data==snapshot
"""
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
