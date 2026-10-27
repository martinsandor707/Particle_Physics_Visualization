/* The interface's name for every choice, shared by each place that lists them.
 *
 * The sidebar carries these as static markup (index.html) because it has to
 * render before any script runs; the Admin Settings panel builds its controls
 * from this map. A test compares the two, so a label renamed in one place and
 * not the other fails the suite instead of showing a reader two names for one
 * thing. `detail` is the muted qualifier after the label.
 *
 * ## The reference frames are a tree
 *
 * The sidebar offers two views. "Absolute" is the detector's own coordinates
 * (API frame `lab`). "Separation-Aligned (D-Frame)" is every co-registered
 * frame, chosen by a nested sub-selector: "Translated" is the SE(3)
 * co-registration of every event onto its entry midpoint (API `canonical`;
 * its entry panel writes the A→B axis as D) and "Local" the shower-fixed
 * frame (API `local`). The per-shower translated frame (API `trans`) keeps
 * no radio of its own: a `#frame=trans` link or a saved default still opens
 * it, and while it is active the sidebar reveals a third, legacy sub-option so
 * the control reflects the state. `FRAME_TREE` is the one definition of that
 * hierarchy; the stored value, the hash key and the admin default stay the
 * flat four-value frame key, and `viewOf` / `frameOf` map between the two.
 */

import { FRAMES, apiFrame } from './state.js';

export const FRAME_TREE = Object.freeze({
  // The primary tier, radio name "frame-view".
  views: [
    { value: 'absolute', label: 'Absolute', detail: '(detector coordinates)', frames: ['lab'] },
    {
      value: 'aligned', label: 'Separation-Aligned (D-Frame)', detail: '(SE(3) co-registered)',
      frames: ['canonical', 'local', 'trans'],
    },
  ],
  // The nested tier, radio name "frame-sub"; the value is the backend frame key.
  subs: [
    { value: 'canonical', label: 'Translated', detail: '(every event on its entry midpoint)' },
    { value: 'local', label: 'Local', detail: '(shower-fixed)' },
    {
      value: 'trans', label: 'Per-shower translated',
      detail: '(legacy: each shower from its own entry point P₀)', legacy: true,
    },
  ],
});

/** The sub-frame Separation-Aligned opens on: "Translated (default on entering)". */
export const DEFAULT_SUB = 'canonical';

/* A single-shower experiment has no A→B separation to align on, so the frame
 * tier is relabelled at runtime (main.js, `relabelChoice`): the view becomes
 * "Shower-Aligned", and the per-shower translated frame - every shower moved to
 * its own entry point, without rotation - is that kind's own Translated frame,
 * shown as a sub-option of its own rather than as a legacy one. The D-frame's
 * radio stays, disabled with the server's reason. The static radios keep their
 * two-shower labels, which the tests pin; nothing here renames a stored key. */
export const SINGLE_SHOWER_FRAME_LABELS = Object.freeze({
  aligned: {
    label: 'Shower-Aligned',
    detail: '(each shower at its own entry point)',
    title: 'Every selected shower is moved to its own entry point P₀: Translated keeps the '
      + 'detector axes, Local also rotates it by its own R(θ, φ) so its incident direction lies along +w.',
  },
  trans: {
    label: 'Translated',
    detail: '(each shower from its own entry point P₀, no rotation)',
    title: 'Each shower is moved to its own entry point P₀ - the energy-weighted x, y centroid of its '
      + 'first populated layer, at that layer’s z - without rotation.',
  },
});

const SUB_VALUES = FRAME_TREE.subs.map((sub) => sub.value);
const ALIGNED = FRAME_TREE.views.find((view) => view.value === 'aligned');
const ABSOLUTE = FRAME_TREE.views.find((view) => view.value === 'absolute');

/** The two tiers a frame key is shown as. */
export function viewOf(frame) {
  return SUB_VALUES.includes(frame) ? { view: 'aligned', sub: frame } : { view: 'absolute', sub: null };
}

/** The frame key the two tiers select; an unknown sub-frame lands on the default. */
export function frameOf(view, sub = null) {
  if (view !== 'aligned') return 'lab';
  return SUB_VALUES.includes(sub) ? sub : DEFAULT_SUB;
}

/** Whether a frame key is the legacy per-shower frame, hidden unless active. */
export function isLegacyFrame(frame) {
  return FRAME_TREE.subs.some((sub) => sub.legacy && sub.value === frame);
}

/** The flat choice list the Admin Settings panel shows: the tree, composed. */
function frameChoices() {
  const choices = [{ value: 'lab', label: ABSOLUTE.label, detail: ABSOLUTE.detail }];
  for (const sub of FRAME_TREE.subs) {
    choices.push(sub.legacy
      ? { value: sub.value, label: sub.label, detail: sub.detail, legacy: true }
      : { value: sub.value, label: `${ALIGNED.label} › ${sub.label}`, detail: sub.detail });
  }
  return choices;
}

