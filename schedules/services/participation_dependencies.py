"""Read-only dependency discovery, deliberately separate from editing policy.

The versioned SQLite view is shared with database guards. An uncertainty row
conservatively includes every candidate rather than guessing missing history.
Before migration 0028 exists the previous protection policy remains in effect;
deploying this feature requires applying that migration separately.
"""
from django.db import connections
from django.core.exceptions import ValidationError


MODELS = {'section', 'program', 'yearlevel', 'department'}
VIEW = 'shs_finalized_participation_v1'


def affected_schedules(model, key, using='default'):
    """Return (schedule_id, uncertain) evidence, never permission to edit."""
    if model not in MODELS | {'configuration'}:
        return ()
    connection = connections[using]
    if connection.vendor != 'sqlite':
        raise NotImplementedError('SHS participation guards require SQLite.')
    predicates = {
        'section': 'd.section_id=%s',
        'program': 'EXISTS (SELECT 1 FROM schedules_section s WHERE s.id=d.section_id AND s.program_id=%s)',
        'yearlevel': 'EXISTS (SELECT 1 FROM schedules_section s WHERE s.id=d.section_id AND s.year_level_id=%s)',
        'department': 'EXISTS (SELECT 1 FROM schedules_section s JOIN schedules_program p ON p.id=s.program_id WHERE s.id=d.section_id AND p.department_id=%s)',
        'configuration': 'd.configuration_id=%s',
    }
    with connection.cursor() as cursor:
        # Required for migration rehearsals against older schema versions. Do
        # not cache this check: the same connection may migrate forward/back.
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='view' AND name=%s", [VIEW])
        if cursor.fetchone() is None:
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_migrations'")
            if cursor.fetchone():
                cursor.execute("SELECT 1 FROM django_migrations WHERE app='schedules' AND name='0028_shs_participation_guards'")
                if cursor.fetchone():
                    raise ValidationError('Schedule participation protection is unavailable. Ask an administrator to verify the database setup before editing records.')
            return ()
        cursor.execute(f'SELECT DISTINCT d.schedule_id, d.uncertain FROM {VIEW} d '
                       f'WHERE d.uncertain=1 OR ({predicates[model]}) ORDER BY d.schedule_id, d.uncertain', [key])
        return tuple(cursor.fetchall())
