# CSV export formula protection

CSV output uses `schedules/services/csv_export.py`. Protection is applied only
while writing output; stored values, authorization and scheduling logic are unchanged.

## Policy

- Prefix suspicious text with an ASCII apostrophe, before its original content.
- Detect `=`, `+`, `-`, `@` and their full-width equivalents after leading
  Unicode whitespace, control characters or format characters (including BOM).
- Also prefix text with leading control/format characters, including tab, CR,
  LF and NUL, even when the next character is ordinary text.
- Preserve ordinary text, Unicode, empty cells and actual numeric Python values.
  A negative numeric value stays numeric; untrusted text such as `-12` is
  deliberately protected as text. Numeric strings with no dangerous prefix remain unchanged.
- Quote CSV fields and double embedded quotes using Python's CSV implementation.
  Embedded delimiters/newlines therefore stay within their original cell.
  Headers and column order are unchanged; serialization now quotes all cells.

Covered outputs: schedule CSV, room-utilization CSV, import error CSV, import
sample CSV, benchmark trial CSV, benchmark summary CSV and workbook
normalization CSV. XLSX, PDF, JSON and database writes are unchanged. Benchmark
JSON remains the lossless machine interchange format when arbitrary text is involved.

## Compatibility and limits

This is the apostrophe-as-text mitigation described by
[OWASP](https://owasp.org/www-community/attacks/CSV_Injection), combined with
proper CSV quoting. The apostrophe may be visible in Excel, LibreOffice or
programmatic CSV readers depending on import settings. Consumers must not strip
it and then interpret the result as formulas. CSV has no cell-type metadata;
there is no universal guarantee across spreadsheet versions, custom delimiters,
or save/reopen transformations. OWASP specifically warns that Excel may remove
protective characters during re-saving. Import columns as text when in doubt.

No Excel or LibreOffice desktop automation/manual verification was performed.
Tests parse actual endpoint responses and generated report files using the
standard CSV reader, asserting cell boundaries, exact text, numbers, headers
and permission behavior. Synthetic fixtures and disposable databases are used.

## Verification

Validation uses Python 3.12.10 / Django 5.2.18 and the isolated launcher from
the Django upgrade task, with an explicit disposable database URL.

- Focused run: **90 passed** in 87.642 seconds (10 new CSV tests plus existing
  room-availability reporting, academic import, benchmark and benchmark-report tests).
- `manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes.
- Full suite: **674 passed** in 492.268 seconds, process exit 0; no failures,
  errors, skips, expected failures or unexpected successes. This includes all
  664 existing tests and the 10 new tests; focused results overlap this total.
- `git diff --check`: passed.
- All four pre-existing root SQLite files retained identical SHA-256 hashes
  across the full-suite run. No working database migrations or seeds were run.

The initial new-test run exposed PowerShell's non-ASCII source encoding and
Windows restricted temporary-directory permissions. Unicode escape literals
and the existing workspace test-directory convention fixed those issues;
the assertions and application permissions were not weakened.
