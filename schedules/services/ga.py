import random
from copy import copy
from time import perf_counter
from collections import defaultdict
from dataclasses import dataclass, asdict
from functools import total_ordering
from datetime import time

from django.utils import timezone

from schedules.models import AvailabilityKind, Room, RoomKind, Schedule, ScheduleEntry, TeachingAssignment, GenerationRun
from .availability import AvailabilityPolicy
from .reproducibility import choose_seed, initial_metadata, input_summary, finished_metadata
from .generation_issues import fail_run, unexpected_diagnostic
from .diagnostics import Diagnostic, GenerationFailure
from .generation_lock import generation_lease, GenerationLeaseLost
from .placements import feasible_placements, PlacementOccupancy
from .meetings import duration_errors
from .repair import overlap_conflicts, repair_candidate
from .credentials import teaching_eligibility
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, add_minutes, contains, slot_starts


@dataclass(frozen=True)
class Gene:
    assignment_id: int
    room_id: int
    day: int
    start_time: time
    end_time: time


@total_ordering
@dataclass(frozen=True)
class Fitness:
    """Higher is better: fewer hard violations, then higher soft score."""
    hard_violations: int
    soft_score: float

    def __lt__(self, other):
        if not isinstance(other, Fitness):
            return NotImplemented
        return (-self.hard_violations, self.soft_score) < (-other.hard_violations, other.soft_score)


