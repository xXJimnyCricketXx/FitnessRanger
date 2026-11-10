import io
import json
import os
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Equipment, Exercise, MuscleGroup
from plans.models import TrainingPlan
from progress.models import BodyMetricsEntry, Goal, ProgressPhoto

from .backup import (
    BackupError,
    create_backup,
    list_backups,
    prune_backups,
    resolve_backup,
    restore_backup,
    run_due_backup,
    validate_backup,
)
from .models import Profile, SystemSettings, UserData

PASSWORD = 'admin-geheim-123'


class TempFoldersMixin:
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.media = Path(self._tmp.name) / 'media'
        self.backups = Path(self._tmp.name) / 'backups'
        self.media.mkdir()
        override = override_settings(MEDIA_ROOT=str(self.media), BACKUP_DIR=str(self.backups))
        override.enable()
        self.addCleanup(override.disable)


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class PermissionTests(TempFoldersMixin, TestCase):
    def test_normal_user_gets_403_everywhere(self):
        target = User.objects.create_user('ben')
        self.client.force_login(User.objects.create_user('anna'))
        urls = [
            ('post', reverse('system-einstellungen')),
            ('post', reverse('backup-erstellen')),
            ('get', reverse('backup-download', args=['fitnessranger-manual-20260101-000000.zip'])),
            ('post', reverse('backup-loeschen', args=['fitnessranger-manual-20260101-000000.zip'])),
            ('post', reverse('backup-wiederherstellen')),
            ('get', reverse('benutzer-neu')),
            ('get', reverse('benutzer-bearbeiten', args=[target.pk])),
            ('post', reverse('benutzer-loeschen', args=[target.pk])),
            ('post', reverse('danger-daten')),
            ('post', reverse('danger-reset')),
        ]
        for method, url in urls:
            self.assertEqual(getattr(self.client, method)(url).status_code, 403, url)

    def test_anonymous_is_sent_to_login(self):
        self.assertEqual(self.client.post(reverse('backup-erstellen')).status_code, 302)
        self.assertEqual(self.client.post(reverse('danger-reset')).status_code, 302)

    def test_normal_user_sees_no_system_content(self):
        self.client.force_login(User.objects.create_user('anna'))
        page = self.client.get(reverse('einstellungen'))
        self.assertNotContains(page, 'Danger Zone')
        self.assertNotContains(page, 'Vorhandene Backups')

    def test_backups_tab_has_only_personal_backup(self):
        self.client.force_login(User.objects.create_user('anna'))
        page = self.client.get(reverse('einstellungen'))
        self.assertContains(page, reverse('backup-meine-daten'))
        self.assertNotContains(page, 'Gesamte Installation')


class GeneralTabTests(TestCase):
    def test_no_promises_below_the_fields(self):
        self.client.force_login(User.objects.create_user('anna'))
        page = self.client.get(reverse('einstellungen'))
        self.assertNotContains(page, 'Weitere Sprachen')
        self.assertNotContains(page, 'sobald es diese Funktionen')


class BackupFileTests(TempFoldersMixin, TransactionTestCase):
    def test_creates_listed_backup_with_database_and_media(self):
        (self.media / 'avatars').mkdir()
        (self.media / 'avatars' / 'x.png').write_bytes(b'x')
        name = create_backup('manual')
        self.assertEqual([backup['name'] for backup in list_backups()], [name])
        self.assertEqual(list_backups()[0]['kind_label'], 'Manuell')
        with zipfile.ZipFile(self.backups / name) as archive:
            self.assertIn('db.sqlite3', archive.namelist())
            self.assertIn('media/avatars/x.png', archive.namelist())

    def test_no_temporary_file_left_after_failure(self):
        with mock.patch('accounts.backup._write_full_archive', side_effect=OSError('voll')):
            with self.assertRaises(OSError):
                create_backup('manual')
        self.assertEqual([path.name for path in self.backups.iterdir()], [])

    def test_retention_only_touches_that_kind(self):
        for stamp in ('01', '02', '03'):
            (self.backups).mkdir(exist_ok=True)
            path = self.backups / f'fitnessranger-auto-20260101-0000{stamp}.zip'
            path.write_bytes(b'x')
            os.utime(path, (int(stamp) * 1000, int(stamp) * 1000))
        manual = self.backups / 'fitnessranger-manual-20260101-000000.zip'
        manual.write_bytes(b'x')
        prune_backups('auto', 1)
        names = {path.name for path in self.backups.iterdir()}
        self.assertEqual(names, {'fitnessranger-auto-20260101-000003.zip', manual.name})

    def test_foreign_and_malicious_names_are_refused(self):
        self.backups.mkdir()
        (self.backups / 'geheim.txt').write_text('x')
        for name in ('geheim.txt', '../db.sqlite3', 'fitnessranger-manual-1.zip', ''):
            with self.assertRaises(BackupError):
                resolve_backup(name)
        self.assertEqual(list_backups(), [])


