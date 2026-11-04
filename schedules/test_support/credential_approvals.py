"""Create explicitly reviewed approvals in disposable regression fixtures."""
from schedules.services.credential_approval import approve_override, approval_token


def scoped_override(*, assignment, faculty, subject, admin_user, reason):
    return approve_override(assignment=assignment, faculty=faculty, subject=subject,
        actor=admin_user, reason=reason,
        scope_token=approval_token(admin_user, faculty, subject, assignment.term))
