# Task 6.2: record counts, sorting and filtering

## Scope and inspection

Task 6.1 supplied SQL search, stable header sorting and 20-row pagination, but
academic lists displayed only the current page length. Most lists had only
record/date sorting and no filters. Task 6.2 extends the same shared view and
template for all 17 resource lists. Existing admin permissions apply before any
record counts or filter options are queried.

Updated lists: departments, programs, year levels, sections, courses, credentials,
faculty credentials, course credential requirements, faculty, students, rooms,
academic terms, assignments, availability, GA settings, schedules and credential
overrides. Error Log, timetable browsing, analytical dashboards and exports retain
their existing workflows. Diagnostics access-control changes belong to Task 6.3.

## Counts and scope

Every list shows **total**, **matching**, and **Showing start–end**. Total means
all records in the administrator's current list scope, before optional search
and filters. Matching means records satisfying all selected filters and search.
Both stay constant across pages. Empty results show `Showing 0–0`.

Schedules are scoped to Active (published), Drafts (draft or approved), or Archived
before counting. Counts never include another tab. An optional term filter narrows
matching records, not the tab's total; it does not override the tab restriction.
There is no existing department-specific or term-specific restriction for the
administrator role. Faculty, students and unauthenticated users cannot access
these lists or their counts/options. Role-scoped timetable browsing is unchanged.

## Controls

All sorting supports ascending/descending and a unique primary-key tie-breaker.
Existing date options and default `modified_desc` behavior remain. On models
without timestamps, the existing date-sort fallback is record ID order.

| List | Additional sorting (existing Record/date sorts remain) | Filters |
| --- | --- | --- |
| Departments | Name | None |
| Programs | Department | Department |
| Year levels | Numeric year level | None |
| Sections | Section name, program, numeric year | Program, year level |
| Courses | Existing code/description, department, units | Department, required room type |
| Credentials | Existing record/name | None |
| Faculty credentials | Issue and expiration dates | Faculty department, credential |
| Course credential requirements | Existing course/required credential | Course department, required credential |
| Faculty | Department | Department |
| Students | Section | Program, year level |
| Rooms | Capacity, room type, active status | Room type, active status |
| Academic terms | Start and end dates | Active status |
| Assignments | Existing course, faculty, section, term | Term, course department, section program/year |
| Availability | Day, start time | Day, availability kind |
| GA settings | Existing record/name | None |
| Schedules | Academic term, status | Term, status within selected tab |
| Credential overrides | Existing faculty/course | Faculty department |

Faculty has no status field; courses have no classification field. Neither was
invented. Sort keys and ORM paths are explicit application-owned allowlists.
Invalid sorting falls back to the existing default. Related sorting uses only
single-valued relationships; equivalent-credential search remains deduplicated.

Filter IDs must match available administrator-visible records. Enumerations and
boolean values must match the offered choices. Invalid/deleted selections show
an explanation, remain visible as “Unavailable selection”, and return no matches
until corrected or cleared. They never silently broaden results. Contradictory
valid filters return zero matches. No filter invokes scheduling validation or
changes records.

## State and presentation

The existing GET form includes search, all relevant filters and sort. Submitting
it resets pagination. Header sorting resets the page while retaining selections.
Pagination retains search, sort, filters and schedule tab. Tab changes retain
term/search/sort but clear status (which could conflict with the new tab) and page.
Clear search and filters retains the sort and tab. Direct URLs work without JS.

Navigation keeps only supported parameters, with one value per key. Repeated
parameters use Django's last-value convention. Invalid sort/tab values normalize
to safe defaults. Parameter values are URL-encoded and template-escaped.

Controls wrap on narrow screens, use existing theme styling, and have associated
labels. Headers keep `aria-sort`; invalid controls have `aria-invalid`, messages
have `role=alert`, and the count summary has `role=status`. CRUD links, exports,
bulk-operation scope, sidebar behavior and schedule safeguards are unchanged.

## Query behavior and limitations

Total and matching counts use one aggregate SQL query (conditional count with a
filtered-ID subquery). Unfiltered lists use one ordinary count. The paginator
reuses the matching count. Rows and meeting prefetch remain page-bounded.

Foreign-key filter options use one ORM UNION query across the needed models,
loading only IDs and labels. Choice-only filters need no option query. On the
existing 25-assignment fixture, full HTTP rendering takes **8 queries** versus
Task 6.1's **7**, within its unchanged eight-query test budget. The extra query
provides all four filter dropdowns. Filtering/search/page 2 still uses eight
queries and one combined count. Department search remains two department-table
queries (count plus bounded rows), as in Task 6.1. These are query-count
measurements, not production runtime benchmarks.

Filter options remain complete collections; very large option lists may warrant
remote selectors in a separate task. Contains searches, counts, and deep OFFSET
pages can still scan substantial data. Text ordering and null placement follow
database conventions. No dependencies, indexes or migrations were added.

## Verification

`schedules.test_list_controls` adds 19 tests for counts/ranges, permissions,
term/tab scope, sort directions/ties/injection resistance, every added sort,
filter choices, combined search/filter/sort, stale selections, M2M deduplication,
state/reset links, duplicate parameters and SQL query bounds.

Verification completed:

- The unchanged 17 Task 6.1 tests and 19 new tests pass together (36 tests).
- Full suite: **471 passed in 298.486 seconds**, preserving all 452 previous
  tests. Zero failures, errors, skips, expected failures or unexpected successes.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.

UI rendering and multi-page behavior are tested using Django's client; no live
browser visual verification has been performed. Task 6.2 is complete within
this verification limit. No commit was created and Task 6.3 was not started.
