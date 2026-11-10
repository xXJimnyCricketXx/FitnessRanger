from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from accounts.models import UserData
from accounts.units import Units

from . import importers
from . import statistics
from .forms import (
    LABELS, LENGTH_FIELDS, SCALE_FIELDS, WEIGHT_FIELDS, BodyMetricsEntryForm, MeasurementEntryForm, WeightEntryForm,
)
from . import goal as goal_module
from .metrics import BODY_METRICS, MEASUREMENT_METRICS, fixed_bands, latest_readings, person_for
from .models import BodyMetricsEntry, Goal, ProgressPhoto
from .photos import POSES, PhotoUploadForm

TABS = ('koerperwerte', 'koerpermasse', 'fotos', 'historie')
DIGITS = {'weight': 2, 'length': 1, 'percent': 1, 'bmi': 1, 'number': 0, 'kcal': 0, 'years': 0}


def format_number(value, digits):
    text = f'{value:,.{digits}f}'
    return text.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def format_change(value, digits):
    rounded = round(value, digits)
    if rounded == 0:
        return format_number(0, digits)
    sign = '+' if rounded > 0 else '−'
    return sign + format_number(abs(rounded), digits)


def trend(change, digits, higher_is_better=False):
    """good, bad or same, judged on the change as the user sees it (after rounding)."""
    if change is None:
        return None
    rounded = round(change, digits)
    if rounded == 0:
        return 'same'
    return 'good' if (rounded > 0) == higher_is_better else 'bad'


def direction(change, digits):
    if change is None:
        return None
    rounded = round(change, digits)
    return 'flat' if rounded == 0 else ('up' if rounded > 0 else 'down')


class Display:
    """Turns stored values into what the user reads, in their units."""

    def __init__(self, units):
        self.units = units

    def unit(self, kind):
        return {
            'weight': self.units.weight_label,
            'length': self.units.length_label,
            'percent': '%',
            'kcal': 'kcal',
        }.get(kind, '')

    def digits(self, kind):
        if kind == 'weight' and self.units.uses_lb:
            return 1
        return DIGITS[kind]

    def convert(self, kind, value):
        if value is None:
            return None
        if kind == 'weight':
            return float(self.units.weight_out(value))
        if kind == 'length':
            return float(self.units.length_out(value))
        return float(value)

    def value(self, kind, value):
        converted = self.convert(kind, value)
        return None if converted is None else format_number(converted, self.digits(kind))

    def tile(self, reading):
        kind = reading.metric.kind
        change = self.convert(kind, reading.change)
        return {
            'key': reading.metric.key,
            'label': reading.metric.label,
            'value': self.value(kind, reading.value),
            'unit': self.unit(kind),
            'date': reading.date,
            'rating': reading.rating,
            'change': None if change is None else format_change(change, self.digits(kind)),
            'trend': trend(change, self.digits(kind), reading.metric.higher_is_better),
            'direction': direction(change, self.digits(kind)),
            'previous_date': reading.previous_date,
        }


def _compare(weight, by_key):
    """Changes shown next to the weight, only when they compare the same two measurements."""
    if not weight or weight['change'] is None:
        return []
    tiles = [by_key.get(key) for key in ('bmi', 'body_fat_pct', 'muscle_mass')]
    return [
        tile for tile in tiles
        if tile and tile['change'] is not None
        and tile['date'] == weight['date'] and tile['previous_date'] == weight['previous_date']
    ]


def _source_label(entry):
    """Body measurements are always typed in, so a day can mix an import with manual values."""
    label = entry.get_source_display()
    has_measurements = any(getattr(entry, name) is not None for name in LENGTH_FIELDS)
    if entry.source != BodyMetricsEntry.Source.MANUAL and has_measurements:
        return f'{label} + Manuell'
    return label


def _user_data(user):
    return UserData.objects.filter(user=user).first()


