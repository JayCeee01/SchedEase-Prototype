"""SHS instructional-day policy; calendar-week accounting remains Monday-Sunday."""
from datetime import date

SHS_DAYS = (0, 1, 2, 3, 4)
WEEKDAY_ERROR = 'SHS classes must be scheduled Monday to Friday; Saturday and Sunday are not allowed.'


def valid_day(day):
    return type(day) is int and day in SHS_DAYS


def snapshot_day_errors(data):
    if not isinstance(data, dict) or not valid_day(data.get('day')):
        return [WEEKDAY_ERROR]
    try:
        dates = data.get('dates')
        if not isinstance(dates, list) or not dates:
            raise ValueError
        if any(date.fromisoformat(value).weekday() not in SHS_DAYS for value in dates):
            return [WEEKDAY_ERROR]
    except (TypeError, ValueError):
        return ['SHS meeting dates are missing or invalid.']
    return []
