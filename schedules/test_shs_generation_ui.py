"""HTTP integration and caller-owned lease safety with synthetic SHS inputs."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db.models.functions import Now
from django.test import Client, TestCase

from . import models as m
from . import test_shs_generation as generation_fixtures
from . import test_contact_workload as workload_fixtures
from .services.ga import GeneticScheduler
from .services.generation_lock import acquire, GenerationLeaseLost
from .services.shs_scheduling import generate_shs
from .services.publication import publish


class SHSGenerationUITests(TestCase):
    def setUp(self):
        generation_fixtures.ControlledSHSGenerationTests.setUp(self)
        self.settings.save()
        self.policy = workload_fixtures.ContactPolicyTests.policy(self)
        self.client.force_login(self.actor)
        self.payload = dict(term=self.term.pk, settings=self.settings.pk, name='SHS UI', seed=17)

    def post(self):
        return self.client.post('/schedules/generate/', self.payload)

    def assert_empty(self):
        for model in (m.TeachingAssignment, m.SHSMeetingBinding, m.Schedule, m.ScheduleEntry):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_http_success_reuses_lease_run_and_publishes(self):
        with patch('schedules.services.generation_lock.acquire', side_effect=AssertionError('double acquire')):
            response = self.post()
        self.assertEqual(response.status_code, 302)
        schedule = m.Schedule.objects.get()
        run = m.GenerationRun.objects.get()
        self.assertEqual((run.status, run.requested_by_id, run.schedule_id), ('SUCCEEDED', self.actor.pk, schedule.pk))
        self.assertIsNotNone(run.lease_owner)
        self.assertEqual(m.GenerationLease.objects.count(), 1)
        self.assertIsNone(m.GenerationLease.objects.get().owner)
        self.assertEqual(schedule.status, 'DRAFT')
        self.assertEqual(m.SHSMeetingBinding.objects.count(), 1)
        published, _ = publish(schedule, self.actor)
        snapshot = m.ScheduleSnapshot.objects.get(schedule=published).data
        self.assertEqual(self.post().status_code, 302)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=published).data, snapshot)
        self.assertEqual(m.SHSMeetingBinding.objects.count(), 1)

    def test_expected_configuration_errors_persist_after_rollback(self):
        self.policy.delete()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assert_empty()
        run = m.GenerationRun.objects.get()
        self.assertEqual(run.status, 'FAILED')
        self.assertTrue(run.issues.filter(reason__icontains='policy').exists())
        self.assertContains(response, 'Error Log')
        self.assertIsNone(m.GenerationLease.objects.get().owner)

    def test_missing_configuration_and_approval(self):
        self.config.is_confirmed = False
        self.config.save()
        self.assertEqual(self.post().status_code, 200)
        self.assertTrue(m.GenerationIssue.objects.filter(reason__icontains='Confirm').exists())
        self.assert_empty()
        self.config.delete()
        self.assertEqual(self.post().status_code, 200)
        self.assertTrue(m.GenerationIssue.objects.filter(reason__icontains='operational configuration').exists())
        self.assert_empty()

    def test_failure_after_schedule_creation_rolls_back_everything(self):
        with patch('schedules.services.conflicts.schedule_validation_messages', side_effect=RuntimeError('private sentinel')):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'private sentinel')
        self.assert_empty()
        self.assertEqual(m.GenerationRun.objects.get().status, 'FAILED')
        self.assertTrue(m.GenerationIssue.objects.exists())
        self.assertIsNone(m.GenerationLease.objects.get().owner)

    def test_stale_binding_rejected_without_replacement(self):
        self.assertEqual(self.post().status_code, 302)
        meeting = m.TeachingAssignment.objects.get()
        original = meeting.shs_binding.data
        self.config.calendar_reference = 'Changed approval reference'
        self.config.save()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(m.Schedule.objects.count(), 1)
        self.assertEqual(m.SHSMeetingBinding.objects.get().data, original)
        self.assertTrue(m.GenerationIssue.objects.filter(reason__icontains='snapshot').exists())

    def test_busy_lease_does_not_create_run(self):
        lease = acquire(self.term.pk)
        try:
            self.assertEqual(self.post().status_code, 200)
            self.assertFalse(m.GenerationRun.objects.exists())
            self.assert_empty()
        finally:
            lease.release()

    def test_invalid_existing_leases_do_not_prepare(self):
        for kind in ('expired', 'replaced', 'released', 'wrong-term'):
            with self.subTest(kind=kind):
                lease = acquire(self.term.pk)
                if kind == 'expired':
                    m.GenerationLease.objects.filter(term=self.term).update(expires_at=Now()-timedelta(seconds=1))
                elif kind == 'replaced':
                    m.GenerationLease.objects.filter(term=self.term).update(owner=uuid4())
                elif kind == 'released':
                    lease.release()
                else:
                    lease.term_id += 1000
                with self.assertRaises(GenerationLeaseLost):
                    generate_shs(self.term, self.settings, actor=self.actor, lease=lease)
                self.assert_empty()
                m.GenerationLease.objects.filter(term=self.term).update(owner=None, expires_at=None)

    def test_valid_caller_lease_is_not_released_and_standalone_still_works(self):
        lease = acquire(self.term.pk)
        with patch('schedules.services.generation_lock.acquire', side_effect=AssertionError('double acquire')):
            generate_shs(self.term, self.settings, actor=self.actor, lease=lease)
        self.assertEqual(m.GenerationLease.objects.get().owner, lease.owner)
        lease.release()
        generate_shs(self.term, self.settings, actor=self.actor)
        self.assertIsNone(m.GenerationLease.objects.get().owner)
        self.assertEqual(m.Schedule.objects.count(), 2)

    def test_wrong_run_owner_rejected(self):
        lease = acquire(self.term.pk)
        run = m.GenerationRun.objects.create(term=self.term, requested_name='Other owner', lease_owner=uuid4())
        lease.run_id = run.pk
        with self.assertRaises(GenerationLeaseLost):
            generate_shs(self.term, self.settings, actor=self.actor, lease=lease)
        self.assert_empty()
        lease.release()

    def test_authorization_and_csrf_precede_preparation(self):
        user = User.objects.create_user('non-admin')
        self.client.force_login(user)
        self.assertEqual(self.post().status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.actor)
        self.assertEqual(csrf.post('/schedules/generate/', self.payload).status_code, 403)
        self.assert_empty()
        self.assertFalse(m.GenerationLease.objects.exists())
        self.assertFalse(m.GenerationRun.objects.exists())

    def test_publication_rechecks_policy_after_http_generation(self):
        self.assertEqual(self.post().status_code, 302)
        schedule = m.Schedule.objects.get()
        self.policy.is_active = False
        self.policy.save()
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            publish(schedule, self.actor)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'DRAFT')

    def test_expiry_during_generation_rolls_back_preparation(self):
        real = GeneticScheduler._generate
        def expire(scheduler, name):
            m.GenerationLease.objects.filter(term=self.term).update(expires_at=Now()-timedelta(seconds=1))
            return real(scheduler, name)
        with patch.object(GeneticScheduler, '_generate', expire):
            self.assertEqual(self.post().status_code, 200)
        self.assert_empty()
        self.assertEqual(m.GenerationRun.objects.get().status, 'FAILED')
        self.assertIsNone(m.GenerationLease.objects.get().owner)

    def test_sqlite_writer_contention_and_same_connection_renewal(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from pathlib import Path
        import sqlite3
        from django.db import connection, connections
        from .services.generation_lock import GenerationBusy
        path = Path.cwd() / ('shs-generation-test-' + uuid4().hex + '.sqlite3')
        config = connection.settings_dict.copy()
        config.update(NAME=str(path), OPTIONS={'timeout': .2})
        wrapper = type(connections['default'])
        locked, attempted = Event(), Event()
        real = GeneticScheduler._generate
        def held(scheduler, name):
            locked.set()
            if not attempted.wait(10):
                raise AssertionError('Contender did not complete')
            # Renewal must work inside the adapter transaction on its own connection.
            scheduler._lease.checkpoint(force=True)
            return real(scheduler, name)
        def owner():
            db = wrapper(config.copy(), alias='default'); connections['default'] = db
            try:
                client = Client(); client.force_login(User.objects.get(pk=self.actor.pk))
                return client.post('/schedules/generate/', self.payload).status_code
            finally:
                db.close()
        def contender():
            db = wrapper(config.copy(), alias='default'); connections['default'] = db
            try:
                if not locked.wait(10): raise AssertionError('Owner never reached generation')
                try:
                    acquire(self.term.pk)
                except GenerationBusy:
                    return 'busy'
                raise AssertionError('Competing writer acquired the lease')
            finally:
                attempted.set(); db.close()
        try:
            assert not path.exists()
            path.write_bytes(connection.connection.serialize())
            with patch.object(GeneticScheduler, '_generate', held), ThreadPoolExecutor(max_workers=2) as pool:
                first, second = pool.submit(owner), pool.submit(contender)
                self.assertEqual(first.result(timeout=20), 302)
                self.assertEqual(second.result(timeout=20), 'busy')
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('select count(*) from schedules_schedule').fetchone()[0], 1)
                self.assertEqual(db.execute("select count(*) from schedules_generationrun where status='SUCCEEDED'").fetchone()[0], 1)
                self.assertIsNone(db.execute('select owner from schedules_generationlease').fetchone()[0])
            db.close()
        finally:
            self.assertEqual(path.resolve().parent, Path.cwd().resolve())
            path.unlink(missing_ok=True)
