"""Validate operational inputs without constructing TeachingAssignments or GA genes."""
from datetime import timedelta
from django.core.exceptions import ValidationError


def sections(config):
    primary = config.assignment.section
    extra = [row.section for row in config.additional_sections.select_related('section__program', 'section__year_level')] if config.pk else []
    return [primary, *extra]


def pattern_errors(pattern):
    config = pattern.configuration
    errors = []
    if pattern.component.plan_id != config.delivery_plan_id:
        errors.append('The instructional component must belong to this delivery plan.')
    if not pattern.room.is_active or pattern.room.room_type != pattern.required_room_type:
        errors.append('Select an active room matching the explicitly approved room type.')
    if pattern.room.capacity < sum(section.size for section in sections(config)):
        errors.append('Room capacity must cover all participating sections.')
    if pattern.window_start and pattern.window_end:
        from .time import SCHOOL_START, SCHOOL_END
        start, end = pattern.window_start, pattern.window_end
        if start < SCHOOL_START or end > SCHOOL_END:
            errors.append('The operating window is outside the currently supported school hours; confirm an operating-hours policy before using it.')
        if start.second or start.microsecond or end.second or end.microsecond:
            errors.append('Operating windows must use whole minutes.')
        minutes = (end.hour-start.hour)*60 + end.minute-start.minute
        if minutes < pattern.component.duration_minutes:
            errors.append('The approved operating window cannot fit the component meeting duration.')
    if pattern.recurrence == 'DATED' and pattern.meeting_date:
        if pattern.meeting_date.weekday() != pattern.weekday:
            errors.append('The weekday must match the meeting date.')
        if config.starts_on and config.ends_on and not config.starts_on <= pattern.meeting_date <= config.ends_on:
            errors.append('The meeting date must fall within the effective teaching dates.')
    return errors


def occurrences(pattern, config):
    if pattern.recurrence == 'DATED':
        return 1
    first = config.starts_on + timedelta(days=(pattern.weekday-config.starts_on.weekday()) % 7)
    return max(0, (config.ends_on-first).days // 7 + 1)


def configuration_errors(config, *, complete=True):
    from schedules.models import Assignment, DeliveryPlan
    assignment = Assignment.objects.select_related('term', 'subject', 'faculty', 'section__program', 'section__year_level').get(pk=config.assignment_id)
    plan = DeliveryPlan.objects.select_related('offering__requirement', 'offering__cohort').get(pk=config.delivery_plan_id)
    config.assignment, config.delivery_plan = assignment, plan
    offering = plan.offering
    errors = []
    if assignment.term_id != offering.academic_term_id or assignment.subject_id != offering.requirement.subject_id:
        errors.append('Assignment term and subject must match the delivery-plan offering.')
    if assignment.term.education_level != 'SHS':
        errors.append('SHS inputs require an SHS academic term.')
    participants = sections(config)
    for section in participants:
        if section.program.education_level != 'SHS' or section.cohort_id != offering.cohort_id or section.year_level.level != offering.cohort.grade_level:
            errors.append('Every participating section must match the offering cohort, grade and SHS level.')
    if len({s.pk for s in participants}) != len(participants):
        errors.append('A section cannot participate twice.')
    if len(participants) > 1 and not config.combined_class_reference.strip():
        errors.append('Combined sections require an institutional approval reference.')
    if config.starts_on and config.ends_on:
        if not assignment.term.starts_on <= config.starts_on <= config.ends_on <= assignment.term.ends_on:
            errors.append('Teaching dates must be ordered and contained in the academic term.')
    if not complete:
        return errors
    if plan.effective_status != 'Approved configuration':
        errors.append('The delivery plan and its curriculum configuration must remain approved.')
    if not config.starts_on or not config.ends_on or not config.calendar_reference.strip():
        errors.append('Effective teaching dates and calendar/operating-window approval are required.')
    from .credentials import teaching_eligibility, missing_credential_message
    if not teaching_eligibility(assignment.faculty, assignment.subject, assignment.term)['eligible']:
        errors.append(missing_credential_message(assignment.faculty, assignment.subject, assignment.term))
    patterns = list(config.patterns.select_related('component', 'room')) if config.pk else []
    if not patterns:
        errors.append('Configure instructional meeting patterns before confirming inputs.')
    for pattern in patterns:
        # Use the candidate config rather than the stored version while editing dates.
        pattern.configuration = config
        try:
            pattern.full_clean()
        except ValidationError as exc:
            errors.extend(exc.messages)
    if config.starts_on and config.ends_on and config.starts_on <= config.ends_on:
        basis = offering.requirement.measurement_basis
        for component in plan.components.all():
            own = [p for p in patterns if p.component_id == component.pk]
            if basis == 'WEEK' and any(p.recurrence != 'WEEKLY' for p in own):
                errors.append('Weekly requirements need weekly patterns; dated exception handling requires a separately approved policy.')
            count = len(own) if basis == 'WEEK' else sum(occurrences(p, config) for p in own)
            if count != component.meeting_count:
                errors.append(f'{component.instruction}: expected {component.meeting_count} meetings {"per week" if basis == "WEEK" else "in the period"}; configured {count}.')
            if any(occurrences(p, config) == 0 for p in own):
                errors.append('A weekly pattern has no occurrence within the effective teaching dates.')
    return list(dict.fromkeys(errors))
