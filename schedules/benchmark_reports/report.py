import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from .charts import write_charts
from .inputs import load_files, require
from .statistics import summarize


def display(value):
    return 'Not Available' if value is None else f'{value:.6g}' if isinstance(value, float) else str(value)


def markdown(report):
    lines = ['# SchedEase GA evaluation report', '',
        f"Report generated (UTC): {report['generated_at']}", '',
        '## Objectives and methodology', '',
        'Evaluate observed scheduling feasibility, feasible-schedule quality and execution time using existing benchmark exports. '
        'This report does not execute the GA or access the scheduling database.', '',
        'Each Task 5.3 trial uses the production GA in a fresh in-memory SQLite worker. '
        'Fitness uses hard-first ranking; soft scores are compared only within identical input/configuration/scoring/environment groups. '
        'Input SHA-256 fingerprints, source identity and seeds identify experiments; elapsed times are measured, not estimated.', '',
        '## Data coverage', '',
        f"Imported records: {report['input_trials']}; duplicate copies removed: {report['duplicates_removed']}; retained trials: {report['total_trials']}.", '',
        '| Scenario | Coverage |', '| --- | --- |']
    lines.extend(f'| {name} | {state} |' for name, state in report['scenario_coverage'].items())
    lines += ['', 'Not Evaluated means no completed trial was supplied; it is not a zero score or zero runtime.', '',
        '### Scenario definitions', '',
        'For synthetic-v1, small/medium/large contain 12/72/216 meetings respectively. Each assignment contains two '
        '60-minute lectures and one 120-minute computer laboratory. Faculty qualifications cover the fixed 2026 term. '
        'Explicit weekday availability, room lunch closures, faculty blocked/preferred periods, capacities and room types constrain placement. '
        'The infeasible fixture deliberately has undersized laboratories. These are synthetic scenarios, not measured school workloads. '
        'Other fixture versions require their own definition; observed counts are shown below.', '',
        '## Statistical methods', '',
        '- Group identity: scenario/version, input fingerprint, complete GA parameters, scoring version and recorded execution environment (including GA source hash). Unknown identities are kept separate.',
        '- Duplicate identity: group + seed + UTC start timestamp. Identical copies count once; conflicting copies are rejected. Different timestamps retain repeated runs of a seed.',
        '- Feasibility rate = 100 × feasible trials / completed trials, including completed execution errors in the denominator. Incomplete trials are excluded and counted separately.',
        '- Validation success rate = 100 × passed final validations / actually performed final validations. Preflight failures are not validated schedules.',
        '- Mean = sum(x)/n; median = middle ordered value (or mean of the central pair). Sample standard deviation = sqrt(sum((x − mean)^2)/(n − 1)); undefined for n < 2.',
        '- Missing values are omitted, never replaced with zero. Every metric includes its own n. Soft-score statistics use feasible trials only; per-seed means distinguish repetitions from independent seeds.',
        '- Trial runtime (seconds) includes fixture construction, scheduler preparation, generation and independent validation; excludes migrations and export. Generation and worker-wall timings are reported separately.',
        '- Infeasible outcome means the search/validation produced no valid schedule; it does not prove mathematical infeasibility. Unexpected execution failures and unfinished trials are separate outcomes.', '',
        '## Summary by comparable experiment', '',
        '| Group | Scenario | Meetings | Trials / seeds | Feasible / infeasible / failed / incomplete | Feasible % | Validation % (n) |',
        '| --- | --- | ---: | --- | --- | ---: | --- |']
    for g in report['groups']:
        o = g['outcomes']
        lines.append(f"| {g['group_id']} | {g['scenario']} | {display((g['input_counts'] or {}).get('meetings'))} | "
            f"{g['total_trials']} / {g['distinct_seeds']} | {o['feasible']} / {o['infeasible']} / {o['failed']} / {o['incomplete']} | "
            f"{display(g['feasibility_percent'])} | {display(g['validation_success_percent'])} ({g['validation_trials']}) |")
    if not report['groups']:
        lines += ['', 'No trials supplied. All statistics are unavailable; no charts can be inferred.']
    for g in report['groups']:
        lines += ['', f"### {g['group_id']} — {g['scenario']}", '',
            f"Fixture version: `{g['scenario_version']}`; input fingerprint: `{g['input_fingerprint'] or 'Not Available'}`.",
            f"Scoring version: `{g['scoring_version']}`. Seeds: {', '.join(map(str, g['seeds']))}.", '',
            'Effective configuration:', '```json', json.dumps(g['parameters'], sort_keys=True, indent=2), '```', '',
            'Recorded environment (null means not recorded; no hardware details are inferred):',
            '```json', json.dumps(g['environment'], sort_keys=True, indent=2), '```', '',
            '| Metric | n | Mean | Median | Minimum | Maximum | Sample SD |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        for key, label in [('soft_score_feasible', 'Feasible soft score'), ('soft_score_seed_means', 'Feasible per-seed mean scores'),
                ('hard_violations', 'Final hard violations (evaluated candidates)'), ('runtime_seconds', 'Completed-trial runtime (s)'),
                ('runtime_feasible_seconds', 'Feasible-trial runtime (s)'), ('runtime_nonfeasible_seconds', 'Nonfeasible-trial runtime (s)'),
                ('generation_seconds', 'Generation runtime (s)'), ('worker_wall_seconds', 'Worker wall time (s)'),
                ('generations_executed', 'Generations executed'), ('repair_attempts', 'Repair attempts'), ('repair_moves', 'Repair moves')]:
            stats = g[key]
            lines.append('| ' + label + ' | ' + ' | '.join(display(stats[k]) for k in ('n', 'mean', 'median', 'min', 'max', 'sample_sd')) + ' |')
        lines += ['', '| Seed | Repetitions | Feasible score n | Feasible mean score | Mean completed runtime (s) |', '| --- | ---: | ---: | ---: | ---: |']
        for seed in g['per_seed']:
            lines.append(f"| {seed['seed']} | {seed['trials']} | {seed['soft_score_feasible']['n']} | {display(seed['soft_score_feasible']['mean'])} | {display(seed['runtime_seconds']['mean'])} |")
        lines += ['', '| Seed | Started (UTC) | Completed (UTC) | Outcome | Hard | Soft | Diagnostic categories |', '| --- | --- | --- | --- | ---: | ---: | --- |']
        for r in g['trials']:
            lines.append(f"| {r['seed']} | {r['started_at']} | {r['completed_at'] or 'Not Available'} | {r['outcome']} | {display(r['hard_violations'])} | {display(r['soft_score'])} | {', '.join(r['diagnostic_categories']) or 'None recorded'} |")
        if g['insufficient_seeds']:
            lines += ['', '**Insufficient sample size:** fewer than three distinct seeds. These descriptive observations cannot support robust variability or significance conclusions.']
        if g['total_trials'] > g['distinct_seeds']:
            lines += ['', 'Repeated seeds are retained as repetitions, not additional independent random seeds. Trial-level statistics weight every retained run equally; seed-mean statistics weight each observed seed equally.']
    lines += ['', '## Figures and scalability observations', '']
    for figure in report['charts']:
        lines += [figure['caption'], '', f"![{figure['caption']}]({figure['svg']})", '', f"[Vector PDF]({figure['pdf']})", '']
    lines += report['chart_notes']
    lines += ['', 'Only measured groups are shown. Different workloads have different input fingerprints and are never pooled for fitness statistics. '
        'Any runtime-versus-workload figure is descriptive and restricted to matching configuration, source/scoring version and recorded environment. '
        'No extrapolation, complexity claim, confidence interval or statistical-significance claim is made.', '',
        '## Limitations and reproducibility', '',
        'Runtime depends on hardware, system load, Python/Django/SQLite versions and process overhead. '
        'Hardware or load not recorded in the exports is unknown. Matching recorded environments cannot guarantee identical hardware conditions. '
        'Failed preflight trials can be much shorter than successful searches; separate outcome-specific runtime summaries prevent interpreting those as faster successful scheduling. '
        'Missing or small datasets do not establish performance at larger scales.', '',
        'Run additional experiments separately using `benchmark_ga`; reporting never starts benchmarks. '
        'Keep the original exports, seeds, configurations and source version. Source-file hashes below identify the exact evidence used. '
        'Only allowlisted experiment fields and diagnostic categories are reported; personal records and free-text failure messages are excluded.', '',
        '### Source evidence', '', '| SHA-256 | Format | Records |', '| --- | --- | ---: |']
    lines.extend(f"| {s['sha256']} | {s['format']} | {s['trials']} |" for s in report['sources'])
    return '\n'.join(lines) + '\n'


