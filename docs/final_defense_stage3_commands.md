# Final-defense Stage 3 handoff

Stage 2 creates academic inputs only. No schedules, publication, GA execution, or exports are performed. All curriculum, calendar and 600-minute SHS weekly workload approvals are **fictional demonstration configuration**, authorized by the user, not STI/DepEd policy. These reduced two-week modules are not complete institutional curricula.

## Select one independent database

Run in a new PowerShell terminal. Selection affects this terminal and its children only; existing servers are not switched. Use one server at a time in a browser to avoid session-cookie collisions.

```powershell
Set-Location 'C:\Users\JEROME\SchedEase-Prototype'
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
# Choose exactly one:
$env:SCHED_EASE_DATABASE_URL = 'sqlite:///tertiary_final_defense.sqlite3'
# $env:SCHED_EASE_DATABASE_URL = 'sqlite:///shs_final_defense.sqlite3'
$env:PYTHONDONTWRITEBYTECODE = '1'
$defenseName = $env:SCHED_EASE_DATABASE_URL.Replace('sqlite:///', '')
if ($defenseName -notin @('tertiary_final_defense.sqlite3','shs_final_defense.sqlite3')) { throw 'Unexpected database selection' }
if (-not (Test-Path -LiteralPath $defenseName -PathType Leaf)) { throw 'Database missing; do not continue' }
python -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'; from django.conf import settings; from pathlib import Path; p=Path(settings.DATABASES['default']['NAME']).resolve(); expected=Path(os.environ['SCHED_EASE_DATABASE_URL'].removeprefix('sqlite:///')).resolve(); assert p==expected and p.is_file(); print(p)"
```

Do not run `migrate`, reset commands, old seeders, or `flush` during demonstration.

## Checks (no academic writes)

```powershell
python manage.py check
python manage.py showmigrations schedules
# Select the matching command; both call the Stage 2 validation service without passwords.
python manage.py shell -c "import runpy; print(runpy.run_path('tools/create_final_defense.py')['verify']('tertiary', {}))"
# python manage.py shell -c "import runpy; print(runpy.run_path('tools/create_final_defense.py')['verify']('shs', {}))"
```

The Stage 2 verifier expects **zero schedules** and the initial counts. Run it before Stage 3, not after generation. It checks relationships, qualifications, component totals or SHS configurations/contact-minute policies, migration state, integrity and foreign keys. It does not claim a GA solution or successful publication. For SHS, the controlled generation adapter subsequently prepares meetings and captures immutable scope evidence; no fabricated approval-evidence rows are seeded.

## Start server and use the supported workflows

```powershell
# Runtime writes: login/session activity and later UI actions write to the selected defense DB.
python manage.py runserver 127.0.0.1:8000
```

1. Log in at the application's normal sign-in page using `tertiary_demo_admin` or `shs_demo_admin` for the selected database.
2. Open **Scheduling → Generate Schedule**; select **Defense Baseline** for the applicable level and the supplied GA settings. Review inputs and submit. **Writes:** generation lease/run, prepared SHS meetings/evidence, draft schedule and entries. This is Stage 3 and was not executed during Stage 2.
3. Review diagnostics, conflicts and workload. Publish through the schedule detail's authorized **Publish** action only after validation passes. **Writes:** status transition, audit and frozen snapshots. Do not update status through SQL or Django shell.
4. Sign in as the matching `*_demo_faculty` and `*_demo_student` to review the baseline. The demo student belongs to a baseline section; `*_live_student` belongs to a live-demo section. Faculty assignments and actual published access should be verified after generation.
5. For the live defense demonstration select **Defense Live Demo**, which has a separate, non-overlapping term and no initial schedules. Generate through the same UI. Do not add assignments to a published baseline term or treat Copy to Draft as independent academic definitions.

Existing supported route names are `generate_schedule` and `publish_schedule`; use navigation rather than fabricated CLI generation/publication commands. Current safeguards enforce administrator access, leases, approved inputs, capacity, availability, workload, publication validation, and historical protections. Successful scheduling still requires Stage 3 execution; no runtime guarantee has been established.

## Credentials and password reset

Initial passwords are random, Django-hashed, and retained only in Windows CurrentUser DPAPI-encrypted files under:

`C:\Users\JEROME\SchedEase-Final-Defense-Credentials-20261104`

The directory ACL is restricted to the current Windows account and contains a wildcard `.gitignore`; it is outside the repository. Do not copy credentials into source or logs. Reset a disposable account password with the supported hidden prompt instead of printing stored credentials:

```powershell
# WRITES the selected defense database. Verify selection above first.
python manage.py changepassword tertiary_demo_admin
python manage.py changepassword tertiary_demo_faculty
python manage.py changepassword tertiary_demo_student
# For the separately selected SHS database:
# python manage.py changepassword shs_demo_admin
# python manage.py changepassword shs_demo_faculty
# python manage.py changepassword shs_demo_student
```

Resetting a password makes the corresponding encrypted initial password obsolete. Other faculty usernames follow `<level>_faculty_02` onward. All faculty and student accounts are nonstaff/nonsuperuser and linked to fictional records; only the dedicated administrator has full administrative access.

Independent databases do not detect resource conflicts with each other. No existing UAT/development database is migrated or replaced by this utility.
