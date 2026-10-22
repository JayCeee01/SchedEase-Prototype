# SchedEase Thesis Development Plan

## Authority, scope and evidence

**Single active roadmap.** This plan supersedes the sequencing of the historical UI/UX plan; completed UI work is retained. T1 is planning/auditing only. T2-T16 require separate authorization. Audit date: 2026-10-21; branch: `development`.

Initial working tree: modified `UI_UX_MASTER_PLAN.md`, `UI_UX_RECORD_EDITORS.md` and `tertiary_sample.sqlite3`. Preserved all three; no database access, migrations, application edits, commits, pushes or deployment. Only this plan and a historical-roadmap notice in the existing UI plan are added by T1. No additional audit/progress document.

Evidence is focused source inspection plus existing test/documentation records, **not a fresh execution of those tests**. The most recent recorded full run is 561 passing Django tests in 307.500 seconds (`ui31-tests.log`, `UI_UX_RECORD_EDITORS.md`); it is a regression baseline, not proof of seven thesis outcomes. No full suite was run for this documentation-only task. Relevant code references below are relative to the repository root; symbols identify inspection locations without brittle line numbers.

Objective labels: **Verified** means the complete stated criterion has reproducible evidence; **Partially Verified** means implemented/tested portions exist but material gaps or acceptance evidence remain; **Missing** means no supporting implementation was found; **Not Yet Verified** means an outcome has not been demonstrated. Capability labels use Existing/Partial/Missing/Not Verified separately. Initial source audit alone certified no end-to-end objective; subsequent executed verification is recorded per task below.

## A. Original UI/UX progress (historical)

- Phase 1: **4/4 Completed**. Phase 2: **4/4 Completed**. Original baseline before editor confirmation: **8/24**.
- Task 3.1 is confirmed **Completed**, bringing historical UI/UX progress to **9/24** (Phase 3: 1/4). Evidence: shared `_editor_heading.html`, `form.html`, `assignment_form.html`, `.record-editor` CSS, four tests in `schedules/test_record_editors.py`, the completed 561-test log, and the recorded 1,120 editor-browser assertions in `UI_UX_RECORD_EDITORS.md`. The previously declined browser command was subsequently completed through normal approval.
- Original Task 3.2 and later tasks remain **Not Started**. Do not increment the original count when thesis tasks are completed. T15 will reassess which original UI tasks are essential; T16 will verify final usability rather than automatically crediting all remaining original tasks.

## Thesis objective audit

All service paths in this table are under `schedules/services/` unless otherwise stated.

| Objective / status | Existing implementation and what it actually does | GA involvement and missing requirements | Evidence needed for fulfillment |
| --- | --- | --- | --- |
| **O1: detect conflicts before finalization - Partially Verified** | `conflicts.py`: `individual_entry_errors`, `validate_entry`, `schedule_validation_issues`; `meetings.py` checks meeting requirements. Subjects are identified through course/meeting requirements and section/resource conflicts. `publication.py:publish` refuses validation issues before publishing under a transaction. `schedules/tests.py:test_publish_is_post_only_and_rejects_unscheduled_requirements`, `test_publish_runs_full_validation_and_succeeds_when_complete`; `test_admin_publication_security.py`, `test_finalized_protection.py`. | GA hard violations cover overlaps and invalid placements; final validation is separate from soft scoring. A subject code alone is not a resource that must never run concurrently: different sections may legitimately take it simultaneously. Missing requirements are detected against existing assignments, not necessarily an authoritative complete curriculum. | T2: documented subject-conflict meaning; matrix of teacher/section/room/time/meeting failures through manual, generation, import and publication paths, including invalid/incomplete schedules and boundary adjacency. Reconcile `CURRICULUM_COMPLETENESS_EVALUATION.md`; do not claim curriculum completeness from assignment coverage. |
| **O2: prevent instructor/room double-booking - Verified (current recurring-term model, SQLite)** | Shared `conflicts.py:validate_entry` checks effective instructor/room collisions locally and against published schedules in different overlapping terms. Manual saves and publication revalidate transactionally; GA final-save validation rolls back invalid output. | Existing GA optimization remains unchanged; final validation rejects external occupancy conflicts. Alternative drafts, archived schedules and same-term replacement versions do not consume external occupancy. | T3 complete: eight focused tests, real separate-connection edit/publication races, and 575 passing full-suite tests. Weekly recurrence is inferred from inclusive term dates; holidays/cancellations and other database engines are not certified. See T3 record below. |
| **O3: teacher/student availability - Verified (fixed-section model)** | Shared `AvailabilityPolicy` now supports administrator-managed section windows alongside faculty/room windows. Effective section validation covers manual overrides; faculty self-service cannot set section ownership. | Section constraints participate in GA domains, hard violations, repair and final-save revalidation; manual edits and publication use the same policy. No constraints retain existing school-hour defaults. | T4 completed: 12 new focused tests and 587 full-suite tests passed. Individual student constraints, term-specific windows and holiday exceptions are outside the current model. Migration 0016 must be applied to the working database before use; see T4 record. |
| **O4: significantly shorten preparation time - Not Yet Verified** | `reproducibility.py`, generation-run models, `schedules/benchmarks/`, `schedules/benchmark_reports/`, benchmark commands and `GA_BENCHMARKS.md`/`GA_EVALUATION_REPORTS.md` provide seeds, parameters, elapsed measurements and reports. Tests: `test_benchmarks.py`, `test_benchmark_reports.py`. | GA runtime can be measured. No documented matched manual preparation study establishing significant end-to-end improvement was located in the inspected evidence. Solver runtime excludes data preparation, corrections and final approval. | T11: matched workloads/quality, consented time recording, defined start/stop points, repetitions, hardware/version/seed/configuration, manual baseline and justified effect/significance analysis. Include failed/infeasible runs; never invent human timing data. |
| **O5: fair instructor load distribution - Partially Verified** | `models.py:Faculty.max_weekly_hours`; `ga.py` preflight totals assigned meeting minutes and rejects overload. `_distribution_penalty` scores faculty/section daily concentration, faculty idle gaps and section gaps. Tests: `test_ga_soft_scoring.py` and generation/preflight tests. | Faculty is fixed on the input meeting; `Gene` selects assignment/time/room, not a new teacher. Temporal spreading and maximum-hour enforcement are **not balancing total load between instructors**. The original timetable GA has no inter-instructor fairness objective. T8 now provides a separate administrator-approved allocation step using workload-percentage variance. | T8: approved utilization-based fairness and explicitly selected reassignment scope; implemented and tested feasible batch allocation without treating unequal teaching hours as unfair. Broader institutional effectiveness still requires representative evaluation. T6 workload presentation and the scoped T8 proposal workflow are complete. Representative institutional fairness effectiveness and broader scheduled-term allocation remain unverified; see T8 evidence below. |
| **O6: room utilization and requirements - Partially Verified** | `placements.py:feasible_placements`, `conflicts.py:individual_entry_errors` enforce active rooms, capacity, type and availability. `room_utilization.py` reports available/scheduled hours, seat metrics and planning assumptions. Tests: `test_room_availability_reporting.py`, `test_availability.py`, `test_ga_soft_scoring.py` and existing room checks. | `ga.py:fitness` penalizes excess capacity; `_room_utilization_penalty` discourages unused suitable rooms and uneven used-room hours. This heuristic is not proof of optimal use. Room model has name/type/capacity/active fields, **no department ownership/eligibility restriction**; department report filtering is not room-allocation enforcement. | T9 completed: retained existing shared-room policy, verified constraints and deterministic capacity-fit/distribution behavior, and corrected effective-section seat/department reporting. Controlled fixture improves seat occupancy 20% to 66.7% with room-time utilization unchanged at 50%. Representative institutional impact and consolidation-versus-spreading preferences remain unverified; no department-exclusive policy was introduced. |
| **O7: sudden changes with limited disruption - Partially Verified** | T10 `smart_repair.py`, `repair_rules.py`, administrator repair views; existing copy/manual transaction/publication safeguards. Twenty-two focused tests include multi-day rules, legacy compatibility, approved draft-entry overrides, recurring outages, new sections, atomic rejection and concurrent application. | Seven reproducible synthetic scenarios measured; weekly recurrence only, bounded search, SQLite application. No matched full-regeneration comparison or representative institutional effectiveness study. | T10 completed for the scoped workflow; see measurements and limitations below. T11 is Manual Evaluation Pending; no benchmarking implementation was authorized. |

## Faculty, Student and Administrator capability audit

Role/authentication evidence: `sched_ease/urls.py` includes Django authentication; `schedules/views.py:role`, `admin_required`, `faculty_required`, `visible_schedule`, `entries_visible_to_user`, `restrict_schedule_filter_choices`; `schedules/urls.py` exposes dashboard-related scheduling routes. `models.py` links users to Faculty/Student, and students to sections. `schedules/tests.py` contains personal timetable, own-section filtering, empty/unassigned access, effective overrides and role-menu tests; `test_diagnostic_access.py` and `test_admin_publication_security.py` cover restricted diagnostic/admin paths. Hiding navigation is not itself authorization.

| Role / capability | Status | Evidence / qualification |
| --- | --- | --- |
| Student authorized published timetable | Existing | `views.py:dashboard`, `browse_schedules`, `visible_schedule`; `student_dashboard.html`, `personal_timetable.html`. Filters published entries to the student's effective section; no assigned section yields no entries. Tests include `test_student_dashboard_shows_section_timetable`, `test_student_browse_only_shows_entries_for_own_section`, `test_student_empty_timetable_and_other_section_schedule_access`, `test_student_browse_respects_effective_section_overrides`. |
| Student subjects, rooms, times, faculty | Existing | `personal_timetable.html`, `entry_table.html`, historical entry rendering; same authorization filters. T5 must verify populated and historical display end to end. |
| Student mobile access | Partial | Shared responsive shell and contained timetable grid exist; prior fixture verification is not a live student-account/device walkthrough. T5/T16 require that evidence. |
| Student concern submission / tracking | Existing / Existing | T7 shared Schedule Concerns navigation, authorized published schedule/class selection and private status/response tracking. |
| Faculty assigned teaching timetable | Existing | `views.py:dashboard` filters published entries by effective faculty; `faculty_dashboard.html` and personal timetable. `test_faculty_dashboard_shows_weekly_personal_timetable`, `test_faculty_cannot_open_schedule_with_no_assigned_entries`. |
| Faculty workload display | Existing | T6 adds published weekly contact minutes/hours, meeting and effective-section counts per schedule, plus the explicitly current faculty limit. Snapshot entries are authoritative; no fairness or academic-unit equivalence is claimed. |
| Faculty own availability | Existing | `my_availability`, `my_availability_create/update`, faculty-only decorator, owner-bound lookup, owner/room controls disabled and server-assigned ownership. `my_availability.html`; shared Availability policy. Review missing-profile handling and cross-owner POST attempts in T6/T12. |
| Faculty concern submission / tracking | Existing / Existing | T7 reuses the same workflow with effective faculty authorization. |
| Administrator concern queue / status / response | Existing / Existing / Existing | T7 adds a filtered queue, official responses, revision checks and transactional review history; separate from generation diagnostics. |
| Administrator authorized corrections | Existing | Draft editing, signed revision tokens, transactional save/removal, suggestions, Copy to Draft, publication validation and immutable snapshots. Existing services/tests above; concern resolution must reuse these paths, never mutate finalized rows directly. |

### T7 planned concern contract (no implementation in T1)

Faculty/Students may report time conflicts, room conflicts/unavailability, incorrect or missing subjects, faculty/section assignment concerns, or other scheduling issues. Bind reports only to schedules/entries the reporter may access; recheck access at submission and read time. A missing-subject report may reference an authorized section/published schedule without requiring an existing entry. Do not expose other students' records through selectors, IDs, attachments, comments or status views.

