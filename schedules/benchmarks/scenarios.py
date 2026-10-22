"""Versioned synthetic definitions. No random input generation."""
from datetime import date, time

SCENARIO_VERSION = 'synthetic-v1'
SCENARIOS = {
    'small': dict(sections=2, courses=2, faculty=2, lecture_rooms=2, lab_rooms=1),
    'medium': dict(sections=6, courses=4, faculty=8, lecture_rooms=3, lab_rooms=2),
    'large': dict(sections=12, courses=6, faculty=18, lecture_rooms=6, lab_rooms=4),
    'infeasible': dict(sections=2, courses=2, faculty=2, lecture_rooms=2, lab_rooms=1),
}


def require_isolation():
    from django.conf import settings
    from django.db import connections
    db = connections['default'].settings_dict
    if (not getattr(settings, 'GA_BENCHMARK_ISOLATED', False)
            or set(connections) != {'default'}
            or db['ENGINE'] != 'django.db.backends.sqlite3' or db['NAME'] != ':memory:'):
        raise RuntimeError('Benchmarks require the dedicated in-memory worker.')


def build_scenario(name):
    require_isolation()
    from django.db import transaction
    from schedules import models as m
    spec = SCENARIOS[name]
    if m.AcademicTerm.objects.exists() or m.Room.objects.exists():
        raise RuntimeError('Each benchmark trial requires a fresh database.')
    with transaction.atomic():
        department = m.Department.objects.create(code='BENCH', name='Synthetic department')
        program = m.Program.objects.create(department=department, code='BENCH', name='Synthetic program')
        year = m.YearLevel.objects.create(level=1, label='Year 1')
        term = m.AcademicTerm.objects.create(name='Synthetic term', school_year='2026-2027',
            starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 1))
        credential = m.Credential.objects.create(name='Synthetic teaching qualification')
        faculty = []
        for i in range(spec['faculty']):
            teacher = m.Faculty.objects.create(department=department, employee_id=f'B{i:03}',
                full_name=f'Synthetic faculty {i:03}', max_weekly_hours=24)
            m.FacultyCredential.objects.create(faculty=teacher, credential=credential,
                issued_on=date(2020, 1, 1), expires_on=date(2030, 12, 31))
            for day in range(5):
                m.Availability.objects.create(faculty=teacher, day=day, start_time=time(8),
                    end_time=time(17), kind=m.AvailabilityKind.AVAILABLE)
            m.Availability.objects.create(faculty=teacher, day=i % 5, start_time=time(13),
                end_time=time(15), kind=m.AvailabilityKind.UNAVAILABLE)
            m.Availability.objects.create(faculty=teacher, day=1, start_time=time(8),
                end_time=time(10), kind=m.AvailabilityKind.PREFERRED)
            faculty.append(teacher)
        courses = []
        for i in range(spec['courses']):
            subject = m.Subject.objects.create(department=department, code=f'B{i:03}',
                title=f'Synthetic course {i:03}', lecture_hours=2, lab_hours=2,
                required_room_type=m.RoomKind.LECTURE)
            m.SubjectCredentialRequirement.objects.create(subject=subject, required_credential=credential)
            courses.append(subject)
        for i in range(spec['sections']):
            section = m.Section.objects.create(program=program, year_level=year,
                name=f'B{i:03}', size=24 + (i % 3) * 4)
            for j, subject in enumerate(courses):
                parent = m.Assignment.objects.create(term=term, subject=subject, section=section,
                    faculty=faculty[(i * spec['courses'] + j) % len(faculty)])
                for index, component, minutes, room_type in (
                        (1, 'LECTURE', 60, m.RoomKind.LECTURE),
                        (2, 'LECTURE', 60, m.RoomKind.LECTURE),
                        (3, 'LABORATORY', 120, m.RoomKind.COMPUTER_LAB)):
                    m.TeachingAssignment.objects.create(assignment=parent, component=component,
                        meeting_index=index, duration_minutes=minutes, required_room_type_override=room_type)
        for room_type, count, capacity in ((m.RoomKind.LECTURE, spec['lecture_rooms'], 40),
                (m.RoomKind.COMPUTER_LAB, spec['lab_rooms'], 10 if name == 'infeasible' else 36)):
            for i in range(count):
                room = m.Room.objects.create(name=f'{room_type}-{i:03}', room_type=room_type, capacity=capacity)
                for day in range(5):
                    m.Availability.objects.create(room=room, day=day, start_time=time(8),
                        end_time=time(17), kind=m.AvailabilityKind.AVAILABLE)
                    m.Availability.objects.create(room=room, day=day, start_time=time(12),
                        end_time=time(13), kind=m.AvailabilityKind.UNAVAILABLE)
        return term