class SchedulerTests(TempFoldersMixin, TransactionTestCase):
    def test_first_run_creates_backup_and_records_it(self):
        self.assertTrue(run_due_backup())
        settings_row = SystemSettings.load()
        self.assertIsNotNone(settings_row.last_auto_at)
        self.assertEqual(settings_row.last_auto_error, '')
        self.assertEqual(list_backups()[0]['kind'], 'auto')

    def test_not_due_before_interval_and_due_after(self):
        run_due_backup()
        self.assertFalse(run_due_backup())
        SystemSettings.objects.update(last_auto_attempt_at=timezone.now() - timedelta(hours=25))
        self.assertTrue(run_due_backup())

    def test_disabled_does_nothing(self):
        SystemSettings.objects.update_or_create(pk=1, defaults={'auto_enabled': False})
        self.assertFalse(run_due_backup())
        self.assertFalse(self.backups.exists() and list(self.backups.iterdir()))

    def test_failure_is_recorded_and_retried_after_short_wait(self):
        with mock.patch('accounts.backup.create_backup', side_effect=OSError('Platte voll')):
            self.assertTrue(run_due_backup())
        self.assertIn('Platte voll', SystemSettings.load().last_auto_error)
        self.assertIsNone(SystemSettings.load().last_auto_at)
        self.assertFalse(run_due_backup())
        SystemSettings.objects.update(last_auto_attempt_at=timezone.now() - timedelta(minutes=16))
        self.assertTrue(run_due_backup())
        self.assertEqual(SystemSettings.load().last_auto_error, '')

    def test_retention_applies_to_automatic_backups(self):
        SystemSettings.objects.update_or_create(pk=1, defaults={'keep_count': 2})
        for _ in range(4):
            create_backup('auto')
        self.assertEqual(len(list_backups()), 2)

    def test_no_backup_during_maintenance(self):
        self.backups.mkdir()
        (self.backups / '.maintenance').touch()
        self.assertFalse(run_due_backup())

    def test_stale_maintenance_marker_is_ignored(self):
        self.backups.mkdir()
        marker = self.backups / '.maintenance'
        marker.touch()
        os.utime(marker, (1000, 1000))
        self.assertTrue(run_due_backup())


class UnusableBackupFolderTests(TransactionTestCase):
    def test_page_still_loads_and_create_reports_error(self):
        self.client.force_login(User.objects.create_superuser('chef'))
        with tempfile.NamedTemporaryFile() as blocker, override_settings(BACKUP_DIR=os.path.join(blocker.name, 'x')):
            self.assertEqual(self.client.get(reverse('einstellungen')).status_code, 200)
            response = self.client.post(reverse('backup-erstellen'), follow=True)
            self.assertContains(response, 'konnte nicht erstellt werden')


class ValidationTests(TempFoldersMixin, TransactionTestCase):
    def _write(self, content):
        path = Path(self._tmp.name) / 'upload.zip'
        path.write_bytes(content)
        return path

    def test_rejects_non_zip(self):
        with self.assertRaises(BackupError):
            validate_backup(self._write(b'kein zip'))

    def test_rejects_personal_backup(self):
        content = make_zip({'backup.json': json.dumps({'format': 'fitnessranger-user-backup'})})
        with self.assertRaises(BackupError):
            validate_backup(self._write(content))

    def test_rejects_path_traversal(self):
        User.objects.create_superuser('chef')
        with zipfile.ZipFile(self.backups.parent / 'x.zip', 'w') as archive:
            archive.writestr('manifest.json', json.dumps({'format': 'fitnessranger-full-backup', 'version': 1}))
            archive.writestr('db.sqlite3', b'x')
            archive.writestr('media/../../evil.txt', b'x')
        with self.assertRaises(BackupError) as caught:
            validate_backup(self.backups.parent / 'x.zip')
        self.assertIn('Dateipfade', str(caught.exception))

    def test_rejects_garbage_database(self):
        content = make_zip({
            'manifest.json': json.dumps({'format': 'fitnessranger-full-backup', 'version': 1}),
            'db.sqlite3': b'keine datenbank',
        })
        with self.assertRaises(BackupError):
            validate_backup(self._write(content))

    def test_rejects_newer_format_version(self):
        content = make_zip({
            'manifest.json': json.dumps({'format': 'fitnessranger-full-backup', 'version': 99}),
            'db.sqlite3': b'x',
        })
        with self.assertRaises(BackupError):
            validate_backup(self._write(content))

    def test_rejects_backup_without_active_admin(self):
        User.objects.create_user('anna')
        name = create_backup('manual')
        with self.assertRaises(BackupError) as caught:
            validate_backup(self.backups / name)
        self.assertIn('Administrator', str(caught.exception))

    def test_accepts_real_backup(self):
        User.objects.create_superuser('chef')
        validate_backup(self.backups / create_backup('manual'))


