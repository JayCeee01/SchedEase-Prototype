"""Display helpers for the guided importer; no academic records are changed here."""
from collections import Counter
from .importers.academic import COLUMNS, REQUIRED
from .importers.academic_sample import SAMPLE_ROW
from .import_presentation import LABELS, HELP, MODULES, message, preview_display

GROUPS = {
    'Programs & departments': ['department_code', 'department_name', 'program_code', 'program_name'],
    'Sections': ['year_level', 'year_label', 'section_code', 'section_size'],
    'Courses': ['course_code', 'course_description', 'units', 'lecture_hours', 'lab_hours', 'course_room_type', 'course_credentials'],
    'Faculty': ['assigned_faculty_id', 'faculty_name', 'faculty_max_hours', 'faculty_credentials'],
    'Rooms': ['room_name', 'room_type', 'room_capacity'],
    'Meetings': ['component', 'meeting_index', 'duration_minutes', 'meeting_room_type'],
    'Availability': ['availability_owner', 'availability_day', 'availability_start', 'availability_end', 'availability_kind'],
    'Reference only': ['reference_faculty', 'reference_room', 'reference_day', 'reference_start', 'reference_end'],
}
NEW_REQUIRED = {'department_name', 'program_name', 'year_label', 'section_size', 'course_description', 'units',
                'lecture_hours', 'lab_hours', 'course_room_type', 'faculty_name', 'faculty_max_hours', 'room_type', 'room_capacity'}
EXAMPLES = {**SAMPLE_ROW, 'faculty_credentials': 'Certificate A|License B', 'course_credentials': 'Certificate A',
            'availability_owner': 'FACULTY', 'availability_day': 'Monday', 'availability_start': '08:00',
            'availability_end': '10:00', 'availability_kind': 'UNAVAILABLE', 'reference_faculty': 'Previous teacher',
            'reference_room': 'Room 101', 'reference_day': 'Monday', 'reference_start': '08:00', 'reference_end': '10:00'}
RESOURCE_LINKS = {'Department': 'departments', 'Program': 'programs', 'YearLevel': 'year-levels',
                  'Section': 'sections', 'Subject': 'subjects', 'Faculty': 'faculty', 'Room': 'rooms',
                  'Credential': 'credentials', 'FacultyCredential': 'faculty-credentials',
                  'SubjectCredentialRequirement': 'subject-credential-requirements',
                  'Assignment': 'assignments', 'TeachingAssignment': 'assignments', 'Availability': 'availability'}


def guide():
    return [{'key': key, 'label': LABELS[key], 'help': HELP[key], 'group': group,
             'requirement': 'Required' if key in REQUIRED else 'For new records' if key in NEW_REQUIRED else 'Optional',
             'example': EXAMPLES.get(key, '')} for group, keys in GROUPS.items() for key in keys]


def issues_for(result):
    issues = result.get('issues') or [{'row': None, 'columns': [], 'problem': e} for e in result.get('errors', [])]
    return [{**issue, 'column_labels': ', '.join(LABELS.get(k, k) for k in issue['columns']) or 'Related records',
             'problem': message(issue['problem']),
             'fix': 'Correct the highlighted information in your file, upload it again, and review the result.' if issue['row']
                    else 'Review the related saved records and check this file again.'} for issue in issues]


def review_context(batch, result, page=1, errors_only=False):
    display = preview_display(result)
    issues = issues_for(result)
    by_row = {}
    for issue in issues:
        by_row.setdefault(issue['row'], []).append(issue)
    mapping = batch.payload['mapping']
    rows = batch.payload['rows']
    # When entity validation fails, the importer deliberately postpones meeting validation.
    # Do not label unchecked rows as ready when the file still contains errors.
    blocked = bool(result['errors'])
    attention = len([n for n in by_row if n is not None])
    filtered = [row for row in rows if not errors_only or row['number'] in by_row or None in by_row]
    pages = max(1, (len(filtered) + 49) // 50)
    page = max(1, min(page, pages))
    preview = []
    for row in filtered[(page - 1) * 50:page * 50]:
        problems = by_row.get(row['number'], [])
        marked = {key for issue in problems for key in issue['columns']}
        preview.append({'number': row['number'], 'issues': problems,
                        'status': 'Needs attention' if problems else 'Check file' if blocked else 'Ready',
                        'cells': [{'value': value, 'error': key in marked, 'ignored': not key}
                                  for key, value in zip(mapping, row['values'])]})
    visible_numbers = {row['number'] for row in preview}
    display['actions'] = [a for a in display['actions'] if a['row'] in visible_numbers]
    counts = Counter(a['module'] for a in result['actions'])
    modules = [{'name': MODULES.get(key, key), 'count': count, 'resource': RESOURCE_LINKS.get(key)} for key, count in counts.items()]
    return {'result': display, 'issues': issues, 'preview_rows': preview, 'global_issues': by_row.get(None, []),
            'preview_headers': [{'source': source, 'label': LABELS.get(key, 'Not imported')} for source, key in zip(batch.payload['headers'], mapping)],
            'attention_count': attention, 'ready_count': 0 if blocked else len(rows), 'modules': modules,
            'page_number': page, 'page_count': pages, 'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < pages else None, 'errors_only': errors_only, 'shown_count': len(filtered)}
