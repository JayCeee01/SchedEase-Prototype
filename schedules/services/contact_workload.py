"""Dated contact accounting, distinct from institutional workload units.

Partial policy weeks fail closed. Initial accounting uses Monday-Sunday weeks,
without prorating or combining policies.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class ContactEvent:
    identity: tuple
    faculty_id: int
    teaching_date: date
    minutes: int
    education_level: str


def unique_events(events):
    seen = {}
    for event in events:
        if type(event.minutes) is not int or event.minutes <= 0 or event.education_level not in ('SHS', 'TERTIARY'):
            raise ValidationError('Contact events require positive integer minutes and a supported academic level.')
        key = (event.identity, event.teaching_date)
        if key in seen and seen[key] != event:
            raise ValidationError('Duplicated teaching-event representations disagree; resolve the event identity before workload approval.')
        seen[key] = event
    return tuple(seen.values())


def shs_contact_events(config):
    """One event per pattern occurrence, never one per participating section."""
    from .shs_operations import configuration_errors
    errors = configuration_errors(config, complete=True)
    if not config.is_confirmed:
        errors.append('Confirm the operational assignment inputs before workload evaluation.')
    if errors:
        raise ValidationError(errors)
    result = []
    for pattern in config.patterns.select_related('component'):
        if pattern.recurrence == 'DATED':
            dates = [pattern.meeting_date]
        else:
            first = config.starts_on + timedelta(days=(pattern.weekday-config.starts_on.weekday()) % 7)
            dates = [first + timedelta(days=7*i) for i in range(max(0,(config.ends_on-first).days//7+1))]
        result.extend(ContactEvent(('shs-pattern',pattern.pk),config.assignment.faculty_id,day,
            pattern.component.duration_minutes,'SHS') for day in dates)
    return tuple(result)


def published_contact_events(starts_on, ends_on, *, exclude_term_id=None):
    """Expand existing published tertiary recurrence; never guess SHS dates.

    New SHS published event persistence must supply exact event identities and
    dates before integration. The legacy weekly representation is insufficient.
    """
    from schedules.models import ScheduleEntry
    entries = ScheduleEntry.objects.filter(schedule__status='PUBLISHED',
        schedule__term__starts_on__lte=ends_on,schedule__term__ends_on__gte=starts_on)
    if exclude_term_id is not None:
        entries = entries.exclude(schedule__term_id=exclude_term_id)
    result = []
    for entry in entries.select_related('schedule__term','assignment__faculty','assignment__shs_binding','faculty_override'):
        term = entry.schedule.term
        left, right = max(starts_on,term.starts_on), min(ends_on,term.ends_on)
        first = left + timedelta(days=(entry.day-left.weekday()) % 7)
        start,end=entry.start_time,entry.end_time
        if start.second or start.microsecond or end.second or end.microsecond:
            raise ValidationError('Published contact times must use whole minutes.')
        minutes=(end.hour-start.hour)*60+end.minute-start.minute
        if term.education_level == 'SHS':
            from .shs_scheduling import binding
            item=binding(entry.assignment)
            if not item:
                raise ValidationError('Published SHS contact accounting requires persisted teaching dates and event identities.')
            dates=[date.fromisoformat(d) for d in item.data['dates'] if starts_on<=date.fromisoformat(d)<=ends_on]
            identity=('shs-pattern',item.pattern_id)
        else:
            dates=[first+timedelta(days=7*i) for i in range(max(0,(right-first).days//7+1))]
            identity=('published-entry',entry.pk)
        for day in dates:
            result.append(ContactEvent(identity,entry.effective_faculty.pk,day,minutes,term.education_level))
    return unique_events(result)


def validate_weekly_contact_limits(events):
    """Check SHS-touched weeks only; tertiary-only validation is unchanged.

    Callers must supply *all* commitments for the complete relevant weeks,
    including events outside an SHS term's own start/end dates.
    """
    from schedules.models import FacultyContactMinutePolicy
    events = unique_events(events)
    required = {}
    for event in events:
        if event.education_level != 'SHS':
            continue
        policies = list(FacultyContactMinutePolicy.objects.filter(faculty_id=event.faculty_id,
            is_verified=True,is_approved=True,is_active=True,
            starts_on__lte=event.teaching_date,ends_on__gte=event.teaching_date))
        if len(policies) != 1:
            week = event.teaching_date - timedelta(days=event.teaching_date.weekday())
            raise ValidationError(f'Faculty {event.faculty_id}, week {week} through {week+timedelta(days=6)}: configure exactly one verified, approved and active full-week contact-minute policy.')
        policy = policies[0]
        policy.full_clean()
        week = event.teaching_date - timedelta(days=event.teaching_date.weekday())
        end = week+timedelta(days=6)
        if policy.starts_on > week or policy.ends_on < end:
            raise ValidationError(f'Faculty {event.faculty_id}, week {week} through {end}: partial policy-week coverage is not supported. One approved policy must cover the entire Monday-Sunday week; limits are not prorated.')
        required[(event.faculty_id, week)] = policy
    totals = {}
    for (faculty,week),policy in required.items():
        minutes = sum(e.minutes for e in events if e.faculty_id==faculty and week<=e.teaching_date<=week+timedelta(days=6))
        if minutes > policy.maximum_contact_minutes:
            raise ValidationError(f'Faculty {faculty}: {minutes} contact minutes in the calendar week starting {week} exceeds the approved limit of {policy.maximum_contact_minutes}.')
        totals[(faculty,week)] = minutes
    return totals


def published_shs_entries(term):
    """Query definition shared by batch and individual validation."""
    from schedules.models import ScheduleEntry
    return ScheduleEntry.objects.filter(schedule__status='PUBLISHED',
        schedule__term__education_level='SHS', schedule__term__starts_on__lte=term.ends_on,
        schedule__term__ends_on__gte=term.starts_on)


def published_shs_faculty_ids(term):
    from django.db.models.functions import Coalesce
    return set(published_shs_entries(term).values_list(
        Coalesce('faculty_override_id', 'assignment__faculty_id'), flat=True))


def validate_tertiary_with_published_shs(entry, *, published_faculty_ids=None):
    """Revalidate mixed workloads on tertiary edits without changing tertiary-only limits."""
    from schedules.models import ScheduleEntry
    term = entry.schedule.term
    faculty_id = entry.effective_faculty.pk
    from .conflicts import effective_resource_filter
    if published_faculty_ids is None:
        published_faculty_ids = published_shs_faculty_ids(term)
    if faculty_id not in published_faculty_ids:
        return
    left = term.starts_on-timedelta(days=term.starts_on.weekday())
    right = term.ends_on+timedelta(days=6-term.ends_on.weekday())
    events = [e for e in published_contact_events(left,right,exclude_term_id=term.pk)
              if e.faculty_id == faculty_id]
    current = list(entry.schedule.entries.exclude(pk=entry.pk).filter(
        effective_resource_filter('faculty',faculty_id)).select_related('assignment','faculty_override'))
    for item in [*current,entry]:
        first = term.starts_on+timedelta(days=(item.day-term.starts_on.weekday()) % 7)
        minutes = (item.end_time.hour-item.start_time.hour)*60+item.end_time.minute-item.start_time.minute
        if minutes <= 0:
            continue  # Individual entry validation reports invalid durations.
        for index in range(max(0,(term.ends_on-first).days//7+1)):
            events.append(ContactEvent(('candidate-entry',item.pk),faculty_id,
                first+timedelta(days=7*index),minutes,'TERTIARY'))
    validate_weekly_contact_limits(events)
