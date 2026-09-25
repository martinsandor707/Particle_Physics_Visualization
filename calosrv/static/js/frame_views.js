/* What each reference frame says about itself: titles, captions, footnotes.
 *
 * Pure and DOM-free, so every sentence can be checked under Node. `main.js`
 * writes the strings; nothing here touches the page.
 *
 * Four frames share three spatial panels:
 *
 * - `lab`: detector coordinates as recorded.
 * - `canonical`: every event co-registered by one rigid-body motion into the
 *   centre-of-separation frame.
 * - `trans`: every hit shifted by its own shower's entry point P₀, so the two
 *   showers of each event are superimposed at the origin.
 * - `local`: translated, then rotated by the shower's own R(θ, φ), so every
 *   incident direction is +w.
 *
 * The three co-registered frames share the canonical renderer and so its
 * payload blocks (`fit`, `rho`, `reconstruction`, `comb`); what differs - the
 * splat, the depth axis, the overlays, what a centroid offset means - is read
 * from the payload's `frame` block and worded here per kind.
 */

import { formatInt, formatSci, floorLabel, formatSigned, typographic } from './scale.js';
import { ordinal } from './export/disclosure.js';
import { displayOf, kernelPhrase } from './export/caption.js';
import { centroidLegend } from './panels/canonical_overlays.js';

export const COREGISTERED = ['canonical', 'trans', 'local'];

/** The frame kind of a projections payload: `lab` unless it carries a frame block. */
export function kindOf(payload) {
  const kind = payload?.frame?.kind;
  return COREGISTERED.includes(kind) ? kind : 'lab';
}

export const FRAME_VIEWS = {
  lab: {
    coregistered: false,
    symbols: { x: 'x', y: 'y', z: 'z' },
    titles: {
      xy: 'XY Projection — Shower Entry',
      yz: 'YZ Projection — Longitudinal Evolution',
      xz: 'XZ Projection — Lateral Profile',
    },
    caption:
      'Detector coordinates as recorded. The depth panels draw individual '
      + 'trajectories for selections of 50 events or fewer, otherwise the measured '
      + 'shower axes; no averaged direction is drawn in this frame.',
    displayLabels: {
      native: 'Native Detector Lattice <span class="muted">(hardware truth)</span>',
      continuous: 'Continuous Field <span class="muted">(anti-aliased splatting)</span>',
    },
    resolutionHint: null,
  },
  canonical: {
    coregistered: true,
    symbols: { x: 'x′', y: 'y′', z: 'z′' },
    titles: {
      xy: 'X′Y′ Projection — Co-registered Shower Entry',
      yz: 'Y′Z′ Projection — Longitudinal Evolution, canonical frame',
      xz: 'X′Z′ Projection — Lateral Profile, canonical frame',
    },
    caption:
      'Every selected event is moved by one rigid-body motion: the midpoint of the '
      + 'two back-projected entry points goes to the origin, the A→B separation to '
      + '+x′, the front face to z′ = 0. Panels show the ensemble-averaged energy '
      + 'density, and two ensemble axes replace individual trajectories.',
    displayLabels: {
      native: 'Native Grid <span class="muted">(raw 20 mm bins, audit)</span>',
      continuous: 'Continuous Field <span class="muted">(kernel reconstruction)</span>',
    },
    resolutionHint:
      'R sets the display bins across the X′Y′ window; the kernel, not R, sets the resolution — '
      + 'no detail exists below the 20 mm grid or the 48 mm cell. Depth stays at the native layers.',
  },
  trans: {
    coregistered: true,
    symbols: { x: 'Δx', y: 'Δy', z: 'Δz' },
    titles: {
      xy: 'Δx–Δy Projection — Superimposed Shower Entry',
      yz: 'Δy–Δz Projection — Longitudinal Evolution, translated frame',
      xz: 'Δx–Δz Projection — Lateral Profile, translated frame',
    },
    caption:
      "Every hit is moved by its own shower's entry point P₀ (the energy-weighted x, y "
      + 'centroid of its first populated layer, at that layer’s z), without rotation, so both '
      + 'showers of every event sit at the origin. D stays the laboratory 3-D centroid '
      + 'distance. The depth panels draw individual incident directions from the origin for '
      + '50 events or fewer; no averaged direction is drawn.',
    displayLabels: {
      native: 'Native Grid <span class="muted">(raw 20 mm bins, audit)</span>',
      continuous: 'Continuous Field <span class="muted">(kernel reconstruction)</span>',
    },
    resolutionHint:
      'R sets the display bins across the window; the kernel, not R, sets the resolution. '
      + "Depth stays on each shower's native layers.",
  },
  local: {
    coregistered: true,
    symbols: { x: 'u', y: 'v', z: 'w' },
    titles: {
      xy: 'u–v Projection — Shower-fixed Entry',
      yz: 'v–w Projection — Longitudinal Evolution, local frame',
      xz: 'u–w Projection — Lateral Profile, local frame',
    },
    caption:
      "Translated as in the translated frame, then rotated by each shower's own R(θ, φ): "
      + 'u and v are the lateral spread, w the depth along the incident direction. w is the '
      + 'incident direction by construction, so no direction overlay is drawn. D stays the '
      + 'laboratory 3-D centroid distance.',
    displayLabels: {
      native: 'Native Grid <span class="muted">(raw 20 mm bins, audit)</span>',
      continuous: 'Continuous Field <span class="muted">(kernel reconstruction)</span>',
    },
    resolutionHint:
      'R sets the display bins across the window; the kernel, not R, sets the resolution. '
      + 'Depth w is binned on a uniform grid and never smoothed.',
  },
};

