"""Frozen proposed-policy enforcement for finalized room/section commitments."""
from django.db import migrations

VIEW = 'finalized_resource_commitments_v1'
MESSAGE = 'This availability change conflicts with a published or archived meeting, or its historical evidence needs review. Keep the current values and review the affected schedules.'

# Reuse the frozen evidence checks from 0030/0028, adding room and effective
# section identity checks. Unknown evidence is never an empty dependency set.
VIEW_SQL = f"""CREATE VIEW {VIEW} AS
WITH source AS (
 SELECT c.*, e.room_id, coalesce(e.section_override_id,a.section_id) AS section_id,
        a.assignment_id,
        CASE WHEN json_valid(b.data) THEN b.data ELSE '{{}}' END AS binding
 FROM finalized_faculty_commitments_v1 c
 LEFT JOIN schedules_scheduleentry e ON e.id=c.entry_id
 LEFT JOIN schedules_teachingassignment a ON a.id=c.meeting_id
 LEFT JOIN schedules_shsmeetingbinding b ON b.meeting_id=c.meeting_id
), checked AS (
 SELECT *, CASE WHEN uncertain=0
   AND julianday('2000-01-01 '||start_time) IS NOT NULL
   AND julianday('2000-01-01 '||end_time) IS NOT NULL AND start_time<end_time
   AND EXISTS(SELECT 1 FROM schedules_room r WHERE r.id=source.room_id)
   AND EXISTS(SELECT 1 FROM schedules_section s WHERE s.id=source.section_id)
   AND (education_level<>'SHS' OR (json_type(binding,'$.room_id')='integer'
        AND json_extract(binding,'$.room_id')=source.room_id))
   AND EXISTS (
   SELECT 1 FROM json_each(history,'$.entries') j WHERE CASE WHEN j.type='object' THEN
     json_extract(j.value,'$.id')=source.entry_id
     AND json_type(j.value,'$.room.id')='integer'
     AND json_type(j.value,'$.section.id')='integer'
     AND json_extract(j.value,'$.room.id')=source.room_id
     AND json_extract(j.value,'$.section.id')=source.section_id
   ELSE 0 END) THEN 0 ELSE 1 END AS unknown FROM source
), owners AS (
 SELECT entry_id,schedule_id,'room' AS owner_kind,room_id AS owner_id,day,start_time,end_time,unknown FROM checked
 UNION
 SELECT entry_id,schedule_id,'section',section_id,day,start_time,end_time,unknown FROM checked
 UNION
 SELECT c.entry_id,c.schedule_id,'section',p.section_id,c.day,c.start_time,c.end_time,c.unknown
 FROM checked c JOIN schedules_shsassignmentconfiguration cfg ON cfg.assignment_id=c.assignment_id
 JOIN schedules_shssectionparticipation p ON p.configuration_id=cfg.id
 UNION
 SELECT c.entry_id,c.schedule_id,'section',json_extract(j.value,'$.id'),c.day,c.start_time,c.end_time,c.unknown
 FROM checked c, json_each(CASE WHEN c.unknown=0 AND json_type(c.binding,'$.sections')='array'
   THEN json_extract(c.binding,'$.sections') ELSE '[]' END) j WHERE j.type='object'
)
SELECT entry_id,schedule_id,owner_kind,owner_id,day,start_time,end_time,unknown AS uncertain FROM owners
"""


