"""Read-only published resource commitments, independent of academic level."""
from dataclasses import dataclass
from datetime import date, time, timedelta

from .time import overlaps, add_minutes


def weekday_intersects(start, end, other_start, other_end, day):
    """Inclusive calendar dates, with no invented holidays or teaching weeks."""
    left, right = max(start, other_start), min(end, other_end)
    return left <= right and left + timedelta(days=(day - left.weekday()) % 7) <= right


@dataclass(frozen=True)
class ResourceCommitment:
    entry_id: int | None
    schedule_id: int | None
    term_id: int
    education_level: str
    faculty_id: int
    room_id: int
    day: int
    start_time: time
    end_time: time
    starts_on: date
    ends_on: date


def published_commitments(term):
    """Other published terms reserve resources; alternative drafts never do.

    The same-term exclusion preserves the existing replacement-draft contract.
    Dates/weekly recurrence reflect the existing timetable model, not holidays.
    """
    from schedules.models import ScheduleEntry, ScheduleStatus
    entries = ScheduleEntry.objects.filter(
        schedule__status=ScheduleStatus.PUBLISHED,
        schedule__term__starts_on__lte=term.ends_on,
        schedule__term__ends_on__gte=term.starts_on,
    ).exclude(schedule__term_id=term.pk).select_related('schedule__term', 'assignment__faculty', 'faculty_override')
    return tuple(ResourceCommitment(
        entry.pk, entry.schedule_id, entry.schedule.term_id,
        entry.schedule.term.education_level, entry.effective_faculty.pk,
        entry.room_id, entry.day, entry.start_time, entry.end_time,
        entry.schedule.term.starts_on, entry.schedule.term.ends_on,
    ) for entry in entries if weekday_intersects(term.starts_on, term.ends_on,
        entry.schedule.term.starts_on, entry.schedule.term.ends_on, entry.day))


def resource_conflicts(candidate, commitments):
    """Return resource type and entry ID; contact totals are not conflicts."""
    result = []
    for other in commitments:
        if candidate.entry_id is not None and candidate.entry_id == other.entry_id:
            continue
        if candidate.day != other.day or not overlaps(candidate.start_time, candidate.end_time, other.start_time, other.end_time):
            continue
        if not weekday_intersects(candidate.starts_on, candidate.ends_on, other.starts_on, other.ends_on, candidate.day):
            continue
        for kind in ('faculty', 'room'):
            if getattr(candidate, kind + '_id') == getattr(other, kind + '_id'):
                result.append((kind, other.entry_id))
    return tuple(result)


def placement_conflicts(term, faculty_id, room_id, day, start, end, commitments):
    """Adapt a proposed placement to the shared dated occupancy contract."""
    candidate = ResourceCommitment(None, None, term.pk, term.education_level,
        faculty_id, room_id, day, start, end, term.starts_on, term.ends_on)
    return resource_conflicts(candidate, commitments)


def placement_boundaries(faculty_id, room_id, day, duration, commitments):
    """Preserve feasible adjacent starts when commitments are off the slot grid."""
    return {start for item in commitments
            if item.day == day and (item.faculty_id == faculty_id or item.room_id == room_id)
            for start in (item.end_time, add_minutes(item.start_time, -duration))}


def contact_minutes_by_faculty(commitments, starts_on, ends_on):
    """Actual recurring contact minutes in a requested date window, not load units.

    Pass a deduplicated set of published commitments. No ceiling or institutional
    conversion is applied, and period totals from delivery plans are not mixed in.
    """
    result, seen = {}, set()
    for item in commitments:
        if item.entry_id is not None and item.entry_id in seen:
            continue
        seen.add(item.entry_id)
        left, right = max(starts_on, item.starts_on), min(ends_on, item.ends_on)
        first = left + timedelta(days=(item.day - left.weekday()) % 7)
        if first > right:
            continue
        count = (right - first).days // 7 + 1
        minutes = (item.end_time.hour * 60 + item.end_time.minute) - (item.start_time.hour * 60 + item.start_time.minute)
        result[item.faculty_id] = result.get(item.faculty_id, 0) + count * minutes
    return result
