"""Add term protection and relationship consistency without changing 0010."""
from django.db import migrations

TRIGGERS = [('h2_term_update',
  'CREATE TRIGGER h2_term_update BEFORE UPDATE ON schedules_academicterm WHEN (EXISTS (SELECT 1 FROM '
  "schedules_schedule p WHERE p.term_id=OLD.id AND p.status IN ('PUBLISHED', 'ARCHIVED')) OR EXISTS (SELECT "
  '1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  'schedules_teachingassignment a ON a.id=e.assignment_id LEFT JOIN schedules_assignment parent ON '
  "parent.id=a.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND (a.term_id=OLD.id OR "
  'parent.term_id=OLD.id))) AND (OLD.id IS NOT NEW.id OR OLD.name IS NOT NEW.name OR OLD.school_year IS NOT '
  'NEW.school_year OR OLD.starts_on IS NOT NEW.starts_on OR OLD.ends_on IS NOT NEW.ends_on) BEGIN SELECT '
  "RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it unchanged "
  "and use separate records for future scheduling.'); END"),
 ('h2_term_delete',
  'CREATE TRIGGER h2_term_delete BEFORE DELETE ON schedules_academicterm WHEN (EXISTS (SELECT 1 FROM '
  "schedules_schedule p WHERE p.term_id=OLD.id AND p.status IN ('PUBLISHED', 'ARCHIVED')) OR EXISTS (SELECT "
  '1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  'schedules_teachingassignment a ON a.id=e.assignment_id LEFT JOIN schedules_assignment parent ON '
  "parent.id=a.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND (a.term_id=OLD.id OR "
  "parent.term_id=OLD.id))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_term_insert',
  'CREATE TRIGGER h2_term_insert BEFORE INSERT ON schedules_academicterm WHEN EXISTS (SELECT 1 FROM '
  'schedules_academicterm target WHERE (target.id=NEW.id OR (target.name=NEW.name AND '
  'target.school_year=NEW.school_year)) AND (EXISTS (SELECT 1 FROM schedules_schedule p WHERE '
  "p.term_id=target.id AND p.status IN ('PUBLISHED', 'ARCHIVED')) OR EXISTS (SELECT 1 FROM "
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  'schedules_teachingassignment a ON a.id=e.assignment_id LEFT JOIN schedules_assignment parent ON '
  "parent.id=a.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND (a.term_id=target.id OR "
  "parent.term_id=target.id)))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_schedule_term_consistency',
  'CREATE TRIGGER h2_schedule_term_consistency BEFORE UPDATE OF term_id ON schedules_schedule WHEN '
  'OLD.term_id IS NOT NEW.term_id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_teachingassignment a ON a.id=e.assignment_id WHERE e.schedule_id=OLD.id AND a.term_id IS NOT '
  "NEW.term_id) BEGIN SELECT RAISE(ABORT, 'Academic terms must match across the schedule, assignment, and "
  'meeting. Remove draft entries before changing their term, or edit the parent assignment for unscheduled '
  "meetings.'); END"),
 ('h2_entry_term_insert',
  'CREATE TRIGGER h2_entry_term_insert BEFORE INSERT ON schedules_scheduleentry WHEN EXISTS (SELECT 1 FROM '
  'schedules_schedule p, schedules_teachingassignment a WHERE p.id=NEW.schedule_id AND '
  "a.id=NEW.assignment_id AND p.term_id IS NOT a.term_id) BEGIN SELECT RAISE(ABORT, 'Academic terms must "
  'match across the schedule, assignment, and meeting. Remove draft entries before changing their term, or '
  "edit the parent assignment for unscheduled meetings.'); END"),
 ('h2_entry_term_update',
  'CREATE TRIGGER h2_entry_term_update BEFORE UPDATE OF schedule_id, assignment_id ON '
  'schedules_scheduleentry WHEN EXISTS (SELECT 1 FROM schedules_schedule p, schedules_teachingassignment a '
  'WHERE p.id=NEW.schedule_id AND a.id=NEW.assignment_id AND p.term_id IS NOT a.term_id) BEGIN SELECT '
  "RAISE(ABORT, 'Academic terms must match across the schedule, assignment, and meeting. Remove draft "
  "entries before changing their term, or edit the parent assignment for unscheduled meetings.'); END"),
 ('h2_meeting_term_insert',
  'CREATE TRIGGER h2_meeting_term_insert BEFORE INSERT ON schedules_teachingassignment WHEN EXISTS (SELECT 1 '
  'FROM schedules_assignment parent WHERE parent.id=NEW.assignment_id AND parent.term_id IS NOT NEW.term_id) '
  'OR EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id WHERE '
  "e.assignment_id=NEW.id AND p.term_id IS NOT NEW.term_id) BEGIN SELECT RAISE(ABORT, 'Academic terms must "
  'match across the schedule, assignment, and meeting. Remove draft entries before changing their term, or '
  "edit the parent assignment for unscheduled meetings.'); END"),
 ('h2_meeting_term_update',
  'CREATE TRIGGER h2_meeting_term_update BEFORE UPDATE OF term_id, assignment_id ON '
  'schedules_teachingassignment WHEN EXISTS (SELECT 1 FROM schedules_assignment parent WHERE '
  'parent.id=NEW.assignment_id AND parent.term_id IS NOT NEW.term_id) OR EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id WHERE e.assignment_id=OLD.id '
  "AND p.term_id IS NOT NEW.term_id) BEGIN SELECT RAISE(ABORT, 'Academic terms must match across the "
  'schedule, assignment, and meeting. Remove draft entries before changing their term, or edit the parent '
  "assignment for unscheduled meetings.'); END"),
 ('h2_parent_term_consistency',
  'CREATE TRIGGER h2_parent_term_consistency BEFORE UPDATE OF term_id ON schedules_assignment WHEN '
  'OLD.term_id IS NOT NEW.term_id AND (EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_teachingassignment a ON a.id=e.assignment_id JOIN schedules_schedule p ON p.id=e.schedule_id '
  'WHERE a.assignment_id=OLD.id AND p.term_id IS NOT NEW.term_id) OR (schedease_term_sync(OLD.id, '
  'NEW.term_id)=0 AND EXISTS (SELECT 1 FROM schedules_teachingassignment a WHERE a.assignment_id=OLD.id AND '
  "a.term_id IS NOT NEW.term_id))) BEGIN SELECT RAISE(ABORT, 'Academic terms must match across the schedule, "
  'assignment, and meeting. Remove draft entries before changing their term, or edit the parent assignment '
  "for unscheduled meetings.'); END"),
 ('h2_schedule_term_insert',
  'CREATE TRIGGER h2_schedule_term_insert BEFORE INSERT ON schedules_schedule WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_teachingassignment a ON a.id=e.assignment_id WHERE '
  "e.schedule_id=NEW.id AND a.term_id IS NOT NEW.term_id) BEGIN SELECT RAISE(ABORT, 'Academic terms must "
  'match across the schedule, assignment, and meeting. Remove draft entries before changing their term, or '
  "edit the parent assignment for unscheduled meetings.'); END"),
 ('h2_parent_term_insert',
  'CREATE TRIGGER h2_parent_term_insert BEFORE INSERT ON schedules_assignment WHEN EXISTS (SELECT 1 FROM '
  'schedules_teachingassignment a WHERE a.assignment_id=NEW.id AND a.term_id IS NOT NEW.term_id) BEGIN '
  "SELECT RAISE(ABORT, 'Academic terms must match across the schedule, assignment, and meeting. Remove draft "
  "entries before changing their term, or edit the parent assignment for unscheduled meetings.'); END")]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        raise RuntimeError("Academic-term guards require the supported SQLite backend.")
    for _, sql in TRIGGERS:
        schema_editor.execute(sql)


def uninstall(apps, schema_editor):
    for name, _ in reversed(TRIGGERS):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')


class Migration(migrations.Migration):
    dependencies = [("schedules", "0010_finalized_schedule_guards")]
    operations = [migrations.RunPython(install, uninstall)]
