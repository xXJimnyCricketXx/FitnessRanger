from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserData, UserSettings
from progress.models import BodyMetricsEntry, Goal

from .views import tool_defaults


class ToolsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna')
        self.url = reverse('tools')

    def test_login_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_page_works_without_any_saved_data(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['defaults']['weight_kg'], None)
        self.assertEqual(response.context['initial_tab'], 'bmi')
        self.assertEqual(response.context['weight_unit'], 'kg')

    def test_heading_and_tabs_match_the_list_pages(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, '<h1 class="list-title">Tools</h1>')
        self.assertContains(response, 'class="list-tab" data-tab="bmi"')

    def test_opening_tools_saves_nothing(self):
        self.client.force_login(self.user)
        self.client.get(self.url)
        self.assertFalse(UserData.objects.filter(user=self.user).exists())
        self.assertFalse(UserSettings.objects.filter(user=self.user).exists())

    def test_tab_from_url_and_unknown_tab(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {'tab': 'herz'}).context['initial_tab'], 'herz')
        self.assertEqual(self.client.get(self.url, {'tab': 'x'}).context['initial_tab'], 'bmi')

    def test_uses_unit_settings(self):
        UserSettings.objects.create(user=self.user, weight_unit='lb', length_unit='ft_in')
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.context['weight_unit'], 'lb')
        self.assertEqual(response.context['length_unit'], 'ft_in')


class ToolDefaultsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna')

    def test_values_from_personal_data(self):
        today = timezone.localdate()
        UserData.objects.create(
            user=self.user, height_cm=180, starting_weight_kg=82, gender='maennlich', activity_level='leicht_aktiv',
            birth_date=date(today.year - 30, today.month, 1) - timedelta(days=1),
        )
        Goal.objects.create(user=self.user, goal_type='abnehmen')
        defaults = tool_defaults(self.user)
        self.assertEqual(defaults['height_cm'], 180)
        self.assertEqual(defaults['weight_kg'], 82.0)
        self.assertEqual(defaults['age'], 30)
        self.assertEqual(defaults['gender'], 'maennlich')
        self.assertEqual(defaults['activity'], 'leicht_aktiv')
        self.assertEqual(defaults['goal'], 'abnehmen')

    def test_latest_measured_weight_beats_starting_weight(self):
        UserData.objects.create(user=self.user, starting_weight_kg=90)
        today = timezone.localdate()
        BodyMetricsEntry.objects.create(user=self.user, date=today - timedelta(days=7), weight_kg=85)
        BodyMetricsEntry.objects.create(user=self.user, date=today - timedelta(days=1), weight_kg=84)
        BodyMetricsEntry.objects.create(user=self.user, date=today)
        self.assertEqual(tool_defaults(self.user)['weight_kg'], 84.0)

    def test_birthday_later_this_year_counts_correctly(self):
        today = timezone.localdate()
        upcoming = today + timedelta(days=1)
        UserData.objects.create(user=self.user, birth_date=date(upcoming.year - 30, upcoming.month, upcoming.day))
        self.assertEqual(tool_defaults(self.user)['age'], 29)

    def test_does_not_see_other_users_data(self):
        other = User.objects.create_user('ben')
        UserData.objects.create(user=other, height_cm=199)
        self.assertIsNone(tool_defaults(self.user)['height_cm'])
