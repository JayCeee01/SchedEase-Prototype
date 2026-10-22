from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schedules", "0004_full_workbook_support")]
    operations = [
        migrations.AddConstraint(
            model_name="availability",
            constraint=models.CheckConstraint(
                check=(models.Q(("faculty__isnull", False), ("room__isnull", True)) |
                       models.Q(("faculty__isnull", True), ("room__isnull", False))),
                name="availability_exactly_one_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="scheduleentry",
            constraint=models.UniqueConstraint(fields=("schedule", "assignment"), name="unique_schedule_assignment"),
        ),
    ]