Plan a private reporter-owned list/detail view and an administrator-only review queue, status transitions, responses and timestamped audit trail. The T7 user instruction supersedes the initial status proposal: Pending, Under Review, Resolved and Rejected. Reports default to Pending; only administrators may change status or official responses. Reports have no delete/edit endpoint for reporters; responses are visible only to their reporter and administrators. Only authorized administrators may resolve via existing draft/copy/correction/publication workflows. **Submitting or changing a concern status must never automatically modify a schedule.** Record resolution references separately; enforce POST/CSRF, object-level ownership and stale-edit protection where applicable. Notifications/availability approval requests are optional T14 work, not prerequisites for safe T7 reporting.

## B. New thesis development progress

**14/16 Completed (T1-T10, T12-T13, T15-T16); T11 Manual Evaluation Pending; T14 Deferred.** T14 is optional. Existing functionality is credited in the audit, not by prematurely marking its future verification task complete. Priorities order work within the specified phases; they do not authorize parallel implementation or bypass dependencies.

| Task / phase | Status / priority | Objectives | Dependencies | Acceptance criteria and evidence/reuse |
| --- | --- | --- | --- | --- |
| T1 / 1: objective and role audit | Completed / Critical | O1-O7 | Existing repository evidence | This single active plan maps all objectives/roles, records gaps, separates progress, preserves prior work and defines T2-T16 without implementation; source references and whitespace verification recorded. |
| T2 / 1: conflict detection verification | Completed / Critical | O1 | T1 | Reproduce each approved conflict category and incomplete requirements before finalization; legitimate adjacency/parallel sections pass; cover manual, import, generation, admin/publication. Reuse `conflicts.py`, `meetings.py`, publication tests; record exact tests/results and remaining policy gaps. |
| T3 / 1: double-booking prevention | Completed / Critical | O2 | T2 | Prove atomic rejection for instructor/room overlaps through all relevant writes and concurrent requests; define cross-term/version scope. Reuse occupancy, manual transactions, publication/finalized protections; no weaker validation bypass. |
| T4 / 1: teacher/student availability | Completed / Critical | O3 | T2, T3; approved student policy | Document source/ownership/aggregation and defaults; support required student or section windows consistently in generation, manual validation and publication; test boundaries, contradictions and infeasibility. Reuse AvailabilityPolicy rather than duplicating faculty/room rules. |
| T5 / 2: student personal timetable | Completed / High | O1, O3 | T3, T4 | Authorized published entries show subject/teacher/room/time, correct empty/override/history states and mobile behavior; direct URL/query isolation and populated browser walkthroughs pass. Reuse existing dashboard/timetable instead of rebuilding. |
| T6 / 2: faculty schedule/load/availability | Completed / High | O3, O5 | T3, T4 | Verify own published timetable and owner-only availability edits; expose clearly defined workload totals/limits without claiming fairness; test cross-owner attacks and missing profiles. Reuse current faculty views and minute calculations. |
| T7 / 2: shared concerns | Completed / High | O1, O3, O7 | T5, T6 | Implement the approved concern contract above: all five categories, reporter-private tracking, admin review/status/response/audit, authorized resolution references and zero automatic schedule mutation. Test ownership/permissions, invalid references and CSRF. |
| T8 / 3: load balancing | Completed / High | O5 | T6; T7 phase gate; approved fairness/reassignment policy | Measure normalized loads and evaluate an actual load-balancing objective/strategy within qualifications, availability and limits; report feasible comparisons. If faculty allocation stays fixed, document the objective gap rather than relabeling day spread as fairness. |
| T9 / 3: room optimization | Completed / High | O6 | T4, T8 | Validate capacity/type/availability/department rules; measure baseline and optimized utilization including unused capacity; document denominator and spreading/consolidation tradeoff. Reuse existing room analytics and GA terms. |
| T10 / 3: targeted rescheduling | Completed / High | O7 | T7, T8, T9 | Handle absence, outage and new-section scenarios on drafts, retain originals/audit and minimize defined movement costs; report changed/unchanged entries, feasibility and response time. Reuse corrections, copy and bounded repair; do not modify snapshots. |
| T11 / 3: performance/manual study | Manual Evaluation Pending / High | O4, supporting O5-O7 | T2-T10; agreed manual-study protocol | Measure full preparation workflow against documented matched manual cases and repeated seeded solver runs; report failures, quality, distributions/effect sizes and limitations. Reuse benchmark/report tooling; no invented timing or unsupported significance claims. |
| T12 / 4: role/integration tests | Completed / Critical | O1-O3, O7; all roles | T5-T11 | Admin/Faculty/Student happy paths and unauthorized direct reads/writes, concern ownership, CSRF, stale edits and finalized protections pass; record actual account/browser evidence and regression results. Reuse existing role/security suites. |
| T13 / 4: thesis acceptance/evidence | Completed (evidence review) / Critical | O1-O7 | T11, T12 | Each objective has explicit pass/fail criteria, reproducible artifacts, data provenance, measured outcomes and approved limitations; no objective marked fulfilled solely from UI/model existence. Collect cases, seeds/configs, conflict counts, load/utilization metrics, timings and disruption comparisons. |
| T14 / 5: availability requests/notifications | Deferred (optional) / Low | O3, O7 | T13; explicit approval and confirmed need | If authorized, define request approval/notifications/privacy/failure handling; requests do not silently rewrite finalized schedules. Not required to count core thesis progress complete unless scope is formally amended. |
| T15 / 5: essential administrator UI | Completed / Medium | Supports O1-O7 | T13; T14 only if adopted and relevant | Reassess historical UI tasks 3.2 onward against actual workflow blockers; preserve 9/24 baseline and implement only approved essentials, with no automatic credit for old tasks. |
| T16 / 5: final usability/accessibility | Completed (focused QA) / Medium | Supports O1-O7 | T13, T15; adopted T14 | Role-based populated workflows across both themes, target widths, keyboard/focus, assistive technology and device/browser matrix verified; document unresolved limitations. Keep this distinct from functional thesis acceptance in T13. |

## Policy decisions and next action

Resolve decisions in their owning task before coding dependent changes: O1 meaning of subject conflicts/curriculum coverage (T2); cross-term collision scope (T3); individual vs section availability and approved default policy (T4); workload units/contracts and permission to reassign teachers (T8); department/shared-room policy and utilization goal (T9); allowable displacement and absence/change semantics (T10); manual-study population, protocol and significance claim (T11). These are open questions, not assumed requirements or permission to change academic rules.

**T10 is Completed for the bounded recurring-repair scope; O7 remains Partially Verified pending representative operational evidence.** T2 verified the existing conflict/publication stack without application changes; see the verification record below. Follow the specified phase order. Do not resume UI Task 3.2 automatically or begin T11 without approval.

## T1 verification and limitations

Focused reads covered models, role/routes/views/templates, GA fitness/placements/repair, availability, conflict/publication/manual services, room reporting, benchmark documentation and relevant test definitions. Searches found no concern workflow in the inspected models/routes/role templates. Absence findings are scoped to repository evidence, not an assertion about external institutional processes. Existing test reports were reviewed, not rerun. No new performance measurements or browser results are claimed. `git diff --check` passed for documentation changes; source/data behavior is unchanged.


## T2 verification record (2026-10-21)

Scope: O1 conflict detection under existing academic rules only. No application defect was confirmed; no business logic, GA fitness, models, migrations, UI or real database records were changed. Added six focused tests in `schedules/test_thesis_conflicts.py`; reused existing coverage rather than duplicating validation.

| Conflict/rule | Backend evidence and verification |
| --- | --- |
| Faculty, room and section collisions | `validate_entry` uses effective overridden identities and strict interval intersections. Existing `test_single_resource_conflicts_and_effective_overrides` isolates each resource. New partial-overlap matrix checks all three diagnostic categories and the same three GA hard violations. |
| Time boundaries | New matrix tests overlap from both directions and exact adjacency before/after a meeting. Adjacent meetings have zero issues and zero GA hard violations; adjacent split meetings successfully publish. |
| Subject restrictions | Duplicate term/subject/section/component/meeting-index and duplicate schedule/meeting entries are rejected. Course/component overrides and lecture/lab totals use shared `meetings.py` validation. Same subject in parallel independent sections is explicitly accepted. Subject code alone is not a mutual-exclusion resource. |
| Manual edits | New direct-service test rejects a partial overlap and preserves entry, revision and audit records. Existing transaction tests cover validation, stale requests and rollback; validation is not merely a frontend warning. |
| Publication and alternate admin routes | New publication-service test rejects persisted draft collisions without changing status/revision/audits/snapshots. Existing admin security tests verify read-only entry/status fields, invalid-publication rejection, permissions, POST and CSRF enforcement. |
| GA output | GA hard overlap checks agree with manual validation in the new boundary matrix. Generation revalidates persisted candidate entries inside its saving transaction. Existing meeting/diagnostic tests reject incomplete, duplicate and conflicting generated output. |
| Spreadsheet import | `importers/academic.py` invokes model and shared meeting validation, checks affected draft entries and uses transactions. Existing import tests cover duplicate rows, invalid meeting totals, rollback and reference-only timetable columns. Imports do not publish schedules or interpret reference times as fixed placements. |

Limitations: detection is verified against recorded assignment/meeting requirements within a schedule. As documented in `CURRICULUM_COMPLETENESS_EVALUATION.md`, authoritative curriculum completeness cannot be established from existing assignments alone. No new prohibition on parallel sections or cross-term schedules was invented. Cross-term/cross-version policy and comprehensive concurrent double-booking verification belong to T3, not this task. O1 remains **Partially Verified** pending academic scope clarification; current-rule detection coverage is recorded above. T2 does not certify every institutional rule or arbitrary direct SQL mutation.

Verification: six new tests passed in isolation (0.435 seconds). Django system check passed; migration dry-run reported no changes. The combined focused run passed **136 tests in 94.723 seconds**, with zero failures, skips, expected failures or unexpected successes. It ran `schedules.test_thesis_conflicts`, `schedules.test_manual_transactions`, `schedules.test_meeting_requirements`, `schedules.test_academic_import`, `schedules.test_admin_publication_security`, `schedules.test_ga_repair`, `schedules.test_generation_diagnostics` and `schedules.test_validation_performance` using `.venv/Scripts/python.exe manage.py test`. Logged exceptions came from intentional mocked failure/rollback cases; the runner finished OK. `git diff --check` passed. T2 is Completed for the existing-rule verification scope; thesis progress is 2/16, and T3 remains Not Started. The historical 561-test full-suite baseline was not rerun or relabeled as a new result.


## T3 verification record (completed after resumption)

**Completed. O2 Verified for the existing weekly-recurring term model on SQLite. Thesis progress: 3/16. T4 remains Not Started.**

### Recovered progress and confirmed correction

The prior session implemented the cross-term validator and eight tests in `schedules/test_thesis_double_booking.py`. Recovered logs show the final full suite already completed: **575 passed in 313.025s**, zero failures/skips/expected failures/unexpected successes (`t3-final-tests.log`). An earlier 573-test run had nine query-budget subtest failures; combining local and external conflict lookup into one query fixed those failures without weakening assertions. The subsequent focused validation/performance run passed **18 tests in 25.601s** (`t3-focused.log`). The initial finalized-record test teardown issue was fixed using test-only trigger removal/restoration around disposable database flushing; protections remain active throughout assertions.

The user explicitly approved checking instructor and room occupancy across published academic terms whose dates overlap. Confirmed defect: the old validator only examined the candidate schedule, so publication could double-book resources across terms. `services/conflicts.py:validate_entry` now includes published entries in different terms with intersecting inclusive dates. The date intersection must contain the meeting weekday, and clock intervals must strictly overlap. Effective faculty overrides are respected. Cross-term section rules and workload policies are unchanged.

### Workflow safeguards and evidence

