import io
import json
import os
import tempfile
import zipfile
from decimal import Decimal

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalog.models import Equipment, Exercise
from plans.models import UserEquipment
from progress.models import Goal

from .models import Profile, UserData, UserSettings, display_name_for


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', email='anna@example.com', password='geheim-12345')
        User.objects.create_user('ohnemail', password='geheim-12345')

    def test_login_with_username(self):
        self.assertEqual(authenticate(username='anna', password='geheim-12345'), self.user)

    def test_login_with_email_ignores_case(self):
        self.assertEqual(authenticate(username='ANNA@example.com', password='geheim-12345'), self.user)

    def test_wrong_password_fails(self):
        self.assertIsNone(authenticate(username='anna@example.com', password='falsch'))

    def test_empty_login_never_matches_accounts_without_email(self):
        self.assertIsNone(authenticate(username='', password='geheim-12345'))


class DisplayNameTests(TestCase):
    def test_falls_back_to_username(self):
        user = User.objects.create_user('anna')
        self.assertEqual(display_name_for(user), 'anna')

    def test_blank_display_name_falls_back_to_username(self):
        user = User.objects.create_user('anna')
        Profile.objects.create(user=user)
        self.assertEqual(display_name_for(user), 'anna')

    def test_uses_display_name(self):
        user = User.objects.create_user('anna')
        Profile.objects.create(user=user, display_name='Anna K.')
        self.assertEqual(display_name_for(user), 'Anna K.')


class ProfilePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', password='geheim-12345')
        User.objects.create_user('ben', email='ben@example.com')
        self.client.force_login(self.user)
        self.url = reverse('profil')

    def test_saves_account_fields(self):
        response = self.client.post(self.url, {'username': 'anna2', 'display_name': 'Anna K.', 'email': 'Anna@Example.com'})
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'anna2')
        self.assertEqual(self.user.email, 'anna@example.com')
        self.assertEqual(self.user.profile.display_name, 'Anna K.')

    def test_rejects_email_of_another_user(self):
        response = self.client.post(self.url, {'username': 'anna', 'email': 'BEN@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'bereits verwendet')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_several_accounts_may_have_no_email(self):
        User.objects.create_user('clara')
        response = self.client.post(self.url, {'username': 'anna', 'email': ''})
        self.assertRedirects(response, self.url)

    def test_rejected_username_is_not_shown_in_header(self):
        response = self.client.post(self.url, {'username': 'ben', 'email': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['display_name'], 'anna')

    def test_password_fields_are_not_required_in_the_browser(self):
        form = self.client.get(self.url).context['password_form']
        for field in ('old_password', 'new_password1', 'new_password2'):
            self.assertNotIn('required', str(form[field]))

    def test_autofilled_current_password_alone_is_ignored(self):
        response = self.client.post(self.url, {'username': 'anna', 'email': '', 'old_password': 'geheim-12345'})
        self.assertRedirects(response, self.url)

    def test_new_password_without_current_password_is_rejected(self):
        response = self.client.post(self.url, {
            'username': 'anna',
            'email': '',
            'new_password1': 'neu-geheim-67890',
            'new_password2': 'neu-geheim-67890',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('geheim-12345'))

    def _upload(self, name='avatar.png'):
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buffer, 'PNG')
        return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')

    def test_avatar_can_be_removed_and_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self.client.post(self.url, {'username': 'anna', 'email': '', 'avatar': self._upload()})
            path = Profile.objects.get(user=self.user).avatar.path
            self.assertTrue(os.path.exists(path))

            page = self.client.get(self.url)
            self.assertContains(page, 'Avatar entfernen')
            self.assertNotContains(page, 'Derzeit')

            response = self.client.post(self.url, {'username': 'anna', 'email': '', 'remove_avatar': 'on'})
            self.assertRedirects(response, self.url)
            self.assertFalse(Profile.objects.get(user=self.user).avatar)
            self.assertFalse(os.path.exists(path))

    def test_avatar_stays_when_saving_without_a_new_file(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self.client.post(self.url, {'username': 'anna', 'email': '', 'avatar': self._upload()})
            self.client.post(self.url, {'username': 'anna', 'email': ''})
            self.assertTrue(Profile.objects.get(user=self.user).avatar)

    def test_new_image_wins_over_remove_checkbox(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self.client.post(self.url, {'username': 'anna', 'email': '', 'remove_avatar': 'on', 'avatar': self._upload()})
            self.assertTrue(Profile.objects.get(user=self.user).avatar)

    def test_no_remove_option_without_avatar(self):
        self.assertNotContains(self.client.get(self.url), 'Avatar entfernen')

    def test_avatar_upload_without_password_fields(self):
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buffer, 'PNG')
        upload = SimpleUploadedFile('avatar.png', buffer.getvalue(), content_type='image/png')
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            response = self.client.post(self.url, {'username': 'anna', 'email': '', 'avatar': upload})
            self.assertRedirects(response, self.url)
            self.user.refresh_from_db()
            self.assertTrue(self.user.profile.avatar)
            self.user.profile.avatar.close()

    def test_changing_username_and_password_together_keeps_both(self):
        response = self.client.post(self.url, {
            'username': 'anna2',
            'email': '',
            'old_password': 'geheim-12345',
            'new_password1': 'neu-geheim-67890',
            'new_password2': 'neu-geheim-67890',
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'anna2')
        self.assertTrue(self.user.check_password('neu-geheim-67890'))
        # The session survives the password change.
        self.assertEqual(self.client.get(self.url).status_code, 200)


class MeineDatenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna')
        self.client.force_login(self.user)
        self.url = reverse('meine-daten')

    def test_personal_data_saves_without_goal(self):
        response = self.client.post(self.url, {'section': 'personal', 'userdata-height_cm': '180'})
        self.assertRedirects(response, f'{self.url}?tab=personal')
        self.assertEqual(UserData.objects.get(user=self.user).height_cm, 180)
        self.assertFalse(Goal.objects.filter(user=self.user).exists())

    def test_goal_saves_on_its_own(self):
        UserData.objects.create(user=self.user, height_cm=180)
        response = self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'halten'})
        self.assertRedirects(response, f'{self.url}?tab=goal')
        self.assertEqual(Goal.objects.get(user=self.user).goal_type, 'halten')
        self.assertEqual(UserData.objects.get(user=self.user).height_cm, 180)

    def test_goal_without_type_shows_error_on_goal_tab(self):
        response = self.client.post(self.url, {'section': 'goal'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_tab'], 'goal')
        self.assertTrue(response.context['goal_form'].errors)
        self.assertFalse(response.context['user_data_form'].errors)

    def test_goal_fields_per_type(self):
        self.client.post(self.url, {
            'section': 'goal', 'goal-goal_type': 'muskelaufbau', 'goal-target_muscle_mass_kg': '75',
            'goal-target_weight_kg': '90',
        })
        goal = Goal.objects.get(user=self.user)
        self.assertEqual((goal.target_muscle_mass_kg, goal.target_weight_kg), (Decimal('75.00'), Decimal('90.00')))
        self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'halten', 'goal-target_weight_kg': '90',
                                    'goal-weight_tolerance_kg': '1.5'})
        self.assertEqual(Goal.objects.get(user=self.user).weight_tolerance_kg, Decimal('1.5'))
        response = self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'halten', 'goal-weight_tolerance_kg': '50'})
        self.assertContains(response, 'nicht plausibel')

    def use_imperial(self):
        UserSettings.objects.update_or_create(user=self.user, defaults={
            'weight_unit': UserSettings.WeightUnit.LB, 'length_unit': UserSettings.LengthUnit.FT_IN,
        })

    def test_goal_in_pounds(self):
        self.use_imperial()
        self.client.post(self.url, {
            'section': 'goal', 'goal-goal_type': 'muskelaufbau', 'goal-target_muscle_mass_kg': '165',
            'goal-target_weight_kg': '176.37',
        })
        goal = Goal.objects.get(user=self.user)
        self.assertEqual((goal.target_muscle_mass_kg, goal.target_weight_kg), (Decimal('74.84'), Decimal('80.00')))
        self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'halten', 'goal-target_weight_kg': '176.37',
                                    'goal-weight_tolerance_kg': '2.2'})
        self.assertEqual(Goal.objects.get(user=self.user).weight_tolerance_kg, Decimal('1.0'))
        page = self.client.get(self.url)
        self.assertContains(page, 'Wunschgewicht (lb)')
        self.assertContains(page, 'Spielraum (± lb, Standard 2,2)')
        self.assertEqual(page.context['goal_form'].initial['target_weight_kg'], Decimal('176.37'))
        # 400 kg is the upper limit, 900 lb is above it
        response = self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'abnehmen', 'goal-target_weight_kg': '900'})
        self.assertContains(response, 'nicht plausibel')

    def test_personal_data_in_pounds_and_inches(self):
        self.use_imperial()
        self.client.post(self.url, {'section': 'personal', 'userdata-height_cm': '68.9', 'userdata-starting_weight_kg': '286.6'})
        data = UserData.objects.get(user=self.user)
        self.assertEqual((data.height_cm, data.starting_weight_kg), (175, Decimal('130.00')))
        page = self.client.get(self.url)
        self.assertContains(page, 'Größe (in)')
        self.assertContains(page, 'Ausgangsgewicht (lb)')
        form = page.context['user_data_form']
        self.assertEqual((form.initial['height_cm'], form.initial['starting_weight_kg']), (Decimal('68.9'), Decimal('286.60')))
        # Saving the shown values again keeps what is stored.
        self.client.post(self.url, {'section': 'personal', 'userdata-height_cm': '68.9', 'userdata-starting_weight_kg': '286.60'})
        data.refresh_from_db()
        self.assertEqual((data.height_cm, data.starting_weight_kg), (175, Decimal('130.00')))

    def test_saving_goal_twice_updates_the_same_goal(self):
        self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'halten'})
        self.client.post(self.url, {'section': 'goal', 'goal-goal_type': 'abnehmen'})
        self.assertEqual(Goal.objects.get(user=self.user).goal_type, 'abnehmen')

    def test_saving_another_tab_keeps_equipment(self):
        equipment = Equipment.objects.create(name='Hantel', category=Equipment.Category.choices[0][0])
        self.client.post(self.url, {'section': 'equipment', 'equipment-equipment': [equipment.pk]})
        self.client.post(self.url, {'section': 'personal', 'userdata-height_cm': '180'})
        saved = UserEquipment.objects.get(user=self.user).equipment.all()
        self.assertEqual(list(saved), [equipment])
        page = self.client.get(self.url)
        self.assertIn(str(equipment.pk), page.context['selected_equipment_ids'])

    def test_unknown_tab_falls_back_to_personal(self):
        self.assertEqual(self.client.get(self.url, {'tab': 'gibtsnicht'}).context['initial_tab'], 'personal')

    def test_unknown_section_saves_nothing(self):
        response = self.client.post(self.url, {'section': 'gibtsnicht', 'userdata-height_cm': '180'})
        self.assertRedirects(response, self.url)
        self.assertFalse(UserData.objects.filter(user=self.user, height_cm=180).exists())


class SettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna')
        self.client.force_login(self.user)
        self.url = reverse('einstellungen')

    def test_defaults(self):
        self.client.get(self.url)
        saved = UserSettings.objects.get(user=self.user)
        self.assertEqual((saved.language, saved.weight_unit, saved.length_unit), ('de', 'kg', 'cm'))

    def test_saves_units(self):
        response = self.client.post(self.url, {'language': 'de', 'weight_unit': 'lb', 'length_unit': 'ft_in'})
        self.assertRedirects(response, self.url)
        saved = UserSettings.objects.get(user=self.user)
        self.assertEqual((saved.weight_unit, saved.length_unit), ('lb', 'ft_in'))

    def test_rejects_unknown_language(self):
        response = self.client.post(self.url, {'language': 'xx', 'weight_unit': 'kg', 'length_unit': 'cm'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_system_tab_only_for_superusers(self):
        self.assertNotContains(self.client.get(self.url), 'data-tab="system"')
        self.assertEqual(self.client.get(self.url, {'tab': 'system'}).context['initial_tab'], 'general')
        admin = User.objects.create_superuser('chef')
        self.client.force_login(admin)
        with tempfile.TemporaryDirectory() as backups, override_settings(BACKUP_DIR=backups):
            self.assertContains(self.client.get(self.url), 'data-tab="system"')


class BackupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', email='anna@example.com', password='geheim-12345')
        self.other = User.objects.create_user('ben', email='ben-geheim@example.com', password='geheim-12345')
        Goal.objects.create(user=self.user, goal_type='halten')
        Goal.objects.create(user=self.other, goal_type='abnehmen')
        UserData.objects.create(user=self.other, height_cm=199)
        self.client.force_login(self.user)

    def _open(self, response):
        return zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('backup-meine-daten')).status_code, 302)

    def test_user_backup_contains_only_own_data(self):
        response = self.client.get(reverse('backup-meine-daten'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        with self._open(response) as archive:
            raw = archive.read('backup.json').decode('utf-8')
        data = json.loads(raw)['data']
        self.assertEqual(data['user'][0]['fields']['username'], 'anna')
        self.assertEqual([goal['fields']['goal_type'] for goal in data['goals']], ['halten'])
        self.assertEqual(data['user_data'], [])
        self.assertNotIn('ben-geheim', raw)

    def test_user_backup_never_contains_password_hash(self):
        with self._open(self.client.get(reverse('backup-meine-daten'))) as archive:
            raw = archive.read('backup.json').decode('utf-8')
        self.assertNotIn('password', raw)
        self.assertNotIn(self.user.password, raw)

    def test_user_backup_contains_own_exercises_and_images(self):
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buffer, 'PNG')
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            profile = Profile.objects.create(user=self.user)
            profile.avatar.save('a.png', SimpleUploadedFile('a.png', buffer.getvalue()))
            profile.avatar.close()
            Exercise.objects.create(name='Eigene Uebung', instructions='x', created_by=self.user)
            Exercise.objects.create(name='Fremde Uebung', instructions='x', created_by=self.other)
            with self._open(self.client.get(reverse('backup-meine-daten'))) as archive:
                data = json.loads(archive.read('backup.json'))['data']
                self.assertIn(f'media/{profile.avatar.name}', archive.namelist())
        self.assertEqual([e['fields']['name'] for e in data['exercises']], ['Eigene Uebung'])
