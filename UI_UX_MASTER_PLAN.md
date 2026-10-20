# SchedEase UI/UX Improvement Master Plan

## Purpose and status

Official planning reference for a six-phase, 24-task refinement of SchedEase's existing interface. Preserve its dark navy and teal/cyan identity, Django architecture and light/dark behavior. This is modernization of the existing system, not a replacement frontend.

**5 of 24 UI/UX tasks completed.** Tasks 1.1-1.4 and 2.1 are **Completed**; **Phase 1 is Completed** and **Phase 2 is In Progress**; all remaining tasks are **Not Started**. See [Component audit](UI_UX_COMPONENT_AUDIT.md) and [Design tokens](UI_UX_DESIGN_TOKENS.md) for findings, measured contrast, 554 passing tests and browser-verification limitations. See [Shared component guide](UI_UX_SHARED_COMPONENTS.md) for Task 1.3 changes and verification. See [Interaction states](UI_UX_INTERACTION_STATES.md) for Task 1.4 verification and remaining manual accessibility checks. See [Sidebar navigation](UI_UX_SIDEBAR_NAVIGATION.md) for Task 2.1 results. Await approval before Task 2.2.

The earlier 34-task improvement plan is a separate completed milestone with **conditional system acceptance**. Its documented baseline is **551 passing automated tests**; these were not rerun for this documentation-only task. See [final system verification](FINAL_SYSTEM_VERIFICATION_REPORT.md) and [acceptance matrix](FINAL_ACCEPTANCE_TEST_MATRIX.md). Outstanding browser, infrastructure, supported-framework upgrade and academic clarification requirements remain outstanding; this initiative does not authorize deployment.

Planning inspection: 2026-10-20. Initial `git status --short` was empty: no modified, staged or untracked files. Preserve any changes present when a future task begins.

## Existing architecture reviewed

Paths below are relative to the repository root and identify implementation surfaces, not authorization to edit them now.

| Area | Actual sources | Reuse and coupling |
| --- | --- | --- |
| Shared shell/navigation | `templates/base.html` | Role-conditioned grouped sidebar, top bar, theme/account controls, shared assets; changing this affects most pages |
| Shared styles | `static/css/app.css` | Existing semantic CSS variables for light and dark themes, component styles, responsive rules, focus and reduced-motion rules |
| Shared interaction | `static/js/app.js` | Theme/localStorage, sidebar/sessionStorage, tooltips, rendered-table search/sort, draft saving, generation feedback and dynamic meeting controls |
| Generic and assignment forms | `templates/schedules/form.html`, `assignment_form.html`, `meeting_fields.html` in the same directory; `schedules/forms.py` | Django form rendering and inline formsets; shared classes plus data attributes, hidden IDs and management fields |
| Record tables | `templates/schedules/resource_list.html`, `templates/schedules/_pagination.html`; `schedules/services/listing.py` | Server GET search/filter/sort/page controls and counts must remain authoritative |
| Schedule views | `templates/schedules/schedule_detail.html`, `schedule_table_view.html`, `schedule_timetable_view.html`, `entry_table.html`, `personal_timetable.html`, `browse.html` in the same directory | Multiple representations: day-column cards, academic tables and time-slot grids; not one interchangeable widget |
| Specialist pages | `templates/schedules/admin_dashboard.html`, `faculty_dashboard.html`, `student_dashboard.html`, `room_utilization.html`, `room_schedule.html`, `room_capacity_planning.html`, `my_availability.html` | Shared panel/hero/table styles combined with role-specific data and analytics |
| Spreadsheet import | `templates/schedules/academic_import.html`, `import_guide.html`, `import_progress.html`, `import_summary.html`; `static/css/academic-import.css`, `static/js/academic-import.js` | Separate assets and stage-specific components require explicit inclusion in shared-token/state changes |
| Confirmations and diagnostics | `templates/schedules/confirm_delete.html`, `credential_override_confirm.html`, `entry_remove_confirm.html`, `publish_replace_confirm.html`, `error_log.html`, `error_detail.html`, `generation_run_detail.html` | Preserve signed revisions, approval attribution, POST/CSRF and private diagnostic scope |
| Public/authentication | `templates/landing.html`, `templates/registration/login.html` | Include visitor and login behavior in later shell/accessibility tests |

Repeated patterns include page heroes/eyebrows, panel cards, toolbars, generic form paragraphs, messages, confirmation actions and empty table rows. Some are shared includes; others repeat markup and inline spacing across templates. Consolidation should follow the Task 1.1 inventory, not an assumption that all similarly styled content has identical semantics.

### Evidence classification

**Source-confirmed observations (not automatically defects):**

