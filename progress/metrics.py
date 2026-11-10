"""Body values shown on the progress page, with their ratings.

The limits match what the RENPHO app showed on 2026-11-06 for a man and on 2026-11-08 for a woman
(176 cm, born 1974), scale R-A031. Where a limit is missing for a gender, the value has no rating.
"""
from dataclasses import dataclass

MALE = 'maennlich'
FEMALE = 'weiblich'

UNDER = 'Unterdurchschnittlich'
AVERAGE = 'Durchschnittlich'
ABOVE = 'Überdurchschnittlich'
HIGH = 'Hoch'
EXCELLENT = 'Ausgezeichnet'

# Bands are (label, colour). A value below limits[i] falls into band i, anything else into the last band.
WEIGHT_BANDS = [(UNDER, 'blue'), (AVERAGE, 'green'), (ABOVE, 'yellow'), (HIGH, 'red')]
BMI_LIMITS = [18.5, 25, 30]

# American Council on Exercise, as used by RENPHO.
BODY_FAT_LIMITS = {MALE: [6, 13, 17, 25], FEMALE: [14, 21, 25, 32]}
BODY_FAT_BANDS = [('Niedrig', 'blue-dark'), ('Athletisch', 'blue'), ('Fitness', 'green'), ('Akzeptabel', 'green-light'), (HIGH, 'red')]

SUBCUTANEOUS_LIMITS = {MALE: [8.6, 16.7], FEMALE: [18.5, 26.7]}
SUBCUTANEOUS_BANDS = [(UNDER, 'blue'), (AVERAGE, 'green'), (ABOVE, 'yellow')]
VISCERAL_LIMITS = {MALE: [6, 11, 15], FEMALE: [6, 11, 15]}
VISCERAL_BANDS = [(UNDER, 'blue'), (AVERAGE, 'green'), (ABOVE, 'yellow'), (HIGH, 'red')]
SKELETAL_MUSCLE_LIMITS = {MALE: [49, 59], FEMALE: [40, 50]}
WATER_LIMITS = {MALE: [50, 65], FEMALE: [45, 60]}
PROTEIN_LIMITS = {MALE: [16, 18], FEMALE: [14, 16]}
# Share of the measured weight: 124.6 kg man -> 3.74 / 6.23 kg, 88.8 kg woman -> 2.22 / 3.55 kg.
BONE_SHARE_LIMITS = {MALE: [3, 5], FEMALE: [2.5, 4]}
MUSCLE_BANDS = [(UNDER, 'blue'), (AVERAGE, 'green'), (EXCELLENT, 'green-dark')]
SHARE_BANDS = [(UNDER, 'blue'), (AVERAGE, 'green'), (ABOVE, 'green-dark')]

# Muscle mass in kg by height. Confirmed against RENPHO for men from 170 cm and women from 160 cm.
MUSCLE_MASS_TABLE = {
    MALE: [(170, (49.4, 59.4)), (160, (44.0, 52.4)), (0, (38.5, 46.5))],
    FEMALE: [(160, (36.5, 42.5)), (150, (32.9, 37.5)), (0, (29.1, 34.7))],
}

# WHO limits for the waist.
WAIST_LIMITS = {MALE: [94, 102], FEMALE: [80, 88]}
WAIST_BANDS = [('Nicht erhöht', 'green'), ('Erhöht', 'yellow'), ('Deutlich erhöht', 'red')]


@dataclass(frozen=True)
class Rating:
    label: str
    colour: str


@dataclass
class Person:
    gender: str = ''
    height_cm: float | None = None
    age: int | None = None


def band(value, limits, bands):
    for limit, result in zip(limits, bands):
        if value < limit:
            return Rating(*result)
    return Rating(*bands[len(limits)])


def _f(value):
    return float(value) if value is not None else None


def expected_bmr(person, weight_kg):
    """Mifflin-St Jeor, the same formula as the calorie calculator."""
    if not person.gender or person.height_cm is None or person.age is None or weight_kg is None:
        return None
    return 10 * weight_kg + 6.25 * person.height_cm - 5 * person.age + (5 if person.gender == MALE else -161)


def muscle_mass_limits(person):
    if person.gender not in MUSCLE_MASS_TABLE or person.height_cm is None:
        return None
    for minimum, limits in MUSCLE_MASS_TABLE[person.gender]:
        if person.height_cm >= minimum:
            return list(limits)
    return None


# Value getters work on one entry. Derived masses only exist when the same entry has a weight.

def _weight(entry):
    return _f(entry.weight_kg)


def _bmi(entry, person):
    if entry.bmi is not None:
        return _f(entry.bmi)
    if entry.weight_kg is None or not person.height_cm:
        return None
    return _f(entry.weight_kg) / (person.height_cm / 100) ** 2


