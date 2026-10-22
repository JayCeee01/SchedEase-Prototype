# SchedEase visual design tokens - UI/UX Task 1.2

## Scope and architecture

The centralized foundation remains in `static/css/app.css`, using the existing `:root` light palette and `[data-theme="dark"]` override. Both themes are intentionally selected, first-class appearances. Shared dimensions inherit; semantic color pairs have separate values. No JavaScript, theme storage key, template, endpoint or backend behavior changed. Existing localStorage `schedease-theme` and toggle selectors continue unchanged.

The Task 1.1 audit is retained as historical evidence. This task addresses its primary contrast issue and shared color foundations, not the login focus trap, help-icon keyboard behavior, sorting, search or draft persistence concerns.

## Token catalogue

| Family | Tokens and application |
| --- | --- |
| Background/surfaces | `--bg`, `--surface`, `--surface-soft`, `--surface-strong`, `--topbar-surface`; pages, opaque cards/panels, controls and top bar |
| Text | `--ink`, `--text-secondary`, `--muted`; primary/secondary/helper roles |
| Borders/focus | `--line`, `--line-strong` for separators; `--control-border` for input boundaries; `--focus` for a two-pixel outline with three-pixel offset |
| Primary | `--primary`, `--primary-strong` (hover), `--primary-active`, `--on-primary`; shared `.primary`/`.button-primary` |
| Secondary/default button | `--button-surface`, `--button-hover`, `--button-active`, `--button-text`; shared `.button` and button foundation |
| Disabled | `--disabled-surface`, `--disabled-text`; controls and buttons, including primary hover precedence and loading-spinner foreground |
| Status | `--success`, `--success-surface`, `--success-border`; `--amber`, `--warning-surface`, `--warning-border`; `--danger`, `--danger-surface`, `--danger-border`; `--info`, `--info-surface`, `--info-border` |
| Destructive button | `--destructive`, `--destructive-hover`, `--destructive-active`, `--on-destructive`; reusable `.button-danger` foundation, no existing action relabelled or changed |
| Navigation/help | `--sidebar`, `--sidebar-end`, `--sidebar-accent`, `--sidebar-text`, `--sidebar-muted`, `--sidebar-selected-text`; `--tooltip-surface`, `--tooltip-text`, `--overlay` |
| Typography | `--font-family` retains Inter/system fallbacks; `--text-body` 16px, `--text-title` clamp(26px,3vw,40px), `--text-heading` 20px, `--text-label` 13px, `--text-helper`/`--text-meta` 12px, `--text-table` 16px |
| Spacing/dimensions | `--space-1` through `--space-6`: 4/8/12/16/20/24px; `--content-padding` 28px, `--card-padding` 18px, `--form-gap` 14px, `--button-padding` 9px 13px, `--control-padding` 10px 12px |
| Shape/elevation/motion | Existing `--radius` 8px and shadows; `--radius-small` 5px, `--radius-pill` 999px, `--border-width` 1px; `--transition-fast` 160ms and `--transition-easing` ease |

Semantic text/status/navigation colors are applied to the existing shared selectors and existing status chips/diagnostics. Global panels and top bar now use solid semantic surfaces to avoid undocumented blended contrast. Input boundaries are intentionally stronger than decorative separators. Native options inherit the control surface/text; native popup rendering remains browser-dependent.

Layout geometry, grid breakpoints, sticky columns, timetable widths, font family, title size and form gaps were retained. This is a foundation, not a complete replacement of every component-specific dimension. Some scale/shape tokens are available for later component adoption; decorative illustration gradients remain component-specific. Existing import CSS already uses shared variables and receives the new palettes without edits. No new stylesheet ordering or theme mechanism was introduced.

## Contrast verification

Calculated from the exact solid sRGB token values, not estimated visually. Formula: linearize each channel c using c/12.92 if c<=0.04045, otherwise ((c+0.055)/1.055)^2.4; luminance is 0.2126R+0.7152G+0.0722B; ratio is (lighter+0.05)/(darker+0.05). Tests use unrounded ratios. Normal text target is 4.5:1, also exceeding the 3:1 large-text target. Relevant control/focus boundaries target 3:1. Disabled text is checked to 4.5:1 even though inactive controls have accessibility exceptions.

The original light muted text #667085 on page background #eef3f8 calculated to 4.46:1. It now uses #526075, with the tested page/surface ratios below.

