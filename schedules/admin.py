from django.contrib import admin
from .auth_forms import LimitedAdminAuthenticationForm

admin.site.login_form = LimitedAdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from .protection import protected, MESSAGE
from .models import (
    CurriculumVersion,
    CurriculumSubjectRequirement,
    SubjectOffering,
    DeliveryPlan,
    DeliveryComponent,
    AcademicPathway,
    Cohort,
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


@admin.register(CurriculumSubjectRequirement)
class CurriculumRequirementAdmin(ProtectedScheduleAdmin):
    list_display = ("subject", "curriculum_version", "grade_level", "academic_period", "verification_status", "is_active", "effective_approval")
    list_filter = ("verification_status", "is_active", "grade_level")
    readonly_fields = ("effective_approval",)

    @admin.display(boolean=True, description="Currently approved configuration")
    def effective_approval(self, obj):
        return obj.approved_for_configuration


@admin.register(SubjectOffering)
class SubjectOfferingAdmin(ProtectedScheduleAdmin):
    list_display = ("requirement", "cohort", "academic_term", "is_approved", "effective_approval")
    list_filter = ("is_approved", "academic_term")
    readonly_fields = ("effective_approval",)

    @admin.display(boolean=True, description="Currently approved configuration")
    def effective_approval(self, obj):
        return obj.approved_for_configuration


@admin.register(DeliveryPlan)
class DeliveryPlanAdmin(ProtectedScheduleAdmin):
    list_display = ("offering", "effective_status", "planned_minutes", "approved_by", "approved_at")
    list_filter = ("is_approved",)
    readonly_fields = ("effective_status", "planned_minutes", "approved_by", "approved_at")

    def save_model(self, request, obj, form, change):
        from django.utils import timezone
        if obj.is_approved and (not change or "is_approved" in form.changed_data):
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        elif not obj.is_approved:
            obj.approved_by = None
            obj.approved_at = None
        super().save_model(request, obj, form, change)


@admin.register(DeliveryComponent)
class DeliveryComponentAdmin(ProtectedScheduleAdmin):
    list_display = ("plan", "position", "instruction", "duration_minutes", "meeting_count")
    list_filter = ("plan",)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or not obj.plan.is_approved)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or not obj.plan.is_approved)

    def delete_queryset(self, request, queryset):
        if queryset.filter(plan__is_approved=True).exists():
            raise ValidationError("Return the delivery plan to draft before deleting its components.")
        super().delete_queryset(request, queryset)


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


from .forms import StudentForm


@admin.register(Student)
class StudentAdmin(ProtectedScheduleAdmin):
    form = StudentForm


for model in [
    CurriculumVersion,
    AcademicPathway,
    Cohort,
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
