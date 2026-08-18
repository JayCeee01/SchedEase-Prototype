import math
import re
from collections import Counter, defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schedules.importers.full_tertiary import CAPACITY_DEFAULTS, normalized_meetings
from schedules.importers.tertiary_workbook import PROGRAMS, SELECTED_SECTIONS, normalized_title
from schedules.models import (
    AcademicTerm, Availability, AvailabilityKind, Credential, Department, Faculty,
    FacultyCredential, GASettings, Program, Room, Section, Subject,
    SubjectCredentialRequirement, TeachingAssignment, YearLevel,
)
from schedules.services.time import SCHOOL_END, SCHOOL_START


class Command(BaseCommand):
    help = "Seed three complete representative sections from the tertiary workbook (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("workbook")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        try:
            all_meetings, _audit, rejected, _duplicates, analysis = normalized_meetings(options["workbook"])
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        meetings = [m for m in all_meetings if (m["program"], m["year"], m["section"]) in SELECTED_SECTIONS]
        if not meetings:
            raise CommandError("None of the configured representative sections were found.")
        self.report(meetings, rejected, analysis)
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("DRY RUN: no data changed. Add --commit only on a development/test database."))
            return
        with transaction.atomic():
            counts = self.persist(meetings)
        self.stdout.write(self.style.SUCCESS("Imported representative sample: " + ", ".join(f"{k}={v}" for k, v in counts.items())))

    def report(self, meetings, rejected, analysis):
        sections = sorted({f'{m["program"]} {m["year"]}-{m["section"]}' for m in meetings})
        components = Counter(m["component"] for m in meetings)
        self.stdout.write(f"Worksheets inspected: {', '.join(analysis['worksheets'])}")
        self.stdout.write(f"Selected complete sections: {', '.join(sections)}")
        self.stdout.write(
            f"Source rows={len({m['row'] for m in meetings})}; requirements={len(meetings)}; "
            f"subjects={len({m['code'] for m in meetings})}; faculty={len({m['faculty'] for m in meetings})}; "
            f"rooms={len({m['room'] for m in meetings})}; lecture={components[TeachingAssignment.Component.LECTURE]}; "
            f"laboratory={components[TeachingAssignment.Component.LABORATORY]}; general={components[TeachingAssignment.Component.GENERAL]}"
        )
        self.stdout.write(f"Workbook-wide ambiguous/rejected rows={len(rejected)}; none are silently converted.")
        self.stdout.write("SOURCE: section, subject, faculty, units, rooms, and meeting patterns. DERIVED: program/year, duration, component, and room type.")
        self.stdout.write("DEFAULT/TEST: section size 30, room capacities, room availability, and synthetic credential checks.")

    def persist(self, meetings):
        term, _ = AcademicTerm.objects.get_or_create(
            name="Second Term - Representative Workbook Sample", school_year="2025-2026",
            defaults={"starts_on": date(2025, 11, 1), "ends_on": date(2026, 4, 30), "is_active": False},
        )
        years = {level: YearLevel.objects.get_or_create(level=level, defaults={"label": f"Year {level}"})[0]
                 for level in {m["year"] for m in meetings}}
        programs = {}
        for code in sorted({m["program"] for m in meetings}):
            dept_code, dept_name, program_name = PROGRAMS[code]
            department, _ = Department.objects.get_or_create(code=dept_code, defaults={"name": dept_name})
            programs[code], _ = Program.objects.get_or_create(
                code=code, defaults={"department": department, "name": program_name}
            )
        sections = {}
        for m in meetings:
            key = (m["program"], m["year"], m["section"])
            sections[key], _ = Section.objects.get_or_create(
                program=programs[m["program"]], year_level=years[m["year"]], name=m["section"], defaults={"size": 30}
            )

        faculty_minutes = Counter()
        for m in meetings:
            faculty_minutes[m["faculty"]] += m["duration"]
        faculty = {}
        for m in meetings:
            name = re.sub(r"\s+", " ", m["faculty"].strip()).upper()
            employee_id = "RSP-XLS-" + re.sub(r"[^A-Z0-9]+", "-", name).strip("-")
            faculty[name], _ = Faculty.objects.get_or_create(
                employee_id=employee_id,
                defaults={"department": programs[m["program"]].department, "full_name": name,
                          "max_weekly_hours": max(24, math.ceil(faculty_minutes[m["faculty"]] / 60))},
            )
        for member in faculty.values():
            for day in range(6):
                Availability.objects.get_or_create(
                    faculty=member, day=day, start_time=SCHOOL_START, end_time=SCHOOL_END,
                    kind=AvailabilityKind.AVAILABLE,
                )

        rooms = {}
        for m in meetings:
            source_name = m["room"].strip().upper()
            rooms[source_name], _ = Room.objects.get_or_create(
                name=f"RSP-{source_name}",
                defaults={"room_type": m["room_type"], "capacity": CAPACITY_DEFAULTS[m["room_type"]]},
            )
        for room in rooms.values():
            for day in range(6):
                Availability.objects.get_or_create(
                    room=room, day=day, start_time=SCHOOL_START, end_time=SCHOOL_END,
                    kind=AvailabilityKind.AVAILABLE,
                )

        indices = defaultdict(int)
        assignments = []
        for m in sorted(meetings, key=lambda item: (item["row"], item["occurrence"], item["source_key"])):
            source_code = m["code"].strip().upper()
            subject, _ = Subject.objects.get_or_create(
                code=f"RSP-{source_code}",
                defaults={"title": normalized_title(m["original_title"]),
                          "department": programs[m["program"]].department, "units": float(m["units"] or 0),
                          "lecture_hours": 0, "lab_hours": 0, "required_room_type": m["room_type"]},
            )
            section = sections[(m["program"], m["year"], m["section"])]
            key = (subject.pk, section.pk, m["component"])
            indices[key] += 1
            assignment, _ = TeachingAssignment.objects.update_or_create(
                term=term, subject=subject, section=section, component=m["component"], meeting_index=indices[key],
                defaults={"faculty": faculty[m["faculty"]], "duration_minutes": m["duration"],
                          "required_room_type_override": m["room_type"], "source_key": m["source_key"],
                          "source_sheet": m["sheet"], "source_row": m["row"]},
            )
            credential, _ = Credential.objects.get_or_create(
                name=f"TEST-RSP-{source_code}",
                defaults={"description": "DEFAULT/TEST credential for representative workbook scheduling only."},
            )
            SubjectCredentialRequirement.objects.get_or_create(
                subject=subject, required_credential=credential,
                defaults={"notes": "DEFAULT/TEST requirement; the workbook provides no credential evidence."},
            )
            FacultyCredential.objects.get_or_create(
                faculty=faculty[m["faculty"]], credential=credential,
                defaults={"issued_by": "SchedEase representative sample", "notes": "DEFAULT/TEST; not provided by the workbook."},
            )
            Availability.objects.get_or_create(
                faculty=faculty[m["faculty"]], day=m["day"], start_time=m["start"], end_time=m["end"],
                kind=AvailabilityKind.PREFERRED,
            )
            assignments.append(assignment)

        settings, _ = GASettings.objects.get_or_create(
            name="Representative Workbook Sample",
            defaults={"population_size": 100, "generations": 180, "mutation_rate": .12, "crossover_rate": .85, "elitism": 6},
        )
        return {"requirements": len(assignments), "subjects": len({a.subject_id for a in assignments}),
                "sections": len(sections), "faculty": len(faculty), "rooms": len(rooms), "ga_settings": settings.pk}
