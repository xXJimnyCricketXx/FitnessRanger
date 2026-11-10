"""Weight trend and progress towards the weight goal.

The expected finish works like a scale app: it takes the current pace (the
seven-day change) and says how many weeks the rest takes at that pace. After a
step the wrong way it shows '–', and a weighing without any change keeps the
forecast of the week before.
"""
from dataclasses import dataclass
from datetime import timedelta

SEVEN_DAYS = 7
# Weekly weighings don't always fall exactly seven days apart.
MAX_GAP_DAYS = 14

LOSE, GAIN, HOLD = 'lose', 'gain', 'hold'
TITLES = {LOSE: 'Körpergewicht verlieren', GAIN: 'Körpergewicht aufbauen', HOLD: 'Gewicht halten'}


@dataclass
class Weighing:
    date: object
    kg: float


def weighings(entries):
    """Entries newest first -> weighings oldest first."""
    return [Weighing(e.date, float(e.weight_kg)) for e in reversed(entries) if e.weight_kg is not None]


def seven_day_change(points):
    """Latest weight against the weighing closest to seven days earlier.

    Someone weighing daily gets exactly a week, someone weighing weekly gets the
    previous weighing even when it was six or eight days before.
    """
    if len(points) < 2:
        return None
    latest = points[-1]
    candidates = [p for p in points[:-1] if 1 <= (latest.date - p.date).days <= MAX_GAP_DAYS]
    if not candidates:
        return None
    # Closest to seven days; on a tie the older one, so the span covers a full week.
    best = min(candidates, key=lambda p: (abs((latest.date - p.date).days - SEVEN_DAYS), p.date))
    return latest.kg - best.kg


def direction(start, target, goal_type):
    if goal_type == 'halten' or abs(start - target) < 0.05:
        return HOLD
    return LOSE if target < start else GAIN


def towards(change, way):
    if change is None or round(change, 2) == 0:
        return False
    return (change < 0) == (way == LOSE)


def current_pace(points, way):
    """Pace for the forecast, or None when the last step didn't go towards the goal.

    Weighings without any change are skipped, so the forecast of the week before stays.
    """
    end = len(points)
    while end > 1 and round(points[end - 1].kg - points[end - 2].kg, 2) == 0:
        end -= 1
    if end < 2:
        return None
    last = points[end - 1].kg - points[end - 2].kg
    pace = seven_day_change(points[:end])
    if not towards(last, way) or not towards(pace, way):
        return None
    return abs(pace)


@dataclass
class GoalProgress:
    direction: str
    title: str
    start_kg: float
    target_kg: float
    current_kg: float
    percent: int | None
    total_change_kg: float
    remaining_kg: float
    reached: bool
    weeks_left: float | None
    finish_date: object


def goal_progress(points, start_kg, target_kg, goal_type):
    if not points or target_kg is None or start_kg is None:
        return None
    current = points[-1].kg
    way = direction(start_kg, target_kg, goal_type)
    remaining = current - target_kg if way == LOSE else target_kg - current
    reached = way != HOLD and remaining <= 0
    percent = None
    if way != HOLD:
        done = (start_kg - current) if way == LOSE else (current - start_kg)
        percent = max(0, min(100, round(done / abs(start_kg - target_kg) * 100)))

    weeks_left = finish = None
    if way != HOLD and not reached:
        pace = current_pace(points, way)
        if pace:
            weeks_left = remaining / pace
            finish = points[-1].date + timedelta(weeks=weeks_left)

    return GoalProgress(
        direction=way,
        title=TITLES[way],
        start_kg=start_kg,
        target_kg=target_kg,
        current_kg=current,
        percent=percent,
        total_change_kg=current - start_kg,
        remaining_kg=max(remaining, 0),
        reached=reached,
        weeks_left=weeks_left,
        finish_date=finish,
    )


def duration_label(weeks):
    """Weeks for the near future, months and years further out, always with the unit."""
    if weeks < 1.5:
        return '1 Woche'
    if weeks < 52:
        return f'{round(weeks)} Wochen'
    months = weeks * 7 / 30.44
    if months < 24:
        return f'ca. {round(months)} Monate'
    return f'ca. {round(weeks / 52.18)} Jahre'


def finish_label(progress):
    if not progress or progress.direction == HOLD:
        return None
    if progress.reached:
        return 'Erreicht'
    if progress.weeks_left is None:
        return '–'
    return duration_label(progress.weeks_left)


def hold_status(points, target_kg, tolerance_kg):
    """For 'Gewicht halten': how far off the wish weight, and since when inside the range."""
    if not points or target_kg is None:
        return None
    inside = [abs(p.kg - target_kg) <= tolerance_kg + 1e-9 for p in points]
    streak_start = None
    for point, ok in zip(reversed(points), reversed(inside)):
        if not ok:
            break
        streak_start = point.date
    weeks = (points[-1].date - streak_start).days // 7 if streak_start else None
    return {
        'deviation_kg': points[-1].kg - target_kg,
        'inside': inside[-1],
        'since': streak_start,
        'weeks': weeks,
    }


def gain_progress(series, target):
    """Progress of something that should grow, e.g. muscle mass. series is [(date, value)] oldest first."""
    if not series:
        return None
    (start_date, start), (_, current) = series[0], series[-1]
    percent = None
    if target is not None and target != start:
        percent = max(0, min(100, round((current - start) / (target - start) * 100)))
    return {
        'start': start,
        'start_date': start_date,
        'current': current,
        'change': current - start,
        'percent': percent,
        'reached': target is not None and current >= target,
    }
