# Central academic spreadsheet import

Apply migrations (`python manage.py migrate`) and open **Generate Schedule → Import Spreadsheet** as an administrator. No additional Python dependencies are required.

## Four guided steps

1. **Download Template**: choose Excel or CSV. Both contain two fictional SAMPLE rows for lecture/lab meetings. Replace all example values with your own information. Highlighted Excel headers are required on every row.
2. **Upload File**: drag in one file or browse for it, then choose the academic term. The selected filename and size are shown; you can replace or remove it.
3. **Review Data**: check column choices and choose how existing records are handled. Review the paginated spreadsheet, highlighted cells and module counts. Filter to rows with errors or download a CSV error report. Fix the original file and upload it again when needed.
4. **Confirm Import**: review the totals and approve any updates. The completion page shows added, updated and unchanged counts with links to the affected modules.

The searchable **Column guide and examples** groups columns by module and distinguishes required, optional and new-record details. Extra guidance is collapsed under **More Information**. Templates use one sheet to stay compatible with the existing parser; instructions are provided on the page instead of an extra worksheet.

No partial import is allowed. If errors exist, the ready count stays at zero until the entire file passes validation. Preview counts distinguish spreadsheet rows from records in individual modules. Large previews show 50 rows per page.

Choose **Keep existing records unchanged** to protect saved information. Choose **Update existing records with information from this file** only when you want to change it. Blank cells do not erase saved information.

After importing, review the records in their usual pages. Return to **Generate Schedule** when you are ready.

<details>
<summary>More Information: supported columns and import rules</summary>

## Supported columns and modules

| Module | Columns |
| --- | --- |
| Departments | `department_code`, `department_name` |
| Programs | `program_code`, `program_name` (linked to department) |
| Year levels / Sections | `year_level`, `year_label`, `section_code`, `section_size` |
| Courses | `course_code`, `course_description`, `units`, `lecture_hours`, `lab_hours`, `course_room_type` |
| Faculty | `assigned_faculty_id`, `faculty_name`, `faculty_max_hours` |
| Credentials | `faculty_credentials`, `course_credentials` (exact names separated by `|`) |
| Rooms | `room_name`, `room_type`, `room_capacity` |
| Assignments / meetings | `component`, `meeting_index`, `duration_minutes`, `meeting_room_type` plus selected term, section, course and assigned faculty |
| Availability | `availability_owner`, `availability_day`, `availability_start`, `availability_end`, `availability_kind` |
| Reference only | `reference_faculty`, `reference_room`, `reference_day`, `reference_start`, `reference_end` |

Required on every row: department code, program code, year level, section code, course code, assigned faculty ID, component, meeting index and duration. Other model-required attributes must be present when creating a new entity. Existing records can be referenced without repeating non-key attributes. Blank values never erase saved values. New courses/programs/faculty use the row's department; create cross-department faculty first and reference them with Skip if needed.

Identifiers match existing records exactly (section codes are normalized uppercase). Different case in course/program/employee codes can identify different records; use the canonical database identifiers. Consistent repeated records are processed once; conflicting repetitions are errors. Unique meeting keys use term, section, course, component and meeting index. Indexes must also be unique across components within each parent assignment.

## Formats

- `units`: nonnegative decimal, at most one decimal place. Hour fields: nonnegative whole numbers.
- Year level, section size, faculty maximum hours, room capacity, meeting index and duration: positive integers. A meeting cannot exceed the 07:00–19:00 school day (720 minutes).
- Room types: `LECTURE`, `COMPUTER_LAB`, `SCIENCE_LAB`, `GYM`, `SPECIAL`.
- Components: `LECTURE`, `LABORATORY`, `GENERAL`. For courses with lecture/lab hours, component totals must exactly match those weekly hours; use separate lecture/lab meetings. `GENERAL` is available only where explicit lecture/lab hours are both zero.
- Availability: owner `FACULTY` or `ROOM`; day Monday–Saturday or 0–5; start/end `HH:MM` within 07:00–19:00. Faculty supports `UNAVAILABLE`/`PREFERRED`; rooms support `AVAILABLE`/`UNAVAILABLE`, matching the existing GA. No availability is invented.
- Credentials are only created/linked when provided. Requirements use the existing exact/equivalent credential validator. No credential overrides are imported. Existing credential links are never removed.

Example: for a course with 2 lecture hours and 3 lab hours, use LECTURE meeting 1 for 120 minutes and LABORATORY meeting 2 for 180 minutes, with the appropriate meeting room type. To split lectures across days, use two 60-minute LECTURE rows with different indexes and a third LABORATORY row. Day choices are made later by the GA.

## Integrity and limits

- Preview simulates database changes in a rolled-back transaction. Confirmation revalidates everything and checks the preview fingerprint in the same transaction as saving. Critical errors roll back the entire import.
- Import requests require an authenticated administrator, CSRF protection and an owner-bound upload ID. Review links expire after two hours. Completed submissions cannot be applied twice.
- Limits: 5 MB uploaded file, 25 MB expanded XLSX contents, 500 ZIP entries, 1,000 data rows, 80 columns, 2,000 characters per cell. XLSX must have exactly one worksheet with row-1 headers, no merged cells, formulas, macros, external workbook links or XML entities. Dates/times must be text in the documented format, not Excel serial dates.
- Skip preserves existing database values and reports differences. Update changes only nonempty supplied values. Existing meetings used by schedules cannot be reassigned or resized through import; shared-record updates are checked against affected schedule entries.
- Generation-readiness issues such as missing suitable rooms or excessive faculty load appear as warnings, allowing administrators to complete/correct inputs in normal modules. The GA retains its own checks and may refuse generation until those issues are resolved.
- The existing schema has no separate Section Course Enrollment entity: Assignment is the term/section/course/faculty relationship, with individual TeachingAssignment meetings. This importer reuses that architecture and its uniqueness constraints.
- The academic term must already exist. This feature does not import students, accounts, credential equivalencies/overrides, GA parameter sets, or fixed day/time/room timetable placements. Explicit faculty mapping assigns a faculty member; the GA does not choose faculty. Source timetable values are retained in the owner-bound import payload for reference, never as schedule entries.
- Successful imports do not generate, approve or publish schedules. Import payloads are stored in `AcademicImport`; expiry blocks confirmation but does not automatically delete the stored payload.

## Verification

`python manage.py test schedules.test_academic_import` covers parsing, invalid/missing data, duplicate and repeated imports, relationships, lecture/lab totals, credential checks, preview rollback, stale confirmation, explicit update approval, permissions/CSRF, and actual GA generation from imported records.

</details>
