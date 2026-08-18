import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schedules", "0005_integrity_constraints"),
    ]

    operations = [
        migrations.CreateModel(
            name="GenerationRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("requested_name", models.CharField(max_length=120)),
                ("status", models.CharField(choices=[("RUNNING", "Running"), ("SUCCEEDED", "Succeeded"), ("SUCCEEDED_WITH_ISSUES", "Succeeded with issues"), ("FAILED", "Failed")], default="RUNNING", max_length=30)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("requested_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="schedule_generation_runs", to=settings.AUTH_USER_MODEL)),
                ("schedule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generation_runs", to="schedules.schedule")),
                ("ga_settings", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generation_runs", to="schedules.gasettings")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generation_runs", to="schedules.academicterm")),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="GenerationIssue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("FACULTY_CONFLICT", "Faculty Conflict"), ("ROOM_CONFLICT", "Room Conflict"), ("SECTION_CONFLICT", "Section Conflict"), ("FACULTY_UNAVAILABLE", "Faculty Unavailable"), ("ROOM_UNAVAILABLE", "Room Unavailable"), ("ROOM_CAPACITY", "Room Capacity"), ("ROOM_TYPE", "Room Type Requirement"), ("FACULTY_CREDENTIAL", "Faculty Credential Requirement"), ("FACULTY_WORKLOAD", "Faculty Workload"), ("INVALID_DURATION", "Invalid Class Duration"), ("NO_SLOT", "No Available Time Slot"), ("UNSCHEDULED", "Unscheduled Class"), ("INVALID_DATA", "Invalid Input/Data"), ("GENERATION_FAILURE", "Generation Failure"), ("OTHER", "Other")], max_length=40)),
                ("severity", models.CharField(choices=[("INFO", "Info"), ("WARNING", "Warning"), ("ERROR", "Error"), ("CRITICAL", "Critical")], default="ERROR", max_length=12)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("REVIEWED", "Reviewed"), ("RESOLVED", "Resolved")], default="OPEN", max_length=12)),
                ("short_description", models.CharField(max_length=240)),
                ("reason", models.TextField()),
                ("suggested_action", models.TextField()),
                ("day", models.PositiveSmallIntegerField(blank=True, choices=[(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday")], null=True)),
                ("start_time", models.TimeField(blank=True, null=True)),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generation_issues", to="schedules.teachingassignment")),
                ("room", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generation_issues", to="schedules.room")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="issues", to="schedules.generationrun")),
            ],
            options={"ordering": ["-created_at", "id"]},
        ),
    ]
