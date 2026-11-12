from datetime import date, time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase, SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import models as m
from . import test_detail_timetable as detail
from . import test_schedule_visibility as visibility
from .services.detail_timetable import room_timetable_context
from .services.room_utilization import utilization_rows
from .test_publication_helpers import historical_visibility, upgrade


@historical_visibility
class RoomDateTimetableTests(TestCase):
    section_for = detail.DetailTimetableTests.section_for
    student = detail.DetailTimetableTests.student
    add_entry = detail.DetailTimetableTests.add_entry

    def test_personal_export_additional_participant_selected_week(self):
        from io import BytesIO
        from openpyxl import load_workbook
        upgrade()
        self.client.force_login(self.extra_user)
        response = self.client.get(reverse('personal_schedule_export', args=['xlsx']),
            {'schedule': self.schedule.pk, 'week': '2026-08-10'})
        self.assertEqual(response.status_code, 200)
        values = list(load_workbook(BytesIO(response.content)).active.values)
        self.assertIn('2026-08-10', str(values))
        self.assertNotIn('2026-08-03', str(values))
        self.assertEqual(len(values), 4)

    def test_export_selected_shs_week(self):
        from io import BytesIO
        from openpyxl import load_workbook
        upgrade()
        params = {'term': self.term.pk, 'schedule': self.schedule.pk, 'room': self.room.pk, 'week': '2026-08-10'}
        response = self.client.get(reverse('room_schedule_export', args=['xlsx']), params)
        self.assertEqual(response.status_code, 200)
        values = list(load_workbook(BytesIO(response.content)).active.values)
        text = str(values)
        self.assertIn('2026-08-10', text)
        self.assertNotIn('2026-08-03', text)
        self.assertNotIn('Other room', text)
        self.assertEqual(len(values), 4)

    def publish(self):
        self.first = self.entry
        self.second = self.add_entry(2)
        self.hidden = self.add_entry(3)
        self.other_room = m.Room.objects.create(name='Other room', capacity=40, room_type='LECTURE')
        self.hidden.room = self.other_room
        self.hidden.save()
        self.large = []
        if self._testMethodName == 'test_query_count_constant':
            self.large = [visibility.ParticipationVisibilityTests.add_entry(self, n) for n in range(5, 17)]
        if self._testMethodName == 'test_unknown_dates_and_missing_snapshot_fallback':
            self.unknown = self.add_entry(5, metadata={'dates': ['bad']})
        selected = self.schedule
        self.other_schedule = m.Schedule.objects.create(term=self.term, name='Other version')
        self.schedule = self.other_schedule
        self.outside = self.add_entry(4)
        self.schedule = selected
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()

    def setUp(self):
        visibility.ParticipationVisibilityTests.setUp(self)
        self.admin = User.objects.create_superuser('room-admin')
        self.client.force_login(self.admin)

    def page(self, **changes):
        query = {'schedule': self.schedule.pk, 'room': self.room.pk, 'term': self.term.pk}
        query.update(changes)
        return self.client.get(reverse('room_schedule'), query)

    def cards(self, response):
        return [e.presentation for row in response.context['grid'] for cell in row['cells'] for e in cell['entries']]

    def test_selected_week_room_schedule_and_single_cards(self):
        upgrade()
        before = utilization_rows(self.schedule)
        for week, expected in (('2026-08-03', self.first), ('2026-08-10', self.second)):
            response = self.page(week=week)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([r['entry_id'] for r in self.cards(response)], [expected.pk])
            self.assertContains(response, f'data-student-timetable-entry="{expected.pk}"', count=1)
            self.assertContains(response, f'datetime="{week}"')
            self.assertEqual(sum(c['occupied'] for row in response.context['grid'] for c in row['cells']), 2)
            self.assertEqual(response.context['schedule'].pk, self.schedule.pk)
            self.assertEqual(response.context['room'].pk, self.room.pk)
            self.assertEqual(response.context['term'].pk, self.term.pk)
            self.assertEqual(len(response.context['timetable_days']), 5)
            self.assertContains(response, 'Vacant within selected schedule')
            self.assertContains(response, 'does not mean globally available')
        self.assertEqual(utilization_rows(self.schedule), before)

    def test_default_invalid_week_and_no_unrelated_dates(self):
        upgrade()
        for query in ({}, {'week': 'bad'}, {'week': '<script>'}, {'week': '2026-08-17'}):
            response = self.page(**query)
            self.assertEqual(response.context['timetable_week'], date(2026, 8, 3))
            self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 3), date(2026, 8, 10)])
            self.assertNotContains(response, '2026-08-17')
            self.assertNotContains(response, '2026-08-24')
        response = self.page(room=self.other_room.pk)
        self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 17)])
        response = self.page(schedule=self.other_schedule.pk)
        self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 24)])

    def test_invalid_selection_and_term_mismatch(self):
        upgrade()
        for key in ('schedule', 'room', 'term'):
            for value in ('bad', '-1', '<script>', '9' * 40, '999999'):
                with self.subTest(key=key, value=value):
                    self.assertEqual(self.page(**{key: value}).status_code, 404)
        other = m.AcademicTerm.objects.create(name='Other', school_year='2026-2027', starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        self.assertEqual(self.page(term=other.pk).status_code, 404)

    def test_admin_only_all_schedule_states(self):
        teacher = User.objects.create_user('room-teacher')
        m.Profile.objects.create(user=teacher, role='FACULTY')
        with transaction.atomic():
            upgrade()
            for user in (self.primary_user, teacher):
                self.client.force_login(user)
                for schedule in (self.schedule, self.other_schedule):
                    self.assertEqual(self.page(schedule=schedule.pk).status_code, 302)
            self.client.logout()
            self.assertEqual(self.page().status_code, 302)
            self.client.force_login(self.admin)
            self.assertEqual(self.page(schedule=self.other_schedule.pk).status_code, 200)
            transaction.set_rollback(True)
        from .protection import archive_transition
        self.schedule.status = 'ARCHIVED'
        with archive_transition(): self.schedule.save(update_fields=['status'])
        upgrade()
        self.client.force_login(self.admin)
        self.assertEqual(self.page().status_code, 200)
        self.client.force_login(teacher)
        self.assertEqual(self.page().status_code, 302)

    def test_unknown_dates_and_missing_snapshot_fallback(self):
        upgrade()
        response = self.page()
        self.assertEqual([r['entry_id'] for r in response.context['timetable_unknown']], [self.unknown.pk])
        self.assertContains(response, 'Meeting dates unavailable')
        with patch('schedules.services.detail_timetable.room_timetable_context', side_effect=m.ScheduleSnapshot.DoesNotExist):
            response = self.page()
        self.assertContains(response, 'Historical timetable unavailable')
        self.assertNotContains(response, 'vacant-cell')

    def test_frozen_labels_and_current_room_policy(self):
        upgrade()
        snapshot = m.ScheduleSnapshot.objects.get(schedule=self.schedule).data
        frozen = next(r for r in snapshot['entries'] if r['id'] == self.first.pk)
        from django.db.models.query import QuerySet
        original = QuerySet._fetch_all
        expected_query = self.room.availability_set.all().query.sql_with_params()
        period = m.Availability(room=self.room, day=0, start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
        def current_periods(qs):
            if qs.model is m.Availability and qs.query.sql_with_params() == expected_query:
                qs._result_cache = [period]
                return
            return original(qs)
        with patch.object(QuerySet, '_fetch_all', current_periods):
            self.assertEqual(list(self.room.availability_set.all()), [period])
            response = self.page()
        row = self.cards(response)[0]
        self.assertEqual(row['source'], 'FINALIZED_SNAPSHOT')
        self.assertEqual(row['room']['label'], frozen['room']['name'])
        self.assertEqual(row['subject']['title'], frozen['course']['title'])
        self.assertEqual(row['faculty']['label'], frozen['faculty']['full_name'])
        self.assertEqual(row['primary_section']['label'], frozen['section']['display_name'])
        occupied = [c for slot in response.context['grid'] for c in slot['cells'] if c['occupied']]
        self.assertTrue(all(not c['available'] for c in occupied))
        self.assertContains(response, 'Outside current room availability')
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, snapshot)

    def test_query_count_constant(self):
        upgrade()
        counts = []
        for entries in ([self.first], [self.first, self.second] + self.large):
            with CaptureQueriesContext(connection) as queries:
                result = room_timetable_context(entries, self.room)
            counts.append(len(queries))
            self.assertTrue(result['grid'])
        self.assertEqual(counts, [3, 3])
        print('Room projection + availability queries: 1/14 distinct entries:', counts)


class RoomMixedProjectionTests(SimpleTestCase):
    def test_weekends_and_mixed_recurring_tertiary(self):
        from types import SimpleNamespace
        rows = [detail.record(1, 'DATED', ['2026-08-03']), detail.record(2, 'DATED', ['2026-08-08'], 5),
                detail.record(3, 'WEEKLY', weekday=5), detail.record(4, 'UNKNOWN')]
        for index, row in enumerate(rows):
            row['academic_context'] = {'education_level': 'SHS' if index < 2 else 'TERTIARY'}
        with patch('schedules.services.detail_timetable.present_entries', return_value=rows):
            result = room_timetable_context([], SimpleNamespace(availability_set=SimpleNamespace(all=lambda: []), is_active=True))
        cards = [e.presentation['entry_id'] for slot in result['grid'] for cell in slot['cells'] for e in cell['entries']]
        self.assertEqual(cards, [1, 3])
        self.assertEqual([r['entry_id'] for r in result['timetable_weekend']], [2])
        self.assertEqual([r['entry_id'] for r in result['timetable_unknown']], [4])
        self.assertEqual(result['timetable_weeks'], [date(2026, 8, 3)])
