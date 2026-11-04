"""Read-only timetable projection; this module performs NO authorization.

``present_entries(entries)`` accepts persisted, already-authorized ScheduleEntry
objects (including querysets). It returns dictionaries in input order, retaining
duplicates. It reloads only those entry IDs; unsaved or deleted entries fail.
Dates/times are ISO strings. None means unavailable, never an inferred default.
``recurrence.kind`` is DATED, WEEKLY, or UNKNOWN; DATED contains the complete
explicit date set, not an assertion that the class repeats every week.
``source`` describes core labels; ``operational_source`` separately identifies
immutable SHS binding metadata. Warnings describe incomplete presentation data,
not scheduling approval. This service neither validates nor repairs schedules.

For a materialized input, two SELECTs load entries/relations and snapshots,
independent of entry count. Queryset evaluation adds its own query. Historical
metadata is never supplemented from mutable operational configurations.
"""
from copy import deepcopy
from datetime import date, time

from schedules.models import ScheduleEntry, ScheduleSnapshot, TeachingAssignment
from .shs_scheduling import binding


def _identity(data, label):
    return {'id': data.get('id'), 'label': data.get(label)}


def _recurrence(level, operational, term, weekday, warnings, *, frozen_weekly=False):
    if operational is not None:
        values = operational.get('dates')
        try:
            if not isinstance(values, list) or not values:
                raise ValueError
            dates = tuple(sorted({date.fromisoformat(value) for value in values}))
            if any(day.weekday() != weekday for day in dates):
                raise ValueError
            return {'kind': 'DATED', 'dates': tuple(day.isoformat() for day in dates),
                    'starts_on': dates[0].isoformat(), 'ends_on': dates[-1].isoformat()}
        except (ValueError, TypeError):
            warnings.append('SHS meeting dates are missing or inconsistent.')
    elif level == 'TERTIARY':
        return {'kind': 'WEEKLY', 'dates': None, 'starts_on': term.get('starts_on'),
                'ends_on': term.get('ends_on')}
    elif frozen_weekly:
        warnings.append('Weekly display uses frozen instructional weekdays and times; no calendar dates are asserted.')
        return {'kind': 'WEEKLY', 'dates': None, 'starts_on': None, 'ends_on': None}
    warnings.append('Meeting recurrence is unavailable; no weekly recurrence was assumed.')
    return {'kind': 'UNKNOWN', 'dates': None, 'starts_on': None, 'ends_on': None}


