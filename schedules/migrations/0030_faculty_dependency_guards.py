"""Frozen, independent SQLite checks of proposed faculty dependency state.

No records are rewritten. Reversal removes only this migration's view/triggers.
The application uses these versioned SQL predicates for matching model feedback.
"""
from django.db import migrations

VIEW = 'finalized_faculty_commitments_v1'
MESSAGE = 'This change would invalidate a published or archived faculty commitment, or its historical evidence needs review. Keep the current values and review the affected schedules.'

VIEW_SQL = f"""CREATE VIEW {VIEW} AS
WITH source AS (
 SELECT e.id AS entry_id, e.schedule_id, e.assignment_id AS meeting_id,
   coalesce(e.faculty_override_id,a.faculty_id) AS faculty_id,
   coalesce(e.subject_override_id,a.subject_id) AS subject_id,
   s.term_id, t.starts_on, t.ends_on, t.education_level,
   e.day, e.start_time, e.end_time,
   CASE WHEN json_valid(h.data) AND h.schema_version=1 THEN h.data ELSE '{{}}' END AS history
 FROM schedules_scheduleentry e JOIN schedules_schedule s ON s.id=e.schedule_id
 JOIN schedules_teachingassignment a ON a.id=e.assignment_id
 JOIN schedules_academicterm t ON t.id=s.term_id
 LEFT JOIN schedules_schedulesnapshot h ON h.schedule_id=s.id
 WHERE s.status IN ('PUBLISHED','ARCHIVED')
)
SELECT *, CASE WHEN
 json_type(history)='object' AND json_type(history,'$.entries')='array'
 AND json_extract(history,'$.schedule.id')=schedule_id
 AND json_extract(history,'$.term.id')=term_id
 AND json_extract(history,'$.term.starts_on')=starts_on
 AND json_extract(history,'$.term.ends_on')=ends_on
 AND starts_on<ends_on
 AND (SELECT count(*) FROM json_each(history,'$.entries') j WHERE CASE WHEN j.type='object' THEN
   json_extract(j.value,'$.id')=source.entry_id ELSE 0 END)=1
 AND EXISTS(SELECT 1 FROM json_each(history,'$.entries') j WHERE CASE WHEN j.type='object' THEN
   json_extract(j.value,'$.id')=source.entry_id
   AND json_extract(j.value,'$.meeting_id')=source.meeting_id
   AND json_extract(j.value,'$.faculty.id')=source.faculty_id
   AND json_extract(j.value,'$.course.id')=source.subject_id
   AND json_extract(j.value,'$.day')=source.day
   AND json_extract(j.value,'$.start_time')=source.start_time
   AND json_extract(j.value,'$.end_time')=source.end_time ELSE 0 END)
 AND NOT EXISTS(SELECT 1 FROM shs_finalized_participation_v1 p
                WHERE p.schedule_id=source.schedule_id AND p.uncertain=1)
 AND (education_level<>'SHS' OR EXISTS (
   SELECT 1 FROM schedules_shsmeetingbinding b WHERE b.meeting_id=source.meeting_id
   AND CASE WHEN json_valid(b.data) THEN
     json_type(b.data,'$.dates')='array' AND json_array_length(b.data,'$.dates')>0
     AND NOT EXISTS(SELECT 1 FROM json_each(b.data,'$.dates') d WHERE
       CASE WHEN d.type='text' AND date(d.value,'+0 days')=d.value
         AND d.value BETWEEN source.starts_on AND source.ends_on
         AND (cast(strftime('%w',d.value) AS INTEGER)+6)%7=source.day
       THEN 0 ELSE 1 END=1) ELSE 0 END))
 THEN 0 ELSE 1 END AS uncertain FROM source
UNION
SELECT NULL,s.id,NULL,NULL,NULL,s.term_id,t.starts_on,t.ends_on,t.education_level,
       NULL,NULL,NULL,'{{}}',1
FROM schedules_schedule s JOIN schedules_academicterm t ON t.id=s.term_id
LEFT JOIN schedules_schedulesnapshot h ON h.schedule_id=s.id
WHERE s.status IN ('PUBLISHED','ARCHIVED') AND CASE WHEN json_valid(h.data) AND h.schema_version=1 THEN
 CASE WHEN json_type(h.data)='object' AND json_type(h.data,'$.entries')='array'
   AND json_array_length(h.data,'$.entries')=(SELECT count(*) FROM schedules_scheduleentry e WHERE e.schedule_id=s.id)
 THEN 0 ELSE 1 END ELSE 1 END=1
"""


