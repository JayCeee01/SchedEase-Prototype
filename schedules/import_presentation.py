"""Plain-language display text. Import keys, rules and preview signatures stay unchanged."""
import re

LABELS = {
    'department_code': 'Department code', 'department_name': 'Department name',
    'program_code': 'Program code', 'program_name': 'Program name',
    'year_level': 'Year level', 'year_label': 'Year level name',
    'section_code': 'Section code', 'section_size': 'Number of students',
    'course_code': 'Course code', 'course_description': 'Course name',
    'units': 'Units', 'lecture_hours': 'Weekly lecture hours', 'lab_hours': 'Weekly lab hours',
    'course_room_type': 'Course room type', 'assigned_faculty_id': 'Assigned teacher’s employee ID',
    'faculty_name': 'Teacher’s full name', 'faculty_max_hours': 'Maximum teaching hours per week',
    'faculty_credentials': 'Teacher’s qualifications', 'course_credentials': 'Qualifications needed for the course',
    'room_name': 'Room name', 'room_type': 'Room type', 'room_capacity': 'Number of seats',
    'component': 'Class type', 'meeting_index': 'Meeting number', 'duration_minutes': 'Class length in minutes',
    'meeting_room_type': 'Room type for this meeting', 'availability_owner': 'Availability applies to',
    'availability_day': 'Availability day', 'availability_start': 'Availability start time',
    'availability_end': 'Availability end time', 'availability_kind': 'Availability choice',
    'reference_faculty': 'Original teacher (for reference)', 'reference_room': 'Original room (for reference)',
    'reference_day': 'Original day (for reference)', 'reference_start': 'Original start time (for reference)',
    'reference_end': 'Original end time (for reference)',
}
HELP = dict(zip(LABELS, [
    'Short department code, such as CCS.', 'Full name, such as College of Computer Studies. Needed for a new department.',
    'Short program code, such as BSCS.', 'Full name, such as Bachelor of Science in Computer Science. Needed for a new program.',
    'A whole number starting at 1, such as 2.', 'For example, Year 2. Needed for a new year level.',
    'Section code only, such as 201 or A.', 'Student count, such as 30. Needed for a new section.',
    'Course code, such as CS101.', 'For example, Introduction to Computing. Needed for a new course.',
    'For example, 3 or 1.5. Use zero or more, with at most one decimal place. Needed for a new course.',
    'Weekly hours, such as 2. Use a whole number, including 0. Needed for a new course.',
    'Weekly hours, such as 3. Use a whole number, including 0. Needed for a new course.',
    'Use LECTURE, COMPUTER_LAB, SCIENCE_LAB, GYM or SPECIAL. Needed for a new course.',
    'Employee ID of the teacher who will teach this class, such as F001.',
    'For example, Maria Santos. Needed for a new teacher.',
    'A whole number above 0, such as 24. Needed for a new teacher.',
    'Use the exact qualification names. Separate multiple names with |, such as License A|Certificate B.',
    'Use the exact qualification names required for this course. Separate multiple names with |.',
    'For example, Room 101. Adding a room does not assign the class to it.',
    'Use LECTURE, COMPUTER_LAB, SCIENCE_LAB, GYM or SPECIAL. Needed for a new room.',
    'A whole number above 0, such as 40. Needed for a new room.',
    'Use LECTURE or LABORATORY. Use GENERAL only when both weekly lecture and lab hours are 0.',
    'Use 1, 2, 3 and so on. Give each meeting in an assignment a different number.',
    'For example, 60 for one hour. Use 1–720. Total lecture and lab minutes must match the course’s weekly hours.',
    'Optional. Use a room type above, such as COMPUTER_LAB for a lab class.',
    'Optional. Use FACULTY for the assigned teacher or ROOM for the named room.',
    'Use Monday through Saturday, or 0 for Monday through 5 for Saturday.',
    'Use 24-hour time, such as 08:00. Earliest time: 07:00.',
    'Use 24-hour time, such as 17:00. Must be after the start and no later than 19:00.',
    'For a teacher: UNAVAILABLE or PREFERRED. For a room: AVAILABLE or UNAVAILABLE. Fill in all five availability columns together.',
    'Optional. Keep the old teacher’s name here without assigning them to the class.',
    'Optional. Keep the old room here without assigning it to the class.',
    'Optional. Keep the old day here without setting the new class day.',
    'Optional. Keep the old start time here without setting the new class time.',
    'Optional. Keep the old end time here without setting the new class time.',
]))
MODULES = {'Department': 'Department', 'Program': 'Program', 'YearLevel': 'Year level',
           'Section': 'Section', 'Subject': 'Course', 'Faculty': 'Teacher', 'Room': 'Room',
           'Credential': 'Qualification', 'FacultyCredential': 'Teacher qualification',
           'SubjectCredentialRequirement': 'Course qualification requirement',
           'Assignment': 'Teaching assignment', 'TeachingAssignment': 'Class meeting', 'Availability': 'Availability'}
