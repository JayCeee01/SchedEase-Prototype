# Database backup and isolated restore (Task 8.2)

## Initial audit and safety scope

The starting working tree was clean. SQLite is the sole configured backend, selected by `SCHED_EASE_DATABASE_URL` (legacy `DATABASE_URL` fallback), defaulting to project-root `db.sqlite3`. Settings/security from Task 8.1 remain unchanged. No existing full-database backup/restore command was found. CSV/PDF exports and academic spreadsheet imports do not preserve the complete database and are not recovery backups.

The application has migrations 0001–0015, depending on Django auth/contenttypes alongside installed admin/session migrations. They establish academic foreign keys, unique/check constraints and indexes; migration 0010 installs finalized-record guards, 0011 adds academic-term guards, 0012 stores immutable JSON historical snapshots with capture/protection triggers, 0013 adds per-term generation leases, and 0014–0015 add structured diagnostics and reproducibility metadata. No migration is modified or applied to the real database by this task.

Safety rules: never replace/delete an existing database; never restore into a configured database or default development path; never change live settings automatically; never migrate a restored copy automatically; use only newly created disposable destinations for drills. No force option exists. All fixtures and recovery mutations in this task are synthetic and isolated. No school data is used.

A read-only inspection found 12 recorded `schedules` migrations in the local development database, while the repository contains 15. Its schema contains 55 triggers. This discrepancy was reported, not repaired. The real database was never migrated, backed up for the drill, restored or edited. Compatibility checks for backups from that database may require review with the corresponding release. Do not interpret `makemigrations --check` as confirmation that a particular database has applied every migration: it checks models against migration files.

## Commands and prerequisites

Use the existing Python 3.12 environment. No new package is required. These commands support file-backed SQLite only, not in-memory databases, URI database names or other engines. Run them from a trusted checkout with the same settings/environment as the database you intend to back up. Production mode still requires Task 8.1's private environment configuration.

Choose an access-controlled directory outside every web-served directory, with sufficient free space for a complete database and temporary copy. The parent directory must already exist. The filename must end in `.sqlite3` or `.db`. Paths in the following PowerShell examples are placeholders: replace them with approved private locations, not public assets.

```powershell
# Example private directory; create it and restrict its ACL before use.
python manage.py backup_database --output "C:\PrivateBackupLocation\schedease-new-backup.sqlite3"

# Restore ONLY into a new disposable file in an existing private directory.
python manage.py restore_database `
  --source "C:\PrivateBackupLocation\schedease-new-backup.sqlite3" `
  --destination "C:\PrivateRecoveryLocation\new-disposable-restore.sqlite3"
```

`backup_database --database <alias>` supports another explicitly configured SQLite alias; default is `default`. Both commands accept `--timeout 60`, a positive integer up to 3600 seconds. Neither command has overwrite, force, migration or activation options. A restore does not change application configuration or start workers against the copy. Live replacement/cutover is outside this procedure and this task.

Only the final location and status are printed. Compatibility warnings and failures do not print academic records or raw SQLite exceptions. Paths themselves should avoid sensitive personal information.

## Consistency and atomic publication

