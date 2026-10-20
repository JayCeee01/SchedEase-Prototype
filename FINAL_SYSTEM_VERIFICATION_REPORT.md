# SchedEase final system verification — Task 8.4

Date: 2026-10-20. Scope: local synthetic acceptance verification; no deployment, real academic data changes or Git commits.

## A. Executive summary

End-to-end tests are needed because correct individual services do not alone establish that forms, generation, publication, history and role-filtered exports work together. This evaluation combines four new server-side workflows with the existing 547-test regression baseline, small isolated benchmark/report commands, production configuration checks and static collection. It preserves existing scheduling rules and authorization architecture.

All 551 tests pass: the 547-test baseline plus four new workflows. They create qualified lecture/lab inputs through administrative forms, generate with the actual GA, publish valid results, inspect restricted timetables, edit copied drafts, reject stale requests, remove draft meetings and verify unchanged finalized history. Failure/retry and legacy-conflict correction paths also pass. Task 8.4's automated verification and reporting criteria are complete; overall system acceptance remains conditional on the explicitly outstanding items below.

The acceptance assessment is limited to the demonstrated automated requirements. Browser acceptance, live hosting/HTTPS, production recovery cutover and representative larger performance experiments are outside the verified evidence. The migration discrepancy is resolved: the developer confirmed that their PowerShell session uses `tertiary_sample.sqlite3` (15 applied migrations), while this verification used `db.sqlite3` (12).

## B. System under test

| Item | Observed environment |
| --- | --- |
| Application | Django monolith; `schedules` models/forms/views/templates, service-based validation/manual edits/publication, Python GA |
| Interpreter | Python 3.12.10, `.venv\Scripts\python.exe` |
| Django | 5.0.6 |
| Database | SQLite 3.49.1; SQLite-specific finalized-record and snapshot triggers |
| Operating system | Windows 10, build 19045, PowerShell; application timezone Asia/Shanghai |
| Pinned dependencies | Django 5.0.6, python-dotenv 1.0.1, ReportLab 4.2.0 (`requirements.txt`) |
| Test tools | Django test runner/client, unittest assertions/mocks, subprocess workers, SQLite read-only connections |
| Repository at start | Existing Task 8.3 changes in four files; preserved. No staged changes or AGENTS.md found. |

The default shell `python` resolves to the WindowsApps alias; all verification commands here explicitly use `.venv\Scripts\python.exe`. No compatibility workaround is used.

## C. Objectives and acceptance criteria

Verify functional correctness across complete workflows; hard-constraint satisfaction; data and audit integrity; authorization/CSRF/privacy; failure atomicity and concurrency; restore integrity; and controlled-seed reproducibility. A passing test must assert the resulting state and, where practical, the visible response. Unsupported unpublication, new roles, curriculum rules and fixed-placement features are not introduced.

Successful publication requires complete recorded meeting requirements and validation, not merely a high GA score. Finalized history must remain unchanged while copied drafts are edited. Failed requests must not create partial finalized data or overwrite previous schedules. Unknown benchmark metrics must remain unknown rather than being represented as zero.

## D. Environment, methodology and execution

### Synthetic dataset and isolation

`schedules/test_acceptance_workflows.py` creates, through actual HTTP resource forms, one dated academic term, a department/program/year, a course with one lecture hour and one laboratory hour, two sections of 20, two linked faculty accounts with dated credentials, two linked synthetic student accounts, one lecture room and one computer laboratory (capacity 30 each), two assignments and four 60-minute meetings. Faculty and room availability is explicitly Monday/Tuesday 08:00–16:00. The GA uses population 6, three generations, elitism 1 and seed 1729. Accounts are synthetic; the ADMIN account is not a Django staff/superuser account.

Ordinary Django tests use a disposable in-memory test database with the repository's migrations. Generation/benchmark workers use their existing isolated in-memory settings. Recovery tests create marked disposable filesystem databases, migrate only those fresh synthetic files, back up and restore to separate new files, and clean their own workspace. No real database is copied or restored. The intentionally invalid legacy draft in one acceptance test is created only inside the test database; all successful edits and corrections use normal forms/services.