export function frameView(kind) {
  return FRAME_VIEWS[kind] ?? FRAME_VIEWS.lab;
}

export function panelTitle(id, kind) {
  return frameView(kind).titles[id];
}

/* ------------------------------------------------------------- helpers -- */

/** A number for prose: fixed decimals with a typographic minus, or an em dash. */
export function num(value, digits = 0) {
  return Number.isFinite(value) ? typographic(Number(value).toFixed(digits)) : '—';
}

/** A fraction as a percentage for prose, or an em dash when undefined. */
export function pct(value, digits = 2) {
  return Number.isFinite(value) ? typographic(`${(100 * value).toFixed(digits)}%`) : '—';
}

const RHO_UNITS = { 'GeV/mm^2/event': 'GeV mm⁻² per event', GeV: 'GeV' };

function unitText(unit) {
  return RHO_UNITS[unit] ?? unit ?? 'GeV mm⁻² per event';
}

const MODEL_WORDS = { segmentation: 'Segmentation', energy: 'Energy', angle: 'Angle' };
const NETWORK_FRAME = { lab: 'absolute', canonical: 'absolute', trans: 'trans', local: 'local' };
const FRAME_WORDS = { absolute: 'laboratory (absolute)', trans: 'translated', local: 'local' };

const CAM_NORMALISATION =
  'Angle- and energy-model CAMs are normalised per shower, segmentation CAMs per event, so an '
  + 'ensemble map mixes independently normalised maps: it shows where the network attends, not '
  + 'how strongly across events.';

/* -------------------------------------------------------- display caption -- */

/**
 * What a displayed bin is, read from the payload.
 *
 * Names what a displayed bin is in each mode - the raw accumulation bin, or a
 * sample of the kernel reconstruction - with the kernel, its width and the
 * total blur, because a smooth picture that does not say how it was smoothed
 * invites a reader to take its smoothness for the shower's.
 */
export function displayCaption(kind, resolution, frame) {
  if (!resolution) return '—';
  if (kind === 'lab') {
    const lowered = Number.isFinite(resolution.requested) && resolution.requested !== resolution.r_x
      ? ` R lowered from ${resolution.requested} to ${resolution.r_x} by the 100 KB response guard.`
      : '';
    return resolution.mode === 'native'
      ? `Native lattice: one bin per calorimeter cell (${resolution.r_x} × ${resolution.r_y} transverse, ${resolution.r_z} depth layers). Every bin is a real cell, so the depth axes carry no empty-bin comb.`
      : `Continuous field: ${resolution.r_x} × ${resolution.r_y} transverse bins by area-weighted splatting, depth locked to ${resolution.r_z} native layers.${lowered}`;
  }
  const sym = frameView(kind).symbols;
  const recon = frame?.reconstruction ?? null;
  const display = displayOf(resolution, frame);
  const layers = kind === 'local'
    ? `${resolution.r_z} uniform w bins`
    : `${resolution.r_z} depth layers`;
  if (display.mode === 'native') {
    const merged = display.merge > 1
      ? `; merged ${display.merge}× to ${num(display.displayPitch, 0)} mm by the payload guard`
      : '';
    return `Native Grid: the raw ${num(resolution.pitch_mm, 0)} mm accumulation bins, no reconstruction `
      + `(${resolution.r_x} × ${resolution.r_y} transverse in the symmetric window, ${layers}) — `
      + `the audit view${merged}.`;
  }
  const kernel = kernelPhrase(display);
  if (!recon || !kernel) {
    // A payload that names no kernel: say what is known, nothing more.
    return `Continuous Field at R = ${resolution.r_x} (${num(resolution.display_pitch_mm, 1)} mm display bins), `
      + `depth locked to ${layers}.`;
  }
  const spread = Number.isFinite(recon.bin_spread_rms_mm)
    ? `${recon.bin_spread_rms_mm.toFixed(1)} mm RMS per ${num(resolution.pitch_mm, 0)} mm bin` : null;
  const blur = recon.blur_rms_mm;
  const total = Number.isFinite(blur?.x) && Number.isFinite(blur?.y)
    ? `total blur ${blur.x.toFixed(1)} × ${blur.y.toFixed(1)} mm RMS with the ${splatPhrase(frame, recon)}`
    : null;
  const detail = [spread, total].filter(Boolean).join('; ');
  const gate = Number.isFinite(recon.gaussian_below_n)
    ? ` Gaussian below N = ${recon.gaussian_below_n} events, tent above.` : '';
  const depth = kind === 'local' ? `depth never smoothed (${layers})` : `depth native (${layers})`;
  return `Continuous Field: conservative ${kernel}${detail ? ` (${detail})` : ''}, ${sym.x}/${sym.y} only, `
    + `${depth}; ${num(resolution.display_pitch_mm, 1)} mm display bins `
    + `(R = ${resolution.r_x}).${gate}`;
}

