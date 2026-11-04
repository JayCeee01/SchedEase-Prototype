"""Explicit, immutable approval scope and finalized requirement protections."""
from contextvars import ContextVar
import json

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError

SALT = 'schedease.credential-scope.v1'
STALE = 'The credential requirements changed or the approval form expired. Review the missing requirements and approve again.'
LOCKED = 'These credential requirements are used by a published or archived schedule. Keep them unchanged; a separate approved revision is required.'
_issuance = ContextVar('credential_scope_issuance', default=None)


def evidence_allowed(override_id, version, data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            return False
    return _issuance.get() == (override_id, version, data) and _issuance.get() is not None


def register_connection(connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_function('schedease_credential_evidence_v1', 3,
            lambda pk, version, data: int(evidence_allowed(pk, version, data)))


def scope_context(faculty, subject, term, result):
    return dict(faculty_id=faculty.pk, subject_id=subject.pk, term_id=term.pk,
                starts_on=term.starts_on.isoformat(), ends_on=term.ends_on.isoformat(),
                requirements=sorted((item['definition'] for item in result['missing']), key=lambda item: item['id']))


def approval_token(actor, faculty, subject, term, result=None):
    from .credentials import faculty_qualification
    result = result or faculty_qualification(faculty, subject, term)
    return signing.dumps({'actor': actor.pk, **scope_context(faculty, subject, term, result)}, salt=SALT)


def approve_override(*, actor, assignment, faculty, subject, reason, scope_token):
    """Approve exactly the displayed missing requirements, never infer old scope."""
    from schedules.models import TeachingAssignment, Faculty, Subject, CredentialOverride, CredentialApprovalEvidence
    from .manual_edits import authorized_administrator
    from .credentials import faculty_qualification, missing_credential_message
    using = assignment._state.db or 'default'
    with transaction.atomic(using=using):
        # First write serializes requirements and approval on SQLite. No record
        # value changes; finalized meeting/override guards remain enforced.
        if TeachingAssignment.objects.using(using).filter(pk=assignment.pk).update(source_key=F('source_key')) != 1:
            raise ValidationError('Choose an existing teaching meeting before approving an exception.')
        actor = authorized_administrator(actor)
        assignment = TeachingAssignment.objects.using(using).select_related('term').get(pk=assignment.pk)
        faculty = Faculty.objects.using(using).get(pk=faculty.pk)
        subject = Subject.objects.using(using).get(pk=subject.pk)
        result = faculty_qualification(faculty, subject, assignment.term)
        context = scope_context(faculty, subject, assignment.term, result)
        try:
            displayed = signing.loads(scope_token, salt=SALT, max_age=3600)
        except (signing.BadSignature, TypeError, ValueError):
            raise ValidationError(STALE)
        if displayed != {'actor': actor.pk, **context}:
            raise ValidationError(STALE)
        if not reason.strip() or not context['requirements']:
            raise ValidationError('An exception needs a reason and explicitly reviewed missing credential requirements.')
        override = CredentialOverride.objects.using(using).create(assignment=assignment, subject=subject,
            faculty=faculty, admin_user=actor, reason=reason.strip(),
            missing_credentials=missing_credential_message(faculty, subject, assignment.term))
        data = {**context, 'assignment_id': assignment.pk, 'administrator_id': actor.pk}
        token = _issuance.set((override.pk, 1, data))
        try:
            CredentialApprovalEvidence.objects.using(using).create(override=override, schema_version=1, data=data)
        finally:
            _issuance.reset(token)
        return override


def finalized_subjects(subject_ids, using='default'):
    from schedules.models import ScheduleEntry
    return ScheduleEntry.objects.using(using).filter(schedule__status__in=['PUBLISHED', 'ARCHIVED']).filter(
        Q(assignment__subject_id__in=subject_ids) | Q(subject_override_id__in=subject_ids) |
        Q(assignment__assignment__subject_id__in=subject_ids)).exists()


def has_evidence(pk, using='default'):
    from schedules.models import CredentialApprovalEvidence
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schedules_credentialapprovalevidence'")
        if not cursor.fetchone():
            return False  # Older-schema migration rehearsals contain no scoped approvals.
    return CredentialApprovalEvidence.objects.using(using).filter(override_id=pk).exists()


def check_requirement_change(sender, instance, using='default', **kwargs):
    old = sender.objects.using(using).filter(pk=instance.pk).first() if instance.pk else None
    if old and (old.subject_id, old.required_credential_id) == (instance.subject_id, instance.required_credential_id):
        return
    if finalized_subjects([instance.subject_id, old.subject_id if old else None], using):
        raise ValidationError(LOCKED)


def check_requirement_delete(sender, instance, using='default', **kwargs):
    if finalized_subjects([instance.subject_id], using):
        raise ProtectedError(LOCKED, [instance])


def check_equivalences(sender, instance, action, reverse, pk_set, using, **kwargs):
    if action not in ('pre_add', 'pre_remove', 'pre_clear') or (action != 'pre_clear' and not pk_set):
        return
    from schedules.models import SubjectCredentialRequirement
    if reverse:
        requirements = SubjectCredentialRequirement.objects.using(using)
        requirements = requirements.filter(acceptable_equivalents=instance) if action == 'pre_clear' else requirements.filter(pk__in=pk_set)
        subject_ids = requirements.values_list('subject_id', flat=True)
    else:
        subject_ids = [instance.subject_id]
    if finalized_subjects(subject_ids, using):
        raise ValidationError(LOCKED)


def check_through_change(sender, instance, using='default', **kwargs):
    from schedules.models import SubjectCredentialRequirement
    previous = sender.objects.using(using).filter(pk=instance.pk).first() if instance.pk else None
    if previous and (previous.subjectcredentialrequirement_id, previous.credential_id) == (instance.subjectcredentialrequirement_id, instance.credential_id):
        return
    ids = [instance.subjectcredentialrequirement_id, previous.subjectcredentialrequirement_id if previous else None]
    if finalized_subjects(SubjectCredentialRequirement.objects.using(using).filter(pk__in=ids).values_list('subject_id', flat=True), using):
        raise ValidationError(LOCKED)


def check_through_delete(sender, instance, using='default', **kwargs):
    from schedules.models import SubjectCredentialRequirement
    subjects = SubjectCredentialRequirement.objects.using(using).filter(pk=instance.subjectcredentialrequirement_id).values_list('subject_id', flat=True)
    if finalized_subjects(subjects, using):
        raise ProtectedError(LOCKED, [instance])
