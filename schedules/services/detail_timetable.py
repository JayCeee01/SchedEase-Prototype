"""Shared timetable projection. Caller must authorize/filter entries first.

Weeks run Monday through Sunday. Missing/invalid/unavailable week selections
use the earliest authorized teaching week, never the server's current date.
Table view and exports remain independent of this timetable-only selection.
"""
from datetime import date, time, timedelta
from types import SimpleNamespace

from .timetable_presentation import present_entries


def timetable_context(entries, requested_week=None):
    entries = list(entries)
    rows = present_entries(entries)
    weeks = set()
    for row in rows:
        if row['recurrence']['kind'] == 'DATED':
            for value in row['recurrence']['dates']:
                day = date.fromisoformat(value)
                if row.get('academic_context', {}).get('education_level') == 'SHS' and day.weekday() >= 5:
                    continue
                weeks.add(day - timedelta(days=day.weekday()))
    weeks = sorted(weeks)
    selected = None
    invalid = False
    if weeks:
        try:
            selected = date.fromisoformat(requested_week) if requested_week else weeks[0]
            if selected not in weeks:
                raise ValueError
        except (ValueError, TypeError):
            selected, invalid = weeks[0], True
    names = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    columns = [{'name': name, 'rows': []} for name in names]
    unknown = []
    weekend = []
    seen = set()
    for row in rows:
        if row['entry_id'] in seen:
            continue
        seen.add(row['entry_id'])
        item = dict(row, start=time.fromisoformat(row['start_time']), end=time.fromisoformat(row['end_time']))
        item['weekday_name'] = names[row['weekday']] if row['weekday'] in range(7) else 'Weekday unavailable'
        kind = row['recurrence']['kind']
        if row.get('academic_context', {}).get('education_level') == 'SHS' and row['weekday'] in (5, 6):
            item['review_dates'] = [date.fromisoformat(value) for value in (row['recurrence']['dates'] or ())]
            weekend.append(item)
            continue
        if kind == 'UNKNOWN' or row['weekday'] not in range(7):
            unknown.append(item)
        elif kind == 'WEEKLY':
            columns[row['weekday']]['rows'].append(dict(item, meeting_date=None))
        else:
            for value in row['recurrence']['dates']:
                day = date.fromisoformat(value)
                if day - timedelta(days=day.weekday()) == selected:
                    columns[day.weekday()]['rows'].append(dict(item, meeting_date=day))
    # Preserve the ordinary Monday-Saturday layout; add Sunday only if needed.
    if rows and all(row.get('academic_context', {}).get('education_level') == 'SHS' for row in rows):
        columns = columns[:5]
    elif not columns[-1]['rows']:
        columns.pop()
    for column in columns:
        column['rows'].sort(key=lambda row: (row['start'], row['end'], row['entry_id']))
    end = min(date.max.toordinal(), selected.toordinal() + 6) if selected else None
    return {'timetable_days': columns, 'timetable_unknown': unknown,
            'timetable_has_weekly': any(row['recurrence']['kind'] == 'WEEKLY' for row in rows),
            'timetable_weekend': weekend,
            'timetable_weeks': weeks, 'timetable_week': selected,
            'timetable_week_end': date.fromordinal(end) if end else None,
            'timetable_week_invalid': invalid,
            'timetable_has_rows': any(column['rows'] for column in columns)}


def personal_timetable_context(entries, requested_week=None):
    """Adapt selected occurrences to the existing grid, without database reads.

The shared projection performs its own two batch reads; grid conversion adds
none. Faculty's existing grid calls retain their defaults.
    """
    from .room_utilization import personal_schedule_grid
    context = timetable_context(entries, requested_week)
    selected = [SimpleNamespace(day=day, start_time=row['start'], end_time=row['end'], presentation=row)
                for day, column in enumerate(context['timetable_days']) for row in column['rows']]
    context['timetable_grid'] = personal_schedule_grid(
        selected, days=range(len(context['timetable_days'])), single_cards=True) if selected else []
    return context


def room_timetable_context(entries, room, requested_week=None):
    """Selected-schedule presentation plus current room policy, not global vacancy.

Reuse occurrence selection/grid placement; utilization arithmetic is untouched.
    """
    from .availability import AvailabilityPolicy
    from .room_utilization import personal_schedule_grid
    context = personal_timetable_context(entries, requested_week)
    grid = context['timetable_grid'] or personal_schedule_grid(
        [], days=range(len(context['timetable_days'])), single_cards=True)
    policy = AvailabilityPolicy.for_resource(room)
    for row in grid:
        for day, cell in enumerate(row['cells']):
            cell['available'] = not policy.rejection_reason(day, row['start'], row['end'])
    context['grid'] = grid
    return context