# With a muscle or strength goal these should grow. Neck, waist and hip should shrink for every goal.
GROWING_MEASUREMENTS = {'shoulders_cm', 'chest_cm', 'upper_arm_cm', 'forearm_cm', 'thigh_cm', 'calf_cm'}
BUILDING_GOALS = {'muskelaufbau', 'kraft_aufbauen'}


def _flip(value):
    return {'good': 'bad', 'bad': 'good'}.get(value, value)


def _measurement_table(entries, display, goal_type):
    """Days with body measurements, newest first, each value compared with the previous one of its kind."""
    measured = [e for e in entries if any(getattr(e, name) is not None for name in LENGTH_FIELDS)]
    columns = [name for name in LENGTH_FIELDS if any(getattr(e, name) is not None for e in measured)]
    digits = display.digits('length')
    rows = []
    for index, entry in enumerate(measured):
        cells = []
        for name in columns:
            value = getattr(entry, name)
            cell = {'value': display.value('length', value)}
            older = next((getattr(e, name) for e in measured[index + 1:] if getattr(e, name) is not None), None)
            if value is not None and older is not None:
                change = display.convert('length', value - older)
                grows = goal_type in BUILDING_GOALS and name in GROWING_MEASUREMENTS
                cell.update({
                    'change': format_change(change, digits),
                    'direction': direction(change, digits),
                    'trend': trend(change, digits, higher_is_better=grows),
                })
            cells.append(cell)
        rows.append({'entry': entry, 'cells': cells})
    return {'columns': [LABELS[name] for name in columns], 'rows': rows}


def _weight_card(points, weight, goal, display, way):
    """Weight trend card: current weight, last and seven-day change, expected finish."""
    if not weight:
        return None
    digits = display.digits('weight')
    gain = way == goal_module.GAIN
    seven = goal_module.seven_day_change(points)
    seven = None if seven is None else display.convert('weight', seven)
    return {
        'value': weight['value'],
        'unit': weight['unit'],
        'date': weight['date'],
        'rating': weight['rating'],
        'last_change': weight['change'],
        'last_trend': weight['trend'],
        'seven_change': None if seven is None else format_change(seven, digits),
        'seven_trend': trend(seven, digits, higher_is_better=gain),
        'finish': goal_module.finish_label(goal),
        'finish_date': goal.finish_date if goal else None,
    }


GOAL_TITLES = {
    'abnehmen': 'Körpergewicht verlieren',
    'halten': 'Gewicht halten',
    'muskelaufbau': 'Muskelaufbau',
    'kraft_aufbauen': 'Kraft aufbauen',
}
SIZE_MEASUREMENTS = ('upper_arm_cm', 'chest_cm', 'thigh_cm')
DEFAULT_TOLERANCE_KG = 1.0


def _weight_goal_card(goal, display):
    change = display.convert('weight', goal.total_change_kg)
    gaining = goal.direction == goal_module.GAIN
    return {
        'kind': 'weight',
        'percent': goal.percent,
        'reached': goal.reached,
        'change_label': 'Gesamtzunahme' if gaining else 'Gesamtabnahme',
        'change': display.value('weight', abs(change)),
        'target': display.value('weight', goal.target_kg),
        'start': display.value('weight', goal.start_kg),
    }


def _hold_goal_card(goal_entry, points, display):
    tolerance = float(goal_entry.weight_tolerance_kg or DEFAULT_TOLERANCE_KG)
    status = goal_module.hold_status(points, float(goal_entry.target_weight_kg), tolerance)
    if not status:
        return {'kind': 'hint', 'text': 'Trag dein erstes Gewicht ein, dann siehst du hier, ob du im Zielbereich bist.'}
    deviation = display.convert('weight', status['deviation_kg'])
    return {
        'kind': 'hold',
        'inside': status['inside'],
        'deviation': format_change(deviation, display.digits('weight')),
        'target': display.value('weight', goal_entry.target_weight_kg),
        'tolerance': display.value('weight', tolerance),
        'weeks': status['weeks'],
        'since': status['since'],
    }


