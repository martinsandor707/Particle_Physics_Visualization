/* The Models page's 2-D cards: network performance, the XGBoost views, the
 * feature explorer and the primaries, each loaded when it scrolls into view
 * and again only when its request changes (lazy_cards.js).
 *
 * The pattern is the Physics page's section (physics_section.js): the cards
 * are built here at construction, with the anatomy of every card on either
 * page (`.card[data-panel]`, Details first in the toolbar, the plot-only
 * Export last), so the shell's Details delegation and the export menu's
 * `[data-export]` wiring cover them; models_main.js constructs the section
 * before `attachExportMenus`. Card-local controls use attributes of their own
 * (`data-models-task`, `data-feature-id`, ...) and never `data-shower`,
 * `data-roi` or `data-reset`.
 *
 * Which cards are on show, and which are shut with the server's reason, is
 * the experiment's plan (capabilities.js `page2Plan`). A card whose request
 * does not apply in the view at hand - the performance cards while the
 * segmentation network is selected, which has no per-shower prediction to set
 * against a truth - says so on the card and asks for nothing.
 *
 * Requests are shared: the prediction-against-truth density and its residual
 * histogram are two readings of one /api/prediction-density, joined while in
 * flight and kept in a small cache, so a card scrolled to later costs no
 * second request. A palette change and a render-only control (the E2
 * statistic, the surrogate tree's output) are repaints of the payload in hand.
 * A load the server refused (a 4xx, the 422 of a shut gate in particular)
 * stays refused for its request; a transient failure (the network, a 5xx)
 * shows its error with a Retry and is asked again on the next refresh.
 *
 * Some state is the page's, not the card's: the network task (`model`, or
 * `xgb_task` where an XGBoost regressor stands in for the networks), the
 * feature, its classes and, on two-shower data, its shower (`fshower`: A or
 * B, sent on every feature request), on an event-level aggregate the frame
 * of its features (the shared `frame` key: absolute, per-shower translated or
 * Local, the sidebar having no frame control there), the XGBoost task and
 * output. Those controls write
 * the shared State, so a link restores them and the sidebar and every card
 * that reads one agree; the rest (`DEFAULT_CONTROLS`) are ephemeral, like the
 * Physics page's card controls.
 *
 * The panel classes and the notes builders are fetched on first use
 * (`import()`, stamped like every static import). A panel module that fails
 * to load (the network, a stale cache) is a load failure like any other: its
 * card says so with a Retry. A notes module that fails to load leaves the
 * drawer with the payload's own notes. Tests inject classes of their own
 * (`panelClasses`) or a module's loader (`panelModules`).
 */

import { getJson, abortRequest, isAbort } from './api.js';
import { LazyCards, requestKey, isRefusal } from './lazy_cards.js';
import { SECTION, notesText, warningsNotShown } from './panel_notes.js';
import { describeError } from './page_common.js';
import { viewFrame } from './capabilities.js';
import { MODELS_LABELS, featureChoices } from './labels.js';

/** Where each panel class lives; fetched on first use. Literal specifiers, so the server stamps them. */
const PANEL_MODULES = {
  PerfBinsPanel: () => import('./panels/perf_bins.js'),
  Hist2dPanel: () => import('./panels/hist2d.js'),
  DistributionPanel: () => import('./panels/distribution.js'),
  FeatureTablePanel: () => import('./panels/feature_table.js'),
  CorrelationPanel: () => import('./panels/correlation.js'),
  RatesPanel: () => import('./panels/rates.js'),
  XgbCvPanel: () => import('./panels/xgb_cv.js'),
  XgbBinaryPanel: () => import('./panels/xgb_binary.js'),
  XgbTreePanel: () => import('./panels/xgb_tree.js'),
  XgbImportancePanel: () => import('./panels/xgb_importance.js'),
};

/** Where each card's notes builders live (Details drawer). */
const NOTES_MODULES = {
  models: () => import('./models_notes.js'),
  xgb: () => import('./xgb_notes.js'),
};

const EXPORT_TITLE = 'Export this panel\'s plot as a publication figure (white background, 300 DPI, '
  + 'plot area only — see Details for its disclosures)';
const DETAILS_TITLE = 'Methodology and disclosures for this panel';

/** What the performance cards say while the segmentation network is selected. */
export const SEGMENTATION_NOTICE = 'The segmentation network has no per-shower prediction to set against a '
  + 'truth: its quality belongs to the whole event (the Physics page’s model cards). Choose the Energy or '
  + 'Angle task on this card.';

/**
 * The cards, in page order. `section` is the page section that holds the
 * card; `group` the request it shares; `notes` the module and builder of its
 * Details drawer; `table` a DOM table, not a chart (never exported).
 */
export const MODELS_CARDS = Object.freeze([
  {
    id: 'perf-bins', section: 'perf', title: 'Model Error vs. Incident Momentum', panel: 'PerfBinsPanel',
    group: 'perf', notes: ['models', 'perfBinsNotes'], exportable: true, wide: true,
  },
  {
    id: 'pred-truth', section: 'perf', title: 'Predicted vs. True', panel: 'Hist2dPanel',
    group: 'pred', notes: ['models', 'predTruthNotes'], exportable: true,
  },
  {
    id: 'pred-residuals', section: 'perf', title: 'Residuals — Predicted − True', panel: 'DistributionPanel',
    group: 'pred', notes: ['models', 'residualNotes'], exportable: true,
  },
  {
    id: 'xgb-cv', section: 'xgb', title: 'Cross-validation (5 Folds)', panel: 'XgbCvPanel',
    group: 'xgb-cv', notes: ['xgb', 'xgbCvNotes'], exportable: true,
  },
  {
    id: 'xgb-binary', section: 'xgb', title: 'Binary Thresholding at 2 GeV', panel: 'XgbBinaryPanel',
    group: 'xgb-binary', notes: ['xgb', 'xgbBinaryNotes'], exportable: true,
  },
  {
    id: 'xgb-surrogate', section: 'xgb', title: 'Depth-3 Surrogate Tree', panel: 'XgbTreePanel',
    group: 'xgb-surrogate', notes: ['xgb', 'xgbTreeNotes'], exportable: true, wide: true,
  },
  {
    id: 'xgb-importance', section: 'xgb', title: 'Gain Feature Importance', panel: 'XgbImportancePanel',
    group: 'xgb-importance', notes: ['xgb', 'xgbImportanceNotes'], exportable: true, wide: true,
  },
  {
    id: 'feat-table', section: 'features', title: 'Event Features — describe()', panel: 'FeatureTablePanel',
    group: 'feat-table', notes: ['models', 'featureTableNotes'], exportable: false, wide: true, table: true,
  },
  {
    id: 'feat-corr', section: 'features', title: 'Feature Correlations', panel: 'CorrelationPanel',
    group: 'feat-corr', notes: ['models', 'featureCorrNotes'], exportable: true,
  },
  {
    id: 'feat-hist', section: 'features', title: 'Feature Distribution by Momentum Class', panel: 'DistributionPanel',
    group: 'feat-hist', notes: ['models', 'featureHistNotes'], exportable: true,
  },
  {
    id: 'feat-hist2d', section: 'features', title: 'Feature vs. Deposited Energy by Momentum Class',
    panel: 'Hist2dPanel', group: 'feat-hist2d', notes: ['models', 'featureHist2dNotes'], exportable: true, wide: true,
  },
  {
    id: 'prim-rate', section: 'primaries', title: 'Events Without a Primary vs. Incident Momentum',
    panel: 'RatesPanel', group: 'prim', notes: ['models', 'primariesNotes'], exportable: true,
  },
]);

