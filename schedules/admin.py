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
    CredentialOverride,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    Program,
    Profile,
    Room,
    Schedule,
    ScheduleEntryAudit,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
]:
    admin.site.register(model, ProtectedScheduleAdmin)
