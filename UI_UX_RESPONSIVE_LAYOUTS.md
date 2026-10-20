# Responsive layouts - Task 2.3

## Pre-change findings

Previous Task 2.2 changes and the modified sample database are preserved. Inspection found specialist filter grids with fixed track minimums that exceed the workspace beside the desktop sidebar (room utilization, capacity planning, room schedules and entry filters). The six-column day board also has a minimum total width greater than the available desktop workspace. Shared form controls have maximum widths but grid children can still retain intrinsic minimum sizes, particularly long selects and unbroken validation text. These cases are being reproduced with shared-asset browser fixtures before changes.

## Verification

In progress.

## Confirmed browser findings and fixes

Before CSS changes, the representative fixture failed at 1360px: schedule board, detail/form grid and long select exceeded their containers and caused page overflow. Actual Django-rendered room-capacity planning later reproduced non-wrapping tab overflow at 390px. Visual inspection at 1024px found a squeezed numerical summary.

- Day columns use available-width tracks at desktop; the existing single-column board remains below 900px. Time-slot grids and academic tables retain their own scrolling treatment.
- Room planning, utilization, room schedule and entry filter grids use available-width tracks with a 190px target minimum, bounded by the container. They stack at the existing 620px breakpoint.
- Form/grid children can shrink; long select values no longer dictate the entire form width. Labels and validation text wrap. Shared nested grids use a bounded 260px target minimum.
- Detail panels stack at the existing 1180px breakpoint to accommodate the expanded sidebar.
- Summary cards use bounded 210px tracks, wrap icon/content groups, and keep numbers together.
- View-switcher buttons wrap in document order. No actions are hidden or reordered.
- Login dialog height accounts for viewport padding using dynamic viewport units; its existing internal scrolling, focus trap and Escape behavior remain.

Shared semantic colors, padding tokens, form-actions convention, table scroll utility, sidebar behavior, search scope and autosave are unchanged. No new application JavaScript, template, business-logic or database changes for Task 2.3.

## Coverage and verification

Reviewed master plan/audit, tokens, shared components, interaction states and both navigation references. Inspected shared CSS, import CSS and actual form, dashboard, planning, table, pagination, schedule and confirmation markup.

Responsive component fixture: Light and Dark at **1360, 1024, 901, 768, 621, 500 and 390px**, height **768px**. The 901/621 cases test just above existing breakpoints. Covers long headings, metrics, planning/utilization filters, day board, long selects/errors, shared form footer, toolbars, pagination, contained wide tables, existing scroll footer and a tall modal with Escape/focus restoration. Final result pending.

Rendered-page fixture: `render_responsive.py` creates a fresh **in-memory SQLite database**, installs existing migrations there, and authenticates a synthetic administrator using Django's test client. It performs GET requests through normal view authorization and assembles returned content in a representative shell. It never connects to the configured sample database. Covers 21 pages: dashboard, generation form, room utilization, room schedule, room planning, generation errors, spreadsheet upload, course/faculty/student/room/credential/assignment/availability/department/program/section lists, course and assignment creation, room deletion confirmation, and a draft schedule detail. Checks each page's contained width across the same seven widths and both themes. Empty lists and an empty draft are intentional; populated wide data is covered separately by component/table fixtures.

This is actual Django-rendered content tested offline, not a live authenticated end-to-end session. No application form is submitted in browser tests. Generated HTML includes synthetic CSRF values only and is removed after verification.

### Theme results

- Light Mode: responsive behavior and existing semantic surfaces/borders/focus retained; representative desktop/tablet screenshots reviewed.
- Dark Mode: identical layout rules and existing navy/teal palette retained; representative mobile screenshot reviewed.
- No palette or theme-storage changes. Screen-reader, physical device and cross-browser certification is not claimed.

### Repeatable commands

```powershell
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --responsive
.\.venv\Scripts\python.exe tests/browser/render_responsive.py
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --rendered
```

The browser runner now waits for Chrome's startup file to become readable, handling a Windows startup file-lock race. No dependencies added.

## Outstanding manual checks

Check live administrator/faculty/student workflows and populated historical/generated timetable views in both themes; native select popup text, browser zoom, physical touch, mobile software keyboard, screen readers and Firefox/Safari. Verify real confirmation submissions, autosave and pagination navigation through their usual permissions. Component fixtures cover layout and retained interactions, not these complete workflows.

## Files changed in Task 2.3

`static/css/app.css`, `tests/browser/run_interactions.py`, new `tests/browser/responsive_layout.html`, new `tests/browser/render_responsive.py`, this reference and master-plan progress. Existing Task 2.2 edits and `tertiary_sample.sqlite3` were preserved. No commit or deployment. Task 2.4 remains Not Started.
