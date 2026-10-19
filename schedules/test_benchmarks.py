"""Fast benchmark contracts. Full medium/large searches are opt-in commands."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .benchmarks.runner import export_results, run_isolated_trial, validate_request
from .benchmarks.scenarios import require_isolation

PARAMETERS = dict(population_size=4, generations=2, mutation_rate=.08, crossover_rate=.85, elitism=1)
ROOT = Path(__file__).resolve().parent.parent


def child_script(source):
    process = subprocess.run([sys.executable, '-c', source], cwd=ROOT, capture_output=True, text=True)
    if process.returncode:
        raise AssertionError(process.stderr)
    return json.loads(process.stdout)


class BenchmarkExecutionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.first = run_isolated_trial('small', 17, PARAMETERS)
        cls.repeat = run_isolated_trial('small', 17, PARAMETERS)
        cls.other = run_isolated_trial('small', 41, PARAMETERS)
        cls.failed = run_isolated_trial('infeasible', 17, PARAMETERS)

    def test_fixed_seed_reproduces_inputs_placements_and_fitness(self):
        for key in ('input_counts', 'input_fingerprint', 'schedule_fingerprint', 'hard_violations',
                    'soft_score', 'generation_statistics', 'repair_statistics', 'parameters', 'status'):
            self.assertEqual(self.first[key], self.repeat[key], key)

    def test_different_seeds_are_recorded_without_changing_inputs(self):
        self.assertEqual((self.first['seed'], self.other['seed']), (17, 41))
        self.assertEqual(self.first['input_fingerprint'], self.other['input_fingerprint'])
        self.assertNotEqual(self.first['schedule_fingerprint'], self.other['schedule_fingerprint'])

    def test_success_is_validated_zero_hard_draft(self):
        for row in (self.first, self.other):
            self.assertEqual(row['status'], 'SUCCEEDED')
            self.assertTrue(row['feasible'])
            self.assertEqual(row['hard_violations'], 0)
            self.assertEqual(row['validation_outcome'], 'passed')
            self.assertEqual(row['validation_errors'], [])
            self.assertEqual(row['schedule_status'], 'DRAFT')
            self.assertIsNone(row['failure_reason'])

    def test_measured_scores_and_effective_parameters_match_metadata(self):
        row = self.first
        metadata = row['reproducibility']
        self.assertEqual(metadata['seed'], row['seed'])
        self.assertEqual(metadata['parameters'], row['parameters'])
        self.assertEqual(metadata['inputs']['sha256'], row['input_fingerprint'])
        self.assertEqual(metadata['outcome']['best_soft_score'], row['soft_score'])
        self.assertEqual(metadata['outcome']['best_hard_violations'], row['hard_violations'])
        self.assertEqual(row['generation_statistics'][-1]['best_so_far']['soft_score'], row['soft_score'])
        for key, value in PARAMETERS.items():
            self.assertEqual(row['parameters'][key], value)
        self.assertEqual(row['scoring_version'], 'hard-first-v2')
        self.assertEqual(row['parameters']['fitness']['faculty_idle_gap_unit'], 'minutes')
        self.assertEqual(row['parameters']['fitness']['day_spread_days'], list(range(6)))

    def test_timing_generations_and_repair_are_measured(self):
        row = self.first
        self.assertGreater(row['generation_seconds'], 0)
        self.assertGreaterEqual(row['elapsed_seconds'], row['generation_seconds'])
        self.assertGreaterEqual(row['worker_wall_seconds'], row['elapsed_seconds'])
        self.assertEqual(row['generations_executed'], 2)
        self.assertEqual([g['generation'] for g in row['generation_statistics']], [0, 1, 2])
        self.assertGreaterEqual(row['repair_statistics']['attempts'], 0)
        self.assertLessEqual(row['started_at'], row['completed_at'])
        self.assertIn('django', row['environment'])
        self.assertIn('python', row['environment'])

    def test_infeasible_reports_failure_without_invented_scores(self):
        row = self.failed
        self.assertEqual(row['status'], 'FAILED')
        self.assertEqual(row['generation_status'], 'FAILED')
        self.assertFalse(row['feasible'])
        self.assertIsNone(row['hard_violations'])  # No candidate evaluated in preflight.
        self.assertIsNone(row['soft_score'])
        self.assertIsNone(row['schedule_id'])
        self.assertEqual(row['generation_statistics'], [])
        self.assertEqual(row['generations_executed'], 0)
        self.assertEqual(row['validation_outcome'], 'not_run')
        self.assertIn('capacity', row['failure_reason'])
        self.assertIn('ROOM_CAPACITY', [d['category'] for d in row['diagnostics']])
        self.assertEqual(row['reproducibility']['inputs']['sha256'], row['input_fingerprint'])
        self.assertNotEqual(row['input_fingerprint'], self.first['input_fingerprint'])

    def test_json_and_csv_have_same_trial_fields(self):
        # Named files, not a new directory: also works in restricted Windows workspaces.
        paths = [ROOT / f'benchmark-test-{uuid4().hex}.{suffix}' for suffix in ('json', 'csv')]
        try:
            rows = [self.first, self.failed]
            for path in paths:
                export_results(rows, path)
            saved = json.loads(paths[0].read_text())
            self.assertEqual(saved['trials'], rows)
            with paths[1].open(newline='', encoding='utf-8') as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(len(exported), 2)
            self.assertEqual(set(exported[0]), set(rows[0]))
            self.assertEqual(json.loads(exported[0]['parameters']), rows[0]['parameters'])
            self.assertEqual(json.loads(exported[0]['feasible']), True)
            self.assertEqual(exported[1]['hard_violations'], '')
            self.assertEqual(exported[1]['status'], 'FAILED')
            with self.assertRaises(FileExistsError):
                export_results(rows, paths[0])
            self.assertEqual(json.loads(paths[0].read_text()), saved)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_exports_contain_no_personal_record_fields(self):
        text = json.dumps(self.first)
        for value in ('employee_id', 'full_name', 'password', 'Synthetic faculty'):
            self.assertNotIn(value, text)


class BenchmarkFixtureTests(SimpleTestCase):
    def test_all_fixture_sizes_fingerprints_and_qualifications(self):
        # Construct larger inputs only; ordinary tests do not search their domains.
        expected = {'small': (2, 2, 2, 3, 4, 12), 'medium': (6, 4, 8, 5, 24, 72),
                    'large': (12, 6, 18, 10, 72, 216)}
        fingerprints = []
        for name, counts in expected.items():
            with self.subTest(scenario=name):
                script = f'''
import json
from schedules.benchmarks.worker import isolated_database
with isolated_database():
    from schedules.benchmarks.scenarios import build_scenario
    from schedules.services.ga import GeneticScheduler
    from schedules.models import GASettings
    ga = GeneticScheduler(build_scenario({name!r}), GASettings(), seed=17)
    print(json.dumps({{'inputs': ga.input_metadata, 'preflight': ga.preflight_issues(),
        'components': sorted(set(a.component for a in ga.assignments)),
        'hours_valid': all(a.duration_minutes in (60, 120) for a in ga.assignments)}}))
'''
                row = child_script(script)
                actual = row['inputs']['counts']
                self.assertEqual(tuple(actual[k] for k in ('sections', 'courses', 'faculty', 'rooms', 'assignments', 'meetings')), counts)
                self.assertEqual(actual['required_minutes'], counts[4] * 240)
                self.assertEqual(actual['eligible_meetings'], counts[5])
                self.assertEqual(actual['faculty_credentials'], counts[2])
                self.assertEqual(actual['credential_requirements'], counts[1])
                self.assertEqual(actual['faculty_availability_periods'], counts[2] * 7)
                self.assertEqual(actual['room_availability_periods'], counts[3] * 10)
                self.assertEqual(row['preflight'], [])
                self.assertEqual(row['components'], ['LABORATORY', 'LECTURE'])
                self.assertTrue(row['hours_valid'])
                fingerprints.append(row['inputs']['sha256'])
                self.assertEqual(row['inputs']['sha256'], child_script(script)['inputs']['sha256'])
        self.assertEqual(len(set(fingerprints)), 3)

    def test_fixture_and_trial_refuse_application_database(self):
        from .benchmarks.scenarios import build_scenario
        from .benchmarks.trial import run_trial
        for action in (require_isolation, lambda: build_scenario('small'), lambda: run_trial({})):
            with self.assertRaisesRegex(RuntimeError, 'dedicated in-memory worker'):
                action()

    def test_worker_ignores_deployment_database_and_settings_environment(self):
        with patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'not_a_real_settings_module',
                                     'DATABASE_URL': 'postgres://do-not-connect',
                                     'SCHED_EASE_DATABASE_URL': 'postgres://do-not-connect'}):
            row = run_isolated_trial('infeasible', 0, PARAMETERS)
        self.assertEqual(row['status'], 'FAILED')
        self.assertEqual(row['environment']['database'], 'sqlite-memory')
        self.assertEqual(row['seed'], 0)

    def test_exception_cleanup_and_global_random_state(self):
        row = child_script('''
import json, random
from unittest.mock import patch
from schedules.benchmarks.worker import isolated_database
from django.db import connections
with patch.object(connections, 'close_all', wraps=connections.close_all) as close:
    with isolated_database():
        from schedules.benchmarks.trial import run_trial
        from schedules.benchmarks.runner import DEFAULT_PARAMETERS
        from schedules.models import Schedule, GenerationLease
        before = random.getstate()
        with patch('schedules.services.ga.GeneticScheduler._generate', side_effect=RuntimeError('test exception')):
            result = run_trial(dict(scenario='small', seed=17, parameters=DEFAULT_PARAMETERS, repair_budget=64))
        count = Schedule.objects.count()
        unchanged = before == random.getstate()
    print(json.dumps({'closed': close.called, 'result': result, 'schedules': count, 'random_unchanged': unchanged}))
''')
        self.assertTrue(row['closed'])
        self.assertTrue(row['random_unchanged'])
        self.assertEqual(row['schedules'], 0)
        self.assertEqual(row['result']['status'], 'ERROR')
        self.assertEqual(row['result']['generation_status'], 'FAILED')
        self.assertEqual(row['result']['failure_type'], 'RuntimeError')
        self.assertIsNone(row['result']['soft_score'])

    def test_independent_validation_failure_is_not_feasible(self):
        row = child_script(f'''
import json
from unittest.mock import patch
from schedules.benchmarks.worker import isolated_database
with isolated_database():
    from schedules.benchmarks.trial import run_trial
    with patch('schedules.services.conflicts.schedule_validation_messages', side_effect=[[], ['Verification rejection']]):
        result = run_trial(dict(scenario='small', seed=17, parameters={PARAMETERS!r}, repair_budget=64))
    print(json.dumps(result))
''')
        self.assertFalse(row['feasible'])
        self.assertEqual(row['status'], 'FAILED')
        self.assertEqual(row['validation_outcome'], 'failed')
        self.assertEqual(row['validation_errors'], ['Verification rejection'])

    def test_failed_search_reports_actual_evaluated_candidate(self):
        row = child_script(f'''
import json
from datetime import time
from unittest.mock import patch
from schedules.benchmarks.worker import isolated_database
with isolated_database():
    from schedules.benchmarks.trial import run_trial
    from schedules.services.ga import Gene, GeneticScheduler
    from schedules.services.time import add_minutes
    def conflicting(ga):
        return [Gene(a.pk, ga.valid_rooms_by_assignment[a.pk][0].pk, 0, time(8),
                     add_minutes(time(8), a.required_duration_minutes)) for a in ga.assignments]
    with patch.object(GeneticScheduler, '_random_chromosome', conflicting):
        result = run_trial(dict(scenario='small', seed=17,
            parameters={dict(PARAMETERS, generations=0)!r}, repair_budget=64))
    print(json.dumps(result))
''')
        self.assertEqual(row['status'], 'FAILED')
        self.assertFalse(row['feasible'])
        self.assertGreater(row['hard_violations'], 0)
        self.assertIsInstance(row['soft_score'], float)
        self.assertEqual(row['generation_statistics'][0]['best_so_far'],
            dict(hard_violations=row['hard_violations'], soft_score=row['soft_score']))
        self.assertEqual(row['reproducibility']['outcome']['best_hard_violations'], row['hard_violations'])
        self.assertIsNone(row['schedule_id'])

    def test_database_cleanup_also_runs_when_migration_fails(self):
        row = child_script('''
import json
from unittest.mock import patch
from schedules.benchmarks.worker import isolated_database
from django.db import connections
with patch.object(connections, 'close_all', wraps=connections.close_all) as close:
    try:
        with patch('django.core.management.call_command', side_effect=RuntimeError('migration test')):
            with isolated_database():
                raise AssertionError('Should never yield')
    except RuntimeError:
        pass
    print(json.dumps({'closed': close.called}))
''')
        self.assertTrue(row['closed'])


class BenchmarkCommandTests(SimpleTestCase):
    def test_command_orders_trials_and_never_queries_parent_database(self):
        # SimpleTestCase forbids SQL on the application's connection.
        output = ROOT / f'benchmark-command-test-{uuid4().hex}.json'
        try:
            with patch('schedules.management.commands.benchmark_ga.run_isolated_trial',
                       return_value={'status': 'SUCCEEDED'}) as worker:
                call_command('benchmark_ga', scenario='all', seeds=[41, 17], output=str(output), stdout=io.StringIO())
            self.assertEqual([(c.args[0], c.args[1]) for c in worker.call_args_list],
                [(scenario, seed) for scenario in ('small', 'medium', 'large', 'infeasible') for seed in (41, 17)])
        finally:
            output.unlink(missing_ok=True)

    def test_invalid_configuration_rejected_before_worker(self):
        for changes in ({'seed': -1}, {'repair_budget': -1}, {'scenario': 'unknown'},
                        {'parameters': {**PARAMETERS, 'population_size': 0}},
                        {'parameters': {**PARAMETERS, 'mutation_rate': float('nan')}},
                        {'parameters': {**PARAMETERS, 'elitism': 4}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_request({**dict(scenario='small', seed=17, parameters=PARAMETERS, repair_budget=64), **changes})

    def test_command_rejects_existing_or_non_export_path(self):
        with patch('schedules.management.commands.benchmark_ga.run_isolated_trial') as worker:
            for path in (ROOT / 'README.md', ROOT / 'never-write.sqlite3'):
                with self.assertRaises(CommandError):
                    call_command('benchmark_ga', output=str(path), stdout=io.StringIO())
            worker.assert_not_called()
