from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserData, UserSettings

from . import goal, importers
from .forms import LENGTH_FIELDS
from .metrics import BODY_METRICS, MEASUREMENT_METRICS, latest_readings
from .models import BodyMetricsEntry


def person(gender='maennlich', height_cm=175, birth_date=date(1987, 1, 1)):
    return SimpleNamespace(gender=gender, height_cm=height_cm, birth_date=birth_date)


def entry(day=date(2026, 11, 6), **values):
    return BodyMetricsEntry(date=day, **values)


# The measurement from the user's RENPHO report on 2026-11-06, with the labels RENPHO showed.
RENPHO_MEASUREMENT = dict(
    weight_kg=Decimal('124.60'), bmi=Decimal('40.7'), body_fat_pct=Decimal('39.2'),
    subcutaneous_fat_pct=Decimal('32.9'), visceral_fat=22, muscle_mass_kg=Decimal('72.02'),
    skeletal_muscle_pct=Decimal('39.0'), fat_free_weight_kg=Decimal('75.76'), bone_mass_kg=Decimal('3.74'),
    water_pct=Decimal('43.9'), protein_pct=Decimal('13.9'), bmr_kcal=1984, metabolic_age=44,
)
RENPHO_LABELS = {
    'weight': 'Hoch',
    'bmi': 'Hoch',
    'body_fat_pct': 'Hoch',
    'fat_mass': 'Hoch',
    'subcutaneous_fat_pct': 'Überdurchschnittlich',
    'visceral_fat': 'Hoch',
    'muscle_pct': 'Ausgezeichnet',
    'muscle_mass': 'Ausgezeichnet',
    'skeletal_muscle_pct': 'Unterdurchschnittlich',
    'skeletal_muscle_mass': 'Unterdurchschnittlich',
    'bone_pct': 'Durchschnittlich',
    'bone_mass': 'Durchschnittlich',
    'metabolic_age': 'Überdurchschnittlich',
    'bmr': 'Unterdurchschnittlich',
    'water_pct': 'Unterdurchschnittlich',
    'water_mass': 'Unterdurchschnittlich',
    'protein_pct': 'Unterdurchschnittlich',
    'protein_mass': 'Unterdurchschnittlich',
}


def ratings(metrics, entries, user_data):
    return {r.metric.key: (r.rating.label if r.rating else None) for r in latest_readings(metrics, entries, user_data)}


