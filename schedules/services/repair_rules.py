"""Recurring repair rules persisted in the existing protected schedule audit trail."""
from datetime import time
from schedules.models import ScheduleEntryAudit
from .time import overlaps


def scenario_days(scenario):
    """Read new multi-day rules and existing single-day audit records."""
    return scenario.get('days', [scenario.get('day')])


def windows(schedule):
    if hasattr(schedule, '_repair_windows'):
        return schedule._repair_windows
    if not getattr(schedule, 'pk', None) or schedule.pk < 0:
        return []
    result, pending, seen = [], [schedule.pk], set()
    while pending:
        pk = pending.pop()
        if pk in seen:
            continue
        seen.add(pk)
        for row in ScheduleEntryAudit.objects.filter(schedule_id=pk).order_by('pk').values_list('new_values', flat=True):
            if row.get('action') == 'copy_to_draft' and row.get('source_schedule_id'):
                pending.append(row['source_schedule_id'])
            if row.get('action') == 'smart_repair_setup' and row['scenario']['kind'] in ('faculty', 'room'):
                result.append(row['scenario'])
    return result


def entry_errors(entry):
    errors = []
    for window in windows(entry.schedule):
        resource = entry.effective_faculty.pk if window['kind'] == 'faculty' else entry.room_id
        if resource == window['resource'] and entry.day in scenario_days(window) and overlaps(
                entry.start_time, entry.end_time, time.fromisoformat(window['start']), time.fromisoformat(window['end'])):
            errors.append('Recurring repair restriction: the selected ' + window['kind'] + ' is unavailable during this time.')
    return errors
