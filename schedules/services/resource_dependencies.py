"""Availability feedback using the same proposed-state SQL as migration 0032."""
from importlib import import_module

from django.core.exceptions import ValidationError
from django.db import connections
from django.db.models.deletion import ProtectedError

policy = import_module('schedules.migrations.0032_resource_availability_guards')


def available(using):
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='view' AND name=%s", [policy.VIEW])
        if cursor.fetchone():
            return True
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_migrations'")
        if cursor.fetchone():
            cursor.execute("SELECT 1 FROM django_migrations WHERE app='schedules' AND name='0032_resource_availability_guards'")
            if cursor.fetchone():
                raise ValidationError('Room and section protection is unavailable. Ask an administrator to check the database setup.')
    return False  # Supports isolated rehearsals of earlier schemas.


def proposed_failures(instance, *, deleting=False, using='default', update_fields=None):
    model = type(instance)
    old = model.objects.using(using).filter(pk=instance.pk).first() if instance.pk else None
    fields = [model._meta.get_field(name.removesuffix('_id')) for name in policy.COLUMNS]
    values = {f.attname: getattr(instance, f.attname) for f in fields}
    if old and update_fields is not None:
        for field in fields:
            if field.name not in update_fields and field.attname not in update_fields:
                values[field.attname] = getattr(old, field.attname)
    owners = set()
    for kind in ('room', 'section'):
        if old and getattr(old, kind+'_id') is not None:
            owners.add((kind, getattr(old, kind+'_id')))
        if not deleting and values[kind+'_id'] is not None:
            owners.add((kind, values[kind+'_id']))
    if not owners or not available(using):
        return ()
    connection = connections[using]
    periods = f'SELECT {",".join(policy.COLUMNS)} FROM schedules_availability WHERE id<>%s'
    params = [instance.pk if instance.pk is not None else -1]
    if not deleting:
        periods += ' UNION ALL SELECT ' + ','.join(['%s']*len(fields))
        params += [f.get_db_prep_value(values[f.attname], connection) for f in fields]
    owner_sql = ' UNION SELECT '.join(['%s,%s']*len(owners))
    for kind, pk in sorted(owners):
        params.extend((kind, pk))
    with connection.cursor() as cursor:
        cursor.execute(policy.failures(periods, 'SELECT '+owner_sql), params)
        return tuple(cursor.fetchall())


def message(rows, using):
    from schedules.models import Schedule
    names = Schedule.objects.using(using).filter(pk__in={row[0] for row in rows}).order_by('pk').values_list('name', flat=True)
    reason = ('Historical room or section commitments need review.' if any(row[3] for row in rows) else
              'The proposed availability would leave a room or section unavailable for an existing meeting.')
    return f'{reason} Affected published or archived schedules: {", ".join(names)}. Keep the current values and review these schedules.'


def check_save(sender, instance, using='default', update_fields=None, **kwargs):
    rows = proposed_failures(instance, using=using, update_fields=update_fields)
    if rows:
        raise ValidationError(message(rows, using))


def check_delete(sender, instance, using='default', **kwargs):
    rows = proposed_failures(instance, using=using, deleting=True)
    if rows:
        raise ProtectedError(message(rows, using), [instance])
