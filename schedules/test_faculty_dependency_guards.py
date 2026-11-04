from .test_publication_helpers import legacy_case, upgrade
from copy import deepcopy
from datetime import time
import subprocess
import sys
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.publication import publish
from .services.conflicts import schedule_validation_messages
from .services.faculty_dependencies import dependencies


class FacultyDependencyTests(SchedulingDefectFixture):
    def setUp(self):
        self.actor=User.objects.create_superuser('dependency-admin',password='synthetic-test')
        self.credential=m.Credential.objects.create(name='Dependency license')
        self.requirement=m.SubjectCredentialRequirement.objects.create(subject=self.subject,required_credential=self.credential)
        self.held=m.FacultyCredential.objects.create(faculty=self.faculty,credential=self.credential,issued_on=self.term.starts_on)
        self.other=m.Faculty.objects.create(department=self.department,employee_id='DEP2',full_name='Other synthetic faculty')

    def finalize(self):
        schedule=m.Schedule.objects.create(term=self.term,name='Dependency test')
        for n,meeting in enumerate(self.meetings):
            schedule.entries.create(assignment=meeting,room=self.room,day=0,start_time=time(8+n),end_time=time(9+n))
        return publish(schedule,self.actor,replace_confirmed=True)[0]

    def period(self, **kwargs):
        values=dict(faculty=self.faculty,day=0,start_time=time(7),end_time=time(11),kind='AVAILABLE')
        values.update(kwargs)
        return m.Availability.objects.create(**values)

    def test_expiry_issue_date_ownership_type_and_deletion(self):
        schedule=self.finalize()
        for changes in ({'expires_on':self.term.starts_on}, {'issued_on':None},
                        {'faculty':self.other}, {'credential':m.Credential.objects.create(name='Unrelated')}):
            with self.subTest(changes=tuple(changes)):
                self.held.refresh_from_db()
                for key,value in changes.items(): setattr(self.held,key,value)
                with self.assertRaises(ValidationError): self.held.full_clean()
                with self.assertRaises(ValidationError): self.held.save()
        self.held.refresh_from_db()
        with self.assertRaises(ProtectedError),transaction.atomic(): self.held.delete()
        self.assertEqual(list(schedule_validation_messages(schedule)),[])

    def test_independently_qualified_faculty(self):
        equivalent=m.Credential.objects.create(name='Equivalent license')
        self.requirement.acceptable_equivalents.add(equivalent)
        alt=m.FacultyCredential.objects.create(faculty=self.faculty,credential=equivalent,issued_on=self.term.starts_on)
        schedule=self.finalize()
        self.held.delete()
        self.assertEqual(list(schedule_validation_messages(schedule)),[])
        with self.assertRaises(ProtectedError),transaction.atomic(): alt.delete()

    def test_scoped_approval_and_history_remain_valid(self):
        from .test_support.credential_approvals import scoped_override
        self.held.delete()
        for meeting in self.meetings:
            scoped_override(assignment=meeting,faculty=self.faculty,subject=self.subject,admin_user=self.actor,reason='Explicit isolated approval')
        held=m.FacultyCredential.objects.create(faculty=self.faculty,credential=self.credential,issued_on=self.term.starts_on)
        schedule=self.finalize()
        frozen=deepcopy(m.ScheduleSnapshot.objects.get(schedule=schedule).data)
        held.delete()
        self.assertEqual(list(schedule_validation_messages(schedule)),[])
        self.assertEqual(m.CredentialApprovalEvidence.objects.count(),2)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data,frozen)

    def test_descriptions_and_unrelated_faculty(self):
        self.finalize()
        self.held.notes='Review note'; self.held.issued_by='Issuing institution'; self.held.save()
        unrelated=m.FacultyCredential.objects.create(faculty=self.other,credential=self.credential)
        unrelated.delete()
        self.period(faculty=self.other,kind='UNAVAILABLE')

    def test_unavailability_conflict_and_outside_commitments(self):
        self.finalize()
        with self.assertRaises(ValidationError): self.period(kind='UNAVAILABLE',start_time=time(8),end_time=time(9))
        safe=self.period(kind='UNAVAILABLE',start_time=time(10),end_time=time(11))
        safe.start_time=time(9)
        with self.assertRaises(ValidationError): safe.save()
        safe.refresh_from_db(); safe.delete()
        self.period(kind='PREFERRED',start_time=time(8),end_time=time(9))

    def test_first_explicit_window_restricts_the_whole_week(self):
        self.finalize()
        with self.assertRaises(ValidationError): self.period(day=1)
        self.period()

    def test_touching_windows_and_deletion_of_last_window(self):
        first=self.period(start_time=time(7),end_time=time(8,30))
        second=self.period(start_time=time(8,30),end_time=time(11))
        self.finalize()
        with self.assertRaises(ProtectedError),transaction.atomic(): first.delete()
        second.start_time=time(7); second.save()
        first.delete(); second.delete()

    def test_availability_reassignment_old_and_new_owners(self):
        first=self.period(); self.period(day=1)
        self.finalize()
        first.faculty=self.other
        with self.assertRaises(ValidationError): first.save()
        unavailable=self.period(faculty=self.other,kind='UNAVAILABLE',start_time=time(8),end_time=time(9))
        unavailable.faculty=self.faculty
        with self.assertRaises(ValidationError): unavailable.save()

    def test_archived_dependencies(self):
        old=self.finalize(); self.finalize(); old.refresh_from_db()
        self.assertEqual(old.status,'ARCHIVED')
        self.assertIn((old.pk,0),dependencies([self.faculty.pk]))
        with self.assertRaises(ProtectedError),transaction.atomic(): self.held.delete()

    def test_bulk_and_raw_credentials_and_replacement(self):
        self.finalize()
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.FacultyCredential.objects.filter(pk=self.held.pk).update(expires_on=self.term.starts_on)
        statements=[
            ('UPDATE schedules_facultycredential SET expires_on=%s WHERE id=%s',[self.term.starts_on,self.held.pk]),
            ('DELETE FROM schedules_facultycredential WHERE id=%s',[self.held.pk]),
            ('UPDATE schedules_facultycredential SET faculty_id=%s WHERE id=%s',[self.other.pk,self.held.pk]),
            ("INSERT OR REPLACE INTO schedules_facultycredential (id,faculty_id,credential_id,issued_by,notes) VALUES (%s,%s,%s,'','')",[self.held.pk,self.other.pk,self.credential.pk]),
            ("INSERT OR REPLACE INTO schedules_facultycredential (faculty_id,credential_id,issued_by,notes) VALUES (%s,%s,'','')",[self.faculty.pk,self.credential.pk]),
        ]
        for sql,args in statements:
            with self.subTest(sql=sql),self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c: c.execute(sql,args)

    def test_bulk_delete_foreign_keys_and_transaction_rollback(self):
        schedule=self.finalize()
        frozen=deepcopy(m.ScheduleSnapshot.objects.get(schedule=schedule).data)
        with self.assertRaises(ProtectedError),transaction.atomic():
            m.FacultyCredential.objects.filter(pk=self.held.pk).delete()
        with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c:
            c.execute('DELETE FROM schedules_credential WHERE id=%s',[self.credential.pk])
            connection.check_constraints()  # SQLite FKs are deferred until commit.
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.FacultyCredential.objects.filter(pk=self.held.pk).update(notes='Must roll back')
            m.Availability.objects.bulk_create([m.Availability(faculty=self.faculty,day=0,
                start_time=time(8),end_time=time(9),kind='UNAVAILABLE')])
        self.held.refresh_from_db()
        self.assertEqual(self.held.notes,'')
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data,frozen)

    def test_overlapping_windows_and_partial_update_fields(self):
        first=self.period(start_time=time(7),end_time=time(9))
        self.period(start_time=time(8),end_time=time(11))
        schedule=self.finalize()
        first.delete()
        self.held.expires_on=self.term.starts_on  # Not part of this partial write.
        self.held.notes='Harmless note'
        self.held.save(update_fields=['notes'])
        self.held.refresh_from_db()
        self.assertIsNone(self.held.expires_on)
        self.assertEqual(list(schedule_validation_messages(schedule)),[])

    def test_legacy_unproven_override_cannot_authorize_credential_loss(self):
        m.CredentialOverride.objects.create(assignment=self.meetings[0],faculty=self.faculty,
            subject=self.subject,admin_user=self.actor,reason='Old approval',missing_credentials='License')
        self.finalize()
        with self.assertRaises(ProtectedError),transaction.atomic(): self.held.delete()

    def test_form_feedback_and_permissions(self):
        from django.urls import reverse
        self.finalize()
        self.client.force_login(self.actor)
        response=self.client.post(reverse('resource_update',args=['faculty-credentials',self.held.pk]),
            {'faculty':self.faculty.pk,'credential':self.credential.pk,'issued_on':str(self.term.starts_on),
             'expires_on':str(self.term.starts_on)})
        self.assertContains(response,'Affected published or archived schedules')
        self.held.refresh_from_db(); self.assertIsNone(self.held.expires_on)
        user=User.objects.create_user('dependency-viewer',password='synthetic')
        m.Profile.objects.create(user=user,role='FACULTY')
        self.client.force_login(user)
        response=self.client.post(reverse('resource_delete',args=['faculty-credentials',self.held.pk]))
        self.assertEqual(response.status_code,302)
        self.assertTrue(m.FacultyCredential.objects.filter(pk=self.held.pk).exists())

    def test_raw_availability_insert_update_delete_replace(self):
        window=self.period(); self.period(day=1)
        blocked=self.period(faculty=self.other,kind='UNAVAILABLE',start_time=time(8),end_time=time(9))
        self.finalize()
        statements=[
            ("INSERT INTO schedules_availability (faculty_id,day,start_time,end_time,kind) VALUES (%s,0,'08:00:00','09:00:00','UNAVAILABLE')",[self.faculty.pk]),
            ('DELETE FROM schedules_availability WHERE id=%s',[window.pk]),
            ('UPDATE schedules_availability SET faculty_id=%s WHERE id=%s',[self.faculty.pk,blocked.pk]),
            ("INSERT OR REPLACE INTO schedules_availability (id,faculty_id,day,start_time,end_time,kind) VALUES (%s,%s,1,'08:00:00','09:00:00','AVAILABLE')",[window.pk,self.other.pk]),
        ]
        for sql,args in statements:
            with self.subTest(sql=sql),self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c: c.execute(sql,args)

    def test_malformed_history_fails_closed(self):
        schedule=self.finalize()
        from importlib import import_module
        original=import_module('schedules.migrations.0012_historical_snapshots').TRIGGERS['h2_snapshot_update']
        # Deliberately malformed legacy evidence, only inside the disposable test DB.
        with connection.cursor() as c:
            c.execute('DROP TRIGGER h2_snapshot_update')
            c.execute('UPDATE schedules_schedulesnapshot SET data=%s WHERE schedule_id=%s',['[]',schedule.pk])
            c.execute(original)
        self.assertTrue(any(row[1] for row in dependencies([self.faculty.pk])))
        with self.assertRaises(ValidationError): self.period(kind='PREFERRED')
        with self.assertRaises(ProtectedError),transaction.atomic(): self.held.delete()
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data,[])

    @legacy_case
    def test_frozen_extra_entry_is_uncertain_even_without_live_entries(self):
        schedule=m.Schedule.objects.create(term=self.term,name='Legacy empty schedule',status='PUBLISHED')
        from importlib import import_module
        import json
        original=import_module('schedules.migrations.0012_historical_snapshots').TRIGGERS['h2_snapshot_update']
        with connection.cursor() as c:
            c.execute('DROP TRIGGER h2_snapshot_update')
            c.execute('UPDATE schedules_schedulesnapshot SET data=%s WHERE schedule_id=%s',
                      [json.dumps({'entries':[{'faculty':{'id':self.faculty.pk}}]}),schedule.pk])
            c.execute(original)
        upgrade()
        self.assertIn((schedule.pk,1),dependencies([self.faculty.pk]))
        with self.assertRaises(ValidationError): self.period(kind='PREFERRED')