def scope_covers():
    # Match schema-v1 evidence exactly as credentials.valid_credential_override.
    # SHS operational configuration independently requires qualification.
    return """c.education_level<>'SHS' AND EXISTS (
      SELECT 1 FROM schedules_credentialoverride o
      JOIN schedules_credentialapprovalevidence ev ON ev.override_id=o.id
      WHERE o.assignment_id=c.meeting_id AND o.faculty_id=c.faculty_id AND o.subject_id=c.subject_id
      AND trim(o.reason)<>'' AND trim(o.missing_credentials)<>'' AND ev.schema_version=1
      AND json_type(ev.data)='object'
      AND json_extract(ev.data,'$.assignment_id')=c.meeting_id
      AND json_extract(ev.data,'$.administrator_id')=o.admin_user_id
      AND json_extract(ev.data,'$.faculty_id')=c.faculty_id
      AND json_extract(ev.data,'$.subject_id')=c.subject_id
      AND json_extract(ev.data,'$.term_id')=c.term_id
      AND json_extract(ev.data,'$.starts_on')=c.starts_on
      AND json_extract(ev.data,'$.ends_on')=c.ends_on
      AND json_type(ev.data,'$.requirements')='array'
      AND EXISTS (SELECT 1 FROM json_each(ev.data,'$.requirements') q WHERE CASE WHEN q.type='object' THEN
        (SELECT count(*) FROM json_each(q.value))=4
        AND json_type(q.value,'$.id')='integer' AND json_type(q.value,'$.subject_id')='integer'
        AND json_type(q.value,'$.required_credential_id')='integer'
        AND json_extract(q.value,'$.id')=r.id AND json_extract(q.value,'$.subject_id')=r.subject_id
        AND json_extract(q.value,'$.required_credential_id')=r.required_credential_id
        AND json_type(q.value,'$.equivalent_ids')='array'
        AND json_array_length(q.value,'$.equivalent_ids')=(SELECT count(*) FROM schedules_subjectcredentialrequirement_acceptable_equivalents x WHERE x.subjectcredentialrequirement_id=r.id)
        AND NOT EXISTS(SELECT 1 FROM schedules_subjectcredentialrequirement_acceptable_equivalents x
           WHERE x.subjectcredentialrequirement_id=r.id AND NOT EXISTS(
             SELECT 1 FROM json_each(q.value,'$.equivalent_ids') v WHERE v.type='integer' AND v.value=x.credential_id))
        ELSE 0 END))"""


def credential_failures(held_sql, owners_sql):
    return f"""WITH held AS ({held_sql})
    SELECT c.schedule_id,c.faculty_id,c.uncertain FROM {VIEW} c WHERE
    c.uncertain=1 OR (c.faculty_id IN ({owners_sql}) AND EXISTS (
      SELECT 1 FROM schedules_subjectcredentialrequirement r WHERE r.subject_id=c.subject_id
      AND NOT EXISTS(SELECT 1 FROM held h WHERE h.faculty_id=c.faculty_id
        AND h.issued_on IS NOT NULL AND date(h.issued_on,'+0 days')=h.issued_on AND h.issued_on<=c.ends_on
        AND (h.expires_on IS NULL OR (date(h.expires_on,'+0 days')=h.expires_on AND h.expires_on>=c.ends_on))
        AND (h.credential_id=r.required_credential_id OR EXISTS (
          SELECT 1 FROM schedules_subjectcredentialrequirement_acceptable_equivalents x
          WHERE x.subjectcredentialrequirement_id=r.id AND x.credential_id=h.credential_id)))
      AND NOT ({scope_covers()})))"""


