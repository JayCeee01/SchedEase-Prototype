"""H7: effective durations, operating boundaries, and active rooms."""
from datetime import time
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.meetings import duration_errors
from .services.conflicts import schedule_validation_messages
from .forms import AssignmentMeetingForm


class DurationBoundaryTests(SchedulingDefectFixture):
    def entry(self, start=time(18), end=time(19)):
        schedule = m.Schedule.objects.create(term=self.term, name="Boundary")
        return m.ScheduleEntry(schedule=schedule, assignment=self.meetings[0], room=self.room,
                               day=0, start_time=start, end_time=end)

    def test_effective_duration_policy(self):
        for minutes in (0, -1, 0.5, 1.5, 721, 840):
            with self.subTest(minutes=minutes):
                self.assertTrue(duration_errors(minutes))
        for minutes in (1, 29, 30, 61, 720):
            with self.subTest(minutes=minutes):
                self.assertEqual(duration_errors(minutes), [])

    def test_assignment_form_rejects_overlong_duration(self):
        form = AssignmentMeetingForm(data={'meeting_index': 1, 'component': 'LECTURE',
                                          'duration_minutes': 721}, instance=self.meetings[0])
        self.assertFalse(form.is_valid())
        self.assertIn('school day', str(form.errors['duration_minutes']))

    def test_zero_fallback_must_resolve_to_valid_duration(self):
        meeting = self.meetings[0]
        meeting.duration_minutes = 0
        self.assertEqual(meeting.required_duration_minutes, 120)
        meeting.full_clean()
        meeting.subject.lecture_hours = 0
        with self.assertRaisesMessage(ValidationError, 'positive whole number'):
            meeting.full_clean()

    def test_opening_closing_and_outside_boundaries(self):
        for start, end, valid in [(time(7), time(8), True), (time(18), time(19), True),
                                  (time(6, 59), time(7, 59), False), (time(18, 1), time(19, 1), False),
                                  (time(18), time(18, 59, 59), False), (time(18), time(18), False)]:
            with self.subTest(start=start, end=end):
                entry = self.entry(start, end)
                if valid:
                    entry.full_clean()
                else:
                    with self.assertRaises(ValidationError):
                        entry.full_clean()

    def test_maximum_day_duration_is_valid(self):
        self.meetings[0].duration_minutes = 720
        entry = self.entry(time(7), time(19))
        entry.full_clean()

    def test_ga_does_not_extend_short_meetings(self):
        self.meetings[0].duration_minutes = 1
        gene = self.scheduler()._random_gene(self.meetings[0])
        self.assertEqual(gene.end_time.hour * 60 + gene.end_time.minute - gene.start_time.hour * 60 - gene.start_time.minute, 1)

    def test_ga_rejects_overlong_input_before_search(self):
        m.TeachingAssignment.objects.filter(pk=self.meetings[0].pk).update(duration_minutes=721)
        scheduler = self.scheduler()
        self.assertTrue(any('school day' in issue for issue in scheduler.preflight_issues()))
        with patch.object(scheduler, '_random_chromosome') as search:
            with self.assertRaisesMessage(ValueError, 'school day'):
                scheduler.generate()
            search.assert_not_called()
        self.assertFalse(m.Schedule.objects.exists())
        self.meetings[0].refresh_from_db()
        with self.assertRaisesMessage(ValidationError, 'school day'):
            self.entry().full_clean()

    def test_inactive_room_rejected_by_manual_ga_and_publication(self):
        self.room.is_active = False
        self.room.save()
        entry = self.entry()
        with self.assertRaisesMessage(ValidationError, 'inactive'):
            entry.full_clean()
        self.assertFalse(self.scheduler().rooms)
        entry.save()  # Historical invalid data must still be blocked at publication.
        entry.schedule.entries.create(assignment=self.meetings[1], room=self.room, day=1, start_time=time(18), end_time=time(19))
        self.assertTrue(any('inactive' in error for error in schedule_validation_messages(entry.schedule)))
        admin = User.objects.create_superuser(username='h7', password='test')
        self.client.force_login(admin)
        self.client.post(f'/schedules/{entry.schedule_id}/publish/')
        entry.schedule.refresh_from_db()
        self.assertEqual(entry.schedule.status, m.ScheduleStatus.DRAFT)

    def test_invalid_manual_edit_does_not_save_or_create_audit(self):
        entry = self.entry()
        entry.save()
        admin = User.objects.create_superuser(username='h7', password='test')
        self.client.force_login(admin)
        response = self.client.post(f'/schedules/{entry.schedule_id}/entry/{entry.pk}/edit/', {
            'revision': self.client.get(f'/schedules/{entry.schedule_id}/entry/{entry.pk}/edit/').context['form'].initial['revision'],
            'assignment': entry.assignment_id, 'room': self.room.pk, 'day': 0,
            'start_time': '18:01', 'end_time': '19:01'})
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.start_time, time(18))
        self.assertEqual(entry.end_time, time(19))
        self.assertFalse(m.ScheduleEntryAudit.objects.filter(entry=entry).exists())

    def test_publication_rejects_invalid_actual_duration_with_all_meetings_present(self):
        entry = self.entry(time(18), time(18, 59))
        entry.save()
        entry.schedule.entries.create(assignment=self.meetings[1], room=self.room, day=1,
                                      start_time=time(18), end_time=time(19))
        admin = User.objects.create_superuser(username='h7', password='test')
        self.client.force_login(admin)
        self.assertTrue(any('Class duration must be 60' in error for error in schedule_validation_messages(entry.schedule)))
        self.client.post(f'/schedules/{entry.schedule_id}/publish/')
        entry.schedule.refresh_from_db()
        self.assertEqual(entry.schedule.status, m.ScheduleStatus.DRAFT)
