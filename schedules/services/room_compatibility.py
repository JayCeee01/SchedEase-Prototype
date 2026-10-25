"""Component policy, separate from capacity, availability and exact room matching."""
def meeting_room_errors(meeting, subject=None):
    from schedules.models import RoomKind, TeachingAssignment
    if subject is None:
        subject = getattr(meeting, 'subject', None)
    if subject is None:
        parent = getattr(meeting, 'assignment', None)
        subject = getattr(parent, 'subject', None)
    if subject is None:
        return []  # Inline forms validate once their parent course is available.
    required = meeting.required_room_type_override or subject.required_room_type
    label = dict(RoomKind.choices).get(required, str(required))
    prefix = f'{subject.code}, meeting {meeting.meeting_index}: '
    if meeting.component == TeachingAssignment.Component.LECTURE and required != RoomKind.LECTURE:
        return [prefix + f'Lecture requires Lecture Room, not {label}. Select Lecture Room for this meeting.']
    if meeting.component == TeachingAssignment.Component.LABORATORY and required not in {
        RoomKind.COMPUTER_LAB, RoomKind.SCIENCE_LAB, RoomKind.GYM, RoomKind.SPECIAL,
    }:
        return [prefix + f'Laboratory cannot use {label}. Select Computer Laboratory or Science Laboratory; use Gym or Specialized Room only when explicitly configured for this course or meeting.']
    return []