- `app.css` already defines light-theme tokens in `:root` and dark overrides under `[data-theme="dark"]`. Token work should extend and reconcile these rather than introduce a competing theme system.
- `base.html` loads Inter through Google Fonts; include a system-font/offline fallback check before making text-fit assumptions.
- Sidebar disclosures and active-link logic coexist with stored collapse/scroll state in JavaScript. Responsive work must consider both initial HTML state and restored state.
- `filterTables()` in `app.js` filters rendered table body rows. Top-bar search is therefore not a database-wide search; resource lists separately submit GET queries and pagination. Clarifying these scopes is a dependency between Tasks 2.2 and 3.4.
- Generic `form.html` uses `form.as_p`, an initial draft-status message, Save/Cancel actions and a generation-specific branch. JavaScript sends draft requests with CSRF, waits about 900 ms after changes, and distinguishes saving, saved and failure. Presentation must reflect those existing semantics.
- The assignment editor uses `meetings.management_form`, an empty-form template, dynamically shown tabs and `data-add-meeting`. Preserve these contracts and existing entered data.
- `resource_list.html` contains the generic eyebrow “Master Data”. Repeated inline toolbar spacing exists in generic forms, dashboard and confirmation templates. Whether it harms usability requires visual evaluation.
- `personal_timetable.html` renders time-slot cells while `schedule_timetable_view.html` renders day-column events with explicit start/end and component labels. Continuity must be evaluated separately for each view.
- Capacity planning already distinguishes “Actual SchedEase data” from “Planning assumptions”. Improve clarity if needed; do not claim this distinction is absent.
- Focus-visible, breakpoints and reduced-motion rules already exist. Their presence is not proof of complete keyboard access, adequate contrast or responsive behavior.

No screenshots were supplied for direct inspection in this task and no browser was launched. The following are **developer-reported candidates from 1360 x 768 at 100% browser zoom**, not independently confirmed visual defects.

| Candidate observation | Verification needed | Primary task(s) |
| --- | --- | --- |
| Expanded sidebar becomes lengthy | Expand all groups, test scrolling/focus and restored state at reference viewport | 2.1, 2.3 |
| Search irrelevant without tables | Check visibility and scope on form, dashboard and timetable pages | 2.2, 3.4 |
| Tooltips interfere with headings | Real hover/focus/touch, edge placement, zoom and dismissal | 2.2, 6.1 |
| Excess vertical space before primary content | Compare content start position and action visibility across pages | 2.4, 1.3 |
| Generic “MASTER DATA” context | Confirm per-resource headings and choose descriptive copy | 1.3, 3.4 |
| Shared editors consistent but improvable; long titles wrap awkwardly | Long synthetic names, errors and both themes | 3.1, 2.4 |
| Dropdown placeholders/related records unclear | Inspect rendered option labels and actual choice semantics | 3.2, 5.3 |
| Information icons and guidance need review | Keyboard/screen-reader association, touch access and necessity | 3.2, 6.1 |
| Save/Cancel difficult to reach | Long forms, keyboard sequence and narrow viewport; do not assume sticky controls are required | 3.1, 3.3 |
| Autosave wording may not match behavior | Slow/failed save, recovery, cancel and submit transitions with synthetic data | 3.3 |
| Meeting controls expose technical language | Inspect visible labels against formset/meeting rules | 3.2, 4.2 |
| Credential equivalency selection unintuitive | Test multi-selection, instructions and term-validity explanations | 3.2, 5.3 |
| Wide tables demand horizontal scrolling | Test representative long data and action access, preserve meaningful columns | 3.4, 6.2 |
| Records omit useful descriptions; availability shows object identifiers | Trace rendered list cells/choice labels to sources before proposing presentation changes | 3.4, 5.3 |
| Empty states lack guidance; counts/filter/sort consistency | Empty versus filtered versus inaccessible data; query state across navigation | 3.4, 5.4 |
| Timetable duration continuity unclear | Inspect grid/day/table views for split-cell interpretation and overlap readability | 4.2 |
| Lecture/lab distinction must remain visible | Verify text labels at all widths, not color alone | 4.2, 6.2 |
| Schedule status/history and corrections unclear | Follow draft, published, archived and correction routes with authorized accounts | 4.4 |
| Scheduling access at narrow widths | View/filter switching and deliberate overflow navigation | 4.3, 6.2 |
| Dashboard metrics need operational priority and term context | Trace existing metric scope before changing labels/order | 5.1 |
| Room estimates versus actuals and metric explanations | Verify existing calculation meaning, units and legends without changing formulas | 5.2 |

## Design direction

- Retain navy shell/surfaces and teal/cyan action identity; retain existing light-theme support and branding.
- Build on semantic tokens: surface, text, muted text, borders, primary action, status, focus and elevation. Define foreground/background pairs for each theme, not isolated colors.
- Reconcile a small type hierarchy and spacing scale after measurement in Task 1.1; use consistent line heights, readable long labels and numeric table alignment. Do not prescribe new pixel values without baseline evidence.
- Prefer reusable headings, panels, control groups, alerts and existing partials. Keep decorative elements subordinate to academic records and scheduling tasks.
- Test the reference 1360 x 768 viewport at 100% zoom, then representative 1024, 768 and 390 CSS-pixel widths and text/zoom enlargement. Exact browser, viewport and device scale must be recorded; these are proposed test cases, not completed tests.
- Treat keyboard access and non-color state cues as design inputs from Phase 1. Use measurable contrast targets (4.5:1 normal text, 3:1 large text and meaningful UI boundaries/focus indicators where applicable), while reserving formal accessibility claims for verified evidence.
- Preserve native semantic controls where feasible. Avoid a new framework, component library, frontend build chain or unnecessary dependency without separate approval.
- Prefer contained scrolling for genuinely wide tables/timetables; do not remove essential data or actions to produce a superficially narrow layout.
- Keep loading and progress truthful to actual server responses. Do not invent completion percentages or change generation/persistence contracts for presentation.