def _muscle_goal_card(goal_entry, entries, display, weight_goal):
    series = [(e.date, float(e.muscle_mass_kg)) for e in reversed(entries) if e.muscle_mass_kg is not None]
    target = float(goal_entry.target_muscle_mass_kg) if goal_entry.target_muscle_mass_kg else None
    card = {'kind': 'muscle'}
    progress = goal_module.gain_progress(series, target)
    if progress:
        change = display.convert('weight', progress['change'])
        card.update({
            'percent': progress['percent'],
            'reached': progress['reached'],
            'change': format_change(change, display.digits('weight')),
            'trend': trend(change, display.digits('weight'), higher_is_better=True),
            'current': display.value('weight', progress['current']),
            'target': display.value('weight', target) if target is not None else None,
            'since': progress['start_date'],
        })
    else:
        # Without a body analysis scale the size of arms, chest and thighs shows the progress.
        sizes = []
        for name in SIZE_MEASUREMENTS:
            values = [(e.date, getattr(e, name)) for e in reversed(entries) if getattr(e, name) is not None]
            if len(values) > 1:
                change = display.convert('length', values[-1][1] - values[0][1])
                sizes.append({
                    'label': LABELS[name],
                    'change': format_change(change, display.digits('length')),
                    'trend': trend(change, display.digits('length'), higher_is_better=True),
                    'since': values[0][0],
                })
        card['sizes'] = sizes
    if weight_goal:
        card['weight_target'] = display.value('weight', weight_goal.target_kg)
        card['weight_left'] = display.value('weight', weight_goal.remaining_kg)
    return card


def _goal_card(goal_entry, weight_goal, points, entries, display):
    """The right-hand goal card, depending on the goal type in Meine Daten."""
    goal_type = goal_entry.goal_type if goal_entry else None
    if not goal_type:
        return None
    card = None
    if goal_type == 'abnehmen':
        card = _weight_goal_card(weight_goal, display) if weight_goal else {
            'kind': 'hint', 'text': 'Trag in Meine Daten ein Zielgewicht ein, dann siehst du hier deinen Fortschritt.'}
    elif goal_type == 'halten':
        card = _hold_goal_card(goal_entry, points, display) if goal_entry.target_weight_kg else {
            'kind': 'hint', 'text': 'Trag in Meine Daten dein Wunschgewicht ein, dann siehst du hier, ob du im Zielbereich bist.'}
    elif goal_type == 'muskelaufbau':
        card = _muscle_goal_card(goal_entry, entries, display, weight_goal)
    else:
        card = {'kind': 'hint', 'text': 'Dein Kraftfortschritt erscheint hier, sobald du Workouts protokollierst.'}
    card['title'] = GOAL_TITLES[goal_type]
    card['unit'] = display.units.weight_label
    card['length_unit'] = display.units.length_label
    return card


def _photo_gallery(user):
    """Days with photos, newest first, one slot per pose, plus the data the comparison needs."""
    photos = list(ProgressPhoto.objects.filter(user=user).order_by('-date', 'pose'))
    by_day = {}
    for photo in photos:
        by_day.setdefault(photo.date, {})[photo.pose] = photo
    labels = dict(ProgressPhoto.Pose.choices)
    days = [
        {'date': day, 'slots': [{'label': labels[pose], 'photo': poses.get(pose)} for pose in POSES]}
        for day, poses in by_day.items()
    ]
    compare = {
        day.isoformat(): {pose: reverse('fortschritt-foto', args=[photo.pk]) for pose, photo in poses.items()}
        for day, poses in by_day.items()
    }
    return days, compare