class RatingTests(TestCase):
    def test_matches_renpho_report(self):
        result = ratings(BODY_METRICS, [entry(**RENPHO_MEASUREMENT)], person())
        for key, label in RENPHO_LABELS.items():
            self.assertEqual(result[key], label, key)
        self.assertIsNone(result['fat_free_weight'])

    def test_derived_masses(self):
        readings = {r.metric.key: r.value for r in latest_readings(BODY_METRICS, [entry(**RENPHO_MEASUREMENT)], person())}
        self.assertAlmostEqual(readings['fat_mass'], 48.84, places=2)
        self.assertAlmostEqual(readings['water_mass'], 54.70, places=2)
        self.assertAlmostEqual(readings['protein_mass'], 17.32, places=2)
        self.assertAlmostEqual(readings['skeletal_muscle_mass'], 48.59, places=2)
        self.assertAlmostEqual(readings['muscle_pct'], 57.8, places=1)

    def test_women_only_get_known_limits(self):
        result = ratings(BODY_METRICS, [entry(**RENPHO_MEASUREMENT)], person(gender='weiblich', height_cm=165))
        self.assertEqual(result['body_fat_pct'], 'Hoch')
        self.assertEqual(result['muscle_mass'], 'Ausgezeichnet')

    def test_female_limits_from_renpho(self):
        woman = person(gender='weiblich', height_cm=176)

        def label(key, **values):
            return ratings(BODY_METRICS, [entry(**{k: Decimal(v) for k, v in values.items()})], woman)[key]
        self.assertEqual(label('weight', weight_kg='57.30'), 'Unterdurchschnittlich')
        self.assertEqual(label('weight', weight_kg='57.32'), 'Durchschnittlich')
        self.assertEqual(label('weight', weight_kg='77.45'), 'Überdurchschnittlich')
        self.assertEqual(label('weight', weight_kg='92.94'), 'Hoch')
        self.assertEqual(label('subcutaneous_fat_pct', subcutaneous_fat_pct='18.4'), 'Unterdurchschnittlich')
        self.assertEqual(label('subcutaneous_fat_pct', subcutaneous_fat_pct='26.7'), 'Überdurchschnittlich')
        self.assertEqual(label('visceral_fat', visceral_fat='11'), 'Überdurchschnittlich')
        self.assertEqual(label('muscle_mass', muscle_mass_kg='36.4'), 'Unterdurchschnittlich')
        self.assertEqual(label('muscle_mass', muscle_mass_kg='42.5'), 'Ausgezeichnet')
        self.assertEqual(label('skeletal_muscle_pct', skeletal_muscle_pct='45'), 'Durchschnittlich')
        self.assertEqual(label('skeletal_muscle_pct', skeletal_muscle_pct='50'), 'Ausgezeichnet')
        self.assertEqual(label('water_pct', water_pct='44.9'), 'Unterdurchschnittlich')
        self.assertEqual(label('water_pct', water_pct='60'), 'Überdurchschnittlich')
        self.assertEqual(label('protein_pct', protein_pct='15'), 'Durchschnittlich')
        self.assertEqual(label('protein_pct', protein_pct='16'), 'Überdurchschnittlich')
        # RENPHO at 88.8 kg: 2.22 / 3.55 kg
        self.assertEqual(label('bone_mass', weight_kg='88.8', bone_mass_kg='2.21'), 'Unterdurchschnittlich')
        self.assertEqual(label('bone_mass', weight_kg='88.8', bone_mass_kg='2.23'), 'Durchschnittlich')
        self.assertEqual(label('bone_mass', weight_kg='88.8', bone_mass_kg='3.56'), 'Überdurchschnittlich')

    def test_no_profile_means_no_personal_ratings(self):
        result = ratings(BODY_METRICS, [entry(**RENPHO_MEASUREMENT)], None)
        self.assertEqual(result['bmi'], 'Hoch')
        self.assertIsNone(result['weight'])
        self.assertIsNone(result['body_fat_pct'])
        self.assertIsNone(result['metabolic_age'])
        self.assertIsNone(result['bmr'])

    def test_bmi_limits(self):
        def bmi_label(value):
            return ratings(BODY_METRICS, [entry(bmi=Decimal(value))], person())['bmi']
        self.assertEqual(bmi_label('18.4'), 'Unterdurchschnittlich')
        self.assertEqual(bmi_label('18.5'), 'Durchschnittlich')
        self.assertEqual(bmi_label('24.9'), 'Durchschnittlich')
        self.assertEqual(bmi_label('25.0'), 'Überdurchschnittlich')
        self.assertEqual(bmi_label('30.0'), 'Hoch')

    def test_bmi_is_calculated_when_missing(self):
        readings = {r.metric.key: r.value for r in latest_readings(BODY_METRICS, [entry(weight_kg=Decimal('70'))], person())}
        self.assertAlmostEqual(readings['bmi'], 22.86, places=2)

    def test_body_fat_ace_limits(self):
        def label(value, gender='maennlich'):
            return ratings(BODY_METRICS, [entry(body_fat_pct=Decimal(value))], person(gender=gender))['body_fat_pct']
        self.assertEqual(label('5.9'), 'Niedrig')
        self.assertEqual(label('6.0'), 'Athletisch')
        self.assertEqual(label('13.0'), 'Fitness')
        self.assertEqual(label('17.0'), 'Akzeptabel')
        self.assertEqual(label('25.0'), 'Hoch')
        self.assertEqual(label('24.9', 'weiblich'), 'Fitness')
        self.assertEqual(label('32.0', 'weiblich'), 'Hoch')

    def test_waist_limits(self):
        def label(value, gender='maennlich'):
            return ratings(MEASUREMENT_METRICS, [entry(waist_cm=Decimal(value))], person(gender=gender))['waist']
        self.assertEqual(label('93.9'), 'Nicht erhöht')
        self.assertEqual(label('94.0'), 'Erhöht')
        self.assertEqual(label('102.0'), 'Deutlich erhöht')
        self.assertEqual(label('80.0', 'weiblich'), 'Erhöht')

    def test_change_uses_previous_measurement_with_that_value(self):
        entries = [
            entry(date(2026, 11, 6), weight_kg=Decimal('124.60'), waist_cm=Decimal('120.0')),
            entry(date(2026, 11, 1), waist_cm=Decimal('121.5')),
            entry(date(2026, 10, 30), weight_kg=Decimal('124.30')),
        ]
        weight = latest_readings(BODY_METRICS, entries, person())[0]
        self.assertAlmostEqual(weight.change, 0.30, places=2)
        self.assertEqual(weight.previous_date, date(2026, 10, 30))
        waist = latest_readings(MEASUREMENT_METRICS, entries, person())[0]
        self.assertAlmostEqual(waist.change, -1.5, places=2)

    def test_latest_value_may_be_older_than_latest_entry(self):
        entries = [entry(date(2026, 11, 6), weight_kg=Decimal('124.60')), entry(date(2026, 10, 1), neck_cm=Decimal('44.0'))]
        neck = latest_readings(MEASUREMENT_METRICS, entries, person())[0]
        self.assertEqual(neck.date, date(2026, 10, 1))
        self.assertIsNone(neck.change)

    def test_age_is_taken_on_the_measurement_day(self):
        user_data = person(birth_date=date(1987, 11, 10))
        result = ratings(BODY_METRICS, [entry(date(2026, 11, 6), metabolic_age=39)], user_data)
        # Still 38 on that day, so 39 is above the real age.
        self.assertEqual(result['metabolic_age'], 'Überdurchschnittlich')


class ProgressPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', password='pw')
        self.other = User.objects.create_user('ben', password='pw')
        self.today = timezone.localdate()

    def test_login_required(self):
        for url in (reverse('fortschritt'), reverse('fortschritt-gewicht'), reverse('fortschritt-masse')):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_empty_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('fortschritt'))
        self.assertContains(response, 'Noch keine Einträge vorhanden')

    def test_shows_only_own_entries(self):
        BodyMetricsEntry.objects.create(user=self.other, date=self.today, weight_kg=Decimal('99.90'))
        BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('70.00'))
        self.client.force_login(self.user)
        response = self.client.get(reverse('fortschritt'))
        self.assertContains(response, '70,00')
        self.assertNotContains(response, '99,90')

    def test_comparison_and_start(self):
        UserData.objects.create(user=self.user, starting_weight_kg=Decimal('130.00'), height_cm=175, gender='maennlich')
        BodyMetricsEntry.objects.create(user=self.user, date=self.today - timedelta(days=7), weight_kg=Decimal('124.30'))
        BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('124.60'))
        self.client.force_login(self.user)
        response = self.client.get(reverse('fortschritt'))
        self.assertEqual(response.context['weight']['change'], '+0,30')
        self.assertEqual(response.context['since_start']['change'], '−5,40')
        self.assertEqual(response.context['weight']['rating'].label, 'Hoch')

    def test_values_in_pounds_and_inches(self):
        UserSettings.objects.create(user=self.user, weight_unit='lb', length_unit='ft_in')
        BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('100.00'), waist_cm=Decimal('101.6'))
        self.client.force_login(self.user)
        response = self.client.get(reverse('fortschritt'))
        self.assertEqual(response.context['weight']['value'], '220,5')
        self.assertEqual(response.context['measurement_tiles'][0]['value'], '40,0')

    def test_tab_from_url(self):
        BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('70.00'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('fortschritt'), {'tab': 'historie'}).context['initial_tab'], 'historie')
        self.assertEqual(self.client.get(reverse('fortschritt'), {'tab': 'x'}).context['initial_tab'], 'koerperwerte')


class EntryFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', password='pw')
        self.other = User.objects.create_user('ben', password='pw')
        self.today = timezone.localdate()
        self.client.force_login(self.user)
        self.url = reverse('fortschritt-gewicht')
        self.masse_url = reverse('fortschritt-masse')

    def post(self, url=None, **data):
        data.setdefault('date', self.today.isoformat())
        return self.client.post(url or self.url, data)

    def test_create_entry(self):
        response = self.post(weight_kg='124.6', body_fat_pct='39.2', visceral_fat='22')
        self.assertRedirects(response, reverse('fortschritt'))
        saved = BodyMetricsEntry.objects.get(user=self.user)
        self.assertEqual(saved.weight_kg, Decimal('124.60'))
        self.assertEqual(saved.visceral_fat, 22)
        self.assertEqual(saved.source, 'manuell')

    def test_forms_only_offer_their_fields(self):
        weight_form = self.client.get(self.url).context['form']
        masse_form = self.client.get(self.masse_url).context['form']
        self.assertNotIn('waist_cm', weight_form.fields)
        self.assertIn('body_fat_pct', weight_form.fields)
        self.assertEqual(list(masse_form.fields), ['date'] + LENGTH_FIELDS)
        self.assertIn('calf_cm', masse_form.fields)

    def test_measurements_on_their_own(self):
        response = self.post(self.masse_url, waist_cm='120')
        self.assertRedirects(response, reverse('fortschritt') + '?tab=koerpermasse')
        saved = BodyMetricsEntry.objects.get(user=self.user)
        self.assertEqual(saved.waist_cm, Decimal('120.0'))
        self.assertIsNone(saved.weight_kg)

    def test_needs_at_least_one_value(self):
        response = self.post()
        self.assertContains(response, 'Bitte trage mindestens einen Wert ein.')
        self.assertFalse(BodyMetricsEntry.objects.exists())

    def test_rejects_future_date(self):
        response = self.post(date=(self.today + timedelta(days=1)).isoformat(), weight_kg='80')
        self.assertContains(response, 'nicht in der Zukunft')

    def test_measurements_fill_in_an_imported_day(self):
        imported = BodyMetricsEntry.objects.create(
            user=self.user, date=self.today, weight_kg=Decimal('124.60'), body_fat_pct=Decimal('39.2'), source='renpho_csv')
        self.post(self.masse_url, waist_cm='120', hip_cm='125')
        self.assertEqual(BodyMetricsEntry.objects.count(), 1)
        imported.refresh_from_db()
        self.assertEqual(imported.waist_cm, Decimal('120.0'))
        self.assertEqual(imported.weight_kg, Decimal('124.60'))
        self.assertEqual(imported.body_fat_pct, Decimal('39.2'))
        history = self.client.get(reverse('fortschritt')).context['history']
        self.assertEqual(history[0]['source'], 'RENPHO CSV + Manuell')
        self.assertEqual(history[0]['measurements'], 'Bauch, Hüfte')

    def test_empty_fields_do_not_erase_the_day(self):
        BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('80'), body_fat_pct=Decimal('20.0'))
        self.post(weight_kg='81')
        saved = BodyMetricsEntry.objects.get(user=self.user)
        self.assertEqual(saved.weight_kg, Decimal('81.00'))
        self.assertEqual(saved.body_fat_pct, Decimal('20.0'))

    def test_edit_still_refuses_a_taken_day(self):
        BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('80'))
        other_day = BodyMetricsEntry.objects.create(user=self.user, date=self.today - timedelta(days=1), weight_kg=Decimal('81'))
        response = self.post(reverse('fortschritt-bearbeiten', args=[other_day.pk]), weight_kg='81')
        self.assertContains(response, 'schon einen Eintrag')

    def test_same_day_is_fine_for_another_user(self):
        BodyMetricsEntry.objects.create(user=self.other, date=self.today, weight_kg=Decimal('80'))
        self.post(weight_kg='81')
        self.assertTrue(BodyMetricsEntry.objects.filter(user=self.user).exists())

    def test_rejects_implausible_values(self):
        response = self.post(weight_kg='1246', body_fat_pct='392')
        self.assertContains(response, 'nicht plausibel', count=2)
        self.assertFalse(BodyMetricsEntry.objects.exists())

    def test_pounds_and_inches_are_stored_in_kg_and_cm(self):
        UserSettings.objects.create(user=self.user, weight_unit='lb', length_unit='ft_in')
        self.post(weight_kg='220.5', muscle_mass_kg='158.8')
        self.post(self.masse_url, waist_cm='40')
        saved = BodyMetricsEntry.objects.get(user=self.user)
        self.assertEqual(saved.weight_kg, Decimal('100.02'))
        self.assertEqual(saved.muscle_mass_kg, Decimal('72.03'))
        self.assertEqual(saved.waist_cm, Decimal('101.6'))

    def test_edit_shows_values_in_user_units(self):
        UserSettings.objects.create(user=self.user, weight_unit='lb')
        saved = BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('100.00'))
        response = self.client.get(reverse('fortschritt-bearbeiten', args=[saved.pk]))
        self.assertContains(response, 'value="220.46"')

    def test_edit_keeps_source(self):
        saved = BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('80'), source='renpho_csv')
        self.post(reverse('fortschritt-bearbeiten', args=[saved.pk]), weight_kg='79.5')
        saved.refresh_from_db()
        self.assertEqual(saved.weight_kg, Decimal('79.50'))
        self.assertEqual(saved.source, 'renpho_csv')

    def test_cannot_touch_other_users_entries(self):
        foreign = BodyMetricsEntry.objects.create(user=self.other, date=self.today, weight_kg=Decimal('80'))
        self.assertEqual(self.client.get(reverse('fortschritt-bearbeiten', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.post(reverse('fortschritt-bearbeiten', args=[foreign.pk]), weight_kg='1').status_code, 404)
        self.assertEqual(self.client.post(reverse('fortschritt-loeschen', args=[foreign.pk])).status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.weight_kg, Decimal('80.00'))

    def test_delete_own_entry(self):
        saved = BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('80'))
        response = self.client.post(reverse('fortschritt-loeschen', args=[saved.pk]))
        self.assertRedirects(response, reverse('fortschritt') + '?tab=historie')
        self.assertFalse(BodyMetricsEntry.objects.exists())

    def test_delete_needs_post(self):
        saved = BodyMetricsEntry.objects.create(user=self.user, date=self.today, weight_kg=Decimal('80'))
        self.assertEqual(self.client.get(reverse('fortschritt-loeschen', args=[saved.pk])).status_code, 405)


RENPHO_HEADER = (
    '\ufeffDatum,Zeitraum,Gewicht(kg),BMI,Körperfett(%),Skelettmuskel(%),Fettfreies Körpergewicht(kg),'
    'Subkutanes Fett(%),Viszeralfett,Körperwasser(%),Muskelmasse(kg),Knochenmasse(kg),Eiweiß(%),'
    'Grundumsatz(kcal),Stoffwechselalter,Optimales Gewicht(kg),Körpertyp,Bemerkungen'
)


def renpho_csv(*lines):
    return '\n'.join((RENPHO_HEADER,) + lines).encode('utf-8')


ROW_0807 = '2026.08.07,13:59:26,129.50,42.3,39.8,38.6,77.96,33.3,24.0,43.5,74.07,3.89,13.7,2049,43,--,--,--'
ROW_0731 = '2026.07.31,09:47:27,130.00,42.4,39.9,38.6,78.13,33.3,24.0,43.4,74.23,3.90,13.7,2053,43,--,--,--'


class ImportParseTests(TestCase):
    def test_reads_renpho_export(self):
        result = importers.parse(renpho_csv(ROW_0807, ROW_0731), today=date(2026, 11, 6))
        self.assertEqual(result.format.key, 'renpho')
        self.assertEqual([r.date for r in result.rows], [date(2026, 8, 7), date(2026, 7, 31)])
        values = result.rows[0].values
        self.assertEqual(values['weight_kg'], Decimal('129.50'))
        self.assertEqual(values['visceral_fat'], 24)
        self.assertEqual(values['bmr_kcal'], 2049)
        self.assertEqual(values['bone_mass_kg'], Decimal('3.89'))
        self.assertEqual(len(values), 13)
        self.assertEqual(result.skipped_columns, ['Optimales Gewicht(kg)', 'Körpertyp', 'Bemerkungen'])
        self.assertEqual(result.problems, [])

    def test_column_order_does_not_matter(self):
        data = 'Gewicht(kg),Datum,Körperfett(%)\n80.0,2026.10.01,20.5'.encode('utf-8')
        row = importers.parse(data, today=date(2026, 11, 6)).rows[0]
        self.assertEqual(row.values, {'weight_kg': Decimal('80.0'), 'body_fat_pct': Decimal('20.5')})

    def test_unknown_format_is_rejected(self):
        with self.assertRaisesMessage(importers.ImportFileError, 'nicht bekannt'):
            importers.parse(b'Date,Weight\n2026-10-01,80', today=date(2026, 11, 6))

    def test_latest_measurement_of_the_day_wins(self):
        early = ROW_0807.replace('13:59:26', '07:00:00').replace('129.50', '131.00')
        result = importers.parse(renpho_csv(early, ROW_0807), today=date(2026, 11, 6))
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0].values['weight_kg'], Decimal('129.50'))
        self.assertEqual(result.replaced_same_day, 1)

    def test_bad_values_are_reported_and_skipped(self):
        bad = ROW_0731.replace('130.00', '1300.00').replace('2053', 'abc')
        result = importers.parse(renpho_csv(bad, '2026.13.01,,80,,,,,,,,,,,,,,,', ROW_0807), today=date(2026, 11, 6))
        self.assertEqual(len(result.rows), 2)
        july = result.rows[1].values
        self.assertNotIn('weight_kg', july)
        self.assertNotIn('bmr_kcal', july)
        self.assertEqual(len(result.problems), 3)

    def test_future_dates_are_skipped(self):
        result = importers.parse(renpho_csv(ROW_0807), today=date(2026, 8, 6))
        self.assertEqual(result.rows, [])


class ImportViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', password='pw')
        self.client.force_login(self.user)
        self.url = reverse('fortschritt-import')

    def upload(self, data, name='renpho.csv'):
        return self.client.post(self.url, {'file': SimpleUploadedFile(name, data, content_type='text/csv')})

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_preview_saves_nothing_until_confirmed(self):
        response = self.upload(renpho_csv(ROW_0807, ROW_0731))
        self.assertEqual(response.context['new_count'], 2)
        self.assertFalse(BodyMetricsEntry.objects.exists())
        response = self.client.post(self.url, {'confirm': '1'})
        self.assertRedirects(response, reverse('fortschritt') + '?tab=historie')
        entries = BodyMetricsEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(e.source == BodyMetricsEntry.Source.RENPHO_CSV for e in entries))

    def test_existing_day_keeps_measurements(self):
        existing = BodyMetricsEntry.objects.create(
            user=self.user, date=date(2026, 8, 7), weight_kg=Decimal('129.00'), waist_cm=Decimal('130.0'))
        response = self.upload(renpho_csv(ROW_0807))
        self.assertEqual(response.context['changed_count'], 1)
        self.client.post(self.url, {'confirm': '1'})
        existing.refresh_from_db()
        self.assertEqual(existing.weight_kg, Decimal('129.50'))
        self.assertEqual(existing.waist_cm, Decimal('130.0'))
        self.assertEqual(existing.body_fat_pct, Decimal('39.8'))
        self.assertEqual(existing.source, BodyMetricsEntry.Source.MANUAL)

    def test_second_import_changes_nothing(self):
        self.upload(renpho_csv(ROW_0807))
        self.client.post(self.url, {'confirm': '1'})
        response = self.upload(renpho_csv(ROW_0807))
        self.assertEqual(response.context['unchanged_count'], 1)
        self.assertContains(response, 'disabled')

    def test_confirm_without_preview(self):
        response = self.client.post(self.url, {'confirm': '1'})
        self.assertContains(response, 'Vorschau ist abgelaufen')

    def test_unknown_file_shows_error(self):
        response = self.upload(b'foo,bar\n1,2')
        self.assertContains(response, 'nicht bekannt')
        self.assertIsNone(self.client.session.get('progress_import'))

    def test_other_users_entries_untouched(self):
        other = User.objects.create_user('ben', password='pw')
        theirs = BodyMetricsEntry.objects.create(user=other, date=date(2026, 8, 7), weight_kg=Decimal('80.00'))
        self.upload(renpho_csv(ROW_0807))
        self.client.post(self.url, {'confirm': '1'})
        theirs.refresh_from_db()
        self.assertEqual(theirs.weight_kg, Decimal('80.00'))
        self.assertEqual(BodyMetricsEntry.objects.filter(user=self.user).count(), 1)


