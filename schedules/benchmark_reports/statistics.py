from collections import Counter, defaultdict
import statistics

from .inputs import canonical, digest, require, SCENARIOS


def describe(values):
    values = [v for v in values if v is not None]
    if not values:
        return dict(n=0, mean=None, median=None, min=None, max=None, sample_sd=None)
    return dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values),
                min=min(values), max=max(values), sample_sd=statistics.stdev(values) if len(values) > 1 else None)


def outcome(row):
    if row['completed_at'] is None or row['status'] in ('RUNNING', 'INCOMPLETE'):
        return 'incomplete'
    if row['feasible']:
        return 'feasible'
    if row['status'] == 'FAILED' and (row['failure_type'] == 'GenerationFailure'
            or row['validation_outcome'] == 'failed' or (row['hard_violations'] or 0) > 0):
        return 'infeasible'
    return 'failed'


def group_identity(row):
    key = {k: row[k] for k in ('scenario', 'scenario_version', 'input_fingerprint',
                              'parameters', 'scoring_version', 'environment')}
    # Missing input or execution identity cannot establish comparable experiments.
    if row['input_fingerprint'] is None or any(row['environment'].get(k) is None
            for k in ('python', 'django', 'ga_source_sha256', 'platform')):
        key['unverified_identity'] = [row['seed'], row['started_at']]
    return key


def summarize(rows, sources):
    unique, counts_by_input, duplicate_count = {}, {}, 0
    for row in rows:
        group = group_identity(row)
        identity = canonical([group, row['seed'], row['started_at']])
        if identity in unique:
            require(unique[identity] == row, 'Conflicting duplicate trial: same experiment, seed and start time but different metrics. Correct the source exports.')
            duplicate_count += 1
            continue
        unique[identity] = row
        if row['input_fingerprint'] is not None:
            key = row['input_fingerprint']
            require(key not in counts_by_input or counts_by_input[key] == row['input_counts'], 'Identical input fingerprints have inconsistent workload counts.')
            counts_by_input[key] = row['input_counts']
    buckets = defaultdict(list)
    for row in unique.values():
        buckets[canonical(group_identity(row))].append(row)
    groups = []
    for key, trials in sorted(buckets.items()):
        trials.sort(key=lambda r: (r['seed'], r['started_at']))
        first = trials[0]
        identity = group_identity(first)
        group = {**identity, 'group_id': 'g-' + digest(identity)[:12], 'input_counts': first['input_counts']}
        group['family_id'] = 'f-' + digest({k: first[k] for k in (
            'scenario_version', 'parameters', 'scoring_version', 'environment')})[:12]
        classified = Counter(outcome(r) for r in trials)
        completed = [r for r in trials if outcome(r) != 'incomplete']
        feasible = [r for r in trials if outcome(r) == 'feasible']
        validated = [r for r in completed if r['validation_outcome'] in ('passed', 'failed')]
        group.update(total_trials=len(trials), distinct_seeds=len({r['seed'] for r in trials}),
            seeds=sorted({r['seed'] for r in trials}), completed_trials=len(completed),
            outcomes={k: classified[k] for k in ('feasible', 'infeasible', 'failed', 'incomplete')},
            feasibility_percent=100 * len(feasible) / len(completed) if completed else None,
            validation_trials=len(validated), validation_success_percent=(
                100 * sum(r['validation_outcome'] == 'passed' for r in validated) / len(validated) if validated else None),
            hard_violations=describe(r['hard_violations'] for r in completed),
            soft_score_feasible=describe(r['soft_score'] for r in feasible),
            runtime_seconds=describe(r['elapsed_seconds'] for r in completed),
            runtime_feasible_seconds=describe(r['elapsed_seconds'] for r in feasible),
            runtime_nonfeasible_seconds=describe(r['elapsed_seconds'] for r in completed if not r['feasible']),
            generation_seconds=describe(r['generation_seconds'] for r in completed),
            worker_wall_seconds=describe(r['worker_wall_seconds'] for r in completed),
            generations_executed=describe(r['generations_executed'] for r in completed),
            repair_attempts=describe(r['repair_statistics'].get('attempts') for r in completed),
            repair_moves=describe(r['repair_statistics'].get('moves') for r in completed),
            trials=[{**r, 'outcome': outcome(r)} for r in trials])
        group['per_seed'] = [dict(seed=seed, trials=sum(r['seed'] == seed for r in trials),
            soft_score_feasible=describe(r['soft_score'] for r in feasible if r['seed'] == seed),
            runtime_seconds=describe(r['elapsed_seconds'] for r in completed if r['seed'] == seed)) for seed in group['seeds']]
        group['soft_score_seed_means'] = describe(s['soft_score_feasible']['mean'] for s in group['per_seed'])
        group['insufficient_seeds'] = group['distinct_seeds'] < 3
        groups.append(group)
    return dict(schema='schedease-evaluation-v1', sources=sources, input_trials=len(rows),
        duplicates_removed=duplicate_count, total_trials=len(unique), groups=groups,
        scenario_coverage={s: 'Evaluated' if any(g['scenario'] == s and g['completed_trials'] for g in groups)
                           else 'Not Evaluated' for s in SCENARIOS})
