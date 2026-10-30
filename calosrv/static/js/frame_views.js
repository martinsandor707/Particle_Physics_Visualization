/* What each reference frame says about itself: titles, captions, footnotes.
 *
 * Pure and DOM-free, so every sentence can be checked under Node. `main.js`
 * writes the strings; nothing here touches the page.
 *
 * Four frames share three spatial panels:
 *
 * - `lab`: the Absolute view, detector coordinates as recorded.
 * - `canonical`: Separation-Aligned (D-Frame), Translated: every event
 *   co-registered by one rigid-body motion onto its entry midpoint, the A→B
 *   separation along +x′, which the entry panel writes as D.
 * - `local`: Separation-Aligned (D-Frame), Local: each shower moved to its
 *   own entry point P₀ and rotated by its own R(θ, φ), so every incident
 *   direction is +w.
 * - `trans`: the legacy per-shower translated frame, P₀ without rotation;
 *   opened by a #frame=trans link or a saved default only.
 *
 * The three co-registered frames share the canonical renderer and so its
 * payload blocks (`fit`, `rho`, `reconstruction`, `comb`); what differs - the
 * splat, the depth axis, the overlays, what a centroid offset means - is read
 * from the payload's `frame` block and worded here per kind.
 */

import {
  formatInt, formatSci, floorLabel, formatSigned, typographic, LIGHT_FIELD_FADE_DECADES,
} from './scale.js';
import { FRAME_SYMBOLS, SEPARATION_AXIS } from './axis_symbols.js';
import { beyondGridSentence, ordinal, showersPerEvent } from './export/disclosure.js';
import { displayOf, kernelPhrase } from './export/caption.js';
import { centroidLegend, frameMeanOverflowText } from './panels/canonical_overlays.js';
import { isPrintTheme, onLightCard } from './panels/chart_panel.js';

export const COREGISTERED = ['canonical', 'trans', 'local'];

/** The frame kind of a projections payload: `lab` unless it carries a frame block. */
export function kindOf(payload) {
  const kind = payload?.frame?.kind;
  return COREGISTERED.includes(kind) ? kind : 'lab';
}