class ImportNewRenphoHeaderTests(TestCase):
    # Newer RENPHO exports from November 2026 renamed columns and added derived values.
    HEADER = (
        '﻿Nr.,Datum,Zeitraum,Gewicht(kg),BMI,Körperfettanteil(%),Körperfettmasse(kg),Muskelanteil(%),'
        'Muskelmasse(kg),Skelettmuskelanteil(%),Skelettmuskelmasse(kg),Knochenanteil(%),Knochenmasse(kg),'
        'Proteinanteil(%),Proteinmasse(kg),Körperwasseranteil(%),Körperwassermasse(kg),'
        'Fettfreies Körpergewicht(kg),Subkutanes Fett(%),Viszeralfett,Grundumsatz(kcal),Stoffwechselalter,'
        'WHR (Taille-Hüfte-Verhältnis),Optimales Gewicht(kg),Gewichtsstufe,Körpertyp,'
        'Ziel zum optimalen Gewicht(kg),Ziel zur optimalen Muskelmasse(kg),Ziel zur optimalen Fettmasse(kg),Bemerkungen,'
    )
    ROW = ('1,2026.11.06,09:43:29,124.60,40.7,39.2,48.84,57.8,72.02,39.0,48.59,3.0,3.74,13.9,17.32,43.9,54.70,'
           '75.76,32.9,22,1984,44,--,93.53,--,Adipositas,-31.07,0.00,-31.07,,')

    def test_reads_new_header(self):
        result = importers.parse((self.HEADER + '\n' + self.ROW).encode('utf-8'), today=date(2026, 11, 6))
        values = result.rows[0].values
        self.assertEqual(values, RENPHO_MEASUREMENT)
        self.assertNotIn('Nr.', result.skipped_columns)
        self.assertNotIn('Körperfettmasse(kg)', result.skipped_columns)
        self.assertIn('WHR (Taille-Hüfte-Verhältnis)', result.skipped_columns)
        self.assertEqual(result.problems, [])


class TrendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna', password='pw')
        self.client.force_login(self.user)
        today = timezone.localdate()
        BodyMetricsEntry.objects.create(user=self.user, date=today - timedelta(days=7), weight_kg=Decimal('130.00'),
                                        muscle_mass_kg=Decimal('74.00'), body_fat_pct=Decimal('40.0'))
        BodyMetricsEntry.objects.create(user=self.user, date=today, weight_kg=Decimal('129.50'),
                                        muscle_mass_kg=Decimal('74.20'), body_fat_pct=Decimal('40.0'))

    def test_colours_follow_what_is_progress(self):
        response = self.client.get(reverse('fortschritt'))
        tiles = {t['key']: t for t in response.context['body_tiles']}
        self.assertEqual(tiles['weight']['trend'], 'good')
        self.assertEqual(tiles['muscle_mass']['trend'], 'good')
        self.assertEqual(tiles['body_fat_pct']['trend'], 'same')
        self.assertEqual(tiles['fat_mass']['trend'], 'good')
        self.assertEqual(response.context['since_start']['trend'], 'good')
        self.assertContains(response, 'metric-trend trend-good')
        self.assertEqual(tiles['weight']['direction'], 'down')
        self.assertEqual(tiles['muscle_mass']['direction'], 'up')
        self.assertEqual(tiles['body_fat_pct']['direction'], 'flat')

    def test_rounding_decides_same(self):
        from .views import trend
        self.assertEqual(trend(0.004, 2), 'same')
        self.assertEqual(trend(0.3, 1), 'bad')
        self.assertEqual(trend(0.3, 1, higher_is_better=True), 'good')
        self.assertIsNone(trend(None, 1))


def weighings(*pairs):
    return [goal.Weighing(day, kg) for day, kg in pairs]


class GoalTests(TestCase):
    # The user's weighings in October and November 2026. RENPHO showed 22 weeks on 23.10.
    OCTOBER = weighings(
        (date(2026, 10, 9), 125.4), (date(2026, 10, 17), 126.3), (date(2026, 10, 23), 124.3),
        (date(2026, 10, 30), 124.3), (date(2026, 11, 6), 124.6),
    )

    def until(self, day):
        return [p for p in self.OCTOBER if p.date <= day]

    def finish(self, day):
        return goal.finish_label(goal.goal_progress(self.until(day), 145.2, 80.0, 'abnehmen'))

    def test_pace_of_this_week_like_renpho(self):
        self.assertEqual(self.finish(date(2026, 10, 23)), '22 Wochen')

    def test_no_change_keeps_last_weeks_forecast(self):
        self.assertEqual(self.finish(date(2026, 10, 30)), '22 Wochen')

    def test_dash_after_gaining(self):
        self.assertEqual(self.finish(date(2026, 11, 6)), '–')
        self.assertEqual(self.finish(date(2026, 10, 17)), '–')

    def test_seven_day_change(self):
        self.assertAlmostEqual(goal.seven_day_change(self.OCTOBER), 0.3)
        self.assertAlmostEqual(goal.seven_day_change(self.until(date(2026, 10, 23))), -2.0)
        daily = weighings(*[(date(2026, 11, d), 80 - d * 0.1) for d in range(1, 9)])
        self.assertAlmostEqual(goal.seven_day_change(daily), -0.7)
        self.assertIsNone(goal.seven_day_change(weighings((date(2026, 9, 1), 80), (date(2026, 11, 6), 79))))

    def test_daily_weighing_uses_the_week_not_the_day(self):
        days = [(date(2026, 11, d), 90 - d * 0.2) for d in range(1, 8)] + [(date(2026, 11, 8), 88.3)]
        result = goal.goal_progress(weighings(*days), 95.0, 80.0, 'abnehmen')
        # 7-day change 88.3 - 89.8 = -1.5 kg, 8.3 kg left.
        self.assertEqual(goal.finish_label(result), '6 Wochen')

    def test_progress_percent(self):
        result = goal.goal_progress(self.OCTOBER, 145.2, 80.0, 'abnehmen')
        self.assertEqual(result.percent, 32)
        self.assertAlmostEqual(result.total_change_kg, -20.6)

    def test_reached_and_gain(self):
        reached = goal.goal_progress(weighings((date(2026, 11, 6), 79.0)), 90.0, 80.0, 'abnehmen')
        self.assertTrue(reached.reached)
        self.assertEqual(reached.percent, 100)
        self.assertEqual(goal.finish_label(reached), 'Erreicht')
        gain = goal.goal_progress(weighings((date(2026, 10, 30), 71.6), (date(2026, 11, 6), 72.0)), 70.0, 80.0, 'muskelaufbau')
        self.assertEqual((gain.direction, gain.percent, goal.finish_label(gain)), ('gain', 20, '20 Wochen'))

    def test_duration_has_a_unit(self):
        self.assertEqual(goal.duration_label(1), '1 Woche')
        self.assertEqual(goal.duration_label(22.4), '22 Wochen')
        self.assertEqual(goal.duration_label(60), 'ca. 14 Monate')
        self.assertEqual(goal.duration_label(223), 'ca. 4 Jahre')