### Commands and observed results

Run from the repository root in PowerShell; activation is optional:

```powershell
.\.venv\Scripts\python.exe manage.py test schedules.test_acceptance_workflows --noinput --verbosity 2
.\.venv\Scripts\python.exe manage.py test --noinput --verbosity 2
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

| Verification | Observed result |
| --- | --- |
| Focused acceptance suite | Four passed in 3.827 seconds; zero failures/errors/skips/expected failures/unexpected successes |
| Full suite | 551 passed in 290.845 seconds: 547 baseline + four new tests; zero failures, errors, skips, expected failures or unexpected successes |
| Django system check | No issues, none silenced |
| Model/migration drift check | No changes detected; this command does not apply migrations |
| Dependency check | No broken requirements found |
| Git whitespace check | Passed; new untracked test/report files also checked for trailing whitespace and conflict markers; Git emits only LF-to-CRLF conversion notices |
| Production check, HSTS=0 | Exit 0 with security.W004 (HSTS not enabled) |
| Production check, HSTS=300 | Exit 0 with security.W005 and W021 (subdomains/preload not enabled) |
| Isolated static collection | 131 files; no `.env`, database or private-key extensions found |

Production checks used public test values in a child-process environment, not actual secrets or persistent shell configuration. Warnings were not suppressed. HSTS and proxy trust still require verification on the eventual host. Static collection used a unique workspace directory, then removed only that directory; deployed/static source assets were not changed.

### Reproduce safe production checks and isolated collection

The following PowerShell here-string creates child-only configuration. It does not start a server or access academic records. Cleanup validates the exact generated directory before removal.

```powershell
@'
import os, pathlib, shutil, subprocess, sys, uuid
root = pathlib.Path.cwd().resolve()
env = {k: v for k, v in os.environ.items()
       if not k.startswith('SCHED_EASE_') and k not in ('DJANGO_SETTINGS_MODULE', 'DATABASE_URL')}
env.update(SCHED_EASE_ENV='production', SCHED_EASE_ALLOWED_HOSTS='school.test',
           SCHED_EASE_SECRET_KEY='public-test-fixture-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh')
for seconds in ('0', '300'):
    env['SCHED_EASE_HSTS_SECONDS'] = seconds
    subprocess.run([sys.executable, 'manage.py', 'check', '--deploy'], env=env, check=True)
destination = root / ('task84-static-' + uuid.uuid4().hex)
code = ("import os; os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'; "
        "import django; django.setup(); from django.conf import settings; "
        "settings.STATIC_ROOT=" + repr(str(destination)) + "; "
        "from django.core.management import call_command; "
        "call_command('collectstatic',interactive=False)")
try:
    subprocess.run([sys.executable, '-c', code], env=env, check=True)
    files = [p for p in destination.rglob('*') if p.is_file()]
    assert not [p for p in files if p.name == '.env' or p.suffix in ('.db', '.sqlite3', '.key', '.pem')]
    print('Collected files:', len(files))
finally:
    assert destination.parent == root and destination.name.startswith('task84-static-')
    if destination.exists():
        shutil.rmtree(destination)