## Project-wide rules and completion gates

1. Implement only one explicitly assigned task at a time. Begin with Git status/diff and preserve all uncommitted work.
2. Inspect relevant code before editing. These file lists are planning references; backend files do not imply authorization to change their logic.
3. Preserve Django functionality, GA generation/fitness/constraints, academic rules and data integrity. No unrelated migrations or schema changes.
4. Preserve finalized immutability, historical snapshots, Copy to Draft, signed revisions, audit history and authorized publication workflows.
5. Preserve role-based and object-level access, Django admin restrictions, CSRF and POST enforcement. UI visibility is not authorization.
6. Treat Light Mode and Dark Mode as equally important throughout every task, with intentionally selected semantic palettes rather than automatic inversion. Verify text, controls, navigation, cards, tables, forms, dropdowns, modals, tooltips and all interaction/status states separately in each theme; report source/automated results separately from actual browser results. Preserve the theme toggle and saved preference behavior. Preserve both themes and existing controls/features. Retain input names, formset fields, endpoint contracts and JavaScript hooks unless a separately authorized change explicitly covers them.
7. Do not change autosave or other persistence behavior without separate authorization. Escalate a confirmed backend defect as a separate scope decision.
8. Avoid unnecessary dependencies. No commits without approval; no deployment.
9. Use synthetic data and disposable test databases for mutation tests. Never change real database selection or run migrations to test visuals. The default and worksheet sample databases differ; see the final verification report.
10. Run focused regression checks appropriate to each implementation change; retain the 551-test baseline. Changes in shared components require representative cross-module checks. Run the full suite for the final acceptance gate and when broad changes justify it.
11. Record source inspection, automated tests, real browser runs and manual checks separately. Do not claim screenshots, visual acceptance or accessibility conformance without actual evidence.
12. Finish each task with files changed, behavior, tests/results, screenshots where executed, remaining issues and tracker update. Wait for the next explicit assignment.

### Regression references

- Generic forms/timetables and role behavior: `schedules/tests.py`.
- Dynamic meeting contracts: `schedules/test_meeting_tabs.py`, `schedules/test_meeting_requirements.py`.
- List query state/counts: `schedules/test_listing.py`, `schedules/test_list_controls.py`; [pagination](ADMIN_LIST_PAGINATION.md), [list controls](ADMIN_LIST_CONTROLS.md).
- Import: `schedules/test_academic_import.py`; [import guide](ACADEMIC_IMPORT.md).
- Manual edits/corrections: `schedules/test_manual_transactions.py`, `schedules/test_corrections.py`, `schedules/test_copy_remove.py`; [manual transaction contract](MANUAL_SCHEDULE_TRANSACTIONS.md).
- Permissions/history: `schedules/test_admin_publication_security.py`, `schedules/test_diagnostic_access.py`, `schedules/test_finalized_protection.py`, `schedules/test_snapshots.py`; [admin audit](ADMIN_PERMISSION_PUBLICATION_AUDIT.md).
- Integrated workflows: `schedules/test_acceptance_workflows.py`; [final acceptance matrix](FINAL_ACCEPTANCE_TEST_MATRIX.md).
- Theme/responsiveness/keyboard behavior requires real browser checks in addition to Django HTML assertions. Existing automated tests do not establish visual acceptance.

## Task definitions

Priority describes impact, not permission to skip dependencies. Complexity is relative (Medium/High), not a time estimate. Source files named below may be inspected now only as planning references; actual changes wait for assignment.

### Phase 1 — Design System and Interface Consistency

#### Task 1.1 — Comprehensive UI Component Audit

- **Objective:** Inventory components and establish evidence before visual changes.
- **Scope:** Shell, templates, CSS cascade, JavaScript hooks, representative roles and themes.
- **Relevant sources/components:** All source groups below; existing UI-related tests and reports.
- **Dependencies:** None
- **Expected deliverables:** Component inventory, evidence-labelled issue register, screenshot/browser checklist and token requirements.
- **Acceptance criteria:** Every major page family and both themes mapped; each issue has source or reproduction evidence, severity, owner task and verification method; no implementation implied.
- **Regression risks:** Incomplete role coverage or mistaking static source findings for visual defects.
- **Priority / estimated complexity:** High / Medium

#### Task 1.2 — Standardize Visual Design Tokens

- **Objective:** Make typography, spacing and surfaces coherent without changing identity.
- **Scope:** Semantic color pairs, type scale, spacing, radii, borders, shadows and button foundations.
- **Relevant sources/components:** static/css/app.css; static/css/academic-import.css; templates/base.html
- **Dependencies:** 1.1
- **Expected deliverables:** Token inventory/mapping and controlled shared-style changes.
- **Acceptance criteria:** Navy/teal branding retained; both themes readable; representative forms, tables and imports checked; no new framework.
- **Regression risks:** Global cascade changes, import overrides, contrast loss and external font fallback.
- **Priority / estimated complexity:** High / High

#### Task 1.3 — Standardize Shared UI Components