- Manual creation/editing: shared validation executes after a conditional revision write inside `manual_edit_transaction`. Rejection preserves entries, revisions and audits. Tests cover creation, partial overlaps, adjacency and different weekdays; T2 evidence is reused.
- GA: existing hard checks are retained, followed by shared validation in the saving transaction. The new cross-term test proves an externally conflicting candidate is rolled back. GA search/weights are unchanged; it may reject a candidate rather than search around external occupancy.
- Publication: the SQLite writer lock precedes validation; cross-term conflicts prevent status, snapshot and audit changes. Existing admin read-only fields and authorized POST publication paths remain intact.
- Copy/repair: independent draft entries preserve historical source records. Legacy issues may remain in a copied draft for correction, but cannot bypass publication validation. Suggestions revalidate through the same transactional manual-save service. The earlier focused copy/correction/concurrent-save selection passed 36 tests in 28.386s.
- Concurrency: real threads and independent database connections race edits to different entries for the same instructor or room. Exactly one commits; the loser is stale or database-locked, and a fresh conflicting retry is rejected. Another test races publication of two overlapping terms: only one becomes published; retry of the other is rejected. No sequential-only concurrency claim is made.
- Boundaries: adjacent periods, different weekdays and non-overlapping dates are valid. A short date intersection without the meeting weekday is valid. Only published schedules in other terms consume external occupancy; alternative drafts and archived schedules do not. Same-term replacement versions remain independent until the existing publication workflow archives the predecessor.

### Resumption verification and files

This resumption reviewed code and completed logs, reran **8 focused T3 tests (1.575s, all passed)**, and finished this document. No application or test implementation changes were needed during resumption. `.venv/Scripts/python.exe manage.py check` passed; `makemigrations --check --dry-run` reported no changes; `git diff --check` passed. The full suite was not redundantly rerun after documentation-only changes. Previous uncommitted UI documentation, T2 tests and database changes were preserved.

T3 implementation files: `schedules/services/conflicts.py`, `schedules/test_thesis_double_booking.py`, and this plan. Execution logs are retained as local evidence. No migrations, real database writes, commits or deployments were performed.

### Scope and limitations

The model represents a weekly weekday/time meeting throughout inclusive academic-term dates. It does not store per-meeting date ranges, holidays, cancelled occurrences or irregular calendars. The validator therefore establishes actual shared weekdays under that existing recurrence model, not an independently verified institutional calendar; no speculative holiday/date fields were introduced.

Concurrency evidence is for Django's SQLite test database with separate connections. Production multi-process load and other database engines are not certified. SQLite may reject a competing writer with a lock error rather than wait; no automatic retry guarantee is claimed. Arbitrary direct SQL writes are outside supported scheduling workflows. Existing finalized records were not retroactively scanned or modified. These boundaries do not leave an outstanding T3 implementation requirement within the approved current-model/SQLite scope.


## T4 implementation and verification

Model decision: **administrator-maintained section availability**. `Student.section`, parent assignments and individual meetings use fixed sections; there is no individual student enrollment/availability aggregation policy. Reuse the existing `Availability` model with an optional section owner and a database constraint requiring exactly one faculty, room or section. No personal student interface, preferences or dashboard redesign is introduced.

Policy follows existing faculty/room semantics: absent constraints retain normal school days/hours; any AVAILABLE row limits the resource to explicitly available windows/days; UNAVAILABLE windows subtract time and win over AVAILABLE windows. Adjacent periods are valid. Section constraints apply weekly to the section wherever used, across terms, just as existing resource availability does; term-specific or individual exceptions are not modeled. Sections support AVAILABLE/UNAVAILABLE only, not PREFERRED. Faculty preferred periods remain soft preferences and faculty hard rules are unchanged.

Administrators record/edit/remove section windows through the existing **Availability** management page: choose Section, leave Faculty and Room blank, select day/times and Available or Unavailable. Existing Django admin permissions also apply. Faculty self-service disables section selection and server-clears it, so posted section IDs cannot grant ownership of section constraints. Student self-management is not required.

Enforcement: shared `individual_entry_errors` validates the effective section (including manual overrides). GA feasible domains include section interval boundaries, including off-grid windows; fitness and repair use cached section policies; final save rechecks current database constraints. Manual create/edit and publication reuse the same validation. Existing schedules without section windows retain previous validity and diagnostic behavior. Section rows are batch-prefetched during schedule validation; the performance test allows two fixed queries for default/overridden section availability rather than queries per meeting. Room availability/utilization and soft optimization weights are unchanged.

Reproducibility inputs now use `schedease-inputs-v2`, including section periods and effective policies so changing availability changes the input fingerprint. Historical metadata remains readable. Section errors use the existing INVALID_DATA diagnostic category with an explicit Section availability message; no unrelated diagnostic schema migration is required.

Migration: `0016_section_availability.py` adds the nullable section foreign key and extends exactly-one-owner enforcement. Existing faculty/room rows remain valid. It is exercised on disposable test databases; it has **not** been applied to the user's existing database. Before using the updated application locally, activate the project environment and run `python manage.py migrate` against the intended database. No real academic records were modified in this task.

Focused coverage in `test_section_availability.py`: no-constraint compatibility, unavailable/partial-overlap/adjacent windows, available-only days and non-grid GA placement, manual/publication rollback, successful publication, effective section overrides, administrator create/edit and faculty ownership enforcement, owner database constraint, rejection of section preferences, fingerprint sensitivity, faculty manual/publication behavior, stale GA input revalidation and contradictory/empty domains. The initial focused run exposed an extra default-section error for already-invalid times; this was corrected so unconfigured sections add no duplicate diagnostic. The latest 13-test targeted run passed (1.500s), including all 12 new T4 tests and the existing diagnostic-equivalence regression.

Scope limitations: no individual student availability, per-term section exceptions, holiday calendars or spreadsheet section-availability mapping. Administrators maintain section windows directly. Existing published snapshots are not rewritten when availability changes; future validation uses current windows. No browser visual verification is claimed; existing shared forms/styles are reused.

Final verification: `python manage.py test` passed **587 tests in 330.717s**, with zero failures, skips, expected failures or unexpected successes (`t4-tests.log`). This includes the prior 575-test suite plus 12 new T4 tests. The final section-list label and its rendering assertion were added while that full run was executing; all **12 focused tests subsequently passed in 1.378s** against those final files. No further business-logic changes followed. System checks passed, migration dry-run found no ungenerated changes, and `git diff --check` passed. Tests used `.venv/Scripts/python.exe` and disposable databases. No browser testing or real-database migration is claimed.

Files changed for T4: `models.py`, `forms.py`, `views.py`; services `availability.py`, `conflicts.py`, `ga.py`, `placements.py`, `repair.py`, `listing.py`, `reproducibility.py`; migration `0016_section_availability.py`; new `test_section_availability.py`; focused updates to `test_ga_placements.py` (new common-window message) and `test_validation_performance.py` (two bounded section-prefetch queries); this plan. The availability list uses a readable section/day/time label via the model representation without changing templates. Existing unrelated changes and T1-T3 work are preserved.

**T4 Completed; O3 Verified for administrator-maintained fixed sections. Thesis progress 4/16.** Apply the migration before local use; T5 remains Not Started and requires approval.


## T5 Student personal timetable verification

**Completed; thesis progress 5/16. T6 remains Not Started.** Existing Student accounts authenticate through the normal login form. Dashboard, browse, detail and exports restrict students to published entries for their effective section; a missing Student profile yields no entries. Existing tests cover mixed-section filtering, effective section overrides, unauthorized direct URLs, filter tampering, snapshots and export isolation. Drafts and archived schedules remain unavailable through current student timetable routes. Students cannot create/edit/remove/publish/copy schedules or create availability through administrative endpoints.

Confirmed presentation gap: the weekly grid put instructor names only in a hover title. Student timetable cells now visibly show the effective instructor, including historical snapshot values, without hover. `student_dashboard.html` passes a flag to the existing `personal_timetable.html`; Faculty rendering is unchanged. Subject code and accessible course-description tooltip, room, weekday, times and academic term/school year were already present. Existing empty state explains that classes appear after an administrator publishes an assigned schedule. Multiple published terms retain their individual cell context; no new current-term selection policy was introduced.

Migration check was read-only: this session resolves `sched_ease.settings` to `C:/Users/JEROME/SchedEase-Prototype/db.sqlite3`, with 0001-0012 applied and 0013-0016 pending. This differs from the user's earlier PowerShell configuration pointing at `tertiary_sample.sqlite3`; no inference about that other database's migration state is made. No migration or record changes were made to either working database. The working database must be brought up to the checked-in migrations before using the updated application. Test/browser fixture migrations ran only in disposable in-memory databases.

### Executed verification

- Four new `schedules.test_student_timetable` tests: normal HTTP login and visible details/context; empty/draft/direct-export isolation; read-only endpoint rejection with unchanged entries/audits; missing-profile safety.
- Combined focused run: **59 passed in 34.105s**, zero failures/skips/expected failures/unexpected successes. Included the four new tests, four existing Student timetable tests, the Faculty timetable test, `test_admin_publication_security`, `test_diagnostic_access` and `test_snapshots`. An expected injected publication failure was logged by a rollback test; the suite finished OK.
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed. Commands used `.venv/Scripts/python.exe`. The 587 full-suite baseline was not rerun or claimed as a new full-suite result; no shared view/permission/selection logic changed.
- Browser: `tests/browser/render_student.py` renders an authenticated, populated Django response with synthetic published data. `run_interactions.py --student` passed **104 assertions** (13 per theme/width) at 1360, 768, 500 and 390px in **Light Mode and Dark Mode**. Checks cover visible instructor/course/room/time/term, table-only horizontal scrolling, no horizontal page overflow, alternate list display, requested theme and working theme toggle. The existing runner's other modes are preserved.
- Initial sandbox browser launch timed out; retry through normal elevated execution succeeded. No approval restriction was bypassed. The failed attempt left a locked disposable browser-profile directory; its exact workspace path was verified and it was removed through normal elevated execution.

Files changed for T5: `templates/schedules/student_dashboard.html`, `templates/schedules/personal_timetable.html`, new `schedules/test_student_timetable.py`, new `tests/browser/render_student.py` and generated `rendered_student.html`, the existing browser runner's optional `--student` mode, and this plan. Unrelated uncommitted changes are preserved.

Limitations: browser assertions exercise real Django-rendered HTML/CSS/JavaScript in a headless desktop browser at mobile widths, not a physical device, screen-reader audit or browser-driven live-server login. HTTP login/security are independently tested through Django's client. No student availability editing, concern reporting, GA changes or dashboard redesign was introduced. No commits, push or deployment.


## T6 Faculty schedule, workload and availability

Existing Faculty functionality verified: normal login, published-only personal timetable, effective faculty overrides, authorized detail/export access, subject/section/room/weekday/time/term display and empty states. Owner-scoped availability views allow direct faculty maintenance; there is no approval/request workflow to replace. Disabled owner selectors and server-assigned ownership reject attempts to attach another faculty, room or section to a faculty's availability. Invalid time spans fail backend validation. Existing T4 availability enforcement is reused unchanged.

Confirmed gap: the Faculty dashboard did not present a calculated workload. The new `services/faculty_workload.py` aggregates only the dashboard's already-authorized historical published entries, separately per schedule. Weekly minutes are the sum of `assignment.required_duration_minutes` from the publication snapshot; hours are minutes / 60, displayed to two decimals with exact minutes alongside. Counts are scheduled meetings and distinct effective sections. These are contact hours, not academic units, total-course hours or an inter-instructor fairness metric. Draft/unpublished assignments are deliberately excluded and the heading states Published teaching workload. Current `Faculty.max_weekly_hours` is shown as the **current** weekly limit, not a historical limit. No GA scoring/assignment/load policy changes were made.

Only the faculty dashboard branch receives the summary. A missing Faculty profile produces no entries/workload and no availability queryset; owner-only availability pages return 404. No private availability from other resource types is loaded for a missing profile. The template reuses existing panel/text/theme styles without CSS or dashboard redesigns.

Migration inspection: active settings resolve to `C:/Users/JEROME/SchedEase-Prototype/db.sqlite3`; migrations 0001-0012 are applied and 0013-0016 pending. No working database migrations or record writes were performed. Fixture migrations use disposable in-memory databases only. This task introduces no migration.

New `test_faculty_timetable.py` covers HTTP login and published details/workload, draft and missing-profile emptiness, effective faculty ownership and prohibited schedule writes, authorized availability updates/invalid periods/cross-owner GET and POST rejection, and fractional minutes/grouped counts. Existing student, role, snapshot and T4 suites provide regression coverage.

