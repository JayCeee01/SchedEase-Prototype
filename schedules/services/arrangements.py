"""Advisory equal-duration arrangements, not timetable feasibility predictions."""
from .meetings import duration_errors


def suggested_arrangements(hours):
    total = hours * 60
    return [[total // count] * count for count in range(1, 5)
            if total > 0 and total % count == 0 and (total // count) % 30 == 0
            and not duration_errors(total // count)]
