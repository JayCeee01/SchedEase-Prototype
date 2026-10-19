from django.core.exceptions import ValidationError
from django.db.models import Q
from .diagnostics import Diagnostic, ValidationMessages
from datetime import datetime, date, timedelta
from .availability import AvailabilityPolicy
from .credentials import missing_credential_message, teaching_eligibility
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, contains, overlaps


# Covers both default and overridden identities plus inherited duration/labels.
ENTRY_RELATIONS = (
    'schedule__term', 'assignment__faculty', 'assignment__subject',
    'assignment__section__program', 'assignment__section__year_level', 'room',
    'faculty_override', 'subject_override', 'section_override__program', 'section_override__year_level',
)


def effective_resource_filter(kind, pk):
    """Use exactly the same override-or-assignment identity as model properties."""
    return Q(**{f'{kind}_override_id': pk}) | Q(**{
        f'{kind}_override__isnull': True, f'assignment__{kind}_id': pk})


def individual_entry_errors(entry, *, eligible=None, faculty_policy=None, room_policy=None, issue_sink=None):
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

    for label, resource, policy in (("Faculty", entry.effective_faculty, faculty_policy), ("Room", entry.room, room_policy)):
        policy = policy if policy is not None else AvailabilityPolicy.for_resource(resource)
        reason = policy.rejection_reason(entry.day, entry.start_time, entry.end_time)
        if reason:
            add(f"{label} {reason}", "FACULTY_UNAVAILABLE" if label == "Faculty" else "ROOM_UNAVAILABLE")

    return errors


def validate_entry(entry):
    sink = getattr(entry, '_generation_issue_sink', None)
    errors = individual_entry_errors(entry, issue_sink=sink)
    def add(message, category, meetings):
        errors.append(message)
        if sink is not None:
            sink.append(Diagnostic.for_meetings(category, message, meetings, room_id=entry.room_id,
                details={'day': entry.day, 'start_time': str(entry.start_time), 'end_time': str(entry.end_time)}))
    # Keep the queryset's existing order and every relevant pair, while avoiding
    # materializing unrelated meetings. Strict inequalities preserve adjacency.
    qs = entry.schedule.entries.exclude(pk=entry.pk).filter(
        day=entry.day, start_time__lt=entry.end_time, end_time__gt=entry.start_time,
    ).filter(effective_resource_filter('faculty', entry.effective_faculty.pk)
             | effective_resource_filter('section', entry.effective_section.pk) | Q(room_id=entry.room_id))
    for other in qs.select_related('assignment__faculty', 'assignment__subject', 'assignment__section',
                                  'faculty_override', 'subject_override', 'section_override', 'room'):
        if not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
            continue
        if other.effective_faculty.pk == entry.effective_faculty.pk:
            add(f"Faculty conflict with {other.effective_subject.code} ({other.start_time}-{other.end_time}).", "FACULTY_CONFLICT", [entry.assignment, other.assignment])
        if other.room_id == entry.room_id:
            add(f"Room conflict in {entry.room.name} with {other.effective_subject.code} ({other.start_time}-{other.end_time}).", "ROOM_CONFLICT", [entry.assignment, other.assignment])
        if other.effective_section.pk == entry.effective_section.pk:
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
    if weekly_minutes > entry.effective_faculty.max_weekly_hours * 60:
        add("Faculty exceeds maximum weekly teaching hours.", "FACULTY_WORKLOAD",
            [entry.assignment] + [e.assignment for e in faculty_entries if e.effective_faculty.pk == entry.effective_faculty.pk])

    if errors:
        raise ValidationError(errors)


def conflict_messages(entries):
    messages = []
    for idx, entry in enumerate(entries):
        for other in entries[idx + 1 :]:
            if entry.day != other.day or not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
                continue
            if entry.effective_faculty.pk == other.effective_faculty.pk:
                messages.append(f"Faculty conflict: {entry.effective_faculty} teaches {entry.effective_subject.code} and {other.effective_subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
            if entry.room_id == other.room_id:
                messages.append(f"Room conflict: {entry.room.name} is assigned to {entry.effective_subject.code} and {other.effective_subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
            if entry.effective_section.pk == other.effective_section.pk:
                messages.append(f"Section conflict: {entry.effective_section} has {entry.effective_subject.code} and {other.effective_subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
    return messages


def schedule_validation_issues(schedule):
    messages = []
    entries = list(schedule.entries.select_related(*ENTRY_RELATIONS))
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
    from .meetings import scheduled_requirement_errors
    requirement_issues = []
    scheduled_requirement_errors(schedule, entries, issue_sink=requirement_issues)
    messages.extend({'entry': None, 'message': issue.message, 'issue': issue} for issue in requirement_issues)
    return messages


def schedule_validation_messages(schedule):
    issues = schedule_validation_issues(schedule)
    return ValidationMessages(list(dict.fromkeys(issue['message'] for issue in issues)), [issue['issue'] for issue in issues])
