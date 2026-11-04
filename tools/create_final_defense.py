"""Create-only fictional defense datasets. Never schedules, publishes or resets.

Run with the project's Python, one level per process. Academic choices use a
fixed seed; passwords deliberately use cryptographic randomness and DPAPI.
"""
import argparse
from collections import Counter
from datetime import date, time
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261104
REFERENCE = 'User-approved fictional defense configuration; not STI/DepEd institutional approval'
HEAD = ('schedules', '0034_publication_membership')


def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in ROOT.glob('*.sqlite3')}


def populate(level, passwords):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password
    from django.utils import timezone
    from schedules import models as m
    from schedules.management.commands.seed_fictional_shs_uat import create
    from schedules.services.fictional_shs_names import GIVEN
    shs = level == 'shs'
    education = 'SHS' if shs else 'TERTIARY'
    rng = random.Random(SEED)
    surnames = ['Reyes','Santos','Cruz','Mendoza','Garcia','Bautista','Navarro','Ramos',
                'Flores','Aquino','Santiago','Torres','Castillo','Mercado','Rivera','Valdez',
                'Pascual','Soriano','Salazar','Villanueva','Fernandez','Dela Cruz','Gonzales',
                'Lopez','Perez','Sanchez','Ramirez','Dizon','Tolentino','Aguilar','Manalo','De Leon']
    names = [f'{given} {surname}' for surname in surnames for given in GIVEN]
    rng.shuffle(names)
    User = get_user_model()
    def account(username, role):
        admin = role == 'ADMIN'
        user = User(username=username, is_active=True, is_staff=admin, is_superuser=admin)
        validate_password(passwords[username], user)
        user.set_password(passwords[username]); user.full_clean(); user.save()
        create(m.Profile, user=user, role=role)
        return user
    admin = account(f'{level}_demo_admin', 'ADMIN')
    department = create(m.Department, code='SHS' if shs else 'COL',
                        name='Fictional Senior High School' if shs else 'Fictional College Division')
    programs = [('STEM','Science, Technology, Engineering and Mathematics'),
                ('ICT','Information and Communications Technology')] if shs else [
                ('BSIT','Bachelor of Science in Information Technology'),
                ('BSCS','Bachelor of Science in Computer Science'),
                ('BSIS','Bachelor of Science in Information Systems'),
                ('BSBA','Bachelor of Science in Business Administration'),
                ('BSAIS','Bachelor of Science in Accounting Information Systems')]
    programs = [create(m.Program, department=department, code=code, name=name,
                       education_level=education) for code,name in programs]
    years = {n:create(m.YearLevel, level=n, label=f'Grade {n}' if shs else f'Year {n}')
             for n in ((11,12) if shs else (1,2,3,4))}
    terms = [create(m.AcademicTerm, name=f'{education} Defense {label}', school_year='2026-2027',
                    starts_on=start, ends_on=end, education_level=education, is_active=True,
                    calendar_context='Fictional two-week defense demonstration')
             for label,start,end in [('Baseline',date(2026,11,2),date(2026,11,15)),
                                     ('Live Demo',date(2026,11,16),date(2026,11,29))]]
    version = create(m.CurriculumVersion, family='Fictional Defense SHS', revision='1',
                     reference_title=REFERENCE, verification_status='VERIFIED', is_active=True) if shs else None
    pathways = [create(m.AcademicPathway, curriculum_version=version, code=p.code,
                       name=p.name, kind='STRAND') for p in programs] if shs else []
    cohorts = {(p,g):create(m.Cohort, curriculum_version=version, pathway=pathways[p],
                           grade_level=g, school_year='2026-2027', implementation_status='PILOT')
               for p in range(2) for g in (11,12)} if shs else {}
    credentials = [create(m.Credential, name=f'{p.code} Demonstration Teaching Qualification',
                          description=REFERENCE) for p in programs]
    faculty = []
    for i in range(12 if shs else 24):
        username = f'{level}_demo_faculty' if i == 0 else f'{level}_faculty_{i+1:02}'
        person = create(m.Faculty, department=department, employee_id=f'{education}-EMP-{i+1:03}',
                        full_name=names[500+i], user=account(username,'FACULTY'), max_weekly_hours=24)
        create(m.FacultyCredential, faculty=person, credential=credentials[i%len(programs)],
               issued_on=date(2026,1,1), issued_by='Fictional Defense Academic Office', notes=REFERENCE)
        if shs:
            create(m.FacultyContactMinutePolicy, faculty=person, accounting_period='CALENDAR_WEEK',
                   covered_levels='SHS_AND_TERTIARY', week_starts_on=0, starts_on=terms[0].starts_on,
                   ends_on=terms[1].ends_on, maximum_contact_minutes=600, reference=REFERENCE,
                   is_verified=True,is_approved=True,is_active=True)
        faculty.append(person)
    sections = []
    for i in range(8 if shs else 16):
        p = i//4 if shs else i%5
        grade = 11+(i//2)%2 if shs else 1+i//5
        section = create(m.Section, program=programs[p], year_level=years[grade], name=f'{i+1:03}',
                         size=28 if shs else 26, cohort=cohorts.get((p,grade)))
        sections.append(section)
        for j in range(section.size):
            # One baseline and one live-demo student; all other students need no login.
            representative = j == 0 and i in (0,7 if shs else 15)
            username = f'{level}_demo_student' if i == 0 else f'{level}_live_student'
            create(m.Student, section=section, student_number=f'{11 if shs else 21}{i+1:03}{j+1:03}',
                   full_name=names[i*section.size+j], user=account(username,'STUDENT') if representative else None)
    rooms = [create(m.Room, name=f'{education}-'+('CL' if i>= (6 if shs else 9) else 'R')+f'{i+1:02}',
                    room_type='COMPUTER_LAB' if i >= (6 if shs else 9) else 'LECTURE', capacity=36)
             for i in range(8 if shs else 12)]
    for owner_type, owners in [('faculty',faculty),('section',sections),('room',rooms)]:
        for owner in owners:
            for day in range(5 if shs else 6):
                create(m.Availability, **{owner_type:owner}, day=day, start_time=time(8),
                       end_time=time(17), kind='AVAILABLE')
    titles = [
        ['Programming Fundamentals','Data Structures','Database Systems','Computer Networks','Web Development','Systems Analysis','Information Security','Software Engineering'],
        ['Computing Foundations','Discrete Mathematics','Algorithms','Object-Oriented Programming','Operating Systems','Artificial Intelligence','Computer Architecture','Software Testing'],
        ['Information Systems Fundamentals','Business Process Management','Enterprise Systems','Data Management','Systems Integration','IT Project Management','Decision Support Systems','Application Development'],
        ['Principles of Management','Marketing Management','Business Mathematics','Financial Management','Organizational Behavior','Entrepreneurship','Business Research','Business Analytics'],
        ['Accounting Fundamentals','Accounting Information Systems','Cost Accounting','Business Law','Financial Reporting','Auditing Principles','Spreadsheet Applications','Internal Control']]
    if shs:
        titles = [
            ['Oral Communication','General Mathematics','Earth and Life Science','Practical Research 1','Statistics and Probability','Reading and Writing','General Biology','Pre-Calculus','Scientific Writing','Computational Science Workshop'],
            ['Communication for Technology','Mathematics for Computing','Digital Citizenship','Computer Systems Fundamentals','Media and Information Literacy','Research in Technology','Programming Fundamentals','Web Design','Entrepreneurship','Computer Programming Workshop']]
    subjects = []
    for p, row in enumerate(titles):
        group = []
        for j,title in enumerate(row):
            lab = j == 9 if shs else p<3 and j in (0,2,4,7) or p==4 and j==6
            subject = create(m.Subject, department=department, code=f'{programs[p].code}{j+101}',title=title,
                             lecture_hours=(0 if lab else 1) if shs else (2 if lab else 3),
                             lab_hours=1 if lab else 0, required_room_type='COMPUTER_LAB' if lab else 'LECTURE',
                             units=0 if shs else 3)
            create(m.SubjectCredentialRequirement,subject=subject,required_credential=credentials[p],notes=REFERENCE)
            group.append(subject)
        subjects.append(group)
    loads = Counter()
    occupied = set()
    for i,section in enumerate(sections):
        p = i//4 if shs else i%5
        term = terms[int(i in (3,7))] if shs else terms[int(i>=12)]
        count = (6 if i<4 else 5) if shs else (6 if i<4 else 5)
        for j in range(count):
            subject = subjects[p][(j+4*(section.year_level.level-11))%10] if shs else subjects[p][(j+3*(i//5))%8]
            eligible = [f for n,f in enumerate(faculty) if n%len(programs)==p]
            person = min(eligible,key=lambda f:(loads[term.pk,f.pk],f.pk))
            loads[term.pk,person.pk] += 60 if shs else 180
            a = create(m.Assignment,term=term,subject=subject,section=section,faculty=person)
            if not shs:
                meetings = [('LECTURE',120),('LABORATORY',60)] if subject.lab_hours else [('LECTURE',90),('LECTURE',90)]
                for index,(component,minutes) in enumerate(meetings,1):
                    create(m.TeachingAssignment,assignment=a,term=term,subject=subject,section=section,faculty=person,
                           component=component,meeting_index=index,duration_minutes=minutes,
                           required_room_type_override='COMPUTER_LAB' if component=='LABORATORY' else 'LECTURE')
                continue
            requirement, _ = m.CurriculumSubjectRequirement.objects.get_or_create(
                curriculum_version=version,subject=subject,pathway=section.cohort.pathway,
                grade_level=section.year_level.level,academic_period='Defense two-week module',
                defaults=dict(classification='Fictional demonstration module',quantity=2,unit='HOURS',
                              measurement_basis='PERIOD',reference_title=REFERENCE,verification_status='VERIFIED',is_active=True))
            requirement.full_clean()
            offering, _ = m.SubjectOffering.objects.get_or_create(requirement=requirement,cohort=section.cohort,
                         academic_term=term,defaults=dict(academic_period=requirement.academic_period,is_approved=True))
            offering.full_clean()
            plan = m.DeliveryPlan.objects.filter(offering=offering).first()
            if plan is None:
                plan=create(m.DeliveryPlan,offering=offering,reference_title=REFERENCE,approval_reference=REFERENCE)
                create(m.DeliveryComponent,plan=plan,instruction='Computer laboratory' if subject.lab_hours else 'Classroom instruction',
                       duration_minutes=60,meeting_count=2)
                plan.is_approved=True; plan.approved_by=admin; plan.approved_at=timezone.now(); plan.save()
            config=create(m.SHSAssignmentConfiguration,assignment=a,delivery_plan=plan,
                          starts_on=term.starts_on,ends_on=term.ends_on,calendar_reference=REFERENCE)
            # A deterministic input-capacity witness, not a GA run or schedule.
            choice=None
            for day in range(5):
                for hour in range(8,16):
                    for room in rooms:
                        keys={(term.pk,day,hour,'faculty',person.pk),(term.pk,day,hour,'section',section.pk),(term.pk,day,hour,'room',room.pk)}
                        if room.room_type==subject.required_room_type and not keys & occupied:
                            choice=(day,hour,room,keys); break
                    if choice: break
                if choice: break
            if choice is None: raise RuntimeError('No conflict-free input window; stop without inventing feasibility.')
            day,hour,room,keys=choice; occupied.update(keys)
            create(m.SHSMeetingPattern,configuration=config,component=plan.components.get(),sequence=1,recurrence='WEEKLY',
                   weekday=day,window_start=time(hour),window_end=time(min(hour+2,17)),
                   required_room_type=room.room_type,room=room,room_approval_reference=REFERENCE)
            config.is_confirmed=True; config.save()
    create(m.GASettings,name='Defense default (unbenchmarked)')
    return verify(level, passwords)


def verify(level, passwords):
    from django.contrib.auth import authenticate, get_user_model
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from schedules import models as m
    from schedules.services.credentials import faculty_qualification
    from schedules.services.meetings import meeting_requirement_errors, meeting_records
    from schedules.services.shs_scheduling import validate_configurations
    shs=level=='shs'
    expected=dict(Program=2 if shs else 5,Section=8 if shs else 16,Faculty=12 if shs else 24,
                  Student=224 if shs else 416,Subject=20 if shs else 40,Room=8 if shs else 12,
                  Assignment=44 if shs else 84,Profile=15 if shs else 27)
    for name,count in expected.items():
        actual=getattr(m,name).objects.count()
        if actual != count: raise RuntimeError(f'{name}: expected {count}, got {actual}')
    if get_user_model().objects.count()!=expected['Profile']: raise RuntimeError('Account count mismatch')
    for person in [*m.Faculty.objects.select_related('user__profile'),*m.Student.objects.select_related('user__profile')]:
        if person.user_id:
            u=person.user
            if u.is_staff or u.is_superuser or not u.is_active or u.profile.role != ('FACULTY' if isinstance(person,m.Faculty) else 'STUDENT'):
                raise RuntimeError('Invalid academic account permissions')
    for username,password in passwords.items():
        if authenticate(username=username,password=password) is None: raise RuntimeError('Authentication failed')
    admin=get_user_model().objects.get(username=f'{level}_demo_admin')
    if not (admin.is_staff and admin.is_superuser and admin.is_active and admin.profile.role=='ADMIN'):
        raise RuntimeError('Administrator permissions failed')
    for section in m.Section.objects.all():
        if section.student_set.count()!=section.size: raise RuntimeError('Section enrollment mismatch')
    term_counts={}
    for term in m.AcademicTerm.objects.all():
        load=Counter()
        for a in m.Assignment.objects.filter(term=term).select_related('faculty','subject','section'):
            if not faculty_qualification(a.faculty,a.subject,term)['qualified']: raise RuntimeError('Unqualified assignment')
            if not shs:
                meetings=list(a.meetings.all())
                if meeting_requirement_errors(a.subject,meeting_records(meetings)): raise RuntimeError('Invalid component totals')
                load[a.faculty_id]+=sum(x.required_duration_minutes for x in meetings)
                if load[a.faculty_id]>a.faculty.max_weekly_hours*60: raise RuntimeError('Faculty workload exceeded')
                for meeting in meetings:
                    if not m.Room.objects.filter(is_active=True,room_type=meeting.effective_room_type,capacity__gte=a.section.size).exists():
                        raise RuntimeError('No compatible room')
        if shs: validate_configurations(term)
        term_counts[term.name]=term.assignment_set.count()
    if any(model.objects.exists() for model in (m.Schedule,m.ScheduleEntry,m.ScheduleSnapshot,m.GenerationRun)):
        raise RuntimeError('Stage 2 must remain unscheduled')
    executor=MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()): raise RuntimeError('Pending migrations')
    with connection.cursor() as c:
        c.execute('PRAGMA integrity_check')
        if c.fetchall()!=[('ok',)]: raise RuntimeError('Integrity failed')
        c.execute('PRAGMA foreign_key_check')
        if c.fetchall(): raise RuntimeError('Foreign keys failed')
        c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'")
        triggers=c.fetchone()[0]
        if triggers<1: raise RuntimeError('Missing protection triggers')
    return dict(counts=expected,terms=term_counts,integrity='ok',foreign_key_violations=0,
                triggers=triggers,migration=HEAD[1],accounts_authenticated=len(passwords),
                schedules=0,shs_evidence='Deferred to controlled Stage 3 preparation' if shs else 'Not applicable')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',choices=['tertiary','shs'],required=True)
    parser.add_argument('--credentials-directory',type=Path,required=True)
    parser.add_argument('--approve-synthetic-defense',action='store_true',required=True)
    args=parser.parse_args()
    target=ROOT/f'{args.level}_final_defense.sqlite3'
    if any(Path(str(target)+s).exists() for s in ('','-wal','-shm','-journal')):
        parser.error('Target or sidecar exists; never overwrite or reseed.')
    directory=args.credentials_directory.resolve(strict=True)
    if directory.is_relative_to(ROOT): parser.error('Credentials must remain outside repository')
    output=directory/f'{args.level}-credentials.dpapi'
    if output.exists(): parser.error('Credential output already exists')
    before=hashes()
    os.environ['SCHED_EASE_DATABASE_URL']='sqlite:///'+target.as_posix()
    os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
    sys.path.insert(0,str(ROOT))
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection,transaction
    from django.db.migrations.loader import MigrationLoader
    from schedules.management.commands.seed_fictional_shs_uat import encrypted_credentials
    if Path(settings.DATABASES['default']['NAME']).resolve()!=target:
        raise RuntimeError('Resolved database does not equal the approved new target')
    loader=MigrationLoader(None)
    if loader.graph.leaf_nodes('schedules')!=[HEAD]: raise RuntimeError('Migration head changed; review required')
    n=12 if args.level=='shs' else 24
    usernames=[f'{args.level}_demo_admin',f'{args.level}_demo_faculty',f'{args.level}_demo_student',f'{args.level}_live_student']
    usernames += [f'{args.level}_faculty_{i+1:02}' for i in range(1,n)]
    passwords={name:secrets.token_urlsafe(24) for name in usernames}
    encrypted_credentials(output,passwords)
    # Exclusive reservation prevents a check/create race. No existing DB is accepted.
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
    try:
        call_command('migrate',interactive=False,verbosity=0)
        with transaction.atomic():
            result=populate(args.level,passwords)
        call_command('check',verbosity=0)
        connection.close()
        result['path']=str(target)
        result['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        result['seed']=SEED
        result['preserved_database_hashes']=before
        result['credential_file']=str(output)
        with (directory/f'{args.level}-stage2-results.json').open('x',encoding='utf-8') as f:
            json.dump(result,f,indent=2)
        print(json.dumps(result,indent=2))
    finally:
        connection.close()
        after=hashes()
        if any(after.get(name)!=value for name,value in before.items()):
            raise RuntimeError('Pre-existing database hash changed; investigate external writers')
        print(f'Pre-existing database hashes unchanged: {len(before)}')


if __name__=='__main__':
    main()
