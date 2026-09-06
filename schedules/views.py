import csv
import json
import logging
import re
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .forms import AssignmentMeetingFormSetFactory, EmailOrUsernameAuthenticationForm, MODEL_FORMS, ScheduleEntryFilterForm, ScheduleEntryForm, ScheduleGenerationForm, ScheduleSearchForm
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
    FormDraft,
    GenerationIssue,
    GenerationRun,
    Program,
    Role,
    Room,
    RoomKind,
    Schedule,
    ScheduleEntry,
    ScheduleEntryAudit,
    ScheduleStatus,
    Section,
    Student,
    Subject,
    SubjectCredentialRequirement,
    TeachingAssignment,
    Weekday,
    YearLevel,
)
from .services.conflicts import conflict_messages, schedule_validation_messages
from .services.credentials import faculty_qualification, missing_credential_message
from .services.ga import GeneticScheduler
from .services.generation_issues import record_generation_messages, record_unexpected_failure
from .services.form_drafts import object_signature, safe_draft_payload
from .services.room_utilization import capacity_planning, filtered_rows, latest_schedule, personal_schedule_grid, room_schedule_grid, utilization_rows, utilization_summary

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
    "assignments": Assignment,
    "availability": Availability,
    "ga-settings": GASettings,
    "schedules": Schedule,
    "credential-overrides": CredentialOverride,
}