Before: dark primary white/#2dd4bf = **1.86:1**, white/#5eead4 hover = **1.48:1**. After: dark foreground #062c2a produces **8.05:1 default**, **10.13:1 hover**, **11.89:1 active**. Light white/#0f766e remains **5.47:1**, with **7.58:1 hover** and **9.48:1 active**.

### Exact foreground/background pairs (normal text)

| Token pair | Light foreground / background | Light ratio | Dark foreground / background | Dark ratio |
| --- | --- | ---: | --- | ---: |
| ink / surface | #101828 / #ffffff | 17.75:1 | #eef2ff / #121a2a | 15.56:1 |
| muted / surface | #526075 / #ffffff | 6.39:1 | #a6b0c3 / #121a2a | 7.97:1 |
| ink / surface-soft | #101828 / #f8fafc | 16.96:1 | #eef2ff / #182235 | 14.24:1 |
| text-secondary / surface | #475569 / #ffffff | 7.58:1 | #cbd5e1 / #121a2a | 11.72:1 |
| on-primary / primary | #ffffff / #0f766e | 5.47:1 | #062c2a / #2dd4bf | 8.05:1 |
| on-primary / primary-strong | #ffffff / #115e59 | 7.58:1 | #062c2a / #5eead4 | 10.13:1 |
| on-primary / primary-active | #ffffff / #134e4a | 9.48:1 | #062c2a / #99f6e4 | 11.89:1 |
| button-text / button-surface | #101828 / #ffffff | 17.75:1 | #eef2ff / #121a2a | 15.56:1 |
| button-text / button-hover | #101828 / #e9f8f6 | 16.24:1 | #eef2ff / #253247 | 11.55:1 |
| button-text / button-active | #101828 / #ccfbf1 | 15.75:1 | #eef2ff / #134e4a | 8.47:1 |
| disabled-text / disabled-surface | #475569 / #e2e8f0 | 6.15:1 | #cbd5e1 / #253247 | 8.70:1 |
| success / success-surface | #166534 / #ecfdf3 | 6.76:1 | #86efac / #123226 | 9.90:1 |
| amber / warning-surface | #92400e / #fffaeb | 6.79:1 | #fcd34d / #382b14 | 9.56:1 |
| danger / danger-surface | #b42318 / #fef3f2 | 6.05:1 | #fda4af / #3b1d29 | 7.97:1 |
| info / info-surface | #1e40af / #eff6ff | 8.01:1 | #93c5fd / #172c4b | 7.77:1 |
| tooltip-text / tooltip-surface | #ffffff / #111827 | 17.74:1 | #101828 / #e2e8f0 | 14.40:1 |
| sidebar-text / sidebar | #ced7e6 / #0b1220 | 12.92:1 | #ced7e6 / #070b12 | 13.59:1 |
| on-destructive / destructive | #ffffff / #b42318 | 6.57:1 | #3b0a18 / #fda4af | 8.94:1 |
| on-destructive / destructive-hover | #ffffff / #912018 | 8.66:1 | #3b0a18 / #fecdd3 | 11.98:1 |
| on-destructive / destructive-active | #ffffff / #7a271a | 9.85:1 | #3b0a18 / #ffe4e6 | 14.08:1 |
| muted / bg | #526075 / #eef3f8 | 5.72:1 | #a6b0c3 / #0b1120 | 8.63:1 |
| muted / surface-soft | #526075 / #f8fafc | 6.10:1 | #a6b0c3 / #182235 | 7.29:1 |

### Control/focus indicators

| Pair | Light colors / ratio | Dark colors / ratio |
| --- | --- | --- |
| focus / surface | #115e59 / #ffffff: 7.58:1 | #5eead4 / #121a2a: 11.76:1 |
| focus / surface-soft | #115e59 / #f8fafc: 7.25:1 | #5eead4 / #182235: 10.76:1 |
| focus / bg | #115e59 / #eef3f8: 6.79:1 | #5eead4 / #0b1120: 12.73:1 |
| control-border / surface | #64748b / #ffffff: 4.76:1 | #8494ab / #121a2a: 5.64:1 |
| control-border / surface-soft | #64748b / #f8fafc: 4.55:1 | #8494ab / #182235: 5.16:1 |
| control-border / bg | #64748b / #eef3f8: 4.26:1 | #8494ab / #0b1120: 6.10:1 |

