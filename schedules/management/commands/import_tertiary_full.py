import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schedules.importers.full_tertiary import CAPACITY_DEFAULTS, PROGRAMS, normalized_meetings, write_reports
from schedules.models import (AcademicTerm, Availability, AvailabilityKind, Department, Faculty, GASettings,
    Program, Room, Schedule, ScheduleEntry, Section, Subject, TeachingAssignment, YearLevel)
from schedules.services.conflicts import conflict_messages
from schedules.services.room_utilization import utilization_rows, utilization_summary
from schedules.services.time import SCHOOL_END, SCHOOL_START


class Command(BaseCommand):
    help = "Analyze and import every usable meeting from the tertiary workbook (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("workbook")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--report-dir", default="workbook_import_report")

    def handle(self, *args, **options):
        try:
            meetings, audit, rejected, duplicates, analysis = normalized_meetings(options["workbook"])
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        report_dir = Path(options["report_dir"])
        write_reports(report_dir, analysis, audit, rejected, duplicates)
        self.stdout.write(str(analysis))
        self.stdout.write(f"Reports written to {report_dir.resolve()}")
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("DRY RUN: no database data changed. Add --commit only on a development/test database."))
            return
        with transaction.atomic():
            result = self.persist(meetings)
        entries = list(result["schedule"].entries.select_related("assignment__faculty", "assignment__section", "room"))
        conflicts = self.audit_conflicts(entries)
        rows = utilization_rows(result["schedule"])
        utilization = [{"room": r.room.name, "room_type": r.room.room_type, "capacity": r.room.capacity,
                        "available_hours": r.available_hours, "scheduled_hours": r.scheduled_hours,
                        "assigned_classes": r.assigned_classes, "utilization_percentage": r.utilization_percentage,
                        "status": r.status} for r in rows]
        analysis["imported"] = result["counts"]
        analysis["original_conflicts"] = len(conflicts)
        analysis["utilization_summary"] = utilization_summary(rows)
        write_reports(report_dir, analysis, audit, rejected, duplicates, conflicts, utilization)
        self.stdout.write(self.style.SUCCESS(f"Imported {result['counts']}; original conflicts={len(conflicts)}"))

    def persist(self, meetings):
        term, _ = AcademicTerm.objects.get_or_create(name="Second Term - Full Workbook", school_year="2025-2026",
            defaults={"starts_on": date(2025, 11, 1), "ends_on": date(2026, 4, 30), "is_active": False})
        years = {n: YearLevel.objects.get_or_create(level=n, defaults={"label": f"Year {n}"})[0] for n in {m["year"] for m in meetings}}
        programs = {}
        for code in {m["program"] for m in meetings}:
            dept_code, dept_name, program_name = PROGRAMS[code]
            dept, _ = Department.objects.get_or_create(code=dept_code, defaults={"name": dept_name})
            programs[code], _ = Program.objects.get_or_create(code=code, defaults={"department": dept, "name": program_name})
        sections = {}
        for m in meetings:
            key = (m["program"], m["year"], m["section"])
            sections[key], _ = Section.objects.get_or_create(program=programs[m["program"]], year_level=years[m["year"]], name=m["section"], defaults={"size": 30})
        faculty = {}
        faculty_minutes = Counter()
        for m in meetings:
            faculty_minutes[m["faculty"]] += m["duration"]
            eid = "XLS-" + re.sub(r"[^A-Z0-9]+", "-", m["faculty"]).strip("-")
            derived_limit = max(24, (faculty_minutes[m["faculty"]] + 59) // 60)
            faculty[m["faculty"]], _ = Faculty.objects.get_or_create(employee_id=eid, defaults={"department": programs[m["program"]].department, "full_name": m["faculty"], "max_weekly_hours": derived_limit})
        rooms = {}
        for m in meetings:
            rooms[m["room"]], _ = Room.objects.get_or_create(name=m["room"], defaults={"room_type": m["room_type"], "capacity": CAPACITY_DEFAULTS[m["room_type"]]})
        for room in rooms.values():
            for day in range(6):
                Availability.objects.get_or_create(room=room, day=day, start_time=SCHOOL_START, end_time=SCHOOL_END, kind=AvailabilityKind.AVAILABLE)
        # Stable occurrence index within subject/section/component, ordered by source provenance.
        indices = defaultdict(int); assignments = []
        for m in meetings:
            units = 0
            try: units = float(m["units"] or 0)
            except ValueError: pass
            subject, _ = Subject.objects.get_or_create(code=m["code"], defaults={"title": m["title"], "department": programs[m["program"]].department, "units": units,
                "lecture_hours": 0, "lab_hours": 0, "required_room_type": m["room_type"]})
            section = sections[(m["program"], m["year"], m["section"])]
            key = (subject.id, section.id, m["component"]); indices[key] += 1
            assignment, _ = TeachingAssignment.objects.update_or_create(term=term, subject=subject, section=section,
                component=m["component"], meeting_index=indices[key], defaults={"faculty": faculty[m["faculty"]],
                "duration_minutes": m["duration"], "required_room_type_override": m["room_type"],
                "source_key": m["source_key"], "source_sheet": m["sheet"], "source_row": m["row"]})
            assignments.append((assignment, m))
        persisted_minutes = Counter()
        for assignment, _ in assignments:
            persisted_minutes[assignment.faculty_id] += assignment.required_duration_minutes
        for obj in faculty.values():
            needed = max(24, (persisted_minutes[obj.id] + 59) // 60)
            if obj.max_weekly_hours < needed:
                obj.max_weekly_hours = needed
                obj.save(update_fields=["max_weekly_hours"])
        schedule, _ = Schedule.objects.get_or_create(term=term, name="Imported Original Tertiary Schedule",
            defaults={"origin": Schedule.Origin.IMPORTED})
        schedule.origin = Schedule.Origin.IMPORTED; schedule.save(update_fields=["origin"])
        schedule.entries.all().delete()
        ScheduleEntry.objects.bulk_create([ScheduleEntry(schedule=schedule, assignment=a, room=rooms[m["room"]], day=m["day"], start_time=m["start"], end_time=m["end"]) for a, m in assignments])
        GASettings.objects.get_or_create(name="Full Workbook", defaults={"population_size": 160, "generations": 250, "mutation_rate": .12, "crossover_rate": .85, "elitism": 8})
        return {"schedule": schedule, "counts": {"meetings": len(assignments), "programs": len(programs), "sections": len(sections), "subjects": len({a.subject_id for a, _ in assignments}), "faculty": len(faculty), "rooms": len(rooms)}}

    def audit_conflicts(self, entries):
        output = [{"type": "overlap", "message": message} for message in conflict_messages(entries)]
        signatures = Counter((e.assignment_id, e.room_id, e.day, e.start_time, e.end_time) for e in entries)
        output.extend({"type": "duplicate", "signature": str(key), "count": count} for key, count in signatures.items() if count > 1)
        for e in entries:
            if e.start_time >= e.end_time:
                output.append({"type": "invalid_time", "entry": e.id})
            if not (SCHOOL_START <= e.start_time and e.end_time <= SCHOOL_END):
                output.append({"type": "outside_hours", "entry": e.id})
            if e.room.room_type != e.assignment.effective_room_type:
                output.append({"type": "room_type", "entry": e.id})
            if e.room.capacity < e.assignment.section.size:
                output.append({"type": "capacity", "entry": e.id})
        return output
