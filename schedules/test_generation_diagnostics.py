"""M5 explicit references, atomic diagnostics, privacy and lease-based recovery."""
from datetime import time, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models.functions import Now

from . import models as m
from .services.diagnostics import Diagnostic, GenerationFailure
from .services.generation_issues import record_issues, fail_run, recover_stale_runs, unexpected_diagnostic
from .services.generation_lock import acquire
from .services.ga import GeneticScheduler, Gene
from .services.conflicts import individual_entry_errors, schedule_validation_messages
from .test_known_defects import SchedulingDefectFixture


class StructuredGenerationTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='diagnostic-admin', password='test')
        self.client.force_login(self.admin)
        self.settings = m.GASettings.objects.create(name='Diagnostics', population_size=2, generations=0, elitism=1)

    def run_record(self, owner=None):
        return m.GenerationRun.objects.create(term=self.term, requested_by=self.admin,
            ga_settings=self.settings, requested_name='Diagnostics', lease_owner=owner)

    def ga(self):
        return GeneticScheduler(self.term, self.settings, seed=8)

    def issue(self, category='INVALID_DATA', message='Review meeting', meetings=None, **kwargs):
        return Diagnostic.for_meetings(category, message, self.meetings if meetings is None else meetings, **kwargs)

    def test_explicit_ids_override_misleading_message_numbers_and_course(self):
        run = self.run_record()
        diagnostic = self.issue('INVALID_DURATION', 'Meeting 9999 REG101 / section 888 requires 120 minutes',
                                [self.meetings[1]], severity='WARNING', details={'minutes': 120})
        row = record_issues(run, [diagnostic])[0]
        self.assertEqual(row.assignment_id, self.meetings[1].pk)
        self.assertEqual(row.details['meeting_ids'], [self.meetings[1].pk])
        self.assertEqual(row.details['assignment_ids'], [self.parent.pk])
        self.assertEqual((row.category, row.severity), ('INVALID_DURATION', 'WARNING'))
        self.assertEqual(row.details['constraint']['minutes'], 120)

    def test_multi_meeting_conflicts_deduplicate(self):
        run = self.run_record()
        issue = self.issue('FACULTY_CONFLICT', 'First direction')
        reverse = self.issue('FACULTY_CONFLICT', 'Reverse direction', list(reversed(self.meetings)))
        self.assertEqual(len(record_issues(run, [issue, issue, reverse])), 1)
        self.assertEqual(record_issues(run, [issue]), [])
        row = run.issues.get()
        self.assertEqual(set(row.details['meeting_ids']), {m.pk for m in self.meetings})

    def test_global_error_has_no_invented_reference(self):
        row = record_issues(self.run_record(), [Diagnostic('NO_SLOT', 'REG101 meeting 1 unavailable')])[0]
        self.assertIsNone(row.assignment_id)
        self.assertEqual(row.details['meeting_ids'], [])
        self.assertEqual(row.details['assignment_ids'], [])

    def test_no_feasible_domain_retains_specific_meeting(self):
        m.Availability.objects.create(room=self.room, kind='AVAILABLE', day=0, start_time=time(8), end_time=time(8, 30))
        with self.assertRaises(GenerationFailure) as caught:
            self.ga().generate()
        issue = caught.exception.issues[0]
        self.assertEqual(issue.category, 'NO_SLOT')
        self.assertEqual(issue.meeting_ids, (self.meetings[0].pk,))
        self.assertEqual(issue.assignment_ids, (self.parent.pk,))
        self.assertIn('reasons', issue.details)

    def test_preflight_capacity_and_qualification_reference_each_meeting(self):
        ga = self.ga()
        for a in ga.assignments:
            ga.valid_rooms_by_assignment[a.pk] = []
            ga.qualification_cache[a.pk] = False
        with self.assertRaises(GenerationFailure) as caught:
            ga.generate()
        issues = caught.exception.issues
        self.assertEqual({i.category for i in issues}, {'ROOM_CAPACITY', 'FACULTY_CREDENTIAL'})
        self.assertEqual({i.meeting_ids for i in issues}, {(a.pk,) for a in self.meetings})

    def test_shared_validation_emits_availability_type_capacity_duration(self):
        wrong = m.Room.objects.create(name='Tiny Lab', capacity=1, room_type='COMPUTER_LAB')
        m.Availability.objects.create(faculty=self.faculty, kind='UNAVAILABLE', day=0, start_time=time(8), end_time=time(10))
        m.Availability.objects.create(room=wrong, kind='UNAVAILABLE', day=0, start_time=time(8), end_time=time(10))
        entry = m.ScheduleEntry(schedule=m.Schedule(term=self.term), assignment=self.meetings[0],
            room=wrong, day=0, start_time=time(8), end_time=time(8, 30))
        sink = []
        errors = individual_entry_errors(entry, eligible=False, issue_sink=sink)
        self.assertTrue(errors)
        self.assertEqual({i.category for i in sink}, {'INVALID_DURATION', 'ROOM_CAPACITY', 'ROOM_TYPE',
            'FACULTY_UNAVAILABLE', 'ROOM_UNAVAILABLE', 'FACULTY_CREDENTIAL'})
        self.assertTrue(all(i.meeting_ids == (self.meetings[0].pk,) for i in sink))

    def test_component_issue_from_existing_validator(self):
        entry = m.ScheduleEntry(schedule=m.Schedule(term=self.term), assignment=self.meetings[0],
            component_override='LABORATORY', room=self.room, day=0, start_time=time(8), end_time=time(9))
        sink = []
        individual_entry_errors(entry, issue_sink=sink)
        self.assertTrue(any(i.category == 'INVALID_DATA' and i.details.get('constraint') == 'meeting_requirements' for i in sink))

    def test_final_validation_has_explicit_unscheduled_and_parent_totals(self):
        schedule = m.Schedule.objects.create(term=self.term, name='Empty')
        messages = schedule_validation_messages(schedule)
        self.assertTrue(messages)
        missing = [i for i in messages.issues if i.category == 'UNSCHEDULED']
        self.assertEqual({i.meeting_ids for i in missing}, {(a.pk,) for a in self.meetings})
        totals = [i for i in messages.issues if i.details.get('constraint') == 'component_totals']
        self.assertTrue(totals)
        self.assertEqual(totals[0].assignment_ids, (self.parent.pk,))

    def test_final_candidate_reports_three_resource_conflicts(self):
        ga = self.ga()
        genes = [Gene(a.pk, self.room.pk, 0, time(8), time(9)) for a in self.meetings]
        issues = ga.candidate_diagnostics(genes, ga.fitness(genes))
        self.assertEqual({i.category for i in issues}, {'NO_SLOT', 'FACULTY_CONFLICT', 'ROOM_CONFLICT', 'SECTION_CONFLICT'})
        self.assertTrue(all(i.meeting_ids == tuple(a.pk for a in self.meetings) for i in issues[1:]))

    def test_final_validation_failure_rolls_back_schedule_but_records_diagnostics(self):
        actual = schedule_validation_messages
        def invalidate(schedule):
            schedule.entries.all().delete()
            return actual(schedule)
        with patch('schedules.services.conflicts.schedule_validation_messages', side_effect=invalidate):
            response = self.client.post('/schedules/generate/', {'term': self.term.pk, 'settings': self.settings.pk, 'name': 'Invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(m.Schedule.objects.exists())
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.issues.filter(category='UNSCHEDULED').count(), 2)
        self.assertTrue(all(row.assignment_id in {a.pk for a in self.meetings} for row in run.issues.filter(category='UNSCHEDULED')))

    def test_deleted_and_unknown_meetings_keep_historical_ids(self):
        run = self.run_record()
        pk = self.meetings[0].pk
        diagnostic = self.issue(meetings=[self.meetings[0]])
        self.meetings[0].delete()
        row = record_issues(run, [diagnostic])[0]
        self.assertIsNone(row.assignment_id)
        self.assertEqual(row.details['meeting_ids'], [pk])
        page = self.client.get(f'/schedules/error-log/{row.pk}/')
        self.assertContains(page, f'Meeting {pk} is no longer available')

    def test_multiple_meetings_display_and_correction_links(self):
        row = record_issues(self.run_record(), [self.issue('FACULTY_CONFLICT')])[0]
        page = self.client.get(f'/schedules/error-log/{row.pk}/')
        self.assertContains(page, 'Meeting 1')
        self.assertContains(page, 'Meeting 2')
        self.assertContains(page, 'Review assignment', count=2)

    def test_failure_status_and_issues_are_atomic(self):
        run = self.run_record()
        real = m.GenerationIssue.objects.create
        count = [0]
        def fail(**kwargs):
            count[0] += 1
            if count[0] == 2:
                raise IntegrityError('forced insertion failure')
            return real(**kwargs)
        with patch('schedules.services.generation_issues.GenerationIssue.objects.create', side_effect=fail):
            with self.assertRaises(IntegrityError):
                fail_run(run, [self.issue(message='One'), self.issue(message='Two')])
        run.refresh_from_db()
        self.assertEqual(run.status, 'RUNNING')
        self.assertFalse(run.issues.exists())

    def test_retry_does_not_duplicate_or_downgrade_success(self):
        run = self.run_record()
        self.assertTrue(fail_run(run, [self.issue()]))
        self.assertFalse(fail_run(run, [self.issue()]))
        self.assertEqual(run.issues.count(), 1)
        succeeded = self.run_record()
        m.GenerationRun.objects.filter(pk=succeeded.pk).update(status='SUCCEEDED')
        self.assertFalse(fail_run(succeeded, [self.issue()]))
        self.assertFalse(succeeded.issues.exists())

    def test_safe_unexpected_failure_and_unstructured_value_error(self):
        for exception in (RuntimeError('private-password'), ValueError('REG101 meeting 999 private-password')):
            with patch('schedules.views.GeneticScheduler.generate', side_effect=exception):
                self.client.post('/schedules/generate/', {'term': self.term.pk, 'settings': self.settings.pk, 'name': 'Failure'})
        self.assertEqual(m.GenerationRun.objects.filter(status='FAILED').count(), 2)
        for row in m.GenerationIssue.objects.all():
            self.assertNotIn('private-password', row.reason)
            self.assertIsNone(row.assignment_id)

    def test_student_and_faculty_cannot_read_details_or_trigger_recovery(self):
        run = self.run_record()
        row = record_issues(run, [self.issue(message='Private diagnostic')])[0]
        for role in ('STUDENT', 'FACULTY'):
            user = User.objects.create_user(username=role)
            m.Profile.objects.create(user=user, role=role)
            self.client.force_login(user)
            for url in ('/schedules/error-log/', f'/schedules/error-log/{row.pk}/'):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertNotIn(b'Private diagnostic', response.content)
            run.refresh_from_db()
            self.assertEqual(run.status, 'RUNNING')

    def test_recovery_preserves_active_matching_owner_and_recovers_expired(self):
        lease = acquire(self.term.pk)
        run = self.run_record(lease.owner)
        self.assertEqual(recover_stale_runs(), 0)
        m.GenerationLease.objects.filter(term=self.term).update(expires_at=Now() - timedelta(seconds=1))
        self.assertEqual(recover_stale_runs(), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.issues.get().details['constraint']['constraint'], 'stale_generation')
        self.assertEqual(recover_stale_runs(), 0)
        lease.release()

    def test_recovery_of_replaced_owner_does_not_touch_successor(self):
        lease = acquire(self.term.pk)
        old = self.run_record(uuid4())
        current = self.run_record(lease.owner)
        self.assertEqual(recover_stale_runs(), 1)
        old.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual((old.status, current.status), ('FAILED', 'RUNNING'))
        self.assertEqual(m.GenerationLease.objects.get(term=self.term).owner, lease.owner)
        lease.release()

    def test_legacy_running_records_are_conservative_and_history_stays_readable(self):
        legacy = self.run_record()
        row = m.GenerationIssue.objects.create(run=legacy, assignment=self.meetings[0], category='OTHER',
            reason='Legacy detail', short_description='Legacy', suggested_action='Review')
        lease = acquire(self.term.pk)
        self.assertEqual(recover_stale_runs(), 0)
        self.assertContains(self.client.get(f'/schedules/error-log/{row.pk}/'), 'Legacy detail')
        lease.release()
        self.assertEqual(recover_stale_runs(), 1)
        row.refresh_from_db()
        self.assertEqual(row.details, {})
        self.assertEqual(row.reason, 'Legacy detail')

    def test_admin_history_visit_recovers_stale_run_once(self):
        run = self.run_record(uuid4())
        self.assertEqual(self.client.get('/schedules/error-log/').status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, 'FAILED')
        self.client.get('/schedules/error-log/')
        self.assertEqual(run.issues.count(), 1)

    def test_multiple_parent_assignments_keep_explicit_ids(self):
        section = m.Section.objects.create(program=self.section.program, year_level=self.section.year_level, name='B', size=20)
        parent = m.Assignment.objects.create(term=self.term, subject=self.subject, faculty=self.faculty, section=section)
        meeting = m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE', meeting_index=1, duration_minutes=120)
        row = record_issues(self.run_record(), [self.issue('FACULTY_CONFLICT', meetings=[self.meetings[1], meeting])])[0]
        self.assertEqual(set(row.details['assignment_ids']), {self.parent.pk, parent.pk})
        self.assertEqual(set(row.details['meeting_ids']), {self.meetings[1].pk, meeting.pk})
        page = self.client.get(f'/schedules/error-log/{row.pk}/')
        self.assertContains(page, str(section))

    def test_same_text_conflicts_retain_every_pair(self):
        third = m.TeachingAssignment.objects.create(assignment=self.parent, component='LECTURE', meeting_index=3, duration_minutes=60)
        schedule = m.Schedule.objects.create(term=self.term, name='Three overlaps')
        for meeting in self.meetings + [third]:
            m.ScheduleEntry.objects.create(schedule=schedule, assignment=meeting, room=self.room, day=0, start_time=time(8), end_time=time(9))
        issues = schedule_validation_messages(schedule).issues
        rows = record_issues(self.run_record(), issues)
        faculty = [row for row in rows if row.category == 'FACULTY_CONFLICT']
        self.assertEqual(len(faculty), 3)
        self.assertEqual({tuple(row.details['meeting_ids']) for row in faculty},
            {(self.meetings[0].pk, self.meetings[1].pk), (self.meetings[0].pk, third.pk), (self.meetings[1].pk, third.pk)})

    def test_failed_issue_persistence_is_safe_and_recoverable(self):
        with patch('schedules.views.GeneticScheduler.generate', side_effect=GenerationFailure('Failure', [self.issue()])), patch(
            'schedules.services.generation_issues.GenerationIssue.objects.create', side_effect=IntegrityError('private SQL')):
            page = self.client.post('/schedules/generate/', {'term': self.term.pk, 'settings': self.settings.pk, 'name': 'Failure'})
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'private SQL')
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'RUNNING')
        self.assertFalse(run.issues.exists())
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)
        self.assertEqual(recover_stale_runs(), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.issues.count(), 1)

    def test_recovery_rechecks_lease_at_write_not_only_discovery(self):
        from django.db.models.query import QuerySet
        legacy = self.run_record()
        real = QuerySet.update
        acquired = []
        def acquire_before_update(queryset, **kwargs):
            if queryset.model is m.GenerationRun and kwargs.get('status') == 'FAILED' and not acquired:
                acquired.append(acquire(self.term.pk))
            return real(queryset, **kwargs)
        with patch.object(QuerySet, 'update', acquire_before_update):
            self.assertEqual(recover_stale_runs(), 0)
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, 'RUNNING')
        self.assertFalse(legacy.issues.exists())
        acquired[0].release()