These measurements do not certify every rendered gradient, alpha blend, native dropdown, disabled composition or component override. Focus offset separates the outline from the button fill; browser verification of actual surroundings remains necessary. Decorative separator contrast is not treated as an interactive boundary guarantee.

## Separate theme verification

| Surface/state | Light Mode | Dark Mode | Verification type |
| --- | --- | --- | --- |
| Primary default/hover/active | 5.47/7.58/9.48:1 | 8.05/10.13/11.89:1 | Calculated and automated |
| Secondary and destructive variants | All listed pairs >=4.5:1 | All listed pairs >=4.5:1 | Calculated and automated |
| Disabled text and focus/control boundaries | >=4.5:1 text; >=3:1 tested boundaries | >=4.5:1 text; >=3:1 tested boundaries | Calculated; CSS disabled/loading precedence reviewed |
| Cards, tables, forms and dropdowns | Shared surfaces/text and placeholders inherited; light native color-scheme | Shared surfaces/text and placeholders inherited; dark native color-scheme | Source review and pair tests; actual native popup appearance unverified |
| Success/warning/error/info | Separate light tinted surfaces and dark text | Separate dark tinted surfaces and light text | Exact pairs above, shared feedback/chip selectors reviewed |
| Sidebar/top navigation/modal/tooltip | Navy sidebar retained; light top bar/modal surface; dark tooltip | Navy sidebar retained; dark top bar/modal surface; light tooltip | Source review and selected pairs; no browser rendering claim |
| Toggle and stored preference | Original JS unchanged | Original JS unchanged | Git diff confirms no JavaScript edits; reload/switch browser checks pending |

## Tests and checks

- Added `schedules/test_design_tokens.py`: three SimpleTestCase tests exercise both theme palettes, primary/status/disabled/destructive text, focus/control contrast, palette completeness and primary foreground wiring. No database needed for these tests.
- Focused run: design tokens + meeting tabs + list tests: **32 passed**. Final token-only rerun after CSS state review: **3 passed**.
- Full suite: **554 passed in 350.801 seconds** (baseline 551 + three palette tests); zero failures, errors, skips or expected failures. The final token-only rerun also covers the last muted-text and CSS-state adjustments.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes.
- CSS static checks: balanced braces and no duplicate declarations within either theme token block; not a substitute for a browser CSS parser.
- `git diff --check`: performed at completion.

## Browser limitations and manual verification procedure

No browser automation was executed. The environment has no detected Node command, Python Playwright or Selenium; no framework/browser packages were installed. Django tests do not execute theme JavaScript or prove pixels, reflow or accessibility conformance.

For **each theme separately**, hard-refresh the static assets and test 1360x768 at 100% zoom, then 768px and 390px widths:

1. Switch appearance, navigate and reload; confirm saved selection and original toggle still work.
2. Inspect text, cards, table headers/rows, long course names, labels/help, placeholders and native dropdown options. Check no fields/actions disappeared or new horizontal page overflow appeared.
3. Exercise primary/default/destructive styling where used: hover, press, keyboard focus, disabled and loading. Confirm focus is visible and loading spinners contrast against their actual disabled surface.
4. Open login modal and tooltips; inspect navbar/sidebar expanded/collapsed and mobile overlay. Known focus/keyboard defects from Task 1.1 are deferred, not fixed here.
5. Trigger safe synthetic success/warning/error/info messages and invalid form controls; inspect badges, credential messages and import upload/mapping/preview stages.
6. Inspect timetable/table, room reports and read-only historical status in the appropriate role; verify all prior data visibility remains unchanged.

Record browser/version, CSS viewport, zoom, theme, screenshots and outcome. Until performed, visual/mobile/native-control acceptance remains **not verified** for both themes. No claim of full WCAG compliance is made.

## Remaining scope and handoff

No changes to search, autosave, login focus trap, help-icon keyboard behavior, local sorting, GA, permissions, publication, historical data or calculations. Existing audit findings remain the next tasks' responsibility. Task 1.3 should standardize component adoption and documentation using these tokens; it should not introduce a competing palette or weaken backend contracts.

Task 1.2 is Completed for the token implementation and automated/source verification scope, with browser verification explicitly outstanding as documented above. Progress is 2/24; Task 1.3 remains Not Started and requires approval. No commits, migrations or deployment performed.