def failures(periods_sql, owners_sql):
    """Same whole-policy test for proposed Django state and native SQL writes."""
    return f"""WITH RECURSIVE raw_periods AS ({periods_sql}), owners(owner_kind,owner_id) AS ({owners_sql}),
    periods AS (
      SELECT 'room' AS owner_kind,room_id AS owner_id,day,start_time,end_time,kind FROM raw_periods WHERE room_id IS NOT NULL
      UNION ALL SELECT 'section',section_id,day,start_time,end_time,kind FROM raw_periods WHERE section_id IS NOT NULL
    ), commitments AS (
      SELECT c.* FROM {VIEW} c WHERE EXISTS(SELECT 1 FROM owners o
        WHERE o.owner_kind=c.owner_kind AND o.owner_id=c.owner_id)
    ), reach(entry_id,owner_kind,owner_id,finish) AS (
      SELECT entry_id,owner_kind,owner_id,julianday('2000-01-01 '||start_time) FROM commitments
      UNION
      SELECT c.entry_id,c.owner_kind,c.owner_id,julianday('2000-01-01 '||p.end_time)
      FROM reach r JOIN commitments c ON c.entry_id=r.entry_id AND c.owner_kind=r.owner_kind AND c.owner_id=r.owner_id
      JOIN periods p ON p.owner_kind=c.owner_kind AND p.owner_id=c.owner_id AND p.day=c.day AND p.kind='AVAILABLE'
      WHERE julianday('2000-01-01 '||p.start_time)<=r.finish AND julianday('2000-01-01 '||p.end_time)>r.finish
    )
    SELECT DISTINCT schedule_id,owner_kind,owner_id,uncertain FROM {VIEW}
      WHERE uncertain=1 AND EXISTS(SELECT 1 FROM owners WHERE owner_id IS NOT NULL)
    UNION
    SELECT c.schedule_id,c.owner_kind,c.owner_id,0 FROM commitments c WHERE
      (c.owner_kind='room' AND NOT EXISTS(SELECT 1 FROM schedules_room r WHERE r.id=c.owner_id AND r.is_active=1))
      OR ((c.owner_kind='room' OR EXISTS(SELECT 1 FROM periods p WHERE p.owner_kind=c.owner_kind AND p.owner_id=c.owner_id)) AND (
        c.day NOT BETWEEN 0 AND 5 OR c.start_time<'07:00:00' OR c.end_time>'19:00:00' OR c.start_time>=c.end_time
        OR EXISTS(SELECT 1 FROM periods p WHERE p.owner_kind=c.owner_kind AND p.owner_id=c.owner_id AND (
          p.kind NOT IN ('AVAILABLE','UNAVAILABLE','PREFERRED') OR (p.owner_kind='section' AND p.kind='PREFERRED')
          OR p.day NOT BETWEEN 0 AND 6 OR p.start_time>=p.end_time
          OR julianday('2000-01-01 '||p.start_time) IS NULL OR julianday('2000-01-01 '||p.end_time) IS NULL))
        OR EXISTS(SELECT 1 FROM periods p WHERE p.owner_kind=c.owner_kind AND p.owner_id=c.owner_id AND p.day=c.day AND p.kind='UNAVAILABLE'
          AND julianday('2000-01-01 '||p.start_time)<julianday('2000-01-01 '||c.end_time)
          AND julianday('2000-01-01 '||p.end_time)>julianday('2000-01-01 '||c.start_time))
        OR (EXISTS(SELECT 1 FROM periods p WHERE p.owner_kind=c.owner_kind AND p.owner_id=c.owner_id AND p.kind='AVAILABLE')
          AND NOT EXISTS(SELECT 1 FROM reach r WHERE r.entry_id=c.entry_id AND r.owner_kind=c.owner_kind AND r.owner_id=c.owner_id
            AND r.finish>=julianday('2000-01-01 '||c.end_time)))
      ))"""


COLUMNS = 'faculty_id room_id section_id day start_time end_time kind'.split()
TRIGGERS = {}
for event in ('INSERT', 'UPDATE', 'DELETE'):
    # Availability has only its primary-key unique constraint. Include the
    # implicit REPLACE victim as well as both sides of owner reassignment.
    ids = 'id=OLD.id' if event == 'DELETE' else 'id=NEW.id'
    if event == 'UPDATE':
        ids += ' OR id=OLD.id'
    owners = f"SELECT 'room',room_id FROM schedules_availability WHERE ({ids}) UNION SELECT 'section',section_id FROM schedules_availability WHERE ({ids})"
    periods = f'SELECT {",".join(COLUMNS)} FROM schedules_availability WHERE NOT ({ids})'
    if event != 'DELETE':
        owners += " UNION SELECT 'room',NEW.room_id UNION SELECT 'section',NEW.section_id"
        periods += ' UNION ALL SELECT ' + ','.join('NEW.'+col for col in COLUMNS)
    name = 'resource_availability_' + event.lower()
    TRIGGERS[name] = f"CREATE TRIGGER {name} BEFORE {event} ON schedules_availability WHEN EXISTS({failures(periods, owners)}) BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        raise RuntimeError('Resource availability guards require SQLite.')
    schema_editor.execute(VIEW_SQL)
    for sql in TRIGGERS.values():
        schema_editor.execute(sql)


def backwards(apps, schema_editor):
    for name in TRIGGERS:
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')
    schema_editor.execute(f'DROP VIEW IF EXISTS {VIEW}')


class Migration(migrations.Migration):
    dependencies = [('schedules', '0031_finalized_unique_collision_guards')]
    operations = [migrations.RunPython(forwards, backwards)]
