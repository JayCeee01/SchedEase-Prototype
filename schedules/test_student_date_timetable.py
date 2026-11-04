from datetime import date
from unittest.mock import patch

from django.db import connection, transaction
from django.test import TestCase, SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import test_detail_timetable as detail
from . import test_schedule_visibility as visibility
from .services.detail_timetable import personal_timetable_context
from .test_publication_helpers import historical_visibility, upgrade


@historical_visibility
class StudentDateTimetableTests(TestCase):
    section_for = detail.DetailTimetableTests.section_for
    student = detail.DetailTimetableTests.student
    add_entry = detail.DetailTimetableTests.add_entry
    setUp = detail.DetailTimetableTests.setUp

    def publish(self):
        self.large = []
        if self._testMethodName == 'test_projection_queries_remain_bounded':
            for sequence in range(4, 16):
                self.large.append(visibility.ParticipationVisibilityTests.add_entry(self, sequence))
        detail.DetailTimetableTests.publish(self)

    def page(self, **params):
        return self.client.get(reverse('dashboard'), params)

    def cards(self, response):
        return [entry.presentation for row in response.context['timetable_grid']
                for cell in row['cells'] for entry in cell['entries']]

    def test_default_and_selected_week_actual_dates_and_single_card(self):
        upgrade()
        for week, expected in ((None, self.first), ('2026-08-10', self.second)):
            response = self.page(**({'week': week} if week else {}))
            self.assertEqual(response.status_code, 200)
            cards = self.cards(response)
            self.assertEqual([e['entry_id'] for e in cards], [expected.pk])
            self.assertEqual(cards[0]['meeting_date'].isoformat(), week or '2026-08-03')
            self.assertContains(response, f'data-student-timetable-entry="{expected.pk}"', count=1)
            self.assertContains(response, f'datetime="{week or "2026-08-03"}"')
            self.assertEqual(sum(cell['occupied'] for row in response.context['timetable_grid'] for cell in row['cells']), 2)
            self.assertContains(response, 'Class continues')

    def test_invalid_week_never_reveals_hidden_dates(self):
        upgrade()
        for value in ('bad', '<script>', '2026-08-17', '2026-08-04'):
            response = self.page(week=value)
            self.assertEqual(response.context['timetable_week'], date(2026, 8, 3))
            self.assertEqual(response.context['timetable_weeks'], [date(2026, 8, 3), date(2026, 8, 10)])
            self.assertNotContains(response, '2026-08-17')
            self.assertEqual([r['entry_id'] for r in self.cards(response)], [self.first.pk])

    def test_primary_additional_unrelated_and_archived(self):
        with transaction.atomic():
            upgrade()
            for user in (self.primary_user, self.extra_user):
                self.client.force_login(user)
                self.assertEqual([r['entry_id'] for r in self.cards(self.page())], [self.first.pk])
            outsider = self.student('no-participation', self.section_for('D'))
            self.client.force_login(outsider)
            response = self.page()
            self.assertEqual(response.context['timetable_weeks'], [])
            self.assertEqual(response.context['timetable_unknown'], [])
            self.assertContains(response, 'No published classes yet')
            transaction.set_rollback(True)
        from .protection import archive_transition
        self.schedule.status = 'ARCHIVED'
        with archive_transition():
            self.schedule.save(update_fields=['status'])
        upgrade()
        self.client.force_login(self.extra_user)
        self.assertEqual(self.page().context['timetable_weeks'], [])

    def test_unknown_dates_are_visible_separately(self):
        upgrade()
        response = self.page()
        self.assertEqual([row['entry_id'] for row in response.context['timetable_unknown']], [self.unknown.pk])
        self.assertContains(response, 'Meeting dates unavailable')
        self.assertContains(response, f'data-student-timetable-entry="{self.unknown.pk}"', count=1)
        self.assertNotContains(response, '2026-08-24')

    def test_frozen_identity_survives_live_label_change(self):
        upgrade()
        # Simulate a changed live label on reads only; frozen evidence stays real.
        from . import models as m
        original = m.Section.from_db.__func__
        def live_section(cls, db, fields, values):
            section = original(cls, db, fields, values)
            if section.pk == self.extra.pk:
                section.name = 'New live label'
            return section
        with patch.object(m.Section, 'from_db', classmethod(live_section)):
            self.assertEqual(m.Section.objects.get(pk=self.extra.pk).name, 'New live label')
            response = self.page()
        card = self.cards(response)[0]
        self.assertEqual(card['primary_section']['label'], self.section.display_name)
        self.assertEqual(card['faculty']['label'], self.faculty.full_name)
        self.assertEqual(card['subject']['code'], self.subject.code)
        self.assertEqual(card['source'], 'FINALIZED_SNAPSHOT')

    def test_projection_queries_remain_bounded(self):
        upgrade()
        counts = []
        for entries in ([self.first], [self.first, self.second] + self.large):
            with CaptureQueriesContext(connection) as queries:
                result = personal_timetable_context(entries)
            counts.append(len(queries))
            self.assertTrue(result['timetable_grid'])
        self.assertEqual(counts, [2, 2])
        print('Student date projection: 1/14 distinct entries, queries:', counts)


class StudentGridProjectionTests(SimpleTestCase):
    def test_overlapping_weekly_cards_are_both_visible_without_calendar_dates(self):
        result = self.project([detail.record(1, 'WEEKLY'), detail.record(2, 'WEEKLY')])
        cards = [e.presentation for row in result['timetable_grid'] for cell in row['cells'] for e in cell['entries']]
        self.assertEqual([r['entry_id'] for r in cards], [1, 2])
        self.assertTrue(result['timetable_has_weekly'])
        self.assertTrue(all(r['meeting_date'] is None for r in cards))

    def project(self, rows, week=None):
        with patch('schedules.services.detail_timetable.present_entries', return_value=rows):
            return personal_timetable_context([], week)

    def test_mixed_known_weekly_and_dated_unknown(self):
        rows = [detail.record(1, 'DATED', ['2026-08-03']), detail.record(2, 'DATED', ['2026-08-10']),
                detail.record(3, 'WEEKLY'), detail.record(4, 'UNKNOWN')]
        result = self.project(rows, '2026-08-10')
        cards = [e.presentation for row in result['timetable_grid'] for cell in row['cells'] for e in cell['entries']]
        self.assertEqual([e['entry_id'] for e in cards], [2, 3])
        self.assertEqual([e['entry_id'] for e in result['timetable_unknown']], [4])
        self.assertIsNone(cards[1]['meeting_date'])

    def test_sunday_boundary_and_tertiary_default_grid(self):
        result = self.project([detail.record(1, 'DATED', ['2026-08-09'], 6), detail.record(2, 'DATED', ['2026-08-10'])])
        self.assertEqual(result['timetable_week'], date(2026, 8, 3))
        self.assertEqual(len(result['timetable_grid'][0]['cells']), 7)
        self.assertEqual(sum(len(cell['entries']) for row in result['timetable_grid'] for cell in row['cells']), 1)
        result = self.project([detail.record(1, 'WEEKLY')])
        self.assertEqual(result['timetable_weeks'], [])
        self.assertEqual(len(result['timetable_grid']), 24)
        self.assertEqual(len(result['timetable_grid'][0]['cells']), 6)
