from copy import deepcopy
from datetime import date, time, timedelta
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import models as m
from . import test_schedule_visibility as fixtures
from .services.detail_timetable import timetable_context
from .test_publication_helpers import historical_visibility, upgrade


def record(pk, kind, dates=None, weekday=0):
    return dict(entry_id=pk, weekday=weekday, start_time='08:00:00', end_time='09:00:00',
                recurrence=dict(kind=kind, dates=dates))


class WeekProjectionTests(SimpleTestCase):
    def project(self, rows, week=None):
        with patch('schedules.services.detail_timetable.present_entries', return_value=rows):
            return timetable_context([], week)

    def test_same_time_different_dates_and_default_week(self):
        rows = [record(1, 'DATED', ['2026-08-03']), record(2, 'DATED', ['2026-08-10'])]
        first = self.project(rows)
        second = self.project(rows, '2026-08-10')
        self.assertEqual([r['entry_id'] for r in first['timetable_days'][0]['rows']], [1])
        self.assertEqual([r['entry_id'] for r in second['timetable_days'][0]['rows']], [2])
        self.assertEqual(second['timetable_days'][0]['rows'][0]['meeting_date'], date(2026, 8, 10))

    def test_week_boundaries_and_duplicate_input(self):
        row = record(1, 'DATED', ['2026-08-09'], 6)
        result = self.project([row, row, record(2, 'DATED', ['2026-08-10'])], '2026-08-03')
        self.assertEqual(result['timetable_week_end'], date(2026, 8, 9))
        self.assertEqual(len(result['timetable_days'][6]['rows']), 1)
        self.assertEqual(result['timetable_days'][0]['rows'], [])

    def test_invalid_or_unavailable_week(self):
        rows = [record(1, 'DATED', ['2026-08-03'])]
        for value in ('bad', '2026-02-30', '2026-08-04', '2099-01-01', '<script>'):
            with self.subTest(value=value):
                result = self.project(rows, value)
                self.assertTrue(result['timetable_week_invalid'])
                self.assertEqual(result['timetable_week'], date(2026, 8, 3))

    def test_mixed_weekly_and_unknown(self):
        result = self.project([record(1, 'DATED', ['2026-08-03']), record(2, 'WEEKLY'), record(3, 'UNKNOWN')])
        self.assertEqual([r['entry_id'] for r in result['timetable_days'][0]['rows']], [1, 2])
        self.assertEqual([r['entry_id'] for r in result['timetable_unknown']], [3])
        self.assertIsNone(result['timetable_days'][0]['rows'][1]['meeting_date'])

    def test_tertiary_weekly_has_no_selector_or_date_invention(self):
        result = self.project([record(1, 'WEEKLY')], '2026-08-03')
        self.assertEqual(result['timetable_weeks'], [])
        self.assertEqual(len(result['timetable_days']), 6)
        self.assertEqual(len(result['timetable_days'][0]['rows']), 1)


