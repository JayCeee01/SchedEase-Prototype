# SchedEase UI/UX Component Audit — Task 1.1

Date: 2026-10-20. Scope: source-based audit and documentation only.

## Executive summary

Reviewed **six major categories**, organized into **30 component groups**, across **33 HTML templates and four shared/import CSS/JavaScript files**, with supporting form, listing, draft-service and regression-test inspection. The existing Django/vanilla-JavaScript frontend provides a reusable foundation: semantic theme variables, shared forms and pagination, role-conditioned navigation, meeting tabs, explicit history indicators and protected POST workflows.

Highest priorities are dark-theme primary-action contrast, keyboard access to custom help/sort controls, login-dialog focus management and truthful draft-save feedback. Global search operates on rendered rows independently of server filtering/counts. Wide timetable grids and truncation are deliberate source behaviors whose visual impact still needs browser evaluation.

This is **not a redesign or browser acceptance test**. No browser, screen reader, screenshots or real database was used. The developer's screenshot observations are hypotheses unless supported below by source evidence. Task 1.1's source/documentation audit is complete; browser follow-up is explicitly assigned to later tasks rather than represented as passed.

Initial Git state: only the existing untracked `UI_UX_MASTER_PLAN.md`. Preserved and updated its progress only. Baseline: 551 passing tests from the prior final verification report; not rerun here.

## Method and evidence labels

- **C — Confirmed source issue:** a concrete implementation omission or mismatch is visible in code. This does not claim a browser reproduction.
- **B — Confirmed behavior:** existing behavior or design choice, not inherently a defect.
- **U — Unverified concern:** requires rendered/browser/assistive-technology evidence.
- Priorities: **High** affects basic access, trustworthy feedback or broad readability; **Medium** affects clarity/efficiency; **Low** is localized consistency.
- Source references use stable file paths plus selectors/functions rather than fragile line ranges. Paths without directories in inventory rows are under `templates/schedules/`.

## Frontend architecture and dependencies

`templates/base.html` provides the application shell and role-conditioned navigation. `templates/landing.html` supplies the public landing/login dialog; `templates/registration/login.html` is the standalone login page. Shared assets are `static/css/app.css` and `static/js/app.js`. Imports additionally use `static/css/academic-import.css` and `static/js/academic-import.js`.

There is no frontend framework required by these inspected assets. Inter loads from Google Fonts with system fallbacks in CSS. Icons use embedded SVG/CSS patterns. Browser capabilities include Web Storage, fetch, native details/select/confirm controls, CSS grid, color-mix and media queries. Verify supported browsers before changing their usage; no packages were installed.

Django forms, formsets, context values, URLs, query strings and data attributes are frontend contracts. Relevant supporting sources: `schedules/forms.py`, `schedules/views.py`, `schedules/services/listing.py`, `schedules/services/form_drafts.py`. These were inspected without modification. Do not change algorithms, permissions, persistence, schema or publication transitions to resolve a visual concern.

## Component inventory — 30 groups

