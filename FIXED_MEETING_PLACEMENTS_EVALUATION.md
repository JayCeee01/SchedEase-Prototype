# Fixed meeting placements evaluation (Task 7.2)

## Decision and scope

**Outcome D — Academic clarification required.** SchedEase does not currently support meeting-level fixed day, time or room requirements for GA generation. Available repository documents do not establish an approved requirement defining this behavior. Defer implementation until the academic head, scheduling administrator or thesis adviser confirms the need and rules below.

This evaluation determines existing support and implementation impact. Missing fixed placements are an unconfirmed feature gap, not a demonstrated defect against approved requirements. It would be premature to declare either that current functionality satisfies every institutional need or that fixed placements are outside the approved thesis scope.

Task 7.2 changes documentation only. No models, migrations, dependencies, UI, validation, genetic operators or tests were changed. Existing uncommitted Task 7.1 documentation and its decision are preserved.

## Definitions

| Concept | Meaning in this evaluation |
|---|---|
| Manual placement | An administrator sets a day, time and room on an entry in a particular schedule. This does not instruct a later GA run to retain them. |
| Fixed placement | A mandatory meeting-level requirement to preserve one or more attributes, such as day, start time or a specific room, throughout generation. Partial and complete locks are possibilities requiring approval, not existing features. |
| Resource availability | Allowed/prohibited windows for a faculty member or room shared by all affected meetings. A preference is a soft objective, not a mandatory placement. |
| Finalized protection | Protection of published/archived records and historical snapshots. It does not constrain choices in a new GA-generated draft. |

## Architecture and evidence inspected

- `schedules/models.py` and existing migrations: `Assignment` stores shared term, course, faculty and section relationships. `TeachingAssignment` represents a meeting with component, duration, meeting index and optional required room **type**. Neither stores fixed placement attributes.
- `ScheduleEntry` stores the actual `day`, `start_time`, `end_time` and `room` for one schedule, plus supported academic overrides. A room type requirement is not a designated room. `Availability` stores resource periods; `ScheduleSnapshot` preserves historical content. Credential overrides concern qualifications, not permission to violate placement constraints.
- `schedules/forms.py`, `views.py`, `urls.py`, `templates/schedules/form.html` and `schedule_detail.html`: generation accepts term, settings, name and optional seed. Manual entry forms expose placement fields and signed revisions. Existing actions include correction suggestions and Copy to Draft; there is no pin/unpin control or source-draft input to generation.
- Services reviewed: `ga.py`, `placements.py`, `repair.py`, `availability.py`, `meetings.py`, `conflicts.py`, `manual_edits.py`, `corrections.py`, `publication.py` and `reproducibility.py`; spreadsheet handling in `schedules/importers/academic.py`.
- Tests reviewed include `test_ga_placements`, `test_ga_repair`, `test_availability`, `test_corrections` and `test_copy_remove`. The complete suite also covers finalized protection, historical snapshots, transactional edits, import behavior, permissions, diagnostics and reproducibility.

## Existing support and gap analysis

