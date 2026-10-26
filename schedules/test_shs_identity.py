"""Academic identities only: no SHS scheduling policy or curriculum seeding."""
from datetime import time

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from . import models as m
from .forms import MODEL_FORMS
from .test_known_defects import SchedulingDefectFixture


class AcademicIdentityTests(TestCase):
    def setUp(self):
        self.version = m.CurriculumVersion.objects.create(family="Example", revision="R1")
        self.other = m.CurriculumVersion.objects.create(family="Example", revision="R2")
        self.pathway = m.AcademicPathway.objects.create(curriculum_version=self.version, code="A", name="Example pathway", kind="TRACK")

    def cohort(self, **changes):
        values = dict(school_year="2026-2027", grade_level=11, curriculum_version=self.version)
        values.update(changes)
        return m.Cohort(**values)

    def test_inactive_default_and_verified_activation(self):
        self.assertFalse(self.version.is_active)
        self.version.is_active = True
        with self.assertRaises(ValidationError):
            self.version.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.CurriculumVersion.objects.filter(pk=self.version.pk).update(is_active=True)
        self.version.verification_status = "VERIFIED"
        with self.assertRaises(ValidationError):
            self.version.save()
        self.version.reference_title = "Synthetic verification reference"
        self.version.save()

    def test_grade_identities_and_database_grade_constraint(self):
        for grade in (11, 12):
            self.cohort(grade_level=grade).save()
        with self.assertRaises(ValidationError):
            self.cohort(grade_level=10).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Cohort.objects.update(grade_level=10)

    def test_normalized_uniqueness_including_null_pathway(self):
        self.cohort().save()
        with self.assertRaises(ValidationError):
            self.cohort(school_year=" 2026-2027 ").save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Cohort.objects.bulk_create([self.cohort()])
        self.cohort(pathway=self.pathway).save()
        with self.assertRaises(ValidationError):
            self.cohort(pathway=self.pathway).save()
        with self.assertRaises(ValidationError):
            m.CurriculumVersion.objects.create(family=" example ", revision="r1")
        with self.assertRaises(ValidationError):
            m.AcademicPathway.objects.create(curriculum_version=self.version, code=" a ", name="Another", kind="STRAND")
        m.AcademicPathway.objects.create(curriculum_version=self.other, code="A", name="Another", kind="ELECTIVE_CLUSTER")

    def test_curriculum_pathway_consistency_and_cycles(self):
        with self.assertRaises(ValidationError):
            self.cohort(curriculum_version=self.other, pathway=self.pathway).save()
        tertiary = m.CurriculumVersion.objects.create(family="Tertiary", revision="1", education_level="TERTIARY")
        with self.assertRaises(ValidationError):
            self.cohort(curriculum_version=tertiary).save()
        child = m.AcademicPathway(curriculum_version=self.other, code="B", name="Child", kind="STRAND", parent=self.pathway)
        with self.assertRaises(ValidationError):
            child.save()
        child.curriculum_version = self.version
        child.save()
        self.pathway.parent = child
        with self.assertRaises(ValidationError):
            self.pathway.save()

    def test_section_relationships_and_used_identity_changes(self):
        department = m.Department.objects.create(code="TEST", name="Test")
        program = m.Program.objects.create(department=department, code="SHS", name="SHS", education_level="SHS")
        year = m.YearLevel.objects.create(level=11, label="Grade 11")
        cohort = self.cohort(pathway=self.pathway)
        cohort.save()
        section = m.Section.objects.create(program=program, year_level=year, name="A", cohort=cohort)
        section.full_clean()
        program.education_level = "TERTIARY"
        with self.assertRaises(ValidationError):
            program.full_clean()
        with self.assertRaises(ValidationError):
            m.Section(program=program, year_level=year, name="B", cohort=cohort).full_clean()
        section.year_level = m.YearLevel.objects.create(level=12, label="Grade 12")
        with self.assertRaises(ValidationError):
            section.save()
        cohort.grade_level = 12
        with self.assertRaises(ValidationError):
            cohort.save()
        self.version.revision = "Changed"
        with self.assertRaises(ValidationError):
            self.version.save()
        self.pathway.curriculum_version = self.other
        with self.assertRaises(ValidationError):
            self.pathway.save()

    def test_admin_registration_and_role_gate(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="faculty", is_staff=True)
        m.Profile.objects.create(user=user, role=m.Role.FACULTY)
        for model in (m.CurriculumVersion, m.AcademicPathway, m.Cohort):
            self.assertIn(model, admin.site._registry)
            self.assertFalse(admin.site._registry[model].has_add_permission(SimpleNamespace(user=user)))


class TertiaryIdentityCompatibilityTests(SchedulingDefectFixture):
    def test_legacy_defaults_and_forms(self):
        self.assertEqual(self.section.program.education_level, "TERTIARY")
        self.assertIsNone(self.section.cohort_id)
        self.assertEqual(self.term.education_level, "TERTIARY")
        self.assertEqual(self.term.calendar_context, "")
        form = MODEL_FORMS['programs'](data={'department':self.department.pk, 'code':'NEW', 'name':'New program'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().education_level, "TERTIARY")
        self.assertEqual(set(self.scheduler().assignment_map), {x.pk for x in self.meetings})

    def test_finalized_identity_changes_blocked_even_by_queryset(self):
        schedule = m.Schedule.objects.create(term=self.term, name="Final")
        schedule.entries.create(assignment=self.meetings[0], room=self.room, day=0, start_time=time(8), end_time=time(9))
        schedule.status = m.ScheduleStatus.PUBLISHED
        schedule.save(update_fields=['status'])
        for obj, change in [(self.section.program, {'education_level':'SHS'}), (self.term, {'calendar_context':'Changed'}), (self.term, {'education_level':'SHS'})]:
            with self.subTest(change=change):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(**change)
                for key, value in change.items():
                    setattr(obj, key, value)
                with self.assertRaises(ValidationError):
                    obj.save()
