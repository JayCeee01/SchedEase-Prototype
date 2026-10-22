# SchedEase

SchedEase is a Django-based academic scheduling system for colleges. It manages departments, programs, year levels, sections, subjects, faculty, students, rooms, academic terms, and generated class schedules.

## Technology Choices

- **Django 5**: mature Python framework with authentication, forms, ORM, validation, admin tooling, and server-rendered pages that fit a CRUD-heavy academic system.
- **SQLite for local development**: zero setup and fully relational. Production database selection and any migration require separate compatibility and integrity testing.
- **ReportLab**: server-side PDF export without a browser dependency.
- **Genetic Algorithm service layer**: scheduling optimization is isolated in `schedules/services/ga.py` so it can evolve independently from views and forms.

## Features

- Role-based dashboards for Admin, Faculty, and Student users.
- CRUD screens for academic master data.
- Faculty and room availability, preferred slots, and unavailable slots.
- Genetic Algorithm schedule generator with population initialization, fitness scoring, selection, crossover, mutation, elitism, hard constraints, and soft optimization.
- Manual schedule editing with conflict validation.
- Published schedule views plus CSV and PDF exports.
- Faculty credential management with exact credential matching, explicit subject-approved equivalents, and audited admin overrides.
- Seed data and focused tests for constraints and GA behavior.

## Frontend Structure

SchedEase uses advanced Django templating with a custom SaaS-style design system instead of a separate JavaScript build pipeline. This keeps deployment simple while still providing a polished product interface.

- `templates/base.html`: responsive app shell with sidebar navigation, topbar search, user menu, notifications, mobile navigation, and dark mode toggle.
- `static/css/app.css`: design tokens, layout primitives, buttons, forms, badges, cards, searchable tables, timetable board, responsive rules, and dark theme.
- `static/js/app.js`: theme persistence, active navigation state, mobile sidebar behavior, dismissible notifications, loading button states, table search, and client-side sorting.
- `templates/schedules/entry_table.html`: reusable schedule table component with filtering, sorting, subject chips, and action buttons.
- `templates/schedules/schedule_detail.html`: timetable-style visualization plus table view for manual review/editing.

## Credential Validation

Faculty qualifications are managed through three admin sections:

- **Credentials**: canonical credential names. Matching is exact by default.
- **Faculty Credentials**: credentials held by each faculty member.
- **Subject Requirements**: required credentials for subjects, plus explicitly allowed equivalent credentials.

Teaching assignments and manual schedule-entry edits validate faculty qualification. If a faculty member is missing a required credential, admins must confirm an override and provide a reason. Overrides store the admin user, reason, timestamp, subject, faculty member, assignment, and missing credential details. The Genetic Algorithm treats missing credentials as a hard scheduling constraint.

## Setup

Use **Python 3.12** (verified with **3.12.10**) and **Django 5.2.18 LTS** for this project's development baseline. `.python-version` records the intended Python series; explicitly select it when creating the environment. Earlier compatibility results below describe the historical Django 5.0.6 baseline, not the current dependency pin. See [Django 5.2 upgrade verification](DJANGO_52_UPGRADE.md) for isolated validation results and existing-environment update instructions.