- **Objective:** Align repeated headings, cards, forms, alerts and table containers.
- **Scope:** Shared template/class conventions; reuse existing includes before introducing new abstractions.
- **Relevant sources/components:** templates/base.html; templates/schedules/form.html; templates/schedules/resource_list.html; templates/schedules/_pagination.html; static/css/app.css
- **Dependencies:** 1.1, 1.2
- **Expected deliverables:** Component usage guide and consistent shared patterns.
- **Acceptance criteria:** Shared families use consistent hierarchy and spacing; existing fields, links, POST forms and data attributes retained.
- **Regression risks:** Breaking template context, CSRF fields, script selectors or specialized layouts.
- **Priority / estimated complexity:** High / High

#### Task 1.4 — Improve Interactive States

- **Objective:** Make interaction and validation states visible and understandable.
- **Scope:** Hover, focus, disabled, loading, success/error and validation states; reduced motion.
- **Relevant sources/components:** static/css/app.css; static/js/app.js; static/js/academic-import.js; templates/schedules/form.html
- **Dependencies:** 1.2, 1.3
- **Expected deliverables:** State matrix and reusable state styling/behavior.
- **Acceptance criteria:** Keyboard focus visible; disabled controls distinguishable; status not communicated by color alone; loading reflects real events and recovers on failure.
- **Regression risks:** Double submissions, permanently disabled controls or falsely claiming completion.
- **Priority / estimated complexity:** High / Medium

### Phase 2 — Navigation and Page Layout

#### Task 2.1 — Refine Sidebar Navigation

- **Objective:** Keep grouped navigation manageable and orientation clear.
- **Scope:** Expanded/collapsed/mobile states, active links, scroll position and disclosure behavior.
- **Relevant sources/components:** templates/base.html; static/js/app.js; static/css/app.css
- **Dependencies:** 1.3, 1.4
- **Expected deliverables:** Refined sidebar and role/state verification notes.
- **Acceptance criteria:** All permitted links remain reachable; active page and expanded group agree; saved state does not trap keyboard/mobile users.
- **Regression risks:** Role-menu leakage, changed storage keys, overflow or focus loss.
- **Priority / estimated complexity:** High / Medium

#### Task 2.2 — Improve Top Navigation and Tooltips

- **Objective:** Make search, account/theme controls and help contextual.
- **Scope:** Clarify current-page search scope; account actions; tooltip placement, dismissal and focus.
- **Relevant sources/components:** templates/base.html; static/js/app.js; static/css/app.css
- **Dependencies:** 1.3, 1.4, 2.1
- **Expected deliverables:** Contextual navigation/search presentation and tooltip rules.
- **Acceptance criteria:** Search accurately describes its scope on table and non-table pages; keyboard/touch help usable without obscuring primary controls; theme and account actions preserved.
- **Regression risks:** Client row filtering conflicting with server pagination; tooltip clipping or lost logout CSRF.
- **Priority / estimated complexity:** High / Medium

#### Task 2.3 — Responsive Layout Improvements

- **Objective:** Preserve workflows at desktop, tablet and narrow widths.
- **Scope:** Shared shell, form columns, control wrapping and explicit contained overflow.
- **Relevant sources/components:** templates/base.html; static/css/app.css; static/css/academic-import.css; shared form/list templates
- **Dependencies:** 2.1, 2.2
- **Expected deliverables:** Responsive rules and representative viewport evidence.
- **Acceptance criteria:** Primary controls reachable at 1360x768/100% and representative narrower sizes; no accidental page-wide overflow; deliberate table scrolling labelled.
- **Regression risks:** Hidden essential columns/actions, sticky layers covering content, theme regression.
- **Priority / estimated complexity:** High / High

#### Task 2.4 — Optimize Page Spacing and Content Density

- **Objective:** Bring primary content into view without crowding it.
- **Scope:** Hero/header height, section gaps, panel padding and long-title wrapping.
- **Relevant sources/components:** static/css/app.css; templates/schedules/resource_list.html; templates/schedules/form.html; dashboard templates
- **Dependencies:** 1.2, 1.3, 2.3
- **Expected deliverables:** Density conventions and before/after evidence.
- **Acceptance criteria:** Useful content visible earlier at reference viewport; long labels remain legible and interactive targets usable in both themes.
- **Regression risks:** Over-compression, clipped validation text or inconsistent specialist overrides.
- **Priority / estimated complexity:** Medium / Medium

### Phase 3 — Record Management and Forms

#### Task 3.1 — Standardize Record Editors

- **Objective:** Make academic record editors consistent and easy to scan.
- **Scope:** Generic and assignment editors, grouping, actions and related-record controls; presentation only.
- **Relevant sources/components:** templates/schedules/form.html; templates/schedules/assignment_form.html; templates/schedules/meeting_fields.html; schedules/forms.py (contract reference); static/js/app.js
- **Dependencies:** 1.3, 1.4, 2.3, 2.4
- **Expected deliverables:** Reusable editor layout and module coverage checklist.
- **Acceptance criteria:** Add/edit fields and meeting formset management preserved; errors keep entered values; Save/Cancel reachable on long forms.
- **Regression risks:** Changing input names, hidden IDs, meeting deletion flags or Django form binding.
- **Priority / estimated complexity:** High / High

#### Task 3.2 — Improve Field Guidance and Validation

