# Final acceptance test matrix — Task 8.4

Verification date: 2026-10-20. This matrix distinguishes server-side integration evidence from browser and deployment acceptance. It accompanies [the final report](FINAL_SYSTEM_VERIFICATION_REPORT.md).

## Evidence conventions

- `AW` = `schedules.test_acceptance_workflows.AcceptanceWorkflowTests` (four new tests).
- Other references are module/test names under `schedules/`; use `python manage.py test schedules.<module>` to reproduce a module.
- Pass means the named automated assertion or command was executed successfully. It does not certify live deployment, browser behavior or every possible input.
- Full suite executed successfully: **551 passed in 290.845 seconds** (547 baseline + four new); zero failures, errors, skips, expected failures or unexpected successes. Every automated row below was executed; no pending test result is represented as a pass.

## Workflow matrix

| ID | Functional area | Scenario | Expected result | Actual result / evidence | Status |
| --- | --- | --- | --- | --- | --- |
| AT-001 | Data preparation | Create term, department/program, course, sections, qualified faculty, rooms, availability and lecture/lab meetings through administrative forms | Records and relationships accepted by real forms; GA consumes them | Every AW setup uses HTTP resource creation; two assignments, four meetings, dated qualifications and explicit availability | Pass |
| AT-002 | Invalid data | Duplicate section and incomplete laboratory minutes | Actionable error, no duplicate or partial assignment | AW `test_invalid_preparation_and_busy_generation_preserve_state_then_retry`: duplicate message and LABORATORY totals 30 error; assignment count unchanged | Pass |
| AT-003 | Generation | Feasible qualified lecture/lab dataset | Four meetings in suitable rooms, within availability, final validation passes | AW `test_preparation_generation_publication_copy_correction_and_private_timetables`: actual GA, per-entry `full_clean`, final validator, room/day/time assertions | Pass |
| AT-004 | Reproducibility | Repeat controlled HTTP generation with seed 1729 | Same placements, input fingerprint/summary, parameters and scores | Same AW lifecycle test; hard violations zero, recorded soft score equals stored fitness | Pass |
| AT-005 | Infeasibility | Reduce lab capacity below section size and retry generation | Failed run and diagnostics, no new schedule/snapshot, previous schedule unchanged | AW `test_infeasible_generation_diagnostics_resource_correction_and_retry` | Pass |
| AT-006 | Recovery from bad input | Follow diagnostics, correct room through form, retry | New valid draft; previous failed run preserved | Same AW failure/retry test opens run/issue detail and restores capacity; reproduced placements | Pass |
| AT-007 | Generation contention | Existing lease blocks request; release allows retry | No competing run/schedule; owner unchanged; subsequent success releases lease | AW `test_invalid_preparation_and_busy_generation_preserve_state_then_retry` | Pass |
| AT-008 | Conflict correction | Legacy draft faculty/section overlap, invalid manual edit and bad suggestion token, then valid correction | Conflicts identified; rejected writes unchanged; valid correction audited | AW `test_legacy_draft_conflict_repair_manual_rejection_and_publication` checks correction link, validator and audit | Pass |
| AT-009 | Manual edits | Edit copied draft with signed revision, then resubmit stale revision | First save succeeds, second rejected without extra audit | AW lifecycle test uses edit form GET token and POST; verifies placement values | Pass |
| AT-010 | Publication | Valid generated/corrected draft versus invalid draft | Valid publication captures snapshot/audit; missing/conflicting meetings block publication | AW lifecycle and conflict tests assert PUBLISHED/DRAFT states | Pass |
| AT-011 | Copy/remove/history | Copy published schedule, edit and remove meeting | Source placements/snapshot/audit unchanged; definitions retained; incomplete copy cannot publish | AW lifecycle checks independent draft, three draft audits, unchanged four meeting definitions | Pass |
| AT-012 | Timetable privacy | Faculty/student view and exports; unpublished and anonymous access | Own entries only; both lecture/lab rooms displayed; private drafts denied | AW lifecycle checks browse/detail, CSV contents, PDF response and direct URL restrictions | Pass |
| AT-013 | Spreadsheet input | Preview, confirmation, mapping, CSV/XLSX and GA | Correct relationships, no invented qualifications or premature writes | `test_academic_import`: `test_preview_rolls_back_then_commit_preserves_relationships_and_ga`, `test_file_validation_csv_and_xlsx`, `test_mapping_validation`, `test_import_does_not_invent_dates_or_approve_undated_credentials` | Pass |
| AT-014 | Parent synchronization | Parent faculty edit propagates to meeting and GA | Consistent faculty information | `test_known_defects.test_H1_parent_faculty_edit_updates_all_meetings_and_ga` | Pass |
| AT-015 | Availability and utilization | Explicit available days, exclusions, defaults and merged intervals | GA/manual/reporting agree | `test_availability.test_explicit_available_periods_close_unlisted_days`, `test_H3_reporting_counts_merged_availability_minus_unavailable`; `test_room_availability_reporting` | Pass |
| AT-016 | Credentials | Term boundaries, equivalents and matched overrides | Expired/late/undated qualifications rejected under documented policy; valid overrides retained | `test_credentials.test_term_boundaries_missing_dates_and_no_expiry`, `test_equivalents_obey_same_dates`, `test_overrides_match_meeting_faculty_course_and_preserve_audit`; H4 regression | Pass |
| AT-017 | Meeting constraints | Duration, opening/closing time, inactive rooms and lecture/lab totals | Invalid placements rejected by manual, GA and publication checks | `test_duration_boundaries.test_opening_closing_and_outside_boundaries`, `test_inactive_room_rejected_by_manual_ga_and_publication`; `test_meeting_requirements` | Pass |
| AT-018 | Hard-first GA and repair | Feasible domain generation and bounded targeted repair | Soft preference cannot outweigh hard violations; repair preserves constraints | `test_ga_fitness`, `test_ga_placements`, `test_ga_repair`; assertions run against production GA | Pass |
| AT-019 | Soft scoring | Merged idle intervals and eligible-day distribution | Correct units, overlap handling, zero counts and ordering | `test_ga_soft_scoring.test_gap_after_overlap_uses_latest_end`, `test_unused_days_and_balanced_week`, `test_shorter_gap_and_balanced_days_rank_better` | Pass |
| AT-020 | Real concurrency | Simultaneous connections and stale owners | One schedule, fenced old owners, atomic rollback | `test_generation_lock.test_simultaneous_requests_on_separate_connections_create_only_one_schedule`, `test_expired_owner_cannot_renew_or_release_successor`; `test_manual_transactions.test_sqlite_competing_writers_cannot_both_commit` | Pass |
| AT-021 | Transaction failure | Audit/final validation failure during edit, override and publication | Entry/override/revision/audit/archive changes roll back | `test_manual_transactions.test_override_and_entry_rollback_when_audit_save_fails`; `test_snapshots.test_snapshot_failure_rolls_back_publication_audit_and_archive` | Pass |
| AT-022 | Finalized protection | Model, ORM bulk, cascades, SQL, admin, imports and term changes | Protected content immutable; unrelated drafts editable | `test_finalized_protection` (including raw SQL, mixed bulk and admin deletion); `test_term_protection`; `test_academic_import` | Pass |
| AT-023 | Snapshot preservation | Direct SQL and bulk snapshot mutation; archive and copied draft | Immutable history and authorized historical rendering | `test_snapshots.test_model_bulk_and_direct_sql_immutability`, `test_archive_retains_identical_snapshot_and_copy_uses_live_draft`, `test_student_filtering_exports_and_archive_access` | Pass |
| AT-024 | Role/endpoint security | Anonymous, student, faculty, plain/staff, ADMIN and superuser | Server-side role/object/model permission checks | All 17 `test_admin_publication_security` tests; `test_diagnostic_access`; AW role-limited timetable checks | Pass |
| AT-025 | CSRF/methods | Publication, diagnostics recovery, form drafts and generation | GET readonly, bad/missing token denied, authorized POST succeeds | `test_admin_publication_security.test_recovery_requires_csrf_and_authorized_post`, `test_publication_post_csrf_validation_and_atomic_service_authorization`, `test_json_draft_csrf_and_privileged_fields_are_not_accepted`; generation lock CSRF test | Pass |
| AT-026 | Production authentication | HTTPS login/logout, role routing, origin/token rejection | Secure cookies and valid role flow; forged origin rejected | `test_security_settings.ProductionAuthenticationTests`; configuration tests exercise headers/proxy trust | Pass |
| AT-027 | Recovery | Synthetic migrated database backup and separate restore | Exact schema/rows/history, integrity/FKs and triggers retained; protected mutations rejected | `test_database_backup.test_synthetic_end_to_end_recovery_drill` invokes actual backup/restore commands and restored protection checks | Pass |
| AT-028 | Backup safety | Existing/private/live paths, WAL, locks and interrupted writes | No overwrite or partial output; committed consistent snapshot | Remaining `test_database_backup` tests | Pass |
| AT-029 | Benchmark/report commands | Two small and two deliberately infeasible trials, then offline report | Two valid zero-hard drafts, two preflight failures; four-trial report with honest missing metrics | Executed `benchmark_ga` and `report_ga_benchmarks`; `benchmark-results/task84-b2a72f83/` | Pass |
| AT-030 | Evaluation contracts | Determinism, grouping, statistics, privacy and missing data | Structured repeatable outputs, no invented scores | `test_benchmarks` and `test_benchmark_reports`, including command tests | Pass |
| AT-031 | Performance regressions | Optimized validation and paginated/filterable lists | Equivalent diagnostics and bounded query behavior | `test_validation_performance`, `test_listing`, `test_list_controls`; no scalability extrapolation | Pass |
| AT-032 | Deployment configuration | Temporary production settings, HSTS 0 and 300 | Secure settings checks; report unresolved HTTPS policy warnings | `check --deploy`: exit 0; W004 at 0, W005/W021 at 300; none silenced | Pass with documented warnings |
| AT-033 | Static assets | Isolated production collection | Assets collected, no private DB/key/environment files | 131 files; no `.sqlite3`, `.db`, `.pem`, `.key` or `.env`; isolated directory removed | Pass |
| AT-034 | Environment | Django check, migration drift, dependency consistency | No issues, no new migrations, no conflicts | `check`, `makemigrations --check --dry-run`, `pip check` all exit 0 | Pass |
| AT-035 | Migration investigation | Compare accessible database migration histories | Read-only evidence identifies distinct databases/configuration | Read-only histories show default DB 12 and sample DB 15; developer confirmed their shell selects `tertiary_sample.sqlite3` with the same interpreter/settings | Pass - discrepancy resolved |
| AT-036 | Browser acceptance | JS tabs, uploads, responsive/dark layout, keyboard and downloads in browser | Correct interactions and rendering | No real browser executed; server HTML/PDF checks do not substitute | Requires manual verification |
| AT-037 | Live infrastructure | TLS/proxy/HSTS, host, production load and recovery cutover | Valid deployed infrastructure | Deployment prohibited; no live server configured | Not executed |
| AT-038 | Larger experiments | Medium/large GA runtime and quality | Measured representative experiments | No medium/large searches executed for this task; fixture/format checks are not performance experiments | Not executed |
| AT-039 | Optional academic scope | Curriculum completeness and fixed placements | Institution-approved requirements | Task 7.1/7.2 evaluations defer implementation pending clarification | Blocked on academic clarification |

