# SchedEase

SchedEase is a Django-based academic scheduling system for colleges. It manages departments, programs, year levels, sections, subjects, faculty, students, rooms, academic terms, and generated class schedules.

## Technology Choices

- **Django 5**: mature Python framework with authentication, forms, ORM, validation, admin tooling, and server-rendered pages that fit a CRUD-heavy academic system.
- **SQLite for local development**: zero setup and fully relational. Move to PostgreSQL for production with the same Django ORM models.
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

Use **Python 3.12** (verified with **3.12.10**) and **Django 5.0.6** for this project's current development baseline. Do not create this environment with Python 3.14: Django 5.0's template-context copying is incompatible with it. `.python-version` records the intended Python series; explicitly select it when creating the environment.

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

Run just these contracts with `python manage.py test schedules.test_known_defects --verbosity 2`. Each uses a temporary `unittest.expectedFailure` marker; none is skipped. Setup, workflow operations, and positive controls run outside the marker so unexpected exceptions and failed prerequisites remain visible. Only the final comparison of the intended outcomes is marked. The GA checks use a fixed seed and inspect deterministic inputs/constraints rather than relying on a random generation result.

Remove each marker when its corresponding Phase 2 defect is fixed and rerun the focused and full suites. An unexpected success fails the suite and requires investigation; it must not be silently accepted. These tests do not implement the fixes. H4 currently exercises the existing qualification API, which has no term argument; if Phase 2 adds term-aware qualification, pass the fixture's term explicitly in that regression test.

## Deployment Notes

Set `SCHED_EASE_DEBUG=False`, provide a strong `SCHED_EASE_SECRET_KEY`, set `SCHED_EASE_ALLOWED_HOSTS`, collect static files with `python manage.py collectstatic`, and run behind a production WSGI server. For PostgreSQL deployment, replace the simple `SCHED_EASE_DATABASE_URL` handling in `sched_ease/settings.py` with `dj-database-url` or explicit Django database settings.
