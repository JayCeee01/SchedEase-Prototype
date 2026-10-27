from datetime import date, time
from types import SimpleNamespace
import os
import subprocess
import sys

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from . import models as m
from . import test_shs_migrations as migration_tests
from .services.scheduling_requirements import resolve_shs
from .services.ga import GeneticScheduler
from .services.diagnostics import GenerationFailure


class OperationalInputTests(TestCase):
    def setUp(self):
        version=m.CurriculumVersion.objects.create(family='Synthetic',revision='1',reference_title='Test source',verification_status='VERIFIED',is_active=True)
        cohort=m.Cohort.objects.create(curriculum_version=version,school_year='2026-2027',grade_level=11)
        self.department=m.Department.objects.create(code='SYN',name='Synthetic')
        self.program=m.Program.objects.create(department=self.department,code='SHS',name='Synthetic SHS',education_level='SHS')
        self.year=m.YearLevel.objects.create(level=11,label='Grade 11')
        self.section=m.Section.objects.create(program=self.program,year_level=self.year,name='A',size=20,cohort=cohort)
        self.faculty=m.Faculty.objects.create(department=self.department,employee_id='SYN1',full_name='Synthetic faculty')
        self.subject=m.Subject.objects.create(department=self.department,code='SYN1',title='Synthetic',lecture_hours=3)
        self.term=m.AcademicTerm.objects.create(name='Synthetic',school_year='2026-2027',starts_on=date(2026,8,1),ends_on=date(2026,12,1),education_level='SHS')
        self.requirement=m.CurriculumSubjectRequirement.objects.create(curriculum_version=version,subject=self.subject,grade_level=11,academic_period='Period 1',classification='Synthetic',quantity=2,unit='HOURS',measurement_basis='PERIOD',reference_title='Test source',verification_status='VERIFIED',is_active=True)
        offering=m.SubjectOffering.objects.create(requirement=self.requirement,cohort=cohort,academic_term=self.term,academic_period='Period 1',is_approved=True)
        self.plan=m.DeliveryPlan.objects.create(offering=offering,reference_title='Test source',approval_reference='Test approval')
        self.component=m.DeliveryComponent.objects.create(plan=self.plan,instruction='Guided work',duration_minutes=60,meeting_count=2)
        self.plan.is_approved=True
        self.plan.save()
        self.assignment=m.Assignment.objects.create(term=self.term,subject=self.subject,faculty=self.faculty,section=self.section)
        self.config=m.SHSAssignmentConfiguration.objects.create(assignment=self.assignment,delivery_plan=self.plan,starts_on=date(2026,8,3),ends_on=date(2026,8,10),calendar_reference='Synthetic calendar approval')
        self.room=m.Room.objects.create(name='Synthetic room',capacity=40,room_type='LECTURE')

    def pattern(self, **changes):
        values=dict(configuration=self.config,component=self.component,sequence=1,recurrence='WEEKLY',weekday=0,window_start=time(8),window_end=time(10),required_room_type='LECTURE',room=self.room,room_approval_reference='Synthetic room approval')
        values.update(changes)
        return m.SHSMeetingPattern.objects.create(**values)

    def confirm(self):
        self.config.is_confirmed=True
        self.config.save()

    def test_operational_resolution_retains_workload_and_generation_blocks(self):
        self.pattern()
        self.confirm()
        result=resolve_shs(self.plan.pk,assignment_id=self.assignment.pk)
        self.assertEqual(result.faculty_id,self.faculty.pk)
        self.assertEqual(result.section_ids,(self.section.pk,))
        self.assertEqual(result.meeting_patterns[0].minutes,60)
        self.assertEqual(result.meeting_patterns[0].room_ids,(self.room.pk,))
        self.assertTrue(any('policy' in message for message in result.blockers))
        self.assertIsNone(result.weekly_limit_minutes)
        with self.assertRaises(ValidationError): result.require_schedulable()
        with self.assertRaises(GenerationFailure): GeneticScheduler(self.term,m.GASettings())
        self.assertFalse(m.TeachingAssignment.objects.exists())
        self.assertEqual(self.subject.lecture_hours,3)

    def test_combined_sections_need_approval_and_adequate_capacity(self):
        extra=m.Section.objects.create(program=self.program,year_level=self.year,name='B',size=30,cohort=self.section.cohort)
        with self.assertRaises(ValidationError): m.SHSSectionParticipation.objects.create(configuration=self.config,section=extra)
        self.config.combined_class_reference='Synthetic combined-class approval'
        self.config.save()
        m.SHSSectionParticipation.objects.create(configuration=self.config,section=extra)
        with self.assertRaises(ValidationError): self.pattern()
        self.room.capacity=50
        self.room.save()
        self.pattern()
        self.confirm()
        self.assertEqual(len(resolve_shs(self.plan.pk).section_ids),2)
        with self.assertRaises(ValidationError): m.SHSSectionParticipation.objects.create(configuration=self.config,section=extra)
        with self.assertRaises(ValidationError): m.SHSSectionParticipation.objects.create(configuration=self.config,section=self.section)

    def test_dates_recurrence_counts_and_windows(self):
        for changes in ({'window_end':time(8,30)},{'window_start':time(6)}, {'recurrence':'DATED','meeting_date':date(2026,8,4),'weekday':0}, {'recurrence':'DATED','meeting_date':date(2026,9,1),'weekday':1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError): self.pattern(**changes)
        self.pattern(weekday=1)
        with self.assertRaises(ValidationError): self.confirm()
        self.config.is_confirmed=False
        self.config.starts_on=date(2026,7,1)
        with self.assertRaises(ValidationError): self.config.save()

    def test_explicit_dated_period_meetings(self):
        self.pattern(recurrence='DATED',meeting_date=date(2026,8,3))
        self.pattern(sequence=2,recurrence='DATED',weekday=1,meeting_date=date(2026,8,4))
        self.confirm()

    def test_weekly_requirement_counts_patterns_not_calendar_weeks(self):
        # Test-only bypass to change the synthetic source without rebuilding fixtures.
        m.CurriculumSubjectRequirement.objects.filter(pk=self.requirement.pk).update(measurement_basis='WEEK')
        self.pattern()
        with self.assertRaises(ValidationError): self.confirm()
        self.config.is_confirmed=False
        self.pattern(sequence=2,weekday=1)
        self.confirm()

    def test_draft_and_unapproved_parent_are_blocked(self):
        self.config.starts_on=None
        self.config.calendar_reference=''
        self.config.save()
        with self.assertRaises(ValidationError): self.confirm()
        self.config.refresh_from_db()
        self.config.starts_on=date(2026,8,3)
        self.config.calendar_reference='Synthetic approval'
        self.config.save()
        self.pattern()
        self.plan.is_approved=False
        self.plan.save()
        with self.assertRaises(ValidationError): self.confirm()

    def test_identity_room_and_duplicates(self):
        with self.assertRaises(ValidationError): self.pattern(required_room_type='SCIENCE_LAB')
        self.pattern()
        with self.assertRaises(ValidationError): self.pattern()
        with self.assertRaises(ValidationError): m.SHSAssignmentConfiguration.objects.create(assignment=self.assignment,delivery_plan=self.plan)
        self.assignment.term=m.AcademicTerm.objects.create(name='Other',school_year='2026-2027',starts_on=date(2026,8,1),ends_on=date(2026,12,1))
        self.assignment.save()
        self.config.refresh_from_db()
        with self.assertRaises(ValidationError): self.config.full_clean()

    def test_admin_permissions(self):
        user=User.objects.create_user(username='faculty',is_staff=True)
        m.Profile.objects.create(user=user,role='FACULTY')
        for model in (m.SHSAssignmentConfiguration,m.SHSMeetingPattern,m.SHSSectionParticipation):
            self.assertFalse(admin.site._registry[model].has_add_permission(SimpleNamespace(user=user)))


class OperationalMigrationTests(migration_tests.SHSMigrationTests):
    def rehearse(self,populated):
        script=migration_tests.REHEARSAL.replace('0020_normalized_identity_uniqueness','0023_shs_delivery_plans').replace('0021_shs_academic_identity','0024_shs_operational_inputs').replace('len(triggers) + 3','len(triggers)')
        env=os.environ.copy()
        env['SHS_MIGRATION_POPULATED']=str(int(populated))
        result=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
