from dataclasses import replace
from datetime import date, time
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TestCase

from . import models as m
from . import test_known_defects as fixtures
from . import test_shs_delivery as delivery_fixtures
from .services.resource_occupancy import (
    ResourceCommitment, published_commitments, resource_conflicts,
    contact_minutes_by_faculty, weekday_intersects,
)
from .services.scheduling_requirements import resolve_shs, resolve_tertiary


class SharedOccupancyTests(fixtures.SchedulingDefectFixture):
    def setUp(self):
        self.schedule=m.Schedule.objects.create(term=self.term,name='Published commitment')
        self.entry=self.schedule.entries.create(assignment=self.meetings[0],room=self.room,day=0,start_time=time(8),end_time=time(9))
        self.query_term=SimpleNamespace(pk=-1,starts_on=date(2026,8,1),ends_on=date(2026,12,1))

    def publish(self):
        self.schedule.status='PUBLISHED'
        self.schedule.save()

    def candidate(self):
        return ResourceCommitment(None,None,-1,'SHS',self.faculty.pk,self.room.pk,0,time(8,30),time(9,30),date(2026,8,1),date(2026,12,1))

    def test_cross_level_faculty_and_room_conflicts(self):
        self.publish()
        occupancy=published_commitments(self.query_term)
        self.assertEqual(set(resource_conflicts(self.candidate(),occupancy)),{('faculty',self.entry.pk),('room',self.entry.pk)})
        self.assertEqual(resource_conflicts(replace(self.candidate(),faculty_id=-1),occupancy),(('room',self.entry.pk),))
        self.assertEqual(resource_conflicts(replace(self.candidate(),room_id=-1),occupancy),(('faculty',self.entry.pk),))

    def test_drafts_and_same_term_versions_do_not_reserve(self):
        self.assertEqual(published_commitments(self.query_term),())
        self.publish()
        self.assertEqual(published_commitments(self.term),())

    def test_calendar_weekday_and_adjacent_boundaries(self):
        self.publish()
        occupancy=published_commitments(self.query_term)
        for changes in ({'day':1},{'start_time':time(9),'end_time':time(10)},
                        {'starts_on':date(2027,1,1),'ends_on':date(2027,2,1)},
                        {'starts_on':date(2026,8,4),'ends_on':date(2026,8,5)}):
            with self.subTest(changes=changes):
                self.assertEqual(resource_conflicts(replace(self.candidate(),**changes),occupancy),())
        self.assertTrue(weekday_intersects(date(2026,8,3),date(2026,8,3),date(2026,8,1),date(2026,8,3),0))
        self.query_term.starts_on=date(2027,1,1)
        self.query_term.ends_on=date(2027,2,1)
        self.assertEqual(published_commitments(self.query_term),())

    def test_shs_published_term_is_visible_to_tertiary(self):
        self.term.education_level='SHS'
        self.term.save()
        self.publish()
        occupancy=published_commitments(self.query_term)
        self.assertEqual(occupancy[0].education_level,'SHS')
        self.assertTrue(resource_conflicts(replace(self.candidate(),education_level='TERTIARY'),occupancy))

    def test_effective_faculty_override_is_used(self):
        replacement=m.Faculty.objects.create(department=self.department,employee_id='OTHER',full_name='Synthetic Other')
        self.entry.faculty_override=replacement
        self.entry.save()
        self.publish()
        occupancy=published_commitments(self.query_term)
        self.assertEqual(occupancy[0].faculty_id,replacement.pk)
        self.assertEqual(resource_conflicts(replace(self.candidate(),room_id=-1),occupancy),())

    def test_contact_minutes_are_dated_information_not_workload_units(self):
        self.publish()
        occupancy=published_commitments(self.query_term)
        self.assertEqual(contact_minutes_by_faculty(occupancy+occupancy,date(2026,8,3),date(2026,8,10)),{self.faculty.pk:120})

    def test_tertiary_adapter_preserves_meeting_contract(self):
        result=resolve_tertiary(self.meetings[0].pk)
        self.assertEqual(result.components[0].minutes_per_meeting,60)
        self.assertEqual(result.weekly_limit_minutes,self.faculty.max_weekly_hours*60)
        self.assertIn(self.room.pk,result.compatible_room_ids)
        self.assertEqual(result.section_ids,(self.section.pk,))
        result.require_schedulable()
        self.term.education_level='SHS'
        self.term.save()
        with self.assertRaises(ValidationError): resolve_tertiary(self.meetings[0].pk)


class SHSRequirementResolutionTests(TestCase):
    def setUp(self):
        delivery_fixtures.DeliveryPlanTests.setUp(self)

    def test_missing_and_unapproved_plan(self):
        with self.assertRaises(ValidationError): resolve_shs(-1)
        result=resolve_shs(self.plan.pk)
        self.assertIn('The delivery plan has not been approved.',result.blockers)
        with self.assertRaises(ValidationError): result.require_schedulable()

    def test_approved_plan_retains_contact_basis_but_cannot_schedule(self):
        m.DeliveryComponent.objects.create(plan=self.plan,instruction='Guided work',duration_minutes=60,meeting_count=80)
        self.plan.is_approved=True
        self.plan.save()
        result=resolve_shs(self.plan.pk)
        self.assertEqual(result.components[0].basis,'PERIOD')
        self.assertEqual(result.components[0].meeting_count,80)
        self.assertIsNone(result.faculty_id)
        self.assertIsNone(result.compatible_room_ids)
        self.assertIsNone(result.weekly_limit_minutes)
        self.assertIsNone(result.teaching_dates)
        with self.assertRaises(ValidationError): result.require_schedulable()
        self.version.is_active=False
        self.version.save()
        self.assertTrue(any('verified, active' in msg for msg in resolve_shs(self.plan.pk).blockers))
