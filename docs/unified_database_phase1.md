# Unified development foundation — checkpoint 1

This is a new development environment, not a replacement for either Final
Defense database. Work stayed on the existing `development` branch.

## Completed

- New repository-root `unified_schedease.sqlite3`, initialized using all current
  supported migrations through schedules `0035_schedule_notifications`.
- SQLite integrity: `ok`; foreign-key violations: 0; installed triggers: 172.
- Existing `*.sqlite3` ignore rule covers this new database.
- A target-locked, transactional `seed_unified_development` command. It requires
  the explicit environment URL and exact resolved repository-root filename,
  refuses missing/symlinked/hard-linked files, never resets data or passwords,
  and rejects changes to its existing representative identities rather than
  overwriting them. Repeating the unchanged seed adds no duplicates.
- 2 programs, 3 terms, 2 sections, 2 subjects, 3 assignments, 1 tertiary meeting,
  1 shared faculty record, 1 shared lecture room, a synthetic qualification and
  subject requirements, weekday availability, 1 SHS curriculum/pathway/cohort,
  2 offerings/plans/configurations and 2 dated meeting proposals.
- Tertiary term: August 3–16, 2026. SHS terms: August 3–16 and September 7–20.
  These are explicitly fictional overlapping/nonoverlapping development dates.
- No imported accounts, credentials, historical records, schedules or snapshots.
  No persistent SHS approvals or workload ceiling were invented.

The representative curriculum is inactive/unverified; offerings/plans are
unapproved and operational configurations unconfirmed. SHS generation correctly
remains blocked. The room reference explicitly says UNAPPROVED; it is not an
approval. Synthetic approved configurations were used only inside rolled-back
tests. Existing services already support both levels in one database and shared
resources; no GA or publication changes were necessary for this checkpoint.

## Verification

Tests ran directly through unittest with Django TestCase transaction rollback
against ONLY the new unified database, before persistent seeding. No Django
test database was created; no flush or migration rollback was used.

- Initial selection: 34 tests, 32 passed, 2 seed errors (required room reference).
- Corrected seed selection: 3/3 passed.
- Additional tertiary-after-published-SHS generation/publication test: 1/1 passed.
- Final aggregate: all 35 distinct selected tests passed after correction.
- Existing selections: ControlledSHSGenerationTests, ContactPolicyTests,
  PersonalExportTests and ScheduleWorkspaceTests. These exercise SHS generation,
  dated recurrence, cross-level occupancy/workload, publication, nonoverlapping
  terms, permissions, browse/timetable and personal exports.
- New tests verify idempotency, refusal of seed drift, wrong-target rejection
  before connection, inactive approval blocking, and shared-engine tertiary
  generation after SHS publication.
- `check`, `showmigrations schedules`, and migration consistency passed.
- The seed command ran twice successfully. No test schedules persisted.

Do not run a normal test runner against this populated database: it may create
another test file or flush fixtures. Future testing must retain the approved
target-only/rollback-only isolation arrangement or obtain authorization for a
separate disposable test database.

## Deliberately unfinished integration

This is a coherent database/seed/service-verification checkpoint, NOT completion
of the full Phase 1 UI feature. No education-level UI selector was added.

1. Add a shared authorized level/term resolver, then integrate write forms and
   read views together. A decorative selector without server-side scoping would
   be unsafe. Keep existing faculty/student authorization as the outer boundary.
2. Close general assignment term/section-level compatibility gaps consistently
   across normal writes, parent edits and relevant database constraints. Existing
   SHS-specific validation and the seed enforce compatible relationships, but
   this checkpoint does not claim all ordinary academic edits are level-scoped.
3. Scope generation, management, browsing, dashboards, reports, export links and
   filter options. Combined context is read-only; faculty and rooms remain shared.
4. Explicitly review any synthetic SHS approvals and workload configuration for
   this environment before enabling its persistent SHS demonstration data.
5. Add integrated scoping/crafted-request tests and concurrent cross-term
   publication tests. No concurrency tests or browser checks ran here.

No historical consolidation, approval import, flexible editing, migration changes,
or changes to existing production protections were implemented.

## Run this environment

```powershell
Set-Location C:\Users\JEROME\SchedEase-Prototype
.\.venv\Scripts\Activate.ps1
$env:SCHED_EASE_DATABASE_URL = 'sqlite:///unified_schedease.sqlite3'
python -B -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'; from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
python -B manage.py check
# Optional: writes ONLY to the explicitly selected unified database.
python -B manage.py createsuperuser
python -B manage.py runserver
```

No administrator password or account was generated automatically. The existing
UI remains available but does not yet offer unified level-scoped navigation.
The environment variable affects only this shell and its child processes.

To verify/repeat the representative seed (writes only missing records):

```powershell
python -B manage.py seed_unified_development
```

Original root/backup database hash evidence is retained locally in
`env/unified-original-database-hashes.json` (ignored). Two pre-existing temporary
directories denied read access during inventory; nothing there was accessed or
modified. No existing database was connected to by Django during this task.