The utility opens a separate read-only SQLite connection to the source with `mode=ro`, then uses `Connection.backup()` to copy committed database state. It does not use a main-file-only copy, SQL dump/reload, or Django fixture export. SQLite's backup API handles active databases and WAL contents. See [Python's backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup) and [SQLite's online backup documentation](https://www.sqlite.org/backup.html).

The copy is written to an exclusively created `.schedease-<random>.partial` file beside the destination. After backup, it is converted to self-contained DELETE journal mode, validated, closed and flushed. A hard link then publishes the verified file at the final name without replacing an existing file. The temporary name and any temporary SQLite sidecars are removed. There is no unsafe overwrite fallback if the filesystem does not support hard links.

Normal failures and Python interruptions clean temporary files. A concurrent creator of the destination wins safely: the backup command fails and preserves that file. A process kill or power loss can leave a private `.partial` file; do not treat it as a successful backup. An administrator should inspect and remove abandoned temporary files only after confirming no operation owns them. File flushing and atomic naming do not guarantee survival of hardware/storage failure or a sudden power loss; maintain independently verified copies according to an approved policy.

Concurrent committed writes can make backup take longer or restart work; long write locks can cause a bounded timeout. A WAL test confirms committed rows are included and uncommitted rows excluded while the writer remains open. A rollback-journal exclusive-lock test confirms failure and cleanup. Plan larger backups during quieter periods and monitor duration/free space. The snapshot represents one consistent committed database state, not necessarily the state at command invocation. Do not compare a live, changing source's row counts to a later backup as if they must be identical.

SQLite may need existing WAL/SHM access or sidecar bookkeeping for a live WAL source; the utility never requests source data writes or checkpoints. Read-only storage lacking necessary WAL access may fail safely. Back up through SQLite while the relevant WAL files remain available; never detach or delete live journal/WAL files.

## Destination protections

Both operations reject:

- Existing destination files/directories, including equivalent normalized paths and any existing `-wal`, `-shm` or `-journal` sidecars.
- Every identifiable configured database path and the default project `db.sqlite3`, even if the destination does not yet exist.
- The source path itself. An existing hard-link alias is also rejected as an existing destination.
- Symbolic links, Windows junctions and other reparse points in database path components.
- Configured STATIC_ROOT, STATICFILES_DIRS (including prefixed entries), MEDIA_ROOT and the conventional project static/media directories.
- Missing parent directories and unsupported output extensions.

The destination directory's identity is checked again before publication; creation of the final name is atomic and exclusive. Storage directories must nevertheless be owned by trusted operators and not writable/renameable by hostile users. Portable path checks are not a complete defense against an attacker concurrently replacing parent directories. External web-server mappings and unconfigured production paths cannot be discovered automatically; administrators must choose an approved private location. No existing file is ever eligible for replacement, whether recognized as production or not.

## Integrity and migration compatibility

Every finalized copy passes `PRAGMA integrity_check` and `PRAGMA foreign_key_check`. Table counts are collected internally without logging rows. Restore additionally requires:

- Exact agreement between recorded Django migrations and the current installed migration files (including Django's installed apps).
- Current managed tables and columns, primary-key/non-null flags, expected field/unique indexes and foreign-key relationships.
- Existing model constraint/index expectations and exact normalized SQL for the frozen protection triggers from migrations 0010, 0011 and 0012.

A structurally sound older database can still be backed up, with a compatibility warning. Restore rejects migration/schema/guard drift for manual review with the matching application release. Neither command repairs schema, fabricates migration records, disables triggers or runs migrations. Backups are not a way to upgrade an older database implicitly.

These checks target the current application and its guards, not every conceivable manually altered SQL expression. They do not authenticate the provenance of an attacker-controlled database or replace a signed/encrypted backup policy. Only restore trusted backups. Future migrations, squashed histories or backend changes require re-evaluation of this compatibility policy.

The synthetic drill compares the full ordered `sqlite_master` definitions (tables, indexes and triggers), all table rows including migration history, primary keys, foreign keys, timestamps and JSON values. Sorting is deterministic; timestamps are preserved exactly rather than regenerated. Comparisons are between quiescent synthetic databases. File hashes independently confirm that the source and backup stay unchanged.

## Academic and historical preservation

The fixture is created in a fresh interpreter with explicit disposable settings, never by importing deployment settings. It applies current migrations only to that new file, then creates synthetic departments, programs, year levels, sections, faculty, rooms, credentials, course requirements, a term, parent assignment, lecture and laboratory meetings, and a small seeded GA-generated schedule. Publication and Copy to Draft produce archived, published and draft records with snapshots and audits. Generation history, reproducibility JSON, a diagnostic and an active lease are included.

The drill confirms that backup/restore preserves all of these records and their links. Seven prohibited mutations on the restored database reject changes to a finalized schedule, archived entries, meeting duration, parent faculty, academic-term identity, snapshot JSON and snapshot deletion. Ordinary reads continue to work. The raw SQLite test connection registers the same unprivileged guard functions used by the application; it grants no archiving or term-sync privilege. SQLite functions are connection-level behavior, not stored backup objects; normal Django startup still registers them via `SchedulesConfig.ready()`.

## Generation leases and operational recovery

Backups preserve leases, owners, expiry times, Running records, completed history and reproducibility metadata faithfully. Restoring does not clear or reuse a lease. Do not start generation against the drill copy or connect old workers to a recovered database.

Before any separately authorized future cutover, stop/isolate old workers, review stored lease expiry and verify clocks. The existing lease mechanism blocks an unexpired owner. After expiry, a new owner can acquire; old owners cannot renew/save. Existing administrator Error Log recovery reconciles stale Running records when no matching unexpired lease exists, marks interrupted runs failed and adds diagnostics. It does not rewrite successful history. Do not manually delete locks to bypass this process.

The second drill phase runs only against the disposable restored file: it confirms the active lease blocks acquisition, simulates elapsed time by expiring that fixture lease, invokes the existing stale-run recovery, and verifies successor acquisition and old-owner rejection. Original source and backup hashes remain unchanged. No GA or lease logic was modified.

## Storage security and unresolved operations

`.gitignore` now excludes `.sqlite3`, `.db`, their sidecars, private temporary copy names and conventional `backups/`/`recovery-drills/` directories. This is accidental-commit prevention, not access control; never force-add confidential backups. No public download route or cloud integration was added.

On POSIX, temporary files are created with owner-only mode 0600 and that mode carries to the final hard link. Windows requires correctly restricted parent-directory ACLs; the utility does not manage institutional ACL policies. Use approved encryption at rest and protected transfer/storage. A database backup can include academic information, password hashes, session data, audits and import payloads. Keep it out of static/media assets, shared source repositories and public logs.

Retention, backup frequency, recovery-point/recovery-time objectives, encryption/key custody, off-site storage and deletion approval require operational decisions. No retention policy or automatic backup deletion is invented here. Database-only backups do not include secret keys, application code, dependencies, static sources or externally stored files: retain the matching release and secret-management recovery plan separately. Recovering under a different signing key may invalidate sessions and signed data; never store the key inside this backup procedure.

Hard-link publication requires a compatible filesystem such as local NTFS; FAT-style or some network storage may fail safely. Other database engines, live replacement, multi-database consistency and restoring an untrusted/mismatched release are unsupported. The current unsupported Django baseline and Task 8.1 deployment prerequisites remain separate concerns.

## Recovery drill and verification

Run the isolated drill or the full focused tests in PowerShell:

```powershell
python manage.py test schedules.test_database_backup.DatabaseBackupTests.test_synthetic_end_to_end_recovery_drill --noinput
python manage.py test schedules.test_database_backup --noinput
python manage.py test --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

The harness creates unique directories under ignored `recovery-drills/`, uses synthetic databases, and removes only its own checked directory afterward. No actual school database is used. The developer's database is read only for initial migration/schema inventory and before/after byte-hash comparison.

| Verification | Result |
|---|---|
| Focused backup/restore suite | 17 passed; strengthened parent-faculty protection drill also passed separately and in the full suite. |
| SQLite integrity and foreign keys | Passed on synthetic backup and restored copy. |
| Full schema/row comparison | 38 tables / 236 rows matched exactly, including migration history, placements, components, snapshots, audits and metadata. |
| Restored guards | 55 triggers and 92 indexes preserved; all 7 prohibited mutations rejected. |
| Schema drift rejection | Missing migration record, missing protection trigger and missing required index each rejected without finalizing a restore. |
| Lease recovery | Unexpired lease blocked; simulated expiry recovered the stale run; old owner rejected. |
| WAL/locks/failures | Committed-only WAL snapshot passed; lock timeout, interruption, permission-error simulation and finalization-race cleanup passed. |
| Full existing + new test suite | 530 passed in 374.339 seconds: all 513 existing plus 17 new. Zero failures/errors, skips, expected failures or unexpected successes. |
| Django system check | Passed, no issues. |
| Migration dry-run | Passed, no changes detected. |
| Git whitespace check / real database hash | Passed; new files also checked for whitespace/conflict markers. Real configured database SHA-256 unchanged from the read-only audit. |

Initial focused runs found a Windows read-only-handle flush failure and synthetic fixture field/function setup errors. These were corrected without changing application models or weakening guards; the focused suite then passed. No tests are skipped or marked expected failure. Deployment settings did not change, so Task 8.1 deployment checks were not rerun for this database-only change.

Task 8.2 is complete. No real database was changed, no dependencies/migrations were added, no deployment or commit was performed, and Task 8.3 has not begun. The local migration-history discrepancy and production storage/cutover decisions remain separate follow-up work.
