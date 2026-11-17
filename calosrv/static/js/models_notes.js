/* What the Details drawer says about each 2-D card of the models page.
 *
 * The Page 2 twin of panel_notes.js's physics builders, in the same four
 * sections (Selection / What is drawn / Disclosures / Marks and legend) plus a
 * card's own headings after them. Each builder takes `{payload, state,
 * experiment, title, card, ...opts}` - the render options the card drew with
 * (quantity, shower, palette, stat) - and returns `{title, hazards, sections}`.
 * Nothing here reads the page: the section controller hands the payloads in,
 * shell.js renders the result, and every sentence can be checked under Node.
 *
 * The payloads carry their prose (`notes`) and their structured disclosures
 * (counts beyond an axis, eps-floored values, provisional ranges, the comb);
 * the builders sort both into the sections and add what the chart itself
 * decided - which marks it drew, what it clipped - through the panels' own
 * pure models (`perfModel`, `residualModel`, `hist2dModel`), so the drawer
 * never states something the picture does not show.
 *
 * `modelsHazards(payload, card)` names the conditions a reader must not miss,
 * from structure only, never by matching text.
 */

import { Notes, SECTION, PHYSICS_HEADINGS, CURVE_AREA_NOTE, onLightScreen, puorScreenNote, rampName } from './panel_notes.js';
import { describeSelection } from './export/caption.js';
import { formatInt, formatNumber, formatPercent } from './scale.js';
import { sigmaText, sigFigs } from './panels/chart_panel.js';
import {
  resolutionModel, modeLabel, DRAWN_FORMS, energyModel, ENERGY_FORMS, RATIO_STEPS, ratioTickLabel, referenceChoiceText,
  weightState, declinedWindow, declinedText, RES_DECOMPOSITION,
} from './panels/resolution_scaling.js';
import { REFERENCE_SOURCE, RESOLUTION_REFERENCES, REFERENCE_UNITS, referenceEquation } from './catalog/resolution_refs.js';
import { LITERATURE_HUES } from './palette.js';
import { isDepositSeries } from './res_axis.js';
import { perfModel, perfQuantities, SOURCE_LABELS, isEnergyMedianRel, MEDIAN_REL_RECONCILIATION } from './panels/perf_bins.js';
import { residualModel, featureHistModel, HISTOGRAM_FLOOR } from './panels/distribution.js';
import { hist2dModel, countRamp, DENSITY2D_FLOOR } from './panels/hist2d.js';
import { featureRows, FEATURE_STATS, ROBUST_N } from './panels/feature_table.js';
import { featureCorrMatrix, containsZero } from './panels/correlation.js';
import { FEATURE_FRAME_NAMES } from './labels.js';
import { rateBins, WIDE_BELOW_N } from './panels/rates.js';

/** The drawer titles by card id; the shell's card title wins when it passes one. */
export const MODELS_TITLES = Object.freeze({
  'perf-bins': 'Network Error per Momentum Bin',
  'pred-truth': 'Prediction against Truth',
  'pred-residuals': 'Residual Distribution',
  'feat-table': 'Shower Features — describe()',
  'feat-corr': 'Feature Correlation',
  'feat-hist': 'Feature Distribution by Momentum Class',
  'feat-hist2d': 'Feature against Deposited Energy by Class',
  'prim-rate': 'Events without a Primary-tagged Hit',
});

/** Headings the models cards add after the four standard ones. */
export const MODELS_HEADINGS = Object.freeze({
  estimators: 'Estimators',
  circular: PHYSICS_HEADINGS.circular,
  counts: 'Exact counts',
});

const num = (v, d = 3) => formatNumber(v, d);

function plural(n, word, many = `${word}s`) {
  return `${formatInt(n)} ${n === 1 ? word : many}`;
}

/** The filter line of a card: the experiment and the narrowed axes only. */
function selectionLine(state, experiment) {
  if (!state) return null;
  return describeSelection(state, experiment, null, null, null, { filtersOnly: true });
}

/** The warnings a payload's meta carries, and its sampling, as disclosures. */
function metaDisclosures(payload) {
  const out = [...(payload?.meta?.warnings ?? [])];
  if (payload?.meta?.exact === false) out.push('Sampled preview: the exact numbers follow.');
  return out;
}

/** A sentence with a terminal full stop. */
function sentence(text) {
  const t = String(text ?? '').trim();
  if (!t) return '';
  return /[.!?:]$/.test(t) ? t : `${t}.`;
}

/** The server's notes object or list as lines. */
function noteLines(notes) {
  if (!notes) return [];
  if (Array.isArray(notes)) return notes.filter((l) => typeof l === 'string');
  return Object.values(notes).filter((l) => typeof l === 'string');
}

/* ================================================================ E2 == */

/**
 * The notes of the per-bin performance card. `quantity` and `shower` are the
 * card's render options; the statistic drawn is the payload's own when the
 * one asked for is absent.
 */
export function perfBinsNotes({ payload, state = null, experiment = null, title = null, quantity = null, shower = 'both' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['perf-bins']);
  const model = perfModel(payload, { quantity, shower });
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no per-bin performance.', ...metaDisclosures(payload)]);
    return notes.done([]);
  }
  const block = payload.by_momentum_bin;
  const xgb = block.source === 'xgb';
  // The aggregate's XGBoost regressor predicts the incident momentum, not an energy (P-5).
  const task = xgb ? `XGBoost ${model.model === 'angle' ? 'angle' : 'momentum'} regressor`
    : (model.model === 'angle' ? 'polar-angle network' : 'energy network');
  const sources = [...new Set(model.series.map((s) => SOURCE_LABELS[s.source] ?? s.source))];
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${plural(block.n_events ?? payload.n_events ?? 0, 'event')}; the ${task}, `
      + `${sources.length ? sources.join(', ') : 'no series'}${shower && shower !== 'both' ? `; shower ${String(shower).toUpperCase()} only` : ''}.`,
  ]);

  const q = model.q;
  const drawn = [
    `${q.label ?? model.quantity} per 1 GeV momentum bin: ${q.definition ?? ''}${model.unit === '%' ? ', read in percent' : ''}.`,
    'Bars from zero, one per network input and shower, at a fixed offset inside their momentum bin, so the x axis stays the momentum in GeV and an empty bin is a gap.',
    ...noteLines(model.notes).filter((l) => !/^Every whisker|^A point drives/.test(l)),
  ];
  notes.section(SECTION.drawn, drawn);

  const disclosures = [];
  if (model.y.provisional) disclosures.push(model.y.note || 'The y range is provisional: no point reaches N = 15, so it comes from the under-powered values, whiskers excluded.');
  if (model.y.n_overflow) {
    const sc = (v) => (Number.isFinite(v) ? num(v * model.factor) : '—');
    const listed = model.y.overflow.map((o) => `${o.series}, bin ${o.bin} (N = ${formatInt(o.n)}): ${sc(o.value)} [${sc(o.lo)}, ${sc(o.hi)}]`);
    disclosures.push(`${plural(model.y.n_overflow, 'under-powered point')} beyond the axis, clipped with a caret: ${listed.join('; ')}${model.y.n_overflow > listed.length ? '; …' : ''}.`);
  }
  if (model.clipped.bars || model.clipped.whiskers) {
    disclosures.push(`Drawn clipped at the axis, each with a caret and its true values in its tooltip: ${plural(model.clipped.bars, 'bar')}, ${plural(model.clipped.whiskers, 'whisker')}.`);
  } else {
    disclosures.push('No bar or whisker leaves the axis.');
  }
  const points = model.series.flatMap((s) => s.points);
  const noun = model.noun ?? 'shower';
  const single = points.filter((p) => p.single).length;
  if (single) disclosures.push(`${plural(single, 'bin')} of one ${noun}, drawn as a dot: one ${noun} is an observation, not an aggregate, so it has no interval and no bar.`);
  const weak = points.filter((p) => p.weak && !p.single).length;
  if (weak) disclosures.push(`${plural(weak, 'bar')} without an interval, drawn faded: the ${q.label ?? model.quantity} has one from N = ${formatInt(model.intervalFloor)}.`);
  const missing = model.series.reduce((sum, s) => sum + s.points.reduce((a, p) => a + (p.n_missing || 0), 0), 0);
  if (missing) disclosures.push(`${plural(missing, 'shower')} without a prediction, dropped from their bins and never zero-filled.`);
  const unbinned = Object.entries(block.excluded?.unbinned ?? {}).filter(([, v]) => v > 0);
  if (unbinned.length) disclosures.push(`Outside every momentum bin: ${unbinned.map(([k, v]) => `shower ${k.toUpperCase()} ${formatInt(v)}`).join(', ')}.`);
  const nonpos = Object.entries(block.excluded?.nonpositive_true ?? {}).filter(([, v]) => v > 0);
  if (nonpos.length) disclosures.push(`Left out of the relative error for a non-positive truth: ${nonpos.map(([k, v]) => `${k} ${formatInt(v)}`).join(', ')}.`);
  if (model.omitted.length) disclosures.push(`Not reported for this statistic, so not drawn: ${model.omitted.join(', ')}.`);
  const small = points.reduce((sum, p) => sum + (p.n_small_theta || 0), 0);
  if (points.some((p) => Number.isFinite(p.theta_min))) {
    const minTheta = Math.min(...points.map((p) => p.theta_min).filter(Number.isFinite));
    disclosures.push(`Small polar angles: ${plural(small, 'shower')} with θ < 0.1 rad over the drawn bins; the smallest true θ is ${num(minTheta, 4)} rad.`
      + (model.quantity === 'median_rel' && small ? ' |Δθ| / θ grows like 1 / θ there: read the median absolute error beside it.' : ''));
  }
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);

  notes.section(SECTION.legend, [
    xgb ? 'Colour is the series (ColorBrewer qualitative hues, each ≥ 3:1 against the card): the XGBoost regressor on its validation split, one shower per event.'
      : 'Colour is the network\'s input frame (ColorBrewer qualitative hues, each ≥ 3:1 against the card); a solid bar is shower A, a light wash with a solid outline shower B, and their legend swatches are drawn the same way.',
    `The capped whisker is the 95% interval of the plotted statistic - ${q.interval ?? 'as the server names it'} - never the spread of the ${noun}s in the bin. It is ${onLightScreen() ? 'dark ink on a light' : 'light ink on a dark'} casing, so it reads over any bar and over the card.`,
    `A faded, dash-outlined bar has no interval. A dot is a bin of one ${noun}: an observation, not an aggregate. A caret at the axis marks a bar, dot or whisker clipped there. The readout lists every series of the bin under the pointer.`,
  ]);
  notes.section(MODELS_HEADINGS.estimators, [
    ...perfQuantities(payload).map((x) => {
      const def = block.quantities[x.key];
      return `${def.label}: ${def.definition}; ${def.interval}.`;
    }),
    block.bootstrap ? `Bootstrap: B = ${formatInt(block.bootstrap.replicates)}, seed ${block.bootstrap.seed}; ${block.bootstrap.seed_rule}.` : '',
    isEnergyMedianRel(model) ? MEDIAN_REL_RECONCILIATION : '',
  ]);
  return notes.done(modelsHazards(payload, 'perf-bins', { quantity: model.quantity, shower }));
}

/* ========================================================= pred-truth == */

/** The colour sentence of the pred-truth ramp for the user's palette. */
function rampSentence(payload, palette) {
  const ramp = countRamp(palette, payload.color?.ramp?.by_palette?.[palette] ?? null);
  const measured = payload.color?.ramp?.by_palette?.[palette];
  const head = `log₁₀ of the showers per bin on ${rampName(palette)}, positions ${num(ramp.from, 2)} to ${num(ramp.to, 2)} of the ramp; an empty bin is transparent.`;
  if (ramp.measured && measured?.first_level) {
    return `${head} A bin of one shower is ${measured.first_level.color}, ${num(measured.first_level.contrast, 2)}:1 against the ${measured.first_level.against} card.`;
  }
  return `${head} The start is where the ramp first clears 3:1 against the card in force.`;
}

/** The notes of the prediction-against-truth card. */
export function predTruthNotes({ payload, state = null, experiment = null, title = null, palette = 'viridis', shower = 'both' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['pred-truth']);
  const model = hist2dModel(payload, { palette, shower });
  const axes = payload.axes ?? {};
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${plural(payload.n_events ?? 0, 'event')}; ${axes.pred?.label ?? 'prediction'} against ${axes.truth?.label ?? 'truth'} [${axes.truth?.unit ?? ''}], `
      + `the ${payload.network?.model ?? ''} network of the ${payload.network?.frame ?? ''} frame.`,
    ...(model?.panels ?? []).map((p) => `${p.label}: ${plural(p.n, 'pair')}, ${formatInt(p.n_in_range)} inside the shared axes; drawn as ${p.draw === 'pairs' ? 'individual pairs' : 'a count raster'}.`),
  ]);
  notes.section(SECTION.drawn, [
    rampSentence(payload, palette),
    // The server measured this note against the dark card (its #1c2128 is named in the text): on the light card
    // it would contradict the ramp sentence above, which is computed against the card in force.
    palette === 'viridis' && !onLightScreen() ? payload.color?.note ?? '' : '',
    'Square axes, 1:1: truth and prediction share one dataset-wide range in one unit, so the identity line is the diagonal.',
    payload.notes?.pairs ?? '',
    payload.notes?.axes ?? '',
    payload.notes?.calibration ?? '',
    payload.notes?.angle ?? '',
  ]);
  const disclosures = [];
  // The server words each shower's outside count as a warning; a shower it did not warn about gets ours.
  const warned = (label) => (payload.meta?.warnings ?? []).some((w) => String(w).startsWith(`${label}:`));
  for (const p of model?.panels ?? []) {
    const o = p.outside ?? {};
    if (o.total && !warned(p.label)) {
      disclosures.push(`${p.label}: ${plural(o.total, 'pair')} outside the shared axes (truth ${formatInt(o.truth_below)} below and ${formatInt(o.truth_above)} above, `
        + `prediction ${formatInt(o.pred_below)} below and ${formatInt(o.pred_above)} above): counted, not drawn.`);
    }
    const m = p.n_missing ?? {};
    if (m.total) disclosures.push(`${p.label}: ${plural(m.total, 'event')} without a finite pair (prediction ${formatInt(m.prediction)}, truth ${formatInt(m.truth)}): counted, never zero-filled.`);
    if (p.draw === 'pairs') disclosures.push(`${p.label}: fewer than ${formatInt(model.floor)} pairs, so the pairs themselves are drawn rather than a density.`);
  }
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Colour is the count of showers in a bin on a logarithmic ramp shared by both showers; the colour bar is labelled in showers. Dots are individual pairs below the density floor.',
    `Dashed diagonal: the identity, ${payload.identity?.label ?? 'prediction = truth'}.`,
  ]);
  return notes.done(modelsHazards(payload, 'pred-truth', { shower }));
}

/* ========================================================== residuals == */

