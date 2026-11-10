from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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
    display_name = models.CharField('Anzeigename', max_length=50, blank=True)

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


class UserSettings(models.Model):
    class Language(models.TextChoices):
        GERMAN = 'de', 'Deutsch'

    class WeightUnit(models.TextChoices):
        KG = 'kg', 'Kilogramm (kg)'
        LB = 'lb', 'Pfund (lb)'

    class LengthUnit(models.TextChoices):
        CM = 'cm', 'Zentimeter (cm)'
        FT_IN = 'ft_in', 'Fuß und Zoll (ft/in)'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='settings')
    language = models.CharField('Sprache', max_length=10, choices=Language.choices, default=Language.GERMAN)
    weight_unit = models.CharField('Gewicht', max_length=5, choices=WeightUnit.choices, default=WeightUnit.KG)
    length_unit = models.CharField('Größe und Maße', max_length=5, choices=LengthUnit.choices, default=LengthUnit.CM)

    class Meta:
        verbose_name_plural = 'User settings'

    def __str__(self):
        return f'Einstellungen von {self.user}'


class SystemSettings(models.Model):
    """Settings for the whole installation. There is always exactly one row."""

    class Interval(models.IntegerChoices):
        HOURS_6 = 6, 'Alle 6 Stunden'
        HOURS_12 = 12, 'Alle 12 Stunden'
        DAILY = 24, 'Täglich'
        WEEKLY = 168, 'Wöchentlich'

    auto_enabled = models.BooleanField('Automatische Backups', default=True)
    interval_hours = models.PositiveIntegerField('Intervall', choices=Interval.choices, default=Interval.DAILY)
    keep_count = models.PositiveIntegerField(
        'Aufbewahren', default=7, validators=[MinValueValidator(1), MaxValueValidator(365)],
    )
    last_auto_at = models.DateTimeField(null=True, blank=True)
    last_auto_attempt_at = models.DateTimeField(null=True, blank=True)
    last_auto_error = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'System settings'

    def __str__(self):
        return 'Systemeinstellungen'

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]


def display_name_for(user):
    """The name shown to others: the display name if set, otherwise the username."""
    try:
        return user.profile.display_name or user.username
    except Profile.DoesNotExist:
        return user.username
