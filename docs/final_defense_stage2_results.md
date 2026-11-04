# Stage 2 completed — 2026-11-04

Recovered the completed tertiary creation process and reports; did not reseed it. Created SHS after its in-memory rehearsal passed. Both use the current local working tree, including uncommitted protections through `0034_publication_membership`.

| Record | Tertiary | SHS |
| --- | ---: | ---: |
| Programs | 5 | 2 |
| Pathways | 0 | 2 |
| Sections | 16 | 8 |
| Faculty | 24 | 12 |
| Students | 416 | 224 |
| Subjects | 40 | 20 |
| Rooms | 12 | 8 |
| Assignments | 84 | 44 |
| Accounts | 27 | 15 |
| Baseline assignments | 64 | 33 |
| Live-demo assignments | 20 | 11 |
| Schedules / generation runs | 0 / 0 | 0 / 0 |

Combined: **640 students and 128 assignments**. All 42 accounts authenticated with their generated initial passwords. Dedicated administrators have ADMIN/staff/superuser access; 24/12 faculty and two students in each database have matching role links and no staff/superuser access.

Databases:

- `C:\Users\JEROME\SchedEase-Prototype\tertiary_final_defense.sqlite3`
- `C:\Users\JEROME\SchedEase-Prototype\shs_final_defense.sqlite3`

Final SHA-256:

- Tertiary: `435a1116d113d34a48b4fc500fe87aa0798afcb9a27131372d27a6c14571331e`
- SHS: `7a3ca8370cc1c336f4062b1fa094fb854845ed7a00a4384548b06c9e20cf7b0c`

Both migrated independently through 0034, with 172 installed triggers each. Both in-memory population rehearsals and actual population validations passed. Django checks reported no issues; `manage.py makemigrations --check --dry-run` reported no changes. Independent read-only checks confirmed counts, education-level separation, unique student names/identifiers, account links, migration state, SQLite integrity `ok`, zero foreign-key violations, and no schedules/history/generation runs. Plain SQLite integrity inspection required registering the existing deterministic identity function used by expression indexes; no schema or guard changes were made.

Tertiary has 168 validated lecture/laboratory meetings. SHS has 44 confirmed operational configurations/patterns, weekday-only recurrence, explicit compatible rooms and approved fictional weekly 600-contact-minute policies. Both have valid credentials, populated sections, availability and capacity. SHS prepared TeachingAssignments, meeting bindings and immutable preparation evidence remain uncreated: the existing controlled Stage 3 adapter captures them transactionally. No GA success or publication is claimed.

Baseline dates: November 2–15, 2026. Live-demo dates: November 16–29, 2026. These are fictional two-week demonstrations, not institutional calendars or complete curricula. Subjects/pathway labels are illustrative; all approval references explicitly disclaim STI/DepEd institutional approval.

Passwords are absent from source and reports. Windows CurrentUser DPAPI credential files and JSON verification reports are in the current-user-only, Git-ignored external directory `C:\Users\JEROME\SchedEase-Final-Defense-Credentials-20261104`. Use the hidden `changepassword` workflow in the handoff to choose demonstration passwords.

All nine original database hashes matched this task's fresh pre-write inventory, including the current UAT demo hash `c95bbe8c7a03fccebff33b1c96ced8a2de48082b7e443220b73948df4a13dafa`. That hash already differed from the older preflight baseline before Stage 2 began. Both reference workbook hashes also remained unchanged. No Git operations, existing-database migrations, GA/publication changes, or Phase 5 work occurred.

Created utility: `tools/create_final_defense.py` (fixed academic seed 20261104, explicit target selection, exclusive create-only reservation, refusal of existing databases/sidecars, transactional population). Initial passwords remain deliberately nondeterministic. The utility must not be rerun against these existing targets.

Next: separately authorize Stage 3, follow [the handoff](final_defense_stage3_commands.md), generate and validate baseline drafts, then publish through the authorized UI. GA feasibility/runtime, published views and exports remain untested by design. No Stage 4 comprehensive checks were performed.