This compatibility baseline preserves the existing framework and application behavior. Django 5.0 is no longer maintained; a supported-framework upgrade remains a separate task before deployment. See [Django's Python compatibility notes](https://docs.djangoproject.com/en/5.2/releases/5.0/#python-compatibility) and [release support status](https://www.djangoproject.com/download/#supported-versions).

### Windows PowerShell

Install Python 3.12 using the Python Install Manager (`py install 3.12`), or install Python 3.12 from python.org if your older `py` launcher does not support `install`. Open PowerShell in the project folder:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -c requirements-lock.txt
python --version
python -m django --version
python -m pip check
```

The execution-policy setting lasts only for this PowerShell session. If activation is blocked by organizational policy, use `.\.venv\Scripts\python.exe` instead of `python` in the commands below. In your editor, select `.venv\Scripts\python.exe` as the interpreter.

If `.venv` was created with another Python version, stop the development server and open a fresh terminal. Rename the old environment to an unused backup name before running the setup commands; do not reuse its installed packages. For Task 1.1, the old Python 3.14 environment was preserved as `.venv-python314-backup`.

For a new checkout, create the local configuration only if it does not exist, then apply migrations and start the server:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python manage.py migrate
python manage.py runserver
```

After pulling changes that add migrations, run:

```powershell
python manage.py migrate
```

Open `http://127.0.0.1:8000`.

Optional: on a disposable demo database, run `python manage.py seed_sample` to create the sample records and users below. Do not run seed commands as part of routine setup or upgrades on an existing database.

Sample users:

- Admin: `admin` / `admin12345`
- Faculty: `f001` / `password123`
- Student: `student` / `password123`

## Worksheet 
```powershell
$env:SCHED_EASE_DATABASE_URL="sqlite:///tertiary_sample.sqlite3"
python manage.py migrate
python manage.py runserver
```

## Academic spreadsheet import

Open **Generate Schedule → Import Spreadsheet** as an administrator. Download the sample, fill in your school’s information, upload the file, review it, then click **Import**. The page includes column examples and help. CSV and Excel (.xlsx) files are supported. Run `python manage.py migrate` before using this feature.

See [Academic import guide](ACADEMIC_IMPORT.md) for supported columns, modules, validation rules and limits. Importing does not generate or publish a schedule.

## Tests

Activate the Python 3.12 environment first. Run the checks directly, without compatibility patches:

```powershell
python --version
python -m django --version
python -m pip check
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

`requirements.txt` retains the application's direct dependency versions. `requirements-lock.txt` pins the complete dependency set verified on Windows/Python 3.12; use it as the constraint file during installation for repeatable resolution.

### Task 1.1 compatibility diagnosis

The previous environment used Python 3.14.7 with Django 5.0.6. Django's `BaseContext.__copy__()` calls `copy(super())`; Python 3.14 changed how `super` objects are copied. The resulting object cannot accept the `dicts` attribute, causing `AttributeError` during template-context copying. A minimal reproduction was `from copy import copy; from django.template import Context; copy(Context())`. The same expression succeeds in the clean Python 3.12.10 environment with the original Django package, without monkey patches. See [Python's documented change](https://docs.python.org/3.14/library/functions.html#super).

Verification on Windows (Task 1.1):

| Check | Result |
| --- | --- |
| `python --version` | Python 3.12.10 |
| `python -m django --version` | 5.0.6 |
| `python -m pip check` | No broken requirements found |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py showmigrations --plan` | Existing migrations applied |
| `python manage.py test` | 98 tests: 97 passed, 1 existing assertion failure; no compatibility errors |
| Development server | Started with `--noreload`; homepage returned HTTP 200 |

At the end of Task 1.1, the remaining failure was `SchedulingTestCase.test_student_browse_only_shows_entries_for_own_section` in `schedules/tests.py`. Task 1.2 confirmed that its expected course label omitted the existing `tabindex` and `data-tooltip` attributes. The assertion now checks the rendered accessible label and the exact authorized entry list. Two additional tests cover empty student timetables, denial of other-section detail/export access, and effective section overrides. No application rendering or access logic changed.

Task 1.2 verification: all five focused tests passed, followed by **100 passing tests** in the complete suite (the original 98 plus two regression tests). Django system checks passed and `makemigrations --check --dry-run` reported no changes.

The suite deliberately logs a mocked `RuntimeError: private technical detail` in its unexpected-generation-failure test; that test passes. Tests create and destroy a separate test database, not the existing application database.

### Task 1.3: known scheduling defects

`schedules/test_known_defects.py` adds three regression contracts that assert the intended correct behavior:

| Issue / Phase 2 work | Test | Current defect |
| --- | --- | --- |
| H1: assignment/meeting synchronization | `test_H1_parent_faculty_edit_updates_all_meetings_and_ga` | Parent-only faculty edits leave both meetings and GA inputs using the previous faculty. |
| H3: shared room availability rules | `test_H3_unlisted_day_is_closed_for_ga_manual_validation_and_reports` | Tuesday has zero available hours in reporting but is accepted by GA room checks and manual validation. |
| H4: credential expiry validation | `test_H4_expired_credential_does_not_qualify_faculty_or_ga` | A credential expired before the fixed academic term still qualifies in the service and GA preflight. |

Run these contracts with `python manage.py test schedules.test_known_defects --verbosity 2`. H1, H3 scheduling/reporting, and H4 now pass normally after Tasks 2.1-2.4. No expected-failure markers remain. H4 passes the academic term explicitly to the shared credential service. The historical verification results below record the baseline at the end of each earlier task.


Task 1.3 completion verification (Python 3.12.10 / Django 5.0.6): `python manage.py test` ran **103 tests: 100 passed, 3 expected failures, 0 unexpected failures/errors, and 0 unexpected successes**. The expected failures are H1, H3, and H4 above. Their assertion differences were also inspected with the markers temporarily disabled in memory, confirming the specific defects rather than unrelated errors. `python manage.py check` passed and `python manage.py makemigrations --check --dry-run` reported no changes. No application logic was modified; Phase 2 fixes remain pending.

### Task 2.1: assignment synchronization

Parent assignment saves now synchronize term, course, section, and faculty to every meeting, including unchanged meeting forms. Meeting duration, type, room requirement, and source metadata remain independent. The assignment editor validates and saves the complete meeting set in one transaction; validation failures roll back parent and meeting changes. Normal parent model saves (including Django admin) also synchronize and validate affected meetings.

Shared-field edits are rejected when any meeting is referenced by a schedule, including a draft. This deliberately conservative H1 safeguard prevents silent changes to existing timetables; it does not create a schedule revision workflow. Existing schedule-entry overrides are preserved. Bulk `QuerySet.update()` bypasses model save hooks and must not be used to edit shared assignment fields. Existing inconsistent records are not automatically rewritten by a migration.

Task 2.1 verification: **108 tests: 106 passed, 2 expected failures (H3/H4), no unexpected failures or successes**. H1 passes normally. Added coverage includes all shared fields, unchanged lecture/lab settings, admin saves, validation rollback, draft/published/archived references, and protection of pre-existing inconsistent scheduled meetings. Django system checks pass; migration checks report no changes.

### Task 2.2: shared scheduling availability

Faculty and room placements now use `schedules/services/availability.py` in both GA evaluation and manual validation:

- If any explicit Available periods exist for a resource, only those periods permit meetings; unlisted days are closed.
- Without any explicit Available periods, the default is the existing school window: Monday-Saturday, 07:00-19:00.
- Overlapping or adjacent Available periods merge. A meeting must fit completely in one resulting interval. Unavailable periods always block overlapping meetings, even inside Available periods.
- A meeting can end exactly when an unavailable period starts, or start exactly when it ends. School-day/hour restrictions always apply; inactive rooms are rejected.
- Preferred periods remain soft preferences and do not restrict otherwise permitted placements. Faculty has no separate active-status field.

Run focused checks with `python manage.py test schedules.test_availability schedules.test_known_defects`. The original H3 test retains its closed-day utilization assertion and now passes without a marker. `test_H3_reporting_counts_merged_availability_minus_unavailable` documented the Task 2.3 reporting defect: 08:00-12:00 plus 10:00-14:00, minus a 10:00-11:00 block, should report five hours; at the end of Task 2.2 the report still returned eight; Task 2.3 corrects this to five. GA weights, optimization strategies, and room reporting calculations were not changed.

Task 2.2 verification: **117 tests: 115 passed, 2 expected failures (H4 expiry and H3 reporting), no unexpected failures/errors or successes**. All previously passing tests remain passing. Django system checks pass and migration checks report no changes.

### Task 2.3: accurate room availability reporting

Room reports now use the shared policy's effective intervals: merged available periods, clipped to school hours, minus the union of unavailable periods. Closed days and inactive rooms contribute zero hours. The room timetable grid uses the same policy for open/closed cells. Daily, weekly, and summary percentages use unrounded hours; displayed hours retain two decimal places.

Examples verified by tests:

| Configuration | Available hours | Scheduled hours | Utilization |
| --- | --- | --- | --- |
| Monday 08-12 and 10-14, blocked 10-11 | 5 | 2 | 40% |
| Monday 08:00-08:20 | 0.3333... | 0.1666... | 50% |
| No availability restrictions | 72 weekly | 0 | 0% |
| Fully blocked or inactive room | 0 | 1 historical hour | 0% (zero-denominator convention) |

Existing scheduled hours remain visible even if later availability changes make them invalid; reporting does not delete entries or repair schedules. The existing zero-denominator convention is retained to avoid division errors. H3 reporting now passes without an expected-failure marker; H4 was deferred at this stage and is now resolved in Task 2.4. Run `python manage.py test schedules.test_room_availability_reporting schedules.test_availability schedules.test_known_defects` for focused coverage, including CSV output.

Task 2.3 verification: **121 tests: 120 passed, 1 expected failure (H4), no unexpected failures/errors or successes**. All 16 focused tests completed with only H4 expected to fail. Django system checks passed and migration checks reported no changes.

### Task 2.4: faculty credentials and administrator overrides

Qualification uses the academic term's actual dates, never today's date. A required credential (or an explicitly accepted equivalent) must have an issue date on or before the term starts and an expiry date on or after the term ends. Both boundaries are inclusive. A blank expiry date means no expiry restriction. Missing issue dates, missing term dates, or invalid term date order cannot establish qualification; correct the data or obtain an explicit administrator override. Courses with no credential requirements do not require a credential.

Overrides are scoped to their linked meeting and the exact faculty/course being scheduled, including schedule-entry faculty/course overrides. They must retain an administrator reference, a nonblank reason, and the recorded missing-credential justification. Old overrides remain in the audit history but do not authorize a different teacher or course. Valid matching overrides can be reused without duplicate approval records. Manual override creation, final entry validation, entry saving, and edit auditing commit or roll back together. Non-administrators cannot approve overrides.

The shared service is used by GA eligibility/preflight, manual validation, assignment editing, spreadsheet validation, and schedule comparison qualification metrics. GA weights, room availability, and assignment synchronization are unchanged.

**Existing data and spreadsheet limitation:** no dates are invented or backfilled. Review undated Faculty Credentials before generating schedules. The current academic spreadsheet format imports credential names, not issue/expiry dates: create the dated faculty credential records first when required, then import assignments. Matching pre-existing administrator overrides remain valid; imports cannot create new approvals. Existing tests now use explicit issue dates for fixtures intended to qualify, and new tests ensure undated credentials are rejected.

Run `python manage.py test schedules.test_credentials schedules.test_known_defects schedules.test_academic_import` for focused checks.

Task 2.4 verification: **132 tests passed, 0 failures/errors, 0 expected failures, and 0 unexpected successes**. All 42 focused credential, import, and original regression tests passed. Django system checks passed and `makemigrations --check --dry-run` reported no changes. H1, H3, and H4 all run normally without expected-failure markers.

## Deployment Notes

Set `SCHED_EASE_DEBUG=False`, provide a strong `SCHED_EASE_SECRET_KEY`, set `SCHED_EASE_ALLOWED_HOSTS`, collect static files with `python manage.py collectstatic`, and run behind a production WSGI server. For PostgreSQL deployment, replace the simple `SCHED_EASE_DATABASE_URL` handling in `sched_ease/settings.py` with `dj-database-url` or explicit Django database settings.


### Lecture and laboratory requirements (Task 2.5)

Assignment forms, spreadsheet imports, generated schedules, and publication use the same component totals. Each course's lecture and laboratory hours are checked separately in integer minutes. Meetings may split a component across several sessions; meeting numbers must be unique within the assignment. No separate meeting-count policy is configured.

Use explicit **LECTURE** and **LABORATORY** meetings. A zero duration uses only that component's course hours. A course with no laboratory hours must not contain laboratory meetings. Legacy **GENERAL** meetings must be reviewed and classified before scheduling or publication; existing records are not automatically rewritten.

Manual entries may be added incrementally, but their course and component must match the assigned meeting. Complete coverage and actual scheduled durations are checked before GA output is saved or a schedule is published. Course/component changes should be made through the assignment workflow, respecting existing schedule locks. Administrators can review validation details; global diagnostics are not shown to students.


### Meeting duration and active rooms (Task 2.6)

Effective meeting durations must be whole minutes from 1 to 720, derived from the configured 07:00-19:00 school day in `schedules/services/time.py`. There is no separate academic minimum or duration increment beyond one minute. The GA's 30-minute start grid does not impose a 30-minute minimum duration. GA preflight rejects invalid durations; generation never extends or shortens them.

The existing stored zero value still means use the course component's hours (Task 2.5); that resolved duration must pass the same limits. Spreadsheet durations remain explicit positive integers. Opening and closing boundaries are inclusive. Actual scheduled durations must match the meeting requirement exactly, without rounding seconds.

Inactive rooms are rejected by imports, manual scheduling, GA generation, and publication using the shared availability policy. Imports do not reactivate rooms automatically. Invalid manual edits remain unsaved and produce no edit audit record.


### Finalized schedule protection (Task 3.1)

Run `python manage.py migrate` after updating to install the SQLite integrity triggers in migration 0010. Published and archived schedules lock their entries and referenced academic content, including bulk updates and cascading deletes. Use unrelated records for future changes; ordinary draft editing remains available. Publication can archive the previous official schedule without unlocking its content.

See [Finalized schedule protection](FINALIZED_SCHEDULE_PROTECTION.md) for the mutation audit, coverage, deployment requirements, and deferred term/snapshot policies.


### Academic-term integrity (Task 3.2)

Run `python manage.py migrate` to install migration 0011 in addition to 0010. Terms referenced by published or archived schedules keep their original names, school years, and dates. Their active-term flag can still change. Empty drafts may move to another term; populated drafts cannot retain meetings from a different term. Edit an unscheduled parent assignment to move its meetings together. Bulk operations cannot leave those relationships inconsistent.


### Atomic manual edits (Task 3.3)

Open the Add/Edit Schedule Entry form before saving. Its signed revision prevents stale forms from overwriting newer edits, including during override confirmation. Reload when asked to review newer data. Entry changes, approvals, audit records and the schedule revision now commit together or roll back together. New entries also receive an audit record.

SQLite can temporarily reject competing writes; no partial changes are saved. See [Manual schedule transactions](MANUAL_SCHEDULE_TRANSACTIONS.md) for the save protocol and concurrency limits. No migration is required for Task 3.3.


### Copy to Draft and Remove Meeting (Task 3.4)

Administrators can select **Copy to Draft** on a published or archived schedule. The new draft has independent meeting placements; shared academic definitions remain protected. Review the draft's validation messages before editing or publishing.

In a draft's table view, select **Remove Meeting**, review the confirmation, and tick the approval box. This removes only that draft entry. Academic assignments and finalized schedules remain unchanged. Required meetings must be restored before publication. Both operations are transactional and audited; stale removal forms require reloading. No migration is required.


### Conflict corrections (Task 3.5)

Administrators can select **Fix Conflict** beside a draft meeting's validation message. The meeting editor shows up to three **Suggested Placements** with an **Apply Suggestion** button. Suggestions preserve saved academic information and required duration; unsaved editor changes are not included.

The search checks the current start time and a 30-minute grid across Monday through Saturday, preferring the same day and nearby times. Every suggested placement passes the existing entry validation. If none is found, other manually entered times may still work; academic requirements may also need correction. Schedule-wide issues without a specific entry remain descriptive messages.

Applying a suggestion requires an administrator, POST, CSRF protection, and a signed user/meeting/revision-bound proposal. The existing manual-save transaction rechecks current constraints, updates the revision and audit together, and rolls back on failure. Changed or expired suggestions require reloading. Published and archived schedules must first be copied to a draft. No migration or dependency is required.


### Historical schedule snapshots (Task 3.6)

Run `python manage.py migrate` to apply migration `0012_historical_snapshots`. Published and archived schedules receive one immutable historical record. The migration reconstructs existing finalized schedules from available data and labels them as reconstructed; it does not invent original publication values.

Finalized schedule details, timetable displays, browsing, and exports use preserved academic labels and placements after applying the existing access restrictions. Drafts continue using live records. Archiving retains the original snapshot; Copy to Draft creates editable placements without copying historical storage.

`python manage.py backfill_schedule_snapshots` safely reconstructs any missing finalized snapshots and reports incomplete historical metadata. Existing snapshots are never overwritten. See [HISTORICAL_SNAPSHOTS.md](HISTORICAL_SNAPSHOTS.md) for the capture schema, safeguards, migration verification, and limitations.


### GA fitness priority (Task 4.1)

The GA ranks candidates by **fewer hard constraint violations first**, then by **higher soft preference score** when violation counts are equal. Preferences cannot outweigh an additional hard violation. Generation reports failure if no feasible result is found, and full schedule validation remains mandatory before saving.

The existing numeric schedule fitness field stores the soft score of a validated result. Per-generation hard/soft statistics are available on `GeneticScheduler.generation_statistics`. See [GA_FITNESS.md](GA_FITNESS.md) for counting, deterministic ties, reporting and regression coverage. No migration is required.


### Feasible GA placements (Task 4.2)

The GA now caches individually valid room/day/time options for each meeting. Initialization and mutation prefer options that avoid other placed meetings; crossover preserves valid inherited placements and checks newly introduced conflicts. Randomized choices preserve variation, while Task 4.1's hard-first ranking remains unchanged.

An empty option set identifies the meeting and explains why it cannot be placed. Individually valid options can still conflict with one another, and full schedule validation remains required before saving. See [GA_PLACEMENTS.md](GA_PLACEMENTS.md) for constraints, failure behavior and the measured deterministic comparison. No migration is required.

### Targeted GA conflict repair (Task 4.3)

The GA now attempts bounded repairs of overlapping meetings after creating initial candidates and after offspring mutation. It moves only affected meetings, uses existing feasible placements, and accepts only reductions in hard violations. Unresolved candidates remain subject to normal selection and final validation; importing or generating does not publish a schedule.

See [GA_REPAIR.md](GA_REPAIR.md) for the repair budget, diagnostics, regression coverage, measured comparison and search limitations. No migration is required.

### Shared generation reservations (Task 4.4)

Generation now uses a database reservation per academic term, shared across application workers. A competing request receives a wait/retry message. Reservations renew during generation; expired requests cannot save results. Different terms can compute independently, subject to SQLite's brief write locks.

Apply migration `0013_generationlease` with `python manage.py migrate` before running the updated application. Stop old workers before migration and restart them with the new code. See [GENERATION_LOCKING.md](GENERATION_LOCKING.md) for lifecycle, transaction safeguards, tests and deployment limits.

### Structured generation diagnostics (Task 4.5)

Generation failures now retain explicit meeting and assignment references, including conflicts involving several meetings. Administrators can review all affected meetings in the Error Log and open their assignment records. Deleted references remain identifiable without breaking historical reports.

Failed-run status and issue records save together. Select **Review Interrupted Runs** in the administrator Error Log to reconcile interrupted Running records against current database leases, preserving active requests. Viewing the log does not change records. Apply migration `0014_generationissue_details_generationrun_lease_owner` with `python manage.py migrate` before restarting updated workers. See [GENERATION_DIAGNOSTICS.md](GENERATION_DIAGNOSTICS.md) for the data format, recovery rules, privacy safeguards and limitations.

### GA reproducibility information (Task 5.1)

Generate Schedule now accepts an optional **Random seed**. Leave it blank to choose and record a seed automatically. In the administrator Error Log, open **Generation history ? View Run** to inspect the seed, effective parameters, input counts/fingerprint, timestamps and outcome for successful or failed runs.

Apply migration `0015_generationrun_reproducibility` with `python manage.py migrate` before restarting updated workers. Historical runs show missing metadata explicitly. A fingerprint identifies prepared inputs; it is not a stored input snapshot or a guarantee of replay across different environments. See [GA_REPRODUCIBILITY.md](GA_REPRODUCIBILITY.md) for coverage, reproducibility evidence and limitations.

### Accurate soft scoring (Task 5.2)

Faculty idle gaps now use actual minutes, and day balancing includes unused Monday-Saturday instructional days. Hard constraints still take priority. Generation metadata records the updated scoring version and parameters. See [GA_SOFT_SCORING.md](GA_SOFT_SCORING.md) for formulas, examples, tests and scope. No migration is required for this change.

### Repeatable synthetic GA benchmarks (Task 5.3)

Use `python manage.py benchmark_ga --scenario small --seeds 17 41 --output small-benchmark.json` to export fixed-seed trials. Each trial uses a separate process with a fresh in-memory database; real scheduling records are not used or changed. Choose a new `.json` or `.csv` filename. See [GA_BENCHMARKS.md](GA_BENCHMARKS.md) for fixture sizes, configurable parameters, full-suite commands, metric definitions and measured smoke results. Large searches are opt-in and no migration is required.

### GA evaluation reports (Task 5.4)

Use `python manage.py report_ga_benchmarks small-benchmark.json --output evaluation-report` to create a Markdown report, statistical CSV/JSON tables, and SVG/PDF charts from existing benchmark files. Multiple JSON/CSV input files are supported. Choose a new output directory. Reporting does not run experiments or access scheduling data; missing scenarios are marked **Not Evaluated**. See [GA_EVALUATION_REPORTS.md](GA_EVALUATION_REPORTS.md) for PowerShell commands, statistical methods, grouping rules and limitations. No new dependency or migration is required.

### Administrative list pagination and search (Task 6.1)

Academic record lists, Error Log issues and generation history now use 20-record server-side pages. Use each list's Search form to search the database; page links retain search, sort and filter selections. Existing academic table headers sort the complete matching list. See [ADMIN_LIST_PAGINATION.md](ADMIN_LIST_PAGINATION.md) for updated pages, search fields, query measurements and limitations. No migration or dependency is required.

### Record counts, sorting and filters (Task 6.2)

Academic record lists now show total records, matching records and the displayed range. Choose a sort order and filters, then select **Search / Apply**. Page links retain your selections; **Clear search and filters** removes them. Schedule totals cover only the selected tab. Invalid or deleted filter selections show a message so you can correct them. See [ADMIN_LIST_CONTROLS.md](ADMIN_LIST_CONTROLS.md) for available controls, count scope, query measurements and limitations. No migration or dependency is required.

### Diagnostic access by role (Task 6.3)

Internal Error Logs and generation history remain administrator-only. Django admin access to credential overrides and schedule edit audits now also requires the SchedEase administrator role (or superuser), in addition to existing Django permissions. Invalid Error Log filters show a correction message instead of causing a server error. Faculty/student timetable access and permitted availability feedback are unchanged. See [DIAGNOSTIC_ACCESS.md](DIAGNOSTIC_ACCESS.md) for the endpoint inventory, access policy, tests and limits. No migration or dependency is required.

### Schedule validation performance (Task 6.4)

Validation now loads only relevant overlapping meetings and faculty workload records, with related data loaded together. Existing constraints, diagnostics, final validation, transactions and generation safeguards remain unchanged. See [SCHEDULE_VALIDATION_PERFORMANCE.md](SCHEDULE_VALIDATION_PERFORMANCE.md) for isolated before/after measurements, exact-output regression tests and limitations. No migration or dependency is required.

### Curriculum completeness evaluation (Task 7.1)

SchedEase checks completeness against entered assignments and lecture/laboratory requirements. It does not independently verify that every curriculum-required course was entered. No authoritative curriculum model or approved thesis requirement for that feature was found. The evaluation selects **Outcome D: academic clarification required** before implementation. See [CURRICULUM_COMPLETENESS_EVALUATION.md](CURRICULUM_COMPLETENESS_EVALUATION.md) for evidence, gaps and questions. This task changes documentation only.

### Fixed meeting placements evaluation (Task 7.2)

Manual edits and Copy to Draft preserve placements within a particular schedule; they do not pin meetings during a new GA run. No approved requirement defining fixed day, time or room rules was found in the available documentation. The evaluation selects **Outcome D: academic clarification required** before implementation. See [FIXED_MEETING_PLACEMENTS_EVALUATION.md](FIXED_MEETING_PLACEMENTS_EVALUATION.md) for existing support, GA impact and questions. This task changes documentation only.

### Production security preparation (Task 8.1)

Local setup is unchanged. Future production workers must explicitly set `SCHED_EASE_ENV=production` and supply a private secret and allowed hosts through their environment. Production disables debugging, enforces HTTPS and secure cookies, and ignores local `.env` files. Proxy trust and HSTS require deployment-specific verification. See [PRODUCTION_SECURITY.md](PRODUCTION_SECURITY.md) for variables, checks, static serving and remaining deployment prerequisites, including a supported Django upgrade. This task does not deploy the application.

### Database backup and isolated restore (Task 8.2)

Use `python manage.py backup_database --output <new-private-file.sqlite3>` for a verified SQLite online backup. Use `python manage.py restore_database --source <backup.sqlite3> --destination <new-disposable-file.sqlite3>` to verify recovery without replacing a live database. Existing files, configured database paths and public asset directories are rejected. See [DATABASE_BACKUP_RESTORE.md](DATABASE_BACKUP_RESTORE.md) for PowerShell examples, migration compatibility, storage security and synthetic recovery tests. No command activates a restored database or runs migrations automatically.

### Admin permissions and publication safeguards (Task 8.3)

Django admin requires an active staff account with the SchedEase administrator role (or superuser status) and the relevant Django model permissions. Publish schedules through the application workflow; schedule status is read-only in Django admin. Schedule entries and their audit records are also read-only there. Credential override approval records identify the administrator who creates them. See [ADMIN_PERMISSION_PUBLICATION_AUDIT.md](ADMIN_PERMISSION_PUBLICATION_AUDIT.md) for the role matrix, confirmed fixes, tests and remaining limitations.

### Final regression and acceptance verification (Task 8.4)

See [Final system verification report](FINAL_SYSTEM_VERIFICATION_REPORT.md) for the synthetic end-to-end workflows, reproducible PowerShell checks, benchmark evidence, migration investigation and remaining deployment prerequisites. The [Acceptance test matrix](FINAL_ACCEPTANCE_TEST_MATRIX.md) maps each scenario to its automated evidence and separates browser/infrastructure checks that still need verification.

Run the focused workflows with `.\.venv\Scripts\python.exe manage.py test schedules.test_acceptance_workflows`, then the full suite with `.\.venv\Scripts\python.exe manage.py test`. Tests use disposable databases. The default `db.sqlite3` and the worksheet's `tertiary_sample.sqlite3` have different migration histories; confirm the effective database path before interpreting `showmigrations`. Task 8.4 does not migrate either real database or deploy the application.
