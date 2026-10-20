# Shared UI components - Task 1.3

## Scope and conventions

Build on the existing CSS and Task 1.2 tokens. No framework, JavaScript, backend, database or dependency changes. Existing uncommitted token work and audit documents were preserved.

| Component | Convention and changes |
| --- | --- |
| Page heading | Existing `.page-hero` wraps its children; its title uses a compact 26-34px hierarchy, 1.2 line height and long-word wrapping. Actions retain flex alignment and can move to the next line. Normal document flow is retained below navigation. |
| Section/card | Existing `.panel`, `.card` share padding, surface, border, radius, shadow and minimum-width behavior. First-child section headings lose redundant top margin; adjacent panels have a consistent gap. Metric cards reuse card padding. Specialized dashboard/import layouts retain their intentional dimensions. |
| Buttons | Shared foundation has 42px minimum height, centered icons/text and wrapping labels. Specialized icon/compact controls retain their overrides. Existing primary and secondary variants remain; destructive confirmation buttons use `.button.button-danger`. |
| Form footer | `.toolbar.form-actions` aligns actions at the start with shared spacing and a separator. Adopted in generic/assignment editors, delete/removal and credential-override confirmations. Keep `.toolbar` alone for distributed filtering/navigation controls. |
| Forms | Existing labels and token-based inputs retained. Controls stay within their container; helper text wraps with consistent line height. No field names, validation, required flags, management fields or draft hooks changed. |
| Feedback | Toast spacing, line height and wrapping are shared. Draft/restoration and conflict notices now use information/warning foreground-background pairs with semantic borders. Badge padding/radius/line height use shared tokens. Existing status text and conditional display remain intact. |
| Tables/empty states | `.table-wrap` retains horizontal scrolling and gains minimum-width/radius conventions. `.table-empty` and `.empty-state` use shared padding. No columns, sorting, filters, pagination or table minimum widths changed. |
| Modal/dropdowns | Login modal uses an opaque semantic surface and shared radius; its sizing/scrolling and interaction remain intact. Native selects/options retain Task 1.2 theme surfaces and control boundaries; no custom dropdown introduced. |

Use the existing classes rather than adding wrapper components around every template. Do not apply form-action footers to search toolbars or apply equal card heights to content with different needs. Read-only historical notices retain their content and inherit the panel conventions. Import components retain their separate stylesheet and shared token inheritance.

## Light Mode verification

Source review and palette regression tests: shared surfaces use the light palette. Primary text contrast remains 5.47:1 default, 7.58:1 hover; destructive default is 6.57:1. Information/warning notice text is 8.01:1 / 6.79:1. No new literal color values introduced by Task 1.3. Browser layout, native dropdowns and theme persistence are not visually verified.

## Dark Mode verification

Source review and palette regression tests: shared surfaces use the independently selected dark palette. Primary text contrast remains 8.05:1 default, 10.13:1 hover; destructive default is 8.94:1. Information/warning notice text is 7.77:1 / 9.56:1. Theme selectors, toggle JavaScript and storage key remain unchanged. Browser layout, native dropdowns and theme persistence are not visually verified.

## Regression verification

- Baseline: 554 tests, including Task 1.2 palette contracts.
- Final token tests: 3 passed.
- Five modified templates compared against HEAD after removing only class/style attributes: all content, Django tags, URLs, CSRF, revision fields and behavioral attributes match.
- Focused meeting/import/removal run: **61 passed in 42.539 seconds**. Full suite: **554 passed in 310.921 seconds**, zero failures, errors, skips or expected failures.
- Django system check: no issues. Migration dry run: no changes.
- Git whitespace check: passed; repeated at completion.

Existing rendering, access, signed-revision, import and meeting tests cover the unchanged contracts. No redundant tests asserting presentation class strings were added.

## Browser limitation and manual checklist

No browser run performed: Node/browser commands and Python Playwright/Selenium were unavailable. Automated Django tests do not establish visual acceptance. Test each theme separately at 1360x768, 768px and 390px, then enlarged text/zoom:

1. Dashboard and resource list: title/action alignment, long academic names, section/card spacing, table horizontal scrolling and empty/filtered states.
2. Generic/assignment forms: long labels, native dropdowns, helper/error text, meeting tabs, Save/Cancel footers and restored/conflicting drafts.
3. Delete and meeting-removal confirmations: destructive colors, required confirmation and unchanged cancel links. Use disposable records only.
4. Published/archived schedules: read-only notice, badges and conflict visibility; all previous safeguards remain enforced.
5. Import upload/mapping/preview: shared buttons and separate import layout, wide tables and status messages.
6. Login modal: opaque surface, radius, internal scroll, narrow screen fit. Existing focus-trap issue remains assigned to a later task.
7. Toggle Light/Dark, navigate and reload to check saved appearance. Review hover/focus/disabled/loading visibility; full interaction-state audit remains Task 1.4.

Record browser/version, viewport, zoom, theme and screenshots. Do not claim full accessibility conformance from source contrast measurements.

## Handoff

Task 1.4 should audit interaction states and keyboard behavior using these conventions. No interaction redesign, search, autosave, publication or scheduling changes were implemented here. Task 1.3 implementation and automated/source verification are complete; browser verification remains outstanding as explicitly documented. Progress: 3/24; Task 1.4 Not Started. No commits or deployment.