/** The notes of the residual histogram (the pred-truth request's residual block). */
export function residualNotes({ payload, state = null, experiment = null, title = null, shower = 'both' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['pred-residuals']);
  const r = payload.residual;
  if (!r) {
    notes.section(SECTION.disclosures, ['This response carries no residual distribution.', ...metaDisclosures(payload)]);
    return notes.done([]);
  }
  const model = residualModel(payload, { shower });
  const unit = r.unit && r.unit !== 'fraction' ? ` ${r.unit}` : '';
  // The XGBoost azimuth residual: wrapped, summarised on the circle, no line statistics drawn.
  const circular = r.statistics === 'circular';
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${r.quantity}${r.unit ? ` [${r.unit}]` : ''}; ${model.entries.map((e) => `${e.label} N = ${formatInt(e.n)}`).join(', ') || 'no shower'}.`,
  ]);
  const drawn = [payload.notes?.residual ?? ''];
  if (r.axis?.bin_rule) {
    drawn.push(`Bins: ${sentence(r.axis.bin_rule)}${Number.isFinite(r.axis.bins) ? ` Here ${formatInt(r.axis.bins)} bins${Number.isFinite(r.axis.bin_width) ? ` of ${num(r.axis.bin_width)}${unit}` : ''}.` : ''}`);
  }
  for (const e of model.entries) {
    const what = circular
      ? (e.hist ? `a density histogram from zero${e.curve ? ' with the Gaussian fit of its core' : ''}` : 'its residuals as ticks in the reserved band, with no summary marks')
      : (e.hist ? 'a density histogram from zero with its fitted Gaussian' : (e.curve ? 'its fitted Gaussian, thin and faint, with its events in the reserved band' : 'its events and summary marks in the reserved band'));
    drawn.push(`${e.label}: ${what}.${e.message ? ` ${e.message}` : ''}`);
  }
  drawn.push('The dotted vertical is zero residual: prediction equals truth.');
  drawn.push(payload.notes?.relative ?? '');
  notes.section(SECTION.drawn, drawn);

  const axis = r.axis ?? {};
  const disclosures = [axis.clipping?.note ?? ''];
  for (const e of model.entries) {
    if (e.below || e.above) disclosures.push(`${e.label}: ${formatInt(e.below)} below and ${formatInt(e.above)} above the axis, counted in every statistic and not drawn.`);
  }
  if (axis.provisional) disclosures.push(`The residual axis is provisional: ${axis.basis ?? 'too few showers for robust percentiles'}.`);
  if (model.provisional) disclosures.push('The density axis is provisional: no series reaches N = 15, so its range comes from the under-powered curves.');
  const clippedCurves = model.entries.filter((e) => e.curve && Number.isFinite(model.yMax) && Math.max(...e.curve.map((p) => p[1]).filter(Number.isFinite)) > model.yMax);
  if (clippedCurves.length) disclosures.push(`Curves clipped at the density axis, each with a caret carrying its true peak: ${clippedCurves.map((e) => e.label).join(', ')}.`);
  const nonpos = Object.entries(r.excluded?.nonpositive_truth ?? {}).filter(([, v]) => v > 0);
  if (nonpos.length) disclosures.push(`Left out for a non-positive truth: ${nonpos.map(([k, v]) => `shower ${k.toUpperCase()} ${formatInt(v)}`).join(', ')}.`);
  // The response's warnings are about the prediction-against-truth axes, which this histogram does not use.
  if ((payload.meta?.warnings ?? []).length) {
    disclosures.push('Pairs beyond the prediction-against-truth axes are still in this histogram: the residual has its own axis.');
  }
  if (payload.meta?.exact === false) disclosures.push('Sampled preview: the exact numbers follow.');
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, circular ? [
    'One shower is drawn in the accent blue, as on the Physics page. φ is an azimuth: no mean rule, whisker or ± 1 SD bar is drawn, because an arithmetic mean and σ of a wrapped residual are not its centre and spread. Its circular mean direction, R̄ and circular SD are listed below and in the tooltip.',
    `From N = ${HISTOGRAM_FLOOR} the histogram is the spread; its curve, where drawn, is the Gaussian fit of the core only. Below N = ${HISTOGRAM_FLOOR} the residuals sit as ticks in the tinted, captioned band at the foot; heights there are drawing offsets.`,
    'A caret marks a curve or residuals beyond the axis.',
  ] : [
    'Shower colour as on the Physics page: A pink, B blue and dashed on two-shower data, and a single shower in the accent blue. From N = 15 a series\' mean is a long-dashed vertical with its 95% Student-t interval of the mean as two thin hairlines; its spread is the histogram itself.',
    `Below N = ${HISTOGRAM_FLOOR} a series sits in the tinted, captioned band at the foot: its events as ticks, its mean with the capped Student-t whisker and an uncapped ± 1 SD bar, the spread of the events - two marks, two quantities; heights there are drawing offsets.`,
    CURVE_AREA_NOTE,
    'A caret marks a curve, a mark or showers beyond the axis.',
  ]);
  notes.section(MODELS_HEADINGS.estimators, model.entries.map((e) => {
    const s = r.series?.[e.key] ?? {};
    if (circular) {
      const c = s.circular ?? {};
      const iv = c.mean_direction_interval;
      const rmse = s.estimates?.rmse ?? {};
      const core = s.core_fit;
      return `${e.label}: circular mean direction ${num(c.mean_direction)}${unit}${iv ? ` [${num(iv.lo)}, ${num(iv.hi)}] (${iv.label})` : ''}; `
        + `mean resultant length R̄ = ${num(c.resultant, 4)}; circular SD ${num(c.circular_sd)}${unit}; `
        + `RMSE ${num(rmse.value)}${unit}${rmse.interval ? ` [${num(rmse.interval.lo)}, ${num(rmse.interval.hi)}]` : ''}`
        + `${core ? `; Gaussian fit of the core: width ${num(core.sigma)}${unit} over ${formatInt(core.n)} residuals` : ''}`
        + '; no bias, σ or σ/μ: an azimuth.'
        + `${c.note ? ` ${c.note}` : ''}`;
    }
    const b = s.estimates?.bias ?? {};
    const sig = sigmaText(e.fit, { unit });
    return `${e.label}: bias ${num(b.value)}${unit}${b.interval ? ` [${num(b.interval.lo)}, ${num(b.interval.hi)}] (${b.interval.label})` : ''}`
      + `${sig ? `; ${sig}` : ''}; ${e.fit.estimator_note ?? e.fit.estimator ?? ''}${e.fit.note ? ` ${e.fit.note}` : ''}`;
  }));
  return notes.done(modelsHazards(payload, 'pred-residuals', { shower }));
}

/* ============================================================= D2-D5 == */

/** A features response's frame, named as the interface names it (the API key when unknown). */
export function featureFrameName(payload) {
  const key = payload?.coord_system;
  return FEATURE_FRAME_NAMES[key] ?? key ?? '—';
}

/** The selection line of a features response: frame, shower, classes. */
function featureSelection(payload) {
  const classes = (payload.classes ?? []).map((c) => `${c.label} (N = ${formatInt(c.n)})`);
  const lines = [
    `${plural(payload.n_selected ?? payload.n_events ?? 0, 'shower')} selected; frame: ${featureFrameName(payload)}`
      + `${payload.shower ? `, shower ${String(payload.shower).toUpperCase()}` : ''}; classes by ${payload.class_basis ?? payload.class_mode ?? '—'}: ${classes.join(', ')}.`,
  ];
  if (payload.n_outside_classes) lines.push(`${plural(payload.n_outside_classes, 'shower')} in no class: counted, never drawn.`);
  if (payload.n_excluded_single_hit) lines.push(`${plural(payload.n_excluded_single_hit, 'shower')} with fewer than 2 hits left out, as the producer's aggregate does.`);
  return lines;
}

/** The notes of the describe() table (D2); `stat` is the cell statistic drawn. */
export function featureTableNotes({ payload, state = null, experiment = null, title = null, stat = 'median' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['feat-table']);
  const model = featureRows(payload, stat);
  notes.section(SECTION.selection, [selectionLine(state, experiment), ...featureSelection(payload)]);
  notes.section(SECTION.drawn, [
    `A table, not a chart: each cell is the ${FEATURE_STATS.find((s) => s.key === model.stat)?.label ?? model.stat} of one feature in one class.`,
    payload.intervals?.mean ? `Mean: ${payload.intervals.mean}.` : '',
    payload.intervals?.sd ? `SD: ${payload.intervals.sd}.` : '',
    ...noteLines(payload.notes),
  ]);
  const disclosures = [];
  const small = model.columns.filter((c) => c.n < ROBUST_N && c.n > 0);
  if (small.length) disclosures.push(`${plural(small.length, 'class', 'classes')} below N = ${ROBUST_N} (flagged ⚑): ${small.map((c) => `${c.label} (N = ${formatInt(c.n)})`).join(', ')}.`);
  for (const [n, note] of Object.entries(payload.notes_by_n ?? {})) {
    const at = model.columns.filter((c) => String(c.n) === n).map((c) => c.label);
    if (at.length) disclosures.push(`N = ${n} (${at.join(', ')}): ${note}`);
  }
  const floored = model.rows.filter((r) => /floored/.test(r.note));
  if (floored.length) disclosures.push(`Eps-floored values, counted in the row note: ${floored.map((r) => `${r.key} — ${r.note}`).join('; ')}.`);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    '⚑ marks a cell from fewer than 20 showers or a row with a note; ↻ marks a circular feature. Every cell\'s tooltip carries its N, the mean\'s Student-t interval, σ with its SE (and below N = 15 its χ² interval and c₄(N)) and the server\'s low-N note.',
    '"mean ± SD" quotes the spread of the showers, not an interval; N = 2 is marked "1 d.o.f.".',
  ]);
  const circular = model.rows.filter((r) => r.circular);
  if (circular.length) {
    notes.section(MODELS_HEADINGS.circular, [
      `${circular.map((r) => r.key).join(', ')}: circular, so their cells give the mean direction and the mean resultant length R̄, never an arithmetic mean, SD or quartile.`,
      ...circular.flatMap((r) => (payload.table?.[r.key]?.circular?.note ?? [])
        .map((note, i) => (note ? `${r.key}, ${model.columns[i]?.label ?? `class ${i}`}: ${note}` : ''))),
    ]);
  }
  return notes.done(modelsHazards(payload, 'feat-table'));
}

/** The notes of the feature correlation matrix (D3). */
export function featureCorrNotes({ payload, state = null, experiment = null, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['feat-corr']);
  const m = featureCorrMatrix(payload);
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${payload.class_label ?? payload.class ?? 'all classes'}: N = ${formatInt(payload.n)} showers; frame: ${featureFrameName(payload)}${payload.shower ? `, shower ${String(payload.shower).toUpperCase()}` : ''}.`,
    payload.exclude_eps && payload.n_excluded_eps
      ? `${plural(payload.n_excluded_eps, 'shower')} with a floored factor left out of the pairs with ${(payload.eps_pair_features ?? []).join(', ')}.` : '',
  ]);
  notes.section(SECTION.drawn, [
    `${payload.scale?.label ?? 'Pearson r'}, lower triangle only (the matrix is symmetric and its diagonal 1), on PuOr symmetric about zero: linear on [−1, +1]${puorScreenNote()}`,
    ...noteLines(payload.notes),
  ]);
  const cells = m.matrix.flatMap((row) => row.filter(Boolean));
  const linear = cells.filter((c) => !c.hatched && Number.isFinite(c.r));
  const disclosures = [payload.interval ? `Interval: ${payload.interval}.` : ''];
  const untestable = linear.filter((c) => !c.ci95).length;
  if (untestable) disclosures.push(`${plural(untestable, 'cell')} carry r without an interval (fewer than ${formatInt(payload.thresholds?.fisher ?? 4)} showers).`);
  const faded = linear.filter((c) => containsZero(c)).length;
  if (faded) disclosures.push(`${plural(faded, 'cell')} drawn faded: the 95% interval contains 0${untestable ? ', or there is none' : ''}, so the sample cannot tell the correlation from none.`);
  const quiet = cells.filter((c) => c.hatched && c.circular && !Number.isFinite(c.circular.value));
  if (quiet.length) disclosures.push(`${plural(quiet.length, 'azimuth cell')} without a circular measure: ${quiet[0].circular.reason ?? 'not estimable at this sample size'}`);
  const notR = cells.filter((c) => !c.hatched && !Number.isFinite(c.r)).length;
  if (notR) disclosures.push(`${plural(notR, 'cell')} with no r (not estimable).`);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Each cell is coloured by r; its tooltip gives r, the 95% interval and N. Where a cell is too small for it the printed r is dropped and the tooltip carries it.',
    'A faded cell is one whose 95% interval contains 0 (or that has no interval): its r is printed, but its colour does not claim an association the sample cannot tell from none.',
    'A hatched cell off the colour scale pairs an azimuth; a hatched cell on the colour scale pairs angular_spread, whose r is coloured with a caution.',
  ]);
  notes.section(MODELS_HEADINGS.circular, [
    ...Object.entries(payload.hatched ?? {}).map(([k, v]) => `${k}: ${v}`),
    ...Object.values(payload.circular_measures ?? {}),
    'parity_r, the notebook\'s linear r of avg_phi, appears in the tooltip only, without an interval, for comparison with the notebook.',
  ]);
  return notes.done(modelsHazards(payload, 'feat-corr'));
}

/** The comb sentence of a features response. */
function combLine(comb) {
  if (!comb) return '';
  const verdict = comb.combed === null || comb.combed === undefined ? 'unmeasurable' : (comb.combed ? 'a comb' : 'no comb');
  return `Comb lag-1 ${Number.isFinite(comb.lag1) ? num(comb.lag1, 2) : '—'}${Number.isFinite(comb.threshold) ? ` against ${num(comb.threshold, 2)}` : ''}, `
    + `measured on the ${comb.measured_on ?? 'counts'}: ${verdict}${comb.cause ? ` (cause: ${comb.cause})` : ''}. ${comb.note ?? ''}`;
}

/** The notes of a feature histogram (D4); `quantity` is 'density' | 'count'. */
export function featureHistNotes({ payload, state = null, experiment = null, title = null, quantity = 'density', palette = 'viridis' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['feat-hist']);
  const model = featureHistModel(payload, { quantity, palette });
  const axis = payload.axis ?? {};
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${axis.label ?? payload.feature}${axis.unit ? ` [${axis.unit}]` : ''}, ${axis.scale ?? 'linear'} axis.`,
    ...featureSelection(payload),
  ]);
  const drawn = [
    model.quantity === 'count' ? `Count axis: ${payload.y_axis?.count ?? 'events per bin'}; a KDE is drawn as the expected count per bin.` : `Density axis: ${payload.y_axis?.density ?? 'count / (N · bin width)'}.`,
    axis.edges_rule ? `Bins: ${axis.edges_rule}.` : '',
  ];
  for (const s of payload.series ?? []) {
    const what = s.draw === 'histogram' ? 'histogram from zero' : (s.draw === 'strip' ? 'its events in the reserved band' : 'nothing');
    drawn.push(`${s.label} (N = ${formatInt(s.n)}): ${what}${s.kde ? ' with a Gaussian KDE' : ''}.${s.message ? ` ${s.message}` : ''}`);
  }
  const kde = (payload.series ?? []).find((s) => s.kde)?.kde;
  if (kde?.rule) drawn.push(`KDE: ${kde.rule}.`);
  drawn.push(...(axis.notes ?? []), ...noteLines(payload.notes));
  notes.section(SECTION.drawn, drawn);

  const disclosures = [axis.clipping?.note ?? ''];
  for (const s of payload.series ?? []) {
    const parts = [];
    if (s.n_below || s.n_above) parts.push(`${formatInt(s.n_below)} below and ${formatInt(s.n_above)} above the axis`);
    if (s.n_floored) parts.push(`${formatInt(s.n_floored)} floored at 10⁻⁶ mm (counted underflow)`);
    if (s.n_excluded_eps) parts.push(`${formatInt(s.n_excluded_eps)} floored values left out`);
    if (s.n_nonpositive) parts.push(`${formatInt(s.n_nonpositive)} non-positive, no logarithm`);
    if (parts.length) disclosures.push(`${s.label}: ${parts.join('; ')}.`);
  }
  if (payload.y_max?.provisional) disclosures.push('The density axis is provisional: no class reaches N = 15.');
  if (payload.y_max?.basis) disclosures.push(`The y range is set by ${payload.y_max.basis}.`);
  const over = payload.y_max?.overflow ?? [];
  if (over.length) disclosures.push(`${plural(over.length, 'under-powered curve')} above the range, clipped with a caret carrying the true peak.`);
  disclosures.push(combLine(payload.comb));
  if (axis.provisional) disclosures.push('The feature axis is provisional: set from few values.');
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Momentum classes in order on the chosen sequential ramp (each colour ≥ 3:1 against the card). A step outline from zero is a histogram (N ≥ 15); a thin curve a Gaussian KDE (N ≥ 8), faint when it does not set the axis.',
    `Below N = ${HISTOGRAM_FLOOR} a class's events are ticks in the tinted, captioned band at the foot, whose heights are drawing offsets. A caret marks a curve or values beyond the axis.`,
  ]);
  if (axis.scale === 'circular') {
    notes.section(MODELS_HEADINGS.circular, ['An azimuth is drawn on its full period (−π, π] and never gets a linear kernel: a KDE would smooth across the ±π cut.']);
  }
  return notes.done(modelsHazards(payload, 'feat-hist'));
}

