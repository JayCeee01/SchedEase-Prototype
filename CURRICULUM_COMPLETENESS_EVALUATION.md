# Task 7.1 — Curriculum completeness evaluation

## Decision: Outcome D — academic clarification required

**Evaluation only; no application changes are justified by the available evidence.**
SchedEase validates completeness against its recorded assignments, meetings and
course hours. It cannot establish completeness against an authoritative curriculum
because no such curriculum structure or approved course-to-program/year/term
requirement list is represented in the repository.

No approved thesis scope document explicitly requiring that additional behavior
was found. This does **not** prove the feature is out of scope, nor prove that the
current system meets every institutional requirement. Outcome D is therefore more
accurate than A (sufficient for all documented thesis requirements), B (confirmed
out of scope), or C (a sufficiently specified implementation gap).

Task 7.1's evaluation can be completed while the academic decision remains open.
Do not implement a curriculum module or new publication gate until the questions
below have authoritative answers.

## Objective and evidence inspected

The objective is to distinguish existing scheduling completeness from curriculum
completeness and identify whether any new validation has an evidenced requirement.
The working tree was clean at the start. Inspection covered:

- `schedules/models.py` and migration history `0001`–`0015`, particularly initial
  academic structures, meeting fields (`0004`), schedule-entry uniqueness (`0005`),
  parent assignment migration (`0008`), finalized/term guards (`0010`/`0011`) and
  historical snapshots (`0012`). No curriculum model was found.
- `services/meetings.py`, `conflicts.py`, `ga.py`, `placements.py`, `publication.py`,
  `manual_edits.py`, assignment models/forms, `views.py`, and the academic importer.
- Existing meeting-requirement, known-defect, term-protection, generation-diagnostic
  and copy/remove tests; the complete suite verifies other preserved safeguards.
- README, SYSTEM_AUDIT, ACADEMIC_IMPORT, REPRESENTATIVE_SAMPLE_REPORT,
  GA_EVALUATION_REPORTS, and prior-task validation/protection documentation.
- Repository searches for curriculum, required courses, enrollment and approved
  thesis scope, plus Markdown/PDF/Word document inventory. No formal approved
  thesis specification or authoritative curriculum matrix was located.

This is a repository-based evaluation, not an institutional curriculum audit.
External documents mentioned by reports were not independently verified.

## Existing academic data structures

| Actual model | Relevant relationships and meaning |
| --- | --- |
| `Department` | Code and name; organizational grouping. |
| `Program` | Belongs to a department. No program-course requirement relationship. |
| `YearLevel` | Numeric level and label. No course requirement mapping. |
| `AcademicTerm` | Name, school year, start/end dates, active flag. No curriculum-version/cohort mapping. |
| `Section` | Program, year level, name, size and optional faculty adviser. Term participation is expressed through assignments, not a curriculum roster. |
| `Subject` | Course code/title, department, units, lecture/lab hours and required room type. Department membership does not establish that every section must take it. |
| `Faculty` / credential models | Assigned teacher, workload limit, qualifications, equivalents and documented overrides. These establish teaching eligibility, not required student courses. |
| `Assignment` | Parent relationship joining term, subject, section and faculty. No separate approval-status field or authoritative curriculum source. |
| `TeachingAssignment` | Individual meeting with component, index, duration and room requirement; normally attached to its parent and synchronized on normal saves. The parent FK remains nullable for legacy compatibility; it is not a curriculum relationship. |
| `Schedule` / `ScheduleEntry` | A term-specific timetable and placements for teaching meetings, including controlled override fields. |
| `Student` | Section membership; no individual curriculum, elective selection or course enrollment model. |
| `ScheduleSnapshot` / audit / diagnostic models | Preserve finalized content, changes and validation evidence. They do not define the courses that should have been entered. |

`ACADEMIC_IMPORT.md` explicitly states that there is no separate Section Course
Enrollment entity: the importer reuses Assignment and TeachingAssignment.
Migration `0008` groups legacy meetings by term/course/section/faculty; it does not
derive required courses from an academic curriculum.