def _weight_context(user, user_data, points):
    """Start, goal and the direction that counts as progress, shared by progress and statistics."""
    goal_entry = Goal.objects.filter(user=user).order_by('-created_at').first()
    goal_type = goal_entry.goal_type if goal_entry else None
    has_start = bool(user_data and user_data.starting_weight_kg is not None)
    start_kg = float(user_data.starting_weight_kg) if has_start else (points[0].kg if points else None)
    target_kg = float(goal_entry.target_weight_kg) if goal_entry and goal_entry.target_weight_kg else None
    # Only weight goals forecast a finish and decide whether gaining weight counts as progress.
    goal = None
    if goal_type in ('abnehmen', 'muskelaufbau'):
        goal = goal_module.goal_progress(points, start_kg, target_kg, goal_type)
    way = goal.direction if goal else goal_module.LOSE
    return goal_entry, goal_type, has_start, start_kg, target_kg, goal, way


class ProgressView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def get(self, request):
        entries = list(BodyMetricsEntry.objects.filter(user=request.user).order_by('-date'))
        user_data = _user_data(request.user)
        units = Units.for_user(request.user)
        display = Display(units)

        points = goal_module.weighings(entries)
        goal_entry, goal_type, has_start, start_kg, target_kg, goal, way = _weight_context(request.user, user_data, points)

        body = [display.tile(r) for r in latest_readings(BODY_METRICS, entries, user_data)]
        if way == goal_module.GAIN:
            for tile in body:
                if tile['key'] in ('weight', 'bmi'):
                    tile['trend'] = _flip(tile['trend'])
        measurements = [display.tile(r) for r in latest_readings(MEASUREMENT_METRICS, entries, user_data)]
        by_key = {tile['key']: tile for tile in body}
        weight = by_key.get('weight')

        since_start = None
        if points and (has_start or len(points) > 1):
            difference = display.convert('weight', points[-1].kg - start_kg)
            since_start = {
                'change': format_change(difference, display.digits('weight')),
                'trend': trend(difference, display.digits('weight'), higher_is_better=way == goal_module.GAIN),
                'start': display.value('weight', start_kg),
                'unit': units.weight_label,
                'label': 'Seit Ausgangsgewicht' if has_start else 'Seit erster Messung',
            }

        history = [{
            'entry': entry,
            'weight': display.value('weight', entry.weight_kg),
            'body_fat': display.value('percent', entry.body_fat_pct),
            'muscle': display.value('weight', entry.muscle_mass_kg),
            'measurements': ', '.join(LABELS[name] for name in LENGTH_FIELDS if getattr(entry, name) is not None),
            'source': _source_label(entry),
        } for entry in entries]

        photo_days, photo_compare = _photo_gallery(request.user)
        tab = request.GET.get('tab')
        return render(request, 'progress/progress.html', {
            'photo_days': photo_days,
            'photo_compare': photo_compare,
            'poses': ProgressPhoto.Pose.choices,
            'entries': entries,
            'weight': weight,
            'weight_card': _weight_card(points, weight, goal, display, way),
            'goal_card': _goal_card(goal_entry, goal, points, entries, display),
            'compare': _compare(weight, by_key),
            'latest_date': entries[0].date if entries else None,
            'since_start': since_start,
            'body_tiles': body,
            'measurement_tiles': measurements,
            'measurement_table': _measurement_table(entries, display, goal_type),
            'waist': next((t for t in measurements if t['key'] == 'waist'), None),
            'history': history,
            'units': units,
            'initial_tab': tab if tab in TABS else TABS[0],
            'missing_profile': not (user_data and user_data.gender and user_data.height_cm and user_data.birth_date),
        })


def _stat(display, kg, way=None, signed=False):
    """One figure for the statistics tiles, in the user's units."""
    if kg is None:
        return None
    value = display.convert('weight', kg)
    digits = display.digits('weight')
    result = {'value': format_change(value, digits) if signed else format_number(value, digits)}
    if way is not None:
        result['trend'] = trend(value, digits, higher_is_better=way == goal_module.GAIN)
        result['direction'] = direction(value, digits)
    return result


