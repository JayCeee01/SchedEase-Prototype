# Phase 2 checkpoint: schedule workspace context

## Phase 2C academic CRUD checkpoint

Implemented:
- `academic_crud.py` centralizes request-level/term consistency, scoped model-choice
  fields, authoritative existing-record context, and dependent academic validation.
- Application create/edit/delete forms and the assignment editor reject explicit
  wrong-level identifiers; edit forms infer the existing record level when omitted.
  Legacy Program/Term create forms that omit the level field use explicit context.
- Django Admin forms and object/bulk deletion use the same context checks in the
  administrator permission mixin. Existing Django/application permissions remain.
- Protected model validation and ordinary-save signals reject assignment/meeting
  term-versus-section mismatch and parent program/term/section changes that would
  invalidate dependent assignments. Shared faculty, rooms and subjects stay shared.
- New additive migration `0036_academic_level_guards` independently checks inserts,
  updates, bulk operations and replacement inserts across 16 academic tables.
  It validates program/term levels; assignment/meeting section compatibility;
  cohort/program/grade; curriculum/pathway relationships; offering curriculum,
  grade, pathway, school year and period; operational configuration/participation;
  and meeting-pattern component/plan identity. Existing delete/FK/history guards
  are retained. It refuses incompatible existing data rather than rewriting it.
- Migration reversal removes only its 32 triggers. No existing migration changed.

Deployment: **0036 tested in disposable in-memory SQLite only. Not applied to
unified_schedease.sqlite3 or any other persistent database.** Database enforcement
requires a separate migration deployment review. Do not claim deployed Phase 2
write isolation while that migration is pending.

Verification: the 32-test selection passed 31 with one new legacy-program-form
failure (a local variable shadowed its model scope). That defect was corrected.
The final targeted 15-test run passed all tests, including the added Admin/offering
test, context tests and parent assignment synchronization. The unchanged scheduling
scope and SHS generation tests passed in the prior selection: 33 distinct tests
passed across the completed runs. Django checks and migration consistency passed.
Migration forward/reverse trigger identity, FK and integrity checks passed. All 18
inventoried existing/unified database hashes remained unchanged. No full suite or
browser run. No persistent database connections were used by Django verification.

Remaining limits:
- Subject ownership/applicability remains undefined and is not inferred from usage.
- Curriculum and operational models retain their existing Django validators;
  database guards add independent scope checks, not a new approval mechanism.
- The SQL guards currently evaluate cross-table invariants on each relevant write;
  large import performance needs measurement before production deployment.
- Not all administrative tools (imports, recovery utilities, draft replay,
  specialized review endpoints) were re-audited for submitted URL-context handling.
  Schema guards protect the listed persisted invariants once deployed, but this
  is not a claim that every endpoint preserves context navigation or friendly errors.
- Certain draft SQL operations may still create a schedule-entry override needing
  correction; existing Phase 2B validation blocks incompatible publication.
- Review normal administrative error presentation for rare concurrent changes
  rejected by a database trigger; a full concurrent-edit UX audit was not performed.

Phase 2 status: core academic persistence protections implemented and rehearsed;
**not yet fully deployed or exhaustively verified application-wide**. Next approve
0036 deployment/rehearsal review on the unified database, inventory the remaining
specialized administrative endpoints, and benchmark guards before global navigation
or reporting expansion. Do not apply it automatically to Final Defense/UAT files.

## Phase 2B scheduling-write checkpoint

Completed without migrations:
- New `academic_scope` service validates schedule/term/submitted level agreement.
  Loaded schedule identity remains authoritative for existing context-free URLs.
- Entry create/update/remove, correction application, copy-to-draft and publication
  views reject contradictory or duplicate submitted context. Combined cannot be
  submitted for these writes. Schedule CRUD checks submitted context as well.
- Direct publication and manual save/remove/copy services accept optional explicit
  level/term assertions and validate them inside their existing transaction.
- Shared entry validation rejects both an original assignment section and an
  overridden section from the wrong academic level. Publication revalidates this
  even if a different writer placed inconsistent data into a draft. Manual saves
  check it before any provisional credential approval.
- Existing actor authorization, optimistic revision checks, SQLite write locking,
  snapshot creation, notifications and finalized protections remain intact.

