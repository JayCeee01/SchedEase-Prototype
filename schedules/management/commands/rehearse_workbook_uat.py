"""Workbook dataset rehearsal ONLY. Refuses databases inside the repository."""
import hashlib
import json
from datetime import date, time, timedelta
from pathlib import Path
import openpyxl
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from schedules import models as m
from schedules.management.commands.seed_fictional_shs_uat import create
from schedules.services.fictional_shs_names import GIVEN, SURNAMES

NOTE = 'Synthetic workbook UAT configuration; not STI or DepEd approval'


def populate(workbook, level):
    w = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    data = {s.title[:2]: [r for r in list(s.values)[1:] if r[0] is not None]
            for s in w if s.title[:2].isdigit()}
    w.close()
    if m.Schedule.objects.exists() or m.GenerationRun.objects.exists():
        raise CommandError('Refusing to clear schedules or generation history.')
    accounts = list(get_user_model().objects.order_by('pk').values())
    profiles = list(m.Profile.objects.order_by('pk').values())
    m.Faculty.objects.update(user=None)
    m.Student.objects.update(user=None)
    for plan in m.DeliveryPlan.objects.all():
        plan.is_approved = False
        plan.save()
    for name in ('SHSMeetingPattern','SHSSectionParticipation','SHSAssignmentConfiguration','TeachingAssignment',
                 'Assignment','DeliveryComponent','DeliveryPlan','SubjectOffering','CurriculumSubjectRequirement',
                 'FacultyContactMinutePolicy','FacultyCredential','SubjectCredentialRequirement','Availability',
                 'Student','Faculty','Section','Cohort','AcademicPathway','Program','YearLevel','Subject','Room',
                 'Credential','AcademicTerm','CurriculumVersion','Department','GASettings'):
        getattr(m, name).objects.all().delete()
    program_rows = [r for r in data['02'] if r[3] == level]
    program_codes = {r[0] for r in program_rows}
    section_rows = [r for r in data['08'] if r[1] in program_codes]
    term_rows = [r for r in data['04'] if r[3] == level]
    term_keys = {r[0] for r in term_rows}
    assignment_rows = [r for r in data['13'] if r[1] in term_keys]
    faculty_ids = {r[4] for r in assignment_rows} | {r[5] for r in section_rows if r[5]}
    subject_rows = [r for r in data['10'] if (r[2] == 'SHS') == (level == 'SHS')]
    department_ids = {r[2] for r in program_rows+subject_rows} | {r[2] for r in data['05'] if r[0] in faculty_ids}
    departments = {r[0]: create(m.Department, code=r[0], name=r[1]) for r in data['01'] if r[0] in department_ids}
    programs = {r[0]: create(m.Program, code=r[0], name=r[1], department=departments[r[2]], education_level=level) for r in program_rows}
    years = {r[0]: create(m.YearLevel, level=r[0], label=r[1]) for r in data['03'] if (r[0] in (11,12)) == (level=='SHS')}
    terms = {r[0]: create(m.AcademicTerm, name=r[1], school_year=r[2], education_level=level,
                         starts_on=date.fromisoformat(r[4]), ends_on=date.fromisoformat(r[5])) for r in term_rows}
    faculty = {r[0]: create(m.Faculty, employee_id=r[0], full_name=r[1], department=departments[r[2]], max_weekly_hours=r[3])
               for r in data['05'] if r[0] in faculty_ids}
    credentials = {r[0]: create(m.Credential, name=r[0], description=r[1]) for r in data['06']}
    for r in data['07']:
        if r[0] in faculty:
            create(m.FacultyCredential, faculty=faculty[r[0]], credential=credentials[r[1]], issued_by=r[2] or '',
                   issued_on=date.fromisoformat(r[3]) if r[3] else None, expires_on=date.fromisoformat(r[4]) if r[4] else None, notes=r[5] or '')
    version = create(m.CurriculumVersion, family='Workbook synthetic UAT', revision='1', reference_title=NOTE,
                     verification_status='VERIFIED', is_active=True) if level=='SHS' else None
    pathways = {code: create(m.AcademicPathway, curriculum_version=version, code=code, name=p.name, kind='STRAND')
                for code,p in programs.items()} if version else {}
    sections = {}
    for index,r in enumerate(section_rows):
        cohort = create(m.Cohort, curriculum_version=version, school_year='2026-2027', grade_level=r[2],
                        pathway=pathways[r[1]], implementation_status='PILOT') if version else None
        sections[r[0]] = create(m.Section, program=programs[r[1]], year_level=years[r[2]], name=r[3].split('-',1)[-1],
                                size=r[4], adviser=faculty.get(r[5]), cohort=cohort)
        for n in range(3):
            create(m.Student, section=sections[r[0]], student_number=f'{11 if level=="SHS" else 21}{index:03}{n:03}',
                   full_name=f'{GIVEN[(index*3+n)%20]} {SURNAMES[(index*3+n)//20]}')
    rooms = {r[0]: create(m.Room, name=r[0], room_type=r[1], capacity=r[2], is_active=r[3]) for r in data['09']}
    subjects = {r[0]: create(m.Subject, code=r[0], title=r[1], department=departments[r[2]], units=r[3] if r[3] is not None else 0,
                            lecture_hours=r[4] if r[4] is not None else 0, lab_hours=r[5] if r[5] is not None else 0,
                            required_room_type=r[6]) for r in subject_rows}
    requirements = {}
    for r in data['11']:
        if r[0] in subjects:
            requirements[(r[0],r[1])] = create(m.SubjectCredentialRequirement, subject=subjects[r[0]], required_credential=credentials[r[1]], notes=r[2] or '')
    for r in data['12']:
        if (r[0],r[1]) in requirements:
            requirements[(r[0],r[1])].acceptable_equivalents.add(credentials[r[2]])
    assignments = {r[0]: create(m.Assignment, term=terms[r[1]], subject=subjects[r[2]], section=sections[r[3]], faculty=faculty[r[4]])
                   for r in assignment_rows}
    for r in data['15']:
        owner = faculty.get(r[1]) if r[0]=='FACULTY' else rooms.get(r[2]) if r[0]=='ROOM' else sections.get(r[3])
        if owner:
            create(m.Availability, **{r[0].lower():owner}, day=r[4], start_time=time.fromisoformat(r[5]), end_time=time.fromisoformat(r[6]), kind=r[7])
    if level=='TERTIARY':
        for r in data['14']:
            if r[0] in assignments:
                a=assignments[r[0]]
                create(m.TeachingAssignment, assignment=a, term=a.term, subject=a.subject, section=a.section, faculty=a.faculty,
                       component=r[5], meeting_index=r[6], duration_minutes=r[7], required_room_type_override=r[8] or '')
    else:
        for index,a in enumerate(assignments.values()):
            first=a.term.starts_on
            last=first+timedelta(days=11)
            req=create(m.CurriculumSubjectRequirement,curriculum_version=version,subject=a.subject,pathway=a.section.cohort.pathway,
                       grade_level=a.section.year_level.level,academic_period=a.term.name,classification='Synthetic UAT',
                       quantity=2,unit='HOURS',measurement_basis='PERIOD',reference_title=NOTE,verification_status='VERIFIED',is_active=True)
            offering=create(m.SubjectOffering,requirement=req,cohort=a.section.cohort,academic_term=a.term,academic_period=a.term.name,is_approved=True)
            plan=create(m.DeliveryPlan,offering=offering,reference_title=NOTE,approval_reference=NOTE)
            component=create(m.DeliveryComponent,plan=plan,instruction='Guided subject instruction',duration_minutes=60,meeting_count=2)
            plan.is_approved=True;plan.save()
            config=create(m.SHSAssignmentConfiguration,assignment=a,delivery_plan=plan,starts_on=first,ends_on=last,calendar_reference=NOTE)
            room=next(room for room in rooms.values() if room.room_type==a.subject.required_room_type and room.capacity>=a.section.size)
            create(m.SHSMeetingPattern,configuration=config,component=component,recurrence='WEEKLY',weekday=index%5,
                   window_start=time(8),window_end=time(17),required_room_type=room.room_type,room=room,room_approval_reference=NOTE)
            config.is_confirmed=True;config.save()
        for person in faculty.values():
            create(m.FacultyContactMinutePolicy,faculty=person,starts_on=min(t.starts_on for t in terms.values()),
                   ends_on=max(t.ends_on for t in terms.values())+timedelta(days=2),accounting_period='CALENDAR_WEEK',
                   covered_levels='SHS_AND_TERTIARY',week_starts_on=0,maximum_contact_minutes=600,
                   reference=NOTE,is_verified=True,is_approved=True,is_active=True)
    r=data['16'][0]
    create(m.GASettings,name=r[0],population_size=r[1],generations=r[2],mutation_rate=r[3],crossover_rate=r[4],elitism=r[5])
    assert accounts==list(get_user_model().objects.order_by('pk').values())
    assert profiles==list(m.Profile.objects.order_by('pk').values())
    return {name:getattr(m,name).objects.count() for name in ('Program','Section','Faculty','Subject','Room','Student','Assignment','TeachingAssignment','SHSMeetingPattern')}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--workbook',required=True)
        parser.add_argument('--level',choices=['SHS','TERTIARY'],required=True)
        parser.add_argument('--expected-sha256',required=True)

    def handle(self,*args,**options):
        path=Path(connection.settings_dict['NAME']).resolve(strict=True)
        if path.is_relative_to(Path(settings.BASE_DIR).resolve()) or path.parent.parent != Path(r'C:\Users\JEROME\SchedEase-Browser-UAT'):
            raise CommandError('Only an external disposable workspace is allowed.')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=options['expected_sha256'].lower():
            raise CommandError('Unexpected database hash.')
        with transaction.atomic():
            counts=populate(options['workbook'],options['level'])
            with connection.cursor() as c:
                c.execute('pragma foreign_key_check')
                assert not c.fetchall()
        self.stdout.write(json.dumps(counts))
