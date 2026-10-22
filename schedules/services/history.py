"""Historical display adapters. Authorize/filter live IDs before using these."""
from datetime import time
from importlib import import_module
from types import SimpleNamespace

from django.db import connection, transaction
from schedules.models import ScheduleEntry, ScheduleSnapshot, TeachingAssignment, Weekday


class HistoricalValue(SimpleNamespace):
    def __str__(self):
        return str(getattr(self, 'display_name', None) or getattr(self, 'full_name', None)
                   or getattr(self, 'name', None) or getattr(self, 'code', None) or 'Unknown')


class HistoricalEntry(HistoricalValue):
    """A read-only projection retaining its ScheduleEntry record identity."""
    def __eq__(self, other):
        if isinstance(other, (HistoricalEntry, ScheduleEntry)):
            return (self.pk, self.schedule_id) == (other.pk, other.schedule_id)
        return NotImplemented

    def __hash__(self):
        return hash(self.pk)


def value(data):
    return HistoricalValue(**data, pk=data.get('id'))


def historical_term(snapshot):
    term = value(snapshot.data['term'])
    term.display_name = f"{term.name or 'Unknown term'} {term.school_year or ''}".strip()
    return term


def historical_entries(entries):
    """Only project the supplied authorized rows; never return full snapshot JSON."""
    entries = list(entries)
    snapshots = {s.schedule_id: s for s in ScheduleSnapshot.objects.filter(
        schedule_id__in={e.schedule_id for e in entries})}
    maps = {pk: {row['id']: row for row in s.data['entries']} for pk, s in snapshots.items()}
    result = []
    for entry in entries:
        if entry.schedule_id not in snapshots:
            if entry.schedule.status in ('PUBLISHED', 'ARCHIVED'):
                # Never silently replace missing history with current values.
                raise ScheduleSnapshot.DoesNotExist('Finalized schedule history is missing.')
            result.append(entry)
            continue
        row = maps[entry.schedule_id][entry.pk]
        snapshot = snapshots[entry.schedule_id]
        section = value(row['section'])
        section.program, section.year_level = value(row['program']), value(row['year_level'])
        course, faculty, room = value(row['course']), value(row['faculty']), value(row['room'])
        schedule = value(snapshot.data['schedule'])
        schedule.status = entry.schedule.status  # Current lifecycle, original publication content.
        schedule.term = historical_term(snapshot)
        component = row['component']
        result.append(HistoricalEntry(id=row['id'], pk=row['id'], schedule_id=entry.schedule_id, schedule=schedule,
            assignment_id=row['meeting_id'], assignment=HistoricalValue(pk=row['meeting_id'],
                meeting_index=row['meeting_index'], required_duration_minutes=row['required_duration_minutes'],
                subject=course, section=section, faculty=faculty),
            effective_subject=course, effective_section=section, effective_faculty=faculty, room=room, room_id=room.pk,
            day=row['day'], start_time=time.fromisoformat(row['start_time']), end_time=time.fromisoformat(row['end_time']),
            get_day_display=lambda day=row['day']: dict(Weekday.choices).get(day, 'Unknown'), effective_component=component,
            effective_component_display=dict(TeachingAssignment.Component.choices).get(component, component),
            historical=True, manual_conflicts=[]))
    return result


def backfill_snapshots():
    """Idempotent repair/backfill using frozen v1 capture SQL. Does not overwrite."""
    migration = import_module('schedules.migrations.0012_historical_snapshots')
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(migration.BACKFILL)
            return cursor.rowcount
