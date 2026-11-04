from copy import deepcopy
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from . import models as m
from . import test_known_defects as fixtures
from . import test_shs_operations as operational_tests
from .services.shs_scheduling import pattern_snapshot
from .services.timetable_presentation import present_entries
from .test_publication_helpers import legacy_case, upgrade


class TertiaryPresentationTests(fixtures.SchedulingDefectFixture):
    def setUp(self):
        self.schedule = m.Schedule.objects.create(term=self.term, name='Synthetic draft')
        self.entry = self.schedule.entries.create(assignment=self.meetings[0], room=self.room,
            day=0, start_time=time(8), end_time=time(9))

    def test_recurring_tertiary_and_effective_identities(self):
        row = present_entries([self.entry])[0]
        self.assertEqual(row['recurrence'], dict(kind='WEEKLY', dates=None,
            starts_on='2026-08-01', ends_on='2026-12-01'))
        self.assertEqual(row['instructional_label'], 'Lecture')
        self.assertEqual(row['source'], 'LIVE')
        self.assertEqual(row['faculty']['id'], self.faculty.pk)
        self.assertEqual(row['primary_section']['label'], self.section.display_name)
        alternate = m.Faculty.objects.create(department=self.department, employee_id='ALT', full_name='Alternate')
        self.entry.faculty_override = alternate
        self.entry.save()
        self.assertEqual(present_entries([self.entry])[0]['faculty']['label'], 'Alternate')

    def test_only_authorized_input_ids_and_order_are_returned(self):
        other = self.schedule.entries.create(assignment=self.meetings[1], room=self.room,
            day=1, start_time=time(8), end_time=time(9))
        rows = present_entries([other, self.entry, other])
        self.assertEqual([r['entry_id'] for r in rows], [other.pk, self.entry.pk, other.pk])
        self.assertEqual(len(present_entries([self.entry])), 1)
        self.assertEqual(present_entries([]), [])
        with self.assertRaises(ValueError):
            present_entries([m.ScheduleEntry()])

    def test_explicit_pk_does_not_make_an_unsaved_entry_persisted(self):
        for pk in (self.entry.pk, self.entry.pk + 1000):
            with self.subTest(pk=pk), self.assertNumQueries(0):
                with self.assertRaisesMessage(ValueError, 'Supply persisted, already-authorized'):
                    present_entries([self.entry, m.ScheduleEntry(pk=pk)])
        self.assertEqual(present_entries([self.entry])[0]['entry_id'], self.entry.pk)

    @legacy_case
    def test_legacy_snapshot_never_infers_missing_level_from_live_term(self):
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()
        upgrade()
        row = present_entries([self.entry])[0]
        self.assertEqual(row['source'], 'FINALIZED_SNAPSHOT')
        self.assertIsNone(row['academic_context']['education_level'])
        self.assertEqual(row['recurrence'], dict(kind='WEEKLY', dates=None, starts_on=None, ends_on=None))
        self.assertEqual(row['subject']['code'], self.subject.code)
        self.assertEqual(row['instructional_label'], 'Lecture')

    def test_undocumented_or_shs_records_never_gain_legacy_weekly_fallback(self):
        from .services.timetable_presentation import _recurrence
        for level, operational in [('SHS', None), ('SHS', {}), (None, None)]:
            with self.subTest(level=level, operational=operational):
                self.assertEqual(_recurrence(level, operational, {}, 0, [])['kind'], 'UNKNOWN')

    @legacy_case
    def test_missing_snapshot_fails_without_live_fallback(self):
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
                present_entries([self.entry])

    def test_constant_query_count_and_read_only_projection(self):
        original = list(m.ScheduleEntry.objects.values())
        with CaptureQueriesContext(connection) as queries:
            rows = present_entries([self.entry] * 32)
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        rows[0]['subject']['title'] = 'Detached output'
        self.assertEqual(rows[1]['subject']['title'], self.subject.title)
        self.assertEqual(list(m.ScheduleEntry.objects.values()), original)


