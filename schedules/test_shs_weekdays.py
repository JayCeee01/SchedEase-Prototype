from .test_publication_helpers import finalize, legacy_case, upgrade
from datetime import date, time
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase, RequestFactory

from . import models as m
from . import test_shs_generation as generation
from . import test_shs_operations as operational
from . import test_contact_workload as workload
from . import test_detail_timetable as detail
from .services.detail_timetable import timetable_context
from .services.shs_days import WEEKDAY_ERROR, snapshot_day_errors
from .services.shs_scheduling import generate_shs, entry_errors


class SHSWeekdayTests(TestCase):
    setUp = generation.ControlledSHSGenerationTests.setUp

    def test_pattern_weekday_validation(self):
        pattern = self.config.patterns.get()
        for day in range(7):
            pattern.weekday = day
            if day < 5:
                pattern.full_clean()
            else:
                with self.assertRaisesMessage(ValidationError, WEEKDAY_ERROR):
                    pattern.full_clean()
        for value in (date(2026, 8, 8), date(2026, 8, 9)):
            pattern.recurrence = 'DATED'
            pattern.meeting_date = value
            pattern.weekday = value.weekday()
            with self.assertRaisesMessage(ValidationError, WEEKDAY_ERROR):
                pattern.full_clean()

    def test_generation_rechecks_bypassed_saturday_input(self):
        workload.ContactPolicyTests.policy(self)
        # Simulate legacy input in the disposable DB; the existing SQL rule permits Saturday.
        m.SHSMeetingPattern.objects.filter(configuration=self.config).update(weekday=5)
        with self.assertRaisesMessage(ValidationError, WEEKDAY_ERROR):
            generate_shs(self.term, self.settings, actor=self.actor)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.TeachingAssignment.objects.exists())

    def test_generation_ignores_weekend_resource_availability(self):
        workload.ContactPolicyTests.policy(self)
        schedule = generate_shs(self.term, self.settings, actor=self.actor, seed=17)
        self.assertEqual(set(schedule.entries.values_list('day', flat=True)), {0})
        entry = schedule.entries.get()
        entry.day = 5
        self.assertIn(WEEKDAY_ERROR, entry_errors(entry))
        with self.assertRaises(ValidationError):
            entry.full_clean()
        # Weekend-only resources cannot force SHS onto Saturday.
        m.Availability.objects.create(faculty=self.faculty, day=5, start_time=time(8), end_time=time(10), kind='AVAILABLE')
        from .services.placements import feasible_placements
        options, errors = feasible_placements(entry.assignment, self.term, [self.room])
        self.assertEqual(options, ())
        self.assertTrue(errors)

    @legacy_case
    def test_frozen_saturday_visible_to_student_and_faculty_with_warning(self):
        from .services.shs_scheduling import pattern_snapshot
        from .services.detail_timetable import timetable_context
        from django.contrib.auth.models import User
        from django.urls import reverse
        # Represent a pre-policy record using only this isolated test database.
        pattern = self.config.patterns.get()
        m.SHSMeetingPattern.objects.filter(pk=pattern.pk).update(weekday=5)
        pattern.refresh_from_db()
        meeting = m.TeachingAssignment.objects.create(assignment=self.assignment, component='GENERAL',
            duration_minutes=60, required_room_type_override='LECTURE')
        m.SHSMeetingBinding.objects.create(meeting=meeting, pattern=pattern, data=pattern_snapshot(pattern))
        schedule = m.Schedule.objects.create(term=self.term, name='Legacy weekend')
        entry = schedule.entries.create(assignment=meeting, room=self.room, day=5, start_time=time(8), end_time=time(9))
        schedule.status = 'PUBLISHED'
        schedule.save()
        upgrade()
        before = m.ScheduleSnapshot.objects.get(schedule=schedule).data
        user = User.objects.create_user('weekend-student')
        m.Profile.objects.create(user=user, role='STUDENT')
        m.Student.objects.create(user=user, section=self.section, student_number='123456', full_name='Synthetic Student')
        faculty_user = User.objects.create_user('weekend-faculty')
        m.Profile.objects.create(user=faculty_user, role='FACULTY')
        self.faculty.user = faculty_user
        self.faculty.save()
        for actor in (user, faculty_user):
            self.client.force_login(actor)
            for url in (reverse('dashboard'), reverse('schedule_detail', args=[schedule.pk])):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Weekend SHS meeting &mdash; review required')
                self.assertContains(response, '2026-08-08')
                self.assertNotContains(response, '<th>Saturday</th>')
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data, before)
        entry.refresh_from_db()
        self.assertEqual(entry.day, 5)

    def test_admin_and_manual_day_choices(self):
        request = RequestFactory().get('/')
        request.user = self.actor
        form = admin.site._registry[m.SHSMeetingPattern].get_form(request)()
        self.assertEqual({v for v, _ in form.fields['weekday'].choices if v != ''}, set(range(5)))
        from .forms import ScheduleEntryForm
        schedule = m.Schedule.objects.create(term=self.term, name='Test')
        form = ScheduleEntryForm(instance=m.ScheduleEntry(schedule=schedule))
        self.assertEqual({v for v, _ in form.fields['day'].choices if v != ''}, set(range(5)))


