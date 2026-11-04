from django.apps import AppConfig


class SchedulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "schedules"

    def ready(self):
        from django.db.backends.signals import connection_created
        from django.db.models.signals import pre_save, pre_delete, m2m_changed
        from .identity import normalize_identity
        def register_identity(connection, **kwargs):
            if connection.vendor == "sqlite":
                connection.connection.create_function("schedease_identity_v1", 1, normalize_identity, deterministic=True)
        connection_created.connect(register_identity, weak=False, dispatch_uid="schedease_identity_connection")
        from .protection import FIELDS, before_save, before_delete, register_connection
        connection_created.connect(register_connection, dispatch_uid="schedease_integrity_connection")
        for name in FIELDS:
            model = self.get_model(name)
            pre_save.connect(before_save, sender=model, dispatch_uid=f"schedease_save_{name}")
            pre_delete.connect(before_delete, sender=model, dispatch_uid=f"schedease_delete_{name}")
        from .services import credential_approval
        connection_created.connect(credential_approval.register_connection, dispatch_uid='credential_scope_connection')
        requirement = self.get_model('SubjectCredentialRequirement')
        pre_save.connect(credential_approval.check_requirement_change, sender=requirement, dispatch_uid='credential_requirement_save')
        pre_delete.connect(credential_approval.check_requirement_delete, sender=requirement, dispatch_uid='credential_requirement_delete')
        m2m_changed.connect(credential_approval.check_equivalences, sender=requirement.acceptable_equivalents.through,
                            dispatch_uid='credential_equivalence_change')
        pre_save.connect(credential_approval.check_through_change, sender=requirement.acceptable_equivalents.through,
                         dispatch_uid='credential_equivalence_save')
        pre_delete.connect(credential_approval.check_through_delete, sender=requirement.acceptable_equivalents.through,
                           dispatch_uid='credential_equivalence_delete')
        from .services import faculty_dependencies
        for name in ('FacultyCredential', 'Availability'):
            model = self.get_model(name)
            pre_save.connect(faculty_dependencies.check_save, sender=model, dispatch_uid=f'faculty_dependency_save_{name}')
            pre_delete.connect(faculty_dependencies.check_delete, sender=model, dispatch_uid=f'faculty_dependency_delete_{name}')
        from .services import resource_dependencies
        availability = self.get_model('Availability')
        pre_save.connect(resource_dependencies.check_save, sender=availability, dispatch_uid='resource_availability_save')
        pre_delete.connect(resource_dependencies.check_delete, sender=availability, dispatch_uid='resource_availability_delete')
        from .services import shs_approval
        from .services import publication_boundary
        connection_created.connect(publication_boundary.register_connection, dispatch_uid='publication_boundary_connection')
        connection_created.connect(shs_approval.register_connection, dispatch_uid='shs_scope_connection')
        for name in shs_approval.policy.FIELDS:
            model = self.get_model(name)
            pre_save.connect(shs_approval.check_save, sender=model, dispatch_uid=f'shs_scope_save_{name}')
            pre_delete.connect(shs_approval.check_delete, sender=model, dispatch_uid=f'shs_scope_delete_{name}')
