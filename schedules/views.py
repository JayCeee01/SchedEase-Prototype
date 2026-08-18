import csv
import logging
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .forms import EmailOrUsernameAuthenticationForm, MODEL_FORMS, ScheduleEntryFilterForm, ScheduleEntryForm, ScheduleGenerationForm, ScheduleSearchForm
from .models import (
    AcademicTerm,
    Availability,
    Credential,
    CredentialOverride,
    Department,
    Faculty,
    FacultyCredential,
    GASettings,
    GenerationIssue,
    GenerationRun,
    Program,
    Role,
    Room,
    RoomKind,
    Schedule,
    ScheduleEntry,
    ScheduleStatus,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    YearLevel,
)
from .services.conflicts import conflict_messages, schedule_validation_messages
from .services.credentials import faculty_qualification, missing_credential_message
from .services.ga import GeneticScheduler
from .services.generation_issues import record_generation_messages, record_unexpected_failure
from .services.room_utilization import filtered_rows, utilization_rows, utilization_summary

logger = logging.getLogger(__name__)

RESOURCE_MODELS = {
    "departments": Department,
    "programs": Program,
    "year-levels": YearLevel,
    "sections": Section,
    "subjects": Subject,
    "credentials": Credential,
    "faculty-credentials": FacultyCredential,
    "subject-credential-requirements": SubjectCredentialRequirement,
    "faculty": Faculty,
    "students": Student,
    "rooms": Room,
    "terms": AcademicTerm,
    "assignments": TeachingAssignment,
    "availability": Availability,
    "ga-settings": GASettings,
    "schedules": Schedule,
    "credential-overrides": CredentialOverride,
}

RESOURCE_DESCRIPTIONS = {
    "departments": "Maintain college departments that own programs, subjects, faculty, and sections.",
    "programs": "Manage academic programs and connect them to their departments.",
    "year-levels": "Define year levels used when organizing sections and student schedules.",
    "sections": "Track section size, program, year level, and advising assignments.",
    "subjects": "Configure subject hours, units, and room requirements used by the generator.",
    "credentials": "Create the exact credential names used for faculty qualification matching.",
    "faculty-credentials": "Assign credentials to faculty members for teaching eligibility checks.",
    "subject-credential-requirements": "Define the required credential for each subject and explicitly allowed equivalents.",
    "faculty": "Manage faculty records and workload details.",
    "students": "Manage student records and section membership.",
    "rooms": "Maintain room capacity, availability, and specialized room types.",
    "terms": "Configure academic terms for schedule generation and publishing.",
    "assignments": "Assign faculty to subjects and sections before schedule generation.",
    "availability": "Define preferred, available, and unavailable time windows for faculty or rooms.",
    "ga-settings": "Adjust how schedules are created and improved.",
    "schedules": "Review, edit, publish, and delete generated schedule records.",
    "credential-overrides": "Audit admin-approved exceptions for unqualified faculty assignments.",
}


def role(user):
    return getattr(getattr(user, "profile", None), "role", None)


def admin_required(user):
    return user.is_authenticated and (user.is_superuser or role(user) == Role.ADMIN)


def faculty_required(user):
    return user.is_authenticated and role(user) == Role.FACULTY


def resource_model(resource):
    try:
        return RESOURCE_MODELS[resource]
    except KeyError as exc:
        raise Http404("Unknown administrative resource.") from exc


def visible_schedule(request, pk):
    schedules = Schedule.objects.all()
    if not admin_required(request.user):
        schedules = schedules.filter(status=ScheduleStatus.PUBLISHED)
    return get_object_or_404(schedules, pk=pk)


def landing_page(request):
    login_form = EmailOrUsernameAuthenticationForm(request, data=request.POST or None)
    login_modal_open = False
    if request.method == "POST":
        login_modal_open = True
        if login_form.is_valid():
            auth_login(request, login_form.get_user())
            if not request.POST.get("remember_me"):
                request.session.set_expiry(0)
            return redirect("dashboard")
    else:
        login_form = EmailOrUsernameAuthenticationForm(request)
    return render(request, "landing.html", {"login_form": login_form, "login_modal_open": login_modal_open})


