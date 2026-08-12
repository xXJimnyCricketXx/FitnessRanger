from django.conf import settings
from django.db import models

from catalog.models import Equipment, Workout


class UserEquipment(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='equipment_profile'
    )
    equipment = models.ManyToManyField(Equipment, blank=True, related_name='user_equipment')
    studio_access = models.BooleanField(default=False)

    def __str__(self):
        return f'Equipment von {self.user}'


class TrainingPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='training_plans')
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.user})'


class TrainingPlanEntry(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Montag'
        TUESDAY = 1, 'Dienstag'
        WEDNESDAY = 2, 'Mittwoch'
        THURSDAY = 3, 'Donnerstag'
        FRIDAY = 4, 'Freitag'
        SATURDAY = 5, 'Samstag'
        SUNDAY = 6, 'Sonntag'

    plan = models.ForeignKey(TrainingPlan, on_delete=models.CASCADE, related_name='entries')
    weekday = models.IntegerField(choices=Weekday.choices)
    time_slot = models.CharField(max_length=50, blank=True)
    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name='plan_entries')
    sets_override = models.PositiveIntegerField(null=True, blank=True)
    reps_override = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['weekday', 'time_slot']

    def __str__(self):
        return f'{self.plan} - {self.get_weekday_display()}'