def present_entries(entries):
    """Project only supplied authorized IDs; return detached display dictionaries.

    Fields: entry_id, schedule_id, source, operational_source, subject, faculty,
    room, weekday, start_time, end_time, instructional_label, primary_section,
    participating_sections, participation_complete, academic_context, recurrence,
    warnings. Missing finalized snapshots/rows raise ScheduleSnapshot.DoesNotExist.
    Legacy v1 snapshots retain UNKNOWN education level. Frozen lecture/laboratory
    weekday/time records may support a date-free weekly display, never SHS dates.
    """
    supplied = list(entries)
    if any(not isinstance(e, ScheduleEntry) or e.pk is None or e._state.adding for e in supplied):
        raise ValueError('Supply persisted, already-authorized ScheduleEntry objects.')
    if not supplied:
        return []
    aliases = {e._state.db or 'default' for e in supplied}
    if len(aliases) != 1:
        raise ValueError('Do not combine entries from different databases.')
    alias = aliases.pop()
    relations = ['schedule__term', 'assignment__subject', 'assignment__faculty',
                 'subject_override', 'faculty_override', 'room', 'assignment__shs_binding',
                 'assignment__assignment__shs_configuration__delivery_plan__offering']
    for section in ('assignment__section', 'section_override'):
        relations.extend(section + suffix for suffix in (
            '__program', '__year_level', '__cohort__curriculum_version',
            '__cohort__pathway__curriculum_version'))
    loaded = {e.pk: e for e in ScheduleEntry.objects.using(alias).filter(
        pk__in=[e.pk for e in supplied]).select_related(*relations)}
    if len(loaded) != len({e.pk for e in supplied}):
        raise ScheduleEntry.DoesNotExist('A supplied entry no longer exists.')
    snapshots = {s.schedule_id: s for s in ScheduleSnapshot.objects.using(alias).filter(
        schedule_id__in={e.schedule_id for e in loaded.values()})}
    rows = {pk: {row['id']: row for row in s.data.get('entries', [])}
            for pk, s in snapshots.items()}
    result = []
    for supplied_entry in supplied:
        e = loaded[supplied_entry.pk]
        item = binding(e.assignment)
        historical = e.schedule.status in ('PUBLISHED', 'ARCHIVED') or e.schedule_id in snapshots
        warnings = []
        operational = None
        if item is not None:
            if isinstance(item.data, dict):
                operational = deepcopy(item.data)
            else:
                # Retain the binding's SHS identity, but never infer its contents.
                operational = {}
                warnings.append('SHS binding metadata is malformed and unavailable.')
        if historical:
            snapshot = snapshots.get(e.schedule_id)
            row = rows.get(e.schedule_id, {}).get(e.pk)
            if snapshot is None or row is None:
                raise ScheduleSnapshot.DoesNotExist('Finalized entry history is unavailable.')
            term = deepcopy(snapshot.data.get('term', {}))
            subject = deepcopy(row.get('course', {}))
            faculty = _identity(row.get('faculty', {}), 'full_name')
            room = _identity(row.get('room', {}), 'name')
            primary = _identity(row.get('section', {}), 'display_name')
            weekday, start, end = row.get('day'), row.get('start_time'), row.get('end_time')
            component = row.get('component')
            context = {'term_id': term.get('id'), 'term_name': term.get('name'),
                       'school_year': term.get('school_year'), 'education_level': term.get('education_level'),
                       'cohort_id': None, 'grade_level': None, 'curriculum_version': None,
                       'pathway': None, 'academic_period': None}
            if snapshot.reconstructed:
                warnings.append('Historical snapshot was reconstructed, not captured at original publication.')
        else:
            t, section = e.schedule.term, e.effective_section
            term = {'starts_on': t.starts_on.isoformat(), 'ends_on': t.ends_on.isoformat()}
            subject = {'id': e.effective_subject.pk, 'code': e.effective_subject.code,
                       'title': e.effective_subject.title}
            faculty = {'id': e.effective_faculty.pk, 'label': e.effective_faculty.full_name}
            room = {'id': e.room_id, 'label': e.room.name}
            primary = {'id': section.pk, 'label': section.display_name}
            weekday, start, end = e.day, e.start_time.isoformat(), e.end_time.isoformat()
            component = e.effective_component
            cohort = section.cohort
            config = getattr(e.assignment.assignment, 'shs_configuration', None)
            context = {'term_id': t.pk, 'term_name': t.name, 'school_year': t.school_year,
                       'education_level': t.education_level, 'cohort_id': section.cohort_id,
                       'grade_level': cohort.grade_level if cohort else None,
                       'curriculum_version': str(cohort.curriculum_version) if cohort else None,
                       'pathway': str(cohort.pathway) if cohort and cohort.pathway else None,
                       'academic_period': config.delivery_plan.offering.academic_period if config else None}
        level = 'SHS' if operational is not None else context['education_level']
        context['education_level'] = level
        label = dict(TeachingAssignment.Component.choices).get(component, component)
        participants = (dict(primary),)
        complete = level == 'TERTIARY'
        if operational is not None:
            label = operational.get('instruction') or None
            sections = operational.get('sections')
            if isinstance(sections, list) and sections and all(isinstance(s, dict) and s.get('id') for s in sections):
                participants = tuple({'id': s['id'], 'label': s.get('name')} for s in sections)
                complete = primary['id'] in {s['id'] for s in participants}
                primary_frozen = next((s for s in sections if s['id'] == primary['id']), {})
                if historical:
                    context['cohort_id'] = primary_frozen.get('cohort_id')
        elif level == 'SHS':
            label = None
        if not complete:
            warnings.append('The complete participating-section list is unavailable.')
        if historical:
            warnings.append('Curriculum, pathway, grade and academic-period labels were not captured in this snapshot.')
        frozen_weekly = False
        if historical and level is None and item is None and component in ('LECTURE', 'LABORATORY'):
            try:
                frozen_weekly = (type(weekday) is int and 0 <= weekday <= 6
                                 and time.fromisoformat(start) < time.fromisoformat(end))
            except (TypeError, ValueError):
                pass
        result.append({'entry_id': e.pk, 'schedule_id': e.schedule_id,
            'source': 'FINALIZED_SNAPSHOT' if historical else 'LIVE',
            'operational_source': 'IMMUTABLE_SHS_BINDING' if item else None,
            'subject': {k: subject.get(k) for k in ('id', 'code', 'title')},
            'faculty': faculty, 'room': room, 'weekday': weekday, 'start_time': start, 'end_time': end,
            'instructional_label': label, 'primary_section': primary,
            'participating_sections': participants, 'participation_complete': complete,
            'academic_context': context,
            'recurrence': _recurrence(level, operational, term, weekday, warnings, frozen_weekly=frozen_weekly),
            'warnings': tuple(warnings)})
    return result