class SHSWeekdayPresentationTests(SimpleTestCase):
    def row(self, pk, weekday, value, level='SHS'):
        row = detail.record(pk, 'DATED', [value], weekday)
        row['academic_context'] = {'education_level': level}
        return row

    def project(self, rows, week=None):
        with patch('schedules.services.detail_timetable.present_entries', return_value=rows):
            return timetable_context([], week)

    def test_weekday_columns_friday_to_monday(self):
        rows = [self.row(1, 4, '2026-08-07'), self.row(2, 0, '2026-08-10')]
        result = self.project(rows)
        self.assertEqual(len(result['timetable_days']), 5)
        self.assertEqual(result['timetable_week'], date(2026, 8, 3))
        self.assertEqual(result['timetable_days'][4]['rows'][0]['entry_id'], 1)
        result = self.project(rows, '2026-08-10')
        self.assertEqual(result['timetable_days'][0]['rows'][0]['entry_id'], 2)

    def test_historical_weekends_are_preserved_as_warnings(self):
        rows = [self.row(1, 5, '2026-08-08'), self.row(2, 6, '2026-08-09')]
        result = self.project(rows)
        self.assertEqual(len(result['timetable_days']), 5)
        self.assertEqual(result['timetable_weeks'], [])
        self.assertEqual([r['entry_id'] for r in result['timetable_weekend']], [1, 2])
        self.assertEqual(result['timetable_weekend'][1]['review_dates'], [date(2026, 8, 9)])
        from django.template.loader import render_to_string
        # Identity dictionaries normally come from the adapter.
        html = render_to_string('schedules/shs_weekend_warning.html', result)
        self.assertIn('Weekend SHS meeting &mdash; review required', html)
        self.assertIn('2026-08-09', html)

    def test_mixed_tertiary_weekend_retained(self):
        rows = [self.row(1, 5, '2026-08-08'), self.row(2, 5, '2026-08-08', 'TERTIARY'),
                self.row(3, 6, '2026-08-09', 'TERTIARY')]
        result = self.project(rows)
        self.assertEqual(len(result['timetable_days']), 7)
        self.assertEqual([r['entry_id'] for r in result['timetable_days'][5]['rows']], [2])
        self.assertEqual([r['entry_id'] for r in result['timetable_days'][6]['rows']], [3])
        self.assertEqual([r['entry_id'] for r in result['timetable_weekend']], [1])

    def test_snapshot_weekend_dates_rejected(self):
        for day, value in ((5, '2026-08-08'), (6, '2026-08-09'), (0, '2026-08-08')):
            self.assertIn(WEEKDAY_ERROR, snapshot_day_errors({'day': day, 'dates': [value]}))