/** The notes of the feature-against-energy small multiples (D5). */
export function featureHist2dNotes({ payload, state = null, experiment = null, title = null, palette = 'viridis' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['feat-hist2d']);
  const model = hist2dModel(payload, { palette });
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${payload.x?.label ?? '—'}${payload.x?.unit ? ` [${payload.x.unit}]` : ''} against ${payload.y?.label ?? '—'}${payload.y?.unit ? ` [${payload.y.unit}]` : ''}${payload.y?.log10 ? ' (log₁₀ axis)' : ''}.`,
    ...featureSelection(payload),
  ]);
  notes.section(SECTION.drawn, [
    payload.color?.note ?? '',
    model ? `One multiple per class, sharing edges and one colour scale (1 to ${formatInt(Math.round(10 ** model.vmax))} events per bin) on ${palette}, positions ${num(model.ramp.from, 2)} to ${num(model.ramp.to, 2)}.` : '',
    payload.x?.edges_rule ? `x bins: ${payload.x.edges_rule}.` : '',
    payload.y?.edges_rule ? `y bins: ${payload.y.edges_rule}.` : '',
    ...noteLines(payload.notes),
  ]);
  const disclosures = [payload.x?.clipping?.note ? `x: ${payload.x.clipping.note}` : '', payload.y?.clipping?.note ? `y: ${payload.y.clipping.note}` : ''];
  for (const s of payload.series ?? []) {
    const parts = [];
    if (s.outside?.total) parts.push(`${formatInt(s.outside.total)} outside the axes (x ${formatInt(s.outside.x_below)} below, ${formatInt(s.outside.x_above)} above; y ${formatInt(s.outside.y_below)} below, ${formatInt(s.outside.y_above)} above), counted and not drawn`);
    if (s.n_floored) parts.push(`${formatInt(s.n_floored)} floored at 10⁻⁶ mm (counted underflow)`);
    if (s.n_excluded_eps) parts.push(`${formatInt(s.n_excluded_eps)} floored values left out`);
    const nonpos = (s.n_nonpositive_x ?? 0) + (s.n_nonpositive_y ?? 0);
    if (nonpos) parts.push(`${formatInt(nonpos)} non-positive, no logarithm`);
    if (s.draw === 'pairs') parts.push(`fewer than ${formatInt(model?.floor ?? DENSITY2D_FLOOR)}: the pairs themselves`);
    if (parts.length) disclosures.push(`${s.label}: ${parts.join('; ')}.`);
  }
  if (payload.color?.provisional) disclosures.push('The colour scale is provisional: set from few events.');
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Colour is the count of events in a bin on a logarithmic ramp shared by every multiple; an empty bin is transparent. Dots are individual events of a class below N = 15.',
  ]);
  return notes.done(modelsHazards(payload, 'feat-hist2d'));
}

/* ================================================================ C11 == */

/** The notes of the no-primary rate card. */
export function primariesNotes({ payload, state = null, experiment = null, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? MODELS_TITLES['prim-rate']);
  const o = payload.overall ?? {};
  const bins = rateBins(payload);
  notes.section(SECTION.selection, [
    selectionLine(state, experiment),
    `${plural(o.n_events ?? 0, 'event')} in ${plural(bins.length, 'momentum bin')}.`,
  ]);
  notes.section(SECTION.drawn, [sentence(payload.definition), ...noteLines(payload.notes)]);
  const disclosures = [];
  if (Number.isFinite(o.fraction)) {
    disclosures.push(`Whole selection: ${formatPercent(o.fraction, 2)} (${formatInt(o.n_no_primary)} of ${formatInt(o.n_events)}), `
      + `${o.interval?.label ?? '95% interval'} [${formatPercent(o.interval?.lo, 2)}, ${formatPercent(o.interval?.hi, 2)}].`);
  }
  const wide = bins.filter((b) => b.n < WIDE_BELOW_N);
  if (wide.length) disclosures.push(`${plural(wide.length, 'bin')} with N < ${WIDE_BELOW_N}, whose Wilson intervals are correspondingly wide: ${wide.map((b) => `${b.label} (N = ${formatInt(b.n)})`).join(', ')}.`);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Each bin is a point at its fraction with a capped, asymmetric whisker: the 95% Wilson score interval of the fraction, events being the independent units. The y axis is the full 0–100%.',
    'The dotted rule is the whole selection\'s fraction; its Wilson interval is in its tooltip, not drawn.',
  ]);
  const pc = payload.primary_count;
  if (pc?.value?.length) {
    const parts = pc.value.map((v, i) => `${i === pc.value.length - 1 && pc.top_bucket ? pc.top_bucket : v}: ${formatInt(pc.events?.[i])}`);
    notes.section(MODELS_HEADINGS.counts, [`Events by number of primary-tagged hit rows (exact): ${parts.join(', ')}.`]);
  }
  return notes.done(modelsHazards(payload, 'prim-rate'));
}

/* ========================================================== res-scaling == */

/**
 * The drawer title of the resolution card when the shell passes none. Kept
 * out of MODELS_TITLES, which the dark golden records as it stood.
 */
export const RES_SCALING_TITLE = 'Energy Resolution vs. 1/√E';

/** The same for the E (GeV) view: the shell's `cardTitle` names it so when it passes a title. */
export const RES_SCALING_ENERGY_TITLE = 'Energy Resolution vs. E';

/** The drawer titles under the Median |rel. err.| estimator, the shell's `cardTitle` words (brief section 4). */
export const RES_SCALING_MEDIAN_TITLE = 'Median Relative Error vs. 1/√E';
export const RES_SCALING_MEDIAN_ENERGY_TITLE = 'Median Relative Error vs. E';

/** The default drawer title of the card for the estimator the payload carries and the view. */
function resDefaultTitle(payload, energy) {
  const median = payload?.estimator?.name === 'median';
  if (energy) return median ? RES_SCALING_MEDIAN_ENERGY_TITLE : RES_SCALING_ENERGY_TITLE;
  return median ? RES_SCALING_MEDIAN_TITLE : RES_SCALING_TITLE;
}

/**
 * The estimator the response plots, as the drawer words it: the payload's own
 * `estimator` block (label, definition, interval, weight, calibration,
 * relation, literature) says what is plotted, and this gathers the phrases the
 * two views share. Under `sample` every phrase is the one the drawer always
 * had; a payload without an estimator block is read as `sample`.
 */
function resWords(payload, gates) {
  const est = payload.estimator ?? {};
  const name = est.name ?? 'sample';
  const sample = name === 'sample';
  const symbol = sample ? 'σ/E' : (est.symbol ?? 'σ/E');
  const intervalName = sample ? 'χ² interval' : (name === 'median' ? 'bootstrap or order-statistic interval' : 'bootstrap interval');
  return {
    est, name, sample, symbol,
    whisker: sample ? 'χ² whisker' : 'interval whisker',
    intervalName,
    // The capped whisker's legend line.
    whiskerLegend: (sample
      ? 'The capped whisker is the 95% χ² interval of the window\'s σ/E (N − 1 degrees of freedom, R̄\'s own error neglected): the uncertainty of the aggregate, never the spread of its events.'
      : `The capped whisker is the 95% interval of the window's ${symbol}: ${sentence(est.interval?.label ?? 'a bootstrap interval')} It is the uncertainty of the aggregate, never the spread of its events.`)
      + (name === 'robust'
        ? ` It is drawn from N = ${formatInt(gates.whisker_n)}, the robust floor, below which no window is drawn.`
        : ` It is drawn from N = ${formatInt(gates.whisker_n)}; windows below N = ${formatInt(gates.fit_n)} are faded, never below 3:1 against the card.`),
    // The fit weights: the clause inside "each by weighted least squares" and, off sample, the server's own
    // sentence, which describes the series' pooled scale c (brief-fix F1), never a window's own κ.
    weightClause: sample
      ? 'weights 1/se², se the delta-method standard error of σ/μ recomputed at the fitted value and iterated'
      : 'weights 1/se², se = c·ŷ/√N with c the series\' pooled scale (below), recomputed at the fitted value and iterated',
    weightSentence: sample ? '' : sentence(est.weight?.label ?? ''),
    // Why a window is not estimable.
    unreportedWhy: (w) => ((w.n ?? 0) < gates.report_n ? `N = ${formatInt(w.n ?? 0)}`
      : (name === 'robust' ? 'median R ≤ 0' : (name === 'median' ? 'no median calibration c̃' : 'R̄ ≤ 0'))),
  };
}

/** A symbol with its first letter capitalised where it is an ASCII letter ("median rel." to "Median rel."), else as it is (σ/E). */
const capital = (t) => (/^[a-z]/.test(t) ? t[0].toUpperCase() + t.slice(1) : t);

/** The Selection line that names the estimator on show. */
function estimatorLine(w) {
  return w.est.label ? `Estimator: ${w.est.label}.` : '';
}

/** "−12.3%" or "+4.5%": a signed percent with the minus sign U+2212. */
function signedPct(v) {
  if (!Number.isFinite(v)) return '—';
  const t = sigFigs(v, 3);
  return `${v > 0 ? '+' : ''}${t}%`;
}

/** The medians' calibration lines: c̃ beside c_sum per shower (median mode), from the payload's `estimator.calibration.showers`. */
function calibrationLines(w) {
  const cal = w.est.calibration;
  if (w.name !== 'median' || !cal) return [];
  const showers = Object.entries(cal.showers ?? {});
  const lines = [sentence(cal.label ?? '')];
  for (const [key, c] of showers) {
    const owner = showers.length > 1 ? `Shower ${String(key).toUpperCase()}` : 'The deposit';
    lines.push(Number.isFinite(c.c_median)
      ? `${owner}: c̃ = ${sigFigs(c.c_median, 6)} beside c_sum = ${sigFigs(c.c_sum, 6)} (${plural(c.n ?? 0, 'event')} with E_dep > 0${c.n_zero_deposit ? `, ${formatInt(c.n_zero_deposit)} with a zero deposit left out of c̃` : ''}); `
        + `the median calibration c̃ makes the deposit's median response exactly 1 over the selection's events with E_dep > 0${c.n_zero_deposit ? ', not over the zero-deposit events, which stay in the windows' : ''}`
        + `${Number.isFinite(c.c_sum) && c.c_median > 0 ? `; c_sum would give them a median response c_sum/c̃ − 1 = ${signedPct(100 * (c.c_sum / c.c_median - 1))}` : ''}.`
      : `${owner}: no c̃, no selected event has E_dep > 0 (c_sum = ${sigFigs(c.c_sum, 6)}), so the deposit has no median value.`);
  }
  return lines.filter(Boolean);
}

/*
 * The calibrated deposit's Deposit toggle and the E view's E max slider (res-emax; Martin's decisions of
 * 2026-11-17). While the deposit is hidden no line of either drawer describes it, apart from the one Selection
 * line that says it is hidden; the range basis is the server's `y_model.note` (the panel's `y.basis`).
 */

/** The Selection line of the Deposit toggle: hidden, forced on, or none (shown by choice, as before). */
function depositSelectionLine(deposit) {
  if (deposit?.hidden) {
    return 'Calibrated deposit: hidden by the card\'s Deposit toggle. Its windows, its fitted curve and its fit-table rows are not drawn, '
      + 'and the error-scale range follows the model series alone.';
  }
  if (deposit?.forced) return 'Calibrated deposit: drawn; it is this response\'s only series, so the Deposit toggle is shut.';
  return '';
}

/** The Marks-and-legend colour sentence; its deposit clause is left out while the deposit is hidden. */
function colourLead(hidden) {
  return hidden
    ? 'Colour is the series: a model in the hue E2 gives its source (ColorBrewer qualitative, ≥ 3:1 against the card).'
    : 'Colour is the series: the detector\'s calibrated deposit in ink, a model in the hue E2 gives its source (ColorBrewer qualitative, ≥ 3:1 against the card).';
}

/**
 * The server's notes of the 1/√E view as lines, with the deposit left out while it is hidden: a note that begins
 * with a hidden series' label, one that names E_dep or the detector series (its definition, its calibration, the
 * c̃ and c_sum sentences), the XGBoost note's closing clause on the detector series' events, and the estimator
 * note's own clauses on the deposit's calibration.
 */
