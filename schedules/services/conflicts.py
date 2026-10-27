from django.core.exceptions import ValidationError
from django.db.models import Q
from .diagnostics import Diagnostic, ValidationMessages
from datetime import datetime, date, timedelta
from .availability import AvailabilityPolicy
from .credentials import missing_credential_message, teaching_eligibility
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, contains, overlaps
from .resource_occupancy import weekday_intersects


# Covers both default and overridden identities plus inherited duration/labels.
ENTRY_RELATIONS = (
    'schedule__term', 'assignment__faculty', 'assignment__subject',
    'assignment__section__program', 'assignment__section__year_level', 'room',
    'faculty_override', 'subject_override', 'section_override__program', 'section_override__year_level',
    'assignment__shs_binding', 'assignment__term',
)


def effective_resource_filter(kind, pk):
    """Use exactly the same override-or-assignment identity as model properties."""
    return Q(**{f'{kind}_override_id': pk}) | Q(**{
        f'{kind}_override__isnull': True, f'assignment__{kind}_id': pk})


def individual_entry_errors(entry, *, eligible=None, faculty_policy=None, room_policy=None, section_policy=None, issue_sink=None):
    from .meetings import entry_requirement_errors
    errors = entry_requirement_errors(entry, issue_sink=issue_sink)
    def add(message, category='INVALID_DATA'):
        errors.append(message)
        if issue_sink is not None:
            text = message.messages[0] if isinstance(message, ValidationError) else message
            issue_sink.append(Diagnostic.for_meetings(category, text, [entry.assignment], room_id=entry.room.pk,
                details={'day': entry.day, 'start_time': str(entry.start_time), 'end_time': str(entry.end_time)}))
    if entry.assignment.term_id != entry.schedule.term_id:
        add("The teaching assignment belongs to a different academic term.")
    if entry.day not in ALLOWED_DAYS:
        add("Classes must be scheduled Monday to Saturday.")
    if not contains(SCHOOL_START, SCHOOL_END, entry.start_time, entry.end_time):
        add("Classes must be scheduled from 7:00 AM to 7:00 PM.")
    if entry.start_time >= entry.end_time:
        add("Start time must be earlier than end time.")
    else:
        elapsed = datetime.combine(date.today(), entry.end_time) - datetime.combine(date.today(), entry.start_time)
        actual_minutes, remainder = divmod(elapsed, timedelta(minutes=1))
        if remainder:
            add("Class duration must use whole minutes; remove seconds from the start and end times.", "INVALID_DURATION")
        if remainder or actual_minutes != entry.assignment.required_duration_minutes:
            add(
                f"Class duration must be {entry.assignment.required_duration_minutes} minutes; the selected time is {actual_minutes} minutes.", "INVALID_DURATION"
            )
    if entry.room.capacity < entry.effective_section.size:
        add("Room capacity is too small for the section.", "ROOM_CAPACITY")
    if entry.room.room_type != entry.assignment.effective_room_type:
        add("Room type does not match the course requirement.", "ROOM_TYPE")
    if eligible is None:
        eligible = teaching_eligibility(entry.effective_faculty, entry.effective_subject, entry.schedule.term, entry.assignment)["eligible"]
    if not eligible:
        add(ValidationError(missing_credential_message(entry.effective_faculty, entry.effective_subject, entry.schedule.term), code="credential_qualification"), "FACULTY_CREDENTIAL")

    for label, resource, policy in (("Faculty", entry.effective_faculty, faculty_policy), ("Room", entry.room, room_policy), ("Section", entry.effective_section, section_policy)):
        policy = policy if policy is not None else AvailabilityPolicy.for_resource(resource)
        if label == "Section" and not policy.configured:
            continue
        reason = policy.rejection_reason(entry.day, entry.start_time, entry.end_time)
        if reason:
            add(f"{label} {reason}", {"Faculty": "FACULTY_UNAVAILABLE", "Room": "ROOM_UNAVAILABLE", "Section": "INVALID_DATA"}[label])

    from .repair_rules import entry_errors
    for message in entry_errors(entry):
        add(message)
    return errors


