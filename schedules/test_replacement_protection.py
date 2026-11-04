from .test_publication_helpers import finalize, legacy_case, upgrade
"""Conflict replacement must not implicitly delete finalized dependencies."""
from datetime import time
import subprocess
import sys

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from . import models as m
from .protection import archive_transition
from .test_known_defects import SchedulingDefectFixture


def replace_copy(obj, **changes):
    """Copy actual columns, avoiding unrelated missing-default failures."""
    table = obj._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table}")')
        columns = [row[1] for row in cursor.fetchall()]
        expressions = ['%s' if col in changes else f'"{col}"' for col in columns]
        values = [changes[col] for col in columns if col in changes]
        names = ','.join(f'"{col}"' for col in columns)
        cursor.execute(f'INSERT OR REPLACE INTO "{table}" ({names}) '
                       f'SELECT {",".join(expressions)} FROM "{table}" WHERE id=%s',
                       [*values, obj.pk])


class ReplacementProtectionTests(SchedulingDefectFixture):
    def setUp(self):
        self.schedule = m.Schedule.objects.create(term=self.term, name='Official')
        self.entries = [self.schedule.entries.create(
            assignment=meeting, room=self.room, day=0,
            start_time=time(8+i), end_time=time(9+i)) for i, meeting in enumerate(self.meetings)]
        finalize(self.schedule)
        self.frozen = m.ScheduleSnapshot.objects.get(schedule=self.schedule).data

    def assert_blocked(self, obj, **changes):
        before = list(type(obj).objects.order_by('pk').values())
        with self.assertRaisesRegex(IntegrityError, 'published|archived|Finalized|finalized'), transaction.atomic():
            replace_copy(obj, **changes)
        self.assertEqual(list(type(obj).objects.order_by('pk').values()), before)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, self.frozen)
        connection.check_constraints()

    def test_original_room_replace_restore_attack(self):
        with self.assertRaisesRegex(IntegrityError, 'published|archived'), transaction.atomic():
            replace_copy(self.room, id=9999)
            m.Room.objects.create(pk=self.room.pk, name='Restored', capacity=1, room_type='LECTURE')
            connection.check_constraints()
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacity, 30)
        self.assertFalse(m.Room.objects.filter(pk=9999).exists())

    def test_all_core_unique_keys_and_primary_keys(self):
        records = [self.department, self.section.program, self.section.year_level,
                   self.term, self.section, self.faculty, self.room, self.subject,
                   self.parent, self.meetings[0], self.schedule, self.entries[0]]
        for obj in records:
            for key in (obj.pk, 9999):
                with self.subTest(model=obj._meta.model_name, replacement_pk=key):
                    self.assert_blocked(obj, id=key)

    def test_normalized_unique_collisions(self):
        for obj, field in [(self.department, 'code'), (self.section.program, 'code'),
                           (self.term, 'name'), (self.section, 'name'),
                           (self.faculty, 'employee_id'), (self.room, 'name'), (self.subject, 'code')]:
            with self.subTest(model=obj._meta.model_name):
                self.assert_blocked(obj, id=9999, **{field: ' ' + getattr(obj, field).swapcase() + ' '})

    def test_faculty_account_unique_collision_and_safe_linking(self):
        user = User.objects.create(username='linked')
        self.faculty.user = user
        self.faculty.save(update_fields=['user'])
        self.assert_blocked(self.faculty, id=9999, employee_id='UNUSED')
        self.faculty.user = None
        self.faculty.save(update_fields=['user'])
        m.Faculty.objects.create(department=self.department, employee_id='FREE', full_name='Free')

    def test_update_or_replace_unique_and_primary_collisions(self):
        free = m.Room.objects.create(name='Free room', capacity=25, room_type='LECTURE')
        for column, value in [('name', self.room.name), ('name', ' ' + self.room.name.upper() + ' '), ('id', self.room.pk)]:
            with self.subTest(column=column, value=value):
                with self.assertRaisesRegex(IntegrityError, 'published|archived'), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(f'UPDATE OR REPLACE schedules_room SET {column}=%s WHERE id=%s', [value, free.pk])
                free.refresh_from_db()
                self.assertEqual(free.name, 'Free room')
                self.room.refresh_from_db()
                self.assertEqual(self.room.capacity, 30)

    @legacy_case
    def test_update_or_replace_composite_meeting_collision(self):
        subject = m.Subject.objects.create(department=self.department, code='FREE', title='Free', lecture_hours=1)
        free = m.TeachingAssignment.objects.create(term=self.term, subject=subject, section=self.section,
            faculty=self.faculty, component='LECTURE', meeting_index=1, duration_minutes=60)
        upgrade()
        with self.assertRaisesRegex(IntegrityError, 'published|archived'), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE OR REPLACE schedules_teachingassignment SET subject_id=%s WHERE id=%s', [self.subject.pk, free.pk])
        free.refresh_from_db()
        self.assertEqual(free.subject_id, subject.pk)

    def test_faculty_credential_composite_replacement(self):
        first = m.Credential.objects.create(name='First')
        second = m.Credential.objects.create(name='Second')
        held = m.FacultyCredential.objects.create(faculty=self.faculty, credential=first, issued_on=self.term.starts_on)
        spare = m.FacultyCredential.objects.create(faculty=self.faculty, credential=second, issued_on=self.term.starts_on)
        self.assert_blocked(held, id=9999)
        with self.assertRaisesRegex(IntegrityError, 'published|archived'), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE OR REPLACE schedules_facultycredential SET credential_id=%s WHERE id=%s', [first.pk, spare.pk])
        self.assertEqual(m.FacultyCredential.objects.filter(faculty=self.faculty).count(), 2)

    def test_archived_dependencies_remain_protected(self):
        finalize(self.schedule, archived=True)
        self.assert_blocked(self.room, id=9999)
        self.assert_blocked(self.faculty, id=9999)

    def test_ordinary_bulk_and_raw_operations_keep_protection(self):
        self.room.capacity = 1
        with self.assertRaises(ValidationError):
            self.room.save()
        for action in ('bulk_update', 'bulk_create', 'raw_update', 'raw_delete'):
            with self.subTest(action=action), self.assertRaises(IntegrityError), transaction.atomic():
                if action == 'bulk_update':
                    m.Room.objects.bulk_update([self.room], ['capacity'])
                elif action == 'bulk_create':
                    m.Room.objects.bulk_create([m.Room(name=self.room.name, room_type='LECTURE', capacity=1)],
                                              update_conflicts=True, update_fields=['capacity'], unique_fields=['name'])
                else:
                    with connection.cursor() as cursor:
                        sql = 'UPDATE schedules_room SET capacity=1 WHERE id=%s' if action == 'raw_update' else 'DELETE FROM schedules_room WHERE id=%s'
                        cursor.execute(sql, [self.room.pk])

    def test_free_rows_inserts_replacements_and_scope_remain_allowed(self):
        free = m.Room.objects.create(name='Free', capacity=20, room_type='LECTURE')
        replace_copy(free, id=9999, capacity=21)
        self.assertFalse(m.Room.objects.filter(pk=free.pk).exists())
        self.assertEqual(m.Room.objects.get(pk=9999).capacity, 21)
        m.Schedule.objects.create(term=self.term, name='Draft')
        other_program = m.Program.objects.create(code='OTHER', name='Other', department=self.department)
        m.Section.objects.create(program=other_program, year_level=self.section.year_level, name=self.section.name, size=10)

    def test_statement_and_transaction_rollback(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Room.objects.create(name='Should roll back', capacity=10, room_type='LECTURE')
            replace_copy(self.room, id=9999)
        self.assertFalse(m.Room.objects.filter(name='Should roll back').exists())
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, self.frozen)

    def test_unique_index_inventory_matches_guard_contract(self):
        # Expression entries are None in index_info. Any added unique index
        # requires a deliberate collision-guard review, not silent omission.
        expected = {
            'department': {('code',), (None,)}, 'program': {('code',), (None,)},
            'yearlevel': {('level',)}, 'academicterm': {('name', 'school_year'), (None, None)},
            'section': {('program_id', 'year_level_id', 'name'), (None, 'program_id', 'year_level_id')},
            'faculty': {('employee_id',), ('user_id',), (None,)},
            'room': {('name',), (None,)}, 'subject': {('code',), (None,)},
            'assignment': {('term_id', 'subject_id', 'section_id', 'faculty_id')},
            'teachingassignment': {('term_id', 'subject_id', 'section_id', 'component', 'meeting_index')},
            'schedule': {('term_id',)}, 'scheduleentry': {('schedule_id', 'assignment_id')},
            'facultycredential': {('faculty_id', 'credential_id')},
        }
        with connection.cursor() as cursor:
            for model, keys in expected.items():
                cursor.execute(f'PRAGMA index_list("schedules_{model}")')
                indexes = [row[1] for row in cursor.fetchall() if row[2]]
                actual = set()
                for index in indexes:
                    cursor.execute(f'PRAGMA index_info("{index}")')
                    actual.add(tuple(row[2] for row in cursor.fetchall()))
                self.assertEqual(actual, keys, model)


