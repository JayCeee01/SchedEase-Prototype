from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schedules", "0003_scheduleentry_updated_at")]
    operations = [
        migrations.RemoveConstraint(model_name="teachingassignment", name="unique_assignment"),
        migrations.AddField(model_name="teachingassignment", name="component", field=models.CharField(choices=[("GENERAL", "General"), ("LECTURE", "Lecture"), ("LABORATORY", "Laboratory")], default="GENERAL", max_length=20)),
        migrations.AddField(model_name="teachingassignment", name="meeting_index", field=models.PositiveSmallIntegerField(default=1)),
        migrations.AddField(model_name="teachingassignment", name="duration_minutes", field=models.PositiveSmallIntegerField(default=0, help_text="Per-meeting duration; zero uses the subject hours.")),
        migrations.AddField(model_name="teachingassignment", name="required_room_type_override", field=models.CharField(blank=True, choices=[("LECTURE", "Lecture Room"), ("COMPUTER_LAB", "Computer Laboratory"), ("SCIENCE_LAB", "Science Laboratory"), ("GYM", "Gym"), ("SPECIAL", "Specialized Room")], max_length=30)),
        migrations.AddField(model_name="teachingassignment", name="source_key", field=models.CharField(blank=True, db_index=True, max_length=160)),
        migrations.AddField(model_name="teachingassignment", name="source_sheet", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="teachingassignment", name="source_row", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="schedule", name="origin", field=models.CharField(choices=[("MANUAL", "Manual"), ("IMPORTED", "Imported Original"), ("GENERATED", "SchedEase Generated")], default="MANUAL", max_length=20)),
        migrations.AddConstraint(model_name="teachingassignment", constraint=models.UniqueConstraint(fields=("term", "subject", "section", "component", "meeting_index"), name="unique_assignment_meeting")),
    ]
