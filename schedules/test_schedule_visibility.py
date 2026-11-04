"""Participation authorization, exercised only against Django test databases."""
from copy import deepcopy
from datetime import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import models as m
from . import test_shs_operations as fixtures
from .services.shs_scheduling import pattern_snapshot
from .services.schedule_visibility import student_entries, _rows
from .services.concerns import authorized_entries
from .views import entries_visible_to_user
from .test_publication_helpers import historical_visibility, upgrade


@historical_visibility
class ParticipationVisibilityTests(TestCase):
    def setUp(self):
        fixtures.OperationalInputTests.setUp(self)
        self.config.combined_class_reference = 'Synthetic approval'
        self.config.save()
        self.extra = self.section_for('B')
        self.other = self.section_for('C')
        m.SHSSectionParticipation.objects.create(configuration=self.config, section=self.extra)
        self.primary_user = self.student('primary', self.section)
        self.extra_user = self.student('extra', self.extra)
        self.other_user = self.student('other', self.other)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Combined')
        self.entry = self.add_entry()
        if self._testMethodName not in ('test_distinct_batch_query_count_and_mixed_visibility', 'test_mixed_schedule_exports_exclude_unrelated_rows'):
            self.publish()

    def section_for(self, name):
        return m.Section.objects.create(program=self.program, year_level=self.year,
            name=name, size=10, cohort=self.section.cohort)

    def student(self, name, section):
        user = User.objects.create_user(name)
        m.Profile.objects.create(user=user, role='STUDENT')
        m.Student.objects.create(user=user, section=section, student_number=str(user.pk), full_name=name)
        return user

    def add_entry(self, sequence=1, metadata=None, section=None):
        pattern = fixtures.OperationalInputTests.pattern(self, sequence=sequence)
        meeting = m.TeachingAssignment.objects.create(assignment=self.assignment,
            component='GENERAL', meeting_index=sequence, duration_minutes=60,
            required_room_type_override='LECTURE')
        data = pattern_snapshot(pattern) if metadata is None else metadata
        m.SHSMeetingBinding.objects.create(meeting=meeting, pattern=pattern, data=data)
        return self.schedule.entries.create(assignment=meeting, room=self.room,
            section_override=section, day=0, start_time=time(8), end_time=time(9))

    def publish(self):
        # Trigger-captured history; this suite tests visibility, not GA feasibility.
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()

    def ids(self, user):
        return list(entries_visible_to_user(m.ScheduleEntry.objects.order_by('pk'), user).values_list('pk', flat=True))

    def test_participants_missing_link_and_no_duplicates(self):
        upgrade()
        self.assertEqual(self.ids(self.primary_user), [self.entry.pk])
        self.assertEqual(self.ids(self.extra_user), [self.entry.pk])
        self.assertEqual(self.ids(self.other_user), [])
        m.Student.objects.filter(user=self.extra_user).delete()
        self.assertEqual(self.ids(self.extra_user), [])

    def test_frozen_membership_survives_live_participation_changes(self):
        upgrade()
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError), transaction.atomic():
            m.SHSSectionParticipation.objects.filter(configuration=self.config).delete()
        # Authorization must not consult mutable participation. Intercept only
        # reads of this model; frozen bindings, snapshots and all writes stay real.
        from django.db.models.query import QuerySet
        original = QuerySet._fetch_all
        replacement = m.SHSSectionParticipation(configuration=self.config, section=self.other)
        live_query = self.config.additional_sections.all().query.sql_with_params()
        def live_participants(qs):
            if (qs.model is m.SHSSectionParticipation
                    and qs.query.sql_with_params() == live_query):
                qs._result_cache = [replacement]
                return
            return original(qs)
        with patch.object(QuerySet, '_fetch_all', live_participants):
            self.assertEqual(list(self.config.additional_sections.all()), [replacement])
            self.assertEqual(self.ids(self.extra_user), [self.entry.pk])
            self.assertEqual(self.ids(self.other_user), [])

    def test_dashboard_browse_filters_and_concerns(self):
        upgrade()
        self.client.force_login(self.extra_user)
        for route in ('dashboard', 'browse_schedules'):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertEqual([e.pk for e in response.context['entries']], [self.entry.pk])
        response = self.client.get(reverse('browse_schedules'), {'section': self.extra.pk})
        self.assertEqual([e.pk for e in response.context['entries']], [self.entry.pk])
        self.assertEqual(list(response.context['form'].fields['section'].queryset.values_list('pk', flat=True)), [self.extra.pk])
        response = self.client.get(reverse('browse_schedules'), {'section': self.other.pk})
        self.assertEqual(list(response.context['entries']), [])
        self.assertEqual(list(authorized_entries(self.extra_user).values_list('pk', flat=True)), [self.entry.pk])
        self.assertEqual(self.client.get(reverse('concern_create')).status_code, 200)

    def test_direct_detail_and_all_exports(self):
        upgrade()
        for user, status in ((self.primary_user, 200), (self.extra_user, 200), (self.other_user, 404)):
            self.client.force_login(user)
            for route in ('schedule_detail', 'export_csv', 'export_pdf', 'export_xlsx'):
                with self.subTest(user=user.username, route=route):
                    response = self.client.get(reverse(route, args=[self.schedule.pk]), {'section': m.Student.objects.get(user=user).section_id})
                    self.assertEqual(response.status_code, status)
                    if status == 200:
                        self.assertTrue(response.content)
                        if route == 'schedule_detail':
                            self.assertEqual([e.pk for e in response.context['entries']], [self.entry.pk])
                        elif route == 'export_csv':
                            self.assertIn(self.subject.code.encode(), response.content)
                        elif route == 'export_xlsx':
                            from io import BytesIO
                            from openpyxl import load_workbook
                            book = load_workbook(BytesIO(response.content))
                            self.assertIn(self.subject.code, [c.value for row in book['Schedule Details'] for c in row])
        self.client.force_login(self.extra_user)
        response = self.client.get(reverse('export_csv', args=[self.schedule.pk]), {'section': self.other.pk})
        self.assertNotIn(self.subject.code.encode(), response.content)

    def test_draft_and_archive_denied_including_direct_urls(self):
        draft = m.Schedule.objects.create(term=self.term, name='Draft')
        draft.entries.create(assignment=self.entry.assignment, room=self.room, day=0, start_time=time(8), end_time=time(9))
        self.assertEqual(self.ids(self.extra_user), [self.entry.pk])
        from .protection import archive_transition
        self.schedule.status = 'ARCHIVED'
        with archive_transition():
            self.schedule.save(update_fields=['status'])
        upgrade()
        self.assertEqual(self.ids(self.extra_user), [])
        self.client.force_login(self.extra_user)
        for schedule in (draft, self.schedule):
            for route in ('schedule_detail', 'export_csv', 'export_pdf', 'export_xlsx'):
                self.assertEqual(self.client.get(reverse(route, args=[schedule.pk])).status_code, 404)

    def test_faculty_and_admin_policy_preserved(self):
        upgrade()
        faculty_user = User.objects.create_user('teacher')
        m.Profile.objects.create(user=faculty_user, role='FACULTY')
        self.faculty.user = faculty_user
        self.faculty.save()
        admin = User.objects.create_superuser('administrator')
        self.assertEqual(self.ids(faculty_user), [self.entry.pk])
        self.assertEqual(self.ids(admin), [self.entry.pk])

    def test_missing_and_malformed_evidence_fail_closed(self):
        upgrade()
        # Patch read results only: immutable bindings and snapshots are never edited.
        snapshot = m.ScheduleSnapshot.objects.get(schedule=self.schedule)
        actual = deepcopy(snapshot.data)
        rows = [(self.entry.pk, self.schedule.pk, self.entry.assignment_id, self.term.pk, None)]
        data = deepcopy(self.entry.assignment.shs_binding.data)
        malformed = [None, [], 'text', 1, {}, dict(data, sections=[]),
            dict(data, sections=[{'id': str(self.section.pk)}, {'id': self.extra.pk}]),
            dict(data, sections=[{'id': True}, {'id': self.extra.pk}]),
            dict(data, sections=[{'id': self.section.pk}, {'id': self.extra.pk}, {'id': self.extra.pk}]),
            dict(data, sections=[{'id': self.extra.pk}, {'id': self.section.pk}]),
            dict(data, term_id=str(self.term.pk)), dict(data, combined_reference=''),
            dict(data, subject_id=self.subject.pk + 100), dict(data, component_id=True)]
        from django.db.models.query import QuerySet
        original = QuerySet.values_list
        for value in malformed:
            def values_list(qs, *fields, **kwargs):
                if qs.model is m.ScheduleEntry and fields == ('pk', 'schedule_id', 'assignment_id', 'schedule__term_id', 'assignment__shs_binding__data'):
                    return [(*rows[0][:4], value)]
                return original(qs, *fields, **kwargs)
            with self.subTest(metadata=value), patch.object(QuerySet, 'values_list', values_list):
                self.assertEqual(self.ids(self.extra_user), [])
                self.assertEqual(self.ids(self.primary_user), [self.entry.pk])
        for value in (None, [], {}, dict(actual, entries=[])):
            self.assertEqual(_rows(value, self.schedule.pk), {})
        with patch('schedules.services.schedule_visibility._rows', return_value={}):
            self.assertEqual(self.ids(self.primary_user), [])
            self.assertEqual(self.ids(self.extra_user), [])
        bad = deepcopy(actual)
        bad['entries'][0]['meeting_id'] += 1000
        with patch('schedules.services.schedule_visibility._rows', return_value={self.entry.pk: bad['entries'][0]}):
            self.assertEqual(self.ids(self.extra_user), [])

    def test_mixed_schedule_exports_exclude_unrelated_rows(self):
        unrelated = self.add_entry(2, section=self.other)
        self.publish()
        upgrade()
        self.client.force_login(self.extra_user)
        response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]))
        self.assertEqual([e.pk for e in response.context['entries']], [self.entry.pk])
        for field, value in (('section', self.extra.pk), ('program', self.program.pk),
                             ('year_level', self.year.pk), ('department', self.department.pk)):
            response = self.client.get(reverse('schedule_detail', args=[self.schedule.pk]), {field: value})
            self.assertEqual([e.pk for e in response.context['entries']], [self.entry.pk])
        response = self.client.get(reverse('export_csv', args=[self.schedule.pk]))
        import csv
        from io import StringIO, BytesIO
        csv_rows = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(len(csv_rows), 3)  # Two frozen dates, one authorized combined meeting.
        self.assertEqual({row[4] for row in csv_rows[1:]}, {str(self.section)})
        self.assertNotIn(str(self.other), {row[4] for row in csv_rows[1:]})
        from openpyxl import load_workbook
        response = self.client.get(reverse('export_xlsx', args=[self.schedule.pk]))
        book = load_workbook(BytesIO(response.content))
        section_cells = [c.value for row in book['Schedule Details'] for c in row]
        self.assertIn(str(self.section), section_cells)
        self.assertNotIn(str(self.other), section_cells)
        with patch('schedules.views.write_table_pdf') as writer:
            self.assertEqual(self.client.get(reverse('export_pdf', args=[self.schedule.pk])).status_code, 200)
            rows = list(writer.call_args.args[4])
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(str(self.section) in row[2] and str(self.extra) in row[2] for row in rows))
            self.assertTrue(all(str(self.other) not in row[2] for row in rows))
        self.assertEqual(list(authorized_entries(self.extra_user).values_list('pk', flat=True)), [self.entry.pk])

    def test_distinct_batch_query_count_and_mixed_visibility(self):
        # Distinct persisted meetings and sections, not repeated Python objects.
        self.schedule = m.Schedule.objects.create(term=self.term, name='Larger batch')
        entries = []
        for index in range(2, 14):
            entries.append(self.add_entry(index))
        # One unrelated frozen primary, with deliberately inconsistent binding:
        # neither primary matching nor additional matching may leak this row.
        unrelated = self.add_entry(14, section=self.other)
        # A legacy recurring entry has no SHS binding but valid primary evidence.
        legacy = m.TeachingAssignment.objects.create(assignment=self.assignment,
            component='LECTURE', meeting_index=15, duration_minutes=60)
        legacy_entry = self.schedule.entries.create(assignment=legacy, room=self.room,
            section_override=self.extra, day=1, start_time=time(8), end_time=time(9))
        self.publish()
        tertiary_program = m.Program.objects.create(department=self.department, code='TER', name='Tertiary')
        tertiary_year = m.YearLevel.objects.create(level=1, label='Year 1')
        tertiary_section = m.Section.objects.create(program=tertiary_program, year_level=tertiary_year, name='T', size=10)
        tertiary_term = m.AcademicTerm.objects.create(name='Tertiary term', school_year='2026-2027', starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        tertiary_assignment = m.Assignment.objects.create(term=tertiary_term, subject=self.subject, faculty=self.faculty, section=tertiary_section)
        tertiary_meeting = m.TeachingAssignment.objects.create(assignment=tertiary_assignment, component='LECTURE', duration_minutes=60)
        tertiary_schedule = m.Schedule.objects.create(term=tertiary_term, name='Tertiary schedule')
        tertiary_entry = tertiary_schedule.entries.create(assignment=tertiary_meeting, room=self.room, day=1, start_time=time(8), end_time=time(9))
        tertiary_schedule.status = 'PUBLISHED'
        tertiary_schedule.save()
        upgrade()
        counts = []
        for size in (1, 12):
            selected = [e.pk for e in entries[:size]] + [unrelated.pk, legacy_entry.pk, tertiary_entry.pk]
            with CaptureQueriesContext(connection) as queries:
                result = list(student_entries(m.ScheduleEntry.objects.filter(pk__in=selected).order_by('-pk'), self.extra.pk).values_list('pk', flat=True))
            self.assertEqual(result, sorted([e.pk for e in entries[:size]] + [legacy_entry.pk], reverse=True))
            counts.append(len(queries))
        self.assertEqual(counts, [3, 3])
        print('Participation authorization queries (4/15 distinct mixed entries):', counts)
