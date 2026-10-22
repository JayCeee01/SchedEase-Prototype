from django.core.management.base import BaseCommand, CommandError
from schedules.benchmark_reports.report import generate_report


class Command(BaseCommand):
    help = 'Generate offline evaluation tables and figures from existing benchmark JSON/CSV exports.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('inputs', nargs='+', help='Existing Task 5.3 JSON/CSV exports.')
        parser.add_argument('--output', required=True, help='New report directory; never overwritten.')

    def handle(self, *args, **options):
        try:
            report = generate_report(options['inputs'], options['output'])
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Reported {report['total_trials']} trials in {len(report['groups'])} groups; "
            f"removed {report['duplicates_removed']} duplicate copies. Output: {options['output']}"))
