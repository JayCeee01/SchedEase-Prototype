"""Concern workflow: authorize references, retain context, never mutate schedules."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from schedules.models import Schedule, ScheduleEntry, ScheduleConcern, ConcernReview, Role, ScheduleStatus
from schedules.views import admin_required, role, entries_visible_to_user
from .history import historical_entries, historical_term


def reporter_allowed(user):
    return user.is_authenticated and user.is_active and not admin_required(user) and role(user) in (Role.STUDENT, Role.FACULTY)


def authorized_entries(user):
    if not reporter_allowed(user):
        return ScheduleEntry.objects.none()
    return entries_visible_to_user(ScheduleEntry.objects.filter(schedule__status=ScheduleStatus.PUBLISHED), user)


def authorized_schedules(user):
    return Schedule.objects.filter(pk__in=authorized_entries(user).values('schedule_id'))


@transaction.atomic
def submit_concern(*, actor, schedule_id, entry_id, category, description):
    if not reporter_allowed(actor):
        raise PermissionDenied
    schedule = authorized_schedules(actor).filter(pk=schedule_id).first()
    if not schedule:
        raise ValidationError('Choose a published schedule assigned to you.')
    entry = None
    if entry_id:
        entry = authorized_entries(actor).filter(pk=entry_id, schedule=schedule).first()
        if not entry:
            raise ValidationError('Choose a class from your selected schedule.')
    from schedules.models import ScheduleSnapshot
    snapshot = ScheduleSnapshot.objects.get(schedule=schedule)
    reference = {'schedule_id': schedule.pk, 'schedule': snapshot.data['schedule']['name'],
                 'term': str(historical_term(snapshot))}
    if entry:
        historical = historical_entries([entry])[0]
        reference.update(entry_id=entry.pk, assignment_id=entry.assignment_id,
            course=f'{historical.effective_subject.code} - {historical.effective_subject.title}',
            faculty=str(historical.effective_faculty), section=str(historical.effective_section),
            room=historical.room.name, day=historical.get_day_display(),
            time=f'{historical.start_time:%H:%M}-{historical.end_time:%H:%M}')
    concern = ScheduleConcern(reporter=actor, reporter_role=role(actor), schedule=schedule, entry=entry,
                              reference=reference, category=category, description=description.strip())
    concern.full_clean()
    concern.save()
    return concern


@transaction.atomic
def review_concern(*, actor, pk, revision, status, response):
    if not admin_required(actor):
        raise PermissionDenied
    if status not in ScheduleConcern.Status.values or len(response) > 3000:
        raise ValidationError('Choose a valid status and keep the response within 3000 characters.')
    # Claim before reading so competing SQLite reviewers cannot lose an update.
    if ScheduleConcern.objects.filter(pk=pk, revision=revision).update(revision=F('revision') + 1) != 1:
        raise ValidationError('This concern changed. Reload the page before saving your review.')
    concern = ScheduleConcern.objects.select_for_update().get(pk=pk)
    ConcernReview.objects.create(concern=concern, administrator=actor,
        previous_status=concern.status, previous_response=concern.response, status=status, response=response.strip())
    concern.status, concern.response = status, response.strip()
    concern.reviewed_by, concern.reviewed_at = actor, timezone.now()
    concern.save(update_fields=['status', 'response', 'reviewed_by', 'reviewed_at'])
    return concern
