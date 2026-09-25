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
 * drops `canonical`.
 *
 * A figure with no spatial bins (`spatial: false`, the energy panel) carries
 * none of the display, frame, channel or kernel tokens: none of them changes
 * what it shows, and an `R150` on it would name bins it does not contain.
 */

const MAX_SLICE = 60;

export function figureName(panelId, format, {
  state, experiment, extra = [], display = null, spatial = true,
} = {}) {
  const parts = [slug(panelId)];

  const slice = describeSlice(state, extra, display, spatial);
  if (slice) parts.push(slice);
  parts.push(timestamp());

  const name = parts.join('_');
  return `${name}.${format}`;
}

/** `gauss10` | `tent` for a canonical kernel reconstruction, else null. */
function kernelToken(display) {
  if (!display?.canonical || display.mode !== 'continuous') return null;
  if (display.kernel === 'gaussian') {
    return Number.isFinite(display.sigma) ? `gauss${Math.round(display.sigma)}` : 'gauss';
  }
  if (display.kernel === 'bilinear') return 'tent';
  return null;
}

function describeSlice(state, extra, display = null, spatial = true) {
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
    // in the two frames must not collide on everything but their timestamp.
    if (state.get('frame') === 'canonical') tokens.push('canonical');
    if (state.get('channel') !== 'density') tokens.push('gradcam');
    const kernel = kernelToken(display);
    if (kernel) tokens.push(kernel);
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
