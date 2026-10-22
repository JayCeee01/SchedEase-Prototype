"""Shared H5 requirements. Durations are integer minutes; no implicit meeting counts."""
from collections import defaultdict
from datetime import date, datetime, timedelta


def duration_errors(minutes):
    """Validate effective duration; stored zero is resolved by the meeting model."""
    from .time import SCHOOL_START, SCHOOL_END
    maximum = (SCHOOL_END.hour * 60 + SCHOOL_END.minute) - (SCHOOL_START.hour * 60 + SCHOOL_START.minute)
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 1:
        return ["Meeting duration must be a positive whole number of minutes (at least 1)."]
    if minutes > maximum:
        return [f"Meeting duration exceeds the {maximum}-minute school day. Split it into shorter meetings."]
    return []


def meeting_requirement_errors(subject, meetings):
    """Return (column, message) pairs for (index, component, minutes) records."""
    totals = {"LECTURE": 0, "LABORATORY": 0}
    seen = set()
    errors = []
    for index, component, minutes in meetings:
        if index in seen:
            errors.append(("meeting_index", "Meeting indexes must be unique within an assignment."))
        seen.add(index)
        if component not in totals:
            errors.append(("component", "Choose LECTURE or LABORATORY to match the course hours."))
        else:
            totals[component] += minutes
        errors.extend(("duration_minutes", message) for message in duration_errors(minutes))
    if not seen:
        errors.append(("meeting_index", "Add at least one meeting."))
    for component, hours in (("LECTURE", subject.lecture_hours), ("LABORATORY", subject.lab_hours)):
        expected = hours * 60
        if totals[component] != expected:
            errors.append(("duration_minutes", f"{component} totals {totals[component]} minutes; course requires {expected}."))
    return errors


def meeting_records(meetings):
    return [(m.meeting_index, m.component, m.required_duration_minutes) for m in meetings]


def entry_requirement_errors(entry, issue_sink=None):
    from .diagnostics import Diagnostic
    errors = duration_errors(entry.assignment.required_duration_minutes)
    if issue_sink is not None:
        issue_sink.extend(Diagnostic.for_meetings('INVALID_DURATION', message, [entry.assignment]) for message in errors)
    duration_count = len(errors)
    if entry.effective_subject.pk != entry.assignment.subject_id:
        errors.append("Course must match the assigned course. Edit the assignment to change its requirements.")
    if entry.effective_component != entry.assignment.component:
        errors.append("Session type must match the assigned meeting component.")
    component = entry.assignment.component
    hours = {"LECTURE": entry.assignment.subject.lecture_hours, "LABORATORY": entry.assignment.subject.lab_hours}
    if component not in hours or not hours[component]:
        errors.append("Meeting component does not match the course's lecture/laboratory requirements. Correct the assignment first.")
    if issue_sink is not None:
        issue_sink.extend(Diagnostic.for_meetings('INVALID_DATA', message, [entry.assignment],
            details={'constraint': 'meeting_requirements'}) for message in errors[duration_count:])
    return errors


def scheduled_requirement_errors(schedule, entries, issue_sink=None):
    """Validate actual time spans against each parent's requirements, including empty parents."""
    grouped = defaultdict(list)
    for entry in entries:
        elapsed = datetime.combine(date.min, entry.end_time) - datetime.combine(date.min, entry.start_time)
        minutes, remainder = divmod(elapsed, timedelta(minutes=1))
        if remainder:
            grouped[entry.assignment.assignment_id].append((entry.assignment.meeting_index, entry.effective_component, 0))
        else:
            grouped[entry.assignment.assignment_id].append((entry.assignment.meeting_index, entry.effective_component, minutes))
    errors = []
    for parent in schedule.term.assignment_set.select_related("subject", "section"):
        for _, message in meeting_requirement_errors(parent.subject, grouped[parent.pk]):
            text = f"{parent.subject.code} / {parent.section}: {message}"
            errors.append(text)
            if issue_sink is not None:
                from .diagnostics import Diagnostic
                issue_sink.append(Diagnostic('INVALID_DATA', text,
                    tuple(parent.meetings.values_list('pk', flat=True)), (parent.pk,),
                    details={'constraint': 'component_totals'}))
    return errors
