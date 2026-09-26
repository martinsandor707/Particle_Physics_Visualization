/* Deterministic, human-readable figure names.
 *
 *     [panel-id]_[slice_or_filter]_[YYYYMMDD_HHMMSS].[svg|png]
 *
 * The slice component names only the axes the user actually narrowed, for the
 * same reason `state.writeHash` omits untouched bounds from a shareable link: a
 * name reading `xy_E1-0.40-20.00_E2-0.40-20.00_D-0-520_...` states three
 * dataset extents and hides the one selection that distinguished this figure
 * from the last. `full` says the same thing in four characters.
 *
 * Timestamps are local rather than UTC. These names are read by the person who
 * pressed the button, minutes later, while deciding which of four exports to
 * put in the paper.
 *
 * The display token - `native` or `R150` - and the canonical kernel token -
 * `gauss10` or `tent` - come from the payload's descriptor (`display`, built
 * by `caption.displayOf`), not from the controls: the payload guard can lower
 * R below the slider, and a file named R150 holding R84 bins is mislabelled.
 * The kernel token is appended last, so the length cap drops it before it
 * drops the frame. A CAM figure names its channel and network
 * (`shapcamE_energy`); the energy panel names a non-lab segmentation frame.
 *
 * A figure with no spatial bins (`spatial: false`, the energy panel) carries
 * none of the display, frame, channel or kernel tokens: none of them changes
 * what it shows, and an `R150` on it would name bins it does not contain.
 */

import { apiFrame } from '../state.js';

const MAX_SLICE = 90;

/** Short tokens for the non-density channels and their networks. */
const CHANNEL_TOKEN = {
  gradcam: 'gradcam', gradcam_energy: 'gradcamE', shapcam: 'shapcam', shapcam_energy: 'shapcamE',
};
const MODEL_TOKEN = { segmentation: 'seg', energy: 'energy', angle: 'angle' };

export function figureName(panelId, format, {
  state, experiment, extra = [], display = null, spatial = true, meta = null,
} = {}) {
  const parts = [slug(panelId)];

  const slice = describeSlice(state, extra, display, spatial, meta);
  if (slice) parts.push(slice);
  parts.push(timestamp());

  const name = parts.join('_');
  return `${name}.${format}`;
}

/** `gauss10` | `tent` for a co-registered kernel reconstruction, else null. */
function kernelToken(display) {
  if (!(display?.coregistered ?? display?.canonical) || display.mode !== 'continuous') return null;
  if (display.kernel === 'gaussian') {
    return Number.isFinite(display.sigma) ? `gauss${Math.round(display.sigma)}` : 'gauss';
  }
  if (display.kernel === 'bilinear') return 'tent';
  return null;
}

/**
 * What the figure holds, from the response's own meta when there is one: the
 * controls can have moved on (a request still in flight, or one that failed)
 * while the chart still shows the previous payload.
 */
function shownBy(state, meta) {
  const frame = ['canonical', 'trans', 'local'].includes(meta?.frame) ? meta.frame
    : (meta ? 'lab' : state.get('frame'));
  return {
    frame,
    channel: meta?.channel ?? state.get('channel'),
    model: meta?.model ?? state.get('model'),
    network: meta?.network?.frame ?? null,
  };
}

function describeSlice(state, extra, display = null, spatial = true, meta = null) {
  if (!state) return extra.filter(Boolean).map(slug).join('-') || null;

  const bounds = [];
  const push = (axis, label, digits) => {
    if (!state.isTouched(axis)) return;
    const lo = state.get(`${axis}_min`);
    const hi = state.get(`${axis}_max`);
    if (lo === null || hi === null) return;
    bounds.push(`${label}${lo.toFixed(digits)}-${hi.toFixed(digits)}`);
  };
  push('e1', 'E1-', 2);
  push('e2', 'E2-', 2);
  push('d', 'D-', 0);

  const tokens = bounds.length ? bounds : ['full'];
  if (spatial) {
    const mode = display?.mode ?? state.get('display');
    const r = Number.isFinite(display?.r) ? display.r : state.get('resolution');
    tokens.push(mode === 'native' ? 'native' : `R${r}`);
    // The frame changes what every pixel means, so two figures of one selection
    // in two frames must not collide on everything but their timestamp.
    const shown = shownBy(state, meta);
    const frame = shown.frame;
    if (meta ? frame === 'canonical' : state.get('frame') === 'canonical') tokens.push('canonical');
    else if (frame && frame !== 'lab') tokens.push(frame);
    // A CAM figure belongs to one network; a density figure to none.
    const channel = shown.channel;
    if (channel && channel !== 'density') {
      tokens.push(CHANNEL_TOKEN[channel] ?? channel);
      tokens.push(MODEL_TOKEN[shown.model] ?? shown.model);
    }
    const kernel = kernelToken(display);
    if (kernel) tokens.push(kernel);
  } else {
    // The energy panel is the selected frame's segmentation reconstruction.
    const network = shownBy(state, meta).network;
    const coord = network ? (network === 'absolute' ? 'lab' : network)
      : apiFrame(state.get('frame')).coord_system;
    if (coord !== 'lab') tokens.push(coord);
  }
  for (const item of extra) if (item) tokens.push(item);

  return slug(tokens.join('_')).slice(0, MAX_SLICE).replace(/[-_]+$/, '');
}

function timestamp(now = new Date()) {
  const p = (n, width = 2) => String(n).padStart(width, '0');
  return `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}`
    + `_${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`;
}

/** Filesystem-safe, and stable across platforms. */
function slug(text) {
  return String(text ?? '')
    .normalize('NFKD')
    .replace(/[^\w.-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '');
}
