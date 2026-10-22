# Task 4.5: structured generation diagnostics

## Confirmed weaknesses

The active generation view previously split exception strings on semicolons, guessed categories from keywords, and found the first teaching meeting whose course code matched a message prefix. A course shared by sections or multiple meetings could therefore be linked incorrectly. Final failures lost exact relationships, and issue insertion and failed-run status were separate writes. Historical RUNNING records had no token tying them to a specific lease owner.

## Representation and storage

`services/diagnostics.py` defines `Diagnostic`: category, message, severity, explicit meeting IDs, parent assignment IDs, optional room ID and constraint details. `GenerationFailure` carries these objects while remaining a `ValueError` for existing callers. No IDs are extracted from prose in active generation.

In this application's schema, `TeachingAssignment` is an individual meeting and `Assignment` is its parent. The existing `GenerationIssue.assignment` foreign key continues to identify a primary live TeachingAssignment for backwards-compatible lists and filters. The new `GenerationIssue.details` JSON field stores all explicit meeting IDs and parent assignment IDs, original room ID, constraint details, a schema version and a deduplication fingerprint. These IDs survive reference deletion; the primary nullable foreign keys still use their existing relationships. Each issue retains its existing generation-run FK, category, severity, explanation, guidance and resolution status.

Global issues have empty reference arrays. Multi-meeting conflicts contain every affected meeting. Reverse reports of the same resource conflict pair are deduplicated. Failure recording conditionally changes only RUNNING runs and writes issues in the same transaction; retries cannot duplicate reports or downgrade successful runs.

Migration `0014_generationissue_details_generationrun_lease_owner` adds the JSON field and nullable `GenerationRun.lease_owner`. It does not rewrite old diagnostic messages or guess historical references. Old records default to empty structured details and retain their existing display fields.

## Integration without new scheduling rules

- Preflight checks emit diagnostics where their existing capacity/type, qualification, duration and workload checks fail. Workload issues identify all affected meetings.
- Empty placement domains preserve the known meeting and existing rejection reasons. Existing component/duration validation emits typed metadata through an optional collector.
- Only the final unsuccessful candidate emits resource-overlap and individual-validation diagnostics, plus its existing hard/soft summary. Fitness, genetic operators and conflict repair are unchanged; no intermediate-candidate issue rows are written.
- Entry validation emits metadata alongside its existing errors. Full model validation remains authoritative. The final schedule validation message list carries its structured issues, preserving the existing list interface for other callers. Remaining model/field errors use INVALID_DATA with the known entry's meeting, without guessing a category from text.
- Missing meetings and aggregate component totals carry explicit meeting and parent references.
- Final validation still occurs inside Task 4.4's fenced save transaction. Exceptions roll back draft entries before their diagnostic records are written. Successful run persistence and lease checks are unchanged.
- Unexpected exceptions are logged server-side; user-visible records contain a fixed safe explanation. An unstructured ValueError is a global failure, never an invitation to infer IDs or expose arbitrary exception text.

The legacy `record_generation_messages` adapter remains for compatibility with existing integrations/tests. It is not called by any active generation path; existing historical rows are displayed directly, not reparsed.

## Display, correction and privacy

The existing error log shows when an issue affects multiple meetings. Its detail page lists all known meetings and links to each existing parent assignment editor, whose existing permissions and finalized-record safeguards remain enforced. Missing meetings display an unavailable-record message using the preserved ID. Historical records without structured details retain their previous display.

Detailed logs, detail pages and status recovery remain administrator-only. Student/faculty requests cannot access diagnostics or trigger recovery. Templates use standard escaped output. Existing list filters continue to use the primary live reference; all references are available in the detail page.

## Stale status recovery

New HTTP runs record the exact lease token acquired by Task 4.4. An administrator explicitly selects **Review Interrupted Runs** in the Error Log to submit a CSRF-protected POST. Viewing the log does not change run records. `recover_stale_runs()` considers only RUNNING records. Its conditional first write checks authoritative current lease state inside the transaction:

- Token-bound runs remain running only while the same owner has an unexpired lease.
- Legacy runs without tokens remain untouched while any unexpired owner holds their term, because original ownership cannot be reconstructed safely.
- Expired, missing or replaced reservations cause the old run to be marked failed, with one structured recovery explanation in the same transaction.

The recovery query rechecks lease state at the write, not just during discovery. It never renews, releases or replaces a lease. Successful/completed runs and audit history are preserved. If failure recording itself encounters a database error, it rolls back, returns a safe response and leaves the run recoverable on a later administrator recovery request.

## Regression coverage

`test_generation_diagnostics.py` covers explicit IDs despite misleading text, categories/severity, multiple parent assignments and meetings, globals, domain failures, shared validators, identical-text conflict pairs, final-save rollback, atomic status/issue failure, safe exception handling, deleted references, historical display, correction links, student/faculty privacy, stale/active/replaced ownership and the discovery-to-write recovery race.

The existing hard-fitness failure-workflow test keeps all its summary/status/rollback assertions and now also requires the three resource-conflict records and exact meeting IDs. Its old single-row assumption was updated to select the summary by category. Other previous tests remain intact.

## Deployment and limits

Stop old workers, apply migrations, then restart the updated code:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
```

Migration 0014 depends on Task 4.4's migration 0013. Fresh test databases exercise migration application; this task leaves the developer database untouched. Do not mix old and new worker code during deployment.

Recovery is lazy on administrator history access, not a background job. Legacy runs with an active term lease are deliberately preserved until ownership is no longer ambiguous. Historical wrong/missing associations cannot be reconstructed reliably and are not rewritten. SQLite write-contention limitations from Task 4.4 still apply. Very large unsuccessful candidates can produce many final conflict records; the existing log displays at most 500 rows, and no intermediate candidates are persisted. No dependencies, scheduling policies, GA operators, locking redesign or Phase 5 work are introduced.

## Verified results

Using the existing Python 3.12.10 / Django 5.0.6 virtual environment:

- Focused diagnostics, locking, GA fitness/placements/repair, known-defect, finalized-protection, term-protection and snapshot suites: 159 passed.
- Full suite: 358 passed in 222.104 seconds (334 previous tests plus 24 new); zero failures, skips, expected failures or unexpected successes.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no additional changes detected.
- `git diff --check`: passed, with only the existing README line-ending conversion advisory.
- Test database setup applied migration 0014 successfully. Legacy-record display tests passed. The developer database was not migrated or rewritten.

Files changed for Task 4.5: `schedules/models.py`, `schedules/views.py`, `schedules/services/diagnostics.py`, `generation_issues.py`, `ga.py`, `placements.py`, `conflicts.py`, `meetings.py`, migration `0014_generationissue_details_generationrun_lease_owner.py`, `schedules/test_generation_diagnostics.py`, `schedules/test_ga_fitness.py`, `templates/schedules/error_detail.html`, `templates/schedules/error_log.html`, `README.md`, `GENERATION_LOCKING.md`, and this document.

Task 4.5 is complete; deployment requires applying the migration before restarting updated workers. No Phase 5 work or commits were performed.