RESOURCE_DESCRIPTIONS = {
    "departments": "Maintain college departments that own programs, courses, faculty, and sections.",
    "programs": "Manage academic programs and connect them to their departments.",
    "year-levels": "Define year levels used when organizing sections and student schedules.",
    "sections": "Track section size, program, year level, and advising assignments.",
    "subjects": "Configure course hours, units, and room requirements used by the generator.",
    "credentials": "Create the exact credential names used for faculty qualification matching.",
    "faculty-credentials": "Assign credentials to faculty members for teaching eligibility checks.",
    "subject-credential-requirements": "Define the required credential for each course and explicitly allowed equivalents.",
    "faculty": "Manage faculty records and workload details.",
    "students": "Manage student records and section membership.",
    "rooms": "Maintain room capacity, availability, and specialized room types.",
    "terms": "Configure academic terms for schedule generation and publishing.",
    "assignments": "Assign faculty to courses and sections, with one or more schedulable meetings.",
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


def entries_visible_to_user(entries, user):
    """Restrict published timetable rows to the faculty member or student's section."""
    if admin_required(user):
        return entries
    if role(user) == Role.FACULTY:
        faculty = Faculty.objects.filter(user=user).first()
        if not faculty:
            return entries.none()
        return entries.filter(
            Q(faculty_override=faculty)
            | Q(faculty_override__isnull=True, assignment__faculty=faculty)
        )
    student = Student.objects.filter(user=user).select_related("section").first()
    if not student or not student.section_id:
        return entries.none()
    return entries.filter(
        Q(section_override=student.section)
        | Q(section_override__isnull=True, assignment__section=student.section)
    )


def resource_model(resource):
    try:
        return RESOURCE_MODELS[resource]
    except KeyError as exc:
        raise Http404("Unknown administrative resource.") from exc


def section_search_q(prefix, search):
    base = (
        Q(**{f"{prefix}name__icontains": search})
        | Q(**{f"{prefix}program__code__icontains": search})
    )
    full = re.fullmatch(r"\s*(\S+)\s+(\d+)-([A-Z0-9][A-Z0-9_-]*)\s*", search, flags=re.IGNORECASE)
    if full:
        base |= Q(**{
            f"{prefix}program__code__iexact": full.group(1),
            f"{prefix}year_level__level": int(full.group(2)),
            f"{prefix}name__iexact": full.group(3),
        })
    elif search.isdigit():
        base |= Q(**{f"{prefix}year_level__level": int(search)})
    return base


def visible_schedule(request, pk):
    schedules = Schedule.objects.all()
    if not admin_required(request.user):
        schedules = schedules.filter(status=ScheduleStatus.PUBLISHED)
    schedule = get_object_or_404(schedules, pk=pk)
    if not admin_required(request.user) and not entries_visible_to_user(schedule.entries.all(), request.user).exists():
        raise Http404("Schedule is not assigned to this user.")
    return schedule


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
        context["entries"] = (ScheduleEntry.objects.filter(schedule__status=ScheduleStatus.PUBLISHED).filter(
            Q(faculty_override=faculty) | Q(faculty_override__isnull=True, assignment__faculty=faculty)
        ) if faculty else ScheduleEntry.objects.none()).select_related(
            "schedule__term", "assignment__subject", "assignment__section", "assignment__faculty", "room",
            "subject_override", "section_override", "faculty_override").order_by("day", "start_time")
        context["timetable_grid"] = personal_schedule_grid(context["entries"])
        context["availability"] = Availability.objects.filter(faculty=faculty)
        return render(request, "schedules/faculty_dashboard.html", context)
    student = Student.objects.filter(user=request.user).select_related("section").first()
    context["student"] = student
    student_section = getattr(student, "section", None)
    context["entries"] = (ScheduleEntry.objects.filter(schedule__status=ScheduleStatus.PUBLISHED).filter(
        Q(section_override=student_section) | Q(section_override__isnull=True, assignment__section=student_section)
    ) if student_section else ScheduleEntry.objects.none()).select_related(
        "schedule__term", "assignment__subject", "assignment__section", "assignment__faculty", "room",
        "subject_override", "section_override", "faculty_override").order_by("day", "start_time")
    context["timetable_grid"] = personal_schedule_grid(context["entries"])
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
    entries = entries_visible_to_user(entries, request.user)
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
    objects = model.objects.all()
    schedule_tab = request.GET.get("tab", "active")
    if resource == "schedules":
        if schedule_tab == "archived":
            objects = objects.filter(status=ScheduleStatus.ARCHIVED)
        elif schedule_tab == "drafts":
            objects = objects.exclude(status__in=[ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED])
        else:
            objects = objects.filter(status=ScheduleStatus.PUBLISHED)
    elif resource == "assignments":
        objects = objects.select_related("subject", "section__program", "section__year_level", "faculty", "term").prefetch_related("meetings")
    field_names = {field.name for field in model._meta.fields}
    created_field = "created_at" if "created_at" in field_names else ("generated_at" if "generated_at" in field_names else "pk")
    modified_field = "updated_at" if "updated_at" in field_names else created_field
    sort = request.GET.get("sort", "modified_desc")
    orderings = {"added_desc": f"-{created_field}", "added_asc": created_field,
                 "modified_desc": f"-{modified_field}", "modified_asc": modified_field}
    objects = objects.order_by(orderings.get(sort, orderings["modified_desc"]))[:200]
    return render(request, "schedules/resource_list.html", {"resource": resource, "objects": objects,
        "drafts": FormDraft.objects.filter(user=request.user, resource=resource),
        "sort": sort, "schedule_tab": schedule_tab, "resource_label": "Courses" if resource == "subjects" else resource.replace("-", " ").title(),
        "has_created_at": created_field != "pk", "has_updated_at": "updated_at" in field_names,
        "description": RESOURCE_DESCRIPTIONS.get(resource, "Manage records for this section.")})


@login_required
@user_passes_test(admin_required)
def room_utilization_dashboard(request):
    term = AcademicTerm.objects.filter(pk=request.GET.get("term")).first() if request.GET.get("term") else None
    schedule = Schedule.objects.filter(pk=request.GET.get("schedule")).first() if request.GET.get("schedule") else latest_schedule(term)
    department = Department.objects.filter(pk=request.GET.get("department")).first() if request.GET.get("department") else None
    rows = utilization_rows(schedule, department=department)
    rows = filtered_rows(
        rows,
        query=request.GET.get("q", ""),
        room_type=request.GET.get("room_type", ""),
        utilization_range=request.GET.get("utilization", ""),
        room_group=request.GET.get("room_group", ""),
        day=request.GET.get("day", ""),
    )
    context = {
        "rows": rows,
        "summary": utilization_summary(rows),
        "schedule": schedule,
        "terms": AcademicTerm.objects.all(),
        "schedules": Schedule.objects.filter(term=term).order_by("-generated_at") if term else Schedule.objects.all().order_by("-generated_at"),
        "departments": Department.objects.all(),
        "weekdays": Weekday.choices,
        "room_types": RoomKind.choices,
        "selected_room_type": request.GET.get("room_type", ""),
        "selected_utilization": request.GET.get("utilization", ""),
        "selected_room_group": request.GET.get("room_group", ""),
        "selected_day": request.GET.get("day", ""),
        "selected_term": str(term.pk) if term else "",
        "selected_schedule": str(schedule.pk) if schedule else "",
        "selected_department": str(department.pk) if department else "",
        "query": request.GET.get("q", ""),
    }
    return render(request, "schedules/room_utilization.html", context)


@login_required
@user_passes_test(admin_required)
def room_schedule_dashboard(request):
    term = AcademicTerm.objects.filter(pk=request.GET.get("term")).first() if request.GET.get("term") else None
    schedule = Schedule.objects.filter(pk=request.GET.get("schedule")).first() if request.GET.get("schedule") else latest_schedule(term)
    room = Room.objects.filter(pk=request.GET.get("room")).first() if request.GET.get("room") else Room.objects.order_by("name").first()
    return render(request, "schedules/room_schedule.html", {
        "term": term, "schedule": schedule, "room": room,
        "terms": AcademicTerm.objects.all(),
        "schedules": Schedule.objects.filter(term=term).order_by("-generated_at") if term else Schedule.objects.all().order_by("-generated_at"),
        "rooms": Room.objects.filter(is_active=True), "weekdays": Weekday.choices,
        "grid": room_schedule_grid(room, schedule) if room else [],
    })


@login_required
@user_passes_test(admin_required)
def room_capacity_planning(request):
    term = AcademicTerm.objects.filter(pk=request.GET.get("term")).first() if request.GET.get("term") else AcademicTerm.objects.filter(is_active=True).first()
    planning, lecture = capacity_planning(term, request.GET)
    return render(request, "schedules/room_capacity_planning.html", {
        "term": term, "terms": AcademicTerm.objects.all(), "planning": planning,
        "lecture": lecture, "room_types": RoomKind.choices,
    })


@login_required
@user_passes_test(admin_required)
def export_room_utilization_csv(request):
    schedule = Schedule.objects.filter(pk=request.GET.get("schedule")).first() if request.GET.get("schedule") else latest_schedule()
    rows = filtered_rows(
        utilization_rows(schedule),
        query=request.GET.get("q", ""),
        room_type=request.GET.get("room_type", ""),
        utilization_range=request.GET.get("utilization", ""),
        room_group=request.GET.get("room_group", ""), day=request.GET.get("day", ""),
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="room-utilization.csv"'
    writer = csv.writer(response)
    writer.writerow(["Room", "Room Type", "Capacity", "Monday %", "Tuesday %", "Wednesday %", "Thursday %", "Friday %", "Saturday %", "Weekly Utilization %", "Seat Utilization %", "Available Hours", "Scheduled Hours", "Assigned Classes", "Status"])
    for row in rows:
        writer.writerow([
            row.room.name,
            row.room.get_room_type_display(),
            row.room.capacity, *[item["percentage"] for item in row.daily], row.utilization_percentage,
            row.capacity_utilization, row.available_hours, row.scheduled_hours, row.assigned_classes, row.status,
        ])
    return response


@login_required
@user_passes_test(admin_required)
def export_room_utilization_pdf(request):
    schedule = Schedule.objects.filter(pk=request.GET.get("schedule")).first() if request.GET.get("schedule") else latest_schedule()
    rows = filtered_rows(
        utilization_rows(schedule),
        query=request.GET.get("q", ""),
        room_type=request.GET.get("room_type", ""),
        utilization_range=request.GET.get("utilization", ""),
        room_group=request.GET.get("room_group", ""), day=request.GET.get("day", ""),
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
    if resource == "assignments":
        return assignment_editor(request)
    form_class = MODEL_FORMS[resource]
    draft = FormDraft.objects.filter(user=request.user, resource=resource, object_pk="").first()
    form = form_class(request.POST or None, initial=draft.payload if draft and request.method == "GET" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        FormDraft.objects.filter(user=request.user, resource=resource, object_pk="").delete()
        messages.success(request, "Record created.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/form.html", {"form": form, "title": f"New {resource.replace('-', ' ')}",
        "description": RESOURCE_DESCRIPTIONS.get(resource, "Create a new record."), "tooltip_context": resource,
        "draft": draft, "draft_resource": resource, "draft_object_pk": ""})


@login_required
@user_passes_test(admin_required)
def resource_update(request, resource, pk):
    model = resource_model(resource)
    obj = get_object_or_404(model, pk=pk)
    if resource == "assignments":
        return assignment_editor(request, obj)
    draft = FormDraft.objects.filter(user=request.user, resource=resource, object_pk=str(pk)).first()
    draft_conflict = bool(draft and draft.base_signature and draft.base_signature != object_signature(obj))
    form = MODEL_FORMS[resource](request.POST or None, instance=obj,
        initial=draft.payload if draft and request.method == "GET" else None)
    if request.method == "POST" and form.is_valid():
        if draft_conflict and request.POST.get("draft_conflict_confirm") != "yes":
            form.add_error(None, "This record changed after your draft was created. Review the latest record and confirm before updating.")
            return render(request, "schedules/form.html", {"form": form, "title": f"Edit {obj}",
                "description": RESOURCE_DESCRIPTIONS.get(resource, "Update this record."), "tooltip_context": resource,
                "draft": draft, "draft_conflict": True, "draft_resource": resource, "draft_object_pk": str(pk)})
        form.save()
        FormDraft.objects.filter(user=request.user, resource=resource, object_pk=str(pk)).delete()
        messages.success(request, "Record updated.")
        return redirect("resource_list", resource=resource)
    return render(request, "schedules/form.html", {"form": form, "title": f"Edit {obj}",
        "description": RESOURCE_DESCRIPTIONS.get(resource, "Update this record."), "tooltip_context": resource,
        "draft": draft, "draft_conflict": draft_conflict, "draft_resource": resource, "draft_object_pk": str(pk)})


def assignment_editor(request, assignment=None):
    assignment = assignment or Assignment()
    posted = request.POST.copy() if request.method == "POST" else None
    if posted is not None and "meetings-TOTAL_FORMS" not in posted:
        legacy_subject = Subject.objects.filter(pk=posted.get("subject")).first()
        legacy_component = TeachingAssignment.Component.GENERAL
        legacy_duration = 0
        if legacy_subject:
            if legacy_subject.lecture_hours:
                legacy_component = TeachingAssignment.Component.LECTURE
                legacy_duration = legacy_subject.lecture_hours * 60
            elif legacy_subject.lab_hours:
                legacy_component = TeachingAssignment.Component.LABORATORY
                legacy_duration = legacy_subject.lab_hours * 60
        posted.update({"meetings-TOTAL_FORMS": "1", "meetings-INITIAL_FORMS": "0",
                       "meetings-MIN_NUM_FORMS": "1", "meetings-MAX_NUM_FORMS": "1000",
                       "meetings-0-meeting_index": posted.get("meeting_index", "1"),
                       "meetings-0-component": posted.get("component", legacy_component),
                       "meetings-0-duration_minutes": posted.get("duration_minutes", legacy_duration),
                       "meetings-0-required_room_type_override": posted.get("required_room_type_override", "")})
    form = MODEL_FORMS["assignments"](posted, instance=assignment)
    meetings = AssignmentMeetingFormSetFactory(posted, instance=assignment, prefix="meetings")
    credential_result = None
    if request.method == "POST" and form.is_valid() and meetings.is_valid():
        credential_result = faculty_qualification(form.cleaned_data["faculty"], form.cleaned_data["subject"])
        confirmed = request.POST.get("credential_override_confirm") == "yes"
        reason = request.POST.get("credential_override_reason", "").strip()
        if credential_result["qualified"] or (confirmed and reason):
            with transaction.atomic():
                parent = form.save()
                children = meetings.save(commit=False)
                for removed in meetings.deleted_objects:
                    removed.delete()
                for meeting in children:
                    meeting.assignment = parent
                    meeting.save()
                if not credential_result["qualified"]:
                    for meeting in parent.meetings.all():
                        CredentialOverride.objects.get_or_create(
                            assignment=meeting, subject=parent.subject, faculty=parent.faculty,
                            defaults={"admin_user": request.user, "reason": reason,
                                      "missing_credentials": missing_credential_message(parent.faculty, parent.subject)},
                        )
            FormDraft.objects.filter(user=request.user, resource="assignments", object_pk__in=["", str(parent.pk)]).delete()
            messages.success(request, "Assignment and its meetings were saved.")
            return redirect("resource_list", resource="assignments")
        if confirmed and not reason:
            form.add_error(None, "An override reason is required.")
        else:
            form.add_error(None, "The selected faculty member does not meet this course's credential requirements.")
    return render(request, "schedules/assignment_form.html", {
        "form": form, "meetings": meetings, "assignment": assignment,
        "credential_result": credential_result,
        "title": "Edit Assignment" if assignment.pk else "New Assignment",
    })


def save_assignment_with_credential_check(request, form, resource):
    assignment = form.save(commit=False)
    result = faculty_qualification(assignment.faculty, assignment.subject)
    if result["qualified"]:
        assignment.save()
        form.save_m2m()
        FormDraft.objects.filter(
            user=request.user, resource=resource, object_pk__in=["", str(assignment.pk)]
        ).delete()
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
            FormDraft.objects.filter(
                user=request.user, resource=resource, object_pk__in=["", str(assignment.pk)]
            ).delete()
        messages.warning(request, "Teaching assignment saved with a credential override.")
        return redirect("resource_list", resource=resource)

    return render_credential_override_confirmation(request, form, result)


@login_required
@user_passes_test(admin_required)
@require_POST
def save_form_draft(request):
    try:
        body = json.loads(request.body or "{}")
    except (TypeError, ValueError):
        return JsonResponse({"error": "The draft data was not valid JSON."}, status=400)

    resource = str(body.get("resource", ""))
    try:
        model = resource_model(resource)
        form_class = MODEL_FORMS[resource]
    except (Http404, KeyError):
        return JsonResponse({"error": "This form cannot be saved as a draft."}, status=400)

    object_pk = str(body.get("object_pk") or "")
    instance = get_object_or_404(model, pk=object_pk) if object_pk else None
    payload = safe_draft_payload(form_class, body.get("payload") or {})
    if not body.get("changed") or not payload:
        return JsonResponse({"saved": False, "reason": "unchanged"})

    draft, created = FormDraft.objects.get_or_create(
        user=request.user,
        resource=resource,
        object_pk=object_pk,
        defaults={"base_signature": object_signature(instance)},
    )
    draft.payload = payload
    if created and instance and not draft.base_signature:
        draft.base_signature = object_signature(instance)
    draft.save()
    return JsonResponse({"saved": True, "draft_id": draft.pk, "updated_at": draft.updated_at.isoformat()})


@login_required
@user_passes_test(admin_required)
@require_POST
def discard_form_draft(request, pk):
    draft = get_object_or_404(FormDraft, pk=pk, user=request.user)
    resource, object_pk = draft.resource, draft.object_pk
    draft.delete()
    messages.success(request, "Draft discarded. The saved record was not changed.")
    if object_pk and resource in RESOURCE_MODELS and RESOURCE_MODELS[resource].objects.filter(pk=object_pk).exists():
        return redirect("resource_update", resource=resource, pk=object_pk)
    return redirect("resource_create", resource=resource)


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
            | section_search_q("assignment__section__", search) | Q(assignment__faculty__full_name__icontains=search)
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
        "subject_override", "section_override__program", "section_override__year_level", "faculty_override",
    )
    entries = entries_visible_to_user(entries, request.user)
    filter_form = ScheduleEntryFilterForm(request.GET or None)
    if filter_form.is_valid():
        values = filter_form.cleaned_data
        if values.get("department"):
            entries = entries.filter(
                Q(section_override__program__department=values["department"])
                | Q(section_override__isnull=True, assignment__section__program__department=values["department"])
            )
        if values.get("program"):
            entries = entries.filter(
                Q(section_override__program=values["program"])
                | Q(section_override__isnull=True, assignment__section__program=values["program"])
            )
        if values.get("year_level"):
            entries = entries.filter(
                Q(section_override__year_level=values["year_level"])
                | Q(section_override__isnull=True, assignment__section__year_level=values["year_level"])
            )
        if values.get("section"):
            entries = entries.filter(
                Q(section_override=values["section"])
                | Q(section_override__isnull=True, assignment__section=values["section"])
            )
        if values.get("faculty"):
            entries = entries.filter(
                Q(faculty_override=values["faculty"])
                | Q(faculty_override__isnull=True, assignment__faculty=values["faculty"])
            )
        if values.get("room"):
            entries = entries.filter(room=values["room"])
        if values.get("day") != "" and values.get("day") is not None:
            entries = entries.filter(day=values["day"])
        if values.get("component"):
            entries = entries.filter(
                Q(component_override=values["component"])
                | Q(component_override="", assignment__component=values["component"])
            )
        search = values.get("q", "").strip()
        if search:
            entries = entries.filter(
                section_search_q("assignment__section__", search)
                | section_search_q("section_override__", search)
                | Q(assignment__subject__code__icontains=search)
                | Q(assignment__subject__title__icontains=search)
                | Q(subject_override__code__icontains=search)
                | Q(subject_override__title__icontains=search)
                | Q(assignment__faculty__full_name__icontains=search)
                | Q(faculty_override__full_name__icontains=search)
                | Q(room__name__icontains=search)
            )
    entries = list(entries.order_by(
        "assignment__section__program__code", "assignment__section__year_level__level",
        "assignment__section__name", "assignment__subject__code", "assignment__component", "day", "start_time",
    ))
    for entry in entries:
        try:
            entry.full_clean()
            entry.manual_conflicts = []
        except ValidationError as exc:
            entry.manual_conflicts = exc.messages
    if request.GET.get("check") == "1":
        count = len(schedule_validation_messages(schedule))
        if count:
            messages.error(request, f"{count} conflicts require attention.")
        else:
            messages.success(request, "No conflicts detected.")
    return render(request, "schedules/schedule_detail.html", {
        "schedule": schedule, "entries": entries, "filter_form": filter_form,
        "conflicts": schedule_validation_messages(schedule), "can_manage": admin_required(request.user),
    })


@login_required
@user_passes_test(admin_required)
def entry_create(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    if schedule.status in {ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED}:
        messages.error(request, "Published and archived schedules are locked. Create or regenerate a draft version before making changes.")
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
    if entry.schedule.status in {ScheduleStatus.PUBLISHED, ScheduleStatus.ARCHIVED}:
        messages.error(request, "Published and archived schedules are locked. Create or regenerate a draft version before making changes.")
        return redirect("schedule_detail", pk=pk)
    form = ScheduleEntryForm(request.POST or None, instance=entry)
    form.fields["assignment"].queryset = TeachingAssignment.objects.filter(term=entry.schedule.term)
    if request.method == "POST" and form.is_valid():
        return save_entry_with_credential_check(request, form, entry.schedule)
    return render(request, "schedules/form.html", {"form": form, "title": "Edit Schedule Entry", "tooltip_context": "schedule-entry"})


def save_entry_with_credential_check(request, form, schedule):
    entry = form.save(commit=False)
    entry.schedule = schedule
    previous = {}
    if entry.pk:
        old = ScheduleEntry.objects.get(pk=entry.pk)
        previous = {field: str(getattr(old, field)) for field in (
            "assignment_id", "subject_override_id", "section_override_id", "faculty_override_id",
            "component_override", "room_id", "day", "start_time", "end_time")}
    result = faculty_qualification(entry.effective_faculty, entry.effective_subject)
    valid_override = entry.assignment.credential_overrides.filter(
        faculty=entry.effective_faculty, subject=entry.effective_subject
    ).exists()
    if not result["qualified"] and not valid_override:
        if request.POST.get("credential_override_confirm") != "yes":
            return render_credential_override_confirmation(request, form, result)
        reason = request.POST.get("credential_override_reason", "").strip()
        if not reason:
            messages.error(request, "Override reason is required.")
            return render_credential_override_confirmation(request, form, result)
        CredentialOverride.objects.create(
            assignment=entry.assignment,
            subject=entry.effective_subject,
            faculty=entry.effective_faculty,
            admin_user=request.user,
            reason=reason,
            missing_credentials=missing_credential_message(entry.effective_faculty, entry.effective_subject),
        )
    try:
        entry.full_clean()
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(request, "schedules/form.html", {"form": form, "title": "Edit Schedule Entry", "description": "Resolve the validation issues before saving this schedule entry.", "tooltip_context": "schedule-entry"})
    entry.save()
    new_values = {field: str(getattr(entry, field)) for field in (
        "assignment_id", "subject_override_id", "section_override_id", "faculty_override_id",
        "component_override", "room_id", "day", "start_time", "end_time")}
    if previous and previous != new_values:
        ScheduleEntryAudit.objects.create(schedule=schedule, entry=entry, user=request.user,
                                          previous_values=previous, new_values=new_values)
    schedule.save(update_fields=["updated_at"])
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
        return redirect("schedule_detail", pk=pk)
    current = Schedule.objects.filter(term=schedule.term, status=ScheduleStatus.PUBLISHED).exclude(pk=schedule.pk).first()
    if current and request.POST.get("replace_confirm") != "yes":
        return render(request, "schedules/publish_replace_confirm.html", {
            "schedule": schedule, "current": current,
        })
    with transaction.atomic():
        locked = Schedule.objects.select_for_update().get(pk=schedule.pk)
        current = Schedule.objects.select_for_update().filter(
            term=locked.term, status=ScheduleStatus.PUBLISHED
        ).exclude(pk=locked.pk).first()
        now = timezone.now()
        if current:
            current.status = ScheduleStatus.ARCHIVED
            current.archived_at = now
            current.replaced_by = locked
            current.save(update_fields=["status", "archived_at", "replaced_by", "updated_at"])
        locked.status = ScheduleStatus.PUBLISHED
        locked.published_at = now
        locked.archived_at = None
        locked.replaced_by = None
        locked.save(update_fields=["status", "published_at", "archived_at", "replaced_by", "updated_at"])
    messages.success(request, "Schedule published. The previous official schedule was archived." if current else "Schedule published.")
    return redirect("schedule_detail", pk=pk)


@login_required
def export_csv(request, pk):
    schedule = visible_schedule(request, pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{schedule.name}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Day", "Start", "End", "Course", "Section", "Faculty", "Room"])
    entries = entries_visible_to_user(schedule.entries.select_related(
        "assignment__subject", "assignment__section", "assignment__faculty", "room",
        "subject_override", "section_override", "faculty_override"), request.user)
    for e in entries:
        writer.writerow([e.get_day_display(), e.start_time, e.end_time, e.effective_subject.code, e.effective_section, e.effective_faculty, e.room.name])
    return response


@login_required
def export_pdf(request, pk):
    schedule = visible_schedule(request, pk)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{schedule.name}.pdf"'
    pdf = canvas.Canvas(response, pagesize=letter)
    pdf.drawString(40, 750, schedule.name)
    y = 720
    entries = entries_visible_to_user(schedule.entries.select_related(
        "assignment__subject", "assignment__section", "assignment__faculty", "room",
        "subject_override", "section_override", "faculty_override"), request.user)
    for e in entries:
        pdf.drawString(40, y, f"{e.get_day_display()} {e.start_time}-{e.end_time} {e.effective_subject.code} {e.effective_section} {e.effective_faculty} {e.room.name}")
        y -= 18
        if y < 50:
            pdf.showPage()
            y = 750
    pdf.save()
    return response
