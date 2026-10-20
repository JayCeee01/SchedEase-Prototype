# Record editors - Task 3.1

## Audit before changes

Preserved all prior uncommitted Phase 2 changes. Generic `form.html` serves programs/departments, courses, sections, terms, faculty/students, rooms and availability, credentials and administration, plus specialized generation and schedule-entry flows. `assignment_form.html` separately renders parent fields and meeting formsets. Credential override confirmation and import workflows have distinct confirmation/staging semantics and retain their layouts.

Confirmed inconsistencies: generic and assignment page headings are duplicated; main editor forms have no accessible heading association; generic editors stretch to the full content width while their fields are single-column; read-only inputs have no dedicated presentation (disabled controls already do). Add/Edit titles already distinguish modes, so preserve those strings and use them in the shared header. Existing form.as_p, help/error markup, required attributes, field order and footer convention are correct and should be reused.

## Verification

In progress.
