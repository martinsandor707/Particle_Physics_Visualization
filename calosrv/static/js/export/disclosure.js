/* Disclosures for an exported figure, read from the payload's structured fields.
 *
 * ## Why these are not scraped off the page
 *
 * The live footnote already travels inside the figure (see caption.js), and
 * it is the right thing to carry because it is what the reader saw. But it is
 * prose assembled by `main.js` for the screen: a sentence can be shortened for
 * a narrow card, a number can be rounded for a tooltip, and a future edit to a
 * footnote would silently change what every exported figure says. The
 * disclosures CLAUDE.md section 2 makes mandatory - the clipping counts, the
 * percentile window and the energy it leaves out, the reference density a
 * colour is relative to, the ensemble statistics behind a drawn axis - are
 * numbers with a definite home in the JSON. Reading them from there means the
 * figure states what was *computed*, not what happened to be rendered.
 *
 * `buildCaption` de-duplicates against the live footnote, so a sentence that
 * `main.js` already put on the panel verbatim is not printed twice.
 *
 * ## Contract
 *
 * `figureDisclosure(payload, panelId, state)` returns an array of short English
 * sentences in a fixed order. Every read is guarded: a lab-frame payload has no
 * `frame` block and must never throw, and the energy panel gets nothing because
 * its disclosures live in its fitted-parameter table and its own footnote.
 */

import { formatSci, formatInt } from '../scale.js';

/** Fallback axis symbols per panel, when a payload does not carry them. */
const AXIS_SYMBOLS = {
  xy: { row: 'y′', col: 'x′' },
  yz: { row: 'y′', col: 'z′' },
  xz: { row: 'x′', col: 'z′' },
};

const SHOWER_NAME = { a: 'A', b: 'B' };

const FRAME_DEFINITION = 'Canonical centre-of-separation frame: each shower\'s 3-D '
  + 'centroid back-projected to the front face along its incident direction; '
  + 'entry midpoint at the origin, A→B entry separation along +x′.';

const ENSEMBLE_LEGEND = 'Dashed line = mean direction, shaded band = sample spread '
  + '(SD) of per-event slopes, thin envelope = 95% t-interval of the mean.';

/**
 * Sentences the figure must carry, derived from the projections payload.
 *
 * `payload` is the JSON of GET /api/projections, `panelId` one of
 * 'xy' | 'yz' | 'xz' | 'energy'. `state` is consulted only for the display
 * mode, and only when the payload does not say itself.
 */
export function figureDisclosure(payload, panelId, state, extra = {}) {
  if (!payload || panelId === 'energy' || !AXIS_SYMBOLS[panelId]) return [];

  const frame = payload.frame ?? null;
  const canonical = frame?.kind === 'canonical';
  const panel = payload.panels?.[panelId] ?? null;
  const scale = panel?.scale ?? null;
  const out = [];

  if (canonical) {
    out.push(FRAME_DEFINITION);
    if (panelId === 'xy' && typeof payload.slab?.note === 'string') out.push(payload.slab.note);
    const counts = frameCounts(frame);
    if (counts) out.push(counts);
    if (frame.n_events === 0) {
      out.push('No selected event has a defined frame; the panels are empty and no ensemble axis is drawn.');
    }
  }

  for (const line of colourScale(scale, canonical, panel)) out.push(line);

  if (canonical) {
    for (const line of displayWindow(frame, panel, panelId)) out.push(line);
    for (const line of splatting(frame)) out.push(line);
  } else if (panelId === 'xy') {
    // The comb is a product of the two transverse axes, so it is only visible
    // on the XY panel - which is also the only panel `main.js` warns on.
    const stagger = payload.meta?.stagger;
    if (stagger?.staggered && payload.meta?.resolution?.mode === 'native'
        && typeof stagger.note === 'string' && stagger.note) {
      out.push(stagger.note);
    }
  }

  if (canonical) {
    const ill = illConditioned(frame);
    if (ill) out.push(ill);
    if (panelId === 'xy') {
      const offsets = anchorOffsets(frame);
      if (offsets) out.push(offsets);
    }
    if (panelId === 'yz' || panelId === 'xz') {
      for (const line of ensembleAxes(frame)) out.push(line);
    }
    if (typeof extra.isometric === 'boolean') {
      out.push(extra.isometric
        ? 'Drawn at a 1:1 metric aspect.'
        : 'Axes carry true extents; the aspect is not 1:1.');
    }
  }

  if (payload.meta?.exact === false) {
    const percent = Number.isFinite(payload.meta?.sample_percent)
      ? payload.meta.sample_percent
      : null;
    out.push(percent === null
      ? 'Values are estimated from an unbiased sample, not the full selection.'
      : `Values are estimated from a ${percent}% unbiased sample.`);
  }

  void state;
  return out.filter((s) => typeof s === 'string' && s.length);
}