class SHSPresentationTests(TestCase):
    def setUp(self):
        operational_tests.OperationalInputTests.setUp(self)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Synthetic SHS')

    def entry(self, day, sequence=1, metadata=None):
        pattern = operational_tests.OperationalInputTests.pattern(self, sequence=sequence,
            recurrence='DATED', meeting_date=day, weekday=day.weekday())
        meeting = m.TeachingAssignment.objects.create(assignment=self.assignment,
            component='GENERAL', meeting_index=sequence, duration_minutes=60,
            required_room_type_override='LECTURE')
        m.SHSMeetingBinding.objects.create(meeting=meeting, pattern=pattern,
            data=pattern_snapshot(pattern) if metadata is None else metadata)
        return self.schedule.entries.create(assignment=meeting, room=self.room,
            day=day.weekday(), start_time=time(8), end_time=time(9))

    def test_dated_meetings_and_instructional_labels(self):
        first = self.entry(date(2026, 8, 3))
        second = self.entry(date(2026, 8, 10), 2)
        rows = present_entries([first, second])
        self.assertEqual([r['recurrence']['dates'] for r in rows], [('2026-08-03',), ('2026-08-10',)])
        self.assertTrue(all(r['recurrence']['kind'] == 'DATED' for r in rows))
        self.assertEqual(rows[0]['instructional_label'], self.component.instruction)
        self.assertEqual(rows[0]['academic_context']['grade_level'], 11)
        self.assertEqual(rows[0]['academic_context']['academic_period'], 'Period 1')

    @legacy_case
    def test_combined_sections_and_frozen_history(self):
        self.config.combined_class_reference = 'Synthetic approval'
        self.config.save()
        extra = m.Section.objects.create(program=self.program, year_level=self.year,
            name='B', size=20, cohort=self.section.cohort)
        m.SHSSectionParticipation.objects.create(configuration=self.config, section=extra)
        entry = self.entry(date(2026, 8, 3))
        original = deepcopy(entry.assignment.shs_binding.data)
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()
        upgrade()
        snapshot = deepcopy(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data)
        original_read = m.Section.from_db.__func__
        def changed_label(cls, db, fields, values):
            section = original_read(cls, db, fields, values)
            if section.pk == extra.pk:
                section.name = 'CHANGED'
            return section
        with patch.object(m.Section, 'from_db', classmethod(changed_label)):
            self.assertEqual(m.Section.objects.get(pk=extra.pk).name, 'CHANGED')
            row = present_entries([entry])[0]
        self.assertEqual(row['primary_section']['id'], self.section.pk)
        self.assertEqual([s['id'] for s in row['participating_sections']], [self.section.pk, extra.pk])
        self.assertEqual(row['participating_sections'][1]['label'], original['sections'][1]['name'])
        self.assertTrue(row['participation_complete'])
        self.assertEqual(row['source'], 'FINALIZED_SNAPSHOT')
        self.assertIsNone(row['academic_context']['academic_period'])
        self.assertIsNone(row['academic_context']['grade_level'])
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data, snapshot)
        self.assertEqual(m.SHSMeetingBinding.objects.get(meeting=entry.assignment).data, original)

    def test_missing_binding_does_not_imply_weekly_recurrence(self):
        entry = self.entry(date(2026, 8, 3))
        m.SHSMeetingBinding.objects.filter(meeting=entry.assignment).delete()
        row = present_entries([entry])[0]
        self.assertEqual(row['recurrence']['kind'], 'UNKNOWN')
        self.assertIsNone(row['instructional_label'])
        self.assertFalse(row['participation_complete'])

    def test_incomplete_binding_reports_unknown_dates(self):
        entry = self.entry(date(2026, 8, 3), metadata={'instruction': 'Synthetic activity'})
        row = present_entries([entry])[0]
        self.assertEqual(row['recurrence']['kind'], 'UNKNOWN')
        self.assertTrue(row['warnings'])

    @legacy_case
    def test_malformed_binding_shapes_are_unavailable_without_mutation(self):
        entry = self.entry(date(2026, 8, 3))
        original = deepcopy(entry.assignment.shs_binding.data)
        for finalized in (False, True):
            if finalized:
                self.schedule.status = 'PUBLISHED'
                self.schedule.save()
                upgrade()
            for malformed in (None, [], ['unexpected'], 'unexpected', 42, 1.5, True, False):
                with self.subTest(finalized=finalized, shape=malformed):
                    # Inject malformed deserialized JSON, including JSON null, without
                    # changing stored immutable bindings or bypassing database guards.
                    with patch('schedules.services.timetable_presentation.binding',
                               return_value=SimpleNamespace(data=malformed)):
                        row = present_entries([entry])[0]
                    self.assertEqual(row['academic_context']['education_level'], 'SHS')
                    self.assertEqual(row['recurrence']['kind'], 'UNKNOWN')
                    self.assertIsNone(row['recurrence']['dates'])
                    self.assertIsNone(row['instructional_label'])
                    self.assertFalse(row['participation_complete'])
                    self.assertEqual(row['participating_sections'], (row['primary_section'],))
                    self.assertIn('SHS binding metadata is malformed and unavailable.', row['warnings'])
                    if finalized:
                        self.assertIsNone(row['academic_context']['cohort_id'])
                        self.assertIsNone(row['academic_context']['academic_period'])
        self.assertEqual(m.SHSMeetingBinding.objects.get(meeting=entry.assignment).data, original)

    @legacy_case
    def test_batch_query_count_and_no_writes(self):
        entries = [self.entry(date(2026, 8, 3)), self.entry(date(2026, 8, 10), 2)]
        self.schedule.status = 'PUBLISHED'
        self.schedule.save()
        upgrade()
        with CaptureQueriesContext(connection) as queries:
            rows = present_entries(entries * 16)
        self.assertEqual(len(rows), 32)
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))


