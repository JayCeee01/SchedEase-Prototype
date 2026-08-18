from collections import Counter, defaultdict
from datetime import datetime, date

from schedules.models import AvailabilityKind
from .conflicts import conflict_messages
from .credentials import faculty_qualification
from .room_utilization import utilization_rows, utilization_summary
from .time import contains


def _minutes(value):
    return value.hour * 60 + value.minute


def _idle_gap_hours(entries, owner):
    buckets = defaultdict(list)
    for entry in entries:
        key = entry.assignment.faculty_id if owner == "faculty" else entry.assignment.section_id
        buckets[(key, entry.day)].append(entry)
    total = 0
    for values in buckets.values():
        values.sort(key=lambda entry: entry.start_time)
        total += sum(max(0, _minutes(right.start_time) - _minutes(left.end_time))
                     for left, right in zip(values, values[1:]))
    return round(total / 60, 2)


def schedule_metrics(schedule):
    if schedule is None:
        return None
    entries = list(schedule.entries.select_related(
        "assignment__faculty", "assignment__section", "assignment__subject", "room"))
    messages = conflict_messages(entries)
    conflict_counts = Counter(message.split(":", 1)[0] for message in messages)
    credential_violations = 0
    preferred = 0
    for entry in entries:
        assignment = entry.assignment
        if (not faculty_qualification(assignment.faculty, assignment.subject)["qualified"]
                and not assignment.credential_overrides.exists()):
            credential_violations += 1
        slots = assignment.faculty.availability_set.filter(day=entry.day, kind=AvailabilityKind.PREFERRED)
        if any(contains(slot.start_time, slot.end_time, entry.start_time, entry.end_time) for slot in slots):
            preferred += 1
    used_room_ids = {entry.room_id for entry in entries}
    room_rows = [row for row in utilization_rows(schedule) if row.room.id in used_room_ids]
    return {"schedule_id": schedule.id, "name": schedule.name, "origin": schedule.origin,
        "fitness_score": schedule.fitness_score, "total_classes": len(entries),
        "faculty_conflicts": conflict_counts["Faculty conflict"],
        "room_conflicts": conflict_counts["Room conflict"],
        "section_conflicts": conflict_counts["Section conflict"],
        "credential_violations": credential_violations,
        "faculty_preferences_satisfied": preferred,
        "faculty_preference_rate": round(preferred / len(entries) * 100, 1) if entries else 0,
        "faculty_idle_gap_hours": _idle_gap_hours(entries, "faculty"),
        "section_idle_gap_hours": _idle_gap_hours(entries, "section"),
        "room_utilization": utilization_summary(room_rows)}


def compare_schedules(term, original, generated=None, failed_reason=""):
    requirements = set(term.teachingassignment_set.values_list("id", flat=True))
    generated_ids = set(generated.entries.values_list("assignment_id", flat=True)) if generated else set()
    unscheduled = term.teachingassignment_set.filter(id__in=requirements - generated_ids).select_related("subject", "section", "faculty")
    return {"term": str(term), "requirements": len(requirements),
        "original": schedule_metrics(original), "generated": schedule_metrics(generated),
        "generation_status": "complete" if generated and len(generated_ids) == len(requirements) else "infeasible_or_incomplete",
        "successfully_scheduled_classes": len(generated_ids), "unscheduled_classes": len(requirements - generated_ids),
        "failure_reason": failed_reason or ("No SchedEase-generated schedule exists for this term." if not generated else ""),
        "unscheduled_requirements": [{"assignment_id": item.id, "source_key": item.source_key,
            "subject": item.subject.code, "section": str(item.section), "faculty": item.faculty.full_name,
            "reason": failed_reason or "No feasible generated placement was saved."} for item in unscheduled]}
