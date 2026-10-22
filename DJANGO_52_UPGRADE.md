# Django 5.2 LTS upgrade validation

## Scope and environment

- Branch: `development`; starting commit: `b5d070b84e5c66e67a00c3bd4e0f4f83353f945d`.
- Python 3.12.10; SQLite runtime 3.49.1.
- Django 5.0.6 upgraded to **5.2.18**, the latest stable 5.2 release returned by PyPI during this validation.
- Other pins remain unchanged: asgiref 3.12.1, sqlparse 0.6.0, tzdata 2026.5, python-dotenv 1.0.1, ReportLab 4.2.0, Pillow 13.0.0 and chardet 7.6.0.
- A separate environment lives in ignored `env/django52-validation/venv`. The existing `.venv` was not upgraded.
- No application logic, permissions, models, migration files, scheduling constraints or algorithms were changed.

## Isolation and checks

The local validation launcher `env/django52-validation/run.py` sets an explicit database URL under that disposable directory **before** importing settings. It invokes Django's management command runner with the project's normal settings. Development dotenv loading cannot override this process variable. The test runner creates a separate test database; existing concurrency/recovery tests create their own synthetic databases. No academic database was copied or migrated.

Commands used with the isolated Python executable:

```powershell
python -B env\django52-validation\run.py check
python -B env\django52-validation\run.py check --deploy
python -B env\django52-validation\run.py makemigrations --check --dry-run
python -B -m pip check
python -B -Wd env\django52-validation\run.py test --noinput
```

The deployment check uses a temporary random secret and `audit.invalid` host in production mode; neither is a real deployment credential. HSTS remains at the existing default of zero.

| Check | Result |
| --- | --- |
| Clean isolated dependency installation | Successful; installed versions match the constraint file |
| Django system check | No issues |
| Synthetic production deployment check | Existing `security.W004`: HSTS not enabled |
| Migration consistency | No changes detected |
| Dependency consistency | No broken requirements |
| Full test suite | **664 passed** in 476.502s; 0 failures, errors, skips, expected failures or unexpected successes |
| Focused confirmation | **6 passed** in 3.770s; direct Python subprocess exit code 0 |
| Working database preservation | All four pre-existing root SQLite files retained identical SHA-256 hashes |
| Existing environment | `.venv` still reports Django 5.0.6 |

The full suite includes GA fitness/placements/repair/reproducibility, credentials and availability, cross-term conflicts, authorization and publication, Smart Repair, imports, CSV/PDF exports, manual transactions, finalized protection, historical snapshots, concurrency, backup and recovery. The synthetic recovery drill preserved exact schema and rows, verified 55 triggers, and rejected seven protected mutations.

Focused confirmation ran `schedules.test_known_defects` plus `SnapshotTests.test_concurrent_sql_publication_captures_exactly_once`, `GenerationLockTests.test_simultaneous_requests_on_separate_connections_create_only_one_schedule`, and `SmartRepairTests.test_http_authorization_csrf_confirmation_and_method`. These six tests are included in the 664-test suite, not additional new tests.

PowerShell's merged native stderr capture reported a wrapper exit status of 1 for the full run despite Django's explicit `Ran 664 tests` / `OK` result. Direct Python subprocess capture of the focused run returned 0. No assertions were changed or failures suppressed. Full output is retained locally in ignored `env/django52-validation/tests.log`; focused output is in `focused.log` alongside it. Expected mocked exception logs are part of the existing failure-path tests.

**Upgrade acceptance: complete for isolated Python 3.12 / SQLite validation.** No compatibility correction or new migration was required. The developer environment remains unchanged pending approval to update it.

## Compatibility assessment

Reviewed the Django 5.1/5.2 release changes, application API usage, settings, migrations and existing test isolation. Parsed all 141 Python source files in `schedules` and `sched_ease`. SQLite 3.49.1 exceeds Django's minimum; the current asgiref pin also satisfies the newer requirement. No custom database backend or replacement migration strategy is introduced.

Particular upgrade risks covered by existing tests include form/admin rendering, constraint validation, query ordering, transactional manual edits, publication, SQLite triggers, immutable snapshots, generation leases and backup schema verification. SQLite-only guards remain SQLite-only; this is not a PostgreSQL portability change.

Deprecations were exposed with `-Wd`, not suppressed:

- `CheckConstraint(check=...)` in the model and migrations 0005/0016 is deprecated for Django 6.0. It remains supported on 5.2. Historical migrations were deliberately preserved.
- ReportLab 4.2.0 references `ast.NameConstant`, deprecated for a future Python version. Python 3.12 remains the verified target; ReportLab was not unnecessarily upgraded.

## Updating the developer environment after approval

Close running development servers first. From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-lock.txt
.\.venv\Scripts\python.exe -m django --version
.\.venv\Scripts\python.exe -m pip check
```

These commands update packages only. **Do not automatically run `migrate`.** This upgrade creates no application migration. Any previously pending migrations on the actual academic database require a separate review and approval. The installation above was not performed against `.venv` during this task.

This validation does not certify production infrastructure, live data, browser behavior or every unrelated dependency's security status. No commit, push, merge or deployment is included.

References: [Django 5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/), [Django 5.1 release notes](https://docs.djangoproject.com/en/5.2/releases/5.1/).