class DistinctEntryQueryTests(fixtures.SchedulingDefectFixture):
    def setUp(self):
        self.shs_program = m.Program.objects.create(department=self.department,
            code='SHS', name='Synthetic SHS', education_level='SHS')
        self.grade = m.YearLevel.objects.create(level=11, label='Grade 11')
        self.shs_term = m.AcademicTerm.objects.create(name='SHS', school_year='2026-2027',
            starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 1), education_level='SHS')
        self.shs_schedule = m.Schedule.objects.create(term=self.shs_term, name='SHS draft')
        self.tertiary_schedule = m.Schedule.objects.create(term=self.term, name='Tertiary draft')
        self.tertiary_entries = [self.tertiary_schedule.entries.create(assignment=meeting,
            room=self.room, day=0, start_time=time(8), end_time=time(9)) for meeting in self.meetings]

    def section_with_pathway(self, code):
        version = m.CurriculumVersion.objects.create(family=code, revision='1')
        pathway = m.AcademicPathway.objects.create(curriculum_version=version,
            code=code, name=code, kind='STRAND')
        cohort = m.Cohort.objects.create(curriculum_version=version, pathway=pathway,
            school_year='2026-2027', grade_level=11)
        return m.Section.objects.create(program=self.shs_program, year_level=self.grade,
            cohort=cohort, name=code, size=20)

    def distinct_entries(self, count, overrides):
        entries, labels = [], []
        for index in range(count):
            code = f'{int(overrides)}-{index}'
            section = self.section_with_pathway('P' + code)
            override = self.section_with_pathway('O' + code) if overrides else None
            faculty = m.Faculty.objects.create(department=self.department, employee_id='F' + code,
                full_name='Synthetic ' + code)
            room = m.Room.objects.create(name='Room ' + code, room_type='LECTURE', capacity=30)
            parent = m.Assignment.objects.create(term=self.shs_term, subject=self.subject,
                faculty=faculty, section=section)
            meeting = m.TeachingAssignment.objects.create(assignment=parent, component='GENERAL',
                duration_minutes=60, meeting_index=1)
            entries.append(self.shs_schedule.entries.create(assignment=meeting, room=room,
                section_override=override, day=0, start_time=time(8), end_time=time(9)))
            labels.append(str((override or section).cohort.pathway))
        return entries, labels

    def test_distinct_primary_and_override_pathways_and_mixed_batches(self):
        for overrides in (False, True):
            entries, labels = self.distinct_entries(16, overrides)
            for count in (2, 16):
                for mixed in (False, True):
                    batch = entries[:count] + (self.tertiary_entries if mixed else [])
                    with self.subTest(overrides=overrides, count=count, mixed=mixed):
                        with CaptureQueriesContext(connection) as queries:
                            rows = present_entries(batch)
                        self.assertEqual(len(queries), 2)
                        self.assertEqual([r['entry_id'] for r in rows], [e.pk for e in batch])
                        self.assertEqual([r['academic_context']['pathway'] for r in rows[:count]], labels[:count])
                        self.assertEqual(len({r['faculty']['id'] for r in rows[:count]}), count)
                        self.assertEqual(len({r['room']['id'] for r in rows[:count]}), count)
                        if mixed:
                            self.assertTrue(all(r['recurrence']['kind'] == 'WEEKLY' for r in rows[count:]))
                        print(f'Presentation queries: override={overrides}, SHS={count}, mixed={mixed}, queries={len(queries)}')
            ordered = [entries[-1], self.tertiary_entries[0], entries[0], entries[-1]]
            self.assertEqual([r['entry_id'] for r in present_entries(ordered)], [e.pk for e in ordered])

    def test_query_assertion_detects_original_missing_pathway_join(self):
        from django.db.models.query import QuerySet
        entries, _ = self.distinct_entries(4, False)
        original = QuerySet.select_related

        def original_paths(queryset, *fields):
            return original(queryset, *(field.replace('__cohort__pathway__curriculum_version',
                '__cohort__pathway') for field in fields))

        with self.assertNumQueries(2):
            corrected = present_entries(entries)
        # Simulate the original missing join in memory; do not edit production code.
        with patch.object(QuerySet, 'select_related', original_paths):
            with CaptureQueriesContext(connection) as queries:
                previous = present_entries(entries)
        self.assertEqual(previous, corrected)
        self.assertEqual(len(queries), 2 + len(entries))
        print(f'Original pathway join simulation: {len(entries)} distinct entries, {len(queries)} queries; corrected: 2.')