- **Objective:** Explain required values and errors in everyday language.
- **Scope:** Labels, examples, placeholders, required indicators, error summary and related-record/equivalent selection guidance.
- **Relevant sources/components:** Shared form/meeting templates; static/js/app.js tooltip dictionaries; schedules/forms.py (inspect labels/widgets only when explicitly assigned)
- **Dependencies:** 3.1
- **Expected deliverables:** Field wording inventory and accessible guidance/error presentation.
- **Acceptance criteria:** Guidance matches real rules; field/error associations usable by keyboard; no invented data or weakened validation; equivalency selection understandable.
- **Regression risks:** Misleading policy descriptions, stale automatic tooltip lookup or altered choice values.
- **Priority / estimated complexity:** High / Medium

#### Task 3.3 — Clarify Draft Saving and Form Actions

- **Objective:** Explain exactly what draft saving and final saving mean.
- **Scope:** Existing autosave states, recovery/conflicts, unsaved changes, Save/Cancel and destructive actions.
- **Relevant sources/components:** templates/schedules/form.html; templates/schedules/assignment_form.html; static/js/app.js; schedules/services/form_drafts.py (contract reference); schedules/views.py (reference)
- **Dependencies:** 3.1, 3.2, 1.4
- **Expected deliverables:** Documented state/action map and truthful status copy.
- **Acceptance criteria:** Saving/saved/error feedback follows actual responses; Cancel/recovery behavior explained accurately; signed revisions and POST/CSRF remain intact.
- **Regression risks:** Changing debounce/payload/persistence or promising discard when data is retained; separate authorization required for persistence changes.
- **Priority / estimated complexity:** High / High

#### Task 3.4 — Improve Record Tables and Controls

- **Objective:** Make useful data and actions easy to reach.
- **Scope:** Density, descriptive columns, headings, counts, search/filter/sort/pagination and empty rows.
- **Relevant sources/components:** templates/schedules/resource_list.html; templates/schedules/_pagination.html; templates/schedules/entry_table.html; static/js/app.js; static/css/app.css; schedules/services/listing.py (contract reference)
- **Dependencies:** 1.3, 2.2, 2.3, 2.4
- **Expected deliverables:** Consistent table controls and responsive action layout.
- **Acceptance criteria:** Query/filter/sort/page state preserved; counts remain accurate; actions keyboard reachable; wide-table strategy does not hide essential information.
- **Regression risks:** Mixing client filtering with server counts, wrong sort semantics or changed column indexes.
- **Priority / estimated complexity:** High / High

### Phase 4 — Scheduling Interface

#### Task 4.1 — Improve Schedule Generation and Management

- **Objective:** Clarify setup, generation feedback and schedule management.
- **Scope:** Generation form/import entry point, current configuration, honest loading/results and schedule status lists.
- **Relevant sources/components:** templates/schedules/form.html; templates/schedules/resource_list.html; templates/schedules/schedule_cards.html; templates/schedules/academic_import.html; static/js/app.js
- **Dependencies:** 3.1, 3.3, 3.4
- **Expected deliverables:** Refined generation/management layout and state guidance.
- **Acceptance criteria:** Import/configuration remain accessible; generation success/failure linked to existing records; no invented progress percentage or automatic publication.
- **Regression risks:** Lease/submit behavior, lost seed/settings fields or conflating saved draft with published schedule.
- **Priority / estimated complexity:** High / High

#### Task 4.2 — Improve Timetable and Schedule Table Readability

- **Objective:** Make meeting time, duration and type clear.
- **Scope:** Day-board, grid, table and personal views; continuous duration cues and lecture/lab distinctions.
- **Relevant sources/components:** templates/schedules/schedule_timetable_view.html; templates/schedules/schedule_table_view.html; templates/schedules/personal_timetable.html; templates/schedules/entry_table.html; static/css/app.css
- **Dependencies:** 1.3, 2.3, 3.4, 4.1
- **Expected deliverables:** Consistent meeting presentation across existing views.
- **Acceptance criteria:** Start/end, course, room, faculty/section and lecture/lab labels readable; one meeting's duration understandable without changing placement data.
- **Regression risks:** Confusing repeated time slots, misrepresented overlaps or losing authorized snapshot fields.
- **Priority / estimated complexity:** High / High

#### Task 4.3 — Improve Scheduling Navigation and Filtering

- **Objective:** Keep filtered meeting information accessible across widths.
- **Scope:** View switching, query persistence, term/section/faculty filters, horizontal navigation and details.
- **Relevant sources/components:** templates/schedules/browse.html; templates/schedules/schedule_detail.html; timetable/table templates; static/js/app.js; static/css/app.css
- **Dependencies:** 4.2, 2.2, 2.3
- **Expected deliverables:** Unified navigation/filter presentation and narrow-screen evidence.
- **Acceptance criteria:** Switching views retains supported filters; long tables scroll predictably; own timetable scope preserved.
- **Regression risks:** Dropping query state, clipping controls or exposing records from another role/section.
- **Priority / estimated complexity:** High / Medium

#### Task 4.4 — Clarify Conflicts and Publication States

