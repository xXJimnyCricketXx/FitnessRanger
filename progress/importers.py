"""Reading exported measurements from other apps.

Each format is recognised by its header line. Columns are matched by name, so a
changed column order still works, and columns we don't know are skipped. Files we
don't recognise are rejected instead of guessed, so nothing lands in the wrong field.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from .forms import RANGES
from .models import BodyMetricsEntry

MAX_FILE_BYTES = 2 * 1024 * 1024
EMPTY_VALUES = {'', '--', '-'}
INTEGER_FIELDS = {'visceral_fat', 'bmr_kcal', 'metabolic_age'}
IMPORT_RANGES = {**RANGES, 'bmi': (5, 150)}


class ImportFileError(Exception):
    """A file that can't be imported at all, with a message for the user."""


@dataclass
class ImportFormat:
    key: str
    name: str
    source: str
    date_column: str
    date_format: str
    time_column: str | None
    columns: dict
    # Each group lists alternative names of a column the file must have.
    required: tuple = ()
    # Columns we know but don't store, e.g. values the app works out itself.
    ignored: tuple = ()

    def matches(self, header):
        return self.date_column in header and all(
            any(name in header for name in group) for group in self.required)


RENPHO = ImportFormat(
    key='renpho',
    name='RENPHO Health',
    source=BodyMetricsEntry.Source.RENPHO_CSV,
    date_column='Datum',
    date_format='%Y.%m.%d',
    time_column='Zeitraum',
    # RENPHO renamed several columns in newer app versions, both spellings are accepted.
    columns={
        'Gewicht(kg)': 'weight_kg',
        'BMI': 'bmi',
        'Körperfett(%)': 'body_fat_pct',
        'Körperfettanteil(%)': 'body_fat_pct',
        'Skelettmuskel(%)': 'skeletal_muscle_pct',
        'Skelettmuskelanteil(%)': 'skeletal_muscle_pct',
        'Fettfreies Körpergewicht(kg)': 'fat_free_weight_kg',
        'Subkutanes Fett(%)': 'subcutaneous_fat_pct',
        'Viszeralfett': 'visceral_fat',
        'Körperwasser(%)': 'water_pct',
        'Körperwasseranteil(%)': 'water_pct',
        'Muskelmasse(kg)': 'muscle_mass_kg',
        'Knochenmasse(kg)': 'bone_mass_kg',
        'Eiweiß(%)': 'protein_pct',
        'Proteinanteil(%)': 'protein_pct',
        'Grundumsatz(kcal)': 'bmr_kcal',
        'Stoffwechselalter': 'metabolic_age',
    },
    required=(('Gewicht(kg)',), ('Körperfett(%)', 'Körperfettanteil(%)')),
    ignored=(
        'Nr.', 'Körperfettmasse(kg)', 'Muskelanteil(%)', 'Skelettmuskelmasse(kg)', 'Knochenanteil(%)',
        'Proteinmasse(kg)', 'Körperwassermasse(kg)',
    ),
)

FORMATS = [RENPHO]


@dataclass
class ImportRow:
    line: int
    date: date
    time: time | None
    values: dict


@dataclass
class ParseResult:
    format: ImportFormat
    rows: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    skipped_columns: list = field(default_factory=list)
    replaced_same_day: int = 0


def _decode(data):
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFileError('Die Datei lässt sich nicht lesen. Bitte exportiere sie erneut als CSV.')


def _number(text, name):
    text = text.strip()
    if text in EMPTY_VALUES:
        return None
    if ',' in text and '.' not in text:
        text = text.replace(',', '.')
    value = Decimal(text)
    if not value.is_finite():
        raise InvalidOperation
    if name in INTEGER_FIELDS:
        if value != value.to_integral_value():
            raise InvalidOperation
        return int(value)
    return value


def detect_format(header):
    for fmt in FORMATS:
        if fmt.matches(header):
            return fmt
    names = ', '.join(fmt.name for fmt in FORMATS)
    raise ImportFileError(f'Das Format dieser Datei ist nicht bekannt. Unterstützt wird bisher: {names}.')


