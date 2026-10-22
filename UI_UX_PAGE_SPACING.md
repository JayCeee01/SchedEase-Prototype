# Page spacing and content density - Task 2.4

## Pre-change audit

Preserved the uncommitted Task 2.3 documentation updates. Reviewed the existing master plan and component, token, interaction, navigation and responsive references. The existing 21-page rendered fixture covers dashboard, schedule generation/detail, academic/faculty/student/room/availability/credential lists, administration, editors and confirmation content. Component fixtures supplement empty records with wide tables, long labels/errors and a tall modal.

Confirmed source inconsistencies: page/card padding 28/18px, section-heading margins 28/14px, table cells 14/16px, card-grid gaps 14/18px, form label gap 7px and specialist filter padding 22px. These sit between existing spacing tokens. Dashboard action tiles reserve 74px while standard controls need 42px. Preserve meaningful section separation and specialized timetable geometry; do not compact every element indiscriminately.

## Verification

Full Django suite: **557 passed in 352.547 seconds**, zero failures, errors, skips or expected failures. System check: no issues. Migration dry run: no changes. Git whitespace check: passed. Browser results are recorded below.

## Changes and conventions

| Area | Before | Final convention |
| --- | --- | --- |
| Page padding | 28px desktop / 18px mobile | `--space-6` (24px) desktop / `--space-4` (16px) below 900px |
| Shared card padding | 18px | `--card-padding: var(--space-4)` (16px) |
| Form field groups | 14px | `--form-gap: var(--space-3)` (12px); label/input gap 8px |
| Section headings | 28px above / 14px below | 24px / 12px; first card headings stay flush; meeting heading keeps its existing grouping |
| Page heading to content | 20px | 16px; title size, wrapping and description line-height retained |
| Dashboard | 24px command padding, 74px action tile minimum | 20px command padding, 64px tiles, 12px inner gaps; hierarchy and destinations retained |
| Table cells | 14px vertical / 16px horizontal | 12px / 16px; existing specialist overrides retained |
| Table toolbar | 14px on all sides | 12px vertical / 16px horizontal, aligned with cell content |
| Utilization filters | 22px padding / 20px gap | 16px padding/gap, 8px label gap |
| Pagination and feedback | Mixed literal gaps/margins | Existing 12/16px spacing expressed with shared tokens; feedback separated by 16px |

The 20px separation between distinct adjacent panels remains. Button and input padding, standard 42px button minimum, colors, font sizes, focus outlines, tooltip positioning, sticky header, table footer and timetable slot geometry are unchanged. Larger semantic sections remain distinct. No width caps or hidden actions were introduced. No template, application JavaScript, backend or data changes.

## Before/after evidence

Measured with the same offline Django-rendered content, viewport and font environment. Heights are rounded CSS pixels; first-panel positions are relative to the individual page content, excluding the common shell. These are fixture-specific measurements, not timing or universal content-size claims. Light and Dark produced the same measurements.

| Page / width | Before height | After height | First panel before / after |
| --- | ---: | ---: | ---: |
| Dashboard, 1360px | 989 | 884 | 364 / 349 |
| Dashboard, 390px | 1901 | 1794 | 760 / 721 |
| Course editor, 1360px | 895 | 871 | 145 / 138 |
| Course editor, 390px | 890 | 870 | 150 / 145 |
| Assignment editor, 1360px | 1371 | 1335 | 145 / 138 |
| Assignment editor, 390px | 1431 | 1399 | 175 / 170 |
| Room utilization, 1360px | 892 | 855 | 213 / 206 |
| Room utilization, 390px | 2036 | 1967 | 297 / 292 |

## Browser verification

Installed Chrome with isolated profiles; no application database access. Reused the Task 2.3 rendered fixture containing 21 authenticated test-client GET responses from an in-memory database. It includes dashboards, schedule generation/detail, room utilization/schedule/planning, error administration, import upload, academic/personnel/availability/credential lists, editors and deletion confirmation. These are offline rendered content checks, not live authenticated sessions. Component fixtures supply populated wide tables, long errors/selects, a day board, card groups and an internally scrolling modal.

- Light Mode: 1360, 1024, 901, 768, 621, 500 and 390px at 768px height; overflow checks and readable-control checks passed. Screenshot review at desktop/tablet widths.
- Dark Mode: same widths, height and checks; mobile screenshot review confirms comfortable padding, readable labels and existing navy/teal surfaces.
- Responsive fixture: **350 assertions** (25 per theme/width), including four added density safeguards for Save-button height, select height, page padding and field separation.
- Rendered fixture: **294 page-width checks** (21 pages per theme/width).
- Previous sidebar **336**, top navigation **208**, shared interactions **88** and table-scroll **92** regression checks all passed.
- `manage.py check`: no issues; migration dry check: no changes; `git diff --check`: passed.

The runner's optional `--measure` prints page heights and content start positions for repeatable comparisons:

```powershell
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --rendered --measure
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --responsive --screenshots
```

## Files and remaining checks

Task changes: `static/css/app.css`, `tests/browser/responsive_layout.html`, `tests/browser/run_interactions.py`, this reference, master-plan progress and refreshed tracked responsive screenshots. Earlier uncommitted changes in `UI_UX_RESPONSIVE_LAYOUTS.md` and the master plan were preserved.

Manual follow-up: live role-based workflows, populated historical/generated timetable content, screen readers, native select popups, browser zoom, physical touch/software keyboard and Firefox/Safari. Existing automated tests do not certify these. No commits, deployment, Phase 3 work or database modifications.

## Final status

Task 2.4 Completed. Phase 2 Completed. Overall progress **8/24**. Phase 3 tasks remain Not Started; await approval before Task 3.1.