def _share_of_weight(field):
    def getter(entry):
        value, weight = getattr(entry, field), entry.weight_kg
        if value is None or weight is None:
            return None
        return _f(value) * _f(weight) / 100
    return getter


def _percent_of_weight(field):
    def getter(entry):
        value, weight = getattr(entry, field), entry.weight_kg
        if value is None or not weight:
            return None
        return _f(value) / _f(weight) * 100
    return getter


def _field(name):
    return lambda entry: _f(getattr(entry, name))


# Raters get the value, the person and the weight of the same entry.

def _by_gender(table, bands, scale_by_weight=False):
    def rate(value, person, weight):
        limits = table.get(person.gender)
        if limits is None:
            return None
        if scale_by_weight:
            if weight is None:
                return None
            limits = [limit * weight / 100 for limit in limits]
        return band(value, limits, bands)
    return rate


def _rate_weight(value, person, weight):
    if not person.height_cm:
        return None
    squared = (person.height_cm / 100) ** 2
    return band(value, [limit * squared for limit in BMI_LIMITS], WEIGHT_BANDS)


def _rate_bmi(value, person, weight):
    return band(value, BMI_LIMITS, WEIGHT_BANDS)


def _rate_muscle_mass(value, person, weight):
    limits = muscle_mass_limits(person)
    return band(value, limits, MUSCLE_BANDS) if limits else None


def _rate_muscle_share(value, person, weight):
    limits = muscle_mass_limits(person)
    if not limits or not weight:
        return None
    return band(value, [limit / weight * 100 for limit in limits], MUSCLE_BANDS)


def _rate_metabolic_age(value, person, weight):
    if person.age is None:
        return None
    return Rating(EXCELLENT, 'green') if value <= person.age else Rating(ABOVE, 'yellow')


def _rate_bmr(value, person, weight):
    expected = expected_bmr(person, weight)
    if expected is None:
        return None
    return Rating(UNDER, 'yellow') if value < expected else Rating(AVERAGE, 'green')


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    kind: str  # weight, length, percent, bmi, number, kcal, years
    get: object
    rate: object = None
    needs_person: bool = False
    # Whether a rise is progress. Weight, fat and body measurements should go down.
    higher_is_better: bool = False

    def value(self, entry, person):
        return self.get(entry, person) if self.needs_person else self.get(entry)


BODY_METRICS = [
    Metric('weight', 'Gewicht', 'weight', _weight, _rate_weight),
    Metric('bmi', 'BMI', 'bmi', _bmi, _rate_bmi, needs_person=True),
    Metric('body_fat_pct', 'Körperfettanteil', 'percent', _field('body_fat_pct'), _by_gender(BODY_FAT_LIMITS, BODY_FAT_BANDS)),
    Metric('fat_mass', 'Körperfettmasse', 'weight', _share_of_weight('body_fat_pct'), _by_gender(BODY_FAT_LIMITS, BODY_FAT_BANDS, True)),
    Metric('subcutaneous_fat_pct', 'Subkutanes Fett', 'percent', _field('subcutaneous_fat_pct'), _by_gender(SUBCUTANEOUS_LIMITS, SUBCUTANEOUS_BANDS)),
    Metric('visceral_fat', 'Viszeralfett', 'number', _field('visceral_fat'), _by_gender(VISCERAL_LIMITS, VISCERAL_BANDS)),
    Metric('muscle_pct', 'Muskelanteil', 'percent', _percent_of_weight('muscle_mass_kg'), _rate_muscle_share, higher_is_better=True),
    Metric('muscle_mass', 'Muskelmasse', 'weight', _field('muscle_mass_kg'), _rate_muscle_mass, higher_is_better=True),
    Metric('skeletal_muscle_pct', 'Skelettmuskelanteil', 'percent', _field('skeletal_muscle_pct'), _by_gender(SKELETAL_MUSCLE_LIMITS, MUSCLE_BANDS), higher_is_better=True),
    Metric('skeletal_muscle_mass', 'Skelettmuskelmasse', 'weight', _share_of_weight('skeletal_muscle_pct'), _by_gender(SKELETAL_MUSCLE_LIMITS, MUSCLE_BANDS, True), higher_is_better=True),
    Metric('bone_pct', 'Knochenanteil', 'percent', _percent_of_weight('bone_mass_kg'), _by_gender(BONE_SHARE_LIMITS, SHARE_BANDS), higher_is_better=True),
    Metric('bone_mass', 'Knochenmasse', 'weight', _field('bone_mass_kg'), _by_gender(BONE_SHARE_LIMITS, SHARE_BANDS, True), higher_is_better=True),
    Metric('fat_free_weight', 'Fettfreies Körpergewicht', 'weight', _field('fat_free_weight_kg'), higher_is_better=True),
    Metric('metabolic_age', 'Stoffwechselalter', 'years', _field('metabolic_age'), _rate_metabolic_age),
    Metric('bmr', 'Grundumsatz', 'kcal', _field('bmr_kcal'), _rate_bmr, higher_is_better=True),
    Metric('water_pct', 'Körperwasseranteil', 'percent', _field('water_pct'), _by_gender(WATER_LIMITS, SHARE_BANDS), higher_is_better=True),
    Metric('water_mass', 'Körperwassermasse', 'weight', _share_of_weight('water_pct'), _by_gender(WATER_LIMITS, SHARE_BANDS, True), higher_is_better=True),
    Metric('protein_pct', 'Proteinanteil', 'percent', _field('protein_pct'), _by_gender(PROTEIN_LIMITS, SHARE_BANDS), higher_is_better=True),
    Metric('protein_mass', 'Proteinmasse', 'weight', _share_of_weight('protein_pct'), _by_gender(PROTEIN_LIMITS, SHARE_BANDS, True), higher_is_better=True),
]

