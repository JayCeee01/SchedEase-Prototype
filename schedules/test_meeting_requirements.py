"""H5: shared component policy and final schedule safeguards."""
from datetime import time
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from . import models as m
from .forms import AssignmentMeetingFormSetFactory
from .test_known_defects import SchedulingDefectFixture
from .services.meetings import meeting_requirement_errors
from .services.conflicts import schedule_validation_messages
from .services.ga import Gene


class MeetingRequirementsTests(SchedulingDefectFixture):
    def test_component_totals_and_classifications(self):
        cases = [
            (2, 0, [(1, "LECTURE", 120)], True),
            (0, 2, [(1, "LABORATORY", 120)], True),
            (2, 1, [(1, "LECTURE", 60), (2, "LECTURE", 60), (3, "LABORATORY", 60)], True),
            (2, 1, [(1, "LECTURE", 120)], False),
            (2, 1, [(1, "LABORATORY", 60)], False),
            (2, 0, [(1, "LECTURE", 120), (2, "LABORATORY", 60)], False),
            (2, 0, [(1, "LECTURE", 60)], False),
            (2, 0, [(1, "LECTURE", 180)], False),
            (2, 0, [(1, "GENERAL", 120)], False),
            (2, 0, [(1, "LECTURE", 60), (1, "LECTURE", 60)], False),
            (2, 0, [], False),
        ]
        for lecture, lab, records, valid in cases:
            with self.subTest(lecture=lecture, lab=lab, records=records):
                self.subject.lecture_hours, self.subject.lab_hours = lecture, lab
                self.assertEqual(not meeting_requirement_errors(self.subject, records), valid)

    def entries(self):
        schedule = m.Schedule.objects.create(term=self.term, name="H5")
        for index, meeting in enumerate(self.meetings):
            schedule.entries.create(assignment=meeting, room=self.room, day=0,
                                    start_time=time(8 + index), end_time=time(9 + index))
        return schedule

    def test_zero_duration_uses_only_its_component_hours(self):
        self.subject.lab_hours = 1
        self.subject.save()
        meeting = self.meetings[0]
        meeting.subject = self.subject
        meeting.duration_minutes = 0
        self.assertEqual(meeting.required_duration_minutes, 120)
        meeting.component = "LABORATORY"
        self.assertEqual(meeting.required_duration_minutes, 60)

    def test_formset_rejects_extra_lab_on_lecture_only_course(self):
        data = {"meetings-TOTAL_FORMS": "3", "meetings-INITIAL_FORMS": "2"}
        for i, meeting in enumerate(self.meetings):
            for field in ("id", "meeting_index", "component", "duration_minutes"):
                data[f"meetings-{i}-{field}"] = getattr(meeting, field)
        data.update({"meetings-2-meeting_index": 3, "meetings-2-component": "LABORATORY", "meetings-2-duration_minutes": 60})
        forms = AssignmentMeetingFormSetFactory(data, instance=self.parent, prefix="meetings")
        self.assertFalse(forms.is_valid())
        self.assertIn("LABORATORY totals 60", str(forms.non_form_errors()))

    def test_manual_overrides_cannot_relabel_course_or_component(self):
        entry = self.entries().entries.first()
        entry.full_clean()
        entry.component_override = "LABORATORY"
        with self.assertRaisesMessage(ValidationError, "Session type must match"):
            entry.full_clean()
        entry.component_override = ""
        entry.subject_override = m.Subject.objects.create(department=self.department, code="OTHER", title="Other", lecture_hours=2)
        with self.assertRaisesMessage(ValidationError, "Course must match"):
            entry.full_clean()

    def test_actual_durations_are_checked_even_when_all_meeting_ids_exist(self):
        schedule = self.entries()
        self.assertEqual(schedule_validation_messages(schedule), [])
        schedule.entries.filter(assignment=self.meetings[1]).update(end_time=time(9, 30))
        self.assertTrue(any("LECTURE totals 90" in error for error in schedule_validation_messages(schedule)))

    def test_publication_blocks_missing_course_component_even_with_all_ids(self):
        schedule = self.entries()
        self.subject.lab_hours = 1
        self.subject.save()
        admin = User.objects.create_superuser(username="h5", password="test")
        self.client.force_login(admin)
        self.client.post(f"/schedules/{schedule.pk}/publish/")
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, m.ScheduleStatus.DRAFT)
        self.assertTrue(any("LABORATORY totals 0" in e for e in schedule_validation_messages(schedule)))

    def test_valid_split_meetings_can_be_published(self):
        schedule = self.entries()
        admin = User.objects.create_superuser(username="h5", password="test")
        self.client.force_login(admin)
        self.assertEqual(self.client.post(f"/schedules/{schedule.pk}/publish/").status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, m.ScheduleStatus.PUBLISHED)

    def test_ga_rejects_incomplete_output_atomically(self):
        scheduler = self.scheduler()
        scheduler.settings.population_size = 2
        scheduler.settings.generations = 0
        genes = [Gene(self.meetings[0].pk, self.room.pk, 0, time(8), time(9))]
        with patch.object(scheduler, "_random_chromosome", return_value=genes):
            with self.assertRaisesMessage(ValueError, "Unscheduled class"):
                scheduler.generate()
        self.assertFalse(m.Schedule.objects.exists())

    def test_ga_rejects_missing_lab_requirement_atomically(self):
        self.subject.lab_hours = 1
        self.subject.save()
        scheduler = self.scheduler()
        scheduler.settings.population_size = 2
        scheduler.settings.generations = 0
        genes = [Gene(meeting.pk, self.room.pk, 0, time(8+i), time(9+i)) for i, meeting in enumerate(self.meetings)]
        with patch.object(scheduler, "_random_chromosome", return_value=genes):
            with self.assertRaisesMessage(ValueError, "LABORATORY totals 0"):
                scheduler.generate()
        self.assertFalse(m.Schedule.objects.exists())

    def test_ga_rejects_duplicate_output(self):
        scheduler = self.scheduler()
        scheduler.settings.population_size = 2
        scheduler.settings.generations = 0
        gene = Gene(self.meetings[0].pk, self.room.pk, 0, time(8), time(9))
        with patch.object(scheduler, "_random_chromosome", return_value=[gene, gene]):
            with self.assertRaisesMessage(ValueError, "duplicate meetings"):
                scheduler.generate()
        self.assertFalse(m.Schedule.objects.exists())
