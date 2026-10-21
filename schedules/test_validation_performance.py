"""Deterministic isolated validation profiling; never uses the production database."""
from collections import Counter
from dataclasses import asdict
from datetime import date, time
import json
import os
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from django.db import connection
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from . import models as m
from .services import conflicts
from .test_support import validation_reference as reference


def workload(count, scenario):
    """Four adjacent one-hour meetings per faculty/section/room; independent groups."""
    prefix = f'{count}-{scenario}'
    department = m.Department.objects.create(code=prefix, name=prefix)
    program = m.Program.objects.create(code=prefix, name=prefix, department=department)
    year, _ = m.YearLevel.objects.get_or_create(level=1, defaults={'label': 'Year 1'})
    term = m.AcademicTerm.objects.create(name=prefix, school_year='2026-2027',
        starts_on=date(2026, 8, 1), ends_on=date(2026, 12, 1))
    schedule = m.Schedule.objects.create(term=term, name=prefix)
    for group in range(count // 4):
        faculty = m.Faculty.objects.create(department=department, full_name=f'Teacher {group}', employee_id=f'{prefix}-{group}')
        section = m.Section.objects.create(program=program, year_level=year, name=str(group), size=20)
        room = m.Room.objects.create(name=f'{prefix}-Room {group:03}', capacity=30, room_type='LECTURE')
        if scenario == 'invalid':
            for fields in ({'faculty': faculty}, {'room': room}):
                m.Availability.objects.create(**fields, day=0, start_time=time(7), end_time=time(18), kind='UNAVAILABLE')
        for index in range(4):
            subject = m.Subject.objects.create(department=department, code=f'{prefix}-{group}-{index}',
                title='Course', lecture_hours=1, required_room_type='LECTURE')
            if scenario == 'invalid':
                credential, _ = m.Credential.objects.get_or_create(name='Expired license')
                m.SubjectCredentialRequirement.objects.create(subject=subject, required_credential=credential)
            parent = m.Assignment.objects.create(term=term, subject=subject, faculty=faculty, section=section)
            meeting = m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE', duration_minutes=0)
            start = 8 if scenario == 'conflicts' else 8 + index
            schedule.entries.create(assignment=meeting, room=room, day=0, start_time=time(start), end_time=time(start+1))
        if scenario == 'invalid':
            m.FacultyCredential.objects.create(faculty=faculty, credential=credential,
                issued_on=date(2025, 1, 1), expires_on=date(2026, 9, 1))
    return schedule


def measured(schedule, legacy=False):
    # Fresh ORM instance prevents warm relation caches from biasing either run.
    schedule = m.Schedule.objects.get(pk=schedule.pk)
    function = reference.schedule_validation_issues if legacy else conflicts.schedule_validation_issues
    validator = reference.validate_entry if legacy else conflicts.validate_entry
    connection.queries_log.clear()  # Exclude fixture setup and avoid capture-buffer rollover.
    overlap_target = 'schedules.test_support.validation_reference.overlaps' if legacy else 'schedules.services.conflicts.overlaps'
    with (patch('schedules.services.conflicts.validate_entry', wraps=validator) as calls,
          patch(overlap_target, wraps=conflicts.overlaps) as comparisons):
        with CaptureQueriesContext(connection) as queries:
            start = perf_counter()
            result = function(schedule)
            duration = perf_counter() - start
    return result, {'queries': len(queries), 'seconds': round(duration, 6), 'validation_calls': calls.call_count,
        'overlap_comparisons': comparisons.call_count,
        'diagnostics': len(result), 'categories': dict(Counter(row['issue'].category for row in result)),
        'subject_selects': sum('FROM "schedules_subject"' in row['sql'] for row in queries)}


def serialized(issues):
    return [{'entry': row['entry'].pk if row['entry'] else None, 'message': row['message'],
             'issue': asdict(row['issue'])} for row in issues]


class ValidationProfilingTests(TestCase):
    def test_profile_and_ordered_equivalence(self):
        records = []
        for size in (8, 32, 96):
            for scenario in ('valid', 'conflicts', 'invalid'):
                with self.subTest(size=size, scenario=scenario):
                    schedule = workload(size, scenario)
                    old, before = measured(schedule, legacy=True)
                    new, after = measured(schedule)
                    self.assertEqual(serialized(new), serialized(old))
                    if scenario == 'valid':
                        self.assertEqual(new, [])
                    self.assertEqual(after['validation_calls'], size)
                    self.assertEqual(after['subject_selects'], 0)
                    self.assertLess(after['queries'], before['queries'])
                    # Up to two batch queries load default/overridden section availability.
                    self.assertLessEqual(after['queries'], (16 if scenario == 'invalid' else 11) * size + 6)
                    self.assertEqual(after['overlap_comparisons'], 3 * size if scenario == 'conflicts' else 0)
                    records.append(dict(meetings=size, scenario=scenario, before=before, after=after))
        output = os.environ.get('VALIDATION_PROFILE_OUTPUT')
        if output:
            Path(output).write_text(json.dumps(records, indent=2), encoding='utf-8')
        print('Validation profiles:', json.dumps(records))


class ValidationEquivalenceTests(TestCase):
    def setUp(self):
        self.schedule = workload(8, 'valid')
        self.entries = list(self.schedule.entries.select_related('assignment__faculty', 'assignment__subject',
            'assignment__section', 'room').order_by('pk'))

    def equivalent(self):
        before, _ = measured(self.schedule, legacy=True)
        after, _ = measured(self.schedule)
        self.assertEqual(serialized(after), serialized(before))
        return after

    def test_single_resource_conflicts_and_effective_overrides(self):
        left, right = self.entries[0], self.entries[4]  # Same time, otherwise independent.
        for field, value, category in [('faculty_override_id', left.assignment.faculty_id, 'FACULTY_CONFLICT'),
                                       ('section_override_id', left.assignment.section_id, 'SECTION_CONFLICT'),
                                       ('room_id', left.room_id, 'ROOM_CONFLICT')]:
            with self.subTest(field=field):
                old = getattr(right, field)
                self.schedule.entries.filter(pk=right.pk).update(**{field: value})
                issues = self.equivalent()
                self.assertEqual({row['issue'].category for row in issues}, {category})
                self.schedule.entries.filter(pk=right.pk).update(**{field: old})

    def test_overriding_away_from_parent_identity_and_workload(self):
        left, right = self.entries[:2]
        self.schedule.entries.filter(pk=right.pk).update(start_time=left.start_time, end_time=left.end_time,
            faculty_override=self.entries[4].assignment.faculty, section_override=self.entries[4].assignment.section,
            room=self.entries[4].room)
        m.Faculty.objects.filter(pk=self.entries[4].assignment.faculty_id).update(max_weekly_hours=1)
        issues = self.equivalent()
        self.assertIn('FACULTY_WORKLOAD', {row['issue'].category for row in issues})
        pairs = [row['issue'].meeting_ids for row in issues if row['issue'].category == 'FACULTY_CONFLICT']
        self.assertNotIn(tuple(sorted([left.assignment_id, right.assignment_id])), pairs)

    def test_capacity_room_type_and_inactive_room(self):
        m.Room.objects.filter(pk=self.entries[0].room_id).update(capacity=1, room_type='COMPUTER_LAB', is_active=False)
        categories = {row['issue'].category for row in self.equivalent()}
        self.assertTrue({'ROOM_CAPACITY', 'ROOM_TYPE', 'ROOM_UNAVAILABLE'} <= categories)

    def test_duration_seconds_hours_and_lab_requirements(self):
        self.schedule.entries.filter(pk=self.entries[0].pk).update(start_time=time(6), end_time=time(7, 0, 30))
        m.Subject.objects.filter(pk=self.entries[1].assignment.subject_id).update(lab_hours=1)
        issues = self.equivalent()
        self.assertIn('INVALID_DURATION', {row['issue'].category for row in issues})
        self.assertTrue(any('LABORATORY totals 0' in row['message'] for row in issues))

    def test_credential_overrides_and_later_changes_are_authoritative(self):
        from django.contrib.auth.models import User
        entry = self.entries[0]
        credential = m.Credential.objects.create(name='License')
        m.SubjectCredentialRequirement.objects.create(subject=entry.assignment.subject, required_credential=credential)
        self.assertIn('FACULTY_CREDENTIAL', {row['issue'].category for row in self.equivalent()})
        admin = User.objects.create_superuser('validation-admin')
        approval = m.CredentialOverride.objects.create(assignment=entry.assignment, subject=entry.assignment.subject,
            faculty=entry.assignment.faculty, admin_user=admin, reason='Approved', missing_credentials='License')
        self.assertEqual(self.equivalent(), [])
        approval.faculty = self.entries[4].assignment.faculty
        approval.save()
        self.assertIn('FACULTY_CREDENTIAL', {row['issue'].category for row in self.equivalent()})

    def test_availability_changes_and_adjacent_intervals(self):
        self.assertEqual(self.equivalent(), [])
        period = m.Availability.objects.create(room=self.entries[0].room, day=0,
            start_time=time(8), end_time=time(9), kind='UNAVAILABLE')
        issues = self.equivalent()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['entry'].pk, self.entries[0].pk)
        period.delete()
        self.assertEqual(self.equivalent(), [])

    def test_other_terms_do_not_influence_validation(self):
        workload(8, 'conflicts')
        self.assertEqual(self.equivalent(), [])

    def test_missing_and_repeated_meetings_keep_references(self):
        first = self.entries[0]
        first.delete()
        issues = self.equivalent()
        self.assertIn('UNSCHEDULED', {row['issue'].category for row in issues})
        m.TeachingAssignment.objects.create(assignment=self.entries[1].assignment.assignment,
            component='LECTURE', meeting_index=2, duration_minutes=30)
        self.assertGreater(len(self.equivalent()), len(issues))

    def test_unsaved_manual_candidate_matches_reference(self):
        entry = m.ScheduleEntry(schedule=self.schedule, assignment=self.entries[0].assignment,
            room=self.entries[0].room, day=0, start_time=time(8), end_time=time(9))
        observations = []
        for validator in (reference.validate_entry, conflicts.validate_entry):
            entry._generation_issue_sink = []
            with self.assertRaises(ValidationError) as caught:
                validator(entry)
            observations.append((caught.exception.messages, [asdict(issue) for issue in entry._generation_issue_sink]))
        self.assertEqual(*observations)