class ProgressCardsTests(TestCase):
    def setUp(self):
        from .models import Goal
        self.user = User.objects.create_user('anna', password='pw')
        self.client.force_login(self.user)
        UserData.objects.create(user=self.user, starting_weight_kg=Decimal('145.20'), height_cm=175, gender='maennlich')
        Goal.objects.create(user=self.user, goal_type='abnehmen', target_weight_kg=Decimal('80.00'))
        for day, kg, waist in ((date(2026, 10, 23), '124.30', '135.5'), (date(2026, 10, 30), '124.30', None),
                               (date(2026, 11, 6), '124.60', '134.5')):
            BodyMetricsEntry.objects.create(user=self.user, date=day, weight_kg=Decimal(kg),
                                            waist_cm=Decimal(waist) if waist else None)

    def test_weight_and_goal_cards(self):
        context = self.client.get(reverse('fortschritt')).context
        card = context['weight_card']
        self.assertEqual(card['last_change'], '+0,30')
        self.assertEqual(card['seven_change'], '+0,30')
        self.assertEqual(card['rating'].label, 'Hoch')
        self.assertEqual(card['finish'], '–')
        self.assertEqual(context['goal_card']['percent'], 32)
        self.assertEqual(context['goal_card']['change'], '20,60')
        self.assertEqual(context['goal_card']['change_label'], 'Gesamtabnahme')

    def test_measurement_table(self):
        table = self.client.get(reverse('fortschritt')).context['measurement_table']
        self.assertEqual(table['columns'], ['Bauch'])
        self.assertEqual(len(table['rows']), 2)
        newest = table['rows'][0]['cells'][0]
        self.assertEqual((newest['value'], newest['change'], newest['direction'], newest['trend']),
                         ('134,5', '−1,0', 'down', 'good'))
        self.assertNotIn('trend', table['rows'][1]['cells'][0])

    def test_without_goal(self):
        from .models import Goal
        Goal.objects.all().delete()
        response = self.client.get(reverse('fortschritt'))
        self.assertIsNone(response.context['goal_card'])
        self.assertIsNone(response.context['weight_card']['finish'])
        self.assertContains(response, 'Noch kein Ziel festgelegt')


class GoalTypeCardTests(TestCase):
    def setUp(self):
        from .models import Goal
        self.user = User.objects.create_user('anna', password='pw')
        self.client.force_login(self.user)
        UserData.objects.create(user=self.user, starting_weight_kg=Decimal('145.20'), height_cm=175, gender='maennlich')
        self.goal = Goal.objects.create(user=self.user, goal_type='abnehmen', target_weight_kg=Decimal('80.00'))
        BodyMetricsEntry.objects.create(user=self.user, date=date(2026, 10, 30), weight_kg=Decimal('124.30'),
                                        muscle_mass_kg=Decimal('71.85'), upper_arm_cm=Decimal('44.0'))
        BodyMetricsEntry.objects.create(user=self.user, date=date(2026, 11, 6), weight_kg=Decimal('124.60'),
                                        muscle_mass_kg=Decimal('72.02'), upper_arm_cm=Decimal('44.5'))

    def card(self, **changes):
        for name, value in changes.items():
            setattr(self.goal, name, value)
        self.goal.save()
        return self.client.get(reverse('fortschritt')).context['goal_card']

    def test_lose_weight(self):
        card = self.card()
        self.assertEqual((card['kind'], card['title'], card['percent']), ('weight', 'Körpergewicht verlieren', 32))

    def test_muscle_goal_follows_muscle_mass_not_weight(self):
        card = self.card(goal_type='muskelaufbau')
        self.assertEqual((card['kind'], card['title'], card['change'], card['trend']), ('muscle', 'Muskelaufbau', '+0,17', 'good'))
        self.assertIsNone(card['percent'])
        self.assertEqual(card['weight_target'], '80,00')
        card = self.card(target_muscle_mass_kg=Decimal('75.00'))
        self.assertEqual(card['percent'], 5)

    def test_muscle_goal_without_scale_uses_sizes(self):
        BodyMetricsEntry.objects.update(muscle_mass_kg=None)
        card = self.card(goal_type='muskelaufbau', target_weight_kg=None)
        self.assertEqual([(s['label'], s['change']) for s in card['sizes']], [('Oberarm', '+0,5')])

    def test_hold(self):
        card = self.card(goal_type='halten', target_weight_kg=Decimal('124.00'))
        self.assertEqual((card['kind'], card['inside'], card['deviation'], card['tolerance']), ('hold', True, '+0,60', '1,00'))
        self.assertEqual(card['since'], date(2026, 10, 30))
        card = self.card(weight_tolerance_kg=Decimal('0.5'))
        self.assertFalse(card['inside'])

    def test_strength_shows_hint(self):
        card = self.card(goal_type='kraft_aufbauen')
        self.assertEqual((card['kind'], card['title']), ('hint', 'Kraft aufbauen'))

    def test_no_finish_forecast_for_hold(self):
        self.card(goal_type='halten', target_weight_kg=Decimal('124.00'))
        self.assertIsNone(self.client.get(reverse('fortschritt')).context['weight_card']['finish'])


