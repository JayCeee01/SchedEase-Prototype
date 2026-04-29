from datetime import date, time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import AcademicTerm, Availability, AvailabilityKind, Credential, CredentialOverride, Department, Faculty, FacultyCredential, GASettings, Profile, Program, Role, Room, RoomKind, Schedule, Section, Subject, SubjectCredentialRequirement, TeachingAssignment, YearLevel
from .services.credentials import faculty_qualification
from .services.ga import GeneticScheduler, Gene


class SchedulingTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(username="admin", password="admin12345", is_staff=True, is_superuser=True)
        Profile.objects.create(user=self.admin_user, role=Role.ADMIN)
        self.department = Department.objects.create(code="CCS", name="Computing")
        self.program = Program.objects.create(department=self.department, code="BSIT", name="IT")
        self.year = YearLevel.objects.create(level=1, label="First Year")
        self.section = Section.objects.create(program=self.program, year_level=self.year, name="A", size=30)
        self.faculty = Faculty.objects.create(department=self.department, employee_id="F1", full_name="Ada")
        self.room = Room.objects.create(name="Lab 1", room_type=RoomKind.COMPUTER_LAB, capacity=35)
        self.subject = Subject.objects.create(code="IT101", title="Programming", department=self.department, lecture_hours=2, lab_hours=1, required_room_type=RoomKind.COMPUTER_LAB)
        self.term = AcademicTerm.objects.create(name="First Semester", school_year="2026-2027", starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 1), is_active=True)
        self.assignment = TeachingAssignment.objects.create(term=self.term, subject=self.subject, faculty=self.faculty, section=self.section)
        self.settings = GASettings.objects.create(name="Fast", population_size=12, generations=8, mutation_rate=0.1, crossover_rate=0.8, elitism=2)

    def test_manual_entry_detects_room_capacity(self):
        small = Room.objects.create(name="Small Lab", room_type=RoomKind.COMPUTER_LAB, capacity=10)
        schedule = Schedule.objects.create(term=self.term, name="Draft")
        entry = schedule.entries.create(assignment=self.assignment, room=small, day=0, start_time=time(8), end_time=time(11))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_ga_penalizes_faculty_unavailability(self):
        Availability.objects.create(faculty=self.faculty, day=0, start_time=time(8), end_time=time(12), kind=AvailabilityKind.UNAVAILABLE)
        scheduler = GeneticScheduler(self.term, self.settings, seed=1)
        blocked = [Gene(self.assignment.id, self.room.id, 0, time(8), time(11))]
        allowed = [Gene(self.assignment.id, self.room.id, 1, time(8), time(11))]
        self.assertLess(scheduler.fitness(blocked), scheduler.fitness(allowed))

    def test_ga_generates_schedule_entries(self):
        scheduler = GeneticScheduler(self.term, self.settings, seed=2)
        schedule = scheduler.generate("Test Schedule")
        self.assertEqual(schedule.entries.count(), 1)
        entry = schedule.entries.first()
        self.assertEqual(entry.room.room_type, self.subject.required_room_type)

    def test_credential_exact_match_qualifies_faculty(self):
        credential = Credential.objects.create(name="Programming")
        SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        FacultyCredential.objects.create(faculty=self.faculty, credential=credential)

        self.assertTrue(faculty_qualification(self.faculty, self.subject)["qualified"])

    def test_related_credentials_only_work_when_explicitly_allowed(self):
        required = Credential.objects.create(name="Programming")
        related = Credential.objects.create(name="Software Development")
        requirement = SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=required)
        FacultyCredential.objects.create(faculty=self.faculty, credential=related)

        self.assertFalse(faculty_qualification(self.faculty, self.subject)["qualified"])
        requirement.acceptable_equivalents.add(related)
        self.assertTrue(faculty_qualification(self.faculty, self.subject)["qualified"])

    def test_ga_penalizes_missing_credentials_as_hard_constraint(self):
        required = Credential.objects.create(name="Programming")
        SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=required)
        scheduler = GeneticScheduler(self.term, self.settings, seed=3)
        chromosome = [Gene(self.assignment.id, self.room.id, 1, time(8), time(11))]
        unqualified_score = scheduler.fitness(chromosome)
        FacultyCredential.objects.create(faculty=self.faculty, credential=required)
        qualified_scheduler = GeneticScheduler(self.term, self.settings, seed=3)
        self.assertLess(unqualified_score, qualified_scheduler.fitness(chromosome))

    def test_manual_schedule_entry_requires_qualification_or_override(self):
        required = Credential.objects.create(name="Programming")
        SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=required)
        schedule = Schedule.objects.create(term=self.term, name="Draft")
        entry = schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))

        with self.assertRaises(ValidationError):
            entry.full_clean()

        CredentialOverride.objects.create(
            assignment=self.assignment,
            subject=self.subject,
            faculty=self.faculty,
            admin_user=self.admin_user,
            reason="Temporary emergency assignment.",
            missing_credentials="Missing Programming",
        )
        entry.full_clean()

    def test_assignment_override_confirmation_stores_audit_details(self):
        required = Credential.objects.create(name="Programming")
        SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=required)
        new_subject = Subject.objects.create(code="IT102", title="Advanced Programming", department=self.department, lecture_hours=3, lab_hours=0, required_room_type=RoomKind.COMPUTER_LAB)
        SubjectCredentialRequirement.objects.create(subject=new_subject, required_credential=required)
        self.client.login(username="admin", password="admin12345")

        response = self.client.post(
            "/schedules/manage/assignments/new/",
            {"term": self.term.id, "subject": new_subject.id, "faculty": self.faculty.id, "section": self.section.id},
        )
        self.assertContains(response, "Unqualified faculty assignment")

        response = self.client.post(
            "/schedules/manage/assignments/new/",
            {
                "term": self.term.id,
                "subject": new_subject.id,
                "faculty": self.faculty.id,
                "section": self.section.id,
                "credential_override_confirm": "yes",
                "credential_override_reason": "Special approval by dean.",
            },
        )
        self.assertEqual(response.status_code, 302)
        override = CredentialOverride.objects.get(subject=new_subject, faculty=self.faculty)
        self.assertEqual(override.admin_user, self.admin_user)
        self.assertIn("Programming", override.missing_credentials)