const SPEC = Object.fromEntries(MODELS_CARDS.map((spec) => [spec.id, spec]));

/** One abort key per shared request group: a newer request of a group supersedes the older. */
export const ABORT_KEYS = Object.freeze({
  perf: 'models-perf',
  pred: 'models-pred',
  'feat-table': 'models-feat-table',
  'feat-corr': 'models-feat-corr',
  'feat-hist': 'models-feat-hist',
  'feat-hist2d': 'models-feat-hist2d',
  prim: 'models-prim',
  'xgb-cv': 'models-xgb-cv',
  'xgb-binary': 'models-xgb-binary',
  'xgb-surrogate': 'models-xgb-surrogate',
  'xgb-importance': 'models-xgb-importance',
});

/** The `/api/features` view of each feature card. */
const FEATURE_VIEWS = { 'feat-table': 'describe', 'feat-corr': 'corr', 'feat-hist': 'hist', 'feat-hist2d': 'hist2d' };
/** The `/api/xgboost` view of each XGBoost card; the binary view has no task. */
const XGB_VIEWS = { 'xgb-cv': 'cv', 'xgb-binary': 'binary', 'xgb-surrogate': 'surrogate', 'xgb-importance': 'importance' };

/* The cards' own controls that no link carries, like the Physics page's: the
 * E2 statistic, the showers each network card draws (two-shower data reports
 * A and B separately, each with its own N), the feature table's statistic,
 * the correlation card's class and the histogram's feature axis. */
export const DEFAULT_CONTROLS = Object.freeze({
  perfStat: 'rmse',
  perfShower: 'both',
  predShower: 'both',
  resShower: 'both',
  tableStat: 'median',
  corrClass: 'pooled',
  histScale: 'auto',
});

/** The page's share of the State a card reads (`viewOf`), with its built-in values. */
const VIEW_DEFAULTS = Object.freeze({
  frame: 'lab', model: 'segmentation', feature: 'num_hits', fclass: 'windows', fshower: 'a',
  xgb_task: 'momentum', xgb_label: 'theta',
});

/** The State keys a card's request or picture reads. */
export function viewOf(state) {
  const get = (key) => (typeof state?.get === 'function' ? state.get(key) : state?.[key]);
  const view = {};
  for (const [key, fallback] of Object.entries(VIEW_DEFAULTS)) view[key] = get(key) ?? fallback;
  return view;
}

/**
 * The task of the performance cards, as the API's `model`: 'energy' or
 * 'angle', or null while the segmentation network is selected. A networked
 * experiment reads the shared `model` key; an aggregate whose XGBoost
 * regressor stands in reads `xgb_task` (its momentum model answers `energy`).
 * Pure.
 */
export function perfTask(plan, view) {
  if (plan?.networks) return view.model === 'energy' || view.model === 'angle' ? view.model : null;
  if (plan?.xgb?.tasks?.length) return view.xgb_task === 'angle' ? 'angle' : 'energy';
  return null;
}

/** Whether the prediction cards draw one output of the XGBoost angle model (`label`). */
export function predLabelApplies(plan, view) {
  return !plan?.networks && Boolean(plan?.xgb?.tasks?.length) && perfTask(plan, view) === 'angle';
}

/** The feature a histogram card draws: the selected one, else the first the experiment offers. Never written back. */
export function featureOf(plan, view) {
  const offered = featureChoices(plan?.hasHits ?? true).map((f) => f.key);
  return offered.includes(view.feature) ? view.feature : (offered.includes('num_hits') ? 'num_hits' : offered[0]);
}

/**
 * Whose features the explorer's cards draw: the selected shower (`fshower`)
 * on two-shower data, where each shower's features are its own and never
 * pooled; null on one-shower data, which has only shower A (the server's
 * default) and refuses B. Never written back.
 */
export function featureShower(plan, view) {
  if ((plan?.nShowers ?? 2) !== 2) return null;
  return view.fshower === 'b' ? 'b' : 'a';
}

/**
 * The frame the feature cards are served in for the selected frame
 * (capabilities.js `viewFrame`). A hit experiment offers the frames of its
 * sidebar; an event-level aggregate, which has none, the frames its feature
 * columns were computed in (`plan.featureFrames`: abs, trn, loc), chosen on
 * the feature cards. Pure.
 */
export function featureFrame(plan, view) {
  if (!plan?.hasHits) {
    const frames = plan?.featureFrames ?? [];
    if (!frames.length) return { frame: null, fallback: false, note: null };
    return viewFrame('features', view.frame, frames, plan?.nShowers ?? 1);
  }
  return viewFrame('features', view.frame, plan?.frames?.offered ?? [], plan?.nShowers ?? 2);
}

/** Whether the feature cards carry their own frame control: an aggregate's, with no sidebar frame. */
export function featureFrameApplies(plan) {
  return Boolean(plan) && !plan.hasHits && (plan.featureFrames?.length ?? 0) > 0;
}

/** Whether the performance cards draw an aggregate's XGBoost regressors rather than networks. */
function xgbStandsIn(plan) {
  return Boolean(plan) && !plan.networks && Boolean(plan.xgb?.tasks?.length);
}