class SHSFacultyDependencyTests(TestCase):
    def test_shs_dates_qualification_and_availability(self):
        from .test_shs_generation import ControlledSHSGenerationTests
        from .test_contact_workload import ContactPolicyTests
        from .services.shs_scheduling import generate_shs
        ControlledSHSGenerationTests.setUp(self); ContactPolicyTests.policy(self)
        credential=m.Credential.objects.create(name='SHS isolated license')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject,required_credential=credential)
        held=m.FacultyCredential.objects.create(faculty=self.faculty,credential=credential,issued_on=self.term.starts_on)
        schedule=generate_shs(self.term,self.settings,actor=self.actor,seed=17)
        schedule,_=publish(schedule,self.actor)
        frozen=deepcopy(m.ScheduleSnapshot.objects.get(schedule=schedule).data)
        with self.assertRaises(ProtectedError),transaction.atomic(): held.delete()
        with self.assertRaises(ValidationError):
            m.Availability.objects.create(faculty=self.faculty,day=0,start_time=time(8),end_time=time(10),kind='UNAVAILABLE')
        m.Availability.objects.create(faculty=self.faculty,day=1,start_time=time(8),end_time=time(10),kind='UNAVAILABLE')
        self.assertEqual(list(schedule_validation_messages(schedule)),[])
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data,frozen)


