from datetime import time, timedelta, datetime

SCHOOL_START = time(7, 0)
SCHOOL_END = time(19, 0)
SLOT_MINUTES = 60
ALLOWED_DAYS = range(6)


def add_hours(start, hours):
    dt = datetime.combine(datetime.today(), start) + timedelta(hours=hours)
    return dt.time()


def add_minutes(start, minutes):
    dt = datetime.combine(datetime.today(), start) + timedelta(minutes=minutes)
    return dt.time()


def overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def contains(window_start, window_end, start, end):
    return window_start <= start and end <= window_end


def hourly_starts(duration_hours):
    current = datetime.combine(datetime.today(), SCHOOL_START)
    latest_end = datetime.combine(datetime.today(), SCHOOL_END)
    while current + timedelta(hours=duration_hours) <= latest_end:
        yield current.time()
        current += timedelta(minutes=SLOT_MINUTES)


def slot_starts(duration_minutes, slot_minutes=30):
    current = datetime.combine(datetime.today(), SCHOOL_START)
    latest_end = datetime.combine(datetime.today(), SCHOOL_END)
    while current + timedelta(minutes=duration_minutes) <= latest_end:
        yield current.time()
        current += timedelta(minutes=slot_minutes)
