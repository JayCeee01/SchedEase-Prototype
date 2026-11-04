"""Reject implicit deletion of protected rows by SQLite conflict replacement.

Frozen predicates come from earlier migrations, never mutable application code.
BEFORE INSERT/UPDATE guards work with recursive_triggers OFF and cover both
REPLACE forms. Ordinary updates of the same row retain their existing policy.
No data, indexes, or earlier triggers are changed.
"""
from importlib import import_module

from django.db import migrations


def normalized(*columns):
    return ' AND '.join(
        f'schedease_identity_v1(victim.{column})=schedease_identity_v1(NEW.{column})'
        for column in columns)


def equal(*columns):
    # SQL equality deliberately preserves SQLite's NULL-distinct unique semantics.
    return ' AND '.join(f'victim.{column}=NEW.{column}' for column in columns)


# Every non-PK unique key on these protected tables at migration 0030.
# Normalized predicates also cover the original exact-text unique constraints.
KEYS = {
    'department': normalized('code'),
    'program': normalized('code'),
    'yearlevel': equal('level'),
    'academicterm': normalized('name', 'school_year'),
    'section': equal('program_id', 'year_level_id') + ' AND ' + normalized('name'),
    'faculty': '(' + normalized('employee_id') + ') OR (' + equal('user_id') + ')',
    'room': normalized('name'),
    'subject': normalized('code'),
    'assignment': equal('term_id', 'subject_id', 'section_id', 'faculty_id'),
    'teachingassignment': equal('term_id', 'subject_id', 'section_id', 'component', 'meeting_index'),
    'schedule': equal('term_id') + " AND victim.status='PUBLISHED' AND NEW.status='PUBLISHED'",
    'scheduleentry': equal('schedule_id', 'assignment_id'),
    'facultycredential': equal('faculty_id', 'credential_id'),
}

base = dict(import_module('schedules.migrations.0010_finalized_schedule_guards').TRIGGERS)
terms = dict(import_module('schedules.migrations.0011_academic_term_guards').TRIGGERS)
participants = import_module('schedules.migrations.0028_shs_participation_guards')


def dependency(model):
    if model == 'facultycredential':
        return """EXISTS (SELECT 1 FROM finalized_faculty_commitments_v1 c
            WHERE c.uncertain=1 OR c.faculty_id=victim.faculty_id)"""
    sql = terms['h2_term_delete'] if model == 'academicterm' else base[f'h2_{model}_delete']
    predicate = sql.split(' WHEN ', 1)[1].split(' BEGIN ', 1)[0].replace('OLD.', 'victim.')
    if model in participants.FIELDS:
        predicate = f'({predicate}) OR ({participants.dependency(model, "victim.id")})'
    return predicate


MESSAGE = 'Cannot replace a record used by a published or archived schedule. Keep the existing record and use a separate unused identity.'
TRIGGERS = {}
for model, key in KEYS.items():
    for event in ('INSERT', 'UPDATE'):
        name = f'finalized_collision_{model}_{event.lower()}'
        other = 'victim.id<>OLD.id AND ' if event == 'UPDATE' else ''
        # SQLite's OR/partial-index planner can fail inside schedule INSERT
        # triggers. A table scan here preserves exact partial-key semantics.
        scan = ' NOT INDEXED' if model == 'schedule' else ''
        TRIGGERS[name] = f"""CREATE TRIGGER {name} BEFORE {event} ON schedules_{model}
            WHEN EXISTS (SELECT 1 FROM schedules_{model} victim{scan}
                WHERE {other}(victim.id=NEW.id OR ({key})) AND ({dependency(model)}))
            BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        raise RuntimeError('Finalized collision guards require SQLite.')
    for sql in TRIGGERS.values():
        schema_editor.execute(sql)


def backwards(apps, schema_editor):
    for name in TRIGGERS:
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')


class Migration(migrations.Migration):
    dependencies = [('schedules', '0030_faculty_dependency_guards')]
    operations = [migrations.RunPython(forwards, backwards)]