/** How a co-registered frame puts each cell's footprint onto its grid. */
function splatPhrase(frame, recon = frame?.reconstruction) {
  const regime = frame?.splat?.regime ?? recon?.splat_regime;
  if (regime === 'box_overlap') return 'exact area-weighted box overlap';
  if (regime === 'subdeposit3d') {
    const k = frame?.splat?.k ?? recon?.subsample_k;
    return `${k} × ${k} × ${frame?.splat?.k_z ?? 1} rotated sub-deposits`;
  }
  const k = recon?.subsample_k ?? frame?.subsample_k;
  return `${k} × ${k} footprint splat`;
}

/** ⟨D_entry⟩ with its interval, as HTML for the X′Y′ tag; '' without events. */
export function entryTag(frame) {
  const entry = frame?.d_entry ?? {};
  if (!(frame?.n_events > 0) || !Number.isFinite(entry.mean)) return '';
  const symbol = '⟨D<sub>entry</sub>⟩';
  const n = Number.isFinite(entry.n) ? entry.n : frame.n_events;
  if (n === 1) return `${symbol} ${num(entry.mean)} mm (single event)`;
  if (!Number.isFinite(entry.ci95_half)) return `${symbol} ${num(entry.mean)} mm (N = ${formatInt(n)})`;
  return `${symbol} ${num(entry.mean)} ± ${num(entry.ci95_half)} mm (95% t, N = ${formatInt(n)})`;
}

/** The XY tag of a per-shower frame: N events and 2N superimposed showers. */
export function showerTag(frame) {
  if (!(frame?.n_events > 0)) return '';
  return `N = ${formatInt(frame.n_events)} · ${formatInt(frame.n_showers)} showers`;
}

/* --------------------------------------------------------- channel caption -- */

/**
 * The channel caption.
 *
 * `frame` is the interface frame (lab | trans | local | canonical); the CAM
 * column is the payload's own `meta.cam.column` when one is in hand, else
 * derived from the model and the frame's network (the canonical frame uses
 * the absolute networks).
 */
export function channelCaption({ channel, model = 'segmentation', frame = 'lab', payload = null,
  display = null, weighting = 'energy' }) {
  const kind = frame;
  const coregistered = COREGISTERED.includes(kind);
  const pf = kindOf(payload) === kind ? payload?.frame : null;
  const floor = floorLabel({ floor_ratio: pf?.reconstruction?.floor_ratio ?? 1e-3 });
  const network = NETWORK_FRAME[kind] ?? 'absolute';
  const cam = channel.startsWith('shapcam') ? 'shapcam' : 'gradcam';
  const column = payload?.meta?.cam?.column ?? `${model}_${network}_${cam}`;
  const lead = `${MODEL_WORDS[model] ?? model} network, ${FRAME_WORDS[network]} frame (${column}):`;
  const normalisation = payload?.meta?.cam?.note ?? CAM_NORMALISATION;
  const mean = weighting === 'count' ? 'count-weighted mean' : 'energy-weighted mean';
  const mode = pf?.reconstruction?.display ?? display;

  if (channel === 'density') {
    if (!coregistered) {
      return 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the brightest cell.';
    }
    const basis = pf?.rho?.basis ?? 'raw 20 mm-grid peak';
    const unit = unitText(payload?.panels?.xy?.rho_unit);
    const both = kind === 'trans' || kind === 'local'
      ? ' Both showers of every event are superimposed, so ⟨ρ⟩ sums the two.' : '';
    return `Average hit density ⟨ρ⟩ = ΣE / (N·ΔA) in ${unit}, drawn as a.u. relative to the stated `
      + `reference peak on a three-decade logarithmic ramp. Bins below ${floor} of ρ_ref are not drawn and the `
      + `bottom half decade fades out; ρ_ref is the ${basis}.${both}`;
  }

  let body;
  if (channel === 'gradcam') {
    body = `${lead} ${mean} Grad-CAM attention of the hits in each bin, fixed 0–1 linear scale.`;
  } else if (channel === 'shapcam') {
    body = `${lead} ${mean} Shap-CAM attribution, symmetric ${typographic('-1')}…+1 linear scale on `
      + 'ColorBrewer PuOr (orange negative, purple positive, brighter with |value|); nothing is clipped.';
  } else if (channel === 'gradcam_energy') {
    body = `${lead} Σ E·Grad-CAM per bin (extensive, conserved across R and display modes), relative to `
      + `this selection's peak on a three-decade log ramp; bins below ${floor} of the peak are not drawn.`;
  } else {
    body = `${lead} Σ E·Shap-CAM per bin (signed, extensive; positive and negative parts each `
      + `conserved) on a signed log ramp ±(${floor}…1) of the selection's peak |value|; |v| below `
      + `${floor} of the peak is not drawn.`;
  }
  if (coregistered && (channel === 'gradcam' || channel === 'shapcam')) {
    const what = channel === 'gradcam' ? 'attention' : 'attribution';
    body += mode === 'continuous'
      ? ` Bins whose reconstructed density falls below ${floor} of ρ_ref are not drawn: the kernel's tails would otherwise paint ${what} where there is no energy.`
      : ` Only bins without hits are left undrawn, so ${what} measured on real hits is never hidden.`;
  }
  return `${body} ${normalisation}`;
}

