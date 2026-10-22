# Task 3.6: immutable historical schedules

## Architecture

`ScheduleSnapshot` stores one versioned JSON document per schedule, with a capture timestamp and an explicit `reconstructed` flag. The only relational link is the protected schedule identity. Historical display fields are scalar values, not lookups into mutable academic records.

Schema v1 captures schedule identity/name/origin/score and finalization metadata; term identity/name/year/dates; entry, parent assignment and meeting IDs; meeting index/component/required and actual durations; day and times; effective course code/title/units/hours; effective faculty ID/employee ID/name; section ID/code/display name/size; program and year-level identities and labels; room identity/name/type/capacity/active state; placement overrides; matching credential approvals including the original approving username and justification. Publication audit metadata includes actor, time, and replaced schedule ID. Unrelated personal information is excluded.

## Capture and lifecycle

Migration 0012 creates five SQLite triggers. AFTER INSERT and AFTER UPDATE OF status capture a snapshot whenever a schedule becomes published or archived and has none. Capture runs in the same SQL statement as finalization, including direct SQL and bulk ORM operations. A capture error aborts the status write. Existing snapshots are retained unchanged during archiving. BEFORE INSERT rejects draft snapshots and replacement (including INSERT OR REPLACE). BEFORE UPDATE and BEFORE DELETE reject all snapshot mutations. Model save/delete provide clear errors; bulk operations are protected by the database.

Publication first claims the current draft revision with a conditional write inside an atomic transaction. This obtains SQLite's writer lock before validation, permission checks, replacement checks, archiving and audit creation. The status update captures the snapshot, including its publication audit. The service verifies snapshot existence before commit. Any error rolls back the revision, previous schedule's archival metadata, publication audit and new snapshot. Competing or stale publishers cannot both finalize the same draft. SQLite contention is reported as a retryable failure; there is no silent retry.

The snapshot records status and timestamps at capture. Later archival time and replacement identity remain protected lifecycle metadata on the schedule; archiving does not rewrite publication history. Direct maintenance finalization without a publication time/actor preserves null and reports it as unknown. The normal publication service validates the complete schedule; snapshots do not make invalid maintenance data valid or relax existing constraints.

## Backfill and missing information

0010 and 0011 are unchanged. 0012 reconstructs existing finalized schedules transactionally from the records available when migration runs. Each is marked reconstructed, with capture time separate from original publication time. Entries are ordered by ID and missing related values remain null using LEFT JOINs. Warnings identify missing publication time, missing term dates, empty schedules, and incomplete entry relationships. Original publication actor metadata may be unavailable. Reconstructed data cannot establish what labels were before migration.

`python manage.py backfill_schedule_snapshots` uses the frozen v1 capture SQL, inserts only missing snapshots inside one transaction and reports known gaps by schedule ID. It is idempotent and never overwrites history. The versioned capture SQL is intentionally frozen in migration 0012; future schema evolution requires a new migration. Back up the database before deployment; reversing the new migration removes historical storage and its guards.

## Historical viewing and permissions

Details, table/timetable displays, personal dashboards, browsing and CSV/PDF exports project authorized entry IDs from snapshot values. The full snapshot JSON and credential approval justifications are not exposed through public views. Existing published-only access for students/faculty and section/faculty filtering remain in force; archived pages remain administrator-only. Non-admin filter choices are restricted to visible academic identities. Missing snapshots fail closed rather than silently displaying live values.

Finalized displays are marked read-only and do not revalidate historical placements against today's availability or credentials. Drafts continue to validate live data. Existing finalized-content and term guards remain enforced, so snapshot creation does not unlock shared academic definitions. Copy to Draft continues to create new placement identities referencing those protected definitions.

## Verification and boundaries

Migration was tested on a temporary SQLite copy of the existing sample database at 0011: two archived and one published schedule were reconstructed, all schedule statuses/timestamps and entry counts were preserved, rerunning backfill created zero rows, all five triggers existed, and direct SQL update/delete attempts failed. The original sample database was not migrated or edited. The default development database had no schedules and was migrated to 0012.

Regression tests cover field capture, actor/approval metadata, model/bulk/SQL immutability, replacement attempts, automatic SQL capture, rollback of archive/audit/status changes, missing-trigger failure, duplicate and concurrent SQLite finalization, backfill idempotence/atomicity, incomplete records, permitted live changes, role-specific display/export access, and draft/copy behavior.

This prototype supports SQLite. A database owner able to drop triggers or rewrite the database file can bypass database safeguards; snapshots are not cryptographic attestations. Existing analytical reports remain live operational reports; they are not redefined as historical snapshot reports. Browser theme/responsive rendering uses existing components and has not been visually automated.
