"""Phase 2 contracts: H1, H3 scheduling, and H4 expiry are fixed.

The H3 reporting regression in test_availability.py also passes after Task 2.3.

All original expectedFailure markers have been removed after their Phase 2 fixes. Operations
and positive controls live in setUp (outside expectedFailure), so unexpected
exceptions and broken prerequisites remain ordinary errors/failures. The final comparison checks all intended outcomes together.
"""

from datetime import date, time

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from . import models as m
from .services.credentials import faculty_qualification
from .services.ga import Gene, GeneticScheduler
from .services.room_utilization import room_available_hours_by_day


class SchedulingDefectFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = m.Department.objects.create(code="REG", name="Regression")
        program = m.Program.objects.create(department=cls.department, code="REG", name="Regression")
        year = m.YearLevel.objects.create(level=1, label="Year 1")
        cls.section = m.Section.objects.create(program=program, year_level=year, name="A", size=20)
        cls.faculty = m.Faculty.objects.create(department=cls.department, employee_id="REG1", full_name="Original Teacher")
        cls.subject = m.Subject.objects.create(department=cls.department, code="REG101", title="Regression Course",
                                              lecture_hours=2, lab_hours=0, required_room_type=m.RoomKind.LECTURE)
        cls.term = m.AcademicTerm.objects.create(name="First Term", school_year="2026-2027",
                                                starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 1))
        cls.parent = m.Assignment.objects.create(term=cls.term, subject=cls.subject, section=cls.section, faculty=cls.faculty)
        cls.meetings = [m.TeachingAssignment.objects.create(
            assignment=cls.parent, component=m.TeachingAssignment.Component.LECTURE,
            meeting_index=index, duration_minutes=60,
        ) for index in (1, 2)]
        cls.room = m.Room.objects.create(name="Regression Room", room_type=m.RoomKind.LECTURE, capacity=30)

    def scheduler(self):
        return GeneticScheduler(self.term, m.GASettings(), seed=13)


class H1AssignmentSynchronizationTests(SchedulingDefectFixture):
    def setUp(self):
        admin = User.objects.create_superuser(username="regression_admin", password="test-password")
        self.client.force_login(admin)
        replacement = m.Faculty.objects.create(department=self.department, employee_id="REG2", full_name="Replacement Teacher")
        payload = {
            "term": self.term.pk, "subject": self.subject.pk, "section": self.section.pk,
            "faculty": replacement.pk, "meetings-TOTAL_FORMS": "2", "meetings-INITIAL_FORMS": "2",
            "meetings-MIN_NUM_FORMS": "1", "meetings-MAX_NUM_FORMS": "1000",
        }
        for index, meeting in enumerate(self.meetings):
            for field in ("id", "component", "meeting_index", "duration_minutes", "required_room_type_override"):
                payload[f"meetings-{index}-{field}"] = getattr(meeting, field)
        response = self.client.post(reverse("resource_update", args=["assignments", self.parent.pk]), payload)
        self.assertRedirects(response, reverse("resource_list", args=["assignments"]), fetch_redirect_response=False)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.faculty_id, replacement.pk)
        saved = list(self.parent.meetings.order_by("meeting_index"))
        self.assertEqual([meeting.pk for meeting in saved], [meeting.pk for meeting in self.meetings])
        self.assertEqual([meeting.duration_minutes for meeting in saved], [60, 60])
        scheduler = self.scheduler()
        self.assertEqual(set(scheduler.assignment_map), {meeting.pk for meeting in saved})
        self.observed = {
            "saved meeting faculty": [meeting.faculty_id for meeting in saved],
            "GA meeting faculty": [scheduler.assignment_map[meeting.pk].faculty_id for meeting in saved],
        }
        self.expected = {key: [replacement.pk, replacement.pk] for key in self.observed}

    def test_H1_parent_faculty_edit_updates_all_meetings_and_ga(self):
        """H1 fixed in Task 2.1: unchanged meeting forms inherit the new faculty."""
        self.assertEqual(self.observed, self.expected, "H1: saved meetings and GA inputs must match their parent's faculty")


class H3RoomAvailabilityTests(SchedulingDefectFixture):
    def setUp(self):
        # Explicit Monday hours make Tuesday closed, matching utilization policy.
        m.Availability.objects.create(room=self.room, day=0, start_time=time(8), end_time=time(12),
                                      kind=m.AvailabilityKind.AVAILABLE)
        scheduler = self.scheduler()
        hours = room_available_hours_by_day(self.room)
        self.assertEqual(hours[0], 4)
        self.assertEqual(hours[1], 0)
        monday = Gene(self.meetings[0].pk, self.room.pk, 0, time(9), time(10))
        tuesday = Gene(self.meetings[0].pk, self.room.pk, 1, time(9), time(10))
        self.assertFalse(scheduler._room_blocked(self.room.pk, monday))
        schedule = m.Schedule.objects.create(term=self.term, name="Availability Regression")
        entry = m.ScheduleEntry(schedule=schedule, assignment=self.meetings[0], room=self.room,
                                day=0, start_time=time(9), end_time=time(10))
        entry.full_clean()  # The same valid meeting must be accepted on Monday.
        entry.day = 1
        manual_rejected = False
        try:
            entry.full_clean()
        except ValidationError as exc:
            # Do not count an unrelated validation failure as the intended fix.
            self.assertTrue(exc.messages)
            self.assertTrue(all("room" in message.lower() and "availab" in message.lower()
                                for message in exc.messages), exc.messages)
            manual_rejected = True
        self.observed = {
            "utilization marks Tuesday closed": hours[1] == 0,
            "GA rejects Tuesday": scheduler._room_blocked(self.room.pk, tuesday),
            "manual validation rejects Tuesday": manual_rejected,
        }

    def test_H3_unlisted_day_is_closed_for_ga_manual_validation_and_reports(self):
        """H3 scheduling fixed in Task 2.2; retain the original closed-day report check."""
        self.assertEqual(self.observed, dict.fromkeys(self.observed, True),
                         "H3: Tuesday has no available interval and must not be schedulable")


class H4ExpiredCredentialTests(SchedulingDefectFixture):
    def setUp(self):
        credential = m.Credential.objects.create(name="Required Teaching License")
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        held = m.FacultyCredential.objects.create(faculty=self.faculty, credential=credential,
                                                  issued_on=date(2024, 1, 1))
        # A matching credential without an expiry is a valid positive control.
        self.assertTrue(faculty_qualification(self.faculty, self.subject, self.term)["qualified"])
        self.assertTrue(all(self.scheduler().qualification_cache.values()))
        held.expires_on = date(2025, 12, 31)
        held.save(update_fields=["expires_on"])
        self.assertLess(held.expires_on, self.term.starts_on)
        self.assertFalse(m.CredentialOverride.objects.exists())
        qualification = faculty_qualification(self.faculty, self.subject, self.term)
        scheduler = self.scheduler()
        self.assertEqual(set(scheduler.assignment_map), {meeting.pk for meeting in self.meetings})
        self.observed = {
            "credential service rejects expiry": not qualification["qualified"],
            "GA rejects expiry for every meeting": all(not value for value in scheduler.qualification_cache.values()),
            "GA preflight reports missing qualification": any("credential" in issue.lower()
                                                              for issue in scheduler.preflight_issues()),
        }

    def test_H4_expired_credential_does_not_qualify_faculty_or_ga(self):
        """Phase 2 H4: a credential expired before the term cannot qualify."""
        self.assertEqual(self.observed, dict.fromkeys(self.observed, True),
                         "H4: expired credentials must be rejected by qualification and GA preflight")
