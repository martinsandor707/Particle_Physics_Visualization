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

  for (const line of colourScale(scale, canonical)) out.push(line);

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

function colourScale(scale, canonical) {
  if (!scale) return [];
  const out = [];

  if (scale.unit === 'a.u.') {
    const norm = scale.norm === 'dataset' ? 'dataset peak' : 'selection peak';
    out.push(`Colour: average hit density (a.u.), 10^${exponent(scale.vmin)}…`
      + `10^${exponent(scale.vmax)} relative to ρ_ref = ${formatSci(scale.rho_ref, 3)} `
      + `GeV mm⁻² per event (${norm}).`);
    if (scale.clipped_low > 0) {
      out.push(`${formatInt(scale.clipped_low)} ${plural(scale.clipped_low, 'bin')} below `
        + 'the ramp floor are drawn at the lowest colour.');
    }
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

  // The Grad-CAM channel is a fixed 0-1 attention scale (`unit: 'attention'`)
  // with nothing to disclose about its bounds; nothing is said rather than
  // something approximate. `canonical` is accepted for symmetry with the
  // callers above and reserved for a frame-specific wording.
  void canonical;
  return out;
}

function displayWindow(frame, panel, panelId) {
  const fit = frame.fit?.[panelId];
  if (!fit) return [];
  const symbols = AXIS_SYMBOLS[panelId];
  const out = [];

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

function splatting(frame) {
  const out = [];
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

function ordinal(n) {
  if (!Number.isFinite(n)) return '—';
  const v = Math.round(n);
  const mod100 = v % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${v}th`;
  switch (v % 10) {
    case 1: return `${v}st`;
    case 2: return `${v}nd`;
    case 3: return `${v}rd`;
    default: return `${v}th`;
  }
}

function plural(n, noun) {
  return Math.round(n) === 1 ? noun : `${noun}s`;
}
