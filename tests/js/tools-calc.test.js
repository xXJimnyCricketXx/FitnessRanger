// Run with: node --test "tests/js/*.test.js"
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const calc = require(path.join(__dirname, '..', '..', 'static', 'js', 'tools-calc.js'));

function near(actual, expected, tolerance = 0.05) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} is not within ${tolerance} of ${expected}`);
}

test('BMI value', () => {
  near(calc.bmi(70, 175), 22.86, 0.01);
  near(calc.bmi(100, 180), 30.86, 0.01);
});

test('BMI classes follow the WHO limits', () => {
  assert.equal(calc.bmiCategory(18.49), 'Untergewicht');
  assert.equal(calc.bmiCategory(18.5), 'Normalgewicht');
  assert.equal(calc.bmiCategory(24.99), 'Normalgewicht');
  assert.equal(calc.bmiCategory(25), 'Übergewicht');
  assert.equal(calc.bmiCategory(29.99), 'Übergewicht');
  assert.equal(calc.bmiCategory(30), 'Adipositas Grad I');
  assert.equal(calc.bmiCategory(35), 'Adipositas Grad II');
  assert.equal(calc.bmiCategory(40), 'Adipositas Grad III');
});

test('normal weight range in kg is rounded inwards', () => {
  assert.deepEqual(calc.normalWeightRange(175, false), [56.7, 76.5]);
  const [low, high] = calc.normalWeightRange(175, false);
  assert.ok(calc.bmi(low, 175) >= 18.5);
  assert.ok(calc.bmi(high, 175) < 25);
});

test('normal weight range in lb for 5 ft 9 in', () => {
  assert.deepEqual(calc.normalWeightRange(69 * calc.CM_PER_INCH, true), [125.3, 169.2]);
});

test('basal metabolic rate after Mifflin-St Jeor', () => {
  assert.equal(calc.basalKcal('maennlich', 80, 180, 30), 1780);
  assert.equal(calc.basalKcal('weiblich', 60, 165, 25), 1345.25);
});

test('total calories use the activity factor', () => {
  assert.equal(calc.totalKcal(1780, 'nicht_aktiv'), 2136);
  assert.equal(calc.totalKcal(1780, 'maessig_aktiv'), 2759);
  assert.equal(calc.totalKcal(1780, ''), null);
});

test('macros for keeping the weight', () => {
  const result = calc.macros(2500, 80, 'halten');
  assert.equal(result.target, 2500);
  assert.equal(result.protein, 128);
  near(result.fat, 69.44, 0.01);
  near(result.carbs, 340.75, 0.01);
  near(result.protein * 4 + result.fat * 9 + result.carbs * 4, result.target, 0.001);
});

test('macros change the calories per goal', () => {
  assert.equal(calc.macros(2500, 80, 'abnehmen').target, 2000);
  near(calc.macros(2500, 80, 'muskelaufbau').target, 2750, 0.001);
  near(calc.macros(2500, 80, 'kraft_aufbauen').target, 2625, 0.001);
  assert.equal(calc.macros(2500, 80, 'abnehmen').protein, 160);
});

test('macros return null when calories are too low', () => {
  assert.equal(calc.macros(800, 100, 'abnehmen'), null);
});

test('one rep max after Brzycki', () => {
  assert.equal(calc.oneRepMax(100, 1), 100);
  near(calc.oneRepMax(100, 10), 133.33, 0.01);
});

test('one rep max table rounds to 0.5 kg or 1 lb', () => {
  const kg = calc.oneRepMaxTable(calc.oneRepMax(100, 10), false);
  assert.equal(kg.length, 9);
  assert.deepEqual(kg[0], [100, 133.5]);
  assert.deepEqual(kg[1], [95, 126.5]);
  const lb = calc.oneRepMaxTable(calc.oneRepMax(100, 10), true);
  assert.deepEqual(lb[1], [95, 127]);
});

test('maximum heart rate after Tanaka', () => {
  assert.equal(calc.maxHeartRate(30), 187);
  assert.equal(calc.maxHeartRate(50), 173);
});

test('heart rate zones without and with resting pulse', () => {
  const plain = calc.heartZones(200, null);
  assert.equal(plain.length, 5);
  assert.deepEqual(plain[0], [100, 120]);
  assert.deepEqual(plain[4], [180, 200]);
  const karvonen = calc.heartZones(200, 60);
  assert.deepEqual(karvonen[0], [130, 144]);
  assert.deepEqual(karvonen[4], [186, 200]);
});

// Reference values from the inch version of the Navy formula.
test('body fat after the Navy method', () => {
  near(calc.navyBodyFat('maennlich', 180, 38, 85), 16.1, 0.5);
  near(calc.navyBodyFat('weiblich', 165, 32, 75, 95), 27.7, 0.5);
});

test('waist risk limits for men', () => {
  assert.equal(calc.waistRisk('maennlich', 93.9), 'Nicht erhöht');
  assert.equal(calc.waistRisk('maennlich', 94), 'Erhöht');
  assert.equal(calc.waistRisk('maennlich', 101.9), 'Erhöht');
  assert.equal(calc.waistRisk('maennlich', 102), 'Deutlich erhöht');
});

test('waist risk limits for women', () => {
  assert.equal(calc.waistRisk('weiblich', 79.9), 'Nicht erhöht');
  assert.equal(calc.waistRisk('weiblich', 80), 'Erhöht');
  assert.equal(calc.waistRisk('weiblich', 87.9), 'Erhöht');
  assert.equal(calc.waistRisk('weiblich', 88), 'Deutlich erhöht');
});

test('a waist of 37 in is just below the limit for men', () => {
  assert.equal(calc.waistRisk('maennlich', 37 * calc.CM_PER_INCH), 'Nicht erhöht');
  assert.equal(calc.waistRisk('maennlich', 37.01 * calc.CM_PER_INCH), 'Erhöht');
});
