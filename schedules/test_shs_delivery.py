"""Delivery configuration only; no generated schedules or curriculum seed data."""
import os
import subprocess
import sys
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from . import models as m
from . import test_shs_curriculum as curriculum_tests
from . import test_shs_migrations as migration_tests


class DeliveryPlanTests(TestCase):
    def setUp(self):
        curriculum_tests.CurriculumConfigurationTests.setUp(self)
        self.offering = m.SubjectOffering.objects.create(requirement=self.requirement, cohort=self.cohort, academic_term=self.term, academic_period="Semester 1", is_approved=True)
        self.plan = m.DeliveryPlan.objects.create(offering=self.offering, reference_title="Synthetic delivery specification", approval_reference="Synthetic institutional approval")

    def component(self, **changes):
        data=dict(plan=self.plan, instruction="Guided practice", duration_minutes=60, meeting_count=80)
        data.update(changes)
        return m.DeliveryComponent.objects.create(**data)

    def approve(self):
        self.plan.is_approved=True
        self.plan.save()

    def test_period_total_approval_does_not_infer_weeks(self):
        self.component()
        self.assertEqual(self.plan.planned_minutes,4800)
        self.approve()
        self.assertEqual(self.plan.effective_status,"Approved configuration")

    def test_weekly_total_and_distinct_components(self):
        # A separate source/offer is needed because existing requirements are locked.
        self.plan.delete()
        self.offering.delete()
        self.requirement.measurement_basis="WEEK"
        self.requirement.quantity=3
        self.requirement.save()
        self.offering.pk=None
        self.offering.save()
        self.plan.pk=None
        self.plan.offering=self.offering
        self.plan.save()
        self.component(duration_minutes=60,meeting_count=1)
        self.component(position=2,instruction="Independent supervised work",duration_minutes=60,meeting_count=2)
        self.approve()
        self.assertEqual(self.plan.planned_minutes,180)

    def test_empty_incomplete_and_excess_totals_block_approval(self):
        with self.assertRaises(ValidationError): self.approve()
        self.plan.is_approved=False
        item=self.component(meeting_count=1)
        for count in (1,81):
            item.meeting_count=count
            item.save()
            with self.assertRaises(ValidationError): self.approve()
            self.plan.is_approved=False

    def test_parent_deactivation_invalidates_effective_status(self):
        self.component()
        self.approve()
        self.version.is_active=False
        self.version.save()
        self.assertEqual(self.plan.effective_status,"Approval blocked")

    def test_missing_provenance_can_remain_draft(self):
        self.component()
        self.plan.reference_title=""
        self.plan.approval_reference=""
        self.plan.save()
        with self.assertRaises(ValidationError): self.approve()

    def test_component_positive_counts_and_duplicates(self):
        for changes in ({'duration_minutes':0},{'meeting_count':0},{'position':0}):
            with self.assertRaises(ValidationError): self.component(**changes)
        self.component()
        with self.assertRaises(ValidationError): self.component()
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.DeliveryComponent.objects.update(duration_minutes=0)
        with self.assertRaises(ValidationError):
            m.DeliveryPlan.objects.create(offering=self.offering)

    def test_approved_components_require_return_to_draft(self):
        item=self.component()
        self.approve()
        item.duration_minutes=30
        with self.assertRaises(ValidationError): item.save()
        with self.assertRaises(ValidationError): item.delete()
        self.plan.is_approved=False
        self.plan.save()
        item.save()

    def test_offering_identity_cannot_change_under_plan(self):
        self.offering.academic_period="Semester 2"
        with self.assertRaises(ValidationError): self.offering.save()
        self.assertEqual(self.subject.lecture_hours,3)

    def test_administrator_form_and_role_permissions(self):
        faculty=User.objects.create_user(username="delivery-faculty",is_staff=True)
        m.Profile.objects.create(user=faculty,role="FACULTY")
        for model in (m.DeliveryPlan,m.DeliveryComponent):
            self.assertFalse(admin.site._registry[model].has_add_permission(SimpleNamespace(user=faculty)))
        user=User.objects.create_superuser(username="delivery-admin",password="test-only")
        request=SimpleNamespace(user=user)
        model_admin=admin.site._registry[m.DeliveryPlan]
        form_class=model_admin.get_form(request,self.plan)
        form=form_class(data={'offering':self.offering.pk,'reference_title':'Source','approval_reference':'Approval','is_approved':True},instance=self.plan)
        self.assertFalse(form.is_valid())
        self.assertIn('is_approved',form.errors)
        self.plan.refresh_from_db()
        self.component()
        self.plan.is_approved=True
        model_admin.save_model(request,self.plan,SimpleNamespace(changed_data=['is_approved']),True)
        self.assertEqual(self.plan.approved_by,user)
        self.assertIsNotNone(self.plan.approved_at)


class DeliveryMigrationTests(migration_tests.SHSMigrationTests):
    def rehearse(self,populated):
        script=migration_tests.REHEARSAL.replace("0020_normalized_identity_uniqueness","0022_shs_curriculum_configuration").replace("0021_shs_academic_identity","0023_shs_delivery_plans").replace('len(triggers) + 3','len(triggers)')
        env=os.environ.copy()
        env['SHS_MIGRATION_POPULATED']=str(int(populated))
        result=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