- **Objective:** Explain actionable conflicts and lifecycle restrictions.
- **Scope:** Correction links, diagnostics, generation outcomes, draft/finalized badges and publication/replacement confirmations.
- **Relevant sources/components:** templates/schedules/schedule_detail.html; templates/schedules/error_log.html; templates/schedules/error_detail.html; templates/schedules/generation_run_detail.html; templates/schedules/publish_replace_confirm.html; templates/schedules/entry_remove_confirm.html
- **Dependencies:** 4.1, 4.2, 4.3, 3.3
- **Expected deliverables:** Consistent status vocabulary and clear corrective/confirmation guidance.
- **Acceptance criteria:** Draft/published/archived and read-only history explicit; correction and Copy to Draft remain supported routes; no invented unpublication; sensitive diagnostics stay restricted.
- **Regression risks:** Misstating supported transitions, exposing private diagnostics or losing signed/confirmed POST fields.
- **Priority / estimated complexity:** High / High

### Phase 5 — Dashboard and Specialized Modules

#### Task 5.1 — Improve Dashboard Information Hierarchy

- **Objective:** Prioritize meaningful role-specific information.
- **Scope:** Term context, publication state, actionable links and existing statistics; no new calculations.
- **Relevant sources/components:** templates/schedules/admin_dashboard.html; templates/schedules/faculty_dashboard.html; templates/schedules/student_dashboard.html; static/css/app.css
- **Dependencies:** 1.3, 2.4, 4.4
- **Expected deliverables:** Role-specific hierarchy and metric wording.
- **Acceptance criteria:** Each displayed metric has clear scope/context; available actions match role; current data sources preserved.
- **Regression risks:** Mislabelled totals, inferred current term or leaking administrator statistics.
- **Priority / estimated complexity:** Medium / Medium

#### Task 5.2 — Improve Room Analytics and Capacity Planning

- **Objective:** Explain room information and distinguish estimates from observations.
- **Scope:** Utilization, room schedule, capacity estimates, legends, units and filter layouts.
- **Relevant sources/components:** templates/schedules/room_utilization.html; templates/schedules/room_schedule.html; templates/schedules/room_capacity_planning.html; static/css/app.css
- **Dependencies:** 3.4, 4.2, 4.3, 5.1
- **Expected deliverables:** Consistent analytics presentation with explanatory labels.
- **Acceptance criteria:** Available/scheduled hours and percentages clear; estimates labelled; no change to availability or utilization calculations; controls/exports preserved.
- **Regression risks:** Presenting estimates as actual occupancy, scale distortion or inaccessible color-only legends.
- **Priority / estimated complexity:** Medium / High

#### Task 5.3 — Improve Specialized Academic Interfaces

- **Objective:** Make credential, availability, faculty and GA settings workflows understandable.
- **Scope:** Presentation using shared editors/lists; qualification/equivalent guidance and settings descriptions.
- **Relevant sources/components:** templates/schedules/my_availability.html; templates/schedules/credential_override_confirm.html; shared forms/lists; static/js/app.js; schedules/forms.py (contract reference)
- **Dependencies:** 3.1, 3.2, 3.3, 3.4, 5.2
- **Expected deliverables:** Specialist copy/layout refinements and contract checklist.
- **Acceptance criteria:** Faculty ownership, credential validity/justification and GA parameter values unchanged; related records identified clearly.
- **Regression risks:** Misstated validity policy, actor attribution changes or unapproved algorithm/settings defaults.
- **Priority / estimated complexity:** Medium / High

#### Task 5.4 — Standardize Feedback and Empty States

- **Objective:** Make feedback consistent across all refined modules.
- **Scope:** Empty/loading/error/success states and existing confirmation dialogs.
- **Relevant sources/components:** templates/base.html; shared form/list templates; templates/schedules/confirm_delete.html; templates/schedules/entry_remove_confirm.html; import templates/assets
- **Dependencies:** 1.4, 4.4, 5.1, 5.2, 5.3
- **Expected deliverables:** Cross-module message/state catalogue and final consistency pass.
- **Acceptance criteria:** Empty dataset distinguished from filtered/no-permission results; useful allowed next action; confirmations name effects; status announcements avoid repetition.
- **Regression risks:** Leaking inaccessible data, generic destructive wording or misleading success messages.
- **Priority / estimated complexity:** Medium / Medium

### Phase 6 — Accessibility, Testing, and Final Polish

#### Task 6.1 — Accessibility Improvements

- **Objective:** Complete cross-module accessibility review and remediation.
- **Scope:** Keyboard order, focus, labels, contrast, dialogs, tooltips, motion and accessible state announcements.
- **Relevant sources/components:** Shared shell/assets plus all changed templates; existing semantic controls and JS handlers
- **Dependencies:** 1.4, 2.1, 2.2, 3.2, 5.4
- **Expected deliverables:** Measured accessibility checklist and scoped fixes/evidence.
- **Acceptance criteria:** Keyboard-only workflows succeed; focus visible/restored; text and non-text contrast measured in both themes; help dismissible; blocked checks documented.
- **Regression risks:** Late shared changes affecting all modules; claiming conformance from source inspection alone.
- **Priority / estimated complexity:** High / High

#### Task 6.2 — Responsive and Overflow Verification

- **Objective:** Verify complete workflows at representative sizes.
- **Scope:** Desktop/tablet/mobile widths, long data, large text, zoom, dropdown/tooltips and overflow.
- **Relevant sources/components:** All changed page families; static/css/app.css; static/css/academic-import.css
- **Dependencies:** 2.3, 4.3, 5.4, 6.1
- **Expected deliverables:** Viewport/theme/role matrix with real screenshots and defects.
- **Acceptance criteria:** 1360x768 at 100% checked; narrower cases and text enlargement checked; essential controls reachable; intentional scrolling distinguished from layout defects.
- **Regression risks:** Testing only short fixtures or one role; hiding columns to force a superficial fit.
- **Priority / estimated complexity:** High / Medium