export const CHOICE_LABELS = Object.freeze({
  frame: frameChoices(),
  model: [
    { value: 'segmentation', label: 'Segmentation Model' },
    { value: 'energy', label: 'Energy Estimation Model' },
    { value: 'angle', label: 'Incident Angle Estimation Model' },
  ],
  channel: [
    { value: 'density', label: 'Average Hit Density (Summed Energy)' },
    { value: 'gradcam', label: 'Grad-CAM Model Attention' },
    { value: 'gradcam_energy', label: 'Energy-weighted Grad-CAM', detail: '(Σ E·CAM)' },
    { value: 'shapcam', label: 'Shap-CAM Attribution', detail: '(signed)' },
    { value: 'shapcam_energy', label: 'Energy-weighted Shap-CAM', detail: '(Σ E·CAM, signed)' },
  ],
  rho_norm: [
    { value: 'selection', label: "Relative to this selection's peak" },
    { value: 'dataset', label: 'Relative to the dataset peak' },
  ],
  // The D-frame's entry anchor (API `anchor`), shown under Translated only.
  anchor: [
    { value: 'backprojected', label: 'Back-projected 3-D centroid', detail: '(default)' },
    { value: 'p0', label: 'First-layer entry point P₀', detail: '(the notebook’s origin)' },
  ],
});

/** A frame key as the interface names it, for a banner or a chip; `nShowers` 1 names a single shower's frames. */
export function frameLabel(frame, nShowers = 2) {
  if (nShowers === 1 && SINGLE_SHOWER_FRAME_NAMES[frame]) return SINGLE_SHOWER_FRAME_NAMES[frame];
  return CHOICE_LABELS.frame.find((choice) => choice.value === frame)?.label ?? String(frame);
}

/** A single shower's frames, by key, as its relabelled frame tier names them. */
const SINGLE_SHOWER_FRAME_NAMES = {
  trans: 'Translated',
  local: 'Shower-Aligned › Local',
};

/**
 * The frame keys an experiment serves, in the interface's order.
 *
 * A frame is offered when the experiment lists it and serves its coordinate
 * system: the D-frame (API `canonical`) is built from the absolute frame's
 * coordinates (`lab`), and the per-shower frames need the extents measured at
 * ingest.
 */
export function offeredFrames(experiment) {
  const frames = experiment?.frames ?? ['lab', 'canonical'];
  const coords = experiment?.coord_systems ?? ['lab'];
  return FRAMES.filter((f) => frames.includes(f) && coords.includes(apiFrame(f).coord_system));
}

/**
 * The sub-frame to land on when Separation-Aligned is entered: Translated
 * when it is offered, else the first offered non-legacy sub-frame, else null
 * (the view is then not offered at all). Never the legacy frame.
 */
export function enteringSub(offered) {
  const list = Array.isArray(offered) ? offered : [];
  if (list.includes(DEFAULT_SUB)) return DEFAULT_SUB;
  const sub = FRAME_TREE.subs.find((s) => !s.legacy && list.includes(s.value));
  return sub ? sub.value : null;
}

/* Display mode, as the panel offers it. A saved mode applies to the default
   frame only, so "each frame's own" is a choice in its own right: native in the
   absolute frame, the kernel reconstruction in the co-registered frames. The
   sidebar's own labels change with the frame, so they are not repeated here. */
export const DISPLAY_CHOICES = Object.freeze([
  { value: null, label: "Frame's own", detail: '(native in Absolute, continuous elsewhere)' },
  { value: 'native', label: 'Native', detail: '(detector lattice, or the raw 20 mm grid)' },
  { value: 'continuous', label: 'Continuous Field' },
]);

/* ------------------------------------------------------- the Models page */

/* The two pages, as the header's tabs name them (page_common.js
 * `wirePageTabs`). The path is the page's route; each tab carries the view
 * across in the link's hash at click time. */
export const PAGE_TABS = Object.freeze([
  { page: 'physics', label: 'Physics', href: '/', title: 'The 2 × 2 spatial diagnostic and the physics cards' },
  { page: 'models', label: 'Models', href: '/models', title: 'Model performance, the feature explorer and the 3-D views' },
]);

/* The per-event features of the explorer, by the id the server's catalog uses
 * (state.js FEATURE_KEYS, in the same order; a test keeps them equal). The
 * catalog (GET /api/features?view=catalog) is the authority on what an
 * experiment offers; these are its names in the sidebar's select. `hitsOnly`
 * marks the two circular companions a hit experiment adds to the aggregate's
 * nineteen; `log` whether a logarithmic axis is offered (an azimuth is drawn
 * on (−π, π], a lattice-quantised feature only on a linear axis). */