# Scales are used about weekly, tape measures far less often.
COMPOSITION_GAP_DAYS = 14
MEASUREMENT_GAP_DAYS = 42
TABLE_COLUMNS = [
    # key, label, kind
    ('weight', 'Gewicht', 'weight'),
    ('body_fat_pct', 'Körperfett', 'percent'),
    ('muscle_mass', 'Muskelmasse', 'weight'),
    ('waist', 'Bauch', 'length'),
]


def _series(metric, entries, user_data, display, max_gap):
    """One metric over the given entries (oldest first) for a chart, or None without values."""
    found = []
    for entry in entries:
        person = person_for(user_data, entry.date)
        value = metric.value(entry, person)
        if value is not None:
            found.append((entry, person, value))
    if not found:
        return None
    kind = metric.kind
    digits = display.digits(kind)
    points = [goal_module.Weighing(entry.date, value) for entry, _, value in found]
    last_entry, last_person, last_value = found[-1]
    rating = metric.rate(last_value, last_person, last_entry.weight_kg and float(last_entry.weight_kg)) if metric.rate else None
    result = {
        'key': metric.key,
        'label': metric.label,
        'unit': display.unit(kind) or ('Jahre' if kind == 'years' else ''),
        'digits': digits,
        'points': [{'x': p.date.isoformat(), 'y': display.convert(kind, p.kg)} for p in points],
        'gaps': statistics.gaps(points, max_gap),
        'latest': display.value(kind, last_value),
        'latest_date': last_entry.date,
        'rating': {'label': rating.label, 'colour': rating.colour} if rating else None,
        'change': None,
    }
    if len(points) > 1:
        change = display.convert(kind, points[-1].kg - points[0].kg)
        result.update({
            'change': format_change(change, digits),
            'trend': trend(change, digits, metric.higher_is_better),
            'direction': direction(change, digits),
            'first_date': points[0].date,
        })
    return result


def _bands_in_units(key, person, kind, display):
    bands = fixed_bands(key, person)
    if not bands:
        return None
    return [{**band, 'low': display.convert(kind, band['low']), 'high': display.convert(kind, band['high'])} for band in bands]


def _overview(entries, user_data, display, way, goal_type, first_day, unit):
    """Week or month averages, newest first, each compared with the bucket before that has the value."""
    metrics = {m.key: m for m in BODY_METRICS + MEASUREMENT_METRICS}
    rows = []
    for entry in entries:
        person = person_for(user_data, entry.date)
        rows.append((entry.date, {key: metrics[key].value(entry, person) for key, _, _ in TABLE_COLUMNS}))
    buckets = statistics.bucket_averages(rows, unit)
    shown = [b for b in buckets if first_day is None or b['end'] >= first_day]
    columns = [c for c in TABLE_COLUMNS if any(c[0] in b['values'] for b in shown)]
    better_up = {
        'weight': way == goal_module.GAIN,
        'body_fat_pct': False,
        'muscle_mass': True,
        'waist': False,
    }
    table = []
    for bucket in reversed(shown):
        index = buckets.index(bucket)
        cells = []
        for key, _, kind in columns:
            value = bucket['values'].get(key)
            cell = {'value': None if value is None else display.value(kind, value)}
            before = next((b for b in reversed(buckets[:index]) if key in b['values']), None)
            if value is not None and before is not None:
                digits = display.digits(kind)
                change = display.convert(kind, value - before['values'][key])
                cell.update({
                    'change': format_change(change, digits),
                    'trend': trend(change, digits, better_up[key]),
                    'direction': direction(change, digits),
                    'compared': before['start'],
                })
            cells.append(cell)
        table.append({'start': bucket['start'], 'end': bucket['end'], 'count': bucket['count'], 'cells': cells})
    return {
        'columns': [{'label': label, 'unit': display.unit(kind)} for _, label, kind in columns],
        'rows': table,
    }


