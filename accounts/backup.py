import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.models import Q
from django.utils import timezone

from catalog.models import Equipment, Exercise, ExerciseMuscle, MuscleGroup, TrainingGoal, Workout, WorkoutExercise
from plans.models import TrainingPlan, TrainingPlanEntry, UserEquipment
from progress.models import BodyMetricsEntry, Goal, ProgressPhoto
from tracking.models import TrackingEntry

from .models import Profile, SystemSettings, UserData, UserSettings

logger = logging.getLogger(__name__)

BACKUP_VERSION = 1
FULL_FORMAT = 'fitnessranger-full-backup'
BACKUP_KINDS = {'auto': 'Automatisch', 'manual': 'Manuell', 'safety': 'Sicherheitskopie'}
BACKUP_NAME_RE = re.compile(r'^fitnessranger-(auto|manual|safety)-\d{8}-\d{6}(-\d+)?\.zip$')
SAFETY_KEEP = 5
RETRY_AFTER_ERROR = timedelta(minutes=15)
MAINTENANCE_MAX_AGE = 3600
# Deliberately excludes the password hash and permissions.
USER_FIELDS = ('username', 'email', 'first_name', 'last_name', 'date_joined')


class BackupError(Exception):
    pass


def _dump(queryset, fields=None):
    return json.loads(serializers.serialize('json', queryset, fields=fields))


def _add_media(archive, file_field):
    if file_field and os.path.exists(file_field.path):
        archive.write(file_field.path, f'media/{file_field.name}')


def _manifest(format_name, **extra):
    return {
        'format': format_name,
        'version': BACKUP_VERSION,
        'created_at': timezone.now().isoformat(),
        **extra,
    }