| Capability | Existing support and timing | Evidence | Gap / recommendation |
|---|---|---|---|
| Manual day/time/room placement and draft editing | Supported after generation or when manually building a schedule | `ScheduleEntry`, `ScheduleEntryForm`, `save_manual_entry`; manual editing views/forms | Use for corrections to a specific schedule. No persistence guarantee for a new GA run. |
| Conflict-aware suggestions | Supported during manual editing | `placement_suggestions`, `apply_suggestion`; `test_corrections` | Suggestions revalidate current constraints and save transactionally. Applying one does not create a fixed requirement. |
| Faculty availability | Supported before generation, during candidate evaluation and manual/final validation | `Availability`, shared availability policy, `individual_entry_errors`; `test_availability` | Resource-wide limits do not express a single meeting's fixed placement. Retain current policy. |
| Room availability | Supported at the same stages | Same shared policy and feasible placements; explicit-unlisted-day and inactive-room tests | Do not narrow a shared room's availability merely to emulate a meeting pin. |
| Preferences | Faculty preferred periods supported as GA soft preferences | GA `_preferred`, availability policy; preference tests | Room preferred periods do not have an equivalent GA soft reward. Neither preference is a mandatory pin; no new preference feature is proposed. |
| Feasible placement filtering | Supported during GA search | `feasible_placements`, `placement_options`; `test_ga_placements` | Filters current constraints, but has no fixed day/time/room predicate. |
| Targeted repair | Supported during GA search | `repair_candidate`, GA `_repair`; `test_ga_repair` | It may move affected meetings. Leaving unaffected genes alone within one repair call is not a permanent user lock. |
| Copy to Draft | Supported after finalization | `copy_to_draft`, copy view/action; `test_copy_preserves_fields_with_independent_entry_identities` | Copies placements to independent entries while sharing academic definitions. This is a manual draft copy, not GA regeneration or pinning. |
| New generation / regeneration | New runs supported | `generate_schedule`, `GeneticScheduler`; generation form | Reads term meeting requirements, not a selected schedule's entries. Prior schedules remain intact, but new placements may differ. |
| Fixed meeting day/time | Missing; requirement unconfirmed | No fields on `TeachingAssignment`, no filter in placement construction | Clarify partial locks, time semantics and scope before implementation. |
| Fixed specific room | Missing; requirement unconfirmed | Room type requirements only; chosen room belongs to `ScheduleEntry` | Clarify whether designated laboratories require an exact room or just an existing type. |
| Fixed attributes across regeneration | Missing; requirement unconfirmed | Generation has no source schedule/pin input | Define persistence and inheritance before promising this behavior. |
| Finalized schedule protection | Supported after publication/archive | Publication validation, model guards and snapshots; finalized/snapshot tests | Preserve these protections. They solve historical integrity, not partial preallocation during generation. |

### Current availability and academic validation

Explicit AVAILABLE periods restrict a resource to those windows, including closing unlisted days. Without explicit available windows, the default is the operating window. UNAVAILABLE intervals are subtracted; full meeting duration must fit. Preferred windows do not close other times. Inactive rooms are rejected. Faculty preference scoring is subordinate to hard constraints.

Placement and manual validation also retain faculty eligibility, academic-term consistency, room capacity/type, lecture/laboratory requirements, duration, operating hours and faculty/section/room conflict checks. Faculty is assigned through the academic meeting definition; the GA does not choose a new faculty member. Spreadsheet reference faculty is not automatically that assignment.

### Practical administrative outcome

Administrators can generate a schedule, inspect conflicts, adjust individual placements, apply validated suggestions and publish after validation. Copy to Draft preserves a finalized source and its history while providing separately editable entries. Signed revision checks, administrator authorization, transactions and audits protect manual saves.

These workflows support post-generation control. They do **not** let an administrator preallocate selected meetings and ask the GA to schedule everything else while guaranteeing preservation of those allocations. Repeated seeds can reproduce results under equivalent conditions; a seed is not a fixed-placement rule.

## GA compatibility and potential implementation impact

The existing architecture offers reusable domains and shared validation, so a bounded meeting-level constraint could plausibly fit it. That is an architectural assessment, not proof that a complete feature would be small. Persistence, scope and administrative policy must be settled first.

| Stage | Current behavior | Impact if fixed placements are approved |
|---|---|---|
| Candidate construction | `feasible_placements` filters active/suitable rooms, qualification, availability and full-duration windows; `placement_options` caches domains | Intersect ordinary feasible domains with authoritative fixed attributes. Never treat a pin as an exemption from academic rules. Empty intersections need understandable diagnostics. |
| Initial population | Chooses from domains, preferring nonconflicting occupancy | Respect constrained domains and consider their occupancy when placing other meetings. A one-choice domain alone does not ensure global feasibility. |
| Crossover | Checks inherited candidates against domains and occupancy, replacing when necessary | Every inherited or replacement gene must retain approved fixed attributes. |
| Mutation | May replace any gene from its meeting's domain | Restrict only approved attributes; mutations must never silently release them. |
| Targeted repair | Moves affected genes within domains to reduce hard violations | Preserve fixed attributes while repairing movable choices. Irreconcilable fixed conflicts must fail rather than be silently moved. |
| Hard evaluation | Evaluates current individual and shared-resource constraints | Recognize fixed-attribute violations, including candidates supplied outside normal construction. |
| Final validation | Saves candidates transactionally and validates current data before success | Shared validation must enforce the same rule for GA, manual editing and publication; recheck current fixed requirements. |
| Failure diagnostics | Structured errors include empty domains and unresolved conflicts | Identify the relevant meeting and incompatible fixed requirement without exposing privileged details to other roles. |
| Reproducibility | Versioned canonical inputs include meetings, rooms, availability, eligibility and effective settings | Include fixed requirements in change-sensitive input fingerprints and summaries. Existing `schedease-inputs-v1` has no such input. Preserve historical metadata compatibility. |
| Concurrency and regeneration | Database leases protect generation; each run creates a new schedule | Define which requirements a run reads and how changes invalidate prepared input. Preserve leases, transactional rollback and stale-owner protections. |

