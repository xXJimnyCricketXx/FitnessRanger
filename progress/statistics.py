"""Numbers for the statistics page: weight over a chosen period.

Everything here works in kg on goal.Weighing points (oldest first). The view
converts to the user's units.
"""
from dataclasses import dataclass
from datetime import timedelta

from .goal import MAX_GAP_DAYS

# key, label, days back (None = everything)
PERIODS = [
    ('4w', '4 Wochen', 28),
    ('3m', '3 Monate', 91),
    ('6m', '6 Monate', 182),
    ('1j', '1 Jahr', 365),
    ('alle', 'Alles', None),
]
PERIOD_KEYS = [key for key, _, _ in PERIODS]
DEFAULT_PERIOD = '3m'
AVERAGE_DAYS = 7


def period_days(key):
    return next((days for k, _, days in PERIODS if k == key), None)


def in_period(points, key, today):
    days = period_days(key)
    if days is None:
        return list(points)
    first_day = today - timedelta(days=days - 1)
    return [p for p in points if p.date >= first_day]


def rolling_average(points, all_points=None, days=AVERAGE_DAYS):
    """Mean of the weighings in the seven days up to each point.

    all_points lets the first points of a period still use the days just before it,
    so the line does not start with a jump.
    """
    source = all_points if all_points is not None else points
    result = []
    for point in points:
        window = [p.kg for p in source if 0 <= (point.date - p.date).days < days]
        result.append(sum(window) / len(window))
    return result


def gaps(points, max_days=MAX_GAP_DAYS):
    """Indexes after which the next weighing is so far away that no line should join them."""
    return [i for i in range(len(points) - 1) if (points[i + 1].date - points[i].date).days > max_days]


@dataclass
class Summary:
    count: int
    first: object
    last: object
    change: float | None
    per_week: float | None
    lowest: object
    highest: object


def summarize(points):
    if not points:
        return None
    first, last = points[0], points[-1]
    span = (last.date - first.date).days
    change = last.kg - first.kg if len(points) > 1 else None
    # Below a week the weekly figure would only blow up day-to-day noise.
    per_week = change / span * 7 if change is not None and span >= 7 else None
    # On equal values the more recent weighing counts.
    lowest = min(reversed(points), key=lambda p: p.kg)
    highest = max(reversed(points), key=lambda p: p.kg)
    return Summary(len(points), first, last, change, per_week, lowest, highest)


WEEK, MONTH = 'woche', 'monat'


def bucket_start(day, unit):
    if unit == WEEK:
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def bucket_end(start, unit):
    if unit == WEEK:
        return start + timedelta(days=6)
    following = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return following - timedelta(days=1)


def bucket_averages(rows, unit):
    """rows: (date, {key: value or None}) in any order -> one dict per week or month, oldest first.

    Each bucket holds the mean of every key that has at least one value in it.
    """
    grouped = {}
    for day, values in rows:
        bucket = grouped.setdefault(bucket_start(day, unit), {'days': set(), 'sums': {}})
        bucket['days'].add(day)
        for key, value in values.items():
            if value is not None:
                bucket['sums'].setdefault(key, []).append(value)
    return [
        {
            'start': start,
            'end': bucket_end(start, unit),
            'count': len(bucket['days']),
            'values': {key: sum(found) / len(found) for key, found in bucket['sums'].items()},
        }
        for start, bucket in sorted(grouped.items())
    ]
