"""H6: feasibility-first fitness across every GA decision point."""
from datetime import time
from unittest.mock import patch
from django.contrib.auth.models import User
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.ga import Fitness, Gene, GeneticScheduler


class HardDominanceTests(SchedulingDefectFixture):
    def setUp(self):
        self.large = m.Room.objects.create(name='Oversized', room_type='LECTURE', capacity=100000)
        self.settings = m.GASettings(population_size=2, generations=0, elitism=1,
                                     crossover_rate=0, mutation_rate=0)
        self.ga = GeneticScheduler(self.term, self.settings, seed=41)
        self.feasible = [Gene(meeting.pk, self.large.pk, 0, time(8+i), time(9+i))
                         for i, meeting in enumerate(self.meetings)]
        self.conflicting = [Gene(meeting.pk, self.room.pk, 0, time(8), time(9)) for meeting in self.meetings]
        self.good_soft = [Gene(meeting.pk, self.room.pk, 0, time(8+i), time(9+i))
                          for i, meeting in enumerate(self.meetings)]

    def test_feasible_outranks_infeasible_despite_extreme_soft_difference(self):
        feasible, conflicting = self.ga.fitness(self.feasible), self.ga.fitness(self.conflicting)
        self.assertEqual(feasible.hard_violations, 0)
        self.assertEqual(conflicting.hard_violations, 3)
        self.assertLess(feasible.soft_score, conflicting.soft_score - 750)
        self.assertGreater(feasible, conflicting)
        # The old 250-per-overlap weighted formula would choose the conflict.
        self.assertGreater(conflicting.soft_score - 750, feasible.soft_score)

    def test_fewer_hard_violations_dominate_any_soft_score(self):
        self.assertGreater(Fitness(1, -1e300), Fitness(2, 1e300))
        self.assertGreater(Fitness(0, -1e300), Fitness(1, 1e300))
        self.assertGreater(Fitness(2, 7), Fitness(2, -8))
        self.assertEqual(Fitness(2, 7), Fitness(2, 7))

    def test_same_hard_count_uses_existing_soft_preferences(self):
        better = self.ga.fitness(self.good_soft)
        worse = self.ga.fitness(self.feasible)
        self.assertEqual((better.hard_violations, worse.hard_violations), (0, 0))
        self.assertGreater(better.soft_score, worse.soft_score)
        self.assertGreater(better, worse)

    def test_population_sort_and_tournament_respect_hard_counts(self):
        ranked = sorted([self.conflicting, self.feasible, self.good_soft], key=self.ga.fitness, reverse=True)
        self.assertEqual(ranked, [self.good_soft, self.feasible, self.conflicting])
        self.assertEqual(self.ga._select([self.conflicting, self.feasible]), self.feasible)

    def test_exact_ties_retain_population_order_and_not_tournament_draw_order(self):
        first = list(self.good_soft)
        second = [Gene(g.assignment_id, g.room_id, 1, g.start_time, g.end_time) for g in first]
        self.assertEqual(self.ga.fitness(first), self.ga.fitness(second))
        self.assertIs(sorted([first, second], key=self.ga.fitness, reverse=True)[0], first)
        with patch.object(self.ga.random, 'sample', return_value=[(1, second), (0, first)]):
            self.assertIs(self.ga._select([first, second]), first)
        with patch.object(self.ga, '_random_chromosome', side_effect=[first, second]):
            schedule = self.ga.generate()
        self.assertEqual(set(schedule.entries.values_list('day', flat=True)), {0})

    def test_final_selection_uses_feasibility_and_persists_only_soft_score(self):
        with patch.object(self.ga, '_random_chromosome', side_effect=[self.conflicting, self.feasible]):
            schedule = self.ga.generate()
        self.assertEqual(set(schedule.entries.values_list('room_id', flat=True)), {self.large.pk})
        self.assertEqual(schedule.fitness_score, self.ga.fitness(self.feasible).soft_score)
        self.assertEqual(self.ga.best_fitness.hard_violations, 0)
        self.assertLess(schedule.fitness_score, 0)
        self.assertEqual(self.ga.generation_statistics[0]['best_so_far']['hard_violations'], 0)

    def test_elitism_preserves_feasible_parent_over_soft_better_conflict(self):
        self.settings.generations = 2
        with patch.object(self.ga, '_random_chromosome', side_effect=[self.conflicting, self.feasible]), \
             patch.object(self.ga, '_mutate', return_value=list(self.conflicting)):
            self.ga.generate()
        self.assertEqual(len(self.ga.generation_statistics), 3)
        self.assertTrue(all(row['population_best']['hard_violations'] == 0 for row in self.ga.generation_statistics))

    def test_best_so_far_survives_worse_generation_without_elitism(self):
        self.settings.generations, self.settings.elitism = 1, 0
        with patch.object(self.ga, '_random_chromosome', side_effect=[self.conflicting, self.feasible]), \
             patch.object(self.ga, '_mutate', return_value=list(self.conflicting)):
            schedule = self.ga.generate()
        self.assertEqual(self.ga.generation_statistics[-1]['population_best']['hard_violations'], 3)
        self.assertEqual(self.ga.generation_statistics[-1]['best_so_far']['hard_violations'], 0)
        self.assertEqual(set(schedule.entries.values_list('room_id', flat=True)), {self.large.pk})

    def test_all_feasible_population_continues_optimizing_soft_score(self):
        self.settings.generations = 2
        with patch.object(self.ga, '_random_chromosome', return_value=list(self.feasible)), \
             patch.object(self.ga, '_mutate', return_value=list(self.good_soft)):
            schedule = self.ga.generate()
        self.assertEqual(self.ga.best_fitness, self.ga.fitness(self.good_soft))
        self.assertEqual(set(schedule.entries.values_list('room_id', flat=True)), {self.room.pk})
        self.assertEqual(len(self.ga.generation_statistics), 3)

    def test_all_infeasible_population_improves_hard_count_then_reports_failure(self):
        small = m.Room.objects.create(name='Small', room_type='LECTURE', capacity=1)
        self.ga = GeneticScheduler(self.term, self.settings, seed=41)
        worse = [Gene(g.assignment_id, small.pk, g.day, g.start_time, g.end_time) for g in self.conflicting]
        self.settings.generations = 1
        with patch.object(self.ga, '_random_chromosome', return_value=worse), \
             patch.object(self.ga, '_mutate', return_value=list(self.conflicting)):
            with self.assertRaisesMessage(ValueError, '3 hard constraint violations (soft preference score:'):
                self.ga.generate()
        self.assertEqual(self.ga.generation_statistics[0]['best_so_far']['hard_violations'], 5)
        self.assertEqual(self.ga.best_fitness.hard_violations, 3)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.ScheduleEntry.objects.exists())

    def test_hard_detectors_keep_independent_constraint_counts(self):
        small_wrong = m.Room.objects.create(name='Wrong small', room_type='SCIENCE_LAB', capacity=1)
        self.ga = GeneticScheduler(self.term, self.settings, seed=41)
        gene = Gene(self.meetings[0].pk, small_wrong.pk, 0, time(8), time(9))
        self.assertEqual(self.ga.fitness([gene]).hard_violations, 2)
        invalid_day = Gene(self.meetings[0].pk, self.room.pk, 6, time(8), time(9))
        # Operating window, faculty availability and room availability each fail.
        self.assertEqual(self.ga.fitness([invalid_day]).hard_violations, 3)
        self.ga.qualification_cache[self.meetings[0].pk] = False
        self.ga._fitness_cache.clear()
        self.assertEqual(self.ga.fitness([gene]).hard_violations, 3)

    def test_preference_reward_cannot_cancel_unavailability(self):
        for kind in ('PREFERRED', 'UNAVAILABLE'):
            m.Availability.objects.create(faculty=self.faculty, day=0, start_time=time(8), end_time=time(10), kind=kind)
        self.ga = GeneticScheduler(self.term, self.settings, seed=41)
        other_day = [Gene(g.assignment_id, g.room_id, 1, g.start_time, g.end_time) for g in self.good_soft]
        blocked, allowed = self.ga.fitness(self.good_soft), self.ga.fitness(other_day)
        self.assertGreater(blocked.soft_score, allowed.soft_score)
        self.assertEqual(blocked.hard_violations, 2)
        self.assertGreater(allowed, blocked)

    def test_final_validation_remains_authoritative_for_zero_ga_violations(self):
        self.subject.lab_hours = 1
        self.subject.save()
        self.ga = GeneticScheduler(self.term, self.settings, seed=41)
        self.assertEqual(self.ga.fitness(self.good_soft).hard_violations, 0)
        with patch.object(self.ga, '_random_chromosome', return_value=list(self.good_soft)):
            with self.assertRaisesMessage(ValueError, 'LABORATORY totals 0'):
                self.ga.generate()
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.ScheduleEntry.objects.exists())

    def test_fixed_seed_reproduces_selection_and_generated_placements(self):
        first = GeneticScheduler(self.term, self.settings, seed=16)
        second = GeneticScheduler(self.term, self.settings, seed=16)
        population = [self.conflicting, self.feasible, self.good_soft]
        self.assertEqual([first._select(population) for _ in range(6)], [second._select(population) for _ in range(6)])
        self.settings.population_size = 6
        self.settings.generations = 2
        schedules = [ga.generate() for ga in (first, second)]
        fields = ('assignment_id', 'room_id', 'day', 'start_time', 'end_time')
        self.assertEqual(list(schedules[0].entries.order_by('assignment_id').values_list(*fields)),
                         list(schedules[1].entries.order_by('assignment_id').values_list(*fields)))
        self.assertEqual(first.generation_statistics, second.generation_statistics)

    def test_failure_workflow_marks_run_failed_without_saving_invalid_schedule(self):
        admin = User.objects.create_superuser(username='ga-admin', password='test')
        self.client.force_login(admin)
        self.settings.save()
        with patch.object(GeneticScheduler, '_random_chromosome', return_value=list(self.conflicting)):
            response = self.client.post('/schedules/generate/', {'term': self.term.pk,
                'settings': self.settings.pk, 'name': 'Infeasible'})
        self.assertEqual(response.status_code, 200)
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'FAILED')
        self.assertIsNone(run.schedule_id)
        self.assertFalse(m.Schedule.objects.exists())
        issue = m.GenerationIssue.objects.get(category=m.GenerationIssue.Category.NO_SLOT)
        conflicts = run.issues.exclude(pk=issue.pk)
        self.assertEqual(set(conflicts.values_list('category', flat=True)),
            {'FACULTY_CONFLICT', 'ROOM_CONFLICT', 'SECTION_CONFLICT'})
        self.assertEqual(conflicts.count(), 3)
        self.assertTrue(all(set(item.details['meeting_ids']) == {a.pk for a in self.meetings} for item in conflicts))
        self.assertIn("3 hard constraint violations", issue.reason)
        self.assertIn("soft preference score", issue.reason)
        self.assertEqual(issue.category, m.GenerationIssue.Category.NO_SLOT)

    def test_cached_fitness_keeps_both_components(self):
        result = self.ga.fitness(self.good_soft)
        with patch.object(self.ga, '_distribution_penalty', side_effect=AssertionError('cache miss')):
            self.assertIs(self.ga.fitness(self.good_soft), result)
        self.assertEqual(result.hard_violations, 0)
        self.assertIsInstance(result.soft_score, float)

    def test_new_feasible_candidate_displaces_soft_better_infeasible_best(self):
        self.settings.generations = 1
        with patch.object(self.ga, '_random_chromosome', return_value=list(self.conflicting)), \
             patch.object(self.ga, '_mutate', return_value=list(self.feasible)):
            schedule = self.ga.generate()
        initial, final = self.ga.generation_statistics
        self.assertEqual(initial['best_so_far']['hard_violations'], 3)
        self.assertEqual(final['best_so_far']['hard_violations'], 0)
        self.assertLess(final['best_so_far']['soft_score'], initial['best_so_far']['soft_score'])
        self.assertEqual(set(schedule.entries.values_list('room_id', flat=True)), {self.large.pk})

    def test_equal_later_generation_keeps_earlier_best(self):
        self.settings.generations, self.settings.elitism = 1, 0
        later = [Gene(g.assignment_id, g.room_id, 1, g.start_time, g.end_time) for g in self.good_soft]
        with patch.object(self.ga, '_random_chromosome', return_value=list(self.good_soft)), \
             patch.object(self.ga, '_mutate', return_value=later):
            schedule = self.ga.generate()
        self.assertEqual(set(schedule.entries.values_list('day', flat=True)), {0})
        self.assertEqual(self.ga.generation_statistics[0]['best_so_far'], self.ga.generation_statistics[1]['best_so_far'])

    def test_success_message_reports_separate_components(self):
        admin = User.objects.create_superuser(username='ga-success', password='test')
        self.client.force_login(admin)
        self.settings.save()
        with patch.object(GeneticScheduler, '_random_chromosome', return_value=list(self.good_soft)):
            response = self.client.post('/schedules/generate/', {'term': self.term.pk,
                'settings': self.settings.pk, 'name': 'Feasible'}, follow=True)
        self.assertContains(response, '0 hard violations; soft preference score')
        self.assertEqual(m.GenerationRun.objects.get().status, 'SUCCEEDED')
