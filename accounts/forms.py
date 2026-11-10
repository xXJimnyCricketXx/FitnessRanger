from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from catalog.models import Equipment
from plans.models import UserEquipment
from progress.models import Goal

from .models import Profile, SystemSettings, UserData, UserSettings
from .units import Units

PLACEHOLDER_CHOICE = ('', 'Bitte wählen')


class UnitFieldsMixin:
    """Shows and takes weights and lengths in the user's units. The database keeps kg and cm.

    The dicts map a field to the decimal places it is stored with.
    """
    weight_fields = {}
    length_fields = {}

    def setup_units(self, units):
        self.units = units or Units()
        for name, places in self.weight_fields.items():
            if self.units.uses_lb:
                self._convert_field(name, self.units.weight_out, 2)
        for name, places in self.length_fields.items():
            if self.units.uses_inches:
                self._convert_field(name, self.units.length_out, 1)

    def _convert_field(self, name, convert, shown_places):
        # Pounds and inches need more decimals than the stored kg or cm field allows.
        old = self.fields[name]
        self.fields[name] = forms.DecimalField(required=old.required, label=old.label, min_value=0)
        if not self.is_bound:
            value = getattr(self.instance, name, None)
            if value is not None:
                self.initial[name] = round(convert(value), shown_places)

    def convert_units(self, cleaned):
        for name, places in self.weight_fields.items():
            if cleaned.get(name) is not None:
                cleaned[name] = self.units.weight_in(cleaned[name], places)
        for name, places in self.length_fields.items():
            if cleaned.get(name) is not None:
                value = self.units.length_in(cleaned[name], places)
                cleaned[name] = int(value) if places == 0 else value
        return cleaned


class UserDataForm(UnitFieldsMixin, forms.ModelForm):
    class Meta:
        model = UserData
        fields = ['birth_date', 'gender', 'height_cm', 'starting_weight_kg', 'fitness_level', 'activity_level']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    weight_fields = {'starting_weight_kg': 2}
    length_fields = {'height_cm': 0}

    def __init__(self, *args, units=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_units(units)
        for name in ('gender', 'fitness_level', 'activity_level'):
            self.fields[name].choices = [PLACEHOLDER_CHOICE] + list(self.fields[name].choices)[1:]
        for name in ('height_cm', 'starting_weight_kg'):
            self.fields[name].widget.attrs.update({'inputmode': 'decimal', 'step': 'any', 'min': '0'})

    def clean(self):
        return self.convert_units(super().clean())


class GoalForm(UnitFieldsMixin, forms.ModelForm):
    class Meta:
        model = Goal
        fields = ['goal_type', 'target_muscle_mass_kg', 'target_weight_kg', 'weight_tolerance_kg', 'target_date']
        widgets = {
            'target_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    # Which fields mean something for which goal. The page hides the others.
    FIELDS_FOR = {
        'target_weight_kg': ('abnehmen', 'halten', 'muskelaufbau'),
        'weight_tolerance_kg': ('halten',),
        'target_muscle_mass_kg': ('muskelaufbau',),
        'target_date': ('abnehmen', 'muskelaufbau'),
    }
    # In kg, checked after the conversion.
    RANGES = {'target_weight_kg': (20, 400), 'target_muscle_mass_kg': (5, 200), 'weight_tolerance_kg': (0.1, 20)}
    weight_fields = {'target_muscle_mass_kg': 2, 'target_weight_kg': 2, 'weight_tolerance_kg': 1}

    def __init__(self, *args, units=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_units(units)
        self.fields['goal_type'].choices = [PLACEHOLDER_CHOICE] + list(self.fields['goal_type'].choices)[1:]
        for name in ('target_weight_kg', 'weight_tolerance_kg', 'target_muscle_mass_kg'):
            self.fields[name].widget.attrs.update({'inputmode': 'decimal', 'step': 'any', 'min': '0'})

    def clean(self):
        cleaned = self.convert_units(super().clean())
        for name, (low, high) in self.RANGES.items():
            value = cleaned.get(name)
            if value is not None and not low <= value <= high:
                self.add_error(name, 'Dieser Wert ist nicht plausibel. Bitte prüfe ihn.')
        return cleaned


class UserEquipmentForm(forms.ModelForm):
    class Meta:
        model = UserEquipment
        fields = ['studio_access', 'equipment']
        widgets = {
            'equipment': forms.CheckboxSelectMultiple(),
        }


class EquipmentCreateForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['name', 'category']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = [PLACEHOLDER_CHOICE] + list(self.fields['category'].choices)[1:]


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ['language', 'weight_unit', 'length_unit']


class SystemSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ['auto_enabled', 'interval_hours', 'keep_count']
        widgets = {'keep_count': forms.NumberInput(attrs={'min': 1, 'max': 365})}


class ManagedUserForm(forms.ModelForm):
    password1 = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'is_superuser', 'is_active']

    def __init__(self, *args, acting_user, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_required_attribute = False
        self.fields['username'].label = 'Benutzername'
        self.fields['username'].help_text = ''
        # Admins can't lock themselves out, which also guarantees one active admin remains.
        if self.instance.pk == acting_user.pk:
            del self.fields['is_superuser']
            del self.fields['is_active']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Diese E-Mail-Adresse wird bereits verwendet.')
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if not password1 and not password2:
            if not self.instance.pk:
                self.add_error('password1', 'Bitte vergib ein Passwort.')
            return cleaned
        if password1 != password2:
            self.add_error('password2', 'Die Passwörter stimmen nicht überein.')
            return cleaned
        try:
            validate_password(password1, self.instance)
        except forms.ValidationError as error:
            self.add_error('password1', error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = user.is_superuser
        if self.cleaned_data.get('password1'):
            user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    remove_avatar = forms.BooleanField(required=False)

    class Meta:
        model = Profile
        fields = ['avatar', 'display_name']
        widgets = {'avatar': forms.FileInput(attrs={'accept': 'image/*'})}

    def save(self, commit=True):
        # A newly chosen image wins over the remove checkbox.
        if self.cleaned_data.get('remove_avatar') and not self.files.get('avatar'):
            self.instance.avatar = None
        return super().save(commit)


class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']
        labels = {'username': 'Benutzername', 'email': 'E-Mail'}

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Diese E-Mail-Adresse wird bereits verwendet.')
        return email
