"""H2 immutable publication history and permission-aware display."""
from datetime import time
from importlib import import_module
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.publication import publish
from .services.history import backfill_snapshots, historical_entries
from .services.manual_edits import copy_to_draft


class SnapshotTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='publisher', password='test')
        self.client.force_login(self.admin)
        self.schedule = m.Schedule.objects.create(term=self.term, name='Historical')
        self.entries = [self.schedule.entries.create(assignment=meeting, room=self.room, day=0,
                        start_time=time(8+i), end_time=time(9+i)) for i, meeting in enumerate(self.meetings)]

    def finalize(self):
        self.schedule, _ = publish(self.schedule, self.admin)
        return self.schedule.snapshot

    def test_capture_academic_information_and_publication_metadata(self):
        snapshot = self.finalize()
        self.assertFalse(snapshot.reconstructed)
        data = snapshot.data
        self.assertEqual(data['term']['starts_on'], self.term.starts_on.isoformat())
        self.assertEqual(data['term']['school_year'], self.term.school_year)
        self.assertEqual(data['publication']['user_id'], self.admin.pk)
        self.assertEqual(data['publication']['username'], 'publisher')
        self.assertEqual(data['schedule']['status'], 'PUBLISHED')
        self.assertIsNotNone(data['schedule']['published_at'])
        self.assertEqual(len(data['entries']), 2)
        row = data['entries'][0]
        self.assertEqual(row['course']['title'], self.subject.title)
        self.assertEqual(row['course']['code'], self.subject.code)
        self.assertEqual(row['faculty']['employee_id'], self.faculty.employee_id)
        self.assertEqual(row['faculty']['full_name'], self.faculty.full_name)
        self.assertEqual(row['section']['display_name'], str(self.section))
        self.assertEqual(row['program']['code'], self.section.program.code)
        self.assertEqual(row['year_level']['label'], self.section.year_level.label)
        self.assertEqual(row['room']['name'], self.room.name)
        self.assertEqual(row['room']['capacity'], 30)
        self.assertEqual(row['required_duration_minutes'], 60)
        self.assertEqual(row['actual_duration_minutes'], 60)
        self.assertEqual(row['component'], 'LECTURE')
        self.assertEqual(row['meeting_id'], self.meetings[0].pk)

    def test_model_bulk_and_direct_sql_immutability(self):
        snapshot = self.finalize()
        original = snapshot.data
        with self.assertRaises(ValidationError):
            snapshot.save()
        with self.assertRaises(ValidationError):
            snapshot.delete()
        attempts = [
            lambda: m.ScheduleSnapshot.objects.filter(pk=snapshot.pk).update(data={}),
            lambda: m.ScheduleSnapshot.objects.filter(pk=snapshot.pk).delete(),
            lambda: m.ScheduleSnapshot.objects.bulk_update([snapshot], ['data']),
            lambda: connection.cursor().execute('UPDATE schedules_schedulesnapshot SET reconstructed=1 WHERE id=%s', [snapshot.pk]),
            lambda: connection.cursor().execute('DELETE FROM schedules_schedulesnapshot WHERE id=%s', [snapshot.pk]),
            lambda: connection.cursor().execute('INSERT OR REPLACE INTO schedules_schedulesnapshot SELECT * FROM schedules_schedulesnapshot WHERE id=%s', [snapshot.pk]),
        ]
        for attempt in attempts:
            with self.subTest(attempt=attempt), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    attempt()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.data, original)

    def test_direct_sql_finalization_cannot_omit_snapshot(self):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE schedules_schedule SET status='PUBLISHED' WHERE id=%s", [self.schedule.pk])
        self.assertEqual(m.ScheduleSnapshot.objects.filter(schedule=self.schedule).count(), 1)
        self.assertTrue(m.ScheduleSnapshot.objects.get(schedule=self.schedule).data['warnings']['publication_time_missing'])

    def test_direct_finalized_insert_captures_incomplete_information_honestly(self):
        empty = m.Schedule.objects.create(term=self.term, name='Legacy empty', status='ARCHIVED')
        snapshot = empty.snapshot
        self.assertEqual(snapshot.data['entries'], [])
        self.assertIsNone(snapshot.data['schedule']['published_at'])
        self.assertIsNone(snapshot.data['publication'])
        self.assertTrue(snapshot.data['warnings']['no_entries'])

    def test_snapshot_failure_rolls_back_publication_audit_and_archive(self):
        original = self.finalize()
        draft = copy_to_draft(source_id=self.schedule.pk, actor=self.admin)
        before_audits = draft.edit_audits.count()
        with connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER fail_snapshot BEFORE INSERT ON schedules_schedulesnapshot BEGIN SELECT RAISE(ABORT,'forced snapshot failure'); END")
        with self.assertRaises(IntegrityError):
            publish(draft, self.admin, True)
        draft.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertEqual(draft.status, 'DRAFT')
        self.assertEqual(draft.edit_audits.count(), before_audits)
        self.assertEqual(self.schedule.status, 'PUBLISHED')
        self.assertIsNone(self.schedule.archived_at)
        self.assertFalse(m.ScheduleSnapshot.objects.filter(schedule=draft).exists())
        self.assertEqual(self.schedule.snapshot.data, original.data)

    def test_missing_trigger_fails_closed_in_application(self):
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER h2_snapshot_finalize_update')
        with self.assertRaises(m.ScheduleSnapshot.DoesNotExist):
            publish(self.schedule, self.admin)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'DRAFT')
        self.assertEqual(self.schedule.edit_audits.count(), 0)

    def test_archive_retains_identical_snapshot_and_copy_uses_live_draft(self):
        original = self.finalize()
        draft = copy_to_draft(source_id=self.schedule.pk, actor=self.admin)
        self.assertFalse(m.ScheduleSnapshot.objects.filter(schedule=draft).exists())
        draft.entries.filter(pk=draft.entries.first().pk).update(day=1)
        publish(draft, self.admin, True)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'ARCHIVED')
        original.refresh_from_db()
        self.assertEqual(original.data['schedule']['status'], 'PUBLISHED')
        self.assertEqual(original.data['entries'][0]['day'], 0)
        self.assertEqual(self.schedule.snapshot.pk, original.pk)
        self.assertEqual(m.ScheduleSnapshot.objects.count(), 2)

    def test_duplicate_and_stale_publication_no_extra_audits(self):
        stale = m.Schedule.objects.get(pk=self.schedule.pk)
        self.finalize()
        with self.assertRaises(ValidationError):
            publish(stale, self.admin)
        with self.assertRaises(ValidationError):
            publish(self.schedule, self.admin)
        self.assertEqual(m.ScheduleSnapshot.objects.count(), 1)
        self.assertEqual(self.schedule.edit_audits.count(), 1)

    def test_reconstructed_backfill_is_idempotent(self):
        # Simulate pre-0012 finalized rows; these test-local DDL changes roll back.
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER h2_snapshot_finalize_update')
            cursor.execute('DROP TRIGGER h2_snapshot_finalize_insert')
        self.schedule.status = 'PUBLISHED'
        self.schedule.save(update_fields=['status'])
        archived = m.Schedule.objects.create(term=self.term, name='Old archive', status='ARCHIVED')
        self.assertEqual(backfill_snapshots(), 2)
        first = list(m.ScheduleSnapshot.objects.order_by('pk').values())
        self.assertTrue(all(s['reconstructed'] for s in first))
        self.assertEqual(backfill_snapshots(), 0)
        self.assertEqual(list(m.ScheduleSnapshot.objects.order_by('pk').values()), first)
        self.assertTrue(archived.snapshot.data['warnings']['no_entries'])
        page = self.client.get(f'/schedules/{self.schedule.pk}/')
        self.assertContains(page, 'Reconstructed from records available')

    def test_permitted_live_changes_do_not_rewrite_history_or_revalidate_display(self):
        override = m.CredentialOverride.objects.create(assignment=self.meetings[0], subject=self.subject,
             faculty=self.faculty, admin_user=self.admin, reason='Private approval', missing_credentials='Original note')
        snapshot = self.finalize()
        original = snapshot.data
        User.objects.filter(pk=self.admin.pk).update(username='renamed-publisher')
        m.Availability.objects.create(room=self.room, day=0, start_time=time(7), end_time=time(19), kind='UNAVAILABLE')
        m.AcademicTerm.objects.filter(pk=self.term.pk).update(is_active=True)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.data, original)
        self.assertEqual(snapshot.data['entries'][0]['credential_overrides'][0]['admin_username'], 'publisher')
        self.assertEqual(snapshot.data['entries'][0]['credential_overrides'][0]['id'], override.pk)
        page = self.client.get(f'/schedules/{self.schedule.pk}/')
        self.assertContains(page, 'Read-only historical schedule')
        self.assertNotContains(page, 'Room is unavailable')
        self.assertNotContains(page, 'Private approval')
        rows = historical_entries(self.schedule.entries.all())
        self.assertEqual(rows[0].effective_subject.title, self.subject.title)
        self.assertFalse(hasattr(rows[0], 'credential_overrides'))

    def test_student_filtering_exports_and_archive_access(self):
        other_section = m.Section.objects.create(program=self.section.program, year_level=self.section.year_level, name='B', size=20)
        self.entries[1].section_override = other_section
        self.entries[1].save()
        self.finalize()
        student = User.objects.create_user(username='history-student')
        m.Profile.objects.create(user=student, role='STUDENT')
        m.Student.objects.create(user=student, section=self.section, student_number='H1', full_name='Student')
        self.client.force_login(student)
        page = self.client.get(f'/schedules/{self.schedule.pk}/')
        self.assertEqual(len(page.context['entries']), 1)
        self.assertNotContains(page, str(other_section))
        csv = self.client.get(f'/schedules/{self.schedule.pk}/export/csv/')
        self.assertEqual(csv.status_code, 200)
        self.assertNotIn(str(other_section), csv.content.decode())
        self.assertEqual(self.client.get(f'/schedules/{self.schedule.pk}/export/pdf/').status_code, 200)
        from .protection import archive_transition
        self.schedule.status = 'ARCHIVED'
        with archive_transition():
            self.schedule.save(update_fields=['status'])
        self.assertEqual(self.client.get(f'/schedules/{self.schedule.pk}/').status_code, 404)

    def test_faculty_receives_only_authorized_snapshot_rows(self):
        user = User.objects.create_user(username='faculty-history')
        m.Profile.objects.create(user=user, role='FACULTY')
        self.faculty.user = user
        self.faculty.save()
        other = m.Faculty.objects.create(department=self.department, employee_id='OTHER', full_name='Private Teacher')
        self.entries[1].faculty_override = other
        self.entries[1].save()
        self.finalize()
        self.client.force_login(user)
        page = self.client.get(f'/schedules/{self.schedule.pk}/')
        self.assertEqual(len(page.context['entries']), 1)
        self.assertNotContains(page, 'Private Teacher')

    def test_draft_uses_live_values_and_no_snapshot(self):
        self.subject.title = 'Current draft title'
        self.subject.save()
        self.assertFalse(m.ScheduleSnapshot.objects.exists())
        page = self.client.get(f'/schedules/{self.schedule.pk}/')
        self.assertContains(page, 'Current draft title')
        self.assertNotContains(page, 'Read-only historical schedule')

    def test_snapshot_trigger_installation(self):
        names = {row[0] for row in connection.cursor().execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        expected = import_module('schedules.migrations.0012_historical_snapshots').TRIGGERS
        self.assertTrue(set(expected) <= names)

    def test_concurrent_sql_publication_captures_exactly_once(self):
        # Serialize this isolated fixture to a private file so two real SQLite
        # writers contend without touching the developer database.
        import sqlite3
        from uuid import uuid4
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        path = Path.cwd() / f"snapshot-test-{uuid4().hex}.sqlite3"
        try:
            path.write_bytes(connection.connection.serialize())
            def attempt():
                db = sqlite3.connect(path, timeout=10)
                db.create_function('schedease_archiving', 0, lambda: 0)
                db.create_function('schedease_term_sync', 2, lambda *args: 0)
                try:
                    barrier.wait(timeout=10)
                    with db:
                        changed = db.execute("UPDATE schedules_schedule SET status='PUBLISHED' WHERE id=? AND status='DRAFT'", [self.schedule.pk]).rowcount
                    return changed
                finally:
                    db.close()
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda _: attempt(), range(2)))
            self.assertEqual(sorted(results), [0, 1])
            db = sqlite3.connect(path)
            try:
                self.assertEqual(db.execute('SELECT count(*) FROM schedules_schedulesnapshot WHERE schedule_id=?', [self.schedule.pk]).fetchone()[0], 1)
            finally:
                db.close()
        finally:
            self.assertEqual(path.resolve().parent, Path.cwd().resolve())
            path.unlink(missing_ok=True)

    def test_backfill_failure_is_atomic(self):
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER h2_snapshot_finalize_update')
            cursor.execute('DROP TRIGGER h2_snapshot_finalize_insert')
        self.schedule.status = 'PUBLISHED'
        self.schedule.save(update_fields=['status'])
        archived = m.Schedule.objects.create(term=self.term, name='Second legacy record', status='ARCHIVED')
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TRIGGER fail_backfill BEFORE INSERT ON schedules_schedulesnapshot WHEN NEW.schedule_id={archived.pk} BEGIN SELECT RAISE(ABORT,'forced backfill failure'); END")
        with self.assertRaises(IntegrityError):
            backfill_snapshots()
        self.assertEqual(m.ScheduleSnapshot.objects.count(), 0)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'PUBLISHED')

    def test_bulk_finalization_and_draft_snapshot_insertion_guard(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ScheduleSnapshot.objects.bulk_create([m.ScheduleSnapshot(schedule=self.schedule,
                captured_at=__import__('django').utils.timezone.now(), data={})])
        m.Schedule.objects.filter(pk=self.schedule.pk).update(status='ARCHIVED')
        self.assertEqual(m.ScheduleSnapshot.objects.filter(schedule=self.schedule).count(), 1)

    def test_publication_failure_returns_safe_message(self):
        with patch('schedules.services.publication.ScheduleSnapshot.objects.get', side_effect=RuntimeError('private failure')):
            page = self.client.post(f'/schedules/{self.schedule.pk}/publish/', follow=True)
        self.assertContains(page, 'Nothing was changed')
        self.assertNotContains(page, 'private failure')
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'DRAFT')
        self.assertEqual(self.schedule.edit_audits.count(), 0)
        self.assertEqual(m.ScheduleSnapshot.objects.count(), 0)
