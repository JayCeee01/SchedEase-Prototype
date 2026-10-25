"""Read-only credential guidance for the administrator assignment editor."""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import AcademicTerm, Assignment, Faculty, Subject
from .services.credentials import faculty_qualification, valid_credential_override
from .views import admin_required


@login_required
@user_passes_test(admin_required)
@require_GET
@never_cache
def qualified_faculty(request):
    ids = {}
    for name in ("subject", "term", "assignment"):
        value = request.GET.get(name, "")
        if value:
            if len(value) > 19 or not value.isascii() or not value.isdigit() or not 0 < int(value) < 2**63:
                return JsonResponse({"error": "Choose a valid course and academic term."}, status=400)
            ids[name] = int(value)
    if "subject" not in ids or "term" not in ids:
        return JsonResponse({"faculty": [], "message": "Choose a course and academic term to check credentials."})
    subject = get_object_or_404(Subject, pk=ids["subject"])
    term = get_object_or_404(AcademicTerm, pk=ids["term"])
    parent = get_object_or_404(Assignment, pk=ids["assignment"]) if "assignment" in ids else None
    same_context = parent and parent.subject_id == subject.pk and parent.term_id == term.pk
    meetings = list(parent.meetings.prefetch_related("credential_overrides")) if same_context else []
    rows = []
    for faculty in Faculty.objects.all():
        qualification = faculty_qualification(faculty, subject, term)
        covered = bool(meetings and parent.faculty_id == faculty.pk) and all(
            valid_credential_override(meeting, faculty, subject) for meeting in meetings)
        status = "qualified" if qualification["qualified"] else "override" if covered else "unqualified"
        rows.append({"id": faculty.pk, "status": status,
                     "missing": [item["required"] for item in qualification["missing"]],
                     "reasons": [reason for item in qualification["missing"] for reason in item["reasons"]]})
    return JsonResponse({"faculty": rows})