Browser checks: the existing synthetic Django renderer and runner now accept `--faculty`. A real authenticated populated Faculty response is rendered into `rendered_faculty.html` and exercised in a headless browser at 1360/768/500/390px in Light and Dark Mode. All **104 assertions passed**, including workload visibility, timetable details/term, table-contained scrolling, no page overflow, alternate list display and theme switching. Browser execution used normal elevation because sandbox browser startup is unavailable. These are rendered-page checks, not a live-server browser login, physical mobile or screen-reader audit; login/authorization are independently tested through Django's HTTP client.

Files changed for T6: `schedules/views.py` (faculty branch only), new `services/faculty_workload.py`, `templates/schedules/faculty_dashboard.html`, new `test_faculty_timetable.py`, `tests/browser/render_student.py` and `run_interactions.py` (optional faculty mode), generated `rendered_faculty.html`, and this plan. Existing T1-T5, Assignment filter and unrelated work are preserved. Full-suite baseline remains the previously executed 587 tests; no new full-suite claim is made. T7 is not started.


T6 final verification: five new tests passed alone in 5.790s; the broader focused selection passed **82 tests in 31.476s**, zero failures/skips/expected failures/unexpected successes. Selection: `test_faculty_timetable`, `test_student_timetable`, `test_section_availability`, `test_availability`, `test_admin_publication_security`, `test_diagnostic_access`, `test_snapshots` and two existing faculty timetable/access tests in `SchedulingTestCase`. A logged injected publication exception belongs to a passing rollback test. Django check passed; migration dry-run found no changes; Git whitespace check passed. All Python commands used the project virtual environment. **T6 Completed; progress 6/16.** O5 remains Partially Verified because load balancing is outside T6. No commits, push, deployment or T7 work.


## T7 Shared Schedule Concerns (Completed)

**Progress: 7/16. T8 remains Not Started.** One shared Student/Faculty workflow is available through **Schedule Concerns** in the existing sidebar. Reporters select an authorized published schedule, optionally an affected class, one of the five requested categories, and a 10-3000-character description. Missing-subject/schedule-wide reports may omit the class. Users can list only their own reports, read their saved context, status and official response; they cannot edit statuses/responses or other users' reports.

Administrators use the same navigation to access a paginated review queue (20 reports/page), filter by status/category/reporter role, open the saved schedule/class context and authorized schedule link, choose Pending/Under Review/Resolved/Rejected, and add/update a response (maximum 3000 characters). No mandatory status sequence or new academic approval policy was invented. Each review records before/after status and response, administrator identity and timestamp. Conditional revision claiming and a transaction reject stale reviews and roll back audit failures without partial updates.

Models: `ScheduleConcern` retains reporter/role, nullable live schedule/entry references, a server-built snapshot of authorized schedule/term/class labels and IDs, category/description, Pending default, official response, submitted/review timestamps, reviewer and revision. `ConcernReview` provides the append-only-through-this-workflow review history; existing scheduling audit models remain unchanged. Reporter deletion is protected; detached scheduling references retain saved context. These models are deliberately not registered for unrestricted Django-admin editing; review uses the authorized application workflow.

Authorization: existing `admin_required`, role checks and `entries_visible_to_user` are reused without changes. Schedule and class dropdowns are limited to authorized published records, references are rechecked in the submission service, and a selected class must belong to the selected schedule. A form referencing a replaced/archived schedule is rejected. Detail queries are reporter-scoped (404 for other reports), reporter POST review attempts are forbidden, and service calls also enforce roles. Login, active-user checks, CSRF and explicit HTTP methods protect writes. Forms whitelist fields and ignore forged reporter/status/response values on submission. Django escaping protects descriptions, responses and saved labels; long text wraps without page overflow.

Schedule safety: concern submission/review never calls generation, manual-save or publication services and never writes schedules, entries, assignments, snapshots or schedule audits. Tests compare those records before/after operations. Authorized administrators follow the existing View schedule link and existing correction workflows separately. Archived/replaced schedules retain saved report context; reporters do not receive a live link unless the schedule is still published and currently authorized. Current unpublished content is never rendered on concern pages. No correction is inferred from a Resolved status.

### Verification

- New `schedules.test_concerns`: **10 passed in 11.630s** on final code/tests. Covers Student/Faculty submissions; default Pending and privileged-field tampering; foreign schedule/class and mismatched references; missing-subject reports; private visibility across Student/Faculty accounts; review filters/audits/statuses/stale updates; invalid descriptions/categories/responses; atomic review rollback; unchanged schedule data; safe text; traceability and stale submission after replacement; authentication, CSRF and method restrictions.
- Combined focused run: **69 passed in 38.992s**, zero failures/skips/expected failures/unexpected successes. Included concerns, Student/Faculty timetable suites, admin publication security, diagnostic access and snapshots. The final two privacy/stale-submission assertions were then added to existing concern tests and the entire concern module rerun successfully. The logged injected publication exception belongs to a passing rollback regression.
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no missing migrations. `git diff --check`: passed (Git may warn about LF/CRLF normalization; no whitespace errors). All Python checks used `.venv/Scripts/python.exe` and isolated Django test databases.
- Browser: `render_concerns.py` builds seven authenticated Django-rendered pages with synthetic in-memory data (Student new/list/detail, Faculty new/detail, Administrator queue/review). `run_interactions.py --concerns` passed **296 assertions**, 37 at each of 1360/768/500/390px in **Light Mode and Dark Mode**. Verified themes, headings, contained form controls, sidebar links, reporter read-only details, administrator controls and no horizontal page overflow, including a long description. Execution used normal elevated headless-browser permissions and disposable profiles. This is rendered-page/browser-layout evidence, not physical-device testing or browser-driven live login.
- No new full-suite run is claimed; the latest executed full-suite baseline remains 587. No existing authentication or timetable selection logic was changed, so focused role/security/snapshot regressions were used.

### Migration, files and limitations

Migration **0017_schedule_concerns.py** creates the concern and review tables; depends on 0016. Active working database: `C:/Users/JEROME/SchedEase-Prototype/db.sqlite3`. Initial inspection showed 0001-0012 applied and 0013-0016 pending; 0017 is also unapplied. **No working-database migration or record writes were performed.** Activate the intended environment and run `python manage.py migrate` against the intended database before using the new feature. Renderer migrations ran only in-memory.

Files: `schedules/models.py`, `urls.py`, new `concern_forms.py`, `concern_views.py`, `services/concerns.py`, migration 0017, `test_concerns.py`; `templates/base.html` navigation and three new `templates/schedules/concerns/` pages; a scoped `.concern-text` wrapping rule in `static/css/app.css`; new `tests/browser/render_concerns.py`, generated `rendered_concerns.html` and the runner's optional concerns mode; this plan.

Limitations: reporting requires at least one currently authorized published entry to establish schedule ownership; a user with no assigned published schedule is directed to contact an administrator. No attachments, notifications, reporter editing/deletion, standalone ticketing or automatic schedule correction. Review concurrency uses revision checks/transactions but no new multi-process load guarantee is claimed. Direct raw database modifications are outside the supported workflow. No commits, push, deployment or T8 work.


## T8 Teaching load verification (2026-10-21)

**Status: In Progress; O5 Partially Verified; roadmap 7/16 completed.** The authorized audit and existing regression checks are complete. Cross-instructor allocation requires a policy decision before implementation, as required by T8 section 3. No application changes or new academic policies were introduced.

### Architecture and scope

`services/ga.py` loads term-specific TeachingAssignment meetings with fixed faculty. `Gene` contains assignment, room, day and start/end times; it has no instructor decision variable. Initialization, crossover and mutation preserve meeting identity. Thus changing placements cannot change each instructor's assigned weekly contact minutes. Administrator assignment workflows can change faculty explicitly; timetable generation is not authorized to do so implicitly.

GA preflight sums required meeting minutes per instructor and rejects totals above `max_weekly_hours * 60`. Shared manual/publication validation uses effective faculty and scheduled meeting minutes within the candidate schedule. These are per-term generation/per-schedule validation limits, not a demonstrated aggregate across overlapping published terms. Qualification checks reuse `teaching_eligibility`; feasible placement generation applies availability and resource rules. Hard-first ranking is preserved.

The distribution penalty measures daily concentration, faculty idle gaps, section gaps and counts across instructional days. It does not measure total workload fairness across instructors. T6 `services/faculty_workload.py` separately displays authorized published snapshot contact minutes/hours per schedule; that display is not an allocation optimizer. Unequal totals alone are not an existing hard violation.

### Verification

Project virtual environment: `manage.py check` passed; `makemigrations --check --dry-run` reported no changes. Focused existing selection passed **61 tests in 40.793 seconds**, with no failures, skips, expected failures or unexpected successes: `test_ga_soft_scoring`, `test_ga_placements`, `test_credentials`, `test_faculty_timetable`, `test_validation_performance`. Evidence covers qualifications/overrides, availability/conflicts and boundaries, preserved gene assignment IDs, seeded candidate reproducibility, workload validation with effective overrides, and published workload summaries. No full-suite run or new fairness regression coverage is claimed. No working database writes or migrations were performed.

### Decision and remaining work

Confirm whether a separate administrator-reviewed assignment proposal step is permitted, which assignments are eligible for reassignment, and which faculty are comparable. Approve the fairness target: absolute weekly contact hours or utilization relative to approved weekly limits (or an institution-specified target). Limits are ceilings and are not automatically contractual workload targets. Preserve qualifications, availability, fixed assignments and mandatory feasibility checks in any approved design.

No before/after optimization measurements exist because no allocation change was authorized or implemented. For fixed inputs, per-instructor sums and their minimum, maximum and spread are invariant under timetable placement changes; no fairness improvement is claimed. After policy approval, finish focused allocation/limit/unequal-load regression tests and reproducible feasible before/after comparisons. T8 remains incomplete; T9 has not started. Existing uncommitted T7, navigation and database changes were preserved.


## T8 approved proposal workflow ? completion (2026-10-21)

This section supersedes the preceding T8 policy-decision checkpoint. The user approved explicit assignment eligibility, administrator-reviewed batch reassignment, and comparison by percentage of weekly limits. **T8 Completed; roadmap 8/16. O5 remains Partially Verified at thesis level:** reproducible synthetic evidence establishes feasible cross-instructor balancing within the scope below, not institution-wide effectiveness or an optimal allocation guarantee. T9 has not started.

### Architecture and conservative scope

`services/workload_balancing.py` is separate from the timetable GA. Administrators select a term, explicitly eligible parent assignments and a comparable instructor group, and confirm compatible responsibilities/workload policies. Only one department is compared, and selected courses must belong to it. All meetings of a selected parent move together through the existing `Assignment.save()` synchronization. Unselected assignments are fixed. Existing parent protection locks assignments referenced by **any** schedule; the feature preserves this rule and conservatively requires the entire term to have no scheduled entries. Published/archived schedules and drafts are never changed or created by this feature. Existing scheduled terms must use the authorized correction workflow rather than this allocation tool.

A shared `faculty_workload.contact_minutes` helper preserves T6's required-meeting-minute calculation for both live assignments and published snapshots. Utilization is `100 * assigned term contact minutes / (max_weekly_hours * 60)`. The objective is population variance of utilization percentages within the selected group, including selected instructors with zero hours. Actual hours, minutes, minimum, maximum and spread are shown. Weekly limits remain ceilings, not contractual workload targets. No cross-term aggregate workload policy is invented.

Deterministic greedy search evaluates coordinated batches, in ID order, accepting only strict variance improvements. Each parent moves at most once. Ties keep the first candidate; unnecessary equal-score moves are not recommended. For each candidate batch, shared credential/override, meeting component totals, room and availability services construct placement domains. A bounded deterministic placement search demonstrates joint faculty/section/room feasibility for **all** meetings in the term. Existing cross-term validation checks overlapping published dates, weekdays and times. No feasible witness means no approval, including search exhaustion; this does not prove mathematical infeasibility. Placement evidence is retained in the approval audit, but is not saved as a schedule or fed into a rewritten GA.