/* --------------------------------------------------------------- footnotes -- */

/**
 * The fitted display window of one co-registered panel, as a phrase.
 *
 * The window is symmetric about the origin, so it is quoted as half-widths,
 * `x′ ±480 mm`, which is what the reader compares against ⟨D_entry⟩/2. Where
 * the floor or the accumulation window set a half-width rather than the
 * percentile, that is said: a floored window is wider than the energy needs.
 */
export function windowPhrase(fit, id, sides) {
  const panelFit = fit[id] || {};
  const parts = [];
  const limits = [];
  for (const [side, symbol] of sides) {
    const axis = panelFit[side];
    if (!axis?.applied || !Array.isArray(axis.range)) {
      parts.push(`${symbol} full window`);
      continue;
    }
    if (fit.rule === 'symmetric') {
      const half = Number.isFinite(axis.half_width)
        ? axis.half_width
        : Math.max(Math.abs(axis.range[0]), Math.abs(axis.range[1]));
      parts.push(`${symbol} ±${Math.round(half)} mm`);
    } else {
      parts.push(`${symbol} ${num(axis.range[0])}–${num(axis.range[1])} mm`);
    }
    if (axis.floored) {
      limits.push(`${symbol} held at the ${num(fit.floor_mm)} mm `
        + `${fit.provisional ? 'provisional' : 'two-footprint'} floor`);
    }
    if (axis.clamped) limits.push(`${symbol} clamped to the accumulation window`);
  }
  const [p0, p1] = Array.isArray(fit.percentiles) && fit.percentiles.length >= 2
    ? fit.percentiles : [1, 99];
  const rule = `${fit.rule === 'symmetric' ? 'symmetric ' : ''}${ordinal(p0)}–${ordinal(p1)} energy percentile`;
  return `Window ${parts.join(', ')} (${[rule, ...limits].join('; ')})`;
}

/**
 * Whether a co-registered panel's bins are a kernel reconstruction: its own
 * `kernel` when the payload names one ('none' is the raw Native Grid, and a
 * guard's box merge of it), else the frame's display mode.
 */
function reconstructedPanel(panel, continuous) {
  if (typeof panel?.kernel === 'string') return panel.kernel !== 'none';
  return Boolean(continuous);
}

/**
 * The display-floor sentence of one co-registered panel, in its channel's terms.
 *
 * Density: the bins under 10⁻³ of ρ_ref are transparent and the bottom half
 * decade fades, so the reader must be told that the edge of the colour is the
 * floor and not the edge of the shower. A mean CAM: the masking rule, which
 * differs by display mode - the continuous field masks where the kernel's
 * tails would paint attention over no energy, the Native Grid only where no
 * hit exists. An energy-weighted CAM: its own floor, 10⁻³ of its own peak.
 */
export function floorSentence(panel, continuous, floor) {
  if (!panel) return '';
  const quantity = panel.scale?.quantity;
  if (panel.scale?.unit === 'attention' || panel.scale?.unit === 'attribution') {
    const mask = panel.attention_mask;
    if (!mask) return '';
    const lead = typeof mask.rule === 'string' && mask.rule
      ? mask.rule.replace(/\.?\s*$/, '.')
      : (continuous
        ? `Attention is not drawn where the reconstructed density is below ${floor} of ρ_ref.`
        : 'Only bins without hits are left undrawn.');
    const largest = quantity === 'shapcam' ? 'largest masked |attribution|' : 'largest masked attention';
    const counts = mask.cells > 0
      ? ` ${formatInt(mask.cells)} bin${mask.cells === 1 ? '' : 's'} masked`
        + (Number.isFinite(mask.hit_fraction) ? `, holding ${pct(mask.hit_fraction)} of this panel's in-window hits` : '')
        + (Number.isFinite(mask.max_attention) ? `; ${largest} ${formatSigned(mask.max_attention, 2)}` : '')
        + '.'
      : '';
    return ` ${lead}${counts}`;
  }
  if (panel.scale?.floor !== 'transparent') return '';
  const cells = Number.isFinite(panel.below_floor_cells)
    ? `${formatInt(panel.below_floor_cells)} bin${panel.below_floor_cells === 1 ? '' : 's'}` : null;
  if (quantity === 'gradcam_energy' || quantity === 'shapcam_energy') {
    const magnitude = quantity === 'shapcam_energy' ? '|Σ E·CAM|' : 'Σ E·CAM';
    return ` Bins whose ${magnitude} is below ${floor} of this selection's peak are not drawn`
      + `${cells ? ` (${cells})` : ''}; bins with no hits are empty.`;
  }
  const energy = reconstructedPanel(panel, continuous) ? 'in-window reconstructed energy' : 'in-window energy';
  const counts = cells
    ? ` (${cells}`
      + (Number.isFinite(panel.below_floor_energy_fraction)
        ? `, ${pct(panel.below_floor_energy_fraction)} of this panel's ${energy}` : '')
      + ')'
    : '';
  return ` Bins below ${floor} of ρ_ref are not drawn${counts}; the bottom half decade fades to `
    + 'transparent, so the edge of the colour is the display floor, not the edge of the shower.';
}

