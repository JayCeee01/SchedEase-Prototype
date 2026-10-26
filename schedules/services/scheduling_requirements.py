"""Read-only foundation. No consumers or SHS generation are enabled here."""
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError

from .resource_occupancy import published_commitments


@dataclass(frozen=True)
class InstructionRequirement:
    identity: int
    label: str
    minutes_per_meeting: int
    meeting_count: int
    basis: str


@dataclass(frozen=True)
class SchedulingRequirements:
    education_level: str
    term_id: int
    calendar_context: str
    calendar_bounds: tuple[date, date]
    curriculum_version_id: int | None
    cohort_id: int | None
    offering_id: int | None
    delivery_plan_id: int | None
    components: tuple
    faculty_id: int | None
    section_ids: tuple
    compatible_room_ids: tuple | None
    teaching_dates: tuple[date, date] | None
    recurrence: str | None
    published_occupancy: tuple
    workload_policy: str | None
    weekly_limit_minutes: int | None
    blockers: tuple

    def require_schedulable(self):
        if self.blockers:
            raise ValidationError(list(self.blockers))
        return self


def resolve_tertiary(meeting_id):
    """Represent the existing meeting contract without changing its consumers.

    Compatible rooms match static capacity/type only; availability, credentials,
    placement and publication must still use their existing validation services.
    """
    from schedules.models import TeachingAssignment, Room, EducationLevel
    meeting = TeachingAssignment.objects.select_related('term', 'section__program', 'faculty', 'subject').get(pk=meeting_id)
    if meeting.term.education_level != EducationLevel.TERTIARY or meeting.section.program.education_level != EducationLevel.TERTIARY:
        raise ValidationError('SHS meetings cannot use the tertiary requirements adapter.')
    meeting.full_clean()
    term = meeting.term
    rooms = tuple(Room.objects.filter(is_active=True, room_type=meeting.effective_room_type,
                                     capacity__gte=meeting.section.size).order_by('pk').values_list('pk', flat=True))
    return SchedulingRequirements('TERTIARY', term.pk, term.calendar_context, (term.starts_on, term.ends_on),
        None, None, None, None,
        (InstructionRequirement(meeting.pk, meeting.component, meeting.required_duration_minutes, 1, 'WEEK'),),
        meeting.faculty_id, (meeting.section_id,), rooms, (term.starts_on, term.ends_on), 'WEEKLY',
        published_commitments(term), 'Existing per-schedule tertiary weekly contact-hour limit',
        meeting.faculty.max_weekly_hours * 60, ())


def resolve_shs(plan_id):
    """Expose approved contact requirements but fail closed for scheduling."""
    from schedules.models import DeliveryPlan
    try:
        plan = DeliveryPlan.objects.select_related('offering__requirement', 'offering__cohort', 'offering__academic_term').get(pk=plan_id)
    except DeliveryPlan.DoesNotExist as exc:
        raise ValidationError('An existing SHS delivery plan is required.') from exc
    offering, requirement = plan.offering, plan.offering.requirement
    term = offering.academic_term
    blockers = list(plan.approval_errors())
    if not plan.is_approved:
        blockers.append('The delivery plan has not been approved.')
    blockers.extend((
        'SHS generation is disabled in this foundation phase.',
        'Faculty assignments and participating sections or teaching groups are not configured.',
        'Component-specific room eligibility has not been established.',
        'Effective teaching dates and dated or weekly meeting recurrence require confirmation.',
        'SHS workload units, conversions and combined workload policy are not verified.',
    ))
    components = tuple(InstructionRequirement(item.pk, item.instruction, item.duration_minutes,
        item.meeting_count, requirement.measurement_basis) for item in plan.components.all())
    return SchedulingRequirements('SHS', term.pk, term.calendar_context, (term.starts_on, term.ends_on),
        requirement.curriculum_version_id, offering.cohort_id, offering.pk, plan.pk, components,
        None, (), None, None, None, published_commitments(term), None, None, tuple(blockers))
