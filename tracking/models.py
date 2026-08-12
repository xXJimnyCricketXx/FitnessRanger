from django.conf import settings
from django.db import models

from catalog.models import Exercise, WorkoutExercise


class TrackingEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tracking_entries')
    date = models.DateField()
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='tracking_entries')
    workout_exercise = models.ForeignKey(
        WorkoutExercise,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tracking_entries',
    )
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.user} - {self.exercise} ({self.date})'