const STAT_CHOICES = [
  { value: 'rmse', label: 'RMSE', title: 'Root-mean-square error, with its χ² interval under normal residuals below N = 20 and its seeded bootstrap interval from N = 20' },
  { value: 'mae', label: 'MAE', title: 'Mean absolute error, with its Student-t interval' },
  { value: 'median_rel', label: 'Median rel.', title: 'Median relative error, with its order-statistic or bootstrap interval' },
  { value: 'bias', label: 'Bias', title: 'Mean signed residual, with its Student-t interval' },
];

const SHOWER_CHOICES = [
  { value: 'a', label: 'A', title: 'Shower A only' },
  { value: 'b', label: 'B', title: 'Shower B only' },
  { value: 'both', label: 'Both', title: 'Showers A and B, each with its own N' },
];

const TABLE_STAT_CHOICES = [
  { value: 'median', label: 'Median [IQR]', title: 'Each cell: the median and the interquartile range' },
  { value: 'mean', label: 'Mean ± SD', title: 'Each cell: the mean and the sample standard deviation' },
  { value: 'range', label: 'Min … max', title: 'Each cell: the smallest and largest value' },
];

const SCALE_CHOICES = [
  { value: 'auto', label: 'Auto', title: 'The server’s choice: logarithmic for a positive feature spanning a decade or more' },
  { value: 'linear', label: 'Linear', title: 'A linear feature axis' },
  { value: 'log', label: 'Log x', title: 'A logarithmic feature axis' },
];

/* The controls, shared by the cards that carry them. `stateKey` writes the
 * shared State (a link restores it); otherwise the value is the section's
 * own (`DEFAULT_CONTROLS`). `request: true` changes the card's request (a
 * reload); otherwise the control repaints the payload in hand. `write`
 * overrides the patch a choice makes; `choiceDisabled` gives the reason one
 * choice is off. Each function takes `{plan, view, controls, payload}`. */
const TASK_CONTROL = {
  name: 'perfTask', kind: 'seg', attr: 'modelsTask', label: 'Task', request: true,
  // An aggregate's XGBoost regressor predicts momentum, and its button says so.
  choices: ({ plan }) => (xgbStandsIn(plan) ? MODELS_LABELS.xgb_perf_task : MODELS_LABELS.task),
  get: ({ plan, view }) => perfTask(plan, view),
  write: ({ plan }, value) => (plan?.networks ? { model: value } : { xgb_task: value === 'angle' ? 'angle' : 'momentum' }),
  visible: ({ plan }) => Boolean(plan?.networks || plan?.xgb?.tasks?.length),
  choiceDisabled: ({ plan }, value) => {
    if (plan?.networks) return plan.models.includes(value) ? null : 'This network is not in the experiment.';
    const task = value === 'angle' ? 'angle' : 'momentum';
    return plan?.xgb?.tasks?.includes(task) ? null : 'No XGBoost model of this task pairs with the experiment.';
  },
};

const STAT_CONTROL = {
  name: 'perfStat', kind: 'seg', attr: 'perfStatistic', label: 'Statistic',
  choices: () => STAT_CHOICES,
  choiceDisabled: ({ payload }, value) => {
    const quantities = payload?.by_momentum_bin?.quantities ?? payload?.stats ?? null;
    if (!quantities || value in quantities) return null;
    return 'Not reported for this task: a relative error of an azimuth means nothing.';
  },
};

const PRED_LABEL_CONTROL = {
  name: 'xgbLabel', kind: 'seg', attr: 'xgbLabel', label: 'Output', stateKey: 'xgb_label', request: true,
  choices: () => MODELS_LABELS.xgb_label,
  visible: ({ plan, view }) => predLabelApplies(plan, view),
};

const XGB_TASK_CONTROL = {
  name: 'xgbTask', kind: 'seg', attr: 'xgbTask', label: 'Task', stateKey: 'xgb_task', request: true,
  choices: () => MODELS_LABELS.xgb_task,
  choiceDisabled: ({ plan }, value) => (plan?.xgb?.tasks?.includes(value)
    ? null : 'No XGBoost model of this task pairs with the experiment.'),
};

const TREE_LABEL_CONTROL = {
  name: 'xgbLabel', kind: 'seg', attr: 'xgbLabel', label: 'Output', stateKey: 'xgb_label',
  choices: () => MODELS_LABELS.xgb_label,
  visible: ({ view }) => view.xgb_task === 'angle',
};

const CLASS_CONTROL = {
  name: 'fclass', kind: 'select', attr: 'featureClasses', label: 'Momentum classes', stateKey: 'fclass', request: true,
  choices: () => MODELS_LABELS.fclass,
};

/* Whose features, on two-shower data: the shared `fshower` key, so every
 * feature card and a link agree. */
const FEATURE_SHOWER_CONTROL = {
  name: 'fshower', kind: 'seg', attr: 'featureShower', label: 'Shower', stateKey: 'fshower', request: true,
  choices: () => MODELS_LABELS.fshower,
  get: ({ plan, view }) => featureShower(plan, view) ?? 'a',
  visible: ({ plan }) => (plan?.nShowers ?? 2) === 2,
};

/* The frame of an aggregate's features: the shared `frame` key, written only
 * with the three frames its columns hold, so the D-frame is never offered. */
const FEATURE_FRAME_CONTROL = {
  name: 'featureFrame', kind: 'seg', attr: 'featureFrame', label: 'Frame', stateKey: 'frame', request: true,
  choices: () => MODELS_LABELS.feature_frame,
  get: ({ plan, view }) => featureFrame(plan, view).frame ?? 'lab',
  visible: ({ plan }) => featureFrameApplies(plan),
  choiceDisabled: ({ plan }, value) => ((plan?.featureFrames ?? []).includes(value)
    ? null : 'The features are not served in this frame for this experiment.'),
};

const FEATURE_CONTROL = {
  name: 'feature', kind: 'select', attr: 'featureId', label: 'Feature', stateKey: 'feature', request: true,
  choices: ({ plan }) => featureChoices(plan?.hasHits ?? true).map((f) => ({ value: f.key, label: f.label })),
  get: ({ plan, view }) => featureOf(plan, view),
};

