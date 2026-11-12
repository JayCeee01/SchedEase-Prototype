"""Finalize valid fixtures through the real authorized workflow."""
from django.contrib.auth.models import User
from .services.publication import publish
from .services.manual_edits import copy_to_draft
from functools import wraps
import subprocess
import sys


def finalize(schedule, archived=False):
    from .services.publication_boundary import installed
    if not installed('default'):
        # Old-schema migration fixtures retain their original lifecycle semantics.
        from .protection import archive_transition
        schedule.status='ARCHIVED' if archived else 'PUBLISHED'
        with archive_transition():
            schedule.save(update_fields=['status'])
        return schedule
    actor, _ = User.objects.get_or_create(username='fixture-publisher',
        defaults={'is_active':True,'is_staff':True,'is_superuser':True})
    schedule.refresh_from_db()
    if schedule.status not in ('PUBLISHED','ARCHIVED'):
        published, _ = publish(schedule,actor,replace_confirmed=True)
        schedule.__dict__.update(published.__dict__)
    if archived and schedule.status!='ARCHIVED':
        draft=copy_to_draft(source_id=schedule.pk,actor=actor)
        publish(draft,actor,replace_confirmed=True)
        schedule.refresh_from_db()
    return schedule


def legacy_case(method):
    """Build real pre-0034 history in a child memory DB, then test its upgrade.

    The decorated method calls upgrade() after constructing the legacy state.
    No installed Phase 4 guard is disabled to manufacture that state.
    """
    @wraps(method)
    def run(self):
        script = '''
import os, importlib
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django; django.setup()
from django.test.utils import setup_test_environment
setup_test_environment()
from django.core.management import call_command
call_command('migrate','auth',verbosity=0)
call_command('migrate','sessions',verbosity=0)
call_command('migrate','schedules','0033',verbosity=0)
# Current dashboard infrastructure is independent of historical publication guards.
from schedules.models import ScheduleNotification
from django.db import connection
with connection.schema_editor() as editor:
    editor.create_model(ScheduleNotification)

from django.test import Client
module=importlib.import_module(__TEST_MODULE__)
cls=getattr(module,__TEST_CLASS__)
cls.setUpTestData()
test=cls(); test.client=Client(); test.setUp()
getattr(cls,__TEST_METHOD__).__wrapped__(test)
'''.replace('__TEST_MODULE__',repr(type(self).__module__)).replace('__TEST_CLASS__',repr(type(self).__name__)).replace('__TEST_METHOD__',repr(method.__name__))
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    return run


def upgrade():
    from django.core.management import call_command
    from django.db import connection
    if connection.in_atomic_block:
        # 0034 contains only additive trigger DDL. Fault-injection subtests roll
        # that DDL back with their synthetic historical variant.
        from importlib import import_module
        migration=import_module('schedules.migrations.0034_publication_membership')
        with connection.cursor() as cursor:
            for sql in migration.TRIGGERS.values():
                cursor.execute(sql)
        return
    call_command('migrate','schedules','0034',verbosity=0)


def historical_visibility(cls):
    """Run legacy visibility fixtures in child memory databases, without guard bypasses.

    Each test explicitly upgrades after its historical fixture is complete.
    unittest runs the child test normally so subtest failures are not lost.
    """
    original_setup = cls.setUp

    def setup(self):
        if getattr(self, '_historical_child', False) or not getattr(
                getattr(self, self._testMethodName), '_historical_visibility', False):
            original_setup(self)

    cls.setUp = setup

    def wrap(method):
        @wraps(method)
        def run(self):
            script = '''
import os, importlib, unittest
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django; django.setup()
from django.test.utils import setup_test_environment
setup_test_environment()
from django.core.management import call_command
call_command('migrate','auth',verbosity=0)
call_command('migrate','sessions',verbosity=0)
call_command('migrate','schedules','0033',verbosity=0)
# Current dashboard infrastructure is independent of historical publication guards.
from schedules.models import ScheduleNotification
from django.db import connection
with connection.schema_editor() as editor:
    editor.create_model(ScheduleNotification)

from django.test import Client
cls=getattr(importlib.import_module(__MODULE__), __CLASS__)
test=cls(__METHOD__)
test.client=Client()
test._historical_child=True
setattr(test, __METHOD__, getattr(cls, __METHOD__).__wrapped__.__get__(test, cls))
result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite([test]))
raise SystemExit(not result.wasSuccessful())
'''.replace('__MODULE__', repr(cls.__module__)).replace('__CLASS__', repr(cls.__name__)).replace('__METHOD__', repr(method.__name__))
            result = subprocess.run([sys.executable, '-B', '-c', script],
                capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run._historical_visibility = True
        return run

    for name, method in list(vars(cls).items()):
        if name.startswith('test_'):
            setattr(cls, name, wrap(method))
    return cls
