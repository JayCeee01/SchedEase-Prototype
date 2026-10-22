"""T8: explicit, unscheduled assignment allocation; never publishes a timetable."""
import hashlib
import json
from copy import copy
from decimal import Decimal
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, connection
from django.core.serializers.json import DjangoJSONEncoder
from schedules import models as m
from .placements import feasible_placements, PlacementOccupancy
from .ga import Gene
from .conflicts import validate_entry
from .faculty_workload import contact_minutes

SALT = 'workload-batch-v1'


def require_admin(user):
    from schedules.views import admin_required
    if not user.is_authenticated or not user.is_active or not admin_required(user):
        raise PermissionDenied


def fingerprint():
    # Includes through tables (credential equivalents), locks, terms and published occupancy.
    names = ('AcademicTerm', 'Department', 'Program', 'YearLevel', 'Section', 'Subject',
             'Faculty', 'Assignment', 'TeachingAssignment', 'Room', 'Availability',
             'Credential', 'FacultyCredential', 'SubjectCredentialRequirement',
             'CredentialOverride', 'Schedule', 'ScheduleEntry')
    models = [getattr(m, name) for name in names]
    models.append(m.SubjectCredentialRequirement.acceptable_equivalents.through)
    data = [(model._meta.label, list(model.objects.order_by('pk').values())) for model in models]
    return hashlib.sha256(json.dumps(data, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def context(term_id, assignment_ids, faculty_ids):
    term = m.AcademicTerm.objects.get(pk=term_id)
    if not term.starts_on or not term.ends_on or term.starts_on >= term.ends_on:
        raise ValidationError('Complete the academic term dates before balancing.')
    faculty = {f.pk: f for f in m.Faculty.objects.filter(pk__in=faculty_ids).order_by('pk')}
    if len(faculty) < 2 or len(faculty) != len(set(faculty_ids)):
        raise ValidationError('Select at least two comparable instructors.')
    departments = {f.department_id for f in faculty.values()}
    if len(departments) != 1 or any(f.max_weekly_hours <= 0 for f in faculty.values()):
        raise ValidationError('Select instructors from one department with positive weekly limits.')
    parents = {a.pk: a for a in m.Assignment.objects.filter(pk__in=assignment_ids).select_related('subject', 'section', 'faculty')}
    if not parents or len(parents) != len(set(assignment_ids)):
        raise ValidationError('Select existing assignments explicitly authorized for reassignment.')
    if len(parents) > 12 or len(faculty) > 12:
        raise ValidationError('Select at most 12 assignments and 12 instructors per preview.')
    for parent in parents.values():
        if parent.term_id != term.pk or parent.faculty_id not in faculty or parent.subject.department_id not in departments:
            raise ValidationError('Assignments must match the term, department and selected instructor group.')
        if not parent.meetings.exists() or m.ScheduleEntry.objects.filter(assignment__assignment=parent).exists():
            raise ValidationError('An assignment has no meetings or is locked by a draft, published or archived schedule. Use the existing correction workflow.')
    # Conservative scope: a complete unscheduled term avoids conflicting alternative draft allocations.
    if m.ScheduleEntry.objects.filter(assignment__term=term).exists():
        raise ValidationError('This term already has scheduled meetings. Balance an unscheduled term; existing schedules remain unchanged.')
    meetings = list(m.TeachingAssignment.objects.filter(term=term).select_related('assignment', 'subject', 'faculty', 'section', 'term').order_by('pk'))
    if len(meetings) > 80:
        raise ValidationError('This preview supports up to 80 meetings. No assignments were changed.')
    return term, faculty, parents, meetings


def metrics(faculty, meetings):
    rows = []
    for pk, f in faculty.items():
        minutes = contact_minutes(a for a in meetings if a.faculty_id == pk)
        percentage = Decimal(minutes) * 100 / (f.max_weekly_hours * 60)
        rows.append(dict(id=pk, name=f.full_name, minutes=minutes, hours=minutes / 60, percentage=float(percentage)))
    values = [Decimal(str(row['percentage'])) for row in rows]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return dict(rows=rows, variance=float(variance), minimum=float(min(values)), maximum=float(max(values)), spread=float(max(values)-min(values)))


def evaluate(term_id, assignment_ids, faculty_ids, changes):
    term, faculty, parents, original = context(term_id, assignment_ids, faculty_ids)
    meetings = [copy(a) for a in original]
    changes = {int(k): int(v) for k, v in changes.items()}
    for pk, target in changes.items():
        if pk not in parents or target not in faculty or parents[pk].faculty_id == target:
            raise ValidationError('The selected change is not authorized for this group.')
        if m.Assignment.objects.filter(term=term, subject=parents[pk].subject, section=parents[pk].section, faculty_id=target).exclude(pk=pk).exists():
            raise ValidationError('The proposed instructor already has this assignment.')
    for a in meetings:
        if a.assignment_id in changes:
            a.faculty = faculty[changes[a.assignment_id]]
    by_faculty = {a.faculty_id: a.faculty for a in meetings}
    if any(contact_minutes(a for a in meetings if a.faculty_id == pk) > f.max_weekly_hours * 60 for pk, f in by_faculty.items()):
        raise ValidationError('The combined assignment load exceeds an instructor’s weekly limit.')
    from .meetings import meeting_requirement_errors, meeting_records
    for parent in m.Assignment.objects.filter(term=term).select_related('subject'):
        errors = meeting_requirement_errors(parent.subject, meeting_records([a for a in meetings if a.assignment_id == parent.pk]))
        if errors:
            raise ValidationError([message for _, message in errors])
    keys = [(a.subject_id, a.section_id, changes.get(a.pk, a.faculty_id)) for a in m.Assignment.objects.filter(term=term)]
    if len(keys) != len(set(keys)):
        raise ValidationError('This batch would duplicate a teaching assignment.')
    rooms = list(m.Room.objects.filter(is_active=True).order_by('pk'))
    schedule = m.Schedule(pk=-1, term=term, name='Workload feasibility preview')
    external = m.Schedule.objects.filter(status=m.ScheduleStatus.PUBLISHED, term__starts_on__lte=term.ends_on, term__ends_on__gte=term.starts_on).exclude(term=term).exists()
    domains = {}
    for a in meetings:
        options, errors = feasible_placements(a, term, rooms)
        if errors:
            raise ValidationError([f'{a.subject.code}: {e}' for e in errors])
        valid = []
        for room_id, day, start, end in options:
            entry = m.ScheduleEntry(schedule=schedule, assignment=a, room_id=room_id, day=day, start_time=start, end_time=end)
            entry.room = next(r for r in rooms if r.pk == room_id)
            try:
                if external:
                    validate_entry(entry)  # includes overlapping published academic terms
            except ValidationError:
                continue
            valid.append(Gene(a.pk, room_id, day, start, end))
        domains[a.pk] = valid
    ordered = sorted(meetings, key=lambda a: (len(domains[a.pk]), a.pk))
    mapping = {a.pk: a for a in meetings}
    visits = 0
    def place(index, chosen):
        nonlocal visits
        if index == len(ordered):
            return chosen
        occupancy = PlacementOccupancy(mapping, chosen)
        for gene in domains[ordered[index].pk]:
            visits += 1
            if visits > 5000:
                return None
            if not occupancy.conflicts(gene):
                result = place(index + 1, chosen + [gene])
                if result is not None:
                    return result
        return None
    witness = place(0, [])
    if witness is None:
        raise ValidationError('No conflict-free placement was found within the preview search limit. No changes were made.')
    before, after = metrics(faculty, original), metrics(faculty, meetings)
    rows = []
    for pk, target in sorted(changes.items()):
        parent = parents[pk]
        ids = (parent.faculty_id, target)
        without = [copy(a) for a in meetings]
        for a in without:
            if a.assignment_id == pk:
                a.faculty = parent.faculty
        contribution = metrics(faculty, without)['variance'] - after['variance']
        rows.append(dict(contribution=contribution, id=pk, target=target, subject=parent.subject.code, section=str(parent.section),
            current=parent.faculty.full_name, proposed=faculty[target].full_name,
            before=[r for r in before['rows'] if r['id'] in ids], after=[r for r in after['rows'] if r['id'] in ids],
            explanation='Eligible: credential rules, weekly limits and common availability passed. A conflict-free placement exists for all term meetings, including checks against other published terms. Percentages below show the combined batch impact.'))
    return dict(before=before, after=after, proposals=rows, changes=changes, hard_violations=0,
                placements=[dict(meeting=g.assignment_id, room=g.room_id, day=g.day, start=g.start_time.isoformat(), end=g.end_time.isoformat()) for g in witness],
                improvement=before['variance'] - after['variance'])


def propose(user, term_id, assignment_ids, faculty_ids):
    require_admin(user)
    start = fingerprint()
    term, faculty, parents, meetings = context(term_id, assignment_ids, faculty_ids)
    changes, attention = {}, []
    current = metrics(faculty, meetings)['variance']
    for _ in range(len(parents)):
        best = None
        for pk, parent in sorted(parents.items()):
            if pk in changes:
                continue
            for target in sorted(faculty):
                if target == parent.faculty_id:
                    continue
                trial = dict(changes, **{str(pk): target})
                # Cheap metric filter before searching timetable feasibility.
                hypothetical = [copy(a) for a in meetings]
                normalized = {int(k): v for k, v in trial.items()}
                for a in hypothetical:
                    if a.assignment_id in normalized:
                        a.faculty_id = normalized[a.assignment_id]
                score = metrics(faculty, hypothetical)['variance']
                if score >= current - 0.000001:
                    continue
                try:
                    result = evaluate(term_id, assignment_ids, faculty_ids, normalized)
                except ValidationError as exc:
                    attention.append(f'{parent.subject.code} → {faculty[target].full_name}: {" ".join(exc.messages)}')
                    continue
                if best is None or score < best['after']['variance'] - 0.000001:
                    best = result
        if best is None:
            break
        changes, current = best['changes'], best['after']['variance']
    if start != fingerprint():
        raise ValidationError('Scheduling inputs changed during preview. Generate proposals again.')
    payload = dict(user=user.pk, term=term_id, assignments=assignment_ids, faculty=faculty_ids,
                   changes=changes, fingerprint=start)
    return signing.dumps(payload, salt=SALT, compress=True), list(dict.fromkeys(attention))


def preview(user, token, selected):
    require_admin(user)
    try:
        payload = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature as exc:
        raise ValidationError('This preview expired or is invalid. Generate proposals again.') from exc
    if payload['user'] != user.pk or payload['fingerprint'] != fingerprint():
        raise ValidationError('This preview is stale or belongs to another administrator. Generate proposals again.')
    selected = {str(v) for v in selected}
    if not selected.issubset(payload['changes']):
        raise ValidationError('Select only proposals from this preview.')
    changes = {k: v for k, v in payload['changes'].items() if k in selected}
    result = evaluate(payload['term'], payload['assignments'], payload['faculty'], changes)
    if payload['fingerprint'] != fingerprint():
        raise ValidationError('Scheduling inputs changed during preview. Generate proposals again.')
    return payload, result


@transaction.atomic
def approve(user, token, selected):
    require_admin(user)
    if connection.vendor != 'sqlite':
        raise ValidationError('Batch approval currently requires the verified SQLite transaction backend.')
    # SQLite writer reservation before reads; failures roll back this audit row too.
    audit = m.WorkloadApproval.objects.create(administrator=user)
    from django.contrib.auth import get_user_model
    require_admin(get_user_model().objects.get(pk=user.pk))
    payload, result = preview(user, token, selected)
    if not result['changes'] or result['improvement'] <= 0.000001:
        raise ValidationError('The selected batch must improve workload fairness. Preview a different selection.')
    for pk, target in sorted(result['changes'].items()):
        parent = m.Assignment.objects.select_for_update().get(pk=pk)
        parent.faculty_id = target
        parent.full_clean()
        parent.save()  # existing parent-to-meeting synchronization and protections
    audit.evidence = dict(inputs=payload, result=result)
    audit.save(update_fields=['evidence'])
    return audit
