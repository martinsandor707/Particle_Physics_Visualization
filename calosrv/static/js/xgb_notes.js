/* What the Details drawer says about the four XGBoost cards of the models page.
 *
 * The same contract as models_notes.js: each builder takes `{payload, state,
 * experiment, title, card, ...opts}` - the render options the card drew with
 * (`task`, `label`, `palette`) - and returns `{title, hazards, sections}` in
 * the four standard sections (Selection / What is drawn / Disclosures / Marks
 * and legend), then the card's own headings (the fold values, the rates, the
 * nodes, the features not drawn), so every number on the card can be quoted
 * from the drawer into a manuscript caption.
 *
 * Every XGBoost view is computed once on the whole experiment, as the
 * notebook does: the payload says so (`selection_note`, `filtered: false`) and
 * the Selection section leads with that sentence, then the run - species,
 * seed, model file and its sha256 - instead of the filter, which does not
 * apply. The split check travels on every response (`run.split`); when the
 * training split is not reproduced it is a hazard on every card.
 *
 * The builders read the panels' own pure models (`cvModel`, `binaryModel`,
 * `treeModel`, `importanceModel`), so the drawer never states something the
 * picture does not show. `xgbHazards(payload, card, opts)` names the
 * conditions a reader must not miss, from structure only.
 */

import { Notes, SECTION } from './panel_notes.js';
import { formatInt, formatPercent } from './scale.js';
import { sigFigs } from './panels/chart_panel.js';
import { cvModel, cvAxis, metricText, FOLD_NAME, MEAN_NAME } from './panels/xgb_cv.js';
import { binaryModel, classKey, otherIntervalName } from './panels/xgb_binary.js';
import { treeModel, ruleText, FRAME_WORDS, fidelityText, treePalette } from './panels/xgb_tree.js';
import { importanceModel, FRAME_LABELS, TOP_N, FOLD_NAME as IMP_FOLD_NAME } from './panels/xgb_importance.js';

/** The drawer titles by card id; the shell's card title wins when it passes one. */
export const XGB_TITLES = Object.freeze({
  'xgb-cv': 'Cross-validation (5 Folds)',
  'xgb-binary': 'Binary Thresholding at 2 GeV (99 : 1)',
  'xgb-surrogate': 'Depth-3 Surrogate Tree',
  'xgb-importance': 'Gain Feature Importance',
});

/** Headings the XGBoost cards add after the four standard ones. */
export const XGB_HEADINGS = Object.freeze({
  folds: 'Fold values',
  rates: 'Rates',
  parity: 'Notebook parity metrics',
  nodes: 'Nodes',
  features: 'Features',
  circular: 'Circular quantities',
});

/** Below this fidelity R² the surrogate is flagged as a sketch of the booster. */
export const LOW_FIDELITY_R2 = 0.5;

const pc = (v, d = 1) => formatPercent(v, d);

/* ------------------------------------------------------------ shared -- */

