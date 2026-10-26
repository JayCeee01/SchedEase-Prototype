"""Rehearse the upgrade in independent, disposable SQLite databases."""
import os
import subprocess
import sys

from django.test import SimpleTestCase


REHEARSAL = r'''
import os
from datetime import date, time
os.environ['DJANGO_SETTINGS_MODULE'] = 'sched_ease.settings'
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
import django
django.setup()
from django.db import connection, IntegrityError
from django.db.migrations.executor import MigrationExecutor
old = [('schedules', '0020_normalized_identity_uniqueness')]
new = [('schedules', '0021_shs_academic_identity')]
executor = MigrationExecutor(connection)
executor.migrate(old)
apps = executor.loader.project_state(old).apps
def create(model_name, **values):
    return apps.get_model('schedules', model_name).objects.create(**values)
if os.environ['SHS_MIGRATION_POPULATED'] == '1':
    dept = create('Department', code='MIG', name='Synthetic department')
    program = create('Program', department=dept, code='MIG', name='Synthetic program')
    year = create('YearLevel', level=1, label='Year 1')
    section = create('Section', program=program, year_level=year, name='A', size=20)
    faculty = create('Faculty', department=dept, employee_id='MIG1', full_name='Synthetic Instructor')
    subject = create('Subject', department=dept, code='MIG101', title='Synthetic Course', lecture_hours=1, lab_hours=0)
    term = create('AcademicTerm', name='First', school_year='2026-2027', starts_on=date(2026,8,1), ends_on=date(2026,12,1))
    parent = create('Assignment', term=term, subject=subject, section=section, faculty=faculty)
    meeting = create('TeachingAssignment', assignment=parent, term=term, subject=subject, section=section, faculty=faculty, component='LECTURE', meeting_index=1, duration_minutes=60)
    room = create('Room', name='Synthetic room', room_type='LECTURE', capacity=30)
    schedule = create('Schedule', term=term, name='Historical fixture')
    create('ScheduleEntry', schedule=schedule, assignment=meeting, room=room, day=0, start_time=time(8), end_time=time(9))
    schedule.status='PUBLISHED'
    schedule.save()
    assert apps.get_model('schedules', 'ScheduleSnapshot').objects.count() == 1
with connection.cursor() as c:
    c.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
    triggers = dict(c.fetchall())
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'schedules_%'")
    original = {}
    for (table,) in c.fetchall():
        c.execute(f'PRAGMA table_info("{table}")')
        columns = [row[1] for row in c.fetchall()]
        selection = ','.join('"'+col+'"' for col in columns)
        c.execute(f'SELECT {selection} FROM "{table}" ORDER BY 1')
        original[table] = (selection, c.fetchall())
MigrationExecutor(connection).migrate(new)
with connection.cursor() as c:
    c.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
    current = dict(c.fetchall())
    assert all(current.get(name) == sql for name, sql in triggers.items()), 'Historical triggers changed'
    assert len(current) == len(triggers) + 3
    for table, (selection, rows) in original.items():
        c.execute(f'SELECT {selection} FROM "{table}" ORDER BY 1')
        assert c.fetchall() == rows, table
    c.execute('PRAGMA integrity_check')
    assert c.fetchall() == [('ok',)]
    c.execute('PRAGMA foreign_key_check')
    assert not c.fetchall()
    c.execute("SELECT count(*) FROM schedules_program WHERE education_level != 'TERTIARY'")
    assert c.fetchone()[0] == 0
    c.execute('SELECT count(*) FROM schedules_section WHERE cohort_id IS NOT NULL')
    assert c.fetchone()[0] == 0
    if os.environ['SHS_MIGRATION_POPULATED'] == '1':
        for sql in ["UPDATE schedules_program SET education_level='SHS'", "UPDATE schedules_program SET name='Changed'", "UPDATE schedules_schedulesnapshot SET data='{}'"]:
            try:
                c.execute(sql)
            except IntegrityError:
                pass
            else:
                raise AssertionError('Protection failed: '+sql)
connection.close()
print('Migration rehearsal passed; original rows, IDs, snapshots and triggers preserved.')
'''


class SHSMigrationTests(SimpleTestCase):
    def rehearse(self, populated):
        env = os.environ.copy()
        env['SHS_MIGRATION_POPULATED'] = str(int(populated))
        result = subprocess.run([sys.executable, '-B', '-c', REHEARSAL], env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_database_upgrade(self):
        self.rehearse(False)

    def test_populated_tertiary_upgrade(self):
        self.rehearse(True)
