import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Max
from django.utils import timezone

from schedules.models import Availability, AvailabilityKind, Room, RoomKind, Schedule, ScheduleEntry, Section, TeachingAssignment
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START, contains, overlaps


UTILIZATION_THRESHOLDS = {"moderate": 35, "well": 60, "high": 80, "full": 95}


@dataclass
class RoomUtilizationRow:
    room: Room
    daily: list
    available_hours: float
    scheduled_hours: float
    utilization_percentage: float
    capacity_utilization: float
    assigned_classes: int
    status: str
    badge_class: str
    last_updated: object

    @property
    def is_laboratory(self):
        return self.room.room_type != RoomKind.LECTURE


def hours_between(start, end):
    start_dt = datetime.combine(timezone.localdate(), start)
    end_dt = datetime.combine(timezone.localdate(), end)
    return max(0, (end_dt - start_dt).total_seconds() / 3600)


def default_daily_hours():
    return hours_between(SCHOOL_START, SCHOOL_END)


def default_weekly_hours():
    return len(list(ALLOWED_DAYS)) * default_daily_hours()


def room_available_hours_by_day(room):
    result = []
    slots = Availability.objects.filter(room=room)
    has_explicit_availability = slots.filter(kind=AvailabilityKind.AVAILABLE).exists()
    for day in ALLOWED_DAYS:
        daily = slots.filter(day=day)
        available = daily.filter(kind=AvailabilityKind.AVAILABLE)
        if available.exists():
            hours = sum(hours_between(slot.start_time, slot.end_time) for slot in available)
        elif has_explicit_availability:
            hours = 0
        else:
            unavailable = sum(hours_between(slot.start_time, slot.end_time)
                              for slot in daily.filter(kind=AvailabilityKind.UNAVAILABLE))
            hours = max(0, default_daily_hours() - unavailable)
        result.append(round(hours, 2))
    return result


def room_available_hours(room):
    return round(sum(room_available_hours_by_day(room)), 2)


def entry_hours(entry):
    return hours_between(entry.start_time, entry.end_time)


def utilization_status(percentage):
    if percentage == 0:
        return "Unused", ""
    if percentage < UTILIZATION_THRESHOLDS["moderate"]:
        return "Underutilized", "warning"
    if percentage < UTILIZATION_THRESHOLDS["well"]:
        return "Moderately Utilized", ""
    if percentage < UTILIZATION_THRESHOLDS["high"]:
        return "Well Utilized", "success"
    if percentage < UTILIZATION_THRESHOLDS["full"]:
        return "Highly Utilized", "danger"
    return "Fully Utilized", "danger"


def latest_schedule(term=None):
    schedules = Schedule.objects.all()
    if term:
        schedules = schedules.filter(term=term)
    return schedules.order_by("-published_at", "-generated_at", "-id").first()


def utilization_rows(schedule=None, department=None):
    schedule = schedule or latest_schedule()
    rooms = Room.objects.all().order_by("name")
    entries = ScheduleEntry.objects.none()
    if schedule:
        entries = schedule.entries.select_related("room", "assignment__section", "assignment__subject")
        if department:
            entries = entries.filter(assignment__section__program__department=department)
    entries = list(entries)
    rows = []
    for room in rooms:
        room_entries = [entry for entry in entries if entry.room_id == room.id]
        available_by_day = room_available_hours_by_day(room)
        daily = []
        for day in ALLOWED_DAYS:
            scheduled = sum(entry_hours(entry) for entry in room_entries if entry.day == day)
            available = available_by_day[day]
            daily.append({"day": day, "available": available, "scheduled": round(scheduled, 2),
                          "percentage": round(scheduled / available * 100, 1) if available else 0})
        scheduled_hours = sum(item["scheduled"] for item in daily)
        available_hours = sum(item["available"] for item in daily)
        percentage = scheduled_hours / available_hours * 100 if available_hours else 0
        seat_values = [min(100, entry.assignment.section.size / room.capacity * 100)
                       for entry in room_entries if room.capacity]
        seat_percentage = sum(seat_values) / len(seat_values) if seat_values else 0
        status, badge_class = utilization_status(percentage)
        last_updated = (ScheduleEntry.objects.filter(room=room, schedule=schedule)
                        .aggregate(value=Max("updated_at"))["value"] if schedule else None)
        rows.append(RoomUtilizationRow(
            room=room, daily=daily, available_hours=round(available_hours, 2),
            scheduled_hours=round(scheduled_hours, 2), utilization_percentage=round(percentage, 1),
            capacity_utilization=round(seat_percentage, 1), assigned_classes=len(room_entries),
            status=status, badge_class=badge_class,
            last_updated=last_updated or getattr(schedule, "generated_at", None),
        ))
    return rows


def utilization_summary(rows):
    total_available = sum(row.available_hours for row in rows)
    total_scheduled = sum(row.scheduled_hours for row in rows)
    average = round(total_scheduled / total_available * 100, 1) if total_available else 0
    most = max(rows, key=lambda row: row.utilization_percentage, default=None)
    least = min(rows, key=lambda row: row.utilization_percentage, default=None)
    return {
        "total_rooms": len(rows),
        "lecture_rooms": sum(not row.is_laboratory for row in rows),
        "laboratories": sum(row.is_laboratory for row in rows),
        "average_utilization": average,
        "most_utilized_room": most.room.name if most else "None",
        "least_utilized_room": least.room.name if least else "None",
        "underutilized_rooms": sum(row.status == "Underutilized" for row in rows),
        "unused_rooms": sum(row.status == "Unused" for row in rows),
    }


