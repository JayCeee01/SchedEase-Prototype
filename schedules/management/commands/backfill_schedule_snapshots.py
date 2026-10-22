from django.core.management.base import BaseCommand
from schedules.models import ScheduleSnapshot
from schedules.services.history import backfill_snapshots


class Command(BaseCommand):
    help = "Reconstruct missing finalized snapshots without overwriting existing history."

    def handle(self, *args, **options):
        count = backfill_snapshots()
        self.stdout.write(f"Created {count} reconstructed snapshot(s). Existing snapshots were unchanged.")
        for snapshot in ScheduleSnapshot.objects.filter(reconstructed=True).order_by('schedule_id'):
            warnings = [name for name, present in snapshot.data['warnings'].items() if present]
            if snapshot.data['publication'] is None:
                warnings.append('original_publication_actor_unknown')
            if any(row['missing_related_data'] for row in snapshot.data['entries']):
                warnings.append('missing_related_data')
            self.stdout.write(f"Schedule {snapshot.schedule_id}: reconstructed; " +
                              (', '.join(warnings) if warnings else 'original values cannot be independently verified'))
