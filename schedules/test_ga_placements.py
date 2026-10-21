"""H6 feasible individual domains and conflict-aware genetic operators."""
from datetime import date, time
from unittest.mock import patch
import random
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test.utils import CaptureQueriesContext
from django.db import connection
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.ga import Gene, GeneticScheduler
from .services.placements import feasible_placements, PlacementOccupancy
from .services.conflicts import individual_entry_errors
from .services.time import ALLOWED_DAYS, add_minutes, slot_starts


class FeasiblePlacementTests(SchedulingDefectFixture):
    def setUp(self):
        self.settings = m.GASettings(population_size=8, generations=3, elitism=1, mutation_rate=1)

    def ga(self, seed=31):
        return GeneticScheduler(self.term, self.settings, seed=seed)

    def available(self, resource, start=time(8), end=time(12), day=0, kind='AVAILABLE'):
        m.Availability.objects.create(**resource, day=day, start_time=start, end_time=end, kind=kind)

    def validate(self, gene, schedule=None):
        schedule = schedule or m.Schedule(term=self.term)
        entry = m.ScheduleEntry(schedule=schedule, assignment=m.TeachingAssignment.objects.get(pk=gene.assignment_id),
            room=m.Room.objects.get(pk=gene.room_id), day=gene.day, start_time=gene.start_time, end_time=gene.end_time)
        self.assertEqual(individual_entry_errors(entry), [])

    def test_options_use_shared_validation_and_cache(self):
        ga = self.ga()
        options = ga.placement_options(ga.assignments[0])
        self.assertTrue(options)
        for gene in options:
            self.validate(gene)
        with CaptureQueriesContext(connection) as queries:
            self.assertIs(ga.placement_options(ga.assignments[0]), options)
        self.assertEqual(len(queries), 0)

    def test_faculty_and_room_available_and_unavailable_periods(self):
        self.available({'faculty': self.faculty})
        self.available({'room': self.room})
        self.available({'faculty': self.faculty}, time(9), time(10), kind='UNAVAILABLE')
        self.available({'room': self.room}, time(10), time(11), kind='UNAVAILABLE')
        ga = self.ga()
        options = ga.placement_options(ga.assignments[0])
        self.assertEqual({(g.day, g.start_time, g.end_time) for g in options},
                         {(0, time(8), time(9)), (0, time(11), time(12))})

    def test_room_capacity_type_and_active_status(self):
        for name, kind, capacity, active in [('Small', 'LECTURE', 1, True),
            ('Inactive', 'LECTURE', 40, False), ('Lab', 'SCIENCE_LAB', 40, True)]:
            m.Room.objects.create(name=name, room_type=kind, capacity=capacity, is_active=active)
        ga = self.ga()
        self.assertEqual({g.room_id for g in ga.placement_options(ga.assignments[0])}, {self.room.pk})

    def test_non_grid_availability_boundary_is_supported(self):
        self.available({'faculty': self.faculty}, time(8, 10), time(9, 10))
        self.available({'room': self.room}, time(8, 10), time(9, 10))
        ga = self.ga()
        options = ga.placement_options(ga.assignments[0])
        self.assertEqual(len(options), 1)
        self.assertEqual((options[0].start_time, options[0].end_time), (time(8, 10), time(9, 10)))

    def test_duration_and_operating_boundaries(self):
        m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(duration_minutes=720)
        ga = self.ga()
        options = ga.placement_options(ga.assignments[0])
        self.assertTrue(options)
        self.assertEqual({(g.start_time, g.end_time) for g in options}, {(time(7), time(19))})
        m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(duration_minutes=721)
        ga = self.ga()
        with self.assertRaisesMessage(ValueError, 'school day'):
            ga.placement_options(ga.assignments[0])

    def test_short_duration_is_not_extended(self):
        m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(duration_minutes=1)
        self.available({'faculty': self.faculty}, time(18, 59), time(19))
        ga = self.ga()
        options = ga.placement_options(ga.assignments[0])
        self.assertEqual(len(options), 1)
        self.assertEqual((options[0].start_time, options[0].end_time), (time(18, 59), time(19)))

    def test_expired_credentials_rejected_matching_override_accepted(self):
        credential = m.Credential.objects.create(name='Required license')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        m.FacultyCredential.objects.create(faculty=self.faculty, credential=credential,
            issued_on=date(2020, 1, 1), expires_on=date(2021, 1, 1))
        ga = self.ga()
        with self.assertRaisesMessage(ValueError, 'credential'):
            ga.placement_options(ga.assignments[0])
        admin = User.objects.create_superuser(username='placements-admin', password='test')
        m.CredentialOverride.objects.create(assignment=self.meetings[0], faculty=self.faculty,
            subject=self.subject, admin_user=admin, reason='Approved term exception', missing_credentials='Expired')
        ga = self.ga()
        self.assertTrue(ga.placement_options(ga.assignments[0]))
        with self.assertRaisesMessage(ValueError, 'credential'):
            ga.placement_options(ga.assignments[1])

    def test_lecture_laboratory_room_requirements(self):
        self.subject.lecture_hours, self.subject.lab_hours = 1, 1
        self.subject.save()
        m.TeachingAssignment.objects.filter(pk=self.meetings[1].pk).update(component='LABORATORY', required_room_type_override='SCIENCE_LAB')
        lab = m.Room.objects.create(name='Science', room_type='SCIENCE_LAB', capacity=30)
        ga = self.ga()
        self.assertEqual({g.room_id for g in ga.placement_options(ga.assignments[0])}, {self.room.pk})
        self.assertEqual({g.room_id for g in ga.placement_options(ga.assignments[1])}, {lab.pk})

    def test_invalid_component_and_term_consistency_rejected(self):
        ga = self.ga()
        assignment = ga.assignments[0]
        assignment.component = 'LABORATORY'
        options, errors = feasible_placements(assignment, self.term, ga.rooms)
        self.assertFalse(options)
        self.assertTrue(any('component' in error for error in errors))
        assignment.component = 'LECTURE'
        other = m.AcademicTerm.objects.create(name='Other', school_year='2027', starts_on=date(2027, 1, 1), ends_on=date(2027, 6, 1))
        options, errors = feasible_placements(assignment, other, ga.rooms)
        self.assertFalse(options)
        self.assertTrue(any('different academic term' in error for error in errors))
        assignment.term = other
        options, errors = feasible_placements(assignment, other, ga.rooms)
        self.assertFalse(options)
        self.assertTrue(any('terms must match' in error for error in errors))

    def test_initialization_prefers_no_conflicts_and_preserves_gene_order(self):
        self.available({'faculty': self.faculty})
        self.available({'room': self.room})
        ga = self.ga()
        for _ in range(20):
            genes = ga._random_chromosome()
            self.assertEqual([g.assignment_id for g in genes], [a.pk for a in ga.assignments])
            self.assertEqual(ga.fitness(genes).hard_violations, 0)
            for gene in genes:
                self.assertIn(gene, ga.placement_options(ga.assignment_map[gene.assignment_id]))

    def test_population_diversity_and_fixed_seed(self):
        first, second = self.ga(), self.ga()
        population = [tuple(first._random_chromosome()) for _ in range(12)]
        self.assertEqual(population, [tuple(second._random_chromosome()) for _ in range(12)])
        self.assertGreater(len(set(population)), 1)

    def test_mutation_uses_different_valid_alternatives(self):
        ga = self.ga()
        original = ga._random_chromosome()
        changed = ga._mutate(original)
        for previous, current in zip(original, changed):
            self.assertNotEqual(previous, current)
            self.assertEqual(previous.assignment_id, current.assignment_id)
            self.assertIn(current, ga.placement_options(ga.assignment_map[current.assignment_id]))
        self.assertEqual(ga.fitness(changed).hard_violations, 0)

    def test_single_option_mutation_terminates(self):
        self.available({'faculty': self.faculty}, time(8), time(9))
        ga = self.ga()
        original = ga._random_chromosome()
        self.assertEqual(ga._mutate(original), original)
        self.assertGreater(ga.fitness(original).hard_violations, 0)

    def test_crossover_preserves_unaffected_inheritance(self):
        ga = self.ga()
        a = [Gene(meeting.pk, self.room.pk, 0, time(8+i), time(9+i)) for i, meeting in enumerate(self.meetings)]
        b = [Gene(meeting.pk, self.room.pk, 1, time(8+i), time(9+i)) for i, meeting in enumerate(self.meetings)]
        self.assertEqual(ga._crossover(a, b), [a[0], b[1]])

    def test_crossover_detects_new_conflicts_and_uses_other_inherited_option(self):
        ga = self.ga()
        a = [Gene(meeting.pk, self.room.pk, 0, time(8+i), time(9+i)) for i, meeting in enumerate(self.meetings)]
        b = [Gene(meeting.pk, self.room.pk, 0, time(9-i), time(10-i)) for i, meeting in enumerate(self.meetings)]
        naive = [a[0], b[1]]
        self.assertGreater(ga.fitness(naive).hard_violations, 0)
        child = ga._crossover(a, b)
        self.assertEqual(child, a)
        self.assertEqual(ga.fitness(child).hard_violations, 0)

    def test_invalid_inherited_single_gene_not_silently_accepted(self):
        ga = self.ga()
        valid = ga._random_gene(ga.assignments[0])
        invalid = Gene(valid.assignment_id, valid.room_id, 6, valid.start_time, valid.end_time)
        self.assertEqual(ga._crossover([invalid], [valid]), [valid])

    def test_individually_empty_domain_reports_meeting_and_reason_before_population(self):
        self.available({'faculty': self.faculty}, time(8), time(9))
        self.available({'room': self.room}, time(10), time(11))
        ga = self.ga()
        with patch.object(ga, '_random_chromosome') as initialize:
            with self.assertRaisesMessage(ValueError, 'Meeting 1') as caught:
                ga.generate()
        self.assertIn('no individually feasible placement', str(caught.exception))
        self.assertIn('common faculty, section and room availability', str(caught.exception))
        initialize.assert_not_called()
        self.assertFalse(m.Schedule.objects.exists())

    def test_nonempty_individual_domains_can_be_jointly_infeasible(self):
        self.available({'faculty': self.faculty}, time(8), time(9))
        ga = self.ga()
        self.assertTrue(all(ga.placement_options(assignment) for assignment in ga.assignments))
        with self.assertRaisesMessage(ValueError, 'No feasible schedule found within the generation limit'):
            ga.generate()
        self.assertFalse(m.Schedule.objects.exists())

    def test_resource_overlap_detection_includes_faculty_section_and_room(self):
        ga = self.ga()
        first = Gene(self.meetings[0].pk, self.room.pk, 0, time(8), time(9))
        touching = Gene(self.meetings[1].pk, self.room.pk, 0, time(9), time(10))
        overlap = Gene(self.meetings[1].pk, self.room.pk, 0, time(8, 30), time(9, 30))
        occupancy = PlacementOccupancy(ga.assignment_map, [first])
        self.assertTrue(occupancy.conflicts(overlap))
        self.assertFalse(occupancy.conflicts(touching))

    def test_candidates_revalidated_against_live_data_before_persistence(self):
        ga = self.ga()
        for assignment in ga.assignments:
            ga.placement_options(assignment)
        # Cached domains do not grant approval after data changes.
        self.room.is_active = False
        self.room.save()
        with self.assertRaisesMessage(ValueError, 'inactive'):
            ga.generate()
        self.assertFalse(m.Schedule.objects.exists())

    def test_measured_individual_invalid_count_against_legacy_sampling(self):
        self.available({'faculty': self.faculty}, time(8), time(10), day=2)
        self.available({'room': self.room}, time(8), time(10), day=2)
        legacy, current = self.ga(seed=17), self.ga(seed=17)
        before = []
        for _ in range(100):
            for assignment in legacy.assignments:
                room = legacy._choose_room_for_assignment(assignment, legacy.valid_rooms_by_assignment[assignment.pk])
                day = legacy.random.choice(list(ALLOWED_DAYS))
                start = legacy.random.choice(list(slot_starts(assignment.required_duration_minutes)))
                before.append(Gene(assignment.pk, room.pk, day, start, add_minutes(start, assignment.required_duration_minutes)))
        after = [gene for _ in range(100) for gene in current._random_chromosome()]
        before_invalid = sum(legacy.fitness([gene]).hard_violations > 0 for gene in before)
        after_invalid = sum(current.fitness([gene]).hard_violations > 0 for gene in after)
        self.assertGreater(before_invalid, 0)
        self.assertEqual(after_invalid, 0)
        print(f'Placement comparison, seed 17: legacy {before_invalid}/{len(before)} individually invalid; feasible domains {after_invalid}/{len(after)}. No timing claim.')
