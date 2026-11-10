from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserData, UserSettings

from . import statistics
from .goal import Weighing
from .metrics import Person, fixed_bands
from .models import BodyMetricsEntry, Goal


def w(day, kg):
    return Weighing(day, kg)


class StatisticsFunctionTests(TestCase):
    def test_period_keeps_the_last_days_including_today(self):
        today = date(2026, 11, 8)
        points = [w(date(2026, 10, 11), 1), w(date(2026, 10, 12), 2), w(today, 3)]
        self.assertEqual([p.kg for p in statistics.in_period(points, '4w', today)], [2, 3])
        self.assertEqual(len(statistics.in_period(points, 'alle', today)), 3)

    def test_rolling_average_uses_the_seven_days_before(self):
        points = [w(date(2026, 11, 1), 100), w(date(2026, 11, 4), 98), w(date(2026, 11, 8), 96)]
        self.assertEqual(statistics.rolling_average(points), [100, 99, 97])

    def test_rolling_average_looks_before_the_period(self):
        everything = [w(date(2026, 11, 1), 100), w(date(2026, 11, 4), 98)]
        self.assertEqual(statistics.rolling_average(everything[1:], everything), [99])

    def test_gaps_over_two_weeks(self):
        points = [w(date(2026, 1, 1), 1), w(date(2026, 1, 15), 1), w(date(2026, 1, 30), 1)]
        self.assertEqual(statistics.gaps(points), [1])

    def test_summary(self):
        points = [w(date(2026, 10, 1), 120), w(date(2026, 10, 8), 118), w(date(2026, 10, 15), 118), w(date(2026, 10, 29), 116)]
        summary = statistics.summarize(points)
        self.assertEqual(summary.count, 4)
        self.assertEqual(summary.change, -4)
        self.assertAlmostEqual(summary.per_week, -1.0)
        self.assertEqual(summary.lowest.date, date(2026, 10, 29))
        self.assertEqual(summary.highest.kg, 120)

    def test_summary_short_spans(self):
        single = statistics.summarize([w(date(2026, 11, 8), 100)])
        self.assertIsNone(single.change)
        self.assertIsNone(single.per_week)
        days = statistics.summarize([w(date(2026, 11, 5), 100), w(date(2026, 11, 8), 99)])
        self.assertEqual(days.change, -1)
        self.assertIsNone(days.per_week)
        self.assertIsNone(statistics.summarize([]))

    def test_equal_lowest_counts_the_latest(self):
        summary = statistics.summarize([w(date(2026, 11, 1), 99), w(date(2026, 11, 8), 99)])
        self.assertEqual(summary.lowest.date, date(2026, 11, 8))


class BandAndBucketTests(TestCase):
    def test_fixed_bands_follow_gender(self):
        man = fixed_bands('body_fat_pct', Person(gender='maennlich'))
        self.assertEqual([(b['low'], b['high']) for b in man], [(None, 6), (6, 13), (13, 17), (17, 25), (25, None)])
        self.assertEqual(man[-1]['label'], 'Hoch')
        woman = fixed_bands('skeletal_muscle_pct', Person(gender='weiblich'))
        self.assertEqual([(b['low'], b['high']) for b in woman], [(None, 40), (40, 50), (50, None)])

    def test_fixed_bands_need_what_they_depend_on(self):
        self.assertIsNone(fixed_bands('body_fat_pct', Person()))
        self.assertIsNone(fixed_bands('muscle_mass', Person(gender='maennlich')))
        self.assertEqual(fixed_bands('muscle_mass', Person(gender='maennlich', height_cm=175))[1]['low'], 49.4)
        # Masses follow the weight of each measurement, so no fixed areas.
        self.assertIsNone(fixed_bands('fat_mass', Person(gender='maennlich')))
        self.assertEqual(len(fixed_bands('bmi', Person())), 4)

    def test_weeks_start_on_monday(self):
        rows = [(date(2026, 11, 2), {'w': 100}), (date(2026, 11, 8), {'w': 98}), (date(2026, 11, 9), {'w': 97})]
        weeks = statistics.bucket_averages(rows, statistics.WEEK)
        self.assertEqual([(b['start'], b['end'], b['count']) for b in weeks],
                         [(date(2026, 11, 2), date(2026, 11, 8), 2), (date(2026, 11, 9), date(2026, 11, 15), 1)])
        self.assertEqual(weeks[0]['values'], {'w': 99})

    def test_months_ignore_missing_values(self):
        rows = [(date(2026, 2, 3), {'w': 100, 'f': None}), (date(2026, 2, 20), {'w': 96, 'f': 30}), (date(2026, 3, 1), {'w': 95})]
        months = statistics.bucket_averages(rows, statistics.MONTH)
        self.assertEqual(months[0]['end'], date(2026, 2, 28))
        self.assertEqual(months[0]['values'], {'w': 98, 'f': 30})
        self.assertEqual(months[1]['start'], date(2026, 3, 1))


