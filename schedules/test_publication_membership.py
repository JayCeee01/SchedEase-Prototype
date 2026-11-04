"""Publication and term membership boundaries, on disposable databases only."""
from datetime import time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.publication import publish
from .services.manual_edits import copy_to_draft
from .services.conflicts import schedule_validation_messages
from .test_publication_helpers import legacy_case, upgrade
from django.test import SimpleTestCase
import subprocess
import sys


class PublicationMembershipTests(SchedulingDefectFixture):
    def setUp(self):
        self.actor=User.objects.create_superuser(username='phase4',password='synthetic-only')
        self.schedule=m.Schedule.objects.create(term=self.term,name='Complete')
        for i,meeting in enumerate(self.meetings):
            self.schedule.entries.create(assignment=meeting,room=self.room,day=0,
                start_time=time(8+i),end_time=time(9+i))

    def test_direct_model_publication_incomplete_and_complete_rejected(self):
        incomplete=m.Schedule.objects.create(term=self.term,name='Incomplete')
        for schedule in (incomplete,self.schedule):
            schedule.status='PUBLISHED'
            with self.assertRaisesMessage(ValidationError,'publication workflow'):
                schedule.save()
            schedule.refresh_from_db()
            self.assertEqual(schedule.status,'DRAFT')
            self.assertFalse(m.ScheduleSnapshot.objects.filter(schedule=schedule).exists())

    def test_bulk_raw_and_insert_publication_rejected(self):
        operations=[
            lambda:m.Schedule.objects.filter(pk=self.schedule.pk).update(status='PUBLISHED'),
            lambda:connection.cursor().execute("UPDATE schedules_schedule SET status='ARCHIVED' WHERE id=%s",[self.schedule.pk]),
            lambda:m.Schedule.objects.bulk_create([m.Schedule(term=self.term,name='Raw final',status='PUBLISHED')]),
            lambda:connection.cursor().execute("UPDATE schedules_schedule SET status='INVALID' WHERE id=%s",[self.schedule.pk]),
        ]
        for operation in operations:
            with self.assertRaises(IntegrityError),transaction.atomic(): operation()
        self.assertFalse(m.ScheduleSnapshot.objects.exists())

    def test_replacement_publication_and_finalized_victim_rejected(self):
        from .test_replacement_protection import replace_copy
        with self.assertRaises(IntegrityError),transaction.atomic():
            replace_copy(self.schedule,status='PUBLISHED')
        self.schedule,_=publish(self.schedule,self.actor)
        with self.assertRaises(IntegrityError),transaction.atomic():
            replace_copy(self.schedule,status='DRAFT',published_at=None)

    def test_valid_publication_and_copy_supersession(self):
        self.schedule,_=publish(self.schedule,self.actor)
        frozen=self.schedule.snapshot.data
        draft=copy_to_draft(source_id=self.schedule.pk,actor=self.actor)
        self.assertEqual(draft.status,'DRAFT')
        with self.assertRaises(ValidationError): publish(draft,self.actor)
        draft.refresh_from_db()
        replacement,archived=publish(draft,self.actor,replace_confirmed=True)
        self.assertEqual(archived.status,'ARCHIVED')
        self.assertEqual(replacement.status,'PUBLISHED')
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data,frozen)
        self.assertEqual(schedule_validation_messages(replacement),[])

    def test_validation_and_capture_failure_roll_back(self):
        incomplete=m.Schedule.objects.create(term=self.term,name='Incomplete')
        with self.assertRaises(ValidationError): publish(incomplete,self.actor)
        with patch('schedules.services.publication.ScheduleSnapshot.objects.get',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError): publish(self.schedule,self.actor)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status,'DRAFT')
        self.assertFalse(m.ScheduleSnapshot.objects.exists())
        self.assertFalse(m.ScheduleEntryAudit.objects.exists())

    def test_unauthorized_and_stale_publication(self):
        user=User.objects.create_user(username='not-admin')
        with self.assertRaises(ValidationError): publish(self.schedule,user)
        self.schedule.refresh_from_db()
        stale=m.Schedule.objects.get(pk=self.schedule.pk)
        self.schedule.name='Changed';self.schedule.save()
        with self.assertRaises(ValidationError): publish(stale,self.actor)

    def test_membership_insert_delete_reassignment_and_bulk(self):
        self.schedule,_=publish(self.schedule,self.actor)
        other=m.AcademicTerm.objects.create(name='Future',school_year='2027-2028',starts_on='2027-08-01',ends_on='2027-12-01')
        subject=m.Subject.objects.create(department=self.department,code='FUTURE',title='Future')
        parent=m.Assignment.objects.create(term=other,subject=subject,faculty=self.faculty,section=self.section)
        with self.assertRaises(ValidationError):
            m.Assignment.objects.create(term=self.term,subject=subject,faculty=self.faculty,section=self.section)
        for operation in (
            lambda:m.Assignment.objects.bulk_create([m.Assignment(term=self.term,subject=subject,faculty=self.faculty,section=self.section)]),
            lambda:m.Assignment.objects.filter(pk=parent.pk).update(term=self.term),
            lambda:connection.cursor().execute('DELETE FROM schedules_teachingassignment WHERE id=%s',[self.meetings[0].pk]),
            lambda:connection.cursor().execute('UPDATE schedules_teachingassignment SET term_id=%s WHERE id=%s',[other.pk,self.meetings[0].pk]),
        ):
            with self.assertRaises(IntegrityError),transaction.atomic():operation()
        with self.assertRaises(ProtectedError):self.meetings[0].delete()
        self.assertEqual(schedule_validation_messages(self.schedule),[])
        # New work in another term is not permanently prohibited.
        m.TeachingAssignment.objects.create(assignment=parent,duration_minutes=60)

    def test_archived_membership_retained(self):
        self.schedule,_=publish(self.schedule,self.actor)
        draft=copy_to_draft(source_id=self.schedule.pk,actor=self.actor)
        publish(draft,self.actor,replace_confirmed=True)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.TeachingAssignment.objects.bulk_create([m.TeachingAssignment(term=self.term,
                subject=self.subject,faculty=self.faculty,section=self.section,meeting_index=3,duration_minutes=60)])
        self.assertEqual(schedule_validation_messages(m.Schedule.objects.get(pk=self.schedule.pk)),[])

    @legacy_case
    def test_legacy_unreferenced_parent_replacement_cannot_escape_term(self):
        from .test_replacement_protection import replace_copy
        subject=m.Subject.objects.create(department=self.department,code='LEGACY',title='Legacy')
        empty=m.Assignment.objects.create(term=self.term,subject=subject,faculty=self.faculty,section=self.section)
        other=m.AcademicTerm.objects.create(name='Future',school_year='2027',starts_on='2027-01-01',ends_on='2027-12-31')
        free=m.Assignment.objects.create(term=other,subject=subject,faculty=self.faculty,section=self.section)
        self.schedule.status='PUBLISHED';self.schedule.save()
        upgrade()
        with self.assertRaises(IntegrityError),transaction.atomic():replace_copy(empty,term_id=other.pk)
        with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as cursor:
            cursor.execute('UPDATE OR REPLACE schedules_assignment SET id=%s WHERE id=%s',[empty.pk,free.pk])
        with self.assertRaises(ProtectedError):empty.delete()
        empty.refresh_from_db()
        self.assertEqual(empty.term_id,self.term.pk)


