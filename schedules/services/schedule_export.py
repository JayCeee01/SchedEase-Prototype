"""Read-only exports of authorized entries; never grants access.

CSV retains its seven leading columns. Appended metadata and dated occurrence
rows are an intentional extension: strict positional consumers must adapt.
"""
from datetime import date, datetime, time

from .timetable_presentation import present_entries

HEADERS = ['Day', 'Start', 'End', 'Course', 'Section', 'Faculty', 'Room',
           'Meeting Date', 'Recurrence', 'Recurrence Start', 'Recurrence End',
           'Participating Sections', 'Academic Term', 'School Year', 'Education Level',
           'Instruction', 'Duration Minutes', 'Evidence', 'Warnings']


def export_occurrences(entries):
    rows, seen = [], set()
    for item in present_entries(entries):
        recurrence = item['recurrence']
        for value in recurrence['dates'] or (None,):
            key = (item['schedule_id'], item['entry_id'], value)
            if key in seen:
                continue
            seen.add(key)
            actual = date.fromisoformat(value) if value else None
            start, end = time.fromisoformat(item['start_time']), time.fromisoformat(item['end_time'])
            warnings = list(item['warnings'])
            if recurrence['kind'] == 'UNKNOWN':
                warnings.append('Meeting dates unavailable')
            if item['academic_context']['education_level'] == 'SHS' and item['weekday'] in (5, 6):
                warnings.append('Weekend SHS meeting - review required')
            sections = item['participating_sections']
            valid = (item['participation_complete'] and
                     all(type(s['id']) is int and s['id'] > 0 for s in sections) and
                     len({s['id'] for s in sections}) == len(sections))
            if not valid:
                sections = (item['primary_section'],)
                warnings.append('Complete participating sections unavailable; primary section shown only.')
            rows.append(dict(item, actual_date=actual, start=start, end=end,
                duration_minutes=int((datetime.combine(date.min, end) - datetime.combine(date.min, start)).total_seconds() / 60),
                sections='; '.join(s['label'] or 'Section name unavailable' for s in sections),
                notes=' '.join(dict.fromkeys(warnings))))
    return sorted(rows, key=lambda r: (r['actual_date'] or date.max, r['weekday'], r['start'],
                                      r['end'], r['schedule_id'], r['entry_id']))


def values(row):
    context, recurrence = row['academic_context'], row['recurrence']
    return [day_name(row), row['start'], row['end'], row['subject']['code'],
            row['primary_section']['label'], row['faculty']['label'], row['room']['label'],
            row['actual_date'], recurrence['kind'], recurrence['starts_on'], recurrence['ends_on'],
            row['sections'], context['term_name'], context['school_year'], context['education_level'],
            row['instructional_label'], row['duration_minutes'],
            ' / '.join(filter(None, (row['source'], row['operational_source']))), row['notes']]


def day_name(row):
    names = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    return names[row['weekday']] if row['weekday'] in range(7) else 'Weekday unavailable'


def pdf_rows(rows):
    for row in rows:
        yield [f"{row['actual_date'] or row['recurrence']['kind']}\n{day_name(row)}\n{row['start']:%H:%M} - {row['end']:%H:%M}",
               f"{row['subject']['code']}\n{row['subject']['title']}", row['sections'],
               row['faculty']['label'], row['room']['label'],
               f"{row['instructional_label'] or 'Instruction unavailable'}\n{row['duration_minutes']} min\n"
               f"{row['recurrence']['kind']} {row['recurrence']['starts_on'] or ''} - {row['recurrence']['ends_on'] or ''}\n"
               f"{row['academic_context']['education_level'] or 'Education level unavailable'}\n"
               f"{row['source']}\n{row['operational_source'] or ''}\n{row['notes']}"]
