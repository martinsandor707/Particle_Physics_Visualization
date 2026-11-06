/* What the Details drawer says about the four Performance cards of the benchmark catalogue.
 *
 * perf-catalog (`accuracyNotes`), perf-overlap (`overlapNotes`), perf-momentum-bias (`momentumNotes`) and
 * perf-diagnostics (`diagnosticsNotes`), in the four sections of `panel_notes.js` `SECTION` (Selection / What
 * is drawn / Disclosures / Marks and legend). Each builder takes `{payload, state, experiment, title, card,
 * species, task, angleScale, palette}` and returns `{title, hazards, sections}`.
 *
 * The payloads are the training report's documented point estimates (`catalog/select.js`); the selection and
 * the experiment never apply, and the Selection section says so. The builders read what the chart decided
 * through the panels' own pure models, so the drawer never states something the picture does not show.
 * Every card's hazards hold "no interval reported" (Martin's recorded exception, 2026-11-05), and the
 * disclosures carry the report's facts F1–F10 wherever they apply to what is drawn.
 */

import { Notes, SECTION } from './panel_notes.js';
import { formatInt } from './scale.js';
import { LEAK_TEXT } from './catalog/gating.js';
import { printed } from './catalog/select.js';
import {
  NO_INTERVAL, POINT_ESTIMATE, benchCatalogModel, labelOf, withUnit,
} from './panels/bench_catalog.js';
import { benchOverlapModel, LEVEL_BADGES, levelText, starvationText, ALL_NOTE } from './panels/bench_overlap.js';
import { benchMomentumModel, windowLabel, windowRule, oneSignBound, BIAS_NAME } from './panels/bench_momentum.js';
import { benchDiagnosticsModel, diagnosticsBlocks, PROTON_ONLY, valueText as diagnosticsValueText } from './panels/bench_diagnostics.js';

/** The drawer titles by card id; the shell's card title wins when it passes one. */
export const CATALOG_PERF_TITLES = Object.freeze({
  'perf-catalog': 'Validation Accuracy by Species, Task and Frame',
  'perf-overlap': 'Error by Overlap Bin',
  'perf-momentum-bias': 'Momentum Error and Bias near 5, 10 and 15 GeV (Absolute)',
  'perf-diagnostics': 'Segmentation Indecision, Throughput and Caveats',
});

/** The recorded exception, as the drawer states it. */
export const EXCEPTION_NOTE = 'Recorded exception (Martin, 2026-11-05): the training report gives point estimates only, '
  + 'so every mark is drawn as reported and every number printed with the report\'s own decimals (1.000 stays 1.000), names its N or says the N is not reported, and no interval is fabricated or '
  + 'derived. Differences smaller than the report\'s rounding are not resolved.';

/** The Marks line every catalogue card shares. */
const FRAME_HUES_NOTE = 'Colour is the frame, in the hues the network-error card E2 gives it (ColorBrewer qualitative, '
  + 'each at least 3:1 against the card): Absolute, Per-shower translated (the report\'s "trans"), Local. A species is '
  + 'never a second hue: it is named by a direct label or takes its own facet.';

/**
 * What the drawers say about the bias's sign. The report states no sign convention, so the card writes
 * "signed error as reported"; its own muon reading (the large errors near 5 and 15 GeV show an estimate
 * pulled toward the middle of the range, with +5.525 GeV at 5 GeV and −4.220 GeV at 15 GeV) only works if
 * the bias is prediction − truth, and the drawer says that much (R1-15).
 */
export const BIAS_SIGN_NOTE = 'The bias is the report\'s signed error as printed. The report states no sign convention; '
  + 'its muon interpretation (an estimate pulled toward the middle of the range, positive at 5 GeV and negative at 15 GeV) '
  + 'implies prediction − truth.';

/** The catalogue's ASCII note in the card's typography: ≤ for <=, × for x between numbers or words. */
function typographicNote(text) {
  return String(text ?? '').replace(/<=/g, '≤').replace(/>=/g, '≥').replace(/(\d) x (?=\w)/g, '$1 × ');
}

function speciesNames(payload) {
  return (payload?.species ?? []).map((s) => labelOf(payload, 'species', s)).join(', ');
}

/** The Selection lines every catalogue drawer opens with. */
function selectionLines(payload, { taskShown = true, extra = null } = {}) {
  const requested = payload?.meta?.species === 'all' ? 'Compare all' : speciesNames(payload);
  return [
    payload?.provenance ?? 'From the training report (models_performance.md): documented point estimates, no intervals reported.',
    `Species shown: ${requested}${payload?.meta?.species === 'all' ? ` (${speciesNames(payload)})` : ''}`
      + `${taskShown ? `; task: ${labelOf(payload, 'task', payload?.task)}` : ''}.`,
    extra,
    'The filter selection and the experiment do not apply: these are the report\'s numbers, not this dataset\'s.',
  ];
}

