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
} from './panels/resolution_scaling.js';
import { REFERENCE_SOURCE, RESOLUTION_REFERENCES, referenceEquation } from './catalog/resolution_refs.js';
import { LITERATURE_HUES } from './palette.js';
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
      + ` It is drawn from N = ${formatInt(gates.whisker_n)}; windows below N = ${formatInt(gates.fit_n)} are faded, never below 3:1 against the card.`,
    // The fit weights: the clause inside "each by weighted least squares" and, off sample, the server's own sentence.
    weightClause: sample
      ? 'weights 1/se², se the delta-method standard error of σ/μ recomputed at the fitted value and iterated'
      : `weights 1/se², se = κ·ŷ with κ the window's bootstrap relative standard error of the ${symbol}, recomputed at the fitted value and iterated`,
    weightSentence: sample ? '' : sentence(est.weight?.label ?? ''),
    // Why a window is not estimable.
    unreportedWhy: (w) => ((w.n ?? 0) < gates.report_n ? `N = ${formatInt(w.n ?? 0)}`
      : (name === 'robust' ? 'median R ≤ 0' : (name === 'median' ? 'no median' : 'R̄ ≤ 0'))),
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
      ? `${owner}: c̃ = ${sigFigs(c.c_median, 6)} beside c_sum = ${sigFigs(c.c_sum, 6)} (${plural(c.n ?? 0, 'event')} with E_dep > 0${c.n_zero_deposit ? `, ${formatInt(c.n_zero_deposit)} with a zero deposit left out` : ''}); the median calibration c̃ makes the deposit's median response over the selection exactly 1.`
      : `${owner}: no c̃, no selected event has E_dep > 0 (c_sum = ${sigFigs(c.c_sum, 6)}), so the deposit has no median value.`);
  }
  return lines.filter(Boolean);
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

