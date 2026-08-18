from datetime import date, time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import AcademicTerm, Availability, AvailabilityKind, Credential, CredentialOverride, Department, Faculty, FacultyCredential, GASettings, Profile, Program, Role, Room, RoomKind, Schedule, ScheduleEntry, ScheduleStatus, Section, Student, Subject, SubjectCredentialRequirement, TeachingAssignment, YearLevel
from .services.credentials import faculty_qualification
from .services.ga import GeneticScheduler, Gene
from .services.room_utilization import filtered_rows, utilization_rows
from .services.schedule_comparison import compare_schedules
from .importers.full_tertiary import days, subject_title, time_pair


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

    def test_generate_page_reports_infeasible_result_without_server_error(self):
        from unittest.mock import patch

        self.client.login(username="admin", password="admin12345")
        with patch("schedules.views.GeneticScheduler.generate", side_effect=ValueError("No feasible test schedule.")):
            response = self.client.post("/schedules/generate/", {
                "term": self.term.id, "settings": self.settings.id, "name": "Impossible"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No feasible test schedule.")
        self.assertFalse(Schedule.objects.filter(name="Impossible").exists())

    def test_generate_page_has_accessible_loading_state(self):
        self.client.login(username="admin", password="admin12345")
        response = self.client.get("/schedules/generate/")
        self.assertContains(response, "data-schedule-generation")
        self.assertContains(response, "data-generation-loading")
        self.assertContains(response, 'role="status"')
        self.assertContains(response, "Please wait while SchedEase creates the schedule.")

    def test_backend_prevents_duplicate_generation_for_same_term(self):
        self.client.login(username="admin", password="admin12345")
        key = f"schedease-generation-term-{self.term.id}"
        cache.set(key, self.admin_user.id, timeout=60)
        try:
            response = self.client.post("/schedules/generate/", {
                "term": self.term.id, "settings": self.settings.id, "name": "Duplicate"})
        finally:
            cache.delete(key)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already being generated")
        self.assertFalse(Schedule.objects.filter(name="Duplicate").exists())

    def test_assignment_meetings_can_preserve_lecture_and_lab_separately(self):
        lab = TeachingAssignment.objects.create(term=self.term, subject=self.subject, faculty=self.faculty,
            section=self.section, component=TeachingAssignment.Component.LABORATORY, meeting_index=2,
            duration_minutes=90, required_room_type_override=RoomKind.COMPUTER_LAB)
        self.assertEqual(lab.required_duration_minutes, 90)
        self.assertEqual(lab.effective_room_type, RoomKind.COMPUTER_LAB)

    def test_manual_entry_enforces_room_availability(self):
        Availability.objects.create(room=self.room, day=0, start_time=time(8), end_time=time(12), kind=AvailabilityKind.AVAILABLE)
        schedule = Schedule.objects.create(term=self.term, name="Availability")
        entry = schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(13), end_time=time(16))
        with self.assertRaisesMessage(ValidationError, "Room is not available"):
            entry.full_clean()

    def test_room_utilization_calculates_latest_schedule_usage(self):
        schedule = Schedule.objects.create(term=self.term, name="Draft")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        rows = utilization_rows(schedule)
        row = next(item for item in rows if item.room == self.room)
        self.assertEqual(row.scheduled_hours, 3)
        self.assertEqual(row.assigned_classes, 1)
        self.assertGreater(row.utilization_percentage, 0)
        self.assertEqual(row.status, "Underutilized")

    def test_room_utilization_respects_room_available_hours(self):
        Availability.objects.create(room=self.room, day=0, start_time=time(8), end_time=time(12), kind=AvailabilityKind.AVAILABLE)
        Availability.objects.create(room=self.room, day=1, start_time=time(8), end_time=time(12), kind=AvailabilityKind.AVAILABLE)
        schedule = Schedule.objects.create(term=self.term, name="Draft")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        row = next(item for item in utilization_rows(schedule) if item.room == self.room)
        self.assertEqual(row.available_hours, 8)
        self.assertEqual(row.utilization_percentage, 37.5)
        self.assertEqual(row.status, "Optimized")

    def test_room_utilization_filters_and_exports(self):
        schedule = Schedule.objects.create(term=self.term, name="Draft")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        rows = filtered_rows(utilization_rows(schedule), query="Lab", room_type=RoomKind.COMPUTER_LAB, utilization_range="under")
        self.assertEqual(len(rows), 1)

        self.client.login(username="admin", password="admin12345")
        dashboard_response = self.client.get("/schedules/room-utilization/")
        self.assertContains(dashboard_response, "Room Utilization")
        csv_response = self.client.get("/schedules/room-utilization/export/csv/")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("room-utilization.csv", csv_response["Content-Disposition"])

    def test_ga_prefers_capacity_fit_for_room_utilization(self):
        huge_room = Room.objects.create(name="Auditorium", room_type=RoomKind.COMPUTER_LAB, capacity=250)
        scheduler = GeneticScheduler(self.term, self.settings, seed=4)
        fit_room = [Gene(self.assignment.id, self.room.id, 1, time(8), time(11))]
        oversized_room = [Gene(self.assignment.id, huge_room.id, 1, time(8), time(11))]
        self.assertGreater(scheduler.fitness(fit_room), scheduler.fitness(oversized_room))

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

    def test_landing_modal_accepts_email_or_username(self):
        self.admin_user.email = "admin@schedease.local"
        self.admin_user.save(update_fields=["email"])

        username_response = self.client.post("/", {"username": "admin", "password": "admin12345"})
        self.assertEqual(username_response.status_code, 302)
        self.assertEqual(username_response["Location"], "/dashboard/")

        self.client.logout()
        email_response = self.client.post("/", {"username": "admin@schedease.local", "password": "admin12345"})
        self.assertEqual(email_response.status_code, 302)
        self.assertEqual(email_response["Location"], "/dashboard/")

        self.client.logout()
        bad_response = self.client.post("/", {"username": "admin", "password": "wrong"})
        self.assertEqual(bad_response.status_code, 200)
        self.assertContains(bad_response, "login-modal-shell is-open")

    def test_full_workbook_time_parser_handles_excel_and_text_times(self):
        start, end, duration = time_pair("0.29166666666666669", "0.35416666666666669")
        self.assertEqual((start, end, duration), (time(7), time(8, 30), 90))
        start, end, duration = time_pair("1:00 PM", "2:30:00 PM")
        self.assertEqual((start, end, duration), (time(13), time(14, 30), 90))

    def test_full_workbook_normalizes_days_and_component_titles(self):
        self.assertEqual(days("M/Th"), [0, 3])
        self.assertEqual(subject_title("Advanced Web Programming (LAB)"), "Advanced Web Programming")

    def test_original_and_generated_schedules_remain_distinguishable(self):
        original = Schedule.objects.create(term=self.term, name="Imported", origin=Schedule.Origin.IMPORTED)
        original.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        generated = Schedule.objects.create(term=self.term, name="Generated", origin=Schedule.Origin.GENERATED)
        generated.entries.create(assignment=self.assignment, room=self.room, day=1, start_time=time(8), end_time=time(11))
        comparison = compare_schedules(self.term, original, generated)
        self.assertEqual(comparison["original"]["origin"], Schedule.Origin.IMPORTED)
        self.assertEqual(comparison["generated"]["origin"], Schedule.Origin.GENERATED)
        self.assertEqual(comparison["generation_status"], "complete")

    def test_manual_entry_requires_matching_term_and_duration(self):
        other_term = AcademicTerm.objects.create(name="Second", school_year="2026-2027", starts_on=date(2027, 1, 1), ends_on=date(2027, 5, 1))
        schedule = Schedule.objects.create(term=other_term, name="Wrong term")
        entry = ScheduleEntry(schedule=schedule, assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(10))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn("different academic term", str(caught.exception))
        self.assertIn("must be 180 minutes", str(caught.exception))

    def test_availability_requires_exactly_one_owner(self):
        item = Availability(faculty=self.faculty, room=self.room, day=0, start_time=time(8), end_time=time(10))
        with self.assertRaisesMessage(ValidationError, "exactly one"):
            item.full_clean()

    def test_schedule_cannot_contain_assignment_twice(self):
        schedule = Schedule.objects.create(term=self.term, name="Unique")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                schedule.entries.create(assignment=self.assignment, room=self.room, day=1, start_time=time(8), end_time=time(11))

    def test_publish_is_post_only_and_rejects_unscheduled_requirements(self):
        self.client.login(username="admin", password="admin12345")
        schedule = Schedule.objects.create(term=self.term, name="Incomplete")
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/publish/").status_code, 405)
        response = self.client.post(f"/schedules/{schedule.id}/publish/", follow=True)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, ScheduleStatus.DRAFT)
        self.assertContains(response, "Resolve conflicts before publishing")
        self.assertContains(response, "Unscheduled class")

    def test_publish_runs_full_validation_and_succeeds_when_complete(self):
        self.client.login(username="admin", password="admin12345")
        schedule = Schedule.objects.create(term=self.term, name="Complete")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        response = self.client.post(f"/schedules/{schedule.id}/publish/")
        schedule.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(schedule.status, ScheduleStatus.PUBLISHED)

    def test_non_admin_cannot_view_or_export_draft_schedule(self):
        student_user = User.objects.create_user(username="learner", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        Student.objects.create(user=student_user, section=self.section, student_number="S1", full_name="Learner")
        schedule = Schedule.objects.create(term=self.term, name="Private draft")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        self.client.login(username="learner", password="password123")
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/export/csv/").status_code, 404)
        schedule.status = ScheduleStatus.PUBLISHED
        schedule.save(update_fields=["status"])
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/").status_code, 200)

    def test_admin_sidebar_groups_real_modules(self):
        self.client.login(username="admin", password="admin12345")
        response = self.client.get("/dashboard/")
        for group in ("Academic Management", "People &amp; Credentials", "Room Management", "Scheduling", "Administration"):
            self.assertContains(response, group)
        self.assertContains(response, 'data-nav-group="academic"')
        self.assertContains(response, ">Year Levels</a>", html=False)
        self.assertContains(response, ">Academic Terms</a>", html=False)

    def test_student_sidebar_hides_admin_groups(self):
        student_user = User.objects.create_user(username="navstudent", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        Student.objects.create(user=student_user, section=self.section, student_number="NAV1", full_name="Nav Student")
        self.client.login(username="navstudent", password="password123")
        response = self.client.get("/dashboard/")
        self.assertNotContains(response, 'data-nav-group="academic"')
        self.assertContains(response, "Browse Schedules")
