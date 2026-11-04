"""Finalization is a validated transaction; finalized terms retain membership."""
from django.db import migrations

MESSAGE = 'This term has a published or archived schedule. Its required assignment membership cannot be changed. Use a separate term until a reviewed revision workflow is available.'
PUBLICATION = 'Finalized schedules require the authorized, validated publication workflow.'


def finalized(term):
    return f"EXISTS(SELECT 1 FROM schedules_schedule s WHERE s.term_id={term} AND s.status IN ('PUBLISHED','ARCHIVED'))"


TRIGGERS = {
    'publication_insert': f"""CREATE TRIGGER publication_insert BEFORE INSERT ON schedules_schedule
      WHEN NEW.status NOT IN ('DRAFT','APPROVED') OR NEW.published_at IS NOT NULL
      OR NEW.archived_at IS NOT NULL OR NEW.replaced_by_id IS NOT NULL
      BEGIN SELECT RAISE(ABORT,'{PUBLICATION}'); END""",
    'publication_update': f"""CREATE TRIGGER publication_update BEFORE UPDATE ON schedules_schedule
      WHEN (OLD.status IS NOT NEW.status OR OLD.published_at IS NOT NEW.published_at
        OR OLD.archived_at IS NOT NEW.archived_at OR OLD.replaced_by_id IS NOT NEW.replaced_by_id)
      AND NOT (
        (OLD.status IN ('DRAFT','APPROVED') AND NEW.status IN ('DRAFT','APPROVED')
         AND NEW.published_at IS NULL AND NEW.archived_at IS NULL AND NEW.replaced_by_id IS NULL)
        OR (OLD.id=NEW.id AND OLD.term_id=NEW.term_id
          AND schedease_publication_v1(OLD.id,OLD.term_id,OLD.status,NEW.status,
            NEW.published_at,NEW.archived_at,NEW.replaced_by_id)=1
          AND ((OLD.status IN ('DRAFT','APPROVED') AND NEW.status='PUBLISHED'
            AND NEW.published_at IS NOT NULL AND NEW.archived_at IS NULL AND NEW.replaced_by_id IS NULL
            AND EXISTS(SELECT 1 FROM schedules_scheduleentry WHERE schedule_id=OLD.id)
            AND NOT EXISTS(SELECT 1 FROM schedules_teachingassignment a WHERE a.term_id=OLD.term_id
              AND NOT EXISTS(SELECT 1 FROM schedules_scheduleentry e WHERE e.schedule_id=OLD.id AND e.assignment_id=a.id))
            AND NOT EXISTS(SELECT 1 FROM schedules_scheduleentry e JOIN schedules_teachingassignment a ON a.id=e.assignment_id
              WHERE e.schedule_id=OLD.id AND a.term_id<>OLD.term_id))
          OR (OLD.status='PUBLISHED' AND NEW.status='ARCHIVED'
            AND NEW.published_at IS OLD.published_at AND NEW.archived_at IS NOT NULL
            AND EXISTS(SELECT 1 FROM schedules_schedule r WHERE r.id=NEW.replaced_by_id
              AND r.term_id=OLD.term_id AND r.status IN ('DRAFT','APPROVED')))))
      ) BEGIN SELECT RAISE(ABORT,'{PUBLICATION}'); END""",
}
for model, columns in (
    ('assignment', 'id term_id subject_id section_id faculty_id'),
    ('teachingassignment', 'id term_id subject_id section_id faculty_id assignment_id component meeting_index duration_minutes required_room_type_override'),
):
    victim = f"EXISTS(SELECT 1 FROM schedules_{model} v WHERE v.id=NEW.id AND {finalized('v.term_id')})"
    for event, condition in (
        ('insert', finalized('NEW.term_id')+' OR '+victim),
        ('delete', finalized('OLD.term_id')),
        ('update', '('+' OR '.join(f'OLD.{c} IS NOT NEW.{c}' for c in columns.split())+') AND ('+finalized('OLD.term_id')+' OR '+finalized('NEW.term_id')+' OR '+victim+')'),
    ):
        name=f'final_membership_{model}_{event}'
        TRIGGERS[name]=f"CREATE TRIGGER {name} BEFORE {event.upper()} ON schedules_{model} WHEN {condition} BEGIN SELECT RAISE(ABORT,'{MESSAGE}'); END"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        raise RuntimeError('Publication protection requires SQLite.')
    for sql in TRIGGERS.values():
        schema_editor.execute(sql)


def backwards(apps, schema_editor):
    for name in TRIGGERS:
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')


class Migration(migrations.Migration):
    dependencies = [('schedules','0033_shs_approval_scope')]
    operations = [migrations.RunPython(forwards, backwards)]