FIELDS = {'name': 'Name', 'code': 'Code', 'title': 'Course name', 'level': 'Year level', 'label': 'Year level name',
          'size': 'Number of students', 'capacity': 'Number of seats', 'full_name': 'Teacher’s full name',
          'employee_id': 'Teacher’s employee ID', 'max_weekly_hours': 'Maximum teaching hours per week',
          'required_room_type': 'Course room type', 'required_room_type_override': 'Room type for this meeting',
          'department': 'Department', 'program': 'Program', 'subject': 'Course', 'faculty': 'Teacher',
          'section': 'Section', 'term': 'Academic term', 'assignment': 'Teaching assignment',
          'credential': 'Qualification', 'required_credential': 'Required qualification',
          'room': 'Room', 'day': 'Day', 'start_time': 'Start time', 'end_time': 'End time',
          'kind': 'Availability choice', 'is_active': 'Active', 'source_key': 'Source reference',
          'source_sheet': 'Source sheet', 'source_row': 'Source row', 'issued_by': 'Issued by',
          'issued_on': 'Issue date', 'expires_on': 'Expiry date', 'notes': 'Notes', 'description': 'Description'}


def label(key):
    if key.endswith('_id'):
        return label(key[:-3]) + ' (record number)'
    return LABELS.get(key, FIELDS.get(key, key.replace('_', ' ').capitalize()))