function withoutDeposit(lines, payload) {
  const labels = (payload.series ?? []).filter((s) => isDepositSeries(s)).map((s) => s.label).filter(Boolean);
  return lines
    .filter((line) => !labels.some((label) => line.startsWith(label)) && !/E_dep|^The detector series/u.test(line))
    .map((line) => line
      .replace(/\s*The detector series uses every selected event[^.]*\./u, '')
      // The estimator note's own clauses on the deposit's calibration: "and c cancels in it, so the detector series does not
      // depend on the calibration" (robust, sample) and ", and it depends on the deposit's calibration" (median).
      .replace(/,? and c cancels in [^,.]*, so the detector series does not depend on the calibration/u, '')
      .replace(/,? and it depends on the deposit's calibration/u, ''));
}

/**
 * Each model series' median-response range over the fitted windows of the mode
 * on show, with the one explanation of what a regressor trained on a bounded
 * range does to it. `model` is either view's pure model.
 */
function responseRangeLines(w, model) {
  const lines = [];
  const modeText = model.mode === 'anchors' ? 'the 3-anchor mode' : 'the all-windows mode';
  const modelSeries = model.series.filter((s) => s.raw?.source && s.raw.source !== 'detector');
  for (const s of modelSeries) {
    const r = s.raw.median_response_range?.[model.mode === 'anchors' ? 'anchors' : 'all'];
    lines.push(Array.isArray(r) && r.every(Number.isFinite)
      ? `${s.label}: the median response R̃ − 1 runs from ${signedPct(r[0])} to ${signedPct(r[1])} over the fitted windows of ${modeText}.`
      : `${s.label}: no median response range, fewer than two fitted windows of ${modeText}.`);
  }
  if (modelSeries.length) {
    const tail = w.name === 'median'
      ? 'The median relative error divides nothing out, so this bias is part of the plotted value there.'
      : `${w.name === 'robust' ? 'The robust width' : 'The sample width'} divides the bias out, so it does not enter the plotted value, though the narrowing does.`;
    lines.push('A regressor trained on a bounded momentum range pulls its predictions toward mid-range, which narrows a width near the range\'s ends and adds a bias to the median relative error there. ' + tail);
  }
  return lines;
}

/**
 * Under robust: the windows of 2 ≤ N < 20 with no value, which Sample σ/μ
 * draws, and, never blamed on N (brief-fix F3, F7), the windows of N ≥ 20
 * with no robust σ/E (median response ≤ 0) and those whose interval is
 * withheld. The server's count of the same is not reprinted (`restatedNote`).
 */
function robustFloorLine(w, model) {
  if (w.name !== 'robust') return '';
  const floor = model.gates.report_n;
  const windows = model.series.flatMap((s) => s.raw.windows ?? []);
  const below = windows.filter((x) => (x.n ?? 0) >= 2 && (x.n ?? 0) < floor && !Number.isFinite(x.value));
  const bare = windows.filter((x) => (x.n ?? 0) >= floor && !Number.isFinite(x.value));
  const withheld = windows.filter((x) => weightState({ name: 'robust' }, x) === 'withheld');
  // Each clause only where its count is not 0 (review nit 8: never "0 windows … have no Robust σ/E").
  let line = below.length
    ? `${plural(below.length, 'window')} of 2 ≤ N < ${formatInt(floor)} ${below.length === 1 ? 'has' : 'have'} no Robust σ/E, below its floor of N = ${formatInt(floor)} (the CLAUDE.md robust floor), `
      + `so ${below.length === 1 ? 'it is' : 'they are'} not drawn; Sample σ/μ reports ${below.length === 1 ? 'it' : 'them'} from N = 2.`
    : '';
  if (bare.length) {
    const one = bare.length === 1;
    line += `${line ? ' ' : ''}${plural(bare.length, 'window')} of N ≥ ${formatInt(floor)} ${one ? 'reports' : 'report'} no Robust σ/E because ${one ? 'its' : 'their'} median response is not positive, so ${one ? 'it is' : 'they are'} not drawn${below.length ? ' either' : ''}.`;
  }
  if (withheld.length) {
    const one = withheld.length === 1;
    line += `${line ? ' ' : ''}${plural(withheld.length, 'window')} ${one ? 'reports' : 'report'} a Robust σ/E whose interval is withheld: more than 2.5% of ${one ? 'its' : 'their'} bootstrap replicates have a median R ≤ 0, so no whisker, SE or fit weight.`;
  }
  return line;
}

/** The drawer's decomposition sentence (brief-fix, R-ui M3), the panel's `RES_DECOMPOSITION`, re-exported for the tests. */
export { RES_DECOMPOSITION };

/**
 * Each series' pooled scale of the fit weights se = c·ŷ/√N (brief-fix F1,
 * the payload's `weight_scale`): c, over its windows from 4 GeV, one per
 * series (single-curve round D3, Martin's decision of 2026-11-15), then the
 * brief's weights sentence; one What-is-drawn line, '' under sample. Both
 * views print it, since both table the three-term fit.
 */
function pooledScaleLine(w, model, payload) {
  if (w.sample) return '';
  const { gates } = model;
  const noiseMin = noiseMinGev(payload);
  const lowRange = `${formatNumber(noiseMin)}–${formatNumber(gates.e_min_gev)} GeV`;
  const weighted = (x) => weightState({ name: w.name }, x) === 'weighted';
  const parts = model.series.map((s) => {
    const ws = s.raw.weight_scale;
    if (!ws) return null;
    const windows = s.raw.windows ?? [];
    if (!Number.isFinite(ws.c)) {
      return `${s.label}: none, no window from ${formatNumber(gates.e_min_gev)} GeV carries a fit weight, so no fit`;
    }
    const strong = windows.some((x) => (x.n ?? 0) >= gates.fit_n && !x.off_axis && (x.p_lo ?? 0) >= gates.e_min_gev && weighted(x));
    return `${s.label}: c = ${sigFigs(ws.c, 3)} over ${plural(ws.n_windows ?? 0, 'window')}`
      + (strong ? '' : ` of N ≥ ${formatInt(gates.whisker_n)}, since no window of N ≥ ${formatInt(gates.fit_n)} carries a fit weight`);
  }).filter(Boolean);
  if (!parts.length) return '';
  const e4 = formatNumber(gates.e_min_gev);
  return `The pooled scale, one per series, c over its windows from ${e4} GeV: it cancels in the fitted parameters and sets only their χ², S and errors. `
    + `${parts.join('; ')}. `
    + `The ${NOISE_FORM} fit weights its windows of ${lowRange} by the same c, se = c·ŷ/√N, which they do not enter, `
    + 'so their residuals count in S and the misfit verdict at c·ŷ/√N, not at their own bootstrap errors.';
}

/**
 * The windows that carry no fit weight for a reason other than N (brief-fix
 * F3, F7), as Disclosures lines: per series its tied windows of N ≥ 20 on the
 * axis, and the drawn windows whose robust interval is withheld. `points` are
 * the drawn windows of the view.
 */
function noWeightLines(w, model, points) {
  if (w.sample) return [];
  const { gates } = model;
  const lines = [];
  for (const s of model.series) {
    const tied = (s.raw.windows ?? []).filter((x) => (x.n ?? 0) >= gates.fit_n && !x.off_axis && weightState({ name: w.name }, x) === 'tied');
    if (!tied.length) continue;
    const one = tied.length === 1;
    lines.push(`${s.label}: ${plural(tied.length, 'window')} of N ≥ ${formatInt(gates.fit_n)} (${tied.map((x) => x.label).join(', ')}) ${one ? 'carries' : 'carry'} no fit weight: `
      + `${one ? 'its' : 'their'} bootstrap SE is below 10⁻⁶ of ${one ? 'its' : 'their'} value (tied replicates, which differ by rounding alone), so ${one ? 'it is' : 'they are'} drawn in the all-windows mode only, never fitted.`);
  }
  const withheld = points.filter((p) => weightState({ name: w.name }, p.w) === 'withheld').length;
  if (withheld) {
    const one = withheld === 1;
    lines.push(`${plural(withheld, 'window')} ${one ? 'is' : 'are'} drawn as a faded dashed ring with no whisker and not fitted: ${one ? 'its' : 'their'} robust interval is withheld, `
      + 'more than 2.5% of the bootstrap replicates having a median R ≤ 0, which would cut the interval\'s upper tail; the tooltip gives the count.');
  }
  return lines;
}

/** The series of the mode in force whose robust fit declines its one fittable window (brief-fix F4), as Disclosures lines. */
function declinedLines(w, model) {
  if (w.name !== 'robust') return [];
  return model.series.map((s) => {
    const one = declinedWindow({ name: w.name }, s.raw, s.mf, model.mode, model.gates);
    if (!one) return '';
    // On the E view a series that declines the fits from 4 GeV may still draw its a/√E ⊕ b ⊕ c/E curve, which runs
    // through its own windows from 1 GeV (SC-backend-check's observation): "no fit is drawn" would then be false.
    if (model.view === 'energy' && s.drawnForm === 'noise') {
      const among = (s.drawn?.points ?? []).includes(one.bin) ? `, ${one.label ?? `bin ${one.bin}`} among them` : '';
      return `${s.label}: ${declinedText(one)}, so a₀/√E and the affine and quadrature fits are not fitted; its ${NOISE_FORM} curve is drawn, `
        + `through its own windows from ${formatNumber(noiseMinGev(model.payload))} GeV${among}.`;
    }
    return `${s.label}: ${declinedText(one)}, so no fit is drawn${model.mode === 'anchors' ? '; the window is drawn in the all-windows mode' : '; the window is drawn unfitted'}.`;
  }).filter(Boolean);
}

/** The relation and MAE/E sentence closing the Disclosures, by estimator; sample keeps today's. */
function relationLine(w) {
  if (w.sample) {
    return 'MAE/E is not σ/E: for unbiased Gaussian errors MAE/E = √(2/π)·σ/E ≈ 0.798·σ/E, and MAE also carries the bias that σ(R)/μ(R) divides out; this card plots σ(R)/μ(R) and never converts one into the other.';
  }
  const rel = w.est.relation ?? '';
  const mae = 'MAE/E is not σ/E either: for unbiased Gaussian errors MAE/E = √(2/π)·σ/E ≈ 0.798·σ/E, and MAE also carries the bias that σ(R)/μ(R) divides out.';
  return w.name === 'median'
    ? `${sentence(rel)} ${mae} This card plots the median relative error and never converts it into σ/E.`
    : `${sentence(rel)} ${mae} This card plots the robust width IQR(R) / (1.349 · median R) and never converts one into another.`;
}

/**
 * A series' on-axis windows that are not drawn because they report no value,
 * as Disclosures lines. Under robust the ones below the robust floor are
 * named as such (never "not estimable"), apart from those of N ≥ 20 whose
 * median response is not positive; the other estimators keep one line.
 */
function unreportedLines(w, s, gates) {
  if (!s.unreported.length) return [];
  const list = (xs) => xs.map((x) => `${x.label} (${w.unreportedWhy(x)})`).join(', ');
  if (w.name !== 'robust') {
    return [`${s.label}: on the axis but not drawn, ${w.symbol} not estimable: ${list(s.unreported)}; ${w.symbol} is reported from N = ${formatInt(gates.report_n)}.`];
  }
  const below = s.unreported.filter((x) => (x.n ?? 0) < gates.report_n);
  const bare = s.unreported.filter((x) => (x.n ?? 0) >= gates.report_n);
  return [
    below.length ? `${s.label}: on the axis but not drawn, below the robust floor of N = ${formatInt(gates.report_n)}, from which Robust σ/E is reported: ${list(below)}.` : '',
    bare.length ? `${s.label}: on the axis but not drawn, no Robust σ/E because the median response is not positive: ${list(bare)}.` : '',
  ].filter(Boolean);
}

/** The payload notes the builder states itself, from structure, in the section they belong to. */
function restatedNote(line, labels) {
  return labels.some((label) => line.startsWith(`${label} (`))
    || /^Off the axis:|^The y range follows|^The y range is provisional:|^E on both axes|^The top axis is an exact|^Anchors:|^Fits:|^σ\/E is reported from|median response R̃ − 1 from|^A regressor trained on a bounded|^For unbiased Gaussian errors median/.test(line)
    // The median calibration c̃ (calibrationLines), the robust floor count (robustFloorLine) and the tied windows (noWeightLines).
    || /: c̃ = 1 \/ median\(E_dep \/ p\) = .* so the deposit's median response over them is 1/.test(line)
    || /^[\d,]+ of the [\d,]+ windows across the series hold N < /.test(line)
    || /: [\d,]+ windows? with a bootstrap SE below 10⁻⁶ of (?:its|their) value/.test(line);
}

/**
 * The Selection lines both views share: the filters, the events and series,
 * the model series, its validation split and the frame note. `model` is
 * either view's (both carry `series` and `nShowers`).
 */
function resSelectionLines(payload, state, experiment, model, shower) {
  const m = payload.model ?? {};
  const selection = [
    selectionLine(state, experiment),
    `${plural(payload.n_events ?? 0, 'event')}; ${model.series.length ? model.series.map((s) => `${s.label} (N = ${formatInt(s.raw.n)})`).join('; ') : 'no series'}`
      + `${shower && shower !== 'both' && model.nShowers > 1 ? `; shower ${String(shower).toUpperCase()} only` : ''}.`,
  ];
  if (m.available) {
    selection.push(m.source === 'xgb'
      ? `Model series: ${m.label ?? 'the XGBoost momentum regressor'}.`
      : `Model series: ${m.label ?? 'the energy network'}${m.frame ? `, read in the ${m.frame} frame` : ''}.`);
  } else if (m.reason) {
    selection.push(`No model series: ${sentence(m.reason)}`);
  }
  if (m.split) {
    selection.push(`Validation split: ${formatInt(m.split.n_validation)} of the ${formatInt(m.split.n_selected)} selected events `
      + `(${formatNumber(100 * (m.split.fraction ?? 0), 0)}%); ${formatInt(m.split.n_training_excluded)} training events are left out of the model series`
      + `${m.split.reproduced === false ? ', and the notebook\'s training split is not reproduced' : ''}.`);
  }
  if (payload.meta?.coord_system_note) selection.push(sentence(payload.meta.coord_system_note));
  return selection;
}

/* ---- the E view's drawer ---- */

/** A fitted span as the panel words it: "5–20 GeV". */
const spanGeV = (span) => (span ? `${formatNumber(span[0])}–${formatNumber(span[1])} GeV` : 'no window');

/** The E view's three-term form, as every sentence names it (brief res-noise §8). */
const NOISE_FORM = 'a/√E ⊕ b ⊕ c/E';

/**
 * The forms the E view's drawer names: the two it can draw, one per series
 * (the three-term form, else a₀/√E), and the quadrature fit, which it tables only.
 */
const ENERGY_FORM_NAMES = Object.freeze({
  quadrature: 'quadrature fit a/√E ⊕ b',
  pinned: 'origin-pinned fit a₀/√E ⊕ 0',
  noise: `${NOISE_FORM} fit`,
});

/** A form as a short list names it: "a/√E ⊕ b", "a/√E ⊕ b ⊕ c/E" or "a₀/√E ⊕ 0". */
function energyFormShort(form) {
  if (form === 'quadrature') return 'a/√E ⊕ b';
  if (form === 'noise') return NOISE_FORM;
  return 'a₀/√E ⊕ 0';
}

/*
 * Which curve a series draws (`drawnForm`, `drawn`) and its spans, entries and
 * cuts are read from the panel's model, so each count is the model's. The
 * three-term fit's own terms, held terms, low anchor and reason are read from
 * the payload (`fits[mode].noise`, `noise_reason`, `gates.noise_min_gev`).
 */

/** A model series' a/√E ⊕ b ⊕ c/E block in `mode` (its payload series' `fits[mode].noise`), or null. */
const noiseFitOf = (s, mode) => s?.raw?.fits?.[mode]?.noise ?? null;

/** Why a model series has no a/√E ⊕ b ⊕ c/E fit in `mode` (the server's `noise_reason`), or null. */
const noiseReasonOf = (s, mode) => s?.raw?.fits?.[mode]?.noise_reason ?? null;

/** The lowest window edge the three-term fit uses, GeV: the server's `noise_min_gev` (1). */
function noiseMinGev(payload) {
  const g = payload?.gates?.noise_min_gev;
  if (Number.isFinite(g)) return g;
  const e = payload?.axis?.energy?.noise_min_gev;
  return Number.isFinite(e) ? e : 1;
}

/** "a", "a and c", "a, b and c". */
function andList(xs) {
  return xs.length < 2 ? (xs[0] ?? '') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`;
}

/** The terms a three-term fit holds at 0, in the order a, b, c (the server's `params.held`). */
function heldTerms(fit) {
  const held = fit?.params?.held;
  return Array.isArray(held) ? ['a', 'b', 'c'].filter((t) => held.includes(t)) : [];
}

/**
 * A series' held terms, as the Disclosures line words them: "b held at 0 by the
 * constraint b² ≥ 0." The line ends there: no band is drawn on this view, so
 * it has no band sentence to add. c is named as the noise term c/E, never a
 * bare c, which the drawer also uses for the calibration c·E_dep and the
 * pooled scale.
 */
function heldLine(label, held) {
  const name = (t) => (t === 'c' ? 'the noise term c/E' : t);
  const one = held.length === 1;
  return `${label}: ${andList(held.map(name))} held at 0 by the constraint${one ? '' : 's'} ${andList(held.map((t) => `${t}² ≥ 0`))}.`;
}

/** A window's label in a payload series, by bin: "3–4 GeV". */
function binLabelOf(raw, bin) {
  const w = (raw?.windows ?? []).find((x) => x.bin === bin);
  return w?.label ?? `bin ${bin}`;
}

/**
 * The largest |ρ| among a drawn three-term fit's squares from which the
 * drawer calls them strongly correlated (the brief's §11 sentence); below it
 * the sentence gives the largest |ρ| instead, since a recording whose terms
 * correlate at −0.3 is not strongly correlated.
 */
const STRONG_RHO = 0.7;

/** "three", "two": a small count in words, as the brief's low-anchor sentence writes it. */
const COUNT_WORDS = Object.freeze(['no', 'one', 'two', 'three', 'four', 'five']);
const countWord = (n) => COUNT_WORDS[n] ?? formatInt(n);

/**
 * The ratio panel's deposit reference for one shower, from the payload alone
 * (brief res-noise §4.2): the shower's deposit a/√E ⊕ b ⊕ c/E fit, whose
 * ratio marks start at `noise_min_gev`; else its a₀/√E fit, from
 * `curve_min_gev` as before, with the deposit's `noise_reason`; else none.
 * {shower, owner, form ('noise' | 'pinned' | null), fit, label (the series'),
 * floor (GeV), span, provisional, misfit, noiseReason, reason}.
 */
function depositRefOf(payload, shower, mode, nShowers, floors) {
  const owner = nShowers > 1 ? `Shower ${String(shower).toUpperCase()}` : 'The deposit';
  const det = (payload.series ?? []).find((s) => s.source === 'detector' && (s.shower ?? 'a') === shower) ?? null;
  const base = { shower, owner, form: null, fit: null, label: det?.label ?? null, floor: null, span: null, provisional: false, misfit: false, noiseReason: null, reason: null };
  if (!det) return { ...base, reason: 'this shower has no calibrated-deposit series' };
  const mf = det.fits?.[mode] ?? null;
  const noise = mf?.noise ?? null;
  if (noise) {
    return {
      ...base, form: 'noise', fit: noise, floor: floors.noise, span: Array.isArray(noise.span_gev) ? noise.span_gev : null,
      provisional: Boolean(noise.provisional), misfit: noise.misfit === true,
    };
  }
  const pinned = mf?.pinned ?? null;
  const noiseReason = mf?.noise_reason ?? null;
  if (!Number.isFinite(pinned?.params?.a0)) {
    return { ...base, noiseReason, reason: `the deposit has no ${NOISE_FORM} or a₀/√E fit in this mode` };
  }
  return {
    ...base, form: 'pinned', fit: pinned, floor: floors.curve, span: Array.isArray(mf.span_gev) ? mf.span_gev : null,
    provisional: Boolean(pinned.provisional ?? mf.provisional), misfit: pinned.misfit === true, noiseReason,
  };
}

/**
 * The 3-anchor mode's low-anchor sentence (brief res-noise §8), once, from the
 * drawn three-term fits' `points` and `low_anchor`: the brief's words where
 * every fit runs through the three anchors and one shared low anchor, the
 * count and window per series otherwise, and a line for a fit that has no low
 * anchor (no other window from 1 GeV fittable). [] outside the 3-anchor mode
 * or with no three-term fit drawn.
 */
function lowAnchorLines(mode, noiseDrawn, gates, noiseMinText) {
  if (mode !== 'anchors' || !noiseDrawn.length) return [];
  const anchorFloor = formatNumber(gates.anchor_low_gev);
  const why = `since anchors from ${anchorFloor} GeV cannot fix a 1/E term`;
  const withLow = noiseDrawn.filter(({ fit }) => fit.low_anchor !== null && fit.low_anchor !== undefined)
    .map(({ s, fit }) => ({ s, k: (fit.points ?? []).filter((b) => b !== fit.low_anchor).length, low: binLabelOf(s.raw, fit.low_anchor) }));
  const without = noiseDrawn.filter(({ fit }) => fit.low_anchor === null || fit.low_anchor === undefined);
  const lines = [];
  if (withLow.length) {
    const shapes = new Set(withLow.map((x) => `${x.k}|${x.low}`));
    if (shapes.size === 1) {
      const { k, low } = withLow[0];
      lines.push(`In the 3-anchor mode ${NOISE_FORM} runs through the ${countWord(k)} anchor${k === 1 ? '' : 's'} and the lowest fittable window from ${noiseMinText} GeV (${low}), ${why}.`);
    } else {
      lines.push(`In the 3-anchor mode ${NOISE_FORM} runs through each series' anchors and its lowest fittable window from ${noiseMinText} GeV, ${why}: `
        + `${withLow.map(({ s, k, low }) => `${s.short}, ${countWord(k)} anchor${k === 1 ? '' : 's'} and ${low}`).join('; ')}.`);
    }
  }
  for (const { s, fit } of without) {
    const k = (fit.points ?? []).length;
    lines.push(`${s.label}: in the 3-anchor mode ${NOISE_FORM} runs through its ${countWord(k)} anchor${k === 1 ? '' : 's'} alone, with no low anchor: no other window from ${noiseMinText} GeV is fittable.`);
  }
  return lines;
}

/** "no a/√E ⊕ b ⊕ c/E fit: …", the server's reason with its first letter lowered to follow a colon. */
const lowerFirst = (t) => String(t ?? '').replace(/^No /u, 'no ').replace(/\.$/u, '');

/** Where the article derives the E view: its section, by number and title, which the drawer names. */
export const RES_ENERGY_METHOD_SECTION = Object.freeze({ number: '2.4.11', title: 'Resolution scaling against E' });

/**
 * The server's E-view range sentence as its basis only: a trailing "n marks
 * beyond it are clipped, not rescaled." counts windows of every series and both
 * modes, which the drawer never reprints; it states the model's own counts.
 */
function rangeBasis(note) {
  return String(note ?? '').replace(/\s*\S+ marks? beyond it (?:is|are) clipped, not rescaled\.\s*$/u, '');
}

