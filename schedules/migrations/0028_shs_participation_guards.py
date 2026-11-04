"""Frozen dependency view and additive guards; never rewrite historical data."""
from django.db import migrations


VIEW = 'shs_finalized_participation_v1'
# JSON is sanitized before traversal. Unknown historical membership is an
# explicit uncertainty row, not an empty/safe dependency set.
VIEW_SQL = f"""CREATE VIEW {VIEW} AS
WITH evidence AS (
 SELECT e.schedule_id, e.id AS entry_id, a.id AS meeting_id, a.section_id AS primary_id, a.assignment_id,
        a.term_id, a.subject_id, a.faculty_id, b.id AS binding_id,
        pat.configuration_id AS live_configuration_id,
        CASE WHEN json_valid(b.data) THEN b.data ELSE '{{}}' END AS data
 FROM schedules_scheduleentry e
 JOIN schedules_schedule s ON s.id=e.schedule_id
 JOIN schedules_academicterm t ON t.id=s.term_id
 JOIN schedules_teachingassignment a ON a.id=e.assignment_id
 LEFT JOIN schedules_shsmeetingbinding b ON b.meeting_id=a.id
 LEFT JOIN schedules_shsmeetingpattern pat ON pat.id=b.pattern_id
 WHERE s.status IN ('PUBLISHED','ARCHIVED')
   AND (t.education_level='SHS' OR b.id IS NOT NULL
        OR EXISTS (SELECT 1 FROM schedules_shsassignmentconfiguration c WHERE c.assignment_id=a.assignment_id))
), checked AS (
 SELECT *, CASE WHEN
   binding_id IS NOT NULL
   AND json_type(data)='object'
   AND json_type(data,'$.sections')='array'
   AND json_array_length(data,'$.sections')>0
   AND json_type(data,'$.configuration_id')='integer'
   AND json_type(data,'$.plan_id')='integer'
   AND json_type(data,'$.component_id')='integer'
   AND json_extract(data,'$.configuration_id')=live_configuration_id
   AND EXISTS (SELECT 1 FROM schedules_shsassignmentconfiguration c
       WHERE c.id=live_configuration_id AND c.assignment_id=evidence.assignment_id
         AND c.delivery_plan_id=json_extract(data,'$.plan_id'))
   AND EXISTS (SELECT 1 FROM schedules_shsmeetingbinding b2
       JOIN schedules_shsmeetingpattern p2 ON p2.id=b2.pattern_id
       WHERE b2.id=binding_id AND p2.component_id=json_extract(data,'$.component_id'))
   AND json_type(data,'$.term_id')='integer' AND json_extract(data,'$.term_id')=term_id
   AND json_type(data,'$.subject_id')='integer' AND json_extract(data,'$.subject_id')=subject_id
   AND json_type(data,'$.faculty_id')='integer' AND json_extract(data,'$.faculty_id')=faculty_id
   AND json_extract(data,'$.sections[0].id')=primary_id
   AND EXISTS (SELECT 1 FROM schedules_schedulesnapshot history
       WHERE history.schedule_id=evidence.schedule_id
       AND CASE WHEN json_valid(history.data) THEN
           CASE WHEN json_type(history.data)='object' AND json_type(history.data,'$.entries')='array'
                     AND json_extract(history.data,'$.schedule.id')=evidence.schedule_id
                     AND json_extract(history.data,'$.term.id')=evidence.term_id
           THEN EXISTS (SELECT 1 FROM json_each(history.data,'$.entries') row
               WHERE CASE WHEN row.type='object' THEN
                   json_type(row.value,'$.id')='integer'
                   AND json_type(row.value,'$.meeting_id')='integer'
                   AND json_type(row.value,'$.section.id')='integer'
                   AND json_extract(row.value,'$.id')=evidence.entry_id
                   AND json_extract(row.value,'$.meeting_id')=evidence.meeting_id
                   AND json_extract(row.value,'$.section.id')=evidence.primary_id
               ELSE 0 END)
               AND (SELECT count(*) FROM json_each(history.data,'$.entries') row
                    WHERE CASE WHEN row.type='object' THEN
                        json_extract(row.value,'$.id')=evidence.entry_id ELSE 0 END)=1
           ELSE 0 END
       ELSE 0 END)
   AND (json_array_length(data,'$.sections')=1 OR
        (json_type(data,'$.combined_reference')='text' AND trim(json_extract(data,'$.combined_reference'))<>''))
   AND NOT EXISTS (
       SELECT 1 FROM json_each(CASE WHEN json_type(data,'$.sections')='array'
                                   THEN json_extract(data,'$.sections') ELSE '[]' END) j
       WHERE CASE WHEN j.type='object' THEN
           CASE WHEN json_type(j.value,'$.id')='integer' AND json_extract(j.value,'$.id')>0
                 AND json_type(j.value,'$.size')='integer' AND json_extract(j.value,'$.size')>=0
                 AND json_type(j.value,'$.cohort_id')='integer'
                 AND json_type(j.value,'$.name')='text'
                 AND EXISTS (SELECT 1 FROM schedules_section sec
                     JOIN schedules_program pr ON pr.id=sec.program_id
                     JOIN schedules_yearlevel y ON y.id=sec.year_level_id
                     JOIN schedules_department d ON d.id=pr.department_id
                     WHERE sec.id=json_extract(j.value,'$.id')
                       AND sec.cohort_id=json_extract(j.value,'$.cohort_id')
                       AND sec.size=json_extract(j.value,'$.size'))
                THEN 0 ELSE 1 END
           ELSE 1 END=1)
   AND (SELECT count(*) FROM json_each(CASE WHEN json_type(data,'$.sections')='array'
               THEN json_extract(data,'$.sections') ELSE '[]' END)) =
       (SELECT count(DISTINCT CASE WHEN j.type='object' THEN json_extract(j.value,'$.id') END)
        FROM json_each(CASE WHEN json_type(data,'$.sections')='array'
               THEN json_extract(data,'$.sections') ELSE '[]' END) j)
 THEN 0 ELSE 1 END AS uncertain
 FROM evidence
)
SELECT schedule_id, NULL AS section_id, NULL AS configuration_id, 1 AS uncertain
FROM checked WHERE uncertain=1
UNION
SELECT c.schedule_id, json_extract(j.value,'$.id'), json_extract(c.data,'$.configuration_id'), 0
FROM checked c, json_each(CASE WHEN c.uncertain=0 THEN json_extract(c.data,'$.sections') ELSE '[]' END) j
UNION
SELECT e.schedule_id, e.primary_id, c.id, 0
FROM evidence e JOIN schedules_shsassignmentconfiguration c ON c.assignment_id=e.assignment_id
UNION
SELECT e.schedule_id, p.section_id, c.id, 0
FROM evidence e JOIN schedules_shsassignmentconfiguration c ON c.assignment_id=e.assignment_id
JOIN schedules_shssectionparticipation p ON p.configuration_id=c.id
"""


