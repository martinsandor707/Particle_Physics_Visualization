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

import { Notes, SECTION, PHYSICS_HEADINGS, CURVE_AREA_NOTE, onLightScreen, puorScreenNote } from './panel_notes.js';
import { describeSelection } from './export/caption.js';
import { formatInt, formatNumber, formatPercent } from './scale.js';
import { sigmaText } from './panels/chart_panel.js';
import { perfModel, perfQuantities, SOURCE_LABELS } from './panels/perf_bins.js';
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
  ]);
  return notes.done(modelsHazards(payload, 'perf-bins', { quantity: model.quantity, shower }));
}

/* ========================================================= pred-truth == */

/** The colour sentence of the pred-truth ramp for the user's palette. */
function rampSentence(payload, palette) {
  const ramp = countRamp(palette, payload.color?.ramp?.by_palette?.[palette] ?? null);
  const measured = payload.color?.ramp?.by_palette?.[palette];
  const head = `log₁₀ of the showers per bin on ${palette}, positions ${num(ramp.from, 2)} to ${num(ramp.to, 2)} of the ramp; an empty bin is transparent.`;
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

