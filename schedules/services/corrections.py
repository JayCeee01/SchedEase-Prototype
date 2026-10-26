"""Read-only placement search; signed proposals use the normal atomic save path."""
from copy import copy
from datetime import time

from django.core import signing
from django.core.exceptions import ValidationError

from schedules.models import Room, ScheduleEntry, ScheduleStatus
from .availability import AvailabilityPolicy
from .manual_edits import FIELDS, authorized_administrator, revision_token, save_manual_entry
from .time import ALLOWED_DAYS, SCHOOL_END, add_minutes, slot_starts
from .resource_occupancy import published_commitments, placement_conflicts, placement_boundaries

SALT = "schedules.placement-suggestion.v1"


def placement_suggestions(entry, actor, limit=3):
    authorized_administrator(actor)
    if entry.schedule.status != ScheduleStatus.DRAFT:
        return []
    duration = entry.assignment.required_duration_minutes
    external = published_commitments(entry.schedule.term)
    from .meetings import entry_requirement_errors
    from .credentials import teaching_eligibility
    if entry_requirement_errors(entry) or not teaching_eligibility(
            entry.effective_faculty, entry.effective_subject, entry.schedule.term, entry.assignment)['eligible']:
        return []
    rooms = list(Room.objects.filter(is_active=True, capacity__gte=entry.effective_section.size,
                                    room_type=entry.assignment.effective_room_type).order_by('name', 'pk'))
    rooms.sort(key=lambda room: room.pk != entry.room_id)
    faculty_policy = AvailabilityPolicy.for_resource(entry.effective_faculty)
    policies = {room.pk: AvailabilityPolicy.for_resource(room) for room in rooms}
    starts = set(slot_starts(duration))
    starts.add(entry.start_time)
    dated_starts = {(day, start) for day in ALLOWED_DAYS for start in starts}
    for day in ALLOWED_DAYS:
        for room in rooms:
            dated_starts.update((day, start) for start in placement_boundaries(entry.effective_faculty.pk, room.pk, day, duration, external))
    placements = sorted(dated_starts,
                        key=lambda pair: (pair[0] != entry.day, abs(pair[0] - entry.day),
                            abs(pair[1].hour * 60 + pair[1].minute - entry.start_time.hour * 60 - entry.start_time.minute), pair))
    results = []
    revision = revision_token(entry.schedule, actor, entry)
    for day, start in placements:
        end = add_minutes(start, duration)
        if end <= start or end > SCHOOL_END or faculty_policy.rejection_reason(day, start, end):
            continue
        for room in rooms:
            if placement_conflicts(entry.schedule.term, entry.effective_faculty.pk, room.pk, day, start, end, external):
                continue
            if (day, start, end, room.pk) == (entry.day, entry.start_time, entry.end_time, entry.room_id):
                continue
            if policies[room.pk].rejection_reason(day, start, end):
                continue
            candidate = copy(entry)
            candidate._state = copy(entry._state)
            candidate._state.fields_cache = entry._state.fields_cache.copy()
            candidate.day, candidate.start_time, candidate.end_time, candidate.room = day, start, end, room
            try:
                candidate.full_clean()
            except ValidationError:
                continue
            token = signing.dumps({'entry': entry.pk, 'schedule': entry.schedule_id, 'user': actor.pk,
                'revision': revision, 'day': day, 'start': start.isoformat(), 'end': end.isoformat(), 'room': room.pk}, salt=SALT)
            results.append({'entry': candidate, 'token': token})
            if len(results) >= limit:
                return results
    return results


def apply_suggestion(*, schedule_id, entry_id, actor, token):
    try:
        proposal = signing.loads(token, salt=SALT, max_age=86400)
        if (proposal['schedule'], proposal['entry'], proposal['user']) != (schedule_id, entry_id, actor.pk):
            raise ValueError
        entry = ScheduleEntry.objects.get(pk=entry_id, schedule_id=schedule_id)
        proposed = {field: getattr(entry, field) for field in FIELDS}
        proposed.update(day=proposal['day'], room_id=proposal['room'],
                        start_time=time.fromisoformat(proposal['start']), end_time=time.fromisoformat(proposal['end']))
    except (signing.BadSignature, KeyError, TypeError, ValueError, ScheduleEntry.DoesNotExist):
        raise ValidationError('This suggestion is missing or expired. Reload the meeting to see current alternatives.')
    return save_manual_entry(schedule_id=schedule_id, entry_id=entry_id, actor=actor,
                             revision=proposal['revision'], proposed=proposed, draft_only=True)