class RestoreTests(TempFoldersMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('chef', password=PASSWORD)
        self.client.force_login(self.admin)

    def _restore_post(self, **extra):
        data = {'confirmation': 'WIEDERHERSTELLEN', 'password': PASSWORD, **extra}
        return self.client.post(reverse('backup-wiederherstellen'), data)

    def test_restores_database_and_media_and_keeps_safety_copy(self):
        Goal.objects.create(user=self.admin, goal_type='halten')
        (self.media / 'alt.png').write_bytes(b'alt')
        name = create_backup('manual')

        Goal.objects.all().delete()
        User.objects.create_user('neu')
        (self.media / 'alt.png').unlink()
        (self.media / 'neu.png').write_bytes(b'neu')

        response = self._restore_post(source=name)
        self.assertRedirects(response, reverse('login-page'), fetch_redirect_response=False)
        self.assertEqual(Goal.objects.filter(goal_type='halten').count(), 1)
        self.assertFalse(User.objects.filter(username='neu').exists())
        self.assertTrue((self.media / 'alt.png').exists())
        self.assertFalse((self.media / 'neu.png').exists())
        self.assertIn('safety', {backup['kind'] for backup in list_backups()})
        self.assertFalse((self.backups / '.maintenance').exists())
        self.assertEqual([path.name for path in Path(self._tmp.name).iterdir() if path.name.startswith('.restore-')], [])

    def test_restore_from_upload(self):
        Goal.objects.create(user=self.admin, goal_type='halten')
        name = create_backup('manual')
        content = (self.backups / name).read_bytes()
        Goal.objects.all().delete()
        upload = SimpleUploadedFile('backup.zip', content, content_type='application/zip')
        self._restore_post(upload=upload)
        self.assertEqual(Goal.objects.count(), 1)
        self.assertEqual([path.name for path in self.backups.iterdir() if path.name.startswith('.upload')], [])

    def test_wrong_confirmation_or_password_changes_nothing(self):
        name = create_backup('manual')
        User.objects.create_user('neu')
        self._restore_post(source=name, confirmation='ja')
        self._restore_post(source=name, password='falsch')
        self.assertTrue(User.objects.filter(username='neu').exists())
        self.assertNotIn('safety', {backup['kind'] for backup in list_backups()})

    def test_invalid_upload_changes_nothing(self):
        User.objects.create_user('neu')
        (self.media / 'bleibt.png').write_bytes(b'x')
        upload = SimpleUploadedFile('backup.zip', b'kein zip')
        response = self._restore_post(upload=upload)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='neu').exists())
        self.assertTrue((self.media / 'bleibt.png').exists())
        self.client.get(reverse('einstellungen'))

    def test_needs_exactly_one_source(self):
        name = create_backup('manual')
        User.objects.create_user('neu')
        self._restore_post()
        self._restore_post(source=name, upload=SimpleUploadedFile('b.zip', b'x'))
        self.assertTrue(User.objects.filter(username='neu').exists())

    def test_failure_rolls_back_media_and_database(self):
        name = create_backup('manual')
        User.objects.create_user('neu')
        (self.media / 'aktuell.png').write_bytes(b'x')
        with mock.patch('accounts.backup.call_command', side_effect=[RuntimeError('kaputt')]):
            with self.assertRaises(BackupError):
                restore_backup(self.backups / name)
        self.assertTrue(User.objects.filter(username='neu').exists())
        self.assertTrue((self.media / 'aktuell.png').exists())
        self.assertFalse((self.backups / '.maintenance').exists())


