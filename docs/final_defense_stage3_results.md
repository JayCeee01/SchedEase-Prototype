# Final-defense Stage 3 results

## COMPLETE (2026-11-04)

Both databases are at migration `0034_publication_membership` in `C:\Users\JEROME\SchedEase-Prototype`:

| Database | Published baseline | Assignment coverage | Entries | Validation issues |
| --- | --- | ---: | ---: | ---: |
| `tertiary_final_defense.sqlite3` | ID 1 | 64/64 | 128/128 | 0 |
| `shs_final_defense.sqlite3` | ID 1 | 33/33 | 33/33 patterns, 66 dated occurrences | 0 |

Tertiary baseline ID 1 was already PUBLISHED; it was retained without regeneration or republication. Read-only application validation found zero issues and all 64 assignments / 128 entries. Snapshot ID 1 and publication audit exist. Faculty/student dashboards rendered 8/12 authorized weekly cards respectively; administrator access and faculty/student denial of generation/publication passed using actual users with Django RequestFactory (no password decryption or login/session writes).

Root cause: the immutable v1 publication snapshot records weekdays, times and instructional components but omits `education_level`. The presentation adapter previously required that level to identify weekly recurrence. A narrow fallback now uses frozen LECTURE/LABORATORY weekdays and valid times when the frozen level and SHS binding are absent. The level remains unknown; no teaching dates or term bounds are inferred. Explicit SHS or malformed binding metadata never uses this fallback. Both dashboard grids show **Recurring Weekly Timetable** with a calendar-date disclaimer. Existing dated SHS selection, unknown-date lists, overlaps and authorization are preserved.

Changed application/test files:

- `schedules/services/timetable_presentation.py`
- `schedules/services/detail_timetable.py`
- `templates/schedules/student_timetable.html`
- `schedules/test_timetable_presentation.py`
- `schedules/test_student_timetable.py`
- `schedules/test_faculty_timetable.py`
- `schedules/test_student_date_timetable.py`

Focused regression selection: timetable presentation, student/faculty timetables, student/faculty date timetables, schedule visibility. Explicit SQLite `:memory:` default and test configuration: **48 passed, zero failures/errors/skips, 173.368 seconds**. Django checks reported no issues. Projection remains two queries for distinct 2/16-entry SHS/mixed batches. Syntax/whitespace checks passed. Evidence: `env/stage3-timetable-tests.log`.

SHS baseline generation succeeded on its first attempt through `generate_shs` with the actual administrator, lease, transactional preparation and immutable approval evidence workflow. Parameters: population 80, generations 120, mutation 0.08, crossover 0.85, elitism 4, seed 20261104. Recorded scheduler execution: 226.516 seconds, 120 evaluated generations, zero hard violations, soft score 680.2571428571428. This excludes adapter preparation and publication/verification time; the full operation took longer. Evidence: `env/stage3-shs.log` and `env/stage3-shs-results.json`. Publication used `publication.publish`, with snapshot ID 1, publication audit, complete membership and valid approval evidence verified afterward.

Actual SHS administrator dashboard/detail access passed. Faculty/student dashboards each rendered 3/6 authorized dated cards in both teaching weeks, with Monday-Friday columns and no unknown-date fallback. The live-demo student saw zero published cards. Faculty/student generation and publication actions were denied. These were real view/rendering checks with authenticated-user objects and RequestFactory, not a browser or password-login test. No browser visual inspection was performed. Stage 2 password authentication was not repeated and no credentials were decrypted.

Tertiary database SHA-256 remained `2a283af3bcab4fa178abfdd29ce25a4c864552cb74129169ec5508c95dccd50d`, preserving its existing finalized entries and snapshot byte-for-byte. Final SHS SHA-256: `4e95658c9178e9aa0d9834bd7d2c6c9d3d7aa257107bb3b9098959515850aa90`. Both databases passed SQLite integrity and foreign-key checks. All nine original database hashes matched the fresh Stage 2 inventory.

Live-demo academic-input fingerprints remained unchanged: tertiary 20 assignments / 40 meetings, SHS 11 configured assignments; both have zero schedules. Neither live-demo GA feasibility nor runtime was tested. Existing historical records were not rewritten. No Stage 4 exports, migrations, Git operations, Phase 5 work, credential changes, or GA/authorization/protection logic changes occurred. Only the authorized SHS baseline preparation, generation and publication wrote to a defense database.

Remaining limitations: legacy unknown/general or malformed SHS records retain their fallback list; no missing historical academic context is inferred. Browser layout checks and comprehensive export checks remain for separately authorized follow-up. Actual live-demo runtime should not be assumed from baseline results.
