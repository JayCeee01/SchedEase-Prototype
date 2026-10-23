from django.contrib import admin
from .auth_forms import LimitedAdminAuthenticationForm

admin.site.login_form = LimitedAdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from .protection import protected, MESSAGE
from .models import (
    AcademicTerm,
    Assignment,
    Availability,
    Credential,
    CredentialOverride,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    Program,
    Profile,
    Room,
    Schedule,
    ScheduleEntry,
    ScheduleEntryAudit,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
)


class AdministratorPermissionMixin:
    """The application role supplements, never replaces, Django permissions."""
    @staticmethod
    def authorized(request):
        from .views import admin_required
        return admin_required(request.user)

    def has_module_permission(self, request):
        return self.authorized(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.authorized(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self.authorized(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.authorized(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.authorized(request) and super().has_delete_permission(request, obj)


class ProtectedScheduleAdmin(AdministratorPermissionMixin, admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or not protected(obj))

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and protected(obj):
            return tuple(field.name for field in obj._meta.fields)
        return super().get_readonly_fields(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is not None and protected(obj):
            class ProtectedForm(form):
                def clean(self):
                    super().clean()
                    raise ValidationError(MESSAGE)
            return ProtectedForm
        return form


class DiagnosticRecordAdmin(ProtectedScheduleAdmin):
    pass


class WorkflowReadOnlyAdmin(DiagnosticRecordAdmin):
    """Use application services for changes requiring revisions or audit creation."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ScheduleEntryAudit, WorkflowReadOnlyAdmin)


@admin.register(CredentialOverride)
class CredentialOverrideAdmin(DiagnosticRecordAdmin):
    readonly_fields = ('admin_user',)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.admin_user = request.user
        super().save_model(request, obj, form, change)


@admin.register(Schedule)
class ScheduleAdmin(ProtectedScheduleAdmin):
    fields = ('term', 'name', 'status', 'origin', 'fitness_score', 'published_at', 'archived_at', 'replaced_by')
    readonly_fields = ('status', 'origin', 'fitness_score', 'published_at', 'archived_at', 'replaced_by')


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(WorkflowReadOnlyAdmin):
    list_display = ("assignment", "room", "day", "start_time", "end_time", "schedule")
    list_filter = ("schedule", "day", "room")
    search_fields = ("assignment__subject__code", "assignment__section__name", "room__name")


for model in [
    AcademicTerm,
    Assignment,
    Availability,
    Credential,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    Program,
    Profile,
    Room,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
]:
    admin.site.register(model, ProtectedScheduleAdmin)


# Staff status/model permissions alone must not open an alternate role-escalation
# path through Django's built-in identity administration.
class ApplicationUserAdmin(AdministratorPermissionMixin, UserAdmin):
    pass


class ApplicationGroupAdmin(AdministratorPermissionMixin, GroupAdmin):
    pass


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, ApplicationUserAdmin)
admin.site.register(Group, ApplicationGroupAdmin)
