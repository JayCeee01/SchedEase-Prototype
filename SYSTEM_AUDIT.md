# SchedEase system audit

## Scope

Reviewed project structure, models, relationships, authentication and roles, administrative CRUD, faculty availability, student/faculty schedule access, credentials and overrides, rooms and utilization, terms, assignments, manual editing, publishing, imports/exports, dashboards, tooltips, responsive/dark styling, generation feedback, GA implementation, seed data, workbook import tooling, and automated tests.

## Already implemented and working

- Admin, faculty, and student roles with backend decorators on administrative and faculty-only workflows.
- Published-only browse results and role-specific dashboard schedule lists.
- Faculty, room, and section overlap detection.
- Capacity, room-type, faculty-unavailability, room-availability, credential, allowed-day, and operating-hour validation.
- Credential equivalents and audited administrator overrides.
- Meeting-level lecture/lab component, duration, room requirement, and workbook provenance support.
- GA selection, crossover, mutation, elitism, reproducible seeds, soft distribution/idle-gap/preference/capacity/utilization scoring, final feasibility rollback, and accessible generation loading state.
- Draft/approved/published statuses and distinct imported/generated origins.
- Room-utilization dashboard and CSV/PDF exports.
- Full and representative workbook import commands, normalization/conflict/utilization reports, and original/generated comparison reporting.
- Responsive layout, light/dark mode, contextual tooltips, empty table states, and delete confirmation pages.

## Problems found and improvements implemented

### Critical

- Publishing previously checked only overlap conflicts. It now validates every entry for term, duration, time, capacity, room type, availability, credentials, weekly load, duplicates, and all missing/unscheduled term requirements.
- Manual entries could use an assignment from another term or an arbitrary duration. Both are now rejected.
- The same teaching requirement could be inserted twice into one schedule. A database uniqueness constraint now prevents this.
- GA credential scoring ignored approved credential overrides. Overrides are now honored consistently.
- An infeasible or invalid GA result is still rolled back; generation preflight now explains missing compatible rooms, missing credentials, excessive workload, and impossible duration before spending time evolving candidates.

### High priority

- Any authenticated user could previously open/export a draft schedule by guessing its ID. Non-admin access is now restricted to published schedules.
- Publishing was a state-changing GET request. It is now POST-only, CSRF protected, and confirmed in the UI.
- Published schedules could be manually edited. They are now locked; administrators must work on a draft/generated version.
- Frontend duplicate-submit prevention did not stop simultaneous HTTP requests. A term-scoped backend generation lock now rejects a second run and is always released after success or failure.
- Availability could belong to both a room and faculty. Application and database validation now require exactly one owner.
- Conflict explanations now identify the affected subjects, faculty/room/section, day, and overlapping times.
- Missing requirements appear as explicit “Unscheduled class” issues with subject, section, faculty, duration, and room type.

### Medium priority

- Protected deletes could expose a server error. Administrators now receive guidance to remove or reassign dependent data.
- Unknown administrative resource slugs now return 404 rather than causing a key error.
- Manual assignment choices are restricted to the schedule’s term.
- Unexpected generator errors are logged server-side and shown as friendly UI errors without saving a partial schedule.
- GA settings validate rates and elitism/population relationships; academic terms validate date order.
- Room-utilization fitness now counts fractional hours correctly.
- The admin dashboard now includes subjects, active rooms, scheduled/unscheduled classes, schedule issues, and average room utilization.
- Edit controls are no longer shown to non-admin schedule viewers.

## Database changes

- `0004_full_workbook_support.py`: meeting-level requirement fields and schedule origin.
- `0005_integrity_constraints.py`: exactly-one availability owner and one entry per assignment per schedule.

## Remaining recommendations

- Add fixed/preassigned meeting locks that the GA carries unchanged. Published schedules are locked, but individual draft meetings cannot yet be pinned.
- Add explicit archived status and restore/compare UI. Separate schedule records already preserve prior versions, but there is no archive workflow.
- Add minimum/contract teaching load and a faculty workload report. Maximum load is enforced; underload is not an invalid-schedule rule today.
- Add section-specific availability, institution lunch/break rules, campus/department operating windows, shared/cross-listed meeting groups, and consecutive lecture/lab policies only after the institution defines them.
- Move long GA runs to a durable background worker with persisted run status. The current synchronous request has a real indeterminate loading state and a process/cache lock, but it cannot report generation-by-generation progress or survive a server restart.
- Improve full-dataset convergence with constructive initialization/conflict repair. The feasibility gate correctly refuses invalid output, but the current evolutionary search cannot reliably solve the 721-meeting workbook workload.
- Replace the development cache with a shared cache in multi-process production so generation locks work across all workers.

## Verification

- 27 automated tests passed.
- Django system check passed.
- Migration consistency check reported no missing migrations.
- `git diff --check` passed.