const CORR_CLASS_CONTROL = {
  name: 'corrClass', kind: 'select', attr: 'featureClass', label: 'Class', request: true,
  // The classes of the response in hand, when it holds this classing.
  choices: ({ view, payload }) => [
    { value: 'pooled', label: 'All classes pooled' },
    ...(payload?.class_mode === view.fclass && Array.isArray(payload?.classes)
      ? payload.classes.map((c) => ({ value: String(c.index), label: `${c.label} (N = ${c.n})` })) : []),
  ],
};

const SCALE_CONTROL = {
  name: 'histScale', kind: 'seg', attr: 'featureScale', label: 'Feature axis', request: true,
  choices: () => SCALE_CHOICES,
  choiceDisabled: ({ plan, view }, value) => {
    if (value !== 'log') return null;
    const feature = featureChoices(plan?.hasHits ?? true).find((f) => f.key === featureOf(plan, view));
    return feature && !feature.log
      ? 'Not offered for this feature: an azimuth is drawn on (−π, π] and a lattice-quantised feature on a linear axis.'
      : null;
  },
};

/** A render-only A / B / Both control of one card, shown on two-shower data. */
function showerControl(name) {
  return {
    name, kind: 'seg', attr: 'modelsShower', label: 'Showers',
    choices: () => SHOWER_CHOICES,
    visible: ({ plan }) => (plan?.nShowers ?? 2) === 2,
  };
}

const TABLE_STAT_CONTROL = {
  name: 'tableStat', kind: 'seg', attr: 'featureStat', label: 'Cell statistic',
  choices: () => TABLE_STAT_CHOICES,
};

const CARD_CONTROLS = {
  'perf-bins': [TASK_CONTROL, STAT_CONTROL, showerControl('perfShower')],
  'pred-truth': [TASK_CONTROL, PRED_LABEL_CONTROL, showerControl('predShower')],
  'pred-residuals': [showerControl('resShower')],
  'xgb-cv': [XGB_TASK_CONTROL],
  'xgb-surrogate': [XGB_TASK_CONTROL, TREE_LABEL_CONTROL],
  'xgb-importance': [XGB_TASK_CONTROL],
  'feat-table': [FEATURE_FRAME_CONTROL, FEATURE_SHOWER_CONTROL, CLASS_CONTROL, TABLE_STAT_CONTROL],
  'feat-corr': [FEATURE_FRAME_CONTROL, FEATURE_SHOWER_CONTROL, CLASS_CONTROL, CORR_CLASS_CONTROL],
  'feat-hist': [FEATURE_FRAME_CONTROL, FEATURE_SHOWER_CONTROL, FEATURE_CONTROL, CLASS_CONTROL, SCALE_CONTROL],
  'feat-hist2d': [FEATURE_FRAME_CONTROL, FEATURE_SHOWER_CONTROL, FEATURE_CONTROL, CLASS_CONTROL],
};

/** The control specs of one card. */
export function cardControls(id) {
  return CARD_CONTROLS[id] ?? [];
}

/** The current value of one control. */
function controlValue(control, ctx) {
  if (typeof control.get === 'function') return control.get(ctx);
  if (control.stateKey) return ctx.view[control.stateKey];
  return ctx.controls[control.name];
}

/**
 * The request of one card: `{route, params, abortKey}`, or null when the card
 * does not load in this view. `filters` is `State.filterParams()`, `view` the
 * State's page keys (`viewOf`). Pure.
 */
export function cardRequest(id, { filters, view = VIEW_DEFAULTS, controls = DEFAULT_CONTROLS, plan = null }) {
  const spec = SPEC[id];
  if (!spec || !filters?.table_name) return null;
  const c = { ...DEFAULT_CONTROLS, ...controls };
  const v = { ...VIEW_DEFAULTS, ...view };
  const abortKey = ABORT_KEYS[spec.group];
  switch (spec.group) {
    case 'perf': {
      const task = perfTask(plan, v);
      if (!task) return null;
      // The breakdown covers every network frame at once (by_momentum_bin),
      // so the frame does not enter the request.
      return { route: '/api/model-performance', abortKey, params: { ...filters, slice_by: 'momentum_bin', model: task } };
    }
    case 'pred': {
      const task = perfTask(plan, v);
      if (!task) return null;
      const params = { ...filters, model: task };
      if (plan?.networks) params.coord_system = viewFrame('network', v.frame).frame;
      if (predLabelApplies(plan, v)) params.label = v.xgb_label;
      return { route: '/api/prediction-density', abortKey, params };
    }
    case 'feat-table':
    case 'feat-corr':
    case 'feat-hist':
    case 'feat-hist2d': {
      const params = { ...filters, view: FEATURE_VIEWS[id], classes: v.fclass };
      const frame = featureFrame(plan, v).frame;
      if (frame) params.coord_system = frame;
      // Every feature card asks for the same shower; one-shower data sends none (its only shower).
      const shower = featureShower(plan, v);
      if (shower) params.shower = shower;
      if (id === 'feat-corr') params.class_index = c.corrClass;
      if (id === 'feat-hist' || id === 'feat-hist2d') params.feature = featureOf(plan, v);
      if (id === 'feat-hist' && c.histScale !== 'auto') params.scale = c.histScale;
      return { route: '/api/features', abortKey, params };
    }
    case 'prim':
      return { route: '/api/primaries', abortKey, params: { ...filters } };
    case 'xgb-cv':
    case 'xgb-binary':
    case 'xgb-surrogate':
    case 'xgb-importance': {
      // Computed once on the whole experiment, as the notebook does: the
      // selection does not apply, so only the experiment is sent.
      const params = { table_name: filters.table_name, view: XGB_VIEWS[id] };
      if (id !== 'xgb-binary') params.task = v.xgb_task;
      return { route: '/api/xgboost', abortKey, params };
    }
    default:
      return null;
  }
}

/**
 * Why a card on show draws nothing in this view, or null: the performance
 * cards while the segmentation network is selected. Pure.
 */
export function cardNotice(id, { view = VIEW_DEFAULTS, plan = null } = {}) {
  const spec = SPEC[id];
  if (!spec || (spec.group !== 'perf' && spec.group !== 'pred')) return null;
  return perfTask(plan, { ...VIEW_DEFAULTS, ...view }) ? null : SEGMENTATION_NOTICE;
}

/** The sentence a card states under its title when it draws in another frame than the one selected. */
export function cardCaption(id, { view = VIEW_DEFAULTS, plan = null } = {}) {
  const spec = SPEC[id];
  if (!spec || spec.section !== 'features') return null;
  return featureFrame(plan, { ...VIEW_DEFAULTS, ...view }).note;
}

