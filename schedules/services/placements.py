"""Individual placement domains and transient occupancy for GA operators."""
from collections import defaultdict
from types import SimpleNamespace

from django.core.exceptions import ValidationError

from .availability import AvailabilityPolicy
from .conflicts import individual_entry_errors
from .credentials import teaching_eligibility, missing_credential_message
from .meetings import entry_requirement_errors
from .time import ALLOWED_DAYS, add_minutes, overlaps, slot_starts


def feasible_placements(assignment, term, rooms, *, eligible=None, faculty_policy=None, room_policies=None, checkpoint=None, issue_sink=None):
    """Return immutable (room, day, start, end) options and failure explanations.

    No inter-meeting conflicts are checked here. Inputs are a run-local snapshot;
    persistence must still use current database validation.
    """
    entry = SimpleNamespace(assignment=assignment, schedule=SimpleNamespace(term=term, term_id=term.pk),
        effective_subject=assignment.subject, effective_faculty=assignment.faculty, effective_section=assignment.section,
        effective_component=assignment.component)
    errors = entry_requirement_errors(entry, issue_sink=issue_sink)
    if assignment.term_id != term.pk:
        errors.append('The teaching assignment belongs to a different academic term.')
    try:
        assignment.full_clean()
    except ValidationError as exc:
        errors.extend(exc.messages)
    if eligible is None:
        eligible = teaching_eligibility(assignment.faculty, assignment.subject, term, assignment)['eligible']
    if not eligible:
        errors.append(missing_credential_message(assignment.faculty, assignment.subject, term))
    if errors:
        return (), tuple(dict.fromkeys(errors))
    rooms = [room for room in rooms if room.is_active and room.room_type == assignment.effective_room_type
             and room.capacity >= assignment.section.size]
    if not rooms:
        return (), ('No active room matches the required room type and section capacity.',)
    faculty_policy = faculty_policy or AvailabilityPolicy.for_resource(assignment.faculty)
    room_policies = room_policies if room_policies is not None else {
        room.pk: AvailabilityPolicy.for_resource(room) for room in rooms}
    duration = assignment.required_duration_minutes
    grid = tuple(slot_starts(duration))
    options = set()
    for room in rooms:
        policy = room_policies[room.pk]
        for day in ALLOWED_DAYS:
            if checkpoint is not None:
                checkpoint()
            for faculty_start, faculty_end in faculty_policy.effective_intervals(day):
                for room_start, room_end in policy.effective_intervals(day):
                    start, end = max(faculty_start, room_start), min(faculty_end, room_end)
                    if start >= end:
                        continue
                    # Include interval boundaries so narrow/non-grid windows work.
                    starts = set(grid) | {start, add_minutes(end, -duration)}
                    for candidate in sorted(starts):
                        finish = add_minutes(candidate, duration)
                        if not (start <= candidate < finish <= end):
                            continue
                        entry.room, entry.day, entry.start_time, entry.end_time = room, day, candidate, finish
                        if not individual_entry_errors(entry, eligible=eligible,
                                faculty_policy=faculty_policy, room_policy=policy):
                            options.add((room.pk, day, candidate, finish))
    if not options:
        return (), (f'No common faculty and room availability window fits the required {duration} minutes '
                    'within operating hours. Review available and unavailable periods.',)
    return tuple(sorted(options)), ()


class PlacementOccupancy:
    """Only inspect meetings sharing a resource/day; no search or repair."""
    def __init__(self, assignment_map, genes=()):
        self.assignment_map = assignment_map
        self.buckets = defaultdict(list)
        for gene in genes:
            self.add(gene)

    def keys(self, gene):
        assignment = self.assignment_map[gene.assignment_id]
        return (('faculty', assignment.faculty_id, gene.day),
                ('section', assignment.section_id, gene.day), ('room', gene.room_id, gene.day))

    def conflicts(self, gene):
        return any(overlaps(gene.start_time, gene.end_time, other.start_time, other.end_time)
                   for key in self.keys(gene) for other in self.buckets[key])

    def add(self, gene):
        for key in self.keys(gene):
            self.buckets[key].append(gene)