def dependency(model, key):
    predicates = {
        'section': f'd.section_id={key}',
        'program': f'EXISTS (SELECT 1 FROM schedules_section x WHERE x.id=d.section_id AND x.program_id={key})',
        'yearlevel': f'EXISTS (SELECT 1 FROM schedules_section x WHERE x.id=d.section_id AND x.year_level_id={key})',
        'department': f'EXISTS (SELECT 1 FROM schedules_section x JOIN schedules_program p ON p.id=x.program_id WHERE x.id=d.section_id AND p.department_id={key})',
        'configuration': f'd.configuration_id={key}',
    }
    return f'EXISTS (SELECT 1 FROM {VIEW} d WHERE d.uncertain=1 OR ({predicates[model]}))'


FIELDS = {
    'section': 'program_id year_level_id name size cohort_id',
    'program': 'department_id code name education_level',
    'yearlevel': 'level label',
    'department': 'code name',
}
MESSAGE = 'This record supports a published or archived SHS schedule, or its historical participation needs review. Keep the current values until a validated editing workflow is available.'
TRIGGERS = {}
for model, fields in FIELDS.items():
    conditions = ' OR '.join(f'OLD.{field} IS NOT NEW.{field}' for field in ['id', *fields.split()])
    unique_match = {
        'section': 'old_record.program_id=NEW.program_id AND old_record.year_level_id=NEW.year_level_id AND schedease_identity_v1(old_record.name)=schedease_identity_v1(NEW.name)',
        'program': 'schedease_identity_v1(old_record.code)=schedease_identity_v1(NEW.code)',
        'department': 'schedease_identity_v1(old_record.code)=schedease_identity_v1(NEW.code)',
        'yearlevel': 'old_record.level=NEW.level',
    }[model]
    collision = f'(old_record.id=NEW.id OR ({unique_match})) AND {dependency(model, "old_record.id")}'
    for operation, condition in (
        ('update', f'(({conditions}) AND {dependency(model, "OLD.id")}) OR EXISTS (SELECT 1 FROM schedules_{model} old_record WHERE old_record.id<>OLD.id AND {collision})'),
        ('delete', dependency(model, 'OLD.id')),
        ('insert', f'EXISTS (SELECT 1 FROM schedules_{model} old_record WHERE {collision})'),
    ):
        name = f'shs_participant_{model}_{operation}'
        TRIGGERS[name] = f"CREATE TRIGGER {name} BEFORE {operation.upper()} ON schedules_{model} WHEN {condition} BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"

old = dependency('configuration', 'OLD.configuration_id')
new = dependency('configuration', 'NEW.configuration_id')
for operation, condition in (
    ('delete', old),
    ('update', f"((OLD.id IS NOT NEW.id OR OLD.configuration_id IS NOT NEW.configuration_id OR OLD.section_id IS NOT NEW.section_id) AND ({old} OR {new})) OR EXISTS (SELECT 1 FROM schedules_shssectionparticipation prior WHERE prior.id<>OLD.id AND prior.id=NEW.id AND {dependency('configuration', 'prior.configuration_id')})"),
    ('insert', f"{new} OR EXISTS (SELECT 1 FROM schedules_shssectionparticipation prior WHERE (prior.id=NEW.id OR (prior.configuration_id=NEW.configuration_id AND prior.section_id=NEW.section_id)) AND {dependency('configuration', 'prior.configuration_id')})"),
):
    name = f'shs_participation_{operation}'
    TRIGGERS[name] = f"CREATE TRIGGER {name} BEFORE {operation.upper()} ON schedules_shssectionparticipation WHEN {condition} BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        schema_editor.execute(VIEW_SQL)
        for sql in TRIGGERS.values():
            schema_editor.execute(sql)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        for name in TRIGGERS:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')
        schema_editor.execute(f'DROP VIEW IF EXISTS {VIEW}')


class Migration(migrations.Migration):
    dependencies = [('schedules', '0027_faculty_account_link')]
    operations = [migrations.RunPython(forwards, backwards)]
