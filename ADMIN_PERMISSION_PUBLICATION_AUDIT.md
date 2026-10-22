# Admin permissions and publication audit (Task 8.3)

## Initial audit

Scope: audit the existing Django admin, application endpoints, publication workflow and indirect mutations, fixing only confirmed authorization and unsafe-request weaknesses. This task does not add roles, publication states or deployment features.

Task 8.2's uncommitted commands, tests, documentation and ignore rules were present at startup and are preserved. This task uses synthetic test databases only.

Existing roles are ADMIN, FACULTY and STUDENT (`Profile.role`), alongside Django superuser/staff flags and model permissions. Normal administrative views use `admin_required`; sensitive manual/publication services recheck active administrator status from the database. Faculty availability and timetable routes scope data by linked faculty/section. Django admin itself requires active staff.

Confirmed gaps before changes:

1. Most admin registrations used `ProtectedScheduleAdmin` with only deletion protection, so staff with model permissions could read/write academic records without the application administrator role. Profile administration and built-in User/Group administration provided alternate privilege-management paths.
2. The generic Schedule admin form exposed status and publication metadata, allowing DRAFT-to-PUBLISHED updates without the validation, replacement confirmation and audit in `services.publication.publish`.
3. Admin ScheduleEntry edits bypassed signed revisions, the transactional manual-save service and its audit creation. Draft audit records could also be rewritten through generic admin forms.
4. Error Log GET requests invoked `recover_stale_runs`, changing generation statuses and creating diagnostics without a POST/CSRF requirement.
5. Credential override forms exposed the approval actor as writable, allowing administrator attribution to be forged.

Existing protections include security/session/authentication/CSRF middleware, finalized and academic-term triggers (0010–0011), immutable snapshot capture/guards (0012), one-published-schedule-per-term constraint, transactional publication/manual-save services, owner-bound imports/drafts, signed correction proposals and database generation leases. These are retained rather than replaced.

## Role and permission matrix

| Account | Application administration | Django admin models | Timetables and exports | Diagnostics |
| --- | --- | --- | --- | --- |
| Anonymous | Login required | Login required | Login required | Login required |
| Faculty | Denied; own availability is editable | Denied even with staff/model permissions | Own published entries | Denied |
| Student | Denied | Denied even with staff/model permissions | Linked section's published entries | Denied |
| Other authenticated account | Denied | Denied without administrator role | No entries without an authorized academic link | Denied |
| Active ADMIN | Allowed | Also requires active staff status and corresponding Django model permissions | Full administrative scope | Allowed |
| Active superuser | Allowed | Requires staff access to the admin site; Django grants model permissions | Full administrative scope | Allowed |

Inactive accounts cannot authenticate through the standard backend. The shared administrator predicate also explicitly rejects inactive accounts. Staff status alone grants no academic authority. An unauthorized staff member can reach the admin index but cannot access registered models. Normal application administrators do not need Django staff status or model permissions.

## Django admin findings and fixes

All registered models now use the shared administrator predicate in addition to Django's module/view/add/change/delete permissions, including built-in User and Group administration. Direct object URLs and password-change URLs therefore enforce the same role restriction as navigation.

Registrations reviewed: AcademicTerm, Assignment, Availability, Credential, CredentialOverride, Department, Faculty, FacultyCredential, GASettings, Program, Profile, Room, Schedule, ScheduleEntry, ScheduleEntryAudit, Section, Student, Subject, SubjectCredentialRequirement, TeachingAssignment, YearLevel, User and Group. There are no custom academic admin actions or inlines providing an alternate mutation path.

- Schedule lifecycle fields are read-only, including status, origin, publication/archive dates and replacement reference. Forged add/change payloads cannot publish a schedule. New admin-created schedules remain drafts.
- ScheduleEntry and ScheduleEntryAudit are view-only in Django admin, including add and bulk delete. Use the existing application editor for revision checks, transactional saves and audit creation.
- Finalized objects expose read-only fields and reject submitted edits. Existing object deletion checks and database guards remain in force.
- CredentialOverride creation records the authenticated administrator in both interfaces. The actor is excluded from the application form and read-only in admin; subsequent edits preserve the original actor.
- Other permitted academic administration continues to work. Django model permissions have not been replaced with a blanket role grant.