| # | Category / group | Sources and selectors | Behavior and reuse |
| --- | --- | --- | --- |
| 1 | Navigation / sidebar | base.html; app.css `.sidebar/.nav-group/.nav-disclosure`; app.js sidebar handlers | Native disclosures, longest-path active link, stored group/collapse/scroll state |
| 2 | Navigation / top bar | base.html `.topbar/.topbar-search` | Shared search plus identity, theme and sign-out |
| 3 | Navigation / search | app.js `filterTables`, `[data-global-filter]` | Current DOM rows only; separate server list controls |
| 4 | Navigation / account | base.html `.user-menu`, logout form | Identity display, not an account dropdown; POST logout with CSRF |
| 5 | Navigation / theme | app.css `:root/[data-theme=dark]`; app.js `[data-theme-toggle]` | Theme stored in localStorage; navy shell retained |
| 6 | Navigation / tooltips | app.js `placeTooltip/bindTooltips`; app.css `.app-tooltip/.info-icon` | Shared fixed tooltip and auto-inserted label help |
| 7 | Shared / page hierarchy | form.html, resource_list.html, dashboard templates; `.page-hero/.hero-card` | Eyebrow, heading, description, actions; repeated pattern |
| 8 | Shared / cards | app.css `.panel/.metrics/.action-tile`; schedule_cards.html | Shared surfaces and metric/action cards |
| 9 | Shared / buttons | app.css `.button/.primary/.button-primary` | Common sizing, hover, disabled and loading styles |
| 10 | Shared / badges and alerts | base.html messages; app.css `.badge/.toast` | Status colors and dismissible messages; specialized messages vary |
| 11 | Shared / dialogs and dropdowns | landing.html login dialog; schedule_detail.html publication confirm; native selects/details | Custom login modal alongside native confirm and separate confirmation pages |
| 12 | Shared / empty/loading | personal_timetable.html, resource_list.html, form.html, import_progress.html | Empty rows/cards, generation spinner, import busy feedback |
| 13 | Forms / generic editors | form.html; forms.py MODEL_FORMS | `form.as_p`, field labels/help/errors, common actions |
| 14 | Forms / assignment meetings | assignment_form.html, meeting_fields.html; app.js `[data-assignment-editor]` | Formset IDs/management, add/remove, summaries, numbered keyboard tabs and error reveal |
| 15 | Forms / validation and guidance | forms.py; meeting_fields.html; app.js tooltip dictionaries | Native/Django validation plus custom guidance; policy descriptions must remain accurate |
| 16 | Forms / draft and actions | form.html, assignment_form.html; app.js `[data-form-draft]` | Owner-bound server drafts, recovery/conflict warnings, Save/Cancel/Discard |
| 17 | Tables / record lists | resource_list.html; listing.py | GET search/sort/filter, total/matching/range counts; assignments have specialized columns |
| 18 | Tables / pagination/actions | _pagination.html; resource_list.html | Query-preserving navigation, current-page marker, Edit/Delete; assignment actions before timestamps |
| 19 | Tables / local sorting | my_availability.html; app.js `th[data-sort]` | Click-based lexicographic sorting of rendered rows |
| 20 | Tables / overflow | app.css `.table-wrap/.academic-schedule-table/.room-schedule-grid` | Horizontal wrappers, sticky course column, minimum grid widths |
| 21 | Scheduling / generation-management | form.html generation branch, resource_list.html schedule tabs, academic_import.html | Settings/seed fields, import link, busy state, result links and status-filtered lists |
| 22 | Scheduling / timetable | schedule_timetable_view.html, personal_timetable.html | Day cards versus repeated time-slot grid; component/time/resource details |
| 23 | Scheduling / table and filters | schedule_table_view.html, entry_table.html, browse.html, schedule_detail.html | Academic grouping, GET filters, view switching and exports |
| 24 | Scheduling / conflicts/history | schedule_detail.html, error_log.html, error_detail.html, generation_run_detail.html | Correction links, diagnostics, raw status/fitness, explicit read-only historical banner |
| 25 | Scheduling / confirmations | publish_replace_confirm.html, entry_remove_confirm.html, credential_override_confirm.html, confirm_delete.html | Specific consequences, protected POST/token/justification fields |
| 26 | Specialized / dashboards | admin_dashboard.html, faculty_dashboard.html, student_dashboard.html | Administrator hero/metrics versus personal role timetables |
| 27 | Specialized / room analytics | room_utilization.html, room_schedule.html, room_capacity_planning.html | Percent/hour tables, slot grids, estimates and assumptions explicitly distinguished |
| 28 | Specialized / availability | my_availability.html, generic resource list/form; models.py Availability | Faculty-specific columns; generic administrative object label differs |
| 29 | Specialized / credentials and GA settings | generic form/list, credential_override_confirm.html; forms.py | Equivalent multi-selection, dated qualification and numeric settings; no custom library |
| 30 | Specialized / spreadsheet import | academic_import.html, import_guide.html, import_summary.html, import_progress.html; import assets | Upload/dropzone, mapping, preview, stage guidance, errors, confirmation and busy states |

### Reuse and duplication

Reuse `base.html`, `_pagination.html`, `meeting_fields.html`, `personal_timetable.html` and the existing schedule table/timetable includes. Repeated heroes, toolbars, form action markup, inline spacing and empty states are consolidation candidates for 1.3, not reasons to merge different workflows.

There are intentionally different controls: server list sorting versus local availability sorting; keyboard-enabled meeting tabs versus click-driven schedule-view tabs; native confirmation dialogs versus the custom login modal. Standardization must retain each data/submission contract. Import assets already scope their layout and reuse shared color variables; test them whenever global tokens change.

