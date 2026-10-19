"""Subprocess-only synthetic drill; never imports the developer's settings."""
from contextlib import closing
from datetime import date, timedelta
import hashlib
from io import StringIO
import json
from pathlib import Path
import sqlite3
import sys


def configure(root, phase):
    from django.conf import settings
    # The test harness creates an empty directory and this explicit marker.
    if not (root / '.synthetic-recovery').is_file():
        raise RuntimeError('A synthetic test workspace marker is required.')
    source = root / ('source.sqlite3' if phase == 'create' else 'restored.sqlite3')
    if phase == 'create' and source.exists():
        raise RuntimeError('Never overwrite a drill source.')
    settings.configure(SECRET_KEY='synthetic-recovery-only', BASE_DIR=root,
        INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.admin',
                        'django.contrib.sessions', 'schedules'],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': source}},
        USE_TZ=True, TIME_ZONE='Asia/Shanghai', DEFAULT_AUTO_FIELD='django.db.models.BigAutoField')
    import django
    django.setup()
    return source


def contents(path):
    from schedules.services.database_backup import quote_identifier, schema, verify
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        report = verify(db, require_current=True)
        rows = {name: sorted(db.execute('SELECT * FROM ' + quote_identifier(name)).fetchall(), key=repr)
                for name in report['counts']}
        return schema(db), rows, report


