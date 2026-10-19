"""Fresh interpreter + RAM-only SQLite. Never imports deployment settings."""
import json
import sys
from contextlib import contextmanager


@contextmanager
def isolated_database():
    from django.conf import settings
    settings.configure(
        SECRET_KEY='synthetic-benchmark-only', GA_BENCHMARK_ISOLATED=True,
        INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'schedules'],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        USE_TZ=True, TIME_ZONE='Asia/Shanghai', DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
    )
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connections
    try:
        call_command('migrate', verbosity=0, interactive=False)
        yield
    finally:
        connections.close_all()
        # The OS releases this process's memory database even on abnormal exit.


def main():
    with isolated_database():
        from .trial import run_trial
        result = run_trial(json.load(sys.stdin))
        sys.stdout.write(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
