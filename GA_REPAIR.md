# Task 4.3: targeted candidate repair

## Strategy and integration

Individual feasible placements can still overlap after initialization or crossover. The GA now repairs completed initial candidates and offspring after mutation (including offspring whose mutation changes nothing). Crossover's existing inheritance checks remain intact. There is one repair pass per new candidate, avoiding a separate redundant pass between crossover and mutation.

`services/repair.py` identifies faculty, section and room overlap pairs by chromosome index. Fitness uses the same overlap detector with the previous per-resource counting semantics. Individual invalidity is reported separately using the shared entry validator; cached feasible-domain members need no repeated individual validation.

Repair freezes initially unaffected genes, randomizes affected-meeting order, and traverses each meeting's Task 4.2 options from a seeded random starting point/direction. Alternatives are evaluated against the complete chromosome. A move must strictly reduce hard violations and introduce no new overlap pairs. Equal-hard moves are rejected regardless of soft score. Meeting identity, faculty, course, component and duration remain those of the original assignment and its validated options.

The default budget is 64 evaluated alternatives per candidate. Developers can configure `GeneticScheduler(..., repair_budget=64)`; zero disables relocation. Each alternative is tried at most once for a particular candidate state. Accepted moves strictly reduce hard violations; retries after a move evaluate a different state. Domain scans also terminate when exhausted. Feasible candidates use no repair randomness or alternative search.

## Diagnostics and safeguards

`last_repair` records status (`unchanged`, `repaired`, `partial`, `unresolved`), hard counts before/after, attempts, accepted moves, remaining affected indexes and individual validation errors. `repair_statistics` aggregates status counts, attempts and moves for the run, and resets on `generate()`. These are in-memory developer diagnostics, not persisted error records or UI changes.

Unrepairable or budget-limited candidates retain the best state reached for normal GA selection. An individual error not counted by the existing fitness policy (for example a malformed externally supplied duration) is reported as unresolved rather than silently declared repaired. Repair does not redesign fitness to handle malformed chromosomes. Normal operators preserve meeting identities and durations; existing final output guards and full database validation remain authoritative.

Task 4.1 ranking, generation limits, Task 4.2 domains, transactional persistence and finalized-schedule protections are unchanged. No dependency or migration is added.

## Measured comparison

The deterministic regression fixture has two 60-minute meetings sharing a faculty, section and room. Both initially occupy Monday 08:00-09:00, creating three resource violations per candidate. Each unchanged input is compared with its repaired version, with seeds 0 through 19 and warm feasible-domain caches.

| Metric | Before repair | After repair |
|---|---:|---:|
| Candidates | 20 | 20 |
| Total hard violations | 60 | 0 |
| Infeasible candidates | 20 | 0 |
| Successfully repaired | 0 | 20 |

Repair evaluated 20 alternatives total. Measured repair-only runtime was approximately 0.003 seconds across all 20 candidates; domain building and scheduler construction are excluded. This deliberately easy fixture demonstrates conflict reduction, not general performance or production scalability. The test prints runtime on each run.

## Limitations

This is bounded single-meeting local search. It cannot cross equal-hard plateaus, swap two meetings atomically, or guarantee discovery of an existing feasible schedule. Rejecting newly introduced overlap pairs and freezing unaffected genes intentionally limits its search. Larger datasets incur domain-building, whole-candidate evaluation and fitness-cache costs; the attempt budget is not a wall-clock deadline. Cached inputs can become stale; fresh final validation still rejects changed data. Generation locking and structured errors remain deferred to Tasks 4.4 and 4.5.

## Regression coverage

`python manage.py test schedules.test_ga_repair` covers resource-specific detection, affected indexes, individual errors, strict reduction, simultaneous conflicts, preserved input/unaffected genes, equal/worse/new-conflict rejection, durations/components, budget exhaustion, partial and unresolved results, empty domains, reproducibility/diversity, operator integration and final rejection. Existing GA fitness/domain tests and Phase 3 protection tests remain unchanged.

## Verification

Verified with the existing Python 3.12.10 / Django 5.0.6 virtual environment:

- Full suite: 308 passed (287 existing plus 21 new), 166.141 seconds; no failures, skips, expected failures or unexpected successes.
- New repair suite: 21 passed.
- Combined fitness, placements, known defects, finalized protection, term protection, snapshots and initial repair suite: 105 passed; the subsequent full run includes all four additional repair tests.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed (Git notes the existing Windows line-ending conversion for README).

Existing tests intentionally log mocked save/publication/generation exceptions; these are successful failure-path tests, not suite failures. No existing tests were edited or weakened.