Limits: at most 12 selected assignments, 12 comparable instructors, 80 term meetings and 5,000 placement-search visits. Local search is not globally optimal and cannot discover every swap or coordinated overload repair. Normal GA generation and publication still independently validate subsequent schedules. The scope is intentionally conservative, not an implicit authorization to unlock scheduled academic records.

### Administrator workflow, explanations and safety

Assignments ? **Workload Balancing Proposals** ? select eligible scope ? Generate ? include/exclude proposals ? Preview selection ? confirm and Approve selected batch. Select all and Cancel are provided. Explanations come from actual shared validations and arithmetic; they distinguish eligibility from whole-batch recommendation. Each proposal displays both instructors' original and combined proposed percentages/minutes/hours, plus its arithmetic marginal contribution to the final batch. The marginal comparison is explicitly not a separately validated batch.

Changing selection hides old metrics, disables approval and requests a fresh preview. Server-side signed reviewed-selection evidence also prevents bypassing that step. Recalculation uses the selected combination; a non-improving or empty batch cannot be approved. Signed proposal tokens are administrator-bound, expire after 30 minutes and include a fingerprint covering scheduling inputs, qualification equivalences and existing occupancy. Input changes invalidate the preview conservatively, even if unrelated to that specific proposal.

Approval rechecks current permissions, scope, qualifications, limits, availability, conflicts, fairness and fingerprint. SQLite acquires its writer reservation through the initial audit insert **before** approval reads; assignment changes and final audit evidence commit together or roll back together. Other database backends fail closed for approval pending transaction-specific verification. Actual multi-process contention testing was not performed; no cross-backend concurrency guarantee is claimed. Authenticated application administrators alone can access the view and approve; POST, CSRF and explicit confirmation are required. No change to authentication policies, GA weights, schedule publication, concern reporting or existing data. Audit history retains approving administrator, timestamp, IDs/labels, original/proposed allocation, metrics and feasibility evidence. There is no audit edit/delete endpoint or Django admin registration.

### Reproducible measurements

Synthetic fixture: three two-hour assignments initially assigned to instructor A, weekly limits A=12h and B=6h. Before: A=360min/6h/50%, B=0min/0h/0%; utilization min/max=0%/50%, spread=50 percentage points, variance=625 squared percentage points. One reassignment gives A=240min/4h/33.3333%, B=120min/2h/33.3333%; spread=0, variance=0, verified hard violations=0. Unequal contact hours are intentionally retained because utilization is balanced. A second fixture with four two-hour assignments and equal 12h limits recommends two changes together to produce 4h/4h, variance=0. Removing one selected change recalculates a nonzero variance. Fixed/unavailable alternatives and already-balanced unequal-hour inputs produce no recommended change. Tests repeat proposal generation with unchanged inputs and obtain the same allocation.

### Files and database safety

New: `schedules/services/workload_balancing.py`, `schedules/workload_views.py`, `schedules/test_workload_balancing.py`, `schedules/migrations/0018_workload_approval.py`, `templates/schedules/workload_proposals.html`, `tests/browser/render_workload.py`, `tests/browser/rendered_workload.html`.
Modified for T8: `schedules/models.py` (WorkloadApproval only), `schedules/urls.py`, `schedules/services/faculty_workload.py` (shared minute helper), `templates/schedules/resource_list.html` (Assignments entry point), `tests/browser/run_interactions.py` (optional workload mode), and this plan. Existing T7, navigation, CSS and database changes were preserved.

Migration 0018 depends on existing 0017 and creates only the approval audit table. Read-only `showmigrations schedules` in this workspace showed 0001?0012 applied and 0013?0018 pending. No migration was applied to the working database. Test migrations and browser fixture data use disposable databases only. Apply pending migrations explicitly in the intended environment before using the feature.


### Final T8 verification

- Final focused suite: **81 passed in 41.371s**, zero failures/skips/expected failures/unexpected successes. Modules: `test_workload_balancing` (19 new tests), `test_known_defects`, `test_ga_placements`, `test_faculty_timetable`, `test_finalized_protection`, `test_admin_publication_security`.
- New tests cover deterministic variance/explanations, selection recalculation, unequal limits, combined overloads, stale/tampered/expired tokens, explicit scope/comparability, rollback after a second assignment fails and audit failure, locked drafts and published snapshots, unavailability/credentials, joint and cross-term conflicts, administrator and faculty permissions, CSRF, HTTP preview/confirmation, no-change balanced inputs, and adjacent available periods. No tests were weakened or skipped.
- Final `manage.py check`: passed. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed (existing models.py LF/CRLF informational warning only). No full-suite run is claimed; historical full-suite baseline remains the previously executed 587.
- Browser: authenticated Django-rendered synthetic scope and proposal pages, **104 assertions passed** (13 at each combination). Light Mode: 1360/768/500/390 all passed. Dark Mode: 1360/768/500/390 all passed. Verified theme selection, headings, contained form controls/no horizontal page overflow, reviewed approval enabled, and changed-selection disabling/hiding stale metrics. Uses existing components/tokens with no new palette or CSS. The runner used normal approved browser execution. This is rendered-page browser verification, not physical-device, screen-reader or live-browser database submission testing; HTTP submission/permissions are separately covered by Django tests.
- Remaining limits: administrator-defined comparability, unscheduled terms only, bounded non-optimal search, per-term workload totals, SQLite-only approvals, no multi-process contention test, no representative institutional fairness study. These are explicit scope limits; no automatic publication or institution-wide optimization claim.

**Final: T8 Completed within the approved conservative scope, O5 Partially Verified, progress 8/16. No commits, push, deployment or T9 work.**


## T8 continuation: simplified discovery workflow

The original T8 implementation and its batch optimization/approval safeguards are retained. The entry workflow is now **Term + Department -> Analyze Workload -> review eligibility -> authorize the displayed candidate scope and confirm comparability -> Generate proposals -> Preview selected batch -> Approve**. This supersedes the earlier mandatory multi-selection instructions. T8 remains the same task; T9 is not started.

### Discovery and authorization

New `services/workload_discovery.py` identifies department/term-compatible assignments and instructor candidates without changing records. It reports total evaluated, eligible candidates, excluded assignments, qualified alternatives with feasible reassignments, readiness and per-assignment exclusion reasons. It reuses existing term-wide credential/override, workload, room, availability, conflict and placement validation. Excluded or locked assignments are never silently unlocked. Existing scheduled-term and search-size restrictions remain in force; users receive reasons and guidance to narrow filters or correct records.

**A discovered candidate is not an authorized reassignment.** The repository has no persistent reassignment-eligibility flag or formal instructor-comparability policy. Therefore the summary lists the exact candidate assignments and instructor group, and requires two explicit confirmations before proposal generation: authorization to consider those assignments, and confirmation of compatible teaching responsibilities/policies. Neither confirmation is preselected. Department membership alone does not authorize interchangeability. Approving actual changes is still a separate explicit batch confirmation. No new policy or database field is invented.

Discovery checks single candidate replacements conservatively before coordinated optimization. Consequently it can exclude a move that would only become feasible as part of a more complex swap or overload repair; no completeness/optimality claim is made. A zero-candidate result explains constraints without weakening them. Advanced exclusions can narrow a large scope, and exclusions remain visible in the summary.

### Optional Advanced Selection

A collapsed section offers four searchable checkbox lists: limit assignments, limit instructors, exclude assignments and exclude instructors. Empty limits mean discover within the chosen term/department. Each list has selected/shown counts, removable selected-item summaries, retained checkbox state during searches and field switches, keyboard-focusable native controls and inline invalid-scope/contradictory-selection feedback. Scheduled assignments have a locked label; other assignment labels explicitly say analysis is required. Server validation rejects mismatched term/department selections and contradictory include/exclude choices.

Changing scope hides old results and disables their actions until Analyze Workload is run again. New server-side analysis invalidates the previous proposal for that browser session, including stale back-button submissions. Signed, expiring analysis data is administrator-bound and fingerprint-checked before authorization. Signed form state retains advanced selections through proposal/preview steps. Starting another analysis in the same session supersedes the previous one, including another browser tab. No localStorage persistence of sensitive scope is introduced.

A loading status and duplicate-submit guard now accompany submissions while preserving the selected action. Results receive focus at the eligibility/proposal heading. The existing batch recalculation, signed selection verification, atomic SQLite approval, audit history and published-schedule safeguards remain unchanged. Explanations and percentage/contact-minute comparisons still use actual calculations. The established example remains 6h/0h at 12h/6h limits -> 4h/2h, utilization 50%/0% -> 33.33%/33.33%, variance 625 -> 0, one reassignment and zero hard conflicts.

### Files and verification

New in this continuation: `schedules/services/workload_discovery.py`, `schedules/test_workload_discovery.py`, `static/js/workload_balancing.js`.
Updated: `schedules/workload_views.py`, `templates/schedules/workload_proposals.html`, `static/css/app.css` (workload-scoped layout only), `schedules/test_workload_balancing.py` (HTTP tests use the explicit discovery/authorization step while retaining assertions), `tests/browser/render_workload.py`, `tests/browser/rendered_workload.html`, and this plan. Prior uncommitted application, migration, navigation and database work was preserved.

Final focused Django run: **29 passed in 34.299s** (19 retained T8 tests and 10 discovery tests), zero failures, skips, expected failures or unexpected successes. Coverage includes discovery without writes, locked-term exclusion, qualification/availability/limit reasons, empty groups, department restrictions, manual filters and selection persistence, conflicting filters, stale analysis, explicit authorization, and the existing batch safety/fairness regressions. No shared GA, assignment synchronization or approval-service logic changed. No new full-suite run is claimed.

`manage.py check` passed; `makemigrations --check --dry-run` found no changes. No new migration or working-database migration was performed. Existing migration 0018 is still required in any environment where it has not been applied. Git whitespace verification passed, with informational LF/CRLF warnings only.

Final browser verification: **336 assertions passed** (42 at each combination). Light Mode and Dark Mode each passed at 1360, 768, 500 and 390px. The isolated authenticated Django-rendered scope, eligibility and proposal pages verified checkbox search, counts, removable summaries, selection persistence, invalid-scope feedback, focus, stale-result hiding, no horizontal page overflow, and loading/submit-action preservation. No live browser database writes or physical-device/screen-reader testing is claimed; Django HTTP tests verify submission and authorization separately.

**Continuation complete: T8 Completed, O5 Partially Verified, roadmap unchanged at 8/16.** Limits remain unscheduled terms, administrator-confirmed comparability/authorization, bounded conservative candidate search and SQLite-only approval. No commits, push, deployment or T9 work.


## T9 room utilization and optimization verification (2026-10-22)

### Existing allocation and policies

The working tree was clean at the start of T9. Inspection was limited to room placement, scoring, shared validation, publication/manual-save boundaries, reporting and relevant tests. T8 workload balancing was not changed.

Rooms are shared resources in the current data model: there is no department owner, department whitelist or year-level restriction. Preserve that existing behavior; reporting by department does not imply ownership. Tests demonstrate sequential use of one room by departments REG and SHARED and year levels 1 and 2. Any future department-exclusive room policy or preference for consolidation rather than spreading requires an explicit institutional decision; none was invented for T9.

Hard constraints: active room; sufficient capacity for the effective section; exact required room type (including laboratory overrides); full-duration room, faculty and section availability; correct academic term; no overlapping faculty/section/room occupancy. Partially overlapping periods conflict, adjacent periods do not. Published schedules in overlapping different terms are checked at the validation/persistence boundary. Feasible GA placement domains reuse these individual rules; joint occupancy is checked during candidate construction/repair and fitness. Final shared validation can reject a GA result against current published occupancy rather than save a conflicting schedule. Manual-save calls full_clean transactionally, and publication invokes schedule-wide validation before finalization. No optimization benefit can override the hard-first fitness ordering.