## Coverage inventory and gap selection

The baseline has 547 tests in 32 modules. Most mix unit and integration assertions; counts are not separate mutually exclusive test categories. Four new workflow tests bring discovery to 551.

| Existing coverage | Modules (test counts) | Why reused |
| --- | --- | --- |
| General application behavior | `tests` (65) | Existing models, forms, views and timetable behavior |
| Data/import/meeting UI | `test_academic_import` (35), `test_meeting_tabs` (12), `test_meeting_requirements` (10) | Imports, lecture/lab policy and server-rendered meeting tabs |
| Academic policies | `test_known_defects` (3), `test_availability` (9), `test_credentials` (9), `test_duration_boundaries` (10), `test_room_availability_reporting` (4) | H1/H3/H4 and detailed boundaries |
| GA algorithms | `test_ga_fitness` (19), `test_ga_placements` (21), `test_ga_repair` (21), `test_ga_soft_scoring` (16) | Unit and production-GA constraint contracts |
| GA operational metadata | `test_generation_lock` (26), `test_generation_diagnostics` (24), `test_reproducibility` (20) | Concurrency, diagnostics, history and deterministic inputs |
| Editing/publication | `test_corrections` (18), `test_manual_transactions` (13), `test_copy_remove` (14) | Atomic edits, correction tokens, safe copies/removal |
| Database protection | `test_finalized_protection` (16), `test_term_protection` (11), `test_snapshots` (18) | ORM, SQL, bulk, cascades and immutable history |
| Security/recovery | `test_admin_publication_security` (17), `test_diagnostic_access` (15), `test_security_settings` (17), `test_database_backup` (17) | Role/CSRF, safe configuration and isolated recovery |
| Research reporting | `test_benchmarks` (18), `test_benchmark_reports` (23) | Isolated execution, schema and honest statistical output |
| Lists/validation performance | `test_listing` (17), `test_list_controls` (19), `test_validation_performance` (10) | Query and semantic regressions |

The meaningful gap was integration across **form-created mixed lecture/lab inputs → actual GA → validation → publication → role-filtered exports → copied draft editing/removal → unchanged original history**, plus failed generation followed by correction and retry. AW adds those workflows without duplicating the full boundary/security suites. Browser, live infrastructure and institutional acceptance evidence remain distinct outstanding work.