Verification: 11 focused tests passed, zero failures/errors/skips, using rollback
transactions only on unified_schedease.sqlite3. Django checks and SQLite integrity
passed; zero foreign-key violations. All 18 inventoried database/backup hashes,
including the unified database, were unchanged (`env/unified-phase2b-hashes.json`).

**Phase 2B remains partial.** General academic CRUD form scoping and parent-record
mutation protection are not completed. In particular, program/term/section edits
can require checking dependent assignments, not just the edited form. Subject has
no education-level applicability field; no exclusive ownership was inferred from
current assignments. Existing SHS curriculum/offering validators are unchanged.
Raw SQL/bulk draft writes have not gained new database-level level constraints;
they cannot use the publication/manual-save services to finalize inconsistent
sections, but prevention at the original academic write still needs work.
Other administrative mutation endpoints and Django Admin require a separate path
inventory before claiming application-wide enforcement. No global selector rollout
is authorized by completion of this checkpoint.

Next: finish academic CRUD dependency validation and shared-subject applicability
policy, then apply the context consistently to remaining mutation endpoints and
confirmation forms. Assess additive database guards only after those invariants are
settled. Do not expand global navigation first. Browser and full-suite verification
were not performed.

## Completed

`services/education_context.py` centralizes explicit `education_level` and `term`
resolution. Valid values are TERTIARY, SHS and COMBINED. It rejects duplicate,
malformed, unavailable and mismatched term/level parameters, including conflicting
GET/POST context. It never grants permissions: callers provide authorized terms.
Single-level callers can infer their existing level; mixed-level generation must
submit an explicit level and term. No session or persistent global selector exists.

Integrated screens:
- Manage Schedules list: level/term scoping before counts, search and pagination;
  scoped term choices and context-preserving management/published primary tabs.
- Browse Published: existing authorization first, then level scoping, then filter
  options, historical presentation, counts and table/timetable selection.
- Generate Schedule: scoped term choices, hidden submitted level, rejection of
  Combined/mismatched context before lease acquisition. Cross-level section/term
  assignments block generation before either engine runs.
- Personal PDF/XLSX exports: browse reuses the same scope; explicit detail-source
  exports also reject a conflicting level. Existing visibility remains mandatory.

The compact selector deliberately resets term/record filters on a level change,
avoiding stale cross-level selections. Applying ordinary filters retains the level;
view switches/export URLs retain the applied query. No timetable renderer changed.

## Not complete — do not treat this as global write isolation

Academic CRUD, administrator dashboards, manual edits, publication actions, shared
resource management, workload/utilization reports and general sidebar navigation
are not integrated with this context yet. Their existing authorization and history
protections remain unchanged. Schedule-detail navigation is not yet context-aware.
The selector scopes the implemented pages only, not every application operation.

Combined is rejected for generation; a global Combined write policy is not yet
implemented. Existing Manage actions still use their existing authorization and
record identity. No claim is made that all direct writes are education-level scoped.

Next coherent phase (before declaring full Phase 2 complete): integrate context
with academic forms and every schedule mutation form/confirmation/redirect,
including publication and manual revision. Add level-consistent relationship
validation for ordinary academic writes and assess database-layer enforcement.
Only then propagate a global selector/sidebar context. Faculty/rooms must remain
shared rather than acquire artificial ownership. Extend dashboards/reports after
that boundary is tested. No additional permissions or institutional approvals were
invented in this checkpoint.

## Verification and safety

- Six focused Django TestCase tests passed (0 failures/errors/skips), executed by
  unittest directly against the selected unified database with rollback, not a
  separate test database. Tested valid/invalid contexts, single-level inference,
  scoped lists/options/navigation, generation rejection before lease, student and
  faculty exports, unauthorized students, and both export source paths.
- Django system checks passed. No migration or schema change.
- All 18 inventoried root/backups database hashes matched before/after, including
  unified_schedease.sqlite3 and both Final Defense databases. Test records did not
  persist. Baseline: ignored `env/unified-phase2-hashes.json`.
- No browser checks, full suite, concurrency suite, or complete mutation-workflow
  regression was run. Those are not claimed as verified.
- Branch remained development; no commit/reset/push/branch operation.

Use the same explicit database environment instructions as Phase 1. Source changes
also affect other environments if their servers reload this working tree; their
database files were not connected to or changed by this task.
