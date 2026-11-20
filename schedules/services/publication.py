"""Publish under SQLite's writer lock; the status trigger captures history."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from schedules.models import Schedule, ScheduleEntryAudit, ScheduleSnapshot, ScheduleStatus
from schedules.protection import archive_transition
from .conflicts import schedule_validation_messages
from .manual_edits import authorized_administrator
from .publication_boundary import _validated_transition
from copy import copy


def publish(schedule, actor, replace_confirmed=False, *, education_level=None, term_id=None):
    with transaction.atomic():
        # Conditional first write serializes SQLite publishers and manual edits.
        claimed = Schedule.objects.filter(pk=schedule.pk, updated_at=schedule.updated_at,
            status=schedule.status, term_id=schedule.term_id).exclude(
            status__in=[ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED]).update(updated_at=timezone.now())
        if claimed != 1:
            raise ValidationError("The schedule changed. Reload and review it before publishing.")
        actor = authorized_administrator(actor)
        locked = Schedule.objects.select_for_update().get(pk=schedule.pk)
        from .academic_scope import require_schedule_scope
        require_schedule_scope(locked, education_level=education_level, term_id=term_id)
        if not locked.entries.exists() or schedule_validation_messages(locked):
            raise ValidationError("Resolve conflicts before publishing.")
        current = Schedule.objects.filter(term=locked.term, status=ScheduleStatus.PUBLISHED).exclude(pk=locked.pk).first()
        if current and not replace_confirmed:
            raise ValidationError("The official schedule changed. Reload and confirm its replacement before publishing.")
        from .schedule_notifications import recipients, record_publication
        old_recipients = recipients(current)
        now = timezone.now()
        if current:
            previous = copy(current)
            current.status, current.archived_at, current.replaced_by = ScheduleStatus.ARCHIVED, now, locked
            with archive_transition(), _validated_transition(current, previous, actor=actor, candidate=locked):
                current.save(update_fields=['status', 'archived_at', 'replaced_by', 'updated_at'])
        ScheduleEntryAudit.objects.create(schedule=locked, user=actor, previous_values={'status': locked.status},
            new_values={'action': 'publish', 'status': ScheduleStatus.PUBLISHED, 'published_at': now.isoformat(),
                        'archived_schedule_id': current.pk if current else None})
        previous = copy(locked)
        locked.status, locked.published_at = ScheduleStatus.PUBLISHED, now
        locked.archived_at, locked.replaced_by = None, None
        with _validated_transition(locked, previous, actor=actor, candidate=locked):
            locked.save(update_fields=['status', 'published_at', 'archived_at', 'replaced_by', 'updated_at'])
        # Fail closed if a database was provisioned without the required trigger.
        ScheduleSnapshot.objects.get(schedule=locked)
        record_publication(locked, current, old_recipients)
        return locked, current