/** "in the 3-anchor mode, both showers": the mode and the shower choice a count belongs to. */
function inForce(model, shower) {
  const mode = model.mode === 'anchors' ? 'the 3-anchor mode' : 'the all-windows mode';
  if (model.nShowers < 2) return `in ${mode}`;
  return `in ${mode}, ${shower && shower !== 'both' ? `shower ${String(shower).toUpperCase()} only` : 'both showers'}`;
}

/** What made a band wide, as the drawer writes it after an outlined band: " (S = 3.62, ν = 1, q = 12.71)", or ''. */
function bandWhy(fit = {}, sig) {
  const why = [
    Number.isFinite(fit.scale_factor) && fit.scale_factor > 1 ? `S = ${sig(fit.scale_factor)}` : null,
    Number.isFinite(fit.ndf) ? `ν = ${formatInt(fit.ndf)}` : null,
    Number.isFinite(fit.band_quantile) ? `q = ${sigFigs(fit.band_quantile, 4)}` : null,
  ].filter(Boolean).join(', ');
  return why ? ` (${why})` : '';
}

/**
 * Each literature curve's hue on every card, as the drawer names it (palette.js `LITERATURE_HUES`):
 * "π± a brown and e± a purple", or with `preposition` 'in ' "π± in a brown and e± in a purple".
 */
function literatureHueList(preposition = '') {
  return RESOLUTION_REFERENCES.map((e) => `${e.particle} ${preposition}a ${LITERATURE_HUES[e.key]}`).join(' and ');
}

/**
 * The E view's legend line on the literature curves: which are drawn and what
 * each is to the ratio panel, the buttons that choose them, and their colours.
 */
function literatureLegendLine(model, depositHidden = false) {
  const hues = `Each literature curve has a colour of its own on every card, ${literatureHueList()}: ColorBrewer qualitative hues kept apart from ${depositHidden ? '' : 'the deposit ink and '}E2's four hues under normal vision, deuteranopia and protanopia.`;
  const buttons = `The ${RESOLUTION_REFERENCES.map((e) => e.particle).join(' and ')} buttons draw either curve, both (the default) or neither. `
    + `The ratio panel divides by the curve drawn; with both drawn, by the one the windows lie farther from; with neither, ${depositHidden ? 'nothing, since the deposit is hidden' : 'by each shower\'s deposit fit'}.`;
  if (!model.literature.length) return `A literature curve is a dotted line in its own colour; none is drawn now. ${buttons} ${hues}`;
  const refLit = model.literature.find((l) => l.isReference);
  const others = model.literature.filter((l) => !l.isReference);
  const parts = [];
  if (refLit) parts.push(`the ${refLit.entry.particle} curve is the ratio's reference`);
  if (others.length) {
    parts.push(`the ${others.map((l) => l.entry.particle).join(' and ')} curve${others.length > 1 ? 's are' : ' is'} drawn beside it, `
      + 'and on the ratio panel divided by it');
  }
  const labelled = model.endLabels.main.some((l) => l.literature) ? ', each labelled in the end column with its particle, in ink, led by a key stroke in the curve\'s own colour, dash, width and strength' : '';
  return `Literature curves are dotted lines in their own colours${labelled}; they are references, not measurements, and never set a range. `
    + `Here ${parts.join('; ')}. ${buttons} ${hues}`;
}

/**
 * One shower's deposit reference, as What is drawn words it (`depositRefOf`):
 * which fit divides its windows and from which energy a window gets a ratio
 * mark, or why the shower has none.
 */
function depositReferenceLine(model, r) {
  if (r.reason) return `${r.owner}: no ratio marks, ${r.reason}.`;
  const sig = (v) => sigFigs(v, 3);
  const misfit = r.misfit
    ? `, a form that does not describe the deposit's windows (S = ${sig(r.fit.scale_factor)} > ${formatNumber(model.gates.misfit_scale)})`
    : '';
  const fitted = `fitted over ${spanGeV(r.span)}${r.provisional ? ', provisional' : ''}${misfit}`;
  if (r.form === 'noise') {
    return `${r.owner}: the ratio divides by its deposit's ${NOISE_FORM} fit (${r.label}), ${fitted}; `
      + `a window gets a ratio mark from ${formatNumber(r.floor)} GeV, the lowest window edge that fit can use.`;
  }
  return `${r.owner}: the ratio divides by its deposit's a₀/√E fit (${r.label}), since it has no ${NOISE_FORM} fit`
    + `${r.noiseReason ? ` (${lowerFirst(r.noiseReason).replace(/^no a\/√E ⊕ b ⊕ c\/E fit: /u, '')})` : ''}, ${fitted}; `
    + `it is evaluated from ${formatNumber(r.floor)} to ${formatNumber(model.x.max)} GeV only, so a window gets a ratio mark from ${formatNumber(r.floor)} GeV.`;
}

/**
 * The Disclosures line naming the fits drawn faded because their form does not
 * describe their windows (the server's `misfit`): series, form, S and χ²/ν,
 * or '' when none is drawn. `items` [{s, f}] are the drawn fits of the mode in
 * force; `formName(form)` names a form as its view does.
 */
function misfitLine(items, gates, formName) {
  const listed = items.filter(({ f }) => f.misfit);
  if (!listed.length) return '';
  const n = listed.length;
  const scale = formatNumber(gates.misfit_scale);
  return `${plural(n, 'fit')} ${n === 1 ? 'is' : 'are'} drawn faded because ${n === 1 ? 'its form does' : 'their forms do'} not describe `
    + `${n === 1 ? 'its' : 'their'} windows: ν ≥ 1 and S = √(χ²/ν) > ${scale}, the residuals averaging more than ${scale} of the windows' own `
    + `standard errors, so ${n === 1 ? 'it never sets' : 'none sets'} a range: `
    + `${listed.map(({ s, f }) => `${s.label}, ${formName(f.form)} (S = ${sigFigs(f.fit.scale_factor, 3)}, χ²/ν = ${sigFigs(f.fit.chi2 / f.fit.ndf, 3)})`).join('; ')}. `
    + 'The size of the misfit decides, not the χ² p-value: where windows hold hundreds of events, the test rejects a form for misfits no reader could see.';
}

/**
 * The notes of the resolution card's E view: σ/E against the energy in GeV,
 * one fitted curve per series (its a/√E ⊕ b ⊕ c/E, else its origin-pinned
 * a₀/√E ⊕ 0, else none; Martin's decision of 2026-11-15), with no band round
 * it, solid over the windows it was fitted to and dashed beyond, and the ratio
 * panel. Every sentence is built from the
 * panel's `energyModel` and the payload's `axis.energy`, never from matching
 * text, so each count is the model's and the drawer never states what the
 * plot does not show.
 */
