"""Artificial result fixtures for arithmetic contracts, NOT experimental findings."""
from copy import deepcopy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
from uuid import uuid4
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .benchmarks.runner import export_results
from .benchmark_reports.inputs import load_files, normalize, ReportInputError, SCHEMA
from .benchmark_reports.statistics import describe, summarize
from .benchmark_reports.report import generate_report
from .models import GASettings
from .services.reproducibility import effective_parameters

ROOT = Path(__file__).resolve().parent.parent
STAMP = '2026-01-01T00:00:00+00:00'


def fixture(seed=1, **changes):
    row = dict(schema=SCHEMA, scenario='small', scenario_version='synthetic-v1', seed=seed,
        parameters=effective_parameters(GASettings(population_size=4, generations=2, elitism=1), 64),
        scoring_version='hard-first-v2', environment=dict(python='3.12.10', django='5.0.6',
            platform='test-platform', ga_source_sha256='a'*64), input_fingerprint='b'*64,
        input_counts={'meetings': 12}, status='SUCCEEDED', feasible=True, hard_violations=0,
        soft_score=10.0, elapsed_seconds=1.0, generation_seconds=.5, worker_wall_seconds=2.0,
        generations_executed=2, generation_statistics=[], repair_statistics={'attempts': 3, 'moves': 1},
        started_at=STAMP, completed_at='2026-01-01T00:01:00+00:00',
        validation_outcome='passed', validation_errors=[], failure_type=None, diagnostics=[])
    row.update(changes)
    return row


