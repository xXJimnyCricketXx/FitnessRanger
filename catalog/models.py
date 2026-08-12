from django.conf import settings
from django.db import models


class MuscleGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    region = models.CharField(max_length=100)

    class Meta:
        ordering = ['region', 'name']

    def __str__(self):
        return self.name


class Equipment(models.Model):
    class Category(models.TextChoices):
        FREE_WEIGHTS = 'freie_gewichte', 'Freie Gewichte'
        MACHINE_STRENGTH = 'maschine_kraft', 'Maschine - Kraft'
        MACHINE_CARDIO = 'maschine_cardio', 'Maschine - Cardio'
        ACCESSORY = 'zubehoer', 'Zubehoer'
        BALANCE = 'balance_koordination', 'Balance & Koordination'

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=30, choices=Category.choices)
    is_bodyweight = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment_created',
    )

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class Exercise(models.Model):
    class Difficulty(models.TextChoices):
        BEGINNER = 'anfaenger', 'Anfaenger'
        ADVANCED = 'fortgeschritten', 'Fortgeschritten'
        PRO = 'profi', 'Profi'

    class Force(models.TextChoices):
        PUSH = 'push', 'Push'
        PULL = 'pull', 'Pull'
        STATIC = 'static', 'Static'

    class Mechanic(models.TextChoices):
        COMPOUND = 'compound', 'Compound'
        ISOLATION = 'isolation', 'Isolation'

    class Grip(models.TextChoices):
        OVERHAND = 'obergriff', 'Obergriff'
        UNDERHAND = 'untergriff', 'Untergriff'
        NEUTRAL = 'neutral', 'Neutral'
        NONE = 'keiner', 'Keiner'

    name = models.CharField(max_length=150)
    muscle_groups = models.ManyToManyField(
        MuscleGroup, through='ExerciseMuscle', related_name='exercises'
    )
    equipment = models.ManyToManyField(Equipment, related_name='exercises', blank=True)
    instructions = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices)
    force = models.CharField(max_length=10, choices=Force.choices, blank=True)
    mechanic = models.CharField(max_length=10, choices=Mechanic.choices, blank=True)
    grip = models.CharField(max_length=10, choices=Grip.choices, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exercises_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ExerciseMuscle(models.Model):
    class Role(models.TextChoices):
        PRIMARY = 'primaer', 'Primaer'
        SECONDARY = 'sekundaer', 'Sekundaer'

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='exercise_muscles')
    muscle_group = models.ForeignKey(MuscleGroup, on_delete=models.CASCADE, related_name='exercise_muscles')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PRIMARY)

    class Meta:
        unique_together = ('exercise', 'muscle_group')

    def __str__(self):
        return f'{self.exercise} - {self.muscle_group} ({self.role})'


class Workout(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workouts_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class WorkoutExercise(models.Model):
    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name='workout_exercises')
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='workout_exercises')
    order = models.PositiveIntegerField(default=0)
    sets = models.PositiveIntegerField()
    reps = models.CharField(max_length=50)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['workout', 'order']

    def __str__(self):
        return f'{self.workout} - {self.exercise} ({self.order})'