export const FRAME_VIEWS = {
  lab: {
    coregistered: false,
    symbols: FRAME_SYMBOLS.lab,
    titles: {
      xy: 'XY Projection — Shower Entry',
      yz: 'YZ Projection — Longitudinal Evolution',
      xz: 'XZ Projection — Lateral Profile',
    },
    caption:
      'Absolute frame: detector coordinates as recorded. The depth panels draw individual '
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
    symbols: FRAME_SYMBOLS.canonical,
    titles: {
      xy: 'D–Y′ Projection — Shower Entry, Separation-Aligned (D-Frame)',
      yz: 'Y′Z′ Projection — Longitudinal Evolution, Separation-Aligned (D-Frame)',
      xz: 'X′Z′ Projection — Lateral Profile, Separation-Aligned (D-Frame)',
    },
    caption:
      'Separation-Aligned, Translated: every selected event is moved by one rigid-body '
      + 'motion: the midpoint of the two back-projected entry points goes to the origin, '
      + 'the A→B separation to +x′ — written D on the entry panel — and the front face to '
      + 'z′ = 0. Panels show the ensemble-averaged energy density, and two ensemble axes '
      + 'replace individual trajectories.',
    displayLabels: {
      native: 'Native Grid <span class="muted">(raw 20 mm bins, audit)</span>',
      continuous: 'Continuous Field <span class="muted">(kernel reconstruction)</span>',
    },
    resolutionHint:
      'R sets the display bins across the D–Y′ window; the kernel, not R, sets the resolution — '
      + 'no detail exists below the 20 mm grid or the 48 mm cell. Depth stays at the native layers.',
  },
  trans: {
    coregistered: true,
    symbols: FRAME_SYMBOLS.trans,
    titles: {
      xy: 'Δx–Δy Projection — Superimposed Shower Entry, per-shower translated (legacy)',
      yz: 'Δy–Δz Projection — Longitudinal Evolution, per-shower translated frame (legacy)',
      xz: 'Δx–Δz Projection — Lateral Profile, per-shower translated frame (legacy)',
    },
    caption:
      "Legacy per-shower translated frame (a #frame=trans link or a saved default): every "
      + "hit is moved by its own shower's entry point P₀ (the energy-weighted x, y "
      + 'centroid of its first populated layer, at that layer’s z), without rotation, so both '
      + 'showers of every event sit at the origin. D stays the absolute-frame 3-D centroid '
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
    symbols: FRAME_SYMBOLS.local,
    titles: {
      xy: 'u–v Projection — Shower-fixed Entry, Separation-Aligned (D-Frame), Local',
      yz: 'v–w Projection — Longitudinal Evolution, Separation-Aligned (D-Frame), Local',
      xz: 'u–w Projection — Lateral Profile, Separation-Aligned (D-Frame), Local',
    },
    caption:
      "Separation-Aligned, Local: each shower is moved to its own entry point P₀, then rotated "
      + "by its own R(θ, φ): "
      + 'u and v are the lateral spread, w the depth along the incident direction. w is the '
      + 'incident direction by construction, so no direction overlay is drawn. D stays the '
      + 'absolute-frame 3-D centroid distance.',
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

/* A single-shower experiment's per-shower frames say what they do without a
 * partner shower or a separation D: every event holds one shower. */
const SINGLE_CAPTIONS = {
  trans: "Translated: every hit is moved by its own shower's entry point P₀ (the energy-weighted x, y "
    + 'centroid of its first populated layer, at that layer’s z), without rotation, so every shower '
    + 'sits at the origin. The depth panels draw individual incident directions from the origin for '
    + '50 events or fewer; no averaged direction is drawn.',
  local: "Shower-Aligned, Local: each shower is moved to its own entry point P₀, then rotated by its own "
    + 'R(θ, φ): u and v are the lateral spread, w the depth along the incident direction. w is the '
    + 'incident direction by construction, so no direction overlay is drawn.',
};

/**
 * The sidebar caption of a frame. `nShowers` is the experiment's showers per
 * event (capabilities `n_showers`); a single-shower experiment's per-shower
 * frames are worded without a partner shower or D.
 */
export function frameCaption(kind, nShowers = 2) {
  if (nShowers === 1 && SINGLE_CAPTIONS[kind]) return SINGLE_CAPTIONS[kind];
  if (nShowers === 1 && kind === 'lab') {
    return 'Absolute frame: detector coordinates as recorded, one shower per event. The depth panels '
      + 'draw individual trajectories for selections of 50 events or fewer, otherwise the centre of '
      + 'deposited energy per layer; no averaged direction is drawn in this frame.';
  }
  return frameView(kind).caption;
}

/* A single-shower experiment's per-shower frames, titled without the D-frame
 * a single shower cannot have (its Translated is the per-shower translated
 * frame, its aligned view Shower-Aligned). */
const SINGLE_TITLES = {
  trans: {
    xy: 'Δx–Δy Projection — Shower Entry, Translated',
    yz: 'Δy–Δz Projection — Longitudinal Evolution, Translated',
    xz: 'Δx–Δz Projection — Lateral Profile, Translated',
  },
  local: {
    xy: 'u–v Projection — Shower-fixed Entry, Shower-Aligned, Local',
    yz: 'v–w Projection — Longitudinal Evolution, Shower-Aligned, Local',
    xz: 'u–w Projection — Lateral Profile, Shower-Aligned, Local',
  },
};

/** A panel's title; `nShowers` (capabilities `n_showers`) words a single shower's frames. */
export function panelTitle(id, kind, nShowers = 2) {
  if (nShowers === 1 && SINGLE_TITLES[kind]) return SINGLE_TITLES[kind][id];
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
const FRAME_WORDS = { absolute: 'absolute (detector)', trans: 'per-shower translated', local: 'local' };

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

/** The XY tag of a per-shower frame: N events and 2N superimposed showers (N showers for one per event). */
export function showerTag(frame, nShowers = 2) {
  if (!(frame?.n_events > 0)) return '';
  if (nShowers === 1) {
    const n = frame.n_showers ?? frame.n_events;
    return `N = ${formatInt(n)} shower${n === 1 ? '' : 's'}`;
  }
  return `N = ${formatInt(frame.n_events)} · ${formatInt(frame.n_showers)} showers`;
}

/* --------------------------------------------------------- channel caption -- */

/**
 * The channel caption.
 *
 * `frame` is the interface frame (lab | trans | local | canonical); the CAM
 * column is the payload's own `meta.cam.column` when one is in hand, else
 * derived from the model and the frame's network (the D-frame uses
 * the absolute networks).
 */
export function channelCaption({ channel, model = 'segmentation', frame = 'lab', payload = null,
  display = null, weighting = 'energy', nShowers = 2 }) {
  const kind = frame;
  const coregistered = COREGISTERED.includes(kind);
  const pf = kindOf(payload) === kind ? payload?.frame : null;
  const floor = floorLabel({ floor_ratio: pf?.reconstruction?.floor_ratio ?? 1e-3 });
  const network = NETWORK_FRAME[kind] ?? 'absolute';
  const cam = channel.startsWith('shapcam') ? 'shapcam' : 'gradcam';
  // The payload's own column and note only when it holds this channel and
  // network: right after a switch the last payload still describes the old one.
  const matching = payload?.meta?.channel === channel && payload?.meta?.model === model;
  const cam_meta = matching ? payload.meta.cam : null;
  const column = cam_meta?.column ?? `${model}_${network}_${cam}`;
  const lead = `${MODEL_WORDS[model] ?? model} network, ${FRAME_WORDS[network]} frame (${column}):`;
  const normalisation = cam_meta?.note ?? CAM_NORMALISATION;
  const mean = weighting === 'count' ? 'count-weighted mean' : 'energy-weighted mean';
  const mode = pf?.reconstruction?.display ?? display;

  if (channel === 'density') {
    if (!coregistered) {
      // On the light card the highest cell is the darkest, so it is named by its value there.
      return 'Summed deposited energy per cell, on a logarithmic scale spanning six decades below the '
        + `${onLightCard() && !isPrintTheme() ? 'highest-energy' : 'brightest'} cell.`;
    }
    const basis = pf?.rho?.basis ?? 'raw 20 mm-grid peak';
    const unit = unitText(payload?.panels?.xy?.rho_unit);
    const both = (kind === 'trans' || kind === 'local') && nShowers !== 1
      ? ' Both showers of every event are superimposed, so ⟨ρ⟩ sums the two.' : '';
    return `Average hit density ⟨ρ⟩ = ΣE / (N·ΔA) in ${unit}, drawn as a.u. relative to the stated `
      + `reference peak on a three-decade logarithmic ramp. Bins below ${floor} of ρ_ref are not drawn and the `
      + `${fadeSpan()} fades out; ρ_ref is the ${basis}.${both}`;
  }

  let body;
  if (channel === 'gradcam') {
    body = `${lead} ${mean} Grad-CAM attention of the hits in each bin, fixed 0–1 linear scale.`;
  } else if (channel === 'shapcam') {
    // The light screen's PuOr arms darken outwards; the dark screen's folded ones brighten.
    const outwards = onLightCard() && !isPrintTheme() ? 'darker' : 'brighter';
    body = `${lead} ${mean} Shap-CAM attribution, symmetric ${typographic('-1')}…+1 linear scale on `
      + `ColorBrewer PuOr (orange negative, purple positive, ${outwards} with |value|); nothing is clipped.`;
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
    const largest = mask.max_is_magnitude
      ? 'masked attribution of largest magnitude' : 'largest masked attention';
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
  return ` Bins below ${floor} of ρ_ref are not drawn${counts}; the ${fadeSpan()} fades to `
    + 'transparent, so the edge of the colour is the display floor, not the edge of the shower.';
}

/**
 * The stretch above a relative ramp's display floor that fades in, as the
 * captions word it: the bottom half decade, and on the light screen the 0.8
 * decade its rasters fade over (scale.js `LIGHT_FIELD_FADE_DECADES`).
 */
function fadeSpan() {
  return onLightCard() && !isPrintTheme()
    ? `${LIGHT_FIELD_FADE_DECADES} decade above that floor` : 'bottom half decade';
}

/** The colour sentence of a co-registered panel, by the quantity it shows. */
function colourSentence(panel, rho, reference, shared = '', weighting = 'energy') {
  const scale = panel?.scale || {};
  const mean = weighting === 'count' ? 'count-weighted mean' : 'energy-weighted mean';
  const unit = unitText(panel?.rho_unit);
  const ref = (value) => `${formatSci(value, 3)} ${unit}`;
  switch (scale.quantity) {
    case 'gradcam':
      return `Colour: ${mean} Grad-CAM attention on a fixed 0–1 scale.`;
    case 'shapcam':
      return `Colour: ${mean} Shap-CAM attribution on a symmetric ${typographic('-1')}…+1 scale `
        + '(PuOr: orange negative, purple positive); nothing is clipped.';
    case 'gradcam_energy':
      return `Colour: Σ E·Grad-CAM per event and mm², relative to this selection's raw-grid peak `
        + `${ref(scale.ref)}${shared}.`;
    case 'shapcam_energy':
      return `Colour: Σ E·Shap-CAM per event and mm² (signed log), relative to this selection's raw-grid `
        + `peak |value| ${ref(scale.ref)}${shared}; Σ E·Shap-CAM drawn in this window: `
        + `${formatSci(scale.positive_total, 3)} GeV positive, ${formatSci(scale.negative_total, 3)} GeV negative.`;
    default: {
      const norm = rho.norm === 'dataset'
        ? `the dataset peak${rho.ref_k && rho.ref_k !== rho.selection_k ? ` (measured with ${rho.ref_k} × ${rho.ref_k} sub-deposits per cell against ${rho.selection_k} × ${rho.selection_k} here)` : ''}`
        : 'this selection’s own peak (autoscaled; switch the density normalisation to compare colours across selections)';
      return `Colour: average hit density (a.u.) relative to ρ_ref = ${ref(reference)}${shared}, ${norm}.`;
    }
  }
}

/**
 * Which entry-anchor definition the D-frame is built on, and how far the
 * other lands from it over the selection: median and p90 per shower, and the
 * showers more than one cell footprint apart. '' for a payload that carries
 * no residual (an empty frame, or one older than the measurement).
 */
export function anchorSentence(frame) {
  const choice = frame?.anchor_choice;
  const residual = frame?.anchor_residual;
  if (!choice) return '';
  const used = choice === 'p0'
    ? 'each shower’s first-layer entry point P₀ (the notebook’s origin), back-projected to the front face'
    : 'each shower’s 3-D centroid, back-projected to the front face';
  const other = choice === 'p0' ? 'the back-projected 3-D centroid' : 'the back-projected first-layer entry point P₀';
  let text = ` Anchor: ${used}.`;
  const parts = [];
  for (const [key, label] of [['a', 'A'], ['b', 'B']]) {
    const block = residual?.[key];
    if (!block || !Number.isFinite(block.median)) continue;
    let part = `shower ${label} median ${num(block.median)} mm`;
    if (Number.isFinite(block.p90)) part += `, p90 ${num(block.p90)} mm`;
    if (Number.isFinite(residual.footprint_mm) && Number.isFinite(block.over_footprint)) {
      part += `, ${formatInt(block.over_footprint)} more than one cell footprint apart`;
    }
    parts.push(part);
  }
  if (parts.length) {
    text += ` The other definition, ${other}, lands a transverse distance away of ${parts.join('; ')}`
      + ` (N = ${formatInt(residual.n)}); the choice is the sidebar’s Entry anchor control.`;
  }
  return text;
}

/**
 * The sidebar's notices for a projections response, as a new array.
 *
 * The per-shower frames state their coordinate source once, in
 * `frame.coordinates.note`; the server no longer repeats it in `meta.notices`
 * (review R-4). It goes back where the server put it: in the frame scope,
 * after the comb note and the floor notice that the server always sends
 * after it, or last when the comb note is absent. A response that still
 * carries the copy is returned unchanged.
 */
export function frameNotices(payload) {
  const notices = [...(payload?.meta?.notices ?? [])];
  const note = payload?.frame?.coordinates?.note;
  if (typeof note !== 'string' || !note || notices.some((n) => n.text === note)) return notices;
  const comb = payload.frame?.comb?.note;
  const after = comb ? notices.findIndex((n) => n.scope === 'frame' && n.text === comb) : -1;
  const at = after >= 0 ? Math.min(notices.length, after + 2) : notices.length;
  notices.splice(at, 0, { scope: 'frame', text: note });
  return notices;
}

/** The per-shower frames' coordinate source and residual, as the payload states them. */
export function coordinatesSentence(frame) {
  const block = frame?.coordinates;
  return typeof block?.note === 'string' && block.note ? ` ${block.note}` : '';
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
  const beyond = beyondGridSentence(f);
  const beyondGrid = beyond ? ` ${beyond}` : '';
  return { f, rho, fit, panels, continuous, floor, outside, kernel, aspect, provisional, combText, beyondGrid };
}

/** The entry panel's horizontal axis, named once for every reader of the D-frame. */
const D_AXIS_SENTENCE = ' The horizontal axis is written D: the signed x′ coordinate along the A→B '
  + 'separation; D itself (the slider) stays the absolute-frame 3-D centroid distance.';

/**
 * Footnotes for the Separation-Aligned (D-Frame), Translated view.
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
      `Separation-Aligned (D-Frame), Translated: no selected event has a defined frame `
      + `(${formatInt(f.n_selected)} selected, ${formatInt(f.n_excluded_no_frame)} without a shower-A `
      + 'centroid or direction). The panels are empty and no ensemble axis is drawn.';
    return { xy: `${payload.slab.note} ${empty}`, yz: empty, xz: empty };
  }
  const p = coregisteredParts(payload, isometric);
  const { rho, fit, panels, continuous, floor, outside, kernel, aspect, provisional, combText, beyondGrid } = p;

  // The interval is named: at N = 2 the Student-t 95% half-width is 12.7
  // standard errors, so a bare "±" would mean whatever the reader assumes.
  const ci = Number.isFinite(f.d_entry?.ci95_half)
    ? ` (95% t-interval of the mean ± ${num(f.d_entry.ci95_half)} mm)`
    : '';
  const base =
    `Separation-Aligned (D-Frame), Translated: N = ${formatInt(f.n_events)} co-registered event${f.n_events === 1 ? '' : 's'}`
    + (f.n_excluded_no_frame ? ` (${formatInt(f.n_excluded_no_frame)} selected event(s) excluded: no shower-A centroid or direction)` : '')
    + `; ⟨D_entry⟩ = ${num(f.d_entry?.mean)} mm at the front face${ci}, ⟨D⟩ = ${num(f.d_dataset?.mean)} mm (dataset, 3-D centroid distance).`;
  const k = f.subsample_k;
  const splat = ` Cells (${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm) are splatted as ${k} × ${k} sub-deposits on a ${f.pitch_mm} mm grid.`;
  const anchor = anchorSentence(f);
  const ill = f.n_ill_conditioned
    ? ` ${formatInt(f.n_ill_conditioned)} event(s) enter closer than ${f.ill_conditioned_threshold_mm} mm apart, so their orientation is effectively random: their energy enters ⟨ρ⟩ averaged over azimuth and their directions enter R̄′, the Rayleigh p and the dispersion band as noise.`
    : '';
  const centroids = centroidLegend(payload.centroids);

  const xy =
    `${payload.slab.note} ${base}${D_AXIS_SENTENCE} ${colourSentence(panels.xy, rho, rho.ref?.xy, '', payload.meta?.weighting)} `
    + `${windowPhrase(fit, 'xy', [['col', SEPARATION_AXIS], ['row', 'y′']])}; ${outside('xy')}.${beyondGrid}${provisional}`
    + `${floorSentence(panels.xy, continuous, floor)}${kernel('xy')} `
    + 'Open diamond and circle: the A and B anchors at D = ∓⟨D_entry⟩/2; faint bar: sample spread (SD) of '
    + 'D_entry/2 across events; thin dashed rule: the mean entry separation (hover for ⟨D_entry⟩ with its '
    + `95% t-interval).${anchor}${centroids ? ` ${centroids}` : ''}${offsetsText(f.anchor_offsets)}${splat}${combText}${ill}`;

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
  const geometry = f.n_events >= 2 ? geometrySentence(payload.overlays?.pointing) : '';
  const anchorsText = {
    yz: ' The open circle at the origin stands for both anchors, which this panel projects onto one point.',
    xz: ' Open diamond and circle at z′ = 0: the A and B anchors, with a faint bar for the sample spread '
      + '(SD) of D_entry/2.',
  };
  const depthRef = (id) => colourSentence(panels[id], rho, rho.ref?.depth, ' (shared by both depth panels)', payload.meta?.weighting);

  return {
    xy,
    yz: `Transverse spread normal to the shower plane against depth. ${depthRef('yz')} `
      + `${windowPhrase(fit, 'yz', [['row', 'y′']])}; ${outside('yz')}.${beyondGrid}${provisional}`
      + `${floorSentence(panels.yz, continuous, floor)}${kernel('yz')}`
      + `${anchorsText.yz}${marks}${geometry} ${axesText}${aspect('yz')}`,
    xz: `Lateral profile along the separation against depth. ${depthRef('xz')} `
      + `${windowPhrase(fit, 'xz', [['row', 'x′']])}; ${outside('xz')}.${beyondGrid}${provisional}`
      + `${floorSentence(panels.xz, continuous, floor)}${kernel('xz')}`
      + `${anchorsText.xz}${marks}${geometry} ${axesText}${aspect('xz')}`,
  };
}

/**
 * Footnotes for the per-shower frames: Separation-Aligned › Local, and the
 * legacy per-shower translated frame.
 *
 * Both superimpose the two showers of every event at the origin, so the voxel
 * centroid pair measures an A-B *offset* of two ensembles each relative to its
 * own entry point - never a separation, which stays the absolute-frame D.
 */
export function showerFootnotes(payload, { isometric = {}, nShowers = null } = {}) {
  const f = payload.frame;
  const kind = f.kind;
  const sym = frameView(kind).symbols;
  const single = showersPerEvent(payload, nShowers) === 1;
  const title = single
    ? (kind === 'trans' ? 'Translated (each shower from its own entry point)' : 'Shower-Aligned, Local')
    : (kind === 'trans' ? 'Per-shower translated frame (legacy)' : 'Separation-Aligned (D-Frame), Local');
  if (!(f.n_events > 0)) {
    const empty = single
      ? `${title}: no selected shower has a defined entry point and incident direction `
        + `(${formatInt(f.n_selected)} selected); the panels are empty.`
      : `${title}: no selected event has a defined A-B separation `
        + `(${formatInt(f.n_selected)} selected); the panels are empty.`;
    return { xy: `${payload.slab.note} ${empty}`, yz: empty, xz: empty };
  }
  const p = coregisteredParts(payload, isometric);
  const { rho, fit, panels, continuous, floor, outside, kernel, aspect, provisional, combText, beyondGrid } = p;

  const half = f.d_dataset?.ci95_half;
  // A narrow D window has a sub-millimetre interval; "± 0 mm" would claim none.
  const ci = Number.isFinite(half)
    ? ` ± ${num(half, half < 10 ? 1 : 0)} mm (95% t-interval of the mean)` : '';
  const base = single
    ? `${title}: N = ${formatInt(f.n_showers ?? f.n_events)} shower${(f.n_showers ?? f.n_events) === 1 ? '' : 's'}, `
      + 'one per event, superimposed at their own entry points'
      + (f.n_excluded_no_frame ? ` (${formatInt(f.n_excluded_no_frame)} selected event(s) excluded: no entry point or incident direction)` : '')
      + '.'
    : `${title}: N = ${formatInt(f.n_events)} event${f.n_events === 1 ? '' : 's'}, `
      + `${formatInt(f.n_showers)} showers superimposed at their own entry points`
      + (f.n_excluded_no_frame ? ` (${formatInt(f.n_excluded_no_frame)} selected event(s) excluded: no A-B separation)` : '')
      + `; D is the absolute-frame 3-D centroid distance, ⟨D⟩ = ${num(f.d_dataset?.mean)} mm${ci}.`;
  const centroids = centroidLegend(payload.centroids);
  const overflow = frameMeanOverflowText(payload);
  const offset = single ? '' : ' The A–B offset of the superimposed centroids (offset_mm) is not a separation.';
  const splat = kind === 'trans'
    ? ` Each cell's ${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm footprint is `
      + `integrated exactly by area-weighted box overlap on a ${f.pitch_mm} mm grid.`
    : ` Each cell's ${num(f.footprint_mm?.[0], 1)} × ${num(f.footprint_mm?.[1], 1)} mm × `
      + `${num(f.depth?.pitch_mm, 1)} mm volume is split into ${f.splat?.k} × ${f.splat?.k} × ${f.splat?.k_z} `
      + `sub-deposits rotated with its shower, on a ${f.pitch_mm} mm grid.`;
  const ab = f.n_ab_hits
    ? ` ${formatInt(f.n_ab_hits)} single 'A+B' hit${f.n_ab_hits === 1 ? '' : 's'} sit at the origin and are counted with shower B.`
    : '';

  const xy = `${payload.slab.note} ${base} ${colourSentence(panels.xy, rho, rho.ref?.xy, '', payload.meta?.weighting)} `
    + `${windowPhrase(fit, 'xy', [['col', sym.x], ['row', sym.y]])}; ${outside('xy')}.${beyondGrid}${provisional}`
    + `${floorSentence(panels.xy, continuous, floor)}${kernel('xy')}`
    + `${centroids ? ` ${centroids}` : ''}${overflow ? ` ${overflow}` : ''}${offset}${splat}${coordinatesSentence(f)}${combText}${ab}`;

  let direction;
  if (kind === 'local') {
    direction = " w is each shower's incident direction by construction; no ensemble axis or Rayleigh "
      + 'statistic is drawn because none could carry information.';
  } else {
    const paths = payload.overlays?.trajectories || [];
    const limit = payload.overlays?.max_trajectory_events ?? 50;
    if (paths.length) {
      direction = ` Dashed lines are the ${paths.length} individual incident directions, drawn from the `
        + (single
          ? "origin along each shower's absolute-frame (θ, φ), one per event."
          : "origin along each event's absolute-frame (θ, φ) — magenta for shower A, blue for shower B.");
    } else {
      const r = f.coherence?.r_a;
      direction = ' No averaged direction: the azimuth keeps its absolute-frame distribution '
        + `(${Number.isFinite(r) ? `R̄ = ${r.toFixed(3)}` : 'near-uniform'}), so its mean would point in an `
        + `arbitrary direction; individual directions are drawn for ${limit} events or fewer.`;
    }
  }
  const depth = kind === 'trans'
    ? " Depth counts each shower's own sampling layers from its first."
    : ` Depth w is binned at the ${num(f.depth?.pitch_mm, 1)} mm layer pitch and never smoothed.`;
  const depthRef = (id) => colourSentence(panels[id], rho, rho.ref?.depth, ' (shared by both depth panels)', payload.meta?.weighting);
  return {
    xy,
    yz: `Transverse spread (${sym.y}) against depth (${sym.z}). ${depthRef('yz')} `
      + `${windowPhrase(fit, 'yz', [['row', sym.y]])}; ${outside('yz')}.${beyondGrid}${provisional}`
      + `${floorSentence(panels.yz, continuous, floor)}${kernel('yz')}${depth}${direction}${aspect('yz')}`,
    xz: `Lateral profile (${sym.x}) against depth (${sym.z}). ${depthRef('xz')} `
      + `${windowPhrase(fit, 'xz', [['row', sym.x]])}; ${outside('xz')}.${beyondGrid}${provisional}`
      + `${floorSentence(panels.xz, continuous, floor)}${kernel('xz')}${depth}${direction}${aspect('xz')}`,
  };
}

/**
 * Footnotes for the Absolute (detector) frame.
 *
 * The depth panels state plainly why an averaged trajectory is absent. The
 * mean resultant length of the incident azimuth is ~0.01 over the full
 * dataset, so a single "average direction" line would point somewhere
 * arbitrary; quoting the measured number on the page is what keeps the
 * omission honest rather than merely silent.
 */
export function labFootnotes(payload, { nShowers = null } = {}) {
  const overlays = payload.overlays || {};
  const single = showersPerEvent(payload, nShowers) === 1;
  const resolution = payload.meta?.resolution || {};
  const stagger = payload.meta?.stagger ?? payload.frame?.comb ?? {};
  // The staggered-lattice comb is detector segmentation, not shower structure.
  // Saying so on the panel itself matters more than saying it in a banner,
  // because the panel is what gets screenshotted into a discussion.
  const combNote = stagger.staggered && resolution.mode === 'native' ? ` ⚠ ${stagger.note}` : '';
  const xy = single
    ? `${payload.slab.note} ${singleCentroidSentence(payload.centroids)}${combNote}`
    : `${payload.slab.note} Diamond marks shower A, circle shower B; the dashed `
      + 'line is the transverse separation between the ground-truth voxel-weighted '
      + `entry centroids.${combNote}`;

  const coherence = overlays.coherence || {};
  const paths = overlays.trajectories || [];
  const limit = overlays.max_trajectory_events ?? 50;
  let direction;
  if (paths.length) {
    direction =
      ` Dashed lines are the ${paths.length} individual incident trajectories, `
      + (single
        ? "projected from each shower's centroid along its (θ, φ), one per event. "
        : "projected from each event's centroid and (θ, φ) — magenta for shower A, "
          + 'blue for shower B. ')
      + 'The centre of deposited energy is withheld at this size: '
      + 'averaging the transverse position of a handful of showers that sit in '
      + 'different places has no common centre to converge on.';
  } else {
    const r = coherence.r_a;
    const spread = Number.isFinite(r) ? `R̄ = ${r.toFixed(3)}` : 'near-uniform';
    direction =
      ' Solid lines are the centres of deposited energy per depth layer, measured from the '
      + (single ? 'binned data on screen: a property of the ' : 'binned data on screen — magenta for shower A, blue for shower B: a property of the ')
      + 'summed picture, not a direction. Individual trajectories are drawn only for selections '
      + `of ${limit} events or fewer; this one holds ${formatInt(payload.selection?.n_events)}. `
      + 'No single averaged trajectory is drawn over the whole face: the incident azimuth is '
      + `near-uniform there (${spread}), so its mean would point in an arbitrary direction.`;
  }
  // Where the directions point, measured against each shower's own position:
  // the reason the azimuth is uniform, and what the windowed axis rests on.
  const pointing = overlays.pointing?.note ? ` ${overlays.pointing.note}` : '';
  // The energy-weighted CAM channels leave bins below their 10⁻³ floor
  // undrawn; the lab density ramp has no such floor and says nothing here.
  const floorOf = (id) => {
    const panel = payload.panels?.[id];
    const quantity = panel?.scale?.quantity;
    if (quantity !== 'gradcam_energy' && quantity !== 'shapcam_energy') return '';
    return floorSentence(panel, false, floorLabel({ floor_ratio: panel.scale.floor_ratio ?? 1e-3 }));
  };
  return {
    xy: `${xy}${floorOf('xy')}`,
    yz: `Transverse spread against calorimeter depth.${direction}${pointing}${floorOf('yz')}`,
    xz: 'Lateral profile against depth, sharing the YZ colour scale so the two may '
      + `be read against one another.${direction}${pointing}${floorOf('xz')}`,
  };
}

/* ----------------------------------------- the absolute frame's marks -- */

/** The legend line of an absolute-frame depth panel's marks. */
export function labLegend(payload, { nShowers = null } = {}) {
  const paths = payload?.overlays?.trajectories || [];
  const single = showersPerEvent(payload, nShowers) === 1;
  if (paths.length) {
    return `Dashed lines: the ${paths.length} individual incident trajectories, each from its event's `
      + (single ? '3-D shower centroid along (θ, φ), one per event.' : '3-D centroid along (θ, φ) — magenta shower A, blue shower B.');
  }
  return single
    ? 'Solid line: the centre of deposited energy per depth layer, a property of the summed picture, not a direction.'
    : 'Solid lines: the centre of deposited energy per depth layer — magenta shower A, blue shower B — '
      + 'a property of the summed picture, not a direction.';
}

/**
 * The absolute-frame entry panel's marks for one shower per event: the
 * centroid markers the payload names (CENTROID_STYLE), and why no separation
 * is drawn. Like the two-shower stars they are drawn without uncertainty
 * marks; the sentence says what each one is.
 */
export function singleCentroidSentence(centroids) {
  const names = Object.values(centroids || {})
    .filter((set) => set && set.a && typeof set.label === 'string')
    .map((set) => set.label);
  const marked = names.length ? `Markers: ${names.join('; ')}, each a point estimate without an uncertainty mark. ` : '';
  return `${marked}One shower per event, so no separation vector is drawn.`;
}

/**
 * The windowed ensemble axis (query/window_axis.py) as the drawer's legend
 * line: what the dashed line, the band and the envelope are.
 */
export function windowAxisLegend(block) {
  if (!block || !block.window) return '';
  const [lo, hi] = block.window;
  return `Windowed ensemble axis for ${block.axis ?? 'x'} ∈ [${num(lo, 0)}, ${num(hi, 0)}] mm: dashed line = `
    + 'the mean incident trajectory of the selected events whose entry point (3-D centroid back-projected '
    + 'to the front face) lies in the window; shaded band = the sample SD of their per-event trajectories '
    + 'at each depth; thin envelope = the Student-t 95% interval of the mean — two quantities, two marks. '
    + 'A faded axis means the mean lean lies within the fan: those showers go straight on average.';
}

/** The windowed axis's own disclosures: the server's per-shower notes and its rule. */
export function windowAxisDisclosures(block) {
  if (!block) return [];
  return [...(block.notes ?? []), block.rule ?? ''];
}

/**
 * What part of a slope dispersion is geometry. In detector coordinates the
 * incident directions point at the origin, so a shower's lean grows with
 * its radius; measured per selection (`overlays.pointing`).
 */
export function geometrySentence(pointing) {
  const sd = pointing?.a?.sd_deg;
  if (!Number.isFinite(sd)) return '';
  return ' Part of that spread is geometry: in detector coordinates the incident directions point at the '
    + `origin (residual ±${num(sd, 1)}° SD against the radial line through each shower A centroid), so `
    + 'showers at larger radius lean more, and the band mixes the spread of entry radii across events '
    + 'with anything physical.';
}

/** The three footnotes of any projections payload; `nShowers` is the experiment's showers per event. */
export function footnotes(payload, { isometric = {}, nShowers = null } = {}) {
  const kind = kindOf(payload);
  if (kind === 'canonical') return canonicalFootnotes(payload, { isometric });
  if (kind === 'trans' || kind === 'local') return showerFootnotes(payload, { isometric, nShowers });
  return labFootnotes(payload, { nShowers });
}

/**
 * The mark legend of an exported co-registered figure.
 *
 * Same wording as the on-screen footnote, and the centroid sets named by the
 * same `centroidLegend`, so the screen, the footnote and the figure describe
 * one set of marks.
 */
export function exportLegend(panelId, payload, { nShowers = null } = {}) {
  const kind = kindOf(payload);
  if (kind === 'trans' || kind === 'local') {
    if (panelId === 'xy') {
      const centroids = centroidLegend(payload?.centroids);
      if (showersPerEvent(payload, nShowers) === 1) return centroids;
      return `${centroids ? `${centroids} ` : ''}The A–B offset of the superimposed centroids is not a separation.`;
    }
    if (kind === 'local') return 'w is the incident direction by construction; no direction is drawn.';
    return (payload?.overlays?.trajectories || []).length
      ? 'Dashed lines: individual incident directions from the origin along each event’s absolute-frame (θ, φ).'
      : 'No averaged direction is drawn: the azimuth keeps its absolute-frame distribution.';
  }
  const axes = 'dashed lines: the two ensemble shower axes; shaded wedge: sample spread of per-event '
    + 'slopes; thin envelope: 95% t-interval of the mean; rules: front and back faces.';
  if (panelId === 'xy') {
    const centroids = centroidLegend(payload?.centroids);
    return 'Open diamond and circle: A and B anchors at D = ∓⟨D_entry⟩/2; faint bar: sample spread (SD) '
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
  return `Reconstructed by the segmentation network of the ${FRAME_WORDS[network.frame] ?? network.frame} `
    + 'frame in every model view; D is the absolute-frame separation.';
}

/* ----------------------------------------------- the Event Inspector -- */

/**
 * The reference notebook's row label for one shower of one event: cells,
 * deposited energy, the incident angles, P₀ and the principal-axis tilt.
 *
 * The tilt is the angle between the energy-weighted principal axis of the
 * cloud in the local frame and +w: the notebook's check that the rotation
 * did what it claims. It is printed, never drawn, and below three cells it is
 * untestable rather than zero.
 */
export function eventRowLabel(event) {
  const s = event?.shower;
  if (!s) return '';
  const p0 = Array.isArray(s.p0) && s.p0.length === 3
    ? `(${s.p0.map((v) => num(v, 1)).join(', ')}) mm` : '—';
  const axis = s.principal_axis;
  const tilt = axis && Number.isFinite(axis.tilt_deg)
    ? `principal axis ${num(axis.tilt_deg, 1)}° from +w`
    : 'principal axis untestable (fewer than 3 cells)';
  const label = s.label ?? String(s.key ?? '').toUpperCase();
  return `Event ${formatInt(event.event_number)}, shower ${label}: `
    + `${formatInt(s.n_hits)} cell${s.n_hits === 1 ? '' : 's'}, ${formatSci(s.energy_gev, 3)} GeV deposited, `
    + `θ = ${num(s.theta_deg, 1)}°, φ = ${num(s.phi_deg, 1)}°, P₀ = ${p0}, ${tilt}.`;
}

/** The event's own kinematics, and whether the current filters select it. */
export function eventSelectionLine(event) {
  if (!event || !Number.isFinite(event.event_number)) return '';
  const energy = (v) => (Number.isFinite(v) ? `${num(v, 2)} GeV` : '—');
  const d = Number.isFinite(event.d) ? `${num(event.d, 0)} mm` : 'undefined';
  return `Event ${formatInt(event.event_number)}: ${formatInt(event.n_hits)} hits in all, `
    + `E₁ = ${energy(event.e1)}, E₂ = ${energy(event.e2)}, D = ${d}; `
    + (event.in_selection
      ? 'inside the current selection.'
      : 'outside the current selection, drawn as asked; previous / next walk the selection.');
}

/**
 * What one frame of the Event Inspector draws, from the response's own
 * `splat` and `depth` blocks: how each cell's footprint reaches the raster,
 * and what the depth axis is.
 */
export function eventFrameSentence(payload, kind) {
  const frame = payload?.frames?.[kind];
  if (!frame) return '';
  const fp = Array.isArray(payload.footprint_mm) ? payload.footprint_mm : [];
  const footprint = fp.length >= 2 ? `${num(fp[0], 2)} × ${num(fp[1], 2)} mm` : 'its measured';
  const pitch = Number.isFinite(frame.splat?.pitch_mm) ? `${num(frame.splat.pitch_mm, 0)} mm` : 'the accumulation';
  const depth = frame.depth?.note ? `; depth is ${frame.depth.note}` : '';
  if (kind === 'lab') {
    return 'Original detector coordinates: the native lattice, one bin per populated cell, every layer '
      + `of the event projected (no entrance slab), cropped to the event's window${depth}.`;
  }
  if (kind === 'trans') {
    return `Translated only: every cell moved by −P₀ without rotation, its ${footprint} footprint `
      + `integrated onto a ${pitch} grid by exact area-weighted box overlap${depth}.`;
  }
  const k = Number.isFinite(frame.splat?.k) ? frame.splat.k : '—';
  const kz = Number.isFinite(frame.splat?.k_z) ? frame.splat.k_z : '—';
  const layer = fp.length >= 3 ? `${num(fp[2], 1)} mm` : 'one layer';
  return `Local: every cell moved by −P₀ and rotated by its shower's R(θ, φ) so the incident direction lies `
    + `along +w; each ${footprint} × ${layer} footprint is split into k × k × k_z = ${k} × ${k} × ${kz} `
    + `sub-deposits rotated with the shower and binned on a ${pitch} grid${depth}.`;
}

/* ----------------------------------------- the entry-anchor explainer -- */

/** The D-frame's two entry-anchor definitions, as the sidebar names them. */
const ANCHOR_NAMES = Object.freeze({
  backprojected: 'Back-projected 3-D centroid',
  p0: 'First-layer entry point P₀',
});

const para = (text) => ({ kind: 'p', text });
/* A formula carries its plain text and its TeX: main.js sets the TeX as
 * MathML through math.js, in the article's notation, and falls back to the
 * text where the compiler refuses it. */
const formula = (text, tex) => ({ kind: 'formula', text, tex });

/**
 * The methodology popup of the sidebar's Entry anchor control.
 *
 * How the Translated D-frame is built from two entry points, how each
 * definition finds them, how far apart the two land on the current
 * selection, and what switching changes. Returns `{title, current,
 * sections: [{heading, current, blocks: [{kind: 'p' | 'formula', text, tex?}]}]}`;
 * pure, so every sentence can be checked under Node, and main.js renders it
 * with text nodes.
 *
 * `choice` is the control's value and marks the definition in use;
 * `frame` is the last D-frame response's `frame` block, whose
 * `anchor_residual` - the distance between the two definitions, measured per
 * shower on the selection - does not depend on which one is in use. Without
 * a frame the definitions are still stated in full.
 *
 * Measured facts behind the wording: the file's `centroid_A_*` is the
 * energy-weighted 3-D centroid of the cells labelled A, and `centroid_B_*`
 * that of the cells labelled B and A+B (checked on production events with
 * and without shared cells, to 0.0002 mm); P₀ counts A+B cells for both
 * showers (ingest check `p0_definition`); the file records no true entry
 * point.
 */
export function anchorExplainer(frame = null, choice = null) {
  const current = choice === 'p0' || choice === 'backprojected'
    ? choice : (frame?.anchor_choice === 'p0' ? 'p0' : 'backprojected');

  const measured = [];
  const residual = frame?.anchor_residual;
  const a = residual?.a;
  const b = residual?.b;
  if (Number.isFinite(a?.median) && Number.isFinite(b?.median)) {
    let text = 'On this selection the two entry points of a shower lie a median '
      + `${num(a.median)} mm apart for shower A and ${num(b.median)} mm for shower B at the front face`;
    if (Number.isFinite(a.p90) && Number.isFinite(b.p90)) {
      text += ` (90th percentile ${num(a.p90)} and ${num(b.p90)} mm)`;
    }
    text += '.';
    if (Number.isFinite(residual.footprint_mm) && Number.isFinite(a.over_footprint)
      && Number.isFinite(b.over_footprint) && Number.isFinite(residual.n)) {
      const showers = (n, label) => `${formatInt(n)} ${label} shower${n === 1 ? '' : 's'}`;
      text += ` Of ${formatInt(residual.n)} events, ${showers(a.over_footprint, 'A')} and `
        + `${showers(b.over_footprint, 'B')} differ by more than one cell footprint `
        + `(${num(residual.footprint_mm, 1)} mm).`;
    }
    measured.push(para(text));
  } else {
    measured.push(para('The distance between the two is measured on every response of this view and '
      + 'printed in the entry panel’s Details drawer once the panels have loaded.'));
  }
  measured.push(para('The file records no true entry point, so neither definition can be checked '
    + 'against one: this distance is the size of the ambiguity, not the error of either.'));

  const sections = [
    {
      heading: 'What the anchor sets',
      current: false,
      blocks: [
        para('The Translated view moves every selected event by one rigid motion, built from two entry '
          + 'points on the calorimeter’s front face z = z_f: one for shower A, one for shower B. Their '
          + 'midpoint m becomes the origin, the direction from A’s entry point to B’s becomes +x′ '
          + '(written D on the entry panel), and z′ = z − z_f. With ψ the azimuth of that A→B line, '
          + 'every hit moves as'),
        formula('x′ = cos ψ · (x − m_x) + sin ψ · (y − m_y)\ny′ = −sin ψ · (x − m_x) + cos ψ · (y − m_y)',
          String.raw`\begin{aligned} x' &= \cos\psi\,(x - m_x) + \sin\psi\,(y - m_y) \\ `
          + String.raw`y' &= -\sin\psi\,(x - m_x) + \cos\psi\,(y - m_y) \end{aligned}`),
        para('Shower A then sits at D = −D_entry/2 and B at D = +D_entry/2, where D_entry is the distance '
          + 'between the two entry points. The two choices differ only in which point of each shower is '
          + 'taken as its entry point; the frame is built from it the same way.'),
      ],
    },
    {
      heading: `${ANCHOR_NAMES.backprojected} (default)`,
      current: current === 'backprojected',
      blocks: [
        para('Starts from the shower’s energy-weighted 3-D centroid c over all of its cells: the file’s '
          + 'centroid_A/B_x, _y, _z columns, where cells labelled A+B count with shower B. It lies inside '
          + 'the shower, well behind the front face, and is slid back to the front face along the '
          + 'shower’s own incident direction (θ, φ):'),
        formula('entry = (c_x, c_y) − (c_z − z_f) · tan θ · (cos φ, sin φ)',
          String.raw`\text{entry} = (c_x,\ c_y) - (c_z - z_{\mathrm f})\tan\theta\,(\cos\varphi,\ \sin\varphi)`),
        para('It uses every cell of the shower. Its weakness is the long extrapolation: wherever the '
          + 'shower’s energy sits off its incident line, that sideways offset is carried unchanged to '
          + 'the front face.'),
      ],
    },
    {
      heading: ANCHOR_NAMES.p0,
      current: current === 'p0',
      blocks: [
        para('Starts from P₀, the energy-weighted (x, y) centroid of the shower’s cells in its first '
          + 'populated layer, at that layer’s depth z₀; cells labelled A+B count for both showers. P₀ is '
          + 'the origin of the per-shower frames and of the reference notebook, and ingest verifies '
          + 'this definition to 0.01 mm. It is slid back the short distance from z₀ to the front face '
          + 'along the same direction:'),
        formula('entry = P₀ − (z₀ − z_f) · tan θ · (cos φ, sin φ)',
          String.raw`\text{entry} = P_0 - (z_0 - z_{\mathrm f})\tan\theta\,(\cos\varphi,\ \sin\varphi)`),
        para('It is the measured point nearest to where the particle entered and needs almost no '
          + 'extrapolation. Its weakness is that it rests on the cells of a single layer, which can be '
          + 'few.'),
      ],
    },
    { heading: 'How far apart they land', current: false, blocks: measured },
    {
      heading: 'What switching changes',
      current: false,
      blocks: [
        para('Switching moves the origin and the rotation ψ of every event, and with them every hit, '
          + 'every incident direction, D_entry, the anchor marks, the fitted panel windows and the '
          + 'ensemble axes. It does not change the selection, D on the slider (the 3-D distance between '
          + 'the two centroids in detector coordinates), the deposited energies or z′.'),
        para('Where an event’s two entry points lie closer than 80 mm, ψ is poorly determined under '
          + 'either definition; the entry panel’s Details drawer counts those events. The choice travels '
          + 'in the page link (anchor=p0) and in an exported figure’s file name.'),
      ],
    },
  ];
  return { title: 'Entry anchor of the D-frame', current, sections };
}
