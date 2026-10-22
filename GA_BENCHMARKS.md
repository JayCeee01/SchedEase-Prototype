# Task 5.3: repeatable synthetic GA benchmarks

## Execution and isolation

`benchmark_ga` starts a fresh Python subprocess for **every trial**. The worker
configures Django directly, with only an in-memory SQLite database; it never
imports deployment settings or reads a database URL. It applies existing
migrations, creates synthetic inputs, and calls the production
`GeneticScheduler.generate()` path, including leases, validation, repair,
diagnostics and reproducibility metadata. No GA implementation is duplicated.
Only drafts are created. Independent final validation runs after generation.

Fixtures and trials refuse to run outside the dedicated in-memory environment.
Connections close in `finally`, including migration and execution errors; process
exit destroys all database contents. Isolation does not depend on deleting
academic records after running against the application database. The command's
parent process performs no database queries and disables automatic system and
migration checks. The normal application checks remain unchanged.

## Fixed fixtures: `synthetic-v1`

| Scenario | Sections | Courses | Faculty | Lecture / computer-lab rooms | Assignments | Meetings | Required hours |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| small | 2 | 2 | 2 | 2 / 1 | 4 | 12 | 16 |
| medium | 6 | 4 | 8 | 3 / 2 | 24 | 72 | 96 |
| large | 12 | 6 | 18 | 6 / 4 | 72 | 216 | 288 |
| infeasible | 2 | 2 | 2 | 2 / 1 | 4 | 12 | 16 |

Every section takes every course. Each assignment has two 60-minute lectures
and one 120-minute laboratory. Faculty are assigned cyclically, with a 24-hour
weekly limit. Sections cycle through sizes 24, 28 and 32. Lecture rooms hold 40;
labs hold 36, except the intentionally infeasible case where labs hold only 10.
That case must fail room-capacity preflight without claiming an evaluated score.

The term is August 1–December 1, 2026. Every course requires a synthetic
qualification held by all fixture faculty, issued January 1, 2020 and expiring
December 31, 2030. Faculty and rooms have explicit Monday–Friday 08:00–17:00
availability. Rooms close for lunch, 12:00–13:00 daily. Each faculty member is
unavailable 13:00–15:00 on weekday `faculty_index % 5` and prefers Tuesday
08:00–10:00. Course, section, faculty and room creation order is fixed. No random
fixture generation, real people or real academic records are used.

These are synthetic experiments, **not measured school workloads**. Larger
scenarios increase shared-resource contention. A failed search is not proof
that a scenario is mathematically infeasible; only the undersized-lab case has
a deliberately established infeasibility condition.

## Run in Windows PowerShell

From the project root, using the existing virtual environment:

```powershell
New-Item -ItemType Directory -Force benchmark-results

# Small smoke run (two fixed seeds)
.\.venv\Scripts\python.exe manage.py benchmark_ga --scenario small --seeds 17 41 --population-size 4 --generations 2 --elitism 1 --output benchmark-results/small.json

# Deliberate failure, exported as CSV
.\.venv\Scripts\python.exe manage.py benchmark_ga --scenario infeasible --seeds 17 41 --output benchmark-results/infeasible.csv

# Complete experiment: opt in when enough time is available
.\.venv\Scripts\python.exe manage.py benchmark_ga --scenario all --output benchmark-results/all.json
```

Use a **new output filename** for each invocation. Existing files are never
overwritten, and only `.json` and `.csv` are accepted. `benchmark-results/` is
ignored by Git. No generated results should be committed by default.

Defaults: seeds `17 41 73`, population 12, generations 10, mutation rate 0.08,
crossover rate 0.85, elitism 2, repair budget 64. Supported options are
`--scenario small|medium|large|infeasible|all`, `--seeds`, `--population-size`,
`--generations`, `--mutation-rate`, `--crossover-rate`, `--elitism`,
`--repair-budget`, and required `--output`. Zero generations evaluates only the
initial population. Trials preserve scenario definition order and the supplied
seed order; repeated seeds are allowed. Invalid parameters fail before workers
start. Unexpected execution errors are exported as `ERROR` and cause a nonzero
command exit; ordinary infeasible/search failures are `FAILED` and do not stop
the experiment. Worker startup failures abort with a command error.

## Output schema: `schedease-benchmark-v1`

JSON is an object with `schema` and `trials` (one object per trial). CSV has one
row per trial with the same field names; nested objects/lists use JSON within a
cell, booleans are `true`/`false`, and unavailable values are blank (JSON `null`).

