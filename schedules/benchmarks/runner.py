"""Parent process has no model imports or database access."""
from schedules.services import csv_export
import io
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from .scenarios import SCENARIOS

DEFAULT_SEEDS = (17, 41, 73)
DEFAULT_PARAMETERS = dict(population_size=12, generations=10, mutation_rate=0.08,
                          crossover_rate=0.85, elitism=2)


def validate_request(request):
    if request['scenario'] not in SCENARIOS:
        raise ValueError('Unknown benchmark scenario.')
    if type(request['seed']) is not int or not 0 <= request['seed'] < 2**63:
        raise ValueError('Seeds must be integers from 0 through 2^63-1.')
    if type(request['repair_budget']) is not int or request['repair_budget'] < 0:
        raise ValueError('Repair budget must be a non-negative integer.')
    p = request['parameters']
    if set(p) != set(DEFAULT_PARAMETERS):
        raise ValueError('Supply exactly the supported GA parameters.')
    for key in ('population_size', 'generations', 'elitism'):
        if type(p[key]) is not int or p[key] < (1 if key == 'population_size' else 0):
            raise ValueError(f'{key} is outside its supported range.')
    if p['elitism'] >= p['population_size']:
        raise ValueError('Elitism must be smaller than population size.')
    for key in ('mutation_rate', 'crossover_rate'):
        if not isinstance(p[key], (int, float)) or not math.isfinite(p[key]) or not 0 <= p[key] <= 1:
            raise ValueError(f'{key} must be between 0 and 1.')


def run_isolated_trial(scenario, seed, parameters=None, repair_budget=64):
    request = dict(scenario=scenario, seed=seed, parameters=dict(
        DEFAULT_PARAMETERS if parameters is None else parameters), repair_budget=repair_budget)
    validate_request(request)
    started = perf_counter()
    completed = subprocess.run([sys.executable, '-m', 'schedules.benchmarks.worker'],
        cwd=Path(__file__).resolve().parents[2], input=json.dumps(request),
        text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError('Isolated benchmark worker failed before exporting a trial. '
                           'No application database was used.\n' + completed.stderr[-4000:])
    result = json.loads(completed.stdout)
    result['worker_wall_seconds'] = perf_counter() - started
    return result


def export_results(rows, path):
    """Exclusive creation prevents replacing existing reports or database files."""
    path = Path(path)
    if path.suffix.lower() == '.json':
        content = json.dumps({'schema': 'schedease-benchmark-v1', 'trials': rows},
                             sort_keys=True, indent=2, allow_nan=False) + '\n'
    elif path.suffix.lower() == '.csv':
        buffer = io.StringIO(newline='')
        writer = csv_export.DictWriter(buffer, fieldnames=sorted(rows[0]) if rows else [])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True, allow_nan=False)
                if isinstance(value, (dict, list, bool)) else value for key, value in row.items()})
        content = buffer.getvalue()
    else:
        raise ValueError('Output must end in .json or .csv.')
    with path.open('x', encoding='utf-8', newline='') as target:
        target.write(content)
