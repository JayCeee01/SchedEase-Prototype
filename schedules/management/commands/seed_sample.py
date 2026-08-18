from datetime import date, time
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from schedules.models import (
    AcademicTerm,
    Availability,
    AvailabilityKind,
    Credential,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    Program,
    Profile,
    Role,
    Room,
    RoomKind,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
)
from schedules.services.time import SCHOOL_END, SCHOOL_START


class Command(BaseCommand):
    help = "Seed sample academic data for local testing."

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True, "email": "admin@schedease.local"})
        admin.email = admin.email or "admin@schedease.local"
        admin.set_password("admin12345")
        admin.save()
        Profile.objects.get_or_create(user=admin, defaults={"role": Role.ADMIN})

        cs, _ = Department.objects.get_or_create(code="CCS", defaults={"name": "College of Computer Studies"})
        it, _ = Program.objects.get_or_create(department=cs, code="BSIT", defaults={"name": "Bachelor of Science in Information Technology"})
        y1, _ = YearLevel.objects.get_or_create(level=1, defaults={"label": "First Year"})
        y2, _ = YearLevel.objects.get_or_create(level=2, defaults={"label": "Second Year"})
        term, _ = AcademicTerm.objects.get_or_create(name="First Semester", school_year="2026-2027", defaults={"starts_on": date(2026, 8, 10), "ends_on": date(2026, 12, 18), "is_active": True})

        faculty_rows = [("F001", "Ada Santos"), ("F002", "Grace Reyes"), ("F003", "Alan Cruz")]
        faculty = []
        for username, full_name in faculty_rows:
            user, _ = User.objects.get_or_create(username=username.lower(), defaults={"email": f"{username.lower()}@schedease.local"})
            user.email = user.email or f"{username.lower()}@schedease.local"
            user.set_password("password123")
            user.save()
            Profile.objects.get_or_create(user=user, defaults={"role": Role.FACULTY})
            obj, _ = Faculty.objects.get_or_create(employee_id=username, defaults={"user": user, "department": cs, "full_name": full_name})
            faculty.append(obj)

        sec_a, _ = Section.objects.get_or_create(program=it, year_level=y1, name="A", defaults={"size": 36})
        sec_b, _ = Section.objects.get_or_create(program=it, year_level=y2, name="A", defaults={"size": 32})

        student_user, _ = User.objects.get_or_create(username="student", defaults={"email": "student@schedease.local"})
        student_user.email = student_user.email or "student@schedease.local"
        student_user.set_password("password123")
        student_user.save()
        Profile.objects.get_or_create(user=student_user, defaults={"role": Role.STUDENT})
        Student.objects.get_or_create(user=student_user, student_number="S2026-0001", defaults={"section": sec_a, "full_name": "Juan Dela Cruz"})

        lec_101, _ = Room.objects.get_or_create(name="Lec 101", defaults={"room_type": RoomKind.LECTURE, "capacity": 45})
        lec_102, _ = Room.objects.get_or_create(name="Lec 102", defaults={"room_type": RoomKind.LECTURE, "capacity": 35})
        comp_lab, _ = Room.objects.get_or_create(name="Comp Lab 1", defaults={"room_type": RoomKind.COMPUTER_LAB, "capacity": 40})
        sci_lab, _ = Room.objects.get_or_create(name="Sci Lab 1", defaults={"room_type": RoomKind.SCIENCE_LAB, "capacity": 35})
        for room in (lec_101, lec_102, comp_lab, sci_lab):
            for day in range(6):
                Availability.objects.get_or_create(
                    room=room, day=day, start_time=SCHOOL_START, end_time=SCHOOL_END,
                    kind=AvailabilityKind.AVAILABLE,
                )

        subjects = [
            ("IT101", "Computer Programming 1", 2, 3, RoomKind.COMPUTER_LAB),
            ("IT102", "Introduction to Computing", 3, 0, RoomKind.LECTURE),
            ("GE101", "Purposive Communication", 3, 0, RoomKind.LECTURE),
            ("IT201", "Data Structures", 2, 3, RoomKind.COMPUTER_LAB),
            ("SCI101", "Science, Technology and Society", 2, 1, RoomKind.SCIENCE_LAB),
        ]
        subject_objs = []
        for code, title, lecture, lab, room_type in subjects:
            subject, _ = Subject.objects.get_or_create(code=code, defaults={"title": title, "department": cs, "lecture_hours": lecture, "lab_hours": lab, "required_room_type": room_type})
            subject_objs.append(subject)

        programming, _ = Credential.objects.get_or_create(name="Programming")
        computing, _ = Credential.objects.get_or_create(name="Computing Foundations")
        communication, _ = Credential.objects.get_or_create(name="Communication")
        science, _ = Credential.objects.get_or_create(name="Science Education")
        software_dev, _ = Credential.objects.get_or_create(name="Software Development")

        FacultyCredential.objects.get_or_create(faculty=faculty[0], credential=programming, defaults={"issued_by": "College Dean"})
        FacultyCredential.objects.get_or_create(faculty=faculty[0], credential=software_dev, defaults={"issued_by": "College Dean"})
        FacultyCredential.objects.get_or_create(faculty=faculty[1], credential=computing, defaults={"issued_by": "College Dean"})
        FacultyCredential.objects.get_or_create(faculty=faculty[1], credential=communication, defaults={"issued_by": "College Dean"})
        FacultyCredential.objects.get_or_create(faculty=faculty[2], credential=science, defaults={"issued_by": "College Dean"})

        req, _ = SubjectCredentialRequirement.objects.get_or_create(subject=subject_objs[0], required_credential=programming)
        req.acceptable_equivalents.add(software_dev)
        SubjectCredentialRequirement.objects.get_or_create(subject=subject_objs[1], required_credential=computing)
        SubjectCredentialRequirement.objects.get_or_create(subject=subject_objs[2], required_credential=communication)
        req, _ = SubjectCredentialRequirement.objects.get_or_create(subject=subject_objs[3], required_credential=programming)
        req.acceptable_equivalents.add(software_dev)
        SubjectCredentialRequirement.objects.get_or_create(subject=subject_objs[4], required_credential=science)

        assignment_faculty = [faculty[0], faculty[1], faculty[1], faculty[0], faculty[2]]
        for i, subject in enumerate(subject_objs):
            section = sec_a if i < 3 else sec_b
            assignment, _ = TeachingAssignment.objects.get_or_create(term=term, subject=subject, section=section, defaults={"faculty": assignment_faculty[i]})
            if assignment.faculty_id != assignment_faculty[i].id:
                assignment.faculty = assignment_faculty[i]
                assignment.save(update_fields=["faculty"])

        Availability.objects.get_or_create(faculty=faculty[0], day=0, start_time=time(7), end_time=time(12), kind=AvailabilityKind.PREFERRED)
        Availability.objects.get_or_create(faculty=faculty[1], day=2, start_time=time(13), end_time=time(17), kind=AvailabilityKind.UNAVAILABLE)
        GASettings.objects.get_or_create(name="Default")

        self.stdout.write(self.style.SUCCESS("Seeded SchedEase sample data. Users: admin/admin12345, student/password123, f001/password123."))