The active room chooser samples/scans feasible placement domains, preserving diversity and avoiding occupied alternatives when possible. The older `_choose_room_for_assignment` capacity-band helper is not used by this path; it is not evidence of the current optimizer. Actual room optimization is in fitness: 0.15 per excess seat plus 10 when spare capacity exceeds section size; 2.5 times the absolute deviations of used-room hours from their mean; 8 per unused capacity/type-suitable room; and 3 per unused active room of a required type. Daily spread, gaps and other soft preferences also compete. These are heuristics, not a guarantee of optimal capacity fit, equal room-time utilization or minimal room changes. The room-spreading penalty counts raw scheduled hours, not percentages of available hours. Its suitable-room set uses capacity/type, not full available windows. T9 preserves these weights and tradeoffs because no new institutional utilization objective was approved.

### Confirmed reporting gap and minimal correction

A focused test reproduced an error: a schedule entry with an authorized section override of 10 students in a 30-seat room was reported at 66.7%, using its original 20-student section. The department filter likewise attributed it to the original department. `services/room_utilization.py:utilization_rows` now joins the optional section override, uses `effective_section.size` for seat occupancy and filters by the effective section's department. The corrected result is 33.3% occupancy; the override department receives 1 scheduled hour and the original department 0. CSV export is tested through the same service. No formula or user-interface redesign was introduced.

### Measurement definitions and evidence

- Room-time utilization = scheduled weekly contact hours / available weekly room hours * 100. Available intervals use the shared merge/subtract policy and operating calendar; sums retain precision until presentation. Aggregate utilization uses total hours, including unused rooms in the denominator.
- Reported seat occupancy = arithmetic mean of per-class `min(100, effective section size / room capacity * 100)`. It is not a duration-weighted institutional occupancy survey or a count of students physically attending.
- Unused seat-hours in the controlled fixture = sum of `(capacity - section size) * meeting hours`. This is a test measurement, not a new dashboard metric.
- Zero-availability/inactive-room behavior remains unchanged: zero percentage is displayed while saved scheduled hours remain visible. Reports describe the selected schedule; overlapping alternatives must not be summed as simultaneous occupancy.

Reproducible controlled fixture: two one-hour lecture meetings for 20 students, a 30-seat room and a 100-seat room, each available Monday 08:00-10:00. The feasible baseline uses the oversized room. The **existing** GA uses seed 19, population 20, 10 generations, elitism 2, crossover 0.8 and mutation 0.1; repeated runs yield identical meeting/room/day/time tuples. The source baseline is unchanged.

| Measure | Feasible oversized baseline | Existing GA output |
| --- | --- | --- |
| Scheduled room-hours | 2 | 2 |
| Available room-hours, including unused room | 4 | 4 |
| Aggregate room-time utilization | 50% | 50% |
| Used-room seat occupancy | 20% | 66.7% |
| Unused seat-hours | 160 | 20 |
| Unused rooms | 1 | 1 |
| Room type compliance | 2/2 lecture meetings | 2/2 lecture meetings |
| Hard violations | 0 | 0 |

This demonstrates better seat fit, **not increased room-time utilization**, and is not a before/after GA code improvement. No GA code was changed. A separate equal-capacity-room test confirms that distributing two adjacent meetings across two suitable rooms reduces the existing room penalty from 11 to 0, while an unneeded laboratory is not penalized. A larger room remains a valid fallback when the fitting room is unavailable. The cross-department/year-level fixture validates and publishes 3 hours in a shared room: 2 hours for the first department/year and 1 hour for the second.

### Scope and files

Only `schedules/services/room_utilization.py`, new `schedules/test_room_optimization.py`, and this development plan were changed. No models, migrations, GA optimization, T8 workload behavior, UI, real database records, commits, push or deployment were changed. No T10 work.

Limitations: these are controlled synthetic fixtures rather than representative multi-term institutional effectiveness measurements. Room-time distribution and capacity fit can compete; the existing weights do not establish an institutionally optimal tradeoff. Shared-room policy remains the implemented default, not a newly approved department-ownership policy. The reporting correction follows effective overrides, but no broader historical reporting redesign was attempted. O6 remains Partially Verified at thesis level despite verified constraints and scoped optimization evidence.


### T9 final verification and status