Two fixed meetings can conflict even when each has a nonempty individual domain. A fixed room may become inactive, unavailable, too small or unsuitable for a laboratory; a time may violate availability, operating hours or required duration. Fixed allocations can also leave no joint solution for remaining meetings. All such cases must retain hard-first validation and explicit failure; permission to create a fixed request must not imply permission to bypass constraints.

## Thesis-scope evidence

- `SYSTEM_AUDIT.md` recommends adding fixed/preassigned meeting locks and explicitly distinguishes them from published-schedule locking. This is an enhancement recommendation, not evidence of institutional approval or a complete policy.
- `GA_PLACEMENTS.md` explicitly states that the current GA model has no separate fixed-placement fields and does not infer them from spreadsheet references.
- `ACADEMIC_IMPORT.md` and the importer describe day/time/room reference columns as reference data, not fixed timetable constraints or saved schedule entries. Explicit faculty mapping can establish academic assignment relationships; reference faculty alone does not.
- `REPRESENTATIVE_SAMPLE_REPORT.md` documents sample/reference data, not an authoritative policy requiring those source placements. Sample values cannot establish mandatory constraints.
- README and implementation/evaluation documents describe manual control, availability and finalized protection. The available repository documentation did not supply an approved thesis specification requiring fixed attributes, their granularity or their behavior across runs. Task 7.1's separate curriculum decision is unchanged.

This finding is limited to documents available in the repository and the supplied task. Absence of an approved specification here does not prove the feature is excluded from an externally approved thesis or school practice.

## Academic clarification questions

1. Which approved thesis requirement or institutional rule requires preassigned meetings? Provide a concrete example that manual post-generation editing cannot adequately handle.
2. Which attributes must be fixed: day, start time, full interval, exact room, or combinations? Does a designated laboratory mean an exact room or an existing room type?
3. Are faculty-requested times mandatory or preferred? Who approves a mandatory request?
4. Do constraints belong to a term meeting, a particular draft, or a reusable template? Should they carry into new runs and Copy to Draft? How are they released?
5. Are requirements weekly recurring, as the current day-based timetable models, or date-specific events requiring a different representation?
6. Who may create, edit and remove fixed requirements, and what justification/audit history is required? How should an ordinary manual move interact with a pin?
7. When fixed requests conflict or become invalid after resource/credential/requirement changes, should generation stop for correction or offer explicitly authorized release? Existing academic validation must remain enforced.

After confirmation, agree on a bounded design and acceptance tests covering every applicable GA stage, direct/manual validation, regeneration, permissions, audit, metadata and impossible combinations. Do not add a UI that appears to guarantee preservation before those paths enforce it.

## Verification

Environment: existing `.venv`, Python 3.12.10, Django 5.0.6. Commands use `.\.venv\Scripts\python.exe` without requiring shell activation.

| Command | Result |
|---|---|
| `python manage.py test schedules.test_ga_placements schedules.test_ga_repair schedules.test_availability schedules.test_corrections schedules.test_copy_remove --noinput` | 83 passed in 24.969 seconds; no failures, skips or expected failures. |
| `python manage.py test --noinput` | All 496 passed in 278.192 seconds; 0 failures/errors, 0 skipped, 0 expected failures, 0 unexpected successes. |
| `python manage.py check` | Passed; no issues, none silenced. |
| `python manage.py makemigrations --check --dry-run` | Passed; no changes detected. |
| `git diff --check` | Passed. Git reports only its existing Windows LF-to-CRLF conversion notice for README. |

No feature tests were added for unsupported behavior. The focused tests verify existing behavior, not a nonexistent fixed-placement guarantee. Tests use their test database; no data migrations or production-record edits were performed. No browser walkthrough or external institutional validation was performed. Only this evaluation and a README reference are Task 7.2 changes.