def create(root, source):
    from django.contrib.auth.models import User
    from django.core.management import call_command
    from django.db import connections
    from django.utils import timezone
    from schedules import models as m
    from schedules.services.ga import GeneticScheduler
    from schedules.services.publication import publish
    from schedules.services.manual_edits import copy_to_draft
    from schedules.services.generation_lock import acquire
    call_command('migrate', interactive=False, verbosity=0)
    admin = User.objects.create_superuser(username='synthetic_admin', password='synthetic-only')
    department = m.Department.objects.create(code='SYN', name='Synthetic Department')
    program = m.Program.objects.create(department=department, code='SYN', name='Synthetic Program')
    year = m.YearLevel.objects.create(level=1, label='Year 1')
    section = m.Section.objects.create(program=program, year_level=year, name='A', size=20)
    faculty = m.Faculty.objects.create(department=department, employee_id='SYN1', full_name='Synthetic Faculty')
    m.Faculty.objects.create(department=department, employee_id='SYN2', full_name='Synthetic Replacement')
    subject = m.Subject.objects.create(department=department, code='SYN101', title='Synthetic Course',
        lecture_hours=1, lab_hours=1, required_room_type=m.RoomKind.LECTURE)
    term = m.AcademicTerm.objects.create(name='Synthetic term', school_year='2026-2027',
        starts_on=date(2026,8,1), ends_on=date(2026,12,1))
    credential = m.Credential.objects.create(name='Synthetic Qualification')
    m.FacultyCredential.objects.create(faculty=faculty, credential=credential,
        issued_on=date(2026,1,1), expires_on=date(2027,1,1))
    m.SubjectCredentialRequirement.objects.create(subject=subject, required_credential=credential)
    parent = m.Assignment.objects.create(term=term, subject=subject, faculty=faculty, section=section)
    meetings = [m.TeachingAssignment.objects.create(assignment=parent, component=component,
        meeting_index=index, duration_minutes=60, required_room_type_override=kind)
        for index, component, kind in [(1,'LECTURE',m.RoomKind.LECTURE),(2,'LABORATORY',m.RoomKind.COMPUTER_LAB)]]
    for name, kind in [('Synthetic lecture',m.RoomKind.LECTURE),('Synthetic laboratory',m.RoomKind.COMPUTER_LAB)]:
        m.Room.objects.create(name=name, room_type=kind, capacity=30)
    ga = m.GASettings.objects.create(name='Synthetic', population_size=4, generations=1, elitism=1)
    scheduler = GeneticScheduler(term, ga, seed=17)
    generated = scheduler.generate('Synthetic generated')
    publish(generated, admin)
    second = copy_to_draft(source_id=generated.pk, actor=admin)
    publish(second, admin, True)
    copy_to_draft(source_id=second.pk, actor=admin)
    lease = acquire(term.pk, seconds=3600)
    run = m.GenerationRun.objects.create(term=term, ga_settings=ga, schedule=generated,
        requested_by=admin, requested_name='Synthetic completed', status='SUCCEEDED',
        completed_at=timezone.now(), reproducibility={'seed':17, 'parameters':{'population_size':4},
        'input_counts':{'meetings':2}, 'fingerprint':'synthetic-fixture'})
    m.GenerationIssue.objects.create(run=run, assignment=meetings[0], category='OTHER',
        short_description='Synthetic diagnostic', reason='Synthetic drill', suggested_action='Review fixture',
        details={'version':1,'synthetic':True})
    m.GenerationRun.objects.create(term=term, requested_name='Synthetic interrupted', lease_owner=lease.owner,
        reproducibility={'seed':18})
    connections.close_all()
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before = contents(source)
    backup, restored = root/'backup.sqlite3', root/'restored.sqlite3'
    call_command('backup_database', output=str(backup), stdout=StringIO())
    backup_hash = hashlib.sha256(backup.read_bytes()).hexdigest()
    call_command('restore_database', source=str(backup), destination=str(restored), stdout=StringIO())
    assert contents(backup) == before == contents(restored)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == backup_hash
    with closing(sqlite3.connect(restored)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        # Match an ordinary application connection, with no privileged workflow.
        db.create_function('schedease_archiving', 0, lambda: 0)
        db.create_function('schedease_term_sync', 2, lambda *args: 0)
        attempts = [
            "UPDATE schedules_schedule SET name='changed' WHERE status='PUBLISHED'",
            "DELETE FROM schedules_scheduleentry WHERE schedule_id IN (SELECT id FROM schedules_schedule WHERE status='ARCHIVED')",
            "UPDATE schedules_teachingassignment SET duration_minutes=120",
            "UPDATE schedules_assignment SET faculty_id=(SELECT MAX(id) FROM schedules_faculty)",
            "UPDATE schedules_academicterm SET name='changed'",
            "UPDATE schedules_schedulesnapshot SET data='{}'",
            "DELETE FROM schedules_schedulesnapshot",
        ]
        for sql in attempts:
            try:
                db.execute(sql)
            except sqlite3.IntegrityError:
                db.rollback()
            else:
                raise AssertionError('Protected mutation was accepted')
    assert contents(restored) == before
    print(json.dumps({'tables':before[2]['table_count'], 'rows':sum(before[2]['counts'].values()),
        'triggers':sum(row[0]=='trigger' for row in before[0]), 'indexes':sum(row[0]=='index' for row in before[0]),
        'protected_mutations_rejected':len(attempts), 'exact_schema_and_rows':True,
        'source_and_backup_unchanged':True}))


def leases():
    from django.db import connections
    from django.utils import timezone
    from schedules.models import GenerationLease, GenerationRun
    from schedules.services.generation_lock import acquire, GenerationBusy, GenerationLeaseLost, Lease
    from schedules.services.generation_issues import recover_stale_runs
    stored = GenerationLease.objects.get()
    try:
        acquire(stored.term_id)
    except GenerationBusy:
        pass
    else:
        raise AssertionError('An active restored lease must not be reused')
    assert recover_stale_runs() == 0
    # Only this disposable restored database is changed to simulate elapsed time.
    GenerationLease.objects.filter(pk=stored.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    assert recover_stale_runs() == 1
    assert GenerationRun.objects.get(requested_name='Synthetic interrupted').status == 'FAILED'
    successor = acquire(stored.term_id)
    try:
        Lease(stored.term_id, stored.owner).checkpoint(force=True)
    except GenerationLeaseLost:
        pass
    else:
        raise AssertionError('Old lease owner must remain fenced')
    successor.release()
    connections.close_all()
    print('Restored lease expiry, stale-run recovery and old-owner rejection passed.')


if __name__ == '__main__':
    root, phase = Path(sys.argv[1]).resolve(), sys.argv[2]
    if phase not in ('create', 'leases'):
        raise RuntimeError('Unknown drill phase')
    source = configure(root, phase)
    create(root, source) if phase == 'create' else leases()