def image_upload(name='bild.jpg', size=(300, 400), exif=True):
    import io
    from PIL import Image
    buffer = io.BytesIO()
    image = Image.new('RGB', size, (200, 80, 60))
    data = Image.Exif()
    data[0x010F] = 'Handy'  # camera make, stands in for all metadata including GPS
    image.save(buffer, 'JPEG', exif=data.tobytes() if exif else b'')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


class PhotoTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user('anna', password='pw')
        self.other = User.objects.create_user('ben', password='pw')
        self.client.force_login(self.user)
        self.url = reverse('fortschritt-fotos-neu')
        self.today = timezone.localdate()

    def upload(self, **files):
        data = {'date': self.today.isoformat(), **files}
        return self.client.post(self.url, data)

    def test_upload_reencodes_and_strips_metadata(self):
        from PIL import Image
        from .models import ProgressPhoto
        response = self.upload(vorne=image_upload(size=(3000, 1500)), hinten=image_upload())
        self.assertRedirects(response, reverse('fortschritt') + '?tab=fotos')
        photos = ProgressPhoto.objects.filter(user=self.user)
        self.assertEqual(sorted(p.pose for p in photos), ['hinten', 'vorne'])
        front = photos.get(pose='vorne')
        self.assertTrue(front.image.name.startswith(f'private/progress_photos/{self.user.pk}/'))
        with Image.open(front.image.path) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (2000, 1000))
            self.assertEqual(len(image.getexif()), 0)

    def test_new_upload_replaces_photo_of_same_day_and_pose(self):
        import os
        from .models import ProgressPhoto
        self.upload(vorne=image_upload())
        old = ProgressPhoto.objects.get().image.path
        self.upload(vorne=image_upload())
        self.assertEqual(ProgressPhoto.objects.count(), 1)
        self.assertFalse(os.path.exists(old))

    def test_needs_a_photo_and_a_real_image(self):
        self.assertContains(self.upload(), 'mindestens ein Foto')
        response = self.upload(seite=SimpleUploadedFile('x.jpg', b'kein bild', content_type='image/jpeg'))
        self.assertContains(response, 'kein lesbares Bild')

    def test_only_the_owner_gets_the_file(self):
        from .models import ProgressPhoto
        self.upload(vorne=image_upload())
        photo = ProgressPhoto.objects.get()
        url = reverse('fortschritt-foto', args=[photo.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('no-store', response['Cache-Control'])
        response.close()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse('fortschritt-foto-loeschen', args=[photo.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_public_media_url_refuses_private_folder(self):
        from .models import ProgressPhoto
        self.upload(vorne=image_upload())
        name = ProgressPhoto.objects.get().image.name
        self.client.logout()
        for path in (name, name.replace('private', 'PRIVATE'), 'x/../' + name, 'private/', 'private'):
            self.assertEqual(self.client.get('/media/' + path).status_code, 404, path)

    def test_delete_removes_file(self):
        import os
        from .models import ProgressPhoto
        self.upload(vorne=image_upload())
        photo = ProgressPhoto.objects.get()
        path = photo.image.path
        response = self.client.post(reverse('fortschritt-foto-loeschen', args=[photo.pk]))
        self.assertRedirects(response, reverse('fortschritt') + '?tab=fotos')
        self.assertFalse(ProgressPhoto.objects.exists())
        self.assertFalse(os.path.exists(path))

    def test_gallery_shows_only_own_photos(self):
        from .models import ProgressPhoto
        self.upload(vorne=image_upload())
        theirs = ProgressPhoto(user=self.other, date=self.today, pose='vorne')
        theirs.image.save('x.jpg', image_upload())
        response = self.client.get(reverse('fortschritt'), {'tab': 'fotos'})
        mine = ProgressPhoto.objects.get(user=self.user)
        self.assertContains(response, reverse('fortschritt-foto', args=[mine.pk]))
        self.assertNotContains(response, reverse('fortschritt-foto', args=[theirs.pk]))
        self.assertEqual(response.context['initial_tab'], 'fotos')
