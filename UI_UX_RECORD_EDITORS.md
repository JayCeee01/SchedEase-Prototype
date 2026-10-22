# Record editors - Task 3.1

## Audit before changes

Preserved all prior uncommitted Phase 2 changes. Generic `form.html` serves programs/departments, courses, sections, terms, faculty/students, rooms and availability, credentials and administration, plus specialized generation and schedule-entry flows. `assignment_form.html` separately renders parent fields and meeting formsets. Credential override confirmation and import workflows have distinct confirmation/staging semantics and retain their layouts.

Confirmed inconsistencies: generic and assignment page headings are duplicated; main editor forms have no accessible heading association; generic editors stretch to the full content width while their fields are single-column; read-only inputs have no dedicated presentation (disabled controls already do). Add/Edit titles already distinguish modes, so preserve those strings and use them in the shared header. Existing form.as_p, help/error markup, required attributes, field order and footer convention are correct and should be reused.

## Recovered work and command decline

The resumed session found the shared heading include, editor containers, read-only styling, four Django tests and rendered-editor fixtures already preserved. The only initial working-tree change was the unrelated sample database; it was not touched.

The earlier browser command was rejected because automatic approval review could not complete after the usage limit was reached. It was not a finding that the command was unsafe, a missing dependency, a PowerShell error or an application failure. The existing virtual environment and browser runner were available. The normal approval workflow accepted the resumed command, and verification completed without bypassing approval.

Prior partial browser runs had passed layout checks but did not constitute complete verification. A previously corrected fixture assertion now waits for the existing disabled-color transition; no production behavior was changed for that assertion.

## Shared conventions

- `_editor_heading.html` supplies the existing title/description and a Create/Edit context label. Existing titles and descriptions remain intact. Both generic and assignment forms reference the heading with `aria-labelledby`.
- `.record-editor` keeps heading, draft notices, form and actions aligned. Ordinary single-column editors are bounded at 56rem and shrink to available width. Assignment meetings, generation and schedule-entry correction flows retain wider layouts.
- Existing `form.as_p`, field order, hidden identities, required attributes, help text and error markup are retained. No new field grouping changes the form-binding contract.
- Assignments retain parent fields, meeting tabs/fieldsets, management fields, deletion flags, Add/Remove controls and draft hooks. Existing `.toolbar.form-actions` and Save/Cancel destinations are unchanged.
- Read-only controls use semantic secondary text/surface colors and a dashed border while remaining focusable. Disabled controls retain their established palette and behavior. No new disabled or read-only application fields were introduced.
- Credential override confirmations, staged imports and generation-specific controls remain specialized exceptions. Field-guidance rewriting and draft-action semantics remain for Tasks 3.2/3.3.

## Module coverage

The shared template covers academic programs/departments, courses, sections, academic terms, faculty, students, rooms, faculty/room availability, credentials and administrative records. Browser fixtures exercise 12 create forms (programs, courses, sections, terms, faculty, students, rooms, availability, credentials, faculty credentials, overrides and assignments), room/term edit forms, and an invalid room submission.

## Verification results

- Completed full Django run: **561 passed in 307.500 seconds** (557 existing plus four new tests), zero failures, errors, skips or expected failures. Recovered from `ui31-tests.log`; no further application code changed on resumption, so the full suite was not repeated unnecessarily.
- Four focused `schedules.test_record_editors` tests rerun successfully: generic create/edit controls, invalid bound values/errors, assignment management fields and generation-specific actions.
- System check: no issues. Migration dry check: no changes. Git whitespace check: passed.
- Editor browser matrix: **1,120 assertions** (80 at each of seven widths in two themes). Widths: **1360, 1024, 901, 768, 621, 500, 390px**, height 768px.
- Shared interactions **88**, top navigation **208**, persistent table scrolling **92**, sidebar **336** (including reload persistence), and responsive layout **350** checks all passed.

### Separate theme results

Light Mode and Dark Mode each passed the full editor matrix: no page overflow, aligned headings/forms, fitting controls/actions, accessible heading names, retained invalid input, focus/Escape tooltip behavior and distinct read-only/disabled presentation. Representative Light desktop and Dark mobile screenshots were inspected. Existing palette, saved theme, focus styles and reduced-motion behavior are reused.

Fixtures are actual Django responses rendered through the test client against an isolated in-memory database with synthetic administrator records. The browser assembles those responses offline; this is not a live authenticated workflow. The invalid POST occurs only in that isolated database. Read-only/disabled browser probes temporarily set attributes on a fixture control without changing application data or field definitions.

```powershell
.\.venv\Scripts\python.exe tests/browser/render_responsive.py --editors
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --editors --screenshots
.\.venv\Scripts\python.exe manage.py test schedules.test_record_editors
```

## Files and remaining limitations

Implementation files recovered unchanged: `templates/schedules/_editor_heading.html`, `form.html`, `assignment_form.html`, `static/css/app.css`, `schedules/test_record_editors.py`, `tests/browser/render_responsive.py`, `run_interactions.py` and the rendered-editor fixture. The resumed session finishes this reference, master-plan status and browser evidence/screenshots.

Manual follow-up: live role-based create/save/edit workflows, populated assignment meetings and credential scenarios, physical touch, screen readers, zoom and Firefox/Safari. No screen-reader certification or live submission testing is claimed. No authentication, academic rules, autosave, publication logic, schema or real database changes. No commits or deployment.

## Final status

Task 3.1 Completed; Phase 3 In Progress; overall progress **9/24**. Task 3.2 remains Not Started. The resumed session changed only this reference and master-plan progress; temporary screenshots were inspected and removed. The unrelated database modification remains untouched.