class BackupActionTests(TempFoldersMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_superuser('chef', password=PASSWORD))

    def test_manual_create_download_delete(self):
        self.client.post(reverse('backup-erstellen'))
        name = list_backups()[0]['name']
        self.assertContains(self.client.get(reverse('einstellungen')), 'Manuell')
        response = self.client.get(reverse('backup-download', args=[name]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        b''.join(response.streaming_content)
        response.close()
        self.client.post(reverse('backup-loeschen', args=[name]))
        self.assertEqual(list_backups(), [])

    def test_download_of_unknown_name_is_404(self):
        name = 'fitnessranger-manual-20260101-000000.zip'
        self.assertEqual(self.client.get(reverse('backup-download', args=[name])).status_code, 404)

    def test_saves_system_settings_and_rejects_invalid(self):
        url = reverse('system-einstellungen')
        self.client.post(url, {'interval_hours': '168', 'keep_count': '3'})
        row = SystemSettings.load()
        self.assertEqual((row.auto_enabled, row.interval_hours, row.keep_count), (False, 168, 3))
        response = self.client.post(url, {'auto_enabled': 'on', 'interval_hours': '168', 'keep_count': '0'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_tab'], 'system')
        self.assertEqual(SystemSettings.load().keep_count, 3)


class UserManagementTests(TempFoldersMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('chef', email='chef@example.com', password=PASSWORD)
        self.client.force_login(self.admin)

    def test_creates_user_with_valid_password(self):
        response = self.client.post(reverse('benutzer-neu'), {
            'username': 'anna', 'email': 'Anna@Example.com', 'password1': 'lang-und-sicher-99',
            'password2': 'lang-und-sicher-99', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='anna')
        self.assertTrue(user.check_password('lang-und-sicher-99'))
        self.assertEqual(user.email, 'anna@example.com')
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_new_user_needs_password_and_validates_it(self):
        base = {'username': 'anna', 'is_active': 'on'}
        self.assertEqual(self.client.post(reverse('benutzer-neu'), base).status_code, 200)
        weak = {**base, 'password1': '123', 'password2': '123'}
        self.assertEqual(self.client.post(reverse('benutzer-neu'), weak).status_code, 200)
        other = {**base, 'password1': 'lang-und-sicher-99', 'password2': 'anders-und-sicher-99'}
        self.assertEqual(self.client.post(reverse('benutzer-neu'), other).status_code, 200)
        self.assertFalse(User.objects.filter(username='anna').exists())

    def test_rejects_duplicate_email(self):
        response = self.client.post(reverse('benutzer-neu'), {
            'username': 'anna', 'email': 'CHEF@example.com', 'password1': 'lang-und-sicher-99',
            'password2': 'lang-und-sicher-99', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'bereits verwendet')

    def test_edit_keeps_password_when_empty_and_syncs_admin_flags(self):
        user = User.objects.create_user('anna', password='lang-und-sicher-99')
        self.client.post(reverse('benutzer-bearbeiten', args=[user.pk]), {
            'username': 'anna', 'is_superuser': 'on', 'is_active': 'on',
        })
        user.refresh_from_db()
        self.assertTrue(user.check_password('lang-und-sicher-99'))
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_edit_can_set_new_password_and_lock_user(self):
        user = User.objects.create_user('anna', password='lang-und-sicher-99')
        self.client.post(reverse('benutzer-bearbeiten', args=[user.pk]), {
            'username': 'anna', 'password1': 'neu-und-sicher-77', 'password2': 'neu-und-sicher-77',
        })
        user.refresh_from_db()
        self.assertTrue(user.check_password('neu-und-sicher-77'))
        self.assertFalse(user.is_active)

    def test_admin_cannot_remove_own_rights(self):
        self.client.post(reverse('benutzer-bearbeiten', args=[self.admin.pk]), {'username': 'chef2'})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.username, 'chef2')
        self.assertTrue(self.admin.is_superuser)
        self.assertTrue(self.admin.is_active)

    def test_changing_own_password_keeps_session(self):
        self.client.post(reverse('benutzer-bearbeiten', args=[self.admin.pk]), {
            'username': 'chef', 'password1': 'neu-und-sicher-77', 'password2': 'neu-und-sicher-77',
        })
        self.assertEqual(self.client.get(reverse('einstellungen')).status_code, 200)

    def test_admin_cannot_delete_self(self):
        self.client.post(reverse('benutzer-loeschen', args=[self.admin.pk]), {'confirmation': 'chef'})
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_delete_needs_exact_username_and_removes_files(self):
        user = User.objects.create_user('anna')
        profile = Profile.objects.create(user=user)
        profile.avatar.save('a.png', SimpleUploadedFile('a.png', b'x'))
        path = profile.avatar.path
        exercise = Exercise.objects.create(name='Bleibt', instructions='x', created_by=user)

        self.client.post(reverse('benutzer-loeschen', args=[user.pk]), {'confirmation': 'falsch'})
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

        self.client.post(reverse('benutzer-loeschen', args=[user.pk]), {'confirmation': 'anna'})
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(os.path.exists(path))
        exercise.refresh_from_db()
        self.assertIsNone(exercise.created_by)

    def test_rejected_edit_page_shows_saved_username(self):
        user = User.objects.create_user('anna')
        User.objects.create_user('ben')
        response = self.client.post(reverse('benutzer-bearbeiten', args=[user.pk]), {'username': 'ben'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['target'].username, 'anna')


class DangerZoneTests(TempFoldersMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('chef', password=PASSWORD)
        self.user = User.objects.create_user('anna')
        self.client.force_login(self.admin)
        Goal.objects.create(user=self.user, goal_type='halten')
        UserData.objects.create(user=self.user, height_cm=170)
        TrainingPlan.objects.create(user=self.user, name='Plan')
        self.entry = BodyMetricsEntry.objects.create(user=self.user, date=timezone.localdate())
        self.photo = ProgressPhoto(user=self.user, date=timezone.localdate(), pose='vorne')
        self.photo.image.save('f.jpg', SimpleUploadedFile('f.jpg', b'x'))
        self.exercise = Exercise.objects.create(name='Bankdruecken', instructions='x', created_by=self.user)

    def _post(self, name, word):
        return self.client.post(reverse(name), {'confirmation': word, 'password': PASSWORD})

    def test_wrong_input_changes_nothing(self):
        self._post('danger-daten', 'loeschen')
        self.client.post(reverse('danger-reset'), {'confirmation': 'ZURÜCKSETZEN', 'password': 'falsch'})
        self.assertEqual(Goal.objects.count(), 1)
        self.assertTrue(User.objects.filter(username='anna').exists())
        self.assertEqual(list_backups(), [])

    def test_delete_data_keeps_accounts_and_library(self):
        photo = self.photo.image.path
        self._post('danger-daten', 'LÖSCHEN')
        self.assertEqual(Goal.objects.count(), 0)
        self.assertEqual(UserData.objects.count(), 0)
        self.assertEqual(TrainingPlan.objects.count(), 0)
        self.assertEqual(BodyMetricsEntry.objects.count(), 0)
        self.assertEqual(ProgressPhoto.objects.count(), 0)
        self.assertFalse(os.path.exists(photo))
        self.assertTrue(User.objects.filter(username='anna').exists())
        self.assertTrue(Exercise.objects.filter(pk=self.exercise.pk).exists())
        self.assertEqual(list_backups()[0]['kind'], 'safety')

    def test_reset_leaves_only_admin_and_seed_data(self):
        Equipment.objects.create(name='Eigenes Gerät', category='zubehoer')
        self._post('danger-reset', 'ZURÜCKSETZEN')
        self.assertEqual(list(User.objects.values_list('username', flat=True)), ['chef'])
        self.assertEqual(Exercise.objects.count(), 0)
        self.assertEqual(Goal.objects.count(), 0)
        self.assertFalse(Equipment.objects.filter(name='Eigenes Gerät').exists())
        self.assertEqual(MuscleGroup.objects.count(), 50)
        self.assertEqual(Equipment.objects.count(), 21)
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertEqual(list_backups()[0]['kind'], 'safety')
        self.assertEqual(self.client.get(reverse('einstellungen')).status_code, 200)

    def test_nothing_is_deleted_if_safety_copy_fails(self):
        with mock.patch('accounts.system_views.create_backup', side_effect=OSError('voll')):
            self._post('danger-reset', 'ZURÜCKSETZEN')
            self._post('danger-daten', 'LÖSCHEN')
        self.assertTrue(User.objects.filter(username='anna').exists())
        self.assertEqual(Goal.objects.count(), 1)


class AdminLinkTests(TestCase):
    def test_admin_link_opens_in_new_tab_for_staff_only(self):
        link = f'<a href="{reverse("admin:index")}" class="user-menu-item" target="_blank"'
        self.client.force_login(User.objects.create_user('anna'))
        self.assertNotContains(self.client.get(reverse('profil')), reverse('admin:index'))
        self.client.force_login(User.objects.create_superuser('chef'))
        self.assertContains(self.client.get(reverse('profil')), link)
