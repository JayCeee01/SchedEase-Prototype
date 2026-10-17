# Task 3.1: finalized schedule protection

## Confirmed audit findings (before implementation)

- Published/archived entry editing is blocked in views, but Schedule and ScheduleEntry model saves, admin, QuerySet.update/bulk_update, and bulk creation bypass those view checks.
- H1 guards parent shared-field saves when any schedule references a meeting. Bulk updates bypass that guard; child duration/component edits are not frozen.
- Timetables render live Subject, Faculty, Section, Program, YearLevel, Department and Room records, including entry overrides. Renaming or reassigning these records changes finalized content.
- Schedule deletion cascades to entries and edit audits. AcademicTerm deletion can reach schedules; ordinary term-field editing is explicitly outside Task 3.1.
- Existing PROTECT foreign keys help deletion but do not prevent updates, entry reassignment, schedule status reversal, or removal of edit audit history.
- Spreadsheet imports validate current feasibility but can still change protected labels or otherwise-valid requirements.
- Publication archives a previous official schedule; this deliberate transition must remain possible without unlocking its content.
