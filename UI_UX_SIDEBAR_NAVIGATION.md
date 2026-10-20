# Sidebar navigation - UI/UX Task 2.1

## Scope and preserved behavior

Reviewed the master plan, component audit, token/component/interaction references and standalone scrollbar refinements. Preserved all existing uncommitted work, including the already-modified sample database (not edited by this task).

The toggle remains above the logo. Desktop still uses the existing expanded sidebar and collapsed icon rail, and clicking destinations never expands it. Menu grouping, URLs, server-side role conditions, native details/summary accordions, sessionStorage keys, saved theme, subtle transitions and reduced-motion behavior remain. The improved Light scrollbar, Dark button palette and table-owned sticky horizontal scrollbars are unchanged.

## Confirmed issues and changes

- Mobile previously toggled visibility without keyboard exclusion, Escape handling or focus restoration. The closed drawer is now inert; opening focuses its close toggle and makes the workspace inert. Tab/Shift+Tab stay within the open drawer; Escape, backdrop and internal toggle close it and restore the opener. At desktop breakpoint the workspace is released; moving into mobile with focus in the sidebar returns focus to the mobile opener.
- The internal toggle previously changed the desktop collapse preference on mobile. It now closes the drawer on mobile and retains the saved desktop preference. Both toggles expose accurate labels, aria-controls and aria-expanded.
- Collapsed links and accordion summaries receive explicit accessible names. Native summary expanded semantics remain authoritative. Duplicate link title tooltips were removed in favor of the existing positioned tooltip. Focused navigation tooltips follow sidebar scrolling instead of disappearing when a link scrolls into view.
- Initial scroll restoration previously reread storage after intermediate scroll events could overwrite the intended value. It now captures the initial position and delays saving until both layout restoration frames complete. Existing scroll/pagehide/pointer saving remains.
- Long labels wrap rather than truncate. Scrollbar gutter and contained overscroll preserve usable spacing and independent scrolling. Active links gain an inset marker; the active group's summary remains emphasized without changing permissions or routing.
- Mobile drawer uses dynamic viewport height and bounded width. Saved desktop collapse styles no longer spread the mobile logo/brand apart; the toggle remains above the logo.

No backend, model, migration, authentication policy, search, autosave or scheduling changes. No template role conditions or destinations changed.

## Theme and responsive verification

| Mode | Verification |
| --- | --- |
| Light | Browser fixtures at 1360, 768, 500 and 390 CSS pixels; expanded/rail or mobile open/closed, focus, active state, tooltips and persistence checked. Existing visible sidebar scrollbar palette retained. |
| Dark | Same four widths and behavioral checks; semantic text/background/focus palettes retained. |

Chrome 155.0.8059.85, height 900px, device scale factor 1. Actual Page.reload checks repeat each fixture, exercising session persistence. Fixture screenshots captured for closed/collapsed and open/expanded states; representative Light/Dark desktop/mobile images inspected. The fixture uses the shared application CSS/JS and representative navigation markup, not authenticated production-page screenshots.

Focused browser checks cover: saved collapsed state and scroll, toggle above logo, visible logo, active destination, destination clicks preserving collapse, named focus tooltips within viewport, desktop workspace alignment, mobile inert background, focus entry/restoration, Escape/backdrop/internal close, desktop preference preservation, drawer bounds, Tab wrapping, accordion persistence and page overflow. Real route navigation is covered by existing Django tests; the fixture prevents destination navigation and separately reloads its page to test persistence.

## Verification results

- Sidebar: **336 assertions passed** (18 desktop and 22 mobile/tablet assertions per theme/width, each repeated after reload).
- Previous interaction fixture: 88 assertions pass across both themes and desktop/mobile.
- Sticky-table fixture: 92 checks pass, including real resizing/native keyboard scrolling.
- Full Django suite: **557 passed in 490.345 seconds**, zero failures, errors, skips or expected failures. The existing 557-test baseline is preserved.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes.
- `git diff --check`: passed, repeated at completion.

Run the sidebar fixture with:

```powershell
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --sidebar
# Optional synthetic screenshots
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --sidebar --screenshots
```

## Files changed in Task 2.1

`static/css/app.css`, `static/js/app.js`, `tests/browser/sidebar_navigation.html` (new), `tests/browser/run_interactions.py`, this reference and `UI_UX_MASTER_PLAN.md`. Other working-tree changes predate this task.

## Remaining manual checks

Verify real administrator/faculty/student accounts with long actual labels, links between actual modules and browser back/forward navigation. Check physical touch gestures, screen-reader announcements, Firefox/Safari, device keyboard appearance/dynamic height and browser zoom. Headless fixture checks do not certify full accessibility conformance. No new framework or dependencies.

Task 2.1 Completed. Phase 2 In Progress. Overall progress 5/24. Task 2.2 and all later tasks remain Not Started. No commits or deployment.