def availability_failures(periods_sql, owners_sql):
    # Reachability merges touching/overlapping AVAILABLE intervals without a
    # row-order assumption. A first explicit window changes the whole week.
    return f"""WITH RECURSIVE periods AS ({periods_sql}),
    commitments AS (SELECT * FROM {VIEW} WHERE faculty_id IN ({owners_sql})),
    reach(entry_id,finish) AS (
      SELECT entry_id,julianday('2000-01-01 '||start_time) FROM commitments
      UNION
      SELECT c.entry_id,julianday('2000-01-01 '||p.end_time)
      FROM reach r JOIN commitments c ON c.entry_id=r.entry_id
      JOIN periods p ON p.faculty_id=c.faculty_id AND p.day=c.day AND p.kind='AVAILABLE'
      WHERE julianday('2000-01-01 '||p.start_time)<=r.finish
        AND julianday('2000-01-01 '||p.end_time)>r.finish
    )
    SELECT schedule_id,faculty_id,uncertain FROM {VIEW} WHERE uncertain=1
    UNION
    SELECT c.schedule_id,c.faculty_id,0 FROM commitments c WHERE
      c.day NOT BETWEEN 0 AND 5 OR c.start_time<'07:00:00' OR c.end_time>'19:00:00'
      OR c.start_time>=c.end_time
      OR EXISTS(SELECT 1 FROM periods p WHERE p.faculty_id=c.faculty_id AND
        (p.kind NOT IN ('AVAILABLE','PREFERRED','UNAVAILABLE') OR p.day NOT BETWEEN 0 AND 6
         OR julianday('2000-01-01 '||p.start_time) IS NULL OR julianday('2000-01-01 '||p.end_time) IS NULL
         OR p.start_time>=p.end_time))
      OR EXISTS(SELECT 1 FROM periods p WHERE p.faculty_id=c.faculty_id AND p.day=c.day AND p.kind='UNAVAILABLE'
         AND julianday('2000-01-01 '||p.start_time)<julianday('2000-01-01 '||c.end_time)
         AND julianday('2000-01-01 '||p.end_time)>julianday('2000-01-01 '||c.start_time))
      OR (EXISTS(SELECT 1 FROM periods p WHERE p.faculty_id=c.faculty_id AND p.kind='AVAILABLE')
          AND NOT EXISTS(SELECT 1 FROM reach r WHERE r.entry_id=c.entry_id
                         AND r.finish>=julianday('2000-01-01 '||c.end_time)))"""


TRIGGERS = {}
for model, columns, query in (
    ('facultycredential', 'faculty_id credential_id issued_on expires_on', credential_failures),
    ('availability', 'faculty_id room_id section_id day start_time end_time kind', availability_failures),
):
    for event, owners in (('INSERT','SELECT NEW.faculty_id'), ('UPDATE','SELECT OLD.faculty_id UNION SELECT NEW.faculty_id'), ('DELETE','SELECT OLD.faculty_id')):
        changed = ' OR '.join(f'OLD.{x} IS NOT NEW.{x}' for x in columns.split())
        relevant = 'NEW.faculty_id IS NOT NULL' if event=='INSERT' else 'OLD.faculty_id IS NOT NULL'
        if event=='UPDATE': relevant = f'(OLD.faculty_id IS NOT NULL OR NEW.faculty_id IS NOT NULL) AND ({changed})'
        name=f'faculty_dependency_{model}_{event.lower()}'
        check=query(f'SELECT * FROM schedules_{model}', owners)
        TRIGGERS[name]=f"CREATE TRIGGER {name} AFTER {event} ON schedules_{model} WHEN {relevant} AND EXISTS({check}) BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"
    # REPLACE may silently delete a different row without firing DELETE guards.
    collision = 'prior.id=NEW.id'
    if model=='facultycredential': collision += ' OR (prior.faculty_id=NEW.faculty_id AND prior.credential_id=NEW.credential_id)'
    name=f'faculty_dependency_{model}_replace'
    TRIGGERS[name]=f"""CREATE TRIGGER {name} BEFORE INSERT ON schedules_{model}
    WHEN EXISTS(SELECT 1 FROM schedules_{model} prior WHERE ({collision}) AND prior.faculty_id IS NOT NULL
       AND EXISTS(SELECT 1 FROM {VIEW} c WHERE c.uncertain=1 OR c.faculty_id=prior.faculty_id))
    BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"""
    name=f'faculty_dependency_{model}_rekey'
    TRIGGERS[name]=f"""CREATE TRIGGER {name} BEFORE UPDATE ON schedules_{model}
    WHEN OLD.id IS NOT NEW.id AND EXISTS(SELECT 1 FROM schedules_{model} prior
      WHERE prior.id IN (OLD.id,NEW.id) AND prior.faculty_id IS NOT NULL
      AND EXISTS(SELECT 1 FROM {VIEW} c WHERE c.uncertain=1 OR c.faculty_id=prior.faculty_id))
    BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        raise RuntimeError('Faculty dependency guards require SQLite.')
    schema_editor.execute(VIEW_SQL)
    for sql in TRIGGERS.values(): schema_editor.execute(sql)


def backwards(apps, schema_editor):
    for name in TRIGGERS: schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')
    schema_editor.execute(f'DROP VIEW IF EXISTS {VIEW}')


class Migration(migrations.Migration):
    dependencies = [('schedules', '0029_credential_approval_scope')]
    operations = [migrations.RunPython(forwards, backwards)]
