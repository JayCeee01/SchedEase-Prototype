from django.contrib import admin
from .models import (
    AcademicTerm,
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
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
)


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(admin.ModelAdmin):
    list_display = ("assignment", "room", "day", "start_time", "end_time", "schedule")
    list_filter = ("schedule", "day", "room")
    search_fields = ("assignment__subject__code", "assignment__section__name", "room__name")


for model in [
    AcademicTerm,
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
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
]:
    admin.site.register(model)
