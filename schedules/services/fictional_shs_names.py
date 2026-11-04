"""Invented UAT display names; not official curriculum mappings or real records."""
from django.core.management.base import CommandError
from schedules import models as m

TERM_NAME = 'FUA SHS UAT Rehearsal (Two Weeks)'
FACULTY = (
    'John Michael Reyes', 'Maria Angelica Santos', 'Patricia Anne Cruz', 'Carlo Miguel Mendoza',
    'Ana Patricia Garcia', 'Joshua Gabriel Bautista', 'Christine Mae Villanueva', 'Rafael Antonio Navarro',
    'Camille Andrea Ramos', 'Paolo Vincent Flores', 'Isabel Therese Aquino', 'Marco Luis Santiago',
    'Nicole Beatrice Torres', 'Francis Adrian Castillo', 'Diana Louise Mercado', 'Emmanuel Jose Rivera',
    'Clarissa Marie Valdez', 'Gabriel Lorenzo Pascual', 'Angela Denise Soriano', 'Luis Fernando Salazar')
GIVEN = ('Adrian James', 'Sofia Isabelle', 'Daniel Luis', 'Bianca Nicole', 'Miguel Angelo',
         'Samantha Louise', 'Nathaniel Jude', 'Alyssa Camille', 'Ethan Gabriel', 'Chloe Andrea',
         'Joshua Rafael', 'Hannah Nicole', 'Matthew Elijah', 'Jasmine Claire', 'Aaron Vincent',
         'Julia Beatrice', 'Christian Paul', 'Kyla Therese', 'Sean Patrick', 'Trisha Mae')
SURNAMES = ('Mendoza', 'Garcia', 'Ramos', 'Torres', 'Fernandez', 'Castillo', 'Dela Cruz', 'Villanueva')
PROGRAMS = (
    ('Science Exploration', 'STEM - Science, Technology, Engineering, and Mathematics'),
    ('Digital Studies', 'ICT - Information and Communications Technology'),
    ('Business Studies', 'ABM - Accountancy, Business, and Management'),
    ('Humanities Studies', 'HUMSS - Humanities and Social Sciences'))
OLD_SUBJECTS = ('Communication', 'Mathematics', 'Research', 'Society', 'Wellness', 'Creative Practice', 'Applied Studies', 'Digital Workshop')
SUBJECTS = (
    ('Oral Communication', 'General Mathematics', 'Practical Research 1', 'Earth and Life Science',
     'Physical Education and Health', 'Scientific Writing', 'Introduction to Statistics', 'Computational Science Workshop'),
    ('Communication for Technology', 'Mathematics for Computing', 'Research in Technology', 'Digital Citizenship',
     'Physical Education and Health', 'Media and Information Literacy', 'Computer Programming Fundamentals', 'Computer Programming Workshop'),
    ('Business Communication', 'Business Mathematics', 'Practical Research 2', 'Organization and Management',
     'Physical Education and Health', 'Creative Business Presentation', 'Entrepreneurship', 'Business Spreadsheet Workshop'),
    ('Reading and Writing', 'Statistics and Probability', 'Introduction to Social Research', 'Understanding Culture, Society, and Politics',
     'Physical Education and Health', 'Creative Writing', 'Community Engagement', 'Digital Media Workshop'))


def naming_plan():
    plan = []
    def add(model, lookup, field, old, new):
        obj = model.objects.get(**lookup)
        if getattr(obj, field) not in (old, new):
            raise CommandError(f'Unexpected {model.__name__}.{field} on record {obj.pk}; refusing overwrite.')
        plan.append((obj, field, new))
    for i, name in enumerate(FACULTY):
        add(m.Faculty, {'employee_id': f'FUA{i+1:03}'}, 'full_name', f'Fictional Instructor {i+1:02}', name)
    for section in range(8):
        for student in range(20):
            add(m.Student, {'student_number': f'0096{section+1:02}{student+1:03}'}, 'full_name',
                f'Fictional Learner {section+1:02}-{student+1:02}', f'{GIVEN[student]} {SURNAMES[section]}')
    for i in range(12):
        old = f'FUA Room {i+1:02}'
        new = f'Lecture Room {301+i}' if i < 8 else f'Computer Laboratory {301+i-8}'
        room = m.Room.objects.get(name__in=(old, new))
        if room.room_type != ('LECTURE' if i < 8 else 'COMPUTER_LAB'):
            raise CommandError('Room type does not match naming plan.')
        add(m.Room, {'pk': room.pk}, 'name', old, new)
    for i, (old, new) in enumerate(PROGRAMS):
        code = f'FUA{i+1}'
        add(m.Program, {'code': code}, 'name', 'Fictional '+old, new+' (UAT)')
        add(m.AcademicPathway, {'code': code}, 'name', 'Fictional '+old, new+' (UAT)')
        for grade in (11, 12):
            add(m.Section, {'program__code': code, 'year_level__level': grade}, 'name', 'UAT', 'A')
        for j, title in enumerate(SUBJECTS[i]):
            add(m.Subject, {'code': f'{code}-{j+1:02}'}, 'title', f'Fictional {old}: {OLD_SUBJECTS[j]}', title)
    add(m.Department, {'code': 'FUA'}, 'name', 'Fictional UAT SHS Department', 'Senior High School Department (Synthetic UAT)')
    add(m.AcademicTerm, {'school_year': '2026-2027'}, 'name', 'FUA Fictional two-week rehearsal', TERM_NAME)
    return plan


def apply_names():
    """Caller owns transaction. Validate the entire plan before any updates."""
    if m.Schedule.objects.exists() or m.TeachingAssignment.objects.exists():
        raise CommandError('Naming requires the pre-generation UAT dataset.')
    plan = naming_plan()
    changed = 0
    for obj, field, name in plan:
        if getattr(obj, field) == name:
            continue
        setattr(obj, field, name)
        obj.full_clean()
        obj.save(update_fields=[field])
        changed += 1
    return changed