def validate_entry(entry):
    sink = getattr(entry, '_generation_issue_sink', None)
    errors = individual_entry_errors(entry, issue_sink=sink)
    def add(message, category, meetings):
        errors.append(message)
        if sink is not None:
            sink.append(Diagnostic.for_meetings(category, message, meetings, room_id=entry.room_id,
                details={'day': entry.day, 'start_time': str(entry.start_time), 'end_time': str(entry.end_time)}))
    from schedules.models import ScheduleEntry, ScheduleStatus
    term = entry.schedule.term
    from .shs_scheduling import dates_overlap, participant_ids, assert_prepared
    if term.education_level == 'SHS':
        try:
            assert_prepared(term)
        except ValidationError as exc:
            errors.extend(exc.messages)
    else:
        from .contact_workload import validate_tertiary_with_published_shs
        try:
            validate_tertiary_with_published_shs(entry, published_faculty_ids=getattr(entry, '_published_shs_faculty_ids', None))
        except ValidationError as exc:
            errors.extend(exc.messages)
    local = Q(schedule_id=entry.schedule_id)
    external = (Q(schedule__status=ScheduleStatus.PUBLISHED,
                  schedule__term__starts_on__lte=term.ends_on,
                  schedule__term__ends_on__gte=term.starts_on)
                & ~Q(schedule__term_id=term.pk))
    faculty_or_room = (effective_resource_filter('faculty', entry.effective_faculty.pk)
                       | Q(room_id=entry.room_id))
    # One query keeps schedule-wide validation's existing query budget. Only
    # local entries participate in section conflicts; external drafts/archives
    # and alternative versions of the same term do not consume occupancy.
    qs = ScheduleEntry.objects.exclude(pk=entry.pk).filter(
        day=entry.day, start_time__lt=entry.end_time, end_time__gt=entry.start_time,
    ).filter((local if term.education_level == 'SHS' else
              local & (faculty_or_room | effective_resource_filter('section', entry.effective_section.pk)))
             | (external & faculty_or_room))
    for other in qs.select_related('schedule__term', 'assignment__faculty', 'assignment__subject',
                                  'assignment__section', 'faculty_override', 'subject_override',
                                  'section_override', 'room','assignment__shs_binding','assignment__term'):
        if not dates_overlap(entry.assignment,other.assignment,entry.day):
            continue
        if other.schedule_id != entry.schedule_id:
            # Inclusive date ranges must intersect on this meeting's weekday.
            if not weekday_intersects(term.starts_on, term.ends_on,
                    other.schedule.term.starts_on, other.schedule.term.ends_on, entry.day):
                continue
        if not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
            continue
        if other.effective_faculty.pk == entry.effective_faculty.pk:
            add(f"Faculty conflict with {other.effective_subject.code} ({other.start_time}-{other.end_time}).", "FACULTY_CONFLICT", [entry.assignment, other.assignment])
        if other.room_id == entry.room_id:
            add(f"Room conflict in {entry.room.name} with {other.effective_subject.code} ({other.start_time}-{other.end_time}).", "ROOM_CONFLICT", [entry.assignment, other.assignment])
        left_sections = set(participant_ids(entry.assignment)) if getattr(entry.assignment,'shs_binding',None) else {entry.effective_section.pk}
        right_sections = set(participant_ids(other.assignment)) if getattr(other.assignment,'shs_binding',None) else {other.effective_section.pk}
        if other.schedule_id == entry.schedule_id and left_sections & right_sections:
            add(f"Section conflict with {other.effective_subject.code} ({other.start_time}-{other.end_time}).", "SECTION_CONFLICT", [entry.assignment, other.assignment])

    weekly_minutes = 0
    faculty_entries = entry.schedule.entries.filter(
        effective_resource_filter('faculty', entry.effective_faculty.pk)).select_related(
            'assignment__faculty', 'assignment__subject', 'faculty_override')
    for faculty_entry in faculty_entries:
        if faculty_entry.pk != entry.pk and faculty_entry.effective_faculty.pk == entry.effective_faculty.pk:
            weekly_minutes += faculty_entry.assignment.required_duration_minutes
    if entry.pk is None:
        weekly_minutes += entry.assignment.required_duration_minutes
    else:
        weekly_minutes += entry.assignment.required_duration_minutes
    if term.education_level != 'SHS' and weekly_minutes > entry.effective_faculty.max_weekly_hours * 60:
        add("Faculty exceeds maximum weekly teaching hours.", "FACULTY_WORKLOAD",
            [entry.assignment] + [e.assignment for e in faculty_entries if e.effective_faculty.pk == entry.effective_faculty.pk])

    if errors:
        raise ValidationError(errors)


