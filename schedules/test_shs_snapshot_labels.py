"""Descriptive labels do not change operational identity or frozen history."""
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from . import models as m
from .test_shs_generation import ControlledSHSGenerationTests
from .test_contact_workload import ContactPolicyTests
from .services.publication import publish
from .services.shs_scheduling import assert_prepared, scheduling_snapshot


class SnapshotComparisonTests(SimpleTestCase):
    def test_only_participant_label_is_excluded(self):
        original = dict(sections=[dict(id=1, name='Original', size=20, cohort_id=2)],
                        dates=['2026-08-03'], minutes=60, faculty_id=3,
                        room_reference='Approved', calendar_reference='Approved')
        renamed = deepcopy(original)
        renamed['sections'][0]['name'] = 'Renamed'
        self.assertEqual(scheduling_snapshot(original), scheduling_snapshot(renamed))
        self.assertEqual(original['sections'][0]['name'], 'Original')
        for key, value in [('id', 9), ('size', 21), ('cohort_id', 8)]:
            changed = deepcopy(original)
            changed['sections'][0][key] = value
            self.assertNotEqual(scheduling_snapshot(original), scheduling_snapshot(changed))
        for key, value in [('dates', ['2026-08-10']), ('minutes', 90), ('faculty_id', 4),
                           ('room_reference', 'Changed'), ('calendar_reference', 'Changed'),
                           ('future_requirement', True)]:
            changed = {**original, key: value}
            self.assertNotEqual(scheduling_snapshot(original), scheduling_snapshot(changed))

    def test_malformed_evidence_fails_closed(self):
        for data in (None, [], {}, {'sections': []}, {'sections': [None]},
                     {'sections': [{'id': 1}]}, {'sections': [{'name': None}]}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                scheduling_snapshot(data)


class PreparedLabelTests(TestCase):
    def setUp(self):
        ControlledSHSGenerationTests.setUp(self)
        ContactPolicyTests.policy(self)
        self.schedule = ControlledSHSGenerationTests.generate(self)

    def test_rename_preserves_binding_and_published_history(self):
        meeting = self.schedule.entries.get().assignment
        frozen = deepcopy(meeting.shs_binding.data)
        self.section.name = 'Z99'
        self.section.save(update_fields=['name'])
        assert_prepared(self.term)
        meeting.shs_binding.refresh_from_db()
        self.assertEqual(meeting.shs_binding.data, frozen)
        published, _ = publish(self.schedule, self.actor)
        history = deepcopy(m.ScheduleSnapshot.objects.get(schedule=published).data)
        # Publication does not refresh the operational binding's earlier label.
        meeting.shs_binding.refresh_from_db()
        self.assertEqual(meeting.shs_binding.data, frozen)
        self.section.name = 'Z98'
        with self.assertRaises(ValidationError):
            self.section.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Section.objects.filter(pk=self.section.pk).update(name='Z98')
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=published).data, history)
        with self.assertRaises(IntegrityError), transaction.atomic():
            published.entries.update(day=1)

    def test_changed_capacity_remains_invalid(self):
        self.section.size += 1
        self.section.save(update_fields=['size'])
        with self.assertRaises(ValidationError):
            assert_prepared(self.term)

    def test_invalid_section_code_is_rejected(self):
        self.section.name = 'Invalid section code'
        with self.assertRaises(ValidationError):
            self.section.save()