/** The colour sentence of a co-registered panel, by the quantity it shows. */
function colourSentence(panel, rho, reference, shared = '') {
  const scale = panel?.scale || {};
  const unit = unitText(panel?.rho_unit);
  const ref = (value) => `${formatSci(value, 3)} ${unit}`;
  switch (scale.quantity) {
    case 'gradcam':
      return 'Colour: energy-weighted mean Grad-CAM attention on a fixed 0–1 scale.';
    case 'shapcam':
      return `Colour: energy-weighted mean Shap-CAM attribution on a symmetric ${typographic('-1')}…+1 scale `
        + '(PuOr: orange negative, purple positive); nothing is clipped.';
    case 'gradcam_energy':
      return `Colour: Σ E·Grad-CAM per event and mm², relative to this selection's raw-grid peak `
        + `${ref(scale.ref)}${shared}.`;
    case 'shapcam_energy':
      return `Colour: Σ E·Shap-CAM per event and mm² (signed log), relative to this selection's raw-grid `
        + `peak |value| ${ref(scale.ref)}${shared}; drawn positive part ${formatSci(scale.positive_total, 3)}, `
        + `negative part ${formatSci(scale.negative_total, 3)} ${unit}·mm².`;
    default: {
      const norm = rho.norm === 'dataset'
        ? `the dataset peak${rho.ref_k && rho.ref_k !== rho.selection_k ? ` (measured with ${rho.ref_k} × ${rho.ref_k} sub-deposits per cell against ${rho.selection_k} × ${rho.selection_k} here)` : ''}`
        : 'this selection’s own peak (autoscaled; switch the density normalisation to compare colours across selections)';
      return `Colour: average hit density (a.u.) relative to ρ_ref = ${ref(reference)}${shared}, ${norm}.`;
    }
  }
}

function offsetsText(offsets) {
  const pair = offsets?.truth_voxel;
  if (!pair || !pair.a || !pair.b) return '';
  const fmt = (v) => `${formatSigned(v[0], 0, { plus: true })}, ${formatSigned(v[1], 0, { plus: true })}`;
  return ` The measured ensemble entry centroids sit at (${fmt(pair.a)}) mm from the A anchor and (${fmt(pair.b)}) mm from the B anchor.`;
}

/**
 * Shared pieces of the co-registered footnotes: outside-window energy, the
 * kernel sentence with the displayed peak's attenuation, the aspect.
 */
function coregisteredParts(payload, isometric) {
  const f = payload.frame;
  const rho = f.rho || {};
  const fit = f.fit || {};
  const recon = f.reconstruction || null;
  const panels = payload.panels || {};
  const continuous = (recon?.display ?? payload.meta?.resolution?.mode) === 'continuous';
  const ratio = ['attention', 'attribution'].includes(panels.xy?.scale?.unit);
  const floor = floorLabel({ floor_ratio: recon?.floor_ratio ?? 1e-3 });
  // Measured after reconstruction when the payload says so: energy the
  // kernel carries across the window edge is energy the reader cannot see.
  const outside = (id) => {
    const after = panels[id]?.energy_fraction_outside_window;
    const value = Number.isFinite(after) ? after : fit[id]?.energy_fraction_outside;
    return `${pct(value ?? 0)} of the ${id === 'xy' ? 'slab ' : ''}energy lies outside`
      + (Number.isFinite(after) && reconstructedPanel(panels[id], continuous)
        ? ' after reconstruction' : '');
  };
  // The kernel sentence, with the attenuation of the displayed peak against
  // this panel's raw 20 mm-grid peak - the reference ρ_ref is measured on.
  const kernel = (id) => {
    const note = typeof recon?.note === 'string' && recon.note ? ` ${recon.note}` : '';
    const a = rho.kernel_attenuation?.[id];
    const attenuation = continuous && !ratio && !panels[id]?.scale?.quantity && Number.isFinite(a)
      ? ` The displayed peak is ${a.toFixed(2)} × this panel's raw 20 mm-grid peak.`
      : '';
    return `${note}${attenuation}`;
  };
  const aspect = (id) => (isometric?.[id]
    ? ' Drawn at a 1:1 metric aspect.'
    : ' Axes carry true extents; the aspect is not 1:1 here.');
  const provisional = fit.provisional ? ` Fitted ranges are provisional (N = ${f.n_events}).` : '';
  const combText = f.comb?.note ? ` ${f.comb.staggered ? '⚠ ' : ''}${f.comb.note}` : '';
  return { f, rho, fit, panels, continuous, floor, outside, kernel, aspect, provisional, combText };
}