## Findings register

Every row identifies current behavior/evidence, classification, impact, recommendation, priority and future owner. No recommendation is implemented here.

| ID | Component and implementation evidence | Current behavior / classification | Impact | Recommended improvement | Priority | Future task |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | app.css `[data-theme=dark]`, `.primary/.button-primary` | **C:** white foreground remains on #2dd4bf default and #5eead4 hover backgrounds | Poor text contrast for primary actions across dark pages | Introduce semantic on-primary foreground paired with each theme, verify all variants | High | 1.2, 1.4 |
| F02 | app.js auto-label `.info-icon` creation and `bindTooltips` | **C:** inserted spans receive no tabindex/accessible name; tooltip has role but no trigger `aria-describedby` linkage | Keyboard and assistive-technology help discovery incomplete; pre-existing manually focusable icons do not fix generated ones | Use consistent focusable help controls and descriptive association | High | 1.3, 2.2, 3.2, 6.1 |
| F03 | app.js `openLoginModal/closeLoginModal`; landing.html `role=dialog` | **C:** opening focuses username; Escape closes; no explicit Tab trap, background inertness or trigger focus restoration in inspected handlers | Dialog semantics promise modal interaction without full focus management | Define and test modal focus lifecycle, preserving login/CSRF | High | 1.4, 2.2, 6.1 |
| F04 | app.js `saveDraft`; views.py `save_form_draft` | **C:** any HTTP-ok response sets “Draft saved”; response JSON is not inspected, while endpoint can return saved:false | Success wording is broader than confirmed persistence; redirected successful login HTML may also be misclassified | Validate response contract and report truthful state; separately authorize persistence changes | High | 3.3 |
| F05 | app.js draft `savedState/dirty` mutation after await | **U (source-supported race risk):** no request-version guard; response completion resets dirty even if inputs changed while awaiting | Potential stale saved indicator/out-of-order draft writes; no loss reproduced | Reproduce with delayed responses and edits before proposing separately scoped logic changes | High | 3.3 |
| F06 | base.html `[data-global-filter]`; app.js `filterTables`; resource_list.html counts | **B/C clarity gap:** global search hides any matching DOM table rows, without updating server counts/pagination; available on pages with no tables | User may confuse current rendered page with database search; zero results lack a coordinated message | Clarify/condition visible search and respect server search/count scope | Medium | 2.2, 3.4 |
| F07 | my_availability.html `th[data-sort]`; app.js sorting handler | **C:** headers only have click handlers, no focusable buttons/keyboard activation or aria-sort updates; sorting uses text localeCompare | Keyboard sorting unavailable; weekday/time semantic ordering may surprise | Use semantic controls and explicit meaningful sort behavior after scope review | High | 3.4, 6.1 |
| F08 | base.html sidebar toggle buttons; app.js toggles CSS classes | **C:** no expanded-state synchronization for custom toggle buttons; native details do provide their own semantics | Collapsed/mobile state not explicitly announced | Add state/control association without replacing native disclosure behavior | Medium | 2.1, 6.1 |
| F09 | app.js `placeTooltip/hideTooltip`; app.css `.app-tooltip` | **C:** fixed tooltip clamps to viewport and hides on scroll/resize; pointer-events:none, disappears when leaving trigger, Escape only closes login modal | Help cannot be hovered and lacks independent Escape dismissal; clipping still unverified | Review dismissible/hoverable behavior and long text at edges; preserve existing clamping | Medium | 2.2, 6.1 |
| F10 | schedule_detail.html view tabs; app.js `[data-schedule-view-button]` | **C:** aria-selected/panel.hidden updated by click; no arrow/Home/End handling or roving tabindex unlike meeting tabs | Inconsistent keyboard tab interaction | Reuse established accessible tab behavior where semantics match | Medium | 4.3, 6.1 |
| F11 | models.py Availability; resource_list.html generic `{{ obj }}` | **C:** Availability defines no __str__; generic admin list renders object representation | “Availability object (pk)” omits useful owner/day/time context; faculty-specific table already has explicit fields | Prefer descriptive presentation fields; do not alter ownership/availability rules | Medium | 3.4, 5.3 |
| F12 | form.html `{{ form.as_p }}`; meeting_fields.html explicit errors/help spans | **U:** error linkage depends on Django-generated markup; custom help/error paths differ | Potential inconsistent announced errors/required guidance | Inspect invalid rendered forms and screen-reader associations; do not claim all labels/errors are missing | Medium | 3.2, 6.1 |
| F13 | form.html/assignment_form.html action toolbar | **B/U:** actions at form end; resource Cancel is link, generic Cancel can use history.back; draft link interceptor saves first | Long-form reach and Cancel expectations need browser confirmation | Explain exact outcomes and evaluate action positioning without changing persistence | Medium | 3.1, 3.3 |
| F14 | app.css h1 clamp/line-height, `.page-hero`; resource_list.html eyebrow | **B/U:** large short-line-height headings and generic “Master Data”; long-name wrapping/vertical waste unmeasured | Potential context loss and primary content below fold | Capture long data at reference viewport; adopt contextual hierarchy and spacing scale | Medium | 1.3, 2.4 |
| F15 | form.html/admin_dashboard.html/confirm_delete.html inline toolbar spacing; app.css draft styles | **B:** repeated inline spacing and mixed rem/px/radius conventions | Shared changes harder to maintain consistently | Inventory tokens and consolidate semantic spacing/component variants | Medium | 1.2, 1.3 |
| F16 | app.css `.room-schedule-grid`, `.room-slot span/small`; personal_timetable.html | **B/U:** grid min-width 1120px; details ellipsized/nowrap; classes rendered in slot cells | Deliberate horizontal scrolling; continuous duration and truncated details may be hard to follow | Test durations/long labels; keep start/end and accessible full details while preserving grid data | Medium | 4.2, 4.3, 6.2 |
| F17 | app.css `.table-wrap`, `.academic-schedule-table`; resource_list.html actions | **B/U:** overflow wrappers and specialized assignment action placement already exist | Excessive scrolling is possible but not confirmed at actual viewport | Test action reach with long records; preserve sorting/filtering, avoid indiscriminate hidden columns | Medium | 3.4, 6.2 |
| F18 | schedule_detail.html status line, history banner and “approval or publishing” message; app.js status tooltip dictionary | **C wording mismatch:** approval terminology remains though reviewed workflows expose publication/Copy to Draft, not a separate approval action | Suggests unsupported action; history banner itself is already explicit | Align terminology to supported states/actions; do not invent unpublication or approval flow | Medium | 4.4 |
| F19 | base.html `.topbar-search input` | **C:** placeholder exists but no explicit label/aria-label | Label disappears with entered text; accessible-name fallback needs browser/AT check | Add persistent accessible search name and scope | Medium | 2.2, 6.1 |
| F20 | app.css `.badge.success/.warning/.danger` fixed light backgrounds | **B/U:** semantic text variables and fixed backgrounds coexist in dark theme | Inconsistent surfaces/contrast possible; not every badge pair measured | Audit all semantic foreground/background combinations before token changes | Medium | 1.2, 1.4 |
| F21 | admin_dashboard.html hero/metrics; faculty/student dashboard templates | **B/U:** admin promotional headline dominates markup; personal dashboards prioritize timetable | Operational hierarchy and term interpretation require data-context review | Scope existing statistics before relabelling; retain role-specific presentations | Medium | 5.1 |
| F22 | room_capacity_planning.html callout; room_utilization.html hour/percentage columns | **B/U:** actual data and planning assumptions already labelled; dense metrics need comprehension testing | Readers may still misunderstand denominators/estimates | Explain units and existing calculation scope, never change formulas for UI work | Medium | 5.2 |
| F23 | forms.py credential multi-choice fields; credential_override_confirm.html | **B/U:** native equivalents selection; explicit term validity and override reason guidance already exists | Discoverability of multiple selection and related names needs evaluation | Improve examples/selection guidance while preserving IDs, validity and attribution | Medium | 3.2, 5.3 |
| F24 | app.js generation submit/pageshow; academic-import.js submit/reset; generic submit listener | **B:** generation/import have busy guards and restoration; generic forms only add loading class | Inconsistent loading semantics; no fake progress currently observed | Standardize truthful progress/state presentation; test cancelled submit/back navigation | Medium | 1.4, 4.1, 5.4 |
| F25 | base.html messages role=status; schedule_detail.html conflict toast; diverse empty rows/cards | **B/U:** shared messages have live status; local conflict/error regions vary | Announcements and helpful next actions inconsistent | Catalogue empty vs filtered vs permission cases and contextual feedback | Medium | 1.3, 5.4, 6.1 |
| F26 | app.css media rules; sidebar JS/storage | **U:** mobile overlay and restored desktop collapse/scroll coexist | Mobile focus escape/scroll reach and long groups need real device testing | Test stored states, all groups expanded and keyboard at narrow widths | High | 2.1, 2.3, 6.2 |

