"""Measure the production generation path; callable only inside the worker."""
from datetime import datetime, timezone
import platform
import sqlite3
from time import perf_counter

from .scenarios import SCENARIO_VERSION, build_scenario, require_isolation


def run_trial(request):
    require_isolation()
    from schedules import models as m
    from schedules.services.ga import GeneticScheduler, Gene
    from schedules.services.conflicts import schedule_validation_messages
    from schedules.services.diagnostics import GenerationFailure
    from schedules.services.reproducibility import initial_metadata, fingerprint
    from .runner import validate_request
    validate_request(request)
    started = perf_counter()
    settings = m.GASettings(**request['parameters'])
    settings.full_clean()
    metadata = initial_metadata(request['seed'], settings, request['repair_budget'])
    result = dict(schema='schedease-benchmark-v1', scenario=request['scenario'],
        scenario_version=SCENARIO_VERSION, seed=request['seed'],
        started_at=datetime.now(timezone.utc).isoformat(), completed_at=None,
        status='ERROR', feasible=False, hard_violations=None, soft_score=None,
        validation_outcome='not_run', validation_errors=[], failure_reason=None,
        failure_type=None, diagnostics=[], input_counts=None, input_fingerprint=None,
        parameters=metadata['parameters'], scoring_version=metadata['parameters']['fitness']['version'],
        environment={**metadata['environment'], 'platform': platform.platform(),
                     'database': 'sqlite-memory', 'sqlite': sqlite3.sqlite_version},
        generations_executed=0, generation_statistics=[], repair_statistics={},
        schedule_id=None, schedule_status=None, schedule_fingerprint=None,
        generation_status=None, reproducibility=metadata,
        elapsed_seconds=None, generation_seconds=None)
    ga = None
    term = None
    try:
        term = build_scenario(request['scenario'])
        ga = GeneticScheduler(term, settings, seed=request['seed'], repair_budget=request['repair_budget'])
        result['input_counts'] = ga.input_metadata['counts']
        result['input_fingerprint'] = ga.input_metadata['sha256']
        schedule = ga.generate('Synthetic benchmark draft')
        errors = list(schedule_validation_messages(schedule))
        entries = list(schedule.entries.order_by('assignment_id'))
        measured = ga.fitness([Gene(e.assignment_id, e.room_id, e.day, e.start_time, e.end_time) for e in entries])
        result.update(validation_outcome='failed' if errors else 'passed', validation_errors=errors,
            schedule_id=schedule.pk, schedule_status=schedule.status,
            schedule_fingerprint=fingerprint([(e.assignment_id, e.room_id, e.day,
                e.start_time.isoformat(), e.end_time.isoformat()) for e in entries]))
        result['feasible'] = not errors and measured.hard_violations == 0 and schedule.status == 'DRAFT'
        result['status'] = 'SUCCEEDED' if result['feasible'] else 'FAILED'
        if not result['feasible']:
            result['failure_reason'] = 'Generated schedule did not pass independent benchmark validation.'
    except GenerationFailure as exc:
        result.update(status='FAILED', failure_type=type(exc).__name__, failure_reason=str(exc))
    except Exception as exc:
        # Unexpected failures remain distinct from a search that found no solution.
        result.update(status='ERROR', failure_type=type(exc).__name__,
            failure_reason='Benchmark execution raised an unexpected error; inspect the test environment.')
    finally:
        if ga is not None:
            if ga.best_fitness is not None:
                result.update(hard_violations=ga.best_fitness.hard_violations, soft_score=ga.best_fitness.soft_score)
            result.update(generation_statistics=ga.generation_statistics,
                generations_executed=max(0, len(ga.generation_statistics) - 1),
                repair_statistics=dict(ga.repair_statistics))
        run = m.GenerationRun.objects.filter(term=term).order_by('-started_at').first() if term else None
        if run:
            result['generation_status'] = run.status
            result['reproducibility'] = run.reproducibility
            result['generation_seconds'] = (run.reproducibility.get('outcome') or {}).get('duration_seconds')
            result['diagnostics'] = list(run.issues.order_by('pk').values('category', 'reason', 'details'))
        result['completed_at'] = datetime.now(timezone.utc).isoformat()
        result['elapsed_seconds'] = perf_counter() - started
    return result