class FacultyDependencyMigrationTests(SimpleTestCase):
    def test_forward_reverse_preserves_history(self):
        script=r'''
import os
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from schedules import models as m
from schedules.test_faculty_dependency_guards import FacultyDependencyTests
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0029',verbosity=0)
f=FacultyDependencyTests(); f.setUpTestData(); f.setUp()
from schedules.test_support.credential_approvals import scoped_override
f.held.delete()
for meeting in f.meetings:
    scoped_override(assignment=meeting,faculty=f.faculty,subject=f.subject,admin_user=f.actor,reason='Migration fixture approval')
f.held=m.FacultyCredential.objects.create(faculty=f.faculty,credential=f.credential,issued_on=f.term.starts_on)
m.CredentialOverride.objects.create(assignment=f.meetings[0],faculty=f.faculty,subject=f.subject,
    admin_user=f.actor,reason='Legacy history',missing_credentials='Historical text')
s=f.finalize()
models=(m.Schedule,m.ScheduleEntry,m.ScheduleSnapshot,m.FacultyCredential,m.CredentialOverride,m.CredentialApprovalEvidence)
before={x.__name__:list(x.objects.values()) for x in models}
with connection.cursor() as c:
    c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
    triggers=dict(c.fetchall())
for target in ('0030','0029','0030'):
    call_command('migrate','schedules',target,verbosity=0)
    assert before=={x.__name__:list(x.objects.values()) for x in models}
    with connection.cursor() as c:
        c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
        current=dict(c.fetchall())
        assert all(current[k]==v for k,v in triggers.items())
        c.execute('PRAGMA integrity_check'); assert c.fetchall()==[('ok',)]
        c.execute('PRAGMA foreign_key_check'); assert c.fetchall()==[]
import sqlite3
native=sqlite3.connect(':memory:')
connection.connection.backup(native)
try:
    native.execute("INSERT INTO schedules_availability (faculty_id,day,start_time,end_time,kind) VALUES (?,0,'08:00:00','09:00:00','UNAVAILABLE')",(f.faculty.pk,))
except sqlite3.IntegrityError:
    native.rollback()
else:
    raise AssertionError('Native SQLite must enforce protection without Django or registered application functions')
native.close()
'''
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
