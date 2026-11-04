from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import models as m
from . import test_detail_timetable as detail
from . import test_schedule_visibility as visibility
from .services.detail_timetable import personal_timetable_context
from .test_publication_helpers import historical_visibility, upgrade


@historical_visibility
class FacultyDateTimetableTests(TestCase):
    section_for = detail.DetailTimetableTests.section_for
    student = detail.DetailTimetableTests.student
    add_entry = detail.DetailTimetableTests.add_entry

    def publish(self):
        self.large = []
        if self._testMethodName == 'test_projection_query_bound':
            self.large = [visibility.ParticipationVisibilityTests.add_entry(self, n) for n in range(4, 16)]
        self.first = self.entry
        self.second = self.add_entry(2)
        self.hidden = self.add_entry(3)
        self.other_faculty = m.Faculty.objects.create(department=self.department, employee_id='OTHER', full_name='Other instructor')
        self.hidden.faculty_override = self.other_faculty
        self.hidden.save()
        if self._testMethodName == 'test_unknown_dates_are_separate':
            self.unknown = self.add_entry(4, metadata={'dates': ['bad']})
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()

    def setUp(self):
        visibility.ParticipationVisibilityTests.setUp(self)
        self.user = User.objects.create_user('dated-faculty')
        m.Profile.objects.create(user=self.user, role='FACULTY')
        self.faculty.user = self.user
        self.faculty.save()
        self.client.force_login(self.user)

    def page(self, **params):
        return self.client.get(reverse('dashboard'), params)

    def cards(self, response):
        return [e.presentation for row in response.context['timetable_grid'] for cell in row['cells'] for e in cell['entries']]

    def test_selected_week_dates_slots_and_workload_unchanged(self):
        upgrade()
        for week, entry in (('2026-08-03', self.first), ('2026-08-10', self.second)):
            response = self.page(week=week)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([r['entry_id'] for r in self.cards(response)], [entry.pk])
            self.assertContains(response, f'data-student-timetable-entry="{entry.pk}"', count=1)
            self.assertContains(response, f'datetime="{week}"')
            self.assertContains(response, 'id="faculty-week"')
            self.assertEqual(len(response.context['timetable_days']), 5)
            self.assertEqual(sum(c['occupied'] for row in response.context['timetable_grid'] for c in row['cells']), 2)
            group = response.context['workloads'][0]
            self.assertEqual((group['minutes'], group['hours'], group['meetings'], group['sections']), (120, Decimal(2), 2, 1))
            self.assertContains(response, 'not academic units or actual teaching hours for the selected SHS week')
            self.assertContains(response, '(120 minutes) total')
            self.assertNotContains(response, '(120 minutes) per week')
            self.assertEqual(self.cards(response)[0]['source'], 'FINALIZED_SNAPSHOT')
            self.assertEqual(self.cards(response)[0]['faculty']['label'], self.faculty.full_name)

    def test_default_invalid_week_no_unrelated_dates(self):
        upgrade()
        for params in ({}, {'week': 'bad'}, {'week': '<script>'}, {'week': '2026-08-17'}):
            response = self.page(**params)
            self.assertEqual(response.context['timetable_week'], date(2026, 8, 3))
            self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 3), date(2026, 8, 10)])
            self.assertNotContains(response, '2026-08-17')
            self.assertNotContains(response, self.other_faculty.full_name)

    def test_unknown_dates_are_separate(self):
        upgrade()
        response = self.page()
        self.assertEqual([e['entry_id'] for e in response.context['timetable_unknown']], [self.unknown.pk])
        self.assertContains(response, 'Meeting dates unavailable')
        self.assertContains(response, f'data-student-timetable-entry="{self.unknown.pk}"', count=1)
        self.assertEqual(response.context['workloads'][0]['minutes'], 180)

    def test_effective_override_and_missing_faculty_link(self):
        upgrade()
        other_user = User.objects.create_user('other-faculty')
        m.Profile.objects.create(user=other_user, role='FACULTY')
        self.other_faculty.user = other_user
        self.other_faculty.save()
        self.client.force_login(other_user)
        response = self.page()
        self.assertEqual([e.pk for e in response.context['entries']], [self.hidden.pk])
        self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 17)])
        self.assertNotContains(response, '2026-08-03')
        self.other_faculty.user = None
        self.other_faculty.save()
        response = self.page()
        self.assertEqual(response.context['timetable_weeks'], [])
        self.assertEqual(response.context['workloads'], [])

    def test_draft_and_archived_dates_denied(self):
        draft = m.Schedule.objects.create(term=self.term, name='Private draft')
        draft.entries.create(assignment=self.first.assignment, room=self.room, day=0, start_time=self.first.start_time, end_time=self.first.end_time)
        from .protection import archive_transition
        self.schedule.status = 'ARCHIVED'
        with archive_transition():
            self.schedule.save(update_fields=['status'])
        upgrade()
        response = self.page()
        self.assertEqual(response.context['entries'], [])
        self.assertEqual(response.context['timetable_weeks'], [])
        self.assertEqual(response.context['timetable_unknown'], [])
        self.assertEqual(response.context['timetable_weekend'], [])

    def test_projection_query_bound(self):
        upgrade()
        counts = []
        for batch in ([self.first], [self.first, self.second] + self.large):
            with CaptureQueriesContext(connection) as queries:
                result = personal_timetable_context(batch)
            counts.append(len(queries))
            self.assertTrue(result['timetable_grid'])
        self.assertEqual(counts, [2, 2])
        print('Faculty projection queries: 1/14 distinct entries:', counts)
