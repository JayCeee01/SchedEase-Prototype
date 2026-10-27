"""Bounded, run-local repair; shared validation and placement domains stay authoritative."""
from collections import defaultdict
from types import SimpleNamespace

from .conflicts import individual_entry_errors


def overlap_conflicts(chromosome, assignment_map):
    """Return (resource kind, left index, right index), once per resource clash."""
    from .shs_scheduling import participant_ids, dates_overlap
    buckets = defaultdict(list)
    for index, gene in enumerate(chromosome):
        assignment = assignment_map[gene.assignment_id]
        for kind, pk in (("faculty", assignment.faculty_id), ("room", gene.room_id),
                         *(("section",pk) for pk in participant_ids(assignment))):
            buckets[kind, gene.day, pk].append((index, gene))
    conflicts = set()
    for (kind, _, _), items in buckets.items():
        active = []
        for index, gene in sorted(items, key=lambda item: item[1].start_time):
            active = [(i, g) for i, g in active if g.end_time > gene.start_time]
            for other_index, _ in active:
                if dates_overlap(assignment_map[gene.assignment_id],assignment_map[chromosome[other_index].assignment_id],gene.day):
                    conflicts.add((kind, min(index, other_index), max(index, other_index)))
            active.append((index, gene))
    return conflicts


def candidate_issues(scheduler, chromosome):
    individual = {}
    for index, gene in enumerate(chromosome):
        # Cached domain members have already passed the same individual rules.
        if gene in scheduler._placement_sets.get(gene.assignment_id, ()):
            continue
        assignment = scheduler.assignment_map[gene.assignment_id]
        entry = SimpleNamespace(assignment=assignment,
            schedule=SimpleNamespace(term=scheduler.term, term_id=scheduler.term.pk),
            effective_subject=assignment.subject, effective_faculty=assignment.faculty,
            effective_section=assignment.section, effective_component=assignment.component,
            room=scheduler.room_map[gene.room_id], day=gene.day,
            start_time=gene.start_time, end_time=gene.end_time)
        errors = individual_entry_errors(entry, eligible=scheduler.qualification_cache[assignment.pk],
            faculty_policy=scheduler.faculty_policies[assignment.faculty_id],
            room_policy=scheduler.room_policies[gene.room_id],
            section_policy=scheduler.section_policies[assignment.section_id])
        if errors:
            individual[index] = tuple(errors)
    conflicts = overlap_conflicts(chromosome, scheduler.assignment_map)
    affected = set(individual) | {index for _, left, right in conflicts for index in (left, right)}
    return individual, conflicts, affected


def _cycle(options, start, direction):
    for offset in range(len(options)):
        yield options[(start + direction * offset) % len(options)]


def repair_candidate(scheduler, chromosome, budget):
    """Strictly decreasing local search, with at most budget alternative evaluations.

    Freeze initially unaffected genes. Reject newly introduced overlap pairs even
    if the overall count drops. Each alternative is tried once per candidate state.
    No database writes; unresolved candidates remain available for GA selection.
    """
    current = list(chromosome)
    before = scheduler.fitness(current).hard_violations
    hard = before
    individual, conflicts, affected = candidate_issues(scheduler, current)
    movable = affected.copy()
    attempts = moves = 0
    while affected and attempts < budget:
        indexes = sorted(affected & movable)
        scheduler.random.shuffle(indexes)
        alternatives = {}
        for index in indexes:
            try:
                options = scheduler.placement_options(scheduler.assignment_map[current[index].assignment_id])
            except ValueError:
                # Normal runs reject empty domains in preflight; a standalone
                # repair still leaves an unrepairable candidate intact.
                continue
            start = scheduler.random.randrange(len(options))
            direction = scheduler.random.choice((-1, 1))
            alternatives[index] = _cycle(options, start, direction)
        improved = False
        while alternatives and attempts < budget and not improved:
            for index in list(alternatives):
                option = next(alternatives[index], None)
                if option is None:
                    del alternatives[index]
                    continue
                if option == current[index]:
                    continue
                attempts += 1
                trial = current.copy()
                trial[index] = option
                trial_hard = scheduler.fitness(trial).hard_violations
                if trial_hard < hard:
                    trial_conflicts = overlap_conflicts(trial, scheduler.assignment_map)
                    if trial_conflicts <= conflicts:
                        current, hard = trial, trial_hard
                        moves += 1
                        individual, conflicts, affected = candidate_issues(scheduler, current)
                        improved = True
                        break
                if attempts >= budget:
                    break
        if not improved:
            break
    status = ("unchanged" if not movable and not hard else
              "repaired" if not affected and not hard else "partial" if moves else "unresolved")
    return current, {"status": status, "hard_before": before, "hard_after": hard,
                     "attempts": attempts, "moves": moves,
                     "remaining_affected": sorted(affected), "individual_errors": individual}