/**
 * What a card's panel is rendered with (the fixed interface): `palette`,
 * `card`, and per card `task`, `label`, `quantity` (the E2 statistic),
 * `classes`, `frame` (the feature cards' served frame) and `feature`; and the
 * options the panels read beside them: `shower` (A, B or both, on two-shower
 * data), the feature table's `stat` and the correlation card's `fadeNull`.
 * Pure.
 */
export function cardOptions(id, { view = VIEW_DEFAULTS, controls = DEFAULT_CONTROLS, plan = null, palette = 'viridis' } = {}) {
  const spec = SPEC[id];
  const opts = { palette, card: id };
  if (!spec) return opts;
  const v = { ...VIEW_DEFAULTS, ...view };
  const c = { ...DEFAULT_CONTROLS, ...controls };
  const two = (plan?.nShowers ?? 2) === 2;
  if (spec.group === 'perf') {
    opts.task = perfTask(plan, v);
    opts.quantity = c.perfStat;
    opts.shower = two ? c.perfShower : 'both';
  } else if (spec.group === 'pred') {
    opts.task = perfTask(plan, v);
    if (predLabelApplies(plan, v)) opts.label = v.xgb_label;
    opts.shower = two ? (id === 'pred-truth' ? c.predShower : c.resShower) : 'both';
  } else if (spec.section === 'features') {
    opts.classes = v.fclass;
    opts.frame = featureFrame(plan, v).frame;
    if (id === 'feat-table') opts.stat = c.tableStat;
    // D-10: a correlation whose 95% interval contains zero is faded (the Physics page's C8 is not).
    if (id === 'feat-corr') opts.fadeNull = true;
    if (id === 'feat-hist' || id === 'feat-hist2d') opts.feature = featureOf(plan, v);
  } else if (spec.section === 'xgb') {
    if (id !== 'xgb-binary') opts.task = v.xgb_task;
    if (id === 'xgb-surrogate' && v.xgb_task === 'angle') opts.label = v.xgb_label;
  }
  return opts;
}

/** What an exported figure is named by: its response's meta and frame. */
export function exportMeta(payload) {
  const meta = { ...(payload?.meta ?? {}) };
  const coord = meta.coord_system ?? payload?.coord_system;
  if (coord) meta.coord_system = coord;
  return meta;
}

/** Plain notes from the payload's own lines, when the card's notes module failed to load. */
function fallbackNotes(title, payload) {
  const raw = payload?.notes;
  const notes = Array.isArray(raw) ? raw : (raw && typeof raw === 'object' ? Object.values(raw) : []);
  const lines = [...notes, ...(payload?.meta?.warnings ?? [])].filter((l) => typeof l === 'string' && l);
  return {
    title,
    hazards: [],
    sections: lines.length ? [{ heading: SECTION.drawn, lines }] : [],
  };
}

/** The drawer of a card that draws nothing: the reason, nothing else. */
function shutNotes(title, reason) {
  return { title, hazards: [], sections: [{ heading: SECTION.disclosures, lines: [reason] }] };
}

/**
 * A panel class by name: an injected one, else its module's export. A module
 * that fails to load rejects as the import did (a transient failure, retried);
 * a module without the class is a release fault, said in plain words.
 */
export async function loadPanelClass(name, injected = null, modules = PANEL_MODULES) {
  if (injected && typeof injected[name] === 'function') return injected[name];
  const load = modules?.[name] ?? PANEL_MODULES[name];
  if (typeof load !== 'function') throw new Error(`No panel module is registered for ${name}.`);
  const module = await load();
  const Class = module?.[name];
  if (typeof Class !== 'function') throw new Error(`The panel module does not export ${name}; reload the page.`);
  return Class;
}

/** How many responses the section keeps for cards scrolled to later. */
const CACHE_SIZE = 24;

export class ModelsSection {
  /**
   * @param {object} hosts  the page sections, by key: `{perf, xgb, features, primaries}`
   * @param {object} options
   *   `state` the interface State; `getExperiment()` the active experiment;
   *   `onRendered(id, payload|null)` after a card drew (or failed), so the
   *   page can rebuild its notes; `onError(error, context)` for a load the
   *   observer started; `onStateChange(patch)` after a card control wrote the
   *   shared State; `onOpenAdmin()` for a shut card's rebuild offer; `root`
   *   the scroll container; `panelClasses` / `notesModules` override the
   *   panel classes and notes builders, and `panelModules` a panel module's
   *   loader (tests).
   */
  constructor(hosts, {
    state, getExperiment = () => null, onRendered = () => {}, onError = () => {}, onStateChange = () => {},
    onOpenAdmin = null, root = null, panelClasses = null, notesModules = null, panelModules = null,
  } = {}) {
    this.hosts = hosts ?? {};
    this.state = state;
    this.getExperiment = getExperiment;
    this.onRendered = onRendered;
    this.onError = onError;
    this.onStateChange = onStateChange;
    this.onOpenAdmin = onOpenAdmin;
    this.panelClasses = panelClasses;
    this.panelModules = panelModules ? { ...PANEL_MODULES, ...panelModules } : PANEL_MODULES;
    this.notesModules = notesModules ? { ...notesModules } : {};
    this.notesPending = {};
    this.plan = null;
    this.controls = { ...DEFAULT_CONTROLS };
    this.cards = new Map();
    this.cache = new Map();
    this.inflight = new Map();
    // Bumped by `reset()` and `invalidate()`: a response that lands after
    // either belongs to what was forgotten and is not cached.
    this.generation = 0;
    this.lazy = new LazyCards({
      root,
      // In view means in view: the plan's decision D3 (Martin).
      rootMargin: '0px',
      onError: (error, element) => this.onError(error, this.titleOf(element)),
    });
    for (const spec of MODELS_CARDS) {
      const host = this.hosts[spec.section];
      if (host) this.buildCard(host, spec);
    }
  }

  /* ------------------------------------------------------------- markup */