## Accessibility observations and measured contrast

Positive source evidence: document language and viewport, navigation labels, active-page markers, native disclosure semantics, POST sign-out, pagination aria-current, meeting tab keyboard handling/error focus, several aria-live status regions, focus-visible styles for meeting tabs/help icons, and reduced-motion rules. These are features to preserve, not replace.

Static relative-luminance calculations for the explicit primary-button colors yield:

| Pair | Contrast ratio | Interpretation |
| --- | ---: | --- |
| White / light primary #0f766e | 5.47:1 | Above the plan's 4.5:1 normal-text target |
| White / dark primary #2dd4bf | 1.86:1 | Below normal and large text targets |
| White / dark hover #5eead4 | 1.48:1 | Below normal and large text targets |

Method: normalize sRGB channels, linearize (c/12.92 at c<=0.04045, otherwise ((c+0.055)/1.055)^2.4), weight 0.2126/0.7152/0.0722 and calculate (lighter+0.05)/(darker+0.05). These are calculations from declared solid colors, not browser pixel samples or a full contrast audit. No claim is made for transparency, disabled states, gradients or every cascade variant.

The auto-generated info-icon and local-sort omissions are stronger source evidence than speculative visual clipping. Login focus trapping/restoration and mobile focus behavior need browser verification after source gaps are documented. Django supplies portions of form markup; inspect actual invalid forms before claiming missing error associations. Native dropdown, multi-select, confirm and details behavior must be tested with keyboard/AT rather than replaced solely for appearance.