def parse(data, today=None):
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError('Die Datei ist zu groß (höchstens 2 MB).')
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = [name.strip() for name in next(reader, [])]
    if not header:
        raise ImportFileError('Die Datei ist leer.')

    fmt = detect_format(header)
    result = ParseResult(format=fmt)
    known = {fmt.date_column, fmt.time_column, *fmt.columns, *fmt.ignored}
    result.skipped_columns = [name for name in header if name and name not in known]
    index = {name: i for i, name in enumerate(header)}
    today = today or date.today()
    by_day = {}

    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue

        def cell(name):
            i = index.get(name)
            return cells[i] if i is not None and i < len(cells) else ''

        try:
            day = datetime.strptime(cell(fmt.date_column).strip(), fmt.date_format).date()
        except ValueError:
            result.problems.append(f'Zeile {line}: Das Datum „{cell(fmt.date_column)}“ ist ungültig.')
            continue
        if day > today:
            result.problems.append(f'Zeile {line}: Das Datum liegt in der Zukunft.')
            continue
        moment = None
        if fmt.time_column:
            try:
                moment = datetime.strptime(cell(fmt.time_column).strip(), '%H:%M:%S').time()
            except ValueError:
                moment = None

        values = {}
        for column, name in fmt.columns.items():
            if column not in index:
                continue
            try:
                value = _number(cell(column), name)
            except (InvalidOperation, ValueError):
                result.problems.append(f'Zeile {line}: „{column}“ ist keine Zahl und wurde übersprungen.')
                continue
            if value is None:
                continue
            low, high = IMPORT_RANGES[name]
            if not low <= value <= high:
                result.problems.append(f'Zeile {line}: „{column}“ ist nicht plausibel und wurde übersprungen.')
                continue
            values[name] = value
        if not values:
            result.problems.append(f'Zeile {line}: Keine Werte gefunden.')
            continue

        row = ImportRow(line=line, date=day, time=moment, values=values)
        earlier = by_day.get(day)
        if earlier:
            result.replaced_same_day += 1
            # One entry per day: the later measurement of the day wins.
            if (row.time or time.min) < (earlier.time or time.min):
                continue
        by_day[day] = row

    result.rows = sorted(by_day.values(), key=lambda r: r.date, reverse=True)
    return result


@dataclass
class PlannedRow:
    row: ImportRow
    entry: BodyMetricsEntry | None
    changes: dict

    @property
    def status(self):
        if self.entry is None:
            return 'neu'
        return 'geändert' if self.changes else 'unverändert'


def plan(user, rows):
    """Compares imported rows with what the user already has. Only fields in the file are touched."""
    existing = {e.date: e for e in BodyMetricsEntry.objects.filter(user=user, date__in=[r.date for r in rows])}
    planned = []
    for row in rows:
        entry = existing.get(row.date)
        changes = {}
        if entry:
            for name, value in row.values.items():
                old = getattr(entry, name)
                if old is None or Decimal(old) != Decimal(value):
                    changes[name] = (old, value)
        planned.append(PlannedRow(row=row, entry=entry, changes=changes))
    return planned


def apply(user, rows, source):
    created = updated = 0
    for item in plan(user, rows):
        if item.entry is None:
            BodyMetricsEntry.objects.create(user=user, date=item.row.date, source=source, **item.row.values)
            created += 1
        elif item.changes:
            for name, (_, value) in item.changes.items():
                setattr(item.entry, name, value)
            item.entry.save(update_fields=list(item.changes))
            updated += 1
    return created, updated


def rows_to_session(rows):
    return [{'date': r.date.isoformat(), 'values': {k: str(v) for k, v in r.values.items()}} for r in rows]


def rows_from_session(data):
    rows = []
    for item in data:
        values = {
            name: int(value) if name in INTEGER_FIELDS else Decimal(value)
            for name, value in item['values'].items() if name in IMPORT_RANGES
        }
        rows.append(ImportRow(line=0, date=date.fromisoformat(item['date']), time=None, values=values))
    return rows
