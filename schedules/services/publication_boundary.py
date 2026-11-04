"""Exact, transaction-local publication transitions and finalized membership."""
from contextvars import ContextVar
from contextlib import contextmanager
from importlib import import_module

from django.core.exceptions import ValidationError
from django.db import connections
from django.db.models.deletion import ProtectedError

rules = import_module('schedules.migrations.0034_publication_membership')
_transition = ContextVar('validated_publication_transition', default=None)


def allowed(*values):
    return _transition.get() is not None and tuple(values) == _transition.get()


def register_connection(connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_function('schedease_publication_v1', 7, lambda *v: int(allowed(*v)))


def installed(using):
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='publication_update'")
        if cursor.fetchone():
            return True
        cursor.execute("SELECT 1 FROM django_migrations WHERE app='schedules' AND name='0034_publication_membership'")
        if cursor.fetchone():
            raise ValidationError('Publication protection is missing. Repair the database setup before making changes.')
    return False


def transition_values(instance, previous, using):
    connection = connections[using]
    return (instance.pk, instance.term_id, previous.status, instance.status,
            connection.ops.adapt_datetimefield_value(instance.published_at),
            connection.ops.adapt_datetimefield_value(instance.archived_at), instance.replaced_by_id)


@contextmanager
def _validated_transition(instance, previous, *, actor, candidate):
    """Validate the exact candidate and actor before issuing one transition."""
    if not connections['default'].in_atomic_block:
        raise ValidationError('Publication requires a transaction.')
    from .manual_edits import authorized_administrator
    from .conflicts import schedule_validation_messages
    from schedules.models import Schedule
    authorized_administrator(actor)
    current = Schedule.objects.get(pk=previous.pk)
    candidate = Schedule.objects.get(pk=candidate.pk)
    publishing = current.status in ('DRAFT','APPROVED') and instance.status=='PUBLISHED' and candidate.pk==instance.pk
    archiving = current.status=='PUBLISHED' and instance.status=='ARCHIVED' and instance.replaced_by_id==candidate.pk
    if (current.status != previous.status or current.term_id != instance.term_id
            or candidate.term_id != instance.term_id or candidate.status not in ('DRAFT','APPROVED')
            or not (publishing or archiving) or not candidate.entries.exists()
            or schedule_validation_messages(candidate)):
        raise ValidationError('The publication candidate is no longer complete and valid. Review it again.')
    token = _transition.set(transition_values(instance, previous, 'default'))
    try:
        yield
    finally:
        _transition.reset(token)


def check(instance, previous, changed, using='default', deleting=False):
    name = instance._meta.model_name
    if name not in ('schedule','assignment','teachingassignment') or not installed(using):
        return
    if name == 'schedule':
        if previous is None:
            invalid = instance.status not in ('DRAFT','APPROVED') or any((instance.published_at,instance.archived_at,instance.replaced_by_id))
        elif changed & {'status','published_at','archived_at','replaced_by_id'}:
            draft = previous.status in ('DRAFT','APPROVED') and instance.status in ('DRAFT','APPROVED') and not any((instance.published_at,instance.archived_at,instance.replaced_by_id))
            invalid = not draft and not allowed(*transition_values(instance, previous, using))
        else:
            invalid = False
        if invalid:
            raise ValidationError(rules.PUBLICATION)
        return
    if previous is not None and not deleting and not changed:
        return
    from schedules.models import Schedule
    terms = {instance.term_id}
    if previous:
        terms.add(previous.term_id)
    if Schedule.objects.using(using).filter(term_id__in=terms,status__in=['PUBLISHED','ARCHIVED']).exists():
        if deleting:
            raise ProtectedError(rules.MESSAGE, [instance])
        raise ValidationError(rules.MESSAGE)
