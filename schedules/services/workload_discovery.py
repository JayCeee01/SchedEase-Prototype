"""Read-only eligibility discovery; discovery is not reassignment authorization."""
from django.core import signing
from django.core.exceptions import ValidationError
from schedules import models as m
from . import workload_balancing as balancing
from .credentials import teaching_eligibility

SALT = 'workload-discovery-v1'


def discover(user, term, department, assignments=(), faculty=(), exclude_assignments=(), exclude_faculty=()):
    balancing.require_admin(user)
    before = balancing.fingerprint()
    parents = m.Assignment.objects.filter(term=term, subject__department=department).select_related('subject', 'section', 'faculty').order_by('pk')
    if assignments:
        parents = parents.filter(pk__in=assignments)
    teachers = m.Faculty.objects.filter(department=department).order_by('pk')
    if faculty:
        teachers = teachers.filter(pk__in=faculty)
    teachers = list(teachers.exclude(pk__in=exclude_faculty))
    rows = list(parents)
    exclusions, candidates, alternatives = [], [], set()
    teacher_ids = [f.pk for f in teachers]
    warnings = []
    if len([a for a in rows if a.pk not in exclude_assignments]) > 12 or len(teachers) > 12:
        warnings.append('This analysis supports up to 12 assignments and 12 instructors. Use Advanced Selection to narrow the scope.')
    if len(teachers) < 2:
        warnings.append('At least two instructors are needed. Review instructor records or your advanced filters.')
    scheduled = m.ScheduleEntry.objects.filter(assignment__term=term).exists()
    for parent in rows:
        reason = ''
        if parent.pk in exclude_assignments:
            reason = 'Excluded in Advanced Selection.'
        elif m.ScheduleEntry.objects.filter(assignment__assignment=parent).exists():
            reason = 'Assignment is locked by an existing schedule. Use the schedule correction workflow.'
        elif scheduled:
            reason = 'This term already has scheduled meetings. Balancing currently requires an unscheduled term.'
        elif parent.faculty_id not in teacher_ids:
            reason = 'Current instructor is outside the selected instructor group or department.'
        elif not parent.meetings.exists():
            reason = 'No meetings are recorded. Complete the assignment first.'
        elif warnings:
            reason = 'Analysis cannot proceed until the scope warnings above are resolved.'
        available = []
        failures = []
        if not reason:
            for teacher in teachers:
                if teacher.pk == parent.faculty_id:
                    continue
                meetings = list(parent.meetings.select_related('subject', 'faculty', 'section'))
                if not all(teaching_eligibility(teacher, parent.subject, term, meeting)['eligible'] for meeting in meetings):
                    failures.append(f'{teacher.full_name}: qualification requirements are not met for the full term.')
                    continue
                try:
                    # Existing validation proves a complete feasible assignment scenario;
                    # this read-only check does not authorize or save the reassignment.
                    balancing.evaluate(term.pk, [parent.pk], teacher_ids, {parent.pk: teacher.pk})
                except ValidationError as exc:
                    failures.append(f'{teacher.full_name}: {" ".join(exc.messages)}')
                else:
                    available.append(teacher.pk)
                    alternatives.add(teacher.pk)
            if not available:
                reason = 'No eligible alternative instructor. ' + ' '.join(failures)
        label = f'{parent.subject.code} / {parent.section} - {parent.faculty.full_name}'
        if reason:
            exclusions.append({'id': parent.pk, 'label': label, 'reason': reason})
        else:
            candidates.append({'id': parent.pk, 'label': label, 'alternatives': available})
    if before != balancing.fingerprint():
        raise ValidationError('Scheduling information changed during analysis. Analyze again.')
    result = dict(total=len(rows), eligible=len(candidates), excluded=len(exclusions), alternatives=len(alternatives),
                  candidates=candidates, exclusions=exclusions, warnings=warnings,
                  teachers=[{'id': f.pk, 'name': f.full_name, 'limit': f.max_weekly_hours} for f in teachers],
                  can_proceed=bool(candidates) and not warnings,
                  term=str(term), department=str(department))
    payload = dict(user=user.pk, term=term.pk, faculty=teacher_ids, assignments=[a['id'] for a in candidates],
                   fingerprint=before)
    return result, signing.dumps(payload, salt=SALT, compress=True)


def authorize(user, analysis_token):
    balancing.require_admin(user)
    try:
        data = signing.loads(analysis_token, salt=SALT, max_age=1800)
    except signing.BadSignature as exc:
        raise ValidationError('This analysis expired or is invalid. Analyze workload again.') from exc
    if data['user'] != user.pk or data['fingerprint'] != balancing.fingerprint():
        raise ValidationError('This analysis is stale or belongs to another administrator. Analyze again.')
    if not data['assignments']:
        raise ValidationError('No eligible assignments were found.')
    return balancing.propose(user, data['term'], data['assignments'], data['faculty'])