User, Group and Profile management remains a privileged capability. An ADMIN explicitly entrusted with identity-management permissions can grant privileges. Such delegation must be limited to trusted operators; this task does not invent a new identity-management role or superuser-only policy.

## Direct endpoint authorization and HTTP methods

| Endpoint group | Authorization / scope | Mutation behavior |
| --- | --- | --- |
| Resource management, room dashboards and room exports | Administrator | Forms/confirmation on GET; writes on POST |
| Generate and generation run details | Administrator | Generation on POST; existing database lease retained |
| Error Log and issue details | Administrator | GET is read-only; recovery requires explicit POST action and CSRF; issue updates use POST |
| Spreadsheet imports and error downloads | Administrator; uploaded import belongs to requester | Mapping/confirmation and transactional writes on POST; existing update approval and signatures retained |
| Form draft save/discard | Administrator and owner | POST; allowed fields exclude privilege and publication fields |
| Manual entry edit/remove and correction suggestions | Administrator, schedule/entry scope | Existing transactional service, confirmation and signed revisions; suggestions are POST-only |
| Copy to Draft | Administrator | POST-only; source remains finalized |
| Publish | Administrator, rechecked by service | POST-only; validation and replacement confirmation required |
| Browse/detail and timetable CSV/PDF | Authenticated, authorized published entries for non-administrators | Same object and row scope in views and exports |
| Faculty availability | Linked faculty, own records | POST saves; faculty/room ownership cannot be reassigned through payload fields |

Direct endpoint tests cover anonymous, unlinked, faculty, student and non-administrator staff accounts. Unauthorized authenticated application requests may redirect through the existing login decorator; object-scoped timetable requests return 404. Hidden buttons are not the authorization mechanism.

CSRF middleware remains enabled. No application `csrf_exempt` endpoints were found. Tests use `Client(enforce_csrf_checks=True)` for publication, recovery and JSON draft writes, checking missing-token rejection and authorized-token success. GET requests may render forms or confirmation pages but do not perform those writes. Unsupported Error Log recovery actions are rejected. Existing Django authentication routes retain their framework protections.

## Publication, finalization and indirect operations

The supported lifecycle remains draft publication, with optional confirmed replacement of the current official schedule. The replacement becomes archived. There is no supported unpublish/reopen endpoint. The legacy APPROVED enum is not a new approval workflow. Copy to Draft is the supported way to edit a finalized schedule's placements.

`services.publication.publish` uses an atomic transaction and conditional first write, rechecks the active administrator, validates the complete schedule, requires replacement confirmation and records the publication audit. It archives the prior official schedule through the restricted transition, publishes the new schedule and requires its historical snapshot to exist. Failures roll back the transaction. The database uniqueness constraint permits only one published schedule per term.

Existing finalized-record, term and snapshot guards remain unchanged. Regression coverage exercises edits/deletes through models, querysets, bulk operations, cascading relationships, admin and imports, including atomic rejection and audit preservation. Draft editing and Copy to Draft remain available. Admin entry mutation is deliberately routed to the existing application workflow rather than duplicating manual-save logic.

Database/CLI access is a trusted operator boundary: a process with direct SQL access can create a legacy finalized record outside the publication service. The existing snapshot triggers preserve that history but do not provide request-actor authorization or replace schedule validation. This audit closes the exposed HTTP admin bypass; it does not claim to constrain a database owner capable of altering triggers or using trusted application code.

## Sensitive data and preserved safeguards

Faculty and student timetable detail, browse and CSV/PDF responses retain their authorized entry filtering. Drafts and archives are not exposed to these roles. Historical rendering does not expose the full snapshot payload. Diagnostic details, generation metadata, credentials and academic management remain administrator-only. No snapshot admin registration or public backup/media download route is introduced. Imports and saved forms remain owner-bound.

No GA scoring, feasibility, repair, generation lease, academic validation, schema, production settings or backup/restore implementation changes were made for this task. Backup and restore commands remain privileged local tools. Deployment must separately enforce private file storage and the production configuration described in `PRODUCTION_SECURITY.md`.

## Resume status and migration discrepancy

