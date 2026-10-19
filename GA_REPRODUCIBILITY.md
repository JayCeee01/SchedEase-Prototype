# Task 5.1: GA reproducibility records

## Confirmed gaps

Previously `GeneticScheduler` accepted an optional seed, but unseeded requests used an unrecorded RNG state. GenerationRun retained only a mutable GASettings reference, basic timestamps/status and a resulting schedule. There was no saved effective configuration, input fingerprint/count summary, measured execution duration or final hard/soft result. Direct scheduler calls did not create generation history.

## Metadata schema v1

Migration `0015_generationrun_reproducibility` adds one JSON field to GenerationRun, defaulting to an empty object for historical rows. Existing term, settings, schedule and issue relationships and start/completion/status fields remain authoritative.

The metadata contains:

- `version`: 1.
- `seed`: the actual integer used by the local RNG.
- `parameters`: population size, generation limit, crossover/mutation rates, elitism, tournament selection and effective tournament size, tie policy, repair-attempt budget, 30-minute placement grid/boundary policy, hard-first fitness version and current numerical preference weights/thresholds.
- `inputs`: versioned input SHA-256, term ID and counts; null when preparation did not complete.
- `environment`: Python version/implementation, Django version and a normalized SHA-256 of the relevant implementation source files. No machine names or filesystem paths are stored.
- `outcome`: measured scheduler-execution seconds, duration scope, best hard count, best soft score and evaluated generations; null when execution did not reach a measurable outcome. Fitness may independently be null for preflight failures.

The model's existing timestamps report request start and completion/recovery. Duration measures the scheduler invocation through outcome recording, including final validation but excluding HTTP/input-constructor time and the final commit overhead. It is not inferred by subtracting timestamps after a hard crash. A zero-hard candidate can still fail final validation, so best fitness is not proof of a successfully saved schedule.

## Seed and configuration behavior

An optional **Random seed** field is available on Generate Schedule. Blank seeds use `secrets.randbits(63)` and are saved before scheduler construction in the HTTP workflow. Explicit zero is preserved. The UI accepts integers from 0 through 2^63-1; the internal API accepts Python integers. Each generation invocation initializes its own `random.Random(recorded_seed)`. Initialization, selection, crossover, mutation and repair continue to use that local generator; global random state is untouched.

A repeated invocation on the same scheduler starts from its recorded seed rather than silently using an advanced RNG stream. Effective model settings are copied at execution start, then serialized; later edits/deletion of the GASettings row cannot change the historical configuration. No genetic operators or fitness formulas were redesigned. Fixed policy metadata describes the current implementation; the separate implementation digest and environment versions identify changes relevant to comparisons.

## Fingerprint schema: schedease-inputs-v1

Canonical JSON uses sorted keys, compact separators, ASCII escaping and no non-finite numbers. Record lists and interval/relationship lists are explicitly sorted. SHA-256 hashes the canonical UTF-8 bytes.

Coverage:

- Term ID and start/end dates; operating days/hours.
- Parent assignments (including empty parents relevant to final completeness checks), meeting IDs and relationships, component/index, stored and effective duration, effective room requirement and loaded qualification eligibility.
- Course lecture/lab requirements and room type; section sizes; faculty maximum workload.
- All active rooms loaded by the GA, including capacity/type/active flag.
- Loaded faculty/room availability periods and effective allowed/blocked policy intervals, including faculty preferred periods.
- Credential IDs and issue/expiry dates; required credentials and accepted-equivalent IDs.
- Override scope and whether administrator, justification and missing-credential information are present. Private justification text is excluded.

Counts distinguish parent assignments from individual meetings and count the loaded faculty, sections, active rooms and courses. They also include availability periods, held credentials, requirements, equivalents, overrides, eligible meetings and required teaching minutes.

Names, employee/student numbers, user IDs/names, course/room labels, credential descriptions/issuers/notes, override justification text, source spreadsheet annotations, timestamps unrelated to scheduling, prior schedules/results and the GA seed/parameters are excluded from the input hash. Only the summary and digest are stored; the canonical input document is transient. Term remains an ordinary existing FK/reference. Parameter/seed differences are compared separately.

