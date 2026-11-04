# Final-defense database implementation blueprint

Preflight: 2026-11-04. Planning only; no database created, opened, migrated, or populated. Neither proposed target currently exists in the repository. This document is the only intended file change.

## Decision and source status

Create two independent, fictional demonstration environments in the repository:

- `C:\Users\JEROME\SchedEase-Prototype\tertiary_final_defense.sqlite3`
- `C:\Users\JEROME\SchedEase-Prototype\shs_final_defense.sqlite3`

The exact requested reference filenames ending in `(6).xlsx` and `(4).xlsm` are absent. The directory contains these provisional alternatives:

- `C:\Users\JEROME\SchedEase-References\TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx`
- `C:\Users\JEROME\SchedEase-References\Main Template - Class Schedule and Faculty Count Projection_SY 25-26.xlsm`

These are not proven to be the requested versions. Confirm their acceptance before deriving an import mapping. They were opened read-only with openpyxl; no macros were executed and no files saved.

Relevant inspection: tertiary `SCHED_REGISTRAR` and `TER SCHED 2T2526` provide section/course/day/time/room/instructor columns, separate lecture/laboratory rows, and sometimes compound day/time notation. SHS `3.3 - SHS Term 1 ` and `3.4 - SHS Term 2` provide pathway/grade-period/classification/title/specialization/LEC/total/section-count/load columns; `4.2 - SHS Schedule` provides placement columns. `5 - Computer Lab` is a capacity projection, not institutional approval of workload or curriculum rules. Its cached projection already shows demand potentially exceeding capacity; do not copy its totals as guaranteed feasible inputs.

Use structural conventions and representative subject types only. All persons, identifiers, account names, academic records, and approval references must be fictional. Workbook units, workload formulas, and lecture totals must not be silently interpreted as scheduled contact minutes. This is a reduced teaching demonstration, not a complete STI/DepEd curriculum.

## Proposed counts per database

Counts below are targets requiring disposable rehearsal, not verified feasibility results.

| Record | Tertiary | SHS |
| --- | ---: | ---: |
| Departments | 2 | 1 |
| Programs | 3 | 2 |
| Year/grade levels | 4 | 2 (11, 12) |
| Curriculum versions / pathways / cohorts | 0 / 0 / 0 | 1 / 2 / 4 |
| Academic terms | 2 | 2 |
| Sections | 8 | 8 |
| Faculty | 12 | 12 |
| Subjects | 12 | 16 |
| Rooms | 8: 6 lecture, 2 computer laboratories | 8: 6 lecture, 2 computer laboratories |
| Synthetic students | 160: 20 per section | 160: 20 per section |
| Credential types / faculty credential links | 4 / 24 | 4 / 24 |
| Subject credential requirements | 12 | 16 |
| Assignments: baseline / live demo | 24 / 8 | 24 / 8 |
| Prepared meetings: baseline / live demo | 48 / 16 | 24 / 8 |
| SHS requirements / offerings / plans / components | 0 / 0 / 0 / 0 | 16 / 24 / 24 / 24 |
| SHS configurations / meeting patterns | 0 / 0 | 32 / 32 |
| Faculty contact-minute policies | 0 | 12 |
| Initial published schedules / drafts | 1 / 0 | 1 / 0 |
| Initial schedule entries | 48 recurring placements | 48 dated occurrences over two weeks |
| Entries expected from live demo | 16 recurring placements | 16 dated occurrences over two weeks |
| User accounts | 21 | 21 |

Account split: one ADMIN, twelve FACULTY, eight STUDENT (one linked representative per section). Other student records need no login. Additional SHS participation rows start at zero: use single-section teaching for the baseline. A combined-class variant is optional and requires a separately specified offering, participant roster, capacity and approval scope; it changes counts and must be rehearsed separately.

SHS distribution: two pathways times two grades gives four cohorts, each with two sections and four subjects. Baseline includes six sections across all four cohorts (2/2/1/1); live demo uses the other two sections. Sixteen baseline cohort/subject offerings plus eight live-demo offerings produce 24 plans/components. Plans may serve separate section assignments with consistent validated requirements. Each component requires two 60-minute occurrences over its two-week period; each assignment has one weekly weekday pattern.

Tertiary distribution: four subjects per section, three integer contact hours per subject weekly. Pure lecture subjects use two 90-minute meetings; mixed subjects use 120 lecture minutes plus 60 laboratory minutes. Each assignment therefore has two meetings; never interchange lecture and laboratory allocations. Units are separate metadata.

## Isolation and initialization procedure (future authorized work)

1. Confirm exact absolute targets, source workbook versions, current code/migration head, and absence of either target or target SQLite sidecars. Stop if either exists; never overwrite or reuse it silently.
2. Hash all nine existing database files and reference workbooks. Do not migrate existing sources, copy old accounts, or load old datasets. Preserve backups.
3. Use a separate process per target with an explicit `SCHED_EASE_DATABASE_URL`, no persistent `.env` edits. Inspect Django's resolved `DATABASES['default']['NAME']` before opening a connection; abort unless it equals the approved target. Never rely on fallback `db.sqlite3`.
4. Rehearse initialization/population on disposable databases first. Apply current migrations through `0034_publication_membership` to each new approved target only; recheck the migration head before execution. Each database receives its own schema and records independently.
5. Verify expected tables, migration records, protection triggers, SQLite `integrity_check`, and zero `foreign_key_check` rows. Use explicit in-memory Django settings for tests: the project's simple URL parser does not itself special-case `sqlite:///:memory:`.
6. Reject nonempty/partial population rather than clearing it. Use transactional population with model validation. On error retain diagnostic evidence and stop; do not reset unrelated files.
7. Recheck protected hashes; confirm education-level separation, role links and expected counts. Store timestamped SQLite-backup-API backups outside the repository after successful preparation/publication.

