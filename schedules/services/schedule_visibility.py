"""Student authorization from frozen identities, never presentation or live participation.

The queryset interface enforces PUBLISHED itself, preserves ordering, and batches
snapshot/binding reads. Missing historical evidence fails closed. Faculty/admin
policy remains the responsibility of the existing role-aware caller.
"""
from schedules.models import ScheduleSnapshot, ScheduleStatus


def _id(value):
    return type(value) is int and value > 0


def _rows(data, schedule_id):
    if not isinstance(data, dict) or not isinstance(data.get('schedule'), dict):
        return {}
    identity = data['schedule'].get('id')
    if not _id(identity) or identity != schedule_id or not isinstance(data.get('entries'), list):
        return {}
    result = {}
    for row in data['entries']:
        if not isinstance(row, dict) or not _id(row.get('id')) or row['id'] in result:
            return {}
        result[row['id']] = row
    return result


def _additional(data, row, term_id, section_id):
    if not isinstance(data, dict):
        return False
    if any(not _id(data.get(key)) for key in ('configuration_id', 'plan_id', 'component_id', 'subject_id')):
        return False
    course = row.get('course')
    if not isinstance(course, dict) or not _id(course.get('id')) or data['subject_id'] != course['id']:
        return False
    if not _id(data.get('term_id')) or data['term_id'] != term_id:
        return False
    participants = data.get('sections')
    if not isinstance(participants, list) or not participants:
        return False
    ids = []
    for participant in participants:
        if not isinstance(participant, dict) or not _id(participant.get('id')):
            return False
        ids.append(participant['id'])
    # The preparation contract puts the primary section first. No inferred or
    # partially valid lists: a corrupt list cannot confer additional access.
    if len(set(ids)) != len(ids) or ids[0] != row['section']['id']:
        return False
    approval = data.get('combined_reference')
    return isinstance(approval, str) and bool(approval.strip()) and section_id in ids


def student_entries(entries, section_id):
    """Return only published entries supported by frozen student membership."""
    published = entries.filter(schedule__status=ScheduleStatus.PUBLISHED)
    if not _id(section_id):
        return published.none()
    candidates = list(published.values_list(
        'pk', 'schedule_id', 'assignment_id', 'schedule__term_id',
        'assignment__shs_binding__data'))
    snapshots = {
        schedule_id: _rows(data, schedule_id)
        for schedule_id, data in ScheduleSnapshot.objects.using(entries.db).filter(
            schedule_id__in={item[1] for item in candidates}
        ).values_list('schedule_id', 'data')
    }
    allowed = set()
    for pk, schedule_id, meeting_id, term_id, binding in candidates:
        row = snapshots.get(schedule_id, {}).get(pk)
        if not row or not _id(row.get('meeting_id')) or row['meeting_id'] != meeting_id:
            continue
        primary = row.get('section')
        if not isinstance(primary, dict) or not _id(primary.get('id')):
            continue
        if primary['id'] == section_id or _additional(binding, row, term_id, section_id):
            allowed.add(pk)
    return published.filter(pk__in=allowed).distinct()