/** Measured ensemble entry centroids relative to the anchors (§1.6 of the plan). */
function anchorOffsets(frame) {
  const pair = frame.anchor_offsets?.truth_voxel;
  if (!pair || !Array.isArray(pair.a) || !Array.isArray(pair.b)) return null;
  const fmt = (v) => `${mm(v[0])}, ${mm(v[1])}`;
  if (![...pair.a, ...pair.b].every(Number.isFinite)) return null;
  return `Measured ensemble entry centroids sit at (${fmt(pair.a)}) mm from the A anchor `
    + `and (${fmt(pair.b)}) mm from the B anchor.`;
}

/* ------------------------------------------------------------ sentences -- */

function frameCounts(frame) {
  const n = frame.n_events;
  if (!Number.isFinite(n)) return null;
  const excluded = Number.isFinite(frame.n_excluded_no_frame) ? frame.n_excluded_no_frame : 0;
  const parts = [
    `N = ${formatInt(n)} co-registered ${n === 1 ? 'event' : 'events'} `
      + `(${formatInt(excluded)} excluded without a frame)`,
  ];

  const entry = frame.d_entry ?? {};
  if (Number.isFinite(entry.mean)) {
    // The interval is named: at N = 2 the Student-t 95% half-width is 12.7
    // standard errors, so an unlabelled "±" would be read as whichever the
    // reader assumes.
    const ci = Number.isFinite(entry.ci95_half)
      ? ` (95% t-interval of the mean ± ${mm(entry.ci95_half)} mm)`
      : '';
    parts.push(`⟨D_entry⟩ = ${mm(entry.mean)} mm (transverse, at entry)${ci}`);
  }
  const dataset = frame.d_dataset ?? {};
  if (Number.isFinite(dataset.mean)) {
    parts.push(`⟨D⟩ = ${mm(dataset.mean)} mm (dataset, 3-D)`);
  }
  return `${parts.join('; ')}.`;
}

/**
 * Whether a panel's bins are a kernel reconstruction. The payload's `kernel`
 * is 'none' for the raw Native Grid (and a guard's box merge of it), and
 * absent on the lab frame, which reconstructs nothing either.
 */
function reconstructed(panel) {
  return typeof panel?.kernel === 'string' && panel.kernel !== 'none';
}