## Three distinct completeness claims

1. **Assignment completeness:** Recorded teaching requirements for the schedule's
   term are represented. Here “required” means entered into the scheduling inputs,
   not independently verified as curriculum-approved. Assignment has no approval flag.
2. **Meeting completeness:** Recorded assignments have the required lecture/lab
   minutes and meeting components derived from their Subject records, and those
   meetings are represented correctly in a finalized schedule.
3. **Curriculum completeness:** Every course required by an authoritative, applicable
   curriculum is assigned and scheduled for the correct section and term, including
   any approved exceptions. The system currently has no independent source for
   this expected-course set.

Example: if Course A is recorded with 120 lecture minutes and one required meeting
is omitted, existing validation can report it. If a curriculum requires Course B
but nobody creates its Assignment, the system cannot infer that omission from
department membership, course catalog entries or the section's year label.

## Gap analysis and existing enforcement

| Requirement | Existing support and evidence | Specific limitation | Classification / recommendation |
| --- | --- | --- | --- |
| Recorded assignment completeness | `conflicts.schedule_validation_issues()` reports every missing TeachingAssignment in the schedule term as `UNSCHEDULED`; `scheduled_requirement_errors()` also examines every parent Assignment, including empty parents. | A course absent from both parent and meeting inputs has no expected record to compare against. | Working recorded-input protection; preserve it. Formal missing-course detection needs academic clarification. |
| Meeting/component completeness | `meeting_requirement_errors()` rejects empty meeting sets, repeated indexes, unsupported components, invalid durations and lecture/lab totals differing from Subject hours. Assignment formsets/imports reuse it; final checks use actual scheduled time spans. | The stored Subject hours are the authority; correctness against an external curriculum is not established. | Existing functionality needs no duplicate validator. |
| Parent/meeting consistency | Assignment saves synchronize shared fields transactionally; TeachingAssignment saves inherit parent fields. Referenced assignment revisions are restricted. See Task 2.1 and term-protection tests. | These are relationship-consistency protections, not course-coverage approval. | Preserve current safeguards; no new model assumption. |
| Term consistency | Entry validation and migration `0011` guards enforce matching schedule/meeting/parent terms; forms scope choices to the term. | No rule maps a curriculum semester or cohort version to AcademicTerm. | Existing term safety is supported; curriculum applicability is unspecified. |
| Duplicate meetings/assignments | Parent uniqueness is `(term, subject, section, faculty)`; meeting uniqueness is `(term, subject, section, component, meeting_index)`; entry uniqueness is `(schedule, assignment)` where assignment means TeachingAssignment. GA also rejects duplicate meeting IDs. | These keys do not determine whether a different faculty/course combination was academically unintended. Parent uniqueness is not simply section/course uniqueness. | Confirmed integrity rules work; do not invent stricter co-teaching/duplicate-course policy. |
| GA input/output completeness | GA loads the selected term's TeachingAssignments, rejects an empty input set and invalid/duplicate output IDs, and performs full final validation inside the lease-protected saving transaction. Feasible placements validate each recorded requirement. | It schedules recorded inputs rather than creating missing curriculum assignments. | Preserve GA behavior; do not add curriculum inference to fitness or operators. |
| Publication completeness | `publication.publish()` invokes full schedule validation under the existing writer transaction before publishing and snapshot capture. Missing recorded meetings and component totals block publication. | It cannot block publication for courses absent from an unknown curriculum. No institution-wide expected section roster is modeled. | Sufficient for recorded scheduling requirements, not proof of curriculum coverage. New gates require explicit scope approval. |
| Editable incomplete drafts | Draft meeting removal and copy-to-draft retain editable intermediate schedules, audit history and later validation. | A draft can intentionally be incomplete while corrected. | Preserve; do not require curriculum completion merely to save a draft. |
| Program/year curriculum consistency | Section stores program/year; Subject stores department. | No curriculum version, required-course list, elective group, approved substitution or cohort applicability exists. | Missing optional capability whose mandatory status is unconfirmed, not a demonstrated defect. |

