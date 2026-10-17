from django.apps import AppConfig


class SchedulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "schedules"

    def ready(self):
        from django.db.backends.signals import connection_created
        from django.db.models.signals import pre_save, pre_delete
        from .protection import FIELDS, before_save, before_delete, register_connection
        connection_created.connect(register_connection, dispatch_uid="schedease_integrity_connection")
        for name in FIELDS:
            model = self.get_model(name)
            pre_save.connect(before_save, sender=model, dispatch_uid=f"schedease_save_{name}")
            pre_delete.connect(before_delete, sender=model, dispatch_uid=f"schedease_delete_{name}")
