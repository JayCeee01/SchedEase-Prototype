from schedules.models import GenerationIssue, TeachingAssignment


CATEGORY_RULES = (
    ("faculty schedule conflict", GenerationIssue.Category.FACULTY_CONFLICT),
    ("faculty conflict", GenerationIssue.Category.FACULTY_CONFLICT),
    ("room schedule conflict", GenerationIssue.Category.ROOM_CONFLICT),
    ("room conflict", GenerationIssue.Category.ROOM_CONFLICT),
    ("section schedule conflict", GenerationIssue.Category.SECTION_CONFLICT),
    ("section conflict", GenerationIssue.Category.SECTION_CONFLICT),
    ("faculty is unavailable", GenerationIssue.Category.FACULTY_UNAVAILABLE),
    ("room is unavailable", GenerationIssue.Category.ROOM_UNAVAILABLE),
    ("room is not available", GenerationIssue.Category.ROOM_UNAVAILABLE),
    ("capacity", GenerationIssue.Category.ROOM_CAPACITY),
    ("room type", GenerationIssue.Category.ROOM_TYPE),
    ("credential", GenerationIssue.Category.FACULTY_CREDENTIAL),
    ("maximum", GenerationIssue.Category.FACULTY_WORKLOAD),
    ("workload", GenerationIssue.Category.FACULTY_WORKLOAD),
    ("duration", GenerationIssue.Category.INVALID_DURATION),
    ("unscheduled", GenerationIssue.Category.UNSCHEDULED),
    ("no active", GenerationIssue.Category.NO_SLOT),
    ("no feasible", GenerationIssue.Category.NO_SLOT),
    ("no available", GenerationIssue.Category.NO_SLOT),
    ("no teaching assignments", GenerationIssue.Category.INVALID_DATA),
)

GUIDANCE = {
    GenerationIssue.Category.FACULTY_CONFLICT: ("A faculty member was assigned to overlapping classes.", "Review the faculty member's assignments and availability."),
    GenerationIssue.Category.ROOM_CONFLICT: ("A room was assigned to overlapping classes.", "Review room availability or add another compatible room."),
    GenerationIssue.Category.SECTION_CONFLICT: ("A section was assigned to overlapping classes.", "Review the section's class requirements and available periods."),
    GenerationIssue.Category.FACULTY_UNAVAILABLE: ("The assigned faculty member is unavailable during the required periods.", "Adjust faculty availability or assign another qualified faculty member."),
    GenerationIssue.Category.ROOM_UNAVAILABLE: ("A compatible room is unavailable during the required periods.", "Adjust room availability or provide another compatible room."),
    GenerationIssue.Category.ROOM_CAPACITY: ("No suitable room has enough capacity for this section.", "Assign a larger compatible room or review the section size."),
    GenerationIssue.Category.ROOM_TYPE: ("The available rooms do not meet this class's room-type requirement.", "Add or activate a compatible room, or verify the subject's room requirement."),
    GenerationIssue.Category.FACULTY_CREDENTIAL: ("The faculty member does not meet this subject's credential requirement.", "Assign qualified faculty or record an authorized credential override."),
    GenerationIssue.Category.FACULTY_WORKLOAD: ("The assigned teaching load exceeds the faculty member's weekly limit.", "Reassign classes or review the faculty workload limit."),
    GenerationIssue.Category.INVALID_DURATION: ("The class duration cannot fit within the configured scheduling window.", "Review the class duration and operating hours."),
    GenerationIssue.Category.NO_SLOT: ("SchedEase could not find a time and room meeting all requirements.", "Review availability, room requirements, and competing assignments."),
    GenerationIssue.Category.UNSCHEDULED: ("A required class was not placed in the schedule.", "Review this class's faculty, room, duration, and availability requirements."),
    GenerationIssue.Category.INVALID_DATA: ("Required scheduling data is missing or invalid.", "Review the academic term, assignments, active rooms, and GA settings."),
    GenerationIssue.Category.GENERATION_FAILURE: ("Schedule generation stopped before a valid result could be saved.", "Review this run's inputs and try again. Contact technical support if it repeats."),
    GenerationIssue.Category.OTHER: ("A scheduling requirement could not be satisfied.", "Review the affected scheduling data and availability."),
}


def category_for(message):
    lowered = message.lower()
    return next((category for phrase, category in CATEGORY_RULES if phrase in lowered), GenerationIssue.Category.OTHER)


def assignment_for(term, message):
    prefix = message.split(":", 1)[0]
    code = prefix.split("/", 1)[0].strip()
    if not code:
        return None
    return (
        TeachingAssignment.objects.filter(term=term, subject__code__iexact=code)
        .select_related("subject", "section", "faculty")
        .first()
    )


def record_generation_messages(run, raw_message, severity=GenerationIssue.Severity.ERROR):
    message = raw_message.replace("Schedule requirements are not feasible:", "").replace("GA could not produce a feasible schedule:", "").strip()
    parts = [part.strip().rstrip(".") for part in message.split(";") if part.strip()]
    if not parts:
        parts = ["Schedule generation could not be completed"]
    issues = []
    for part in dict.fromkeys(parts):
        category = category_for(part)
        reason, action = GUIDANCE[category]
        assignment = assignment_for(run.term, part)
        issues.append(GenerationIssue.objects.create(
            run=run,
            category=category,
            severity=severity,
            assignment=assignment,
            short_description=reason,
            reason=part,
            suggested_action=action,
        ))
    return issues


def record_unexpected_failure(run):
    reason, action = GUIDANCE[GenerationIssue.Category.GENERATION_FAILURE]
    return GenerationIssue.objects.create(
        run=run,
        category=GenerationIssue.Category.GENERATION_FAILURE,
        severity=GenerationIssue.Severity.CRITICAL,
        short_description=reason,
        reason="An unexpected internal error stopped this generation attempt. Technical details were recorded in the server log.",
        suggested_action=action,
    )
