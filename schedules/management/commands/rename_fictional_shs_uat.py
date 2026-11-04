"""Rename only the existing FUA labels, with exact database/hash fencing."""
import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from schedules.services.fictional_shs_names import apply_names, naming_plan


def protected_state():
    allowed = {}
    for obj, field, name in naming_plan():
        allowed.setdefault(obj._meta.db_table, {})[obj.pk] = obj._meta.get_field(field).column
    result = {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cursor.fetchall()]
        for table in tables:
            cursor.execute('SELECT * FROM "'+table+'"')
            columns = [d[0] for d in cursor.description]
            rows = []
            for values in cursor.fetchall():
                row = dict(zip(columns, values))
                field = allowed.get(table, {}).get(row.get('id'))
                if field:
                    row.pop(field)
                rows.append(row)
            result[table] = rows
    return result


class Command(BaseCommand):
    help = 'Rename existing fictional SHS UAT labels, preserving codes and protected data.'

    def add_arguments(self, parser):
        parser.add_argument('--database-path', required=True)
        parser.add_argument('--expected-sha256', required=True)

    def handle(self, *args, **options):
        path = Path(options['database_path']).resolve(strict=True)
        if Path(connection.settings_dict['NAME']).resolve(strict=True) != path:
            raise CommandError('Configured database does not match the explicit target.')
        if hashlib.sha256(path.read_bytes()).hexdigest() != options['expected_sha256'].lower():
            raise CommandError('Database changed since verification; stopping.')
        connection.ensure_connection()
        previous_mode = connection.transaction_mode
        connection.transaction_mode = 'EXCLUSIVE'
        try:
            with transaction.atomic():
                before = protected_state()
                changed = apply_names()
                if before != protected_state():
                    raise CommandError('Protected data changed; rolling back.')
                with connection.cursor() as cursor:
                    cursor.execute('PRAGMA integrity_check')
                    if cursor.fetchall() != [('ok',)]:
                        raise CommandError('Integrity check failed.')
                    cursor.execute('PRAGMA foreign_key_check')
                    if cursor.fetchall():
                        raise CommandError('Foreign-key check failed.')
        finally:
            connection.transaction_mode = previous_mode
        self.stdout.write(json.dumps({'labels_changed': changed, 'protected_data_unchanged': True}))
