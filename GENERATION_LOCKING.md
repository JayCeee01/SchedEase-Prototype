# Task 4.4: shared generation leases

## Confirmed weaknesses

The generation view used `cache.add()` with a one-hour timeout. No shared cache backend is configured, so Django's default local-memory cache could admit one owner in each worker process. There was no renewal, no unique request ownership token, and unconditional `cache.delete()` could clear a successor's lock after expiry. GenerationRun creation occurred outside cleanup, and successful run metadata was saved after unlocking. There was no ownership check at result persistence.

## Shared scope and lifecycle

Migration `0013_generationlease` adds one small coordination table, keyed by academic term. Acquisition conditionally updates an unowned or expired row. When the row does not exist, its unique primary key arbitrates competing inserts. A fresh UUID identifies each acquisition. All application workers must use the same database file.

The default lease is 120 seconds. Cooperative checkpoints in fitness evaluation and placement generation renew at most every 40 seconds. Renewal conditionally updates only the matching, still-unexpired owner. Database time determines expiry, avoiding disagreement between application-worker wall clocks; a monotonic timer only throttles renewal calls. A renewal failure stops generation. A lease cannot revive itself after expiration.

Cleanup runs after success and exceptions, including failures before GA construction. Release matches the owner token, so delayed cleanup cannot release a successor. A database-busy cleanup is logged and leaves expiry to recover the reservation. Crashed workers need no scheduled cleanup job: the next acquisition can replace an expired owner.

`GeneticScheduler.generate()` also acquires a lease when invoked directly. The HTTP view acquires before creating its run and passes that same lease into the scheduler. Different terms have separate owners and may compute concurrently.

## Fencing and atomic persistence

Immediately before saving, a conditional ownership/expiry UPDATE is the first operation in a short database transaction. It obtains a write lock held through schedule creation, entry creation, fresh full schedule validation, successful GenerationRun update, and commit. An expired/replaced owner cannot pass this fence. Failure rolls everything back. A missing or mismatched generation run also rejects the save.

There is no transaction holding a write lock throughout GA computation. The final transaction blocks takeover while saving, even if its wall-clock duration exceeds the nominal lease. Once it commits, a successor can acquire only after release or expiration. This is fencing: at most one owner is authorized to generate/save for a term. A paused or stalled process cannot be forcibly stopped by a database lease; after takeover it may finish a piece of in-memory computation before its next checkpoint, but it cannot renew or commit a stale result. This does not promise immediate OS-level cancellation of old CPU work.

Only new drafts are created. Existing academic validation, hard-first scoring, feasible placements, targeted repair, finalized schedule protection, snapshots and publication rules remain intact. The placement service's only change is an optional renewal callback; its options and validation rules are unchanged.

## Feedback and permissions

The existing login, administrator and CSRF checks remain. Contention displays a retry/wait message without creating a failed GA run or error-log issue. Losing ownership produces a separate reservation-expired/stopped message; any existing run is marked failed using its existing status fields. Genuine validation and unexpected failures retain their existing safe error-log behavior. No Task 4.5 error schema is introduced.

## Deployment

Stop/drain existing application workers before deploying: workers running the old cache-only implementation do not honor the new database fence. Back up the database according to the existing deployment practice, then run:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
```

Start workers on the new code only after migration. The migration is tested on fresh test databases; the developer's existing database was not migrated by this task. All workers must share the same SQLite database on storage with reliable SQLite file locking. Separate database copies cannot coordinate. The current settings support SQLite; other database engines have not been certified here.

## Deterministic evidence

`test_generation_lock.py` uses barriers/events and controlled clocks, not sleeps:

- Two HTTP requests on separate Django connections to a cloned SQLite test file start together. The winning GA waits until its competitor receives the busy response. Exactly one successful run and one schedule exist afterward; the lease is released.
- Two separate connections acquire different term leases and rendezvous while both are held, confirming independent scopes.
- Stale and fabricated tokens cannot renew, release successors, or enter persistence. Takeover during computation rejects the old scheduler's final save.
- Controlled time advances through repeated renewals beyond the initial deadline, both for the lease service and a real GA run.
- Validation, run-record and unexpected failures roll back partial writes and release leases. Forced cleanup failure recovers after expiry.
- Authorization/CSRF checks, draft-only output and unchanged published/archived snapshots are verified.

The old cache-lock regression now acquires the database lease instead; its contention and no-duplicate assertions are retained.

## Limitations

SQLite serializes writes across terms; independent computations can run together, while brief acquisition/renewal/final-save transactions may wait or return a safe busy response. The lease duration must accommodate the longest uninterrupted computation/I/O segment. A worker paused for longer than its lease is intentionally rejected on resumption. No background heartbeat thread or worker service is introduced.

After a hard process crash, an existing GenerationRun may still display RUNNING; the lease row, not this historical status, determines admission. Reconciliation of historical run status and structured error records is not implemented here. A later intentional generation after the prior run finishes is allowed; this is scope exclusion, not permanent request idempotency. Production-scale throughput and additional database backends are not claimed by the two-connection tests.

## Verification results

Using the existing virtual environment:

- `manage.py test schedules.test_generation_lock`: 26 passed.
- Combined requested GA fitness, placements, repair, finalized-protection, term-protection and snapshot suites: 106 passed.
- `manage.py test`: 334 passed in 210.920 seconds (308 previous plus 26 new); zero failures, skips, expected failures or unexpected successes.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no additional changes detected.
- `git diff --check`: passed; only Git's README line-ending conversion advisory.

Fresh test database creation applied migration 0013 successfully. The tests' deliberate exception logs exercise rollback and safe error responses; they are not test failures. The developer database and its existing uncommitted changes were left untouched.

Task 4.4 implementation and regression verification are complete. Deployment still requires applying the included migration before starting the updated workers. Task 4.5 was not started.

Task 4.5 subsequently adds lease-token-aware recovery of stale historical RUNNING records on administrator error-log access. See [GENERATION_DIAGNOSTICS.md](GENERATION_DIAGNOSTICS.md). Acquisition, renewal and save fencing remain unchanged.
