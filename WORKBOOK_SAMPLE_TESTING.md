# Tertiary workbook sample testing

Source: `TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx`, sheet `TER SCHED 2T2526`.

The workbook was inspected before import. It contains 519 usable schedule rows: 9 program labels, year levels 1–4, 60 instructor labels, and 122 distinct room-cell values (including combined values such as `313/204`). Days use 32 notations, and times mix Excel fractions with text. The selected rows are **12, 13, 15, 16, 21, 22, 23, 26, 76, 77, 205, 210, and 341**. They cover ACT, BSCS, BSAIS, BSIT, BSCPE, and BSHM; years 1–3; seven instructors; lecture rooms, computer labs, a physics lab, a kitchen, and a PE area; and Monday–Saturday meetings.

## Mapping and explicit defaults

| Workbook | SchedEase | Handling |
|---|---|---|
| Section | Program, YearLevel, Section | Parsed as program + year + section number |
| Course Code/Description | Subject | `(LAB)`/`(LEC)` suffix normalized; source code retained |
| Units | Subject.units | Retained where present; zero/missing values remain zero |
| Day/Start/End | Availability preference | Excel fractions and text times parsed; actual meeting becomes a faculty preference |
| Room | Room | Source name retained; type inferred from `CL`, `PHYLAB`, `PEA`, `KITCHEN`, or lecture-room naming |
| Instructor | Faculty | Uppercase source label retained; `XLS-...` test employee ID added |
| Remarks | No current field | Read but not imported; visible in the source workbook |

The workbook has no section sizes, room capacities, faculty availability rules, or credentials. Test defaults are therefore explicit: section size 30; capacities 45 lecture, 40 computer lab, 35 science lab, 60 gym, and 30 specialized room. A `TEST-<course code>` credential is required and granted only to the source instructor. These credentials are synthetic and make no real-world qualification claim.

The current model supports one room type and one contiguous whole-hour GA block per subject/section. Paired lecture/lab rows are aggregated, specialized room type wins, and fractional weekly hours round upward. This is suitable for exercising the existing GA but cannot reproduce the workbook timetable exactly.

## Safe use

The command is dry-run by default and never updates existing matching records:

```powershell
.\.venv\Scripts\python.exe manage.py import_tertiary_sample "C:\Users\JED\Downloads\TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx"
```

Use an isolated SQLite database for a committed test:

```powershell
$env:SCHED_EASE_DATABASE_URL="sqlite:///tertiary_sample.sqlite3"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py import_tertiary_sample "C:\Users\JED\Downloads\TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx" --commit
```

Delete `tertiary_sample.sqlite3` afterward if it is no longer needed. Do not use `--commit` against production.

## Test result (seed 2526)

The isolated import created 9 assignments, 8 subjects, 7 sections, 7 faculty records, and 12 rooms. The existing GA generated all 9 entries with fitness **942.5**. Independent `full_clean()` validation passed every entry, and `conflict_messages()` reported no faculty, room, or section overlaps. All entries were Monday–Saturday between 7:00 AM and 9:00 PM, used sufficient-capacity rooms of the required type, and had the synthetic test credential. Three entries matched a workbook-derived faculty preference.

The existing automated suite also passed (13 tests). It directly covers room capacity, faculty unavailability, room type generation, credential qualification/override, and capacity-fit optimization.

### Existing constraint gaps found

- `Room` availability records are not consulted by `GeneticScheduler.fitness()` or `validate_entry()`. Room conflicts between generated classes are enforced, but a class can currently be placed outside a room's declared availability.
- `Faculty.max_weekly_hours` is not consulted by the GA or manual-entry validator.
- GA hard constraints are large fitness penalties, not a final feasibility gate. This sample passed a separate final validation, but generation could persist an infeasible best candidate for a more constrained dataset.
- The balanced-schedule goal considers per-day class counts and idle gaps. The room-utilization goal considers capacity fit, distribution of used hours, and unused suitable rooms. It does not optimize against actual room-availability hours during generation.

These findings were not bypassed or weakened to make this sample succeed.

## Full workbook import

For comprehensive testing, use the newer `import_tertiary_full` command. It reads every worksheet for analysis and imports every usable relational row from `TER SCHED 2T2526`, the workbook's complete normalized table. `SCHED_REGISTRAR` is a print-layout cross-check: most rows rely on blank/merged carry-forward values and cannot independently establish section and faculty relationships.

```powershell
$env:SCHED_EASE_DATABASE_URL="sqlite:///tertiary_full_test.sqlite3"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py import_tertiary_full "C:\Users\JED\Downloads\TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx" --report-dir full_workbook_report --commit
```

The command is dry-run without `--commit`, is deterministic/idempotent, preserves the original timetable as **Imported Original Tertiary Schedule**, and labels GA results as **SchedEase Generated**. Reports include workbook/sheet analysis, every normalization, rejected questionable rows, duplicate signatures, original conflicts, and per-room utilization.

The analyzed workbook produced 721 meetings from 517 of 519 normalized source rows: 9 programs, all 4 year levels, 63 sections, 125 subjects, 60 faculty labels, and 39 normalized rooms. Rows 156 and 516 were rejected because each supplies multiple rooms/times for only one day, so associating them would require silently inventing an occurrence. The original schedule produced 111 findings: 59 room conflicts, 50 faculty conflicts, 1 section conflict, and 1 class outside the allowed hours. No credentials were created because the workbook contains no qualification evidence; subjects without requirements remain eligible under the existing credential rules.

The workbook provides neither capacities nor availability. Imported sections therefore use test size 30; inferred room types use documented test capacities (lecture 45, computer lab 40, science lab 35, gym 60, specialized 30); and rooms are available Monday–Saturday, 7:00 AM–9:00 PM. Each faculty member's test maximum is the larger of 24 hours or their derived spreadsheet workload, so the importer does not reject the workload it is meant to reproduce. These are explicitly test/derived values, not claims about the institution.

On the imported original schedule, all 39 rooms were used. Average weekly utilization was 41.0%; 15 rooms were underutilized and 2 highly utilized. `CL2` was highest at 78.6% (66 scheduled hours, 22 classes), while `206` was the least-used active room at 1.8% (1.5 hours, 1 class). Full per-room results are in `full_workbook_report/room_utilization.json`.

A deterministic full GA trial (seed 2526, population 30, 60 generations) completed in about 63 seconds but retained faculty, room, and section conflicts. The feasibility gate correctly rolled the generated schedule back rather than saving an invalid result. This demonstrates a real scalability/convergence limit of the existing GA on 721 meetings; constraints were not weakened.

The complete machine-readable deliverables are in `full_workbook_report/`: `analysis.json`, `import_summary.json`, `data_quality.json`, `normalizations.csv`, `rejected_rows.json`, `duplicate_signatures.json`, `original_conflicts.json`, `room_utilization.json`, and `schedule_comparison.json`. The comparison includes every unscheduled requirement and its source key. Regenerate it with:

```powershell
.\.venv\Scripts\python.exe manage.py compare_tertiary_schedules --failure-reason "Describe the latest full GA outcome"
```

Small-sample subjects use the `SMP-` namespace so synthetic `TEST-` credential requirements cannot contaminate the canonical full-workbook subjects.