function resolutionEnergyNotes({ payload, state, experiment, title, windows, shower, reference, literature, deposit, eMax }) {
  const notes = new Notes(title ?? resDefaultTitle(payload, true));
  const model = energyModel(payload, { windows, shower, reference, literature, deposit, eMax });
  if (!model) {
    notes.section(SECTION.disclosures, [
      'This response carries no energy-resolution series with an E-view axis (axis.energy), so the E view draws nothing.',
      ...metaDisclosures(payload),
    ]);
    return notes.done([]);
  }
  const { gates, mode, x, y, ratio, clipped } = model;
  const w = resWords(payload, gates);
  const ref = model.reference;
  const lit = ref.literature;
  const pct = (v) => (Number.isFinite(v) ? `${sigFigs(v, 3)}%` : '—');
  const sig = (v) => sigFigs(v, 3);
  const m = payload.model ?? {};
  const curveMin = formatNumber(model.curveMinGev);
  const yMin = formatNumber(model.yMinGev);
  const points = model.series.flatMap((s) => s.points);
  // One fitted curve per series (single-curve round, Martin's decision of 2026-11-15), read from the model's
  // `drawnForm` and `drawn`: the a/√E ⊕ b ⊕ c/E fit where it is drawable, else the origin-pinned a₀/√E fallback.
  const curves = model.series.filter((s) => s.drawn).map((s) => ({ s, f: s.drawn, form: s.drawnForm }));
  const noiseMin = noiseMinGev(payload);
  const noiseMinText = formatNumber(noiseMin);
  const noiseItems = model.series.map((s) => ({ s, reason: noiseReasonOf(s, mode) }));
  const noiseKnown = noiseItems.some((x) => x.reason) || curves.some(({ form }) => form === 'noise');
  // The series drawing a/√E ⊕ b ⊕ c/E (the payload's block: its terms, windows, low anchor), the ones that fall back to
  // a₀/√E with the server's reason, and the ones with no curve.
  const noiseDrawn = curves.filter(({ form }) => form === 'noise').map(({ s, f }) => ({ s, fit: f.fit }));
  const fallbacks = curves.filter(({ form }) => form === 'pinned');
  const noCurve = model.series.filter((s) => !s.drawn);
  // Every drawn curve's fitted span.
  const spanList = curves.map(({ s, f, form }) => ({ key: s.key, short: s.short, form, span: f.span }));
  const spanShared = model.spans.shared;
  // The ratio panel's deposit reference per shower, from the payload (brief res-noise §4.2).
  const floors = { noise: noiseMin, curve: model.curveMinGev };
  // Never read with the deposit hidden: no reference is then its fit, and the drawer does not describe it.
  const hidden = model.deposit.hidden;
  const depositRefs = hidden ? [] : Object.keys(ref.byShower ?? {}).map((sh) => depositRefOf(payload, sh, mode, model.nShowers, floors));
  // As the axis writes it: "1/8 to 8".
  const kText = `${ratioTickLabel(1 / ratio.k)} to ${ratioTickLabel(ratio.k)}`;
  const is = (n) => (n === 1 ? 'is' : 'are');
  // Under E max the axis may end between two ticks of its step: the end is ticked too (`eAxisTicks`).
  const endTicked = Array.isArray(x.ticks) && x.ticks.length > 0 && x.interval > 0
    && Math.abs(x.ticks[x.ticks.length - 1] / x.interval - Math.round(x.ticks[x.ticks.length - 1] / x.interval)) > 1e-9;

  // ---- Selection
  const selection = resSelectionLines(payload, state, experiment, model, shower);
  selection.push(estimatorLine(w));
  selection.push(`View: ${w.symbol} against the energy E in GeV, 0 to ${formatNumber(x.max)} GeV, with a ratio panel underneath on the same energy axis.`);
  if (x.eMax) {
    const em = x.eMax;
    selection.push(`E max: ${formatNumber(x.max)} GeV, set by the card's slider (${formatNumber(em.min)}–${formatNumber(em.max)} GeV in ${formatNumber(em.step)} GeV steps; `
      + 'its lower end is the data\'s highest window edge, so every window is on the axis). Nothing beyond it is drawn on either panel.');
  }
  selection.push(depositSelectionLine(model.deposit));
  if (ratio.none) {
    selection.push('Ratio to: none. The deposit is hidden and no literature curve is on, so the ratio panel draws no mark; switch on π±, e± or the deposit to draw one.');
  } else {
    selection.push(lit
      ? `Ratio to: ${ref.label}, the literature curve ${referenceEquation(lit)}, the same curve for every shower.`
      : `Ratio to: ${ref.label}.`);
  }
  selection.push(model.literature.length
    ? `Literature curves drawn: ${model.literature.map((l) => `${l.entry.particle}${l.isReference ? ' (the ratio\'s reference)' : ''}`).join(' and ')}.`
    : 'Literature curves drawn: none.');
  notes.section(SECTION.selection, selection.filter(Boolean));

  // ---- What is drawn
  const spanRule = spanShared && spanList[0].span
    ? `here ${spanGeV(spanList[0].span)}`
    : (spanList.length ? 'each its own, listed under Disclosures' : 'no fit is drawn for this selection');
  // The literature curves the reader drew beside the reference (the reference itself is always drawn).
  const beside = model.literature.filter((l) => !l.isReference);
  const refLines = lit
    ? [`The ratio's reference is the literature curve ${referenceEquation(lit)}, evaluated at every E on the axis and drawn dotted on the main panel in its own colour. `
      + 'The ratio panel draws no band about 1 for it: no interval reported.',
      ...beside.filter((l) => l.ratio?.rows?.length).map((l) => {
        const rows = l.ratio.rows;
        return `The ${l.entry.particle} curve, drawn beside it, is drawn on the ratio panel too, divided by it, one line for every shower: `
          + `${referenceEquation(l.entry)} over ${referenceEquation(lit)} reads ${sig(rows[0][1])} at ${formatNumber(rows[0][0])} GeV and ${sig(rows[rows.length - 1][1])} at ${formatNumber(rows[rows.length - 1][0])} GeV.`;
      })]
    : [...depositRefs.map((r) => depositReferenceLine(model, r)),
      'With no literature curve drawn, the ratio divides each shower by its own deposit fit.'];
  // With both curves drawn, why the ratio divides by the one it does.
  const choiceLine = referenceChoiceText(model);
  if (choiceLine) refLines.splice(1, 0, choiceLine);
  const method = RES_ENERGY_METHOD_SECTION;
  notes.section(SECTION.drawn, [
    model.rule ? sentence(model.rule) : 'Each window is drawn at E = 1/x², x = ⟨1/√p⟩ being the 1/√E view\'s own abscissa.',
    `Methodology §${method.number}, "${method.title}", derives this view, from E = 1/x² to the ratio panel's axis; §3.6 audits its marks.`,
    'Windows of different series at one energy are drawn at that energy, not set apart: a window sits on its own curve, which no offset could follow.',
    // This view's two drawn forms fit from different floors, so its mode line names both (the 1/√E view's
    // modeLabel says "from 4 GeV", true there).
    `Mode drawn: ${mode === 'all'
      ? `every window; a₀/√E fits those from ${curveMin} GeV and ${NOISE_FORM} those from ${noiseMinText} GeV, each with N ≥ ${formatInt(gates.fit_n)}`
      : `${modeLabel(mode, gates)}${noiseDrawn.some(({ fit }) => fit.low_anchor !== null && fit.low_anchor !== undefined) ? `, with the low anchor of ${NOISE_FORM}` : ''}`}. ${mode === 'anchors'
      ? 'The windows control reads "3 anchors": only the windows the 3-anchor fits used are drawn.'
      : `The windows control reads "All windows": every window with N ≥ ${formatInt(gates.report_n)} that has a ${w.symbol} is drawn; the fits use the fittable ones, a₀/√E from ${curveMin} GeV and ${NOISE_FORM} from ${noiseMinText} GeV, and a window below ${noiseMinText} GeV is drawn as a point no fit uses.`}`,
    `${plural(model.nPoints, 'window')} and ${plural(model.nLines, 'fit curve')} are drawn in this view.`,
    `One fitted curve per series is drawn on each panel (Martin's decision, 2026-11-15): its ${NOISE_FORM}, from 0 GeV, or, where the series has none, `
      + `its origin-pinned a₀/√E ⊕ 0, from ${curveMin} GeV, the thinner line. `
      + `The quadrature a/√E ⊕ b, the affine a/√E + b and, beside a drawn ${NOISE_FORM}, the origin-pinned a₀/√E are in the fit table only; the affine fit is drawn in the 1/√E view.`,
    'No band is drawn round a fitted curve on this view: each curve\'s tooltip and the fit table give its terms with their standard errors, χ²/ν and S, and every window keeps its whisker.',
    ...fallbacks.map(({ s, f }) => `${s.label}: ${sentence(noiseReasonOf(s, mode) ?? `no ${NOISE_FORM} fit in this response`)} `
      + `Its origin-pinned a₀/√E ⊕ 0 is drawn instead, from ${curveMin} GeV${f.provisional ? ', provisional' : ''}, as the thinner line.`),
    ...noCurve.map((s) => `${s.label}: no fitted curve is drawn. ${sentence(noiseReasonOf(s, mode) ?? `No ${NOISE_FORM} fit in this response`)} `
      + `Its origin-pinned a₀/√E ⊕ 0 has no curve either: ${s.fits?.pinned?.reason ?? 'no fit in this response'}.`),
    noiseKnown
      ? `${NOISE_FORM} is fitted as (${w.symbol})² = A/E + B + C/E² by weighted least squares with A = a², B = b² and C = c² held non-negative, so every term is real; `
        + 'a term the constraint holds at 0 is named under Disclosures, and the fit\'s ν counts its free terms only.'
      : '',
    ...lowAnchorLines(mode, noiseDrawn, gates, noiseMinText),
    w.weightSentence,
    pooledScaleLine(w, model, payload),
    spanList.length
      ? `Each curve is solid over the span of the windows it was fitted to, the lowest window edge to the highest (${spanRule}), and dashed beyond it.`
      : '',
    `The energy axis is linear from 0 to ${formatNumber(x.max)} GeV in steps of ${formatNumber(x.interval)} GeV${endTicked ? `; the end, ${formatNumber(x.max)} GeV, is ticked too` : ''}${Number.isFinite(model.dataMaxGev) ? `; the highest window edge is ${formatNumber(model.dataMaxGev)} GeV` : ''}. `
      + `${capital(w.symbol)} starts at zero and ends at ${pct(y.hi)}${y.provisional ? ' (provisional)' : ''}.`,
    // The server's own restatement of the one-curve rule is left out: the sentences above say it, and say it once.
    // While the deposit is hidden, the range's basis is the server's second one, `y.basis`, verbatim.
    ...model.notes.map((note, i) => (i === 0 ? (y.basis ?? rangeBasis(note)) : note)).filter((note) => note && !/^Each series draws one fitted curve with no band round it/u.test(note)).map(sentence),
    // With no reference on show the ratio panel draws nothing: one sentence says so, and no line describes a reference or an axis.
    ...(ratio.none
      ? ['The ratio panel shares the energy axis but draws no mark, no 1.0 rule and no scale: no reference is on show (the deposit is hidden and no literature curve is on).']
      : [
        `The ratio panel shares the energy axis. A window is drawn as its ${w.symbol} divided by the reference at its E and its whisker, where it has one, as the two ends of its interval divided the same way; each series' drawn curve is divided by the reference too; the curve that is the reference is not drawn, being 1 by construction.`,
        ...refLines,
        `The ratio axis is logarithmic and symmetric about 1, from ${kText}, so a factor k above 1 and a factor k below lie at equal distances from the 1.0 rule; `
          + `k is the first of ${RATIO_STEPS.map(String).join(', ')} that covers the robust ratio marks, the windows alone: those of N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV (whiskers included), `
          + 'each against a reference that is neither provisional nor of a form that does not describe its windows. No fitted curve sets it: a curve\'s ratio that leaves the axis is clipped there with a caret. '
          + `The ladder ends at ${RATIO_STEPS[RATIO_STEPS.length - 1]}, and a robust mark beyond it is clipped with a caret.`,
      ]),
    'The fit table under the plot lists each series\' four fits with their status on this view: its Fit cell names the one curve drawn, and the other three are table only; the affine fit is drawn in the 1/√E view.',
  ]);

  // ---- Disclosures
  const dis = [];
  if (y.provisional) {
    // What sets a provisional range: the response's weaker windows, counted over every series (the range is the response's).
    // The windows of the series on show: every payload series as before, the model series alone while the deposit is hidden.
    const rangeSeries = hidden ? (payload.series ?? []).filter((s) => !isDepositSeries(s)) : (payload.series ?? []);
    const reported = rangeSeries.flatMap((s) => s.windows ?? [])
      .filter((w) => Number.isFinite(w.value) && (w.n ?? 0) >= gates.report_n);
    const weakFrom = reported.filter((w) => (w.p_lo ?? 0) >= model.yMinGev && w.n < gates.fit_n).length;
    // Windows of N ≥ 20 from the floor that still set nothing carry no fit weight: never blamed on N (brief-fix F3).
    const unweighted = reported.filter((x) => (x.p_lo ?? 0) >= model.yMinGev && x.n >= gates.fit_n
      && ['tied', 'withheld', 'none'].includes(weightState({ name: w.name }, x))).length;
    const belowFloor = reported.filter((w) => (w.p_lo ?? 0) < model.yMinGev).length;
    const by = [
      weakFrom && `the ${plural(weakFrom, 'window')} of N < ${formatInt(gates.fit_n)} from ${yMin} GeV`,
      unweighted && `the markers of the ${plural(unweighted, 'window')} of N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV without a fit weight`,
      belowFloor && `the markers of the ${plural(belowFloor, 'window')} below ${yMin} GeV`,
    ].filter(Boolean);
    const cause = unweighted
      ? `no window from ${yMin} GeV of N ≥ ${formatInt(gates.fit_n)} carries a fit weight (What is drawn names the causes)`
      : `no window from ${yMin} GeV reaches N = ${formatInt(gates.fit_n)}`;
    dis.push(`The y range is provisional: ${cause}${by.length
      ? `, so it is set by weaker windows of the response, ${by.join(' and ')}`
      : `, and no window of the response reports ${w.symbol}, so nothing on the plot sets it`}.`);
  } else {
    dis.push(`The y range follows the windows alone, from zero: those with N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV, whiskers included. A fit summarises its windows and is not more evidence, `
      + `so no fitted curve or extrapolation sets it; a window below ${yMin} GeV never sets it, whatever its N.`);
  }
  const parts = [
    clipped.markers && plural(clipped.markers, 'marker'),
    clipped.whiskers && plural(clipped.whiskers, 'whisker'),
    clipped.fits && plural(clipped.fits, 'fitted curve'),
    clipped.literature && plural(clipped.literature, 'literature curve'),
  ].filter(Boolean);
  if (parts.length) {
    dis.push(`Clipped at the top of the main panel (${pct(y.hi)}) ${inForce(model, shower)}, each with a caret and its true value in its tooltip: ${parts.join(', ')}.`);
  }
  const offEntries = model.offScale.reduce((a, g) => a + g.entries.length, 0);
  if (offEntries) {
    dis.push(`${plural(offEntries, 'window')} ${offEntries === 1 ? 'lies' : 'lie'} above the top of the axis (${pct(y.hi)}), drawn clipped with a caret and listed by window: `
      + `${model.offScale.map((g) => `${g.label} — ${g.entries.map((e) => `${e.short} ${pct(e.value)} (N = ${formatInt(e.n)})`).join(', ')}`).join('; ')}.`);
  }
  const cutFits = curves.filter(({ f }) => f.cut);
  if (cutFits.length) {
    dis.push(`${plural(cutFits.length, 'fitted curve')} ${cutFits.length === 1 ? 'leaves' : 'leave'} the top of the main panel, each clipped there with a caret whose tooltip gives its true value: `
      + `${cutFits.map(({ s, f, form }) => `${s.label}, ${ENERGY_FORM_NAMES[form]}${f.provisional ? ' (provisional)' : ''} `
        + `curve, highest ${pct(f.cut.peak[1])} at E = ${sig(f.cut.peak[0])} GeV`).join('; ')}. `
      + 'The range follows the windows alone, so no curve or extrapolation sets it.');
  }
  // The three-term curves' entry at the top: each rises without bound as E → 0 unless A = C = 0 (brief res-noise
  // §4.1), read from the panel's model (`s.fits.noise.entry`, review nit 3), never solved again here.
  const entries = noiseDrawn.map(({ s, fit }) => ({ s, fit, e: s.drawn.entry })).filter((it) => it.e);
  const entering = entries.filter((it) => !it.e.above && it.e.lineAt !== null && it.e.lineAt !== undefined);
  const above = entries.filter((it) => it.e.above);
  if (entering.length) {
    const n = entering.length;
    dis.push(`${plural(n, `${NOISE_FORM} curve`)} ${n === 1 ? 'comes' : 'come'} down into the main panel from its top (${pct(y.hi)}), ${n === 1 ? 'with a caret where it enters, since it rises' : 'each with a caret where it enters, since they rise'} without bound as E → 0: `
      + `${entering.map(({ s, e }) => `${s.label} at E = ${sig(e.lineAt)} GeV, through its ${e.term === 'c' ? 'noise term c/E' : 'stochastic term a/√E'}`
        + `${e.atAxis ? ' (less than 0.1% of the axis from E = 0: the curve runs up along the axis line there)' : ''}`).join('; ')}.`);
  }
  for (const { s, fit } of above) {
    const bAlone = fit.params?.b2 >= y.hi * y.hi;
    dis.push(`${s.label}: its ${NOISE_FORM} curve lies above the top of the main panel (${pct(y.hi)}) at every E on the axis${bAlone ? `, its constant term b = ${pct(fit.params?.b)} alone reaching it` : ''}; it is clipped there with a caret.`);
  }
  // A fallback a₀/√E above the top at its first energy comes down into the plot, since it falls with E (the panel's
  // entry, review-ui F5), or lies above the whole axis; the drawer names it as it names the three-term curves.
  for (const { s, f } of curves.filter(({ form, f }) => form === 'pinned' && f.entry)) {
    dis.push(f.entry.above
      ? `${s.label}: its origin-pinned a₀/√E lies above the top of the main panel (${pct(y.hi)}) at every energy from ${curveMin} GeV; it is clipped there with a caret.`
      : `${s.label}: its origin-pinned a₀/√E comes down into the main panel from its top (${pct(y.hi)}) at E = ${sig(f.entry.lineAt)} GeV, with a caret there: it falls as 1/√E, so from ${curveMin} GeV up to that energy it lies above the top.`);
  }
  const misfits = misfitLine(curves.map(({ s, f, form }) => ({ s, f: { form, fit: f.fit, misfit: f.misfit } })), gates, (form) => ENERGY_FORM_NAMES[form]);
  if (misfits) dis.push(misfits);
  if (!spanList.length) {
    dis.push('No fitted curve is drawn for this selection, so the main panel shows windows only and the ratio panel marks only.');
  } else if (!spanShared) {
    // One clause per span, the fits that share it named by shower, estimator and form.
    const bySpan = new Map();
    for (const b of spanList) {
      const key = spanGeV(b.span);
      bySpan.set(key, [...(bySpan.get(key) ?? []), `${b.short} ${energyFormShort(b.form)}`]);
    }
    dis.push(`The curves were not all fitted over the same windows, so their solid parts differ: ${[...bySpan].map(([span, names]) => `${span} for ${names.join(', ')}`).join('; ')}; each is dashed beyond its own span.`);
  }
  for (const s of model.series) {
    const mf = s.mf;
    if (!mf) continue;
    if (mf.provisional) dis.push(`${s.label}: the fits are provisional, through windows of N ≥ ${formatInt(gates.whisker_n)}, because fewer than two windows from ${curveMin} GeV reach N = ${formatInt(gates.fit_n)}; drawn faded.`);
    if (mode === 'anchors') for (const sub of mf.substitutions ?? []) dis.push(`${s.label}: ${sentence(sub.reason)}`);
    for (const [form, fit] of [['affine', mf.affine], ['pinned', mf.pinned], ['quadrature', mf.quadrature], ['noise', mf.noise]]) {
      if (!fit) continue;
      const name = { affine: 'affine fit (tabled in this view)', quadrature: 'quadrature fit a/√E ⊕ b (tabled in this view)' }[form]
        ?? (form === s.drawnForm ? ENERGY_FORM_NAMES[form] : `${ENERGY_FORM_NAMES[form]} (tabled in this view)`);
      if (!(fit.ndf > 0)) dis.push(`${s.label}, ${name}: ν = 0, the fit passes through its points exactly and has no χ² test.`);
      if (fit.scale_factor > 1) {
        dis.push(`${s.label}, ${name}: χ²/ν = ${sig(fit.chi2 / fit.ndf)} (p = ${sig(fit.p_value)}), so its standard errors are scaled by S = ${sig(fit.scale_factor)} (PDG).`);
      }
      if (fit.converged === false) {
        dis.push(`${s.label}, ${name}: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so it is the last refit's ${form === 'quadrature' || form === 'noise' ? 'fit' : 'line'}, not a fixed point.`);
      }
    }
  }
  // The three-term fit (brief res-noise §5, §11): its floor, the terms it holds, the series without one, and what its terms mean.
  if (noiseKnown) {
    dis.push(`The ${NOISE_FORM} fit uses windows from ${noiseMinText} GeV: below that a 1 GeV window reaches momenta near zero, so its average of 1/E² is far from what its plotted energy implies, `
      + 'and no single abscissa can carry the noise term c/E.');
  }
  for (const { s, fit } of noiseDrawn) {
    const held = heldTerms(fit);
    if (held.length) dis.push(heldLine(s.label, held));
  }
  if (noiseDrawn.length) {
    dis.push('c/E is the calorimeter\'s conventional noise term. Here it takes up whatever grows like 1/E at low momentum (for a network, its pull toward mid-range; '
      + 'under Median |rel. err.|, the response\'s bias as well), so c is a fitted coefficient, not a measured noise level.');
    const rhos = noiseDrawn.flatMap(({ fit }) => Object.values(fit.params?.rho ?? {})).filter(Number.isFinite);
    if (rhos.length) {
      const top = Math.max(...rhos.map(Math.abs));
      const how = top >= STRONG_RHO ? 'strongly correlated (each curve\'s tooltip gives ρ)' : `correlated (here |ρ| ≤ ${sig(top)}; each curve's tooltip gives ρ)`;
      dis.push(`Over the fitted windows 1/√E, 1 and 1/E change together, so the fitted squares are ${how}: the curve is better determined than its split into a, b and c, `
        + 'and each free term\'s standard error already carries that correlation, conditional only on the held terms.');
    }
    // The held-term caveat stands whenever a drawn fit holds a term, with or without a correlation to give (review m3).
    if (noiseDrawn.some(({ fit }) => heldTerms(fit).length)) {
      dis.push('A term held at 0 means the windows need no separate term of that form once the others are free, not that the detector has none.');
    }
  }
  const weak = points.filter((p) => p.weak && !p.subFloor);
  // A window the three-term fit alone uses is fitted too (review m1).
  const weakFitted = weak.filter((p) => p.fitted || p.noiseFitted).length;
  const weakAlone = weak.length - weakFitted;
  if (weakFitted) dis.push(`${plural(weakFitted, 'window')} of N < ${formatInt(gates.fit_n)} drawn faded with ${weakFitted === 1 ? 'its' : 'their'} ${w.whisker} and fitted, in a provisional fit.`);
  if (weakAlone) dis.push(`${plural(weakAlone, 'window')} of N < ${formatInt(gates.fit_n)} drawn faded with ${weakAlone === 1 ? 'its' : 'their'} ${w.whisker}, not fitted.`);
  const sub = points.filter((p) => p.subFloor && weightState({ name: w.name }, p.w) !== 'withheld').length;
  if (sub) dis.push(`${plural(sub, 'window')} of N < ${formatInt(gates.whisker_n)} drawn as a faded dashed ring with no whisker: ${w.symbol} is reported from N = ${formatInt(gates.report_n)}, an interval is drawn from N = ${formatInt(gates.whisker_n)}.`);
  // The drawn windows below a₀/√E's floor: the three-term fit may use those from 1 GeV (its own points), no fit the rest.
  const below = model.series.flatMap((s) => {
    const used = new Set(noiseFitOf(s, mode)?.points ?? []);
    return s.points.filter((p) => (p.w.p_lo ?? p.E) < model.curveMinGev).map((p) => ({ s, p, noise: used.has(p.w.bin) }));
  });
  if (below.length) {
    const inNoise = below.filter((b) => b.noise);
    const none = below.length - inNoise.length;
    dis.push(`${plural(below.length, 'drawn window')} ${below.length === 1 ? 'lies' : 'lie'} below ${curveMin} GeV, where a₀/√E uses none: `
      + [
        inNoise.length && `${plural(inNoise.length, 'window')} ${is(inNoise.length)} fitted by ${NOISE_FORM} only (${inNoise.map(({ s, p }) => `${s.short} ${p.w.label}`).join(', ')})`,
        none && `${plural(none, 'window')} ${is(none)} drawn as ${none === 1 ? 'a point' : 'points'} no fit uses`,
      ].filter(Boolean).join('; ') + '.');
  }
  const lowRange = points.filter((p) => (p.w.p_lo ?? Infinity) < model.yMinGev);
  if (lowRange.length) {
    const they = lowRange.length === 1 ? 'it' : 'they';
    dis.push(`${plural(lowRange.length, 'drawn window')} start${lowRange.length === 1 ? 's' : ''} below ${yMin} GeV: ${y.provisional
      ? `${they} set the y range only provisionally, by ${lowRange.length === 1 ? 'its marker' : 'their markers'}, while no window from ${yMin} GeV reaches N = ${formatInt(gates.fit_n)}, and never the ratio range`
      : `${they} never set the y range or the ratio range`}.`);
  }
  const belowAnchors = model.series.filter((s) => s.points.some((p) => p.fitted && (p.w.p_lo ?? 0) < gates.anchor_low_gev));
  if (mode === 'all' && belowAnchors.length) {
    const names = [...new Set(belowAnchors.flatMap((s) => s.points
      .filter((p) => p.fitted && (p.w.p_lo ?? 0) < gates.anchor_low_gev).map((p) => p.w.label)))];
    dis.push(`a₀/√E fits every window from ${curveMin} GeV, ${names.join(', ')} included (${plural(belowAnchors.length, 'series', 'series')}): below ${formatNumber(gates.anchor_low_gev)} GeV, `
      + `the anchors' floor, the sampling fraction is still rising and a₀/√E may not describe ${w.symbol}${w.symbol.endsWith('.') ? '' : '.'}`);
  }
  for (const s of model.series) dis.push(...unreportedLines(w, s, gates));
  dis.push(...noWeightLines(w, model, points), ...declinedLines(w, model));

  // The ratio panel: with no reference on show it draws nothing, so no range, no reference block and no clipped count is stated.
  if (!ratio.none) dis.push(ratio.provisional
    ? `The ratio range, ${kText}, is provisional: no window of N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV gives a ratio mark against a reference that is neither provisional nor of a form that does not describe its windows, so k is set by the markers alone, or is 2 without any; no fit sets it.`
    : `The ratio range, ${kText}, follows the windows alone: those of N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV (whiskers included), each against a reference that is neither provisional nor of a form that does not describe its windows; no fit sets it.`);
  if (ratio.capped) {
    const cap = RATIO_STEPS[RATIO_STEPS.length - 1];
    dis.push(`The ratio axis is capped at ×${cap}, the last step of its ladder: ${plural(ratio.capped, 'robust ratio mark')} ${ratio.capped === 1 ? 'reaches' : 'reach'} beyond it (whiskers included), `
      + 'clipped there with carets whose tooltips give the true values.');
  }
  const ratioParts = [
    ratio.clipped.markers && plural(ratio.clipped.markers, 'marker'),
    ratio.clipped.whiskers && plural(ratio.clipped.whiskers, 'whisker'),
    ratio.clipped.fits && plural(ratio.clipped.fits, 'fitted curve'),
    ratio.clipped.literature && plural(ratio.clipped.literature, 'literature ratio line'),
  ].filter(Boolean);
  if (ratioParts.length) {
    dis.push(`Clipped at the ratio axis (${kText}) ${inForce(model, shower)}, each with a caret and its true value in its tooltip: ${ratioParts.join(', ')}.`);
  }
  if (points.some((p) => p.ratio.drawn && Number.isFinite(p.ratio.lo))) {
    dis.push(`A ratio whisker is the window's 95% ${w.sample ? 'χ² interval' : 'interval'} divided by ${lit ? 'the literature curve' : 'the reference fit'} at its E: it is conditional on the reference, ${ref.label}, `
      + `and does not include the reference's own uncertainty.${lit ? ' The literature curve has no interval reported, so none is carried.' : ''}`);
  }
  // The drawn windows below the floor of their shower's deposit reference: 1 GeV under the deposit's three-term
  // fit, a₀/√E's 4 GeV where the deposit has none (brief res-noise §4.2), counted from the payload.
  if (!lit && !ratio.none) {
    const belowRef = (form) => {
      const refs = depositRefs.filter((r) => r.form === form);
      const n = model.series.reduce((acc, s) => {
        const r = refs.find((x) => x.shower === (s.raw.shower ?? 'a'));
        return acc + (r ? s.points.filter((p) => (p.w.p_lo ?? p.E) < r.floor).length : 0);
      }, 0);
      return { refs, n };
    };
    const owners = (refs) => (model.nShowers > 1 && refs.length < depositRefs.length ? ` (${andList(refs.map((r) => `shower ${String(r.shower).toUpperCase()}`))})` : '');
    const noiseBelow = belowRef('noise');
    if (noiseBelow.n) {
      dis.push(`${plural(noiseBelow.n, 'window')} below ${noiseMinText} GeV${owners(noiseBelow.refs)} ${is(noiseBelow.n)} not drawn on the ratio panel: `
        + `no window below ${noiseMinText} GeV enters the deposit's ${NOISE_FORM} fit.`);
    }
    const pinnedBelow = belowRef('pinned');
    if (pinnedBelow.n) {
      dis.push(`${plural(pinnedBelow.n, 'window')} below ${curveMin} GeV${owners(pinnedBelow.refs)} ${is(pinnedBelow.n)} not drawn on the ratio panel: `
        + `the deposit has no ${NOISE_FORM} fit, and its a₀/√E fit is drawn from ${curveMin} GeV, so the reference has no value there.`);
    }
  }
  for (const r of ratio.noReference) {
    dis.push(`${model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}` : 'The deposit'} has no ratio marks: ${sentence(r.reason)}`);
  }
  if (!lit && !ratio.none) {
    for (const r of depositRefs.filter((x) => !x.reason)) {
      const owner = model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}'s` : 'The deposit';
      if (r.provisional) dis.push(`${owner} reference fit is provisional: its ratio marks are conditional on a fit through windows of N < ${formatInt(gates.fit_n)}, so none of them sets the ratio range.`);
      if (r.misfit) {
        const which = `${model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}'s reference, its deposit's` : 'The reference, the deposit\'s'} `
          + `${r.form === 'noise' ? NOISE_FORM : 'a₀/√E'} fit,`;
        dis.push(`${which} does not describe its windows (S = ${sig(r.fit.scale_factor)} > ${formatNumber(gates.misfit_scale)}, χ²/ν = ${sig(r.fit.chi2 / r.fit.ndf)}): `
          + 'its ratio marks are conditional on a form its own windows reject, so none of them sets the ratio range.');
      }
    }
  }

  // The literature curves drawn.
  if (model.literature.length) {
    dis.push(`The literature curves are the two legend curves of one figure, ${REFERENCE_SOURCE.figure}, supplied by ${REFERENCE_SOURCE.by} on ${REFERENCE_SOURCE.supplied} `
      + `(record ${REFERENCE_SOURCE.record}): ${RESOLUTION_REFERENCES.map((e) => referenceEquation(e)).join(' and ')}, transcribed as the legend prints them, ${REFERENCE_UNITS}.`);
    dis.push('Each is a documented point estimate with no interval reported and none derived: no band is drawn for it, and a ratio taken against it carries none of its uncertainty.');
    dis.push(`They are ${REFERENCE_SOURCE.scope}: a reference to compare with, never a statement about this detector.`);
    dis.push('The figure does not state the energy range either curve was fitted over; each is drawn over the whole axis, and no part of it can be marked as extrapolated.');
    const crossing = model.literature.filter((l) => l.cut).map((l) => l.entry.particle);
    const ratioOut = model.literature.filter((l) => l.ratio?.cut).map((l) => l.entry.particle);
    dis.push(`No literature curve sets a range on either panel${crossing.length
      ? `; the ${crossing.join(' and ')} curve${crossing.length > 1 ? 's cross' : ' crosses'} the top of the main panel, clipped there with a caret` : ''}${ratioOut.length
      ? `; the ${ratioOut.join(' and ')} curve's ratio leaves the ratio axis, clipped there with a caret` : ''}.`);
  }
  dis.push('The quadrature b and the affine b are different constant terms: one adds in quadrature, the other linearly, so they are not compared as one number.');
  if (noiseDrawn.length) dis.push(`The b of ${NOISE_FORM} is a third: it is fitted beside the noise term c/E, so it is not compared with either.`);
  dis.push(relationLine(w), RES_DECOMPOSITION);
  // The deposit's calibration is the deposit's: left out while it is hidden.
  if (!hidden) dis.push(...calibrationLines(w));
  dis.push(robustFloorLine(w, model));
  dis.push(...responseRangeLines(w, model));
  // Martin's override: the literature curves stay on under the median, and the server's own warning says what that comparison is.
  if (w.name === 'median' && model.literature.length && w.est.literature?.warning) dis.push(w.est.literature.warning);
  if (m.source === 'xgb' && !hidden) dis.push('The detector series uses every selected event; the XGBoost series only its validation split, so the two series do not share their events.');
  dis.push('E is the incident momentum p as the producer writes it; for a massive species √(p² + m²) differs from p by at most m²/2p², 1.7% for a proton at 5 GeV/c.');
  if (model.series.some((s) => s.isB)) {
    const raised = model.series.filter((s) => s.isB && s.lineOpacity(false) > 0.7 + 1e-6)
      .map((s) => `${s.short} at ${Math.round(100 * s.lineOpacity(false))}%`);
    dis.push(`Shower B's lines are drawn at 70% strength, raised where the card needs it to keep 3:1 (${raised.length ? `${raised.join(', ')} on this card` : 'no hue needs it on this card'})`
      + `${model.twoOnShow ? ', so the end labels "A" and "B" name the shower' : ''}; on this view the dash means extrapolation, so shower B gives up the long dash the 1/√E view gives it.`);
  }
  dis.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, dis.filter(Boolean));

  // ---- Marks and legend
  const extrapolation = model.noteText.extrapolation;
  notes.section(SECTION.legend, [
    `${colourLead(hidden)} On two-shower data fill and line strength are the shower: shower A is a filled marker with full-strength lines, shower B a hollow marker with its lines at 70% strength, raised to 3:1 where the card needs it. With both showers drawn, a letter "A" or "B" in ink at each curve\'s right end, in a column beside the plot, led by a short key stroke in the curve\'s own colour, dash, width and strength, names the shower; a curve that leaves the plot before the axis end has its caret instead. A larger marker is a window of the 3-anchor fit.`,
    `The dash is extrapolation and the width is the form: a solid line is a fit over the windows it was fitted to and a dashed line the same fit beyond them; the thicker line is ${NOISE_FORM}, the thinner the origin-pinned a₀/√E ⊕ 0 a series draws where it has no ${NOISE_FORM} fit. `
      + `A fit drawn fainter, its curve and dashed extrapolation alike, is ${w.name === 'robust' ? '' : 'provisional or '}of a form that does not describe its windows (S > ${formatNumber(gates.misfit_scale)}); no fit, faded or not, sets either panel's range.`,
    w.whiskerLegend,
    literatureLegendLine(model, hidden),
    ratio.none
      ? 'The ratio panel draws no 1.0 rule and no scale: with no reference on show it holds only its frame, the shared energy axis and one sentence saying so.'
      : `The ratio panel: the 1.0 rule in ink marks ${w.symbol} equal to the reference; ${lit
        ? 'no band about 1 is drawn, since the literature curve has no interval reported'
        : 'the reference is held exact'}; the axis is logarithmic and symmetric about 1, with ticks at 1 and at the round steps up to k with their reciprocals, which read 1/x below 1, so ÷3 reads 1/3 beside 3.`,
    `A linked crosshair crosses both panels at one E and reads it on the bottom axis, an exact coordinate readout and no data mark; the item tooltips carry the values. A caret at an axis edge marks a mark clipped there, its true value in its tooltip. The note above the plot lists the windows above the top${extrapolation ? ` and states the extrapolation rule ("${extrapolation}")` : ''}. A legend entry shows or hides every mark of its series.`,
  ]);
  return notes.done(modelsHazards(payload, 'res-scaling', { windows, shower, view: 'energy', reference, literature, deposit, eMax }));
}

