/* What the Details drawer says about the three distillation cards of the benchmark catalogue
 * (`distill-pysr`, `distill-triangle`, `distill-curves`), the training report's numbers.
 *
 * The contract of models_notes.js and xgb_notes.js: each builder takes `{ payload, state, experiment,
 * title, card, species, task, angleScale, palette, panelState }` and returns `{ title, hazards, sections }`
 * in the four standard sections (Selection / What is drawn / Disclosures / Marks and legend), then the
 * card's own headings, so every number on the card can be quoted from the drawer.
 *
 * The builders read the panels' own pure models (`pysrModel`, `triangleModel`, `curvesModel`), so the
 * drawer never says what the picture does not show; `panelState` is the card's own state (the PySR
 * chips' highlight, the curves' slider values), passed by ModelsSection from the panel's `notesState()`.
 *
 * Every card's hazards include "no interval reported" (Martin's recorded exception, 2026-11-05: the
 * report gives point estimates only; nothing is derived), and "label leakage" wherever a leak flag of the
 * report (F8) is drawn. The Selection section names the report, the species and task shown, and says the
 * selection and the experiment do not apply.
 */

import { Notes, SECTION } from './panel_notes.js';
import { formatInt, formatNumber } from './scale.js';
import { LEAK_TEXT, NOT_A_PHYSICAL_LAW, TIER_LABELS, thresholdText } from './catalog/gating.js';
import { printed, PROTON_SIGNAL_MIN_R2_GAP } from './catalog/select.js';
import { pysrModel, TIER_BORDERS, highlightStatus, FORMULA_FIT, R2_PYSR } from './panels/pysr_matrix.js';
import {
  triangleModel, R2_MEASURES, MAE_MEASURES, N_NOT_REPORTED, POINT_ESTIMATE, protonValidationN, protonTreeN,
  reportedWithUnit, SEGMENTATION_MAE_SCOPE,
} from './panels/distill_triangle.js';
import {
  curvesModel, SPECIES_GLYPH, TIER_STROKE, LABEL_SHIFT_MAX_LINES, BAND_SHIFT_MAX,
} from './panels/distill_curves.js';

/** The drawer titles by card id; the shell's card title wins when it passes one. */
export const DISTILL_TITLES = Object.freeze({
  'distill-pysr': 'PySR Formulas and Top Features',
  'distill-triangle': 'Distillation Fidelity — Tree, Formula and Network',
  'distill-curves': 'Distilled Energy Response p̂(E_sum)',
});

/** The headings the catalogue cards add after the four standard ones. */
export const DISTILL_HEADINGS = Object.freeze({
  tiers: 'Tiers',
  values: 'Values in force',
  rows: 'Rows',
});

/** The hazard every catalogue card carries (Martin's recorded exception). */
export const NO_INTERVAL = 'no interval reported';
/** The hazard of a card that draws a leak flag of the report (F8). */
export const LABEL_LEAKAGE = 'label leakage';

/** The hazard of a card that draws a tree beating its network on the truth. */
export const LEAKAGE_SIGNAL = 'leakage signal';

/** The recorded exception, as one disclosure line. */
export const EXCEPTION_LINE = 'Recorded exception (Martin, 2026-11-05): the training report prints point estimates only, so every '
  + 'number is drawn as reported and printed with the report\'s own decimals (1.000 stays 1.000), each mark names its N or says it is not reported, no interval is fabricated or '
  + `derived, and differences smaller than the report's rounding are not resolved (${POINT_ESTIMATE}).`;

const t = (v) => thresholdText(v);
const list = (items) => items.filter(Boolean).join(', ');

/** The Selection lines every catalogue card opens with. */
export function catalogSelection(payload, { task = null, allTasks = false } = {}) {
  const labels = payload?.speciesLabels ?? {};
  const species = (payload?.species ?? []).map((s) => labels[s] ?? s);
  const taskLabel = payload?.taskLabels?.[task ?? payload?.task] ?? task ?? payload?.task;
  return [
    payload?.provenance ?? 'From the training report (models_performance.md): documented point estimates, no intervals reported; the selection and the experiment do not apply.',
    `Species shown: ${species.length > 1 ? `${list(species)} (Compare all)` : list(species)}.`,
    allTasks ? 'Every task (segmentation, angle and energy) in every frame, whatever task the bench bar shows.'
      : `Task: ${taskLabel}.`,
    'The filter selection and the experiment do not apply: these are the report\'s numbers, not the data on screen.',
  ];
}