IDs are included because identity and sorted meeting/room order influence scheduling. An equivalent reordered query result with the same IDs hashes identically; rebuilding a database with new IDs is not guaranteed to do so. Fingerprints are conservative: changing a covered value can change the digest without necessarily changing a generated schedule.

## Integration and transaction boundaries

HTTP requests create baseline seed/configuration metadata before constructing the scheduler. Accepted direct `generate()` calls also create a GenerationRun (with no requesting user for internal calls). Seed and prepared input metadata are persisted before computation, under the existing lease ownership fence. Known and unexpected direct-call failures use Task 4.5's structured, atomic failure recording.

Successful results, metadata, schedule entries and successful run status commit in Task 4.4's existing fenced transaction. Validation failures roll back schedule writes but retain failed-run metadata and structured issues. Expired owners cannot record success. Interrupted runs retain only captured metadata; Task 4.5 recovery updates stale status without inventing a duration or fitness result. Contention and unauthorized requests do not begin a new generation attempt. A failed database write cannot guarantee a history record; partial transactional writes are rolled back.

Input preparation uses the scheduler's loaded objects, availability policies and qualification cache; the summary is refreshed at invocation before being frozen for that run. Inputs can still be edited concurrently: final validation reads current data and remains authoritative. This fingerprint describes prepared GA inputs, not an atomic historical snapshot of all live validation queries.

## Administrator interface and privacy

The existing Error Log now includes a collapsible **Generation history** table covering successful and failed runs. **View Run** shows recorded parameters, counts, fingerprint, environment, seed, timestamps, status, measurable results, issue links and the resulting schedule. Issue detail pages link to their run information. Existing panels/tables/details controls support the site's themes and responsive layouts.

Run details use the existing login and administrator checks. Students, faculty and anonymous users cannot retrieve them. Historical rows explicitly show that metadata was not recorded. Incomplete inputs/results are labeled unavailable rather than filled with defaults. Sensitive personal data and confidential notes are not placed in metadata or fingerprints.

## Reproducibility evidence and limits

The regression fixture generates identical ordered placements, generation statistics and best scores with the same seed, settings and inputs. Tests also verify RNG isolation, repeated scheduler calls, equivalent ordering, irrelevant label changes, and changed hashes for room capacity, meeting duration, availability, term dates, credentials, equivalents and overrides.

This is not universal replay. Reproduction requires compatible Python/Django/code versions, the same IDs and relevant data, stable inputs during execution and the same parameters. The source digest is not a packaged release or database backup. A fingerprint cannot reconstruct lost input data. No benchmark framework, replay service, idle-gap scoring change or thesis report is introduced.

## Deployment

Stop old application workers, apply migrations and restart the updated code:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
```

Migration 0015 depends on Task 4.5's migration 0014. Test databases exercise the migration; the developer's database and existing uncommitted data changes remain untouched.

## Resumed verification — 2026-10-19

The implementation, migration 0015, administrator history UI and 20 Task 5.1 tests were already present in commit `8bde47e` when work resumed. Review found no missing implementation or test requirements. This session completed verification and added this report; no application code or migrations were changed, and no commits were made.

Verified using the existing virtual environment:

- `python manage.py test schedules.test_reproducibility`: 20 passed.
- `python manage.py test`: 378 passed in 225.829 seconds, including all 358 prior tests and the 20 Task 5.1 tests. Zero failures, errors, skips, expected failures or unexpected successes.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no model changes detected.
- `git diff --check`: passed.

The tests verify automatic/explicit seeds, identical seeded placements and fitness statistics, RNG isolation, effective settings preservation, counts, canonical ordering, relevant/irrelevant input changes, successful/failed/interrupted runs, stale-owner rejection, rollback, historical compatibility and administrator-only metadata. The full suite also retains generation diagnostics, leases and finalized-schedule safeguards.

Migration 0015 was preserved without modification or duplication and applied successfully during fresh test-database creation. Read-only `showmigrations` inspection found migrations 0013, 0014 and 0015 pending in the configured development database. They were not applied during this session; run `python manage.py migrate` before using the updated application. The existing modification to `tertiary_sample.sqlite3` was preserved.

Task 5.1 implementation and verification are complete. Deployment still requires the pending migrations. The fingerprint/replay limitations above remain applicable. Task 5.2 was not started.
