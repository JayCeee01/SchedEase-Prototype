from django.core.exceptions import ValidationError
from schedules.models import AvailabilityKind
from .credentials import missing_credential_message, faculty_qualification
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, contains, overlaps


def validate_entry(entry):
    errors = []
    if entry.day not in ALLOWED_DAYS:
        errors.append("Classes must be scheduled Monday to Saturday.")
    if not contains(SCHOOL_START, SCHOOL_END, entry.start_time, entry.end_time):
        errors.append("Classes must be scheduled from 7:00 AM to 9:00 PM.")
    if entry.start_time >= entry.end_time:
        errors.append("Start time must be earlier than end time.")
    if entry.room.capacity < entry.assignment.section.size:
        errors.append("Room capacity is too small for the section.")
    if entry.room.room_type != entry.assignment.subject.required_room_type:
        errors.append("Room type does not match the subject requirement.")
    if not faculty_qualification(entry.assignment.faculty, entry.assignment.subject)["qualified"] and not entry.assignment.credential_overrides.exists():
        errors.append(missing_credential_message(entry.assignment.faculty, entry.assignment.subject))

    faculty_blocks = entry.assignment.faculty.availability_set.filter(day=entry.day, kind=AvailabilityKind.UNAVAILABLE)
    if any(overlaps(entry.start_time, entry.end_time, a.start_time, a.end_time) for a in faculty_blocks):
        errors.append("Faculty is unavailable during this time.")

    qs = entry.schedule.entries.exclude(pk=entry.pk).filter(day=entry.day)
    for other in qs.select_related("assignment__faculty", "assignment__section", "room"):
        if not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
            continue
        if other.assignment.faculty_id == entry.assignment.faculty_id:
            errors.append("Faculty schedule conflict.")
        if other.room_id == entry.room_id:
            errors.append("Room schedule conflict.")
        if other.assignment.section_id == entry.assignment.section_id:
            errors.append("Section schedule conflict.")

    if errors:
        raise ValidationError(errors)


def conflict_messages(entries):
    messages = []
    for idx, entry in enumerate(entries):
        for other in entries[idx + 1 :]:
            if entry.day != other.day or not overlaps(entry.start_time, entry.end_time, other.start_time, other.end_time):
                continue
            if entry.assignment.faculty_id == other.assignment.faculty_id:
                messages.append(f"Faculty conflict: {entry.assignment.faculty} overlaps on {entry.get_day_display()}.")
            if entry.room_id == other.room_id:
                messages.append(f"Room conflict: {entry.room} overlaps on {entry.get_day_display()}.")
            if entry.assignment.section_id == other.assignment.section_id:
                messages.append(f"Section conflict: {entry.assignment.section} overlaps on {entry.get_day_display()}.")
    return messages
