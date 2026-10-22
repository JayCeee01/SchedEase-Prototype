import csv
import io
from datetime import time

from django.contrib.auth.models import User

from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.availability import AvailabilityPolicy
from .services.room_utilization import room_available_hours_by_day, room_schedule_grid, utilization_rows, utilization_summary


class RoomAvailabilityReportingTests(SchedulingDefectFixture):
    def add_periods(self, periods):
        for kind, day, start, end in periods:
            m.Availability.objects.create(room=self.room, kind=kind, day=day, start_time=start, end_time=end)

    def test_interval_totals_and_placement_consistency(self):
        cases = [
            ('defaults', [], [12] * 6),
            ('selected days', [('AVAILABLE', 0, time(8), time(12))], [4, 0, 0, 0, 0, 0]),
            ('merge available', [('AVAILABLE', 0, time(8), time(12)), ('AVAILABLE', 0, time(10), time(14)),
                                 ('AVAILABLE', 0, time(14), time(15))], [7, 0, 0, 0, 0, 0]),
            ('merge blocked', [('UNAVAILABLE', 0, time(8), time(11)), ('UNAVAILABLE', 0, time(10), time(12))], [8, 12, 12, 12, 12, 12]),
            ('subtract intersection', [('AVAILABLE', 0, time(8), time(12)), ('UNAVAILABLE', 0, time(6), time(9)),
                                      ('UNAVAILABLE', 0, time(11), time(20))], [2, 0, 0, 0, 0, 0]),
            ('clip operating hours', [('AVAILABLE', 0, time(6), time(20)), ('UNAVAILABLE', 0, time(5), time(8)),
                                      ('UNAVAILABLE', 0, time(18), time(22))], [10, 0, 0, 0, 0, 0]),
            ('fully blocked', [('AVAILABLE', 0, time(8), time(12)), ('UNAVAILABLE', 0, time(7), time(19)),
                               ('UNAVAILABLE', 0, time(8), time(18))], [0] * 6),
            ('outside window', [('AVAILABLE', 0, time(5), time(6))], [0] * 6),
        ]
        for name, periods, expected in cases:
            with self.subTest(name=name):
                self.room.availability_set.all().delete()
                self.add_periods(periods)
                self.assertEqual(room_available_hours_by_day(self.room), expected)
                policy = AvailabilityPolicy.for_resource(self.room)
                # Independent half-hour placement checks cover the entire school week.
                grid = room_schedule_grid(self.room, None)
                for day in range(6):
                    permitted_hours = sum(not policy.rejection_reason(day, row['start'], row['end']) for row in grid) / 2
                    self.assertEqual(permitted_hours, expected[day])
                    self.assertEqual(sum(row['cells'][day]['available'] for row in grid) / 2, expected[day])

    def test_correct_denominator_reaches_rows_summary_and_csv(self):
        self.add_periods([('AVAILABLE', 0, time(8), time(12)), ('AVAILABLE', 0, time(10), time(14)),
                          ('UNAVAILABLE', 0, time(10), time(11))])
        schedule = m.Schedule.objects.create(term=self.term, name='Reporting')
        for meeting, start in zip(self.meetings, (8, 11)):
            entry = m.ScheduleEntry(schedule=schedule, assignment=meeting, room=self.room,
                                    day=0, start_time=time(start), end_time=time(start + 1))
            entry.full_clean()
            entry.save()
        rows = utilization_rows(schedule)
        row = rows[0]
        self.assertEqual((row.available_hours, row.scheduled_hours, row.utilization_percentage), (5, 2, 40))
        self.assertEqual(row.daily[0]['percentage'], 40)
        self.assertEqual(row.daily[1]['percentage'], 0)
        self.assertEqual(utilization_summary(rows)['average_utilization'], 40)
        admin = User.objects.create_superuser(username='reporting-admin', password='test-password')
        self.client.force_login(admin)
        response = self.client.get('/schedules/room-utilization/export/csv/', {'schedule': schedule.pk})
        self.assertEqual(response.status_code, 200)
        exported = list(csv.DictReader(io.StringIO(response.content.decode())))[0]
        self.assertEqual(float(exported['Available Hours']), 5)
        self.assertEqual(float(exported['Scheduled Hours']), 2)
        self.assertEqual(float(exported['Weekly Utilization %']), 40)

    def test_inactive_and_zero_availability_are_safe_without_hiding_saved_hours(self):
        schedule = m.Schedule.objects.create(term=self.term, name='Historical entry')
        schedule.entries.create(assignment=self.meetings[0], room=self.room, day=0, start_time=time(8), end_time=time(9))
        for inactive in (False, True):
            with self.subTest(inactive=inactive):
                self.room.availability_set.all().delete()
                self.room.is_active = not inactive
                self.room.save(update_fields=['is_active'])
                if not inactive:
                    self.add_periods([('AVAILABLE', 0, time(8), time(9)), ('UNAVAILABLE', 0, time(7), time(19))])
                self.assertEqual(room_available_hours_by_day(self.room), [0] * 6)
                row = utilization_rows(schedule)[0]
                self.assertEqual((row.available_hours, row.scheduled_hours, row.utilization_percentage), (0, 1, 0))
                self.assertEqual(utilization_summary([row])['average_utilization'], 0)
                self.assertTrue(all(not cell['available'] for slot in room_schedule_grid(self.room, schedule) for cell in slot['cells']))

    def test_percentages_use_unrounded_minutes(self):
        self.add_periods([('AVAILABLE', 0, time(8), time(8, 20))])
        schedule = m.Schedule.objects.create(term=self.term, name='Minute precision')
        schedule.entries.create(assignment=self.meetings[0], room=self.room, day=0,
                                start_time=time(8), end_time=time(8, 10))
        row = utilization_rows(schedule)[0]
        self.assertEqual(row.available_hours, 0.33)
        self.assertEqual(row.scheduled_hours, 0.17)
        self.assertEqual(row.daily[0]['percentage'], 50)
        self.assertEqual(row.utilization_percentage, 50)
        self.assertEqual(utilization_summary([row])['average_utilization'], 50)
