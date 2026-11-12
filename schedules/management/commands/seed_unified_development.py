from django.core.management.base import BaseCommand
from schedules.services.unified_development import seed_representative_data


class Command(BaseCommand):
    help = 'Add idempotent fictional proposals ONLY to unified_schedease.sqlite3; never approves SHS data.'
    requires_system_checks = []

    def handle(self, *args, **options):
        self.stdout.write(seed_representative_data())