def build_user_backup(user):
    """Returns a temporary ZIP file with everything that belongs to this user.

    Shared library entries are included if the user created them or their plans and
    tracking refer to them, because the personal data would be incomplete without them.
    """
    workouts = Workout.objects.filter(
        Q(created_by=user)
        | Q(plan_entries__plan__user=user)
        | Q(workout_exercises__tracking_entries__user=user)
    ).distinct()
    workout_exercises = WorkoutExercise.objects.filter(workout__in=workouts)
    exercises = Exercise.objects.filter(
        Q(created_by=user)
        | Q(tracking_entries__user=user)
        | Q(workout_exercises__workout__in=workouts)
    ).distinct()
    exercise_muscles = ExerciseMuscle.objects.filter(exercise__in=exercises)
    equipment = Equipment.objects.filter(
        Q(created_by=user)
        | Q(user_equipment__user=user)
        | Q(exercises__in=exercises)
    ).distinct()
    profiles = Profile.objects.filter(user=user)
    body_metrics = BodyMetricsEntry.objects.filter(user=user)
    progress_photos = ProgressPhoto.objects.filter(user=user)

    data = {
        'user': _dump(get_user_model().objects.filter(pk=user.pk), fields=USER_FIELDS),
        'profile': _dump(profiles),
        'settings': _dump(UserSettings.objects.filter(user=user)),
        'user_data': _dump(UserData.objects.filter(user=user)),
        'goals': _dump(Goal.objects.filter(user=user)),
        'user_equipment': _dump(UserEquipment.objects.filter(user=user)),
        'training_plans': _dump(TrainingPlan.objects.filter(user=user)),
        'training_plan_entries': _dump(TrainingPlanEntry.objects.filter(plan__user=user)),
        'tracking_entries': _dump(TrackingEntry.objects.filter(user=user)),
        'body_metrics': _dump(body_metrics),
        'progress_photos': _dump(progress_photos),
        'exercises': _dump(exercises),
        'exercise_muscles': _dump(exercise_muscles),
        'workouts': _dump(workouts),
        'workout_exercises': _dump(workout_exercises),
        'equipment': _dump(equipment),
        'muscle_groups': _dump(MuscleGroup.objects.filter(exercise_muscles__in=exercise_muscles).distinct()),
        'training_goals': _dump(TrainingGoal.objects.filter(exercises__in=exercises).distinct()),
    }

    output = tempfile.TemporaryFile()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        manifest = _manifest('fitnessranger-user-backup', data=data)
        archive.writestr('backup.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        for profile in profiles:
            _add_media(archive, profile.avatar)
        for photo in progress_photos:
            _add_media(archive, photo.image)
        for exercise in exercises:
            _add_media(archive, exercise.image)
    output.seek(0)
    return output


def backup_dir():
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_full_archive(target):
    with tempfile.TemporaryDirectory() as workdir, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        snapshot_path = os.path.join(workdir, 'db.sqlite3')
        # Unlike sqlite3's backup(), this fails instead of waiting forever if the database is busy.
        with connection.cursor() as cursor:
            cursor.execute('VACUUM INTO %s', [snapshot_path])

        archive.writestr('manifest.json', json.dumps(_manifest(FULL_FORMAT), indent=2))
        archive.write(snapshot_path, 'db.sqlite3')
        media_root = str(settings.MEDIA_ROOT)
        for folder, _, files in os.walk(media_root):
            for name in files:
                path = os.path.join(folder, name)
                relative = os.path.relpath(path, media_root).replace(os.sep, '/')
                archive.write(path, f'media/{relative}')


def create_backup(kind):
    """Writes a full backup into the backup folder and returns its file name."""
    if kind not in BACKUP_KINDS:
        raise ValueError(kind)
    directory = backup_dir()
    stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
    name = f'fitnessranger-{kind}-{stamp}.zip'
    counter = 1
    while (directory / name).exists():
        name = f'fitnessranger-{kind}-{stamp}-{counter}.zip'
        counter += 1

    # Written under a temporary name, so an interrupted backup never appears in the list.
    temporary = directory / f'{name}.tmp'
    try:
        _write_full_archive(temporary)
        os.replace(temporary, directory / name)
    finally:
        temporary.unlink(missing_ok=True)

    if kind == 'auto':
        prune_backups('auto', SystemSettings.load().keep_count)
    elif kind == 'safety':
        prune_backups('safety', SAFETY_KEEP)
    return name


def list_backups():
    backups = []
    try:
        paths = list(backup_dir().iterdir())
    except OSError:
        # An unusable folder must not take the whole settings page down with it.
        logger.exception('Backup folder is not available')
        return []
    for path in paths:
        match = BACKUP_NAME_RE.match(path.name)
        if not match or not path.is_file():
            continue
        stat = path.stat()
        backups.append({
            'name': path.name,
            'kind': match.group(1),
            'kind_label': BACKUP_KINDS[match.group(1)],
            'created_at': datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
            'size': stat.st_size,
        })
    return sorted(backups, key=lambda backup: (backup['created_at'], backup['name']), reverse=True)


def prune_backups(kind, keep):
    matching = [backup for backup in list_backups() if backup['kind'] == kind]
    for backup in matching[keep:]:
        (backup_dir() / backup['name']).unlink(missing_ok=True)


def resolve_backup(name):
    # Only names we generate ourselves, so the parameter can't reach files outside the folder.
    if not BACKUP_NAME_RE.match(name or ''):
        raise BackupError('Dieses Backup gibt es nicht.')
    path = backup_dir() / name
    if not path.is_file():
        raise BackupError('Dieses Backup gibt es nicht.')
    return path


def delete_backup(name):
    resolve_backup(name).unlink()


def _is_safe_member(name):
    if name in ('manifest.json', 'db.sqlite3'):
        return True
    if not name.startswith('media/') or name.endswith('/') or '\\' in name:
        return False
    return '..' not in name.split('/') and not os.path.isabs(name)


def validate_backup(path):
    """Checks a full backup completely before anything gets replaced."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if 'manifest.json' not in names or 'db.sqlite3' not in names:
                raise BackupError('Das ist kein Komplett-Backup von FitnessRanger.')
            if not all(_is_safe_member(name) for name in names):
                raise BackupError('Das Backup enthält ungültige Dateipfade.')
            if archive.testzip() is not None:
                raise BackupError('Das Backup ist beschädigt.')
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('format') != FULL_FORMAT:
                raise BackupError('Das ist kein Komplett-Backup von FitnessRanger.')
            if manifest.get('version', 0) > BACKUP_VERSION:
                raise BackupError('Das Backup stammt aus einer neueren Version der App.')
            with tempfile.TemporaryDirectory() as workdir:
                archive.extract('db.sqlite3', workdir)
                _validate_database(os.path.join(workdir, 'db.sqlite3'))
    except (zipfile.BadZipFile, json.JSONDecodeError, AttributeError) as error:
        raise BackupError('Das ist kein gültiges Backup.') from error


def _validate_database(path):
    database = sqlite3.connect(path)
    try:
        if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise BackupError('Die Datenbank im Backup ist beschädigt.')
        applied = set(database.execute('SELECT app, name FROM django_migrations').fetchall())
        admins = database.execute(
            'SELECT COUNT(*) FROM auth_user WHERE is_superuser = 1 AND is_active = 1'
        ).fetchone()[0]
    except sqlite3.DatabaseError as error:
        raise BackupError('Die Datenbank im Backup ist nicht lesbar.') from error
    finally:
        database.close()

    if not applied <= set(MigrationLoader(None).disk_migrations):
        raise BackupError('Das Backup stammt aus einer neueren Version der App.')
    if not admins:
        raise BackupError('Das Backup enthält keinen aktiven Administrator. Danach könnte sich niemand mehr anmelden.')


def _copy_database(source):
    name = str(connection.settings_dict['NAME'])
    connection.close()
    source_db = sqlite3.connect(source)
    target_db = sqlite3.connect(name, uri=name.startswith('file:'))
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()
    connection.close()


def _maintenance_file():
    return backup_dir() / '.maintenance'


def maintenance_active():
    try:
        return time.time() - _maintenance_file().stat().st_mtime < MAINTENANCE_MAX_AGE
    except FileNotFoundError:
        return False


@contextmanager
def maintenance():
    """Keeps the scheduler from starting a backup while data is being replaced."""
    marker = _maintenance_file()
    marker.touch()
    try:
        yield
    finally:
        marker.unlink(missing_ok=True)


def restore_backup(path):
    """Replaces the database and uploads. Returns the name of the safety copy made first."""
    validate_backup(path)
    media_root = Path(settings.MEDIA_ROOT)
    media_root.parent.mkdir(parents=True, exist_ok=True)

    with maintenance():
        # Next to the media folder, so the folders can be swapped by renaming them.
        staging = Path(tempfile.mkdtemp(dir=media_root.parent, prefix='.restore-'))
        try:
            new_media = staging / 'unpacked' / 'media'
            with zipfile.ZipFile(path) as archive:
                archive.extractall(staging / 'unpacked')
            new_media.mkdir(parents=True, exist_ok=True)

            safety_name = create_backup('safety')

            old_media = staging / 'old-media'
            if media_root.exists():
                os.rename(media_root, old_media)
            os.rename(new_media, media_root)
            try:
                _copy_database(staging / 'unpacked' / 'db.sqlite3')
                call_command('migrate', verbosity=0, interactive=False)
            except Exception as error:
                logger.exception('Restore failed, rolling back')
                shutil.rmtree(media_root, ignore_errors=True)
                if old_media.exists():
                    os.rename(old_media, media_root)
                with zipfile.ZipFile(backup_dir() / safety_name) as archive:
                    archive.extract('db.sqlite3', staging / 'rollback')
                _copy_database(staging / 'rollback' / 'db.sqlite3')
                raise BackupError('Die Wiederherstellung ist fehlgeschlagen. Der vorherige Stand ist wieder aktiv.') from error
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return safety_name


def run_due_backup():
    """Creates an automatic backup if one is due. Returns True if a backup was attempted."""
    if maintenance_active():
        return False
    system_settings = SystemSettings.load()
    if not system_settings.auto_enabled:
        return False

    now = timezone.now()
    last_attempt = system_settings.last_auto_attempt_at
    wait = RETRY_AFTER_ERROR if system_settings.last_auto_error else timedelta(hours=system_settings.interval_hours)
    if last_attempt and now - last_attempt < wait:
        return False

    updates = {'last_auto_attempt_at': now}
    try:
        create_backup('auto')
    except Exception as error:
        logger.exception('Automatic backup failed')
        updates['last_auto_error'] = str(error)[:500]
    else:
        updates['last_auto_at'] = now
        updates['last_auto_error'] = ''
    # Only these fields, so changes saved in the settings meanwhile aren't overwritten.
    SystemSettings.objects.filter(pk=system_settings.pk).update(**updates)
    return True