@historical_visibility
class DetailTimetableTests(TestCase):
    section_for = fixtures.ParticipationVisibilityTests.section_for
    student = fixtures.ParticipationVisibilityTests.student
    def add_entry(self, sequence=1, metadata=None, section=None):
        from .test_shs_operations import OperationalInputTests
        from .services.shs_scheduling import pattern_snapshot
        self.config.ends_on = date(2026, 8, 31)
        self.config.save()
        day = date(2026, 8, 3) + timedelta(days=7 * (sequence - 1))
        pattern = OperationalInputTests.pattern(self, sequence=sequence, recurrence='DATED', meeting_date=day)
        meeting = m.TeachingAssignment.objects.create(assignment=self.assignment, component='GENERAL',
            meeting_index=sequence, duration_minutes=60, required_room_type_override='LECTURE')
        data = pattern_snapshot(pattern)
        if metadata is not None:
            data.update(metadata)
        m.SHSMeetingBinding.objects.create(meeting=meeting, pattern=pattern, data=data)
        return self.schedule.entries.create(assignment=meeting, room=self.room, section_override=section,
            day=0, start_time=time(8), end_time=time(9))

    def publish(self):
        # Build all test entries before finalization, retaining trigger protections.
        self.first = self.entry
        self.second = self.add_entry(2)
        self.hidden = self.add_entry(3, section=self.other)
        if self._testMethodName == 'test_unknown_dates_are_visible_separately':
            self.unknown = self.add_entry(4, metadata={'dates': ['invalid']})
        # Bindings are immutable: metadata is provided when creating meetings.
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()

    def setUp(self):
        fixtures.ParticipationVisibilityTests.setUp(self)
        self.client.force_login(self.extra_user)

    def test_authorized_weeks_filters_and_views(self):
        upgrade()
        response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]),
                                   {'week': '2026-08-10', 'section': self.extra.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['timetable_week'], date(2026, 8, 10))
        rows = response.context['timetable_days'][0]['rows']
        self.assertEqual({r['entry_id'] for r in rows}, {self.second.pk})
        self.assertTrue(all(r['meeting_date'] == date(2026, 8, 10) for r in rows))
        self.assertContains(response, f'data-timetable-entry="{self.second.pk}"', count=1)
        self.assertNotContains(response, f'data-timetable-entry="{self.first.pk}"')
        self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 3), date(2026, 8, 10)])
        self.assertNotContains(response, '2026-08-17')
        self.assertNotContains(response, f'data-timetable-entry="{self.hidden.pk}"')
        self.assertContains(response, 'data-schedule-view-panel="table"')
        self.assertContains(response, 'data-schedule-view-panel="timetable"')
        self.assertEqual(response.context['filter_form']['section'].value(), str(self.extra.pk))
        self.assertEqual(list(response.context['filter_form'].fields['section'].queryset), [self.extra])

    def test_published_grid_uses_only_authorized_selected_week(self):
        upgrade()
        response=self.client.get(reverse('browse_schedules'), {'view':'timetable','week':'2026-08-10','section':self.extra.pk})
        self.assertTemplateUsed(response,'schedules/_time_grid.html')
        cards=[e.presentation for row in response.context['timetable_grid'] for cell in row['cells'] for e in cell['entries']]
        self.assertEqual([r['entry_id'] for r in cards],[self.second.pk])
        self.assertEqual(cards[0]['meeting_date'],date(2026,8,10))
        self.assertNotContains(response,f'data-timetable-entry="{self.hidden.pk}"')
        denied=self.client.get(reverse('browse_schedules'),{'view':'timetable','section':self.other.pk})
        self.assertEqual(denied.context['timetable_weeks'],[])
        self.assertEqual(denied.context['timetable_grid'],[])

    def test_primary_additional_unrelated_and_crafted_filter(self):
        upgrade()
        for user in (self.primary_user, self.extra_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('schedule_detail', args=[self.schedule.pk])).status_code, 200)
        # The unrelated section is authorized only for its own override entry.
        self.client.force_login(self.extra_user)
        response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]), {'section': self.other.pk})
        self.assertEqual(response.context['timetable_weeks'], [])
        self.assertFalse(response.context['timetable_has_rows'])
        from django.contrib.auth.models import User
        user = self.student('unrelated-new', self.section_for('D'))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('schedule_detail', args=[self.schedule.pk])).status_code, 404)

    def test_missing_invalid_week_and_table_scope(self):
        upgrade()
        for query in ({}, {'week': 'bad'}, {'week': '2050-01-03'}):
            response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]), query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['timetable_week'], date(2026, 8, 3))
            self.assertEqual(len(response.context['entries']), 2)
        self.assertContains(response, 'requested week is unavailable')

    def test_unknown_dates_are_visible_separately(self):
        upgrade()
        response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]))
        self.assertEqual([r['entry_id'] for r in response.context['timetable_unknown']], [self.unknown.pk])
        self.assertContains(response, 'Meeting dates unavailable')
        self.assertContains(response, f'data-timetable-entry="{self.unknown.pk}"', count=1)
        self.assertNotContains(response, '2026-08-24')

    def test_adapter_queries_bounded(self):
        upgrade()
        for entries in ([self.first], [self.first, self.second]):
            with CaptureQueriesContext(connection) as queries:
                result = timetable_context(entries)
            self.assertEqual(len(queries), 2)
            self.assertEqual(len(result['timetable_days'][0]['rows']), 1)
        print('Detail projection: 2 SELECTs for 1 and 2 distinct entries.')


    def test_tab_state_filters_and_safe_default(self):
        upgrade()
        from html.parser import HTMLParser
        class Elements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.elements = []
            def handle_starttag(self, tag, attrs):
                self.elements.append((tag, dict(attrs)))
        for supplied, expected in ((None, 'table'), ('table', 'table'), ('timetable', 'timetable'),
                                   ('#schedule-table-view', 'table'), ('<script>alert(1)</script>', 'table')):
            with self.subTest(view=supplied):
                query = {'week': '2026-08-10', 'section': self.extra.pk}
                if supplied is not None:
                    query['view'] = supplied
                response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]), query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['schedule_view'], expected)
                self.assertEqual(response.context['timetable_week'], date(2026, 8, 10))
                self.assertEqual(response.context['filter_form']['section'].value(), str(self.extra.pk))
                parsed = Elements()
                parsed.feed(response.content.decode())
                state = [a for tag, a in parsed.elements if a.get('name') == 'view']
                self.assertEqual(state, [{'type': 'hidden', 'name': 'view', 'value': expected, 'data-schedule-view-state': None}])
                for tag, attrs in parsed.elements:
                    if 'data-schedule-view-panel' in attrs:
                        self.assertEqual('hidden' not in attrs, attrs['data-schedule-view-panel'] == expected)
                    if 'data-schedule-view-button' in attrs:
                        self.assertEqual(attrs['aria-selected'], str(attrs['data-schedule-view-button'] == expected).lower())

    def test_clean_separators_and_tab_does_not_bypass_filters(self):
        upgrade()
        from pathlib import Path
        from django.conf import settings
        for template in ('schedule_detail.html', 'schedule_timetable_view.html'):
            source = (Path(settings.BASE_DIR) / 'templates/schedules' / template).read_text(encoding='utf-8')
            self.assertNotIn('Monday?Sunday', source)
            self.assertNotIn(' }} ? {{ ', source)
        response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]),
            {'view': 'timetable', 'section': self.other.pk, 'week': '2026-08-17'})
        self.assertEqual(response.context['schedule_view'], 'timetable')
        self.assertFalse(response.context['timetable_weeks'])
        self.assertFalse(response.context['entries'])
