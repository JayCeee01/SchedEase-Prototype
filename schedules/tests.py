import json
from datetime import date, time
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import AcademicTerm, Assignment, Availability, AvailabilityKind, Credential, CredentialOverride, Department, Faculty, FacultyCredential, FormDraft, GASettings, GenerationIssue, GenerationRun, Profile, Program, Role, Room, RoomKind, Schedule, ScheduleEntry, ScheduleEntryAudit, ScheduleStatus, Section, Student, Subject, SubjectCredentialRequirement, TeachingAssignment, YearLevel
from .services.credentials import faculty_qualification
from .services.ga import GeneticScheduler, Gene
from .services.generation_issues import record_generation_messages
from .services.room_utilization import capacity_planning, filtered_rows, room_schedule_grid, utilization_rows, utilization_summary
from .services.schedule_comparison import compare_schedules
from .importers.full_tertiary import days, subject_title, time_pair
from .importers.tertiary_workbook import SELECTED_SECTIONS


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
        self.assertContains(response, "Schedule generation could not be completed")
        self.assertContains(response, "View Error Log")
        self.assertNotContains(response, "No feasible test schedule")
        self.assertFalse(Schedule.objects.filter(name="Impossible").exists())
        run = GenerationRun.objects.get(requested_name="Impossible")
        self.assertEqual(run.status, GenerationRun.Status.FAILED)
        self.assertEqual(run.issues.count(), 1)

    def test_generation_issue_is_categorized_and_associated_with_run(self):
        run = GenerationRun.objects.create(
            term=self.term, ga_settings=self.settings, requested_by=self.admin_user, requested_name="Problem run"
        )
        issues = record_generation_messages(
            run, "IT101 / BSIT-1A: no active Computer Laboratory has capacity 30."
        )
        self.assertEqual(issues[0].run, run)
        self.assertEqual(issues[0].category, GenerationIssue.Category.ROOM_CAPACITY)
        self.assertEqual(issues[0].assignment, self.assignment)
        self.assertEqual(issues[0].severity, GenerationIssue.Severity.ERROR)

    def test_warning_and_unscheduled_issue_are_supported(self):
        run = GenerationRun.objects.create(
            term=self.term, ga_settings=self.settings, requested_by=self.admin_user, requested_name="Warning run"
        )
        issues = record_generation_messages(
            run, "IT101 / BSIT-1A: class remains unscheduled.", severity=GenerationIssue.Severity.WARNING
        )
        self.assertEqual(issues[0].category, GenerationIssue.Category.UNSCHEDULED)
        self.assertEqual(issues[0].severity, GenerationIssue.Severity.WARNING)

    def test_unexpected_generation_failure_creates_critical_safe_log(self):
        from unittest.mock import patch

        self.client.login(username="admin", password="admin12345")
        with patch("schedules.views.GeneticScheduler.generate", side_effect=RuntimeError("private technical detail")):
            response = self.client.post("/schedules/generate/", {
                "term": self.term.id, "settings": self.settings.id, "name": "Crashed run"
            })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "private technical detail")
        issue = GenerationRun.objects.get(requested_name="Crashed run").issues.get()
        self.assertEqual(issue.severity, GenerationIssue.Severity.CRITICAL)
        self.assertNotIn("private technical detail", issue.reason)

    def test_error_log_filters_and_displays_issue_details(self):
        run = GenerationRun.objects.create(
            term=self.term, ga_settings=self.settings, requested_by=self.admin_user, requested_name="Filtered run"
        )
        issue = GenerationIssue.objects.create(
            run=run, assignment=self.assignment, category=GenerationIssue.Category.FACULTY_WORKLOAD,
            severity=GenerationIssue.Severity.ERROR, short_description="Faculty workload is too high.",
            reason="Ada exceeds the maximum weekly load.", suggested_action="Reassign one class."
        )
        self.client.login(username="admin", password="admin12345")
        response = self.client.get("/schedules/error-log/", {"run": run.pk, "severity": "ERROR", "q": "Ada"})
        self.assertContains(response, "Faculty workload is too high")
        self.assertContains(response, 'data-auto-tooltips="false"')
        self.assertContains(response, 'class="info-icon"', count=3)
        self.assertContains(response, 'class="field-label">Generation Run <span class="info-icon"', html=False)
        detail = self.client.get(f"/schedules/error-log/{issue.pk}/")
        self.assertContains(detail, "Reassign one class")
        self.client.post(f"/schedules/error-log/{issue.pk}/", {"status": "REVIEWED"})
        issue.refresh_from_db()
        self.assertEqual(issue.status, GenerationIssue.Status.REVIEWED)

    def test_error_log_is_restricted_to_administrators(self):
        student_user = User.objects.create_user(username="logstudent", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        Student.objects.create(user=student_user, section=self.section, student_number="LOG1", full_name="Log Student")
        self.client.login(username="logstudent", password="password123")
        response = self.client.get("/schedules/error-log/")
        self.assertEqual(response.status_code, 302)

    def test_successful_generation_run_has_no_error_issues(self):
        self.client.login(username="admin", password="admin12345")
        response = self.client.post("/schedules/generate/", {
            "term": self.term.id, "settings": self.settings.id, "name": "Successful run"
        })
        self.assertEqual(response.status_code, 302)
        run = GenerationRun.objects.get(requested_name="Successful run")
        self.assertEqual(run.status, GenerationRun.Status.SUCCEEDED)
        self.assertIsNotNone(run.schedule)
        self.assertFalse(run.issues.exists())

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
        self.assertEqual(row.status, "Moderately Utilized")

    def test_room_utilization_calculates_daily_and_weighted_weekly_values(self):
        Availability.objects.create(room=self.room, day=0, start_time=time(7), end_time=time(19), kind=AvailabilityKind.AVAILABLE)
        Availability.objects.create(room=self.room, day=1, start_time=time(7), end_time=time(13), kind=AvailabilityKind.AVAILABLE)
        schedule = Schedule.objects.create(term=self.term, name="Variable availability")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        row = next(item for item in utilization_rows(schedule) if item.room == self.room)
        self.assertEqual(row.daily[0]["percentage"], 25.0)
        self.assertEqual(row.daily[1]["percentage"], 0)
        self.assertEqual(row.available_hours, 18)
        self.assertEqual(row.utilization_percentage, 16.7)
        self.assertEqual(row.capacity_utilization, 85.7)
        self.assertEqual(utilization_summary([row])["average_utilization"], 16.7)

    def test_room_schedule_uses_thirty_minute_slots(self):
        schedule = Schedule.objects.create(term=self.term, name="Room grid")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        grid = room_schedule_grid(self.room, schedule)
        self.assertEqual(len(grid), 24)
        eight_am = next(row for row in grid if row["start"] == time(8))
        self.assertEqual(eight_am["cells"][0]["entries"][0].assignment, self.assignment)
        self.assertFalse(eight_am["cells"][1]["entries"])
        self.assertTrue(eight_am["cells"][1]["available"])

    def test_room_capacity_planning_uses_actual_room_types_and_requirements(self):
        culinary_room = Room.objects.create(name="Training Kitchen", room_type=RoomKind.SPECIAL, capacity=30)
        culinary_subject = Subject.objects.create(
            code="CUL101", title="Culinary Laboratory", department=self.department,
            lecture_hours=0, lab_hours=3, required_room_type=RoomKind.SPECIAL,
        )
        TeachingAssignment.objects.create(
            term=self.term, subject=culinary_subject, faculty=self.faculty, section=self.section,
            component=TeachingAssignment.Component.LABORATORY, meeting_index=1, duration_minutes=180,
        )
        planning, lecture = capacity_planning(self.term, {"students": 80, "class_size": 40, "subjects": 5, "hours": 3})
        computer = next(row for row in planning if row["room_type"] == RoomKind.COMPUTER_LAB)
        culinary = next(row for row in planning if row["room_type"] == RoomKind.SPECIAL)
        self.assertEqual(computer["requirements"], 1)
        self.assertEqual(computer["required_hours"], 3)
        self.assertEqual(culinary["rooms"], 1)
        self.assertEqual(culinary["required_hours"], 3)
        self.assertEqual(lecture["sections"], 2)
        self.assertEqual(lecture["required_hours"], 30)

    def test_room_modules_filter_schedule_version_and_require_admin(self):
        schedule = Schedule.objects.create(term=self.term, name="Selected room schedule")
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        self.client.login(username="admin", password="admin12345")
        utilization = self.client.get("/schedules/room-utilization/", {"term": self.term.pk, "schedule": schedule.pk})
        self.assertContains(utilization, "Selected room schedule")
        self.assertContains(utilization, "Monday")
        room_schedule = self.client.get("/schedules/room-schedule/", {"schedule": schedule.pk, "room": self.room.pk})
        self.assertContains(room_schedule, "Weekly room timetable")
        self.assertContains(room_schedule, self.subject.code)
        planning = self.client.get("/schedules/room-capacity-planning/", {"term": self.term.pk})
        self.assertContains(planning, "Plan room capacity")

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

    def test_representative_sample_uses_three_complete_sections(self):
        self.assertEqual(
            SELECTED_SECTIONS,
            (("ACT", 1, "201"), ("BSCS", 3, "201"), ("BSAIS", 2, "201")),
        )

    def test_original_and_generated_schedules_remain_distinguishable(self):
        original = Schedule.objects.create(term=self.term, name="Imported", origin=Schedule.Origin.IMPORTED)
        original.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        generated = Schedule.objects.create(term=self.term, name="Generated", origin=Schedule.Origin.GENERATED)
        generated.entries.create(assignment=self.assignment, room=self.room, day=1, start_time=time(8), end_time=time(11))
        comparison = compare_schedules(self.term, original, generated)
        self.assertEqual(comparison["original"]["origin"], Schedule.Origin.IMPORTED)
        self.assertEqual(comparison["generated"]["origin"], Schedule.Origin.GENERATED)
        self.assertEqual(comparison["generation_status"], "complete")

    def test_schedule_detail_defaults_to_grouped_academic_table(self):
        schedule = Schedule.objects.create(term=self.term, name="Academic Table")
        schedule.entries.create(
            assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11)
        )
        self.client.login(username="admin", password="admin12345")
        response = self.client.get(f"/schedules/{schedule.pk}/")
        self.assertContains(response, 'data-schedule-view-panel="table"')
        self.assertContains(response, 'data-schedule-view-panel="timetable" hidden')
        self.assertContains(response, "Course Description")
        self.assertContains(response, "Time Start")
        self.assertContains(response, "Instructor")
        self.assertContains(response, str(self.section))
        content = response.content.decode()
        self.assertLess(content.index(">Table View<"), content.index(">Timetable View<"))

    def test_schedule_detail_filters_by_day_and_shows_empty_state(self):
        schedule = Schedule.objects.create(term=self.term, name="Filtered Academic Table")
        schedule.entries.create(
            assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11)
        )
        self.client.login(username="admin", password="admin12345")
        response = self.client.get(f"/schedules/{schedule.pk}/", {"day": "5"})
        self.assertContains(response, "No schedule entries found")
        self.assertContains(response, '<option value="5" selected>Saturday</option>', html=True)

    def test_schedule_filters_apply_to_timetable_and_effective_overrides(self):
        schedule = Schedule.objects.create(term=self.term, name="Filtered Timetable")
        schedule.entries.create(
            assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11)
        )
        other_subject = Subject.objects.create(
            code="IT202", title="Networks", department=self.department,
            lecture_hours=3, lab_hours=0, required_room_type=RoomKind.COMPUTER_LAB,
        )
        other_assignment = TeachingAssignment.objects.create(
            term=self.term, subject=other_subject, faculty=self.faculty, section=self.section,
            component=TeachingAssignment.Component.LECTURE, duration_minutes=180,
        )
        schedule.entries.create(
            assignment=other_assignment, subject_override=self.subject, room=self.room,
            day=1, start_time=time(12), end_time=time(15),
        )
        self.client.login(username="admin", password="admin12345")

        response = self.client.get(f"/schedules/{schedule.pk}/", {"q": "IT101"})
        self.assertContains(response, 'class="schedule-block', count=2)
        self.assertNotContains(response, ">IT202<")

    def test_manual_entry_requires_matching_term_and_duration(self):
        other_term = AcademicTerm.objects.create(name="Second", school_year="2026-2027", starts_on=date(2027, 1, 1), ends_on=date(2027, 5, 1))
        schedule = Schedule.objects.create(term=other_term, name="Wrong term")
        entry = ScheduleEntry(schedule=schedule, assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(10))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn("different academic term", str(caught.exception))
        self.assertIn("must be 180 minutes", str(caught.exception))

    def test_manual_entry_cannot_end_after_seven_pm(self):
        schedule = Schedule.objects.create(term=self.term, name="After hours")
        entry = ScheduleEntry(
            schedule=schedule,
            assignment=self.assignment,
            room=self.room,
            day=0,
            start_time=time(17),
            end_time=time(20),
        )
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn("7:00 AM to 7:00 PM", str(caught.exception))

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

    def test_publishing_replacement_requires_confirmation_and_archives_current(self):
        self.client.login(username="admin", password="admin12345")
        current = Schedule.objects.create(term=self.term, name="Current", status=ScheduleStatus.PUBLISHED)
        current.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        candidate = Schedule.objects.create(term=self.term, name="Replacement")
        candidate.entries.create(assignment=self.assignment, room=self.room, day=1, start_time=time(8), end_time=time(11))

        response = self.client.post(f"/schedules/{candidate.id}/publish/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Archive Current")
        current.refresh_from_db()
        self.assertEqual(current.status, ScheduleStatus.PUBLISHED)

        response = self.client.post(f"/schedules/{candidate.id}/publish/", {"replace_confirm": "yes"})
        self.assertEqual(response.status_code, 302)
        current.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(current.status, ScheduleStatus.ARCHIVED)
        self.assertEqual(current.replaced_by, candidate)
        self.assertEqual(candidate.status, ScheduleStatus.PUBLISHED)

    def test_schedule_entry_override_is_version_only_and_audited(self):
        self.client.login(username="admin", password="admin12345")
        alternate = Faculty.objects.create(department=self.department, employee_id="F2", full_name="Grace")
        schedule = Schedule.objects.create(term=self.term, name="Editable")
        entry = schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        response = self.client.post(f"/schedules/{schedule.id}/entry/{entry.id}/edit/", {
            "assignment": self.assignment.id, "subject_override": self.subject.id,
            "section_override": self.section.id, "faculty_override": alternate.id,
            "component_override": TeachingAssignment.Component.LECTURE,
            "room": self.room.id, "day": 1, "start_time": "09:00", "end_time": "12:00",
        })
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(entry.effective_faculty, alternate)
        self.assertEqual(self.assignment.faculty, self.faculty)
        self.assertEqual(ScheduleEntryAudit.objects.filter(entry=entry, user=self.admin_user).count(), 1)

    def test_legacy_meeting_creation_gets_shared_assignment(self):
        self.assertIsNotNone(self.assignment.assignment)
        self.assertEqual(Assignment.objects.count(), 1)

    def test_assignment_management_list_renders_assignment_timestamps(self):
        self.client.login(username="admin", password="admin12345")
        response = self.client.get("/schedules/manage/assignments/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.subject.code)
        self.assertContains(response, "Date Added")

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
        self.assertContains(response, ">Error Log</a>", html=False)

    def test_faculty_dashboard_shows_weekly_personal_timetable(self):
        faculty_user = User.objects.create_user(username="facultyview", password="password123")
        Profile.objects.create(user=faculty_user, role=Role.FACULTY)
        self.faculty.user = faculty_user
        self.faculty.save(update_fields=["user"])
        schedule = Schedule.objects.create(term=self.term, name="Official", status=ScheduleStatus.PUBLISHED)
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        self.client.login(username="facultyview", password="password123")

        response = self.client.get("/dashboard/")
        self.assertContains(response, "Weekly Teaching Timetable")
        self.assertContains(response, 'class="room-schedule-grid personal-timetable"')
        self.assertContains(response, self.subject.code)
        self.assertContains(response, self.room.name)

    def test_student_dashboard_shows_section_timetable(self):
        student_user = User.objects.create_user(username="studentview", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        Student.objects.create(user=student_user, section=self.section, student_number="VIEW1", full_name="Student View")
        schedule = Schedule.objects.create(term=self.term, name="Official", status=ScheduleStatus.PUBLISHED)
        schedule.entries.create(assignment=self.assignment, room=self.room, day=2, start_time=time(9), end_time=time(12))
        self.client.login(username="studentview", password="password123")

        response = self.client.get("/dashboard/")
        self.assertContains(response, "Weekly Class Timetable")
        self.assertContains(response, 'class="room-schedule-grid personal-timetable"')
        self.assertContains(response, self.subject.code)
        self.assertContains(response, "Wednesday")

    def test_student_browse_only_shows_entries_for_own_section(self):
        student_user = User.objects.create_user(username="restrictedstudent", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        Student.objects.create(user=student_user, section=self.section, student_number="RS1", full_name="Restricted Student")
        other_section = Section.objects.create(program=self.program, year_level=self.year, name="B", size=25)
        other_subject = Subject.objects.create(code="PRIVATE201", title="Other Section Course", department=self.department,
                                               lecture_hours=3, required_room_type=RoomKind.COMPUTER_LAB)
        other_assignment = TeachingAssignment.objects.create(term=self.term, subject=other_subject,
                                                              faculty=self.faculty, section=other_section,
                                                              duration_minutes=180)
        schedule = Schedule.objects.create(term=self.term, name="Mixed Official", status=ScheduleStatus.PUBLISHED)
        schedule.entries.create(assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11))
        schedule.entries.create(assignment=other_assignment, room=self.room, day=1, start_time=time(8), end_time=time(11))
        self.client.login(username="restrictedstudent", password="password123")

        browse = self.client.get("/schedules/browse/")
        detail = self.client.get(f"/schedules/{schedule.id}/")
        csv_export = self.client.get(f"/schedules/{schedule.id}/export/csv/")
        self.assertContains(browse, f'<span class="subject-chip">{self.subject.code}</span>', html=True)
        self.assertNotContains(browse, f'<span class="subject-chip">{other_subject.code}</span>', html=True)
        self.assertContains(detail, self.subject.code)
        self.assertNotContains(detail, other_subject.code)
        self.assertContains(csv_export, self.subject.code)
        self.assertNotContains(csv_export, other_subject.code)

    def test_faculty_cannot_open_schedule_with_no_assigned_entries(self):
        faculty_user = User.objects.create_user(username="restrictedfaculty", password="password123")
        Profile.objects.create(user=faculty_user, role=Role.FACULTY)
        self.faculty.user = faculty_user
        self.faculty.save(update_fields=["user"])
        other_faculty = Faculty.objects.create(department=self.department, employee_id="F9", full_name="Other Teacher")
        other_term = AcademicTerm.objects.create(name="Second Semester", school_year="2026-2027",
                                                 starts_on=date(2027, 1, 1), ends_on=date(2027, 5, 1))
        other_assignment = TeachingAssignment.objects.create(term=other_term, subject=self.subject,
                                                              faculty=other_faculty, section=self.section)
        schedule = Schedule.objects.create(term=other_term, name="Other Faculty", status=ScheduleStatus.PUBLISHED)
        schedule.entries.create(assignment=other_assignment, room=self.room, day=0,
                                start_time=time(8), end_time=time(11))
        self.client.login(username="restrictedfaculty", password="password123")

        self.assertNotContains(self.client.get("/schedules/browse/"),
                               f'<span class="subject-chip">{self.subject.code}</span>', html=True)
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/export/csv/").status_code, 404)
        self.assertEqual(self.client.get(f"/schedules/{schedule.id}/export/pdf/").status_code, 404)

    def test_student_sidebar_hides_admin_groups(self):
        student_user = User.objects.create_user(username="navstudent", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        Student.objects.create(user=student_user, section=self.section, student_number="NAV1", full_name="Nav Student")
        self.client.login(username="navstudent", password="password123")
        response = self.client.get("/dashboard/")
        self.assertNotContains(response, 'data-nav-group="academic"')
        self.assertContains(response, "Browse Schedules")
        self.assertContains(response, "<small>Student</small>", html=True)
        self.assertNotContains(response, "<small>Administrator</small>", html=True)

    def test_faculty_user_menu_displays_faculty_role(self):
        faculty_user = User.objects.create_user(username="rolefaculty", password="password123")
        Profile.objects.create(user=faculty_user, role=Role.FACULTY)
        self.faculty.user = faculty_user
        self.faculty.save(update_fields=["user"])
        self.client.login(username="rolefaculty", password="password123")

        response = self.client.get("/dashboard/")
        self.assertContains(response, "<small>Faculty</small>", html=True)
        self.assertNotContains(response, "<small>Administrator</small>", html=True)

    def test_form_draft_is_created_updated_and_does_not_create_official_record(self):
        self.client.login(username="admin", password="admin12345")
        url = "/schedules/drafts/save/"
        response = self.client.post(url, json.dumps({
            "resource": "departments", "object_pk": "", "changed": True,
            "payload": {"code": "ENG", "name": "Engineering", "not_allowed": "ignored"},
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        draft = FormDraft.objects.get(user=self.admin_user, resource="departments", object_pk="")
        self.assertEqual(draft.payload, {"code": "ENG", "name": "Engineering"})
        self.assertFalse(Department.objects.filter(code="ENG").exists())
        self.client.post(url, json.dumps({
            "resource": "departments", "object_pk": "", "changed": True,
            "payload": {"code": "ENG", "name": "College of Engineering"},
        }), content_type="application/json")
        self.assertEqual(FormDraft.objects.filter(user=self.admin_user, resource="departments").count(), 1)
        draft.refresh_from_db()
        self.assertEqual(draft.payload["name"], "College of Engineering")

    def test_unchanged_form_does_not_create_a_draft(self):
        self.client.login(username="admin", password="admin12345")
        response = self.client.post("/schedules/drafts/save/", json.dumps({
            "resource": "departments", "object_pk": "", "changed": False,
            "payload": {"code": "", "name": ""},
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FormDraft.objects.exists())

    def test_draft_restores_and_final_create_removes_it(self):
        self.client.login(username="admin", password="admin12345")
        FormDraft.objects.create(user=self.admin_user, resource="departments", payload={"code": "SCI", "name": "Science"})
        response = self.client.get("/schedules/manage/departments/new/")
        self.assertContains(response, "Draft restored")
        self.assertContains(response, 'value="SCI"')
        response = self.client.post("/schedules/manage/departments/new/", {"code": "SCI", "name": "Science"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Department.objects.filter(code="SCI").exists())
        self.assertFalse(FormDraft.objects.filter(user=self.admin_user, resource="departments").exists())

    def test_user_can_only_discard_their_own_draft(self):
        other = User.objects.create_user(username="otheradmin", password="password123", is_staff=True)
        Profile.objects.create(user=other, role=Role.ADMIN)
        draft = FormDraft.objects.create(user=self.admin_user, resource="departments", payload={"code": "X"})
        self.client.login(username="otheradmin", password="password123")
        self.assertEqual(self.client.post(f"/schedules/drafts/{draft.pk}/discard/").status_code, 404)
        self.assertTrue(FormDraft.objects.filter(pk=draft.pk).exists())
        self.client.login(username="admin", password="admin12345")
        self.assertEqual(self.client.post(f"/schedules/drafts/{draft.pk}/discard/").status_code, 302)
        self.assertFalse(FormDraft.objects.filter(pk=draft.pk).exists())

    def test_edit_draft_detects_newer_official_record(self):
        self.client.login(username="admin", password="admin12345")
        self.client.post("/schedules/drafts/save/", json.dumps({
            "resource": "departments", "object_pk": str(self.department.pk), "changed": True,
            "payload": {"code": "CCS", "name": "Draft name"},
        }), content_type="application/json")
        self.department.name = "Changed by another request"
        self.department.save()
        url = f"/schedules/manage/departments/{self.department.pk}/edit/"
        self.assertContains(self.client.get(url), "changed after this draft began")
        self.assertEqual(self.client.post(url, {"code": "CCS", "name": "Draft name"}).status_code, 200)
        self.department.refresh_from_db()
        self.assertEqual(self.department.name, "Changed by another request")
        response = self.client.post(url, {
            "code": "CCS", "name": "Draft name", "draft_conflict_confirm": "yes",
        })
        self.assertEqual(response.status_code, 302)
        self.department.refresh_from_db()
        self.assertEqual(self.department.name, "Draft name")
        self.assertFalse(FormDraft.objects.filter(user=self.admin_user, object_pk=str(self.department.pk)).exists())

    def test_non_admin_cannot_save_drafts_and_invalid_json_is_safe(self):
        student_user = User.objects.create_user(username="draftstudent", password="password123")
        Profile.objects.create(user=student_user, role=Role.STUDENT)
        self.client.login(username="draftstudent", password="password123")
        self.assertEqual(self.client.post("/schedules/drafts/save/", "{}", content_type="application/json").status_code, 302)
        self.client.login(username="admin", password="admin12345")
        self.assertEqual(self.client.post("/schedules/drafts/save/", "not-json", content_type="application/json").status_code, 400)

    def test_section_uses_standard_display_name_and_normalizes_full_input(self):
        self.assertEqual(str(self.section), "BSIT 1-A")
        parsed = Section(program=self.program, year_level=self.year, name="bsit 1-201", size=30)
        parsed.save()
        self.assertEqual(parsed.name, "201")
        self.assertEqual(parsed.section_code, "201")
        self.assertEqual(parsed.display_name, "BSIT 1-201")

    def test_section_rejects_malformed_codes_and_duplicate_combination(self):
        with self.assertRaises(ValidationError):
            Section(program=self.program, year_level=self.year, name="1 201", size=30).save()
        self.client.login(username="admin", password="admin12345")
        response = self.client.post("/schedules/manage/sections/new/", {
            "program": self.program.pk, "year_level": self.year.pk, "name": "a", "size": 30,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This section already exists.")

    def test_section_form_has_live_preview_and_restores_individual_draft_values(self):
        self.client.login(username="admin", password="admin12345")
        FormDraft.objects.create(user=self.admin_user, resource="sections", payload={
            "program": str(self.program.pk), "year_level": str(self.year.pk), "name": "201", "size": "30",
        })
        response = self.client.get("/schedules/manage/sections/new/")
        self.assertContains(response, "Section Name Preview")
        self.assertContains(response, "Section Code")
        self.assertContains(response, 'data-section-preview')
        self.assertContains(response, 'value="201"')

    def test_complete_section_name_search_finds_schedule_entry(self):
        schedule = Schedule.objects.create(term=self.term, name="Searchable", status=ScheduleStatus.DRAFT)
        schedule.entries.create(
            assignment=self.assignment, room=self.room, day=0, start_time=time(8), end_time=time(11)
        )
        self.client.login(username="admin", password="admin12345")
        response = self.client.get(f"/schedules/{schedule.pk}/", {"q": "BSIT 1-A"})
        self.assertContains(response, "IT101")
        self.assertContains(response, "BSIT 1-A")
