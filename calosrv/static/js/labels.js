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