/**
 * Footnotes for the canonical frame.
 *
 * Every number a reader needs to reproduce or discount the picture is on the
 * panel itself: the anchor definition, N and what was excluded, both separation
 * definitions, the density reference, the fitted window and what lies outside
 * it, the display floor, the reconstruction kernel, the sub-cell factor, the
 * measured comb, and the coherence of each axis.
 */
export function canonicalFootnotes(payload, { isometric = {} } = {}) {
  const f = payload.frame;
  if (!(f.n_events > 0)) {
    // Nothing was co-registered: say so, rather than print zeros for means
    // that are undefined and windows that were never fitted.
    const empty =
      `Canonical centre-of-separation frame: no selected event has a defined frame `
      + `(${formatInt(f.n_selected)} selected, ${formatInt(f.n_excluded_no_frame)} without a shower-A `
      + 'centroid or direction). The panels are empty and no ensemble axis is drawn.';
    return { xy: `${payload.slab.note} ${empty}`, yz: empty, xz: empty };
  }
  const p = coregisteredParts(payload, isometric);
  const { rho, fit, panels, continuous, floor, outside, kernel, aspect, provisional, combText } = p;

  // The interval is named: at N = 2 the Student-t 95% half-width is 12.7
  // standard errors, so a bare "±" would mean whatever the reader assumes.
  const ci = Number.isFinite(f.d_entry?.ci95_half)
    ? ` (95% t-interval of the mean ± ${num(f.d_entry.ci95_half)} mm)`
    : '';
  const base =
    `Canonical centre-of-separation frame: N = ${formatInt(f.n_events)} co-registered event${f.n_events === 1 ? '' : 's'}`
    + (f.n_excluded_no_frame ? ` (${formatInt(f.n_excluded_no_frame)} selected event(s) excluded: no shower-A centroid or direction)` : '')
    + `; ⟨D_entry⟩ = ${num(f.d_entry?.mean)} mm at the front face${ci}, ⟨D⟩ = ${num(f.d_dataset?.mean)} mm (dataset, 3-D centroid distance).`;
  const k = f.subsample_k;
  const splat = ` Cells (${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm) are splatted as ${k} × ${k} sub-deposits on a ${f.pitch_mm} mm grid.`;
  const ill = f.n_ill_conditioned
    ? ` ${formatInt(f.n_ill_conditioned)} event(s) enter closer than ${f.ill_conditioned_threshold_mm} mm apart, so their orientation is effectively random: their energy enters ⟨ρ⟩ averaged over azimuth and their directions enter R̄′, the Rayleigh p and the dispersion band as noise.`
    : '';
  const centroids = centroidLegend(payload.centroids);

  const xy =
    `${payload.slab.note} ${base} ${colourSentence(panels.xy, rho, rho.ref?.xy)} `
    + `${windowPhrase(fit, 'xy', [['col', 'x′'], ['row', 'y′']])}; ${outside('xy')}.${provisional}`
    + `${floorSentence(panels.xy, continuous, floor)}${kernel('xy')} `
    + 'Open diamond and circle: the A and B anchors at ∓⟨D_entry⟩/2; faint bar: sample spread (SD) of '
    + 'D_entry/2 across events; thin dashed rule: the mean entry separation (hover for ⟨D_entry⟩ with its '
    + `95% t-interval).${centroids ? ` ${centroids}` : ''}${offsetsText(f.anchor_offsets)}${splat}${combText}${ill}`;

  const axesText = (f.notes || []).join(' ');
  const marks = f.n_events === 1
    ? ' Dashed lines are this single event’s two incident directions, not an ensemble; no dispersion '
      + 'band or interval can be drawn from one event. Thin rules mark the front and back faces (first and '
      + 'last sampling layer); the transverse outline rotates with each event and has no ensemble image.'
    : ' Dashed lines are the two ensemble shower axes (mean incident direction in this frame); the shaded '
      + 'wedge behind each is the sample spread of the per-event slopes and the thin envelope the 95% '
      + 't-interval of the mean — two different quantities, so two different marks. Individual trajectories '
      + 'are not drawn in this frame. Thin rules mark the front and back faces (first and last sampling '
      + 'layer); the transverse outline rotates with each event and has no ensemble image.';
  const anchorsText = {
    yz: ' The open circle at the origin stands for both anchors, which this panel projects onto one point.',
    xz: ' Open diamond and circle at z′ = 0: the A and B anchors, with a faint bar for the sample spread '
      + '(SD) of D_entry/2.',
  };
  const depthRef = (id) => colourSentence(panels[id], rho, rho.ref?.depth, ' (shared by both depth panels)');

  return {
    xy,
    yz: `Transverse spread normal to the shower plane against depth. ${depthRef('yz')} `
      + `${windowPhrase(fit, 'yz', [['row', 'y′']])}; ${outside('yz')}.${provisional}`
      + `${floorSentence(panels.yz, continuous, floor)}${kernel('yz')}`
      + `${anchorsText.yz}${marks} ${axesText}${aspect('yz')}`,
    xz: `Lateral profile along the separation against depth. ${depthRef('xz')} `
      + `${windowPhrase(fit, 'xz', [['row', 'x′']])}; ${outside('xz')}.${provisional}`
      + `${floorSentence(panels.xz, continuous, floor)}${kernel('xz')}`
      + `${anchorsText.xz}${marks} ${axesText}${aspect('xz')}`,
  };
}