class StatisticsView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def get(self, request):
        entries = list(BodyMetricsEntry.objects.filter(user=request.user).order_by('-date'))
        user_data = _user_data(request.user)
        units = Units.for_user(request.user)
        display = Display(units)
        all_points = goal_module.weighings(entries)
        goal_entry, goal_type, has_start, start_kg, target_kg, goal, way = _weight_context(
            request.user, user_data, all_points,
        )

        period = request.GET.get('zeitraum')
        if period not in statistics.PERIOD_KEYS:
            period = statistics.DEFAULT_PERIOD
        points = statistics.in_period(all_points, period, timezone.localdate())
        summary = statistics.summarize(points)

        tiles = None
        if summary:
            tiles = {
                'change': _stat(display, summary.change, way=way, signed=True),
                'per_week': _stat(display, summary.per_week, way=way, signed=True),
                'lowest': {**_stat(display, summary.lowest.kg), 'date': summary.lowest.date},
                'highest': {**_stat(display, summary.highest.kg), 'date': summary.highest.date},
                'count': summary.count,
                'first_date': summary.first.date,
                'last_date': summary.last.date,
                'span': goal_module.duration_label((summary.last.date - summary.first.date).days / 7),
            }

        lines = []
        if start_kg is not None:
            lines.append({
                'label': 'Ausgangsgewicht' if has_start else 'Erste Messung', 'kind': 'start',
                'y': display.convert('weight', start_kg),
            })
        band = None
        if goal_type == 'halten' and target_kg is not None:
            tolerance = float(goal_entry.weight_tolerance_kg or DEFAULT_TOLERANCE_KG)
            band = {
                'label': 'Zielbereich',
                'low': display.convert('weight', target_kg - tolerance),
                'high': display.convert('weight', target_kg + tolerance),
            }
        elif goal_type in ('abnehmen', 'muskelaufbau') and target_kg is not None:
            lines.append({'label': 'Zielgewicht', 'kind': 'target', 'y': display.convert('weight', target_kg)})

        averages = statistics.rolling_average(points, all_points)
        chart = {
            'unit': units.weight_label,
            'digits': display.digits('weight'),
            'points': [{'x': p.date.isoformat(), 'y': display.convert('weight', p.kg)} for p in points],
            'average': [display.convert('weight', kg) for kg in averages],
            'gaps': statistics.gaps(points),
            'lines': lines,
            'band': band,
        }

        today = timezone.localdate()
        oldest_first = list(reversed(entries))
        period_entries = statistics.in_period(oldest_first, period, today)
        days = statistics.period_days(period)
        first_day = today - timedelta(days=days - 1) if days else None
        person = person_for(user_data, today)

        composition = []
        for metric in BODY_METRICS:
            if metric.key == 'weight':
                continue
            series = _series(metric, period_entries, user_data, display, COMPOSITION_GAP_DAYS)
            if series:
                if way == goal_module.GAIN and metric.key == 'bmi' and series['change']:
                    series['trend'] = _flip(series['trend'])
                series['bands'] = _bands_in_units(metric.key, person, metric.kind, display)
                composition.append(series)
        keys = [series['key'] for series in composition]
        preferred = ['muscle_mass', 'body_fat_pct'] if goal_type in BUILDING_GOALS else ['body_fat_pct', 'muscle_mass']
        composition_default = next((key for key in preferred if key in keys), keys[0] if keys else None)

        measurements = []
        for metric in MEASUREMENT_METRICS:
            series = _series(metric, period_entries, user_data, display, MEASUREMENT_GAP_DAYS)
            if series:
                if goal_type in BUILDING_GOALS and f'{metric.key}_cm' in GROWING_MEASUREMENTS and series['change']:
                    series['trend'] = _flip(series['trend'])
                measurements.append(series)
        available = [series['key'] for series in measurements]
        wanted = ['waist'] + (['upper_arm', 'chest'] if goal_type in BUILDING_GOALS else [])
        measurement_default = [key for key in wanted if key in available] or available[:1]

        overview = {
            unit: _overview(oldest_first, user_data, display, way, goal_type, first_day, unit)
            for unit in (statistics.WEEK, statistics.MONTH)
        }

        return render(request, 'progress/statistics.html', {
            'has_weighings': bool(all_points),
            'has_entries': bool(entries),
            'composition': composition,
            'composition_default': composition_default,
            'measurements': measurements,
            'measurement_default': measurement_default,
            'overview': overview,
            'overview_default': statistics.WEEK if days and days <= 91 else statistics.MONTH,
            'periods': statistics.PERIODS,
            'period': period,
            'period_label': dict((k, label) for k, label, _ in statistics.PERIODS)[period],
            'tiles': tiles,
            'chart': chart,
            'unit': units.weight_label,
        })


