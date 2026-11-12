import os
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import TestCase

from . import models as m
from .services.unified_development import require_unified_database, seed_representative_data


class UnifiedDevelopmentTests(TestCase):
    def seed(self):
        # Standard test runners use another database; only bypass the filename
        # check in this test, never academic validation or integrity safeguards.
        with patch('schedules.services.unified_development.require_unified_database'):
            seed_representative_data()

    def test_idempotent_shared_resources_and_unapproved_shs(self):
        self.seed()
        counts = {model: model.objects.count() for model in (
            m.Assignment, m.TeachingAssignment, m.Availability, m.SHSMeetingPattern)}
        self.seed()
        self.assertEqual(counts, {model: model.objects.count() for model in counts})
        self.assertEqual(set(m.AcademicTerm.objects.values_list('education_level', flat=True)), {'SHS', 'TERTIARY'})
        self.assertEqual(m.Assignment.objects.values('faculty_id').distinct().count(), 1)
        self.assertEqual(m.SHSMeetingPattern.objects.values('room_id').distinct().count(), 1)
        self.assertEqual(m.Assignment.objects.count(), 3)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.SHSApprovalEvidence.objects.exists())
        self.assertFalse(m.FacultyContactMinutePolicy.objects.exists())
        from .services.scheduling_requirements import resolve_shs
        for config in m.SHSAssignmentConfiguration.objects.all():
            self.assertTrue(resolve_shs(config.delivery_plan_id, assignment_id=config.assignment_id).blockers)

    def test_changed_seed_record_is_not_overwritten(self):
        self.seed()
        room = m.Room.objects.get()
        room.capacity = 35
        room.save()
        with self.assertRaises(CommandError):
            self.seed()
        room.refresh_from_db()
        self.assertEqual(room.capacity, 35)

    def test_other_environment_rejected_before_connection(self):
        with patch.dict(os.environ, {'SCHED_EASE_DATABASE_URL': 'sqlite:///tertiary_final_defense.sqlite3'}):
            with self.assertNumQueries(0), self.assertRaises(CommandError):
                require_unified_database()


class UnifiedGenerationTests(TestCase):
    def test_tertiary_generation_respects_published_shs(self):
        from . import test_shs_generation as fixtures
        from . import test_contact_workload as policies
        from .services.ga import GeneticScheduler
        from .services.publication import publish
        from .services.conflicts import schedule_validation_messages
        from .services.shs_scheduling import generate_shs
        fixtures.ControlledSHSGenerationTests.setUp(self)
        policies.ContactPolicyTests.policy(self, maximum_contact_minutes=180)
        shs = generate_shs(self.term, self.settings, actor=self.actor, seed=17)
        publish(shs, self.actor)
        draft, _ = fixtures.ControlledSHSGenerationTests.tertiary(self)
        tertiary = GeneticScheduler(draft.term, self.settings, seed=17).generate('Unified tertiary')
        self.assertEqual(tertiary.entries.count(), 1)
        self.assertEqual(schedule_validation_messages(tertiary), [])
        a, b = shs.entries.get(), tertiary.entries.get()
        self.assertTrue(a.day != b.day or a.end_time <= b.start_time or b.end_time <= a.start_time)
        publish(tertiary, self.actor)
        self.assertEqual(m.Schedule.objects.filter(status='PUBLISHED').count(), 2)