export const FEATURES = Object.freeze([
  { key: 'width', label: 'Width — x extent', unit: 'mm', log: true },
  { key: 'height', label: 'Height — y extent', unit: 'mm', log: true },
  { key: 'depth', label: 'Depth — deepest z below the front face', unit: 'mm', log: false },
  { key: 'depth_range', label: 'Depth range — z extent', unit: 'mm', log: false },
  { key: 'volume', label: 'Volume — width × height × depth', unit: 'mm³', log: true },
  { key: 'num_hits', label: 'Number of hits', unit: 'hits', log: false },
  { key: 'total_hit_energy', label: 'Total deposited energy', unit: 'GeV', log: true },
  { key: 'centroid_x', label: 'Energy-weighted centroid x', unit: 'mm', log: true },
  { key: 'centroid_y', label: 'Energy-weighted centroid y', unit: 'mm', log: true },
  { key: 'centroid_z', label: 'Energy-weighted centroid z', unit: 'mm', log: true },
  { key: 'mean_r', label: 'Mean hit radius r', unit: 'mm', log: true },
  { key: 'std_r', label: 'SD of hit radius r', unit: 'mm', log: true },
  { key: 'max_r', label: 'Maximum hit radius r', unit: 'mm', log: true },
  { key: 'weighted_r_mean', label: 'Energy-weighted mean radius r', unit: 'mm', log: true },
  { key: 'avg_theta', label: 'Mean polar angle θ of the hits', unit: 'rad', log: true },
  { key: 'avg_phi', label: 'Arithmetic mean of the hits’ azimuth φ', unit: 'rad', log: false, circular: true },
  {
    key: 'avg_phi_circ', label: 'Mean direction of the hits’ azimuth φ', unit: 'rad', log: false,
    circular: true, hitsOnly: true,
  },
  { key: 'angular_spread', label: 'Angular spread SD(θ) + SD(φ)', unit: 'rad', log: true },
  { key: 'angular_spread_circ', label: 'Angular spread SD(θ) + circular SD(φ)', unit: 'rad', log: true, hitsOnly: true },
  { key: 'numerical_density', label: 'Hit density — hits / volume', unit: 'hits/mm³', log: true },
  { key: 'energy_density', label: 'Energy density — energy / volume', unit: 'GeV/mm³', log: true },
]);

/** The features an experiment's explorer offers: the aggregate has no hits to add the circular companions from. */
export function featureChoices(hasHits = true) {
  return FEATURES.filter((feature) => hasHits || !feature.hitsOnly);
}

/** The Models page's choices, by state key; the cards' toolbars are built from these. */
export const MODELS_LABELS = Object.freeze({
  fclass: [
    { value: 'windows', label: 'Momentum windows', title: 'The features notebook’s windows: (1, 2, 5, 10, 19.5) ± 0.5 GeV' },
    { value: 'label', label: 'p < 2 | p ≥ 2 GeV', title: 'The binary label: incident momentum below 2 GeV against 2 GeV and above' },
  ],
  // Whose features the explorer draws on two-shower data: one shower at a
  // time, never the two pooled (GET /api/features `shower`).
  fshower: [
    { value: 'a', label: 'A', title: 'Shower A’s features (incoming_momentum_A, …)' },
    { value: 'b', label: 'B', title: 'Shower B’s features, classed by its own incident momentum' },
  ],
  // The network task of the performance cards, by the API's `model` value.
  task: [
    { value: 'energy', label: 'Energy', title: 'The energy (momentum) regression: predicted against true incident momentum' },
    { value: 'angle', label: 'Angle', title: 'The incident-angle regression: predicted against true polar angle θ' },
  ],
  xgb_task: [
    { value: 'momentum', label: 'Momentum', title: 'The XGBoost momentum regressor' },
    { value: 'angle', label: 'Angle', title: 'The XGBoost angle regressor (two outputs: φ and θ)' },
  ],
  xgb_label: [
    { value: 'theta', label: 'θ', title: 'The polar angle θ output of the angle regressor' },
    { value: 'phi', label: 'φ', title: 'The azimuth φ output of the angle regressor; its residual is wrapped to (−π, π]' },
  ],
  voxel_channel: [
    { value: 'energy', label: 'Deposited energy' },
    { value: 'gradcam', label: 'Grad-CAM Model Attention' },
    { value: 'shapcam', label: 'Shap-CAM Attribution', detail: '(signed)' },
    { value: 'segerr', label: 'Segmentation error', detail: '(|f_A,pred − f_A,true|)' },
    { value: 'species', label: 'Particle species' },
  ],
  ens_channel: [
    { value: 'density', label: 'Average Hit Density (Summed Energy)' },
    { value: 'gradcam_energy', label: 'Energy-weighted Grad-CAM', detail: '(Σ E·CAM)' },
    { value: 'shapcam_energy', label: 'Energy-weighted Shap-CAM', detail: '(Σ E·CAM, signed)' },
  ],
});
