from datetime import time

from django.core.exceptions import ValidationError

from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.ga import Gene
from .services.room_utilization import room_available_hours_by_day


class AvailabilitySchedulingTests(SchedulingDefectFixture):
    def check_cases(self, periods, cases):
        # Exercise exactly the same inputs for both resource types and validators.
        for owner in ('faculty', 'room'):
            with self.subTest(owner=owner):
                m.Availability.objects.all().delete()
                resource = getattr(self, owner)
                for kind, day, start, end in periods:
                    m.Availability.objects.create(**{owner: resource}, kind=kind, day=day,
                                                  start_time=start, end_time=end)
                scheduler = self.scheduler()
                schedule, _ = m.Schedule.objects.get_or_create(term=self.term, name='Availability checks')
                for day, start, end, permitted in cases:
                    with self.subTest(day=day, start=start, end=end):
                        gene = Gene(self.meetings[0].pk, self.room.pk, day, start, end)
                        blocked = scheduler._blocked(self.faculty.pk, gene) if owner == 'faculty' else scheduler._room_blocked(self.room.pk, gene)
                        self.assertEqual(blocked, not permitted)
                        meeting = m.TeachingAssignment.objects.get(pk=self.meetings[0].pk)
                        meeting.duration_minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
                        entry = m.ScheduleEntry(schedule=schedule, assignment=meeting, room=self.room,
                                                day=day, start_time=start, end_time=end)
                        if permitted:
                            entry.full_clean()
                        else:
                            with self.assertRaises(ValidationError) as raised:
                                entry.full_clean()
                            self.assertTrue(any(owner.capitalize() in message and 'availab' in message
                                                for message in raised.exception.messages), raised.exception.messages)

    def test_explicit_available_periods_close_unlisted_days(self):
        self.check_cases([('AVAILABLE', 0, time(8), time(12))], [
            (0, time(8), time(12), True), (1, time(8), time(9), False),
            (0, time(7), time(9), False), (0, time(11), time(13), False),
        ])

    def test_defaults_and_operating_boundaries(self):
        self.check_cases([], [
            (0, time(7), time(8), True), (5, time(18), time(19), True),
            (6, time(9), time(10), False), (0, time(6), time(8), False),
            (0, time(18), time(20), False), (0, time(9), time(9), False),
            (0, time(10), time(9), False),
        ])

    def test_unavailable_overrides_available_with_touching_boundaries(self):
        self.check_cases([('AVAILABLE', 0, time(8), time(12)), ('UNAVAILABLE', 0, time(9), time(10))], [
            (0, time(8), time(9), True), (0, time(10), time(12), True),
            (0, time(9), time(10), False), (0, time(8), time(11), False),
        ])

    def test_unavailable_only_and_preferences_do_not_close_other_days(self):
        self.check_cases([('UNAVAILABLE', 0, time(9), time(10)), ('PREFERRED', 0, time(11), time(12))], [
            (0, time(9), time(10), False), (1, time(9), time(10), True),
            (0, time(7), time(8), True),
        ])

    def test_overlap_and_adjacency_merge_but_real_gaps_remain_closed(self):
        self.check_cases([('AVAILABLE', 0, time(8), time(10)), ('AVAILABLE', 0, time(9), time(11)),
                          ('AVAILABLE', 0, time(11), time(12)), ('AVAILABLE', 0, time(13), time(14))], [
            (0, time(8), time(12), True), (0, time(11), time(13, 30), False),
        ])

    def test_intervals_are_clipped_to_operating_hours(self):
        self.check_cases([('AVAILABLE', 0, time(6), time(20))], [
            (0, time(7), time(19), True), (0, time(6), time(8), False), (0, time(18), time(20), False),
        ])

    def test_inactive_room_is_rejected_by_ga_and_manual_validation(self):
        self.room.is_active = False
        self.room.save(update_fields=['is_active'])
        scheduler = self.scheduler()
        self.assertNotIn(self.room.pk, scheduler.room_map)
        self.assertTrue(scheduler._room_blocked(self.room.pk, Gene(self.meetings[0].pk, self.room.pk, 0, time(8), time(9))))
        schedule = m.Schedule.objects.create(term=self.term, name='Inactive room')
        entry = m.ScheduleEntry(schedule=schedule, assignment=self.meetings[0], room=self.room,
                                day=0, start_time=time(8), end_time=time(9))
        with self.assertRaisesMessage(ValidationError, 'Room is inactive'):
            entry.full_clean()

    def test_ga_fitness_evaluates_explicit_faculty_availability(self):
        m.Availability.objects.create(faculty=self.faculty, day=0, start_time=time(8), end_time=time(12), kind='AVAILABLE')
        scheduler = self.scheduler()
        monday = Gene(self.meetings[0].pk, self.room.pk, 0, time(8), time(9))
        tuesday = Gene(self.meetings[0].pk, self.room.pk, 1, time(8), time(9))
        self.assertGreater(scheduler.fitness([monday]), scheduler.fitness([tuesday]))


class H3ReportingDeferredTests(SchedulingDefectFixture):
    def setUp(self):
        # Task 2.3 counts the union (08-14) minus the blocked hour (10-11).
        for kind, start, end in [('AVAILABLE', time(8), time(12)), ('AVAILABLE', time(10), time(14)),
                                  ('UNAVAILABLE', time(10), time(11))]:
            m.Availability.objects.create(room=self.room, day=0, start_time=start, end_time=end, kind=kind)
        self.hours = room_available_hours_by_day(self.room)
        scheduler = self.scheduler()
        self.assertTrue(scheduler._room_blocked(self.room.pk, Gene(self.meetings[0].pk, self.room.pk, 0, time(10), time(11))))
        self.assertFalse(scheduler._room_blocked(self.room.pk, Gene(self.meetings[0].pk, self.room.pk, 0, time(11), time(13))))

    def test_H3_reporting_counts_merged_availability_minus_unavailable(self):
        """H3 reporting fixed in Task 2.3: count merged periods minus blocked time."""
        self.assertEqual(self.hours, [5, 0, 0, 0, 0, 0])
