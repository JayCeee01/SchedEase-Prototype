"""SQLite guards are necessary because bulk ORM operations bypass model validation.

Frozen SQL: later policy changes must use a new migration, not edit this one.
"""
from django.db import migrations

TRIGGERS = [('h2_department_update',
  'CREATE TRIGGER h2_department_update BEFORE UPDATE ON schedules_department WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '((EXISTS (SELECT 1 FROM schedules_subject c WHERE c.id IN (a.subject_id, e.subject_override_id) AND '
  'c.department_id=OLD.id) OR EXISTS (SELECT 1 FROM schedules_faculty f WHERE f.id IN (a.faculty_id, '
  'e.faculty_override_id) AND f.department_id=OLD.id) OR EXISTS (SELECT 1 FROM schedules_section s JOIN '
  'schedules_program pr ON pr.id=s.program_id WHERE s.id IN (a.section_id, e.section_override_id) AND '
  'pr.department_id=OLD.id))))) AND (OLD.id IS NOT NEW.id OR OLD.code IS NOT NEW.code OR OLD.name IS NOT '
  "NEW.name) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is "
  "locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_department_delete',
  'CREATE TRIGGER h2_department_delete BEFORE DELETE ON schedules_department WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '((EXISTS (SELECT 1 FROM schedules_subject c WHERE c.id IN (a.subject_id, e.subject_override_id) AND '
  'c.department_id=OLD.id) OR EXISTS (SELECT 1 FROM schedules_faculty f WHERE f.id IN (a.faculty_id, '
  'e.faculty_override_id) AND f.department_id=OLD.id) OR EXISTS (SELECT 1 FROM schedules_section s JOIN '
  'schedules_program pr ON pr.id=s.program_id WHERE s.id IN (a.section_id, e.section_override_id) AND '
  "pr.department_id=OLD.id)))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_department_insert',
  'CREATE TRIGGER h2_department_insert BEFORE INSERT ON schedules_department WHEN EXISTS (SELECT 1 FROM '
  'schedules_department target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e '
  'JOIN schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON '
  "a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND ((EXISTS (SELECT 1 FROM "
  'schedules_subject c WHERE c.id IN (a.subject_id, e.subject_override_id) AND c.department_id=target.id) OR '
  'EXISTS (SELECT 1 FROM schedules_faculty f WHERE f.id IN (a.faculty_id, e.faculty_override_id) AND '
  'f.department_id=target.id) OR EXISTS (SELECT 1 FROM schedules_section s JOIN schedules_program pr ON '
  'pr.id=s.program_id WHERE s.id IN (a.section_id, e.section_override_id) AND '
  "pr.department_id=target.id))))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_program_update',
  'CREATE TRIGGER h2_program_update BEFORE UPDATE ON schedules_program WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND '
  's.program_id=OLD.id)))) AND (OLD.id IS NOT NEW.id OR OLD.department_id IS NOT NEW.department_id OR '
  "OLD.code IS NOT NEW.code OR OLD.name IS NOT NEW.name) BEGIN SELECT RAISE(ABORT, 'This record is used by a "
  'published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_program_delete',
  'CREATE TRIGGER h2_program_delete BEFORE DELETE ON schedules_program WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND '
  "s.program_id=OLD.id))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule "
  "and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_program_insert',
  'CREATE TRIGGER h2_program_insert BEFORE INSERT ON schedules_program WHEN EXISTS (SELECT 1 FROM '
  'schedules_program target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id '
  "WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND (EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN "
  "(a.section_id, e.section_override_id) AND s.program_id=target.id)))) BEGIN SELECT RAISE(ABORT, 'This "
  'record is used by a published or archived schedule and is locked. Keep it unchanged and use separate '
  "records for future scheduling.'); END"),
 ('h2_yearlevel_update',
  'CREATE TRIGGER h2_yearlevel_update BEFORE UPDATE ON schedules_yearlevel WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND '
  's.year_level_id=OLD.id)))) AND (OLD.id IS NOT NEW.id OR OLD.level IS NOT NEW.level OR OLD.label IS NOT '
  "NEW.label) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is "
  "locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_yearlevel_delete',
  'CREATE TRIGGER h2_yearlevel_delete BEFORE DELETE ON schedules_yearlevel WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(EXISTS (SELECT 1 FROM schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND '
  "s.year_level_id=OLD.id))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_yearlevel_insert',
  'CREATE TRIGGER h2_yearlevel_insert BEFORE INSERT ON schedules_yearlevel WHEN EXISTS (SELECT 1 FROM '
  'schedules_yearlevel target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e '
  'JOIN schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON '
  "a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND (EXISTS (SELECT 1 FROM "
  'schedules_section s WHERE s.id IN (a.section_id, e.section_override_id) AND s.year_level_id=target.id)))) '
  "BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it "
  "unchanged and use separate records for future scheduling.'); END"),
 ('h2_section_update',
  'CREATE TRIGGER h2_section_update BEFORE UPDATE ON schedules_section WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '((a.section_id=OLD.id OR e.section_override_id=OLD.id)))) AND (OLD.id IS NOT NEW.id OR OLD.program_id IS '
  'NOT NEW.program_id OR OLD.year_level_id IS NOT NEW.year_level_id OR OLD.name IS NOT NEW.name OR OLD.size '
  "IS NOT NEW.size) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and "
  "is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_section_delete',
  'CREATE TRIGGER h2_section_delete BEFORE DELETE ON schedules_section WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "((a.section_id=OLD.id OR e.section_override_id=OLD.id))) BEGIN SELECT RAISE(ABORT, 'This record is used "
  'by a published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_section_insert',
  'CREATE TRIGGER h2_section_insert BEFORE INSERT ON schedules_section WHEN EXISTS (SELECT 1 FROM '
  'schedules_section target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id '
  "WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND ((a.section_id=target.id OR "
  "e.section_override_id=target.id)))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or "
  "archived schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); "
  'END'),
 ('h2_faculty_update',
  'CREATE TRIGGER h2_faculty_update BEFORE UPDATE ON schedules_faculty WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '((a.faculty_id=OLD.id OR e.faculty_override_id=OLD.id)))) AND (OLD.id IS NOT NEW.id OR OLD.user_id IS NOT '
  'NEW.user_id OR OLD.department_id IS NOT NEW.department_id OR OLD.employee_id IS NOT NEW.employee_id OR '
  'OLD.full_name IS NOT NEW.full_name OR OLD.max_weekly_hours IS NOT NEW.max_weekly_hours) BEGIN SELECT '
  "RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it unchanged "
  "and use separate records for future scheduling.'); END"),
 ('h2_faculty_delete',
  'CREATE TRIGGER h2_faculty_delete BEFORE DELETE ON schedules_faculty WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "((a.faculty_id=OLD.id OR e.faculty_override_id=OLD.id))) BEGIN SELECT RAISE(ABORT, 'This record is used "
  'by a published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_faculty_insert',
  'CREATE TRIGGER h2_faculty_insert BEFORE INSERT ON schedules_faculty WHEN EXISTS (SELECT 1 FROM '
  'schedules_faculty target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id '
  "WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND ((a.faculty_id=target.id OR "
  "e.faculty_override_id=target.id)))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or "
  "archived schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); "
  'END'),
 ('h2_room_update',
  'CREATE TRIGGER h2_room_update BEFORE UPDATE ON schedules_room WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(e.room_id=OLD.id))) AND (OLD.id IS NOT NEW.id OR OLD.name IS NOT NEW.name OR OLD.room_type IS NOT '
  'NEW.room_type OR OLD.capacity IS NOT NEW.capacity OR OLD.is_active IS NOT NEW.is_active) BEGIN SELECT '
  "RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it unchanged "
  "and use separate records for future scheduling.'); END"),
 ('h2_room_delete',
  'CREATE TRIGGER h2_room_delete BEFORE DELETE ON schedules_room WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "(e.room_id=OLD.id)) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule "
  "and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_room_insert',
  'CREATE TRIGGER h2_room_insert BEFORE INSERT ON schedules_room WHEN EXISTS (SELECT 1 FROM schedules_room '
  'target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule '
  'p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN '
  "('PUBLISHED', 'ARCHIVED') AND (e.room_id=target.id))) BEGIN SELECT RAISE(ABORT, 'This record is used by a "
  'published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_subject_update',
  'CREATE TRIGGER h2_subject_update BEFORE UPDATE ON schedules_subject WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '((a.subject_id=OLD.id OR e.subject_override_id=OLD.id)))) AND (OLD.id IS NOT NEW.id OR OLD.code IS NOT '
  'NEW.code OR OLD.title IS NOT NEW.title OR OLD.department_id IS NOT NEW.department_id OR OLD.units IS NOT '
  'NEW.units OR OLD.lecture_hours IS NOT NEW.lecture_hours OR OLD.lab_hours IS NOT NEW.lab_hours OR '
  "OLD.required_room_type IS NOT NEW.required_room_type) BEGIN SELECT RAISE(ABORT, 'This record is used by a "
  'published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_subject_delete',
  'CREATE TRIGGER h2_subject_delete BEFORE DELETE ON schedules_subject WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "((a.subject_id=OLD.id OR e.subject_override_id=OLD.id))) BEGIN SELECT RAISE(ABORT, 'This record is used "
  'by a published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_subject_insert',
  'CREATE TRIGGER h2_subject_insert BEFORE INSERT ON schedules_subject WHEN EXISTS (SELECT 1 FROM '
  'schedules_subject target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id '
  "WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND ((a.subject_id=target.id OR "
  "e.subject_override_id=target.id)))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or "
  "archived schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); "
  'END'),
 ('h2_assignment_update',
  'CREATE TRIGGER h2_assignment_update BEFORE UPDATE ON schedules_assignment WHEN (EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(a.assignment_id=OLD.id))) AND (OLD.id IS NOT NEW.id OR OLD.term_id IS NOT NEW.term_id OR OLD.subject_id '
  'IS NOT NEW.subject_id OR OLD.faculty_id IS NOT NEW.faculty_id OR OLD.section_id IS NOT NEW.section_id) '
  "BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it "
  "unchanged and use separate records for future scheduling.'); END"),
 ('h2_assignment_delete',
  'CREATE TRIGGER h2_assignment_delete BEFORE DELETE ON schedules_assignment WHEN EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "(a.assignment_id=OLD.id)) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_assignment_insert',
  'CREATE TRIGGER h2_assignment_insert BEFORE INSERT ON schedules_assignment WHEN EXISTS (SELECT 1 FROM '
  'schedules_assignment target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e '
  'JOIN schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON '
  "a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND (a.assignment_id=target.id))) BEGIN "
  "SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it "
  "unchanged and use separate records for future scheduling.'); END"),
 ('h2_teachingassignment_update',
  'CREATE TRIGGER h2_teachingassignment_update BEFORE UPDATE ON schedules_teachingassignment WHEN ((EXISTS '
  '(SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(a.id=OLD.id))) AND (OLD.id IS NOT NEW.id OR OLD.term_id IS NOT NEW.term_id OR OLD.subject_id IS NOT '
  'NEW.subject_id OR OLD.faculty_id IS NOT NEW.faculty_id OR OLD.section_id IS NOT NEW.section_id OR '
  'OLD.component IS NOT NEW.component OR OLD.meeting_index IS NOT NEW.meeting_index OR OLD.duration_minutes '
  'IS NOT NEW.duration_minutes OR OLD.required_room_type_override IS NOT NEW.required_room_type_override OR '
  'OLD.assignment_id IS NOT NEW.assignment_id)) OR ((OLD.assignment_id IS NOT NEW.assignment_id AND EXISTS '
  '(SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "a.assignment_id=NEW.assignment_id))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or "
  "archived schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); "
  'END'),
 ('h2_teachingassignment_delete',
  'CREATE TRIGGER h2_teachingassignment_delete BEFORE DELETE ON schedules_teachingassignment WHEN EXISTS '
  '(SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "(a.id=OLD.id)) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is "
  "locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_teachingassignment_insert',
  'CREATE TRIGGER h2_teachingassignment_insert BEFORE INSERT ON schedules_teachingassignment WHEN (EXISTS '
  '(SELECT 1 FROM schedules_teachingassignment target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(a.id=target.id)))) OR (EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON '
  'p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN '
  "('PUBLISHED', 'ARCHIVED') AND a.assignment_id=NEW.assignment_id)) BEGIN SELECT RAISE(ABORT, 'This record "
  'is used by a published or archived schedule and is locked. Keep it unchanged and use separate records for '
  "future scheduling.'); END"),
 ('h2_schedule_update',
  "CREATE TRIGGER h2_schedule_update BEFORE UPDATE ON schedules_schedule WHEN (OLD.status IN ('PUBLISHED', "
  "'ARCHIVED')) AND (OLD.id IS NOT NEW.id OR OLD.term_id IS NOT NEW.term_id OR OLD.name IS NOT NEW.name OR "
  'OLD.status IS NOT NEW.status OR OLD.fitness_score IS NOT NEW.fitness_score OR OLD.generated_at IS NOT '
  'NEW.generated_at OR OLD.published_at IS NOT NEW.published_at OR OLD.archived_at IS NOT NEW.archived_at OR '
  'OLD.replaced_by_id IS NOT NEW.replaced_by_id OR OLD.origin IS NOT NEW.origin) AND NOT '
  "(schedease_archiving()=1 AND OLD.status='PUBLISHED' AND NEW.status='ARCHIVED' AND OLD.id IS NEW.id AND "
  'OLD.term_id IS NEW.term_id AND OLD.name IS NEW.name AND OLD.fitness_score IS NEW.fitness_score AND '
  'OLD.generated_at IS NEW.generated_at AND OLD.published_at IS NEW.published_at AND OLD.origin IS '
  "NEW.origin) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is "
  "locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_schedule_delete',
  "CREATE TRIGGER h2_schedule_delete BEFORE DELETE ON schedules_schedule WHEN OLD.status IN ('PUBLISHED', "
  "'ARCHIVED') BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is "
  "locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_schedule_insert',
  'CREATE TRIGGER h2_schedule_insert BEFORE INSERT ON schedules_schedule WHEN EXISTS (SELECT 1 FROM '
  "schedules_schedule target WHERE target.id=NEW.id AND target.status IN ('PUBLISHED', 'ARCHIVED')) BEGIN "
  "SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it "
  "unchanged and use separate records for future scheduling.'); END"),
 ('h2_scheduleentry_update',
  'CREATE TRIGGER h2_scheduleentry_update BEFORE UPDATE ON schedules_scheduleentry WHEN ((EXISTS (SELECT 1 '
  "FROM schedules_schedule p WHERE p.id=OLD.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED'))) AND "
  '(OLD.id IS NOT NEW.id OR OLD.schedule_id IS NOT NEW.schedule_id OR OLD.assignment_id IS NOT '
  'NEW.assignment_id OR OLD.room_id IS NOT NEW.room_id OR OLD.day IS NOT NEW.day OR OLD.start_time IS NOT '
  'NEW.start_time OR OLD.end_time IS NOT NEW.end_time OR OLD.subject_override_id IS NOT '
  'NEW.subject_override_id OR OLD.section_override_id IS NOT NEW.section_override_id OR '
  'OLD.faculty_override_id IS NOT NEW.faculty_override_id OR OLD.component_override IS NOT '
  'NEW.component_override)) OR (OLD.schedule_id IS NOT NEW.schedule_id AND EXISTS (SELECT 1 FROM '
  "schedules_schedule p WHERE p.id=NEW.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED'))) BEGIN SELECT "
  "RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it unchanged "
  "and use separate records for future scheduling.'); END"),
 ('h2_scheduleentry_delete',
  'CREATE TRIGGER h2_scheduleentry_delete BEFORE DELETE ON schedules_scheduleentry WHEN EXISTS (SELECT 1 '
  "FROM schedules_schedule p WHERE p.id=OLD.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED')) BEGIN "
  "SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it "
  "unchanged and use separate records for future scheduling.'); END"),
 ('h2_scheduleentry_insert',
  'CREATE TRIGGER h2_scheduleentry_insert BEFORE INSERT ON schedules_scheduleentry WHEN EXISTS (SELECT 1 '
  'FROM schedules_scheduleentry target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM schedules_schedule p '
  "WHERE p.id=target.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED'))) OR (EXISTS (SELECT 1 FROM "
  "schedules_schedule p WHERE p.id=NEW.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED'))) BEGIN SELECT "
  "RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it unchanged "
  "and use separate records for future scheduling.'); END"),
 ('h2_scheduleentryaudit_update',
  'CREATE TRIGGER h2_scheduleentryaudit_update BEFORE UPDATE ON schedules_scheduleentryaudit WHEN ((EXISTS '
  "(SELECT 1 FROM schedules_schedule p WHERE p.id=OLD.schedule_id AND p.status IN ('PUBLISHED', "
  "'ARCHIVED'))) AND (OLD.id IS NOT NEW.id OR OLD.schedule_id IS NOT NEW.schedule_id OR OLD.entry_id IS NOT "
  'NEW.entry_id OR OLD.user_id IS NOT NEW.user_id OR OLD.previous_values IS NOT NEW.previous_values OR '
  'OLD.new_values IS NOT NEW.new_values OR OLD.created_at IS NOT NEW.created_at)) OR (OLD.schedule_id IS NOT '
  'NEW.schedule_id AND EXISTS (SELECT 1 FROM schedules_schedule p WHERE p.id=NEW.schedule_id AND p.status IN '
  "('PUBLISHED', 'ARCHIVED'))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_scheduleentryaudit_delete',
  'CREATE TRIGGER h2_scheduleentryaudit_delete BEFORE DELETE ON schedules_scheduleentryaudit WHEN EXISTS '
  "(SELECT 1 FROM schedules_schedule p WHERE p.id=OLD.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED')) "
  "BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is locked. Keep it "
  "unchanged and use separate records for future scheduling.'); END"),
 ('h2_scheduleentryaudit_insert',
  'CREATE TRIGGER h2_scheduleentryaudit_insert BEFORE INSERT ON schedules_scheduleentryaudit WHEN EXISTS '
  '(SELECT 1 FROM schedules_scheduleentryaudit target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM '
  "schedules_schedule p WHERE p.id=target.schedule_id AND p.status IN ('PUBLISHED', 'ARCHIVED'))) OR (EXISTS "
  "(SELECT 1 FROM schedules_schedule p WHERE p.id=NEW.schedule_id AND p.status IN ('PUBLISHED', "
  "'ARCHIVED'))) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived schedule and is "
  "locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_credentialoverride_update',
  'CREATE TRIGGER h2_credentialoverride_update BEFORE UPDATE ON schedules_credentialoverride WHEN ((EXISTS '
  '(SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(a.id=OLD.assignment_id))) AND (OLD.id IS NOT NEW.id OR OLD.assignment_id IS NOT NEW.assignment_id OR '
  'OLD.subject_id IS NOT NEW.subject_id OR OLD.faculty_id IS NOT NEW.faculty_id OR OLD.admin_user_id IS NOT '
  'NEW.admin_user_id OR OLD.reason IS NOT NEW.reason OR OLD.missing_credentials IS NOT '
  'NEW.missing_credentials OR OLD.created_at IS NOT NEW.created_at)) OR ((OLD.assignment_id IS NOT '
  'NEW.assignment_id AND EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON '
  'p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN '
  "('PUBLISHED', 'ARCHIVED') AND a.id=NEW.assignment_id))) BEGIN SELECT RAISE(ABORT, 'This record is used by "
  'a published or archived schedule and is locked. Keep it unchanged and use separate records for future '
  "scheduling.'); END"),
 ('h2_credentialoverride_delete',
  'CREATE TRIGGER h2_credentialoverride_delete BEFORE DELETE ON schedules_credentialoverride WHEN EXISTS '
  '(SELECT 1 FROM schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  "(a.id=OLD.assignment_id)) BEGIN SELECT RAISE(ABORT, 'This record is used by a published or archived "
  "schedule and is locked. Keep it unchanged and use separate records for future scheduling.'); END"),
 ('h2_credentialoverride_insert',
  'CREATE TRIGGER h2_credentialoverride_insert BEFORE INSERT ON schedules_credentialoverride WHEN (EXISTS '
  '(SELECT 1 FROM schedules_credentialoverride target WHERE target.id=NEW.id AND EXISTS (SELECT 1 FROM '
  'schedules_scheduleentry e JOIN schedules_schedule p ON p.id=e.schedule_id JOIN '
  "schedules_teachingassignment a ON a.id=e.assignment_id WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND "
  '(a.id=target.assignment_id)))) OR (EXISTS (SELECT 1 FROM schedules_scheduleentry e JOIN '
  'schedules_schedule p ON p.id=e.schedule_id JOIN schedules_teachingassignment a ON a.id=e.assignment_id '
  "WHERE p.status IN ('PUBLISHED', 'ARCHIVED') AND a.id=NEW.assignment_id)) BEGIN SELECT RAISE(ABORT, 'This "
  'record is used by a published or archived schedule and is locked. Keep it unchanged and use separate '
  "records for future scheduling.'); END")]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        raise RuntimeError("Finalized schedule guards require the supported SQLite backend.")
    for _, sql in TRIGGERS:
        schema_editor.execute(sql)


def uninstall(apps, schema_editor):
    for name, _ in reversed(TRIGGERS):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')


class Migration(migrations.Migration):
    dependencies = [("schedules", "0009_academicimport")]
    operations = [migrations.RunPython(install, uninstall)]
