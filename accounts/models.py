from django.conf import settings
from django.db import models


class UserData(models.Model):
    class Gender(models.TextChoices):
        MALE = 'maennlich', 'Männlich'
        FEMALE = 'weiblich', 'Weiblich'

    class FitnessLevel(models.TextChoices):
        BEGINNER = 'anfaenger', 'Anfänger'
        ADVANCED = 'fortgeschritten', 'Fortgeschritten'
        PRO = 'profi', 'Profi'

    class ActivityLevel(models.TextChoices):
        SEDENTARY = 'nicht_aktiv', 'Nicht aktiv (kaum bis keine Bewegung, sitzende Tätigkeit)'
        LIGHT = 'leicht_aktiv', 'Leicht aktiv (1-3 Tage pro Woche Sport)'
        MODERATE = 'maessig_aktiv', 'Mäßig aktiv (3-5 Tage pro Woche Sport)'
        ACTIVE = 'sehr_aktiv', 'Sehr aktiv (6-7 Tage pro Woche Sport)'
        EXTREME = 'extrem_aktiv', 'Extrem aktiv (zwei Trainingseinheiten pro Tag)'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_data')
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    height_cm = models.PositiveIntegerField(null=True, blank=True)
    starting_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fitness_level = models.CharField(max_length=20, choices=FitnessLevel.choices, blank=True)
    activity_level = models.CharField(max_length=20, choices=ActivityLevel.choices, blank=True)

    class Meta:
        verbose_name_plural = 'User data'

    def __str__(self):
        return f'Meine Daten von {self.user}'


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/%Y/%m/', null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = Profile.objects.get(pk=self.pk)
            except Profile.DoesNotExist:
                old = None
            new_name = self.avatar.name if self.avatar else None
            if old and old.avatar and old.avatar.name != new_name:
                old.avatar.delete(save=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Profil von {self.user}'
