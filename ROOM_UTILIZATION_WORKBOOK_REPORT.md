# Room utilization workbook implementation report

Reference workbook (read-only): `Main Template - Class Schedule and Faculty Count Projection_SY 25-26.xlsm`.

## Sheets analyzed

- `Room Utilization Efficiency`: lecture/laboratory separation, Monday-Saturday percentages, weekly averages.
- `Room Schedule`: room selector, 30-minute rows, Monday-Saturday columns, occupied and vacant periods.
- `5 - Computer Lab`: operating hours × days × laboratory count and program/year laboratory demand.
- `6 - Culinary Lab `: simultaneous-session capacity and weekly culinary laboratory demand.
- `7 - Classroom Calculator`: enrollment, target class size, sections, subjects, hours, operating capacity, and rooms needed.
- `MONDAY` through `SATURDAY`: 30-minute room grids and the source calculations used by utilization summaries.
- Section projection and tertiary schedule sheets were inspected as supporting sources for calculator relationships.

## SchedEase implementation

Room Utilization now calculates each day's scheduled hours divided by that room's actual available hours. Weekly utilization is total scheduled hours divided by total available hours, rather than an unweighted average of daily percentages. It separates time utilization from average seat utilization and supports lecture/laboratory grouping, academic term, schedule version, room type, room, day, department, status, search, sorting, CSV, and PDF.

Room Schedule is a separate administrator page with a room and schedule selector and a 30-minute Monday-Saturday grid. Cells distinguish scheduled, available/vacant, and unavailable time.

Room Capacity Planning is separate from utilization. It provides a workbook-inspired lecture-room assumptions calculator and a reusable actual-data table for every SchedEase room type, including computer and specialized/culinary laboratories. Calculations compare required teaching-assignment hours with actual available room hours and report estimated utilization, rooms needed, and surplus/shortage.

No database migration or Excel runtime dependency was introduced. Existing rooms, availability, sections, academic terms, schedules, and teaching assignments are reused. The Genetic Algorithm and all hard/soft constraint logic were left unchanged.

## Intentional differences

- Excel macros, named-range helper formulas, print formatting, and manual `VACANT` text are not copied. SchedEase derives these values from its database.
- Future enrollment and subject-load assumptions are not saved automatically; they remain clearly labeled planning inputs and do not alter academic records.
- SchedEase supports all configured specialized room types rather than hard-coding only the workbook's computer and culinary categories.
- Charts were omitted because summary cards and daily tables communicate the current data directly without decorative duplication.
