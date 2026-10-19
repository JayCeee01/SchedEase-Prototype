# Task 5.4: offline GA evaluation reports

## Architecture and scope

`report_ga_benchmarks` reads existing Task 5.3 `schedease-benchmark-v1` JSON or
CSV exports. The `schedules/benchmark_reports/` package validates records,
groups comparable experiments, calculates descriptive statistics and writes
Markdown, JSON, CSV and vector SVG/PDF figures. It does not query the database,
instantiate the scheduler, or start benchmark workers. The command disables
automatic Django system/migration checks; application checks remain unchanged.

ReportLab is already a project dependency and provides the chart rendering.
No dependencies, migrations, scoring changes, GA changes or benchmark-runner
changes are needed. Output directories must be new. Original benchmark files
and existing reports are never overwritten. Failed rendering removes only the
new report directory's artifacts. Keep generated output under the existing
Git-ignored `benchmark-results/` directory.

## PowerShell commands

From the project root (activation is optional with the explicit interpreter):

```powershell
.\.venv\Scripts\python.exe manage.py report_ga_benchmarks `
  benchmark-results/smoke-a.json `
  benchmark-results/smoke-b.json `
  benchmark-results/infeasible.csv `
  --output benchmark-results/thesis-evaluation
```

Choose another output directory for a later invocation. Inputs may be JSON,
CSV, or both. At least one input file is required. A valid JSON export with an
empty `trials` list produces an empty report with all scenarios Not Evaluated.

Additional experiments are **separate, opt-in work**, not part of reporting:

```powershell
# May be expensive: execute only when you choose to collect more evidence.
.\.venv\Scripts\python.exe manage.py benchmark_ga --scenario all --seeds 17 41 73 --output benchmark-results/additional.json

.\.venv\Scripts\python.exe manage.py report_ga_benchmarks benchmark-results/additional.json --output benchmark-results/additional-report
```

Use matching GA settings, source implementation and environment when collecting
data intended for comparison. See [GA_BENCHMARKS.md](GA_BENCHMARKS.md) for fixture
definitions, generation controls, metric units and isolation guarantees.

## Validation and duplicate policy

- JSON envelope and trial schemas must match version 1. CSV headers must contain
  the required benchmark fields. Invalid JSON, duplicate JSON fields, duplicate
  CSV headers, malformed rows and non-finite numbers are rejected.
- Identity/configuration fields are required; unavailable numerical measurements
  may be absent/null (blank in CSV). Numbers must have the appropriate type and
  sign. Seed ranges, timestamps, statuses, success flags, fitness versions and
  available generation/reproducibility metadata must agree.
- Successful trials require zero hard violations, successful final validation,
  completion time and identified inputs. Missing values never become zero.
- Group identity includes scenario/version, input fingerprint, full effective
  configuration, scoring version and recorded environment including GA source
  hash. Unknown input/source/runtime identity prevents pooling across trials.
- Trial identity is group + seed + normalized UTC start timestamp. Identical
  re-exported records count once. Conflicting records with that identity cause
  an error. Different timestamps retain repetitions of the same seed and are
  explicitly distinguished from independent seeds. Repeating an identical file
  path reads it only once. Input fingerprints with conflicting counts fail.
- Unknown benchmark schema/configuration fields are rejected rather than
  silently interpreted as compatible future experiments. Known but different
  scoring versions stay in separate groups; their soft scores are never pooled.

Only allowlisted experiment data is reported. Arbitrary environment fields,
personal fields, free-text diagnostic messages and detailed diagnostic payloads
are excluded. Diagnostic categories remain available. Source SHA-256 hashes
identify evidence without exposing local filesystem paths. Input errors name
the file and trial to help correct the source.

## Statistics and denominators

All statistics use actual exported measurements. For nonmissing values `x`:

- Mean: `sum(x) / n`.
- Median: middle sorted value, or mean of the middle pair for even `n`.
- **Sample** standard deviation: `sqrt(sum((x - mean)^2) / (n - 1))`.
- Minimum/maximum: observed extrema.
- Zero observations: all numerical summaries null, `n = 0`.
- One observation: mean/median/extrema available; sample SD null.

Outcome counts distinguish feasible, infeasible scheduling outcomes, execution
failures, and incomplete trials. A scheduling failure or invalid candidate is
not proof of mathematical infeasibility. A run without completion is incomplete.

Feasibility percentage is `100 * feasible / completed trials`. Completed
execution errors are included; incomplete runs are excluded and counted
separately. Validation success is `100 * passed / performed final validations`;
preflight failures are not final validation attempts. Both denominators appear
in the exported summaries and report.

