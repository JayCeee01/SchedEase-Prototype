import csv
import io
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from openpyxl import load_workbook

from . import test_timetable_presentation as fixtures
from .services.schedule_export import export_occurrences, HEADERS
from .services.xlsx_export import occurrence_workbook
from .test_publication_helpers import legacy_case, upgrade


class DateAwareExportTests(TestCase):
    def setUp(self):
        fixtures.SHSPresentationTests.setUp(self)
        self.client.force_login(User.objects.create_superuser('export-date-admin'))

    def entry(self, *args, **kwargs):
        return fixtures.SHSPresentationTests.entry(self, *args, **kwargs)

    def test_dates_cross_format_week_filter_and_read_only(self):
        first = self.entry(date(2026, 8, 3))
        second = self.entry(date(2026, 8, 10), 2)
        with CaptureQueriesContext(connection) as queries:
            rows = export_occurrences([second, first, first])
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(q['sql'].lstrip().startswith('SELECT') for q in queries))
        self.assertEqual([r['actual_date'] for r in rows], [date(2026, 8, 3), date(2026, 8, 10)])
        response = self.client.get(reverse('export_csv', args=[self.schedule.pk]), {'week': '2026-08-03'})
        data = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(data[0], HEADERS)
        self.assertEqual([r[7] for r in data[1:]], ['2026-08-03', '2026-08-10'])
        response = self.client.get(reverse('export_xlsx', args=[self.schedule.pk]))
        ws = load_workbook(io.BytesIO(response.content))['Schedule Details']
        self.assertEqual([ws.cell(i, 10).value.date() for i in (4, 5)], [r['actual_date'] for r in rows])
        self.assertEqual(ws['J4'].number_format, 'yyyy-mm-dd')
        with patch('schedules.views.write_table_pdf') as pdf:
            self.client.get(reverse('export_pdf', args=[self.schedule.pk]))
            rendered = list(pdf.call_args.args[4])
        self.assertEqual(len(rendered), 2)
        self.assertIn('2026-08-10', rendered[1][0])

    def test_unknown_metadata_is_retained(self):
        entry = self.entry(date(2026, 8, 3), metadata={'dates': None})
        row = export_occurrences([entry])[0]
        self.assertIsNone(row['actual_date'])
        self.assertIn('Meeting dates unavailable', row['notes'])
        self.assertIn('primary section shown only', row['notes'])

    def test_multi_date_expansion_and_weekend_warning(self):
        entry = self.entry(date(2026, 8, 3))
        from .services.timetable_presentation import present_entries
        metadata = present_entries([entry])[0]
        metadata['recurrence']['dates'] = ('2026-08-03', '2026-08-10')
        with patch('schedules.services.schedule_export.present_entries', return_value=[metadata]):
            self.assertEqual(len(export_occurrences([entry])), 2)
        metadata['weekday'] = 5
        metadata['recurrence']['dates'] = ('2026-08-08',)
        with patch('schedules.services.schedule_export.present_entries', return_value=[metadata]):
            row = export_occurrences([entry])[0]
        self.assertIn('Weekend SHS meeting', row['notes'])
        self.assertEqual(row['actual_date'], date(2026, 8, 8))

    def test_persisted_date_set_and_inconsistent_dates(self):
        for index, dates in enumerate((['2026-08-03', '2026-08-10'], ['2026-08-04'], None), 1):
            entry = self.entry(date(2026, 8, 3), index, metadata={'dates': dates})
            rows = export_occurrences([entry])
            if index == 1:
                self.assertEqual([r['actual_date'].isoformat() for r in rows], dates)
            else:
                self.assertEqual(len(rows), 1)
                self.assertIsNone(rows[0]['actual_date'])
                self.assertEqual(rows[0]['recurrence']['kind'], 'UNKNOWN')

    def test_added_text_fields_are_safe_and_unicode_preserved(self):
        entry = self.entry(date(2026, 8, 3))
        rows = export_occurrences([entry])
        rows[0]['sections'] = '=1+1; Pe\u00f1a'
        wb = occurrence_workbook('Test', self.term, rows, [])
        cell = wb['Schedule Details']['N4']
        self.assertEqual(cell.value, '=1+1; Pe\u00f1a')
        self.assertEqual(cell.data_type, 's')

    @legacy_case
    def test_frozen_combined_participation(self):
        fixtures.SHSPresentationTests.test_combined_sections_and_frozen_history.__wrapped__(self)
        rows = export_occurrences(list(self.schedule.entries.all()))
        self.assertNotIn('CHANGED', rows[0]['sections'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'FINALIZED_SNAPSHOT')

    def test_distinct_batch_queries_and_no_writes(self):
        entries = [self.entry(date(2026, 8, 3), index) for index in range(1, 9)]
        counts = []
        for batch in (entries[:1], entries):
            with CaptureQueriesContext(connection) as queries:
                rows = export_occurrences(batch)
            counts.append(len(queries))
            self.assertEqual(len(rows), len(batch))
            self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertEqual(counts, [2, 2])

    def test_all_new_csv_text_fields_use_formula_protection(self):
        from .services.schedule_export import values
        from .services.csv_export import writer
        entry = self.entry(date(2026, 8, 3))
        row = export_occurrences([entry])[0]
        row['sections'] = '=1+1'
        row['academic_context'].update(term_name='@term', school_year='+year', education_level='-level')
        row['instructional_label'] = '=instruction'
        row['notes'] = '\t=warning'
        output = io.StringIO()
        writer(output).writerow(values(row))
        cells = next(csv.reader(io.StringIO(output.getvalue())))
        for index in (11, 12, 13, 14, 15, 18):
            self.assertTrue(cells[index].startswith("'"))

    def test_long_participants_pdf_and_workbook_retain_content(self):
        from .services.schedule_export import pdf_rows
        from .services.pdf_export import write_table_pdf
        from .services.xlsx_export import workbook_bytes
        entry = self.entry(date(2026, 8, 3))
        rows = export_occurrences([entry])
        rows[0]['sections'] = '; '.join('Synthetic section ' + str(i) for i in range(150))
        book = load_workbook(io.BytesIO(workbook_bytes(occurrence_workbook('Long', self.term, rows, []))))
        self.assertEqual(book['Schedule Details']['N4'].value, rows[0]['sections'])
        output = io.BytesIO()
        write_table_pdf(output, 'Long', 'Term', ['Date', 'Course', 'Sections', 'Faculty', 'Room', 'Evidence'],
                        pdf_rows(rows), [1, 1, 2, 1, 1, 2])
        self.assertTrue(output.getvalue().startswith(b'%PDF'))

    @legacy_case
    def test_missing_finalized_snapshot_still_fails(self):
        entry = self.entry(date(2026, 8, 3))
        from . import models as m
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()
        upgrade()
        from django.db.models.query import QuerySet
        original = QuerySet._fetch_all
        def missing_snapshot(qs):
            if qs.model is m.ScheduleSnapshot:
                qs._result_cache = []
                return
            return original(qs)
        with patch.object(QuerySet, '_fetch_all', missing_snapshot):
            with self.assertRaises(m.ScheduleSnapshot.DoesNotExist):
                export_occurrences([entry])
