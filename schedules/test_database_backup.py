from contextlib import closing
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from .services import database_backup as backup


class DatabaseBackupTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(settings.BASE_DIR).resolve() / ('recovery-drills/test-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup)
        self.source = self.root/'source.sqlite3'
        self.output = self.root/'copy.sqlite3'
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)')
            db.execute('INSERT INTO records VALUES (1, ?)', ('synthetic-only',))
            db.commit()

    def cleanup(self):
        root = self.root.resolve()
        assert root.parent == Path(settings.BASE_DIR).resolve()/'recovery-drills'
        assert root.name.startswith('test-')
        shutil.rmtree(root)

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).digest()

    def assert_no_partial(self):
        self.assertEqual(list(self.root.glob('.schedease-*')), [])

    def test_backup_integrity_and_source_unchanged(self):
        before = self.digest(self.source)
        report = backup.snapshot(self.source, self.output)
        self.assertEqual(self.digest(self.source), before)
        self.assertEqual(report['counts'], {'records':1})
        self.assertFalse(report['current_schema'])
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(db.execute('SELECT * FROM records').fetchall(), [(1,'synthetic-only')])
        self.assert_no_partial()

    def test_existing_destinations_and_same_source_rejected(self):
        self.output.write_bytes(b'existing-private-sentinel')
        for destination in (self.source, self.output, self.root/'sub'/ '..' / 'source.sqlite3'):
            with self.subTest(destination=destination.name), self.assertRaises(backup.BackupError):
                backup.snapshot(self.source, destination)
        self.assertEqual(self.output.read_bytes(), b'existing-private-sentinel')

    def test_active_database_path_rejected_even_when_missing(self):
        self.assertFalse(self.output.exists())
        with patch.object(backup, 'protected_paths', return_value={self.output}):
            with self.assertRaises(backup.BackupError):
                backup.snapshot(self.source, self.root/'unused'/ '..' / self.output.name, restore=True)
        self.assertFalse(self.output.exists())

    def test_configured_database_and_default_path_are_protected(self):
        self.assertIn((Path(settings.BASE_DIR)/'db.sqlite3').resolve(), backup.protected_paths())
        with self.assertRaises(backup.BackupError):
            backup.destination_path(Path(settings.BASE_DIR)/'db.sqlite3', self.source)

    def test_public_directories_and_wrong_extension_rejected(self):
        with override_settings(STATIC_ROOT=self.root/'assets', MEDIA_ROOT=self.root/'uploads',
                               STATICFILES_DIRS=[('prefix',self.root/'source-assets')]):
            for value in ('assets/x.sqlite3','uploads/x.sqlite3','source-assets/x.sqlite3','x.txt'):
                with self.subTest(value=value), self.assertRaises(backup.BackupError):
                    backup.snapshot(self.source,self.root/value)

    def test_missing_directory_missing_source_and_memory_rejected(self):
        for source, target in ((self.root/'missing.sqlite3',self.output),
                              (self.source,self.root/'missing'/'copy.db'), (':memory:',self.output)):
            with self.subTest(source=source), self.assertRaises(backup.BackupError):
                backup.snapshot(source,target)
        self.assertFalse(self.output.exists())

    def test_invalid_and_corrupt_sources_no_destination(self):
        for content in (b'', b'not a database private sentinel', b'SQLite format 3\x00' + b'broken'*100):
            self.source.write_bytes(content)
            with self.assertRaises(backup.BackupError) as error:
                backup.snapshot(self.source,self.output,restore=True)
            self.assertNotIn('private sentinel',str(error.exception))
            self.assertFalse(self.output.exists())
            self.assert_no_partial()

    def test_foreign_key_violation_rejected(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE child (parent_id INTEGER REFERENCES records(id))')
            db.execute('INSERT INTO child VALUES (999)')
            db.commit()
        with self.assertRaisesMessage(backup.BackupError, 'Foreign-key'):
            backup.snapshot(self.source,self.output)
        self.assertFalse(self.output.exists())
        self.assert_no_partial()

    def test_incompatible_restore_rejected_but_backup_allowed(self):
        backup.snapshot(self.source,self.output)
        with self.assertRaisesMessage(backup.BackupError, 'migration history'):
            backup.snapshot(self.output,self.root/'restore.sqlite3',restore=True)
        self.assertFalse((self.root/'restore.sqlite3').exists())
        self.assert_no_partial()

    def test_wal_committed_snapshot_ignores_uncommitted_changes(self):
        with closing(sqlite3.connect(self.source)) as writer:
            self.assertEqual(writer.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('INSERT INTO records VALUES (2, ?)',('committed',))
            writer.commit()
            writer.execute('INSERT INTO records VALUES (3, ?)',('uncommitted',))
            backup.snapshot(self.source,self.output)
            with closing(sqlite3.connect(self.output)) as copy:
                self.assertEqual(copy.execute('SELECT id FROM records ORDER BY id').fetchall(),[(1,),(2,)])
                self.assertEqual(copy.execute('PRAGMA journal_mode').fetchone()[0],'delete')
            writer.rollback()
        self.assert_no_partial()

    def test_locked_source_times_out_and_cleans_up(self):
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(backup.BackupError):
                backup.snapshot(self.source,self.output,timeout=0.05)
            writer.rollback()
        self.assertFalse(self.output.exists())
        self.assert_no_partial()

    def test_interruption_and_permission_failure_leave_no_destination(self):
        for error in (KeyboardInterrupt(), PermissionError('private-path-sentinel')):
            with self.subTest(error=type(error).__name__), patch.object(backup,'verify',side_effect=error):
                with self.assertRaises((KeyboardInterrupt,backup.BackupError)):
                    backup.snapshot(self.source,self.output)
            self.assertFalse(self.output.exists())
            self.assert_no_partial()

    def test_finalization_failure_and_concurrent_destination_creation(self):
        for create in (False,True):
            def fail_link(source,destination):
                if create:
                    Path(destination).write_bytes(b'other-writer')
                raise FileExistsError('do not replace')
            with patch.object(backup.os,'link',side_effect=fail_link), self.assertRaises(backup.BackupError):
                backup.snapshot(self.source,self.output)
            if create:
                self.assertEqual(self.output.read_bytes(),b'other-writer')
            else:
                self.assertFalse(self.output.exists())
            self.assert_no_partial()

    def test_preexisting_sqlite_sidecar_rejected(self):
        sidecar=Path(str(self.output)+'-wal')
        sidecar.write_bytes(b'preserve')
        with self.assertRaises(backup.BackupError):
            backup.snapshot(self.source,self.output)
        self.assertEqual(sidecar.read_bytes(),b'preserve')
        self.assertFalse(self.output.exists())

    def test_symlink_or_junction_is_not_resolved_into_destination(self):
        link=self.root/'linked'
        try:
            link.symlink_to(self.root,target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(self.root)],capture_output=True)
            self.assertEqual(result.returncode,0,'Could not create junction for Windows safety test')
        try:
            with self.assertRaises(backup.BackupError):
                backup.snapshot(self.source,link/'new.sqlite3')
        finally:
            if link.is_symlink():
                link.unlink()
            else:
                link.rmdir()
        self.assertFalse((self.root/'new.sqlite3').exists())

    def test_command_errors_do_not_expose_source_contents(self):
        self.source.write_bytes(b'private-content-sentinel')
        with self.assertRaises(CommandError) as error:
            call_command('restore_database',source=str(self.source),destination=str(self.output),stdout=StringIO())
        self.assertNotIn('private-content-sentinel',str(error.exception))

    def test_synthetic_end_to_end_recovery_drill(self):
        # Separate fresh interpreter applies migrations only to this empty fixture.
        drill=self.root/'drill'
        drill.mkdir()
        (drill/'.synthetic-recovery').touch()
        result=subprocess.run([sys.executable,'-m','schedules.test_support.recovery_drill',str(drill),'create'],
                              capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout.strip())
        self.assertTrue(report['exact_schema_and_rows'])
        self.assertTrue(report['source_and_backup_unchanged'])
        self.assertGreater(report['triggers'],0)
        self.assertEqual(report['protected_mutations_rejected'],7)
        print('Synthetic recovery drill:',json.dumps(report,sort_keys=True))
        source_hash=self.digest(drill/'source.sqlite3')
        backup_hash=self.digest(drill/'backup.sqlite3')
        result=subprocess.run([sys.executable,'-m','schedules.test_support.recovery_drill',str(drill),'leases'],
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.digest(drill/'source.sqlite3'),source_hash)
        self.assertEqual(self.digest(drill/'backup.sqlite3'),backup_hash)
        # Drift checks modify separate disposable candidates, never the backup.
        for label, sql in [
            ('migration', "DELETE FROM django_migrations WHERE app='schedules' AND name='0015_generationrun_reproducibility'"),
            ('trigger', 'DROP TRIGGER h2_snapshot_update'),
            ('index', None),
        ]:
            candidate=drill/(label+'.sqlite3')
            backup.snapshot(drill/'backup.sqlite3',candidate)
            with closing(sqlite3.connect(candidate)) as db:
                if label=='index':
                    index=db.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='schedules_generationrun' AND sql IS NOT NULL LIMIT 1").fetchone()[0]
                    sql='DROP INDEX '+backup.quote_identifier(index)
                db.execute(sql)
                db.commit()
            with self.subTest(drift=label), self.assertRaises(backup.BackupError):
                backup.snapshot(candidate,drill/(label+'-restore.sqlite3'),restore=True)
            self.assertFalse((drill/(label+'-restore.sqlite3')).exists())