Soft-score summaries use feasible outcomes only, within one compatible group.
Invalid candidates may have recorded soft scores, but those are not included in
quality summaries. Hard violations summarize evaluated candidates, including
failed candidates; no candidate means no measured hard count. Reports include
trial-level summaries, per-seed means, and sample SD across seed means. Repeated
runs weight trial summaries equally; seed-mean statistics weight seeds equally.

Runtime is in **seconds**, with separate summaries for:

- Completed-trial elapsed time, including failed outcomes.
- Feasible and nonfeasible completed-trial elapsed time separately.
- Production generation duration.
- Full subprocess wall time, including startup and migrations.

Generation counts and repair attempts/moves are summarized where recorded.
Each metric has its own nonmissing `n`. Detailed generation statistics remain
in the JSON table; the report does not duplicate GA measurement logic.

## Outputs and chart policy

- `report.md`: objectives, methodology, coverage, scenario definitions,
  configurations, fingerprints, environment, seeds, timestamps, summary and
  per-seed/trial tables, figures and interpretation limits.
- `summary.json`: complete grouped statistics, sanitized trial records, source
  hashes, report timestamp, per-seed summaries and chart manifest.
- `summary.csv`: one row per group with flattened statistical columns; nested
  configuration/environment/outcome fields contain JSON. Missing values are blank.
- SVG and PDF charts: feasibility, mean completed runtime, and feasible soft
  scores by seed. Figures require at least two completed observations from two
  distinct seeds with a verified identity. Soft-score figures require feasible
  scores for at least two seeds. Bars name groups rather than pooling different
  input fingerprints.
- Runtime-versus-workload figures require at least two measured meeting counts,
  each with sufficient feasible observations, under the same configuration,
  source/scoring version, fixture version and recorded environment. No fitted
  curves or extrapolation are produced. Missing sizes never appear as zero bars.

Medium and large are **Not Evaluated** when no completed observations are
supplied. Groups with fewer than three seeds have an explicit small-sample
warning; three is a warning threshold, not a statistical sufficiency guarantee.
No significance tests or significance claims are made. Figure PDFs have stable
metadata; with a fixed report timestamp, all artifacts are byte-reproducible.

## Actual reporting smoke test

The existing `smoke-a.json`, `smoke-b.json`, and `infeasible.csv` were read without
running new benchmarks. The two smoke files are distinct executions (different
timestamps), not duplicate copies. The resulting report is locally available at
`benchmark-results/evaluation-verified/report.md` with corresponding tables and
three SVG/PDF figure pairs.

- Five retained trials: four small trials (two repetitions each of seeds 17
  and 41) and one deliberately infeasible trial.
- Small feasibility and final-validation rates: **100%**, four observations.
- Small feasible soft-score mean: **911.7**; trial-level sample SD:
  **11.739455473522412**.
- Small elapsed-runtime mean: **0.5124625749999723 seconds**; sample SD:
  **0.0017176513759007454 seconds**.
- Means and SDs were independently checked using sums and squared deviations
  from the original records, matching the generated summaries.
- Medium and large: **Not Evaluated**. No scalability chart was produced.
- SHA-256 hashes of every source file and the existing sample database were
  unchanged before/after report generation.

These observations describe only the available synthetic smoke runs, not real
school throughput or statistical significance. Hardware/system load was not
recorded; the report says so rather than inventing hardware details.

## Testing

`schedules.test_benchmark_reports` uses explicitly artificial result fixtures
with known arithmetic. These unit-test values are not experimental findings.
Tests cover imports, validation, duplicate policy, grouping, statistics,
incomplete/failed/single/empty data, chart labels and omission rules, deterministic
artifacts, privacy, unchanged inputs, database-free operation, and output cleanup.

```powershell
.\.venv\Scripts\python.exe manage.py test schedules.test_benchmark_reports
.\.venv\Scripts\python.exe manage.py test schedules.test_benchmarks schedules.test_ga_soft_scoring schedules.test_ga_fitness schedules.test_generation_lock
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
git diff --check
```

### Verified results

- Reporting tests: **23 passed** (including stricter malformed-record checks
  and chart eligibility based on completed, actually measured seeds).
- Combined requested reporting/benchmark/fitness/soft-scoring/generation-lock
  tests: **102 passed**.
- Final full suite: **435 passed in 267.445 seconds**: all 412 previous tests
  plus 23 reporting tests. Zero failures, errors, skips, expected failures or
  unexpected successes. No existing assertions were changed.
- Django system check: no issues. Migration dry-run check: no changes detected.
- `git diff --check`: passed.
- Reporting smoke test used only existing exports. Source files and production
  sample data were unchanged. No medium/large benchmark was executed.

The report importer, grouping/statistics, rendering and command were already
present when resuming. This session completed validation edge cases, regression
coverage, chart eligibility, documentation, smoke checks and full verification.
Task 5.4 is complete; Phase 6 was not started. No Git commit was created.