class PublicationMembershipMigrationTests(SimpleTestCase):
    def test_forward_reverse_preserves_legacy_and_native_enforcement(self):
        script=r'''
import os,sqlite3
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django;django.setup()
from django.core.management import call_command
from django.db import connection
from schedules import models as m
from schedules.test_known_defects import SchedulingDefectFixture
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0033',verbosity=0)
SchedulingDefectFixture.setUpTestData(); f=SchedulingDefectFixture()
# Preserve pre-existing incomplete history without legitimizing new finalization.
s=m.Schedule.objects.create(term=f.term,name='Legacy',status='ARCHIVED')
draft=m.Schedule.objects.create(term=f.term,name='Draft')
from schedules.test_shs_generation import ControlledSHSGenerationTests
from schedules.test_contact_workload import ContactPolicyTests
from schedules.services.shs_scheduling import generate_shs
from schedules.services.publication import publish
shs=ControlledSHSGenerationTests();shs.setUp();ContactPolicyTests.policy(shs)
generated=generate_shs(shs.term,shs.settings,actor=shs.actor,seed=17)
publish(generated,shs.actor)
assert m.SHSApprovalEvidence.objects.exists()
tables=(m.Schedule,m.ScheduleSnapshot,m.Assignment,m.TeachingAssignment,m.ScheduleEntry,
        m.SHSApprovalEvidence,m.SHSMeetingBinding,m.FacultyContactMinutePolicy,m.CurriculumVersion)
before={x.__name__:list(x.objects.values()) for x in tables}
with connection.cursor() as c:
 c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"); old=dict(c.fetchall())
for target in ('0034','0033','0034'):
 call_command('migrate','schedules',target,verbosity=0)
 assert before=={x.__name__:list(x.objects.values()) for x in tables}
 with connection.cursor() as c:
  c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"); current=dict(c.fetchall())
  assert all(current[k]==v for k,v in old.items())
  c.execute('PRAGMA integrity_check');assert c.fetchall()==[('ok',)]
  c.execute('PRAGMA foreign_key_check');assert c.fetchall()==[]
native=sqlite3.connect(':memory:');connection.connection.backup(native)
for sql in ("UPDATE schedules_schedule SET status='PUBLISHED' WHERE id="+str(draft.pk),
            'DELETE FROM schedules_teachingassignment',
            'INSERT OR REPLACE INTO schedules_teachingassignment SELECT * FROM schedules_teachingassignment'):
 try: native.execute(sql)
 except sqlite3.DatabaseError: native.rollback()
 else: raise AssertionError('Native bypass: '+sql)
assert before=={x.__name__:list(x.objects.values()) for x in tables}
native.close()
'''
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
