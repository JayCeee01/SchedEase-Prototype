import re
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schedules.importers.tertiary_workbook import (
    PROGRAMS, SAMPLE_ROWS, SAMPLE_SHEET, duration_hours, normalized_title, parse_days,
    parse_section, parse_time, read_rows, room_kind, rounded_weekly_hours,
)
from schedules.models import (
    AcademicTerm, Availability, AvailabilityKind, Credential, Department, Faculty,
    FacultyCredential, GASettings, Program, Room, RoomKind, Section, Subject,
    SubjectCredentialRequirement, TeachingAssignment, YearLevel,
)
from schedules.services.time import SCHOOL_END, SCHOOL_START


CAPACITY_DEFAULTS = {RoomKind.LECTURE: 45, RoomKind.COMPUTER_LAB: 40,
                     RoomKind.SCIENCE_LAB: 35, RoomKind.GYM: 60, RoomKind.SPECIAL: 30}


class Command(BaseCommand):
    help = "Import a documented representative sample from the supplied tertiary workbook (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("workbook")
        parser.add_argument("--commit", action="store_true", help="Persist data. Without this option the command only validates and reports.")

    def handle(self, *args, **options):
        try:
            rows = read_rows(options["workbook"])
            prepared = self.prepare(rows)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.report(rows, prepared)
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("DRY RUN: no database records were changed. Add --commit on an isolated development/test database."))
            return
        with transaction.atomic():
            counts = self.persist(rows, prepared)
        self.stdout.write(self.style.SUCCESS("Imported sample: " + ", ".join(f"{key}={value}" for key, value in counts.items())))

    def prepare(self, rows):
        meetings = []
        for row in rows:
            program, year, section = parse_section(row.section)
            if program not in PROGRAMS:
                raise ValueError(f"No explicit program mapping for {program!r}")
            starts = [parse_time(item) for item in row.start.split("/")]
            ends = [parse_time(item) for item in row.end.split("/")]
            days = parse_days(row.days)
            if len(starts) == len(ends) == 1:
                starts *= len(days); ends *= len(days)
            if not (len(days) == len(starts) == len(ends)):
                raise ValueError(f"Row {row.row_number} has mismatched day/time counts")
            for day, start, end in zip(days, starts, ends):
                meetings.append({"row": row, "program": program, "year": year, "section": section,
                                 "day": day, "start": start, "end": end,
                                 "hours": duration_hours(start, end), "room_type": room_kind(row.room, row.description)})
        return meetings

    def report(self, rows, meetings):
        programs = sorted({parse_section(row.section)[0] for row in rows})
        self.stdout.write(f"Workbook sheet: {SAMPLE_SHEET}; selected source rows: {', '.join(map(str, SAMPLE_ROWS))}")
        self.stdout.write(f"Sample: rows={len(rows)}, meetings={len(meetings)}, programs={programs}, "
                          f"faculty={len({r.instructor for r in rows})}, rooms={len({r.room for r in rows})}, "
                          f"subjects={len({r.course_code for r in rows})}")
        self.stdout.write("Defaults: section size=30; room capacities by type=45/40/35/60/30; workbook meetings become faculty preferences.")
        self.stdout.write("Credentials are test-only, inferred per subject and granted to the workbook's assigned instructor.")
        self.stdout.write("Lecture/lab rows sharing course+section are combined into one GA assignment; fractional weekly hours round upward.")

    def persist(self, rows, meetings):
        term, _ = AcademicTerm.objects.get_or_create(name="Second Term - Workbook Sample", school_year="2025-2026",
            defaults={"starts_on": date(2025, 11, 1), "ends_on": date(2026, 4, 30), "is_active": False})
        years = {level: YearLevel.objects.get_or_create(level=level, defaults={"label": f"Year {level}"})[0] for level in {m["year"] for m in meetings}}
        programs = {}
        for code in {m["program"] for m in meetings}:
            dept_code, dept_name, program_name = PROGRAMS[code]
            department, _ = Department.objects.get_or_create(code=dept_code, defaults={"name": dept_name})
            programs[code], _ = Program.objects.get_or_create(code=code, defaults={"department": department, "name": program_name})
        sections = {}
        for m in meetings:
            key = (m["program"], m["year"], m["section"])
            sections[key], _ = Section.objects.get_or_create(program=programs[m["program"]], year_level=years[m["year"]], name=m["section"], defaults={"size": 30})
        faculty = {}
        for m in meetings:
            name = re.sub(r"\s+", " ", m["row"].instructor.strip()).upper()
            department = programs[m["program"]].department
            employee_id = "XLS-" + re.sub(r"[^A-Z0-9]+", "-", name).strip("-")
            faculty[name], _ = Faculty.objects.get_or_create(employee_id=employee_id, defaults={"department": department, "full_name": name})
        rooms = {}
        for m in meetings:
            name = m["row"].room.strip().upper()
            kind = m["room_type"]
            rooms[name], _ = Room.objects.get_or_create(name=name, defaults={"room_type": kind, "capacity": CAPACITY_DEFAULTS[kind]})
            Availability.objects.get_or_create(room=rooms[name], day=m["day"], start_time=SCHOOL_START, end_time=SCHOOL_END, kind=AvailabilityKind.AVAILABLE)

        grouped = defaultdict(list)
        for m in meetings:
            grouped[(m["row"].course_code.strip().upper(), m["program"], m["year"], m["section"])].append(m)
        assignments = []
        for (code, program, year, section_name), group in grouped.items():
            source_code = code
            code = f"SMP-{source_code}"
            specialized = [m for m in group if m["room_type"] != RoomKind.LECTURE]
            required_type = specialized[0]["room_type"] if specialized else RoomKind.LECTURE
            lecture = sum(m["hours"] for m in group if "LAB" not in m["row"].description.upper())
            lab = sum(m["hours"] for m in group if "LAB" in m["row"].description.upper())
            first = group[0]
            subject, _ = Subject.objects.get_or_create(code=code, defaults={
                "title": normalized_title(first["row"].description), "department": programs[program].department,
                "units": first["row"].units or 0, "lecture_hours": rounded_weekly_hours(lecture) if lecture else 0,
                "lab_hours": rounded_weekly_hours(lab) if lab else 0, "required_room_type": required_type})
            instructor = faculty[re.sub(r"\s+", " ", first["row"].instructor.strip()).upper()]
            duration_minutes = max(30, round(sum(m["hours"] for m in group) * 60))
            assignment, _ = TeachingAssignment.objects.update_or_create(
                term=term, subject=subject, section=sections[(program, year, section_name)],
                component=TeachingAssignment.Component.GENERAL, meeting_index=1,
                defaults={"faculty": instructor, "duration_minutes": duration_minutes,
                          "required_room_type_override": required_type})
            credential, _ = Credential.objects.get_or_create(name=f"TEST-{source_code}", defaults={"description": "Test-only credential inferred for workbook sample validation."})
            SubjectCredentialRequirement.objects.get_or_create(subject=subject, required_credential=credential,
                defaults={"notes": "Test-only requirement; the workbook contains no credential data."})
            FacultyCredential.objects.get_or_create(faculty=instructor, credential=credential,
                defaults={"issued_by": "SchedEase workbook sample", "notes": "Test-only; not asserted by source workbook."})
            assignments.append(assignment)
        for m in meetings:
            instructor = faculty[re.sub(r"\s+", " ", m["row"].instructor.strip()).upper()]
            Availability.objects.get_or_create(faculty=instructor, day=m["day"], start_time=m["start"], end_time=m["end"], kind=AvailabilityKind.PREFERRED)
        settings, _ = GASettings.objects.get_or_create(name="Workbook Sample Fast", defaults={"population_size": 40, "generations": 80, "mutation_rate": .12, "crossover_rate": .85, "elitism": 4})
        return {"assignments": len(assignments), "subjects": len({a.subject_id for a in assignments}), "sections": len(sections),
                "faculty": len(faculty), "rooms": len(rooms), "ga_settings": settings.pk}