/** Under robust: the windows of 2 ≤ N < 20 with no value, which Sample σ/μ draws. */
function robustFloorLine(w, model) {
  if (w.name !== 'robust') return '';
  const floor = model.gates.report_n;
  const below = model.series.flatMap((s) => (s.raw.windows ?? []).filter((x) => (x.n ?? 0) >= 2 && (x.n ?? 0) < floor && !Number.isFinite(x.value)));
  return `${plural(below.length, 'window')} of 2 ≤ N < ${formatInt(floor)} ${below.length === 1 ? 'has' : 'have'} no Robust σ/E, below its floor of N = ${formatInt(floor)} (the CLAUDE.md robust floor), `
    + `so ${below.length === 1 ? 'it is' : 'they are'} not drawn; Sample σ/μ reports ${below.length === 1 ? 'it' : 'them'} from N = 2.`;
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

/** The payload notes the builder states itself, from structure, in the section they belong to. */
function restatedNote(line, labels) {
  return labels.some((label) => line.startsWith(`${label} (`))
    || /^Off the axis:|^The y range follows|^E on both axes|^The top axis is an exact|^Anchors:|^Fits:|^σ\/E is reported from|median response R̃ − 1 from|^A regressor trained on a bounded|^For unbiased Gaussian errors median/.test(line);
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

/** The two forms the E view draws, as the drawer names them. */
const ENERGY_FORM_NAMES = Object.freeze({
  quadrature: 'quadrature fit a/√E ⊕ b',
  pinned: 'origin-pinned fit a₀/√E ⊕ 0',
});

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

/** The fit a band belongs to, as the drawer lists an outlined band: "A deposit a/√E ⊕ b (S = 3.62, ν = 1, q = 12.71)". */
function outlinedBandName(b, sig) {
  const form = b.form === 'quadrature' ? 'a/√E ⊕ b' : 'a₀/√E ⊕ 0';
  return `${b.reference ? `the reference band about 1 of ${b.short} ${form}` : `${b.short} ${form}`}${bandWhy(b.fit ?? {}, sig)}`;
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
function literatureLegendLine(model) {
  const hues = `Each literature curve has a colour of its own on every card, ${literatureHueList()}: ColorBrewer qualitative hues kept apart from the deposit ink and E2's four hues under normal vision, deuteranopia and protanopia.`;
  const buttons = `The ${RESOLUTION_REFERENCES.map((e) => e.particle).join(' and ')} buttons draw either curve, both (the default) or neither. `
    + 'The ratio panel divides by the curve drawn; with both drawn, by the one the windows lie farther from; with neither, by each shower\'s deposit fit.';
  if (!model.literature.length) return `A literature curve is a dotted line in its own colour; none is drawn now. ${buttons} ${hues}`;
  const refLit = model.literature.find((l) => l.isReference);
  const others = model.literature.filter((l) => !l.isReference);
  const parts = [];
  if (refLit) parts.push(`the ${refLit.entry.particle} curve is the ratio's reference`);
  if (others.length) {
    parts.push(`the ${others.map((l) => l.entry.particle).join(' and ')} curve${others.length > 1 ? 's are' : ' is'} drawn beside it, `
      + 'and on the ratio panel divided by it');
  }
  const labelled = model.endLabels.main.some((l) => l.literature) ? ', labelled with their particles in the end column' : '';
  return `Literature curves are dotted lines in their own colours${labelled}; they are references, not measurements, and never set a range. `
    + `Here ${parts.join('; ')}. ${buttons} ${hues}`;
}

/** One ratio reference's line for a shower: which fit divides its windows, or why nothing does. */
function depositReferenceLine(model, r) {
  const owner = model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}` : 'The deposit';
  if (r.reason) return `${owner}: no ratio marks, ${r.reason}.`;
  const misfit = r.misfit
    ? `, a form that does not describe the deposit's windows (S = ${sigFigs(r.fit.scale_factor, 3)} > ${formatNumber(model.gates.misfit_scale)})`
    : '';
  return `${owner}: the ratio divides by ${r.why} (${r.seriesLabel}), fitted over ${spanGeV(r.span)}${r.provisional ? ', provisional' : ''}${misfit}; `
    + `it is evaluated from ${formatNumber(model.curveMinGev)} to ${formatNumber(model.x.max)} GeV only.`;
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
 * the a/√E ⊕ b and a₀/√E ⊕ 0 fits solid over the windows each was fitted to
 * and dashed beyond, and the ratio panel. Every sentence is built from the
 * panel's `energyModel` and the payload's `axis.energy`, never from matching
 * text, so each count is the model's and the drawer never states what the
 * plot does not show.
 */
function resolutionEnergyNotes({ payload, state, experiment, title, windows, shower, reference, literature }) {
  const notes = new Notes(title ?? resDefaultTitle(payload, true));
  const model = energyModel(payload, { windows, shower, reference, literature });
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
  const drawn = model.series.flatMap((s) => ENERGY_FORMS.map((form) => ({ s, f: s.fits[form] })).filter(({ f }) => f?.drawable));
  const points = model.series.flatMap((s) => s.points);
  // As the axis writes it: "1/8 to 8".
  const kText = `${ratioTickLabel(1 / ratio.k)} to ${ratioTickLabel(ratio.k)}`;
  const is = (n) => (n === 1 ? 'is' : 'are');

  // ---- Selection
  const selection = resSelectionLines(payload, state, experiment, model, shower);
  selection.push(estimatorLine(w));
  selection.push(`View: ${w.symbol} against the energy E in GeV, 0 to ${formatNumber(x.max)} GeV, with a ratio panel underneath on the same energy axis.`);
  selection.push(lit
    ? `Ratio to: ${ref.label}, the literature curve ${referenceEquation(lit)}, the same curve for every shower.`
    : `Ratio to: ${ref.label}.`);
  selection.push(model.literature.length
    ? `Literature curves drawn: ${model.literature.map((l) => `${l.entry.particle}${l.isReference ? ' (the ratio\'s reference)' : ''}`).join(' and ')}.`
    : 'Literature curves drawn: none.');
  notes.section(SECTION.selection, selection);

  // ---- What is drawn
  const spanRule = model.spans.shared && model.spans.span
    ? `here ${spanGeV(model.spans.span)}`
    : (drawn.length ? 'each its own, listed under Disclosures' : 'no fit is drawn for this selection');
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
    : [...Object.values(ref.byShower).map((r) => depositReferenceLine(model, r)),
      'The reference fit\'s own 95% band relative to itself, [lo/ŷ, hi/ŷ] about 1, is a muted wash, fainter beyond the reference\'s fitted span.',
      'With no literature curve drawn, the ratio divides each shower by its own deposit fit.'];
  // With both curves drawn, why the ratio divides by the one it does.
  const choiceLine = referenceChoiceText(model);
  if (choiceLine) refLines.splice(1, 0, choiceLine);
  const method = RES_ENERGY_METHOD_SECTION;
  notes.section(SECTION.drawn, [
    model.rule ? sentence(model.rule) : 'Each window is drawn at E = 1/x², x = ⟨1/√p⟩ being the 1/√E view\'s own abscissa.',
    `Methodology §${method.number}, "${method.title}", derives this view, from E = 1/x² to the ratio panel's axis; §3.6 audits its marks.`,
    'Windows of different series at one energy are drawn at that energy, not set apart: a window sits on its own curve, which no offset could follow.',
    `Mode drawn: ${modeLabel(mode, gates)}. ${mode === 'anchors'
      ? 'The windows control reads "3 anchors": only the windows the 3-anchor fit used are drawn.'
      : `The windows control reads "All windows": every window with N ≥ ${formatInt(gates.report_n)} that has a ${w.symbol} is drawn, those below ${curveMin} GeV as points only, since no fit uses them.`}`,
    `${plural(model.nPoints, 'window')} and ${plural(model.nLines, 'fit curve')} are drawn in this view.`,
    'Two fits per series can be drawn, each by weighted least squares with the 1/√E view\'s iterated weights: the quadrature a/√E ⊕ b = √(a²/E + b²), fitted as (σ/E)² = A/E + B and drawn only where both terms are defined (A > 0 and B > 0), '
      + 'and the origin-pinned a₀/√E ⊕ 0, always. The affine a/√E + b is drawn in the 1/√E view and stays in the fit table; on that view the quadrature fit is tabled, never drawn.',
    w.weightSentence,
    `Each curve is solid over the span of the windows it was fitted to (the lowest window edge to the highest: ${spanRule}) and dashed beyond it, up to ${formatNumber(x.max)} GeV and down to ${curveMin} GeV; `
      + `no curve is drawn below ${curveMin} GeV, the lowest window edge any fit can use. Its 95% band continues over the dashed parts at one third of its strength.`,
    `The energy axis is linear from 0 to ${formatNumber(x.max)} GeV in steps of ${formatNumber(x.interval)} GeV${Number.isFinite(model.dataMaxGev) ? `; the highest window edge is ${formatNumber(model.dataMaxGev)} GeV` : ''}. `
      + `${capital(w.symbol)} starts at zero and ends at ${pct(y.hi)}${y.provisional ? ' (provisional)' : ''}.`,
    ...model.notes.map((note, i) => (i === 0 ? rangeBasis(note) : note)).filter(Boolean).map(sentence),
    'The ratio panel shares the energy axis. A window is drawn as its σ/E divided by the reference at its E and its whisker, where it has one, as the two ends of its interval divided the same way; each drawn fit is divided by the reference too, with its band divided the same way; the fit that is the reference is not drawn, being 1 by construction.',
    ...refLines,
    `The ratio axis is logarithmic and symmetric about 1, from ${kText}, so a factor k above 1 and a factor k below lie at equal distances from the 1.0 rule; `
      + `k is the first of ${RATIO_STEPS.map(String).join(', ')} that covers the robust ratio marks, the windows alone: those of N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV (whiskers included), `
      + 'each against a reference that is neither provisional nor of a form that does not describe its windows. No fit sets it: a fit\'s ratio that leaves the axis is clipped there with a caret. '
      + `The ladder ends at ${RATIO_STEPS[RATIO_STEPS.length - 1]}, and a robust mark beyond it is clipped with a caret.`,
    'The fit table under the plot keeps the three rows per series in the 1/√E view\'s order, affine, origin-pinned and quadrature, named for this view: the affine fit "drawn in the 1/√E view", the origin-pinned fit "drawn", the quadrature fit "drawn" or "not drawn" with its reason.',
  ]);

  // ---- Disclosures
  const dis = [];
  if (y.provisional) {
    // What sets a provisional range: the response's weaker windows, counted over every series (the range is the response's).
    const reported = (payload.series ?? []).flatMap((s) => s.windows ?? [])
      .filter((w) => Number.isFinite(w.value) && (w.n ?? 0) >= gates.report_n);
    const weakFrom = reported.filter((w) => (w.p_lo ?? 0) >= model.yMinGev && w.n < gates.fit_n).length;
    const belowFloor = reported.filter((w) => (w.p_lo ?? 0) < model.yMinGev).length;
    const by = [
      weakFrom && `the ${plural(weakFrom, 'window')} of N < ${formatInt(gates.fit_n)} from ${yMin} GeV`,
      belowFloor && `the markers of the ${plural(belowFloor, 'window')} below ${yMin} GeV`,
    ].filter(Boolean);
    dis.push(`The y range is provisional: no window from ${yMin} GeV reaches N = ${formatInt(gates.fit_n)}${by.length
      ? `, so it is set by weaker windows of the response, ${by.join(' and ')}`
      : `, and no window of the response reports ${w.symbol}, so nothing on the plot sets it`}.`);
  } else {
    dis.push(`The y range follows the windows alone, from zero: those with N ≥ ${formatInt(gates.fit_n)} from ${yMin} GeV, whiskers included. A fit summarises its windows and is not more evidence, `
      + `so no fitted curve, band or extrapolation sets it; a window below ${yMin} GeV never sets it, whatever its N.`);
  }
  const parts = [
    clipped.markers && plural(clipped.markers, 'marker'),
    clipped.whiskers && plural(clipped.whiskers, 'whisker'),
    clipped.fits && plural(clipped.fits, 'fit'),
    clipped.literature && plural(clipped.literature, 'literature curve'),
  ].filter(Boolean);
  if (parts.length) {
    dis.push(`Clipped at the top of the main panel (${pct(y.hi)}) ${inForce(model, shower)}, each with a caret and its true values in its tooltip: ${parts.join(', ')}.`);
  }
  const offEntries = model.offScale.reduce((a, g) => a + g.entries.length, 0);
  if (offEntries) {
    dis.push(`${plural(offEntries, 'window')} ${offEntries === 1 ? 'lies' : 'lie'} above the top of the axis (${pct(y.hi)}), drawn clipped with a caret and listed by window: `
      + `${model.offScale.map((g) => `${g.label} — ${g.entries.map((e) => `${e.short} ${pct(e.value)} (N = ${formatInt(e.n)})`).join(', ')}`).join('; ')}.`);
  }
  const cutFits = drawn.filter(({ f }) => f.cut);
  if (cutFits.length) {
    dis.push(`${plural(cutFits.length, 'fit')} ${cutFits.length === 1 ? 'leaves' : 'leave'} the top of the main panel, line or band, each clipped there with a caret whose tooltip gives its true values: `
      + `${cutFits.map(({ s, f }) => `${s.label}, ${ENERGY_FORM_NAMES[f.form]}${f.provisional ? ' (provisional)' : ''} `
        + `${f.cut.lineAt !== null ? 'line and band' : 'band'}, highest ${pct(f.cut.peak[3])} at E = ${sig(f.cut.peak[0])} GeV`).join('; ')}. `
      + 'The range follows the windows alone, so no curve, band or extrapolation sets it.');
  }
  const misfits = misfitLine(drawn, gates, (form) => ENERGY_FORM_NAMES[form]);
  if (misfits) dis.push(misfits);
  const floorCut = drawn.filter(({ f }) => f.floorCut);
  if (floorCut.length) {
    const why = [
      floorCut.some(({ f }) => f.form === 'quadrature') && 'for the quadrature fit, where the band of (σ/E)² falls below zero, its lower edge is cut at 0',
      floorCut.some(({ f }) => f.form === 'pinned') && 'for the origin-pinned fit, where a₀/√E − q·SE(a₀)/√E would be negative, its lower edge is cut at σ/E = 0',
    ].filter(Boolean);
    dis.push(`${plural(floorCut.length, 'fit')} ${floorCut.length === 1 ? 'has the lower edge of its band' : 'have the lower edges of their bands'} cut at 0: `
      + `${floorCut.map(({ s, f }) => `${s.label}, ${ENERGY_FORM_NAMES[f.form]}`).join('; ')}; ${why.join('; ')}.`);
  }
  const outlined = model.bandsOutlined;
  if (outlined.main || outlined.ratio) {
    const listed = ['main', 'ratio'].map((panel) => [panel, outlined.entries.filter((b) => b.panel === panel)])
      .filter(([, list]) => list.length)
      .map(([panel, list]) => `${panel === 'main' ? 'main panel' : 'ratio panel'}: ${list.map((b) => outlinedBandName(b, sig)).join('; ')}`);
    const n = outlined.main + outlined.ratio;
    dis.push(`${plural(n, 'band')} ${n === 1 ? 'spans' : 'span'} half ${n === 1 ? 'its' : 'their'} axis or more at some energy over the fitted windows, `
      + `so ${n === 1 ? 'it is' : 'they are'} drawn as two thin edges in the series' colour, solid over the span and dashed beyond, never as a wash: ${listed.join('; ')}. `
      + 'A small ν makes such a band wide: once S > 1 scales the covariance, q is Student\'s t of the fit\'s own ν, 12.7 at ν = 1.');
  }
  if (!drawn.length) {
    dis.push('No fit is drawn for this selection, so the main panel shows windows only and the ratio panel marks only.');
  } else if (!model.spans.shared) {
    // One clause per span, the fits that share it named by shower, estimator and form.
    const bySpan = new Map();
    for (const b of model.spans.bySeries) {
      const key = spanGeV(b.span);
      const short = model.series.find((x) => x.key === b.key)?.short ?? b.label;
      bySpan.set(key, [...(bySpan.get(key) ?? []), `${short} ${b.form === 'quadrature' ? 'a/√E ⊕ b' : 'a₀/√E ⊕ 0'}`]);
    }
    dis.push(`The fits were not all fitted over the same windows, so their solid parts differ: ${[...bySpan].map(([span, names]) => `${span} for ${names.join(', ')}`).join('; ')}; each is dashed beyond its own span.`);
  }
  for (const s of model.series) {
    for (const form of ENERGY_FORMS) {
      const f = s.fits[form];
      if (!f || f.drawable) continue;
      const q = f.fit?.params;
      const numbers = form === 'quadrature' && q && Number.isFinite(q.a2) && Number.isFinite(q.b2)
        ? ` (A = ${sig(q.a2)} ± ${sig(q.se_a2)} %²·GeV, B = ${sig(q.b2)} ± ${sig(q.se_b2)} %²)` : '';
      dis.push(`${s.label}: the ${ENERGY_FORM_NAMES[form]} is not drawn, ${f.reason}${numbers}; it stays in the fit table.`);
    }
  }
  for (const s of model.series) {
    const mf = s.mf;
    if (!mf) continue;
    if (mf.provisional) dis.push(`${s.label}: the fits are provisional, through windows of N ≥ ${formatInt(gates.whisker_n)}, because fewer than two windows reach N = ${formatInt(gates.fit_n)}; drawn faded.`);
    if (mode === 'anchors') for (const sub of mf.substitutions ?? []) dis.push(`${s.label}: ${sentence(sub.reason)}`);
    for (const [form, fit] of [['affine', mf.affine], ['pinned', mf.pinned], ['quadrature', mf.quadrature]]) {
      if (!fit) continue;
      const name = form === 'affine' ? 'affine fit (tabled in this view)' : ENERGY_FORM_NAMES[form];
      const bandDrawn = form !== 'affine' && s.fits[form]?.drawable;
      if (!(fit.ndf > 0)) dis.push(`${s.label}, ${name}: ν = 0, the fit passes through its points exactly and has no χ² test.`);
      if (fit.scale_factor > 1) {
        dis.push(`${s.label}, ${name}: χ²/ν = ${sig(fit.chi2 / fit.ndf)} (p = ${sig(fit.p_value)}), so its standard errors are scaled by S = ${sig(fit.scale_factor)} (PDG)`
          + `${bandDrawn ? `, and its band takes Student's t₀.₉₇₅,${formatInt(fit.ndf)} = ${sigFigs(fit.band_quantile, 4)} rather than 1.96, since S is estimated from the fit's own ν = ${formatInt(fit.ndf)}` : ''}.`);
      }
      if (fit.converged === false) {
        dis.push(`${s.label}, ${name}: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so it is the last refit's ${form === 'quadrature' ? 'fit' : 'line'}, not a fixed point.`);
      }
    }
  }
  const weak = points.filter((p) => p.weak && !p.subFloor);
  const weakFitted = weak.filter((p) => p.fitted).length;
  const weakAlone = weak.length - weakFitted;
  if (weakFitted) dis.push(`${plural(weakFitted, 'window')} of N < ${formatInt(gates.fit_n)} drawn faded with ${weakFitted === 1 ? 'its' : 'their'} ${w.whisker} and fitted, in a provisional fit.`);
  if (weakAlone) dis.push(`${plural(weakAlone, 'window')} of N < ${formatInt(gates.fit_n)} drawn faded with ${weakAlone === 1 ? 'its' : 'their'} ${w.whisker}, not fitted.`);
  const sub = points.filter((p) => p.subFloor).length;
  if (sub) dis.push(`${plural(sub, 'window')} of N < ${formatInt(gates.whisker_n)} drawn as a faded dashed ring with no whisker: ${w.symbol} is reported from N = ${formatInt(gates.report_n)}, an interval is drawn from N = ${formatInt(gates.whisker_n)}.`);
  const below = points.filter((p) => p.below4);
  if (below.length) {
    dis.push(`${plural(below.length, 'window')} below ${curveMin} GeV ${is(below.length)} drawn as ${below.length === 1 ? 'a point' : 'points'} only: no fit uses ${below.length === 1 ? 'it' : 'them'}, and no curve is drawn there.`);
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
    dis.push(`This mode fits every window from ${curveMin} GeV, ${names.join(', ')} included (${plural(belowAnchors.length, 'series', 'series')}): below ${formatNumber(gates.anchor_low_gev)} GeV, `
      + 'the anchors\' floor, the sampling fraction is still rising and a/√E ⊕ b may not describe σ/E.');
  }
  for (const s of model.series) {
    if (!s.unreported.length) continue;
    dis.push(`${s.label}: on the axis but not drawn, ${w.symbol} not estimable: `
      + `${s.unreported.map((x) => `${x.label} (${w.unreportedWhy(x)})`).join(', ')}; ${w.symbol} is reported from N = ${formatInt(gates.report_n)}.`);
  }

  // The ratio panel.
  dis.push(ratio.provisional
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
    ratio.clipped.fits && plural(ratio.clipped.fits, 'fit'),
    ratio.clipped.bands && plural(ratio.clipped.bands, 'reference band'),
    ratio.clipped.literature && plural(ratio.clipped.literature, 'literature ratio line'),
  ].filter(Boolean);
  if (ratioParts.length) {
    dis.push(`Clipped at the ratio axis (${kText}) ${inForce(model, shower)}, each with a caret and its true values in its tooltip: ${ratioParts.join(', ')}.`);
  }
  if (ratio.clipped.bands) {
    dis.push(`${plural(ratio.clipped.bands, 'reference band')} about 1 ${is(ratio.clipped.bands)} clamped at the ratio axis, a muted wash with one muted caret where it first leaves the axis, scanning up in E.`);
  }
  if (points.some((p) => p.ratio.drawn && Number.isFinite(p.ratio.lo))) {
    dis.push(`A ratio whisker is the window's 95% ${w.sample ? 'χ² interval' : 'interval'} divided by ${lit ? 'the literature curve' : 'the reference fit'} at its E: it is conditional on the reference, ${ref.label}, `
      + `and does not include the reference's own uncertainty. ${lit
        ? 'The literature curve has no interval reported, so none is carried.'
        : 'The reference fit\'s own band about 1 is drawn beside it, not folded in.'}`);
  }
  if (ratio.belowNotDrawn) {
    dis.push(`${plural(ratio.belowNotDrawn, 'window')} below ${curveMin} GeV ${is(ratio.belowNotDrawn)} not drawn on the ratio panel: the deposit fit is drawn from ${curveMin} GeV, so the reference has no value there.`);
  }
  for (const r of ratio.noReference) {
    dis.push(`${model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}` : 'The deposit'} has no ratio marks: ${sentence(r.reason)}`);
  }
  if (!lit) {
    for (const r of Object.values(ref.byShower)) {
      const owner = model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}'s` : 'The deposit';
      if (r.provisional) dis.push(`${owner} reference fit is provisional: its ratio marks are conditional on a fit through windows of N < ${formatInt(gates.fit_n)}, so none of them sets the ratio range.`);
      if (r.misfit) {
        const which = `${model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}'s reference, its deposit's` : 'The reference, the deposit\'s'} `
          + `${r.form === 'quadrature' ? 'a/√E ⊕ b' : 'a₀/√E'} fit,`;
        dis.push(`${which} does not describe its windows (S = ${sig(r.fit.scale_factor)} > ${formatNumber(gates.misfit_scale)}, χ²/ν = ${sig(r.fit.chi2 / r.fit.ndf)}): `
          + 'its ratio marks are conditional on a form its own windows reject, so none of them sets the ratio range.');
      }
    }
  }

  // The literature curves drawn.
  if (model.literature.length) {
    dis.push(`The literature curves are the two legend curves of one figure, ${REFERENCE_SOURCE.figure}, supplied by ${REFERENCE_SOURCE.by} on ${REFERENCE_SOURCE.supplied} `
      + `(record ${REFERENCE_SOURCE.record}): ${RESOLUTION_REFERENCES.map((e) => referenceEquation(e)).join(' and ')}, transcribed as the legend prints them.`);
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
  dis.push(relationLine(w));
  dis.push(...calibrationLines(w));
  dis.push(robustFloorLine(w, model));
  dis.push(...responseRangeLines(w, model));
  // Martin's override: the literature curves stay on under the median, and the server's own warning says what that comparison is.
  if (w.name === 'median' && model.literature.length && w.est.literature?.warning) dis.push(w.est.literature.warning);
  if (m.source === 'xgb') dis.push('The detector series uses every selected event; the XGBoost series only its validation split, so the two series do not share their events.');
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
    'Colour is the estimator: the detector\'s calibrated deposit in ink, a model in the hue E2 gives its source (ColorBrewer qualitative, ≥ 3:1 against the card). On two-shower data fill and line strength are the shower: shower A is a filled marker with full-strength lines, shower B a hollow marker with its lines at 70% strength, raised to 3:1 where the card needs it. With both showers drawn, a letter "A" or "B" in the series\' colour at each curve\'s right end, in a column beside the plot, names the shower; a curve that leaves the plot before the axis end has its caret instead. A larger marker is a window of the 3-anchor fit.',
    'The dash is extrapolation and the width is the form: a solid line is a fit over the windows it was fitted to and a dashed line the same fit beyond them; the thicker line is the quadrature a/√E ⊕ b, the thinner the origin-pinned a₀/√E ⊕ 0. '
      + `A fit drawn fainter, its curve, dashed extrapolation and band alike, is provisional or of a form that does not describe its windows (S > ${formatNumber(gates.misfit_scale)}); no fit, faded or not, sets either panel's range.`,
    w.whiskerLegend,
    'The shaded bands are the fits\' 95% confidence bands: the quadrature band is the square root of the band of z = (σ/E)² = A/E + B, ẑ ± q√(gᵀΣg) with g = (1/E, 1), and the pinned band is a₀/√E ± q·SE(a₀)/√E, at half the quadrature band\'s strength; q is 1.96, or Student\'s t₀.₉₇₅,ν once S = √(χ²/ν) > 1 scales the covariance. Over the dashed parts they continue at one third of their strength and are the parameters\' uncertainty only, which assumes the form holds. A band that spans half its axis or more over its fitted windows is drawn as two thin edges in the series\' colour, solid over the span and dashed beyond, never as a wash.',
    literatureLegendLine(model),
    `The ratio panel: the 1.0 rule in ink marks σ/E equal to the reference; ${lit
      ? 'no band about 1 is drawn, since the literature curve has no interval reported'
      : 'a muted wash is the reference fit\'s own 95% band about 1, fainter beyond its fitted span (two thin muted edges where it spans half the axis or more within that span)'}; the axis is logarithmic and symmetric about 1, with ticks at 1 and at the round steps up to k with their reciprocals, which read 1/x below 1, so ÷3 reads 1/3 beside 3.`,
    `A linked crosshair crosses both panels at one E and reads it on the bottom axis, an exact coordinate readout and no data mark; the item tooltips carry the values. A caret at an axis edge marks a mark clipped there, its true values in its tooltip; a muted caret on the ratio panel marks where the reference's band about 1 leaves it. The note above the plot lists the windows above the top${extrapolation ? ` and states the extrapolation rule ("${extrapolation}")` : ''}. A legend entry shows or hides every mark of its series.`,
  ]);
  return notes.done(modelsHazards(payload, 'res-scaling', { windows, shower, view: 'energy', reference, literature }));
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
  view = 'linear', reference = 'deposit', literature = undefined,
} = {}) {
  if (!payload) return null;
  if (view === 'energy') return resolutionEnergyNotes({ payload, state, experiment, title, windows, shower, reference, literature });
  const notes = new Notes(title ?? resDefaultTitle(payload, false));
  const model = resolutionModel(payload, { windows, shower });
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no energy-resolution series.', ...metaDisclosures(payload)]);
    return notes.done([]);
  }
  const { gates, mode } = model;
  const w = resWords(payload, gates);
  const pct = (v) => (Number.isFinite(v) ? `${sigFigs(v, 3)}%` : '—');
  const sig = (v) => sigFigs(v, 3);
  const m = payload.model ?? {};

  // ---- Selection
  notes.section(SECTION.selection, [...resSelectionLines(payload, state, experiment, model, shower), estimatorLine(w)]);

  // ---- What is drawn
  const labels = (payload.series ?? []).map((s) => s.label).filter(Boolean);
  const est = payload.estimator ?? {};
  const nominal = payload.anchors?.labels ?? [];
  // A series with fewer than two windows of N ≥ 20 is fitted provisionally, through its weaker windows.
  const provisional = model.series.some((s) => s.provisional);
  const weakRule = mode === 'anchors' ? ''
    : provisional
      ? `; windows of N < ${formatInt(gates.fit_n)} are drawn faded, and fitted only by a series with fewer than two windows of N ≥ ${formatInt(gates.fit_n)}, whose fit is then provisional`
      : `; windows of N < ${formatInt(gates.fit_n)} are drawn faded and not fitted`;
  notes.section(SECTION.drawn, [
    est.definition ? sentence(est.definition) : '',
    `Each window is the producer's 1 GeV momentum bin; its abscissa is x = ⟨1/√p⟩ over its events, in GeV⁻¹ᐟ², on a reversed axis from 0.5 (4 GeV) at the left to 0 (E → ∞) at the right border, and ${w.symbol} starts at zero, so the bottom-right corner is the origin.`,
    `Mode drawn: ${modeLabel(mode, gates)}${weakRule}.`,
    'Two fits per series are drawn, each by weighted least squares with ' + w.weightClause + `: the affine ${w.symbol} = a/√E + b and the origin-pinned ${w.symbol} = a₀/√E. The quadrature form √(a²/E + b²) is fitted as (σ/E)² = A/E + B and tabled under the plot, not drawn.`,
    w.weightSentence,
    payload.anchors?.rule
      ? `Anchors${nominal.length ? ` (nominal: ${nominal.join(', ')})` : ''}: ${sentence(payload.anchors.rule)}`
      : '',
    `The top axis is a second x axis allowed only as an exact unit conversion: ${sentence(payload.axis?.top?.rule ?? 'E = 1/x², an exact relabelling of the bottom axis; no data are plotted against it.')}`,
    ...noteLines(payload.notes).filter((line) => !restatedNote(line, labels)),
  ].filter(Boolean));

  // ---- Disclosures
  const disclosures = [];
  if (model.y.provisional) disclosures.push(`The y range is provisional: no window reaches N = ${formatInt(gates.fit_n)}, so it is set by weaker windows; no fit sets it.`);
  else {
    disclosures.push(`The y range follows the windows with N ≥ ${formatInt(gates.fit_n)} (whiskers included) alone, from zero: a fit summarises its windows and is not more evidence, `
      + 'so no fitted line or band sets it.');
  }
  const clipped = model.clipped.markers + model.clipped.whiskers;
  if (clipped) {
    disclosures.push(`Clipped at the axis in this view, each with a caret and its true values in its tooltip: ${plural(model.clipped.markers, 'marker')}, ${plural(model.clipped.whiskers, 'whisker')} (the server's count over every on-axis window of every series, both modes: ${formatInt(model.y.n_clipped)}).`);
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
  // The bands drawn as their edges, as the E view lists them: a band that spans half its axis or more over its fitted windows.
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
  for (const s of model.series) {
    if (!s.unreported.length) continue;
    disclosures.push(`${s.label}: on the axis but not drawn, ${w.symbol} not estimable: `
      + `${s.unreported.map((x) => `${x.label} (${w.unreportedWhy(x)})`).join(', ')}; ${w.symbol} is reported from N = ${formatInt(gates.report_n)}.`);
  }
  const points = model.series.flatMap((s) => s.points);
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
      + 'fraction is still rising and a/√E + b may not describe σ/E.');
  }
  const sub = points.filter((p) => p.subFloor).length;
  if (sub) disclosures.push(`${plural(sub, 'window')} of N < ${formatInt(gates.whisker_n)} drawn as a faded dashed ring with no whisker: ${w.symbol} is reported from N = ${formatInt(gates.report_n)}, an interval is drawn from N = ${formatInt(gates.whisker_n)}.`);
  for (const s of model.series) {
    const mf = s.mf;
    if (!mf) continue;
    if (mf.provisional) disclosures.push(`${s.label}: the fits are provisional, through windows of N ≥ ${formatInt(gates.whisker_n)}, because fewer than two windows reach N = ${formatInt(gates.fit_n)}; drawn faded.`);
    if (mode === 'anchors') for (const x of mf.substitutions ?? []) disclosures.push(`${s.label}: ${sentence(x.reason)}`);
    const affine = mf.affine;
    const pinned = mf.pinned;
    if (!affine) disclosures.push(`${s.label}: fewer than two windows to fit, so no line is drawn.`);
    for (const fit of [affine, pinned, mf.quadrature]) {
      if (!fit) continue;
      const name = { affine: 'affine fit', pinned: 'origin-pinned fit', quadrature: 'quadrature fit (tabled)' }[fit.form];
      if (!(fit.ndf > 0)) disclosures.push(`${s.label}, ${name}: ν = 0, the fit passes through its points exactly and has no χ² test.`);
      if (fit.scale_factor > 1) {
        disclosures.push(fit.form === 'quadrature'
          ? `${s.label}, ${name}: χ²/ν = ${sig(fit.chi2 / fit.ndf)} (p = ${sig(fit.p_value)}), so the standard errors in the table are scaled by S = ${sig(fit.scale_factor)} (PDG).`
          : `${s.label}, ${name}: χ²/ν = ${sig(fit.chi2 / fit.ndf)} (p = ${sig(fit.p_value)}), so its standard errors are scaled by S = ${sig(fit.scale_factor)} (PDG), `
            + `and its band takes Student's t₀.₉₇₅,${formatInt(fit.ndf)} = ${sigFigs(fit.band_quantile, 4)} rather than 1.96, since S is estimated from the fit's own ν = ${formatInt(fit.ndf)}; the unscaled errors are in its tooltip.`);
      }
      if (fit.converged === false) {
        disclosures.push(`${s.label}, ${name}: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so it is the last refit's ${fit.form === 'quadrature' ? 'fit' : 'line'}, not a fixed point.`);
      }
    }
    if (affine?.negative_intercept) {
      disclosures.push(`${s.label}: the affine b is negative (${pct(affine.params?.b)}): the points fall faster than a/√E; the line runs down to the axis and stops there.`);
    }
    if (Number.isFinite(affine?.params?.a) && affine.params.a < 0) {
      disclosures.push(`${s.label}: the affine a is negative (${sig(affine.params.a)} %·√GeV): σ/E rises with E over these windows, which no stochastic term describes.`);
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
  disclosures.push(w.sample ? '' : sentence(w.est.relation ?? ''), ...calibrationLines(w), robustFloorLine(w, model), ...responseRangeLines(w, model));
  if (m.source === 'xgb') disclosures.push('The detector series uses every selected event; the XGBoost series only its validation split, so the two series do not share their events.');
  disclosures.push('E on both axes is the incident momentum p as the producer writes it; for a massive species √(p² + m²) differs from p by at most m²/2p², 1.7% for a proton at 5 GeV/c.');
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures.filter(Boolean));

  // ---- Marks and legend
  notes.section(SECTION.legend, [
    'Colour is the estimator: the detector\'s calibrated deposit in ink, a model in the hue E2 gives its source (ColorBrewer qualitative, ≥ 3:1 against the card). Shower A is a filled marker and a solid affine line, shower B a hollow marker and a dashed affine line; the origin-pinned fit is a thinner dotted line for both. A larger marker is a window of the 3-anchor fit.',
    w.whiskerLegend,
    'The shaded bands are the fits\' 95% confidence bands from the parameter covariance: ±1.96 √(gᵀΣg) while the windows\' own errors stand, and ±t₀.₉₇₅,ν √(gᵀΣg) once S = √(χ²/ν) > 1 scales the covariance, since S is then estimated from the fit\'s own ν (12.71 at ν = 1). They are the uncertainty of the line, not the spread of the events. The affine band is the stronger wash, the pinned band half of it. '
      + 'A band that spans half its axis or more over its fitted windows (their momentum edges, mapped by x = 1/√E) is drawn as two thin solid edges in the series\' colour, never as a wash; this view marks no extrapolation, so the edges are not dashed beyond those windows.',
    `A fit drawn faded, its line and its band alike, is provisional (fewer than two windows of N ≥ ${formatInt(gates.fit_n)}) or of a form that does not describe its windows (S > ${formatNumber(gates.misfit_scale)}); `
      + 'no fit, faded or not, sets the range.',
    'The top axis reads the energy at the same x, E = 1/x², with ∞ at the right border; no data are plotted against it. A caret at the axis marks a marker, whisker, fitted line or band clipped there, its true values in its tooltip. A legend entry shows or hides every mark of its series.',
  ]);
  return notes.done(modelsHazards(payload, 'res-scaling', { windows, shower }));
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
    if (model.clipped.markers || model.clipped.whiskers || model.clipped.fits || model.clipped.literature || model.clipped.ratio) {
      out.push('marks clipped at the axis');
    }
    const fitsOf = (s) => [s.mf?.affine, s.mf?.pinned, s.mf?.quadrature].filter(Boolean);
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
    const fitsOf = (s) => [...DRAWN_FORMS.map((f) => s.mf?.[f]), s.mf?.quadrature].filter(Boolean);
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