/** The run's sentences: what the analysis was computed on and with. */
export function runLines(payload, experiment = null) {
  const run = payload?.run ?? {};
  const lines = [
    payload?.selection_note ?? 'Computed once on the whole experiment, as the notebook does; the selection does not apply.',
  ];
  if (experiment?.display_name) lines.push(`Experiment: ${experiment.display_name}.`);
  const labels = (run.labels ?? []).map((l) => `${l}${run.label_units?.[l] ? ` [${run.label_units[l]}]` : ''}`).join(', ');
  lines.push(`Species ${run.species ?? '—'}, seed ${run.seed ?? '—'}; the ${run.task ?? payload?.task ?? ''} model`
    + `${labels ? ` (outputs in the model's order: ${labels})` : ''}.`);
  lines.push(`Model file ${run.model_file ?? '—'} (sha256 ${run.sha256 ?? '—'}), XGBoost ${run.xgboost_version ?? '—'}, analysis version ${run.analysis_version ?? '—'}.`);
  if (Number.isFinite(run.n_rows)) {
    lines.push(`${formatInt(run.n_rows)} rows: ${formatInt(run.n_train)} training, ${formatInt(run.n_holdout)} hold-out `
      + `(train_test_split, test_size ${run.test_size ?? 0.2}, random_state 42, over the rows in event order).`);
  }
  return lines;
}

/**
 * The split check, as a disclosure: seed 42's ratio against the largest of
 * the other seeds the server compared (`max_others`, `seed_of_max`), never
 * the 99 ratios themselves.
 */
export function splitLines(payload) {
  const run = payload?.run ?? {};
  const split = run.split;
  const out = [];
  if (split) {
    const nOthers = split.n_others ?? split.ratio_others?.length ?? 0;
    const against = Number.isFinite(split.max_others)
      ? `, against at most ${sigFigs(split.max_others, 3)} at the ${formatInt(nOthers)} other seeds (random_state ${split.seed_of_max})`
      : '';
    const measured = `validation / training MSE of the shipped model is ${sigFigs(split.ratio_42, 3)} at random_state 42${against}`;
    if (split.reproduced === false) {
      const warning = split.warning ?? `${measured}; the hold-out rows may include rows the model was trained on.`;
      out.push(/^Split not reproduced/.test(warning) ? warning : `Split not reproduced: ${warning.replace(/\.?$/, '.')}`);
    } else {
      const margin = Number.isFinite(split.headroom) && Number.isFinite(split.margin)
        ? ` (${sigFigs(split.headroom, 3)} times the largest, where ${sigFigs(split.margin, 3)} is required)`
        : '';
      out.push(`Split check passed: ${measured}${margin}. The rule: ${split.rule ?? 'the ratio at random_state 42 must exceed the others.'}`);
    }
  }
  if (run.archive_increasing === false) {
    out.push('The archive\'s event_number was not strictly increasing, so the event order may not be the file order the notebook split.');
  }
  return out;
}

/** The payload's warnings and its sampling, as disclosures. */
function metaDisclosures(payload) {
  const out = [...(payload?.meta?.warnings ?? [])];
  if (payload?.meta?.exact === false) out.push('Sampled preview: the exact numbers follow.');
  return out;
}

/** The server's notes object as lines, skipping the keys a builder words itself. */
function noteLines(notes, skip = []) {
  if (!notes || typeof notes !== 'object') return [];
  return Object.entries(notes).filter(([k, v]) => typeof v === 'string' && !skip.includes(k)).map(([, v]) => v);
}

/**
 * The conditions a reader must not miss on an XGBoost card, from structure
 * only: the split check on every card; per card the clipped intervals, the
 * minority class, a low-fidelity surrogate, a drawn azimuth.
 */
export function xgbHazards(payload, card, opts = {}) {
  const out = [];
  if (!payload) return out;
  if (payload.meta?.exact === false) out.push('sampled');
  if (payload.run?.split?.reproduced === false) out.push('split not reproduced');
  if (payload.run?.archive_increasing === false) out.push('event order unverified');
  if (card === 'xgb-cv') {
    const model = cvModel(payload);
    if (model?.clipped.length) out.push('interval clipped');
  } else if (card === 'xgb-binary') {
    if (payload.minority) out.push(`minority class of ${formatInt(payload.minority.n)} rows`);
    if (payload.design?.fallback) out.push('fallback class rule');
    if ((payload.rates ?? []).some((r) => !Number.isFinite(r.value))) out.push('undefined rate');
  } else if (card === 'xgb-surrogate') {
    const model = treeModel(payload, opts);
    if (model && Number.isFinite(model.fidelity.r2) && model.fidelity.r2 < LOW_FIDELITY_R2) out.push('low surrogate fidelity');
    if (model?.label === 'phi') out.push('linear mean of an azimuth');
  } else if (card === 'xgb-importance') {
    if ((payload.features ?? []).some((f) => f.clipped)) out.push('interval clipped');
  }
  return out;
}

/* ================================================================ E1 == */

/** One fold's numbers, as the drawer lists them. */
function foldLine(payload, k) {
  const f = payload.folds[k];
  const metrics = (payload.metrics ?? []).map((m) => `${m.label} ${metricText(f.metrics?.[m.id], m.id, m.unit)}`).join(' · ');
  const head = `Fold ${formatInt(f.fold + 1)} (refitted on ${formatInt(f.n_train)} rows, scored on ${formatInt(f.n_val)})`;
  if (!f.per_label || !payload.per_label) return `${head}: ${metrics}.`;
  const per = Object.entries(payload.per_label).map(([label, block]) => {
    const vals = (block.metrics ?? []).map((m) => `${m.label} ${metricText(f.per_label?.[label]?.[m.id], m.id, m.unit)}`).join(', ');
    return `${label === 'phi' ? 'φ' : label === 'theta' ? 'θ' : label} ${vals}`;
  }).join('; ');
  return `${head}: parity ${metrics}; ${per}.`;
}

/** The E1 drawer. */
export function xgbCvNotes({ payload, experiment = null, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? XGB_TITLES['xgb-cv']);
  const model = cvModel(payload);
  const k = payload.kfold ?? {};
  const hp = payload.hyperparameters ?? {};
  notes.section(SECTION.selection, [
    ...runLines(payload, experiment),
    `KFold(${k.n_splits ?? 5}, shuffle=${k.shuffle === false ? 'False' : 'True'}, random_state=${k.random_state ?? 42}) over all `
      + `${formatInt(payload.n_rows)} rows; each fold refits the notebook's regressor (${hp.objective ?? 'reg:squarederror'}, `
      + `${hp.n_estimators ?? 100} trees, learning rate ${hp.learning_rate ?? 0.1}, random_state ${hp.random_state ?? 42}).`,
  ]);
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no folds.', ...splitLines(payload), ...metaDisclosures(payload)]);
    return notes.done(xgbHazards(payload, 'xgb-cv'));
  }
  const drawn = [
    'One small multiple per metric, each on its own scale: the error metrics (MAE, MSE, RMSE) from zero, R² near 1.',
    payload.notes?.folds ?? '',
    payload.notes?.interval ?? '',
    ...(payload.metrics ?? []).map((m) => `${m.label}${m.unit ? ` [${m.unit}]` : ''}: ${m.definition}.`),
  ];
  if (model.angle) {
    drawn.push('Top row: the notebook\'s parity numbers (sklearn\'s mean over φ and θ, φ unwrapped), in rad.');
    drawn.push(payload.notes?.per_label ?? 'Bottom row: per label, in mrad.');
  }
  for (const row of model.rows) {
    for (const panel of row.panels) {
      const axis = cvAxis(panel);
      if (axis.truncated) {
        drawn.push(`The ${panel.title} axis${model.angle ? ` (${row.id === 'parity' ? 'parity' : 'per label'})` : ''} is truncated: it runs from `
          + `${metricText(axis.min, 'r2', '')} to 1, marked by a break on the axis and named in the panel title.`);
      }
    }
  }
  notes.section(SECTION.drawn, drawn);

  const disclosures = [...splitLines(payload)];
  if (model.clipped.length) disclosures.push(`Intervals clipped by the server to the range the metric can take: ${model.clipped.join('; ')}.`);
  if (model.angle) {
    disclosures.push(payload.notes?.parity ?? 'The parity numbers average φ and θ with φ unwrapped, as the notebook prints them.');
    disclosures.push('φ: the per-label residual is wrapped to (−π, π] before its MAE and RMSE; φ has no R², which is undefined for an azimuth.');
    if (payload.notes?.order) disclosures.push(payload.notes.order);
  }
  disclosures.push(payload.notes?.refit ?? '');
  disclosures.push(...noteLines(payload.notes, ['folds', 'interval', 'refit', 'parity', 'per_label', 'order']));
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);

  notes.section(SECTION.legend, [
    `${FOLD_NAME}: an open ring, one per fold, left of the slot's centre - five observations, so their spread is shown by the dots themselves.`,
    `${MEAN_NAME}: the filled diamond. Its capped whisker is the ${model.intervalLabel}: the uncertainty of the mean, never the spread of the folds.`,
    'The SD of the folds is in the mean\'s tooltip, beside the SE; it has no mark, the folds being drawn.',
    'A double stroke across an R² axis marks a truncated scale. Every tooltip gives the fold\'s or the mean\'s full numbers.',
  ]);

  const folds = payload.folds.map((_, i) => foldLine(payload, i));
  const summaries = [];
  for (const row of model.rows) {
    for (const panel of row.panels) {
      for (const slot of panel.slots) {
        const s = slot.summary ?? {};
        const u = (v) => metricText(v, panel.metric, panel.unit);
        const spread = (v) => `${sigFigs(v, 3)}${panel.unit ? ` ${panel.unit}` : ''}`;
        summaries.push(`${panel.title}, ${slot.long}: mean ${u(s.mean)}, interval [${u(s.t95?.[0])}, ${u(s.t95?.[1])}], SD ${spread(s.sd)}, SE ${spread(s.se)}.`);
      }
    }
  }
  notes.section(XGB_HEADINGS.folds, [...folds, ...summaries]);
  return notes.done(xgbHazards(payload, 'xgb-cv'));
}

