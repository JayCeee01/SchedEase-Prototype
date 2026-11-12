"""Create-only representative data; never an institutional approval or importer."""
from datetime import date, time
from pathlib import Path
import os

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connections, transaction


def require_unified_database():
    """Check configuration and file identity before opening a connection."""
    expected = Path(settings.BASE_DIR) / 'unified_schedease.sqlite3'
    configured = connections['default'].settings_dict
    if (os.environ.get('SCHED_EASE_DATABASE_URL') != 'sqlite:///unified_schedease.sqlite3'
            or configured['ENGINE'] != 'django.db.backends.sqlite3'
            or Path(configured['NAME']).absolute() != expected.absolute()
            or expected.is_symlink() or expected.resolve() != expected.absolute()):
        raise CommandError('Explicitly select sqlite:///unified_schedease.sqlite3; no other target is allowed.')
    if not expected.is_file() or expected.stat().st_nlink != 1:
        raise CommandError('Initialize the new standalone unified database first; missing or linked files are refused.')
    return expected


def seed_representative_data():
    require_unified_database()
    with transaction.atomic():
        return _seed()


def _seed():
    from schedules import models as m

    def ensure(model, identity, **values):
        obj = model.objects.filter(**identity).first()
        if obj is not None:
            for field, value in values.items():
                actual = getattr(obj, field)
                if actual != value:
                    raise CommandError(f'{model.__name__} seed identity has changed; refusing to overwrite it.')
            return obj
        obj = model(**identity, **values)
        obj.full_clean()
        obj.save()
        return obj

    department = ensure(m.Department, {'code': 'UNI-DEV'}, name='Fictional unified development')
    faculty = ensure(m.Faculty, {'employee_id': 'UNI-DEV-F01'},
                     department=department, full_name='Alexis Dela Cruz (fictional)', max_weekly_hours=24)
    room = ensure(m.Room, {'name': 'UNI-DEV-R01'}, room_type='LECTURE', capacity=40, is_active=True)
    credential = ensure(m.Credential, {'name': 'Unified development teaching qualification'},
                        description='Synthetic development qualification, not institutional evidence.')
    ensure(m.FacultyCredential, {'faculty': faculty, 'credential': credential},
           issued_by='Fictional development fixture')
    version = ensure(m.CurriculumVersion, {'family': 'Unified development SHS', 'revision': '1'},
                     education_level='SHS', reference_title='Fictional, unverified development structure',
                     verification_status='UNVERIFIED', is_active=False)
    pathway = ensure(m.AcademicPathway, {'curriculum_version': version, 'code': 'UNI-DEV-STEM'},
                     name='Fictional STEM pathway', kind='STRAND')
    cohort = ensure(m.Cohort, {'curriculum_version': version, 'school_year': '2026-2027',
                             'grade_level': 11, 'pathway': pathway})
    sections, subjects = {}, {}
    for level, year in [('TERTIARY', 1), ('SHS', 11)]:
        program = ensure(m.Program, {'code': f'UNI-{level}'}, department=department,
                         name=f'Fictional {level} program', education_level=level)
        year_obj = ensure(m.YearLevel, {'level': year}, label=f'Year {year}' if year == 1 else 'Grade 11')
        sections[level] = ensure(m.Section, {'program': program, 'year_level': year_obj, 'name': 'A'},
                                 size=20, cohort=cohort if level == 'SHS' else None)
        subjects[level] = ensure(m.Subject, {'code': f'UNI-{level}-101'}, department=department,
                                 title=f'Fictional {level} communication', lecture_hours=1, lab_hours=0,
                                 required_room_type='LECTURE')
        ensure(m.SubjectCredentialRequirement, {'subject': subjects[level], 'required_credential': credential})
    requirement = ensure(m.CurriculumSubjectRequirement,
                         {'curriculum_version': version, 'subject': subjects['SHS'],
                          'grade_level': 11, 'academic_period': 'Development period', 'pathway': pathway},
                         classification='Development example', quantity=60, unit='MINUTES',
                         measurement_basis='PERIOD', verification_status='UNVERIFIED', is_active=False)
    scenarios = [('TERTIARY', 'baseline', date(2026, 8, 3), date(2026, 8, 16)),
                 ('SHS', 'overlapping', date(2026, 8, 3), date(2026, 8, 16)),
                 ('SHS', 'nonoverlapping', date(2026, 9, 7), date(2026, 9, 20))]
    for level, label, start, end in scenarios:
        term = ensure(m.AcademicTerm, {'name': f'UNI {level} {label}', 'school_year': '2026-2027'},
                      education_level=level, starts_on=start, ends_on=end, is_active=False,
                      calendar_context='Fictional development dates; no institutional approval')
        section = sections[level]
        if section.program.education_level != term.education_level:
            raise CommandError('Assignment section and term must have the same education level.')
        assignment = ensure(m.Assignment, {'term': term, 'subject': subjects[level],
                                          'section': section, 'faculty': faculty})
        if level == 'TERTIARY':
            ensure(m.TeachingAssignment, {'assignment': assignment, 'component': 'LECTURE', 'meeting_index': 1},
                   term=term, subject=subjects[level], section=section, faculty=faculty, duration_minutes=60)
        else:
            offering = ensure(m.SubjectOffering, {'requirement': requirement, 'cohort': cohort,
                                                  'academic_term': term}, academic_period='Development period',
                              is_approved=False)
            plan = ensure(m.DeliveryPlan, {'offering': offering},
                          reference_title='Fictional proposal only', is_approved=False)
            component = ensure(m.DeliveryComponent, {'plan': plan, 'instruction': 'Guided communication'},
                               duration_minutes=60, meeting_count=1)
            config = ensure(m.SHSAssignmentConfiguration, {'assignment': assignment}, delivery_plan=plan,
                            starts_on=start, ends_on=end, is_confirmed=False)
            ensure(m.SHSMeetingPattern, {'configuration': config, 'component': component, 'sequence': 1},
                   recurrence='DATED', weekday=0, meeting_date=start, window_start=time(8), window_end=time(12),
                   required_room_type='LECTURE', room=room,
                   room_approval_reference='UNAPPROVED fictional development room proposal')
    for owner in ({'faculty': faculty}, {'room': room}, *({'section': s} for s in sections.values())):
        for day in range(5):
            ensure(m.Availability, {**owner, 'day': day, 'kind': 'AVAILABLE',
                                    'start_time': time(8), 'end_time': time(17)})
    return 'Representative data verified: 2 levels, 3 terms, 3 assignments, 1 shared faculty and room. SHS approvals remain inactive.'
