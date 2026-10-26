"""H6 targeted repair contracts and reproducible, deliberately small comparison."""
from dataclasses import replace
from datetime import time
from time import perf_counter
from unittest.mock import patch

from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.ga import Gene, GeneticScheduler
from .services.repair import candidate_issues, overlap_conflicts


class TargetedRepairTests(SchedulingDefectFixture):
    def ga(self, seed=17, budget=64):
        return GeneticScheduler(self.term, m.GASettings(population_size=4, generations=2,
            elitism=1, mutation_rate=0, crossover_rate=1), seed, repair_budget=budget)

    def collision(self):
        return [Gene(a.pk, self.room.pk, 0, time(8), time(9)) for a in self.meetings]

    def domains(self, ga, options):
        for assignment, choices in zip(ga.assignments, options):
            ga._placement_cache[assignment.pk] = tuple(choices)
            ga._placement_sets[assignment.pk] = frozenset(choices)

    def third(self):
        return m.TeachingAssignment.objects.create(assignment=self.parent,
            component='LECTURE', meeting_index=3, duration_minutes=60)

    def test_detect_categories_indexes_and_individual_errors_separately(self):
        ga = self.ga()
        genes = self.collision()
        individual, conflicts, affected = candidate_issues(ga, genes)
        self.assertEqual(individual, {})
        self.assertEqual(conflicts, {(kind, 0, 1) for kind in ('faculty', 'section', 'room')})
        self.assertEqual(affected, {0, 1})
        genes[1] = replace(genes[1], day=6)
        individual, conflicts, affected = candidate_issues(ga, genes)
        self.assertEqual(set(individual), {1})
        self.assertEqual(conflicts, set())
        self.assertEqual(affected, {1})

    def test_overlap_count_matches_fitness_and_adjacent_is_allowed(self):
        ga = self.ga()
        genes = self.collision()
        self.assertEqual(ga.fitness(genes).hard_violations, len(overlap_conflicts(genes, ga.assignment_map)))
        genes[1] = replace(genes[1], start_time=time(9), end_time=time(10))
        self.assertFalse(overlap_conflicts(genes, ga.assignment_map))

    def test_success_preserves_input_unaffected_gene_and_identity(self):
        third = self.third()
        ga = self.ga()
        genes = self.collision() + [Gene(third.pk, self.room.pk, 5, time(17), time(18))]
        original = genes.copy()
        repaired = ga._repair(genes)
        self.assertEqual(genes, original)
        self.assertEqual(repaired[2], original[2])
        self.assertEqual([g.assignment_id for g in repaired], [g.assignment_id for g in genes])
        self.assertEqual(ga.fitness(repaired).hard_violations, 0)
        self.assertEqual(ga.last_repair['status'], 'repaired')
        for gene in repaired[:2]:
            self.assertIn(gene, ga.placement_options(ga.assignment_map[gene.assignment_id]))
            self.assertEqual(gene.end_time.hour * 60 + gene.end_time.minute - gene.start_time.hour * 60 - gene.start_time.minute, 60)

    def test_simultaneous_conflicts_are_strictly_reduced(self):
        third = self.third()
        ga = self.ga()
        genes = self.collision() + [Gene(third.pk, self.room.pk, 0, time(8), time(9))]
        self.assertEqual(ga.fitness(genes).hard_violations, 9)
        result = ga._repair(genes)
        self.assertEqual(ga.fitness(result).hard_violations, 0)
        self.assertGreaterEqual(ga.last_repair['moves'], 2)

    def test_equal_hard_better_soft_is_rejected_without_repeated_trials(self):
        huge = m.Room.objects.create(name='Huge', capacity=100000, room_type='LECTURE')
        ga = self.ga()
        genes = [replace(g, room_id=huge.pk) for g in self.collision()]
        alternatives = [replace(g, start_time=time(8, 30), end_time=time(9, 30)) for g in genes]
        self.domains(ga, [[g, alt] for g, alt in zip(genes, alternatives)])
        # Preference scores cannot authorize an equal-hard replacement.
        real = ga.fitness
        from .services.ga import Fitness
        def score(candidate):
            value = real(candidate)
            return Fitness(value.hard_violations, value.soft_score + (10000 if candidate != genes else 0))
        with patch.object(ga, 'fitness', side_effect=score):
            self.assertEqual(ga._repair(genes), genes)
        self.assertEqual(ga.last_repair['attempts'], 2)
        self.assertEqual(ga.last_repair['status'], 'unresolved')

    def test_move_creating_new_conflict_is_rejected_and_unaffected_is_frozen(self):
        third = self.third()
        ga = self.ga()
        genes = self.collision() + [Gene(third.pk, self.room.pk, 0, time(10), time(11))]
        self.domains(ga, [[g, replace(g, start_time=time(10), end_time=time(11))] for g in genes[:2]] + [[genes[2]]])
        self.assertEqual(ga._repair(genes), genes)
        self.assertEqual(ga.last_repair['moves'], 0)

    def test_worse_alternatives_are_rejected(self):
        third = self.third()
        ga = self.ga()
        genes = self.collision() + [Gene(third.pk, self.room.pk, 0, time(9), time(10))]
        # Half-hour shift overlaps both remaining meetings instead of one.
        self.domains(ga, [[g, replace(g, start_time=time(8, 30), end_time=time(9, 30))] for g in genes[:2]] + [[genes[2]]])
        self.assertEqual(ga._repair(genes), genes)
        self.assertEqual(ga.last_repair['hard_after'], 3)

    def test_partial_repair_preserves_best_at_budget(self):
        third = self.third()
        ga = self.ga(budget=1)
        genes = self.collision() + [Gene(third.pk, self.room.pk, 0, time(8), time(9))]
        self.domains(ga, [[replace(g, day=1)] for g in genes])
        result = ga._repair(genes)
        self.assertEqual(ga.fitness(result).hard_violations, 3)
        self.assertEqual(ga.last_repair['status'], 'partial')
        self.assertEqual(ga.last_repair['attempts'], 1)

    def test_zero_budget_leaves_candidate_unresolved(self):
        ga = self.ga(budget=0)
        self.assertEqual(ga._repair(self.collision()), self.collision())
        self.assertEqual(ga.last_repair['attempts'], 0)
        self.assertEqual(ga.last_repair['status'], 'unresolved')

    def test_already_feasible_unchanged_without_domain_search_or_rng(self):
        ga = self.ga()
        genes = self.collision()
        genes[1] = replace(genes[1], day=1)
        state = ga.random.getstate()
        with patch.object(ga, 'placement_options', side_effect=AssertionError('unnecessary search')):
            self.assertEqual(ga._repair(genes), genes)
        self.assertEqual(ga.random.getstate(), state)
        self.assertEqual(ga.last_repair['status'], 'unchanged')

    def test_fixed_seed_and_diversity(self):
        results = []
        for seed in range(10):
            left, right = self.ga(seed), self.ga(seed)
            result = left._repair(self.collision())
            self.assertEqual(result, right._repair(self.collision()))
            self.assertEqual(left.last_repair, right.last_repair)
            results.append(tuple(result))
        self.assertGreater(len(set(results)), 1)

    def test_initialization_and_crossover_then_mutation_integration(self):
        ga = self.ga()
        with patch.object(ga, '_repair', wraps=ga._repair) as repair:
            ga._random_chromosome()
            self.assertEqual(repair.call_count, 1)
            child = ga._crossover(self.collision(), self.collision())
            self.assertGreater(ga.fitness(child).hard_violations, 0)
            result = ga._mutate(child)
            self.assertEqual(repair.call_count, 2)
            self.assertEqual(ga.fitness(result).hard_violations, 0)

    def test_individual_invalidity_repaired_from_domain(self):
        ga = self.ga()
        genes = [replace(g, day=6) for g in self.collision()]
        result = ga._repair(genes)
        self.assertEqual(ga.fitness(result).hard_violations, 0)
        self.assertEqual(candidate_issues(ga, result), ({}, set(), set()))

    def test_laboratory_component_and_duration_remain_intact(self):
        m.TeachingAssignment.objects.filter(pk__in=[a.pk for a in self.meetings]).update(component='LABORATORY', duration_minutes=90)
        m.Subject.objects.filter(pk=self.subject.pk).update(lecture_hours=0, lab_hours=3, required_room_type='COMPUTER_LAB')
        m.Room.objects.filter(pk=self.room.pk).update(room_type='COMPUTER_LAB')
        ga = self.ga()
        genes = [replace(g, end_time=time(9, 30)) for g in self.collision()]
        result = ga._repair(genes)
        self.assertEqual(ga.fitness(result).hard_violations, 0)
        for gene in result:
            self.assertEqual(ga.assignment_map[gene.assignment_id].component, 'LABORATORY')
            self.assertIn(gene, ga.placement_options(ga.assignment_map[gene.assignment_id]))
            self.assertEqual(gene.end_time.hour * 60 + gene.end_time.minute - gene.start_time.hour * 60 - gene.start_time.minute, 90)

    def test_unrepairable_generation_never_saves(self):
        m.Availability.objects.create(room=self.room, day=0, start_time=time(8), end_time=time(9), kind='AVAILABLE')
        ga = self.ga()
        with self.assertRaisesMessage(ValueError, 'No feasible schedule found'):
            ga.generate()
        self.assertFalse(m.Schedule.objects.exists())
        self.assertGreater(ga.repair_statistics['unresolved'], 0)
        self.assertEqual(ga.last_repair['moves'], 0)

    def test_final_database_validation_still_rejects_stale_domain(self):
        ga = self.ga()
        for a in ga.assignments:
            ga.placement_options(a)
        m.Room.objects.filter(pk=self.room.pk).update(is_active=False)
        with self.assertRaisesMessage(ValueError, 'inactive'):
            ga.generate()
        self.assertFalse(m.Schedule.objects.exists())

    def test_deterministic_population_comparison(self):
        before = after = repaired = attempts = 0
        elapsed = 0
        for seed in range(20):
            ga = self.ga(seed)
            for a in ga.assignments:
                ga.placement_options(a)
            genes = self.collision()
            before += ga.fitness(genes).hard_violations
            start = perf_counter()
            result = ga._repair(genes)
            elapsed += perf_counter() - start
            after += ga.fitness(result).hard_violations
            repaired += ga.last_repair['status'] == 'repaired'
            attempts += ga.last_repair['attempts']
        self.assertEqual((before, after, repaired), (60, 0, 20))
        print(f'Repair comparison seeds 0..19: hard {before}->{after}; repaired {repaired}/20; unresolved {20-repaired}; attempts {attempts}; repair-only {elapsed:.4f}s (warm domains).')

    def test_conflict_categories_can_be_identified_independently(self):
        from types import SimpleNamespace
        genes = self.collision()
        for kind in ('faculty', 'section', 'room'):
            mapping = {genes[0].assignment_id: SimpleNamespace(faculty_id=1, section_id=1),
                       genes[1].assignment_id: SimpleNamespace(faculty_id=1 if kind == 'faculty' else 2,
                                                              section_id=1 if kind == 'section' else 2)}
            candidate = [genes[0], replace(genes[1], room_id=self.room.pk if kind == 'room' else self.room.pk + 1)]
            self.assertEqual(overlap_conflicts(candidate, mapping), {(kind, 0, 1)})

    def test_empty_domain_leaves_best_candidate_unresolved(self):
        ga = self.ga()
        with patch.object(ga, 'placement_options', side_effect=ValueError('No feasible placement')):
            self.assertEqual(ga._repair(self.collision()), self.collision())
        self.assertEqual(ga.last_repair['status'], 'unresolved')
        self.assertEqual(ga.last_repair['attempts'], 0)

    def test_invalid_duration_is_reported_without_changing_fitness_policy(self):
        ga = self.ga()
        genes = [replace(self.collision()[0], end_time=time(8, 30))]
        self.assertEqual(ga.fitness(genes).hard_violations, 0)
        self.assertEqual(ga._repair(genes), genes)
        self.assertEqual(ga.last_repair['status'], 'unresolved')
        self.assertIn(0, ga.last_repair['individual_errors'])

    def test_budget_must_be_nonnegative_integer(self):
        for budget in (-1, 1.5):
            with self.assertRaisesMessage(ValueError, 'non-negative integer'):
                self.ga(budget=budget)