class EntryFormMixin(LoginRequiredMixin):
    login_url = 'login-page'
    form_class = BodyMetricsEntryForm
    title = 'Eintrag bearbeiten'

    def render_form(self, request, form, entry=None):
        return render(request, 'progress/entry_form.html', {
            'form': form,
            'entry': entry,
            'title': self.title,
            'has_weight': 'weight_kg' in form.fields,
            'measurement_fields': [form[name] for name in LENGTH_FIELDS if name in form.fields],
            'scale_fields': [form[name] for name in SCALE_FIELDS if name in form.fields],
        })

    def form_for(self, request, entry=None):
        return self.form_class(
            request.POST if request.method == 'POST' else None,
            instance=entry,
            user=request.user,
            units=Units.for_user(request.user),
        )


class EntryCreateView(EntryFormMixin, View):
    tab = None

    def get(self, request):
        return self.render_form(request, self.form_for(request))

    def post(self, request):
        form = self.form_for(request)
        if not form.is_valid():
            return self.render_form(request, form)
        form.save()
        messages.success(request, 'Eintrag gespeichert.')
        url = reverse('fortschritt')
        return redirect(f'{url}?tab={self.tab}' if self.tab else url)


class WeightCreateView(EntryCreateView):
    form_class = WeightEntryForm
    title = 'Gewicht eintragen'


class MeasurementCreateView(EntryCreateView):
    form_class = MeasurementEntryForm
    title = 'Körpermaße eintragen'
    tab = 'koerpermasse'


class EntryEditView(EntryFormMixin, View):
    def get(self, request, pk):
        entry = get_object_or_404(BodyMetricsEntry, pk=pk, user=request.user)
        return self.render_form(request, self.form_for(request, entry), entry)

    def post(self, request, pk):
        entry = get_object_or_404(BodyMetricsEntry, pk=pk, user=request.user)
        form = self.form_for(request, entry)
        if not form.is_valid():
            return self.render_form(request, form, entry)
        form.save()
        messages.success(request, 'Eintrag gespeichert.')
        return redirect(f"{reverse('fortschritt')}?tab=historie")


class EntryDeleteView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def post(self, request, pk):
        entry = get_object_or_404(BodyMetricsEntry, pk=pk, user=request.user)
        entry.delete()
        messages.success(request, 'Eintrag gelöscht.')
        return redirect(f"{reverse('fortschritt')}?tab=historie")


IMPORT_SESSION_KEY = 'progress_import'
IMPORT_LABELS = {**LABELS, 'bmi': 'BMI'}


def _import_value(display, name, value):
    if value is None:
        return '–'
    if name in WEIGHT_FIELDS:
        return f"{display.value('weight', value)} {display.units.weight_label}"
    if name == 'bmi':
        return display.value('bmi', value)
    if name in ('visceral_fat', 'bmr_kcal', 'metabolic_age'):
        return display.value('number', value)
    return display.value('percent', value)


