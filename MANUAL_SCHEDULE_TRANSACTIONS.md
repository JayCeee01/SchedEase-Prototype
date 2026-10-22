# Task 3.3: atomic manual edits

## Audit findings

The previous manual-save path already rolled back provisional overrides and entry validation failures inside transaction.atomic. However, qualification/approval decisions and the audit's previous values were read before that transaction. Requests carried no edit revision, so an older browser form could overwrite a newer edit. Schedule status was checked only in the outer view (with triggers providing the final safety net). Database-lock errors had no dedicated user-facing response.

## Save protocol

- Add/edit forms carry a signed, user-bound revision containing the schedule ID, term, status and updated_at plus the entry ID, signature and timestamp. Tokens expire after 24 hours and remain unchanged through override confirmation. Missing or stale tokens require reopening the form.
- The save service starts one atomic transaction. Its first database operation conditionally updates the draft schedule timestamp using the submitted revision. SQLite obtains its write lock before subsequent reads; a competing request either fails the revision comparison or gets a lock/busy error. select_for_update is also used but is not relied on for SQLite locking.
- Under that transaction the service reloads administrator permissions, schedule status, the current entry, effective related records, qualifications and scoped approvals. Direct entry edits that did not update timestamps are detected by the entry signature.
- If needed, an explicitly confirmed override with a nonblank reason is created provisionally. Full existing entry validation then checks term, component, duration, room, availability, workload and conflicts. The existing finalized-content triggers remain authoritative.
- The entry and its audit (including creation audits) are saved together. Any error rolls back the provisional schedule revision, entry, override and audit. Previous audit values are read inside the transaction, not from the browser.
- Validation errors are displayed. Database contention and unexpected exceptions produce a safe failure message; technical exceptions are logged. There is no silent retry of an old edit.

## Scope and limitations

This service handles the existing single-entry workflow and its multiple related records; Task 3.3 added no batch-correction UI, snapshots, removal or copying; Task 3.4 now adds removal and copying as described below. Existing assignment-form transactions remain unchanged. Direct SQL/ORM draft maintenance remains trusted maintenance code: it does not create manual-edit audits, although Tasks 3.1/3.2 triggers still protect finalized content and term consistency. Other callers should use save_manual_entry for the same edit protocol.

SQLite serializes writers across the database, not just one schedule. Busy requests must reload and retry. Edits to different entries in the same schedule conservatively invalidate older form revisions. Permissions, scheduling rules and credential rules are unchanged. No migration or dependency is needed.

Regression coverage includes real separate-connection competing writers, stale browser forms and approvals, status changes after form validation, permission revocation, missing/tampered tokens, forced audit failures, provisional-override rollback and successful creation/edit audits.


## Task 3.4: copying and removal

Copy to Draft is an administrator-only POST action on published/archived schedule detail pages. A new draft and new ScheduleEntry rows preserve the source term, placement times/rooms, and all override fields. Its first transactional write creates the destination, acquiring SQLite's write lock before copying the entries. Permissions and source status are checked again. The source receives no writes, and its audit history is not moved. A new draft audit records the source schedule and original/copied entry IDs. Errors roll back the entire destination.

Independence is at the schedule and placement level: academic assignments, meeting definitions, courses, rooms, sections and faculty remain shared references. Cloning those definitions is unnecessary for independent placement edits and would create duplicate academic requirements. Their existing finalized-content protection remains enforced. Definition changes (including new credential-override records on protected shared meeting definitions) are not unlocked by copying. No historical snapshots are created. Existing historical validation issues can be copied for review; term/foreign-key guards still apply and full publication validation remains mandatory.

Remove Meeting opens an administrator-only confirmation page for DRAFT entries. Confirmation submits POST with CSRF and the signed entry revision. Removal reuses the same atomic claim/status/permission/revision helper as manual editing. Only the ScheduleEntry is deleted. Prior audits retain their values (their nullable entry link is cleared by the existing FK policy), and a removal audit records the deleted entry ID and its previous placement. The schedule revision changes only on success. Failed deletion or audit creation rolls back entry deletion, audit-link changes and the revision. Missing requirements continue to block publication.

All actions reuse existing template classes and the application's responsive/light/dark styles. No dependencies or migrations are needed. SQLite busy failures require reload/retry; duplicate intentional copy requests create separate drafts.
