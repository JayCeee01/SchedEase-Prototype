"""CSV security contracts using synthetic records and parsed output, not Excel automation."""
import csv
import io
from datetime import time
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
import shutil
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse

from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.csv_export import writer

ATTACKS = ['=1+1', '+1+1', '-1+1', '@SUM(1)', '  =1', '\t=1', '\r=1', '\n=1',
           '\u00a0=1', '\u2003+1', '\ufeff=1', '\x00=1', '\x1f@x', '\uff1d1', '\uff0b1', '\uff0d1', '\uff20x', '\tordinary']
ORDINARY = ['Course 101', 'Teacher Example', 'Room A', '\u4e2d\u6587 Caf\u00e9', ' A room', 'A,"B"\n=1', "O'Brien", '?Question']


@contextmanager
def TemporaryDirectory(*, dir):
    # Follow existing report tests: inherit workspace ACLs on Windows.
    path = dir / ('csv-test-' + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        assert path.resolve().parent == dir.resolve()
        shutil.rmtree(path)


def rows(response):
    return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'), newline='')))


class CSVEndpointSecurityTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='csv-admin', password='test-only')
        self.client.force_login(self.admin)
        self.schedule = m.Schedule.objects.create(term=self.term, name='CSV synthetic')
        m.ScheduleEntry.objects.create(schedule=self.schedule, assignment=self.meetings[0], room=self.room,
                                      day=0, start_time=time(8), end_time=time(9))

    def test_schedule_response_and_storage(self):
        for value in ATTACKS + ORDINARY:
            with self.subTest(value=repr(value)):
                m.Subject.objects.filter(pk=self.subject.pk).update(code=value)
                m.Faculty.objects.filter(pk=self.faculty.pk).update(full_name=value)
                m.Room.objects.filter(pk=self.room.pk).update(name=value)
                response = self.client.get(reverse('export_csv', args=[self.schedule.pk]))
                self.assertEqual(response.status_code, 200)
                data = rows(response)
                self.assertEqual(data[0], ['Day', 'Start', 'End', 'Course', 'Section', 'Faculty', 'Room'])
                self.assertEqual(len(data), 2)
                self.assertEqual(len(data[1]), 7)
                expected = "'" + value if value in ATTACKS else value
                self.assertEqual([data[1][i] for i in (3, 5, 6)], [expected] * 3)
                self.assertEqual(data[1][4], str(self.section))
                self.room.refresh_from_db()
                self.assertEqual(self.room.name, value)

    def test_section_display_is_sanitized(self):
        m.Program.objects.filter(pk=self.section.program_id).update(code='=1')
        response = self.client.get(reverse('export_csv', args=[self.schedule.pk]))
        self.assertEqual(rows(response)[1][4], "'=1 1-A")

    def test_room_response_and_numeric_columns(self):
        for value in ATTACKS + ORDINARY:
            with self.subTest(value=repr(value)):
                m.Room.objects.filter(pk=self.room.pk).update(name=value)
                response = self.client.get(reverse('room_utilization_csv'), {'schedule': self.schedule.pk})
                self.assertEqual(response.status_code, 200)
                data = rows(response)
                self.assertEqual(data[0], ['Room', 'Room Type', 'Capacity', 'Monday %', 'Tuesday %', 'Wednesday %', 'Thursday %', 'Friday %', 'Saturday %', 'Weekly Utilization %', 'Seat Utilization %', 'Available Hours', 'Scheduled Hours', 'Assigned Classes', 'Status'])
                self.assertEqual(len(data), 2)
                self.assertEqual(data[1][0], "'" + value if value in ATTACKS else value)
                self.assertEqual(int(data[1][2]), 30)
                self.assertEqual(float(data[1][12]), 1)

    def test_import_error_response_and_owner_permissions(self):
        batch = m.AcademicImport.objects.create(user=self.admin, payload={'preview': {'issues': [
            {'row': 2, 'columns': [value], 'problem': value} for value in ATTACKS]}})
        url = reverse('academic_import_errors', args=[batch.pk])
        response = self.client.get(url)
        data = rows(response)
        self.assertEqual(data[0], ['Spreadsheet row', 'Column', 'Problem', 'How to fix'])
        for row, value in zip(data[1:], ATTACKS):
            self.assertEqual(row[1:3], ["'" + value] * 2)
            self.assertEqual(len(row), 4)
        other = User.objects.create_superuser(username='other-csv-admin', password='test-only')
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_template_response_and_access(self):
        from .importers.academic import COLUMNS, SAMPLE_ROWS
        url = reverse('academic_import_template', args=['csv'])
        response = self.client.get(url)
        data = rows(response)
        self.assertEqual(data[0], list(COLUMNS))
        self.assertEqual(len(data), len(SAMPLE_ROWS) + 1)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_export_access_remains_restricted(self):
        urls = [reverse('export_csv', args=[self.schedule.pk]), reverse('room_utilization_csv')]
        for role in (m.Role.STUDENT, m.Role.FACULTY):
            user = User.objects.create_user(username='csv-' + role, password='test-only')
            m.Profile.objects.update_or_create(user=user, defaults={'role': role})
            self.client.force_login(user)
            self.assertEqual(self.client.get(urls[0]).status_code, 404)
            self.assertEqual(self.client.get(urls[1]).status_code, 302)
            self.assertEqual(self.client.get(reverse('academic_import_template', args=['csv'])).status_code, 403)
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)


class CSVServiceSecurityTests(SimpleTestCase):
    def test_typed_numbers_and_text_numbers(self):
        stream = io.StringIO(newline='')
        writer(stream).writerow([0, -12, 1.5, Decimal('-2.50'), None, '-12', '+12', '123'])
        self.assertEqual(next(csv.reader(io.StringIO(stream.getvalue()))), ['0', '-12', '1.5', '-2.50', '', "'-12", "'+12", '123'])

    def test_benchmark_csv_output(self):
        from .benchmarks.runner import export_results
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / 'results.csv'
            export_results([{'name': value, 'score': -12.5} for value in ATTACKS + ORDINARY], path)
            with path.open(newline='', encoding='utf-8') as stream:
                data = list(csv.DictReader(stream))
            for row, value in zip(data, ATTACKS + ORDINARY):
                self.assertEqual(row['name'], "'" + value if value in ATTACKS else value)
                self.assertEqual(float(row['score']), -12.5)

    def test_workbook_normalization_csv_output(self):
        from .importers.full_tertiary import write_reports
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            write_reports(directory, {}, [{'sheet': 'Synthetic', 'row': 2, 'field': 'room',
                'original': value, 'normalized': value, 'reason': 'Review'} for value in ATTACKS + ORDINARY], [], [])
            with (Path(directory) / 'normalizations.csv').open(newline='', encoding='utf-8') as stream:
                data = list(csv.DictReader(stream))
            for row, value in zip(data, ATTACKS + ORDINARY):
                expected = "'" + value if value in ATTACKS else value
                self.assertEqual(row['original'], expected)
                self.assertEqual(row['normalized'], expected)

    def test_benchmark_summary_csv_output(self):
        from .benchmarks.runner import export_results
        from .benchmark_reports.report import generate_report
        from .test_benchmark_reports import fixture
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            source = Path(directory) / 'input.json'
            export_results([fixture()], source)
            target = Path(directory) / 'report'
            generate_report([source], target)
            with (target / 'summary.csv').open(newline='', encoding='utf-8') as stream:
                data = list(csv.DictReader(stream))
            self.assertEqual(data[0]['scenario'], 'small')
            self.assertEqual(float(data[0]['feasibility_percent']), 100)
