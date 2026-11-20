from importlib import import_module
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from . import models as m
from . import test_known_defects as fixtures


class AcademicCrudTests(fixtures.SchedulingDefectFixture):
    def setUp(self):
        from django.contrib.auth.models import User
        self.admin=User.objects.create_superuser('crud-admin')
        self.client.force_login(self.admin)
        self.program=m.Program.objects.create(code='CRUD-SHS',name='SHS',education_level='SHS',department=self.department)
        year=m.YearLevel.objects.create(level=11,label='Grade 11')
        self.shs_section=m.Section.objects.create(program=self.program,year_level=year,name='A',size=20)
        self.shs_term=m.AcademicTerm.objects.create(name='SHS',school_year=self.term.school_year,
            starts_on=self.term.starts_on,ends_on=self.term.ends_on,education_level='SHS')

    def test_valid_levels_share_faculty_subject_and_room(self):
        assignment=m.Assignment.objects.create(term=self.shs_term,section=self.shs_section,
            subject=self.subject,faculty=self.faculty)
        self.assertEqual(assignment.faculty_id,self.parent.faculty_id)
        self.assertEqual(assignment.subject_id,self.parent.subject_id)
        self.assertEqual(m.Room.objects.count(),1)

    def test_model_and_bulk_reject_mismatch(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.AcademicTerm.objects.filter(pk=self.shs_term.pk).update(education_level='OTHER')
        for term,section in [(self.term,self.shs_section),(self.shs_term,self.section)]:
            with self.assertRaises(ValidationError):
                m.Assignment.objects.create(term=term,section=section,faculty=self.faculty,subject=self.subject)
            with self.assertRaises(IntegrityError),transaction.atomic():
                m.Assignment.objects.bulk_create([m.Assignment(term=term,section=section,
                    faculty=self.faculty,subject=self.subject)])

    def test_parent_changes_reject_dependent_mismatch(self):
        for obj,field,value in [(self.term,'education_level','SHS'),
                                (self.section.program,'education_level','SHS'),
                                (self.section,'program_id',self.program.pk)]:
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(IntegrityError),transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(**{field:value})
                setattr(obj,field,value)
                with self.assertRaises(ValidationError): obj.full_clean()
                obj.refresh_from_db()

    def test_form_context_and_deletion_reject_wrong_level(self):
        for action in ('resource_update','resource_delete'):
            response=self.client.post(reverse(action,args=['sections',self.section.pk]),{'education_level':'SHS'})
            self.assertEqual(response.status_code,404)
        response=self.client.get(reverse('resource_create',args=['sections']),{'education_level':'SHS'})
        self.assertEqual(set(response.context['form'].fields['program'].queryset.values_list('education_level',flat=True)),{'SHS'})
        self.assertContains(response,'name="education_level" value="SHS"')

    def test_legacy_program_form_uses_explicit_creation_level(self):
        response=self.client.post(reverse('resource_create',args=['programs']),
            {'education_level':'SHS','department':self.department.pk,'code':'CRUD-NEW','name':'New SHS'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(m.Program.objects.get(code='CRUD-NEW').education_level,'SHS')

    def test_offering_and_admin_context(self):
        version=m.CurriculumVersion.objects.create(family='Offering scope',revision='1')
        cohort=m.Cohort.objects.create(curriculum_version=version,school_year='2026-2027',grade_level=11)
        requirement=m.CurriculumSubjectRequirement.objects.create(curriculum_version=version,
            subject=self.subject,grade_level=11,academic_period='Period 1',classification='Test',
            quantity=60,unit='MINUTES',measurement_basis='PERIOD')
        offering=m.SubjectOffering.objects.create(requirement=requirement,cohort=cohort,
            academic_term=self.shs_term,academic_period='Period 1')
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.SubjectOffering.objects.filter(pk=offering.pk).update(academic_term=self.term)
        offering.academic_term=self.term
        with self.assertRaises(ValidationError): offering.full_clean()
        response=self.client.get(reverse('admin:schedules_section_change',args=[self.section.pk]),
            {'education_level':'SHS'})
        self.assertEqual(response.status_code,404)

    def test_replacement_and_curriculum_bulk_changes_rejected(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE schedules_assignment SET section_id=%s WHERE id=%s',
                               [self.shs_section.pk,self.parent.pk])
        # Replacing the referenced primary key must also check dependents.
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('INSERT OR REPLACE INTO schedules_program (id,code,name,department_id,education_level) VALUES (%s,%s,%s,%s,%s)',
                    [self.section.program_id,self.section.program.code,'Replacement',self.department.pk,'SHS'])
        version=m.CurriculumVersion.objects.create(family='CRUD',revision='1')
        cohort=m.Cohort.objects.create(curriculum_version=version,school_year='2026-2027',grade_level=11)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.CurriculumVersion.objects.filter(pk=version.pk).update(education_level='TERTIARY')
        self.shs_section.cohort=cohort
        self.shs_section.save()
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.Cohort.objects.filter(pk=cohort.pk).update(grade_level=12)

    def test_migration_trigger_reverse_forward_preserves_other_guards(self):
        migration=import_module('schedules.migrations.0036_academic_level_guards')
        # Execute only this migration's trigger DDL in the test transaction.
        # schema_editor(atomic=False) avoids changing FK settings inside TestCase.
        editor=connection.schema_editor(atomic=False)
        with connection.cursor() as cursor:
            before={r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        migration.reverse(None,editor)
        with connection.cursor() as cursor:
            middle={r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertEqual(before-middle,{f'academic_level_{table}_{event}' for table in migration.TABLES for event in ('insert','update')})
        migration.forward(None,editor)
        with connection.cursor() as cursor:
            after={r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertEqual(before,after)
        with connection.cursor() as cursor:
            self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