/* ================================================================ E3 == */

/** The E3 drawer. */
export function xgbBinaryNotes({ payload, experiment = null, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? XGB_TITLES['xgb-binary']);
  const model = binaryModel(payload);
  const d = payload.design ?? {};
  notes.section(SECTION.selection, [
    ...runLines(payload, experiment),
    `Drawn from ${d.drawn_from ?? 'the validation split'}: ${formatInt(d.n_0_target)} rows of class 0 (${d.class_0_rule ?? 'p < 2 GeV'}) and `
      + `${formatInt(d.n_1_target)} of class 1 (${d.class_1_rule ?? 'p > 10 GeV'}), ${d.ratio ?? '99 : 1'}; pools of ${formatInt(d.pool_0)} and ${formatInt(d.pool_1)} rows.`,
    d.sampler ? `Sampler: ${d.sampler}.` : '',
    d.prediction ? `Prediction: ${d.prediction}.` : '',
  ]);
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no confusion matrix.', ...splitLines(payload), ...metaDisclosures(payload)]);
    return notes.done(xgbHazards(payload, 'xgb-binary'));
  }
  const c = model.confusion;
  const other = model.rates.find((r) => r.method && r.method !== 'wilson');
  notes.section(SECTION.drawn, [
    `Left: the confusion matrix as counts - TN ${formatInt(c.tn)}, FP ${formatInt(c.fp)}, FN ${formatInt(c.fn)}, TP ${formatInt(c.tp)} (${c.layout ?? 'rows true class, columns predicted class'}); `
      + 'each cell prints its count and its share of the true class, with no colour ramp (at 99 : 1 a ramp over counts says only that class 0 is large).',
    'Right: accuracy, balanced accuracy and the per-class recall and precision as points on the full 0–100% scale, each with its 95% interval as a capped whisker.',
    payload.notes?.intervals ?? '',
    payload.notes?.counts ?? '',
  ]);
  const disclosures = [];
  if (payload.minority?.note) disclosures.push(payload.minority.note);
  if (d.fallback) disclosures.push(`Class 1 fell back to ${d.class_1_rule ?? 'p > 2 GeV'}: the notebook's rule takes p > 10 GeV only when at least 50 validation rows lie there.`);
  const counts = payload.counts ?? {};
  if (Number.isFinite(d.n_0_target) && counts.class_0 < d.n_0_target) disclosures.push(`Class 0 holds ${formatInt(counts.class_0)} rows, short of the ${formatInt(d.n_0_target)} asked for: its pool had no more.`);
  if (Number.isFinite(d.n_1_target) && counts.class_1 < d.n_1_target) disclosures.push(`Class 1 holds ${formatInt(counts.class_1)} rows, short of the ${formatInt(d.n_1_target)} asked for: its pool had no more.`);
  for (const r of model.rates.filter((x) => x.undefined)) disclosures.push(`${r.label} is undefined: its denominator is empty; no point is drawn.`);
  for (const r of model.rates.filter((x) => x.nUndefinedReplicates)) disclosures.push(`${r.label}: ${formatInt(r.nUndefinedReplicates)} bootstrap replicates were undefined and dropped.`);
  for (const r of model.rates.filter((x) => x.note)) disclosures.push(`${r.label}: ${r.note}`);
  disclosures.push(payload.notes?.weighted ?? 'The notebook\'s support-weighted metrics are dominated by the majority class; they are kept for parity only.');
  disclosures.push(...splitLines(payload));
  disclosures.push(...noteLines(payload.notes, ['intervals', 'counts', 'weighted']));
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);

  notes.section(SECTION.legend, [
    'A solid outline marks a correct cell (TN, TP), a dashed one a wrong cell (FP, FN). The counts carry no interval.',
    'Point and capped whisker in the accent colour: a proportion k / n with its 95% Wilson score interval, the uncertainty of the rate.',
    other ? `Point and capped whisker in text ink: the ${other.short.toLowerCase()} with its ${other.intervalLabel ?? other.method} (legend: ${otherIntervalName(model)}).` : '',
    `Under the matrix: ${classKey(model, 0)}; ${classKey(model, 1)}.`,
  ]);
  notes.section(XGB_HEADINGS.rates, model.rates.map((r) => (r.undefined
    ? `${r.label}: undefined (n = ${formatInt(r.n)}).`
    : `${r.label}: ${pc(r.value)}${Number.isFinite(r.k) ? ` = ${formatInt(r.k)} / ${formatInt(r.n)}` : ` over ${formatInt(r.n)} rows`}; `
      + `${r.intervalLabel ?? '95% interval'} [${pc(r.lo)}, ${pc(r.hi)}]; ${r.definition}.`)));
  const p = payload.parity ?? {};
  notes.section(XGB_HEADINGS.parity, [
    p.label ?? '',
    `Accuracy ${sigFigs(p.accuracy, 4)}, balanced accuracy ${sigFigs(p.balanced_accuracy, 4)}, weighted precision ${sigFigs(p.precision_weighted, 4)}, `
      + `weighted recall ${sigFigs(p.recall_weighted, 4)}, weighted F1 ${sigFigs(p.f1_weighted, 4)}; class counts ${formatInt(p.class_0_count)} and ${formatInt(p.class_1_count)}.`,
  ]);
  return notes.done(xgbHazards(payload, 'xgb-binary'));
}