  buildCard(host, spec) {
    const { id } = spec;
    const card = document.createElement('div');
    card.className = `card models-card${spec.wide ? ' is-wide' : ''}`;
    card.dataset.panel = id;
    card.hidden = true;

    const heading = document.createElement('h2');
    const title = document.createElement('span');
    title.className = 'title';
    title.id = `title-${id}`;
    title.title = 'Open the panel\'s methodology and disclosures';
    title.textContent = spec.title;
    const actions = document.createElement('span');
    actions.className = 'card-actions';

    const details = document.createElement('button');
    details.type = 'button';
    details.className = 'mini';
    details.dataset.inspect = id;
    details.setAttribute('aria-controls', 'inspector');
    details.setAttribute('aria-expanded', 'false');
    details.title = DETAILS_TITLE;
    details.textContent = 'Details';
    actions.append(details);

    const controls = {};
    for (const control of cardControls(id)) {
      const built = this.buildControl(id, control);
      controls[control.name] = built;
      actions.append(built.element);
    }

    let exporter = null;
    if (spec.exportable) {
      exporter = document.createElement('button');
      exporter.type = 'button';
      exporter.className = 'mini';
      exporter.dataset.export = id;
      exporter.setAttribute('aria-haspopup', 'menu');
      exporter.title = EXPORT_TITLE;
      exporter.append('Export ', document.createTextNode('▾'));
      actions.append(exporter);
    }
    heading.append(title, actions);

    // The frame a card draws in when it is not the selected one.
    const caption = document.createElement('div');
    caption.className = 'card-caption';
    caption.hidden = true;

    const frame = document.createElement('div');
    frame.className = 'plot-frame';
    const plot = document.createElement('div');
    plot.className = spec.table ? 'card-table' : 'plot';
    plot.id = `plot-${id}`;
    const message = document.createElement('div');
    message.className = 'card-error';
    message.setAttribute('role', 'status');
    message.hidden = true;
    frame.append(plot, message);
    card.append(heading, caption, frame);
    host.append(card);

    const record = {
      spec, element: card, title, details, caption, plot, message, exporter, controls,
      panel: null, panelPromise: null, payload: null, opts: null, disabled: null, notice: null,
      error: null, loading: null,
    };
    this.cards.set(id, record);
    this.lazy.watch(card, {
      key: () => this.keyOf(id),
      load: (key) => this.loadCard(record, key),
    });
    return record;
  }