class ImportView(LoginRequiredMixin, View):
    login_url = 'login-page'
    template_name = 'progress/import.html'

    def get(self, request):
        request.session.pop(IMPORT_SESSION_KEY, None)
        return render(request, self.template_name, {'formats': importers.FORMATS})

    def post(self, request):
        if 'confirm' in request.POST:
            return self.confirm(request)
        upload = request.FILES.get('file')
        if not upload:
            return self.error(request, 'Bitte wähle eine Datei aus.')
        if upload.size > importers.MAX_FILE_BYTES:
            return self.error(request, 'Die Datei ist zu groß (höchstens 2 MB).')
        try:
            result = importers.parse(upload.read(), today=timezone.localdate())
        except importers.ImportFileError as error:
            return self.error(request, str(error))
        if not result.rows:
            return self.error(request, 'In der Datei wurden keine gültigen Messungen gefunden.', result.problems)

        request.session[IMPORT_SESSION_KEY] = {
            'format': result.format.key,
            'rows': importers.rows_to_session(result.rows),
        }
        display = Display(Units.for_user(request.user))
        planned = importers.plan(request.user, result.rows)
        preview = [{
            'date': item.row.date,
            'status': item.status,
            'weight': _import_value(display, 'weight_kg', item.row.values.get('weight_kg')),
            'body_fat': _import_value(display, 'body_fat_pct', item.row.values.get('body_fat_pct')),
            'count': len(item.row.values),
            'changes': [
                {'label': IMPORT_LABELS[name], 'old': _import_value(display, name, old),
                 'new': _import_value(display, name, new)}
                for name, (old, new) in item.changes.items()
            ],
        } for item in planned]
        return render(request, self.template_name, {
            'formats': importers.FORMATS,
            'result': result,
            'preview': preview,
            'file_name': upload.name,
            'new_count': sum(1 for p in planned if p.status == 'neu'),
            'changed_count': sum(1 for p in planned if p.status == 'geändert'),
            'unchanged_count': sum(1 for p in planned if p.status == 'unverändert'),
        })

    def confirm(self, request):
        data = request.session.pop(IMPORT_SESSION_KEY, None)
        fmt = next((f for f in importers.FORMATS if data and f.key == data.get('format')), None)
        if not fmt:
            return self.error(request, 'Die Vorschau ist abgelaufen. Bitte lade die Datei erneut hoch.')
        created, updated = importers.apply(request.user, importers.rows_from_session(data['rows']), fmt.source)
        if created or updated:
            messages.success(request, f'Import abgeschlossen: {created} neu, {updated} aktualisiert.')
        else:
            messages.success(request, 'Import abgeschlossen: Alle Werte waren schon vorhanden.')
        return redirect(f"{reverse('fortschritt')}?tab=historie")

    def error(self, request, message, problems=None):
        request.session.pop(IMPORT_SESSION_KEY, None)
        return render(request, self.template_name, {
            'formats': importers.FORMATS, 'error': message, 'problems': problems or [],
        })


class PhotoUploadView(LoginRequiredMixin, View):
    login_url = 'login-page'
    template_name = 'progress/photo_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': PhotoUploadForm(user=request.user)})

    def post(self, request):
        form = PhotoUploadForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})
        saved = form.save()
        messages.success(request, 'Foto gespeichert.' if len(saved) == 1 else f'{len(saved)} Fotos gespeichert.')
        return redirect(f"{reverse('fortschritt')}?tab=fotos")


class PhotoFileView(LoginRequiredMixin, View):
    """Hands a photo only to its owner. Everyone else gets a 404, not even a hint that it exists."""
    login_url = 'login-page'

    def get(self, request, pk):
        photo = get_object_or_404(ProgressPhoto, pk=pk, user=request.user)
        response = FileResponse(photo.image.open('rb'), content_type='image/jpeg')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class PhotoDeleteView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def post(self, request, pk):
        photo = get_object_or_404(ProgressPhoto, pk=pk, user=request.user)
        if photo.image:
            photo.image.delete(save=False)
        photo.delete()
        messages.success(request, 'Foto gelöscht.')
        return redirect(f"{reverse('fortschritt')}?tab=fotos")
