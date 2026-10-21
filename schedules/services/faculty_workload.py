"""Display workload from already-authorized published timetable entries."""
from decimal import Decimal


def published_workload(entries):
    groups = {}
    for entry in entries:
        group = groups.setdefault(entry.schedule_id, {
            'schedule': entry.schedule, 'minutes': 0, 'meetings': 0, 'section_ids': set(),
        })
        group['minutes'] += entry.assignment.required_duration_minutes
        group['meetings'] += 1
        group['section_ids'].add(entry.effective_section.pk)
    return [dict(schedule=g['schedule'], minutes=g['minutes'],
                 hours=Decimal(g['minutes']) / 60, meetings=g['meetings'],
                 sections=len(g['section_ids'])) for g in groups.values()]