/* ========================================================= perf-catalog == */

export function accuracyNotes({ payload, title = null, angleScale = 'linear' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? CATALOG_PERF_TITLES['perf-catalog']);
  const model = benchCatalogModel(payload, { angleScale });
  notes.section(SECTION.selection, selectionLines(payload, {
    taskShown: false, extra: 'Every task is drawn, one facet per quantity; the task control does not narrow this card.',
  }));
  if (!model) return notes.done([NO_INTERVAL]);
  notes.section(SECTION.drawn, [
    'Four facets, each with its own zero-based axis and never a shared or dual one: the segmentation E-MAE (energy-weighted MAE of the predicted fraction, unitless), the angle MAE in mrad, the energy (momentum) MAE in GeV, and the energy network\'s R² to the truth on 0–1.',
    model.scale === 'log'
      ? 'The angle facet is on a log₁₀ axis and draws dots, a Cleveland dot plot: a bar measured from an arbitrary log floor encodes nothing, so no bar is drawn on log.'
      : 'Every bar starts at zero. The angle facet can switch to a log₁₀ axis (Angle axis control), where it draws dots, never bars.',
    model.ttaSpecies.length
      ? `The proton's value with test-time augmentation (TTA) is a tick across its bar, and its RMSE a hollow marker in the same unit.`
      : '',
    `Validation N: ${(payload.species ?? []).map((s) => {
      const row = payload.rows.find((r) => r.species === s);
      return row ? `${labelOf(payload, 'species', s)} ${formatInt(row.n.events)} combined events and ${formatInt(row.n.particles)} particles${row.n.nDerived ? ' (derived as 2 per combined event)' : ''}` : '';
    }).filter(Boolean).join('; ')}.`,
    'The secondary metrics (bias, R², the overlap-core MAE, the tree\'s R² to the network) are in the table under the plot, as reported.',
  ]);
  const disclosures = [EXCEPTION_NOTE];
  const noTta = model.species.filter((s) => !model.ttaSpecies.includes(s));
  if (noTta.length) {
    disclosures.push(`TTA not reported: ${noTta.map((s) => labelOf(payload, 'species', s)).join(', ')}. The report gives TTA, RMSE and bias for the proton only; its main table for the new species shows the single forward pass (F10).`);
  }
  if (model.clamped) disclosures.push(`${formatInt(model.clamped)} R² below zero clamped at 0 with an "R² < 0" mark; the tooltip gives the value as printed.`);
  for (const flag of model.leaks) disclosures.push(`Marked "leak": ${LEAK_TEXT[flag]}`);
  disclosures.push(LEAK_TEXT['oracle-separation']);
  disclosures.push(BIAS_SIGN_NOTE);
  if (model.species.some((s) => s !== 'proton')) {
    disclosures.push('For the muon, electron and pion the angle and energy R² and the tree\'s R² come from the report\'s summary table; their particle counts are derived as 2 per combined event.');
  }
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    FRAME_HUES_NOTE,
    `A ${model.scale === 'log' ? 'dot' : 'bar'} is the main metric; the tick across a bar is the TTA value; the hollow marker the RMSE; "leak" marks a frame the report flags for label leakage; "R² < 0" a clamped R². Every tooltip names the N and says: ${POINT_ESTIMATE}.`,
  ]);
  const hazards = [NO_INTERVAL];
  if (model.leaks.length) hazards.push('label leakage');
  if (model.clamped) hazards.push('R² < 0 clamped');
  return notes.done(hazards);
}

/* ========================================================= perf-overlap == */