## Search and autosave contracts

### Search, sorting and counts

- Top search placeholder already says “Search visible tables”; JS filters `table tbody tr` in the document. It is not a server/global academic search, does not filter timetable cards through that handler, and can affect multiple or hidden-view tables.
- Resource lists use GET q/sort/filter/page, server count summaries and query-preserving pagination/header links. DOM hiding neither recomputes those counts nor searches unloaded pages.
- Availability uses local data-table-filter and text sorting. Schedule-specific live filtering has separate table/card handling. Preserve these distinctions in 2.2/3.4; do not invent backend global search.
- Top search is hidden by CSS below 620px; appropriate page-level search must be verified before changing responsive behavior.

### Draft persistence and actions

- Draft-enabled forms serialize supported fields, including multiple selections; files and CSRF inputs are excluded from payload. Requests are authenticated same-origin JSON POST with CSRF.
- Input/change schedules save after 900ms; focusout after 250ms. Same-origin link navigation while dirty waits for save; pagehide attempts keepalive. Final submission stops draft scheduling. These are best-effort events, not proof that every interrupted navigation persists.
- Server endpoint permits administrators, uses user/resource/object keyed FormDraft records, filters allowed fields and saves draft payload/base signature. It does **not** save the academic record. It can return saved:false for unchanged/empty payload.
- Discard is an owner-bound POST deleting the draft, with explicit “saved record was not changed” feedback. Save is the actual record operation. Cancel may navigate after draft save; do not describe it as discarding edits.
- F04/F05 require truthful response/state handling and controlled delayed-response tests. Any persistence fix goes through separate authorization under the master plan; none was made in this audit.

## Responsiveness and screenshot follow-up

Existing shared breakpoints include 1180px (multi-column rearrangement), 900px (off-canvas sidebar, single-column day board, two-column filters), 620px (hidden top search and stacked controls), plus meeting/form-specific 600/640px rules. Import has its own scoped responsive styles. Fixed-minimum-width grids and ellipsis are explicit design choices.

