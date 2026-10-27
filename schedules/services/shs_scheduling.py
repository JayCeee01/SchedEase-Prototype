"""SHS adapters for the shared engine; no alternate solver or bypass flags."""
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.db import transaction


def binding(meeting):
    return getattr(meeting, 'shs_binding', None)


def participant_ids(meeting):
    item = binding(meeting)
    return tuple(row['id'] for row in item.data['sections']) if item else (meeting.section_id,)


def participant_size(meeting):
    item = binding(meeting)
    return sum(row['size'] for row in item.data['sections']) if item else meeting.section.size


def dates_overlap(left, right, day):
    a, b = binding(left), binding(right)
    if a and b:
        return bool(set(a.data['dates']) & set(b.data['dates']))
    if not a and not b:
        return True
    item, other = (a, right) if a else (b, left)
    return any(other.term.starts_on <= date.fromisoformat(d) <= other.term.ends_on
               and date.fromisoformat(d).weekday() == day for d in item.data['dates'])


def pattern_snapshot(pattern):
    from .shs_operations import sections
    config = pattern.configuration
    if pattern.recurrence == 'DATED':
        dates = [pattern.meeting_date]
    else:
        first = config.starts_on + timedelta(days=(pattern.weekday-config.starts_on.weekday()) % 7)
        dates = [first+timedelta(days=7*i) for i in range(max(0,(config.ends_on-first).days//7+1))]
    return dict(configuration_id=config.pk, plan_id=config.delivery_plan_id,
        subject_id=config.assignment.subject_id, faculty_id=config.assignment.faculty_id,
        term_id=config.assignment.term_id, component_id=pattern.component_id,
        instruction=pattern.component.instruction, minutes=pattern.component.duration_minutes,
        day=pattern.weekday, dates=[d.isoformat() for d in dates], room_id=pattern.room_id,
        room_type=pattern.required_room_type, window_start=pattern.window_start.isoformat(),
        window_end=pattern.window_end.isoformat(), calendar_reference=config.calendar_reference,
        room_reference=pattern.room_approval_reference,
        combined_reference=config.combined_class_reference,
        sections=[dict(id=s.pk,name=s.display_name,size=s.size,cohort_id=s.cohort_id) for s in sections(config)])


def validate_configurations(term):
    from schedules.models import SHSAssignmentConfiguration
    from .shs_operations import configuration_errors
    from .contact_workload import shs_contact_events, published_contact_events, validate_weekly_contact_limits
    configs=list(SHSAssignmentConfiguration.objects.filter(assignment__term=term).select_related('assignment','delivery_plan'))
    if not configs or {c.assignment_id for c in configs} != set(term.assignment_set.values_list('pk',flat=True)):
        raise ValidationError('Every SHS assignment needs an explicit operational configuration.')
    events=[]
    for config in configs:
        errors=configuration_errors(config,complete=True)
        if not config.is_confirmed:
            errors.append('Confirm the SHS operational inputs before generation.')
        if errors:
            raise ValidationError(errors)
        events.extend(shs_contact_events(config))
    first=min(e.teaching_date for e in events)
    last=max(e.teaching_date for e in events)
    first-=timedelta(days=first.weekday())
    last+=timedelta(days=6-last.weekday())
    external=published_contact_events(first,last,exclude_term_id=term.pk)
    faculty_ids={e.faculty_id for e in events}
    validate_weekly_contact_limits([*events,*(e for e in external if e.faculty_id in faculty_ids)])
    return configs


def assert_prepared(term):
    configs=validate_configurations(term)
    expected={p.pk for c in configs for p in c.patterns.all()}
    meetings=list(term.teachingassignment_set.select_related('shs_binding__pattern__configuration'))
    if len(meetings) != len(expected) or not meetings or any(binding(m) is None for m in meetings) or {binding(m).pattern_id for m in meetings} != expected:
        raise ValidationError('Prepare validated SHS operational meetings through the controlled adapter before generation.')
    for meeting in meetings:
        item=binding(meeting)
        if (meeting.assignment_id != item.pattern.configuration.assignment_id
                or meeting.section_id != item.pattern.configuration.assignment.section_id
                or meeting.component != 'GENERAL'):
            raise ValidationError('The SHS meeting must retain its approved parent, section and instructional component.')
        if item.data != pattern_snapshot(item.pattern):
            raise ValidationError('SHS operational inputs changed after meeting preparation; do not reuse this meeting snapshot.')
        if (meeting.faculty_id,meeting.subject_id,meeting.term_id,meeting.duration_minutes,meeting.required_room_type_override) != (item.data['faculty_id'],item.data['subject_id'],item.data['term_id'],item.data['minutes'],item.data['room_type']):
            raise ValidationError('The prepared SHS meeting no longer matches its approved operational snapshot.')
    return meetings


@transaction.atomic
def generate_shs(term, settings, *, actor, seed=None, name='SHS schedule'):
    """Only validated records create shared meetings; failed runs roll back."""
    from schedules.models import TeachingAssignment, SHSMeetingBinding
    from .ga import GeneticScheduler
    from .manual_edits import authorized_administrator
    authorized_administrator(actor)
    if term.education_level != 'SHS':
        raise ValidationError('The controlled SHS adapter requires an SHS term.')
    configs=validate_configurations(term)
    if not term.teachingassignment_set.exists():
        for config in configs:
            for index,pattern in enumerate(config.patterns.select_related('component','room').order_by('component_id','sequence'),1):
                meeting=TeachingAssignment.objects.create(assignment=config.assignment,component='GENERAL',
                    meeting_index=index,duration_minutes=pattern.component.duration_minutes,
                    required_room_type_override=pattern.required_room_type)
                SHSMeetingBinding.objects.create(meeting=meeting,pattern=pattern,data=pattern_snapshot(pattern))
    assert_prepared(term)
    return GeneticScheduler(term,settings,seed=seed).generate(name=name)


def entry_errors(entry):
    from datetime import time
    from .availability import AvailabilityPolicy
    from schedules.models import Section
    item=binding(entry.assignment)
    if not item:
        return ['SHS meeting is missing its validated operational snapshot.']
    data=item.data
    errors=[]
    if not hasattr(entry,'room'):
        return errors  # Requirement-only preflight; placement fields follow later.
    if entry.day != data['day'] or entry.room.pk != data['room_id']:
        errors.append('SHS weekday and room must match the approved meeting pattern.')
    if entry.start_time < time.fromisoformat(data['window_start']) or entry.end_time > time.fromisoformat(data['window_end']):
        errors.append('SHS meeting falls outside its approved operating window.')
    if entry.effective_faculty.pk != data['faculty_id'] or entry.effective_subject.pk != data['subject_id'] or entry.effective_section.pk != entry.assignment.section_id:
        errors.append('SHS faculty, subject and primary section must match the approved operational assignment.')
    if entry.room.capacity < participant_size(entry.assignment):
        errors.append('Room capacity is insufficient for the combined sections.')
    for section in Section.objects.filter(pk__in=participant_ids(entry.assignment)):
        policy=AvailabilityPolicy.for_resource(section)
        if policy.configured and policy.rejection_reason(entry.day,entry.start_time,entry.end_time):
            errors.append('A participating SHS section is unavailable in this time window.')
    return errors
