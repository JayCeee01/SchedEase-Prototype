# Task 4.1: hard constraints before soft preferences

## Root cause and comparison

The former fitness value was `1000 - weighted_hard_penalties - soft_penalties`. Hard penalties had fixed weights (150–300 per detected violation); soft costs grew with room capacity and schedule size. A feasible chromosome with a sufficiently poor soft score could therefore lose to an infeasible chromosome.

`GeneticScheduler.fitness()` now returns immutable `Fitness(hard_violations, soft_score)`. Higher fitness compares `(-hard_violations, soft_score)` lexicographically: fewer violations always win, and only equal counts compare preferences. There is no normalization or multiplier allowing preferences to cancel hard violations.

Existing detectors are unchanged. Each failing per-gene check contributes one violation: operating day/window, capacity, room type, qualification, faculty availability, and room availability. Every overlapping pair contributes one violation per shared faculty, section, or room. For example, two overlapping meetings sharing all three resources count as three violations. These are independent constraint failures, not unique human-readable issue messages; an out-of-hours placement can also fail availability checks. Former penalty weights no longer affect hard ranking. Existing soft rewards and penalties—including preferred times, capacity fit, distribution and room utilization—retain their formulas.

## Integration and tie handling

Population sorting, tournament selection, elites, generation winners and the best-so-far candidate all compare the same Fitness object. Stable sorting and max retain the earliest population member for equal scores. Tournament ties select the earliest sampled member's population rank, independent of draw order. Best-so-far changes only on a strict improvement. Fixed random seeds remain reproducible for the same ordered input data.

The existing fixed generation budget remains in force. Finding zero GA violations does not stop soft optimization early. There was no stagnation termination mechanism to update. Random placement generation, crossover, mutation, generation locking and concurrency are unchanged.

## Reporting and persistence

`scheduler.best_fitness` exposes separate hard and soft components. `scheduler.generation_statistics` records generation 0 (the initial population) and each completed generation, with separate `population_best` and `best_so_far` dictionaries containing `hard_violations` and `soft_score`. These statistics remain in memory for the run; no database schema change is needed.

The stored `Schedule.fitness_score` remains numeric and stores the soft preference score of a successfully validated result: `1000 - soft_penalties`. This matches the old formula for feasible results, so existing valid historical scores need no conversion. The success message explicitly reports zero hard violations and the soft preference score. Historical records and snapshots are not rewritten.

If the best candidate still has detected hard violations after the generation budget, generation raises a clear failure with both components before creating a schedule. The existing failed-run/error-log workflow handles it. It does not persist an invalid draft or report success.

## Validation boundary

Fitness is an optimization comparison, not a substitute for full schedule validation. Normal chromosomes retain one gene per meeting and required durations through the existing operators. Existing preflight checks, duplicate/reference guards and transactional final schedule validation remain authoritative, including course component totals, missing meetings, and current database constraints. A zero GA count can still fail full validation (for example, inconsistent academic input or data changed during a run); all provisional records then roll back.

The regression scenario uses a valid oversized-room placement with a poor soft score and an overlapping normal-room placement with a much better soft score. It asserts both that the former weighted formula would favor the overlap and that the new comparator always favors the feasible placement. Tests also cover equal hard counts, tournament ties, elitism, best-so-far preservation without elites, later feasible improvements, all-feasible/all-infeasible populations, final validation, cache structure, deterministic runs and user-facing success/failure reporting.

No candidate-placement search (Task 4.2) or targeted repair (Task 4.3) is introduced. Search is still stochastic and can exhaust its budget even when a feasible solution exists.
