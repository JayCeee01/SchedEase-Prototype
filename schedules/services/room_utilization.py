from dataclasses import dataclass
from datetime import datetime

from django.db.models import Max
from django.utils import timezone

from schedules.models import Availability, AvailabilityKind, Room, Schedule, ScheduleEntry
from .time import ALLOWED_DAYS, SCHOOL_END, SCHOOL_START


@dataclass
class RoomUtilizationRow:
    room: Room
    available_hours: float
    scheduled_hours: float
    utilization_percentage: float
    assigned_classes: int
    status: str
    badge_class: str
    last_updated: object


def hours_between(start, end):
    start_dt = datetime.combine(timezone.localdate(), start)
    end_dt = datetime.combine(timezone.localdate(), end)
    return max(0, (end_dt - start_dt).total_seconds() / 3600)


def default_weekly_hours():
    return len(list(ALLOWED_DAYS)) * hours_between(SCHOOL_START, SCHOOL_END)


def room_available_hours(room):
    slots = Availability.objects.filter(room=room)
    explicit_available = slots.filter(kind=AvailabilityKind.AVAILABLE)
    if explicit_available.exists():
        return sum(hours_between(slot.start_time, slot.end_time) for slot in explicit_available)

    unavailable_hours = sum(
        hours_between(slot.start_time, slot.end_time)
        for slot in slots.filter(kind=AvailabilityKind.UNAVAILABLE)
    )
    return max(0, default_weekly_hours() - unavailable_hours)


def entry_hours(entry):
    return hours_between(entry.start_time, entry.end_time)


def utilization_status(percentage):
    if percentage < 35:
        return "Underutilized", "warning"
    if percentage <= 75:
        return "Optimized", "success"
    return "Highly Utilized", "danger"


def latest_schedule():
    return Schedule.objects.order_by("-published_at", "-generated_at", "-id").first()


def utilization_rows(schedule=None):
    schedule = schedule or latest_schedule()
    rooms = Room.objects.all().order_by("name")
    entries = ScheduleEntry.objects.none()
    if schedule:
        entries = schedule.entries.select_related("room")

    rows = []
    for room in rooms:
        room_entries = [entry for entry in entries if entry.room_id == room.id]
        scheduled_hours = sum(entry_hours(entry) for entry in room_entries)
        available_hours = room_available_hours(room)
        percentage = (scheduled_hours / available_hours * 100) if available_hours else 0
        status, badge_class = utilization_status(percentage)
        last_updated = (
            ScheduleEntry.objects.filter(room=room, schedule=schedule).aggregate(value=Max("updated_at"))["value"]
            if schedule
            else None
        )
        rows.append(
            RoomUtilizationRow(
                room=room,
                available_hours=round(available_hours, 2),
                scheduled_hours=round(scheduled_hours, 2),
                utilization_percentage=round(percentage, 1),
                assigned_classes=len(room_entries),
                status=status,
                badge_class=badge_class,
                last_updated=last_updated or getattr(schedule, "generated_at", None),
            )
        )
    return rows


def utilization_summary(rows):
    total_rooms = len(rows)
    average = round(sum(row.utilization_percentage for row in rows) / total_rooms, 1) if total_rooms else 0
    most = max(rows, key=lambda row: row.utilization_percentage, default=None)
    least = min(rows, key=lambda row: row.utilization_percentage, default=None)
    underutilized = sum(1 for row in rows if row.status == "Underutilized")
    return {
        "total_rooms": total_rooms,
        "average_utilization": average,
        "most_utilized_room": most.room.name if most else "None",
        "least_utilized_room": least.room.name if least else "None",
        "underutilized_rooms": underutilized,
    }


def filtered_rows(rows, query="", room_type="", utilization_range=""):
    query = query.strip().lower()
    if query:
        rows = [row for row in rows if query in row.room.name.lower()]
    if room_type:
        rows = [row for row in rows if row.room.room_type == room_type]
    if utilization_range == "under":
        rows = [row for row in rows if row.utilization_percentage < 35]
    elif utilization_range == "optimized":
        rows = [row for row in rows if 35 <= row.utilization_percentage <= 75]
    elif utilization_range == "high":
        rows = [row for row in rows if row.utilization_percentage > 75]
    return sorted(rows, key=lambda row: row.utilization_percentage, reverse=True)