def filtered_rows(rows, query="", room_type="", utilization_range="", room_group="", day=""):
    query = query.strip().lower()
    if query:
        rows = [row for row in rows if query in row.room.name.lower()]
    if room_type:
        rows = [row for row in rows if row.room.room_type == room_type]
    if room_group == "lecture":
        rows = [row for row in rows if not row.is_laboratory]
    elif room_group == "laboratory":
        rows = [row for row in rows if row.is_laboratory]
    if day not in ("", None):
        rows = [row for row in rows if row.daily[int(day)]["scheduled"] > 0]
    legacy_statuses = {"under": "Underutilized", "optimized": "Moderately Utilized", "high": "Highly Utilized"}
    utilization_range = legacy_statuses.get(utilization_range, utilization_range)
    if utilization_range:
        rows = [row for row in rows if row.status == utilization_range]
    return sorted(rows, key=lambda row: row.utilization_percentage, reverse=True)


def room_schedule_grid(room, schedule, slot_minutes=30):
    entries = list(schedule.entries.filter(room=room).select_related(
        "assignment__subject", "assignment__section", "assignment__faculty"
    )) if schedule else []
    availability = list(room.availability_set.all())
    explicit = any(slot.kind == AvailabilityKind.AVAILABLE for slot in availability)
    rows = []
    current = datetime.combine(timezone.localdate(), SCHOOL_START)
    finish = datetime.combine(timezone.localdate(), SCHOOL_END)
    while current < finish:
        next_time = current + timedelta(minutes=slot_minutes)
        cells = []
        for day in ALLOWED_DAYS:
            matched = [entry for entry in entries if entry.day == day and
                       overlaps(current.time(), next_time.time(), entry.start_time, entry.end_time)]
            slots = [slot for slot in availability if slot.day == day]
            available_slots = [slot for slot in slots if slot.kind == AvailabilityKind.AVAILABLE]
            unavailable_slots = [slot for slot in slots if slot.kind == AvailabilityKind.UNAVAILABLE]
            available = (not explicit or any(contains(slot.start_time, slot.end_time, current.time(), next_time.time())
                                             for slot in available_slots))
            if any(overlaps(current.time(), next_time.time(), slot.start_time, slot.end_time) for slot in unavailable_slots):
                available = False
            cells.append({"entries": matched, "available": available})
        rows.append({"start": current.time(), "end": next_time.time(), "cells": cells})
        current = next_time
    return rows


def personal_schedule_grid(entries, slot_minutes=30):
    """Build the same 7 AM–7 PM grid used by room schedules for a user queryset."""
    entries = list(entries)
    rows = []
    current = datetime.combine(timezone.localdate(), SCHOOL_START)
    finish = datetime.combine(timezone.localdate(), SCHOOL_END)
    while current < finish:
        next_time = current + timedelta(minutes=slot_minutes)
        cells = []
        for day in ALLOWED_DAYS:
            matched = [entry for entry in entries if entry.day == day and
                       overlaps(current.time(), next_time.time(), entry.start_time, entry.end_time)]
            cells.append({"entries": matched})
        rows.append({"start": current.time(), "end": next_time.time(), "cells": cells})
        current = next_time
    return rows


def capacity_planning(term=None, assumptions=None):
    assumptions = assumptions or {}
    assignments = TeachingAssignment.objects.all()
    if term:
        assignments = assignments.filter(term=term)
    result = []
    for room_type, label in RoomKind.choices:
        rooms = list(Room.objects.filter(room_type=room_type, is_active=True))
        relevant = [item for item in assignments.select_related("section", "subject")
                    if item.effective_room_type == room_type]
        required = sum(item.required_duration_minutes for item in relevant) / 60
        available = sum(room_available_hours(room) for room in rooms)
        average_room_hours = available / len(rooms) if rooms else default_weekly_hours()
        needed = math.ceil(required / average_room_hours) if required and average_room_hours else 0
        result.append({"room_type": room_type, "label": label, "rooms": len(rooms),
                       "requirements": len(relevant), "required_hours": round(required, 1),
                       "available_hours": round(available, 1), "estimated_utilization": round(required / available * 100, 1) if available else 0,
                       "rooms_needed": needed, "surplus": len(rooms) - needed})
    students = int(assumptions.get("students") or sum(section.size for section in Section.objects.all()))
    class_size = max(1, int(assumptions.get("class_size") or 40))
    subjects = float(assumptions.get("subjects") or 7)
    hours = float(assumptions.get("hours") or 3)
    sections = math.ceil(students / class_size) if students else 0
    required_hours = sections * subjects * hours
    lecture_rooms = [row for row in result if row["room_type"] == RoomKind.LECTURE][0]
    assumed_needed = math.ceil(required_hours / default_weekly_hours()) if required_hours else 0
    lecture_assumptions = {"students": students, "class_size": class_size, "subjects": subjects, "hours": hours,
                           "sections": sections, "required_classes": round(sections * subjects),
                           "required_hours": round(required_hours, 1), "rooms_needed": assumed_needed,
                           "existing_rooms": lecture_rooms["rooms"], "surplus": lecture_rooms["rooms"] - assumed_needed}
    return result, lecture_assumptions
