from django import forms
from django.contrib.auth.models import User

from catalog.models import Equipment
from plans.models import UserEquipment
from progress.models import Goal

from .models import Profile, UserData

PLACEHOLDER_CHOICE = ('', 'Bitte wählen')


class UserDataForm(forms.ModelForm):
    class Meta:
        model = UserData
        fields = ['birth_date', 'gender', 'height_cm', 'starting_weight_kg', 'fitness_level', 'activity_level']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('gender', 'fitness_level', 'activity_level'):
            self.fields[name].choices = [PLACEHOLDER_CHOICE] + list(self.fields[name].choices)[1:]


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ['goal_type', 'target_weight_kg', 'target_date']
        widgets = {
            'target_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['goal_type'].choices = [PLACEHOLDER_CHOICE] + list(self.fields['goal_type'].choices)[1:]


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


class AvatarForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['avatar']


class UsernameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username']
        labels = {'username': 'Benutzername'}
