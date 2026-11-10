(function () {
  var root = document.getElementById('tools');
  var defaults = JSON.parse(document.getElementById('toolDefaults').textContent);
  var usesLb = root.dataset.weightUnit === 'lb';
  var usesInches = root.dataset.lengthUnit === 'ft_in';
  var weightUnit = root.dataset.weightUnit;

  var calc = window.ToolsCalc;
  var KG_PER_LB = calc.KG_PER_LB;
  var CM_PER_INCH = calc.CM_PER_INCH;
  var ONE_RM_REPS = ['1', '2', '4', '6', '8', '10', '12', '15', '20'];
  var HEART_ZONE_NAMES = ['Regeneration', 'Grundlagenausdauer', 'Aerob', 'Anaerob', 'Maximal'];
  var HEART_ZONE_PERCENTS = ['50 bis 60 %', '60 bis 70 %', '70 bis 80 %', '80 bis 90 %', '90 bis 100 %'];

  function el(id) { return document.getElementById(id); }

  function num(id) {
    var field = el(id);
    if (!field || field.value === '') return null;
    var value = parseFloat(field.value);
    return isNaN(value) ? null : value;
  }

  function positive(id) {
    var value = num(id);
    return value !== null && value > 0 ? value : null;
  }

  function format(value, digits) {
    return value.toLocaleString('de-DE', { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 });
  }

  function weightKg(id) {
    var value = positive(id + '-weight');
    if (value === null) return null;
    return usesLb ? value * KG_PER_LB : value;
  }

  function heightCm(id) {
    if (!usesInches) return positive(id + '-height-cm');
    var feet = num(id + '-height-ft') || 0;
    var inches = num(id + '-height-in') || 0;
    var total = feet * 12 + inches;
    return total > 0 ? total * CM_PER_INCH : null;
  }

  function lengthCm(id) {
    var value = positive(id);
    if (value === null) return null;
    return usesInches ? value * CM_PER_INCH : value;
  }

  function show(id, html) {
    var box = el(id);
    box.innerHTML = html || '';
    box.classList.toggle('active', Boolean(html));
  }

  function stat(label, value, note) {
    return '<div class="tool-stat"><span class="tool-stat-label">' + label + '</span>'
      + '<span class="tool-stat-value">' + value + '</span>'
      + (note ? '<span class="tool-stat-note">' + note + '</span>' : '') + '</div>';
  }

  function table(headers, rows) {
    var head = headers.map(function (h) { return '<th>' + h + '</th>'; }).join('');
    var body = rows.map(function (row) {
      return '<tr>' + row.map(function (cell) { return '<td>' + cell + '</td>'; }).join('') + '</tr>';
    }).join('');
    return '<div class="table-wrap"><table class="data-table"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function calcBmi() {
    var kg = weightKg('bmi');
    var cm = heightCm('bmi');
    if (kg === null || cm === null) return show('bmi-result');
    var bmi = calc.bmi(kg, cm);
    var range = calc.normalWeightRange(cm, usesLb);
    show('bmi-result', stat('Dein BMI', format(bmi, 1), calc.bmiCategory(bmi))
      + stat('Normalgewicht bei deiner Größe', format(range[0], 1) + ' bis ' + format(range[1], 1) + ' ' + weightUnit));
  }

  var calculatedKcal = null;

  function calcCalories() {
    var gender = el('kcal-gender').value;
    var age = positive('kcal-age');
    var kg = weightKg('kcal');
    var cm = heightCm('kcal');
    calculatedKcal = null;
    if (!gender || age === null || kg === null || cm === null) return show('kcal-result');
    var bmr = calc.basalKcal(gender, kg, cm, age);
    var html = stat('Grundumsatz', format(bmr) + ' kcal');
    calculatedKcal = calc.totalKcal(bmr, el('kcal-activity').value);
    if (calculatedKcal !== null) html += stat('Gesamtumsatz pro Tag', format(calculatedKcal) + ' kcal');
    show('kcal-result', html);
  }

  var macroKcalTouched = false;

  function calcMacros() {
    if (!macroKcalTouched) el('macro-kcal').value = calculatedKcal === null ? '' : calculatedKcal;
    var kcal = positive('macro-kcal');
    var kg = weightKg('macro');
    var goal = el('macro-goal').value;
    if (kcal === null || kg === null || !goal) return show('macro-result');
    var result = calc.macros(kcal, kg, goal);
    if (result === null) return show('macro-result', '<p class="settings-error">Die Kalorien reichen für diese Eiweiß- und Fettmenge nicht aus. Bitte prüfe deine Eingaben.</p>');
    show('macro-result', stat('Kalorienziel', format(result.target) + ' kcal')
      + stat('Eiweiß', format(result.protein) + ' g')
      + stat('Fett', format(result.fat) + ' g')
      + stat('Kohlenhydrate', format(result.carbs) + ' g'));
  }

  function calcOneRm() {
    var weight = positive('orm-weight');
    var reps = positive('orm-reps');
    if (weight === null || reps === null) return show('orm-result');
    if (reps > 12 || reps !== Math.floor(reps)) {
      return show('orm-result', '<p class="settings-error">Die Formel ist nur für 1 bis 12 ganze Wiederholungen sinnvoll.</p>');
    }
    var max = calc.oneRepMax(weight, reps);
    var rows = calc.oneRepMaxTable(max, usesLb).map(function (row, index) {
      return [row[0] + ' %', format(row[1], usesLb ? 0 : 1) + ' ' + weightUnit, 'ca. ' + ONE_RM_REPS[index]];
    });
    show('orm-result', stat('Geschätztes 1RM', format(max, 1) + ' ' + weightUnit) + table(['Anteil', 'Gewicht', 'Wiederholungen'], rows));
  }

  function calcHeart() {
    var age = positive('hr-age');
    var ownMax = positive('hr-max');
    var rest = positive('hr-rest');
    if (ownMax === null && age === null) return show('hr-result');
    var max = ownMax !== null ? ownMax : calc.maxHeartRate(age);
    if (rest !== null && rest >= max) {
      return show('hr-result', '<p class="settings-error">Der Ruhepuls muss unter dem Maximalpuls liegen.</p>');
    }
    var rows = calc.heartZones(max, rest).map(function (range, index) {
      return [HEART_ZONE_NAMES[index], HEART_ZONE_PERCENTS[index], format(range[0]) + ' bis ' + format(range[1]) + ' bpm'];
    });
    show('hr-result', stat('Maximalpuls', format(max) + ' bpm', ownMax !== null ? 'Dein eigener Wert' : 'Geschätzt') + table(['Zone', 'Anteil', 'Puls'], rows));
  }

  function calcBodyFat() {
    var gender = el('bf-gender').value;
    el('bf-hip-field').style.display = gender === 'maennlich' ? 'none' : '';
    var cm = heightCm('bf');
    var neck = lengthCm('bf-neck');
    var waist = lengthCm('bf-waist');
    var hip = lengthCm('bf-hip');
    var risk = gender && waist !== null ? stat('Risiko laut Bauchumfang', calc.waistRisk(gender, waist)) : '';
    if (!gender || cm === null || neck === null || waist === null) return show('bf-result', risk);
    if (gender === 'maennlich') {
      if (waist <= neck) return show('bf-result', '<p class="settings-error">Der Bauchumfang muss größer sein als der Halsumfang.</p>');
    } else {
      if (hip === null) return show('bf-result', risk);
      if (waist + hip <= neck) return show('bf-result', '<p class="settings-error">Bitte prüfe die Umfänge.</p>');
    }
    var value = calc.navyBodyFat(gender, cm, neck, waist, hip);
    if (value <= 0 || value >= 75) return show('bf-result', '<p class="settings-error">Dieses Ergebnis ist nicht plausibel. Bitte prüfe die Umfänge.</p>');
    show('bf-result', stat('Geschätzter Körperfettanteil', format(value, 1) + ' %') + risk);
  }

  function calcAll() {
    calcBmi();
    calcCalories();
    calcMacros();
    calcOneRm();
    calcHeart();
    calcBodyFat();
  }

  function setValue(field, value) {
    if (field && value !== null && value !== undefined && value !== '') field.value = value;
  }

  function prefill() {
    if (defaults.weight_kg !== null) {
      var weight = usesLb ? defaults.weight_kg / KG_PER_LB : defaults.weight_kg;
      root.querySelectorAll('[data-weight]').forEach(function (field) { field.value = Math.round(weight * 10) / 10; });
    }
    if (defaults.height_cm !== null) {
      ['bmi', 'kcal', 'bf'].forEach(function (id) {
        if (!usesInches) return setValue(el(id + '-height-cm'), defaults.height_cm);
        var totalInches = Math.round(defaults.height_cm / CM_PER_INCH);
        setValue(el(id + '-height-ft'), Math.floor(totalInches / 12));
        setValue(el(id + '-height-in'), totalInches % 12);
      });
    }
    root.querySelectorAll('[data-age]').forEach(function (field) { setValue(field, defaults.age); });
    root.querySelectorAll('[data-gender]').forEach(function (field) { setValue(field, defaults.gender); });
    setValue(el('kcal-activity'), defaults.activity);
    setValue(el('macro-goal'), defaults.goal);
  }

  root.addEventListener('input', function (event) {
    if (event.target.id === 'macro-kcal') macroKcalTouched = event.target.value !== '';
    calcAll();
  });
  root.addEventListener('change', calcAll);

  prefill();
  calcAll();
})();
