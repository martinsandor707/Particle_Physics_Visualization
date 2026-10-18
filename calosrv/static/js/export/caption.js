/* Sentences naming the selection and the display, shared by the Details
 * drawer, the on-screen footnote prose and the export file name.
 *
 * Nothing here is drawn into a figure. An exported figure is the plot canvas
 * alone (export/figure.js); the provenance a reader needs to cite the
 * picture - experiment, filters, frame, grid, channel, event count, the
 * displayed window - is the first section of the panel's Details drawer
 * (panel_notes.js), built by `describeSelection` and `describeView` below.
 * `displayOf` reads what the displayed bins are from the payload rather than
 * from the controls, because the payload guard may have lowered R below the
 * slider; `kernelPhrase` words the kernel. frame_views.js and
 * export/filename.js read both, so the panel's caption and the figure's name
 * describe the same bins.
 */

import { typographic } from '../scale.js';

/** How each co-registered frame is named in a provenance sentence. */
const FRAME_PHRASE = {
  canonical: 'Separation-Aligned (D-Frame), Translated',
  trans: 'per-shower translated frame (legacy; each shower at its own P₀, no rotation)',
  local: 'Separation-Aligned (D-Frame), Local (shower-fixed, R(θ, φ))',
};

/** How each network's input frame is named. */
const NETWORK_PHRASE = {
  absolute: 'absolute (detector) frame',
  trans: 'per-shower translated frame',
  local: 'local frame',
};

/** How each CAM channel is named in a provenance sentence. */
const CHANNEL_PHRASE = {
  gradcam: 'energy-weighted mean Grad-CAM attention',
  gradcam_energy: 'Σ E·Grad-CAM (a.u. of selection peak)',
  shapcam: 'energy-weighted mean Shap-CAM attribution (signed, −1…+1)',
  shapcam_energy: 'Σ E·Shap-CAM (signed log, a.u. of peak |v|)',
};

/**
 * One sentence naming the selection the panel was measured on.
 *
 * Only axes the user actually narrowed are named. An untouched axis spans the
 * whole dataset and says nothing, and printing three redundant full ranges
 * would bury the one bound that matters - the same reasoning `state.writeHash`
 * applies to keeping a shareable link short.
 *
 * `frame` is the payload's `frame` block, or null. In a co-registered frame
 * the display phrase names the accumulation grid rather than the detector
 * lattice - there is no lattice to be native to once every event has been
 * moved - and the channel is a per-event average density in arbitrary units,
 * not a summed energy.
 *
 * `display` is the descriptor `displayOf` reads from the payload. The grid is
 * worded from it rather than from the controls, because the payload guard may
 * have lowered R below the slider, and a caption must name the bins it shows.
 * The controls are consulted only when no descriptor is given.
 *
 * `spatial: false` is for a panel with no spatial bins - the energy panel -
 * whose content depends on neither the frame, the grid, R, the kernel nor the
 * spatial channel: naming them would describe bins the panel does not show.
 */
