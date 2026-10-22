"""M4 reproducibility metadata, canonical fingerprints and private run history."""
import random
from datetime import time, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db.models.functions import Now

from . import models as m
from .forms import ScheduleGenerationForm
from .services.ga import GeneticScheduler
from .services.reproducibility import canonical_inputs, fingerprint, initial_metadata
from .services.generation_issues import recover_stale_runs
from .services.generation_lock import acquire, GenerationLeaseLost
from .test_known_defects import SchedulingDefectFixture


class ReproducibilityTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='research-admin', password='test')
        self.client.force_login(self.admin)
        self.settings = m.GASettings.objects.create(name='Experiment', population_size=4, generations=2,
            mutation_rate=0.2, crossover_rate=0.6, elitism=1)
        self.payload = {'term': self.term.pk, 'settings': self.settings.pk, 'name': 'Experiment'}

    def ga(self, seed=123, **kwargs):
        return GeneticScheduler(self.term, self.settings, seed=seed, **kwargs)

    def test_automatic_seed_is_saved_and_passed_to_scheduler(self):
        with patch('schedules.services.reproducibility.secrets.randbits', return_value=987654):
            response = self.client.post('/schedules/generate/', self.payload)
        self.assertEqual(response.status_code, 302)
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.reproducibility['seed'], 987654)
        self.assertEqual(run.status, 'SUCCEEDED')
        self.assertIsNotNone(run.schedule_id)

    def test_explicit_zero_seed_and_optional_form(self):
        response = self.client.post('/schedules/generate/', {**self.payload, 'seed': 0})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.GenerationRun.objects.get().reproducibility['seed'], 0)
        for seed in ('bad', -1, 9223372036854775808):
            form = ScheduleGenerationForm({**self.payload, 'seed': seed})
            self.assertFalse(form.is_valid())
            self.assertIn('seed', form.errors)

    def test_identical_seed_and_inputs_reproduce_placements_and_fitness(self):
        first, second = self.ga(), self.ga()
        left, right = first.generate('First'), second.generate('Second')
        fields = ('assignment_id', 'room_id', 'day', 'start_time', 'end_time')
        self.assertEqual(list(left.entries.order_by('assignment_id').values_list(*fields)),
                         list(right.entries.order_by('assignment_id').values_list(*fields)))
        runs = list(m.GenerationRun.objects.order_by('started_at'))
        self.assertEqual(runs[0].reproducibility['inputs'], runs[1].reproducibility['inputs'])
        self.assertEqual(runs[0].reproducibility['parameters'], runs[1].reproducibility['parameters'])
        self.assertEqual(first.generation_statistics, second.generation_statistics)
        self.assertEqual(runs[0].reproducibility['outcome']['best_soft_score'], left.fitness_score)

    def test_each_attempt_starts_its_recorded_rng_without_changing_global_state(self):
        state = random.getstate()
        ga = self.ga()
        self.assertEqual(ga.random.random(), random.Random(123).random())
        first, second = ga.generate(), ga.generate()
        self.assertEqual(list(first.entries.order_by('assignment_id').values_list('room_id', 'day', 'start_time')),
                         list(second.entries.order_by('assignment_id').values_list('room_id', 'day', 'start_time')))
        self.assertEqual(random.getstate(), state)

    def test_effective_parameters_capture_runtime_values_not_mutable_settings_link(self):
        ga = self.ga(repair_budget=7)
        self.settings.generations = 1
        ga.generate()
        run = m.GenerationRun.objects.get()
        params = run.reproducibility['parameters']
        self.assertEqual({key: params[key] for key in ('population_size', 'generations', 'elitism', 'repair_attempt_limit')},
                         {'population_size': 4, 'generations': 1, 'elitism': 1, 'repair_attempt_limit': 7})
        self.assertEqual((params['mutation_rate'], params['crossover_rate'], params['tournament_size']), (0.2, 0.6, 4))
        self.assertEqual(params['fitness']['preferred_period_bonus'], 12)
        m.GASettings.objects.filter(pk=self.settings.pk).update(generations=90, mutation_rate=0.99)
        run.refresh_from_db()
        self.assertEqual(run.reproducibility['parameters'], params)

    def test_input_counts_include_relevant_constraints(self):
        m.Availability.objects.create(faculty=self.faculty, day=0, start_time=time(8), end_time=time(12), kind='AVAILABLE')
        m.Availability.objects.create(room=self.room, day=0, start_time=time(8), end_time=time(12), kind='AVAILABLE')
        credential = m.Credential.objects.create(name='Credential')
        held = m.FacultyCredential.objects.create(faculty=self.faculty, credential=credential, issued_on=self.term.starts_on)
        requirement = m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        equivalent = m.Credential.objects.create(name='Equivalent')
        requirement.acceptable_equivalents.add(equivalent)
        counts = self.ga().input_metadata['counts']
        self.assertEqual({key: counts[key] for key in ('assignments', 'meetings', 'faculty', 'rooms', 'sections')},
                         {'assignments': 1, 'meetings': 2, 'faculty': 1, 'rooms': 1, 'sections': 1})
        self.assertEqual(counts['faculty_availability_periods'], 1)
        self.assertEqual(counts['room_availability_periods'], 1)
        self.assertEqual(counts['faculty_credentials'], 1)
        self.assertEqual(counts['credential_requirements'], 1)
        self.assertEqual(counts['accepted_equivalents'], 1)
        self.assertEqual(counts['eligible_meetings'], 2)
        self.assertEqual(counts['required_minutes'], 120)

    def test_fingerprint_is_independent_of_record_and_dictionary_order(self):
        ga = self.ga()
        before = fingerprint(canonical_inputs(ga))
        ga.assignments.reverse()
        ga.rooms.reverse()
        self.assertEqual(fingerprint(canonical_inputs(ga)), before)
        self.assertEqual(fingerprint({'a': 1, 'b': 2}), fingerprint({'b': 2, 'a': 1}))
        self.assertEqual(len(before), 64)

    def test_presentation_changes_do_not_change_fingerprint(self):
        before = self.ga().input_metadata['sha256']
        m.Faculty.objects.filter(pk=self.faculty.pk).update(full_name='Private renamed teacher', employee_id='NEW')
        m.Subject.objects.filter(pk=self.subject.pk).update(title='New title', code='RENAMED')
        m.Room.objects.filter(pk=self.room.pk).update(name='New room label')
        self.assertEqual(self.ga().input_metadata['sha256'], before)

    def test_capacity_duration_availability_and_term_changes_change_fingerprint(self):
        previous = self.ga().input_metadata['sha256']
        changes = [lambda: m.Room.objects.filter(pk=self.room.pk).update(capacity=31),
            lambda: m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(duration_minutes=90),
            lambda: m.Availability.objects.create(room=self.room, day=1, start_time=time(8), end_time=time(10), kind='UNAVAILABLE'),
            lambda: setattr(self.term, 'ends_on', self.term.ends_on + timedelta(days=1))]
        for change in changes:
            change()
            current = self.ga().input_metadata['sha256']
            self.assertNotEqual(current, previous)
            previous = current

    def test_credentials_equivalents_and_override_validity_affect_fingerprint(self):
        credential = m.Credential.objects.create(name='Required')
        held = m.FacultyCredential.objects.create(faculty=self.faculty, credential=credential, issued_on=self.term.starts_on)
        requirement = m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        before = self.ga().input_metadata['sha256']
        held.expires_on = self.term.starts_on
        held.save()
        after = self.ga().input_metadata['sha256']
        self.assertNotEqual(before, after)
        other = m.Credential.objects.create(name='Alternative')
        requirement.acceptable_equivalents.add(other)
        self.assertNotEqual(self.ga().input_metadata['sha256'], after)
        before = self.ga().input_metadata['sha256']
        m.CredentialOverride.objects.create(assignment=self.meetings[0], faculty=self.faculty, subject=self.subject,
            admin_user=self.admin, reason='Secret justification', missing_credentials='Secret diagnosis')
        self.assertNotEqual(self.ga().input_metadata['sha256'], before)

    def test_loaded_input_summary_is_preserved_when_live_data_changes(self):
        ga = self.ga()
        before = ga.input_metadata.copy()
        m.Room.objects.filter(pk=self.room.pk).update(is_active=False)
        with self.assertRaises(ValueError):
            ga.generate()
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.reproducibility['inputs'], before)
        self.assertEqual(run.status, 'FAILED')
        self.assertFalse(m.Schedule.objects.exists())

    def test_preflight_failure_retains_seed_inputs_and_unknown_fitness(self):
        m.Room.objects.filter(pk=self.room.pk).update(capacity=1)
        with self.assertRaises(ValueError):
            self.ga(seed=5).generate()
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.reproducibility['seed'], 5)
        self.assertIsNone(run.reproducibility['outcome']['best_hard_violations'])
        self.assertTrue(run.issues.exists())
        self.assertGreaterEqual(run.reproducibility['outcome']['duration_seconds'], 0)
        self.assertIsNotNone(run.completed_at)

    def test_initialization_failure_has_seed_but_no_invented_inputs(self):
        with patch('schedules.views.GeneticScheduler', side_effect=RuntimeError('private initialization failure')):
            self.client.post('/schedules/generate/', {**self.payload, 'seed': 99})
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.reproducibility['seed'], 99)
        self.assertIsNone(run.reproducibility['inputs'])
        self.assertIsNone(run.reproducibility['outcome'])
        self.assertEqual(run.status, 'FAILED')

    def test_interruption_preserves_partial_metadata_and_recovery_does_not_invent_result(self):
        ga = self.ga()
        with patch.object(ga, '_generate', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ga.generate()
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'RUNNING')
        self.assertEqual(run.reproducibility['seed'], 123)
        self.assertIsNone(run.reproducibility['outcome'])
        self.assertEqual(recover_stale_runs(), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, 'FAILED')
        self.assertIsNone(run.reproducibility['outcome'])

    def test_stale_owner_cannot_record_success_or_schedule(self):
        ga = self.ga()
        real = ga._random_chromosome
        def expire():
            result = real()
            m.GenerationLease.objects.filter(term=self.term).update(expires_at=Now() - timedelta(seconds=1))
            return result
        with patch.object(ga, '_random_chromosome', side_effect=expire):
            with self.assertRaises(GenerationLeaseLost):
                ga.generate()
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'FAILED')
        self.assertIsNone(run.schedule_id)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertEqual(run.reproducibility['seed'], 123)

    def test_final_validation_rollback_preserves_failure_metadata(self):
        with patch('schedules.services.conflicts.schedule_validation_messages', return_value=['Forced failure']):
            with self.assertRaises(ValueError):
                self.ga().generate()
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'FAILED')
        self.assertIsNone(run.schedule_id)
        self.assertFalse(m.ScheduleEntry.objects.exists())
        self.assertEqual(run.reproducibility['outcome']['best_hard_violations'], 0)
        self.assertTrue(run.issues.exists())

    def test_metadata_is_private_and_contains_no_personal_fields(self):
        self.ga().generate()
        run = m.GenerationRun.objects.get()
        import json
        stored = json.dumps(run.reproducibility)
        self.assertNotIn(self.faculty.full_name, stored)
        self.assertNotIn(self.faculty.employee_id, stored)
        self.assertNotIn(self.admin.username, stored)
        url = f'/schedules/generation-runs/{run.pk}/'
        for role in ('STUDENT', 'FACULTY'):
            user = User.objects.create_user(username=role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_admin_can_inspect_metadata_and_historical_missing_values(self):
        schedule = self.ga().generate()
        run = m.GenerationRun.objects.get()
        page = self.client.get(f'/schedules/generation-runs/{run.pk}/')
        self.assertContains(page, run.reproducibility['inputs']['sha256'])
        self.assertContains(page, '123')
        self.assertContains(page, 'View Schedule')
        old = m.GenerationRun.objects.create(term=self.term, requested_name='Historical', status='FAILED')
        self.assertContains(self.client.get(f'/schedules/generation-runs/{old.pk}/'), 'unavailable for this historical run')
        self.assertContains(self.client.get('/schedules/error-log/'), 'View Run')

    def test_metadata_survives_settings_deletion(self):
        self.ga().generate()
        run = m.GenerationRun.objects.get()
        saved = run.reproducibility
        self.settings.delete()
        run.refresh_from_db()
        self.assertIsNone(run.ga_settings_id)
        self.assertEqual(run.reproducibility, saved)

    def test_new_fingerprint_excludes_prior_results_and_parameters(self):
        ga = self.ga()
        before = ga.input_metadata['sha256']
        ga.generate()
        self.settings.mutation_rate = 0.9
        self.assertEqual(self.ga(seed=999).input_metadata['sha256'], before)