/* --------------------------------------------------------------- PySR -- */

/** The drawer of the PySR matrix. */
export function pysrNotes({ payload, title = null, panelState = null } = {}) {
  if (!payload) return null;
  const model = pysrModel(payload, { highlight: panelState?.highlight ?? null });
  const notes = new Notes(title ?? DISTILL_TITLES['distill-pysr']);
  if (!model) {
    notes.section(SECTION.disclosures, ['This payload carries no formulas.', EXCEPTION_LINE]);
    return notes.done([NO_INTERVAL]);
  }
  notes.section(SECTION.selection, catalogSelection(payload, { allTasks: true }));
  const th = model.thresholds;
  notes.section(SECTION.drawn, [
    `A ${formatInt(model.tasks.length)} × ${formatInt(model.frames.length)} matrix: tasks are rows, frames are columns (Absolute, Per-shower translated, Local)${model.compare ? '; under Compare all each cell stacks the four species' : ''}.`,
    `Each entry gives the PySR formula as native MathML with its LaTeX source and a Copy button, ${R2_PYSR} (the formula's fidelity to the network's own validation predictions, not to the truth), the network's R² to the truth where the report prints one, the tier and its reason, the badges and the tree's top features as chips; on the new species' angle models, the formula's own MAE to the true angle beside the network's, from the report's angle table.`,
    `${formatInt(model.entries.length)} models shown: ${Object.entries(model.counts).map(([k, n]) => `${formatInt(n)} ${model.tierLabels[k] ?? k}`).join(', ')}.`,
    model.highlight ? highlightStatus(model) : 'No feature is highlighted.',
  ]);
  const disclosures = [EXCEPTION_LINE,
    `${N_NOT_REPORTED} for ${R2_PYSR}. The network's R² to truth is the accuracy table's, on its validation sample: ${protonValidationN()} for the proton; 4,000 validation combined events for the other species (8,000 particles, derived as two per event).`];
  disclosures.push(`Tier rules (catalog/gating.js): a law candidate needs ${R2_PYSR} ≥ ${t(th.lawMinPysrR2 ?? 0.75)} and the network's R² to truth ≥ ${t(th.lawMinNetR2 ?? 0.7)}, in physical units with no leak flag; ${R2_PYSR} ≥ ${t(th.lawMinPysrR2 ?? 0.75)} without a reported truth R² is "High fidelity, truth R² not reported"; ${t(th.partialMinPysrR2 ?? 0.25)} ≤ ${R2_PYSR} < ${t(th.lawMinPysrR2 ?? 0.75)}, or a high-fidelity formula capped by a leak flag or by standardised features, is a partial surrogate; anything lower, "< 0", "≈ 0", no formula, or a network whose R² to truth is below ${t(th.lawMinNetR2 ?? 0.7)} is not a law.`);
  disclosures.push(`A law candidate is not a law: the report says "${NOT_A_PHYSICAL_LAW}", and the rule bounds the formula's fidelity to the network and the network's to the truth, not the formula's own fit to the truth. Where the report's angle table gives that fit, it is printed beside the tier.`);
  const fvn = model.entries.filter((e) => e.formulaVsNet);
  if (fvn.length) disclosures.push(`The formula's own MAE to the true angle, beside the network's (the report's angle table): ${fvn.map((e) => `${e.speciesLabel} ${payload.frameLabels?.[e.frame] ?? e.frame}: formula ${printed(e.formulaVsNet.formulaMae, e.formulaVsNet.dp.formulaMae)} ${e.formulaVsNet.unit}, network ${printed(e.formulaVsNet.netMae, e.formulaVsNet.dp.netMae)} ${e.formulaVsNet.unit} (${e.tierLabel})`).join('; ')}.`);
  disclosures.push('Qualified values keep their qualifiers as the report prints them ("< 0" with no number, "≈ 0", "no meaningful formula"); none is coerced to a number (F9).');
  const absent = model.entries.filter((e) => e.absent);
  if (absent.length) disclosures.push(`No meaningful formula (said in place, the printed R² kept): ${absent.map((e) => `${e.speciesLabel} ${payload.taskLabels?.[e.task] ?? e.task} ${payload.frameLabels?.[e.frame] ?? e.frame} (${R2_PYSR} ${e.r2Text})`).join('; ')}.`);
  const negative = model.entries.filter((e) => e.negative);
  if (negative.length) disclosures.push(`R² < 0 (worse than predicting the mean): ${negative.map((e) => `${e.speciesLabel} ${payload.taskLabels?.[e.task] ?? e.task} ${payload.frameLabels?.[e.frame] ?? e.frame} (${e.r2Text === '< 0' ? 'reported only as < 0' : e.r2Text})`).join('; ')}.`);
  if (model.entries.some((e) => e.units === 'standardised')) disclosures.push('The report: the segmentation formulas use standardised voxel features, so their coefficients carry no physical unit; such a formula is at most a partial surrogate.');
  const flags = [...new Set(model.entries.flatMap((e) => e.leaks))];
  for (const flag of flags) disclosures.push(`Label leakage (F8), on ${model.entries.filter((e) => e.leaks.includes(flag)).length} entries: ${LEAK_TEXT[flag] ?? flag}`);
  if (model.entries.some((e) => e.caveats.includes('oracle-separation'))) disclosures.push(`A caveat on every angle and energy formula, not a tier cap: ${LEAK_TEXT['oracle-separation']}`);
  if (model.entries.some((e) => e.featureMapInferred)) disclosures.push('The proton\'s formulas are printed with Hungarian variable names; their English keys (n_voxels, centroid_theta, centroid_r) are mapped by inference, which the report does not state; the badge and the chips\' titles say so.');
  const inferred = Object.entries(model.features).filter(([, f]) => f?.inferred).map(([k]) => k);
  if (inferred.length) disclosures.push(`Feature names mapped from the report's Hungarian by inference: ${inferred.join(', ')}.`);
  const undefinedKeys = Object.entries(model.features).filter(([, f]) => !f?.definition).map(([k]) => k);
  if (undefinedKeys.length) disclosures.push(`Defined only in the report's distill/surrogate.json, which is not shipped: ${undefinedKeys.join(', ')}.`);
  const fit = FORMULA_FIT;
  disclosures.push(`Long formulas are set smaller, never cut, by measurement: each starts at ${formatInt(fit.normal.px)} px and, while wider than its cell, steps down to ${formatInt(fit.compact.px)} px and then to ${formatInt(fit.floor.px)} px, the floor. Only a formula still wider than its cell at the floor scrolls sideways inside its own box (a visible scrollbar, a "scroll sideways" hint under it, and a keyboard stop), never the page.`);
  const byId = new Map(model.entries.map((e) => [e.id, e]));
  const scrolling = (panelState?.scrolling ?? []).map((id) => byId.get(id)).filter(Boolean);
  if (scrolling.length) {
    disclosures.push(`Scrolling sideways at the card's current width: ${scrolling.map((e) => `${e.speciesLabel} ${payload.taskLabels?.[e.task] ?? e.task} ${payload.frameLabels?.[e.frame] ?? e.frame}`).join('; ')}.`);
  }
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    `Border: ${Object.entries(TIER_BORDERS).map(([k, b]) => `${model.tierLabels[k] ?? k} ${b}`).join(', ')}; "Not a law" also in muted ink. The tier is always written in its chip, never carried by colour alone.`,
    'Badges: "standardised voxel features", "label leakage" (its title gives the report\'s caveat), "R² < 0", "names mapped by inference" (the proton\'s Hungarian variable names; not on a formula whose names the report prints in English).',
    'A feature chip highlights every model whose tree features or formula variables use it; the chip\'s title gives its definition where the report gives one.',
    'The column heads carry their frame\'s hue as on every catalogue card; nothing else here is coloured by data.',
  ]);
  notes.section(DISTILL_HEADINGS.tiers, model.entries.map((e) => `${e.speciesLabel} · ${payload.taskLabels?.[e.task] ?? e.task} · ${payload.frameLabels?.[e.frame] ?? e.frame}: ${e.tierLabel} — ${e.reasons.join(' ')}${e.formulaVsNet ? ` ${e.formulaVsNet.text}` : ''}`));
  const hazards = [NO_INTERVAL];
  if (flags.length) hazards.push(LABEL_LEAKAGE);
  return notes.done(hazards);
}

