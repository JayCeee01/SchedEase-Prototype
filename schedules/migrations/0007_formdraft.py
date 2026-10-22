import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schedules", "0006_generationrun_generationissue"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("resource", models.CharField(max_length=80)),
                ("object_pk", models.CharField(blank=True, max_length=80)),
                ("payload", models.JSONField(default=dict)),
                ("base_signature", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="form_drafts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddConstraint(
            model_name="formdraft",
            constraint=models.UniqueConstraint(fields=("user", "resource", "object_pk"), name="unique_user_form_draft"),
        ),
    ]