/**
 * The notes of the resolution card: σ/E against 1/√E with its fits. `windows`
 * ('anchors' | 'all') and `shower` are the card's render options; the drawer
 * describes the mode in force and the series the shower choice draws, through
 * the panel's own pure model, so it never states what the plot does not show.
 * `view` 'energy' hands over to the E view's drawer (`reference` is its ratio
 * panel's `literature`, the curves drawn, which decide its ratio's reference;
 * the older single `reference` where it is absent); any other view is this
 * one, unchanged.
 */
export function resolutionScalingNotes({
  payload, state = null, experiment = null, title = null, windows = 'anchors', shower = 'both',
  view = 'linear', reference = 'deposit', literature = undefined, deposit = undefined, eMax = undefined,
} = {}) {
  if (!payload) return null;
  if (view === 'energy') return resolutionEnergyNotes({ payload, state, experiment, title, windows, shower, reference, literature, deposit, eMax });
  const notes = new Notes(title ?? resDefaultTitle(payload, false));
  const model = resolutionModel(payload, { windows, shower, deposit });
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no energy-resolution series.', ...metaDisclosures(payload)]);
    return notes.done([]);
  }
  const { gates, mode } = model;
  const hidden = model.deposit.hidden;
  const w = resWords(payload, gates);
  const pct = (v) => (Number.isFinite(v) ? `${sigFigs(v, 3)}%` : '—');
  const sig = (v) => sigFigs(v, 3);
  const m = payload.model ?? {};

  // ---- Selection
  notes.section(SECTION.selection, [...resSelectionLines(payload, state, experiment, model, shower), estimatorLine(w), depositSelectionLine(model.deposit)]);

  // ---- What is drawn
  const labels = (payload.series ?? []).map((s) => s.label).filter(Boolean);
  const est = payload.estimator ?? {};
  const nominal = payload.anchors?.labels ?? [];
  // A series with fewer than two windows of N ≥ 20 is fitted provisionally, through its weaker windows.
  const provisional = model.series.some((s) => s.provisional);
  const weakRule = mode === 'anchors' || w.name === 'robust' ? ''
    : provisional
      ? `; windows of N < ${formatInt(gates.fit_n)} are drawn faded, and fitted only by a series with fewer than two windows of N ≥ ${formatInt(gates.fit_n)}, whose fit is then provisional`
      : `; windows of N < ${formatInt(gates.fit_n)} are drawn faded and not fitted`;
  notes.section(SECTION.drawn, [
    est.definition ? sentence(est.definition) : '',
    `Each window is the producer's 1 GeV momentum bin; its abscissa is x = ⟨1/√p⟩ over its events, in GeV⁻¹ᐟ², on a reversed axis from 0.5 (4 GeV) at the left to 0 (E → ∞) at the right border, and ${w.symbol} starts at zero, so the bottom-right corner is the origin.`,
    `Mode drawn: ${modeLabel(mode, gates)}${weakRule}.`,
    'Two fits per series are drawn, each by weighted least squares with ' + w.weightClause + `: the affine ${w.symbol} = a/√E + b and the origin-pinned ${w.symbol} = a₀/√E. The quadrature form √(a²/E + b²) is fitted as (${w.symbol})² = A/E + B and tabled under the plot, not drawn.`,
    // The three-term fit's definition, which the server no longer serves as a note (res-noise fix round FX3): its form,
    // its constraint, its windows in each mode and its floor, with why this view only tables it.
    `${NOISE_FORM}, fitted as (${w.symbol})² = A/E + B + C/E² with A, B and C held non-negative, is tabled under the plot as well, not drawn: `
      + `it is fitted to windows from ${formatNumber(noiseMinGev(payload))} GeV, and those below ${formatNumber(gates.e_min_gev)} GeV lie off this view's axis, so it is drawn in the E (GeV) + ratio view.`,
    `It is fitted by weighted least squares through every fittable window from ${formatNumber(noiseMinGev(payload))} GeV, or in the 3-anchor mode through the anchors `
      + `and the lowest fittable window from ${formatNumber(noiseMinGev(payload))} GeV, since anchors from ${formatNumber(gates.anchor_low_gev)} GeV cannot fix a 1/E term; `
      + 'a term the constraint holds at 0 is written "0 (held)" in the table. '
      + `Below ${formatNumber(noiseMinGev(payload))} GeV a window's momenta reach nearly zero, so no single abscissa carries its average of 1/E².`,
    // A tabled fit of the 3-anchor mode with no low anchor: the payload's `low_anchor: null` is its only sign (FX3).
    ...lowAnchorLines(mode, model.series.map((s) => ({ s, fit: noiseFitOf(s, mode) }))
      .filter(({ fit }) => fit && (fit.low_anchor === null || fit.low_anchor === undefined)), gates, formatNumber(noiseMinGev(payload))),
    w.weightSentence,
    pooledScaleLine(w, model, payload),
    payload.anchors?.rule
      ? `Anchors${nominal.length ? ` (nominal: ${nominal.join(', ')})` : ''}: ${sentence(payload.anchors.rule)}`
      : '',
    `The top axis is a second x axis allowed only as an exact unit conversion: ${sentence(payload.axis?.top?.rule ?? 'E = 1/x², an exact relabelling of the bottom axis; no data are plotted against it.')}`,
    ...(hidden ? withoutDeposit(noteLines(payload.notes), payload) : noteLines(payload.notes)).filter((line) => !restatedNote(line, labels)),
  ].filter(Boolean));

  // ---- Disclosures
  const disclosures = [];
  // A provisional range takes the server's own basis, which names why no window sets it (N, or no fit weight: brief-fix F3).
  const provisionalBasis = noteLines(payload.notes).find((line) => line.startsWith('The y range is provisional:'));
  if (model.y.basis) {
    // The deposit is hidden: the range follows the model series alone, and the server's second basis says so, verbatim.
    disclosures.push(model.y.basis);
  } else if (model.y.provisional) {
    disclosures.push(provisionalBasis
      ? `${provisionalBasis.replace(/\s*No fit sets it:.*$/su, '')} No fit sets it.`
      : `The y range is provisional: no window reaches N = ${formatInt(gates.fit_n)}, so it is set by weaker windows; no fit sets it.`);
  }
  else {
    disclosures.push(`The y range follows the windows with N ≥ ${formatInt(gates.fit_n)} (whiskers included) alone, from zero: a fit summarises its windows and is not more evidence, `
      + 'so no fitted line or band sets it.');
  }
  const clipped = model.clipped.markers + model.clipped.whiskers;
  if (clipped) {
    disclosures.push(`Clipped at the axis in this view, each with a caret and its true values in its tooltip: ${plural(model.clipped.markers, 'marker')}, ${plural(model.clipped.whiskers, 'whisker')} (the server's count over every on-axis window of every ${hidden ? 'model series' : 'series'}, both modes: ${formatInt(model.y.n_clipped)}).`);
  }
  const cutFits = model.series.flatMap((s) => DRAWN_FORMS.map((f) => s.fits[f]).filter((f) => f?.cut).map((f) => [s, f]));
  if (cutFits.length) {
    disclosures.push(`${plural(cutFits.length, 'fit')} ${cutFits.length === 1 ? 'leaves' : 'leave'} the top of the plot, line or band, each clipped there with a caret whose tooltip gives its true values: `
      + `${cutFits.map(([s, f]) => `${s.label}, ${f.form === 'affine' ? 'affine' : 'origin-pinned'}${f.provisional ? ' (provisional)' : ''} `
        + `${f.cut.lineAt !== null ? 'line and band' : 'band'}, highest ${pct(f.cut.peak[3])} at x = ${formatNumber(f.cut.peak[0], 3)}`).join('; ')}. `
      + 'The range follows the windows alone, so no line or band sets it.');
  }
  const lineName = (form) => (form === 'affine' ? 'affine fit a/√E + b' : 'origin-pinned fit a₀/√E');
  const drawnFits = model.series.flatMap((s) => DRAWN_FORMS.map((form) => ({ s, f: s.fits[form] })).filter(({ f }) => f));
  const misfits = misfitLine(drawnFits, gates, lineName);
  if (misfits) disclosures.push(misfits);
  // The 1/√E view's bands drawn as their edges: a band that spans half its axis or more over its fitted windows.
  const outlined = drawnFits.filter(({ f }) => f.outlined);
  if (outlined.length) {
    const n = outlined.length;
    disclosures.push(`${plural(n, 'band')} ${n === 1 ? 'spans' : 'span'} half ${n === 1 ? 'its' : 'their'} axis or more at some x over the fitted windows, `
      + `so ${n === 1 ? 'it is' : 'they are'} drawn as two thin solid edges in the series' colour, never as a wash: `
      + `${outlined.map(({ s, f }) => `${s.label}, ${lineName(f.form)}${bandWhy(f.fit, sig)}`).join('; ')}. `
      + 'A small ν makes such a band wide: once S > 1 scales the covariance, q is Student\'s t of the fit\'s own ν, 12.7 at ν = 1.');
  }
  for (const s of model.series) {
    const off = (s.raw.windows ?? []).filter((w) => w.off_axis);
    if (off.length) {
      disclosures.push(`${s.label}: off the axis (below ${formatNumber(gates.e_min_gev)} GeV, x > 0.5), not drawn: `
        + `${off.map((w) => `${w.label} ${Number.isFinite(w.value) ? pct(w.value) : 'not estimable'} (N = ${formatInt(w.n)})`).join(', ')}.`);
    }
  }
  for (const s of model.series) disclosures.push(...unreportedLines(w, s, gates));
  const points = model.series.flatMap((s) => s.points);
  disclosures.push(...noWeightLines(w, model, points));
  const weak = points.filter((p) => p.weak && !p.subFloor);
  const weakFitted = weak.filter((p) => p.fitted).length;
  const weakAlone = weak.length - weakFitted;
  if (weakFitted) disclosures.push(`${plural(weakFitted, 'window')} of N < ${formatInt(gates.fit_n)} drawn faded with ${weakFitted === 1 ? 'its' : 'their'} ${w.whisker} and fitted, in a provisional fit.`);
  if (weakAlone) disclosures.push(`${plural(weakAlone, 'window')} of N < ${formatInt(gates.fit_n)} drawn faded with ${weakAlone === 1 ? 'its' : 'their'} ${w.whisker}, not fitted.`);
  // The all-windows mode starts at 4 GeV, below the anchors' 5 GeV floor: the windows it fits there are named.
  const belowAnchors = model.series.filter((s) => s.points.some((p) => p.fitted && (p.w.p_lo ?? 0) < gates.anchor_low_gev));
  if (mode === 'all' && belowAnchors.length) {
    const windows = [...new Set(belowAnchors.flatMap((s) => s.points
      .filter((p) => p.fitted && (p.w.p_lo ?? 0) < gates.anchor_low_gev).map((p) => p.w.label)))];
    disclosures.push(`This mode fits every window from ${formatNumber(gates.e_min_gev)} GeV, ${windows.join(', ')} included `
      + `(${plural(belowAnchors.length, 'series', 'series')}): below ${formatNumber(gates.anchor_low_gev)} GeV, the anchors' floor, the sampling `
      + `fraction is still rising and a/√E + b may not describe ${w.symbol}${w.symbol.endsWith('.') ? '' : '.'}`);
  }
  const sub = points.filter((p) => p.subFloor && weightState({ name: w.name }, p.w) !== 'withheld').length;
  if (sub) disclosures.push(`${plural(sub, 'window')} of N < ${formatInt(gates.whisker_n)} drawn as a faded dashed ring with no whisker: ${w.symbol} is reported from N = ${formatInt(gates.report_n)}, an interval is drawn from N = ${formatInt(gates.whisker_n)}.`);
  for (const s of model.series) {
    const mf = s.mf;
    if (!mf) continue;
    if (mf.provisional) disclosures.push(`${s.label}: the fits are provisional, through windows of N ≥ ${formatInt(gates.whisker_n)}, because fewer than two windows reach N = ${formatInt(gates.fit_n)}; drawn faded.`);
    if (mode === 'anchors') for (const x of mf.substitutions ?? []) disclosures.push(`${s.label}: ${sentence(x.reason)}`);
    const affine = mf.affine;
    const pinned = mf.pinned;
    const declined = declinedWindow({ name: w.name }, s.raw, mf, mode, gates);
    if (declined) disclosures.push(`${s.label}: ${declinedText(declined)}, so no line is drawn${mode === 'anchors' ? '; the window is drawn in the all-windows mode' : '; the window is drawn unfitted'}.`);
    else if (!affine) disclosures.push(`${s.label}: fewer than two windows to fit, so no line is drawn.`);
    for (const fit of [affine, pinned, mf.quadrature, mf.noise]) {
      if (!fit) continue;
      const name = { affine: 'affine fit', pinned: 'origin-pinned fit', quadrature: 'quadrature fit (tabled)', noise: `${NOISE_FORM} fit (tabled)` }[fit.form];
      if (!(fit.ndf > 0)) disclosures.push(`${s.label}, ${name}: ν = 0, the fit passes through its points exactly and has no χ² test.`);
      if (fit.scale_factor > 1) {
        disclosures.push(fit.form === 'quadrature' || fit.form === 'noise'
          ? `${s.label}, ${name}: χ²/ν = ${sig(fit.chi2 / fit.ndf)} (p = ${sig(fit.p_value)}), so the standard errors in the table are scaled by S = ${sig(fit.scale_factor)} (PDG).`
          : `${s.label}, ${name}: χ²/ν = ${sig(fit.chi2 / fit.ndf)} (p = ${sig(fit.p_value)}), so its standard errors are scaled by S = ${sig(fit.scale_factor)} (PDG), `
            + `and its band takes Student's t₀.₉₇₅,${formatInt(fit.ndf)} = ${sigFigs(fit.band_quantile, 4)} rather than 1.96, since S is estimated from the fit's own ν = ${formatInt(fit.ndf)}; the unscaled errors are in its tooltip.`);
      }
      if (fit.converged === false) {
        disclosures.push(`${s.label}, ${name}: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so it is the last refit's ${fit.form === 'quadrature' || fit.form === 'noise' ? 'fit' : 'line'}, not a fixed point.`);
      }
    }
    if (affine?.negative_intercept) {
      disclosures.push(`${s.label}: the affine b is negative (${pct(affine.params?.b)}): the points fall faster than a/√E; the line runs down to the axis and stops there.`);
    }
    if (Number.isFinite(affine?.params?.a) && affine.params.a < 0) {
      disclosures.push(`${s.label}: the affine a is negative (${sig(affine.params.a)} %·√GeV): ${w.symbol} rises with E over these windows, which no stochastic term describes.`);
    }
    const q = mf.quadrature?.params;
    if (q) {
      if (q.a_defined === false) disclosures.push(`${s.label}: quadrature A = ${sig(q.a2)} ± ${sig(q.se_a2)} %²·GeV ≤ 0, so a = √A is undefined.`);
      if (q.b_defined === false) {
        const z = Math.abs(q.b2 / q.se_b2);
        disclosures.push(`${s.label}: quadrature B = ${sig(q.b2)} ± ${sig(q.se_b2)} %² ≤ 0, so b = √B is undefined; B lies ${sig(z)} SE below zero, `
          + (z < 1.96 ? 'consistent with zero at 95%.' : 'not consistent with zero at 95%, so the quadrature form does not describe these windows.'));
      }
    }
  }
  disclosures.push('The quadrature b and the affine b are different constant terms: one adds in quadrature, the other linearly, so they are not compared as one number.');
  disclosures.push(w.sample ? '' : sentence(w.est.relation ?? ''), RES_DECOMPOSITION, ...(hidden ? [] : calibrationLines(w)), robustFloorLine(w, model), ...responseRangeLines(w, model));
  if (m.source === 'xgb' && !hidden) disclosures.push('The detector series uses every selected event; the XGBoost series only its validation split, so the two series do not share their events.');
  disclosures.push('E on both axes is the incident momentum p as the producer writes it; for a massive species √(p² + m²) differs from p by at most m²/2p², 1.7% for a proton at 5 GeV/c.');
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures.filter(Boolean));

  // ---- Marks and legend
  notes.section(SECTION.legend, [
    `${colourLead(hidden)} Shower A is a filled marker and a solid affine line, shower B a hollow marker and a dashed affine line; the origin-pinned fit is a thinner dotted line for both. A larger marker is a window of the 3-anchor fit.`,
    w.whiskerLegend,
    'The shaded bands are the fits\' 95% confidence bands from the parameter covariance: ±1.96 √(gᵀΣg) while the windows\' own errors stand, and ±t₀.₉₇₅,ν √(gᵀΣg) once S = √(χ²/ν) > 1 scales the covariance, since S is then estimated from the fit\'s own ν (12.71 at ν = 1). They are the uncertainty of the line, not the spread of the events. The affine band is the stronger wash, the pinned band half of it. '
      + 'A band that spans half its axis or more over its fitted windows (their momentum edges, mapped by x = 1/√E) is drawn as two thin solid edges in the series\' colour, never as a wash; this view marks no extrapolation, so the edges are not dashed beyond those windows.',
    `A fit drawn faded, its line and its band alike, is ${w.name === 'robust' ? '' : `provisional (fewer than two windows of N ≥ ${formatInt(gates.fit_n)}) or `}of a form that does not describe its windows (S > ${formatNumber(gates.misfit_scale)}); `
      + 'no fit, faded or not, sets the range.',
    'The top axis reads the energy at the same x, E = 1/x², with ∞ at the right border; no data are plotted against it. A caret at the axis marks a marker, whisker, fitted line or band clipped there, its true values in its tooltip. A legend entry shows or hides every mark of its series.',
  ]);
  return notes.done(modelsHazards(payload, 'res-scaling', { windows, shower, deposit }));
}