/**
 * Footnotes for the translated and local frames.
 *
 * Both superimpose the two showers of every event at the origin, so the voxel
 * centroid pair measures an A-B *offset* of two ensembles each relative to its
 * own entry point - never a separation, which stays the laboratory D.
 */
export function showerFootnotes(payload, { isometric = {} } = {}) {
  const f = payload.frame;
  const kind = f.kind;
  const sym = frameView(kind).symbols;
  const title = kind === 'trans' ? 'Translated frame' : 'Local frame';
  if (!(f.n_events > 0)) {
    const empty = `${title}: no selected event has a defined A-B separation `
      + `(${formatInt(f.n_selected)} selected); the panels are empty.`;
    return { xy: `${payload.slab.note} ${empty}`, yz: empty, xz: empty };
  }
  const p = coregisteredParts(payload, isometric);
  const { rho, fit, panels, continuous, floor, outside, kernel, aspect, provisional, combText } = p;

  const ci = Number.isFinite(f.d_dataset?.ci95_half)
    ? ` ± ${num(f.d_dataset.ci95_half)} mm (95% t-interval of the mean)` : '';
  const base = `${title}: N = ${formatInt(f.n_events)} event${f.n_events === 1 ? '' : 's'}, `
    + `${formatInt(f.n_showers)} showers superimposed at their own entry points`
    + (f.n_excluded_no_frame ? ` (${formatInt(f.n_excluded_no_frame)} selected event(s) excluded: no A-B separation)` : '')
    + `; D is the laboratory 3-D centroid distance, ⟨D⟩ = ${num(f.d_dataset?.mean)} mm${ci}.`;
  const centroids = centroidLegend(payload.centroids);
  const offset = ' The A–B offset of the superimposed centroids (offset_mm) is not a separation.';
  const splat = kind === 'trans'
    ? ` Each cell's ${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm footprint is `
      + `integrated exactly by area-weighted box overlap on a ${f.pitch_mm} mm grid.`
    : ` Each cell's ${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm × `
      + `${num(f.depth?.pitch_mm, 1)} mm volume is split into ${f.splat?.k} × ${f.splat?.k} × ${f.splat?.k_z} `
      + `sub-deposits rotated with its shower, on a ${f.pitch_mm} mm grid.`;
  const ab = f.n_ab_hits
    ? ` ${formatInt(f.n_ab_hits)} single 'A+B' hit${f.n_ab_hits === 1 ? '' : 's'} sit at the origin and are counted with shower B.`
    : '';

  const xy = `${payload.slab.note} ${base} ${colourSentence(panels.xy, rho, rho.ref?.xy)} `
    + `${windowPhrase(fit, 'xy', [['col', sym.x], ['row', sym.y]])}; ${outside('xy')}.${provisional}`
    + `${floorSentence(panels.xy, continuous, floor)}${kernel('xy')}`
    + `${centroids ? ` ${centroids}` : ''}${offset}${splat}${combText}${ab}`;

  let direction;
  if (kind === 'local') {
    direction = " w is each shower's incident direction by construction; no ensemble axis or Rayleigh "
      + 'statistic is drawn because none could carry information.';
  } else {
    const paths = payload.overlays?.trajectories || [];
    const limit = payload.overlays?.max_trajectory_events ?? 50;
    if (paths.length) {
      direction = ` Dashed lines are the ${paths.length} individual incident directions, drawn from the `
        + "origin along each event's laboratory (θ, φ) — magenta for shower A, blue for shower B.";
    } else {
      const r = f.coherence?.r_a;
      direction = ' No averaged direction: the azimuth keeps its laboratory distribution '
        + `(${Number.isFinite(r) ? `R̄ = ${r.toFixed(3)}` : 'near-uniform'}), so its mean would point in an `
        + `arbitrary direction; individual directions are drawn for ${limit} events or fewer.`;
    }
  }
  const depth = kind === 'trans'
    ? " Depth counts each shower's own sampling layers from its first."
    : ` Depth w is binned at the ${num(f.depth?.pitch_mm, 1)} mm layer pitch and never smoothed.`;
  const depthRef = (id) => colourSentence(panels[id], rho, rho.ref?.depth, ' (shared by both depth panels)');
  return {
    xy,
    yz: `Transverse spread (${sym.y}) against depth (${sym.z}). ${depthRef('yz')} `
      + `${windowPhrase(fit, 'yz', [['row', sym.y]])}; ${outside('yz')}.${provisional}`
      + `${floorSentence(panels.yz, continuous, floor)}${kernel('yz')}${depth}${direction}${aspect('yz')}`,
    xz: `Lateral profile (${sym.x}) against depth (${sym.z}). ${depthRef('xz')} `
      + `${windowPhrase(fit, 'xz', [['row', sym.x]])}; ${outside('xz')}.${provisional}`
      + `${floorSentence(panels.xz, continuous, floor)}${kernel('xz')}${depth}${direction}${aspect('xz')}`,
  };
}

