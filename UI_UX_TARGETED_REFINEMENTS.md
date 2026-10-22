# Targeted UI refinements: sidebar, primary buttons and table scrolling

## Recovery and scope

Recovered the existing uncommitted Phase 1 work and the in-progress targeted refinement. The sidebar tokens, button palette, reusable table utility and initial tests were already implemented. This continuation completed real-time browser verification, foreground-tab focus setup, row-action avoidance, documentation and final checks. No changes to business logic, database, GA, permissions, publication, search/filter/sort/pagination semantics or autosave. No commits or deployment.

This is separate from the master plan. Its progress remains **4/24**, with Phase 1 completed and all later tasks Not Started. It overlaps future sidebar and table work (2.1/3.4/6.2), without marking those tasks complete. Earlier audit/token/component reports remain historical evidence.

## A. Light Mode sidebar scrollbar

The actual scroll container is `.nav-group`, which retains `overflow-y:auto`, its existing width and collapse/expand behavior. Introduced scoped `--nav-scrollbar-*` tokens; page scrollbars are untouched.

| Light token | Color | Thumb/track contrast |
| --- | --- | --- |
| Track | `#132235` | - |
| Thumb | `#8496aa` | 5.29:1 |
| Hover | `#b3c3d3` | 8.92:1 |

Previously the sidebar inherited a dark translucent thumb `rgba(15,23,42,.24)` over a transparent track, despite the sidebar itself being navy in Light Mode. Standard `scrollbar-color`/`scrollbar-width` and WebKit selectors now use the scoped palette. Light Mode container hover supplies a distinguishable standard-property hover state as well. Dark Mode aliases the original track/thumb/hover tokens unchanged. Scrollbars appear only on overflow.

## B. Dark Mode primary buttons

New button-only tokens separate action fills from the existing primary accent/status palette. Primary button foreground remains `#062c2a`. No badge/status colors, Light Mode colors, dimensions or actions changed.

| State | Previous background | Previous text contrast | New background | New text contrast |
| --- | --- | --- | --- | --- |
| Normal | `#2dd4bf` | 8.05:1 | `#69b5aa` | 6.27:1 |
| Hover | `#5eead4` | 10.13:1 | `#82c6bc` | 7.67:1 |
| Active | `#99f6e4` | 11.89:1 | `#9bd5cc` | 9.12:1 |

`--primary-button`, `--primary-button-hover`, `--primary-button-active` are centralized in both palettes. Light Mode retains white text on `#0f766e`, `#115e59`, `#134e4a`: 5.47/7.58/9.48:1. Dark button fill contrast against `#121a2a` surface is 7.28/8.91/10.59:1. Focus, disabled and destructive palettes are unchanged. Ratios use the same sRGB luminance calculation as the token tests; every normal-sized label exceeds 4.5:1.

## C. Original floating implementation (superseded by the correction below)

`static/js/table-scroll.js`, loaded once by `templates/base.html`, creates one native overflow scrollbar near the viewport bottom. It controls the currently relevant long, wide table; it does not copy or reorder table contents.

- Automatically discovers `.table-wrap` and `.import-scroll` containing actual tables.
- Appears only when horizontal overflow exists and the visible table extends below the viewport. Short/fitting/offscreen tables retain their native scrollbar alone.
- Synchronizes both directions using scroll-range proportions and a tolerance to avoid recursive scroll churn. Unchanged layout updates do not reset a user's scroll position.
- Passive scroll listeners schedule one animation-frame layout update. ResizeObserver tracks wrappers/tables; batched MutationObserver handles filtering, replacement, row changes and inserted/removed wrappers. Removed tables lose listeners/observation. Pagehide suspends global work; pageshow resumes for browser back/forward cache.
- Handles multiple tables with one active owner. Resizing and sidebar width changes update position/range.
- Hides during dialogs and mobile navigation. The narrow strip moves above overlapping row actions; if a dense control area leaves no safe position near the bottom, it temporarily hides rather than covering those controls. Native table scrolling remains available.
- Native focusable region has an accessible name and `aria-controls`; keyboard ArrowRight was verified to move the real table. No custom drag/keyboard implementation or extra table copies. Pointer/touch/trackpad handlers are not intercepted.

### Module coverage

Shared resource list covers academic records, programs/departments, courses, sections, faculty/students, rooms, credentials, availability and assignments as applicable. Other covered templates: entry tables, academic schedule tables, room utilization/capacity planning, personal availability, administrative error logs, import mapping/preview/comparison and import guide tables.