class ReportingTests(SimpleTestCase):
    def setUp(self):
        self.directory = ROOT / ('report-test-' + uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        assert self.directory.resolve().parent == ROOT.resolve()
        shutil.rmtree(self.directory)

    def write(self, rows, name='input.json'):
        path = self.directory / name
        export_results(rows, path)
        return path

    def summary(self, rows):
        return summarize([normalize(r) for r in rows], [])

    def test_json_csv_equivalence_and_multiple_files(self):
        rows = [fixture(), fixture(2, soft_score=20, elapsed_seconds=3)]
        a, b = self.write(rows), self.write(rows, 'input.csv')
        x, _ = load_files([a]); y, _ = load_files([b])
        self.assertEqual(x, y)
        imported, sources = load_files([a, b])
        report = summarize(imported, sources)
        self.assertEqual(report['input_trials'], 4)
        self.assertEqual(report['duplicates_removed'], 2)
        self.assertEqual(report['total_trials'], 2)

    def test_identical_file_path_is_read_once(self):
        a = self.write([fixture()])
        rows, sources = load_files([a, a])
        self.assertEqual((len(rows), len(sources)), (1, 1))

    def test_conflicting_duplicates_are_rejected(self):
        with self.assertRaisesRegex(ReportInputError, 'Conflicting duplicate'):
            self.summary([fixture(), fixture(soft_score=12)])

    def test_repeated_seeds_are_repetitions_not_independent_seeds(self):
        report = self.summary([fixture(), fixture(started_at='2026-01-01T00:00:01Z', soft_score=30), fixture(2, soft_score=60)])
        g = report['groups'][0]
        self.assertEqual((g['total_trials'], g['distinct_seeds']), (3, 2))
        self.assertEqual(g['per_seed'][0]['soft_score_feasible']['mean'], 20)
        self.assertEqual(g['soft_score_seed_means']['mean'], 40)
        self.assertAlmostEqual(g['soft_score_seed_means']['sample_sd'], math.sqrt(800))

    def test_known_runtime_and_soft_statistics(self):
        g = self.summary([fixture(), fixture(2, soft_score=20, elapsed_seconds=3)])['groups'][0]
        self.assertEqual(g['runtime_seconds'], dict(n=2, mean=2, median=2, min=1, max=3, sample_sd=math.sqrt(2)))
        self.assertEqual(g['soft_score_feasible']['mean'], 15)
        self.assertAlmostEqual(g['soft_score_feasible']['sample_sd'], math.sqrt(50))
        self.assertEqual(g['repair_attempts']['mean'], 3)
        self.assertEqual(g['generations_executed']['mean'], 2)

    def test_rates_separate_infeasible_error_and_incomplete(self):
        failed = fixture(2, status='FAILED', feasible=False, validation_outcome='failed',
                         hard_violations=2, soft_score=1000, failure_type='GenerationFailure')
        error = fixture(3, status='ERROR', feasible=False, validation_outcome='not_run', hard_violations=None, soft_score=None)
        unfinished = fixture(4, status='RUNNING', feasible=False, validation_outcome='not_run', completed_at=None,
                             hard_violations=None, soft_score=None, elapsed_seconds=None)
        g = self.summary([fixture(), failed, error, unfinished])['groups'][0]
        self.assertEqual(g['outcomes'], dict(feasible=1, infeasible=1, failed=1, incomplete=1))
        self.assertAlmostEqual(g['feasibility_percent'], 100/3)
        self.assertEqual(g['validation_success_percent'], 50)
        self.assertEqual(g['validation_trials'], 2)
        self.assertEqual(g['soft_score_feasible']['mean'], 10)  # Exclude invalid candidate's 1000.
        self.assertEqual(g['hard_violations']['mean'], 1)
        self.assertEqual(g['runtime_seconds']['n'], 3)

    def test_preflight_failure_missing_metrics_not_zero(self):
        r = fixture(status='FAILED', feasible=False, validation_outcome='not_run', hard_violations=None,
                    soft_score=None, failure_type='GenerationFailure', elapsed_seconds=None)
        g = self.summary([r])['groups'][0]
        self.assertEqual(g['feasibility_percent'], 0)
        self.assertIsNone(g['validation_success_percent'])
        self.assertEqual(g['soft_score_feasible']['n'], 0)
        self.assertIsNone(g['hard_violations']['mean'])
        self.assertIsNone(g['runtime_seconds']['mean'])

    def test_empty_single_and_only_incomplete(self):
        self.assertEqual(describe([])['n'], 0)
        self.assertIsNone(describe([None])['mean'])
        self.assertIsNone(describe([5])['sample_sd'])
        self.assertEqual(describe([5])['mean'], 5)
        self.assertEqual(self.summary([])['scenario_coverage']['small'], 'Not Evaluated')
        r = fixture(status='INCOMPLETE', feasible=False, validation_outcome='not_run', completed_at=None)
        g = self.summary([r])['groups'][0]
        self.assertIsNone(g['feasibility_percent'])

    def test_configuration_fingerprint_version_and_environment_separate_groups(self):
        base = fixture()
        rows = [base]
        for field, value in [('input_fingerprint', 'c'*64), ('scenario', 'medium'), ('scenario_version', 'synthetic-v2')]:
            rows.append(fixture(**{field: value}))
        configured = fixture(); configured['parameters']['population_size'] = 8; rows.append(configured)
        scored = fixture(scoring_version='hard-first-v1'); scored['parameters']['fitness']['version'] = 'hard-first-v1'; rows.append(scored)
        environment = fixture(); environment['environment']['python'] = '3.13.0'; rows.append(environment)
        self.assertEqual(len(self.summary(rows)['groups']), 7)

    def test_missing_identity_keeps_trials_separate(self):
        rows = [fixture(i) for i in (1, 2)]
        for row in rows:
            row['environment'].pop('ga_source_sha256')
        self.assertEqual(len(self.summary(rows)['groups']), 2)

    def test_same_fingerprint_inconsistent_counts_rejected(self):
        with self.assertRaisesRegex(ReportInputError, 'inconsistent workload counts'):
            self.summary([fixture(), fixture(2, input_counts={'meetings': 50})])

    def test_schema_required_fields_and_numeric_errors(self):
        for update in ({'schema': 'unknown-v3'}, {'seed': True}, {'elapsed_seconds': -1},
                       {'soft_score': float('inf')}, {'hard_violations': .5}, {'feasible': 'yes'},
                       {'input_counts': {'meetings': -1}}, {'input_fingerprint': 'wrong'},
                       {'started_at': 'yesterday'}, {'completed_at': '2025-01-01T00:00:00Z'},
                       {'generations_executed': 3}, {'generation_statistics': [{'generation': 1}]},
                       {'repair_statistics': []}, {'generation_statistics': {}}, {'reproducibility': []}, {'diagnostics': {}}):
            with self.subTest(update=update), self.assertRaises(ReportInputError):
                normalize(fixture(**update))
        raw = fixture(); del raw['parameters']
        with self.assertRaisesRegex(ReportInputError, 'Missing required'):
            normalize(raw)

    def test_contradictory_success_and_metadata_rejected(self):
        for update in ({'hard_violations': 1}, {'feasible': False}, {'validation_outcome': 'failed'},
                       {'validation_errors': ['bad']}, {'reproducibility': {'inputs': {'sha256': 'wrong'}}},
                       {'reproducibility': {'seed': 15}}, {'reproducibility': {'outcome': {'best_soft_score': 999}}}):
            with self.subTest(update=update), self.assertRaises(ReportInputError):
                normalize(fixture(**update))

    def test_generation_statistics_must_agree_with_final_metrics(self):
        stats = [dict(generation=0, population_best=dict(hard_violations=0, soft_score=10),
                      best_so_far=dict(hard_violations=0, soft_score=10))]
        row = fixture(generation_statistics=stats, generations_executed=0)
        self.assertEqual(normalize(row)['soft_score'], 10)
        for change in ({'soft_score': 11}, {'generations_executed': 1}):
            with self.assertRaises(ReportInputError):
                normalize({**row, **change})

    def test_malformed_files_have_actionable_error(self):
        for name, content in [('bad.json', '{'), ('double.json', '{"schema":1,"schema":2}'),
                              ('nan.json', '{"x":NaN}'), ('bad.csv', 'scenario,scenario\nsmall,small'),
                              ('missing.csv', 'seed\n1')]:
            path = self.directory / name; path.write_text(content)
            with self.subTest(name=name), self.assertRaisesRegex(ReportInputError, name):
                load_files([path])

    def test_outputs_labels_partial_coverage_and_known_values(self):
        source = self.write([fixture(), fixture(2, elapsed_seconds=3, soft_score=20)])
        target = self.directory / 'report'
        report = generate_report([source], target, generated_at=STAMP)
        text = (target / 'report.md').read_text(encoding='utf-8')
        for phrase in ('medium | Not Evaluated', 'large | Not Evaluated', 'Sample SD', 'Insufficient sample size',
                       'hard-first-v2', 'input fingerprint', 'test-platform', 'no hardware details are inferred'):
            self.assertIn(phrase, text)
        self.assertEqual(len(report['charts']), 3)
        for chart in report['charts']:
            self.assertTrue((target / chart['pdf']).read_bytes().startswith(b'%PDF'))
            self.assertIn('<svg', (target / chart['svg']).read_text())
        svg = ''.join((target / c['svg']).read_text() for c in report['charts'])
        for label in ('Mean runtime (seconds)', 'Feasible / completed trials (%)', 'Random seed', 'higher is better'):
            self.assertIn(label, svg)
        with (target / 'summary.csv').open(newline='') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(float(row['runtime_seconds_mean']), 2)
        self.assertEqual(json.loads((target / 'summary.json').read_text())['groups'][0]['soft_score_feasible']['mean'], 15)

    def test_workload_chart_requires_measured_comparable_sizes(self):
        rows = [fixture(), fixture(2)]
        rows += [fixture(i, scenario='medium', input_fingerprint='c'*64, input_counts={'meetings': 72}) for i in (1, 2)]
        report = generate_report([self.write(rows)], self.directory / 'multi', generated_at=STAMP)
        workload = [c for c in report['charts'] if '-workload' in c['svg']]
        self.assertEqual(len(workload), 1)
        svg = (self.directory / 'multi' / workload[0]['svg']).read_text()
        self.assertIn('small (12)', svg); self.assertIn('medium (72)', svg)
        self.assertEqual(report['scenario_coverage']['large'], 'Not Evaluated')

    def test_single_trial_and_empty_reports_omit_charts(self):
        repeated_with_incomplete_seed = [fixture(), fixture(started_at='2026-01-01T00:00:01Z'),
            fixture(2, status='RUNNING', feasible=False, completed_at=None, validation_outcome='not_run')]
        for index, rows in enumerate(([fixture()], [], repeated_with_incomplete_seed)):
            report = generate_report([self.write(rows, f'{index}.json')], self.directory / str(index))
            self.assertEqual(report['charts'], [])
            self.assertTrue(report['chart_notes'])

    def test_deterministic_content_with_fixed_timestamp_and_input_order(self):
        a = self.write([fixture()], 'a.json'); b = self.write([fixture(2)], 'b.json')
        first, second = self.directory / 'one', self.directory / 'two'
        generate_report([a, b], first, generated_at=STAMP)
        generate_report([b, a], second, generated_at=STAMP)
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes(), path.name)

    def test_inputs_unchanged_no_database_or_benchmark_execution(self):
        source = self.write([fixture(), fixture(2)])
        before = hashlib.sha256(source.read_bytes()).digest()
        # SimpleTestCase rejects database queries; also forbid launching benchmark workers.
        with patch('subprocess.run', side_effect=AssertionError('Reporting must not execute experiments')):
            call_command('report_ga_benchmarks', str(source), output=str(self.directory / 'report'), stdout=io.StringIO())
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), before)

    def test_privacy_excludes_free_text_and_unknown_environment_fields(self):
        row = fixture(failure_reason='PRIVATE STUDENT', validation_errors=[])
        row['environment']['username'] = 'PRIVATE STUDENT'
        row['diagnostics'] = [{'category': 'INVALID_DATA', 'reason': 'PRIVATE STUDENT', 'details': {'name': 'PRIVATE STUDENT'}}]
        row['student_name'] = 'PRIVATE STUDENT'
        target = self.directory / 'report'
        generate_report([self.write([row])], target)
        for path in target.iterdir():
            self.assertNotIn(b'PRIVATE STUDENT', path.read_bytes())

    def test_command_rejects_bad_inputs_without_partial_output(self):
        target = self.directory / 'report'
        source = self.write([fixture(schema='future')])
        with self.assertRaises(CommandError):
            call_command('report_ga_benchmarks', str(source), output=str(target), stdout=io.StringIO())
        self.assertFalse(target.exists())

    def test_existing_directory_preserved_and_render_failure_cleaned(self):
        source = self.write([fixture(), fixture(2)])
        with self.assertRaises(ReportInputError):
            generate_report([source], self.directory)
        target = self.directory / 'report'
        with patch('schedules.benchmark_reports.report.write_charts', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                generate_report([source], target)
        self.assertFalse(target.exists())
