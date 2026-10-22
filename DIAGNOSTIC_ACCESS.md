# Task 6.3: diagnostic access audit

## Policy and findings

Internal generation issues, constraint details, input fingerprints, parameters,
override reasons and edit-audit payloads are administrator-only. Application
authorization reuses `admin_required`: an authenticated superuser or a user with
the existing ADMIN profile role. Faculty, students, users without that role and
anonymous users cannot read or update these diagnostics, including through direct
URLs, guessed IDs, query strings, POST or AJAX-style requests.

The main diagnostic views already enforced this policy before loading records.
Task 2.5's meeting/constraint validation remains unchanged; detailed draft
diagnostics are reachable only by administrators. Task 4.5's structured issue
storage, safe unexpected-error messages, logging and authorized stale-run recovery
also remain unchanged. Published timetable responses use historical entries and
do not compute or embed draft conflict diagnostics for non-administrators.

Two gaps were addressed:

1. Django admin registered credential overrides and schedule-entry audits with
   ordinary model permissions alone. A non-ADMIN staff user granted model
   permissions could access their internal payloads. These two registrations now
   require the existing application administrator check **as well as** Django's
   staff/model permissions, for list, view, add, change, history and deletion.
   Existing finalized-record deletion protection is retained.
2. Error Log filter values were passed directly into ORM conversions. Invalid
   UUIDs, numeric IDs or dates could raise exceptions, including a technical debug
   page when development DEBUG is enabled. `DiagnosticFilterForm` validates UUID,
   bounded positive integer IDs, ISO date and enum choices. Invalid filters return
   zero issues and a generic correction message, not an unfiltered issue list or
   traceback. Valid unknown IDs return zero matches. Generation history remains
   independently scoped as before and accessible only to administrators.

## Endpoint inventory

Paths below use `/schedules/` unless otherwise stated. No standalone generation
diagnostic JSON API or generation-issue export is registered in the URL configs.

| Access point | Existing rule and audit result |
| --- | --- |
| `error-log/` (issues plus generation history, filters and independent pagination) | Login + `admin_required`, before queries and stale-run recovery. Retained; malformed filters now validated. |
| `error-log/<int:pk>/` (issue detail; POST resolution status) | Login + `admin_required` before lookup. All affected-meeting references remain constrained to the issue run's term. |
| `generation-runs/<uuid:pk>/` | Login + `admin_required` before lookup; seed, parameters, fingerprint, outcomes and related issues remain available to administrators. |
| `generate/` | Login + `admin_required`; expected diagnostics retained, unexpected exceptions logged with generic browser feedback. |
| `<pk>/` and `?check=1` | Login + `visible_schedule` + user-specific entry scope. Non-admins can access only assigned published schedules. Draft conflict details remain admin-only; historical views return no internal conflicts. |
| `<pk>/entry/new/`, `<pk>/entry/<entry_pk>/edit/` | Login + `admin_required`; permitted administrative validation and credential feedback retained. |
| `<pk>/entry/<entry_pk>/apply-suggestion/`, `remove/`, `<pk>/copy-to-draft/`, `publish/` | Administrator-only server checks, existing supported-method, signed-token, transaction and finalized-state safeguards retained. |
| `manage/<resource>/` and new/edit/delete routes, particularly `credential-overrides` and `assignments` | Login + `admin_required`; Task 6.1/6.2 list state, counts, filters and sorts retained. GenerationIssue/GenerationRun are not generic resource mappings. |
| `drafts/save/` JSON, `drafts/<pk>/discard/` | Login + `admin_required` + POST; existing owner scoping and safe validation responses retained. JS uses this endpoint only for form drafts, not diagnostic retrieval. |
| `import/`, `import/<uuid:pk>/`, `import/<uuid:pk>/errors/` CSV | Login + existing equivalent administrator check; review/errors also require upload ownership. Error download retains its two-hour age restriction. Template download is also administrator-only. |
| `<pk>/export/csv/`, `<pk>/export/pdf/` | Login + `visible_schedule` + user-specific entries; export only timetable fields, not diagnostics or generation metadata. Full permitted export scope retained. |
| `room-utilization/`, CSV/PDF exports, `room-schedule/`, `room-capacity-planning/` | Login + `admin_required`; no alternate public diagnostic access. |
| `/dashboard/`, `browse/`, `my-availability/` and create/edit | Role-scoped timetable output and own-faculty availability. Safe validation feedback remains available for permitted actions; no internal issue/history payload is embedded. |
| `/admin/schedules/credentialoverride/`, `/admin/schedules/scheduleentryaudit/` and object/history/add/delete routes | Added application administrator check on top of Django admin/model permissions. Neither GenerationIssue nor GenerationRun is registered in Django admin. |

Root and schedules URL configurations, diagnostic services, admin registrations,
Error Log/history/detail templates, timetable templates, sidebar conditions and
`static/js/app.js` were inspected. No legacy diagnostic route or client-side
diagnostic fetch was found. CLI benchmark/report tools are not HTTP endpoints;
they retain existing local operating-system access and unchanged calculations.

## Responses, scope and preserved behavior

- Existing application admin decorators redirect unauthorized users to login
  (302), without querying diagnostic records. Import endpoints retain 403 for
  authenticated non-admins; Django admin returns 403 to staff lacking the required
  role/permission. Anonymous Django admin requests redirect to its login page.
  These established conventions were not replaced by a new permission framework.
- Unknown authorized record IDs use 404. Import records remain owner-scoped.
  There is no department/term restriction on existing application administrators;
  filters narrow results and never grant additional permission.
- Templates retain normal escaping. Non-admin timetable HTML, including hidden
  elements, contains no generation issue payload, fingerprint or internal audit
  reasons. A published schedule's existing aggregate score/status is ordinary
  timetable information, not a generation diagnostic record.
- No generation, validation, lease, snapshot, historical metadata or scheduling
  record storage logic changed. Audit history is not rewritten or deleted.
- Error Log search and pagination, independent history search, issue resolution,
  correction suggestions and administrator diagnostic details are preserved.

## Regression coverage and verification

`schedules.test_diagnostic_access` adds 15 tests covering all application roles,
direct and guessed URLs, GET/POST/AJAX-style requests, rejection before record
lookup/recovery, administrator metadata/history access and issue updates,
multi-page search/filtering, invalid filter handling with DEBUG enabled, scoped
import-error downloads, timetable HTML/CSV/PDF privacy, faculty availability
feedback, draft conflict feedback, alternate Django admin URLs, and logging
without exposing unexpected exception text.

Verification results:

- 75 targeted tests pass (new security tests plus existing diagnostic and Task
  6.1/6.2 list suites).
- Full suite: **486 passed in 294.980 seconds**, preserving all 471 previous
  tests and adding 15 security tests. Zero failures, errors, skips, expected
  failures or unexpected successes. Test runner exit code: 0.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.

Task 6.3 is complete within the verification limits below. No commit was created
and Task 6.4 was not started.

## Limits

Verification uses Django's HTTP test client; no live browser testing or external
penetration test was performed. This audit covers registered application access
paths, not operating-system/database/server-log access. Production must continue
to use `SCHED_EASE_DEBUG=False`; Django development debug pages are not a safe
production error-reporting policy for arbitrary failures elsewhere in the app.
No deployment settings, role framework, dependencies or migrations were changed.