class SHSReplacementTests(TestCase):
    def test_additional_participant_and_parent_collisions(self):
        from .test_participation_protection import fixture
        fixture(self)
        frozen = m.ScheduleSnapshot.objects.get(schedule=self.schedule).data
        for obj in (self.extra, self.extra_program, self.extra_department, self.year, self.room):
            with self.subTest(model=obj._meta.model_name), self.assertRaises(IntegrityError), transaction.atomic():
                replace_copy(obj, id=9999)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, frozen)
        connection.check_constraints()


class ReplacementMigrationTests(SimpleTestCase):
    def test_forward_reverse_and_native_sqlite(self):
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
from schedules.test_known_defects import SchedulingDefectFixture
from schedules.test_replacement_protection import ReplacementProtectionTests
from schedules.identity import normalize_identity
call_command('migrate', 'schedules', '0030', verbosity=0)
ReplacementProtectionTests.setUpTestData()
f=ReplacementProtectionTests(); f.setUp()
before={model.__name__:list(model.objects.values()) for model in (m.Room,m.Faculty,m.Schedule,m.ScheduleEntry,m.ScheduleSnapshot)}
with connection.cursor() as c:
    c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
    original=dict(c.fetchall())
for target in ('0031','0030','0031'):
    call_command('migrate','schedules',target,verbosity=0)
    assert before=={model.__name__:list(model.objects.values()) for model in (m.Room,m.Faculty,m.Schedule,m.ScheduleEntry,m.ScheduleSnapshot)}
    with connection.cursor() as c:
        c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
        current=dict(c.fetchall())
        assert all(current[k]==v for k,v in original.items())
        assert len(current)==len(original)+(26 if target=='0031' else 0)
        c.execute('PRAGMA integrity_check'); assert c.fetchall()==[('ok',)]
        c.execute('PRAGMA foreign_key_check'); assert c.fetchall()==[]
        if target=='0030':
            # Positive control: reproduce the complete historical attack only
            # on this disposable DB, then undo it before migrating forward.
            c.execute('SAVEPOINT original_defect')
            try:
                c.execute("INSERT OR REPLACE INTO schedules_room(id,name,room_type,capacity,is_active) VALUES(9999,%s,'LECTURE',30,1)",[f.room.name])
                c.execute("INSERT INTO schedules_room(id,name,room_type,capacity,is_active) VALUES(%s,'Restored','LECTURE',1,1)",[f.room.pk])
                c.execute('PRAGMA foreign_key_check'); assert c.fetchall()==[]
                c.execute('SELECT capacity FROM schedules_room WHERE id=%s',[f.room.pk]); assert c.fetchone()==(1,)
            finally:
                c.execute('ROLLBACK TO original_defect')
                c.execute('RELEASE original_defect')