def message(text):
    """Translate display text only; the original result still controls confirmation."""
    replacements = {
        'XML entities and document types are not accepted.': 'This file contains unsupported content. Copy your values into the sample spreadsheet and upload it again.',
        'Workbook expands beyond the 25 MB content limit.': 'This workbook contains too much content. Copy the rows you need into a new file and try again.',
        'Encrypted workbooks are not supported.': 'Remove the workbook password, save a copy, and upload it again.',
        'Macros and external workbook links are not accepted.': 'Copy the values into the sample spreadsheet. Remove macros and links to other workbooks.',
        'Invalid spreadsheet. Use UTF-8 CSV or a valid single-sheet XLSX file.': 'We could not read this file. Save it as Excel (.xlsx) with one sheet, or CSV UTF-8 (.csv), and try again.',
        'Invalid column mapping.': 'Choose what each spreadsheet column contains, then click Review Information.',
        'Each destination column may be mapped only once.': 'You selected the same information for more than one column. Choose it only once.',
        'Map required columns: ': 'Choose a spreadsheet column for each required item: ',
        'Data changed since preview. Validate and review a fresh preview before confirming.': 'Some saved information has changed. Click Review Information again before importing.',
        'Choose skip or update.': 'Choose whether to keep or update existing records.',
        'Maximum 1,000 data rows per upload.': 'This file has too many rows. Split it into files with no more than 1,000 rows each.',
        'Maximum 80 columns.': 'This file has too many columns. Keep no more than 80 columns and upload it again.',
        'Upload must be 5 MB or smaller.': 'This file is too large. Choose a file of 5 MB or less.',
        'The spreadsheet contains no data rows.': 'This file is empty. Add your information below the column headings and upload it again.',
        'A header row is required in row 1.': 'Add column headings to the first row, then upload the file again.',
        'Provide 1–80 unique, nonempty column headers.': 'Give every column a different heading. Remove empty headings and keep no more than 80 columns.',
        'Use a workbook with exactly one worksheet and a header in row 1.': 'Keep your information on one Excel sheet, with column headings in the first row.',
        'Merged cells are not supported; use one row per meeting.': 'Separate merged cells and use one row for each class meeting. Then upload the file again.',
        'replace formulas/errors with plain values.': 'Replace the formula or error in this cell with its value, then upload the file again.',
        'No availability is inferred. Review room/faculty availability and GA settings before generating. Original timetable columns are reference only; fixed day/time/room slots are not supported.': 'Before generating a schedule, review teacher and room availability. Original days, times and rooms are kept for reference only.',
        'Generation readiness: ': 'Before generating a schedule: ',
        'required value is missing.': 'This information is missing. Fill it in and upload the file again.',
        'missing required fields: ': 'Fill in these details for the new record: ',
        'conflicting values for the same record in this file.': 'This record has different details in another row. Make the details match.',
        'repeat the same attributes on every row for this record.': 'Use the same details every time this record appears in the spreadsheet.',
        'duplicate meeting in this file; included only once.': 'This class meeting appears more than once. It will be added only once.',
        'differs; database values retained.': 'has different details. Your saved information will be kept.',
        'enter a finite nonnegative decimal.': 'Enter a number such as 3 or 1.5, using zero or more.',
        'required when room attributes are supplied.': 'Enter the room name along with its type and number of seats.',
        'supply owner, day, start, end and kind together.': 'Fill in all five availability columns: who or what, day, start time, end time and choice.',
        'choose FACULTY, or ROOM with room_name.': 'Use FACULTY for a teacher, or ROOM for a room. Include the room name when choosing ROOM.',
        'the GA supports FACULTY UNAVAILABLE/PREFERRED and ROOM AVAILABLE/UNAVAILABLE.': 'For a teacher, use UNAVAILABLE or PREFERRED. For a room, use AVAILABLE or UNAVAILABLE.',
        'use an interval within 07:00–19:00.': 'Enter a start and end time between 07:00 and 19:00. The end must be later than the start.',
        'exceeds the 12-hour school day.': 'A class cannot be longer than 720 minutes. Check the class length.',
        'this meeting is used by a schedule; edit it through the existing schedule workflow.': 'This class is already on a schedule. Open that schedule to make changes.',
        'meeting indexes must be unique across components.': 'Give each lecture and lab meeting a different meeting number.',
        'use LECTURE/LABORATORY when the course specifies those hours.': 'Use LECTURE or LABORATORY to match the course hours.',
        'No active ': 'No available ',
        'lacks the required credential or override.': 'does not have the qualifications needed for this course. Check the teacher’s qualifications before generating.',
        'required duration exceeds school operating hours.': 'has a class longer than the school day. Check its class length.',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'Row (\d+), (?:data|meeting): ', r'Row \1: ', text)
    text = re.sub(r'expected an integer of at least (\d+)\.', r'Enter a whole number of \1 or more.', text)
    text = re.sub(r'Would invalidate schedule entry (\d+): ', r'This change would cause a problem with scheduled class \1. Check the following: ', text)
    text = re.sub(r'Invalid isoformat string:.*', 'Enter the time in 24-hour format, such as 08:00 or 13:30.', text)
    text = re.sub(r'invalid literal for int\(\).*', 'We could not read a number in this file. Copy your values into the sample spreadsheet and upload it again.', text)
    text = re.sub(r'Constraint [“"].*?[”"] is violated\.', 'This record repeats information already saved. Check its code and meeting number.', text)
    text = re.sub(r'Value (.+?) is not a valid choice\.', r'\1 is not an accepted choice. Use one of the choices in the column guide.', text)
    text = text.replace('This field cannot be blank.', 'Fill in the missing information and review the file again.')
    text = text.replace('This field cannot be null.', 'Fill in the missing information and review the file again.')
    text = text.replace("[<class 'decimal.ConversionSyntax'>]", 'Units: Enter a number such as 3 or 1.5.')
    text = re.sub(r'(LECTURE|LABORATORY) totals (\d+) minutes; course requires (\d+)\.',
                  r'\1 meetings add up to \2 minutes, but the course needs \3. Adjust the meeting lengths to match.', text)
    text = text.replace('extra columns, NUL characters, or a cell exceeding 2,000 characters.',
                        'Check that every column has a heading and each cell has no more than 2,000 characters. If needed, copy the values into the sample spreadsheet.')
    for key, value in sorted({**FIELDS, **LABELS, **MODULES}.items(), key=lambda item: -len(item[0])):
        text = re.sub(r'\b' + re.escape(key) + r'\b', lambda match: value, text)
    return text


def preview_display(result):
    """Copy the preview for display without changing its signed import values."""
    actions = []
    for action in result['actions']:
        details = {}
        for side in ('before', 'provided'):
            details[side] = [(label(key), {'': 'Not provided', 'None': 'Not provided', 'True': 'Yes', 'False': 'No'}.get(value, value))
                             for key, value in action[side].items() if key != 'id']
        actions.append({**action, **details, 'module': MODULES.get(action['module'], action['module']),
                        'action': {'created': 'New record', 'updated': 'Update existing', 'skipped': 'Keep existing'}[action['action']]})
    return {**result, 'actions': actions, 'errors': [message(e) for e in result['errors']],
            'warnings': [message(w) for w in result['warnings']],
            'existing_count': result['counts'].get('updated', 0) + result['counts'].get('skipped', 0)}
