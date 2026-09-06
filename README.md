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

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_sample
python manage.py runserver
```

After pulling changes that add migrations, run:

```powershell
python manage.py migrate
python manage.py seed_sample
```

Open `http://127.0.0.1:8000`.

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

## Tests

```powershell
python manage.py test
```

## Deployment Notes

Set `SCHED_EASE_DEBUG=False`, provide a strong `SCHED_EASE_SECRET_KEY`, set `SCHED_EASE_ALLOWED_HOSTS`, collect static files with `python manage.py collectstatic`, and run behind a production WSGI server. For PostgreSQL deployment, replace the simple `SCHED_EASE_DATABASE_URL` handling in `sched_ease/settings.py` with `dj-database-url` or explicit Django database settings.
