import uuid

from django.conf import settings
from django.db import models

# Everything below this folder is never served by the public media URL.
PRIVATE_MEDIA_PREFIX = 'private/'


class BodyMetricsEntry(models.Model):
    class Source(models.TextChoices):
        MANUAL = 'manuell', 'Manuell'
        RENPHO_CSV = 'renpho_csv', 'RENPHO CSV'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='body_metrics')
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bmi = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    body_fat_pct = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    skeletal_muscle_pct = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    fat_free_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    subcutaneous_fat_pct = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    visceral_fat = models.PositiveIntegerField(null=True, blank=True)
    water_pct = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    muscle_mass_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bone_mass_kg = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    protein_pct = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    bmr_kcal = models.PositiveIntegerField(null=True, blank=True)
    metabolic_age = models.PositiveIntegerField(null=True, blank=True)
    neck_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    shoulders_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    chest_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    upper_arm_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    forearm_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    waist_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    hip_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    thigh_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    calf_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = ('user', 'date')
        verbose_name_plural = 'Body metrics entries'

    def __str__(self):
        return f'{self.user} - {self.date}'


class Goal(models.Model):
    class GoalType(models.TextChoices):
        LOSE_WEIGHT = 'abnehmen', 'Abnehmen'
        BUILD_MUSCLE = 'muskelaufbau', 'Muskelaufbau'
        BUILD_STRENGTH = 'kraft_aufbauen', 'Kraft aufbauen'
        MAINTAIN = 'halten', 'Halten'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='goals')
    target_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    target_muscle_mass_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_tolerance_kg = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    goal_type = models.CharField(max_length=20, choices=GoalType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.get_goal_type_display()}'


def progress_photo_path(instance, filename):
    """Random names, so nobody can guess the address of someone else's photo."""
    return f'{PRIVATE_MEDIA_PREFIX}progress_photos/{instance.user_id}/{uuid.uuid4().hex}.jpg'


class ProgressPhoto(models.Model):
    class Pose(models.TextChoices):
        FRONT = 'vorne', 'Vorne'
        SIDE = 'seite', 'Seite'
        BACK = 'hinten', 'Hinten'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='progress_photos')
    date = models.DateField()
    pose = models.CharField(max_length=10, choices=Pose.choices)
    image = models.ImageField(upload_to=progress_photo_path)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'pose']
        unique_together = ('user', 'date', 'pose')

    def __str__(self):
        return f'{self.user} - {self.date} - {self.get_pose_display()}'
