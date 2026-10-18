# Task 4.2: feasible placement options

## Root cause

The former sampler selected a compatible room, then independently sampled a day and a 30-minute start. It did not check faculty/room availability before constructing the gene. Mutation repeated this process and crossover combined parents without considering newly introduced overlaps.

## Shared validation and individual options

`services/placements.py` builds a cached domain for each meeting. `individual_entry_errors()` is extracted from the existing entry validator; manual validation still calls the same rules and then performs its existing overlap/workload checks. The GA passes its existing run-local eligibility and availability caches to avoid querying the database for every option.

Domains respect active rooms, capacity, room type, qualification and matching credential overrides, faculty/room availability and unavailable periods, required component/duration, operating hours, and academic-term consistency. Existing meeting model validation also runs before building a domain. Faculty, section and course identities remain those of the assignment; the GA does not invent faculty assignments. There are no separate fixed-placement fields supported by the current GA model, so none are introduced or inferred from spreadsheet references.

Candidate starts include the existing 30-minute grid and the beginning/latest-fitting start of each common faculty/room availability interval. Boundary starts allow narrow windows such as 08:10–09:10. Every resulting option passes shared individual entry validation. Options are deduplicated and ordered before seeded sampling. Domains are finite and cached once per meeting/run; they are not a search over all schedule combinations.

## Genetic operators and diversity

- Initialization randomizes meeting order, then prioritizes smaller domains, preserving random order for equal sizes. A transient occupancy index tracks faculty, section and room by day. Selection starts at a random domain position and scans in a random direction, preferring a placement without conflicts. The chromosome is returned in original assignment order for compatibility with crossover.
- Crossover keeps the existing single split. When an inherited placement conflicts with the accepted prefix, it tries the other parent's placement for that same meeting. Unaffected genes remain unchanged. It does not search for repairs or revisit earlier placements. Invalid individual inherited options are replaced from the validated domain rather than silently accepted.
- Mutation selects a different domain option whenever one exists, preferring one that avoids the other current genes. Singleton domains terminate safely and retain their only option.
- If no conflict-free option fits a partial chromosome, operators may retain an individually feasible but conflicting option. Task 4.1's unchanged lexicographic fitness ranks these combinations. No globally invalid candidate is declared valid merely because all its individual placements are valid.

The random start/direction scan avoids copying and shuffling a complete domain on every choice. Occupancy checks inspect only matching resource/day buckets. Domain size and full scans can still be expensive for very large datasets; no broad runtime improvement is claimed.

## Failure and persistence

An empty individual domain stops generation before population construction, identifying the course, section, meeting number, faculty and relevant validation or availability reason. Existing preflight messages still cover globally missing rooms, credentials, excessive workloads and invalid durations. A nonempty set of individual domains can be jointly impossible; exhaustion remains a distinct generation-limit failure with hard/soft statistics.

Cached options are not approval to persist. Current full schedule validation remains inside the existing atomic save boundary, including completeness, workload, current availability and academic requirements. Changes to live data during a run still cause validation failure and rollback. Generation locking, error-record structure and publication/finalized-schedule protections are unchanged.

## Deterministic comparison

The regression fixture contains two 60-minute meetings, one compatible room and faculty/room availability only on Wednesday 08:00–10:00. For 100 chromosomes (200 genes), seed 17:

| Sampling | Individually invalid placements |
|---|---:|
| Former room/day/time sampler | 195 / 200 |
| Feasible-domain initialization | 0 / 200 |

Both counts use the existing hard checks for each gene. This is an individual-validity observation on one deliberately restricted fixture, not a timing benchmark or proof of globally conflict-free schedules. Randomized initialization/operator tests also verify repeatability and more than one chromosome when alternatives exist.

No targeted repair (Task 4.3), generation locking changes (Task 4.4), structured error redesign (Task 4.5), dependencies or migrations are introduced.

Task 4.3 subsequently adds bounded repair after initialization and offspring mutation. See [GA_REPAIR.md](GA_REPAIR.md); the placement rules described above remain unchanged.
