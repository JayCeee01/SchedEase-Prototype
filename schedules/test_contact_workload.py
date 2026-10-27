from datetime import date, time
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
import os
import subprocess
import sys

from . import models as m
from . import test_shs_operations as operational_tests
from . import test_shs_migrations as migration_tests
from . import test_known_defects as fixtures
from .services.contact_workload import ContactEvent, shs_contact_events, validate_weekly_contact_limits, published_contact_events


class ContactPolicyTests(TestCase):
    def setUp(self):
        operational_tests.OperationalInputTests.setUp(self)
        operational_tests.OperationalInputTests.pattern(self)
        operational_tests.OperationalInputTests.confirm(self)

    def policy(self, **changes):
        values=dict(faculty=self.faculty,accounting_period='CALENDAR_WEEK',covered_levels='SHS_AND_TERTIARY',week_starts_on=0,
            starts_on=date(2026,8,3),ends_on=date(2026,8,16),maximum_contact_minutes=120,
            reference='Synthetic isolated-test approval',is_verified=True,is_approved=True,is_active=True)
        values.update(changes)
        return m.FacultyContactMinutePolicy.objects.create(**values)

    def test_missing_unverified_and_inactive_policy_fail_closed(self):
        events=shs_contact_events(self.config)
        with self.assertRaises(ValidationError): validate_weekly_contact_limits(events)
        policy=self.policy(is_active=False,is_approved=False,is_verified=False)
        with self.assertRaises(ValidationError): validate_weekly_contact_limits(events)
        policy.is_active=True
        with self.assertRaises(ValidationError): policy.save()
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.FacultyContactMinutePolicy.objects.filter(pk=policy.pk).update(is_active=True)

    def test_combined_levels_week_boundaries_and_duplicate_identity(self):
        self.policy()
        events=shs_contact_events(self.config)
        tertiary=ContactEvent(('entry',1),self.faculty.pk,date(2026,8,9),60,'TERTIARY')
        totals=validate_weekly_contact_limits((*events,tertiary,tertiary))
        self.assertEqual(totals[(self.faculty.pk,date(2026,8,3))],120)
        self.assertEqual(totals[(self.faculty.pk,date(2026,8,10))],60)
        excess=ContactEvent(('entry',2),self.faculty.pk,date(2026,8,9),1,'TERTIARY')
        with self.assertRaises(ValidationError): validate_weekly_contact_limits((*events,tertiary,excess))
        outside=ContactEvent(('entry',3),self.faculty.pk,date(2026,7,27),999,'TERTIARY')
        self.assertEqual(validate_weekly_contact_limits((*events,outside)),validate_weekly_contact_limits(events))
        self.assertEqual(validate_weekly_contact_limits([outside]),{})

    def test_combined_class_counted_once(self):
        self.config.combined_class_reference='Synthetic combined approval'
        self.config.save()
        extra=m.Section.objects.create(program=self.program,year_level=self.year,name='B',size=20,cohort=self.section.cohort)
        m.SHSSectionParticipation.objects.create(configuration=self.config,section=extra)
        self.policy()
        events=shs_contact_events(self.config)
        self.assertEqual(len(events),2)
        self.assertEqual(sum(e.minutes for e in events),120)

    def test_ambiguous_overlap_and_unsupported_contract_rejected(self):
        self.policy()
        with self.assertRaises(ValidationError): self.policy()
        with self.assertRaises(ValidationError): self.policy(accounting_period='TERM')
        with self.assertRaises(ValidationError): self.policy(covered_levels='SHS_ONLY')

    def test_partial_weeks_fail_closed(self):
        self.policy(starts_on=date(2026,8,4))
        event=ContactEvent(('shs',99),self.faculty.pk,date(2026,8,5),60,'SHS')
        with self.assertRaisesMessage(ValidationError,'partial policy-week'):
            validate_weekly_contact_limits([event])

    def test_explicit_week_start_and_inconsistent_duplicates(self):
        with self.assertRaises(ValidationError):
            self.policy(week_starts_on=6)
        self.policy()
        events=shs_contact_events(self.config)
        self.assertIn((self.faculty.pk,date(2026,8,3)),validate_weekly_contact_limits(events))
        conflicting=ContactEvent(events[0].identity,self.faculty.pk,events[0].teaching_date,61,'SHS')
        with self.assertRaises(ValidationError): validate_weekly_contact_limits((*events,conflicting))


class PublishedContactTests(fixtures.SchedulingDefectFixture):
    def setUp(self):
        self.schedule=m.Schedule.objects.create(term=self.term,name='Synthetic publication')
        self.schedule.entries.create(assignment=self.meetings[0],room=self.room,day=0,start_time=time(8),end_time=time(9))

    def test_actual_dates_published_only_and_replacement_exclusion(self):
        self.assertEqual(published_contact_events(date(2026,8,1),date(2026,8,10)),())
        self.schedule.status='PUBLISHED'
        self.schedule.save()
        events=published_contact_events(date(2026,8,1),date(2026,8,10))
        self.assertEqual([e.teaching_date for e in events],[date(2026,8,3),date(2026,8,10)])
        self.assertEqual(sum(e.minutes for e in events),120)
        self.assertEqual(published_contact_events(date(2027,1,1),date(2027,2,1)),())
        self.assertEqual(published_contact_events(date(2026,8,1),date(2026,8,10),exclude_term_id=self.term.pk),())

    def test_legacy_shs_entries_are_not_silently_counted_as_weekly(self):
        self.term.education_level='SHS'
        self.term.save()
        self.schedule.status='PUBLISHED'
        self.schedule.save()
        with self.assertRaises(ValidationError):
            published_contact_events(date(2026,8,1),date(2026,8,10))


class ContactPolicyMigrationTests(migration_tests.SHSMigrationTests):
    def rehearse(self,populated):
        script=migration_tests.REHEARSAL.replace('0020_normalized_identity_uniqueness','0024_shs_operational_inputs').replace('0021_shs_academic_identity','0025_faculty_contact_minute_policy').replace('len(triggers) + 3','len(triggers)')
        env=os.environ.copy()
        env['SHS_MIGRATION_POPULATED']=str(int(populated))
        result=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