export function overlapNotes({ payload, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? CATALOG_PERF_TITLES['perf-overlap']);
  const model = benchOverlapModel(payload);
  notes.section(SECTION.selection, selectionLines(payload));
  if (!model) return notes.done([NO_INTERVAL]);
  const q = model.task === 'segmentation' ? 'E-MAE' : 'MAE';
  notes.section(SECTION.drawn, [
    `The ${q}${model.unit ? ` in ${model.unit}` : ''} per overlap bin (0 %, 10 %, 20 %, 30 %, 40–100 %, as the report prints them), from zero; one series of dots joined by thin lines per frame.`,
    `${ALL_NOTE}: drawn as a dotted horizontal rule per frame, never as a sixth bin.`,
    model.all ? 'Compare all draws one facet per species, each on its own zero-based axis.' : '',
    ...model.facets.map((f) => `${labelOf(payload, 'species', f.species)}: ${LEVEL_BADGES[f.level] ?? ''}, ${levelText(f.level, model.task)}.`),
  ]);
  const disclosures = [EXCEPTION_NOTE];
  for (const f of model.facets) {
    if (f.events) {
      const sum = f.events.bins.reduce((a, b) => a + b, 0);
      disclosures.push(`${labelOf(payload, 'species', f.species)}: the five bins hold ${formatInt(sum)} of the ${formatInt(f.events.all)} events (${f.events.bins.map(formatInt).join(' + ')}); ${formatInt(f.events.unbinned)} fall in no bin (F1).`);
    }
  }
  if (model.notReported.length) {
    disclosures.push(`N not reported: ${model.notReported.map((s) => labelOf(payload, 'species', s)).join(', ')}. The report prints no per-bin event counts for these species, so none is shown and the proton's are never borrowed (F2).`);
  }
  if (model.mixedLevels) {
    disclosures.push('Per-hit and per-particle errors are different estimands (F3): the proton\'s angle and energy rows are titled hit-level, the other species\' are per particle, so the facets are not one scale.');
  } else if (model.task !== 'segmentation' && model.facets.some((f) => f.species === 'proton')) {
    disclosures.push('The proton\'s angle and energy rows sit under a heading the report titles hit-level; the other species\' angle and energy rows are per particle (F3).');
  }
  // The report's figures cover the starved bins together; the sentence names them, so no "in this bin".
  for (const f of model.facets) if (f.starvation && f.starved.length) disclosures.push(`${labelOf(payload, 'species', f.species)}: ${starvationText(f.starvation, model.bins)}`);
  for (const flag of model.leaks) disclosures.push(LEAK_TEXT[flag]);
  if (model.task !== 'segmentation') disclosures.push(LEAK_TEXT['oracle-separation']);
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    FRAME_HUES_NOTE,
    'Dots joined by thin lines: one frame\'s errors over the ordered bins. Dotted rule: that frame\'s All. Under the plot, the N strip: the proton\'s events per bin as bars from zero with their counts; "N not reported" for a species the report gives none for. One "info-starved" label over a bracket spans the bins of the report\'s information-starvation note.',
    `The facet heading carries the unit badge, "per hit" or "per particle". Every tooltip names the N or says "N not reported", and says: ${POINT_ESTIMATE}.`,
  ]);
  const hazards = [NO_INTERVAL];
  if (model.notReported.length) hazards.push('N not reported');
  if (model.leaks.length) hazards.push('label leakage');
  if (model.mixedLevels) hazards.push('per-hit and per-particle mixed');
  return notes.done(hazards);
}

/* =================================================== perf-momentum-bias == */

