# Admin permissions and publication audit (Task 8.3)

## Initial audit

Task 8.2's uncommitted commands, tests, documentation and ignore rules were present at startup and are preserved. This task uses synthetic test databases only.

Existing roles are ADMIN, FACULTY and STUDENT (`Profile.role`), alongside Django superuser/staff flags and model permissions. Normal administrative views use `admin_required`; sensitive manual/publication services recheck active administrator status from the database. Faculty availability and timetable routes scope data by linked faculty/section. Django admin itself requires active staff.

Confirmed gaps before changes:

1. Most admin registrations used `ProtectedScheduleAdmin` with only deletion protection, so staff with model permissions could read/write academic records without the application administrator role. Profile administration and built-in User/Group administration provided alternate privilege-management paths.
2. The generic Schedule admin form exposed status and publication metadata, allowing DRAFT-to-PUBLISHED updates without the validation, replacement confirmation and audit in `services.publication.publish`.
3. Admin ScheduleEntry edits bypassed signed revisions, the transactional manual-save service and its audit creation. Draft audit records could also be rewritten through generic admin forms.
4. Error Log GET requests invoked `recover_stale_runs`, changing generation statuses and creating diagnostics without a POST/CSRF requirement.
5. Credential override forms exposed the approval actor as writable, allowing administrator attribution to be forged.

Existing protections include security/session/authentication/CSRF middleware, finalized and academic-term triggers (0010–0011), immutable snapshot capture/guards (0012), one-published-schedule-per-term constraint, transactional publication/manual-save services, owner-bound imports/drafts, signed correction proposals and database generation leases. These are retained rather than replaced.