- Reproduced the reporting regression before the fix: one failure (`66.7 != 33.3`) with the other four initial T9 tests passing.
- After correction, the final **7 T9 tests passed in 2.890s**, covering effective-section seat/department metrics and CSV, hard-first capacity scoring, seeded real generation and baseline preservation, large-room fallback, shared rooms across departments/year levels and publication, transactional manual/publication rejection of capacity/type/inactive/unavailable rooms, and equal-capacity distribution scoring.
- Broader affected selection: **132 tests passed in 79.850s**, zero failures/skips/expected failures/unexpected successes. Modules: `test_room_optimization` (six tests at that run's collection), `test_room_availability_reporting`, `test_availability`, `test_ga_placements`, `test_ga_fitness`, `test_thesis_double_booking`, and `tests.SchedulingTestCase`. The seventh T9 test and the additional baseline-preservation assertion were subsequently included in the successful final seven-test run. These overlapping runs are not summed as unique tests. The logged mocked RuntimeError is an intentional passing diagnostic regression.
- `manage.py check`: passed. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed. All Python commands used the project virtual environment and tests used disposable databases. No new full-suite result is claimed.
- No templates/CSS/JavaScript changed, so browser layout testing was not necessary. CSV output and reporting consumers were exercised by Django tests.

**T9 Completed; O6 Partially Verified; roadmap 9/16.** No pending implementation in the stated scoped verification; institutional effectiveness and any future room ownership/tradeoff policy remain explicit limitations. T10 has not started.


## T10 completion record (2026-10-22)

**T10 Completed for bounded recurring repair; O7 Partially Verified; roadmap 10/16.** T11 and later tasks were not started. No working database changes, migrations, commits, push or deployment were performed by this task.

### Recovered work and approved decision

The earlier checkpoint inspected Copy to Draft, manual transactions, GA repair, qualifications, availability, publication and T8 locks. The initial 66 foundation tests passed. The interrupted implementation subsequently added the repair service, recurring rules, administrator screens, and 19 focused tests. The recovered regression log records **124 passing tests in 69.453s** (T10, copying/removal, corrections, GA repair, manual transactions, cross-term double booking, section availability and T8 workload balancing). These files were already present in the user's latest local commit when work resumed; no reset or reimplementation was performed.

The user explicitly approved **draft-entry instructor overrides**, and reaffirmed this in the resume request. T8's general locked-parent policy is unchanged. Only selected affected meetings and an administrator-selected group of at most three comparable instructors from the original instructor's department can be considered. A separate checked approval is required to apply the displayed batch. Qualifications (including existing matching credential overrides), availability, weekly workload and resource conflicts remain mandatory.

Work finished after resumption: explicit original/replacement instructor identity and reason in the approval audit; publication persistence assertions; comparison across equally sized authorized rearrangement scopes; a candidate-domain safety bound; narrowly scoped UI selectors and duplicate-submit handling; browser verification; seven-scenario measurement output; and this roadmap update.

### Workflow and reuse

1. Open a published schedule and select **Smart Repair**.
2. Describe a weekly recurring instructor/room outage, or select additional sections with recorded teaching assignments. Optional replacement authorization and limited rearrangement remain explicit.
3. Create an independently editable repair draft using `copy_to_draft`.
4. Preview affected classes, original/proposed placements, reasons, preserved/modified/added/unresolved counts, time/room/instructor changes, preservation percentage, hard violations and search time.
5. Explicitly approve the complete proposal. Atomic application uses the existing manual-edit revision transaction. It does not publish.
6. Review the draft and use the existing publication/replacement confirmation workflow.

The service reuses `AvailabilityPolicy`, credential eligibility, shared entry validation (including overlapping published terms), `PlacementOccupancy`, `Gene`, meeting requirement checks, existing GA soft scoring as the final tie breaker, protected audit records, and normal copy/manual/publication services. It adds bounded incumbent search because the existing GA candidate repair helper cannot represent draft-entry instructor overrides or approved change-event rules. GA weights, generation, parent assignments, T8 allocation and publication policies are unchanged.

Recurring restrictions are stored as `smart_repair_setup` records in the existing schedule audit trail, not global faculty/room availability. Shared entry validation enforces them during later manual edits and publication. Copy lineage carries them into subsequent copies. No new model or migration is needed. The original published schedule's availability and placements are unchanged.

### Search and approval safeguards

- Direct repair freezes unaffected entries and retains instructors. Room outages favor a suitable alternate room at the same time before moving a class.
- Only after direct repair fails does the service consider explicitly selected replacement instructors. No replacement can exceed its effective weekly teaching limit.
- If authorized, limited rearrangement considers moving one, then two, of the first six related meetings in stable meeting-ID order. It compares all explored scopes of the same size before widening.
- Within each authorized priority stage, feasible proposals compare `(unaffected changes, time changes, room changes, instructor changes, negative existing GA soft score)` lexicographically. Feasibility is mandatory; weights cannot buy permission to violate constraints.
- Search is deterministic under unchanged inputs. Limits: 40 meetings per draft, 100,000 candidate checks and 6,000 joint-search attempts. Candidate starts include the existing half-hour grid, original times and availability/outage boundaries. A limit does not prove infeasibility or global optimality.
- Additional sections use existing term teaching assignments only; missing required classes prevent a complete repair. No curriculum or instructor allocation is invented.
- Signed previews bind the administrator, draft, revision and scheduling-input fingerprint, and expire after 30 minutes. Changed inputs/source state, replay and other-user tokens cannot silently apply.
- Application reserves the SQLite writer, rechecks the revision/inputs and validates the whole resulting draft inside the transaction. Failed validation rolls back placements, revision and audit records. Separate-connection concurrent apply testing verifies that only one competing application commits; the other is stale or receives a lock rejection.
- The batch audit records original/replacement instructor IDs and names, entry and meeting IDs, recurring scenario and reason; its existing user/timestamp fields record approval. Publication retains the effective override rather than reverting to the shared parent instructor. Original finalized entries and their history remain protected.
- Admin-only GET/POST endpoints, CSRF, explicit confirmation and backend permissions are tested. Reporters cannot access repair drafts. There is no automatic publication.

### Reproducible measurements

`test_smart_repair.py` uses a synthetic two-meeting published timetable (Monday 08:00-09:00 and 09:00-10:00), recorded room/availability constraints and explicit scenario variations. No stochastic full regeneration is used. Measurements below are from the final focused run; seconds are machine-dependent, not service-level guarantees.

| Scenario | Preserved original meetings | Modified / added | Time / room / instructor changes | Hard violations in proposal | Unresolved | Search seconds |
| --- | --- | --- | --- | --- | --- | --- |
| Instructor outage, same instructor moved | 1/2 (50%) | 1 / 0 | 1 / 0 / 0 | 0 | 0 | 0.0555 |
| Approved eligible instructor replacement | 1/2 (50%) | 1 / 0 | 0 / 0 / 1 | 0 | 0 | 0.0784 |
| Qualified replacement lacks remaining capacity | No feasible proposal | No changes applied | Not applicable | Not applicable | 1 | 0.0578 |
| Room outage, suitable same-time alternative | 1/2 (50%) | 1 / 0 | 0 / 1 / 0 | 0 | 0 | 0.1365 |
| Room outage requiring a time change | 1/2 (50%) | 1 / 0 | 1 / 0 / 0 | 0 | 0 | 0.0481 |
| Additional authorized section | 2/2 (100%) | 0 / 1 | 0 / 0 / 0 | 0 | 0 | 0.0565 |
| No feasible room/time within authorized scope | No feasible proposal | No changes applied | Not applicable | Not applicable | 1 | 0.0474 |

Time/room/instructor change counts refer to pre-existing meetings; additions are counted separately. The preservation denominator is the draft's incumbent meeting set at preview time. Failed searches do not receive a fabricated zero-hard-violation score. Workload/qualification/room-type/capacity reasons come from actual checks; a bounded-search failure is explicitly scoped and does not claim mathematical infeasibility. Retry can create a new repair draft with revised inputs. No superiority to full regeneration, production-scale timing or institutional effectiveness is claimed.

### Verification

- Recovered broad regression: **124 passed**, 69.453s; no failures/skips/expected failures. Intentional mocked error logging belongs to passing rollback/diagnostic tests.
- Shared validation regression and earlier T10 checks: **25 passed**, 37.680s, including 10 existing validation-performance/parity tests; query budgets and diagnostics remained intact.
- Final changed T10 functionality: **19 passed**, 15.194s, including separate-thread/connection concurrency, explicit override audit/publication persistence, unresolved workload, source changes, stale/replayed previews, permissions/CSRF, inherited rules, alternatives, new sections, bounded search and limited rearrangement. No failures, skips, expected failures or unexpected successes. The final direct command exited successfully (0).
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed (line-ending conversion notices are not whitespace failures).
- Browser fixture: `tests/browser/render_repair.py` renders authenticated Django setup, successful preview and unresolved responses using an isolated in-memory database. `run_interactions.py --repair` passed **25 checks x 8 combinations = 200 checks**, at 1360/768/500/390px in both themes. Checked headings, contained controls/no page overflow, scenario visibility, checkbox focus/selection retention, unassumed authorization, disabled irrelevant replacements, before/after content, unavailable apply on failure and action-preserving duplicate-submit handling. Initial browser failures exposed and led to fixing an overbroad sidebar-details selector; the final run passed.
- Light Mode: all four widths passed; desktop screenshot inspected for layout/readability. Dark Mode: all four widths passed; mobile screenshot inspected for layout/readability. Existing semantic styles/theme persistence are reused. This is local Chrome evidence, not an assistive-technology or cross-browser certification.

Reproduce with `.\.venv\Scripts\python.exe manage.py test schedules.test_smart_repair --noinput`. Browser verification uses `.\.venv\Scripts\python.exe tests/browser/render_repair.py`, then `.\.venv\Scripts\python.exe tests/browser/run_interactions.py --repair`. Browser HTML/images are disposable generated artifacts. The renderer migrates only its isolated in-memory fixture; it never migrates the working database. No new full-suite result is claimed.

### Files and remaining limitations

T10 files: `schedules/services/smart_repair.py`, `repair_rules.py`, the small `conflicts.py` validation integration; `schedules/repair_views.py`, routes in `schedules/urls.py`; `templates/schedules/repair_start.html`, `repair_review.html`, the Smart Repair link in `schedule_detail.html`; `static/js/smart-repair.js`; `schedules/test_smart_repair.py`; `tests/browser/render_repair.py` and the `--repair` runner option; this plan. Existing T9 changes were preserved.

Weekly recurrence only: one-day absence, holidays and date-specific exceptions remain unsupported. Inherited recurring restrictions persist for the repaired schedule lineage; global availability is not changed. Scope revision starts a new draft from the source rather than silently deleting prior audit rules. Application is deliberately restricted to the tested SQLite backend. Fingerprints conservatively invalidate on unrelated scheduling-data changes. Search is bounded and may miss feasible placements outside its time grid, related-meeting subset or attempt limits. Representative school datasets, matched full-regeneration comparisons, other database engines and broader accessibility/browser testing remain unverified. These are explicit O7 evidence limitations, not permission to start T11.

### T10 follow-up: multiple unavailable days

Replaced the single weekday selector with Monday-Saturday checkboxes for room and instructor outages. One start/end time applies to all selected days. Backend validation requires at least one valid weekday; preview, search and later entry/publication validation enforce every selected day. Existing single-day audit records remain readable without migration. The preview lists weekday names. Different times for individual days are not part of this change.

Verification: 22 focused repair tests passed (15.599s), including multi-day rules, unaffected days, adjacent periods, invalid/empty selections and legacy records. Browser checks passed 26 assertions at each of four widths in both themes (208 total). Django system checks, migration dry-run and whitespace checks passed. No working database changes.

## T12 cross-role verification (2026-10-22)

**Completed for the requested focused verification scope; roadmap 11/16.** The user explicitly authorized T12 while deferring T11 measurements. **T11: Manual Evaluation Pending. O4: Not Yet Verified** until actual matched manual/automated comparison measurements exist. No T11 implementation or T13 work was performed.

### Evidence and results

Executed existing tests only; no duplicate tests or new infrastructure:

- `test_admin_publication_security` (17): role/model permissions, direct admin and application endpoints, escalation attempts, CSRF/POST, authorized publication/snapshots, invalid publication rejection and scoped exports.
- `test_student_timetable` (4): real HTTP login, published timetable details, draft exclusion, empty/missing-profile states, rejected mutation routes and unchanged records/audits.
- `test_faculty_timetable` (5): HTTP login, own published timetable/workload, effective instructor filtering, read-only scheduling, availability ownership and rejected cross-owner GET/POST.
- `test_concerns` (10): Student/Faculty submissions, published/authorized references, reporter-only visibility, administrator review/status/history, stale/invalid requests, safe text, CSRF and schedule immutability.
- `test_diagnostic_access` (15): role-scoped diagnostics, private metadata exclusion from timetables/exports, direct JSON and correction endpoints, import ownership and allowed administrator actions.
- Three selected `GenerationLockTests`: `test_success_records_run_and_schedule_before_release`, `test_admin_and_csrf_enforced_before_acquisition`, `test_generation_preserves_published_and_archived_history`.
- The above combined run: **54 passed in 26.755s**.
- Four selected `SchedulingTestCase` privacy tests: `test_student_browse_only_shows_entries_for_own_section`, `test_student_empty_timetable_and_other_section_schedule_access`, `test_student_browse_respects_effective_section_overrides`, `test_faculty_cannot_open_schedule_with_no_assigned_entries`: **4 passed in 5.711s**.

**New executions: 58 passed; zero failures, skips, expected failures or unexpected successes.** No full-suite execution or new full-suite count is claimed.

Reused unchanged prior evidence rather than rerunning successful tests: T8's `test_workload_balancing` module in the 124-test T10 regression run covers role-administrator approval, denied faculty approval, explicit confirmation, signed/stale scope, CSRF and atomic audited batches. The latest **22 passing Smart Repair tests** cover administrator-only HTTP/service access, explicit approval, multi-day constraints, workload/qualification restrictions, unchanged parents/original schedules, publication retention, rollback and competing applications.

### Representative UI evidence reused

Existing authenticated Django-rendered browser fixtures and `run_interactions.py` already cover all requested roles in Light and Dark Mode at 1360/768/500/390px: Student timetable **104 assertions**, Faculty timetable/workload **104**, Administrator workload workflow **336**, and latest Administrator Smart Repair **208**. Recorded checks include theme behavior, content visibility, control containment, responsive overflow, and relevant interaction states. No affected UI or shared authorization code changed during T12; no additional browser executions were needed or claimed. HTTP login and permissions were freshly tested with Django clients, not a live-server browser login.

### Final checks and limitations

`manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed. All test data used Django's disposable database; the already-modified working SQLite database and all existing uncommitted implementation files were preserved.

No confirmed permission, privacy, publication or workflow defect was found in the executed/reused coverage. **Only this development plan changed for T12.** This is focused regression verification, not an exhaustive security audit, physical-device/screen-reader certification, live deployment test or full-suite rerun. Previously documented SQLite/search/weekly-recurrence limits remain. Manual preparation-time comparisons and O4 effectiveness remain unverified. No commits, push or deployment.

## T13 objective evidence and defense checklist (2026-10-22)

**T13 Completed: evidence review/documentation, not institutional acceptance of every objective. Roadmap 12/16.** Objective statuses below are unchanged from their supported summaries. T11 remains **Manual Evaluation Pending**; T14-T16 remain Deferred. This review reused the existing T2-T12 records and their cited tests/measurements; no new tests, browser runs, application changes or database operations were needed. Historical test totals are evidence from their recorded runs, not a newly executed full-suite result.

### Consolidated O1-O7 matrix

| Objective / current status | Implemented functionality | Existing supporting evidence | Limits of the evidence | Needed for full institutional verification |
| --- | --- | --- | --- | --- |
| **O1 conflict detection: Partially Verified** | Shared effective faculty/room/section overlap checks, partial-time intersections, meeting requirements and backend manual/publication rejection. | T2: six `test_thesis_conflicts` tests; 136-test focused combined run. T12 reconfirmed publication/security paths. Adjacent classes and legitimate parallel sections are accepted. | Validates recorded requirements; assignment coverage does not establish authoritative curriculum completeness. No certification of every institutional academic rule. | Academic approval of the conflict/subject-rule matrix; reconcile required curriculum against recorded assignments; demonstrate detection and absence of false positives on representative term data. |
| **O2 double-booking: Verified within recurring-term model / SQLite** | Instructor/room conflicts within a schedule and across overlapping published terms; transactional manual edits, final GA save and publication. | T3: eight focused tests, real separate-connection races, recorded 575-test full-suite result; `test_thesis_double_booking`. T12 authorization/publication checks; T10 concurrent apply evidence. | Alternative drafts are independent. Weekly recurrence derives from term dates; holidays/cancellations and other database engines are not certified. | Replay representative overlapping terms, instructors and rooms using approved calendars; confirm the deployed database and concurrency behavior. Record institution-approved exception handling. |
| **O3 availability: Verified within fixed-section model** | Faculty and administrator-managed section availability enforced in GA domains, manual editing and publication; faculty self-service ownership enforced. | T4: 12 new focused tests and recorded 587-test full-suite result; `test_section_availability`, `test_availability`. T12 Faculty ownership tests passed. | Section constraints represent fixed cohorts, not individual student preferences; no term-specific availability or holiday exceptions. | Obtain approved faculty/section windows and section membership; confirm fixed-section assumptions; reconcile actual classes against availability and record exceptions. |
| **O4 preparation-time reduction: Not Yet Verified** | Reproducible GA runs, recorded seeds/configuration/timing and benchmark/report tools exist. | Existing reproducibility/benchmark/report tests establish tooling, not a manual comparison. | Solver runtime excludes preparation, correction and approval; no measured end-to-end reduction or statistical significance is established. | Complete the matched manual-versus-SchedEase protocol below. Keep T11 Manual Evaluation Pending until measurements exist. |
| **O5 workload balancing: Partially Verified** | Separate administrator-approved allocation proposals compare workload percentages, enforce qualifications/availability/limits, and audit atomic approval. | T8 synthetic case: A/B 6h/0h with 12h/6h limits becomes 4h/2h; percentage variance 625 to 0, spread 50 to 0 points, zero hard violations. `test_workload_balancing`; approval/lock evidence reused by T12. | Unequal hours can be legitimate; timetable GA does not itself reassign faculty. Scheduled parents remain locked outside approved draft-entry repair overrides. | Approved comparable instructor groups and workload ceilings; representative terms; before/after percentage variance, spread, overloads, eligible/excluded assignments and administrator acceptance. Do not equate equal hours with fairness. |
| **O6 room optimization: Partially Verified** | Feasible room capacity/type/availability allocation, capacity-fit and room-use soft scoring, and utilization reporting. | T9 seeded fixture (seed 19): seat occupancy 20% to 66.7%, unused seat-hours 160 to 20, zero hard violations; room-time utilization stays 50%. `test_room_optimization`, room availability/report tests. | Controlled existing-GA behavior, not a newly improved optimizer or proof of optimal room use. Rooms have no department-exclusive ownership policy. | Representative sizes, departments, levels, specialized rooms and availability; compare feasible baselines with identical demand. Separately report room-hours/available-hours, seat fit, unused seat-hours, compatibility/conflicts and departmental distribution. Approve consolidation/spreading preferences. |
| **O7 adaptability: Partially Verified** | Recurring instructor/room outages (multiple weekdays), approved draft-entry replacements, new-section insertion, bounded low-disruption search and separate publication. | T10 seven synthetic scenarios; 22 focused tests. Successful outage repairs preserve 1/2 meetings; section insertion preserves 2/2 and adds one; valid proposals have zero hard violations. No-capacity/infeasible cases remain unresolved without changes. T12 reused safeguard evidence. | Weekly recurrence, SQLite application and bounded search; no one-date exceptions, global-optimality guarantee or representative full-regeneration comparison. | Representative outage/new-section cases at realistic scale; matched targeted repair/full regeneration/manual correction with the same inputs and constraints. Record preserved/modified/added/unresolved meetings, time/room/instructor changes, feasibility, response time and reviewer acceptance. |

### Defense demonstration checklist (prepared; not newly executed)

Use a disposable demonstration database and anonymized/synthetic records. Identify which evidence is controlled testing and which, if later collected, is institutionally observed. Preserve original published schedules throughout demonstrations.

- [ ] Show the academic term, assignments, meeting requirements, availability, room capacities/types and input provenance; explain that completeness is checked against recorded requirements.
- [ ] Generate and review a schedule; show validation before explicit publication and the resulting published version. Keep seed/configuration and run record available.
- [ ] Demonstrate faculty, room and section overlaps, including partial overlap; show backend rejection and an adjacent valid time. Demonstrate overlapping published-term occupancy separately from independent drafts.
- [ ] Show allowed/unavailable faculty and section windows and rejected unauthorized availability edits.
- [ ] Log in as Faculty and Student; show own published timetable, Faculty workload, hidden drafts/other records and a concern submission. Switch to Administrator to review/respond without changing the timetable. T12 provides HTTP permission evidence.
- [ ] Show workload proposal scope/comparability, before/after percentage metrics, explicit batch approval/audit and an overload/unqualified rejection. Label the 625-to-0 variance example synthetic.
- [ ] Show room capacity/type compliance and report denominators. Explain why improved seat fit in T9 did **not** increase aggregate room-time utilization.
- [ ] From a published schedule, create a repair draft; select unavailable days/times, preview preserved/changed classes, explicitly approve any instructor replacement and publish separately. Show an unresolved no-capacity case and unchanged parent/original entries.
- [ ] Present the O1-O7 matrix and supporting test references. Separate successful controlled tests from institutional effectiveness; disclose O4's missing comparison and O5-O7's representative-data limitations.

### Minimum fair manual-versus-SchedEase evaluation (T11 pending)

1. **Matched problem:** use identical anonymized term data, sections, meetings/durations, faculty qualifications/limits/availability, rooms and constraints. Record dataset provenance/version and approved corrections. Both methods must meet the same completeness and zero-hard-conflict criteria.
2. **Defined timing:** agree on start/end events covering data preparation/entry, initial scheduling, corrections, validation and approval. Record phase times and total elapsed/active time consistently; distinguish breaks, setup/training and external waiting. Solver runtime alone cannot answer O4.
3. **Participants and environment:** identify qualified schedulers, experience/training and consent where applicable; record manual tools, SchedEase/code version, hardware/database, seed/configuration and run identifiers. Counterbalance method order where practical to reduce practice effects.
4. **Repeated observations:** agree on representative cases and repetitions before collection. Preserve timestamps/raw logs, failed/incomplete attempts, unresolved constraints, correction counts and final schedule quality. Do not select only successful or fastest runs. Determine an adequate sample with the thesis adviser before making significance claims.
5. **Comparison and reporting:** pair results by case; report manual and SchedEase times, differences and variability alongside feasibility/quality. Percentage reduction = `(manual time - SchedEase time) / manual time * 100` when manual time is positive; negative values indicate slower preparation. Report uncertainty and justify any statistical method. Do not claim significance or savings without actual observations.

For O5-O7, retain the representative measurements listed in the matrix with raw inputs/outputs, seeds/configurations where relevant, equal comparison constraints, failed cases and institutional reviewer decisions. No measurements have been invented and no T11 benchmarking features were added.

### Review outcome

No concrete evidence inconsistency required a new test. The O7 summary was refreshed from the earlier 19-test checkpoint to the already-recorded 22-test multi-day follow-up without changing its Partially Verified status. `git diff --check` passed after documentation changes. Only this plan was modified for T13; all existing uncommitted application and working-database changes were preserved. T13 documentation completion does not close T11 or upgrade O1/O4/O5/O6/O7. No T14 work, commits, push or deployment.

## T15 essential administrator UI correctness (2026-10-22)

**Completed; roadmap 13/16 (81.25%).** Resumed the already-implemented fixes and completed documentation; successful verification was not repeated. T11 remains Manual Evaluation Pending, T14 Deferred and T16 Not Started. O1-O7 statuses are unchanged. Historical UI/UX progress remains 9/24; this scoped review does not complete historical tasks wholesale.

### Essential workflows reviewed

- Record editors already share headings/actions, preserve entered values and validation feedback, and retain specialized assignment/generation controls. Reused the existing four `test_record_editors` tests and prior responsive/editor evidence.
- Draft creation/update, unchanged-form handling, restoration/final-save cleanup, owner-only discard, stale-record detection and unauthorized/invalid submissions already have backend coverage. Six existing draft tests were executed; only the confirmed browser state issue below needed correction.
- Generation loading feedback already exists and its focused Django test passed. Existing T2/T10 conflict explanations and validation, T12 publication/confirmation/CSRF evidence, and Smart Repair approval/rollback tests were reused; no scheduling or permission changes were needed.
- Reviewed relevant historical UI items 3.2/3.3 (guidance, validation and truthful saving states); no table, navigation or broad design work was resumed.

### Confirmed fixes

1. **Late autosave response could falsely mark newer edits saved.** The previous callback cleared the dirty flag unconditionally; overlapping requests could also be outstanding. `static/js/app.js` now permits one draft request at a time, compares current field values with the acknowledged payload, retains the pending state when they differ, and queues the newer draft. Failed requests show the existing error feedback and can retry. Payloads, debounce intervals, endpoints and backend persistence rules are unchanged.
2. **Smart Repair actions could remain disabled after browser history restoration.** `static/js/smart-repair.js` now resets transient submission/busy/loading state on `pageshow`, restores original button states, and removes generated action inputs/status messages. This prevents stale duplicate action values when submitting again. Signed previews, confirmation requirements and backend stale-request checks remain unchanged.

### Verification recovered from the interrupted session

- **11 focused Django tests passed in 10.411s**, zero failures/skips/expected failures: four `test_record_editors` tests; `SchedulingTestCase.test_form_draft_is_created_updated_and_does_not_create_official_record`, `test_unchanged_form_does_not_create_a_draft`, `test_draft_restores_and_final_create_removes_it`, `test_user_can_only_discard_their_own_draft`, `test_edit_draft_detects_newer_official_record`, `test_non_admin_cannot_save_drafts_and_invalid_json_is_safe`, and `test_generate_page_has_accessible_loading_state`.
- Existing `interaction_states.html` gained delayed-response/newer-edit, serialized-request, failure and successful-retry assertions. `run_interactions.py` passed **28 checks x 4 combinations = 112** (Light/Dark at 1360/390px).
- Existing Django-rendered Smart Repair fixture gained history-restoration/button/transient-state assertions. `run_interactions.py --repair` passed **28 checks x 8 combinations = 224** (Light/Dark at 1360/768/500/390px), retaining selected-day, approval, preview, error-state and no-overflow checks. **336 browser assertions total**, all passed.
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed, including the final documentation update. No full suite or unrelated browser pages were rerun.

### Files and limits

T15 changed only `static/js/app.js`, `static/js/smart-repair.js`, `tests/browser/interaction_states.html`, the existing-in-progress `tests/browser/render_repair.py`, and this plan. Other pending application changes and the already-modified working database were preserved; no working-database writes, migrations, dependencies, commits, push or deployment.

Browser autosave tests deliberately control network response timing; history recovery is tested through a persisted `pageshow` event, not physical-device navigation or a live-server end-to-end session. Existing editor responsive evidence is reused, not newly rerun for every editor. Full screen-reader/cross-browser evaluation, broader wording/field guidance and unrelated historical UI improvements remain outside T15. No T14 or T16 implementation was performed.

## T16 final focused usability/accessibility verification (2026-10-22)

**Completed within the requested targeted QA scope; roadmap 14/16 (87.5%).** This is not a claim of full WCAG compliance or comprehensive device/assistive-technology certification. T11 remains Manual Evaluation Pending; T14 remains Deferred; O1-O7 statuses and historical UI/UX task progress are unchanged.

### Coverage and reused evidence

| Critical area | Evidence reviewed/reused; no unnecessary rerun |
| --- | --- |
| Administrator record editing, invalid forms and autosave | T15's 11 passing focused Django tests and 112 browser assertions: retained values, recoverable errors, serialized draft requests, accurate pending/error/saved feedback; existing shared-editor responsive evidence. |
| Generation, conflicts and publication | T12's 58 focused passes cover authorized generation/publication, invalid publication rejection, CSRF and object privacy; T2/T10 cover conflict explanations and transactional safeguards. Existing generation loading test and T15 evidence retained. |
| Workload proposal approval | T8's 336 browser assertions and approval tests reused: scope labels, selection/focus, stale-result invalidation, explicit authorization and responsive controls. |
| Smart Repair | T10/T15 tests retain preview, explicit approval, unresolved/error behavior, duplicate-submit prevention and history-recovery states. Newly tested description/error associations below. |
| Faculty timetable/availability and Student timetable/concerns | T12 HTTP access/ownership checks plus recorded Student/Faculty browser evidence (104 assertions each), concern browser coverage and response/status tests reused. No fresh live-account walkthrough is claimed. |
| Navigation, dialogs, focus and contrast | Existing sidebar evidence (336 assertions) covers keyboard containment/restoration, Escape, drawer bounds and persistence; T15 interaction checks retain login-dialog/help focus and Escape handling. Design-token measurements document primary text contrast of 5.47/7.58/9.48:1 in Light and 8.05/10.13/11.89:1 in Dark for default/hover/active; focus/surface ratios 7.58:1 and 11.76:1. These are recorded token measurements, not newly measured universal component contrast. |

Existing evidence covers desktop/tablet/mobile widths 1360/768/500/390, theme behavior, contained forms, table-only horizontal scrolling and action visibility. Physical touch ergonomics, every target-size/spacing combination and all zoom/device conditions remain unverified. No exhaustive page matrix or full suite was rerun.

### Confirmed accessibility defect and smallest correction

The custom Smart Repair form rendered help paragraphs without the IDs referenced by accessible descriptions, and did not explicitly link validation errors to controls. Multi-checkbox fields also needed a consistently named group.

- `RepairForm` now supplies `aria-describedby` references for rendered errors and applicable help text.
- `repair_start.html` renders matching IDs, announces field errors with `role="alert"`, and uses fieldsets/legends for grouped checkbox fields. Existing labels, Django invalid-state attributes, validation rules and preserved form values are unchanged.
- The existing repair browser fixture now includes an actual invalid Django POST response and verifies resolved descriptions, named/labeled weekday controls, visible keyboard focus, error association and retained selections. No new testing infrastructure, CSS redesign or scheduling behavior was introduced.

### New verification

- Existing `SmartRepairTests.test_http_authorization_csrf_confirmation_and_method`: **1 passed in 0.819s**, no failure/skip/expected failure; validates the affected form route and its existing authorization/confirmation handling.
- Existing `run_interactions.py --repair`: **42 assertions x 8 theme/width combinations = 336 passed**, including the new invalid-form/accessibility checks and existing preview, selection, loading/history recovery and overflow checks. Light and Dark Mode each passed at 1360/768/500/390px.
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `git diff --check`: passed. The fixture uses an isolated in-memory database; the working database was not modified.

### Files and limitations

T16 changes: `schedules/repair_views.py`, `templates/schedules/repair_start.html`, existing `tests/browser/render_repair.py`, and this plan. All earlier uncommitted changes were preserved.

Automated DOM/focus checks establish the tested associations and interactions, not actual screen-reader speech. Real assistive-technology sessions, physical touch devices, Firefox/Safari, comprehensive zoom/reflow and universal contrast/target-size certification remain outstanding. Browser fixtures render Django responses offline; live-server end-to-end navigation is not claimed. Existing status announcements are retained; no claim is made that every success/error message across the application has been audited. These limits are explicitly recorded rather than implying full WCAG conformance. No T11/T14 implementation, new dependencies, commits, push or deployment.
