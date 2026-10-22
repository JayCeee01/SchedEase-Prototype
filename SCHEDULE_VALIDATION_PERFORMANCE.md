# Task 6.4: schedule validation performance

## Scope and workflow inspection

The working tree already contained Task 6.3 changes. Those were preserved.
Production changes for Task 6.4 are confined to `services/conflicts.py`; no GA
operator, scoring formula, validation policy, transaction or permission changed.

| Entry point | Validation and safeguards retained |
| --- | --- |
| GA candidate evaluation (`ga.py`, `placements.py`, `repair.py`) | Existing run-local qualification/availability caches, feasible domains, resource buckets, hard-first fitness and repair remain unchanged. |
| Generated schedule persistence | `schedule_validation_messages()` still executes after entries are created inside the fenced generation-lease saving transaction. Failure still rolls back persistence. |
| Manual editing/overrides (`manual_edits.py`) | Conditional revision claim, current administrator check, current credential/override checks, `entry.full_clean()`, save and audit remain in the same transaction. |
| Correction suggestions (`corrections.py`) | Every proposed candidate still passes `full_clean()`; signed application of a suggestion uses the authoritative manual-save service. |
| Publication (`publication.py`) | Current-state full schedule validation remains inside the writer transaction before status change and snapshot capture. |
| Draft review and conflict display | Existing view-level checks and full schedule diagnostics remain. No check is skipped or reclassified. |
| Copy/remove | Copy preserves source records and copies historical placements for later correction; removal retains its existing signed revision, confirmation, transaction and audit behavior. |

Also inspected: availability policy, meeting/component totals, credential
eligibility, ScheduleEntry model validation/ordering, full schedule aggregation,
and existing validation, publication, locking and snapshot tests.

## Baseline methodology

The measurements use Django's isolated test database, Python 3.12.10, Django
5.0.6 and SQLite. Production scheduling records are never used or modified.
Fixtures contain **8, 32 and 96 meetings** (small/medium/large for this validation
study). Each group of four meetings shares a faculty member, section and room;
groups otherwise have independent resources. Each course has one lecture hour,
with a zero stored duration to exercise inherited-duration resolution.

Three variants run at every size:

- **Valid:** four adjacent one-hour Monday meetings per resource group.
- **Conflicts:** all four meetings at 08:00–09:00, producing faculty, room and
  section conflicts. Existing directed diagnostics are preserved, not deduplicated.
- **Invalid:** otherwise valid times with unavailable faculty/rooms and credentials
  expiring before the academic term ends.

Task 5.3 scenario definitions were inspected and left unchanged. This study uses
purpose-built placed schedules so valid and invalid outcomes are known without
running GA experiments. No full GA benchmark was run. Test fixture construction
is outside the measured interval.

`CaptureQueriesContext` counts SQL and `perf_counter()` measures validation time.
Each invocation starts from a fresh Schedule instance. The query log is cleared
before capture to exclude fixture setup and avoid its 9,000-query buffer limit.
Validation-call and Python overlap-comparison counts are also measured. Memory
usage was not measured. The measurements are single instrumented samples, not
statistical throughput estimates or cold-cache database benchmarks.

Before changing validation code, the successful baseline recorded:

| Meetings | Valid queries / seconds | Conflict queries / seconds | Invalid queries / seconds |
| ---: | ---: | ---: | ---: |
| 8 | 116 / 0.125914 | 156 / 0.158970 | 172 / 0.183817 |
| 32 | 452 / 0.642892 | 612 / 0.902086 | 676 / 0.836497 |
| 96 | 1,348 / 2.667591 | 1,828 / 3.022953 | 2,020 / 3.253399 |

Initial fixture development caught an omitted lecture component and query-log
buffer rollover. Both profiling-fixture issues were corrected before these
baseline measurements; failed measurements are not used as evidence.

## Demonstrated bottlenecks and changes

1. **Unrelated peer rows:** each entry loaded all other entries on the same day,
   even when times/resources could not conflict. SQL now narrows peers using the
   same strict interval inequalities and effective faculty/section/room identities.
   Existing queryset ordering and the original Python checks remain.
2. **Unrelated workload rows:** every entry loaded all schedule entries before
   checking faculty identity. SQL now selects only that effective faculty's entries,
   including override identities and preserving the original own-entry handling.
3. **Repeated related-object fetches:** inherited duration and conflict messages
   loaded course/override objects individually. Queries now join the specific
   related objects needed by each path. Full schedule entry loading also includes
   term and section labels. Separate subject SELECTs fell from 288 (valid) or 576
   (conflicting) to zero for the 96-meeting workloads.

The shared identity predicate implements exactly `override OR (override is NULL
AND assignment identity)`. A changed override never retains the parent's identity
for conflict/workload matching. Strict inequalities preserve adjacent intervals
as non-overlapping. Day and schedule scoping are retained.

