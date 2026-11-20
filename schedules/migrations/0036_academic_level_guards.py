"""Reject cross-level academic relationships, including bulk and raw SQL writes.

No data repair, policy inference, or changes to existing historical guards.
"""
from django.db import migrations

INVALID = """
EXISTS (SELECT 1 FROM schedules_program WHERE education_level NOT IN ('SHS','TERTIARY'))
OR EXISTS (SELECT 1 FROM schedules_academicterm WHERE education_level NOT IN ('SHS','TERTIARY'))
OR EXISTS (SELECT 1 FROM schedules_assignment a
 JOIN schedules_academicterm t ON t.id=a.term_id
 JOIN schedules_section s ON s.id=a.section_id JOIN schedules_program p ON p.id=s.program_id
 WHERE t.education_level<>p.education_level)
OR EXISTS (SELECT 1 FROM schedules_teachingassignment a
 JOIN schedules_academicterm t ON t.id=a.term_id
 JOIN schedules_section s ON s.id=a.section_id JOIN schedules_program p ON p.id=s.program_id
 WHERE t.education_level<>p.education_level)
OR EXISTS (SELECT 1 FROM schedules_section s
 JOIN schedules_program p ON p.id=s.program_id JOIN schedules_cohort c ON c.id=s.cohort_id
 JOIN schedules_yearlevel y ON y.id=s.year_level_id
 WHERE p.education_level<>'SHS' OR y.level<>c.grade_level)
OR EXISTS (SELECT 1 FROM schedules_cohort c
 JOIN schedules_curriculumversion v ON v.id=c.curriculum_version_id
 LEFT JOIN schedules_academicpathway p ON p.id=c.pathway_id
 WHERE v.education_level<>'SHS' OR (c.pathway_id IS NOT NULL AND p.curriculum_version_id<>c.curriculum_version_id))
OR EXISTS (SELECT 1 FROM schedules_academicpathway p
 JOIN schedules_academicpathway parent ON parent.id=p.parent_id
 WHERE p.curriculum_version_id<>parent.curriculum_version_id)
OR EXISTS (SELECT 1 FROM schedules_curriculumsubjectrequirement r
 JOIN schedules_curriculumversion v ON v.id=r.curriculum_version_id
 LEFT JOIN schedules_academicpathway p ON p.id=r.pathway_id
 WHERE v.education_level<>'SHS' OR (r.pathway_id IS NOT NULL AND p.curriculum_version_id<>r.curriculum_version_id))
OR EXISTS (SELECT 1 FROM schedules_subjectoffering o
 JOIN schedules_curriculumsubjectrequirement r ON r.id=o.requirement_id
 JOIN schedules_cohort c ON c.id=o.cohort_id
 JOIN schedules_academicterm t ON t.id=o.academic_term_id
 WHERE t.education_level<>'SHS' OR r.curriculum_version_id<>c.curriculum_version_id
 OR r.grade_level<>c.grade_level OR (r.pathway_id IS NOT NULL AND r.pathway_id IS NOT c.pathway_id)
 OR schedease_identity_v1(t.school_year)<>schedease_identity_v1(c.school_year)
 OR schedease_identity_v1(o.academic_period)<>schedease_identity_v1(r.academic_period))
OR EXISTS (SELECT 1 FROM schedules_shsassignmentconfiguration c
 JOIN schedules_assignment a ON a.id=c.assignment_id
 JOIN schedules_section s ON s.id=a.section_id
 JOIN schedules_deliveryplan p ON p.id=c.delivery_plan_id
 JOIN schedules_subjectoffering o ON o.id=p.offering_id
 JOIN schedules_curriculumsubjectrequirement r ON r.id=o.requirement_id
 WHERE a.term_id<>o.academic_term_id OR a.subject_id<>r.subject_id OR s.cohort_id IS NOT o.cohort_id)
OR EXISTS (SELECT 1 FROM schedules_shssectionparticipation x
 JOIN schedules_shsassignmentconfiguration c ON c.id=x.configuration_id
 JOIN schedules_deliveryplan p ON p.id=c.delivery_plan_id
 JOIN schedules_subjectoffering o ON o.id=p.offering_id
 JOIN schedules_section s ON s.id=x.section_id WHERE s.cohort_id IS NOT o.cohort_id)
OR EXISTS (SELECT 1 FROM schedules_shsmeetingpattern p
 JOIN schedules_shsassignmentconfiguration c ON c.id=p.configuration_id
 JOIN schedules_deliverycomponent d ON d.id=p.component_id WHERE d.plan_id<>c.delivery_plan_id)
"""
TABLES = ('assignment', 'teachingassignment', 'academicterm', 'section', 'program',
          'yearlevel', 'cohort', 'curriculumversion', 'academicpathway',
          'curriculumsubjectrequirement', 'subjectoffering', 'shsassignmentconfiguration',
          'shssectionparticipation', 'deliveryplan', 'deliverycomponent', 'shsmeetingpattern')


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        raise RuntimeError('Academic relationship guards require SQLite.')
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT ' + INVALID)
        if cursor.fetchone()[0]:
            raise RuntimeError('Existing incompatible academic relationships require review; no automatic repair was made.')
        for table in TABLES:
            for event in ('INSERT', 'UPDATE'):
                cursor.execute(f'''CREATE TRIGGER academic_level_{table}_{event.lower()}
                    AFTER {event} ON schedules_{table} WHEN {INVALID}
                    BEGIN SELECT RAISE(ABORT, 'Academic level or curriculum relationships are incompatible.'); END''')


def reverse(apps, schema_editor):
    for table in TABLES:
        for event in ('insert', 'update'):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS academic_level_{table}_{event}')


class Migration(migrations.Migration):
    dependencies = [('schedules', '0035_schedule_notifications')]
    operations = [migrations.RunPython(forward, reverse)]
