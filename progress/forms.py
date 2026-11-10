from django import forms
from django.utils import timezone

from accounts.units import Units

from .models import BodyMetricsEntry

WEIGHT_FIELDS = ['weight_kg', 'muscle_mass_kg', 'fat_free_weight_kg', 'bone_mass_kg']
LENGTH_FIELDS = [
    'neck_cm', 'shoulders_cm', 'chest_cm', 'upper_arm_cm', 'forearm_cm', 'waist_cm', 'hip_cm', 'thigh_cm', 'calf_cm',
]
SCALE_FIELDS = [
    'body_fat_pct', 'subcutaneous_fat_pct', 'visceral_fat', 'muscle_mass_kg', 'skeletal_muscle_pct',
    'fat_free_weight_kg', 'bone_mass_kg', 'water_pct', 'protein_pct', 'bmr_kcal', 'metabolic_age',
]
VALUE_FIELDS = ['weight_kg'] + LENGTH_FIELDS + SCALE_FIELDS

LABELS = {
    'date': 'Datum',
    'weight_kg': 'Gewicht',
    'neck_cm': 'Hals',
    'shoulders_cm': 'Schultern',
    'chest_cm': 'Brust',
    'upper_arm_cm': 'Oberarm',
    'forearm_cm': 'Unterarm',
    'waist_cm': 'Bauch',
    'hip_cm': 'Hüfte',
    'thigh_cm': 'Oberschenkel',
    'calf_cm': 'Wade',
    'body_fat_pct': 'Körperfettanteil (%)',
    'subcutaneous_fat_pct': 'Subkutanes Fett (%)',
    'visceral_fat': 'Viszeralfett',
    'muscle_mass_kg': 'Muskelmasse',
    'skeletal_muscle_pct': 'Skelettmuskelanteil (%)',
    'fat_free_weight_kg': 'Fettfreies Körpergewicht',
    'bone_mass_kg': 'Knochenmasse',
    'water_pct': 'Körperwasseranteil (%)',
    'protein_pct': 'Proteinanteil (%)',
    'bmr_kcal': 'Grundumsatz (kcal)',
    'metabolic_age': 'Stoffwechselalter',
}

# Plausible ranges in stored units (kg, cm). Anything outside is almost certainly a typo.
RANGES = {
    'weight_kg': (20, 400),
    'muscle_mass_kg': (5, 200),
    'fat_free_weight_kg': (10, 300),
    'bone_mass_kg': (0.5, 15),
    'body_fat_pct': (1, 75),
    'subcutaneous_fat_pct': (1, 75),
    'skeletal_muscle_pct': (5, 90),
    'water_pct': (10, 90),
    'protein_pct': (1, 50),
    'visceral_fat': (1, 59),
    'bmr_kcal': (500, 6000),
    'metabolic_age': (10, 120),
    **{name: (10, 250) for name in LENGTH_FIELDS},
}


class BodyMetricsEntryForm(forms.ModelForm):
    class Meta:
        model = BodyMetricsEntry
        fields = ['date'] + VALUE_FIELDS
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    # New entries for a day that already has one fill in that entry instead of failing.
    adds_to_day = False

    def __init__(self, *args, user, units=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.units = units or Units()
        if not self.instance.pk:
            self.initial.setdefault('date', timezone.localdate())
        for name, field in self.fields.items():
            field.label = LABELS[name]
            field.required = name == 'date'
            if name == 'date':
                continue
            if isinstance(field, forms.IntegerField):
                field.widget.attrs.update({'inputmode': 'numeric', 'step': '1', 'min': '0'})
            else:
                field.widget.attrs.update({'inputmode': 'decimal', 'step': 'any', 'min': '0'})
        for name in WEIGHT_FIELDS:
            if name in self.fields:
                self._use_unit(name, self.units.weight_label, self.units.weight_out)
        for name in LENGTH_FIELDS:
            if name in self.fields:
                self._use_unit(name, self.units.length_label, self.units.length_out)

    def _use_unit(self, name, label, convert):
        field = self.fields[name]
        field.label = f'{field.label} ({label})'
        # Values in pounds or inches get more decimals than the stored field allows.
        field.decimal_places = None
        field.max_digits = None
        field.validators = []
        if self.instance.pk and not self.is_bound:
            value = getattr(self.instance, name)
            if value is not None:
                self.initial[name] = round(convert(value), 2 if name in WEIGHT_FIELDS else 1)

    def clean_date(self):
        day = self.cleaned_data['date']
        if day > timezone.localdate():
            raise forms.ValidationError('Das Datum darf nicht in der Zukunft liegen.')
        if self.adds_to_day:
            return day
        others = BodyMetricsEntry.objects.filter(user=self.user, date=day).exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError('Für diesen Tag gibt es schon einen Eintrag. Bitte bearbeite diesen.')
        return day

    def clean(self):
        cleaned = super().clean()
        for name in self.value_fields:
            if name in WEIGHT_FIELDS:
                cleaned[name] = self.units.weight_in(cleaned.get(name))
            elif name in LENGTH_FIELDS:
                cleaned[name] = self.units.length_in(cleaned.get(name))
            low, high = RANGES[name]
            value = cleaned.get(name)
            if value is not None and not low <= value <= high:
                self.add_error(name, 'Dieser Wert ist nicht plausibel. Bitte prüfe ihn.')
        if not any(cleaned.get(name) is not None for name in self.value_fields) and not self.errors:
            raise forms.ValidationError('Bitte trage mindestens einen Wert ein.')
        return cleaned

    @property
    def value_fields(self):
        return [name for name in self.fields if name != 'date']

    def save(self, commit=True):
        if self.adds_to_day:
            entry = BodyMetricsEntry.objects.filter(user=self.user, date=self.cleaned_data['date']).first()
            if entry:
                # Only filled-in fields change, so imported scale values and earlier measurements stay.
                for name in self.value_fields:
                    if self.cleaned_data.get(name) is not None:
                        setattr(entry, name, self.cleaned_data[name])
                if commit:
                    entry.save()
                return entry
        entry = super().save(commit=False)
        entry.user = self.user
        if commit:
            entry.save()
        return entry


class WeightEntryForm(BodyMetricsEntryForm):
    adds_to_day = True

    class Meta(BodyMetricsEntryForm.Meta):
        fields = ['date', 'weight_kg'] + SCALE_FIELDS


class MeasurementEntryForm(BodyMetricsEntryForm):
    adds_to_day = True

    class Meta(BodyMetricsEntryForm.Meta):
        fields = ['date'] + LENGTH_FIELDS