/* ================================================================ E4 == */

/** One node, as the drawer lists it. */
function nodeLine(model, node) {
  const outputs = model.labels.map((l) => {
    const unit = model.units?.[l] ? ` ${model.units[l]}` : '';
    const circ = node.circular?.[l];
    const r = Number.isFinite(circ?.resultant) ? `, R̄ ${sigFigs(circ.resultant, 3)}` : '';
    return `${l} ${sigFigs(node.values?.[l], 4)} ± ${sigFigs(node.sds?.[l], 4)}${unit}${r}`;
  }).join('; ');
  const head = node.leaf ? `Leaf ${node.id}` : `Node ${node.id}: ${ruleText(node)} (${FRAME_WORDS[node.frame] ?? 'no frame'})`;
  const via = node.path.length ? ` [${node.path.map((p) => `${p.text} ${p.branch}`).join(' → ')}]` : '';
  return `${head}, depth ${node.depth}, n = ${formatInt(node.n)}: ${outputs}${via}.`;
}

/** The E4 drawer. `label` (φ or θ) and `palette` are the card's render options. */
export function xgbTreeNotes({ payload, experiment = null, title = null, label = null, palette = 'viridis' } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? XGB_TITLES['xgb-surrogate']);
  const model = treeModel(payload, { label, palette });
  const tree = payload.tree ?? {};
  notes.section(SECTION.selection, [
    ...runLines(payload, experiment),
    `DecisionTreeRegressor(max_depth=${tree.max_depth ?? 3}, random_state=${tree.random_state ?? 42}, criterion ${tree.criterion ?? 'squared_error'}) `
      + `fitted to ${tree.target ?? 'the booster\'s predictions'} on all ${formatInt(tree.n_rows)} rows, in-sample, as the notebook.`,
  ]);
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no tree.', ...splitLines(payload), ...metaDisclosures(payload)]);
    return notes.done(xgbHazards(payload, 'xgb-surrogate', { label }));
  }
  const ramp = model.ramp;
  notes.section(SECTION.drawn, [
    `${formatInt(model.nodes.length)} nodes, ${payload.rule ?? 'left: feature ≤ threshold; right: feature > threshold'}. `
      + 'Top-down when every box fits the card, else an indented outline in depth-first order.',
    'Each split names its feature, the feature\'s frame, its threshold and the rows that reach it; every node prints the mean of the booster\'s predictions over its rows ± their within-node SD.',
    model.labels.length > 1 ? `The boxes print the ${model.label === 'phi' ? 'azimuth φ' : 'polar angle θ'}; the other output is in each tooltip and in the node list below.` : '',
    model.coloured
      ? `Colour: the node mean on ${treePalette(palette)}, positions ${sigFigs(ramp.from, 2)} to ${sigFigs(ramp.to, 2)} of the ramp (the run that clears 3:1 against the card), `
        + `over ${sigFigs(model.domain[0], 3)} to ${sigFigs(model.domain[1], 3)}${model.unit ? ` ${model.unit}` : ''}; leaves filled, splits outlined.`
      : 'Not coloured: this output\'s node values are linear means of an azimuth, which a sequential ramp would order as if they did not wrap.',
    payload.notes?.description ?? '',
  ]);
  const disclosures = [`${fidelityText(model)}. ${payload.notes?.fidelity ?? ''}`];
  const fid = model.fidelity;
  if (Number.isFinite(fid.r2) && fid.r2 < LOW_FIDELITY_R2) {
    disclosures.push(`The fidelity R² is below ${LOW_FIDELITY_R2}: these three levels of rules describe less than half of the booster's variance; read them as a sketch, not as the model.`);
  }
  const outputs = Object.entries(fid.overall?.outputs ?? {});
  if (outputs.length > 1) disclosures.push(`Per output: ${outputs.map(([l, o]) => `${l} R² ${sigFigs(o.r2, 3)}, MAE ${sigFigs(o.mae, 3)}`).join('; ')}.`);
  disclosures.push(payload.notes?.impurity ?? '');
  disclosures.push(...splitLines(payload));
  disclosures.push(...noteLines(payload.notes, ['description', 'fidelity', 'impurity']));
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'A box is a node: bold first line the rule, then the frame and n, then mean ± within-node SD (a description of the booster: no whisker, no interval).',
    model.coloured ? 'A filled box is a leaf, coloured by its value; an outlined box is a split, outlined in its value\'s colour. The ramp in the header names the scale.'
      : 'A box outlined in text ink is a leaf; a muted outline a split.',
    'Branches: ≤ to the left (the rule holds), > to the right. Each tooltip gives the node\'s path from the root and every output.',
  ]);
  if (model.labels.includes('phi')) {
    notes.section(XGB_HEADINGS.circular, [
      'φ node values are sklearn\'s linear means of the booster\'s predicted azimuths, kept for notebook parity: a linear mean of an azimuth is not a mean direction (CLAUDE.md: never average a circular quantity).',
      model.nodes.some((n) => Number.isFinite(n.circular?.phi?.resultant))
        ? 'Each node\'s mean resultant length R̄ of the predicted φ is printed beside it: near 1 the predictions point one way, near 0 they share no direction.'
        : 'This response carries no circular statistic per node.',
    ]);
  }
  notes.section(XGB_HEADINGS.nodes, model.nodes.map((n) => nodeLine(model, n)));
  return notes.done(xgbHazards(payload, 'xgb-surrogate', { label }));
}

