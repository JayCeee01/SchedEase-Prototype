"""SQLite snapshots and restore-to-new-file only. No live replacement operation."""
from contextlib import closing
from importlib import import_module
import os
from pathlib import Path
import sqlite3
import stat
import time
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader


class BackupError(Exception):
    """Messages are safe for console output; never include database row values."""


def local_path(value):
    text = str(value)
    if not text or text == ':memory:' or text.startswith('file:'):
        raise BackupError('Use an explicit filesystem database path, not an in-memory database or SQLite URI.')
    path = Path(os.path.abspath(text))
    # Reject links, including junctions/reparse points on Windows, before resolve.
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and
                getattr(part.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024)):
            raise BackupError('Symbolic links and junctions are not allowed in database paths.')
    return path.resolve()


def configured_source(alias='default'):
    config = settings.DATABASES.get(alias)
    if not config or config['ENGINE'] != 'django.db.backends.sqlite3':
        raise BackupError('Only configured file-backed SQLite databases are supported.')
    return local_path(config['NAME'])


def protected_paths():
    paths = [Path(settings.BASE_DIR) / 'db.sqlite3']
    for config in settings.DATABASES.values():
        name = str(config.get('NAME', ''))
        if name and name != ':memory:' and not name.startswith('file:'):
            paths.append(Path(name))
    return {path.resolve() for path in paths}


def public_roots():
    roots = [Path(settings.BASE_DIR) / 'static', Path(settings.BASE_DIR) / 'media']
    roots.extend(Path(value) for value in (getattr(settings, 'STATIC_ROOT', ''),
                                         getattr(settings, 'MEDIA_ROOT', '')) if value)
    roots.extend(Path(value[1] if isinstance(value, (tuple, list)) else value)
                 for value in getattr(settings, 'STATICFILES_DIRS', []))
    return [root.resolve() for root in roots]


def destination_path(value, source):
    path = local_path(value)
    if path in protected_paths() or path == source:
        raise BackupError('Destination is a protected or source database. Choose a new isolated file.')
    if any(path == root or root in path.parents for root in public_roots()):
        raise BackupError('Database copies must not be stored in public static or media directories.')
    if path.suffix.lower() not in ('.sqlite3', '.db'):
        raise BackupError('Destination must end in .sqlite3 or .db so database files remain excluded from Git.')
    if not path.parent.is_dir():
        raise BackupError('Create a private destination directory first.')
    if any(os.path.lexists(str(path) + suffix) for suffix in ('', '-wal', '-shm', '-journal')):
        raise BackupError('Destination or its SQLite sidecar already exists; overwrite is never allowed.')
    return path


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def schema(connection):
    return connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()


def compatibility(connection):
    """Fail closed on migration drift and missing current tables/columns/guards."""
    expected = set(MigrationLoader(None).disk_migrations)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'django_migrations' not in tables:
        return False
    applied = set(connection.execute('SELECT app,name FROM django_migrations'))
    if applied != expected:
        return False
    for model in apps.get_models(include_auto_created=True):
        if not model._meta.managed or model._meta.proxy:
            continue
        table = model._meta.db_table
        if table not in tables:
            return False
        info = {row[1]: row for row in connection.execute(f'PRAGMA table_info({quote_identifier(table)})')}
        columns = set(info)
        if columns != {field.column for field in model._meta.local_fields}:
            return False
        indexes = []
        for row in connection.execute(f'PRAGMA index_list({quote_identifier(table)})').fetchall():
            indexed_columns = tuple(info[2] for info in connection.execute(f'PRAGMA index_info({quote_identifier(row[1])})'))
            indexes.append((indexed_columns, bool(row[2])))
        foreign_keys = {(row[3],row[2],row[4]) for row in connection.execute(f'PRAGMA foreign_key_list({quote_identifier(table)})')}
        for field in model._meta.local_fields:
            if (field.many_to_one or field.one_to_one) and field.db_constraint and (
                    field.column,field.target_field.model._meta.db_table,field.target_field.column) not in foreign_keys:
                return False
            if field.primary_key:
                if not info[field.column][5]:
                    return False
                continue
            if not field.null and not info[field.column][3]:
                return False
            if field.unique and ((field.column,), True) not in indexes:
                return False
            if field.db_index and not any(columns == (field.column,) for columns, unique in indexes):
                return False
        for fields in model._meta.unique_together:
            if (tuple(model._meta.get_field(field).column for field in fields), True) not in indexes:
                return False
        table_sql = connection.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?', ('table',table)).fetchone()[0]
        for constraint in model._meta.constraints:
            if getattr(constraint, 'fields', ()):
                if (tuple(model._meta.get_field(field).column for field in constraint.fields),True) not in indexes:
                    return False
            elif constraint.name not in table_sql:
                return False
    guards = {}
    for module in ('0010_finalized_schedule_guards', '0011_academic_term_guards', '0012_historical_snapshots'):
        guards.update(dict(import_module('schedules.migrations.' + module).TRIGGERS))
    actual = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
    normalize = lambda sql: ' '.join(sql.strip().rstrip(';').split())
    return all(name in actual and normalize(actual[name]) == normalize(sql) for name, sql in guards.items())


