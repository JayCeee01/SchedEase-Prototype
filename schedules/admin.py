from django.contrib import admin
from .protection import protected
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


class ProtectedScheduleAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or not protected(obj))


class DiagnosticRecordAdmin(ProtectedScheduleAdmin):
    """Audit/override diagnostics need the app role AND Django admin permissions."""
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


admin.site.register([CredentialOverride, ScheduleEntryAudit], DiagnosticRecordAdmin)


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(ProtectedScheduleAdmin):
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
    Schedule,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
]:
    admin.site.register(model, ProtectedScheduleAdmin)