'@ | .\.venv\Scripts\python.exe -
```

## E. Acceptance matrix and coverage inventory

See [FINAL_ACCEPTANCE_TEST_MATRIX.md](FINAL_ACCEPTANCE_TEST_MATRIX.md) for 39 traceable scenarios, expected/actual outcomes and explicit Pass, Not executed, Requires manual verification and Blocked distinctions. The inventory covers all 32 baseline test modules and explains why four cross-service scenarios were added rather than duplicating detailed unit tests.

## F. Functional verification

The new tests prove form-created academic records can be consumed by the GA and published through the application service. Generated lecture/lab entries are independently checked against the normal validator, room type and availability. Invalid preparation leaves no partial assignment. Lowering laboratory capacity produces a retained failed run and structured diagnostics; correcting the room through its form permits a successful retry with the original seed.

Legacy faculty/section overlap is detected and linked to the editor. Invalid duration/room edits and invalid suggestion signatures leave placements/audits unchanged. A valid signed suggestion clears conflicts, creates an audit and permits publication. A copied draft accepts a valid manual edit, rejects the stale resubmission, and allows confirmed removal without deleting shared teaching definitions. Missing requirements then prevent publication of the copy.

Faculty/student navigation, direct schedule URLs and CSV/PDF responses are exercised after publication. HTML/CSV excludes the other teacher's entries, while lecture/laboratory rooms and course are present. Draft direct access is denied. Anonymous visitors are redirected to login. Existing snapshot/export tests provide further row-filtering assertions. These are server-rendered response tests, not browser interaction or PDF visual inspections.

## G. Data integrity and recovery

Existing finalized/term/snapshot tests cover model saves, queryset updates, mixed bulk updates/deletions, cascades, SQL replacement, admin attempts and imports. The new lifecycle joins those protections to actual generation/publication/copy/edit/remove endpoints and asserts unchanged original placements, snapshot JSON and publication audit.

The existing `DatabaseBackupTests.test_synthetic_end_to_end_recovery_drill` runs the actual backup and restore commands against a separately configured synthetic database. It checks SQLite integrity, foreign keys, full schema/rows and migration history, archived/published schedules, snapshots, triggers and rejection of protected mutations after restoration. It also checks that source and backup are unchanged and rejects migration/trigger/index drift in separate disposable candidates. This already provides the required integrated recovery drill and is reused, not duplicated.

Executed recovery result: **38 tables, 92 indexes, 55 triggers and 236 rows**; exact schema/rows preserved; source and backup unchanged; all **seven protected mutations rejected** on the restored database. The drill and all other recovery tests passed in the full suite.

Reproduce it alone:

```powershell
.\.venv\Scripts\python.exe manage.py test schedules.test_database_backup.DatabaseBackupTests.test_synthetic_end_to_end_recovery_drill --noinput --verbosity 2
```

The real configured database's SHA-256 was unchanged before and after verification: `8af12d70cf8fabdc0e4a2eccc8a9e8aebc237c24b5aebaf894477e75ccd473fd`. No real migration, backup/restore or mutation was run.

## H. Security verification

Task 8.3 tests retain the active ADMIN/superuser predicate, Django staff/model-permission requirements, direct endpoint checks, immutable admin lifecycle fields, read-only schedule entries/audits and authenticated override attribution. Role matrices include anonymous, faculty, student, plain authenticated, non-ADMIN staff, ADMIN and superuser accounts. Task 6.3 retains administrator-only diagnostics; imports/form drafts remain owner-bound. CSRF-enforcing clients verify relevant tokens, origins and POST requirements, including generation and publication.

Database operators and explicitly entrusted identity administrators remain privileged trust boundaries. Tests do not claim to constrain an operator able to alter database triggers. No public backup route was added. Production settings tests cover secure cookies, HTTPS redirects, proxy trust defaults and private error pages, while actual infrastructure remains untested.

## I. GA reproducibility and evaluation evidence

The new lifecycle repeats HTTP generation with identical inputs/configuration and seed 1729, comparing placements and stored input/parameter metadata. Existing reproducibility tests cover canonical versioned fingerprints, changed-input sensitivity, historical records, failed runs and private history. Reproducibility is limited to equivalent implementation/runtime and stable input ordering; elapsed times are not deterministic guarantees.

Actual new command evidence is retained under `benchmark-results/task84-b2a72f83/` (Git-ignored experiment artifacts, not overwritten). Both small and infeasible runs used seeds 17 and 41, population 4, two generations and elitism 1, with the remaining existing defaults. Workers were isolated in memory. The reporting command consumed both JSON files and produced Markdown/JSON/CSV and SVG/PDF figures: four trials, two comparable groups, zero duplicate copies.

| Fixture | Seed | Outcome | Hard violations | Soft score | Trial seconds |
| --- | ---: | --- | ---: | ---: | ---: |
| small (12 meetings) | 17 | SUCCEEDED, final validation passed | 0 | 901.5333333333333 | 0.724951 |
| small (12 meetings) | 41 | SUCCEEDED, final validation passed | 0 | 921.8666666666667 | 0.637118 |
| infeasible (undersized labs) | 17 | FAILED at preflight, no schedule | Not evaluated | Not evaluated | 0.172272 |
| infeasible (undersized labs) | 41 | FAILED at preflight, no schedule | Not evaluated | Not evaluated | 0.183841 |

These are smoke measurements, not a scalability or statistical-significance claim. Trial time includes fixture construction, scheduler preparation, generation and independent validation; excludes migrations/export. Medium and large searches were not executed for this task. The generated report correctly labels them Not Evaluated. Existing benchmark/report tests check repeatable seeds, grouping, formula correctness, missing metrics and privacy; those fixtures do not replace larger experiments.

Evidence SHA-256:

- `small.json`: `615601673d1c44325cb5df16905601eb9f002bdd0eaafbc0c794ee2d60dfeee0`.
- `infeasible.json`: `b312720e8e358c837b2da53483f6d8b1d9d8910d17c6300ee9b87b3aee825bf5`.

Reproduce without replacing existing experiments:

```powershell
$evidence = "benchmark-results/task84-" + [guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $evidence
.\.venv\Scripts\python.exe manage.py benchmark_ga --scenario small --seeds 17 41 --population-size 4 --generations 2 --elitism 1 --output "$evidence/small.json"
.\.venv\Scripts\python.exe manage.py benchmark_ga --scenario infeasible --seeds 17 41 --population-size 4 --generations 2 --elitism 1 --output "$evidence/infeasible.json"
.\.venv\Scripts\python.exe manage.py report_ga_benchmarks "$evidence/small.json" "$evidence/infeasible.json" --output "$evidence/report"
```

## J. Migration discrepancy investigation

Read-only queries of `django_migrations` found:

| Resolved file under `C:\Users\JEROME\SchedEase-Prototype` | Applied schedules migrations | Last migration |
| --- | ---: | --- |
| `db.sqlite3` (current Codex default) | 12 | `0012_historical_snapshots` |
| `tertiary_sample.sqlite3` | 15 | `0015_generationrun_reproducibility` |
| `tertiary_full_test.sqlite3` | 6 | `0006_generationrun_generationissue` |
| `db.backup-before-workbook-clean-20260817.sqlite3` | 4 | `0004_full_workbook_support` |

Current cwd is the repository root; settings module is `sched_ease.settings`; backend is `django.db.backends.sqlite3`; interpreter is the project's Python 3.12.10 virtual environment. No process `DJANGO_SETTINGS_MODULE`, `SCHED_EASE_ENV`, database URL or `VIRTUAL_ENV` override was present during inspection. Local `.env` includes `SCHED_EASE_DATABASE_URL`; effective settings resolve to `db.sqlite3`. No credentials or academic rows were printed.

`settings.py` loads `.env` in development without overriding an existing process variable. `SCHED_EASE_DATABASE_URL` takes precedence over `DATABASE_URL`; relative SQLite paths are resolved from `BASE_DIR`, not an arbitrary current directory. README's **Worksheet** instructions explicitly set `$env:SCHED_EASE_DATABASE_URL="sqlite:///tertiary_sample.sqlite3"`. This offers a concrete, evidence-supported explanation for the 12-versus-15 reports: a PowerShell session following that instruction would inspect the sample database, which does have all 15. A virtual environment alone does not select a database.

The developer subsequently supplied their PowerShell configuration output: interpreter `C:\Users\JEROME\SchedEase-Prototype\.venv\Scripts\python.exe`, settings `sched_ease.settings`, engine `django.db.backends.sqlite3`, and database `C:\Users\JEROME\SchedEase-Prototype\tertiary_sample.sqlite3`. The interpreter and settings match this verification; the selected database differs. Combined with the read-only migration histories above, this **resolves the discrepancy: both counts describe different databases correctly**. The exact source of the shell override need not be inferred to establish this result. No migration is needed merely to reconcile these observations. For future read-only configuration comparisons:

```powershell
python -c "import os,sys,pathlib; os.environ.setdefault('DJANGO_SETTINGS_MODULE','sched_ease.settings'); import django; django.setup(); from django.conf import settings; print(sys.executable); print(os.environ['DJANGO_SETTINGS_MODULE']); print(settings.DATABASES['default']['ENGINE']); print(pathlib.Path(settings.DATABASES['default']['NAME']).resolve())"
python manage.py showmigrations schedules
```

Both commands inspect configuration/history without applying migrations. The 12-migration database lacks the later lease/diagnostic/reproducibility schema; passing tests against fresh fully migrated test databases do not establish that this real database is ready to run those features. Any future migration decision requires a separate intentional database selection and backup procedure.

## K. Defects and corrective actions

No confirmed new application defect was found in the new focused acceptance workflows. No business logic, GA algorithm, authorization policy, model, dependency or migration was changed. The new tests and reports close evidence gaps. The earlier Task 8.3 recovery-test/documentation changes were present at startup and preserved; they are not new Task 8.4 fixes. The observed database-history discrepancy is an environment finding, not evidence that the migration files themselves are defective.

## L. Limitations and outstanding work

- No real browser was executed. Validate JavaScript meeting tabs, spreadsheet upload/mapping, responsive and dark layouts, keyboard access and downloads in an actual browser.
- No deployment, hosting purchase, live WSGI server, domain/TLS/proxy verification or HSTS rollout was performed. W004/W005/W021 remain visible and require infrastructure-specific decisions.
- The existing production guide requires a supported Django upgrade and dependency review before live deployment; the compatibility baseline here is not a production security certification.
- No live recovery cutover or production load experiment was performed. SQLite-specific triggers and concurrency behavior cannot be assumed on a different database backend.
- Medium/large GA searches and representative institutional workload evidence are not established by these smoke trials; no statistical-significance or scalability claim is made.
- Curriculum completeness and fixed placements remain deferred pending the academic clarification documented in Tasks 7.1 and 7.2. Recorded-input completeness is not proof that every curriculum course was entered.
- The migration discrepancy is resolved, but database selection still matters: `db.sqlite3` remains at 12 and the developer-selected `tertiary_sample.sqlite3` at 15. Test success and migration counts alone do not certify deployment readiness.

## M. Final acceptance assessment and master-plan status

**Task 8.4 complete; automated acceptance passed (551/551). Overall assessment: conditional pass**, with manual/infrastructure/institutional items explicitly outstanding. The verified functional requirements pass, and no new application defect requires a fix. Browser and deployment readiness have not been established. The evidence supports a controlled deployment-preparation phase only after separately approving and addressing its prerequisites; this report does not authorize deployment or describe SchedEase as fully production-ready.

Task 8.4 is the requested final verification task. The repository's earlier phase reports and preserved regression suite support their documented implementation/evaluation work; they do not prove all institutional or deployment conditions are fulfilled. The 34-task plan must therefore not be represented as unconditionally production-complete. Its final automated-verification milestone can be closed on the evidence here, while the above deferred decisions and deployment prerequisites remain open. No additional task is started by this assessment.

### Files and preservation

- Added `schedules/test_acceptance_workflows.py` (four tests), `FINAL_SYSTEM_VERIFICATION_REPORT.md` and `FINAL_ACCEPTANCE_TEST_MATRIX.md`.
- Appended Task 8.4 links and commands to `README.md`, preserving its existing Task 8.3 edits.
- Preserved pre-existing changes in `ADMIN_PERMISSION_PUBLICATION_AUDIT.md`, `GENERATION_DIAGNOSTICS.md` and `schedules/test_generation_diagnostics.py` without further edits during Task 8.4.
- Retained new, uniquely named benchmark/report artifacts under the Git-ignored evidence directory. No previous experiments were overwritten. Temporary test logs/static collection were removed after recording their results.
- No production code, schema, dependency, real database or persistent environment changes; no commits or deployment.
