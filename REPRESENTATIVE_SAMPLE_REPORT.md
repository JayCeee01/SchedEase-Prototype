# Representative tertiary workbook sample

Source workbook: `TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx`.

Both `SCHED_REGISTRAR` and `TER SCHED 2T2526` were inspected. `TER SCHED 2T2526` is the primary source because it provides the normalized section, course, units, day/time, room, instructor, and remarks columns. `SCHED_REGISTRAR` is retained as a print-layout cross-check but relies heavily on merged/carry-forward cells.

## Selected complete sections

- `ACT 1-201`
- `BSCS 3-201`
- `BSAIS 2-201`

These three sections produce 44 separate scheduling requirements from 34 source rows: 25 subjects, 17 faculty labels, and 22 source room identifiers. The requirements comprise 10 lecture meetings, 10 laboratory meetings, and 24 general meetings. Separate lecture/laboratory and repeated weekly meetings remain separate `TeachingAssignment` records; original days, times, and rooms are not forced onto the generated schedule.

## Provenance and mapping

| Classification | Values |
|---|---|
| SOURCE | Section, subject code/title, units, instructor, source room identifier, original meeting pattern, worksheet and row |
| DERIVED | Program and year parsed from section, duration from start/end, meeting count from multi-day rows, lecture/lab component, conservative room type |
| DEFAULT/TEST | Section size 30; capacities of 45 lecture, 40 computer lab, 35 science lab, 60 gym, 30 specialized; broad Monday-Saturday faculty/room availability from 7 AM-7 PM; `TEST-RSP-*` credentials |

`CL*` rooms are computer laboratories and `PEA*` is an activity/gym facility. Ordinary numbered rooms are lecture rooms. Synthetic capacities and credentials are explicitly labeled and are not claims about the institution. Original meeting times become preferences only, leaving the Genetic Algorithm free to create a new timetable.

The sample importer uses `RSP-` prefixes for rooms, subjects, and faculty identifiers plus a dedicated academic term, preventing collisions with older or canonical workbook data. It uses deterministic uniqueness keys, so rerunning it does not continually create records.

## Safe import

Dry run:

```powershell
.\.venv\Scripts\python.exe manage.py seed_tertiary_sample "C:\Users\JED\Downloads\TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx"
```

Isolated test database:

```powershell
$env:SCHED_EASE_DATABASE_URL="sqlite:///tertiary_sample.sqlite3"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_tertiary_sample "C:\Users\JED\Downloads\TERTIARY CLASS SCHEDULE_2T2526_for capstone_sapno.xlsx" --commit
```

Then sign in, select **Second Term - Representative Workbook Sample**, select **Representative Workbook Sample** GA settings, and generate a schedule. The source workbook is read-only and is never modified.

## Validation and generation result

The command inspected 519 normalized workbook rows. Two workbook-wide ambiguous rows were rejected by the shared parser rather than guessed; neither belongs to the selected sample. All 34 selected source rows were usable.

An isolated deterministic run (seed 2526, population 100, 180 generations) produced:

- Total requirements: 44
- Successfully scheduled: 44
- Unscheduled: 0
- Hard-constraint violations: 0
- Fitness score: 729.75
- Runtime: 35.702 seconds
- Average utilization across all 22 sample rooms: 5.7%
- Most utilized room: `RSP-CL3`, 10.4%
- Least utilized active room: `RSP-204`, 0% (unused)
- Least utilized room receiving a class: `RSP-405`, 2.8%

Low average utilization is expected because the sample deliberately retains the actual variety of rooms used by the three sections while containing only 44 requirements. The different utilization values still exercise used, unused, and underutilized-room reporting.