| Fields | Meaning |
| --- | --- |
| `scenario`, `scenario_version`, `seed` | Fixed fixture and RNG identity |
| `input_counts`, `input_fingerprint` | Actual prepared input summary and Task 5.1 SHA-256 |
| `parameters`, `scoring_version` | Effective GA settings and `hard-first-v2` formula |
| `environment` | Python/Django/SQLite versions, OS description, GA source hash |
| `status`, `feasible`, `failure_type`, `failure_reason`, `diagnostics` | Distinct successful, failed, and unexpected-error outcomes |
| `hard_violations`, `soft_score` | Best evaluated candidate fitness; null before evaluation |
| `validation_outcome`, `validation_errors` | Independent saved-schedule check: passed, failed, or not_run |
| `generations_executed`, `generation_statistics`, `repair_statistics` | Actual GA statistics; initial population is generation 0 |
| `schedule_id`, `schedule_status`, `schedule_fingerprint` | Temporary draft identity and ordered meeting/room/day/time digest |
| `generation_status`, `reproducibility` | Original production run status and full Task 5.1 metadata |
| `started_at`, `completed_at` | UTC trial timestamps |
| `elapsed_seconds` | Fixture creation, scheduler preparation, generation and independent validation; excludes migrations/export |
| `generation_seconds` | Production metadata's scheduler execution duration |
| `worker_wall_seconds` | Parent-measured subprocess duration, including startup, migrations, trial, serialization and exit |

Scores are not replaced by zero on failure. A failed preflight has no candidate
fitness; a failed search can have measured hard/soft values. Independent
validation failure can reject a zero-hard candidate: `feasible` requires both
zero hard violations and successful final validation. Temporary IDs are not
links to application records. Exports contain no real user/faculty details.

## Reproducibility and limits

Compare inputs, parameters, source identity, schedule digest, fitness and
generation/repair statistics. Do not expect timestamps, elapsed times, or OS
descriptions to match. Every trial starts from a fresh database so IDs and input
fingerprints do not depend on preceding trials. Local seeded GA RNG is reused;
global random state is not modified by benchmark execution.

RAM-only SQLite avoids disk writes and measures that particular execution
environment; times are not production-throughput estimates. Hardware load,
Python/Django versions and source changes affect timing or replay. Default GA
budgets are modest and do not guarantee solutions to larger scenarios. Full
medium/large searches are deliberately **opt-in management commands**, not
ordinary regression tests. Their fixture construction and fingerprints are
tested without running the expensive search. No thesis charts, statistical
claims or Task 5.4 analysis are implemented here.

## Measured smoke run

Using population 4, generations 2, elitism 1, mutation 0.08, crossover 0.85 and
repair budget 64, two independent executions produced:

| Seed | Feasible | Hard violations | Soft score | Trial seconds (repeat run) |
| --- | --- | ---: | ---: | ---: |
| 17 | yes | 0 | 901.5333333333333 | 0.5103 |
| 41 | yes | 0 | 921.8666666666667 | 0.5127 |

Both executed two generations, passed independent validation, and reproduced
input/schedule fingerprints, effective parameters and generation/repair
statistics. The input hash was
`ff95310db9f3d172bd58c7ceaa172fdb1475582e08e0a082f3feafe45da85dbf`.
The infeasible CSV trial reported `FAILED`, room-capacity diagnostics and null
hard/soft scores. The existing sample database SHA-256 was unchanged before
and after these smoke runs. These are measured examples, not performance claims.

## Verification completed

- 18 new regression tests cover fixture counts/fingerprints, fixed/different
  seeds, actual candidate scores, successful and infeasible runs, unexpected
  errors, independent validation, exports, parent-database isolation, ignored
  deployment settings, random-state preservation and cleanup (including failed
  migrations).
- Combined targeted run: **186 passed** in 109.830 seconds, including existing
  fitness, placement, repair, generation lock, soft scoring, finalized schedule,
  academic-term, snapshot and reproducibility modules.
- Full `python manage.py test`: **412 passed** in 256.616 seconds: all 394
  previous tests plus 18 new tests. Zero failures, errors, skips, expected failures
  or unexpected successes. Existing assertions were not weakened or modified.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.

Existing uncommitted work was preserved. No production GA, fitness, validation,
lease or publication implementation was changed for Task 5.3. No migration,
dependency, commit, or Task 5.4 implementation was added.