/* ------------------------------------------------------------ triangle -- */

/** The drawer of the distillation triangle. */
export function triangleNotes({ payload, title = null, task = null } = {}) {
  if (!payload) return null;
  const model = triangleModel(payload, { task });
  const notes = new Notes(title ?? DISTILL_TITLES['distill-triangle']);
  if (!model) {
    notes.section(SECTION.disclosures, ['This payload carries no rows.', EXCEPTION_LINE]);
    return notes.done([NO_INTERVAL]);
  }
  notes.section(SECTION.selection, catalogSelection(payload, { task: model.task }));
  const unit = model.unit ? ` [${model.unit}]` : '';
  notes.section(SECTION.drawn, [
    `One row per ${model.compare ? 'species and frame, grouped by species' : 'frame'} (${formatInt(model.rows.length)} rows).`,
    `Left: the R² fidelities on a fixed 0–1 axis, bars from zero — ${R2_MEASURES.map((m) => `${m.name} (${m.mark}: ${m.definition})`).join('; ')}.`,
    `Right: the MAE dumbbell on an axis from zero${unit} — ${MAE_MEASURES.filter((m) => m.key !== 'formula' || model.hasFormula).map((m) => `${m.name} (${m.mark})`).join(', ')}; the network's and the tree's MAE to truth are joined by a thin line.`,
    model.task === 'segmentation'
      ? `The segmentation MAEs are the ${SEGMENTATION_MAE_SCOPE.replace(/^MAE of /, 'MAEs of ')}, and are never drawn against it.`
      : (model.task === 'angle' ? 'The angle MAEs are in mrad: the distillation table gives radians, multiplied by 1000 here (F4) and printed with the triad\'s own digits (0.0216 rad is 21.6 mrad, 0.00046 rad is 0.46 mrad: three decimals fewer, no precision added); the formula MAEs come from the report\'s angle table, already in mrad.' : 'The energy MAEs are in GeV, as the report prints them.'),
  ]);
  const disclosures = [EXCEPTION_LINE];
  const proton = model.rows.filter((r) => r.species === 'proton');
  disclosures.push(`${N_NOT_REPORTED} for the distillation numbers of the muon, the electron and the pion, and for every ${R2_PYSR}.${proton.length ? ` The proton's tree R² (to the network and to the truth): ${protonTreeN(model.task)}.` : ''}${proton.some((r) => r.maeSource?.netTruth === 'accuracy') ? ` The proton's network MAE is the accuracy table's validation MAE: ${protonValidationN()}.` : ''}`);
  for (const c of model.clamped) {
    const row = model.rows[c.index];
    const m = R2_MEASURES.find((x) => x.key === c.measure);
    disclosures.push(`${row.label}: ${m.name} ${c.text}; drawn at 0 with the "R² < 0" mark (worse than predicting the mean).`);
  }
  const approx = model.rows.flatMap((row) => R2_MEASURES.filter((m) => row.r2[m.key]?.approx).map((m) => `${row.label} ${m.name} ≈ ${printed(row.r2[m.key].q.value, row.r2[m.key].q.dp)}`));
  if (approx.length) disclosures.push(`Reported as approximate (F9), drawn at the value and labelled: ${approx.join('; ')}.`);
  const absent = model.rows.filter((r) => r.formulaAbsent);
  if (absent.length) disclosures.push(`No meaningful formula, the printed R² kept (outline dashed): ${absent.map((r) => r.label).join(', ')}.`);
  for (const row of model.signalRows) disclosures.push(`${row.label}: ${row.leakSignalText} Never read it as a better model.`);
  if (model.signalRows.some((r) => r.species === 'proton')) disclosures.push(`The proton's leakage signal is the dashboard's rule, a drawing choice: the report gives no tree MAEs for it, so its tree's R² to the truth is compared with its R² to the network, and a lead of more than ${printed(PROTON_SIGNAL_MIN_R2_GAP, 1)} is flagged. The report's own indecision finding is the other reading, given in the row.`);
  for (const row of model.beatsRows) disclosures.push(`${row.label}: ${row.treeBeatsNetworkText} No badge and no hazard: a leakage signal is judged on the segmentation rows only.`);
  const flags = [...new Set(model.rows.flatMap((r) => r.leaks))];
  for (const flag of flags) disclosures.push(`Label leakage (F8) on ${model.rows.filter((r) => r.leaks.includes(flag)).map((r) => r.label).join(', ')}: ${LEAK_TEXT[flag] ?? flag}`);
  if (model.task !== 'segmentation') disclosures.push(`A caveat on every angle and energy number: ${LEAK_TEXT['oracle-separation']}`);
  const missing = [...new Set(model.rows.flatMap((r) => r.missing))];
  disclosures.push(...missing);
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Colour is the frame (E2\'s hues, the same on every catalogue card); the measure is told apart by fill and shape: solid bar, outlined bar, tick; filled circle, hollow circle, hollow square (a little below the line), filled diamond (a little above).',
    'The column at the right prints each row\'s flags as text, in the warning ink with ⚑: "label leakage" where the report flags its own leakage and "leakage signal" where, on a segmentation row, the tree fitted to truth beats the network on truth. An angle or energy row where the tree\'s printed MAE to truth is below the network\'s carries no flag: the two MAEs are drawn and the tooltip gives the gap.',
    `Every tooltip names the quantity, its unit, the N ("${N_NOT_REPORTED}" or the accuracy table's sample) and "${POINT_ESTIMATE}".`,
  ]);
  notes.section(DISTILL_HEADINGS.rows, model.rows.map((r) => {
    const r2 = R2_MEASURES.map((m) => `${m.name} ${r.r2[m.key] ? r.r2[m.key].text : 'not reported'}`).join('; ');
    const mae = MAE_MEASURES.filter((m) => r.mae[m.key] !== null).map((m) => `${m.name} ${reportedWithUnit(r.mae[m.key], model.unit, r.maeDp?.[m.key])}`).join('; ');
    return `${r.label}: ${r2}${mae ? `; ${mae}` : '; no MAE in the report'}.`;
  }));
  const hazards = [NO_INTERVAL];
  if (flags.length) hazards.push(LABEL_LEAKAGE);
  if (model.signalRows.length) hazards.push(LEAKAGE_SIGNAL);
  return notes.done(hazards);
}

