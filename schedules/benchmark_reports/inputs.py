import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re

SCHEMA = 'schedease-benchmark-v1'
SCENARIOS = ('small', 'medium', 'large', 'infeasible')
REQUIRED = {'schema', 'scenario', 'scenario_version', 'seed', 'parameters', 'scoring_version',
            'environment', 'status', 'feasible', 'validation_outcome', 'started_at', 'input_fingerprint', 'input_counts'}
NUMBERS = ('hard_violations', 'soft_score', 'elapsed_seconds', 'generation_seconds',
           'worker_wall_seconds', 'generations_executed')
STRUCTURED = ('parameters', 'environment', 'input_counts', 'generation_statistics',
              'repair_statistics', 'diagnostics', 'reproducibility', 'validation_errors')
CONFIG_KEYS = set('population_size generations mutation_rate crossover_rate elitism selection tournament_size tie_break repair_attempt_limit slot_minutes availability_boundary_starts fitness'.split())
FITNESS_KEYS = set('version ordering base_score preferred_period_bonus capacity_gap_weight excess_capacity_penalty wrong_non_special_room_penalty daily_class_threshold extra_daily_class_penalty whole_hour_gap_threshold whole_hour_gap_weight faculty_idle_gap_unit faculty_idle_gap_hour_weight faculty_idle_gap_method section_whole_hour_gap_threshold section_whole_hour_gap_weight day_spread_weight day_spread_scope day_spread_days room_hours_deviation_weight unused_suitable_room_penalty unused_required_type_room_penalty'.split())
ENV_KEYS = ('python', 'django', 'implementation', 'platform', 'database', 'sqlite',
            'ga_source_sha256', 'processor', 'architecture', 'cpu_count', 'memory_bytes')
COUNT_KEYS = set('assignments meetings faculty rooms sections courses faculty_availability_periods room_availability_periods faculty_credentials credential_requirements accepted_equivalents credential_overrides eligible_meetings required_minutes'.split())


class ReportInputError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field; correct the source export.')
            result[key] = value
        return result
    def constant(value):
        raise ReportInputError('Non-finite JSON numbers are not supported; use null for missing metrics.')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ReportInputError(message)


def number(value, name, *, integer=False, nonnegative=True):
    if value is None:
        return None
    require(type(value) in (int, float) and math.isfinite(value), f'{name}: use a finite number or null.')
    require(not integer or type(value) is int, f'{name}: use a whole number.')
    require(not nonnegative or value >= 0, f'{name}: cannot be negative.')
    return value


def timestamp(value, name):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None, f'{name}: include a UTC offset.')
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, AttributeError, TypeError) as exc:
        raise ReportInputError(f'{name}: use an ISO-8601 timestamp with UTC offset.') from exc


def token(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', value),
            f'{name}: expected a version/name token.')
    return value