Explicit exclusions: `.room-schedule-grid` (including personal time-slot timetables) and `.timetable-grid`. Day-column schedule views without actual tables are not touched. Nested wrappers are not registered twice. Existing sticky columns, native horizontal scroll, URLs, filtering, sorting and pagination remain intact.

## Verification

- Django: **557 passed in 306.800 seconds**; baseline 554 plus three added checks. Zero failures, errors, skips or expected failures.
- Token tests: **6 passed**, including button/surface contrast, Light sidebar thumb contrast/Dark alias preservation and single utility inclusion.
- System check: no issues. Migration dry run: no changes. Git whitespace check: passed.
- Chrome **155.0.8059.85**, isolated local fixtures, measured **1360x900 and 390x900**, Light and Dark separately: **23 table assertions plus two real resize/keyboard checks per configuration (100 checks)**.
- Previous interaction fixture: **22 assertions per configuration (88 checks)** passed with the same real-time runner.
- Screenshots inspected in both themes and widths: visible native proxy/focus, readable refined buttons and Light sidebar thumb. These are synthetic component fixtures, not authenticated-page screenshots.

Browser checks exercise wide/fitting and long/short tables, forward/reverse/native scrolling, filtering, row reordering, multiple tables, container width changes, actual viewport resizing, dialog/sidebar hiding, overlapping row actions, removal, pagehide/pageshow and native keyboard scrolling. Real application pagination uses full page rendering and the shared include; it was not separately clicked in the fixture. Existing Django pagination tests remain passing.

### Browser harness

```powershell
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --tables
.\.venv\Scripts\python.exe tests/browser/run_interactions.py
# Optional reproducible screenshots in the repository root
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --tables --screenshots
```

Uses installed Windows Chrome/Edge, a disposable profile and a minimal standard-library local DevTools client. No new dependencies or real database. Real event-loop execution replaced virtual-time dump mode, which did not reliably deliver native scroll events. The runner brings its tab forward and emulates foreground focus; a background-tab focus failure in the old interaction fixture was resolved in the harness, without an application change. Device metrics now provide a true 390px viewport.

## Files changed for this refinement

- `static/css/app.css`: scoped scrollbar/button tokens and proxy styling.
- `static/js/table-scroll.js`: reusable utility (new).
- `templates/base.html`: one shared script include.
- `schedules/test_design_tokens.py`: updated button pairs and three additional tests.
- `tests/browser/table_scrolling.html`: new table regression fixture.
- `tests/browser/cdp_browser.py`: local DevTools test helper (new).
- `tests/browser/run_interactions.py`: real-time runner and viewport/native keyboard checks.
- This implementation note.

Other modified/untracked files in Git were already present and were preserved.

## Remaining verification and limits

Firefox and physical touch/trackpad/Shift+wheel interactions were not run; standard native scrolling is preserved but needs device verification. Check actual long resource lists and import previews in both themes, expand/collapse sidebar, navigate pagination, and verify native scrollbar preferences on the target OS. Check screen-reader naming and very dense row-action layouts. Overlay scrollbars may follow OS auto-hide preferences. Right-to-left layouts are not part of the existing application and were not tested. No full cross-browser/accessibility certification is claimed.

All three requested refinements are implemented and verified within the scope above. Master-plan progress is unchanged; await further instructions.


## Follow-up: steady table-owned scrollbars

The page-level bar could jump or disappear as row actions entered its collision-detection area. Replaced it with a native synchronized footer owned by each table frame. CSS `position:sticky` keeps it at the viewport bottom only within that frame; no vertical-scroll listener, visibility threshold, active-table switching or collision repositioning remains. Each table has independent scrolling. Fitting tables have no extra control; overflowing tables replace their bottom native bar with the same persistent footer, avoiding a duplicate at the end. Touch/trackpad scrolling still acts on the real wrapper. Independently vertically scrolling panes retain their original native bars.

The academic schedule panel uses `overflow:clip` to preserve clipping without creating an ancestor scroll container that defeats sticky positioning. Existing template fields, table contents, business logic and theme palettes are unchanged.

Verification: 21 fixture assertions plus real viewport-resize and native keyboard checks in Light/Dark at 1360px and 390px (92 checks); repeated upward/downward scrolling explicitly checks visibility and table bounds. Six token/integration tests and Django system check passed; whitespace check passed. Screenshots inspected for Light desktop and Dark mobile. Full Django suite was not rerun for this focused CSS/JavaScript correction; the previous 557-test result above is historical. Firefox/physical touch and authenticated-page walkthroughs remain outstanding.