export function describeSelection(
  state, experiment, selection, frame = null, display = null, { spatial = true, meta = null } = {},
) {
  const parts = [];
  if (experiment) {
    parts.push(`Experiment ${experiment.display_name || experiment.table_name}`);
  }

  const bound = (axis, label, unit, digits) => {
    if (!state.isTouched(axis)) return null;
    const lo = state.get(`${axis}_min`);
    const hi = state.get(`${axis}_max`);
    if (lo === null || hi === null) return null;
    return `${label} ${lo.toFixed(digits)}–${hi.toFixed(digits)} ${unit}`;
  };

  const filters = [
    bound('e1', 'E₁', 'GeV', 2),
    bound('e2', 'E₂', 'GeV', 2),
    bound('d', 'D', 'mm', 0),
  ].filter(Boolean);
  parts.push(filters.length
    ? `selection ${filters.join(', ')}`
    : 'full kinematic range');

  if (state.get('include_undefined_d')) parts.push('including events with undefined D');

  const kind = ['canonical', 'trans', 'local'].includes(frame?.kind) ? frame.kind : 'lab';
  const coregistered = kind !== 'lab';
  const mode = display?.mode ?? state.get('display');
  const r = Number.isFinite(display?.r) ? display.r : state.get('resolution');
  // What the panel holds, from its response's meta where it says: the
  // controls may have moved on while the chart still shows the last payload.
  const uiFrame = ['canonical', 'trans', 'local'].includes(meta?.frame) ? meta.frame
    : (meta?.coord_system ? 'lab' : state.get('frame'));
  const network = meta?.network?.frame
    ?? { lab: 'absolute', canonical: 'absolute', trans: 'trans', local: 'local' }[uiFrame]
    ?? 'absolute';
  if (!spatial) {
    // Only the network describes this panel: the energy panel is the
    // segmentation reconstruction of the selected frame.
    parts.push(`segmentation network, ${NETWORK_PHRASE[network] ?? `${network} frame`}`);
  } else if (coregistered) {
    const name = FRAME_PHRASE[kind];
    const pitch = Number.isFinite(frame.pitch_mm) ? frame.pitch_mm : null;
    const kernel = display ? kernelPhrase(display) : null;
    if (mode === 'native') {
      const merged = display?.merge > 1 && Number.isFinite(display.displayPitch)
        ? `, merged ${display.merge}× to ${fmtMm(display.displayPitch)} mm`
        : '';
      parts.push(`${name}, raw ${pitch ?? 20} mm bins `
        + `(Native Grid, no reconstruction${merged})`);
    } else if (kernel) {
      const bins = Number.isFinite(display.displayPitch)
        ? `${fmtMm(display.displayPitch)} mm display bins` : 'display bins';
      parts.push(`${name}, ${kernel} on ${bins} (R = ${r})`);
    } else {
      // A payload that names no kernel: say what is known, nothing more.
      const grid = pitch !== null ? `${pitch} mm accumulation grid` : 'accumulation grid';
      parts.push(`${name}, ${grid}, Continuous Field at R = ${r}`);
    }
  } else {
    parts.push(mode === 'native'
      ? 'native detector lattice'
      : `continuous field, R = ${r}`);
  }

  const channel = meta?.channel ?? state.get('channel');
  if (!spatial) {
    // The channel colours the spatial panels only.
  } else if (channel && channel !== 'density') {
    const model = meta?.model ?? state.get('model') ?? 'segmentation';
    const count = (meta?.weighting ?? state.get('weighting')) === 'count';
    let phrase = CHANNEL_PHRASE[channel] ?? channel;
    if (count && (channel === 'gradcam' || channel === 'shapcam')) {
      phrase = phrase.replace('energy-weighted', 'count-weighted');
    }
    parts.push(`${model} network (${network}): ${phrase}`);
  } else {
    parts.push(coregistered ? 'average hit density (a.u.)' : 'summed deposited energy');
  }

  if (selection) {
    parts.push(`${plural(selection.n_events, 'event')}, `
      + `${plural(selection.n_hits, 'hit')}`);
  }
  return `${parts.join(' · ')}.`;
}

/**
 * What a displayed bin is, read from the payload rather than from the controls.
 *
 * `resolution` is the response's `meta.resolution` (retained by each panel as
 * `lastOpts.resolution`), `frame` its `frame` block, `panelPayload` the panel.
 * Returns `{mode, r, displayPitch, merge, kernel, sigma, canonical, coregistered,
 * kind}`; any field the payload does not carry is null (merge 1), so callers
 * can fall back field by field. The kernel is 'none' for a raw-bin display.
 */
export function displayOf(resolution, frame = null, panelPayload = null) {
  const res = resolution || {};
  const kind = ['canonical', 'trans', 'local'].includes(frame?.kind) ? frame.kind : 'lab';
  const canonical = kind === 'canonical';
  const coregistered = kind !== 'lab';
  const recon = coregistered ? (frame.reconstruction ?? null) : null;
  const kernel = res.kernel?.type ?? recon?.kernel ?? panelPayload?.kernel ?? null;
  const sigma = res.kernel?.sigma_mm ?? recon?.sigma_mm ?? null;
  return {
    mode: res.mode ?? recon?.display ?? null,
    r: Number.isFinite(res.r_x) ? res.r_x : null,
    displayPitch: Number.isFinite(res.display_pitch_mm) ? res.display_pitch_mm : null,
    merge: Number.isFinite(res.merge) ? res.merge : 1,
    kernel,
    sigma: Number.isFinite(sigma) ? sigma : null,
    canonical,
    coregistered,
    kind,
  };
}

/**
 * The reconstruction kernel as a phrase, or null for a raw-bin display.
 *
 * Gaussian names its σ, since the width is what a reader needs to judge how
 * much the picture was smoothed; the tent's width is fixed by the grid.
 */
export function kernelPhrase(display) {
  switch (display?.kernel) {
    case 'gaussian':
      return Number.isFinite(display.sigma)
        ? `Gaussian kernel, σ = ${fmtMm(display.sigma)} mm`
        : 'Gaussian kernel';
    case 'bilinear': return 'bilinear (tent) kernel';
    case 'box': return 'box (area-weighted) kernel';
    default: return null;
  }
}

/** Millimetres to at most one decimal: 10 → "10", 4.4 → "4.4". */
function fmtMm(value) {
  return Number.isInteger(value) ? String(value) : Number(value).toFixed(1);
}

/** The displayed window, so a zoomed panel states the region it shows. */
export function describeView(view, colName, rowName) {
  if (!view) return '';
  const mm = (v) => typographic(String(Math.round(v)));
  return `View ${colName} ${mm(view.col[0])}–${mm(view.col[1])} mm, `
    + `${rowName} ${mm(view.row[0])}–${mm(view.row[1])} mm.`;
}

function plural(value, noun) {
  if (!Number.isFinite(value)) return `— ${noun}s`;
  const n = Math.round(value);
  return `${n.toLocaleString()} ${noun}${n === 1 ? '' : 's'}`;
}