#### Task 6.3 — Role-Based UI Regression Testing

- **Objective:** Prove visual changes preserve role workflows and protections.
- **Scope:** Administrator, faculty, student, visitor and staff-without-ADMIN flows, exports, diagnostics and denied direct URLs.
- **Relevant sources/components:** schedules/test_acceptance_workflows.py; schedules/test_admin_publication_security.py; schedules/test_diagnostic_access.py; schedules/test_security_settings.py; schedules/tests.py; changed templates
- **Dependencies:** 6.1, 6.2
- **Expected deliverables:** Updated focused assertions, full baseline regression results and browser role checks.
- **Acceptance criteria:** All 551 baseline tests preserved; legitimate HTML changes reflected without weakening privacy assertions; permissions/CSRF/snapshots unchanged; browser claims backed by runs.
- **Regression risks:** Treating hidden links as authorization or weakening tests to accept a visual regression.
- **Priority / estimated complexity:** High / High

#### Task 6.4 — Final Visual Consistency and Acceptance Review

- **Objective:** Close the initiative with traceable acceptance evidence.
- **Scope:** Final component/page review, open issues, test evidence, limitations and handoff.
- **Relevant sources/components:** UI_UX_MASTER_PLAN.md; all changed UI files; FINAL_SYSTEM_VERIFICATION_REPORT.md (baseline reference)
- **Dependencies:** 6.3; all earlier tasks completed or explicitly dispositioned
- **Expected deliverables:** UI/UX acceptance report and updated tracker with evidence links.
- **Acceptance criteria:** All 24 tasks accounted for; both themes/roles/viewports evidenced; deferred or blocked items explicit; no unsupported production-readiness claim.
- **Regression risks:** Equating automated tests with visual acceptance or losing unresolved institutional/deployment conditions.
- **Priority / estimated complexity:** High / Medium

## Dependencies and recommended execution order

Default order remains **1.1 → 1.2 → 1.3 → 1.4 → 2.1 ... → 6.4**, one explicitly authorized task at a time. Dependency lists identify required shared contracts; they do not grant parallel implementation authority. The planning review found no mandatory reason to renumber or remove tasks.

Important coupling:

- Shared tokens precede component consolidation; both must cover the independent import stylesheet.
- Sidebar geometry affects top-bar tooltip placement; establish it before final navigation/tooltip adjustments.
- Server list controls and rendered-row search must be reconciled conceptually before table polish.
- Generic editors, assignment tabs and draft states share JavaScript/data attributes; validate these together even when only one assigned task changes.
- Timetable readability precedes final scheduling overflow/navigation refinement.
- Dashboard and analytics wording depends on existing metric scope, not new backend computations.
- Final role-based testing follows shared accessibility/responsive fixes, but targeted role checks must run throughout.

## Proposed Master Plan Adjustments

No tasks are removed, merged or renumbered. Recommended refinements within the original six-phase structure:

1. **Accessibility throughout, final review in 6.1.** Establish keyboard/contrast requirements in 1.1 and apply them to each assigned change. Waiting until Phase 6 risks repeating global CSS and tooltip work; Task 6.1 remains the comprehensive review/remediation task.
2. **Responsive checks throughout, final matrix in 6.2.** Task 2.3 owns shared responsive implementation; Tasks 3–5 check their affected pages; Task 6.2 remains end-to-end verification.
3. **Separate shared primitives from feature adoption.** Task 1.3 defines consistent components, while 3.1/3.4/5.4 adapt specialist editors, table workflows and final feedback. Avoid redesigning later modules during Phase 1.
4. **Search contract before visual table refinement.** Tasks 2.2 and 3.4 must document current-page versus server search boundaries. A global backend search would be a separate feature, not an implied part of these tasks.
5. **Capture comparable evidence.** Task 1.1 should establish synthetic examples, roles, viewport/zoom/theme and baseline screenshots if a browser is available, enabling meaningful comparisons in 6.4.
6. **No unsupported scope expansion.** Curriculum completeness, fixed placements, deployment and framework upgrade remain outside this UI/UX plan; report limitations instead of quietly implementing them.

## Progress tracker

Statuses: **Not Started**, **In Progress**, **Completed**, **Blocked**, **Deferred**. A blocked/deferred task needs a reason and next action. Mark Completed only after its acceptance evidence is recorded; do not count this planning document as Task 1.1 completion.

**5 of 24 UI/UX tasks completed.**