class GeneticScheduler:
    """Genetic Algorithm for assigning teaching assignments to rooms and time slots."""

    def __init__(self, term, settings, seed=None, *, repair_budget=64):
        if not isinstance(repair_budget, int) or repair_budget < 0:
            raise ValueError("Repair budget must be a non-negative integer.")
        self.repair_budget = repair_budget
        self.last_repair = None
        self.repair_statistics = defaultdict(int)
        self._lease = None
        self.term = term
        self.settings = settings
        self.seed = choose_seed(seed)
        self.random = random.Random(self.seed)
        self.assignments = list(
            TeachingAssignment.objects.filter(term=term)
            .select_related("subject", "faculty", "section__program", "section__year_level", "assignment")
            .prefetch_related(
                "faculty__credentials__credential",
                "subject__credential_requirements__required_credential",
                "subject__credential_requirements__acceptable_equivalents",
                "faculty__availability_set",
                "section__availability_set",
                "credential_overrides",
            )
            .order_by("id")
        )
        self.rooms = list(Room.objects.filter(is_active=True).prefetch_related("availability_set").order_by("id"))
        self.assignment_map = {a.id: a for a in self.assignments}
        self.room_map = {r.id: r for r in self.rooms}
        self.valid_rooms_by_assignment = {
            assignment.id: [
                room
                for room in self.rooms
                if room.room_type == assignment.effective_room_type and room.capacity >= assignment.section.size
            ]
            for assignment in self.assignments
        }
        self.qualification_cache = {
            assignment.id: teaching_eligibility(assignment.faculty, assignment.subject, self.term, assignment)["eligible"]
            for assignment in self.assignments
        }
        faculty = {a.faculty_id: a.faculty for a in self.assignments}
        self.faculty_policies = {pk: AvailabilityPolicy.for_resource(item) for pk, item in faculty.items()}
        self.section_policies = {a.section_id: AvailabilityPolicy.for_resource(a.section) for a in self.assignments}
        self.room_policies = {room.pk: AvailabilityPolicy.for_resource(room) for room in self.rooms}
        self.faculty_preferred = self._availability_map(AvailabilityKind.PREFERRED)
        self._placement_cache = {}
        self._placement_sets = {}
        self._fitness_cache = {}
        self.generation_statistics = []
        self.best_fitness = None
        self.input_metadata = input_summary(self)

    def _availability_map(self, kind):
        data = defaultdict(list)
        for assignment in self.assignments:
            for item in assignment.faculty.availability_set.all():
                if item.kind != kind:
                    continue
                data[assignment.faculty_id].append(item)
        return data

    def generate(self, name="Generated Schedule", *, lease=None):
        if lease is None:
            with generation_lease(self.term.pk) as owned:
                return self.generate(name, lease=owned)
        if lease.term_id != self.term.pk:
            raise GenerationLeaseLost("Generation reservation belongs to a different term.")
        self._lease = lease
        self._execution_started = perf_counter()
        self.settings = copy(self.settings)
        self.random = random.Random(self.seed)
        self.run_metadata = initial_metadata(self.seed, self.settings, self.repair_budget)
        self.input_metadata = input_summary(self)
        self.run_metadata['inputs'] = self.input_metadata
        self.best_fitness = None
        self.generation_statistics = []
        run = None
        try:
            with lease.saving():
                if lease.run_id is None:
                    run = GenerationRun.objects.create(term=self.term, ga_settings=self.settings if self.settings.pk else None,
                        requested_name=name, lease_owner=lease.owner, reproducibility=self.run_metadata)
                    lease.run_id = run.pk
                else:
                    changed = GenerationRun.objects.filter(pk=lease.run_id, term=self.term, status='RUNNING').update(
                        reproducibility=self.run_metadata)
                    if changed != 1:
                        raise GenerationLeaseLost('The generation request is no longer available. Please try again.')
                    run = GenerationRun.objects.get(pk=lease.run_id)
            return self._generate(name)
        except GenerationLeaseLost:
            if run is not None:
                GenerationRun.objects.filter(pk=run.pk, status='RUNNING').update(status='FAILED', completed_at=timezone.now(),
                    reproducibility=finished_metadata(self.run_metadata, self, perf_counter() - self._execution_started))
            raise
        except Exception as exc:
            if run is not None:
                from django.db import DatabaseError
                try:
                    fail_run(run, exc.issues if isinstance(exc, GenerationFailure) else [unexpected_diagnostic()],
                        metadata=finished_metadata(self.run_metadata, self, perf_counter() - self._execution_started))
                except DatabaseError:
                    # Leave the atomic prior state recoverable; the HTTP layer
                    # logs/retries failure recording without exposing internals.
                    pass
            raise
        finally:
            self._lease = None

    def _checkpoint(self):
        if self._lease is not None:
            self._lease.checkpoint()

    def _generate(self, name):
        self.generation_statistics = []
        self.best_fitness = None
        self.repair_statistics.clear()
        self.last_repair = None
        if not self.assignments:
            raise GenerationFailure("No teaching assignments found for the selected term.", [Diagnostic("INVALID_DATA", "No teaching assignments found for the selected term.")])
        if not self.rooms:
            raise GenerationFailure("No active rooms available.", [Diagnostic("INVALID_DATA", "No active rooms available.")])
        preflight = self.preflight_issues()
        if preflight:
            raise GenerationFailure("Schedule requirements are not feasible: " + "; ".join(preflight), self._preflight_diagnostics)

        for assignment in self.assignments:
            self.placement_options(assignment)
        population = [self._random_chromosome() for _ in range(self.settings.population_size)]
        best = max(population, key=self.fitness)
        best_score = self.fitness(best)
        self._record_generation(0, best_score, best_score)
        for generation in range(1, self.settings.generations + 1):
            ranked = sorted(population, key=self.fitness, reverse=True)
            next_population = ranked[: self.settings.elitism]
            while len(next_population) < self.settings.population_size:
                parent_a = self._select(ranked)
                parent_b = self._select(ranked)
                if self.random.random() < self.settings.crossover_rate:
                    child = self._crossover(parent_a, parent_b)
                else:
                    child = list(parent_a)
                child = self._mutate(child)
                next_population.append(child)
            population = next_population
            candidate = max(population, key=self.fitness)
            candidate_score = self.fitness(candidate)
            if candidate_score > best_score:
                best = candidate
                best_score = candidate_score
            self._record_generation(generation, candidate_score, best_score)

        ids = [gene.assignment_id for gene in best]
        if len(ids) != len(set(ids)):
            raise GenerationFailure("GA output contains duplicate meetings.", [Diagnostic("INVALID_DATA", "GA output contains duplicate meetings.", tuple(sorted(set(ids))))])
        if any(pk not in self.assignment_map for pk in ids) or any(gene.room_id not in self.room_map for gene in best):
            raise GenerationFailure("GA output references an unknown meeting or room.", [Diagnostic("INVALID_DATA", "GA output references an unknown meeting or room.")])
        if best_score.hard_violations:
            raise GenerationFailure(
                f"No feasible schedule found within the generation limit. Best candidate has "
                f"{best_score.hard_violations} hard constraint violations (soft preference score: "
                f"{best_score.soft_score:.2f}). Review scheduling requirements or try another run.",
                self.candidate_diagnostics(best, best_score)
            )
        with self._lease.saving():
            # Only validated feasible results persist; retain the numeric column
            # for the soft score (the old feasible-score formula is unchanged).
            schedule = Schedule.objects.create(term=self.term, name=name, fitness_score=best_score.soft_score, origin=Schedule.Origin.GENERATED)
            entries = [ScheduleEntry(schedule=schedule, assignment=self.assignment_map[gene.assignment_id],
                                     room=self.room_map[gene.room_id], day=gene.day,
                                     start_time=gene.start_time, end_time=gene.end_time) for gene in best]
            ScheduleEntry.objects.bulk_create(entries)
            from .conflicts import schedule_validation_messages
            errors = schedule_validation_messages(schedule)
            if errors:
                raise GenerationFailure("GA could not produce a feasible schedule: " + "; ".join(sorted(set(errors))),
                    getattr(errors, "issues", [Diagnostic("INVALID_DATA", message) for message in errors]))
            if self._lease.run_id is not None:
                recorded = GenerationRun.objects.filter(pk=self._lease.run_id, term=self.term).update(
                    schedule=schedule, status=GenerationRun.Status.SUCCEEDED, completed_at=timezone.now(),
                    reproducibility=finished_metadata(self.run_metadata, self, perf_counter() - self._execution_started))
                if recorded != 1:
                    raise GenerationLeaseLost("The generation request is no longer available. Please try again.")
        return schedule

    def _record_generation(self, generation, population_best, best_so_far):
        self.best_fitness = best_so_far
        self.generation_statistics.append({
            "generation": generation,
            "population_best": asdict(population_best),
            "best_so_far": asdict(best_so_far),
        })

    def preflight_issues(self):
        issues = []
        self._preflight_diagnostics = []
        def add(message, category, meetings, details=None):
            issues.append(message)
            self._preflight_diagnostics.append(Diagnostic.for_meetings(category, message, meetings, details=details or {}))
        faculty_minutes = defaultdict(int)
        for assignment in self.assignments:
            faculty_minutes[assignment.faculty_id] += assignment.required_duration_minutes
            if not self.valid_rooms_by_assignment[assignment.id]:
                add(
                    f"{assignment.subject.code} / {assignment.section}: no active {dict(RoomKind.choices)[assignment.effective_room_type]} has capacity {assignment.section.size}.",
                    "ROOM_CAPACITY" if any(r.room_type == assignment.effective_room_type for r in self.rooms) else "ROOM_TYPE", [assignment],
                    {"required_capacity": assignment.section.size, "required_room_type": assignment.effective_room_type}
                )
            if not self.qualification_cache[assignment.id]:
                add(f"{assignment.subject.code} / {assignment.section}: {assignment.faculty} lacks the required credential or override.", "FACULTY_CREDENTIAL", [assignment])
            from .room_compatibility import meeting_room_errors
            for message in meeting_room_errors(assignment):
                add(message, "ROOM_TYPE", [assignment])
            for message in duration_errors(assignment.required_duration_minutes):
                add(f"{assignment.subject.code} / {assignment.section}: {message}", "INVALID_DURATION", [assignment])
        faculty_by_id = {assignment.faculty_id: assignment.faculty for assignment in self.assignments}
        for faculty_id, minutes in faculty_minutes.items():
            faculty = faculty_by_id[faculty_id]
            if minutes > faculty.max_weekly_hours * 60:
                add(f"{faculty}: assigned load is {minutes / 60:g} hours but the maximum is {faculty.max_weekly_hours} hours.", "FACULTY_WORKLOAD",
                    [a for a in self.assignments if a.faculty_id == faculty_id], {"minutes": minutes, "maximum_minutes": faculty.max_weekly_hours * 60})
        return list(dict.fromkeys(issues))

    def candidate_diagnostics(self, chromosome, score):
        from types import SimpleNamespace
        from .conflicts import individual_entry_errors
        issues = [Diagnostic('NO_SLOT', f'No feasible schedule found within the generation limit. Best candidate has {score.hard_violations} hard constraint violations (soft preference score: {score.soft_score:.2f}). Review scheduling requirements or try another run.',
            details={'hard_violations': score.hard_violations, 'soft_score': score.soft_score})]
        for kind, left, right in sorted(overlap_conflicts(chromosome, self.assignment_map)):
            genes = [chromosome[left], chromosome[right]]
            issues.append(Diagnostic.for_meetings(kind.upper() + '_CONFLICT',
                f'{kind.capitalize()} overlap between meetings {genes[0].assignment_id} and {genes[1].assignment_id}.',
                [self.assignment_map[g.assignment_id] for g in genes],
                room_id=genes[0].room_id if kind == 'room' else None,
                details={'placements': [{'meeting_id': g.assignment_id, 'room_id': g.room_id, 'day': g.day,
                    'start_time': str(g.start_time), 'end_time': str(g.end_time)} for g in genes]}))
        for gene in chromosome:
            a = self.assignment_map[gene.assignment_id]
            entry = SimpleNamespace(assignment=a, schedule=SimpleNamespace(term=self.term, term_id=self.term.pk),
                effective_subject=a.subject, effective_section=a.section, effective_faculty=a.faculty,
                effective_component=a.component, room=self.room_map[gene.room_id], day=gene.day,
                start_time=gene.start_time, end_time=gene.end_time)
            individual_entry_errors(entry, eligible=self.qualification_cache[a.pk],
                faculty_policy=self.faculty_policies[a.faculty_id], room_policy=self.room_policies[gene.room_id], section_policy=self.section_policies[a.section_id], issue_sink=issues)
        return issues

    def placement_options(self, assignment):
        self._checkpoint()
        if assignment.pk not in self._placement_cache:
            domain_issues = []
            options, errors = feasible_placements(assignment, self.term, self.rooms,
                eligible=self.qualification_cache[assignment.pk],
                faculty_policy=self.faculty_policies[assignment.faculty_id], room_policies=self.room_policies, section_policy=self.section_policies[assignment.section_id],
                checkpoint=self._checkpoint, issue_sink=domain_issues)
            if not options:
                message = f"{assignment.subject.code} / {assignment.section} / Meeting {assignment.meeting_index} ({assignment.faculty}): no individually feasible placement. " + " ".join(errors)
                raise GenerationFailure(message, domain_issues or [Diagnostic.for_meetings('NO_SLOT', message, [assignment],
                    details={'constraint': 'feasible_placements', 'reasons': list(errors)})])
            genes = tuple(Gene(assignment.pk, *option) for option in options)
            self._placement_cache[assignment.pk] = genes
            self._placement_sets[assignment.pk] = frozenset(genes)
        return self._placement_cache[assignment.pk]

    def _choose_placement(self, assignment, occupancy=None, exclude=None):
        options = self.placement_options(assignment)
        # A random start/direction avoids copying and shuffling entire domains.
        # This bounded scan is not a search over schedule combinations.
        start = self.random.randrange(len(options))
        direction = self.random.choice((-1, 1))
        fallback = None
        for offset in range(len(options)):
            gene = options[(start + direction * offset) % len(options)]
            if gene == exclude and len(options) > 1:
                continue
            if fallback is None:
                fallback = gene
            if occupancy is None or not occupancy.conflicts(gene):
                return gene
        # Domains can be individually valid but jointly impossible. Fitness and
        # final validation handle those conflicts; never invent invalid genes.
        return fallback

    def _random_gene(self, assignment):
        return self._choose_placement(assignment)

    def _choose_room_for_assignment(self, assignment, rooms):
        best_fit = [
            room for room in rooms
            if room.capacity >= assignment.section.size and room.capacity <= max(assignment.section.size + 15, assignment.section.size * 1.35)
        ]
        return self.random.choice(best_fit or rooms)

    def _random_chromosome(self):
        order = list(self.assignments)
        self.random.shuffle(order)
        order.sort(key=lambda assignment: len(self.placement_options(assignment)))
        occupancy = PlacementOccupancy(self.assignment_map)
        placed = {}
        for assignment in order:
            gene = self._choose_placement(assignment, occupancy)
            placed[assignment.pk] = gene
            occupancy.add(gene)
        return self._repair([placed[assignment.pk] for assignment in self.assignments])

    def _select(self, ranked):
        contenders = self.random.sample(list(enumerate(ranked)), k=min(4, len(ranked)))
        # Equal fitness retains the earliest population rank, not draw order.
        return max(contenders, key=lambda item: (self.fitness(item[1]), -item[0]))[1]

    def _crossover(self, parent_a, parent_b):
        point = self.random.randint(1, len(parent_a) - 1) if len(parent_a) > 1 else 1
        inherited = list(parent_a[:point]) + list(parent_b[point:])
        occupancy = PlacementOccupancy(self.assignment_map)
        child = []
        for index, gene in enumerate(inherited):
            assignment = self.assignment_map[gene.assignment_id]
            self.placement_options(assignment)
            valid = gene in self._placement_sets[assignment.pk]
            alternate = parent_b[index] if index < point else parent_a[index]
            if not valid or occupancy.conflicts(gene):
                if alternate in self._placement_sets[assignment.pk] and not occupancy.conflicts(alternate):
                    gene = alternate
                elif not valid:
                    gene = self._choose_placement(assignment, occupancy)
            child.append(gene)
            occupancy.add(gene)
        return child

    def _mutate(self, chromosome):
        mutated = list(chromosome)
        for index, gene in enumerate(chromosome):
            if self.random.random() < self.settings.mutation_rate:
                occupancy = PlacementOccupancy(self.assignment_map, mutated[:index] + mutated[index+1:])
                mutated[index] = self._choose_placement(self.assignment_map[gene.assignment_id], occupancy, exclude=gene)
        # Crossover offspring (including unchanged mutations) are repaired once here.
        return self._repair(mutated)

    def _repair(self, chromosome):
        repaired, report = repair_candidate(self, chromosome, self.repair_budget)
        self.last_repair = report
        self.repair_statistics[report["status"]] += 1
        for key in ("attempts", "moves"):
            self.repair_statistics[key] += report[key]
        return repaired

    def fitness(self, chromosome):
        self._checkpoint()
        cache_key = tuple(chromosome)
        cached = self._fitness_cache.get(cache_key)
        if cached is not None:
            return cached

        score = 1000.0
        hard_violations = 0
        soft_penalty = 0

        for gene in chromosome:
            assignment = self.assignment_map[gene.assignment_id]
            room = self.room_map[gene.room_id]
            if gene.day not in ALLOWED_DAYS or not contains(SCHOOL_START, SCHOOL_END, gene.start_time, gene.end_time):
                hard_violations += 1
            if room.capacity < assignment.section.size:
                hard_violations += 1
            if room.room_type != assignment.effective_room_type:
                hard_violations += 1
            if not self.qualification_cache[assignment.id]:
                hard_violations += 1
            if self._blocked(assignment.faculty_id, gene):
                hard_violations += 1
            if self._room_blocked(gene.room_id, gene):
                hard_violations += 1
            if (self.section_policies[assignment.section_id].configured and
                    self.section_policies[assignment.section_id].rejection_reason(gene.day, gene.start_time, gene.end_time)):
                hard_violations += 1
            if self._preferred(assignment.faculty_id, gene):
                soft_penalty -= 12
            capacity_gap = max(0, room.capacity - assignment.section.size)
            soft_penalty += capacity_gap * 0.15
            if capacity_gap > assignment.section.size:
                soft_penalty += 10
            if room.room_type != assignment.effective_room_type and room.room_type != "SPECIAL":
                soft_penalty += 20

        hard_violations += len(overlap_conflicts(chromosome, self.assignment_map))

        soft_penalty += self._distribution_penalty(chromosome)
        soft_penalty += self._room_utilization_penalty(chromosome)
        fitness_score = Fitness(hard_violations=hard_violations, soft_score=score - soft_penalty)
        self._fitness_cache[cache_key] = fitness_score
        return fitness_score

    def _blocked(self, faculty_id, gene):
        return bool(self.faculty_policies[faculty_id].rejection_reason(gene.day, gene.start_time, gene.end_time))

    def _preferred(self, faculty_id, gene):
        return any(contains(a.start_time, a.end_time, gene.start_time, gene.end_time) for a in self.faculty_preferred[faculty_id] if a.day == gene.day)

    def _room_blocked(self, room_id, gene):
        policy = self.room_policies.get(room_id)
        return policy is None or bool(policy.rejection_reason(gene.day, gene.start_time, gene.end_time))

    def _distribution_penalty(self, chromosome):
        by_faculty_day = defaultdict(list)
        by_section_day = defaultdict(list)
        for gene in chromosome:
            assignment = self.assignment_map[gene.assignment_id]
            by_faculty_day[(assignment.faculty_id, gene.day)].append(gene)
            by_section_day[(assignment.section_id, gene.day)].append(gene)

        penalty = 0
        for buckets in (by_faculty_day, by_section_day):
            for genes in buckets.values():
                genes.sort(key=lambda g: (g.start_time, g.end_time))
                if len(genes) > 3:
                    penalty += (len(genes) - 3) * 8
        # Merge occupied intervals before counting faculty idle time. A nested
        # overlap must not create a false gap after the shorter meeting ends.
        total_idle_minutes = 0
        for genes in by_faculty_day.values():
            occupied_until = None
            idle_minutes = 0
            for gene in genes:
                start = gene.start_time.hour * 60 + gene.start_time.minute
                end = gene.end_time.hour * 60 + gene.end_time.minute
                if occupied_until is not None:
                    idle_minutes += max(0, start - occupied_until)
                occupied_until = max(occupied_until or end, end)
            total_idle_minutes += idle_minutes
        penalty += total_idle_minutes * 4 / 60
        # Preserve the separate, existing section gap preference.
        for genes in by_section_day.values():
            for left, right in zip(genes, genes[1:]):
                gap = right.start_time.hour - left.end_time.hour
                if gap > 1:
                    penalty += gap * 4
        # School-wide instructional calendar, not just days used by this candidate.
        day_counts = dict.fromkeys(ALLOWED_DAYS, 0)
        for gene in chromosome:
            if gene.day in day_counts:
                day_counts[gene.day] += 1
        if day_counts:
            spread = max(day_counts.values()) - min(day_counts.values())
            penalty += spread * 3
        return penalty

    def _room_utilization_penalty(self, chromosome):
        by_room_hours = defaultdict(float)
        by_room_classes = defaultdict(int)
        suitable_room_ids = set()
        required_room_types = set()

        for gene in chromosome:
            assignment = self.assignment_map[gene.assignment_id]
            duration = max(0, (gene.end_time.hour * 60 + gene.end_time.minute - gene.start_time.hour * 60 - gene.start_time.minute) / 60)
            by_room_hours[gene.room_id] += duration
            by_room_classes[gene.room_id] += 1
            required_room_types.add(assignment.effective_room_type)
            for room in self.valid_rooms_by_assignment.get(assignment.id, []):
                suitable_room_ids.add(room.id)

        penalty = 0
        used_hours = list(by_room_hours.values())
        if used_hours:
            average = sum(used_hours) / len(used_hours)
            penalty += sum(abs(hours - average) for hours in used_hours) * 2.5

        for room_id in suitable_room_ids:
            if by_room_classes[room_id] == 0:
                penalty += 8

        for room in self.rooms:
            if room.room_type in required_room_types and by_room_classes[room.id] == 0:
                penalty += 3

        return penalty