def generate_report(inputs, output, *, generated_at=None):
    rows, sources = load_files(inputs)
    report = summarize(rows, sources)
    target = Path(output).resolve()
    require(not target.exists() and target.parent.is_dir(), 'Choose a new report directory inside an existing parent directory.')
    report['generated_at'] = generated_at or datetime.now(timezone.utc).isoformat()
    target.mkdir()
    try:
        report['charts'], report['chart_notes'] = write_charts(report, target)
        (target / 'report.md').write_text(markdown(report), encoding='utf-8')
        (target / 'summary.json').write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        fields = ['group_id', 'scenario', 'meetings', 'total_trials', 'distinct_seeds', 'completed_trials',
                  'feasibility_percent', 'validation_success_percent', 'input_fingerprint', 'scoring_version',
                  'parameters', 'environment', 'seeds', 'outcomes']
        metrics = ['runtime_seconds', 'runtime_feasible_seconds', 'runtime_nonfeasible_seconds', 'soft_score_feasible',
                   'soft_score_seed_means', 'hard_violations', 'generations_executed', 'repair_attempts', 'repair_moves']
        stat_names = ('n', 'mean', 'median', 'min', 'max', 'sample_sd')
        fields += [f'{metric}_{stat}' for metric in metrics for stat in stat_names]
        with (target / 'summary.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for group in report['groups']:
                row = {k: group[k] for k in fields if k in group and k not in metrics}
                row['meetings'] = (group['input_counts'] or {}).get('meetings')
                for key in ('parameters', 'environment', 'seeds', 'outcomes'):
                    row[key] = json.dumps(row[key], sort_keys=True)
                row.update({f'{metric}_{stat}': group[metric][stat] for metric in metrics for stat in stat_names})
                writer.writerow(row)
    except Exception:
        # This directory was exclusively created above; remove only our flat artifacts.
        for path in target.iterdir():
            path.unlink()
        target.rmdir()
        raise
    return report
