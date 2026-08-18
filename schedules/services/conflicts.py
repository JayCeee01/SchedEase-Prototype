from django.core.exceptions import ValidationError
from datetime import datetime, date
from schedules.models import AvailabilityKind
from .credentials import missing_credential_message, faculty_qualification
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, contains, overlaps


def validate_entry(entry):
    errors = []
    if entry.assignment.term_id != entry.schedule.term_id:
        errors.append("The teaching assignment belongs to a different academic term.")
    if entry.day not in ALLOWED_DAYS:
        errors.append("Classes must be scheduled Monday to Saturday.")
    if not contains(SCHOOL_START, SCHOOL_END, entry.start_time, entry.end_time):
        errors.append("Classes must be scheduled from 7:00 AM to 7:00 PM.")
    if entry.start_time >= entry.end_time:
        errors.append("Start time must be earlier than end time.")
    else:
        actual_minutes = int((datetime.combine(date.today(), entry.end_time) - datetime.combine(date.today(), entry.start_time)).total_seconds() / 60)
        if actual_minutes != entry.assignment.required_duration_minutes:
            errors.append(
                f"Class duration must be {entry.assignment.required_duration_minutes} minutes; the selected time is {actual_minutes} minutes."
            )
    if entry.room.capacity < entry.assignment.section.size:
        errors.append("Room capacity is too small for the section.")
    if entry.room.room_type != entry.assignment.effective_room_type:
        errors.append("Room type does not match the subject requirement.")
    if not faculty_qualification(entry.assignment.faculty, entry.assignment.subject)["qualified"] and not entry.assignment.credential_overrides.exists():
        errors.append(missing_credential_message(entry.assignment.faculty, entry.assignment.subject))

    faculty_blocks = entry.assignment.faculty.availability_set.filter(day=entry.day, kind=AvailabilityKind.UNAVAILABLE)
    if any(overlaps(entry.start_time, entry.end_time, a.start_time, a.end_time) for a in faculty_blocks):
        errors.append("Faculty is unavailable during this time.")

    room_slots = entry.room.availability_set.filter(day=entry.day)
    available = room_slots.filter(kind=AvailabilityKind.AVAILABLE)
    unavailable = room_slots.filter(kind=AvailabilityKind.UNAVAILABLE)
    if available.exists() and not any(contains(a.start_time, a.end_time, entry.start_time, entry.end_time) for a in available):
        errors.append("Room is not available during this time.")
    if any(overlaps(entry.start_time, entry.end_time, a.start_time, a.end_time) for a in unavailable):
        errors.append("Room is unavailable during this time.")

    qs = entry.schedule.entries.exclude(pk=entry.pk).filter(day=entry.day)
    for other in qs.select_related("assignment__faculty", "assignment__section", "room"):
        if not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
            continue
        if other.assignment.faculty_id == entry.assignment.faculty_id:
            errors.append(f"Faculty conflict with {other.assignment.subject.code} ({other.start_time}-{other.end_time}).")
        if other.room_id == entry.room_id:
            errors.append(f"Room conflict in {entry.room.name} with {other.assignment.subject.code} ({other.start_time}-{other.end_time}).")
        if other.assignment.section_id == entry.assignment.section_id:
            errors.append(f"Section conflict with {other.assignment.subject.code} ({other.start_time}-{other.end_time}).")

    weekly_minutes = 0
    faculty_entries = entry.schedule.entries.filter(assignment__faculty=entry.assignment.faculty).select_related("assignment")
    for faculty_entry in faculty_entries:
        weekly_minutes += faculty_entry.assignment.required_duration_minutes
    if entry.pk is None:
        weekly_minutes += entry.assignment.required_duration_minutes
    if weekly_minutes > entry.assignment.faculty.max_weekly_hours * 60:
        errors.append("Faculty exceeds maximum weekly teaching hours.")

    if errors:
        raise ValidationError(errors)


def conflict_messages(entries):
    messages = []
    for idx, entry in enumerate(entries):
        for other in entries[idx + 1 :]:
            if entry.day != other.day or not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
                continue
            if entry.assignment.faculty_id == other.assignment.faculty_id:
                messages.append(f"Faculty conflict: {entry.assignment.faculty} teaches {entry.assignment.subject.code} and {other.assignment.subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
            if entry.room_id == other.room_id:
                messages.append(f"Room conflict: {entry.room.name} is assigned to {entry.assignment.subject.code} and {other.assignment.subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
            if entry.assignment.section_id == other.assignment.section_id:
                messages.append(f"Section conflict: {entry.assignment.section} has {entry.assignment.subject.code} and {other.assignment.subject.code} on {entry.get_day_display()} at {entry.start_time}-{entry.end_time} / {other.start_time}-{other.end_time}.")
    return messages


def schedule_validation_messages(schedule):
    messages = []
    entries = list(schedule.entries.select_related("assignment__faculty", "assignment__subject", "assignment__section", "room"))
    scheduled_ids = {entry.assignment_id for entry in entries}
    missing = schedule.term.teachingassignment_set.exclude(id__in=scheduled_ids).select_related("subject", "section", "faculty")
    for assignment in missing:
        messages.append(
            f"Unscheduled class: {assignment.subject.code} for {assignment.section}, taught by {assignment.faculty}; "
            f"requires {assignment.required_duration_minutes} minutes in a {assignment.get_required_room_type_override_display() if assignment.required_room_type_override else assignment.subject.get_required_room_type_display()}."
        )
    for entry in entries:
        try:
            entry.full_clean()
        except ValidationError as exc:
            messages.extend(f"{entry.assignment.subject.code} / {entry.assignment.section}: {message}" for message in exc.messages)
    return list(dict.fromkeys(messages))
