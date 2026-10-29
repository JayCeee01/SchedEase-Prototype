"""Add an explicitly fictional, two-week UAT dataset. Never an STI curriculum.

Requires an existing database, exact path/hash, and a new external encrypted
credential file. No resets, migrations, generation, or publication are performed.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
from datetime import date, time

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from schedules import models as m
from schedules.services.shs_scheduling import validate_configurations

PREFIX = 'FUA'
REFERENCE = 'Fictional UAT fixture only; not STI or DepEd institutional approval'
START, END = date(2026, 11, 2), date(2026, 11, 13)
COUNTS = {'Department': 1, 'Program': 4, 'YearLevel': 2, 'CurriculumVersion': 1,
          'AcademicPathway': 4, 'Cohort': 8, 'AcademicTerm': 1, 'Section': 8,
          'Faculty': 20, 'Room': 12, 'Subject': 32, 'Student': 160,
          'Assignment': 64, 'SHSAssignmentConfiguration': 64, 'SHSMeetingPattern': 64,
          'CurriculumSubjectRequirement': 64, 'SubjectOffering': 64,
          'DeliveryPlan': 64, 'DeliveryComponent': 64, 'FacultyContactMinutePolicy': 20,
          'Credential': 1, 'FacultyCredential': 20, 'SubjectCredentialRequirement': 32,
          'Profile': 28, 'GASettings': 1}


def create(model, **fields):
    obj = model(**fields)
    obj.full_clean()
    obj.save()
    return obj


def verify_dataset():
    for name, expected in COUNTS.items():
        if apps.get_model('schedules', name).objects.count() != expected:
            raise CommandError(f'Unexpected {name} count; no repair or overwrite attempted.')
    term = m.AcademicTerm.objects.get(name='FUA Fictional two-week rehearsal')
    validate_configurations(term)
    for student in m.Student.objects.select_related('section'):
        student.full_clean()
    for model, role in ((m.Faculty, 'FACULTY'), (m.Student, 'STUDENT')):
        for record in model.objects.filter(user__isnull=False).select_related('user__profile'):
            user = record.user
            if user.profile.role != role or user.is_staff or user.is_superuser or not user.is_active:
                raise CommandError('Fictional account permissions are inconsistent.')
    if m.Schedule.objects.exists() or m.TeachingAssignment.objects.exists():
        raise CommandError('Expected a pre-generation dataset; schedules/meetings already exist.')
    return COUNTS


def populate(passwords):
    """Called inside a transaction; reject nonempty or partially populated data."""
    if m.CurriculumVersion.objects.filter(family='FUA Fictional curriculum').exists():
        verify_dataset()
        return False
    if any(model.objects.exists() for model in apps.get_app_config('schedules').get_models()):
        raise CommandError('Existing application records found; refusing to mix or overwrite datasets.')
    User = get_user_model()
    if User.objects.filter(username__startswith='fua_').exists():
        raise CommandError('Conflicting fictional usernames exist.')
    def account(username, role):
        user = User(username=username, is_active=True, is_staff=False, is_superuser=False)
        validate_password(passwords[username], user)
        user.set_password(passwords[username])
        user.full_clean()
        user.save()
        create(m.Profile, user=user, role=role)
        return user
    version = create(m.CurriculumVersion, family='FUA Fictional curriculum', revision='UAT-1',
        reference_title=REFERENCE, verification_status='VERIFIED', is_active=True)
    department = create(m.Department, code=PREFIX, name='Fictional UAT SHS Department')
    term = create(m.AcademicTerm, name='FUA Fictional two-week rehearsal', school_year='2026-2027',
        starts_on=START, ends_on=END, education_level='SHS')
    years = {grade: create(m.YearLevel, level=grade, label=f'Grade {grade}') for grade in (11, 12)}
    credential = create(m.Credential, name='FUA Fictional Teaching Qualification', description=REFERENCE)
    faculty = []
    for i in range(20):
        person = create(m.Faculty, department=department, employee_id=f'FUA{i+1:03}',
            full_name=f'Fictional Instructor {i+1:02}', user=account(f'fua_faculty_{i+1:02}', 'FACULTY'))
        create(m.FacultyCredential, faculty=person, credential=credential, issued_on=date(2026, 1, 1), issued_by=REFERENCE)
        create(m.FacultyContactMinutePolicy, faculty=person, accounting_period='CALENDAR_WEEK',
            covered_levels='SHS_AND_TERTIARY', week_starts_on=0, starts_on=START, ends_on=date(2026,11,15),
            maximum_contact_minutes=600, reference=REFERENCE, is_verified=True, is_approved=True, is_active=True)
        faculty.append(person)
    rooms = [create(m.Room, name=f'FUA Room {i+1:02}', capacity=30,
                    room_type='LECTURE' if i < 8 else 'COMPUTER_LAB') for i in range(12)]
    for pathway_index, title in enumerate(('Science Exploration', 'Digital Studies', 'Business Studies', 'Humanities Studies')):
        code = f'FUA{pathway_index+1}'
        pathway = create(m.AcademicPathway, curriculum_version=version, code=code, name='Fictional '+title, kind='STRAND')
        program = create(m.Program, department=department, code=code, name='Fictional '+title, education_level='SHS')
        subjects = []
        for j, subject_title in enumerate(('Communication', 'Mathematics', 'Research', 'Society', 'Wellness', 'Creative Practice', 'Applied Studies', 'Digital Workshop')):
            subject = create(m.Subject, department=department, code=f'{code}-{j+1:02}', title=f'Fictional {title}: {subject_title}',
                lecture_hours=0 if j==7 else 1, lab_hours=1 if j==7 else 0,
                required_room_type='COMPUTER_LAB' if j==7 else 'LECTURE')
            create(m.SubjectCredentialRequirement, subject=subject, required_credential=credential, notes=REFERENCE)
            subjects.append(subject)
        for grade in (11, 12):
            index = pathway_index*2 + grade-11
            cohort = create(m.Cohort, curriculum_version=version, school_year='2026-2027', grade_level=grade,
                            pathway=pathway, implementation_status='PILOT')
            section = create(m.Section, program=program, year_level=years[grade], name='UAT', size=20, cohort=cohort)
            for student_index in range(20):
                user = account(f'fua_student_{index+1:02}', 'STUDENT') if student_index==0 else None
                create(m.Student, section=section, student_number=f'0096{index+1:02}{student_index+1:03}',
                       full_name=f'Fictional Learner {index+1:02}-{student_index+1:02}', user=user)
            for j, subject in enumerate(subjects):
                requirement = create(m.CurriculumSubjectRequirement, curriculum_version=version, subject=subject,
                    pathway=pathway, grade_level=grade, academic_period='UAT two-week period', classification='Fictional practice',
                    quantity=2, unit='HOURS', measurement_basis='PERIOD', reference_title=REFERENCE,
                    verification_status='VERIFIED', is_active=True)
                offering = create(m.SubjectOffering, requirement=requirement, cohort=cohort, academic_term=term,
                                  academic_period='UAT two-week period', is_approved=True)
                plan = create(m.DeliveryPlan, offering=offering, reference_title=REFERENCE, approval_reference=REFERENCE)
                component = create(m.DeliveryComponent, plan=plan, instruction='Computer workshop' if j==7 else 'Classroom instruction',
                                   duration_minutes=60, meeting_count=2)
                plan.is_approved=True
                plan.save()
                assignment = create(m.Assignment, term=term, subject=subject, section=section, faculty=faculty[(index+j)%20])
                config = create(m.SHSAssignmentConfiguration, assignment=assignment, delivery_plan=plan,
                                starts_on=START, ends_on=END, calendar_reference=REFERENCE)
                hour = 8+j//5 if j!=7 else 10+index//4
                room = rooms[index] if j!=7 else rooms[8+index%4]
                create(m.SHSMeetingPattern, configuration=config, component=component, sequence=1, recurrence='WEEKLY',
                    weekday=j%5, window_start=time(hour), window_end=time(hour+1), required_room_type=room.room_type,
                    room=room, room_approval_reference=REFERENCE)
                config.is_confirmed=True
                config.save()
    create(m.GASettings, name='FUA Bounded rehearsal', population_size=8, generations=5, elitism=1)
    verify_dataset()
    return True


def encrypted_credentials(path, passwords):
    """Windows DPAPI CurrentUser encryption; plaintext never reaches disk/logs."""
    if os.name != 'nt':
        raise CommandError('Credential storage requires Windows CurrentUser DPAPI.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_byte))]
    raw = json.dumps(passwords).encode('utf-8')
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
        raise CommandError('DPAPI credential encryption failed.')
    try:
        with path.open('xb') as output:
            output.write(ctypes.string_at(destination.data, destination.size))
    finally:
        ctypes.windll.kernel32.LocalFree(destination.data)


class Command(BaseCommand):
    help = 'Populate an empty, explicitly selected database with fictional SHS UAT records.'

    def add_arguments(self, parser):
        parser.add_argument('--database-path', required=True)
        parser.add_argument('--expected-sha256', required=True)
        parser.add_argument('--credentials-file', required=True)

    def handle(self, *args, **options):
        target = Path(options['database_path']).resolve(strict=True)
        configured = Path(connection.settings_dict['NAME']).resolve(strict=True)
        if configured != target or hashlib.sha256(target.read_bytes()).hexdigest() != options['expected_sha256'].lower():
            raise CommandError('Database path/hash mismatch.')
        credentials = Path(options['credentials_file']).resolve()
        from django.conf import settings
        if credentials.is_relative_to(Path(settings.BASE_DIR).resolve()):
            raise CommandError('Credentials must be stored outside the repository.')
        connection.ensure_connection()
        if connection.connection.in_transaction:
            raise CommandError('Unexpected existing transaction.')
        # Obtain the SQLite writer fence before checking records; release only on completion.
        connection.set_autocommit(False)
        connection.connection.execute('BEGIN EXCLUSIVE')
        try:
            users_before = list(get_user_model().objects.exclude(username__startswith='fua_').values())
            if m.CurriculumVersion.objects.filter(family='FUA Fictional curriculum').exists():
                verify_dataset()
                changed=False
            else:
                passwords = {f'fua_faculty_{i+1:02}': secrets.token_urlsafe(24) for i in range(20)}
                passwords.update({f'fua_student_{i+1:02}': secrets.token_urlsafe(24) for i in range(8)})
                encrypted_credentials(credentials, passwords)
                changed=populate(passwords)
            if users_before != list(get_user_model().objects.exclude(username__startswith='fua_').values()):
                raise CommandError('Existing account preservation check failed.')
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA integrity_check')
                if cursor.fetchall() != [('ok',)]:
                    raise CommandError('Integrity check failed.')
                cursor.execute('PRAGMA foreign_key_check')
                if cursor.fetchall():
                    raise CommandError('Foreign-key check failed.')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.set_autocommit(True)
        self.stdout.write(json.dumps({'created': changed, 'counts': COUNTS, 'schedules': 0}))
