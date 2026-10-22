from django.core.management.base import BaseCommand, CommandError
from schedules.services.database_backup import BackupError, snapshot


class Command(BaseCommand):
    help = 'Restore a compatible SQLite backup into a NEW isolated file only. Never changes application settings.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True)
        parser.add_argument('--destination', required=True)
        parser.add_argument('--timeout', type=int, default=60)

    def handle(self, *args, **options):
        try:
            report = snapshot(options['source'], options['destination'], restore=True, timeout=options['timeout'])
        except BackupError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS(f"Verified isolated restore: {report['destination']}"))
        self.stdout.write('Application database configuration is unchanged. Do not start workers against this recovery copy.')
