from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from . import models as m
from . import test_shs_migrations as migration_tests
import os
import subprocess
import sys


class CurriculumConfigurationTests(TestCase):
    def setUp(self):
        self.version = m.CurriculumVersion.objects.create(family="Synthetic", revision="1", verification_status="VERIFIED", reference_title="Test reference", is_active=True)
        self.cohort = m.Cohort.objects.create(school_year="2026-2027", grade_level=11, curriculum_version=self.version)
        dept = m.Department.objects.create(code="TEST", name="Test")
        self.subject = m.Subject.objects.create(department=dept, code="TEST", title="Test", lecture_hours=3)
        self.term = m.AcademicTerm.objects.create(name="Test term", school_year="2026-2027", starts_on=date(2026,8,1), ends_on=date(2026,12,1), education_level="SHS")
        self.requirement = m.CurriculumSubjectRequirement.objects.create(curriculum_version=self.version, subject=self.subject, grade_level=11, academic_period="Semester 1", classification="Source-specific", quantity=80, unit="HOURS", measurement_basis="PERIOD", reference_title="Test reference", verification_status="VERIFIED", is_active=True)

    def offering(self, **changes):
        values=dict(requirement=self.requirement, cohort=self.cohort, academic_term=self.term, academic_period="Semester 1")
        values.update(changes)
        return m.SubjectOffering(**values)

    def test_approved_and_draft_configuration(self):
        offering=self.offering()
        offering.save()
        self.assertFalse(offering.approved_for_configuration)
        offering.is_approved=True
        offering.save()
        self.assertTrue(offering.approved_for_configuration)
        self.version.is_active=False
        self.version.save()
        self.assertFalse(offering.approved_for_configuration)
        with self.assertRaises(ValidationError):
            offering.save()

    def test_unverified_requirement_cannot_be_approved(self):
        self.requirement.is_active=False
        self.requirement.verification_status="UNVERIFIED"
        self.requirement.save()
        with self.assertRaises(ValidationError):
            self.offering(is_approved=True).save()
        self.offering().save()

    def test_invalid_cohort_period_and_term(self):
        for field,value in [('grade_level',12),('school_year','2027-2028')]:
            original=getattr(self.cohort,field)
            setattr(self.cohort,field,value)
            self.cohort.save()
            with self.assertRaises(ValidationError):
                self.offering().save()
            setattr(self.cohort,field,original)
            self.cohort.save()
        with self.assertRaises(ValidationError):
            self.offering(academic_period="Semester 2").save()
        self.term.education_level="TERTIARY"
        self.term.save()
        with self.assertRaises(ValidationError):
            self.offering().save()

    def test_pathway_and_version_mismatch(self):
        other=m.CurriculumVersion.objects.create(family="Other",revision="1")
        pathway=m.AcademicPathway.objects.create(curriculum_version=other, code="X", name="X", kind="ELECTIVE_CLUSTER")
        self.requirement.pathway=pathway
        with self.assertRaises(ValidationError):
            self.requirement.save()
        pathway.curriculum_version=self.version
        pathway.save()
        self.requirement.pathway=pathway
        self.requirement.save()
        with self.assertRaises(ValidationError):
            self.offering().save()
        self.cohort.pathway=pathway
        self.cohort.save()
        self.offering().save()

    def test_quantity_basis_and_tertiary_hours_independent(self):
        self.requirement.quantity=Decimal('1.50')
        self.requirement.measurement_basis="WEEK"
        self.requirement.save()
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.lecture_hours,3)
        for field,value in [('quantity',0),('unit','UNKNOWN'),('measurement_basis','UNKNOWN')]:
            original=getattr(self.requirement,field)
            setattr(self.requirement,field,value)
            with self.assertRaises(ValidationError):
                self.requirement.save()
            setattr(self.requirement,field,original)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.CurriculumSubjectRequirement.objects.update(quantity=0)

    def test_duplicate_and_used_requirement_protection(self):
        self.offering().save()
        with self.assertRaises(ValidationError):
            self.offering().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.SubjectOffering.objects.bulk_create([self.offering()])
        self.requirement.quantity=81
        with self.assertRaises(ValidationError):
            self.requirement.save()

        self.requirement.pk=None
        self.requirement.academic_period=" semester 1 "
        with self.assertRaises(ValidationError):
            self.requirement.save()

    def test_admin_role_gate_and_effective_approval(self):
        from django.contrib import admin
        from django.contrib.auth.models import User
        from types import SimpleNamespace
        user=User.objects.create_user(username="test-faculty", is_staff=True)
        m.Profile.objects.create(user=user, role="FACULTY")
        for model in (m.CurriculumSubjectRequirement, m.SubjectOffering):
            self.assertFalse(admin.site._registry[model].has_add_permission(SimpleNamespace(user=user)))
        self.assertTrue(admin.site._registry[m.CurriculumSubjectRequirement].effective_approval(self.requirement))
        self.version.is_active=False
        self.version.save()
        self.assertFalse(admin.site._registry[m.CurriculumSubjectRequirement].effective_approval(self.requirement))


class CurriculumMigrationTests(migration_tests.SHSMigrationTests):
    def rehearse(self, populated):
        # Reuse the existing independent-process rehearsal and historical fixture.
        script=migration_tests.REHEARSAL.replace("0020_normalized_identity_uniqueness", "0021_shs_academic_identity").replace("0021_shs_academic_identity')]\nexecutor", "0022_shs_curriculum_configuration')]\nexecutor").replace('len(triggers) + 3','len(triggers)')
        env=os.environ.copy()
        env['SHS_MIGRATION_POPULATED']=str(int(populated))
        result=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
