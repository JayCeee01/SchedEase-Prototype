from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("schedules", "0002_credential_credentialoverride_facultycredential_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleentry",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
