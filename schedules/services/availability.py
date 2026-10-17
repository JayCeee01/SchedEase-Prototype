"""Shared availability policy for placement validation and room reporting."""

from schedules.models import AvailabilityKind
from .time import ALLOWED_DAYS, SCHOOL_START, SCHOOL_END, contains, overlaps


def merge_intervals(intervals):
    """Merge overlapping and touching intervals; touching meetings do not overlap."""
    merged = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


class AvailabilityPolicy:
    def __init__(self, periods, *, active=True):
        periods = list(periods)
        self.active = active
        explicit = any(item.kind == AvailabilityKind.AVAILABLE for item in periods)
        self.allowed = {}
        self.blocked = {}
        for day in ALLOWED_DAYS:
            self.allowed[day] = merge_intervals(
                (max(SCHOOL_START, item.start_time), min(SCHOOL_END, item.end_time))
                for item in periods if item.day == day and item.kind == AvailabilityKind.AVAILABLE
            ) if explicit else [(SCHOOL_START, SCHOOL_END)]
            self.blocked[day] = merge_intervals(
                (item.start_time, item.end_time) for item in periods
                if item.day == day and item.kind == AvailabilityKind.UNAVAILABLE
            )

    def effective_intervals(self, day):
        """Return allowed intervals after subtracting blocked time, without double counting."""
        intervals = list(self.allowed.get(day, [])) if self.active else []
        for blocked_start, blocked_end in self.blocked.get(day, []):
            remaining = []
            for start, end in intervals:
                if not overlaps(start, end, blocked_start, blocked_end):
                    remaining.append((start, end))
                    continue
                if start < blocked_start:
                    remaining.append((start, blocked_start))
                if blocked_end < end:
                    remaining.append((blocked_end, end))
            intervals = remaining
        return intervals

    def active_rejection_reason(self):
        return "" if self.active else "is inactive. Choose an active resource."

    def rejection_reason(self, day, start, end):
        if self.active_rejection_reason():
            return self.active_rejection_reason()
        if day not in self.allowed or start >= end or not contains(SCHOOL_START, SCHOOL_END, start, end):
            return "is not available outside the school's operating days and hours."
        if any(overlaps(start, end, left, right) for left, right in self.blocked[day]):
            return "is unavailable during this time. Choose a time outside its unavailable periods."
        if not self.allowed[day]:
            return "is not available on this day. Choose a day with an available period."
        if not any(contains(left, right, start, end) for left, right in self.allowed[day]):
            return "is not available for the entire meeting. Choose a time fully inside an available period."
        return ""

    @classmethod
    def for_resource(cls, resource):
        return cls(resource.availability_set.all(), active=getattr(resource, "is_active", True))