| Browser scenario (not executed) | Evidence to collect | Related findings |
| --- | --- | --- |
| 1360x768 at 100%, both themes | Primary content position, long headings, action visibility, default/hover contrast | F01, F14–17, F20–22 |
| Sidebar all groups expanded/collapsed/restored | Scroll reach, active item visibility, group state, tooltip edge positioning | F08–09, F26 |
| 1024, 768 and 390 CSS-pixel widths | Form/table/timetable overflow, sidebar focus and long labels; record actual device scale | F13, F16–17, F26 |
| 200% zoom/text enlargement | Reflow, focus visibility, clipping, essential actions accessible | F02–03, F12–17 |
| Keyboard-only/AT | Login trap/restore, search labels, sorting, meeting and view tabs, help dismissal, error focus | F02–03, F07–10, F12, F19 |
| Long forms plus slow/offline/expired session | Draft saving/error/recovery, Cancel/Save/Discard outcomes and navigation | F04–05, F13 |
| Published/archived versus editable draft | Read-only banner, original/reconstructed history, correction/Copy to Draft controls per role | F18, F25 |

All developer screenshot concerns from the master plan are covered: lengthy navigation, irrelevant search, interfering tooltips, whitespace/generic headings, long titles, placeholders/help, form actions/drafts, technical meeting terms, equivalents/related records, wide/sparse tables and generic availability IDs, counts/empty states, duration/type visibility, historical status/conflicts, narrower timetables, operational metrics/term context and estimated versus actual analytics. Only source-supported portions are confirmed above. No screenshot observation is treated as a measured visual defect.

## Design system recommendations and Task 1.2 priorities

1. **First: semantic foreground/background pairs.** Address F01 with on-primary tokens appropriate to each theme; evaluate hover/focus and shared import usage. Audit all status badges and muted text next. Do not merely darken all teal branding.
2. **Inventory existing tokens before additions.** Retain navy/teal identity, light/dark switching and Inter/system fallback. Consolidate repeated spacing, type hierarchy, radii and shadows with documented mappings.
3. **Separate semantic state from color.** Define focus, invalid, warning, success, disabled and loading semantics; pair text/icons with color and preserve reduced motion.
4. **Keep component adoption scoped.** Token work may affect every page; verify shared buttons, forms, tables, import stages and public login in both themes. Save structural form/navigation redesign for its assigned tasks.
5. **Use realistic synthetic labels and reference views.** Check 1360x768 and narrower/zoom cases before selecting density values. No design token values or CSS were changed by this audit.

## Dependencies and regression protection

Task 1.2 now has a source inventory and measured primary-color issue. Task 1.3 should address duplicated heroes/actions and help primitives; 1.4/2.2 should address interaction/focus/tooltip behavior. Search scope must be coordinated between 2.2 and 3.4. Draft truthfulness belongs to 3.3 and cannot silently expand into persistence changes. Grid readability precedes 4.3 overflow changes. Specialist metrics remain tied to existing backend meanings. Phase 6 verifies cross-page accessibility, responsiveness and roles; targeted checks should occur earlier too.

Reviewed regression references include:
- `schedules/test_meeting_tabs.py`: draft restoration of added/deleted meetings, invalid values/errors, removal limits and synchronized fields.
- `schedules/test_listing.py`, `schedules/test_list_controls.py`: query-preserving pagination/sort, counts, all-resource rendering and permissions.
- `schedules/test_academic_import.py`: stage/mapping/preview and owner validation.
- `schedules/test_acceptance_workflows.py`: form creation through actual generation/publication, copied draft and private timetable flows.
- `schedules/test_admin_publication_security.py`, `schedules/test_diagnostic_access.py`, `schedules/test_snapshots.py`: privacy, POST/CSRF and historical presentation.
- `schedules/tests.py`: existing dashboard, timetable, forms and data behavior.

Django response assertions do not execute the custom JavaScript or certify layout. Add focused browser evidence when implementing the relevant tasks; retain the 551-test baseline and do not weaken meaningful access assertions merely for visual changes.

## Verification and completion

Audit covers all six requested major categories with 30 inventory groups and 26 evidence-labelled findings, each including source, current behavior, impact, recommendation, priority and future task. All source references are repository paths/selectors. Contrast calculations used source values only. No browser verification or full Django test run is claimed.

Only this document and master-plan progress tracking were changed. No application code, migrations, database, dependencies, commits or deployment. Git whitespace and new-document structure/path checks are performed at completion.

**Task 1.1: Completed (source/documentation audit). UI/UX progress: 1/24.** All remaining tasks remain Not Started. Browser evidence limitations and future verification are explicit. Await approval before Task 1.2.

