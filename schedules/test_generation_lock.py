"""M3: database ownership, fencing, lifecycle and simultaneous HTTP requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import connection, connections
from django.db.models.functions import Now
from django.test import Client

from . import models as m
from .services.ga import GeneticScheduler
from .services.generation_lock import acquire, Lease, GenerationBusy, GenerationLeaseLost
from .test_known_defects import SchedulingDefectFixture


class GenerationLockTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='lock-admin', password='test')
        self.settings = m.GASettings.objects.create(name='Lock tests', population_size=4, generations=2, elitism=1)
        self.client.force_login(self.admin)
        self.payload = {'term': self.term.pk, 'settings': self.settings.pk, 'name': 'Concurrent generation'}

    def expire(self):
        m.GenerationLease.objects.filter(term=self.term).update(expires_at=Now() - timedelta(seconds=1))

    def test_same_scope_is_exclusive_and_release_allows_retry(self):
        first = acquire(self.term.pk)
        with self.assertRaises(GenerationBusy):
            acquire(self.term.pk)
        self.assertEqual(first.release(), 1)
        second = acquire(self.term.pk)
        self.assertNotEqual(first.owner, second.owner)
        self.assertEqual(first.release(), 0)
        second.release()

    def test_independent_terms_have_independent_owners(self):
        other = m.AcademicTerm.objects.create(name='Other', school_year='2027-2028', starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        first, second = acquire(self.term.pk), acquire(other.pk)
        self.assertNotEqual(first.owner, second.owner)
        first.release()
        second.checkpoint(force=True)
        second.release()

    def test_expired_owner_cannot_renew_or_release_successor(self):
        old = acquire(self.term.pk)
        self.expire()
        new = acquire(self.term.pk)
        with self.assertRaises(GenerationLeaseLost):
            old.checkpoint(force=True)
        self.assertEqual(old.release(), 0)
        self.assertEqual(m.GenerationLease.objects.get(term=self.term).owner, new.owner)
        new.release()

    def test_expired_owner_cannot_save_even_without_successor(self):
        old = acquire(self.term.pk)
        self.expire()
        with self.assertRaises(GenerationLeaseLost), old.saving():
            m.Schedule.objects.create(term=self.term, name='Stale')
        self.assertFalse(m.Schedule.objects.exists())

    def test_wrong_token_cannot_renew_or_release(self):
        owner = acquire(self.term.pk)
        fake = Lease(self.term.pk, uuid4())
        with self.assertRaises(GenerationLeaseLost):
            fake.checkpoint(force=True)
        self.assertEqual(fake.release(), 0)
        owner.checkpoint(force=True)
        owner.release()

    def test_expiration_at_final_save_rolls_back_and_releases(self):
        ga = GeneticScheduler(self.term, self.settings, seed=1)
        real = ga._random_chromosome
        def expire_after_compute():
            result = real()
            self.expire()
            return result
        with patch.object(ga, '_random_chromosome', side_effect=expire_after_compute):
            with self.assertRaises(GenerationLeaseLost):
                ga.generate()
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.ScheduleEntry.objects.exists())
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_takeover_during_computation_fences_old_save(self):
        old = acquire(self.term.pk)
        ga = GeneticScheduler(self.term, self.settings, seed=1)
        real = ga._random_chromosome
        successor = []
        def takeover():
            result = real()
            if not successor:
                self.expire()
                successor.append(acquire(self.term.pk))
            return result
        with patch.object(ga, '_random_chromosome', side_effect=takeover):
            with self.assertRaises(GenerationLeaseLost):
                ga.generate(lease=old)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertEqual(old.release(), 0)
        successor[0].release()

    def test_validation_failure_releases_and_rolls_back(self):
        with patch('schedules.services.conflicts.schedule_validation_messages', return_value=['Forced validation failure']):
            with self.assertRaisesMessage(ValueError, 'Forced validation failure'):
                GeneticScheduler(self.term, self.settings).generate()
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.ScheduleEntry.objects.exists())
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_success_records_run_and_schedule_before_release(self):
        response = self.client.post('/schedules/generate/', self.payload)
        self.assertEqual(response.status_code, 302)
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'SUCCEEDED')
        self.assertEqual(run.schedule.status, 'DRAFT')
        self.assertEqual(run.schedule.term_id, self.term.pk)
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_success_record_failure_rolls_back_schedule(self):
        # Fail only the GenerationRun update inside the final fenced transaction.
        from django.db.models.query import QuerySet
        real = QuerySet.update
        def fail(queryset, **kwargs):
            if queryset.model is m.GenerationRun and kwargs.get('status') == 'SUCCEEDED':
                raise RuntimeError('forced run write failure')
            return real(queryset, **kwargs)
        with patch.object(QuerySet, 'update', fail):
            response = self.client.post('/schedules/generate/', self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.ScheduleEntry.objects.exists())
        self.assertEqual(m.GenerationRun.objects.get().status, 'FAILED')
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_view_failures_release_lock(self):
        for error in (ValueError('invalid requirements'), RuntimeError('secret failure')):
            with self.subTest(error=type(error)), patch('schedules.views.GeneticScheduler.generate', side_effect=error):
                response = self.client.post('/schedules/generate/', self.payload)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'secret failure')
            self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)
        self.assertEqual(m.GenerationRun.objects.filter(status='FAILED').count(), 2)

    def test_run_creation_failure_also_releases_lock(self):
        with patch('schedules.views.GenerationRun.objects.create', side_effect=RuntimeError('private database failure')):
            response = self.client.post('/schedules/generate/', self.payload)
        self.assertContains(response, 'Generation could not start')
        self.assertNotContains(response, 'private database failure')
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_contention_is_not_a_failed_generation_run(self):
        owner = acquire(self.term.pk)
        response = self.client.post('/schedules/generate/', self.payload)
        self.assertContains(response, 'already being generated')
        self.assertFalse(m.GenerationRun.objects.exists())
        self.assertFalse(m.GenerationIssue.objects.exists())
        self.assertFalse(m.Schedule.objects.exists())
        owner.release()

    def test_lost_lease_has_safe_distinct_feedback(self):
        with patch('schedules.views.GeneticScheduler.generate', side_effect=GenerationLeaseLost('Reservation expired. Please try again.')):
            response = self.client.post('/schedules/generate/', self.payload)
        self.assertContains(response, 'Reservation expired')
        self.assertFalse(m.GenerationIssue.objects.exists())
        self.assertEqual(m.GenerationRun.objects.get().status, 'FAILED')
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_admin_and_csrf_enforced_before_acquisition(self):
        anonymous = Client()
        self.assertEqual(anonymous.post('/schedules/generate/', self.payload).status_code, 302)
        ordinary = User.objects.create_user(username='ordinary')
        self.client.force_login(ordinary)
        self.assertEqual(self.client.post('/schedules/generate/', self.payload).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post('/schedules/generate/', self.payload).status_code, 403)
        self.assertFalse(m.GenerationLease.objects.exists())

    def test_wrong_term_lease_rejected(self):
        other = m.AcademicTerm.objects.create(name='Other', school_year='2027-2028', starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        lease = acquire(other.pk)
        with self.assertRaises(GenerationLeaseLost):
            GeneticScheduler(self.term, self.settings).generate(lease=lease)
        self.assertFalse(m.Schedule.objects.exists())
        lease.release()

    def test_long_running_operation_renews_past_initial_deadline(self):
        # Controlled database clock advances; no timing-dependent sleeps.
        from django.db.models import Value, DateTimeField
        from django.utils import timezone
        clock = [timezone.now()]
        def now():
            return Value(clock[0], output_field=DateTimeField())
        with patch('schedules.services.generation_lock.Now', side_effect=now):
            lease = acquire(self.term.pk, seconds=120)
            first_deadline = m.GenerationLease.objects.get(term=self.term).expires_at
            for _ in range(6):
                clock[0] += timedelta(seconds=40)
                lease.next_renewal = 0
                lease.checkpoint()
                with self.assertRaises(GenerationBusy):
                    acquire(self.term.pk)
            self.assertGreater(clock[0], first_deadline)
            with lease.saving():
                m.Schedule.objects.create(term=self.term, name='Long running')
            lease.release()
        self.assertEqual(m.Schedule.objects.count(), 1)

    def test_saving_transaction_rolls_back_partial_work(self):
        lease = acquire(self.term.pk)
        with self.assertRaises(RuntimeError):
            with lease.saving():
                m.Schedule.objects.create(term=self.term, name='Partial')
                raise RuntimeError('abort')
        self.assertFalse(m.Schedule.objects.exists())
        lease.release()

    def test_simultaneous_requests_on_separate_connections_create_only_one_schedule(self):
        # Clone this isolated test DB, including its fixture. Thread-local Django
        # connections use the same file, so process-local cache cannot arbitrate.
        barrier, loser_finished = Barrier(2), Event()
        path = Path.cwd() / f'generation-test-{uuid4().hex}.sqlite3'
        config = connection.settings_dict.copy()
        config['NAME'] = str(path)
        config['OPTIONS'] = {'timeout': 10}
        wrapper = type(connection._connections['default'])
        real = GeneticScheduler._generate
        def held(scheduler, name):
            if not loser_finished.wait(15):
                raise AssertionError('Competing request was not rejected while owner was computing')
            return real(scheduler, name)
        def request():
            db = wrapper(config.copy(), alias='default')
            connections['default'] = db
            try:
                client = Client()
                client.force_login(User.objects.get(pk=self.admin.pk))
                barrier.wait(timeout=15)
                response = client.post('/schedules/generate/', self.payload)
                if response.status_code == 200:
                    self.assertIn(b'already being generated', response.content)
                    loser_finished.set()
                return response.status_code
            finally:
                db.close()
        try:
            path.write_bytes(connection.connection.serialize())
            with patch.object(GeneticScheduler, '_generate', held), ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda _: request(), range(2)))
            self.assertEqual(sorted(results), [200, 302])
            import sqlite3
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM schedules_schedule').fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM schedules_generationrun WHERE status='SUCCEEDED'").fetchone()[0], 1)
                self.assertIsNone(db.execute('SELECT owner FROM schedules_generationlease').fetchone()[0])
            db.close()
        finally:
            self.assertEqual(path.resolve().parent, Path.cwd().resolve())
            path.unlink(missing_ok=True)

    def test_ga_checkpoints_renew_a_long_running_generation(self):
        from django.db.models import Value, DateTimeField
        from django.utils import timezone
        clock = [timezone.now()]
        started = clock[0]
        def now():
            return Value(clock[0], output_field=DateTimeField())
        real = Lease.checkpoint
        def checkpoint(lease, *, force=False):
            clock[0] += timedelta(seconds=40)
            return real(lease, force=True)
        with patch('schedules.services.generation_lock.Now', side_effect=now), patch.object(Lease, 'checkpoint', checkpoint):
            schedule = GeneticScheduler(self.term, self.settings, seed=2).generate()
        self.assertGreater((clock[0] - started).total_seconds(), 120)
        self.assertEqual(schedule.entries.count(), 2)
        self.assertIsNone(m.GenerationLease.objects.get(term=self.term).owner)

    def test_generation_preserves_published_and_archived_history(self):
        for status in ('PUBLISHED', 'ARCHIVED'):
            m.Schedule.objects.create(term=self.term, name=status, status=status)
        before = list(m.ScheduleSnapshot.objects.order_by('pk').values())
        finalized = list(m.Schedule.objects.order_by('pk').values())
        result = GeneticScheduler(self.term, self.settings, seed=2).generate()
        self.assertEqual(result.status, 'DRAFT')
        self.assertEqual(list(m.Schedule.objects.exclude(pk=result.pk).order_by('pk').values()), finalized)
        self.assertEqual(list(m.ScheduleSnapshot.objects.order_by('pk').values()), before)

    def test_busy_database_returns_safe_contention_response(self):
        from django.db import OperationalError
        with patch('schedules.services.generation_lock.GenerationLease.objects.filter', side_effect=OperationalError('database is locked')):
            response = self.client.post('/schedules/generate/', self.payload)
        self.assertContains(response, 'Generation is busy')
        self.assertNotContains(response, 'database is locked')
        self.assertFalse(m.GenerationRun.objects.exists())

    def test_failed_renewal_stops_instead_of_continuing_unprotected(self):
        from django.db import OperationalError
        lease = acquire(self.term.pk)
        with patch.object(lease, 'owned', side_effect=OperationalError('database is locked')):
            with self.assertRaises(GenerationLeaseLost):
                lease.checkpoint(force=True)
        lease.release()

    def test_failed_cleanup_can_be_recovered_after_expiry(self):
        from django.db import OperationalError
        lease = acquire(self.term.pk)
        with patch('schedules.services.generation_lock.GenerationLease.objects.filter', side_effect=OperationalError('database is locked')):
            self.assertEqual(lease.release(), 0)
        self.expire()
        successor = acquire(self.term.pk)
        self.assertNotEqual(successor.owner, lease.owner)
        self.assertEqual(lease.release(), 0)
        successor.release()

    def test_independent_scopes_acquire_concurrently_on_separate_connections(self):
        other = m.AcademicTerm.objects.create(name='Other concurrent', school_year='2027-2028',
            starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        barrier = Barrier(2)
        path = Path.cwd() / f'generation-test-{uuid4().hex}.sqlite3'
        config = connection.settings_dict.copy()
        config.update(NAME=str(path), OPTIONS={'timeout': 10})
        wrapper = type(connections['default'])
        def request(term_id):
            db = wrapper(config.copy(), alias='default')
            connections['default'] = db
            lease = None
            try:
                barrier.wait(timeout=15)
                lease = acquire(term_id)
                barrier.wait(timeout=15)  # Both scopes must own a lease at once.
                lease.checkpoint(force=True)
                return lease.owner
            finally:
                if lease is not None:
                    lease.release()
                db.close()
        try:
            path.write_bytes(connection.connection.serialize())
            with ThreadPoolExecutor(max_workers=2) as workers:
                owners = list(workers.map(request, [self.term.pk, other.pk]))
            self.assertEqual(len(set(owners)), 2)
        finally:
            self.assertEqual(path.resolve().parent, Path.cwd().resolve())
            path.unlink(missing_ok=True)

    def test_missing_generation_run_rolls_back_result(self):
        lease = acquire(self.term.pk)
        lease.run_id = uuid4()
        with self.assertRaises(GenerationLeaseLost):
            GeneticScheduler(self.term, self.settings).generate(lease=lease)
        self.assertFalse(m.Schedule.objects.exists())
        self.assertFalse(m.ScheduleEntry.objects.exists())
        lease.release()
