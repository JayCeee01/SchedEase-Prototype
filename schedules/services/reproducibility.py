"""Versioned run metadata; hashes identify loaded inputs, not historical snapshots."""
import hashlib
import json
import platform
import secrets
from copy import deepcopy
from pathlib import Path
from functools import lru_cache

import django
from .time import ALLOWED_DAYS, SCHOOL_START, SCHOOL_END


def choose_seed(seed=None):
    if seed is None:
        return secrets.randbits(63)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError('The random seed must be an integer.')
    return seed


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


@lru_cache(maxsize=1)
def implementation_hash():
    root = Path(__file__).parent
    files = [root / name for name in ('ga.py', 'repair.py', 'placements.py', 'availability.py',
             'credentials.py', 'meetings.py', 'time.py', 'conflicts.py')]
    files.append(root.parent / 'models.py')
    # Normalize checkout line endings; source identity is separate from input hash.
    return fingerprint({p.name: p.read_text(encoding='utf-8').replace('\r\n', '\n') for p in files})


def effective_parameters(settings, repair_budget):
    return {**{key: getattr(settings, key) for key in ('population_size', 'generations', 'crossover_rate', 'mutation_rate', 'elitism')},
        'selection': 'tournament', 'tournament_size': min(4, settings.population_size),
        'tie_break': 'earliest_population_rank', 'repair_attempt_limit': repair_budget,
        'slot_minutes': 30, 'availability_boundary_starts': True,
        'fitness': {'version': 'hard-first-v2', 'ordering': ['fewest_hard_violations', 'highest_soft_score'],
            'base_score': 1000.0, 'preferred_period_bonus': 12, 'capacity_gap_weight': 0.15,
            'excess_capacity_penalty': 10, 'wrong_non_special_room_penalty': 20,
            'daily_class_threshold': 3, 'extra_daily_class_penalty': 8,
            'faculty_idle_gap_unit': 'minutes', 'faculty_idle_gap_hour_weight': 4,
            'faculty_idle_gap_method': 'merged_occupied_intervals',
            'section_whole_hour_gap_threshold': 1, 'section_whole_hour_gap_weight': 4,
            'day_spread_weight': 3, 'day_spread_scope': 'all_instructional_days',
            'day_spread_days': list(ALLOWED_DAYS),
            'room_hours_deviation_weight': 2.5, 'unused_suitable_room_penalty': 8, 'unused_required_type_room_penalty': 3}}


def initial_metadata(seed, settings, repair_budget=64):
    return {'version': 1, 'seed': seed, 'parameters': effective_parameters(settings, repair_budget),
        'inputs': None, 'outcome': None,
        'environment': {'python': platform.python_version(), 'implementation': platform.python_implementation(),
                        'django': django.get_version(), 'ga_source_sha256': implementation_hash()}}


def canonical_inputs(ga):
    """Use loaded objects/policies/eligibility, excluding names and private text."""
    faculty = {a.faculty_id: a.faculty for a in ga.assignments}
    subjects = {a.subject_id: a.subject for a in ga.assignments}
    sections = {a.section_id: a.section for a in ga.assignments}
    def periods(resource):
        return sorted((p.day, str(p.start_time), str(p.end_time), p.kind) for p in resource.availability_set.all())
    def policy(value):
        return {'active': value.active, 'allowed': {day: [(str(s), str(e)) for s, e in values] for day, values in value.allowed.items()},
                'blocked': {day: [(str(s), str(e)) for s, e in values] for day, values in value.blocked.items()}}
    held = sorted((pk, c.credential_id, str(c.issued_on) if c.issued_on else None,
                   str(c.expires_on) if c.expires_on else None) for pk, f in faculty.items() for c in f.credentials.all())
    requirements = sorted((pk, r.required_credential_id, sorted(e.pk for e in r.acceptable_equivalents.all()))
        for pk, subject in subjects.items() for r in subject.credential_requirements.all())
    overrides = sorted((a.pk, o.faculty_id, o.subject_id, bool(o.admin_user_id),
                        bool(o.reason.strip()), bool(o.missing_credentials.strip()))
                       for a in ga.assignments for o in a.credential_overrides.all())
    parents = list(ga.term.assignment_set.order_by('pk').values_list('pk', 'subject_id', 'faculty_id', 'section_id'))
    # Empty parents also matter to final completeness validation.
    from schedules.models import Subject
    parent_subjects = {s.pk: s for s in Subject.objects.filter(pk__in=[p[1] for p in parents])}
    parent_subjects.update(subjects)
    return {'schema': 'schedease-inputs-v2',
        'term': {'id': ga.term.pk, 'start': str(ga.term.starts_on), 'end': str(ga.term.ends_on)},
        'operating_days': list(ALLOWED_DAYS), 'operating_hours': [str(SCHOOL_START), str(SCHOOL_END)],
        'assignments': parents,
        'meetings': sorted((a.pk, a.assignment_id, a.subject_id, a.faculty_id, a.section_id, a.component,
            a.meeting_index, a.duration_minutes, a.required_duration_minutes, a.effective_room_type,
            ga.qualification_cache[a.pk]) for a in ga.assignments),
        'subjects': sorted((pk, s.lecture_hours, s.lab_hours, s.required_room_type) for pk, s in parent_subjects.items()),
        'sections': sorted((pk, s.size, periods(s), policy(ga.section_policies[pk])) for pk, s in sections.items()),
        'faculty': [(pk, f.max_weekly_hours, periods(f), policy(ga.faculty_policies[pk])) for pk, f in sorted(faculty.items())],
        'rooms': [(r.pk, r.room_type, r.capacity, r.is_active, periods(r), policy(ga.room_policies[r.pk])) for r in sorted(ga.rooms, key=lambda r: r.pk)],
        'credentials': held, 'requirements': requirements, 'overrides': overrides}


def input_summary(ga):
    data = canonical_inputs(ga)
    return {'schema': data['schema'], 'sha256': fingerprint(data), 'term_id': ga.term.pk,
        'counts': {'assignments': len(data['assignments']), 'meetings': len(data['meetings']),
            'faculty': len(data['faculty']), 'rooms': len(data['rooms']), 'sections': len(data['sections']),
            'courses': len(data['subjects']), 'faculty_availability_periods': sum(len(row[2]) for row in data['faculty']),
            'room_availability_periods': sum(len(row[4]) for row in data['rooms']),
            'faculty_credentials': len(data['credentials']), 'credential_requirements': len(data['requirements']),
            'accepted_equivalents': sum(len(row[2]) for row in data['requirements']),
            'credential_overrides': len(data['overrides']), 'eligible_meetings': sum(ga.qualification_cache.values()),
            'required_minutes': sum(a.required_duration_minutes for a in ga.assignments)}}


def finished_metadata(metadata, ga, elapsed):
    result = deepcopy(metadata)
    result['outcome'] = {'duration_seconds': max(0.0, elapsed),
        'duration_scope': 'scheduler_execution',
        'best_hard_violations': ga.best_fitness.hard_violations if ga.best_fitness else None,
        'best_soft_score': ga.best_fitness.soft_score if ga.best_fitness else None,
        'evaluated_generations': max(0, len(ga.generation_statistics) - 1)}
    return result
