import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from schedules.models import AcademicTerm, Schedule
from schedules.services.schedule_comparison import compare_schedules


class Command(BaseCommand):
    help = "Compare the imported original tertiary schedule with the latest feasible generated schedule."

    def add_arguments(self, parser):
        parser.add_argument("--report", default="full_workbook_report/schedule_comparison.json")
        parser.add_argument("--failure-reason", default="")

    def handle(self, *args, **options):
        term = AcademicTerm.objects.filter(name="Second Term - Full Workbook", school_year="2025-2026").first()
        if not term:
            raise CommandError("The full workbook term has not been imported.")
        original = Schedule.objects.filter(term=term, origin=Schedule.Origin.IMPORTED).order_by("-id").first()
        if not original:
            raise CommandError("The imported original schedule was not found.")
        generated = Schedule.objects.filter(term=term, origin=Schedule.Origin.GENERATED).order_by("-id").first()
        result = compare_schedules(term, original, generated, options["failure_reason"])
        path = Path(options["report"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Comparison written to {path.resolve()}"))
        self.stdout.write(f"Status={result['generation_status']}; scheduled={result['successfully_scheduled_classes']}; unscheduled={result['unscheduled_classes']}")
