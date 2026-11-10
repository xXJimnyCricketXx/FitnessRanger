// Pure formulas for the tools page. No DOM access, so they can be tested with `node --test`.
(function (exports) {
  var KG_PER_LB = 0.45359237;
  var CM_PER_INCH = 2.54;
  var ACTIVITY = { nicht_aktiv: 1.2, leicht_aktiv: 1.375, maessig_aktiv: 1.55, sehr_aktiv: 1.725, extrem_aktiv: 1.9 };
  var GOAL_KCAL = { abnehmen: 0.8, muskelaufbau: 1.1, kraft_aufbauen: 1.05, halten: 1 };
  var GOAL_PROTEIN = { abnehmen: 2, muskelaufbau: 1.8, kraft_aufbauen: 1.8, halten: 1.6 };
  var ONE_RM_PERCENTS = [100, 95, 90, 85, 80, 75, 70, 65, 60];
  var HEART_ZONES = [[50, 60], [60, 70], [70, 80], [80, 90], [90, 100]];

  function bmi(kg, cm) {
    return kg / Math.pow(cm / 100, 2);
  }

  function bmiCategory(value) {
    if (value < 18.5) return 'Untergewicht';
    if (value < 25) return 'Normalgewicht';
    if (value < 30) return 'Übergewicht';
    if (value < 35) return 'Adipositas Grad I';
    if (value < 40) return 'Adipositas Grad II';
    return 'Adipositas Grad III';
  }

  // Weight range for BMI 18.5 to 25, rounded inwards to 0.1 so both ends really are inside it.
  function normalWeightRange(cm, usesLb) {
    var squared = Math.pow(cm / 100, 2);
    var toUnit = function (kg) { return usesLb ? kg / KG_PER_LB : kg; };
    return [Math.ceil(toUnit(18.5 * squared) * 10) / 10, Math.floor(toUnit(25 * squared) * 10) / 10];
  }

  // Mifflin-St Jeor
  function basalKcal(gender, kg, cm, age) {
    return 10 * kg + 6.25 * cm - 5 * age + (gender === 'maennlich' ? 5 : -161);
  }

  function totalKcal(basal, activity) {
    var factor = ACTIVITY[activity];
    return factor ? Math.round(basal * factor) : null;
  }

  // Returns null when the calories do not cover protein and fat.
  function macros(kcal, kg, goal) {
    var target = kcal * GOAL_KCAL[goal];
    var protein = kg * GOAL_PROTEIN[goal];
    var fat = target * 0.25 / 9;
    var carbs = (target - protein * 4 - fat * 9) / 4;
    if (carbs < 0) return null;
    return { target: target, protein: protein, fat: fat, carbs: carbs };
  }

  // Brzycki, sensible for 1 to 12 whole repetitions.
  function oneRepMax(weight, reps) {
    return weight * 36 / (37 - reps);
  }

  function oneRepMaxTable(max, usesLb) {
    var step = usesLb ? 1 : 0.5;
    return ONE_RM_PERCENTS.map(function (percent) {
      return [percent, Math.round(max * percent / 100 / step) * step];
    });
  }

  // Tanaka
  function maxHeartRate(age) {
    return 208 - 0.7 * age;
  }

  // Karvonen when a resting pulse is given, otherwise plain percentages of the maximum.
  function heartZones(max, rest) {
    return HEART_ZONES.map(function (zone) {
      return zone.map(function (percent) {
        return rest !== null && rest !== undefined ? rest + (max - rest) * percent / 100 : max * percent / 100;
      });
    });
  }

  // US Navy method, all lengths in cm.
  function navyBodyFat(gender, cm, neck, waist, hip) {
    if (gender === 'maennlich') {
      return 495 / (1.0324 - 0.19077 * Math.log10(waist - neck) + 0.15456 * Math.log10(cm)) - 450;
    }
    return 495 / (1.29579 - 0.35004 * Math.log10(waist + hip - neck) + 0.221 * Math.log10(cm)) - 450;
  }

  // WHO limits for the waist circumference in cm.
  function waistRisk(gender, waist) {
    var limits = gender === 'maennlich' ? [94, 102] : [80, 88];
    if (waist < limits[0]) return 'Nicht erhöht';
    return waist < limits[1] ? 'Erhöht' : 'Deutlich erhöht';
  }

  exports.KG_PER_LB = KG_PER_LB;
  exports.CM_PER_INCH = CM_PER_INCH;
  exports.bmi = bmi;
  exports.bmiCategory = bmiCategory;
  exports.normalWeightRange = normalWeightRange;
  exports.basalKcal = basalKcal;
  exports.totalKcal = totalKcal;
  exports.macros = macros;
  exports.oneRepMax = oneRepMax;
  exports.oneRepMaxTable = oneRepMaxTable;
  exports.maxHeartRate = maxHeartRate;
  exports.heartZones = heartZones;
  exports.navyBodyFat = navyBodyFat;
  exports.waistRisk = waistRisk;
})(typeof module !== 'undefined' ? module.exports : (window.ToolsCalc = {}));