export function momentumNotes({ payload, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? CATALOG_PERF_TITLES['perf-momentum-bias']);
  const model = benchMomentumModel(payload);
  notes.section(SECTION.selection, selectionLines(payload, {
    taskShown: false, extra: 'The energy (momentum) network in the Absolute frame, whatever the task control shows: the report gives these windows for no other task or frame.',
  }));
  if (!model) return notes.done([NO_INTERVAL]);
  if (model.empty) {
    notes.section(SECTION.disclosures, [model.empty, EXCEPTION_NOTE]);
    return notes.done([NO_INTERVAL]);
  }
  notes.section(SECTION.drawn, [
    'For each species a pair of plots over three true-momentum windows: the MAE as a bar from zero, and the bias as a dot on an axis symmetric about zero with an explicit zero rule.',
    `${BIAS_NAME}: the report's average signed error, as printed. ${BIAS_SIGN_NOTE.replace(/^The bias is the report's signed error as printed\. /, '')}`,
    `Windows: ${(model.rows[0]?.windows ?? []).map((w) => `${windowLabel(w)}, ${windowRule(w)}`).join('; ')}.`,
    model.all ? 'Each species takes its own row with its own axes.' : '',
    ...model.rows.flatMap((r) => r.windows.map((w) => `${labelOf(payload, 'species', r.species)} ${windowLabel(w)}: MAE ${withUnit(printed(w.mae, w.dp?.mae), model.unit)}, bias ${withUnit(printed(w.bias, w.dp?.bias, { sign: true }), model.unit)}, n = ${formatInt(w.n)}.`)),
  ]);
  const disclosures = [
    EXCEPTION_NOTE,
    `Training split included (F6): ${typographicNote(model.note) || 'the windows are computed on the whole exported model output, not on the validation subset.'}`,
  ];
  if (model.inconsistent.length) {
    disclosures.push(`n does not count independent particles for ${model.inconsistent.map((s) => labelOf(payload, 'species', s)).join(' and ')}: the windows' n sum beyond the 2 × 20,000 = 40,000 particles of the dataset. n is shown as reported and no interval is ever built from it.`);
  } else {
    disclosures.push('n is shown as reported; no interval is built from it.');
  }
  if (model.oneSigned.length) {
    const bound = oneSignBound(model.oneSigned[0]);
    const boundText = bound ? `under ${bound.text} ${model.unit}` : 'within the rounding';
    disclosures.push(`|bias| equals the MAE to the report's rounding at ${model.oneSigned.map((w) => `${labelOf(payload, 'species', w.species)} ${windowLabel(w)} (${printed(w.bias, w.dp?.bias, { sign: true })} ${model.unit})`).join(' and ')} (F7). MAE − |bias| is (2/n)·Σ|e| over the errors of the other sign, and two values printed alike leave it at most one unit of the last printed decimal, so those errors average ${boundText} per particle of the window: (almost) every error has one sign. This is a bound from the rounding, not an exact implication. The dot is a diamond labelled "one sign".`);
  }
  if (model.notReported.length) disclosures.push(`${model.notReported.map((s) => labelOf(payload, 'species', s)).join(', ')}: the report gives no momentum windows.`);
  disclosures.push(LEAK_TEXT['oracle-separation']);
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Every mark takes the Absolute frame\'s E2 hue; a species is a row with its own heading, never a hue. Bars: the MAE from zero. Dots: the bias; a diamond labelled "one sign" where, to the report\'s rounding, (almost) every error has one sign. The muted horizontal line is zero. Each window\'s n is printed under its label.',
    `Every tooltip names the window, its rule and its n as reported, and says: ${POINT_ESTIMATE}.`,
  ]);
  const hazards = [NO_INTERVAL, 'training split included'];
  if (model.inconsistent.length) hazards.push('n exceeds the particles');
  return notes.done(hazards);
}

/* ===================================================== perf-diagnostics == */

export function diagnosticsNotes({ payload, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? CATALOG_PERF_TITLES['perf-diagnostics']);
  const model = benchDiagnosticsModel(payload);
  notes.section(SECTION.selection, selectionLines(payload));
  if (!model) return notes.done([NO_INTERVAL]);
  const blocks = diagnosticsBlocks(payload);
  notes.section(SECTION.drawn, [
    `The proton segmentation's indecision, as dumbbells per frame: the energy-weighted ⟨|2f − 1|⟩ on 0–1 (1 = every voxel decided) and the share of the energy with ${printed(model.band[0])} ≤ f ≤ ${printed(model.band[1])} on 0–100 %, the network's prediction against the truth. Both axes start at zero and span the quantities' whole range.`,
    `Under the plot, screen only: ${blocks.map((b) => b.label).join('; ')}.`,
    ...model.panels.flatMap((p) => p.rows.map((r) => {
      const v = (x) => diagnosticsValueText(p, x);
      return `${labelOf(payload, 'frame', r.frame)}, ${p.short}: prediction ${v(r.predicted)}, truth ${v(r.truth)}.`;
    })),
  ]);
  const disclosures = [
    EXCEPTION_NOTE,
    `${PROTON_ONLY}: the indecision and the H200 throughput. The report made no speed measurement for the muon, electron and pion and says the proton's numbers must not be copied to them (F10); these blocks keep their proton heading whatever species is on show.`,
    'The report gives no N for the indecision measurement.',
    'The architecture is the same for every species, as the report states; the parameter counts are the proton models\'.',
    'The caveats are the report\'s own, in English; its "translated" frame is written Per-shower translated, the dashboard\'s name for it.',
  ];
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'A filled dot is the network\'s prediction, a hollow one the truth, joined by a thin line in the frame\'s E2 hue (ColorBrewer qualitative, each at least 3:1 against the card).',
    `Every tooltip says: ${POINT_ESTIMATE}.`,
  ]);
  const hazards = [NO_INTERVAL];
  if (!model.protonShown || (payload.species ?? []).length > 1) hazards.push('measured on the proton only');
  return notes.done(hazards);
}

/** The builders by card id, for the section controller. */
export const CATALOG_PERF_NOTE_BUILDERS = Object.freeze({
  'perf-catalog': 'accuracyNotes',
  'perf-overlap': 'overlapNotes',
  'perf-momentum-bias': 'momentumNotes',
  'perf-diagnostics': 'diagnosticsNotes',
});
