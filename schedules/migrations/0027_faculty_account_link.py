"""Allow account association changes; retain all academic-content guards."""
from importlib import import_module
from django.db import migrations


ORIGINAL = dict(import_module('schedules.migrations.0010_finalized_schedule_guards').TRIGGERS)['h2_faculty_update']
UPDATED = ORIGINAL.replace('OLD.user_id IS NOT NEW.user_id OR ', '')


def replace_trigger(schema_editor, sql):
    if schema_editor.connection.vendor == 'sqlite':
        schema_editor.execute('DROP TRIGGER IF EXISTS h2_faculty_update')
        schema_editor.execute(sql)


def forwards(apps, schema_editor):
    replace_trigger(schema_editor, UPDATED)


def backwards(apps, schema_editor):
    replace_trigger(schema_editor, ORIGINAL)


class Migration(migrations.Migration):
    dependencies = [('schedules', '0026_shs_meeting_snapshots')]
    operations = [migrations.RunPython(forwards, backwards)]
