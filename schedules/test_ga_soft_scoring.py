"""M4: minute-accurate faculty gaps and the complete instructional week."""
from datetime import time
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from .services.ga import Gene, GeneticScheduler
from .services.reproducibility import effective_parameters
from .services.time import ALLOWED_DAYS
from .test_known_defects import SchedulingDefectFixture
from . import models as m


class SoftScoringTests(SimpleTestCase):
    def penalty(self, intervals, days=(0,), faculty=None, sections=None):
        # Distinct sections isolate faculty gaps from the legacy section preference.
        ga = object.__new__(GeneticScheduler)
        genes = [Gene(i, 1, day, time(*start), time(*end))
                 for i, (day, start, end) in enumerate(intervals)]
        ga.assignment_map = {i: SimpleNamespace(
            faculty_id=faculty[i] if faculty else 1,
            section_id=sections[i] if sections else i) for i in range(len(genes))}
        with patch('schedules.services.ga.ALLOWED_DAYS', days):
            return ga._distribution_penalty(genes)

    def test_adjacent_meetings_have_zero_gap(self):
        self.assertEqual(self.penalty([(0, (8, 0), (9, 0)), (0, (9, 0), (10, 0))]), 0)

    def test_thirty_and_one_hundred_twenty_minutes(self):
        for start, end, expected in [((9, 30), (10, 30), 2), ((11, 0), (12, 0), 8)]:
            with self.subTest(start=start):
                self.assertEqual(self.penalty([(0, (8, 0), (9, 0)), (0, start, end)]), expected)

    def test_multiple_gaps_counted_once(self):
        self.assertEqual(self.penalty([(0, (8, 0), (9, 0)),
            (0, (9, 30), (10, 30)), (0, (11, 0), (12, 0))]), 4)

    def test_overlapping_and_nested_meetings_have_no_artificial_gap(self):
        for last in [(9, 30), (10, 30)]:
            self.assertEqual(self.penalty([(0, (8, 0), (12, 0)),
                (0, (9, 0), (10, 0)), (0, last, (11, 30))]), 0)

    def test_gap_after_overlap_uses_latest_end(self):
        self.assertEqual(self.penalty([(0, (8, 0), (10, 30)),
            (0, (9, 0), (10, 0)), (0, (11, 0), (12, 0))]), 2)

    def test_different_days_do_not_share_idle_time(self):
        self.assertEqual(self.penalty([(0, (8, 0), (9, 0)),
            (1, (15, 0), (16, 0))], days=(0, 1)), 0)

    def test_different_faculty_do_not_share_idle_time(self):
        self.assertEqual(self.penalty([(0, (8, 0), (9, 0)),
            (0, (15, 0), (16, 0))], faculty=[1, 2]), 0)

    def test_order_independent(self):
        rows = [(0, (8, 0), (9, 0)), (0, (9, 30), (10, 30)), (0, (11, 0), (12, 0))]
        self.assertEqual(self.penalty(rows), self.penalty(list(reversed(rows))))

    def test_empty_and_single_meeting(self):
        self.assertEqual(self.penalty([]), 0)
        self.assertEqual(self.penalty([(0, (12, 0), (13, 0))]), 0)

    def test_operating_boundaries_no_exterior_time(self):
        self.assertEqual(self.penalty([(0, (7, 0), (8, 0)), (0, (18, 0), (19, 0))]), 40)
        self.assertEqual(self.penalty([(0, (7, 0), (19, 0))]), 0)

    def test_unused_days_and_balanced_week(self):
        balanced = [(d, (8, 0), (9, 0)) for d in ALLOWED_DAYS]
        self.assertEqual(self.penalty(balanced, days=ALLOWED_DAYS), 0)
        concentrated = [(0, (8, 0), (9, 0)) for _ in ALLOWED_DAYS]
        self.assertEqual(self.penalty(concentrated, days=ALLOWED_DAYS,
            faculty=list(range(6))), 18)

    def test_ineligible_days_do_not_enter_day_counts(self):
        self.assertEqual(self.penalty([(6, (8, 0), (9, 0))], days=ALLOWED_DAYS), 0)

    def test_different_calendars_include_zero_counts(self):
        rows = [(0, (8, 0), (9, 0)), (1, (8, 0), (9, 0))]
        self.assertEqual(self.penalty(rows, days=(0, 1)), 0)
        self.assertEqual(self.penalty(rows, days=(0, 1, 2)), 3)
        self.assertEqual(self.penalty(rows, days=()), 0)
        self.assertEqual(self.penalty(rows[::-1], days=(2, 1, 0)), 3)

    def test_section_gap_and_daily_load_weights_preserved(self):
        rows = [(0, (8, 0), (9, 0)), (0, (11, 0), (12, 0))]
        self.assertEqual(self.penalty(rows, sections=[1, 1]), 16)  # 8 faculty + 8 section
        rows = [(0, (8+i, 0), (9+i, 0)) for i in range(4)]
        self.assertEqual(self.penalty(rows, sections=[1]*4), 16)  # 8 per resource

    def test_metadata_describes_effective_formula(self):
        settings = m.GASettings(population_size=4, generations=1, elitism=1)
        fitness = effective_parameters(settings, 64)['fitness']
        self.assertEqual(fitness['version'], 'hard-first-v2')
        self.assertEqual(fitness['faculty_idle_gap_unit'], 'minutes')
        self.assertEqual(fitness['faculty_idle_gap_hour_weight'], 4)
        self.assertEqual(fitness['day_spread_days'], list(ALLOWED_DAYS))
        self.assertEqual(fitness['day_spread_weight'], 3)
        self.assertEqual(fitness['preferred_period_bonus'], 12)
        self.assertEqual(fitness['capacity_gap_weight'], .15)
        self.assertNotIn('whole_hour_gap_threshold', fitness)


class SoftScoringIntegrationTests(SchedulingDefectFixture):
    def test_shorter_gap_and_balanced_days_rank_better(self):
        ga = GeneticScheduler(self.term, m.GASettings(population_size=2, generations=0, elitism=1), seed=42)
        first, second = self.meetings
        def candidate(day, hour, minute=0):
            return [Gene(first.pk, self.room.pk, 0, time(8), time(9)),
                    Gene(second.pk, self.room.pk, day, time(hour, minute), time(hour+1, minute))]
        short = ga.fitness(candidate(0, 9, 30))
        long = ga.fitness(candidate(0, 11))
        balanced = ga.fitness(candidate(1, 8))
        adjacent = ga.fitness(candidate(0, 9))
        self.assertEqual([v.hard_violations for v in (short, long, balanced, adjacent)], [0]*4)
        self.assertEqual(short.soft_score - long.soft_score, 14)  # faculty 6 + section 8
        self.assertEqual(balanced.soft_score - adjacent.soft_score, 3)
        self.assertGreater(short, long)
        self.assertGreater(balanced, adjacent)