/**
 * Footnotes for the laboratory frame.
 *
 * The depth panels state plainly why an averaged trajectory is absent. The
 * mean resultant length of the incident azimuth is ~0.01 over the full
 * dataset, so a single "average direction" line would point somewhere
 * arbitrary; quoting the measured number on the page is what keeps the
 * omission honest rather than merely silent.
 */
export function labFootnotes(payload) {
  const overlays = payload.overlays || {};
  const resolution = payload.meta?.resolution || {};
  const stagger = payload.meta?.stagger || {};
  // The staggered-lattice comb is detector segmentation, not shower structure.
  // Saying so on the panel itself matters more than saying it in a banner,
  // because the panel is what gets screenshotted into a discussion.
  const combNote = stagger.staggered && resolution.mode === 'native' ? ` ⚠ ${stagger.note}` : '';
  const xy = `${payload.slab.note} Diamond marks shower A, circle shower B; the dashed `
    + 'line is the transverse separation between the ground-truth voxel-weighted '
    + `entry centroids.${combNote}`;

  const coherence = overlays.coherence || {};
  const paths = overlays.trajectories || [];
  const limit = overlays.max_trajectory_events ?? 50;
  let direction;
  if (paths.length) {
    direction =
      ` Dashed lines are the ${paths.length} individual incident trajectories, `
      + "projected from each event's centroid and (θ, φ) — magenta for shower A, "
      + 'blue for shower B. The ensemble shower axis is withheld at this size: '
      + 'averaging the transverse position of a handful of showers that sit in '
      + 'different places has no common centre to converge on.';
  } else {
    const r = coherence.r_a;
    const spread = Number.isFinite(r) ? `R̄ = ${r.toFixed(3)}` : 'near-uniform';
    direction =
      ' Solid lines are the energy-weighted shower axes measured from the binned '
      + 'data on screen — magenta for shower A, blue for shower B. Individual '
      + `trajectories are drawn only for selections of ${limit} events or fewer; `
      + `this one holds ${formatInt(payload.selection?.n_events)}. No single averaged `
      + 'trajectory is drawn either: the incident azimuth is near-uniform '
      + `(${spread}), so its mean would point in an arbitrary direction.`;
  }
  return {
    xy,
    yz: `Transverse spread against calorimeter depth.${direction}`,
    xz: 'Lateral profile against depth, sharing the YZ colour scale so the two may '
      + `be read against one another.${direction}`,
  };
}

/** The three footnotes of any projections payload. */
export function footnotes(payload, { isometric = {} } = {}) {
  const kind = kindOf(payload);
  if (kind === 'canonical') return canonicalFootnotes(payload, { isometric });
  if (kind === 'trans' || kind === 'local') return showerFootnotes(payload, { isometric });
  return labFootnotes(payload);
}

/**
 * The mark legend of an exported co-registered figure.
 *
 * Same wording as the on-screen footnote, and the centroid sets named by the
 * same `centroidLegend`, so the screen, the footnote and the figure describe
 * one set of marks.
 */
export function exportLegend(panelId, payload) {
  const kind = kindOf(payload);
  if (kind === 'trans' || kind === 'local') {
    if (panelId === 'xy') {
      const centroids = centroidLegend(payload?.centroids);
      return `${centroids ? `${centroids} ` : ''}The A–B offset of the superimposed centroids is not a separation.`;
    }
    if (kind === 'local') return 'w is the incident direction by construction; no direction is drawn.';
    return (payload?.overlays?.trajectories || []).length
      ? 'Dashed lines: individual incident directions from the origin along each event’s laboratory (θ, φ).'
      : 'No averaged direction is drawn: the azimuth keeps its laboratory distribution.';
  }
  const axes = 'dashed lines: the two ensemble shower axes; shaded wedge: sample spread of per-event '
    + 'slopes; thin envelope: 95% t-interval of the mean; rules: front and back faces.';
  if (panelId === 'xy') {
    const centroids = centroidLegend(payload?.centroids);
    return 'Open diamond and circle: A and B anchors at ∓⟨D_entry⟩/2; faint bar: sample spread (SD) '
      + 'of D_entry/2 across events; thin dashed rule: the mean entry separation.'
      + (centroids ? ` ${centroids}` : '');
  }
  if (panelId === 'yz') {
    return `Open circle: both anchors, projected onto one point; ${axes}`;
  }
  return 'Open diamond and circle at z′ = 0: A and B anchors, with the faint spread bar; '
    + `${axes}`;
}

/** The energy panel's network sentence, from the payload's `meta.network`. */
export function energyNetworkSentence(payload) {
  const network = payload?.meta?.network;
  if (!network) return '';
  return `Reconstructed by the ${FRAME_WORDS[network.frame] ?? network.frame}-frame segmentation `
    + 'network in every model view; D is the laboratory separation.';
}
