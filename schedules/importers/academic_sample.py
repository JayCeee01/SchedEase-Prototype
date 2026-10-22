"""Explicitly fictional examples, never defaults applied to uploaded data."""
SAMPLE_ROW = {
    'department_code': 'SAMPLE-CS', 'department_name': 'Sample Computing Department',
    'program_code': 'SAMPLE-BSCS', 'program_name': 'Sample Computer Science Program',
    'year_level': '1', 'year_label': 'Year 1', 'section_code': 'SAMPLE-A', 'section_size': '25',
    'course_code': 'SAMPLE-CS101', 'course_description': 'Sample Programming Course',
    'units': '3', 'lecture_hours': '2', 'lab_hours': '1', 'course_room_type': 'LECTURE',
    'assigned_faculty_id': 'SAMPLE-F001', 'faculty_name': 'Sample Teacher', 'faculty_max_hours': '24',
    'room_name': 'SAMPLE-101', 'room_type': 'LECTURE', 'room_capacity': '30',
    'component': 'LECTURE', 'meeting_index': '1', 'duration_minutes': '120', 'meeting_room_type': 'LECTURE',
}
SAMPLE_ROWS = [SAMPLE_ROW, {**SAMPLE_ROW, 'room_name': 'SAMPLE-LAB', 'room_type': 'COMPUTER_LAB',
                         'component': 'LABORATORY', 'meeting_index': '2', 'duration_minutes': '60',
                         'meeting_room_type': 'COMPUTER_LAB'}]