/* -------------------------------------------------------------- curves -- */

/** The drawer of the energy-response curves. */
export function curvesNotes({ payload, title = null, panelState = null, values = null } = {}) {
  if (!payload) return null;
  const model = curvesModel(payload, { values: panelState?.values ?? values ?? null });
  const notes = new Notes(title ?? DISTILL_TITLES['distill-curves']);
  if (!model) {
    notes.section(SECTION.disclosures, ['This payload carries no formulas.', EXCEPTION_LINE]);
    return notes.done([NO_INTERVAL]);
  }
  notes.section(SECTION.selection, [...catalogSelection(payload, { task: 'energy' }), 'The card draws the energy formulas whatever task the bench bar shows.']);
  const by = model.domain?.bySpecies ?? {};
  const setter = Object.entries(by).sort((a, b) => b[1].eSum - a[1].eSum)[0];
  notes.section(SECTION.drawn, [
    `p̂ [GeV] against E_sum [GeV], one facet per frame, for the ${formatInt(model.curves.length)} energy formulas in physical units; each curve is evaluated from the report's formula by a small parser (catalog/formula.js), never by eval.`,
    `x runs from 0 to ${formatNumber(model.xTop, 3)} GeV: ${model.ceiling.rule}${setter ? ` Here ${payload.speciesLabels?.[setter[0]] ?? setter[0]} sets it (${setter[1].reached === 'crossed' ? `its Absolute formula reaches ${formatNumber(model.yTop)} GeV at E_sum = ${formatNumber(setter[1].eSum, 3)} GeV` : `its formula ${setter[1].reached === 'at-origin' ? 'is at the ceiling already at E_sum = 0' : 'never reaches the ceiling below 10 GeV'}`}).` : ''}`,
    `y runs from 0 to the ${formatNumber(model.yTop)} GeV ceiling, a drawing choice: the top of the XGBoost aggregates' 0–20 GeV range; the report states no momentum range.`,
    ...model.curves.map((c) => `${c.speciesLabel} · ${c.frameLabel}: ${c.formulaText} — ${c.tierLabel} (${R2_PYSR} ${c.r2Text}; network R² to truth ${c.netR2Text}).`),
  ]);
  const disclosures = [EXCEPTION_LINE, `${N_NOT_REPORTED} for any formula.`];
  disclosures.push(`${model.note}`);
  if (model.clipped.length) {
    disclosures.push(`${formatInt(model.clipped.length)} of ${formatInt(model.curves.length)} curves leave the 0–${formatNumber(model.yTop)} GeV range and are clipped at the axis with ${formatInt(model.carets)} caret${model.carets === 1 ? '' : 's'} whose tooltips give the formula's own values: `
      + model.clipped.map((c) => `${c.speciesLabel} · ${c.frameLabel} (${c.runs.map((r) => `${r.dir === 'above' ? 'above' : 'below 0'} from E_sum ${formatNumber(r.from, 3)} GeV, reaching ${formatNumber(r.extreme, 3)} GeV`).join('; ')})`).join('; ') + '.');
  } else {
    disclosures.push(`Every curve stays inside 0–${formatNumber(model.yTop)} GeV.`);
  }
  for (const [species, w] of Object.entries(model.weakTruth)) disclosures.push(`${payload.speciesLabels?.[species] ?? species}: the curves ${w.text}; they are not a law of the physics.`);
  if (model.curves.some((c) => c.tier === 'law')) disclosures.push(`A law candidate is not a law: the report says "${NOT_A_PHYSICAL_LAW}".`);
  for (const c of model.curves.filter((x) => x.tier !== 'law')) disclosures.push(`${c.speciesLabel} · ${c.frameLabel}, ${c.tierLabel}: ${c.reasons.join(' ')}`);
  const unlabelled = (panelState?.unlabelled ?? []).map((k) => model.curves.find((c) => c.key === k)).filter(Boolean);
  if (unlabelled.length) disclosures.push(`At the card's current width ${formatInt(unlabelled.length)} curve${unlabelled.length === 1 ? '' : 's'} carry no direct label, every free place being further than the limit below; each is named by its species' end mark in the key: ${unlabelled.map((c) => `${c.speciesLabel} · ${c.frameLabel}`).join(', ')}.`);
  for (const x of payload.absentOrExcluded ?? []) disclosures.push(`${payload.speciesLabels?.[x.species] ?? x.species} · ${payload.frameLabels?.[x.frame] ?? x.frame} not drawn: ${x.reason}`);
  if (model.curves.some((c) => c.undefinedRuns.length)) disclosures.push('Part of a curve where its formula is undefined (a root or logarithm of a negative) is not drawn.');
  disclosures.push(`A caveat on every energy formula: ${LEAK_TEXT['oracle-separation']}`);
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Colour is the frame (E2\'s hues); each facet is one frame and says so in its title.',
    `Stroke is the tier: ${Object.entries(TIER_STROKE).filter(([k]) => model.tiers.includes(k)).map(([k, s]) => `${TIER_LABELS[k] ?? k} ${s.words}`).join('; ')}. A faded curve stays at 3:1 against the card.`,
    `Each curve ends in its species' mark with a direct label: ${model.species.map((s) => `${SPECIES_GLYPH[s] ?? ''} ${payload.speciesLabels?.[s] ?? s}`).join(', ')} (filled for a law candidate, hollow below it); species are never a second hue.`,
    `A direct label sits where its curve ends (in the gutter right of the facet) or leaves through the top (in a band above the plot, over its caret), and inside the plot only where no curve passes. To stay clear of another label it moves at most ${formatInt(LABEL_SHIFT_MAX_LINES)} label lines (along the band, at most ${formatInt(BAND_SHIFT_MAX * 100)} % of the facet's width, in up to two rows), and a muted leader line joins a moved label to its curve. A curve whose label finds no place within that limit is named by its end mark in the key.`,
    'A caret at the axis marks where a curve leaves the range; the key above the facets repeats the values in force, so an export carries them.',
  ]);
  const used = Object.entries(model.used);
  notes.section(DISTILL_HEADINGS.values, used.length
    ? used.map(([k, spec]) => `${spec.label ?? k} = ${formatNumber(model.values[k], spec.unit === 'mm' ? 0 : 2)}${spec.unit ? ` ${spec.unit}` : ''} (domain ${formatNumber(spec.domain[0])} to ${formatNumber(spec.domain[1])}${spec.unit ? ` ${spec.unit}` : ''}, a drawing choice; default ${formatNumber(spec.default)}; read by ${(spec.usedBy ?? []).map((u) => `${payload.speciesLabels?.[u.species] ?? u.species} · ${payload.frameLabels?.[u.frame] ?? u.frame}`).join(', ')}).`)
    : ['Every curve drawn depends on E_sum alone.']);
  return notes.done([NO_INTERVAL]);
}