  /** One toolbar control: a segmented group of buttons, or a select. */
  buildControl(id, control) {
    if (control.kind === 'select') {
      const select = document.createElement('select');
      select.className = 'mini-select';
      select.dataset[control.attr] = id;
      select.setAttribute('aria-label', control.label);
      select.title = control.label;
      select.addEventListener('change', () => this.setControl(control, select.value));
      return { element: select, select, control };
    }
    const group = document.createElement('span');
    group.className = 'seg';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', control.label);
    const buttons = new Map();
    for (const choice of control.choices(this.ctx(null))) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mini';
      button.dataset[control.attr] = choice.value;
      button.textContent = choice.label;
      if (choice.title) button.title = choice.title;
      button.addEventListener('click', () => this.setControl(control, choice.value));
      buttons.set(choice.value, { button, title: choice.title ?? '' });
      group.append(button);
    }
    return { element: group, buttons, control };
  }

  /** What the control functions read, for one card's payload. */
  ctx(record) {
    return {
      plan: this.plan,
      view: viewOf(this.state),
      controls: this.controls,
      payload: record?.payload ?? null,
    };
  }

  /** Reflect the controls' values, visibility and availability, and each card's notice and caption. */
  syncControls() {
    for (const record of this.cards.values()) {
      const ctx = this.ctx(record);
      for (const built of Object.values(record.controls)) {
        const { control, element } = built;
        const value = controlValue(control, ctx);
        // A shut card has nothing to steer: its controls go with its picture.
        element.hidden = Boolean(record.disabled) || (control.visible ? !control.visible(ctx) : false);
        if (built.select) {
          const choices = control.choices(ctx);
          const current = [...built.select.options].map((o) => `${o.value}=${o.textContent}`).join('|');
          if (current !== choices.map((c) => `${c.value}=${c.label}`).join('|')) {
            built.select.replaceChildren(...choices.map((choice) => {
              const option = document.createElement('option');
              option.value = choice.value;
              option.textContent = choice.label;
              return option;
            }));
          }
          built.select.value = String(value);
          built.select.disabled = choices.length < 2;
        } else {
          const labelled = new Map(control.choices(ctx).map((c) => [c.value, c]));
          for (const [choice, entry] of built.buttons) {
            const named = labelled.get(choice);
            if (named) {
              if (entry.button.textContent !== named.label) entry.button.textContent = named.label;
              entry.title = named.title ?? '';
            }
            const { button, title } = entry;
            const reason = control.choiceDisabled ? control.choiceDisabled(ctx, choice) : null;
            button.classList.toggle('is-active', choice === value);
            button.setAttribute('aria-pressed', String(choice === value));
            button.disabled = Boolean(reason);
            button.title = reason ?? title;
          }
        }
      }
      if (record.exporter) record.exporter.disabled = Boolean(record.disabled);
      this.syncCaption(record);
    }
  }

  /** The card's frame caption, and its notice when it draws nothing in this view. */
  syncCaption(record) {
    const view = viewOf(this.state);
    const shown = !record.element.hidden && !record.disabled;
    const caption = shown ? cardCaption(record.spec.id, { view, plan: this.plan }) : null;
    record.caption.textContent = caption ?? '';
    record.caption.hidden = !caption;
    const notice = shown ? cardNotice(record.spec.id, { view, plan: this.plan }) : null;
    if (notice !== record.notice) {
      record.notice = notice;
      if (notice) {
        this.blank(record);
        this.showMessage(record, notice, { kind: 'notice' });
      } else if (record.message.dataset.kind === 'notice') {
        this.hideMessage(record);
      }
    }
  }

  /* ------------------------------------------------------------- plan */

  /**
   * Show the cards of a plan (capabilities.js `page2Plan`): the applicable
   * ones, each shut card with the server's reason. Every card goes stale; the
   * visible ones load on the caller's next `refresh()`, the others when they
   * scroll into view.
   */
  applyPlan(plan) {
    this.plan = plan;
    // The correlation card's class belongs to the classing in hand.
    this.controls = { ...this.controls, corrClass: 'pooled' };
    for (const [id, record] of this.cards) {
      const card = plan?.cards?.[id] ?? { shown: false, enabled: false, reason: null };
      record.element.hidden = !card.shown;
      record.disabled = card.shown && !card.enabled ? (card.reason ?? 'Not available for this experiment.') : null;
      record.notice = null;
      if (record.disabled) {
        this.blank(record);
        // The rebuild is offered where it is the reason.
        const stale = Boolean(plan.stale?.notice) && plan.stale.notice === record.disabled;
        this.showMessage(record, record.disabled, { offerRebuild: stale, kind: 'disabled' });
      } else if (record.message.dataset.kind === 'disabled' || record.message.dataset.kind === 'notice') {
        this.hideMessage(record);
      }
    }
    this.syncControls();
    this.lazy.forget();
  }

  /** Every card id of the section (whether or not on show). */
  ids() {
    return [...this.cards.keys()];
  }

  /** Whether `id` is one of this section's cards. */
  has(id) {
    return this.cards.has(id);
  }

  /** The request of one card now, or null when it does not load. */
  requestOf(id) {
    const record = this.cards.get(id);
    if (!record || !this.plan || record.element.hidden || record.disabled) return null;
    return cardRequest(id, {
      filters: this.state.filterParams(), view: viewOf(this.state), controls: this.controls, plan: this.plan,
    });
  }

  /** The request key of one card now, or null when it does not load. */
  keyOf(id) {
    const request = this.requestOf(id);
    return request ? requestKey(request.route, request.params) : null;
  }

  /* ------------------------------------------------------------ loading */

  /**
   * Change one control. A State control writes the shared State and tells
   * the page (the sidebar and the 3-D views may read the key too); a section
   * control changes this section alone. Request controls reload their cards,
   * the others repaint.
   */
  setControl(control, value) {
    const ctx = this.ctx(null);
    if (controlValue(control, ctx) === value) return;
    if (control.choiceDisabled && control.choiceDisabled(ctx, value)) return;
    if (control.write || control.stateKey) {
      const patch = control.write ? control.write(ctx, value) : { [control.stateKey]: value };
      // A new classing has other classes: the correlation card goes back to the pool.
      if ('fclass' in patch) this.controls = { ...this.controls, corrClass: 'pooled' };
      this.state.set(patch);
      this.onStateChange(patch);
    } else {
      this.controls = { ...this.controls, [control.name]: value };
    }
    this.syncControls();
    // Cards whose request changed reload; the others that read the control repaint.
    this.refreshVisible();
    for (const record of this.cards.values()) {
      if (!cardControls(record.spec.id).some((c) => c.name === control.name)) continue;
      if (this.lazy.isCurrent(record.element)) this.paint(record);
    }
  }

  /** The title of the card an element belongs to, for an error's context. */
  titleOf(element) {
    const record = [...this.cards.values()].find((r) => r.element === element);
    return record ? record.spec.title : 'models card';
  }

  /** Load the visible stale cards after a control changed, reporting failures one by one. */
  refreshVisible() {
    this.lazy.refresh().then((results) => {
      for (const result of results) {
        if (result.status === 'rejected' && !isAbort(result.reason)) {
          this.onError(result.reason, this.titleOf(result.element));
        }
      }
    });
  }

  /**
   * The page's State changed outside this section (the sidebar's network or
   * frame): bring the controls, captions and notices into line. The caller
   * refreshes.
   */
  sync() {
    this.syncControls();
  }

  /**
   * Load every visible card whose request changed. Rejects with one error
   * naming each card that failed (each also says so on itself); a superseded
   * request is not a failure of the page.
   */
  async refresh() {
    if (!this.plan) return [];
    this.syncControls();
    const results = await this.lazy.refresh();
    const failures = results
      .filter((result) => result.status === 'rejected' && !isAbort(result.reason))
      .map((result) => `${this.titleOf(result.element)}: ${describeError(result.reason)}`);
    if (failures.length) throw new Error(failures.join('; '));
    return results;
  }

  /** The card's panel, created on first use. */
  async ensurePanel(record) {
    if (record.panel) return record.panel;
    if (!record.panelPromise) {
      record.panelPromise = (async () => {
        const Class = await loadPanelClass(record.spec.panel, this.panelClasses, this.panelModules);
        const panel = new Class(record.plot, { card: record.spec.id });
        record.panel = panel;
        return panel;
      })();
      // A failed import may succeed later (a transient network fault).
      record.panelPromise.catch(() => { record.panelPromise = null; });
    }
    return record.panelPromise;
  }

  /** A card's notes module, fetched on first use; null when it is missing. */
  async ensureNotes(record) {
    const [name] = record.spec.notes;
    if (name in this.notesModules) return this.notesModules[name];
    if (!this.notesPending[name]) {
      const load = NOTES_MODULES[name];
      this.notesPending[name] = (typeof load === 'function' ? load() : Promise.resolve(null))
        .then((module) => module ?? null, () => null)
        .then((module) => {
          this.notesModules[name] = module;
          delete this.notesPending[name];
          return module;
        });
    }
    return this.notesPending[name];
  }

  async loadCard(record, key) {
    const request = this.requestOf(record.spec.id);
    if (!request || requestKey(request.route, request.params) !== key) return;
    // The load in charge of the card's busy state: one superseded by a newer
    // load (or forgotten by `reset`) leaves the newer one's state alone.
    const loading = {};
    record.loading = loading;
    this.setCardBusy(record, true);
    try {
      const [panel, payload] = await Promise.all([
        this.ensurePanel(record),
        this.fetchShared(request),
        this.ensureNotes(record),
      ]);
      // A newer request, or another experiment, may have taken the card over.
      if (this.keyOf(record.spec.id) !== key) return;
      record.payload = payload;
      record.error = null;
      this.hideMessage(record);
      this.draw(record, panel, payload);
      this.onRendered(record.spec.id, payload);
    } catch (error) {
      if (isAbort(error)) throw error;
      if (this.keyOf(record.spec.id) === key) {
        record.payload = null;
        record.error = describeError(error);
        this.blank(record);
        // A refusal is the server's answer to this request; anything else
        // (a failed panel import included) may pass, and the card is asked
        // again on its next visibility, the next refresh, or now.
        this.showMessage(record, record.error, { offerRetry: !isRefusal(error), kind: 'error' });
        this.onRendered(record.spec.id, null);
      }
      throw error;
    } finally {
      if (record.loading === loading) {
        record.loading = null;
        this.setCardBusy(record, false);
      }
    }
  }

  /** One response per key: joined while in flight, kept for a card scrolled to later. */
  fetchShared({ route, params, abortKey }) {
    const key = requestKey(route, params);
    if (this.cache.has(key)) {
      const payload = this.cache.get(key);
      this.cache.delete(key);
      this.cache.set(key, payload);
      return Promise.resolve(payload);
    }
    const pending = this.inflight.get(key);
    if (pending) return pending;
    const promise = getJson(route, params, abortKey);
    this.inflight.set(key, promise);
    const generation = this.generation;
    promise.then((payload) => {
      // A response that lands after a reset belongs to what was forgotten.
      if (generation !== this.generation) return;
      this.cache.set(key, payload);
      while (this.cache.size > CACHE_SIZE) this.cache.delete(this.cache.keys().next().value);
    }, () => {}).finally(() => {
      if (this.inflight.get(key) === promise) this.inflight.delete(key);
    });
    return promise;
  }

  /** Draw a payload on its card's panel with the card's current options. */
  draw(record, panel, payload) {
    record.opts = cardOptions(record.spec.id, {
      view: viewOf(this.state), controls: this.controls, plan: this.plan, palette: this.state.get('palette'),
    });
    panel.render(payload, record.opts);
    // Controls whose choices come from the response (the correlation card's classes).
    this.syncControls();
  }

  /** Redraw one card from the payload in hand (a palette or a render-only control). */
  paint(record) {
    if (!record.panel || !record.payload || record.element.hidden || record.disabled || record.notice) return;
    this.draw(record, record.panel, record.payload);
    this.onRendered(record.spec.id, record.payload);
  }

  /** Every drawn card again, with the current palette; no request. */
  repaint() {
    for (const record of this.cards.values()) this.paint(record);
  }

  /** Re-lay every created chart out at its container's size. */
  relayout() {
    for (const record of this.cards.values()) {
      if (record.panel && !record.element.hidden) record.panel.relayout?.();
    }
  }

  setCardBusy(record, busy) {
    record.element.classList.toggle('is-loading', busy);
    record.panel?.setBusy?.(busy);
  }

  /** Take a card's picture down: a failed or shut card keeps no stale picture. */
  blank(record) {
    record.payload = null;
    record.opts = null;
    record.panel?.clear?.();
  }

  /**
   * Say on the card why it shows nothing: a load that failed, a gate the
   * server shut, or a view the card does not apply in.
   * A card shut for want of a derived-table rebuild offers Admin Settings.
   */
  showMessage(record, text, { offerRebuild = false, offerRetry = false, kind = 'error' } = {}) {
    const line = document.createElement('p');
    line.textContent = text;
    const nodes = [line];
    if (offerRetry) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'action';
      button.dataset.retry = record.spec.id;
      button.textContent = 'Retry';
      button.title = 'Ask the server again for this card';
      button.addEventListener('click', () => {
        this.lazy.invalidate(record.element);
        this.refreshVisible();
      });
      nodes.push(button);
    }
    if (offerRebuild && typeof this.onOpenAdmin === 'function') {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'action';
      button.dataset.openAdmin = record.spec.id;
      button.textContent = 'Rebuild derived tables…';
      button.title = 'Open Admin Settings on the Physics page, where an experiment\'s derived tables are rebuilt '
        + 'from its archive';
      button.addEventListener('click', () => this.onOpenAdmin());
      nodes.push(button);
    }
    record.message.replaceChildren(...nodes);
    record.message.dataset.kind = kind;
    record.message.hidden = false;
  }

  hideMessage(record) {
    record.message.hidden = true;
    record.message.replaceChildren();
    delete record.message.dataset.kind;
  }

  /**
   * Forget everything this experiment showed: abort the requests in flight,
   * drop the cached responses, blank every card. The next refresh (or scroll)
   * loads afresh, and a response of the previous experiment never draws.
   */
  reset() {
    for (const key of Object.values(ABORT_KEYS)) abortRequest(key);
    this.generation += 1;
    this.cache.clear();
    this.inflight.clear();
    for (const record of this.cards.values()) {
      this.blank(record);
      record.error = null;
      // No load of the previous experiment holds the card busy any more.
      record.loading = null;
      this.setCardBusy(record, false);
      if (!record.disabled && !record.notice) this.hideMessage(record);
    }
    this.lazy.forget();
  }

  /** Drop cached responses without blanking: the same experiment, reactivated. */
  invalidate() {
    this.generation += 1;
    this.cache.clear();
    this.inflight.clear();
    this.lazy.forget();
  }

  /** The response a card holds now, or null. */
  payloadOf(id) {
    return this.cards.get(id)?.payload ?? null;
  }

  /* ------------------------------------------------------ drawer, export */

  /**
   * The drawer's notes of one card: its builder's, by name from its notes
   * module (models_notes.js, xgb_notes.js), else the payload's own lines; a
   * card that draws nothing states why.
   */
  notes(id, { state = this.state, experiment = this.getExperiment() } = {}) {
    const record = this.cards.get(id);
    if (!record) return null;
    const title = record.spec.title;
    if (record.disabled) return shutNotes(title, record.disabled);
    if (record.notice) return shutNotes(title, record.notice);
    if (!record.payload) return record.error ? shutNotes(title, record.error) : null;
    const [moduleName, builderName] = record.spec.notes;
    const builder = this.notesModules[moduleName]?.[builderName];
    if (typeof builder !== 'function') return fallbackNotes(title, record.payload);
    const opts = record.opts ?? {};
    const notes = builder({ ...opts, payload: record.payload, state, experiment, title, card: id });
    return notes ?? fallbackNotes(title, record.payload);
  }

  /** `{panel, meta}` for the exporter; null when nothing is drawn; undefined for a foreign id. */
  exportTarget(id) {
    const record = this.cards.get(id);
    if (!record) return undefined;
    if (!record.spec.exportable || record.element.hidden || record.disabled || record.notice) return null;
    if (!record.panel || !record.payload) return null;
    return { panel: record.panel, meta: exportMeta(record.payload) };
  }

  /**
   * The warnings of the cards on show that their own drawer does not state,
   * for the page's banner: a disclosure lives in the Details drawer, and the
   * banner keeps what the reader could not otherwise see.
   */
  warnings() {
    const out = [];
    for (const record of this.cards.values()) {
      if (record.element.hidden || !record.payload) continue;
      const said = notesText(this.notes(record.spec.id));
      out.push(...warningsNotShown(record.payload.meta?.warnings ?? [], said));
    }
    return out;
  }
}