MEASUREMENT_METRICS = [
    Metric('neck', 'Hals', 'length', _field('neck_cm')),
    Metric('shoulders', 'Schultern', 'length', _field('shoulders_cm')),
    Metric('chest', 'Brust', 'length', _field('chest_cm')),
    Metric('upper_arm', 'Oberarm', 'length', _field('upper_arm_cm')),
    Metric('forearm', 'Unterarm', 'length', _field('forearm_cm')),
    Metric('waist', 'Bauch', 'length', _field('waist_cm'), _by_gender(WAIST_LIMITS, WAIST_BANDS)),
    Metric('hip', 'Hüfte', 'length', _field('hip_cm')),
    Metric('thigh', 'Oberschenkel', 'length', _field('thigh_cm')),
    Metric('calf', 'Wade', 'length', _field('calf_cm')),
]


def age_on(birth_date, day):
    if not birth_date:
        return None
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def person_for(user_data, day):
    if user_data is None:
        return Person()
    return Person(
        gender=user_data.gender,
        height_cm=_f(user_data.height_cm),
        age=age_on(user_data.birth_date, day),
    )


@dataclass
class Reading:
    """The latest value of one metric, with its rating and the change to the measurement before."""
    metric: Metric
    value: float
    date: object
    rating: Rating | None
    change: float | None
    previous_date: object


def latest_readings(metrics, entries, user_data):
    """entries must be ordered newest first."""
    readings = []
    for metric in metrics:
        found = []
        for entry in entries:
            value = metric.value(entry, person_for(user_data, entry.date))
            if value is not None:
                found.append((entry, value))
                if len(found) == 2:
                    break
        if not found:
            continue
        entry, value = found[0]
        rating = metric.rate(value, person_for(user_data, entry.date), _weight(entry)) if metric.rate else None
        previous = found[1] if len(found) > 1 else None
        readings.append(Reading(
            metric=metric,
            value=value,
            date=entry.date,
            rating=rating,
            change=value - previous[1] if previous else None,
            previous_date=previous[0].date if previous else None,
        ))
    return readings


# Limits that stay the same from one measurement to the next, so a chart can draw them as
# coloured areas. Masses whose limits follow the weight of each measurement are left out.
FIXED_LIMITS = {
    'bmi': (lambda person: BMI_LIMITS, WEIGHT_BANDS),
    'body_fat_pct': (lambda person: BODY_FAT_LIMITS.get(person.gender), BODY_FAT_BANDS),
    'subcutaneous_fat_pct': (lambda person: SUBCUTANEOUS_LIMITS.get(person.gender), SUBCUTANEOUS_BANDS),
    'visceral_fat': (lambda person: VISCERAL_LIMITS.get(person.gender), VISCERAL_BANDS),
    'muscle_mass': (muscle_mass_limits, MUSCLE_BANDS),
    'skeletal_muscle_pct': (lambda person: SKELETAL_MUSCLE_LIMITS.get(person.gender), MUSCLE_BANDS),
    'bone_pct': (lambda person: BONE_SHARE_LIMITS.get(person.gender), SHARE_BANDS),
    'water_pct': (lambda person: WATER_LIMITS.get(person.gender), SHARE_BANDS),
    'protein_pct': (lambda person: PROTEIN_LIMITS.get(person.gender), SHARE_BANDS),
}


def fixed_bands(key, person):
    """[{'low', 'high', 'label', 'colour'}] from the lowest band up, or None.

    The lowest band has no lower end and the highest no upper end.
    """
    if key not in FIXED_LIMITS:
        return None
    get_limits, bands = FIXED_LIMITS[key]
    limits = get_limits(person)
    if not limits:
        return None
    edges = [None] + list(limits) + [None]
    return [
        {'low': edges[i], 'high': edges[i + 1], 'label': label, 'colour': colour}
        for i, (label, colour) in enumerate(bands[:len(limits) + 1])
    ]
