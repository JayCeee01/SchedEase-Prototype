import csv
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .forms import MODEL_FORMS, ScheduleEntryForm, ScheduleGenerationForm, ScheduleSearchForm
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
    Role,
    Room,
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
from .services.conflicts import conflict_messages
from .services.credentials import faculty_qualification, missing_credential_message
from .services.ga import GeneticScheduler

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


@login_required
def dashboard(request):
    schedules = Schedule.objects.all()[:5]
    user_role = role(request.user)
    context = {"schedules": schedules, "user_role": user_role}
    if admin_required(request.user):
        context.update(
            {
                "counts": {
                    "departments": Department.objects.count(),
                    "faculty": Faculty.objects.count(),
                    "sections": Section.objects.count(),
                    "assignments": TeachingAssignment.objects.count(),
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
    return render(request, "schedules/form.html", {"form": form, "title": "Add Availability"})


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
    return render(request, "schedules/form.html", {"form": form, "title": "Edit Availability"})


@login_required
@user_passes_test(admin_required)
def resource_list(request, resource):
    model = RESOURCE_MODELS[resource]
    return render(request, "schedules/resource_list.html", {"resource": resource, "objects": model.objects.all()[:200], "description": RESOURCE_DESCRIPTIONS.get(resource, "Manage records for this section.")})


@login_required
@user_passes_test(admin_required)
def resource_create(request, resource):
    form_class = MODEL_FORMS[resource]
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if resource == "assignments":
            return save_assignment_with_credential_check(request, form, resource)
        form.save()
        messages.success(request, "Record created.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/form.html", {"form": form, "title": f"New {resource.replace('-', ' ')}", "description": RESOURCE_DESCRIPTIONS.get(resource, "Create a new record.")})


@login_required
@user_passes_test(admin_required)
def resource_update(request, resource, pk):
    model = RESOURCE_MODELS[resource]
    obj = get_object_or_404(model, pk=pk)
    form = MODEL_FORMS[resource](request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        if resource == "assignments":
            return save_assignment_with_credential_check(request, form, resource)
        form.save()
        messages.success(request, "Record updated.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/form.html", {"form": form, "title": f"Edit {obj}", "description": RESOURCE_DESCRIPTIONS.get(resource, "Update this record.")})


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
    model = RESOURCE_MODELS[resource]
    obj = get_object_or_404(model, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Record deleted.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/confirm_delete.html", {"resource": resource, "object": obj})


@login_required
@user_passes_test(admin_required)
def generate_schedule(request):
    form = ScheduleGenerationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        scheduler = GeneticScheduler(form.cleaned_data["term"], form.cleaned_data["settings"])
        schedule = scheduler.generate(form.cleaned_data["name"])
        messages.success(request, f"Schedule generated with fitness score {schedule.fitness_score:.2f}.")
        return redirect("schedule_detail", pk=schedule.pk)
    return render(request, "schedules/form.html", {"form": form, "title": "Generate Schedule"})


@login_required
def schedule_detail(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    entries = list(schedule.entries.select_related("assignment__subject", "assignment__faculty", "assignment__section", "room"))
    return render(request, "schedules/schedule_detail.html", {"schedule": schedule, "entries": entries, "conflicts": conflict_messages(entries)})


@login_required
@user_passes_test(admin_required)
def entry_create(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    form = ScheduleEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return save_entry_with_credential_check(request, form, schedule)
    return render(request, "schedules/form.html", {"form": form, "title": "Add Schedule Entry"})


@login_required
@user_passes_test(admin_required)
def entry_update(request, pk, entry_pk):
    entry = get_object_or_404(ScheduleEntry, pk=entry_pk, schedule_id=pk)
    form = ScheduleEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        return save_entry_with_credential_check(request, form, entry.schedule)
    return render(request, "schedules/form.html", {"form": form, "title": "Edit Schedule Entry"})


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
        return render(request, "schedules/form.html", {"form": form, "title": "Edit Schedule Entry", "description": "Resolve the validation issues before saving this schedule entry."})
    entry.save()
    messages.success(request, "Schedule entry saved.")
    return redirect("schedule_detail", pk=schedule.pk)


@login_required
@user_passes_test(admin_required)
def publish_schedule(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    conflicts = conflict_messages(list(schedule.entries.all()))
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
    schedule = get_object_or_404(Schedule, pk=pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{schedule.name}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Day", "Start", "End", "Subject", "Section", "Faculty", "Room"])
    for e in schedule.entries.select_related("assignment__subject", "assignment__section", "assignment__faculty", "room"):
        writer.writerow([e.get_day_display(), e.start_time, e.end_time, e.assignment.subject.code, e.assignment.section, e.assignment.faculty, e.room.name])
    return response


@login_required
def export_pdf(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
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
