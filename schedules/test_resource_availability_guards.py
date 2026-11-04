from .test_publication_helpers import finalize
"""Whole-policy protection, exercised exclusively on disposable databases."""
from datetime import time
from importlib import import_module
import json
import subprocess
import sys

from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase

from . import models as m
from .protection import archive_transition
from .services.conflicts import schedule_validation_messages
from .test_known_defects import SchedulingDefectFixture
from .test_replacement_protection import replace_copy


class ResourceAvailabilityTests(SchedulingDefectFixture):
    def setUp(self):
        self.schedule = m.Schedule.objects.create(term=self.term, name='Resource commitments')
        for index, meeting in enumerate(self.meetings):
            self.schedule.entries.create(assignment=meeting, room=self.room, day=0,
                start_time=time(8+index), end_time=time(9+index))
        finalize(self.schedule)
        self.frozen = m.ScheduleSnapshot.objects.get(schedule=self.schedule).data

    def period(self, owner, **changes):
        values = {owner._meta.model_name: owner, 'day': 0, 'start_time': time(7),
                  'end_time': time(11), 'kind': 'AVAILABLE'}
        values.update(changes)
        return m.Availability.objects.create(**values)

    def assert_intact(self):
        self.assertEqual(list(schedule_validation_messages(self.schedule)), [])
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, self.frozen)
        connection.check_constraints()

    def test_room_and_section_conflicts_model_clean_and_sql(self):
        for owner in (self.room, self.section):
            row = m.Availability(**{owner._meta.model_name: owner}, day=0,
                start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
            with self.subTest(owner=owner._meta.model_name):
                with self.assertRaisesMessage(ValidationError, self.schedule.name):
                    row.full_clean()
                with self.assertRaises(ValidationError):
                    row.save()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    m.Availability.objects.bulk_create([row])
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(f"INSERT INTO schedules_availability ({owner._meta.model_name}_id,day,start_time,end_time,kind) VALUES (%s,0,'08:00:00','09:00:00','UNAVAILABLE')", [owner.pk])
        self.assert_intact()

    def test_safe_outside_touching_and_unrelated_periods(self):
        for owner in (self.room, self.section):
            self.period(owner, start_time=time(7), end_time=time(8), kind='UNAVAILABLE')
            self.period(owner, start_time=time(10), end_time=time(11), kind='UNAVAILABLE')
            self.period(owner, day=1, kind='UNAVAILABLE')
        free = m.Room.objects.create(name='Unrelated', capacity=30, room_type='LECTURE')
        self.period(free, kind='UNAVAILABLE')
        self.assert_intact()

    def test_first_available_window_affects_whole_week(self):
        for owner in (self.room, self.section):
            with self.assertRaises(ValidationError):
                self.period(owner, day=1)
        self.assert_intact()

    def test_adjacent_and_overlapping_windows_deletion_and_defaults(self):
        for owner in (self.room, self.section):
            broad = self.period(owner)
            left = self.period(owner, start_time=time(8), end_time=time(8,30))
            right = self.period(owner, start_time=time(8,30), end_time=time(10))
            broad.delete()  # Touching windows jointly cover both commitments.
            overlap = self.period(owner, start_time=time(8,15), end_time=time(10))
            right.delete()
            with self.assertRaises(ProtectedError), transaction.atomic():
                left.delete()
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute('DELETE FROM schedules_availability WHERE id=%s', [left.pk])
            replacement = self.period(owner)
            left.delete()
            overlap.delete()
            replacement.delete()  # No explicit AVAILABLE rows restores defaults.
        self.assert_intact()

    def test_modification_bulk_update_and_update_fields(self):
        for owner in (self.room, self.section):
            row = self.period(owner)
            row.end_time = time(8,30)
            with self.assertRaises(ValidationError):
                row.save()
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.Availability.objects.bulk_update([row], ['end_time'])
            row.save(update_fields=['day'])  # Unsaved end_time is not submitted.
            row.refresh_from_db()
            self.assertEqual(row.end_time, time(11))
        self.assert_intact()

    def test_owner_reassignment_checks_old_and_new_policy(self):
        for owner in (self.room, self.section):
            broad = self.period(owner)
            left = self.period(owner, start_time=time(8), end_time=time(9))
            self.period(owner, start_time=time(9), end_time=time(10))
            broad.delete()
            free = m.Room.objects.create(name='Free '+owner._meta.model_name, capacity=30, room_type='LECTURE')
            setattr(left, owner._meta.model_name, None)
            left.room = free
            with self.assertRaises(ValidationError):
                left.save()
            blocker = self.period(free, start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
            blocker.room = None
            setattr(blocker, owner._meta.model_name, owner)
            with self.assertRaises(ValidationError):
                blocker.save()
        self.assert_intact()

    def test_safe_owner_reassignment(self):
        row = self.period(self.room, start_time=time(10), end_time=time(11), kind='UNAVAILABLE')
        row.room = None
        row.section = self.section
        row.save()
        row.delete()
        self.assert_intact()

    def test_bulk_delete_and_raw_update(self):
        for owner in (self.room, self.section):
            harmless = self.period(owner, day=1, kind='UNAVAILABLE')
            m.Availability.objects.filter(pk=harmless.pk).delete()
            broad = self.period(owner)
            left = self.period(owner, start_time=time(8), end_time=time(9))
            self.period(owner, start_time=time(9), end_time=time(10))
            broad.delete()
            with self.assertRaises(ProtectedError), transaction.atomic():
                m.Availability.objects.filter(pk=left.pk).delete()
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE schedules_availability SET kind='UNAVAILABLE' WHERE id=%s", [left.pk])
        self.assert_intact()

    def test_room_preferences_and_section_kind_validation(self):
        preferred = self.period(self.room, kind='PREFERRED')
        preferred.delete()
        row = m.Availability(section=self.section, day=0, start_time=time(8), end_time=time(9), kind='PREFERRED')
        with self.assertRaises(ValidationError):
            row.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Availability.objects.bulk_create([row])
        self.assert_intact()

    def test_replace_and_update_replace_include_implicit_victim(self):
        for owner in (self.room, self.section):
            broad = self.period(owner)
            left = self.period(owner, start_time=time(8), end_time=time(9))
            self.period(owner, start_time=time(9), end_time=time(10))
            broad.delete()
            free = m.Room.objects.create(name='Replacement '+owner._meta.model_name, capacity=30, room_type='LECTURE')
            source = self.period(free)
            with self.assertRaises(IntegrityError), transaction.atomic():
                replace_copy(source, id=left.pk)
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute('UPDATE OR REPLACE schedules_availability SET id=%s WHERE id=%s', [left.pk, source.pk])
            # Safe replacement of the same row is not a blanket prohibition.
            replace_copy(left, start_time='07:30:00')
        self.assert_intact()

    def test_availability_unique_inventory(self):
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA index_list(schedules_availability)')
            self.assertFalse([row for row in cursor.fetchall() if row[2]])

    def test_archived_and_transaction_rollback(self):
        finalize(self.schedule, archived=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.period(self.room, day=1, kind='UNAVAILABLE')
            m.Availability.objects.bulk_create([m.Availability(section=self.section, day=0,
                start_time=time(8), end_time=time(9), kind='UNAVAILABLE')])
        self.assertEqual(m.Availability.objects.count(), 0)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, self.frozen)

    def test_malformed_or_inconsistent_history_fails_closed(self):
        trigger = import_module('schedules.migrations.0012_historical_snapshots').TRIGGERS['h2_snapshot_update']
        wrong_room = json.loads(json.dumps(self.frozen))
        wrong_room['entries'][0]['room']['id'] = 9999
        for evidence in ([], None, wrong_room):
            with connection.cursor() as cursor:
                cursor.execute('DROP TRIGGER h2_snapshot_update')
                cursor.execute('UPDATE schedules_schedulesnapshot SET data=%s WHERE schedule_id=%s', [json.dumps(evidence), self.schedule.pk])
                cursor.execute(trigger)
            with self.assertRaisesMessage(ValidationError, 'Historical'):
                self.period(self.room, day=1, kind='UNAVAILABLE')
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.Availability.objects.bulk_create([m.Availability(section=self.section, day=1,
                    start_time=time(8), end_time=time(9), kind='UNAVAILABLE')])

    def test_drafts_do_not_reserve_resources(self):
        free = m.Room.objects.create(name='Draft room', capacity=30, room_type='LECTURE')
        draft = m.Schedule.objects.create(term=self.term, name='Draft')
        draft.entries.create(assignment=self.meetings[0], room=free, day=1, start_time=time(8), end_time=time(9))
        self.period(free, day=1, kind='UNAVAILABLE')

    def test_owner_commits_are_entry_specific(self):
        term = m.AcademicTerm.objects.create(name='Other', school_year=self.term.school_year,
            starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        other = m.Section.objects.create(program=self.section.program, year_level=self.section.year_level, name='B', size=20)
        room = m.Room.objects.create(name='Other booked room', capacity=30, room_type='LECTURE')
        schedule = m.Schedule.objects.create(term=term, name='Separate owners')
        for index, (section, booked_room) in enumerate(((self.section, self.room), (other, room))):
            subject = m.Subject.objects.create(department=self.department, code='ONE'+str(index), title='One hour', lecture_hours=1)
            meeting = m.TeachingAssignment.objects.create(term=term, subject=subject, section=section,
                faculty=self.faculty, component='LECTURE', meeting_index=1, duration_minutes=60)
            schedule.entries.create(assignment=meeting, room=booked_room, day=1,
                start_time=time(8+index), end_time=time(9+index))
        finalize(schedule)
        for owner in (other, room):
            self.period(owner, day=1, start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
            with self.assertRaises(ValidationError):
                self.period(owner, day=1, start_time=time(9), end_time=time(10), kind='UNAVAILABLE')
        self.assertEqual(list(schedule_validation_messages(schedule)), [])


class SHSResourceAvailabilityTests(TestCase):
    def setUp(self):
        from .test_participation_protection import fixture
        fixture(self)
        self.frozen = m.ScheduleSnapshot.objects.get(schedule=self.schedule).data

    def assert_section_blocked(self, section):
        row = m.Availability(section=section, day=0, start_time=time(7), end_time=time(19), kind='UNAVAILABLE')
        with self.assertRaises(ValidationError):
            row.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Availability.objects.bulk_create([row])

    def test_primary_additional_room_and_safe_day(self):
        for section in (self.section, self.extra):
            self.assert_section_blocked(section)
            m.Availability.objects.create(section=section, day=1, start_time=time(7), end_time=time(19), kind='UNAVAILABLE')
        with self.assertRaises(ValidationError):
            m.Availability.objects.create(room=self.room, day=0, start_time=time(7), end_time=time(19), kind='UNAVAILABLE')
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, self.frozen)

    def legacy_participation_case(self, mode):
        # Construct pre-0033 historical drift at its actual schema version.
        # Never remove the new approval guards to make a fixture pass.
        script = r'''import os,sys
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from importlib import import_module
from schedules import models as m
from schedules.test_resource_availability_guards import SHSResourceAvailabilityTests
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0032',verbosity=0)
f=SHSResourceAvailabilityTests(); f.setUp()
mode=sys.argv[1]
if mode=='frozen':
    section=f.extra
    name='shs_participation_delete'
    statement='DELETE FROM schedules_shssectionparticipation WHERE id=%s'
    params=[f.participation.pk]
else:
    section=m.Section.objects.create(program=f.extra_program,year_level=f.year,cohort=f.extra.cohort,name='C',size=1)
    name='shs_participation_insert'
    statement='INSERT INTO schedules_shssectionparticipation(configuration_id,section_id) VALUES(%s,%s)'
    params=[f.config.pk,section.pk]
# The old fixture intentionally represents historic live/frozen divergence.
with connection.cursor() as cursor:
    cursor.execute('DROP TRIGGER '+name)
    cursor.execute(statement,params)
    cursor.execute(import_module('schedules.migrations.0028_shs_participation_guards').TRIGGERS[name])
call_command('migrate','schedules','0033',verbosity=0)
f.assert_section_blocked(section)
f.assertEqual(m.ScheduleSnapshot.objects.get(schedule=f.schedule).data,f.frozen)
with connection.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'shs_scope_%'")
    f.assertEqual(cursor.fetchone()[0],36)
'''
        result=subprocess.run([sys.executable,'-B','-c',script,mode],capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_frozen_only_participant(self):
        self.legacy_participation_case('frozen')

    def test_live_only_participant(self):
        self.legacy_participation_case('live')

    def test_malformed_binding_conservative(self):
        guards = import_module('schedules.migrations.0026_shs_meeting_snapshots').TRIGGERS
        name = next(name for name, sql in guards.items() if 'BEFORE UPDATE' in sql)
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER '+name)
            cursor.execute("UPDATE schedules_shsmeetingbinding SET data='[]'")
            cursor.execute(guards[name])
        self.assert_section_blocked(self.extra)


class ResourceAvailabilityMigrationTests(SimpleTestCase):
    def test_forward_reverse_native_and_original_defects(self):
        script = r'''
import os, sqlite3
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from schedules import models as m
from schedules.test_resource_availability_guards import ResourceAvailabilityTests
call_command('migrate','schedules','0031',verbosity=0)
ResourceAvailabilityTests.setUpTestData()
f=ResourceAvailabilityTests(); f.setUp()
models=(m.Schedule,m.ScheduleEntry,m.ScheduleSnapshot,m.Room,m.Section,m.Faculty,m.Availability,m.CredentialApprovalEvidence)
before={model.__name__:list(model.objects.values()) for model in models}
with connection.cursor() as c:
    c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"); original=dict(c.fetchall())
for target in ('0032','0031','0032'):
    call_command('migrate','schedules',target,verbosity=0)
    assert before=={model.__name__:list(model.objects.values()) for model in models}
    with connection.cursor() as c:
        c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"); current=dict(c.fetchall())
        assert all(current[k]==v for k,v in original.items())
        assert len(current)==len(original)+(3 if target=='0032' else 0)
        c.execute('PRAGMA integrity_check'); assert c.fetchall()==[('ok',)]
        c.execute('PRAGMA foreign_key_check'); assert c.fetchall()==[]
        if target=='0031':
            c.execute('SAVEPOINT old_defects')
            try:
                for column,pk in (('room_id',f.room.pk),('section_id',f.section.pk)):
                    c.execute(f"INSERT INTO schedules_availability({column},day,start_time,end_time,kind) VALUES(%s,0,'08:00:00','09:00:00','UNAVAILABLE')",[pk])
                from schedules.services.conflicts import schedule_validation_messages
                assert list(schedule_validation_messages(f.schedule))
            finally:
                c.execute('ROLLBACK TO old_defects')
                c.execute('RELEASE old_defects')
native=sqlite3.connect(':memory:')
connection.connection.backup(native)
native.execute('PRAGMA recursive_triggers=OFF')
for column,pk in (('room_id',f.room.pk),('section_id',f.section.pk)):
    try:
        native.execute(f"INSERT INTO schedules_availability({column},day,start_time,end_time,kind) VALUES(?,0,'08:00:00','09:00:00','UNAVAILABLE')",(pk,))
    except sqlite3.IntegrityError as exc:
        assert 'availability change' in str(exc), str(exc)
        native.rollback()
    else: raise AssertionError('Native SQLite bypass')
native.close()
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