/* ================================================================ E5 == */

/** The E5 drawer. */
export function xgbImportanceNotes({ payload, experiment = null, title = null } = {}) {
  if (!payload) return null;
  const notes = new Notes(title ?? XGB_TITLES['xgb-importance']);
  const model = importanceModel(payload);
  notes.section(SECTION.selection, [
    ...runLines(payload, experiment),
    `${formatInt(payload.n_features)} model features, ${formatInt(payload.n_used)} split on by the shipped booster.`,
  ]);
  if (!model) {
    notes.section(SECTION.disclosures, ['This response carries no features.', ...splitLines(payload), ...metaDisclosures(payload)]);
    return notes.done(xgbHazards(payload, 'xgb-importance'));
  }
  const m = payload.measure ?? {};
  notes.section(SECTION.drawn, [
    `One row per feature that carries any gain, in the shipped model or in a refit, sorted by the shipped model, at most ${TOP_N}: ${formatInt(model.shown.length)} drawn.`,
    `Bar, from zero: ${m.shipped ?? 'the shipped booster\'s normalised gain'}, in percent.`,
    `Dots: ${m.folds ?? 'the five refits\' normalised gain'}; bracket: their mean with its ${payload.interval?.label ?? '95% interval'}.`,
    `Colour is the feature's frame (ColorBrewer qualitative hues, each ≥ 3:1 against the card): ${model.frames.map((k) => FRAME_LABELS[k]).join(', ')}.`,
    payload.notes?.bar ?? '',
  ]);
  const disclosures = [];
  if (model.hiddenUsed.length) {
    disclosures.push(`Not drawn, beyond the first ${TOP_N} with gain: ${model.hiddenUsed.map((f) => `${f.name} ${pc(f.shipped, 2)} (folds' mean ${pc(f.fold_mean, 2)})`).join('; ')}.`);
  }
  if (model.unused.length) {
    disclosures.push(`Never split on (0 in the shipped model and every refit), not drawn: ${model.unused.map((f) => f.name).join(', ')}.`);
  }
  const clipped = (payload.features ?? []).filter((f) => f.clipped);
  if (clipped.length) disclosures.push(`Interval clipped ${payload.interval?.clip ?? 'to [0, 1]'}: ${clipped.map((f) => f.name).join(', ')}.`);
  disclosures.push(payload.notes?.gain ?? '');
  disclosures.push(`Raw scores: ${m.raw ?? 'get_score gain, weight and cover'}; in each tooltip and below.`);
  disclosures.push(...splitLines(payload));
  disclosures.push(...noteLines(payload.notes, ['bar', 'gain']));
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Bar: the shipped booster, one model - never the folds\' mean.',
    `${IMP_FOLD_NAME}: open rings under the bar, one per refit.`,
    `${model.envelope}: a short tick at the folds' mean inside a thin capped bracket, the uncertainty of that mean. The SD of the folds is in the tooltip; it has no mark.`,
    'The rest of the features are counted at the foot of the plot and listed under Disclosures.',
  ]);
  notes.section(XGB_HEADINGS.features, model.shown.map((f) => `${f.rank}. ${f.name} (${FRAME_LABELS[f.frame] ?? f.frame}): shipped ${pc(f.shipped, 2)}; `
    + `folds ${(f.folds ?? []).map((v) => pc(v, 2)).join(', ')}; mean ${pc(f.fold_mean, 2)} [${pc(f.fold_t95?.[0], 2)}, ${pc(f.fold_t95?.[1], 2)}]; `
    + `gain ${sigFigs(f.raw?.gain, 4)}, weight ${sigFigs(f.raw?.weight, 4)}, cover ${sigFigs(f.raw?.cover, 4)}.`));
  return notes.done(xgbHazards(payload, 'xgb-importance'));
}

/** The builders by card id, for the section controller. */
export const XGB_NOTE_BUILDERS = Object.freeze({
  'xgb-cv': 'xgbCvNotes',
  'xgb-binary': 'xgbBinaryNotes',
  'xgb-surrogate': 'xgbTreeNotes',
  'xgb-importance': 'xgbImportanceNotes',
});