native=sqlite3.connect(':memory:')
# Existing expression indexes need normalization, not an authorization callback.
native.create_function('schedease_identity_v1',1,normalize_identity,deterministic=True)
connection.connection.backup(native)
native.execute('PRAGMA recursive_triggers=OFF')
try:
    native.execute("INSERT OR REPLACE INTO schedules_room(id,name,room_type,capacity,is_active) VALUES(9999,?,'LECTURE',1,1)",(f.room.name,))
except sqlite3.IntegrityError as exc:
    assert 'Cannot replace' in str(exc), str(exc)
    native.rollback()
else:
    raise AssertionError('Native SQLite allowed replacement')
assert native.execute('SELECT capacity FROM schedules_room WHERE id=?',(f.room.pk,)).fetchone()==(30,)
native.execute("INSERT INTO schedules_room(id,name,room_type,capacity,is_active) VALUES(9998,'Free','LECTURE',20,1)")
native.commit()
try:
    native.execute('UPDATE OR REPLACE schedules_room SET name=? WHERE id=9998',(f.room.name,))
except sqlite3.IntegrityError as exc:
    assert 'Cannot replace' in str(exc), str(exc)
    native.rollback()
else:
    raise AssertionError('Native SQLite allowed UPDATE OR REPLACE')
native.close()
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
