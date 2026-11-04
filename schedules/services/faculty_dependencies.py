"""Proposed-state checks shared with the independently enforced SQLite guards.

Dependency discovery is separate from editing policy. This version permits
changes only when every affected finalized commitment remains valid. It does
not waive missing evidence, existing conflicts, or SHS operational qualification.
"""
from importlib import import_module

from django.core.exceptions import ValidationError
from django.db import connections
from django.db.models.deletion import ProtectedError

policy = import_module('schedules.migrations.0030_faculty_dependency_guards')


def available(using):
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='view' AND name=%s", [policy.VIEW])
        if cursor.fetchone(): return True
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_migrations'")
        if cursor.fetchone():
            cursor.execute("SELECT 1 FROM django_migrations WHERE app='schedules' AND name='0030_faculty_dependency_guards'")
            if cursor.fetchone():
                raise ValidationError('Faculty dependency protection is unavailable. Ask an administrator to check the database setup.')
    return False  # Disposable rehearsals of schema versions before 0030.


def dependencies(faculty_ids, using='default'):
    """Return affected schedule identities and uncertainty, not edit permission."""
    if not available(using): return ()
    ids = sorted({x for x in faculty_ids if x is not None})
    if not ids: return ()
    with connections[using].cursor() as cursor:
        cursor.execute(f'SELECT DISTINCT schedule_id,uncertain FROM {policy.VIEW} '
                       f'WHERE uncertain=1 OR faculty_id IN ({",".join(["%s"]*len(ids))})', ids)
        return tuple(cursor.fetchall())


def proposed_failures(instance, *, deleting=False, using='default', update_fields=None):
    model = type(instance)
    old = model.objects.using(using).filter(pk=instance.pk).first() if instance.pk else None
    if instance._meta.model_name=='facultycredential':
        critical = ('faculty_id','credential_id','issued_on','expires_on')
        query = policy.credential_failures
    else:
        critical = ('faculty_id','room_id','section_id','day','start_time','end_time','kind')
        query = policy.availability_failures
    fields = [f for f in instance._meta.concrete_fields if not f.primary_key]
    values = {f.attname: getattr(instance, f.attname) for f in fields}
    if old and update_fields is not None:
        for f in fields:
            if f.name not in update_fields and f.attname not in update_fields:
                values[f.attname] = getattr(old, f.attname)
    if not deleting and old and all(getattr(old,key)==values[key] for key in critical): return ()
    owners = {old.faculty_id if old else None, None if deleting else values['faculty_id']} - {None}
    if not owners or not available(using): return ()
    # Parameters are converted by the real model fields, matching stored dates/times.
    connection = connections[using]
    columns = ','.join(f.column for f in fields)
    table = instance._meta.db_table
    proposed = f'SELECT {columns} FROM {table} WHERE id<>%s'
    params = [instance.pk or -1]
    if not deleting:
        proposed += ' UNION ALL SELECT ' + ','.join(['%s']*len(fields))
        params += [f.get_db_prep_value(values[f.attname], connection) for f in fields]
    owner_sql = ' UNION SELECT '.join(['%s']*len(owners))
    sql = query(proposed, 'SELECT ' + owner_sql)
    params += sorted(owners)
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return tuple(cursor.fetchall())


def check_save(sender, instance, using='default', update_fields=None, **kwargs):
    rows = proposed_failures(instance, using=using, update_fields=update_fields)
    if rows: raise ValidationError(message(rows, using))


def check_delete(sender, instance, using='default', **kwargs):
    rows = proposed_failures(instance, deleting=True, using=using)
    if rows: raise ProtectedError(message(rows, using), [instance])


def message(rows, using):
    from schedules.models import Schedule
    names = Schedule.objects.using(using).filter(pk__in={row[0] for row in rows}).order_by('pk').values_list('name',flat=True)
    reason = ('Historical faculty commitments need review.' if any(row[2] for row in rows) else
              'The proposed credential or availability change would leave faculty requirements unmet.')
    return f'{reason} Affected published or archived schedules: {", ".join(names)}. Keep the current values and review these schedules before making this change.'
