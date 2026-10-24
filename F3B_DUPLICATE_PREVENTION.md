# F-3B: normalized identifier uniqueness

## Approved scopes

| Record | Identifier | Scope |
| --- | --- | --- |
| Department | Code | Global |
| Program | Code | Global |
| Course (Subject) | Code | Global |
| Faculty | Employee ID | Global |
| Student | Student ID | Global |
| Room | Name | Global |
| Credential | Name | Global |
| Academic term | Name and school year | Combined pair |
| Section | Section code | Program and year level |

Department/program names, course titles, year-level labels, and personal names
remain non-unique. Existing relational uniqueness constraints remain unchanged.

## Comparison and validation

`schedules.identity` compares strings with Python `strip().casefold()`. This
ignores surrounding Unicode whitespace and handles Unicode case variants.
Internal whitespace, punctuation, accents and leading zeros are not removed.
Comparison does not rewrite stored identifiers. Existing form trimming and
section-code formatting continue to apply.

Student IDs still require ASCII digits, reject surrounding whitespace, and keep
leading zeros. The existing narrow exception for unchanged legacy IDs remains.
Employee IDs retain their existing string validation and alphanumeric support.

Model uniqueness/constraint validation supplies field-specific errors; normal
ModelForms and Django admin reuse it. The current record is excluded during
editing. Spreadsheet import identity matching and repeated-row detection use
the same comparison. Both workbook import commands reuse normalized matches.
Existing import skip/update behavior and finalized-record protections remain.

## Database migration and compatibility

`0020_normalized_identity_uniqueness` adds nine unique expression indexes while
retaining existing constraints. SQLite migration SQL creates indexes only: no
table rebuild, row rewrite, or trigger replacement. Index creation fails if a
database contains normalized collisions; resolve these separately with owner
approval, never silently merge or delete records.

SQLite connections register the deterministic function `schedease_identity_v1`.
It uses the same comparison as application validation. Unique indexes also
reject duplicate ORM bulk writes and raw SQL writes that bypass forms. Normal
SQLite locking and index enforcement remain in effect; no application-level
read-then-write check is treated as a concurrency guarantee.

**Operational requirement:** after applying this migration, use this application
version for writes and integrity checks. Standalone SQLite tools and older
application versions must register the identical function; otherwise operations
requiring those indexes fail rather than bypass protection. The existing backup
and restore service registers it and verifies expression-index definitions.
Recovery tests exercise the same registration. PostgreSQL support is not added.

Do not change version-1 normalization or upgrade its Unicode semantics without
reviewing index compatibility and planning an explicit index migration. Restoring
an older backup requires the matching application release and the existing
controlled migration process.

No migration was applied to working databases during implementation. Do not
apply it to development or UAT databases without separate authorization.

## Verification

Focused tests cover normalized identifiers, Unicode and surrounding whitespace,
scoped terms/sections, unchanged edits, legitimate duplicate personal names,
Student ID compatibility, admin/forms, spreadsheet skip/update matching, both
workbook persistence paths, bypassed ORM/raw SQL writes, and backup/recovery.
Tests use disposable databases. Multi-worker UI race behavior is not separately
load-tested; final duplicate rejection is enforced by the unique indexes.