function colourScale(scale, canonical, panel = null) {
  if (!scale) return [];
  const out = [];

  if (scale.unit === 'a.u.') {
    const norm = scale.norm === 'dataset' ? 'dataset peak' : 'selection peak';
    out.push(`Colour: average hit density (a.u.), 10^${exponent(scale.vmin)}…`
      + `10^${exponent(scale.vmax)} relative to ρ_ref = ${formatSci(scale.rho_ref, 3)} `
      + `GeV mm⁻² per event (${norm}).`);
    if (scale.floor === 'transparent') {
      // The print raster has no fade (floorFadeDecades 0), so the floor is a
      // hard contour - which a reader will take for the edge of the shower
      // unless the figure says otherwise.
      const floor = floorPower(scale.floor_ratio, scale.vmin);
      const cells = Number.isFinite(panel?.below_floor_cells) ? panel.below_floor_cells : null;
      const energy = reconstructed(panel) ? 'in-window reconstructed energy' : 'in-window energy';
      const share = Number.isFinite(panel?.below_floor_energy_fraction)
        ? `, ${percent(panel.below_floor_energy_fraction)} of the panel's ${energy}`
        : '';
      const counted = cells !== null ? ` (${formatInt(cells)} ${plural(cells, 'bin')}${share})` : '';
      out.push(`Bins below ${floor} of ρ_ref are not drawn${counted}; the dark outline is the `
        + `${floor} display floor, not a shower edge.`);
    } else if (scale.clipped_low > 0) {
      out.push(`${formatInt(scale.clipped_low)} ${plural(scale.clipped_low, 'bin')} below `
        + 'the ramp floor are drawn at the lowest colour.');
    }
    return out;
  }

  if (scale.unit === 'attention' && canonical) {
    out.push('Colour: energy-weighted mean Grad-CAM attention on a fixed 0–1 linear scale.');
    const mask = attentionMask(panel?.attention_mask);
    if (mask) out.push(mask);
    return out;
  }

  if (scale.unit === 'GeV') {
    const basis = scale.locked
      ? ' (locked to the dataset maximum)'
      : ' (autoscaled to this selection)';
    out.push(`Colour: summed energy, log₁₀ from 10^${exponent(scale.vmin)} to `
      + `10^${exponent(scale.vmax)} GeV${basis}.`);
    const lo = scale.clipped_low > 0 ? scale.clipped_low : 0;
    const hi = scale.clipped_high > 0 ? scale.clipped_high : 0;
    if (lo && hi) {
      out.push(`${formatInt(lo)} cells fall below and ${formatInt(hi)} above the ramp `
        + 'and are clipped to its ends.');
    } else if (lo) {
      out.push(`${formatInt(lo)} ${plural(lo, 'cell')} fall below the ramp and are `
        + 'clipped to its floor.');
    } else if (hi) {
      out.push(`${formatInt(hi)} ${plural(hi, 'cell')} fall above the ramp and are `
        + 'clipped to its ceiling.');
    }
    return out;
  }

  // The lab Grad-CAM channel is a fixed 0-1 attention scale with nothing to
  // disclose about its bounds; nothing is said rather than something
  // approximate. The canonical one is handled above, because its mask is.
  return out;
}

/**
 * The Grad-CAM masking rule of a canonical panel, from its `attention_mask`.
 *
 * Continuous Field masks bins whose reconstructed density falls below the
 * floor, because the kernel's tails paint attention over no energy; the
 * Native Grid masks only bins without hits, so no attention measured on a
 * real hit is ever hidden. The payload's own `rule` names which applies.
 */
function attentionMask(mask) {
  if (!mask) return null;
  const rule = typeof mask.rule === 'string' && mask.rule
    ? mask.rule.replace(/\.?\s*$/, '.')
    : null;
  const cells = Number.isFinite(mask.cells) ? mask.cells : 0;
  if (cells <= 0) return rule;
  const hits = Number.isFinite(mask.hit_fraction)
    ? `, holding ${percent(mask.hit_fraction)} of the panel's in-window hits`
    : '';
  const peak = Number.isFinite(mask.max_attention)
    ? `; the largest masked attention is ${mask.max_attention.toFixed(2)}`
    : '';
  return `${rule ? `${rule} ` : ''}Attention not drawn in ${formatInt(cells)} `
    + `${plural(cells, 'bin')}${hits}${peak}.`;
}

