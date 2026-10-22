# Task 6.1: administrative pagination and search

## Inspection and scope

The shared `resource_list` view sliced results at 200 rows. Its browser-side
search and header sorting could see only those rendered rows. Most resources
did not preload foreign keys used by their display labels. Assignment meetings
were prefetched, but a meeting inheriting its duration still fetched its subject
individually. Error Log issues and generation history were capped at 500 and 100
rows respectively; Error Log search already used ORM filtering.

Updated pages:

- Departments, programs, year levels, sections and courses.
- Credentials, faculty credentials and course credential requirements.
- Faculty, students, rooms, academic terms and assignments.
- Availability, GA settings and credential overrides.
- Schedule lists (Active, Drafts, Archived).
- Error Log issues and generation history, with independent page controls.

Timetable grids, role-scoped schedule browsing, availability editors, analytical
dashboards, imports and exports are not administrative record-list tables and
retain their existing behavior. Personal unfinished-form draft panels and filter
selection controls also retain their existing scope.

## Implementation

`schedules/services/listing.py` provides shared search mappings, related-record
loading definitions, query-string links and Django `Paginator` navigation.
Pages contain at most **20 records**. SQL performs filtering, ordering and
LIMIT/OFFSET before rows or meeting collections are materialized. Stable primary
key tie-breaking follows every ordering. The previous default/date sort options
remain, and existing clickable table headers now sort the complete matching
queryset rather than only the current browser page. No new filter categories or
Task 6.2 sorting/count features were added.

Missing, nonnumeric, fractional, zero and negative page numbers select page 1;
numbers beyond the end select the last page. Empty lists use page 1 of 1.
Navigation includes Previous/Next and elided page numbers. Links preserve active
query parameters, including search, sorting, schedule status and Error Log
filters. Submitting a new academic search/sort resets to page 1. History uses
`run_page` and `run_q` independently of issue `page` and `q`.

`templates/schedules/_pagination.html` reuses the existing button classes and
theme colors, with wrapping navigation for narrow screens, keyboard-accessible
links and `aria-current`. Column links expose `aria-sort`. Search uses a labeled
GET form and works without JavaScript. Existing CSS tokens support both themes;
no sidebar or transition code changed. The topbar's existing local-table search
remains labeled as searching the tables currently shown; the list's own Search
form searches all matching records in the database.

## Search fields

Search trims whitespace and uses case-insensitive partial matches through safe
ORM expressions. Literal percent/underscore and other special characters are
escaped by Django's LIKE handling, not interpolated into SQL.

| Lists | Search scope |
| --- | --- |
| Departments, programs | Code/name; programs also department code/name |
| Year levels, sections | Label/level; section name, program code/name, formatted section label |
| Courses | Course code and description |
| Credentials | Credential name |
| Faculty credentials | Faculty name/employee ID and credential name |
| Course requirements | Course code/description, required credential and accepted equivalent names |
| Faculty, students | Name and employee/student identifier; students also section/program |
| Rooms | Name, room-type code/display label |
| Terms | Name and school year |
| Assignments | Course, section, faculty name/employee ID, term name/school year |
| Availability | Faculty name/employee ID, room name, availability kind and weekday label |
| GA settings | Settings name |
| Schedules | Name, term name/school year and status, within the selected status tab |
| Credential overrides | Faculty name/employee ID and course code/description |
| Error Log | Existing course/section/faculty/room/problem searches and filters |
| Generation history | Requested name, term name/school year and status |

Many-to-many equivalent-credential searches use `distinct()` to avoid duplicate
requirements. Section searches reuse the existing formatted-section parser;
unreasonably large numeric input is not converted into an overflowing database
integer. Search fields and ordering are allowlisted, never derived directly from
user-provided SQL or field names.

## Performance and action scope

- Academic list queries use one filtered COUNT and a bounded SELECT, plus
  page-scoped prefetch where needed. Foreign-key display labels use
  `select_related()`.
- Assignment meeting prefetch includes the subject needed for inherited
  durations. In the test dataset, the prior data/render access required **26
  queries for 25 assignments**. The new complete HTTP rendering required **7
  queries for a 20-assignment page**, including authentication and draft lookup.
  This comparison has different row counts and includes more request overhead
  in the new figure; it is not a runtime benchmark.
- A filtered 200-record department dataset uses exactly **two department-table
  queries** (COUNT and SELECT with `LIMIT 20 OFFSET 20`) for page 2. Records beyond
  the former 200-row cap remain reachable.
- Error Log summary counts still cover the entire filtered dataset. Pagination
  reuses the existing total instead of issuing another identical COUNT.
- Generation-run filter choices are separate from the paginated history and
  include all runs, loading only their IDs and timestamps. Filtering does not
  silently become restricted to the current history page.
- CRUD handlers, export/bulk-operation queries, permissions, schedule generation
  and finalized/term protection services are unchanged. No scheduling data is
  modified by the list changes.

## Verification and limitations

`schedules.test_listing` covers all resource-page rendering, first/middle/last
pages, ties, invalid/empty pages, database search, literal characters, related
search and deduplication, parameters, role permissions, CRUD, schedule tabs,
full filtered issue totals, history choices and query bounds. Existing export,
import and schedule-protection tests remain part of the full suite.

Case-insensitive matching and ordering use the database's collation; non-ASCII
case behavior depends on the configured backend. Text contains searches and
COUNT/large OFFSET queries can still scan substantial data. No index or backend
change was justified by this task. Filter dropdowns and personal draft panels
remain complete collections; converting them to remote selectors is outside
Task 6.1. No production-scale performance claims or browser automation claims
are made.

No dependencies, migrations, GA changes or Task 6.2 work were introduced.

### Verification results

- Targeted list, finalized-schedule and term-protection tests: **44 passed**.
- Full suite: **452 passed in 266.190 seconds**, comprising all 435 previous
  tests and 17 new list tests. Zero failures, errors, skips, expected failures
  or unexpected successes. Existing tests were not weakened or modified.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.
- Representative multi-page lists and navigation were verified using Django's
  test client and captured SQL. Desktop/mobile behavior uses wrapping controls
  and existing theme styles; no live browser automation was available.

Task 6.1 is complete. No commit was created and Task 6.2 was not started.