An entirely unrepresented section/course cannot generate an “unscheduled class”
message. This is the boundary of the available data, not evidence that the current
missing-meeting checks malfunction. No newly confirmed defect requiring a Task 7.1
code fix was established.

## Evidence from requirements and tests

- README describes an academic scheduling system managing master data, teaching
  assignments, constraints and generated schedules. It does not define formal
  curriculum validation or automatic curriculum-to-section assignment.
- SYSTEM_AUDIT describes publication checks for missing/unscheduled **term
  requirements**. Current code identifies those requirements from recorded
  assignments. The document predates several completed tasks and is not an
  approved institutional curriculum policy.
- REPRESENTATIVE_SAMPLE_REPORT calls its selection “complete sections” in a
  source-workbook extraction context. It does not compare that workbook to a
  curriculum matrix; the wording is not evidence of curriculum completeness.
  Its synthetic capacities/credentials are explicitly not institutional facts.
- GA_EVALUATION_REPORTS describes offline experiment reporting. Thesis-ready
  charts and measured GA feasibility do not certify that required curriculum
  inputs were entered, and do not establish an approved thesis scope.
- `test_meeting_requirements.py` tests exact component totals, valid split
  meetings, rejection of missing labs/incomplete GA output/duplicate output,
  and publication blocking even when existing meeting IDs are all present.
- `test_known_defects.py` preserves parent synchronization and scheduling checks;
  `test_term_protection.py` verifies mismatched terms and finalized restrictions;
  `test_generation_diagnostics.py` verifies structured references and atomic failure
  recording; `test_copy_remove.py` preserves draft correction and stale-edit safety.

These support assignment/meeting completeness. None supplies an independent
required curriculum list or proves every approved course was entered.

## Questions for the academic head, adviser or administrator

Before approving any implementation, establish:

1. Does the approved thesis scope require a curriculum audit, or only feasible
   scheduling of administrator-supplied assignments? Identify the approved text.
2. What is the authoritative curriculum source, who approves it, and how are
   versions mapped to programs, cohorts, year levels and actual academic terms?
3. Which sections must have offerings in a term, including irregular students,
   inactive sections, electives, repeated courses and merged/cross-listed classes?
4. How are substitutions, exemptions, deferred offerings and co-teaching approved?
   Is missing-course feedback advisory, or must it prevent publication?
5. Who maintains the expected-course list, approves exceptions, and reviews the
   comparison? Which evidence and audit history must be retained?
6. Are the stored lecture/lab hours and units authoritative and current for each
   curriculum version, and may these differ between cohorts?

These are unresolved requirements, not proposed default answers. No user input
is needed to finish this evaluation document; it is needed before implementing
unsupported academic behavior.

## Recommendation and implementation decision

Retain the existing recorded-assignment and meeting validation. Describe the
current result as **complete against entered scheduling requirements**, never
“curriculum complete” without independent curriculum evidence.

If formal coverage is later approved, first obtain a versioned, authoritative
expected-course dataset and exception policy. A future comparison could report
expected versus assigned versus scheduled courses, but its data model, workflow
and publication consequences must be decided separately. This is a possible
enhancement, not an approved implementation specification.

For Task 7.1: no code, test, model, migration, dependency, GA rule, constraint,
permission or publication behavior is changed. No artificial tests are added.
Only this evaluation and a README reference are created/updated.

## Verification

- Focused existing suites: **62 passed in 30.298 seconds**.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- Full suite: **496 passed in 275.476 seconds**; all prior tests preserved, no new
  tests added. Zero failures, errors, skips, expected failures or unexpected
  successes. Test runner exit code: 0.
- `git diff --check`: passed. Final change review confirms only this evaluation
  and the README reference changed; application behavior and schema are unchanged.

**Final status:** Task 7.1 evaluation complete, Outcome D. Curriculum implementation
remains deferred pending academic clarification. No commit was created and Task
7.2 was not started.

Limitations: no approved external thesis/curriculum source was supplied or found;
no institutional decisions are inferred. Verification uses existing automated
tests, not a live browser or a comparison with actual registrar curriculum data.
