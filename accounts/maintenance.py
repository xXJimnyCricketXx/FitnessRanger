import os
import shutil

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import transaction

from catalog.models import Equipment, Exercise, MuscleGroup, TrainingGoal, Workout
from plans.models import TrainingPlan, UserEquipment
from progress.models import BodyMetricsEntry, Goal, ProgressPhoto
from progress.photos import delete_photo_files
from tracking.models import TrackingEntry

from .models import Profile, UserData, UserSettings


def delete_user_with_files(user):
    """Cascading deletes keep files on disk, so the user's own uploads go first."""
    profile = Profile.objects.filter(user=user).first()
    if profile and profile.avatar:
        profile.avatar.delete(save=False)
    delete_photo_files(ProgressPhoto.objects.filter(user=user))
    user.delete()


def delete_training_data():
    """Removes everyone's plans and progress. Accounts and the shared library stay."""
    delete_photo_files(ProgressPhoto.objects.all())
    with transaction.atomic():
        TrackingEntry.objects.all().delete()
        TrainingPlan.objects.all().delete()
        BodyMetricsEntry.objects.all().delete()
        ProgressPhoto.objects.all().delete()
        Goal.objects.all().delete()
        UserData.objects.all().delete()
        UserEquipment.objects.all().delete()


def reset_installation(keep_user, keep_session_key):
    """Back to a fresh install: only this admin account and the seeded reference data remain."""
    with transaction.atomic():
        get_user_model().objects.exclude(pk=keep_user.pk).delete()
        TrackingEntry.objects.all().delete()
        TrainingPlan.objects.all().delete()
        BodyMetricsEntry.objects.all().delete()
        ProgressPhoto.objects.all().delete()
        Goal.objects.all().delete()
        UserData.objects.all().delete()
        UserEquipment.objects.all().delete()
        Profile.objects.all().delete()
        UserSettings.objects.all().delete()
        Workout.objects.all().delete()
        Exercise.objects.all().delete()
        Equipment.objects.all().delete()
        TrainingGoal.objects.all().delete()
        MuscleGroup.objects.all().delete()
        Session.objects.exclude(session_key=keep_session_key).delete()
        call_command('loaddata', 'seed_catalog', verbosity=0)

    media_root = str(settings.MEDIA_ROOT)
    if os.path.isdir(media_root):
        for entry in os.scandir(media_root):
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                os.unlink(entry.path)