Future launch selection from the repository root: `$env:SCHED_EASE_DATABASE_URL = 'sqlite:///tertiary_final_defense.sqlite3'` or `'sqlite:///shs_final_defense.sqlite3'`. Verify the resolved path before `python manage.py runserver`. Separate terminals/processes do not inherit later environment changes. If running both simultaneously, use distinct ports and cookie names to avoid browser login collisions.

## Creation order and service contracts

1. Securely provision administrator and Profile role `ADMIN`; active/staff/superuser for dedicated defense administration. Faculty/student users: active, corresponding Profile role, neither staff nor superuser. Use Django password validation/hashing with hidden input or approved encrypted credential delivery; no passwords in source, logs, or blueprint.
2. Departments, programs, year levels; SHS synthetic curriculum/version/pathways/cohorts; terms; sections; rooms; faculty and students with explicit unique account links. Preserve leading-zero student IDs and alphanumeric employee IDs.
3. Credentials, faculty validity records, and subject requirements. All assigned faculty must independently qualify; no credential overrides in the base dataset. Issue dates must be on/before term end and expirations absent or at/after term end. Use separately approved immutable scope evidence if a later override scenario is needed.
4. Subjects and complete term assignment sets. Create every baseline requirement before publication. Membership changes in finalized terms are blocked by `0034`; Copy to Draft is not an independent revision of shared academic definitions.
5. SHS requirements, approved offerings, plans/components, assignments/configurations, section participation, patterns and full-week workload policies. Mark references explicitly `Synthetic final-defense scenario; not STI/DepEd institutional approval`. No actual institutional curriculum activation.
6. Use the existing administrator-authorized, lease-aware `generate_shs` preparation path. It captures immutable approval evidence transactionally via `shs_approval.new_preparation`; do not fabricate evidence rows or reuse legacy seeder flags as proof of approval. Existing prepared inputs require the explicit review/reapproval workflow.
7. Generate baseline drafts through existing generation services. Validate all requirements, credentials, capacity, compatibility, availability and resource conflicts. Publish with `publication.publish` and a real authorized actor; never direct-save final status. Verify snapshot and SHS binding evidence.
8. Keep the live-demo term unpublished and without schedules. Verify both role dashboards, authorized exports and historical views after baseline publication. Verify demo generation on a disposable copy, leaving final live-demo schedules uncreated.

Dependencies already declared: Django 5.2.18, openpyxl 3.1.5, et-xmlfile 2.0.0; reuse current export dependencies. No new dependency is proposed. Existing `seed_fictional_shs_uat` is a useful model-validation/account-storage example but has hardcoded counts and dates. `rehearse_workbook_uat` consumes a different normalized workbook format, deletes academic records, and refuses repository databases. Neither should be run unchanged for this task.

## Feasibility and demonstration boundaries

- Use separate non-overlapping baseline/live-demo terms, e.g. fictional 2026-11-02 through 2026-11-15 and 2026-11-16 through 2026-11-29, with matching school-year/period/cohort context. These are proposed demonstration dates, not an institutional calendar. A published baseline and freely editable live demonstration must not share term membership.
- SHS only Monday-Friday; school operating range is 07:00-19:00. Proposed demonstration windows 08:00-16:00, 30-minute granularity, no holidays assumed. Tertiary retains its existing Monday-Saturday rules, though this baseline can use weekdays.
- Room capacity at least 30 for sections of 20. Explicit computer-laboratory patterns only for appropriate components; omit culinary, chemistry, gym and equipment-specific scenarios until capability/policy mappings are established.
- Tertiary baseline demand is 72 contact hours/week across rooms; live demo is 24. SHS baseline is 24 contact hours/week, live demo 8. Aggregate capacity alone does not prove feasible faculty/section/room intersections. Balance assignments and precompute a valid placement witness before bounded GA rehearsal.
- Proposed synthetic SHS limit: 600 contact minutes/faculty/calendar week, configured over complete Monday-Sunday weeks and explicitly verified/approved as fictional. Preserve separate tertiary maximum-hour validation. Numeric limits and timings require user acceptance before population; never present them as STI policy.
- Reuse shared rooms/faculty within each database. Independent databases do not detect conflicts with each other; do not claim the pair demonstrates cross-database occupancy protection.
- Use a small seeded live scenario (eight assignments) for predictable demonstration time; tune existing GA settings only after bounded rehearsal. No runtime or success guarantee until measured. Do not change GA weights or constraints.
- Historical meetings use frozen content; current room-policy overlays and filter context are not a complete archive of original constraints. Demonstrate protected history honestly, not unrestricted post-publication academic editing.

## Acceptance and next step

After explicit authorization: first confirm which workbook versions are authoritative and approve this fictional count/date/policy scope. Then implement a new create-only, path-guarded preparation utility and rehearse both complete datasets on disposable databases using current migrations, authenticated roles, bounded GA generation, authorized publication, exports, integrity checks and hash preservation. No final-defense database should be created until rehearsal evidence is reviewed under the requested deployment authorization.

Current blockers: requested filename/version mismatch; no feasibility timing for this proposed medium dataset; synthetic account-password delivery and numeric/date choices not yet finalized. No schema or GA change is currently justified. Existing regression baseline is 1,073 passing tests, reused rather than rerun for this preflight.
