"""Append-only SHS scope evidence; no legacy backfill or historical rewrite."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

FIELDS = {
    'curriculumversion': 'family revision education_level reference_title reference_url reference_notes verification_status is_active',
    'academicpathway': 'curriculum_version_id code kind parent_id',
    'cohort': 'school_year grade_level curriculum_version_id implementation_status pathway_id',
    'curriculumsubjectrequirement': 'curriculum_version_id subject_id pathway_id grade_level academic_period classification selection quantity unit measurement_basis reference_title reference_url reference_locator reference_notes verification_status is_active',
    'subjectoffering': 'requirement_id cohort_id academic_term_id academic_period is_approved',
    'deliveryplan': 'offering_id reference_title reference_notes approval_reference is_approved approved_by_id approved_at',
    'deliverycomponent': 'plan_id position instruction duration_minutes meeting_count',
    'shsassignmentconfiguration': 'assignment_id delivery_plan_id starts_on ends_on calendar_reference combined_class_reference is_confirmed',
    'shsmeetingpattern': 'configuration_id component_id sequence recurrence weekday meeting_date window_start window_end required_room_type room_id room_approval_reference',
    'facultycontactminutepolicy': 'faculty_id accounting_period covered_levels week_starts_on starts_on ends_on maximum_contact_minutes reference is_verified is_approved is_active',
    'shssectionparticipation': 'configuration_id section_id',
}

KEYS = {
    'curriculumversion': "schedease_identity_v1(v.family)=schedease_identity_v1(NEW.family) AND schedease_identity_v1(v.revision)=schedease_identity_v1(NEW.revision) AND v.education_level=NEW.education_level",
    'academicpathway': 'v.curriculum_version_id=NEW.curriculum_version_id AND schedease_identity_v1(v.code)=schedease_identity_v1(NEW.code)',
    'cohort': 'schedease_identity_v1(v.school_year)=schedease_identity_v1(NEW.school_year) AND v.grade_level=NEW.grade_level AND v.curriculum_version_id=NEW.curriculum_version_id AND v.pathway_id IS NEW.pathway_id',
    'curriculumsubjectrequirement': 'v.curriculum_version_id=NEW.curriculum_version_id AND v.subject_id=NEW.subject_id AND v.grade_level=NEW.grade_level AND schedease_identity_v1(v.academic_period)=schedease_identity_v1(NEW.academic_period) AND v.pathway_id IS NEW.pathway_id',
    'subjectoffering': 'v.requirement_id=NEW.requirement_id AND v.cohort_id=NEW.cohort_id AND v.academic_term_id=NEW.academic_term_id',
    'deliveryplan': 'v.offering_id=NEW.offering_id',
    'deliverycomponent': 'v.plan_id=NEW.plan_id AND v.position=NEW.position',
    'shsassignmentconfiguration': 'v.assignment_id=NEW.assignment_id',
    'shsmeetingpattern': 'v.configuration_id=NEW.configuration_id AND v.component_id=NEW.component_id AND v.sequence=NEW.sequence',
    'shssectionparticipation': 'v.configuration_id=NEW.configuration_id AND v.section_id=NEW.section_id',
    'facultycontactminutepolicy': '0',
}
VIEW = 'shs_operational_dependencies_v1'
MESSAGE = 'This change affects finalized SHS operational approvals, or historical approval scope is unproven. Keep the approved definitions and use a separately reviewed configuration.'

# Traverse both the immutable captured identities and current relationships.
# A later review never converts missing original evidence into proven history.
EDGES = [
    ('shsassignmentconfiguration', 'deliveryplan', 'delivery_plan_id'),
    ('shsmeetingpattern', 'shsassignmentconfiguration', 'configuration_id'),
    ('shsmeetingpattern', 'deliverycomponent', 'component_id'),
    ('deliverycomponent', 'deliveryplan', 'plan_id'),
    ('deliveryplan', 'subjectoffering', 'offering_id'),
    ('subjectoffering', 'curriculumsubjectrequirement', 'requirement_id'),
    ('subjectoffering', 'cohort', 'cohort_id'),
    ('curriculumsubjectrequirement', 'curriculumversion', 'curriculum_version_id'),
    ('curriculumsubjectrequirement', 'academicpathway', 'pathway_id'),
    ('cohort', 'curriculumversion', 'curriculum_version_id'),
    ('cohort', 'academicpathway', 'pathway_id'),
    ('academicpathway', 'academicpathway', 'parent_id'),
    ('academicpathway', 'curriculumversion', 'curriculum_version_id'),
]
edge_sql = ' UNION ALL '.join(f"SELECT '{a}' AS source_model,id AS source_id,'{b}' AS model,{column} AS record_id FROM schedules_{a} WHERE {column} IS NOT NULL" for a,b,column in EDGES)
VIEW_SQL = f"""CREATE VIEW {VIEW} AS WITH RECURSIVE
final AS (
 SELECT DISTINCT s.id AS schedule_id,s.term_id FROM schedules_schedule s
 JOIN schedules_academicterm t ON t.id=s.term_id WHERE s.status IN ('PUBLISHED','ARCHIVED')
 AND (t.education_level='SHS' OR EXISTS(SELECT 1 FROM schedules_scheduleentry e
 JOIN schedules_shsmeetingbinding b ON b.meeting_id=e.assignment_id WHERE e.schedule_id=s.id))
), evidence AS (
 SELECT f.schedule_id,a.kind,CASE WHEN json_valid(a.data) AND a.schema_version=1 THEN a.data ELSE '{{}}' END AS data
 FROM final f JOIN schedules_shsapprovalevidence a ON a.term_id=f.term_id
), roots(schedule_id,model,record_id) AS (
 SELECT f.schedule_id,'shsassignmentconfiguration',c.id FROM final f
 JOIN schedules_scheduleentry e ON e.schedule_id=f.schedule_id
 JOIN schedules_teachingassignment a ON a.id=e.assignment_id
 JOIN schedules_shsassignmentconfiguration c ON c.assignment_id=a.assignment_id
 UNION
 SELECT f.schedule_id,'shsmeetingpattern',b.pattern_id FROM final f
 JOIN schedules_scheduleentry e ON e.schedule_id=f.schedule_id JOIN schedules_shsmeetingbinding b ON b.meeting_id=e.assignment_id
 UNION
 SELECT p.schedule_id,'cohort',s.cohort_id FROM shs_finalized_participation_v1 p JOIN schedules_section s ON s.id=p.section_id
 UNION
 SELECT ev.schedule_id,json_extract(j.value,'$.model'),json_extract(j.value,'$.id')
 FROM evidence ev,json_each(CASE WHEN json_type(ev.data,'$.records')='array' THEN json_extract(ev.data,'$.records') ELSE '[]' END) j
 WHERE j.type='object'
 UNION
 SELECT f.schedule_id,k.value,json_extract(b.data,'$.'||k.key) FROM final f
 JOIN schedules_scheduleentry e ON e.schedule_id=f.schedule_id JOIN schedules_shsmeetingbinding b ON b.meeting_id=e.assignment_id,
 json_each('{{"configuration_id":"shsassignmentconfiguration","plan_id":"deliveryplan","component_id":"deliverycomponent"}}') k
 WHERE CASE WHEN json_valid(b.data) THEN json_type(b.data,'$.'||k.key)='integer' ELSE 0 END
), edges AS ({edge_sql}), tree(schedule_id,model,record_id) AS (
 SELECT * FROM roots WHERE record_id IS NOT NULL
 UNION SELECT t.schedule_id,e.model,e.record_id FROM tree t JOIN edges e ON e.source_model=t.model AND e.source_id=t.record_id
), unknown AS (
 SELECT f.schedule_id FROM final f WHERE
 EXISTS(SELECT 1 FROM shs_finalized_participation_v1 p WHERE p.schedule_id=f.schedule_id AND p.uncertain=1)
 OR EXISTS(SELECT 1 FROM finalized_resource_commitments_v1 p WHERE p.schedule_id=f.schedule_id AND p.uncertain=1)
 OR NOT EXISTS(SELECT 1 FROM schedules_scheduleentry WHERE schedule_id=f.schedule_id)
 OR EXISTS(SELECT 1 FROM schedules_scheduleentry e LEFT JOIN schedules_shsmeetingbinding b ON b.meeting_id=e.assignment_id
   WHERE e.schedule_id=f.schedule_id AND NOT EXISTS(
     SELECT 1 FROM evidence ev,json_each(CASE WHEN json_type(ev.data,'$.bindings')='array' THEN json_extract(ev.data,'$.bindings') ELSE '[]' END) j
     WHERE ev.schedule_id=f.schedule_id AND ev.kind='PREPARATION' AND j.type='object'
       AND json_type(ev.data,'$.records')='array' AND json_array_length(ev.data,'$.records')>0
       AND json_extract(ev.data,'$.term_id')=f.term_id
       AND EXISTS(SELECT 1 FROM json_each(ev.data,'$.records') r WHERE r.type='object' AND json_extract(r.value,'$.model')='curriculumversion')
       AND EXISTS(SELECT 1 FROM json_each(ev.data,'$.records') r WHERE r.type='object' AND json_extract(r.value,'$.model')='facultycontactminutepolicy')
       AND json_extract(j.value,'$.id')=b.id AND json_extract(j.value,'$.meeting_id')=b.meeting_id
       AND json_extract(j.value,'$.pattern_id')=b.pattern_id
       AND CASE WHEN json_valid(b.data) THEN json_extract(j.value,'$.stored_json')=b.data ELSE 0 END))
)
SELECT schedule_id,model,record_id,0 AS uncertain FROM tree
UNION SELECT schedule_id,'*',NULL,1 FROM unknown
"""


def dependency(model, key):
    return f"EXISTS(SELECT 1 FROM {VIEW} d WHERE d.uncertain=1 OR (d.model='{model}' AND d.record_id={key}))"


def destination(model, alias):
    parents = {'deliverycomponent': ('deliveryplan','plan_id'), 'shsmeetingpattern': ('shsassignmentconfiguration','configuration_id'),
               'shssectionparticipation': ('shsassignmentconfiguration','configuration_id')}
    if model in parents:
        parent, column = parents[model]
        return dependency(parent, f'{alias}.{column}')
    if model == 'facultycontactminutepolicy':
        return f"""({alias}.is_active=1 AND EXISTS(SELECT 1 FROM {VIEW} d
          LEFT JOIN schedules_facultycontactminutepolicy p ON d.model='facultycontactminutepolicy' AND p.id=d.record_id
          WHERE d.uncertain=1 OR (p.is_active=1 AND p.faculty_id={alias}.faculty_id
          AND p.starts_on<={alias}.ends_on AND p.ends_on>={alias}.starts_on)))"""
    return '0'


TRIGGERS = {
    'shs_scope_insert': """CREATE TRIGGER shs_scope_insert BEFORE INSERT ON schedules_shsapprovalevidence
      WHEN NEW.schema_version<>1 OR NEW.kind NOT IN ('PREPARATION','CURRENT_REVIEW')
      OR schedease_shs_scope_v1(NEW.term_id,NEW.actor_id,NEW.kind,NEW.reason,NEW.data)<>1
      OR NOT (julianday(NEW.created_at)=julianday(json_extract(NEW.data,'$.reviewed_at')))
      OR EXISTS(SELECT 1 FROM schedules_shsapprovalevidence WHERE id=NEW.id)
      BEGIN SELECT RAISE(ABORT,'Use the authorized SHS approval review workflow.'); END""",
    'shs_scope_update': "CREATE TRIGGER shs_scope_update BEFORE UPDATE ON schedules_shsapprovalevidence BEGIN SELECT RAISE(ABORT,'SHS approval evidence is immutable.'); END",
    'shs_scope_delete': "CREATE TRIGGER shs_scope_delete BEFORE DELETE ON schedules_shsapprovalevidence BEGIN SELECT RAISE(ABORT,'SHS approval evidence cannot be deleted.'); END",
    'shs_binding_identity': "CREATE TRIGGER shs_binding_identity BEFORE UPDATE ON schedules_shsmeetingbinding WHEN OLD.id IS NOT NEW.id BEGIN SELECT RAISE(ABORT,'SHS binding identity is immutable.'); END",
}
for model, fields in FIELDS.items():
    collision = f"EXISTS(SELECT 1 FROM schedules_{model} v WHERE (v.id=NEW.id OR ({KEYS[model]})) AND ({dependency(model,'v.id')}))"
    for event, condition in (
        ('INSERT', f'({collision}) OR ({destination(model,"NEW")})'),
        ('DELETE', f'({dependency(model,"OLD.id")}) OR ({destination(model,"OLD")})'),
        ('UPDATE', '('+' OR '.join(f'OLD.{field} IS NOT NEW.{field}' for field in ['id',*fields.split()])+') AND ('+
         f'{dependency(model,"OLD.id")} OR {destination(model,"OLD")} OR {destination(model,"NEW")} OR '+
         f"EXISTS(SELECT 1 FROM schedules_{model} v WHERE v.id<>OLD.id AND (v.id=NEW.id OR ({KEYS[model]})) AND ({dependency(model,'v.id')})))"),
    ):
        name=f'shs_scope_{model}_{event.lower()}'
        TRIGGERS[name]=f"CREATE TRIGGER {name} BEFORE {event} ON schedules_{model} WHEN {condition} BEGIN SELECT RAISE(ABORT,'{MESSAGE}'); END"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        raise RuntimeError('SHS approval scope requires SQLite.')
    schema_editor.execute(VIEW_SQL)
    for sql in TRIGGERS.values(): schema_editor.execute(sql)


def backwards(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT 1 FROM schedules_shsapprovalevidence LIMIT 1')
        if cursor.fetchone():
            raise RuntimeError('Cannot reverse 0033 while SHS approval evidence exists. Preserve the approval history.')
    for name in TRIGGERS: schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')
    schema_editor.execute(f'DROP VIEW IF EXISTS {VIEW}')


class Migration(migrations.Migration):
    dependencies = [('schedules','0032_resource_availability_guards'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='SHSApprovalEvidence',fields=[
        ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
        ('schema_version',models.PositiveSmallIntegerField(default=1)),
        ('kind',models.CharField(max_length=20,choices=[('PREPARATION','New preparation'),('CURRENT_REVIEW','Current validity review')])),
        ('reason',models.TextField()),('data',models.JSONField()),
        ('created_at',models.DateTimeField(default=django.utils.timezone.now,editable=False)),
        ('term',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='schedules.academicterm')),
        ('actor',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
    ]),migrations.RunPython(forwards,backwards)]
