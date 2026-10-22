# Task 5.2: faculty idle gaps and day distribution

## Confirmed weaknesses

The previous faculty calculation subtracted only hour fields and charged only
when that result exceeded one. It discarded minutes and treated short gaps as
free. Day spread counted only occupied days, so a week concentrated on one day
had zero spread.

## Corrected formulas

Faculty meetings are grouped by faculty and day, then sorted by start/end.
Maintain the latest occupied end, adding `max(0, next_start - latest_end)` in
minutes. This merges overlapping intervals and prevents nested meetings from
creating artificial gaps. Sum integer minutes before applying the weight:
`faculty penalty = total idle minutes * 4 / 60`.
There is no charge outside the first/last meeting or between different days.

Day spread remains `3 * (maximum count - minimum count)`, across the whole
candidate schedule. Counts include zero for every existing `ALLOWED_DAYS` day:
Monday through Saturday. Sunday is excluded. Faculty/room availability still
constrains placements; it does not redefine the school's instructional calendar.
No new calendar or resource availability policy was introduced.

| Example (isolated component) | Expected | Verified actual |
| --- | ---: | ---: |
| Adjacent faculty meetings | 0 | 0 |
| 30 idle minutes | 2 | 2 |
| 120 idle minutes | 8 | 8 |
| Two 30-minute gaps | 4 | 4 |
| Nested overlapping meetings | 0 | 0 |
| Six meetings, one on each instructional day | 0 | 0 |
| Six meetings, all on one instructional day | 18 | 18 |

These are component penalties, not complete fitness scores. Existing section
whole-hour gap penalties, daily load penalties, room penalties and preferred
period bonuses remain in place. The unchanged section preference can also
charge for a gap when the same section attends both meetings. Weights are
existing code constants, not new administrator settings.

Hard violations still outrank every soft preference. Initialization, mutation,
crossover, repair, leases, diagnostics and finalized schedule protections are
unchanged. Fitness metadata now identifies `hard-first-v2`, faculty minute units
and hourly weight, section-only legacy gap parameters, and all instructional
days used for distribution. Historical metadata is not rewritten. Identical
seeds are reproducible under the same inputs, settings and implementation;
schedules/scores need not match the previous formula version.

## Scope and limitations

This is the existing whole-schedule meeting-count spread, not a new per-faculty,
per-section or duration-weighted balancing policy. Section gap modernization is
outside Task 5.2. No dependencies, database changes or UI changes are required.

## Verification

Using the existing Python 3.12 virtual environment:

- New soft scoring + existing fitness + reproducibility modules: 55 passed.
- Placement, repair, generation lock, finalized protection, term protection and
  snapshot modules: 113 passed.
- Full `python manage.py test`: 394 passed in 214.601 seconds, comprising all
  378 previous tests and 16 new tests. Zero failures, errors, skips, expected
  failures or unexpected successes. No previous test assertions were changed.
- Fixed-seed placement/fitness and per-generation reproducibility tests passed.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.

The failure-path tests deliberately log exceptions; their assertions passed.
Existing uncommitted reproducibility documentation and sample database changes
were preserved. Task 5.3 was not started and no commit was created.