At resumption, the working tree was clean and the earlier Task 8.3 implementation and 17 new security tests were already present. The audit document was incomplete. The remaining older diagnostic test still expected recovery on GET. It now asserts that GET leaves the run RUNNING with no issues, while repeated explicit recovery POSTs mark it FAILED with exactly one issue. This strengthens the intended security behavior without removing the test.

Read-only inspection on 2026-10-20 used `sched_ease.settings` and `C:\Users\JEROME\SchedEase-Prototype\db.sqlite3`. Its `django_migrations` table contains 12 applied schedules migrations (0001–0012), matching the earlier Task 8.2 observation. Its SHA-256 was `8af12d70cf8fabdc0e4a2eccc8a9e8aebc237c24b5aebaf894477e75ccd473fd`. The user's separate `showmigrations` result reports all 15 applied. Follow-up confirmation during Task 8.4 established that their PowerShell session uses `C:\Users\JEROME\SchedEase-Prototype\tertiary_sample.sqlite3`, with the same virtual-environment interpreter and settings module. Read-only inspection of that file confirmed all 15 migrations. The discrepancy is resolved: the reports refer to different databases. No migration or live database write was performed. Test databases apply the repository's full migration chain independently, so passing tests do not establish the live database's migration readiness.

## Verification

Verified on 2026-10-20 using the existing `.venv` (Python 3.12.10 / Django 5.0.6). The 530 pre-task tests are retained, with the one recovery assertion intentionally updated as described above. The new `schedules.test_admin_publication_security` module adds 17 tests covering admin role gates, direct identity URLs, model permissions, protected lifecycle fields, read-only entries/audits, override attribution, CSRF/POST enforcement, endpoint role matrices, publication validation/atomicity, export privacy and privileged form fields.

| Command | Result |
| --- | --- |
| `python manage.py test schedules.test_admin_publication_security schedules.test_finalized_protection schedules.test_term_protection schedules.test_snapshots schedules.test_diagnostic_access schedules.test_copy_remove schedules.test_generation_diagnostics schedules.test_credentials --noinput` | 124 passed in 61.186 seconds |
| `python manage.py test --noinput` | 547 passed in 301.133 seconds |
| `python manage.py check` | No issues, none silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `git diff --check` | Passed |

Both test runs had zero failures, errors, skips, expected failures or unexpected successes. Injected exception messages in generation rollback tests are synthetic test fixtures, not leaked live data or failing tests. The real database SHA-256 remained unchanged. No migrations, commits or deployments were performed.

**Task 8.3 is complete.** Resumption changed only this audit, README, the diagnostic recovery guide and the existing recovery test. Earlier security implementation files (`schedules/admin.py`, `schedules/views.py`, `schedules/forms.py`, `templates/schedules/error_log.html` and `schedules/test_admin_publication_security.py`) were preserved. Task 8.4 was not started.

### Code and test references

- [Admin registrations and permission methods](schedules/admin.py), [application views](schedules/views.py), [routes](schedules/urls.py) and [forms](schedules/forms.py).
- [Publication transaction](schedules/services/publication.py), [manual editing service](schedules/services/manual_edits.py) and [finalized protection](schedules/protection.py).
- [New security regression tests](schedules/test_admin_publication_security.py) and [generation recovery tests](schedules/test_generation_diagnostics.py).
- Existing coverage: [finalized protection](schedules/test_finalized_protection.py), [term protection](schedules/test_term_protection.py), [snapshots](schedules/test_snapshots.py), [diagnostic access](schedules/test_diagnostic_access.py), [Copy to Draft/removal](schedules/test_copy_remove.py) and [credentials](schedules/test_credentials.py).
- [Production preparation](PRODUCTION_SECURITY.md) and [backup/restore safeguards](DATABASE_BACKUP_RESTORE.md).

## Remaining risks and limitations

- This is a source and automated regression audit, not an external penetration test or a production deployment certification.
- Reconcile the live database migration discrepancy before using features requiring 0013–0015. This task does not change the real database.
- Privileged identity administrators, superusers, management-command operators and database owners remain trusted. Restrict their credentials and local file access.
- The supported Django upgrade and deployment/proxy checks already identified in Task 8.1 remain separate work; no dependency upgrade is included here.
- No unsupported unpublication workflow or new roles were introduced. No further academic policy decision was needed for these confirmed fixes.
