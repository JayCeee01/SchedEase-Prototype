"""Scheduling identity invariants, independent of UI context and resource ownership."""
from django.core.exceptions import ValidationError
from django.http import Http404
from functools import wraps


def require_schedule_scope(schedule, *, education_level=None, term_id=None):
    level = schedule.term.education_level
    if level not in ('SHS', 'TERTIARY'):
        raise ValidationError('The schedule requires a valid academic level.')
    if education_level and education_level != level:
        raise ValidationError('The schedule belongs to a different education level.')
    if term_id is not None and str(term_id) != str(schedule.term_id):
        raise ValidationError('The schedule belongs to a different academic term.')


def check_schedule_request(request, schedule):
    """The loaded schedule is authoritative; absent context preserves old URLs."""
    for data in (request.GET, request.POST):
        for key in ('education_level', 'term'):
            if len(data.getlist(key)) > 1:
                raise Http404('Specify one academic context.')
        level, term = data.get('education_level'), data.get('term')
        if request.method == 'GET' and level == 'COMBINED':
            level = None
        try:
            require_schedule_scope(schedule, education_level=level, term_id=term or None)
        except ValidationError as exc:
            raise Http404('The schedule does not match the selected academic context.') from exc


def entry_scope_errors(entry):
    """Shared validation used by manual edits, repairs and final publication.

    Faculty, rooms and subjects are not assigned invented level ownership.
    SHS offering/subject/approval validation remains in the existing adapter.
    """
    level = entry.schedule.term.education_level
    errors = []
    if entry.assignment.term_id != entry.schedule.term_id:
        errors.append('The teaching assignment belongs to a different academic term.')
    if (entry.assignment.section.program.education_level != level or
            entry.effective_section.program.education_level != level):
        errors.append('The assigned and selected sections must match the schedule education level.')
    return errors


def schedule_request_scope(view):
    @wraps(view)
    def wrapped(request, pk, *args, **kwargs):
        from django.shortcuts import get_object_or_404
        from schedules.models import Schedule
        schedule = get_object_or_404(Schedule.objects.select_related('term'), pk=pk)
        check_schedule_request(request, schedule)
        return view(request, pk, *args, **kwargs)
    return wrapped
