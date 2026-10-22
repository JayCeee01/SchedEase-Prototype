from django.core.management.base import BaseCommand, CommandError
from schedules.services.database_backup import BackupError, configured_source, snapshot


class Command(BaseCommand):
    help = 'Create a verified SQLite online backup in a new private file; never overwrite.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--database', default='default')
        parser.add_argument('--timeout', type=int, default=60)

    def handle(self, *args, **options):
        try:
            report = snapshot(configured_source(options['database']), options['output'], timeout=options['timeout'])
        except BackupError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS(f"Verified backup: {report['destination']}"))
        if not report['current_schema']:
            self.stderr.write('Warning: migration/schema compatibility requires manual review with the matching application release.')