| Task | Title | Phase | Status | Dependencies | Verification / completion notes |
| --- | --- | --- | --- | --- | --- |
| 1.1 | Comprehensive UI Component Audit | 1 | Completed | None | 2026-10-20: [Component audit](UI_UX_COMPONENT_AUDIT.md); 30 groups, 26 findings; source review only, browser follow-up documented. |
| 1.2 | Standardize Visual Design Tokens | 1 | Completed | 1.1 | Shared light/dark tokens, contrast regression tests and reference completed; 554 tests pass. Browser checks outstanding, explicitly documented in [token verification](UI_UX_DESIGN_TOKENS.md). |
| 1.3 | Standardize Shared UI Components | 1 | Completed | 1.1, 1.2 | Shared styling and form-footer conventions; 554 full-suite tests and 61 focused tests pass. Browser limitations/checklist in [component guide](UI_UX_SHARED_COMPONENTS.md). |
| 1.4 | Improve Interactive States | 1 | Completed | 1.2, 1.3 | 554 Django tests and 88 browser fixture assertions pass. See [interaction states](UI_UX_INTERACTION_STATES.md) for theme/keyboard evidence and manual limitations. |
| 2.1 | Refine Sidebar Navigation | 2 | Completed | 1.3, 1.4 | 557 Django tests and 336 sidebar browser assertions pass. See [sidebar reference](UI_UX_SIDEBAR_NAVIGATION.md) for behavior, themes and manual limits. |
| 2.2 | Improve Top Navigation and Tooltips | 2 | Not Started | 1.3, 1.4, 2.1 | Await explicit assignment; no implementation or task verification yet. |
| 2.3 | Responsive Layout Improvements | 2 | Not Started | 2.1, 2.2 | Await explicit assignment; no implementation or task verification yet. |
| 2.4 | Optimize Page Spacing and Content Density | 2 | Not Started | 1.2, 1.3, 2.3 | Await explicit assignment; no implementation or task verification yet. |
| 3.1 | Standardize Record Editors | 3 | Not Started | 1.3, 1.4, 2.3, 2.4 | Await explicit assignment; no implementation or task verification yet. |
| 3.2 | Improve Field Guidance and Validation | 3 | Not Started | 3.1 | Await explicit assignment; no implementation or task verification yet. |
| 3.3 | Clarify Draft Saving and Form Actions | 3 | Not Started | 3.1, 3.2, 1.4 | Await explicit assignment; no implementation or task verification yet. |
| 3.4 | Improve Record Tables and Controls | 3 | Not Started | 1.3, 2.2, 2.3, 2.4 | Await explicit assignment; no implementation or task verification yet. |
| 4.1 | Improve Schedule Generation and Management | 4 | Not Started | 3.1, 3.3, 3.4 | Await explicit assignment; no implementation or task verification yet. |
| 4.2 | Improve Timetable and Schedule Table Readability | 4 | Not Started | 1.3, 2.3, 3.4, 4.1 | Await explicit assignment; no implementation or task verification yet. |
| 4.3 | Improve Scheduling Navigation and Filtering | 4 | Not Started | 4.2, 2.2, 2.3 | Await explicit assignment; no implementation or task verification yet. |
| 4.4 | Clarify Conflicts and Publication States | 4 | Not Started | 4.1, 4.2, 4.3, 3.3 | Await explicit assignment; no implementation or task verification yet. |
| 5.1 | Improve Dashboard Information Hierarchy | 5 | Not Started | 1.3, 2.4, 4.4 | Await explicit assignment; no implementation or task verification yet. |
| 5.2 | Improve Room Analytics and Capacity Planning | 5 | Not Started | 3.4, 4.2, 4.3, 5.1 | Await explicit assignment; no implementation or task verification yet. |
| 5.3 | Improve Specialized Academic Interfaces | 5 | Not Started | 3.1, 3.2, 3.3, 3.4, 5.2 | Await explicit assignment; no implementation or task verification yet. |
| 5.4 | Standardize Feedback and Empty States | 5 | Not Started | 1.4, 4.4, 5.1, 5.2, 5.3 | Await explicit assignment; no implementation or task verification yet. |
| 6.1 | Accessibility Improvements | 6 | Not Started | 1.4, 2.1, 2.2, 3.2, 5.4 | Await explicit assignment; no implementation or task verification yet. |
| 6.2 | Responsive and Overflow Verification | 6 | Not Started | 2.3, 4.3, 5.4, 6.1 | Await explicit assignment; no implementation or task verification yet. |
| 6.3 | Role-Based UI Regression Testing | 6 | Not Started | 6.1, 6.2 | Await explicit assignment; no implementation or task verification yet. |
| 6.4 | Final Visual Consistency and Acceptance Review | 6 | Not Started | 6.3; all earlier tasks completed or explicitly dispositioned | Await explicit assignment; no implementation or task verification yet. |

## Original planning session and current handoff

The original planning session created only `UI_UX_MASTER_PLAN.md`; no template, CSS, JavaScript, view, form, model, migration, test or database changes. That initial architecture inspection was preliminary. Task 1.1 has now completed the source/documentation audit in `UI_UX_COMPONENT_AUDIT.md`; its browser follow-up remains explicitly documented.

Original planning acceptance checks: six phases, 24 uniquely numbered sequential task definitions, eight required planning fields per task, 24 matching Not Started tracker rows, actual referenced source paths, no application changes and Git whitespace checks. A full test run is unnecessary for documentation creation; baseline evidence is linked above rather than claimed as rerun.

For a future session: read this plan, inspect current Git changes, locate the explicitly assigned task, confirm its dependencies and source contracts, execute only that task, record evidence and update its row. **Tasks 1.1-1.4 and 2.1 are complete. Phase 2 is In Progress. Await separate approval/instructions before beginning Task 2.2.**

