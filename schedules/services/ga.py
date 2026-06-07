import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import time

from schedules.models import AvailabilityKind, Room, Schedule, ScheduleEntry, TeachingAssignment
from .credentials import faculty_qualification
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, add_hours, contains, hourly_starts, overlaps


@dataclass(frozen=True)
class Gene:
    assignment_id: int
    room_id: int
    day: int
    start_time: time
    end_time: time


class GeneticScheduler:
    """Genetic Algorithm for assigning teaching assignments to rooms and time slots."""

    def __init__(self, term, settings, seed=None):
        self.term = term
        self.settings = settings
        self.random = random.Random(seed)
        self.assignments = list(
            TeachingAssignment.objects.filter(term=term)
            .select_related("subject", "faculty", "section")
            .prefetch_related(
                "faculty__credentials__credential",
                "subject__credential_requirements__required_credential",
                "subject__credential_requirements__acceptable_equivalents",
                "faculty__availability_set",
            )
            .order_by("id")
        )
        self.rooms = list(Room.objects.filter(is_active=True).order_by("id"))
        self.assignment_map = {a.id: a for a in self.assignments}
        self.room_map = {r.id: r for r in self.rooms}
        self.valid_rooms_by_assignment = {
            assignment.id: [
                room
                for room in self.rooms
                if room.room_type == assignment.subject.required_room_type and room.capacity >= assignment.section.size
            ]
            for assignment in self.assignments
        }
        self.qualification_cache = {
            assignment.id: faculty_qualification(assignment.faculty, assignment.subject)["qualified"]
            for assignment in self.assignments
        }
        self.faculty_unavailable = self._availability_map(AvailabilityKind.UNAVAILABLE)
        self.faculty_preferred = self._availability_map(AvailabilityKind.PREFERRED)
        self._fitness_cache = {}

    def _availability_map(self, kind):
        data = defaultdict(list)
        for assignment in self.assignments:
            for item in assignment.faculty.availability_set.all():
                if item.kind != kind:
                    continue
                data[assignment.faculty_id].append(item)
        return data

    def generate(self, name="Generated Schedule"):
        if not self.assignments:
            raise ValueError("No teaching assignments found for the selected term.")
        if not self.rooms:
            raise ValueError("No active rooms available.")

        population = [self._random_chromosome() for _ in range(self.settings.population_size)]
        best = max(population, key=self.fitness)
        best_score = self.fitness(best)
        for _ in range(self.settings.generations):
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

        schedule = Schedule.objects.create(term=self.term, name=name, fitness_score=best_score)
        entries = [
            ScheduleEntry(
                schedule=schedule,
                assignment=self.assignment_map[gene.assignment_id],
                room=self.room_map[gene.room_id],
                day=gene.day,
                start_time=gene.start_time,
                end_time=gene.end_time,
            )
            for gene in best
        ]
        ScheduleEntry.objects.bulk_create(entries)
        return schedule

    def _random_gene(self, assignment):
        valid_rooms = self.valid_rooms_by_assignment[assignment.id]
        room = self._choose_room_for_assignment(assignment, valid_rooms or self.rooms)
        duration = max(1, assignment.required_hours)
        day = self.random.choice(list(ALLOWED_DAYS))
        start = self.random.choice(list(hourly_starts(duration)))
        return Gene(assignment.id, room.id, day, start, add_hours(start, duration))

    def _choose_room_for_assignment(self, assignment, rooms):
        best_fit = [
            room
            for room in rooms
            if room.capacity >= assignment.section.size and room.capacity <= max(assignment.section.size + 15, assignment.section.size * 1.35)
        ]
        return self.random.choice(best_fit or rooms)

    def _random_chromosome(self):
        return [self._random_gene(assignment) for assignment in self.assignments]

    def _select(self, ranked):
        contenders = self.random.sample(ranked, k=min(4, len(ranked)))
        return max(contenders, key=self.fitness)

    def _crossover(self, parent_a, parent_b):
        if len(parent_a) < 2:
            return list(parent_a)
        point = self.random.randint(1, len(parent_a) - 1)
        return list(parent_a[:point]) + list(parent_b[point:])

    def _mutate(self, chromosome):
        mutated = []
        for gene in chromosome:
            if self.random.random() < self.settings.mutation_rate:
                mutated.append(self._random_gene(self.assignment_map[gene.assignment_id]))
            else:
                mutated.append(gene)
        return mutated

    def fitness(self, chromosome):
        cache_key = tuple(chromosome)
        cached = self._fitness_cache.get(cache_key)
        if cached is not None:
            return cached

        score = 1000.0
        hard_penalty = 0
        soft_penalty = 0

        for gene in chromosome:
            assignment = self.assignment_map[gene.assignment_id]
            room = self.room_map[gene.room_id]
            if gene.day not in ALLOWED_DAYS or not contains(SCHOOL_START, SCHOOL_END, gene.start_time, gene.end_time):
                hard_penalty += 200
            if room.capacity < assignment.section.size:
                hard_penalty += 150
            if room.room_type != assignment.subject.required_room_type:
                hard_penalty += 150
            if not self.qualification_cache[assignment.id]:
                hard_penalty += 300
            if self._blocked(assignment.faculty_id, gene):
                hard_penalty += 200
            if self._preferred(assignment.faculty_id, gene):
                soft_penalty -= 12
            capacity_gap = max(0, room.capacity - assignment.section.size)
            soft_penalty += capacity_gap * 0.15
            if capacity_gap > assignment.section.size:
                soft_penalty += 10
            if room.room_type != assignment.subject.required_room_type and room.room_type != "SPECIAL":
                soft_penalty += 20

        for i, gene in enumerate(chromosome):
            left = self.assignment_map[gene.assignment_id]
            for other in chromosome[i + 1 :]:
                if gene.day != other.day or not overlaps(gene.start_time, gene.end_time, other.start_time, other.end_time):
                    continue
                right = self.assignment_map[other.assignment_id]
                if left.faculty_id == right.faculty_id:
                    hard_penalty += 250
                if left.section_id == right.section_id:
                    hard_penalty += 250
                if gene.room_id == other.room_id:
                    hard_penalty += 250

        soft_penalty += self._distribution_penalty(chromosome)
        soft_penalty += self._room_utilization_penalty(chromosome)
        fitness_score = score - hard_penalty - soft_penalty
        self._fitness_cache[cache_key] = fitness_score
        return fitness_score

    def _blocked(self, faculty_id, gene):
        return any(overlaps(gene.start_time, gene.end_time, a.start_time, a.end_time) for a in self.faculty_unavailable[faculty_id] if a.day == gene.day)

    def _preferred(self, faculty_id, gene):
        return any(contains(a.start_time, a.end_time, gene.start_time, gene.end_time) for a in self.faculty_preferred[faculty_id] if a.day == gene.day)

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
                genes.sort(key=lambda g: g.start_time)
                if len(genes) > 3:
                    penalty += (len(genes) - 3) * 8
                for left, right in zip(genes, genes[1:]):
                    gap = right.start_time.hour - left.end_time.hour
                    if gap > 1:
                        penalty += gap * 4
        day_counts = defaultdict(int)
        for gene in chromosome:
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
            duration = max(0, gene.end_time.hour - gene.start_time.hour)
            by_room_hours[gene.room_id] += duration
            by_room_classes[gene.room_id] += 1
            required_room_types.add(assignment.subject.required_room_type)
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
