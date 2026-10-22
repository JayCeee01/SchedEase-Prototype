# Task 3.1: finalized schedule protection

## Confirmed audit findings (before implementation)

- Published/archived entry editing is blocked in views, but Schedule and ScheduleEntry model saves, admin, QuerySet.update/bulk_update, and bulk creation bypass those view checks.
- H1 guards parent shared-field saves when any schedule references a meeting. Bulk updates bypass that guard; child duration/component edits are not frozen.
- Timetables render live Subject, Faculty, Section, Program, YearLevel, Department and Room records, including entry overrides. Renaming or reassigning these records changes finalized content.
- Schedule deletion cascades to entries and edit audits. AcademicTerm deletion can reach schedules; ordinary term-field editing is explicitly outside Task 3.1.
- Existing PROTECT foreign keys help deletion but do not prevent updates, entry reassignment, schedule status reversal, or removal of edit audit history.
- Spreadsheet imports validate current feasibility but can still change protected labels or otherwise-valid requirements.
- Publication archives a previous official schedule; this deliberate transition must remain possible without unlocking its content.


## Implemented protection

`protection.py` supplies model/form validation and pre-save/pre-delete guards. Migration 0010 installs SQLite triggers for protected content updates, deletions and replacement inserts. The triggers enforce protection for QuerySet.update, bulk_update, bulk_create, cascades and direct SQL as well as ordinary model saves. Multi-batch bulk_update and imports retain their transaction rollback behavior. Protected deletion raises ProtectedError; bypassing model validation raises IntegrityError with the same actionable lock message.

Protected content includes schedules, entries, referenced parent assignments and meetings, course/faculty/section/room details, program/year/department labels and relationships, effective overrides, and associated edit/credential-override audits. New meetings cannot be attached to a protected parent. Unrelated draft records and non-content source metadata remain editable. H1's existing restriction on parent shared fields referenced by any schedule is preserved.

Publication rechecks status and validation inside its transaction. Its internal archive_transition scope permits only PUBLISHED-to-ARCHIVED metadata changes; it cannot change content or reopen an archive. Ordinary admin or bulk status changes cannot unlock finalized records. Admin deletion permission checks provide feedback before database enforcement.

## Deployment and boundaries

Run `python manage.py migrate` to install 0010 on every database. It adds triggers only and does not rewrite existing schedule data. The project supports SQLite; another backend requires equivalent guards before deployment. Application connections register the lifecycle function used by the triggers. External connections cannot authorize archiving without the function and fail closed.

A database owner able to drop triggers or modify schema can bypass database safeguards; this is outside ordinary application mutation paths. Future schema migrations affecting protected tables must preserve/reinstall these triggers. Bulk callers should catch database errors outside transaction.atomic blocks, not inside a broken transaction.

This is content protection, not historical snapshots. Task 3.2 now protects referenced academic-term identity and dates as described below. Credential and availability policies are unchanged and remain live. Snapshotting those policies and labels is deferred to Task 3.6. No Copy to Draft feature is included.


## Task 3.2: academic terms

Audit: 0010 already freezes finalized schedule/assignment/meeting term references, but did not freeze AcademicTerm names, school years, or dates. Draft schedule term edits and bulk parent/meeting edits could leave inconsistent cross-term references. Imports select an existing term rather than importing or editing term fields; their assignment keys include that term.

Migration 0011 adds 11 triggers without changing any of the 39 triggers in 0010. Referenced terms are protected through direct schedule references and through meeting/parent term references (including legacy inconsistent records). Names, school years, start/end dates, primary-key replacements and deletion are blocked. The is_active selection flag remains editable because it does not change historical identity or dates.

Draft schedules can move terms when empty. A populated draft cannot move until its entries are removed or otherwise made consistent; this task does not automatically migrate entries. Unscheduled parent assignments retain the existing atomic model-save synchronization of their meetings. A narrowly scoped connection function authorizes that specific parent/target-term pair during the transaction. Bulk parent term changes with unsynchronized children are rejected. Entry insert/update and meeting insert/update enforce matching terms, including replacement inserts. Model forms receive validation messages before database enforcement.

Install with `python manage.py migrate`. The new migration contains triggers only and rewrites no records. Existing legacy inconsistencies are not repaired automatically; affected relationship edits must correct them, and publication still performs full validation. Unrelated terms remain editable. Historical snapshots and Copy to Draft remain out of scope.