def safe_configuration(value, keys, name):
    require(isinstance(value, dict), f'{name}: expected an object.')
    require(not set(value) - keys, f'{name}: unsupported parameter fields; use a compatible benchmark export.')
    for key, item in value.items():
        if key == 'fitness':
            safe_configuration(item, FITNESS_KEYS, 'fitness')
        elif isinstance(item, list):
            require(all(type(v) is int or isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', v) for v in item), f'{name}.{key}: invalid list.')
        elif isinstance(item, str):
            token(item, f'{name}.{key}')
        elif type(item) is not bool:
            require(item is not None, f'{name}.{key}: missing parameter.')
            number(item, f'{name}.{key}', nonnegative=False)
    return value


def normalize(raw):
    require(isinstance(raw, dict), 'Each trial must be an object.')
    required = REQUIRED
    require(required <= set(raw), 'Missing required fields: ' + ', '.join(sorted(required - set(raw))))
    require(raw['schema'] == SCHEMA, f'Unsupported schema; expected {SCHEMA}.')
    require(raw['scenario'] in SCENARIOS, 'Unknown scenario; expected small, medium, large or infeasible.')
    row = {k: raw[k] for k in required}
    token(row['scenario_version'], 'scenario_version')
    token(row['scoring_version'], 'scoring_version')
    require(type(row['seed']) is int and 0 <= row['seed'] < 2**63, 'seed: expected an integer from 0 to 2^63-1.')
    safe_configuration(row['parameters'], CONFIG_KEYS, 'parameters')
    p = row['parameters']
    require({'population_size', 'generations', 'elitism', 'crossover_rate', 'mutation_rate', 'fitness'} <= set(p), 'parameters: missing GA settings or fitness formula.')
    for key in ('population_size', 'generations', 'elitism'):
        number(p[key], key, integer=True)
    require(p['population_size'] > 0 and p['elitism'] < p['population_size'], 'parameters: invalid population/elitism.')
    for key in ('crossover_rate', 'mutation_rate'):
        require(type(p[key]) in (float, int) and 0 <= p[key] <= 1, f'{key}: must be between 0 and 1.')
    require(p['fitness'].get('version') == row['scoring_version'], 'scoring_version differs from parameters.fitness.version.')
    require(isinstance(row['environment'], dict), 'environment: expected an object.')
    row['environment'] = {k: row['environment'].get(k) for k in ENV_KEYS}
    for key, value in row['environment'].items():
        if value is None:
            continue
        if key in ('cpu_count', 'memory_bytes'):
            number(value, f'environment.{key}', integer=True)
        else:
            require(isinstance(value, str) and len(value) <= 250 and not any(c in value for c in '\n\r<>`'), f'environment.{key}: invalid text.')
    for key in ('input_fingerprint',):
        require(row[key] is None or isinstance(row[key], str) and re.fullmatch('[0-9a-f]{64}', row[key]), f'{key}: expected SHA-256 or null.')
    source_hash = row['environment'].get('ga_source_sha256')
    require(source_hash is None or re.fullmatch('[0-9a-f]{64}', source_hash), 'ga_source_sha256: expected SHA-256 or null.')
    counts = row['input_counts']
    if counts is not None:
        require(isinstance(counts, dict) and 'meetings' in counts, 'input_counts: expected an object with meetings.')
        require(not set(counts) - COUNT_KEYS, 'input_counts: unsupported fields.')
        for key, value in counts.items():
            require(value is not None, f'input_counts.{key}: missing count.')
            number(value, f'input_counts.{key}', integer=True)
    require(row['status'] in ('SUCCEEDED', 'FAILED', 'ERROR', 'RUNNING', 'INCOMPLETE'), 'status: unknown outcome.')
    require(type(row['feasible']) is bool, 'feasible: use true or false.')
    require(row['validation_outcome'] in ('passed', 'failed', 'not_run'), 'validation_outcome: expected passed, failed or not_run.')
    row['started_at'] = timestamp(row['started_at'], 'started_at')
    require(row['started_at'] is not None, 'started_at is required to identify duplicate trials.')
    row['completed_at'] = timestamp(raw.get('completed_at'), 'completed_at')
    require(row['completed_at'] is None or row['completed_at'] >= row['started_at'], 'completed_at precedes started_at.')
    for key in NUMBERS:
        row[key] = number(raw.get(key), key, integer=key in ('hard_violations', 'generations_executed'), nonnegative=key != 'soft_score')
    require(row['generations_executed'] is None or row['generations_executed'] <= p['generations'], 'generations_executed exceeds the configured budget.')
    if row['status'] == 'SUCCEEDED':
        require(row['feasible'] and row['hard_violations'] == 0 and row['validation_outcome'] == 'passed'
                and row['completed_at'] is not None and row['input_fingerprint'] is not None and counts is not None,
                'SUCCEEDED requires feasible=true, zero hard violations, passed validation, completion time and inputs.')
        require(not raw.get('validation_errors'), 'A successful validation cannot contain errors.')
    else:
        require(not row['feasible'], 'Only SUCCEEDED trials may be feasible.')
    if row['status'] in ('RUNNING', 'INCOMPLETE'):
        require(row['completed_at'] is None, 'An incomplete trial cannot have a completion timestamp.')
    row['repair_statistics'] = {} if raw.get('repair_statistics') is None else raw['repair_statistics']
    require(isinstance(row['repair_statistics'], dict), 'repair_statistics: expected an object.')
    # Only numeric counters are exported; free-text diagnostic content is excluded.
    for key, value in row['repair_statistics'].items():
        token(key, 'repair statistic name')
        require(value is not None, 'repair_statistics: missing counter.')
        number(value, 'repair_statistics.' + key, integer=True)
    row['generation_statistics'] = [] if raw.get('generation_statistics') is None else raw['generation_statistics']
    require(isinstance(row['generation_statistics'], list), 'generation_statistics: expected a list.')
    for item in row['generation_statistics']:
        require(isinstance(item, dict) and set(item) == {'generation', 'population_best', 'best_so_far'}, 'generation_statistics: invalid record.')
        require(item['generation'] is not None, 'generation: missing index.')
        number(item['generation'], 'generation', integer=True)
        for key in ('population_best', 'best_so_far'):
            require(isinstance(item[key], dict) and set(item[key]) == {'hard_violations', 'soft_score'}, f'{key}: invalid fitness record.')
            require(all(v is not None for v in item[key].values()), f'{key}: missing evaluated fitness.')
            number(item[key]['hard_violations'], key, integer=True)
            number(item[key]['soft_score'], key, nonnegative=False)
    stats = row['generation_statistics']
    if stats:
        require([s['generation'] for s in stats] == list(range(len(stats))), 'generation_statistics: indices must start at zero and increase consecutively.')
        require(row['generations_executed'] is None or row['generations_executed'] == stats[-1]['generation'], 'Generation count disagrees with the recorded statistics.')
        for key in ('hard_violations', 'soft_score'):
            require(row[key] is None or row[key] == stats[-1]['best_so_far'][key], f'{key} disagrees with the final generation statistic.')
    diagnostics = [] if raw.get('diagnostics') is None else raw['diagnostics']
    require(isinstance(diagnostics, list) and all(isinstance(d, dict) for d in diagnostics), 'diagnostics: expected a list of objects.')
    row['diagnostic_categories'] = sorted({token(d.get('category'), 'diagnostic category') for d in diagnostics})
    row['failure_type'] = token(raw['failure_type'], 'failure_type') if raw.get('failure_type') else None
    metadata = {} if raw.get('reproducibility') is None else raw['reproducibility']
    require(isinstance(metadata, dict), 'reproducibility: expected an object.')
    if metadata.get('parameters') is not None:
        require(metadata['parameters'] == p, 'Reproducibility parameters disagree with the trial.')
    if metadata.get('inputs') is not None:
        require(isinstance(metadata['inputs'], dict) and metadata['inputs'].get('sha256') == row['input_fingerprint'], 'Reproducibility input fingerprint disagrees with the trial.')
        if metadata['inputs'].get('counts') is not None and counts is not None:
            require(metadata['inputs']['counts'] == counts, 'Reproducibility counts disagree with the trial.')
    if metadata.get('seed') is not None:
        require(metadata['seed'] == row['seed'], 'Reproducibility seed disagrees with the trial.')
    recorded = metadata.get('outcome')
    if recorded is not None:
        require(isinstance(recorded, dict), 'reproducibility.outcome: expected an object.')
        for key in ('hard_violations', 'soft_score'):
            value = recorded.get('best_' + key)
            require(value is None or row[key] is None or value == row[key], f'{key} disagrees with reproducibility metadata.')
    return row


def load_files(paths):
    rows, sources = [], []
    for path in sorted({Path(p).resolve() for p in paths}, key=str):
        try:
            data = path.read_bytes()
            text = data.decode('utf-8-sig')
            if path.suffix.lower() == '.json':
                payload = strict_json(text)
                require(isinstance(payload, dict) and payload.get('schema') == SCHEMA and isinstance(payload.get('trials'), list), 'Expected a benchmark schema and trials list.')
                records = payload['trials']
            elif path.suffix.lower() == '.csv':
                reader = csv.DictReader(io.StringIO(text))
                require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), 'CSV needs unique column headers.')
                require(REQUIRED <= set(reader.fieldnames), 'CSV is missing required benchmark columns.')
                records = []
                for raw in reader:
                    require(None not in raw and all(v is not None for v in raw.values()), 'CSV row does not match its header.')
                    for key in (*STRUCTURED, *NUMBERS, 'seed', 'feasible'):
                        if key in raw:
                            raw[key] = strict_json(raw[key]) if raw[key] else None
                    for key, value in raw.items():
                        if value == '':
                            raw[key] = None
                    records.append(raw)
            else:
                raise ReportInputError('Use .json or .csv benchmark exports.')
            for index, raw in enumerate(records, 1):
                try:
                    rows.append(normalize(raw))
                except (ReportInputError, TypeError, KeyError, AttributeError) as exc:
                    raise ReportInputError(f'Trial {index}: {exc}') from exc
            sources.append(dict(sha256=hashlib.sha256(data).hexdigest(), format=path.suffix.lower()[1:], trials=len(records)))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise ReportInputError(f'{path.name}: {exc}') from exc
    return rows, sorted(sources, key=canonical)
