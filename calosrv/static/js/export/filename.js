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
 */

const MAX_SLICE = 60;

export function figureName(panelId, format, { state, experiment, extra = [] } = {}) {
  const parts = [slug(panelId)];

  const slice = describeSlice(state, extra);
  if (slice) parts.push(slice);
  parts.push(timestamp());

  const name = parts.join('_');
  return `${name}.${format}`;
}

function describeSlice(state, extra) {
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
  tokens.push(state.get('display') === 'native' ? 'native' : `R${state.get('resolution')}`);
  if (state.get('channel') !== 'density') tokens.push('gradcam');
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