@login_required
def dashboard(request):
    schedules = Schedule.objects.all()[:5]
    user_role = role(request.user)
    context = {"schedules": schedules, "user_role": user_role}
    if admin_required(request.user):
        latest = Schedule.objects.first()
        latest_entries = latest.entries.count() if latest else 0
        latest_requirements = latest.term.teachingassignment_set.count() if latest else 0
        utilization = utilization_summary(utilization_rows(latest)) if latest else {"average_utilization": 0}
        context.update(
            {
                "counts": {
                    "departments": Department.objects.count(),
                    "faculty": Faculty.objects.count(),
                    "sections": Section.objects.count(),
                    "subjects": Subject.objects.count(),
                    "rooms": Room.objects.filter(is_active=True).count(),
                    "scheduled classes": latest_entries,
                    "unscheduled classes": max(0, latest_requirements - latest_entries),
                    "schedule issues": len(schedule_validation_messages(latest)) if latest else 0,
                    "average room utilization": f"{utilization['average_utilization']}%",
                }
            }
        )
        return render(request, "schedules/admin_dashboard.html", context)
    if user_role == Role.FACULTY:
        faculty = Faculty.objects.filter(user=request.user).first()
        context["entries"] = ScheduleEntry.objects.filter(assignment__faculty=faculty, schedule__status=ScheduleStatus.PUBLISHED)
        context["availability"] = Availability.objects.filter(faculty=faculty)
        return render(request, "schedules/faculty_dashboard.html", context)
    student = Student.objects.filter(user=request.user).select_related("section").first()
    context["student"] = student
    context["entries"] = ScheduleEntry.objects.filter(assignment__section=getattr(student, "section", None), schedule__status=ScheduleStatus.PUBLISHED)
    return render(request, "schedules/student_dashboard.html", context)


@login_required
def browse_schedules(request):
    form = ScheduleSearchForm(request.GET or None)
    entries = ScheduleEntry.objects.filter(schedule__status=ScheduleStatus.PUBLISHED).select_related(
        "schedule__term",
        "assignment__subject__department",
        "assignment__section__program__department",
        "assignment__section__year_level",
        "assignment__faculty",
        "room",
    )
    if form.is_valid():
        term = form.cleaned_data.get("term")
        department = form.cleaned_data.get("department")
        program = form.cleaned_data.get("program")
        year_level = form.cleaned_data.get("year_level")
        section = form.cleaned_data.get("section")
        subject = form.cleaned_data.get("subject")
        if term:
            entries = entries.filter(schedule__term=term)
        if department:
            entries = entries.filter(assignment__section__program__department=department)
        if program:
            entries = entries.filter(assignment__section__program=program)
        if year_level:
            entries = entries.filter(assignment__section__year_level=year_level)
        if section:
            entries = entries.filter(assignment__section=section)
        if subject:
            entries = entries.filter(assignment__subject=subject)
    return render(request, "schedules/browse.html", {"form": form, "entries": entries})


@login_required
@user_passes_test(faculty_required)
def my_availability(request):
    faculty = get_object_or_404(Faculty, user=request.user)
    return render(request, "schedules/my_availability.html", {"availability": Availability.objects.filter(faculty=faculty)})


@login_required
@user_passes_test(faculty_required)
def my_availability_create(request):
    faculty = get_object_or_404(Faculty, user=request.user)
    form_class = MODEL_FORMS["availability"]
    form = form_class(request.POST or None)
    form.fields["faculty"].initial = faculty
    form.fields["faculty"].disabled = True
    form.fields["room"].disabled = True
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.faculty = faculty
        item.room = None
        item.save()
        messages.success(request, "Availability saved.")
        return redirect("my_availability")
    return render(request, "schedules/form.html", {"form": form, "title": "Add Availability", "tooltip_context": "availability"})


@login_required
@user_passes_test(faculty_required)
def my_availability_update(request, pk):
    faculty = get_object_or_404(Faculty, user=request.user)
    item = get_object_or_404(Availability, pk=pk, faculty=faculty)
    form_class = MODEL_FORMS["availability"]
    form = form_class(request.POST or None, instance=item)
    form.fields["faculty"].disabled = True
    form.fields["room"].disabled = True
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.faculty = faculty
        item.room = None
        item.save()
        messages.success(request, "Availability updated.")
        return redirect("my_availability")
    return render(request, "schedules/form.html", {"form": form, "title": "Edit Availability", "tooltip_context": "availability"})


