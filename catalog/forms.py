from django import forms

from .models import Exercise

PLACEHOLDER_CHOICE = ('', 'Bitte wählen')


class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ['name', 'image', 'goals', 'instructions', 'video_url', 'difficulty', 'force', 'mechanic', 'grip']
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 5}),
            'goals': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['image'].required = False
        self.fields['video_url'].required = False
        self.fields['instructions'].required = False
        self.fields['goals'].required = False
        self.fields['difficulty'].choices = [PLACEHOLDER_CHOICE] + list(self.fields['difficulty'].choices)[1:]
        for name in ('force', 'mechanic', 'grip'):
            self.fields[name].required = False
            self.fields[name].choices = [PLACEHOLDER_CHOICE] + list(self.fields[name].choices)[1:]