class StatisticsPageTests(TestCase):
    url = reverse('statistik')

    def setUp(self):
        self.user = User.objects.create_user('anna', password='pw')
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def weigh(self, days_ago, kg, user=None):
        BodyMetricsEntry.objects.create(user=user or self.user, date=self.today - timedelta(days=days_ago), weight_kg=Decimal(kg))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_empty(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Noch keine Messungen')
        self.assertNotContains(response, 'chart.umd.js')

    def test_tiles_and_chart(self):
        UserData.objects.create(user=self.user, starting_weight_kg=Decimal('130.00'))
        Goal.objects.create(user=self.user, goal_type='abnehmen', target_weight_kg=Decimal('80.00'))
        self.weigh(200, '130.00')
        self.weigh(14, '121.00')
        self.weigh(7, '120.00')
        self.weigh(0, '119.00')
        response = self.client.get(self.url)
        tiles = response.context['tiles']
        self.assertEqual(response.context['period'], '3m')
        self.assertEqual(tiles['count'], 3)
        self.assertEqual(tiles['change']['value'], '−2,00')
        self.assertEqual(tiles['change']['trend'], 'good')
        self.assertEqual(tiles['per_week']['value'], '−1,00')
        self.assertEqual(tiles['span'], '2 Wochen')
        self.assertEqual(tiles['lowest']['value'], '119,00')
        chart = response.context['chart']
        self.assertEqual(len(chart['points']), 3)
        self.assertEqual([line['label'] for line in chart['lines']], ['Ausgangsgewicht', 'Zielgewicht'])
        self.assertIsNone(chart['band'])
        self.assertContains(response, 'chart.umd.js')
        self.assertContains(response, 'weight-chart-data')

        everything = self.client.get(self.url, {'zeitraum': 'alle'}).context
        self.assertEqual(everything['tiles']['count'], 4)
        self.assertEqual(everything['chart']['gaps'], [0])

    def test_unknown_period_falls_back(self):
        self.weigh(0, '100.00')
        self.assertEqual(self.client.get(self.url, {'zeitraum': 'kaputt'}).context['period'], '3m')

    def test_period_without_weighings(self):
        self.weigh(60, '100.00')
        response = self.client.get(self.url, {'zeitraum': '4w'})
        self.assertIsNone(response.context['tiles'])
        self.assertContains(response, 'gibt es kein Gewicht')

    def test_gaining_counts_as_good_for_muscle_goal(self):
        UserData.objects.create(user=self.user, starting_weight_kg=Decimal('70.00'))
        Goal.objects.create(user=self.user, goal_type='muskelaufbau', target_weight_kg=Decimal('80.00'))
        self.weigh(7, '70.00')
        self.weigh(0, '71.00')
        self.assertEqual(self.client.get(self.url).context['tiles']['change']['trend'], 'good')

    def test_hold_goal_shows_band(self):
        Goal.objects.create(user=self.user, goal_type='halten', target_weight_kg=Decimal('80.00'),
                            weight_tolerance_kg=Decimal('1.5'))
        self.weigh(0, '80.50')
        chart = self.client.get(self.url).context['chart']
        self.assertEqual((chart['band']['low'], chart['band']['high']), (78.5, 81.5))
        self.assertEqual([line['label'] for line in chart['lines']], ['Erste Messung'])

    def test_pounds(self):
        UserSettings.objects.create(user=self.user, weight_unit=UserSettings.WeightUnit.LB)
        self.weigh(7, '100.00')
        self.weigh(0, '99.00')
        response = self.client.get(self.url)
        self.assertEqual(response.context['unit'], 'lb')
        self.assertEqual(response.context['tiles']['lowest']['value'], '218,3')
        self.assertAlmostEqual(response.context['chart']['points'][0]['y'], 220.462, places=2)

    def test_only_own_weighings(self):
        other = User.objects.create_user('ben', password='pw')
        self.weigh(0, '150.00', user=other)
        self.assertContains(self.client.get(self.url), 'Noch keine Messungen')

    def test_nav_links_to_statistics(self):
        response = self.client.get(reverse('fortschritt'))
        self.assertContains(response, f'href="{self.url}"')


class StatisticsSectionsTests(TestCase):
    url = reverse('statistik')

    def setUp(self):
        self.user = User.objects.create_user('anna', password='pw')
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        UserData.objects.create(user=self.user, gender='maennlich', height_cm=175, birth_date=date(1987, 1, 1))

    def add(self, days_ago, **values):
        BodyMetricsEntry.objects.create(
            user=self.user, date=self.today - timedelta(days=days_ago),
            **{key: Decimal(value) for key, value in values.items()},
        )

    def test_measurements_without_weight_still_show_the_page(self):
        self.add(3, waist_cm='110.0')
        response = self.client.get(self.url)
        self.assertContains(response, 'Noch kein Gewicht eingetragen')
        self.assertEqual([m['key'] for m in response.context['measurements']], ['waist'])
        self.assertContains(response, 'chart.umd.js')

    def test_composition(self):
        self.add(14, weight_kg='120.00', body_fat_pct='35.0', muscle_mass_kg='72.00')
        self.add(0, weight_kg='118.00', body_fat_pct='34.0', muscle_mass_kg='72.50')
        response = self.client.get(self.url)
        by_key = {s['key']: s for s in response.context['composition']}
        self.assertEqual(response.context['composition_default'], 'body_fat_pct')
        fat = by_key['body_fat_pct']
        self.assertEqual((fat['latest'], fat['change'], fat['trend']), ('34,0', '−1,0', 'good'))
        self.assertEqual(fat['rating']['label'], 'Hoch')
        self.assertEqual(len(fat['bands']), 5)
        self.assertEqual(by_key['muscle_mass']['trend'], 'good')
        self.assertIsNone(by_key['fat_mass']['bands'])
        self.assertNotIn('weight', by_key)

    def test_muscle_goal_starts_with_muscle_mass_and_growing_sizes(self):
        Goal.objects.create(user=self.user, goal_type='muskelaufbau')
        self.add(14, muscle_mass_kg='72.00', body_fat_pct='30.0', upper_arm_cm='38.0', waist_cm='100.0')
        self.add(0, muscle_mass_kg='72.50', body_fat_pct='30.0', upper_arm_cm='38.5', waist_cm='99.0')
        context = self.client.get(self.url).context
        self.assertEqual(context['composition_default'], 'muscle_mass')
        self.assertEqual(context['measurement_default'], ['waist', 'upper_arm'])
        by_key = {s['key']: s for s in context['measurements']}
        self.assertEqual(by_key['upper_arm']['trend'], 'good')
        self.assertEqual(by_key['waist']['trend'], 'good')

    def test_measurement_gaps_are_long(self):
        self.add(60, waist_cm='112.0')
        self.add(30, waist_cm='110.0')
        self.add(0, waist_cm='108.0')
        waist = self.client.get(self.url).context['measurements'][0]
        self.assertEqual(waist['gaps'], [])
        self.assertEqual(waist['change'], '−4,0')

    def test_overview_weeks_and_months(self):
        # Two weighings in one week, one in an earlier week.
        monday = self.today - timedelta(days=self.today.weekday())
        for day, kg in ((monday, '100.00'), (monday + timedelta(days=1), '98.00'), (monday - timedelta(days=7), '101.00')):
            if day <= self.today:
                BodyMetricsEntry.objects.create(user=self.user, date=day, weight_kg=Decimal(kg))
        context = self.client.get(self.url).context
        weeks = context['overview']['woche']
        self.assertEqual(context['overview_default'], 'woche')
        self.assertEqual([c['label'] for c in weeks['columns']], ['Gewicht'])
        newest = weeks['rows'][0]
        expected = '99,00' if monday + timedelta(days=1) <= self.today else '100,00'
        self.assertEqual(newest['cells'][0]['value'], expected)
        self.assertEqual(newest['cells'][0]['trend'], 'good')
        self.assertEqual(weeks['rows'][-1]['start'], monday - timedelta(days=7))
        self.assertNotIn('change', weeks['rows'][-1]['cells'][0])
        self.assertTrue(context['overview']['monat']['rows'])
        self.assertEqual(self.client.get(self.url, {'zeitraum': 'alle'}).context['overview_default'], 'monat')

    def test_overview_compares_with_the_bucket_before_the_period(self):
        self.add(200, weight_kg='110.00')
        self.add(0, weight_kg='100.00')
        rows = self.client.get(self.url, {'zeitraum': '4w'}).context['overview']['woche']['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cells'][0]['change'], '−10,00')

    def test_page_renders_all_sections(self):
        self.add(7, weight_kg='120.00', body_fat_pct='35.0', waist_cm='110.0')
        self.add(0, weight_kg='119.00', body_fat_pct='34.5', waist_cm='109.0')
        response = self.client.get(self.url)
        for text in ('Gewichtsverlauf', 'Körperzusammensetzung', 'Körpermaße', 'Übersicht', 'composition-data',
                     'measurement-data', 'data-overview="woche"', 'data-overview="monat"', 'Training'):
            self.assertContains(response, text)