No new persistent, request or transaction cache was introduced. Every validation
invocation still queries current database state. The optimization reduces repeated
loads and unrelated comparisons, not the number of required validation calls.

## Final paired comparison

After optimization, the frozen original and optimized validator were run on the
same fixtures in the same process. Both were instrumented alike, including
overlap-call counting. These are the final paired measurements:

| Meetings | Scenario | Queries before | Queries after | Seconds before | Seconds after |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8 | Valid | 116 | 92 | 0.122587 | 0.135002 |
| 8 | Conflicts | 156 | 92 | 0.157903 | 0.137466 |
| 8 | Invalid | 172 | 132 | 0.174765 | 0.180827 |
| 32 | Valid | 452 | 356 | 0.607609 | 0.523333 |
| 32 | Conflicts | 612 | 356 | 0.788054 | 0.541254 |
| 32 | Invalid | 676 | 516 | 0.857974 | 0.698599 |
| 96 | Valid | 1,348 | 1,060 | 3.260213 | 1.585955 |
| 96 | Conflicts | 1,828 | 1,060 | 3.401318 | 1.661221 |
| 96 | Invalid | 2,020 | 1,540 | 3.733565 | 2.149908 |

The 8-meeting valid/invalid samples were slightly slower despite fewer queries;
there is no claim of universal runtime improvement. Instrumentation adds overhead,
particularly when the original performs many Python overlap checks.

| Meetings | Original Python overlap checks | Optimized valid/invalid | Optimized conflicts | Conflict diagnostics |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 56 | 0 | 24 | 72 |
| 32 | 992 | 0 | 96 | 288 |
| 96 | 9,120 | 0 | 288 | 864 |

These count Python checks, not database query-planner comparisons. Each relevant
pair can still appear in both directed entry validations, as required by the
existing diagnostic contract. Valid workloads have zero diagnostics; invalid
workloads have 24/96/288 diagnostics, respectively. `full_clean()` still runs
exactly once per entry in each full schedule validation.

Machine-readable initial and paired measurements are preserved in
`schedules/test_support/validation_measurements.json`.

## Correctness and performance regression coverage

`schedules/test_support/validation_reference.py` is a frozen test-only copy of
the original conflict validator. It is never imported by production code. The
oracle runs original entry validation during `full_clean()`; unchanged credential,
availability and meeting requirement services are shared.

The ten new tests compare the **complete ordered output**, including messages,
categories, severity, entry references, meeting/assignment IDs, room IDs and
structured details. No diagnostic sorting or normalization hides differences.
Coverage includes:

- All nine profiling workloads, with deterministic query budgets and zero
  per-entry subject SELECTs; no wall-clock assertions.
- Individual faculty/room/section conflicts and combined conflicts.
- Overrides both toward and away from parent identities, plus workload limits.
- Small/wrong-type/inactive rooms, seconds/duration/hour boundaries and missing labs.
- Missing credentials, valid and mismatched overrides, and changes between calls.
- Changed/deleted availability, adjacent meetings, unrelated terms, missing and
  repeated meetings, and unsaved manual candidates.

Existing manual transaction, publication, finalization, corrections, credential,
GA, locking, diagnostic, snapshot and thesis tests remain unchanged.

To repeat profiling without running GA benchmarks:

```powershell
$env:VALIDATION_PROFILE_OUTPUT = 'validation-profile.json'
.\.venv\Scripts\python.exe manage.py test schedules.test_validation_performance
Remove-Item Env:VALIDATION_PROFILE_OUTPUT
```

The optional output path is a local test report. The command uses Django's test
database, not the development database.

## Verification and remaining limits

- 91 targeted validation, manual transaction, diagnostic, correction, finalized
  protection and meeting-requirement tests passed.
- System check: no issues. Migration check: no changes detected.
- Full suite: **496 passed in 334.010 seconds**, preserving all 486 previous
  tests plus 10 new validation tests. Zero failures, errors, skips, expected
  failures or unexpected successes. Test runner exit code: 0.
- `git diff --check`: passed.

The full run finished successfully while the resume request arrived; it was not
interrupted and did not need repeating. The original and paired profiling
measurements above remain the recorded performance comparison. Full-suite
profiling reproduced the same query/operation counts and exact diagnostic
equivalence. The tracked `task64-test-results.log` retains that run's output.

Task 6.4 is complete within the measurement limits below. No Git commit was
created by the assistant, and Phase 7 was not started.

Full model validation still performs field/constraint, credential and availability
queries per entry. Parent requirement validation still has related-label work.
Dense conflicts still inherently produce many diagnostics. No global linear-time
claim is made; SQL scan costs depend on backend/data distribution. Indexes and
deeper operation-local caching were not needed for this focused improvement.
GA caches/operators and repeated authoritative checks across distinct transactions
were deliberately retained. No production-load or live browser test was performed.
The timings measure the shared validation service, not end-to-end GA generation,
manual-save transactions, suggestion searches or publication latency; those
workflows were inspected and regression-tested without claiming separate speedups.