function displayWindow(frame, panel, panelId) {
  const fit = frame.fit?.[panelId];
  if (!fit) return [];
  const symbols = AXIS_SYMBOLS[panelId];
  const out = [];

  if (frame.fit?.rule === 'symmetric') {
    const sentence = symmetricWindow(frame.fit, fit, panel, symbols);
    if (sentence) out.push(sentence);
    if (frame.fit?.provisional) {
      out.push(`Fitted ranges are provisional (N = ${formatInt(frame.n_events)}).`);
    }
    return out;
  }

  const cropped = [];
  for (const side of ['col', 'row']) {
    const axis = fit[side];
    if (!axis?.applied || !Array.isArray(axis.range) || axis.range.length < 2) continue;
    const [lo, hi] = axis.range;
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) continue;
    const symbol = panel?.axes?.[side]?.symbol ?? symbols[side];
    cropped.push(`${symbol} ∈ [${mm(lo)}, ${mm(hi)}] mm`);
  }

  if (cropped.length) {
    const [p0, p1] = Array.isArray(frame.fit?.percentiles) && frame.fit.percentiles.length >= 2
      ? frame.fit.percentiles
      : [1, 99];
    const outside = Number.isFinite(fit.energy_fraction_outside)
      ? `${(100 * fit.energy_fraction_outside).toFixed(2)}%`
      : '—';
    out.push(`Display window: ${cropped.join(', ')} (${ordinal(p0)}–${ordinal(p1)} energy `
      + `percentile); ${outside} of the panel's energy lies outside it.`);
  }

  if (frame.fit?.provisional) {
    out.push(`Fitted ranges are provisional (N = ${formatInt(frame.n_events)}).`);
  }
  return out;
}

/**
 * The symmetric window as one sentence: half-widths, the percentile rule, any
 * floor or clamp that set a half-width instead, and the energy outside.
 *
 * The outside share is the panel's own, measured after reconstruction - what
 * the reader cannot see - falling back to the fit's pre-reconstruction figure
 * for a payload that does not carry it. A Native Grid panel has nothing
 * reconstructed, so its share is stated without the qualifier.
 */
function symmetricWindow(windowFit, fit, panel, symbols) {
  const parts = [];
  const limits = [];
  for (const side of ['col', 'row']) {
    const axis = fit[side];
    if (!axis?.applied || !Array.isArray(axis.range) || axis.range.length < 2) continue;
    const [lo, hi] = axis.range;
    const half = Number.isFinite(axis.half_width)
      ? axis.half_width
      : Math.max(Math.abs(lo), Math.abs(hi));
    if (!Number.isFinite(half)) continue;
    const symbol = panel?.axes?.[side]?.symbol ?? symbols[side];
    parts.push(`${symbol} ±${Math.round(half)} mm`);
    if (axis.floored && Number.isFinite(windowFit.floor_mm)) {
      limits.push(`${symbol} held at the ${Math.round(windowFit.floor_mm)} mm floor`);
    }
    if (axis.clamped) limits.push(`${symbol} clamped to the accumulation window`);
  }
  if (!parts.length) return null;

  const [p0, p1] = Array.isArray(windowFit.percentiles) && windowFit.percentiles.length >= 2
    ? windowFit.percentiles
    : [0.1, 99.9];
  const after = panel?.energy_fraction_outside_window;
  const outside = Number.isFinite(after) ? after : fit.energy_fraction_outside;
  const tail = Number.isFinite(after) && reconstructed(panel) ? ' after reconstruction' : '';
  return `Display window: ${parts.join(', ')}, symmetric about the origin at the `
    + `${ordinal(p0)}–${ordinal(p1)} energy percentile`
    + `${limits.length ? `; ${limits.join('; ')}` : ''}; `
    + `${Number.isFinite(outside) ? percent(outside) : '—'} of the panel's energy lies outside it${tail}.`;
}

function splatting(frame) {
  const out = [];
  // What a displayed bin is - the kernel, its width, the gate - before the
  // comb verdict, which is measured on the raw grid underneath it.
  const recon = frame.reconstruction?.note;
  if (typeof recon === 'string' && recon) out.push(recon);
  const fp = frame.footprint_mm;
  const k = frame.subsample_k;
  const pitch = frame.pitch_mm;
  if (Array.isArray(fp) && fp.length >= 2 && Number.isFinite(fp[0]) && Number.isFinite(fp[1])
      && Number.isFinite(k) && Number.isFinite(pitch)) {
    out.push(`Cells (${fp[0].toFixed(1)} × ${fp[1].toFixed(1)} mm) were splatted as `
      + `${k} × ${k} sub-deposits on a ${pitch} mm grid.`);
  }
  const note = frame.comb?.note;
  if (typeof note === 'string' && note) out.push(note);
  return out;
}