def conflict_messages(entries):
    from .shs_scheduling import binding, dates_overlap, participant_ids
    messages = []
    for idx, entry in enumerate(entries):
        for other in entries[idx + 1 :]:
            if entry.day != other.day or not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
                continue
            if not dates_overlap(entry.assignment, other.assignment, entry.day):
                continue
            if entry.effective_faculty.pk == other.effective_faculty.pk:
                messages.append(f"Faculty conflict: {entry.effective_faculty} teaches {entry.effective_subject.code} and {other.effective_subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
            if entry.room_id == other.room_id:
                messages.append(f"Room conflict: {entry.room.name} is assigned to {entry.effective_subject.code} and {other.effective_subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
            left = participant_ids(entry.assignment) if binding(entry.assignment) else (entry.effective_section.pk,)
            right = participant_ids(other.assignment) if binding(other.assignment) else (other.effective_section.pk,)
            if set(left) & set(right):
                messages.append(f"Section conflict: {entry.effective_section} has {entry.effective_subject.code} and {other.effective_subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
    return messages


def schedule_validation_issues(schedule):
    messages = []
    from .repair_rules import windows
    repair_windows = windows(schedule)
    from django.db.models import Exists, OuterRef
    from django.db.models.functions import Coalesce
    from .contact_workload import published_shs_entries
    entries = list(schedule.entries.select_related(*ENTRY_RELATIONS).prefetch_related(
        "assignment__section__availability_set", "section_override__availability_set").annotate(
            _contact_faculty_id=Coalesce('faculty_override_id', 'assignment__faculty_id'),
            _has_published_shs=Exists(published_shs_entries(schedule.term).filter(
                Q(faculty_override_id=OuterRef('_contact_faculty_id')) |
                Q(faculty_override__isnull=True, assignment__faculty_id=OuterRef('_contact_faculty_id'))))))
    scheduled_ids = {entry.assignment_id for entry in entries}
    missing = schedule.term.teachingassignment_set.exclude(id__in=scheduled_ids).select_related("subject", "section", "faculty")
    for assignment in missing:
        messages.append({"entry": None, "assignment": assignment, "message": (
            f"Unscheduled class: {assignment.subject.code} for {assignment.section}, taught by {assignment.faculty}; "
            f"requires {assignment.required_duration_minutes} minutes in a {assignment.get_required_room_type_override_display() if assignment.required_room_type_override else assignment.subject.get_required_room_type_display()}."
        )})
    for item in messages:
        item['issue'] = Diagnostic.for_meetings('UNSCHEDULED', item['message'], [item['assignment']])
    for entry in entries:
        entry._published_shs_faculty_ids = {entry._contact_faculty_id} if entry._has_published_shs else set()
        entry.schedule._repair_windows = repair_windows
        entry._generation_issue_sink = []
        try:
            entry.full_clean()
        except ValidationError as exc:
            from collections import defaultdict
            emitted = defaultdict(list)
            for issue in entry._generation_issue_sink:
                emitted[issue.message].append(issue)
            for message in exc.messages:
                diagnostic = (emitted[message].pop(0) if emitted[message] else None) or Diagnostic.for_meetings('INVALID_DATA', message, [entry.assignment], room_id=entry.room_id)
                messages.append({'entry': entry, 'message': f"{entry.effective_subject.code} / {entry.effective_section}: {message}", 'issue': diagnostic})
        finally:
            del entry._published_shs_faculty_ids
    from .meetings import scheduled_requirement_errors
    requirement_issues = []
    scheduled_requirement_errors(schedule, entries, issue_sink=requirement_issues)
    messages.extend({'entry': None, 'message': issue.message, 'issue': issue} for issue in requirement_issues)
    return messages


def schedule_validation_messages(schedule):
    issues = schedule_validation_issues(schedule)
    return ValidationMessages(list(dict.fromkeys(issue['message'] for issue in issues)), [issue['issue'] for issue in issues])