/* ============================================================ hazards == */

/** Structural hazards of the models cards, by card id; never text matching. */
export function modelsHazards(payload, card, opts = {}) {
  const out = [];
  if (!payload) return out;
  if (payload.meta?.exact === false) out.push('sampled');
  if (card === 'perf-bins') {
    const model = perfModel(payload, opts);
    if (!model) return out;
    const points = model.series.flatMap((s) => s.points);
    if (model.y.provisional) out.push('provisional range');
    if (model.y.n_overflow || model.clipped.bars || model.clipped.whiskers) out.push('marks clipped at the axis');
    if (points.some((p) => !p.drives)) out.push('low-statistics bins');
    if (points.some((p) => p.n_missing > 0)) out.push('missing predictions');
    if (model.quantity === 'median_rel' && points.some((p) => p.n_small_theta > 0)) out.push('small-θ relative error');
    return out;
  }
  if (card === 'pred-truth') {
    const density = Object.values(payload.density ?? {});
    if (density.some((d) => d.encoding === 'pairs' && d.n > 0)) out.push('pairs below N = 15');
    if (density.some((d) => (d.outside?.total ?? 0) > 0)) out.push('pairs outside the axes');
    if (density.some((d) => (d.n_missing?.total ?? 0) > 0)) out.push('missing predictions');
    return out;
  }
  if (card === 'pred-residuals') {
    const r = payload.residual;
    if (!r) return out;
    const series = Object.values(r.series ?? {}).filter((s) => (s.fit?.n ?? 0) > 0);
    if (series.some((s) => s.draw !== 'histogram')) out.push('low-statistics series');
    if ((r.axis?.clipping?.n_outside ?? 0) > 0) out.push('clipped residual range');
    if (r.axis?.provisional) out.push('provisional range');
    if (series.some((s) => s.fit?.non_gaussian)) out.push('non-Gaussian tail');
    return out;
  }
  if (card === 'feat-table') {
    if ((payload.classes ?? []).some((c) => c.n > 0 && c.n < ROBUST_N)) out.push('small classes');
    if (Object.values(payload.table ?? {}).some((t) => (t.n_eps ?? []).some((v) => v > 0))) out.push('floored values');
    if ((payload.features ?? []).some((f) => f.circular)) out.push('circular feature');
    return out;
  }
  if (card === 'feat-corr') {
    if ((payload.circular_cells ?? []).length || Object.keys(payload.hatched ?? {}).length) out.push('circular variable');
    const m = featureCorrMatrix(payload);
    const cells = m.matrix.flatMap((row) => row.filter(Boolean));
    if (cells.some((c) => !c.hatched && Number.isFinite(c.r) && !c.ci95)) out.push('interval untestable');
    if (cells.some((c) => c.hatched && c.circular && !Number.isFinite(c.circular.value))) out.push('circular measure not quoted');
    return out;
  }
  if (card === 'feat-hist') {
    const series = payload.series ?? [];
    if (series.some((s) => s.draw !== 'histogram')) out.push('low-statistics classes');
    if ((payload.axis?.clipping?.n_outside ?? 0) > 0) out.push('clipped range');
    if (series.some((s) => s.n_floored > 0)) out.push('floored values');
    if (payload.y_max?.provisional) out.push('provisional range');
    if (payload.comb?.combed === true) out.push('measured comb');
    return out;
  }
  if (card === 'feat-hist2d') {
    const series = payload.series ?? [];
    if (series.some((s) => s.draw === 'pairs')) out.push('pairs below N = 15');
    if (series.some((s) => (s.outside?.total ?? 0) > 0)) out.push('values outside the axes');
    if (series.some((s) => s.n_floored > 0)) out.push('floored values');
    return out;
  }
  if (card === 'prim-rate') {
    if (rateBins(payload).some((b) => b.n < WIDE_BELOW_N)) out.push('small bins');
    return out;
  }
  if (card === 'res-scaling' && opts.view === 'energy') {
    const model = energyModel(payload, opts);
    if (!model) return out;
    const drawn = model.series.flatMap((s) => ENERGY_FORMS.map((form) => s.fits[form]).filter((f) => f?.drawable));
    if (drawn.some((f) => f.provisional)) out.push('provisional fit');
    if (model.series.some((s) => s.points.some((p) => p.weak))) out.push('weak windows drawn');
    if (model.y.provisional) out.push('provisional range');
    if (model.ratio.provisional) out.push('provisional ratio range');
    // A drawn curve above the top at every energy shows nothing but its caret: a clipped mark too (FX-jstests F-a).
    if (model.clipped.markers || model.clipped.whiskers || model.clipped.fits || model.clipped.literature || model.clipped.ratio
      || model.series.some((s) => s.drawn?.entry?.above)) {
      out.push('marks clipped at the axis');
    }
    const fitsOf = (s) => [s.mf?.affine, s.mf?.pinned, s.mf?.quadrature, s.mf?.noise].filter(Boolean);
    if (model.series.some((s) => fitsOf(s).some((fit) => fit.converged === false))) out.push('fit not converged');
    // A drawn literature curve is a documented point estimate, reference or not (CLAUDE.md §2's recorded exception).
    if (model.literature.length) out.push('no interval reported');
    // Martin's override of 2026-11-12: the curves stay on under the median, which is not a σ.
    if (model.literature.length && payload.estimator?.name === 'median') out.push('median rel. against σ/E curve');
    return out;
  }
  if (card === 'res-scaling') {
    const model = resolutionModel(payload, opts);
    if (!model) return out;
    const drawsFit = (s) => DRAWN_FORMS.some((f) => s.fits[f]);
    if (model.series.some((s) => s.provisional && drawsFit(s))) out.push('provisional fit');
    if (model.series.some((s) => s.points.some((p) => p.weak))) out.push('weak windows drawn');
    if (model.y.provisional) out.push('provisional range');
    if (model.clipped.markers || model.clipped.whiskers || model.clipped.fits) out.push('marks clipped at the axis');
    const fitsOf = (s) => [...DRAWN_FORMS.map((f) => s.mf?.[f]), s.mf?.quadrature, s.mf?.noise].filter(Boolean);
    if (model.series.some((s) => fitsOf(s).some((fit) => fit.converged === false))) out.push('fit not converged');
    return out;
  }
  return out;
}

/** The builders by card id, for the section controller. */
export const MODELS_NOTE_BUILDERS = Object.freeze({
  'perf-bins': 'perfBinsNotes',
  'pred-truth': 'predTruthNotes',
  'pred-residuals': 'residualNotes',
  'feat-table': 'featureTableNotes',
  'feat-corr': 'featureCorrNotes',
  'feat-hist': 'featureHistNotes',
  'feat-hist2d': 'featureHist2dNotes',
  'prim-rate': 'primariesNotes',
});