function illConditioned(frame) {
  const n = frame.n_ill_conditioned;
  if (!(n > 0)) return null;
  const threshold = Number.isFinite(frame.ill_conditioned_threshold_mm)
    ? frame.ill_conditioned_threshold_mm
    : 80;
  return `${formatInt(n)} ${plural(n, 'event')} enter closer than ${threshold} mm apart, so `
    + 'their orientation is effectively random: their energy enters ⟨ρ⟩ averaged over '
    + 'azimuth and their directions enter R̄′, the Rayleigh p and the dispersion band as noise.';
}

function ensembleAxes(frame) {
  const out = [];
  let anyEnsemble = false;
  for (const key of ['a', 'b']) {
    // The gated block: `frame.ensemble` withholds R̄′ and p below two events,
    // where a resultant length is trivially 1.0 and says nothing.
    const gated = frame.ensemble?.[key] ?? {};
    const axis = frame.axes?.[key] ?? {};
    const n = Number.isFinite(gated.n) ? gated.n : axis.n;
    if (!(n > 0)) continue;
    const name = SHOWER_NAME[key];
    const resultant = gated.resultant_transverse;
    if (n < 2 || !Number.isFinite(resultant)) {
      out.push(`Shower ${name} axis: ${gated.label || 'single event, not an ensemble'} `
        + `(N = ${formatInt(n)}); no dispersion band or interval can be drawn.`);
      continue;
    }
    anyEnsemble = true;
    const p = Number.isFinite(gated.rayleigh_p) ? gated.rayleigh_p.toPrecision(2) : '—';
    const faded = gated.faded
      ? ' (direction not distinguishable from uniform, drawn faded)'
      : '';
    const weak = gated.label ? ` — ${gated.label}` : '';
    out.push(`Shower ${name} ensemble axis: R̄′ = ${resultant.toFixed(3)}, `
      + `Rayleigh p = ${p}, N = ${formatInt(n)}${weak}${faded}.`);
  }
  if (anyEnsemble) out.push(ENSEMBLE_LEGEND);
  return out;
}

/* -------------------------------------------------------------- helpers -- */

/** Millimetres with no decimals and a typographic minus. */
function mm(value) {
  if (!Number.isFinite(value)) return '—';
  const rounded = Math.round(value);
  return rounded < 0 ? `−${Math.abs(rounded)}` : String(rounded);
}

/** A log₁₀ exponent: integers as-is, fractions to two decimals. */
function exponent(value) {
  if (!Number.isFinite(value)) return '—';
  const text = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return text.startsWith('-') ? `−${text.slice(1)}` : text;
}

/**
 * An ordinal for a percentile, decimal-aware: 1 → "1st", 0.1 → "0.1st",
 * 99.9 → "99.9th".
 *
 * A decimal takes the suffix its last digit is read with ("nought point one
 * first"), which is the convention "0.1st percentile" follows. Exported for
 * the on-screen footnotes, so the screen and the figure word it the same way.
 */
export function ordinal(n) {
  if (!Number.isFinite(n)) return '—';
  const text = Number.isInteger(n) ? String(n) : String(Number(n.toFixed(3)));
  const digits = text.replace(/[^0-9]/g, '');
  const last = Number(digits.slice(-1));
  const lastTwo = Number(digits.slice(-2));
  const integral = !text.includes('.');
  if (integral && lastTwo >= 11 && lastTwo <= 13) return `${text}th`;
  switch (last) {
    case 1: return `${text}st`;
    case 2: return `${text}nd`;
    case 3: return `${text}rd`;
    default: return `${text}th`;
  }
}

/** log₁₀ floor of a relative ramp as a power of ten, e.g. 10^−3. */
function floorPower(ratio, fallbackExponent) {
  const exp = Number.isFinite(ratio) && ratio > 0 ? Math.log10(ratio) : fallbackExponent;
  if (!Number.isFinite(exp)) return 'the floor';
  const rounded = Math.round(exp * 10) / 10;
  return `10^${exponent(rounded)}`;
}

function percent(value) {
  return `${(100 * value).toFixed(2)}%`;
}

function plural(n, noun) {
  return Math.round(n) === 1 ? noun : `${noun}s`;
}