def verify(connection, *, require_current=False):
    if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise BackupError('SQLite integrity verification failed. Preserve the source for investigation.')
    if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise BackupError('Foreign-key verification failed. No copy was finalized.')
    current = compatibility(connection)
    if require_current and not current:
        raise BackupError('Backup migration history, schema or protection triggers do not match this application. Review using the matching release; no migrations were run.')
    counts = {name: connection.execute(f'SELECT count(*) FROM {quote_identifier(name)}').fetchone()[0]
              for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}
    return {'current_schema': current, 'table_count': len(counts), 'counts': counts}


def snapshot(source, destination, *, restore=False, timeout=60):
    """Online backup to a private temporary file, checked then linked without clobber.

    Directories must be trusted and not concurrently renamed by other users.
    Atomic hard-link publication intentionally has no unsafe copy/replace fallback.
    """
    temporary = None
    try:
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 3600:
            raise BackupError('Timeout must be greater than zero and at most 3600 seconds.')
        source = local_path(source)
        if not source.is_file() or source.stat().st_size == 0:
            raise BackupError('Source database does not exist, is empty or is not a regular file.')
        destination = destination_path(destination, source)
        parent_identity = destination.parent.stat()
        temporary = destination.parent / ('.schedease-' + uuid4().hex + '.partial')
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        deadline = time.monotonic() + timeout

        def progress(*unused):
            if time.monotonic() >= deadline:
                raise BackupError('Database copy timed out. Retry during a quieter period or increase --timeout.')

        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=min(timeout, 1))) as original:
            original.execute('PRAGMA query_only=ON')
            with closing(sqlite3.connect(temporary)) as copied:
                original.backup(copied, pages=256, progress=progress, sleep=0.05)
                # Materialize a self-contained rollback-journal file even from WAL.
                copied.execute('PRAGMA journal_mode=DELETE')
                copied.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
                report = verify(copied, require_current=restore)
        with temporary.open('rb+') as file:
            os.fsync(file.fileno())
        destination_path(destination, source)
        current_parent = destination.parent.stat()
        if (parent_identity.st_dev, parent_identity.st_ino) != (current_parent.st_dev, current_parent.st_ino):
            raise BackupError('Destination directory changed during the operation. Retry in private storage.')
        # link fails atomically if the name now exists, on both NTFS and POSIX.
        os.link(temporary, destination)
        return {**report, 'destination': destination}
    except (sqlite3.Error, OSError, ValueError):
        # SQLite errors may contain record/constraint values; do not echo them.
        raise BackupError('Database copy failed. Check source validity, locks, directory permissions, free space and hard-link support. No existing file was replaced.') from None
    finally:
        if temporary is not None:
            for suffix in ('', '-wal', '-shm', '-journal'):
                path = Path(str(temporary) + suffix)
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    raise BackupError('Temporary-file cleanup failed. Restrict access and have the storage administrator inspect .schedease-*.partial files.') from None