@login_required
@user_passes_test(admin_required)
def resource_list(request, resource):
    model = resource_model(resource)
    return render(request, "schedules/resource_list.html", {"resource": resource, "objects": model.objects.all()[:200], "description": RESOURCE_DESCRIPTIONS.get(resource, "Manage records for this section.")})


@login_required
@user_passes_test(admin_required)
def room_utilization_dashboard(request):
    rows = utilization_rows()
    rows = filtered_rows(
        rows,
        query=request.GET.get("q", ""),
        room_type=request.GET.get("room_type", ""),
        utilization_range=request.GET.get("utilization", ""),
    )
    context = {
        "rows": rows,
        "summary": utilization_summary(rows),
        "room_types": RoomKind.choices,
        "selected_room_type": request.GET.get("room_type", ""),
        "selected_utilization": request.GET.get("utilization", ""),
        "query": request.GET.get("q", ""),
    }
    return render(request, "schedules/room_utilization.html", context)


@login_required
@user_passes_test(admin_required)
def export_room_utilization_csv(request):
    rows = filtered_rows(
        utilization_rows(),
        query=request.GET.get("q", ""),
        room_type=request.GET.get("room_type", ""),
        utilization_range=request.GET.get("utilization", ""),
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="room-utilization.csv"'
    writer = csv.writer(response)
    writer.writerow(["Room Name", "Room Type", "Room Capacity", "Available Hours", "Scheduled Hours", "Utilization %", "Assigned Classes", "Status", "Last Updated"])
    for row in rows:
        writer.writerow([
            row.room.name,
            row.room.get_room_type_display(),
            row.room.capacity,
            row.available_hours,
            row.scheduled_hours,
            row.utilization_percentage,
            row.assigned_classes,
            row.status,
            row.last_updated,
        ])
    return response


@login_required
@user_passes_test(admin_required)
def export_room_utilization_pdf(request):
    rows = filtered_rows(
        utilization_rows(),
        query=request.GET.get("q", ""),
        room_type=request.GET.get("room_type", ""),
        utilization_range=request.GET.get("utilization", ""),
    )
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="room-utilization.pdf"'
    pdf = canvas.Canvas(response, pagesize=letter)
    pdf.drawString(40, 750, "SchedEase Room Utilization Report")
    y = 720
    for row in rows:
        pdf.drawString(
            40,
            y,
            f"{row.room.name} | {row.room.get_room_type_display()} | {row.utilization_percentage}% | {row.status} | {row.scheduled_hours}/{row.available_hours} hrs",
        )
        y -= 18
        if y < 50:
            pdf.showPage()
            y = 750
    pdf.save()
    return response


@login_required
@user_passes_test(admin_required)
def resource_create(request, resource):
    resource_model(resource)
    form_class = MODEL_FORMS[resource]
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if resource == "assignments":
            return save_assignment_with_credential_check(request, form, resource)
        form.save()
        messages.success(request, "Record created.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/form.html", {"form": form, "title": f"New {resource.replace('-', ' ')}", "description": RESOURCE_DESCRIPTIONS.get(resource, "Create a new record."), "tooltip_context": resource})


@login_required
@user_passes_test(admin_required)
def resource_update(request, resource, pk):
    model = resource_model(resource)
    obj = get_object_or_404(model, pk=pk)
    form = MODEL_FORMS[resource](request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        if resource == "assignments":
            return save_assignment_with_credential_check(request, form, resource)
        form.save()
        messages.success(request, "Record updated.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/form.html", {"form": form, "title": f"Edit {obj}", "description": RESOURCE_DESCRIPTIONS.get(resource, "Update this record."), "tooltip_context": resource})


def save_assignment_with_credential_check(request, form, resource):
    assignment = form.save(commit=False)
    result = faculty_qualification(assignment.faculty, assignment.subject)
    if result["qualified"]:
        assignment.save()
        form.save_m2m()
        messages.success(request, "Teaching assignment saved.")
        return redirect("resource_list", resource=resource)

    if request.POST.get("credential_override_confirm") == "yes":
        reason = request.POST.get("credential_override_reason", "").strip()
        if not reason:
            messages.error(request, "Override reason is required.")
            return render_credential_override_confirmation(request, form, result)
        with transaction.atomic():
            assignment.save()
            form.save_m2m()
            CredentialOverride.objects.create(
                assignment=assignment,
                subject=assignment.subject,
                faculty=assignment.faculty,
                admin_user=request.user,
                reason=reason,
                missing_credentials=missing_credential_message(assignment.faculty, assignment.subject),
            )
        messages.warning(request, "Teaching assignment saved with a credential override.")
        return redirect("resource_list", resource=resource)

    return render_credential_override_confirmation(request, form, result)


def render_credential_override_confirmation(request, form, result):
    obj = form.save(commit=False)
    assignment = obj if hasattr(obj, "subject") else obj.assignment
    return render(
        request,
        "schedules/credential_override_confirm.html",
        {
            "form": form,
            "assignment": assignment,
            "missing": result["missing"],
            "posted": request.POST,
        },
    )


@login_required
@user_passes_test(admin_required)
def resource_delete(request, resource, pk):
    model = resource_model(resource)
    obj = get_object_or_404(model, pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Record deleted.")
        except ProtectedError:
            messages.error(request, "This record is still used by other scheduling data and cannot be deleted. Remove or reassign those references first.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/confirm_delete.html", {"resource": resource, "object": obj})


@login_required
@user_passes_test(admin_required)
def generate_schedule(request):
    form = ScheduleGenerationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        term = form.cleaned_data["term"]
        lock_key = f"schedease-generation-term-{term.pk}"
        if not cache.add(lock_key, request.user.pk, timeout=3600):
            form.add_error(None, "A schedule is already being generated for this term. Please wait for it to finish.")
            messages.warning(request, "Generation is already in progress for the selected term.")
            return render(request, "schedules/form.html", {"form": form, "title": "Generate Schedule", "tooltip_context": "generate-schedule"})
        run = GenerationRun.objects.create(
            term=term,
            ga_settings=form.cleaned_data["settings"],
            requested_by=request.user,
            requested_name=form.cleaned_data["name"],
        )
        try:
            scheduler = GeneticScheduler(term, form.cleaned_data["settings"])
            schedule = scheduler.generate(form.cleaned_data["name"])
        except ValueError as exc:
            record_generation_messages(run, str(exc))
            run.status = GenerationRun.Status.FAILED
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at"])
            form.add_error(None, "Schedule generation could not be completed. Review the Error Log for complete details and suggested actions.")
            messages.error(request, "Schedule generation could not be completed. Please check the Error Log for more information.")
            return render(request, "schedules/form.html", {"form": form, "title": "Generate Schedule", "tooltip_context": "generate-schedule", "error_run": run})
        except Exception:
            logger.exception("Unexpected schedule generation failure for term %s", term.pk)
            record_unexpected_failure(run)
            run.status = GenerationRun.Status.FAILED
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at"])
            form.add_error(None, "Schedule generation could not be completed. Review the Error Log for complete details and suggested actions.")
            messages.error(request, "Schedule generation could not be completed. Please check the Error Log for more information.")
            return render(request, "schedules/form.html", {"form": form, "title": "Generate Schedule", "tooltip_context": "generate-schedule", "error_run": run})
        finally:
            cache.delete(lock_key)
        run.schedule = schedule
        run.status = GenerationRun.Status.SUCCEEDED
        run.completed_at = timezone.now()
        run.save(update_fields=["schedule", "status", "completed_at"])
        messages.success(request, f"Schedule generated with fitness score {schedule.fitness_score:.2f}.")
        return redirect("schedule_detail", pk=schedule.pk)
    return render(request, "schedules/form.html", {"form": form, "title": "Generate Schedule", "tooltip_context": "generate-schedule"})


@login_required
@user_passes_test(admin_required)
def generation_error_log(request):
    issues = GenerationIssue.objects.select_related(
        "run__term", "assignment__subject", "assignment__section", "assignment__faculty", "room"
    )
    filters = {
        "run": "run_id", "term": "run__term_id", "category": "category", "severity": "severity",
        "subject": "assignment__subject_id", "section": "assignment__section_id",
        "faculty": "assignment__faculty_id", "room": "room_id", "status": "status",
    }
    for parameter, lookup in filters.items():
        value = request.GET.get(parameter, "").strip()
        if value:
            issues = issues.filter(**{lookup: value})
    date_value = request.GET.get("date", "").strip()
    if date_value:
        issues = issues.filter(created_at__date=date_value)
    search = request.GET.get("q", "").strip()
    if search:
        issues = issues.filter(
            Q(short_description__icontains=search) | Q(reason__icontains=search)
            | Q(assignment__subject__code__icontains=search) | Q(assignment__subject__title__icontains=search)
            | Q(assignment__section__name__icontains=search) | Q(assignment__faculty__full_name__icontains=search)
            | Q(room__name__icontains=search)
        )
    summary_source = issues
    summary = {
        "total": summary_source.count(),
        "critical": summary_source.filter(severity=GenerationIssue.Severity.CRITICAL).count(),
        "errors": summary_source.filter(severity=GenerationIssue.Severity.ERROR).count(),
        "warnings": summary_source.filter(severity=GenerationIssue.Severity.WARNING).count(),
        "unscheduled": summary_source.filter(category=GenerationIssue.Category.UNSCHEDULED).count(),
    }
    return render(request, "schedules/error_log.html", {
        "issues": issues[:500], "summary": summary,
        "runs": GenerationRun.objects.select_related("term")[:100], "terms": AcademicTerm.objects.all(),
        "categories": GenerationIssue.Category.choices, "severities": GenerationIssue.Severity.choices,
        "statuses": GenerationIssue.Status.choices, "subjects": Subject.objects.all(), "sections": Section.objects.all(),
        "faculty_list": Faculty.objects.all(), "rooms": Room.objects.all(),
    })


@login_required
@user_passes_test(admin_required)
def generation_error_detail(request, pk):
    issue = get_object_or_404(GenerationIssue.objects.select_related(
        "run__term", "run__ga_settings", "run__schedule", "assignment__subject",
        "assignment__section", "assignment__faculty", "room"
    ), pk=pk)
    if request.method == "POST":
        status = request.POST.get("status")
        if status in GenerationIssue.Status.values:
            issue.status = status
            issue.save(update_fields=["status", "updated_at"])
            messages.success(request, "Issue status updated.")
            return redirect("generation_error_detail", pk=issue.pk)
    return render(request, "schedules/error_detail.html", {"issue": issue, "statuses": GenerationIssue.Status.choices})


@login_required
def schedule_detail(request, pk):
    schedule = visible_schedule(request, pk)
    entries = schedule.entries.select_related(
        "assignment__subject__department", "assignment__faculty",
        "assignment__section__program__department", "assignment__section__year_level", "room",
    )
    filter_form = ScheduleEntryFilterForm(request.GET or None)
    if filter_form.is_valid():
        values = filter_form.cleaned_data
        if values.get("department"):
            entries = entries.filter(assignment__section__program__department=values["department"])
        if values.get("program"):
            entries = entries.filter(assignment__section__program=values["program"])
        if values.get("year_level"):
            entries = entries.filter(assignment__section__year_level=values["year_level"])
        if values.get("section"):
            entries = entries.filter(assignment__section=values["section"])
        if values.get("faculty"):
            entries = entries.filter(assignment__faculty=values["faculty"])
        if values.get("room"):
            entries = entries.filter(room=values["room"])
        if values.get("day") != "" and values.get("day") is not None:
            entries = entries.filter(day=values["day"])
        if values.get("component"):
            entries = entries.filter(assignment__component=values["component"])
        search = values.get("q", "").strip()
        if search:
            entries = entries.filter(
                Q(assignment__section__name__icontains=search)
                | Q(assignment__section__program__code__icontains=search)
                | Q(assignment__subject__code__icontains=search)
                | Q(assignment__subject__title__icontains=search)
                | Q(assignment__faculty__full_name__icontains=search)
                | Q(room__name__icontains=search)
            )
    entries = list(entries.order_by(
        "assignment__section__program__code", "assignment__section__year_level__level",
        "assignment__section__name", "assignment__subject__code", "assignment__component", "day", "start_time",
    ))
    return render(request, "schedules/schedule_detail.html", {
        "schedule": schedule, "entries": entries, "filter_form": filter_form,
        "conflicts": schedule_validation_messages(schedule), "can_manage": admin_required(request.user),
    })


@login_required
@user_passes_test(admin_required)
def entry_create(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    if schedule.status == ScheduleStatus.PUBLISHED:
        messages.error(request, "Published schedules are locked. Create or regenerate a draft version before making changes.")
        return redirect("schedule_detail", pk=pk)
    form = ScheduleEntryForm(request.POST or None)
    form.fields["assignment"].queryset = TeachingAssignment.objects.filter(term=schedule.term)
    if request.method == "POST" and form.is_valid():
        return save_entry_with_credential_check(request, form, schedule)
    return render(request, "schedules/form.html", {"form": form, "title": "Add Schedule Entry", "tooltip_context": "schedule-entry"})


@login_required
@user_passes_test(admin_required)
def entry_update(request, pk, entry_pk):
    entry = get_object_or_404(ScheduleEntry, pk=entry_pk, schedule_id=pk)
    if entry.schedule.status == ScheduleStatus.PUBLISHED:
        messages.error(request, "Published schedules are locked. Create or regenerate a draft version before making changes.")
        return redirect("schedule_detail", pk=pk)
    form = ScheduleEntryForm(request.POST or None, instance=entry)
    form.fields["assignment"].queryset = TeachingAssignment.objects.filter(term=entry.schedule.term)
    if request.method == "POST" and form.is_valid():
        return save_entry_with_credential_check(request, form, entry.schedule)
    return render(request, "schedules/form.html", {"form": form, "title": "Edit Schedule Entry", "tooltip_context": "schedule-entry"})


def save_entry_with_credential_check(request, form, schedule):
    entry = form.save(commit=False)
    entry.schedule = schedule
    result = faculty_qualification(entry.assignment.faculty, entry.assignment.subject)
    if not result["qualified"] and not entry.assignment.credential_overrides.exists():
        if request.POST.get("credential_override_confirm") != "yes":
            return render_credential_override_confirmation(request, form, result)
        reason = request.POST.get("credential_override_reason", "").strip()
        if not reason:
            messages.error(request, "Override reason is required.")
            return render_credential_override_confirmation(request, form, result)
        CredentialOverride.objects.create(
            assignment=entry.assignment,
            subject=entry.assignment.subject,
            faculty=entry.assignment.faculty,
            admin_user=request.user,
            reason=reason,
            missing_credentials=missing_credential_message(entry.assignment.faculty, entry.assignment.subject),
        )
    try:
        entry.full_clean()
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(request, "schedules/form.html", {"form": form, "title": "Edit Schedule Entry", "description": "Resolve the validation issues before saving this schedule entry.", "tooltip_context": "schedule-entry"})
    entry.save()
    messages.success(request, "Schedule entry saved.")
    return redirect("schedule_detail", pk=schedule.pk)


@login_required
@user_passes_test(admin_required)
@require_POST
def publish_schedule(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    conflicts = schedule_validation_messages(schedule)
    if conflicts:
        messages.error(request, "Resolve conflicts before publishing.")
    else:
        schedule.status = ScheduleStatus.PUBLISHED
        schedule.published_at = timezone.now()
        schedule.save()
        messages.success(request, "Schedule published.")
    return redirect("schedule_detail", pk=pk)


@login_required
def export_csv(request, pk):
    schedule = visible_schedule(request, pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{schedule.name}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Day", "Start", "End", "Subject", "Section", "Faculty", "Room"])
    for e in schedule.entries.select_related("assignment__subject", "assignment__section", "assignment__faculty", "room"):
        writer.writerow([e.get_day_display(), e.start_time, e.end_time, e.assignment.subject.code, e.assignment.section, e.assignment.faculty, e.room.name])
    return response


@login_required
def export_pdf(request, pk):
    schedule = visible_schedule(request, pk)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{schedule.name}.pdf"'
    pdf = canvas.Canvas(response, pagesize=letter)
    pdf.drawString(40, 750, schedule.name)
    y = 720
    for e in schedule.entries.select_related("assignment__subject", "assignment__section", "assignment__faculty", "room"):
        pdf.drawString(40, y, f"{e.get_day_display()} {e.start_time}-{e.end_time} {e.assignment.subject.code} {e.assignment.section} {e.assignment.faculty} {e.room.name}")
        y -= 18
        if y < 50:
            pdf.showPage()
            y = 750
    pdf.save()
    return response
