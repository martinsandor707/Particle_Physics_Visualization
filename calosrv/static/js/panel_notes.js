/* What the Details drawer says about one panel: its methodology and its
 * statistical disclosures, as sections of plain text.
 *
 * The four on-card footnotes used to carry this. They were multi-line blocks
 * under every plot, read once and then scrolled past, and they stole height
 * from the pictures. The same sentences now live behind a Details trigger on
 * each card, built from the same pure functions - `footnotes()` for the prose
 * the reader saw on the card, `figureDisclosure()` for the sentences derived
 * from the payload's structured fields, `exportLegend()` for the marks,
 * `describeSelection()` / `describeView()` for what the panel was measured
 * on. Nothing here reads the page: main.js hands the payloads in and shell.js
 * renders the result, so every sentence can be checked under Node.
 *
 * `hazards()` names the conditions a reader should not miss - a provisional
 * range, a measured comb, a sampled preview - so the trigger can be flagged
 * on the card while the drawer stays closed.
 *
 * The physics cards below the 2 × 2 (profiles, response, B3, distributions,
 * correlations, statistics) have builders of their own at the end of this
 * file. Their payloads carry their prose (`notes`) and their structured
 * disclosures (clip counts, comb, intervals); the builders sort both into the
 * same four sections and add what the chart itself decided - the marks it
 * drew, the ranges it clipped - so the drawer never states something the
 * picture does not show.
 */

import {
  footnotes, exportLegend, kindOf, panelTitle, energyNetworkSentence,
  eventRowLabel, eventSelectionLine, eventFrameSentence, num, pct,
  labLegend, windowAxisLegend, windowAxisDisclosures,
} from './frame_views.js';
import { figureDisclosure, showersPerEvent } from './export/disclosure.js';
import { describeSelection, describeView, displayOf } from './export/caption.js';
import { panelSymbols } from './axis_symbols.js';
import { formatSci, formatInt } from './scale.js';
import { profileAxisKey, ensembleLabel } from './panels/profile.js';
import { gridSlices, subplotScale, seriesMessage, estimatorNote } from './panels/response_grid.js';
import { sigmaText, clampInterval } from './panels/chart_panel.js';
import { SHAPE_FLOOR_SHOWERS } from './panels/distribution.js';

export const SECTION = Object.freeze({
  selection: 'Selection',
  drawn: 'What is drawn',
  disclosures: 'Disclosures',
  legend: 'Marks and legend',
  density: 'Reading the density axis',
});

export const ENERGY_TITLE = 'Reconstructed Energy vs. Separation D';

export const ENERGY_MARKS =
  'Solid curves are Gaussian fits and dashed curves mark shower B; a thinner, '
  + 'fainter curve is a thin slice, drawn but not allowed to set the density '
  + 'axis. Below the histogram floor the individual events appear as baseline '
  + 'ticks, with the sample dispersion as a shaded band and the mean with its '
  + '95% confidence interval as a capped whisker — two different quantities, '
  + 'so two different marks. Dotted verticals are the isolated single-shower '
  + 'reference benchmarks at μ ± σ: stated widths, not fits.';

export const DENSITY_EXPLAINER =
  'A probability density is not a probability. The curve integrates to 1.0 over '
  + 'the energy axis, so its height carries units of GeV⁻¹ and legitimately '
  + 'exceeds 1.0 wherever the distribution is narrow — a resolution of '
  + 'σ = 0.4 GeV already peaks near 1.0 GeV⁻¹, and anything sharper peaks higher. '
  + 'A tall peak therefore means good resolution, not a probability above one. '
  + 'For the same reason a curve integrating to 1.0 says nothing about how many '
  + 'events it was built from: the peak height of a fit from nine events and one '
  + 'from ninety thousand are equally tall for equal σ. The event ticks along the '
  + 'baseline are what carry the sample size, which is why a thin slice is drawn '
  + 'with its events beneath it and is never allowed to set the axis scale.';

/** The Event Inspector's marks: every one belongs to the one shower drawn. */
export const EVENT_MARKS =
  'Dashed line = the incident direction (θ, φ) forward from the shower origin; dotted line = '
  + 'the same direction extrapolated backward, upstream of the origin; dash-dot line = the plane '
  + 'of the first populated layer (z = z₀ in the original and translated frames; on the local '
  + 'X′Z′ panel the tilted line w = tan θ · u it maps to, which has no image on the other local '
  + 'panels); ✕ = the shower origin P₀, in the shower’s colour. No ensemble statistic is drawn: '
  + 'every mark belongs to this one shower, and the principal-axis tilt is printed, not drawn.';

/** The semantic axes of each Event Inspector panel: column, row. */
const EVENT_PANEL_AXES = { xy: ['x', 'y'], xz: ['z', 'x'], yz: ['z', 'y'] };

/** Whitespace-collapsed text, for comparing sentences that came from different sources. */
function collapse(text) {
  return String(text ?? '').replace(/\s+/g, ' ').trim();
}

/** Lines of a notes object, in a builder that drops empties and repeats. */
export class Notes {
  constructor(title) {
    this.title = title;
    this.sections = [];
    this.seen = new Set();
  }

  section(heading, lines) {
    const kept = [];
    for (const line of lines) {
      const key = collapse(line);
      if (!key || key === '—' || this.seen.has(key)) continue;
      this.seen.add(key);
      kept.push(key);
    }
    if (kept.length) this.sections.push({ heading, lines: kept });
    return this;
  }

  done(hazards) {
    return { title: this.title, hazards, sections: this.sections };
  }
}

/**
 * The notes of one spatial panel.
 *
 * `isometric` is `{xy, yz, xz}` as the panels currently draw themselves (the
 * depth panels decide 1:1 from their size), `view` the displayed window in
 * millimetres or null for the full extent, `state` the interface State (null
 * under a bare Node test, which then gets no selection line), `windowAxis`
 * the absolute-frame depth panel's windowed ensemble axis response, when one
 * is drawn.
 */
export function projectionNotes({
  payload, panelId, isometric = {}, view = null, state = null, experiment = null, windowAxis = null,
}) {
  const panel = payload?.panels?.[panelId];
  if (!panel) return null;
  const kind = kindOf(payload);
  const frame = payload.frame ?? null;
  // A single-shower experiment words its frames without a partner shower or D
  // (frame_views.js); the payload says as much when no experiment is given.
  const nShowers = experiment?.capabilities?.n_showers ?? null;
  const notes = new Notes(panelTitle(panelId, kind, nShowers ?? showersPerEvent(payload)));

  const selection = [];
  if (state) {
    selection.push(describeSelection(
      state, experiment, payload.selection ?? null, frame,
      displayOf(payload.meta?.resolution, frame, panel), { spatial: true, meta: payload.meta ?? null },
    ));
  }
  if (view && panel.axes) {
    const symbols = panelSymbols(kind, panelId, panel.axes);
    selection.push(describeView(view, symbols.col, symbols.row));
  }
  notes.section(SECTION.selection, selection);

  const footnote = footnotes(payload, { isometric, nShowers })[panelId] ?? '';
  notes.section(SECTION.drawn, [footnote]);
  const disclosures = figureDisclosure(payload, panelId, state, { isometric: Boolean(isometric[panelId]), nShowers });
  const windowed = kind === 'lab' && panelId !== 'xy' ? windowAxis : null;
  if (windowed) disclosures.push(...windowAxisDisclosures(windowed));
  notes.section(SECTION.disclosures, disclosures);
  if (kind !== 'lab') notes.section(SECTION.legend, [exportLegend(panelId, payload, { nShowers })]);
  else if (panelId !== 'xy') notes.section(SECTION.legend, [labLegend(payload, { nShowers }), windowAxisLegend(windowed)]);
  return notes.done(hazards(payload, panelId));
}

/**
 * The notes of the energy panel.
 *
 * `notices` are the low-statistics sentences the panel shows on the card
 * (`EnergyPanel.lastNotices`), passed in rather than scraped; `selection` is
 * the projections response's selection block, which the energy response does
 * not repeat.
 */
export function energyNotes({
  payload, notices = [], selection = null, state = null, experiment = null,
}) {
  if (!payload) return null;
  // A momentum-sliced response (plot 4 of a single-shower experiment) is B3:
  // its own title and sections. The separation view below is unchanged.
  if (payload.slice_by === 'momentum') return responseGridNotes({ payload, state, experiment });
  const notes = new Notes(ENERGY_TITLE);
  if (state) {
    notes.section(SECTION.selection, [describeSelection(
      state, experiment, selection, null, null, { spatial: false, meta: payload.meta ?? null },
    )]);
  }

  const drawn = [];
  const calibration = payload.calibration || {};
  if (calibration.applied) {
    drawn.push(
      'Energies are calibrated to the incident-momentum scale by the fitted '
      + `sampling fractions f_A = ${formatSci(calibration.sampling_fraction_a, 3)}, `
      + `f_B = ${formatSci(calibration.sampling_fraction_b, 3)}.`,
    );
  }
  const network = energyNetworkSentence(payload);
  if (network) drawn.push(network);
  drawn.push(ENERGY_MARKS);
  // The energy panel's warnings describe its own slices and are stated in
  // its notices; only the payload guard's re-sampling is new, and it belongs
  // with the curves it changed.
  for (const warning of payload.meta?.warnings || []) {
    if (String(warning).startsWith('Density curves sampled')) drawn.push(warning);
  }
  notes.section(SECTION.drawn, drawn);

  const disclosures = [];
  const clipping = payload.axis?.clipping;
  if (clipping && clipping.applied && clipping.n_outside) disclosures.push(clipping.note);
  disclosures.push(...(notices || []));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.density, [DENSITY_EXPLAINER]);
  return notes.done(hazards(payload, 'energy'));
}

/**
 * The notes of one Event Inspector panel: one shower of one event in one
 * frame (`kind`: lab | trans | local), one projection (`panelId`: xy | xz |
 * yz). `payload` is the whole `/api/event` response. `windowScope` names the
 * panels that share the window: the inspector's nine by default, the three
 * projections beside the Models page's 3-D event view there. A per-axis
 * window (the Models page asks for `window=per_axis`) names each axis's
 * half-width (`frames.<f>.half_mm_axes`); Page 1's shared window keeps its
 * one-half-width sentence.
 */
export function eventNotes({
  payload, kind, panelId, view = null, state = null, experiment = null, windowScope = 'all nine panels',
}) {
  const frame = payload?.frames?.[kind];
  const panel = frame?.panels?.[panelId];
  if (!panel) return null;
  const event = payload.event ?? {};
  const symbols = frame.symbols ?? {};
  const [first, second] = { xy: ['x', 'y'], xz: ['x', 'z'], yz: ['y', 'z'] }[panelId] ?? ['x', 'y'];
  const notes = new Notes(`${frame.title}: ${symbols[first] ?? first}–${symbols[second] ?? second}`);

  const selection = [eventRowLabel(event), eventSelectionLine(event)];
  if (state) {
    selection.push(describeSelection(state, experiment, null, null, null, { filtersOnly: true }));
  }
  if (view) {
    const [c, r] = EVENT_PANEL_AXES[panelId] ?? ['x', 'y'];
    selection.push(describeView(view, symbols[c] ?? c, symbols[r] ?? r));
  }
  notes.section(SECTION.selection, selection);

  // A per-axis window (`/api/event?window=per_axis`, the Models page) carries each axis's
  // half-width; the shared one (Page 1) has one for every axis, and its sentence is unchanged.
  const halves = frame.half_mm_axes;
  let axesLine;
  if (halves && ['x', 'y', 'z'].every((a) => Number.isFinite(halves[a]))) {
    const each = ['x', 'y', 'z'].map((a) => `${symbols[a] ?? a} ${num(halves[a], 0)} mm`).join(', ');
    axesLine = `Axes 1:1 (isometric), per-axis half-widths ${each} on ${windowScope}: each panel is sized `
      + 'from its two millimetre spans and letterboxed, so the tilt reads at its true angle; the raster '
      + 'covers the populated part of the window and the rest is empty.';
  } else {
    const half = Number.isFinite(frame.half_mm) ? `${num(frame.half_mm, 0)} mm` : 'one';
    axesLine = `Axes 1:1 (isometric), ${half} half-width on every axis of ${windowScope}, so the tilt reads at `
      + 'its true angle; the raster covers the populated part of the window and the rest is empty.';
  }
  notes.section(SECTION.drawn, [
    eventFrameSentence(payload, kind),
    payload.window?.rule ?? '',
    axesLine,
  ]);

  const disclosures = [payload.scale?.rule ?? ''];
  const below = panel.scale?.clipped_low ?? 0;
  disclosures.push(below > 0
    ? `${formatInt(below)} populated bin${below === 1 ? '' : 's'} of this panel lie below the ramp floor and are drawn at the lowest colour.`
    : 'No populated bin of this panel lies below the ramp floor.');
  const outside = panel.energy_outside_window_gev ?? 0;
  const total = panel.total_energy_all_gev;
  disclosures.push(outside > 0
    ? `${formatSci(outside, 3)} GeV (${pct(panel.energy_fraction_outside_window ?? (total ? outside / total : 0))}) `
      + `of the shower's ${formatSci(total, 3)} GeV falls outside this panel's window and is not drawn.`
    : 'Every cell of the shower lies inside this panel\'s window.');
  if (payload.coordinates?.note) disclosures.push(payload.coordinates.note);
  for (const note of payload.grid?.notes ?? []) disclosures.push(note);
  if (event.in_selection === false) {
    disclosures.push('This event lies outside the current selection and is drawn as asked; '
      + 'the previous / next controls walk the selection.');
  }
  notes.section(SECTION.disclosures, disclosures);

  const axis = event.shower?.principal_axis;
  const tilt = axis && Number.isFinite(axis.tilt_deg)
    ? `Principal axis of the energy-weighted cloud in the local frame: ${num(axis.tilt_deg, 1)}° from +w `
      + `over ${formatInt(axis.n)} cells - the notebook's check on the rotation, printed in the row label.`
    : 'Principal axis: untestable below 3 populated cells, so no tilt is quoted.';
  notes.section(SECTION.legend, [EVENT_MARKS, tilt]);
  return notes.done(hazards(payload, panelId));
}

/**
 * The conditions a reader should not miss, from the payload's structure.
 *
 * Structural predicates only, never text matching: a provisional fitted
 * range, a measured comb, a sampled preview, an empty frame; for the energy
 * panel, low-statistics series (any series drawn below the histogram floor),
 * a clipped energy range and uncalibrated energies.
 */
export function hazards(payload, panelId) {
  const out = [];
  if (!payload) return out;
  if (payload.frames && payload.event) {
    // An Event Inspector response: one event, nine panels, one set of hazards.
    if (payload.event.in_selection === false) out.push('event outside the selection');
    if (payload.coordinates && payload.coordinates.within_tolerance === false) {
      out.push('coordinate residual above tolerance');
    }
    if (payload.grid?.notes?.length) out.push('coarsened grid');
    if (payload.event.shower && !payload.event.shower.principal_axis) out.push('principal axis untestable');
    return out;
  }
  if (panelId === 'energy') {
    if ((payload.series || []).some((s) => s.draw && s.draw !== 'histogram')) {
      out.push('low-statistics series');
    }
    const clipping = payload.axis?.clipping;
    if (clipping && clipping.applied && clipping.n_outside) out.push('clipped energy range');
    if (payload.calibration && payload.calibration.applied === false) out.push('uncalibrated energies');
    return out;
  }
  if (PHYSICS_HAZARDS[panelId]) return PHYSICS_HAZARDS[panelId](payload);
  const meta = payload.meta || {};
  const frame = payload.frame || null;
  if (meta.exact === false) out.push('sampled preview');
  if (kindOf(payload) === 'lab') {
    if (panelId === 'xy' && meta.stagger?.staggered && meta.resolution?.mode === 'native') {
      out.push('measured lattice comb');
    }
    return out;
  }
  if (frame?.comb?.staggered) out.push('measured comb');
  if (frame?.fit?.provisional) out.push('provisional fitted range');
  if (frame && frame.n_events === 0) out.push('empty frame');
  return out;
}

/** The lines of one section, or [] when the section is absent. */
export function notesLines(notes, heading) {
  return notes?.sections?.find((section) => section.heading === heading)?.lines ?? [];
}

/** Every line of a notes object joined by a space; '' for null. */
export function notesText(notes) {
  if (!notes) return '';
  return notes.sections.flatMap((section) => section.lines).join(' ');
}

/**
 * The warnings a banner should still show: those not already stated in the
 * text on screen, without duplicates, in their original order.
 */
export function warningsNotShown(warnings, shownText = '') {
  const shown = collapse(shownText);
  const seen = new Set();
  const out = [];
  for (const warning of warnings || []) {
    const text = collapse(warning);
    if (!text || seen.has(text) || shown.includes(text)) continue;
    seen.add(text);
    out.push(warning);
  }
  return out;
}

/* ======================================================= physics cards == */

/** The physics cards' drawer titles by card id, plus profile-w's native-depth variant. */
export const PHYSICS_TITLES = Object.freeze({
  'profile-w': 'Longitudinal Profile along w',
  'profile-native': 'Longitudinal Profile (native layers)',
  'profile-r': 'Radial Profile',
  'response-b1': 'Sampling Fraction — Per-Event Distribution',
  'response-b2': 'Sampling Fraction vs. Incident Momentum',
  'response-res': 'Relative Resolution σ/μ vs. Incident Momentum',
  'response-b3': 'Response vs. Incident Momentum p',
  distribution: 'Distributions by Momentum Bin',
  correlation: 'Hit-level Pearson Correlation',
  statistics: 'Selection Statistics — describe()',
});

/** B3's title, where the energy panel shows a momentum-sliced response. */
export const RESPONSE_TITLE = PHYSICS_TITLES['response-b3'];

/** Headings the physics cards add after the four standard ones. */
export const PHYSICS_HEADINGS = Object.freeze({
  estimators: 'Estimators',
  circular: 'Circular quantities',
  weightings: 'Weightings',
  negative: 'Hits behind the entry plane',
});

/** The response card each mode's notes belong to, and the prefix of its server notes. */
const RESPONSE_PARTS = {
  b1: { id: 'response-b1', prefix: 'B1' },
  b2: { id: 'response-b2', prefix: 'B2' },
  resolution: { id: 'response-res', prefix: 'Resolution' },
};
/** A server note of one part starts with its name and a colon or a comma ("B1:", "B1, Shower A:"). */
const PART_NOTE = /^(B1|B2|Resolution)[:,]\s*/;

/** The filter line of a physics card: the experiment and the narrowed axes only. */
function physicsSelection(state, experiment) {
  if (!state) return null;
  return describeSelection(state, experiment, null, null, null, { filtersOnly: true });
}

function plural(n, word, many = `${word}s`) {
  return `${formatInt(n)} ${n === 1 ? word : many}`;
}

/** The warnings a payload's meta carries, and its sampling, as disclosures. */
function metaDisclosures(payload) {
  const out = [...(payload?.meta?.warnings ?? [])];
  const meta = payload?.meta ?? {};
  if (meta.exact === false) {
    out.push(Number.isFinite(meta.sample_percent)
      ? `Sampled preview: computed on ${num(meta.sample_percent, 1)}% of the hits; the exact numbers follow.`
      : 'Sampled preview: the exact numbers follow.');
  }
  return out;
}

/* ---------------------------------------------------------------- C7 -- */

/**
 * The notes of one profile card. `axis` is the card's axis ('depth' | 'w' |
 * 'kt' | 'r'); the payload's notes describe the whole response (both axes),
 * its structured fields the axis drawn here. `title` is the card's own; a
 * native-depth response is titled as such whatever the card says.
 */
export function profileNotes({ payload, state = null, experiment = null, axis = 'depth', title = null }) {
  if (!payload) return null;
  const key = profileAxisKey(payload, axis);
  const ax = key ? payload.axes[key] : null;
  const id = key === 'r' ? 'profile-r' : 'profile-w';
  const notes = new Notes(key === 'kt' ? PHYSICS_TITLES['profile-native'] : (title ?? PHYSICS_TITLES[id]));
  const e = payload.ensemble ?? {};
  const label = ensembleLabel(payload);
  notes.section(SECTION.selection, [
    physicsSelection(state, experiment),
    `${plural(e.n_showers ?? 0, 'shower')} in ${plural(e.n_events ?? 0, 'event')}`
      + `${payload.shower && payload.shower !== 'both' ? ` (shower ${payload.shower.toUpperCase()} only)` : ''}`
      + `${label ? ` — ${label}` : ''}.`,
    payload.convention?.label ? `Convention: ${payload.convention.label}.` : '',
  ]);
  notes.section(SECTION.drawn, [...(payload.notes ?? [])]);

  const disclosures = [];
  if (ax) {
    const c = ax.y?.clipped ?? {};
    const parts = [];
    if (c.band) parts.push(`${plural(c.band, 'SD-band bin')} above the axis`);
    if (c.band_below_zero) parts.push(`${plural(c.band_below_zero, 'SD-band bin')} below zero`);
    if (c.envelope) parts.push(`${plural(c.envelope, 'envelope bin')} above the axis`);
    if (c.envelope_below_zero) parts.push(`${plural(c.envelope_below_zero, 'envelope bin')} below zero`);
    if (c.pooled_interval) parts.push(`${plural(c.pooled_interval, 'pooled-interval bin')} above the axis`);
    if (c.pooled_interval_below_zero) parts.push(`${plural(c.pooled_interval_below_zero, 'pooled-interval bin')} below zero`);
    disclosures.push(parts.length
      ? `Clipped at the axis, each with a caret and its true values in the readout: ${parts.join('; ')}.`
      : 'No band or interval leaves the axis.');
    if (ax.y?.provisional) {
      disclosures.push(`The y range is provisional: fewer than 20 showers (${label || `N = ${formatInt(e.n_showers)}`}).`);
    }
    const o = ax.outside ?? {};
    if ((o.below_fraction ?? 0) > 0 || (o.above_fraction ?? 0) > 0) {
      disclosures.push(`Outside the drawn ${ax.symbol} window ${num(o.window_cm?.[0], 2)} to ${num(o.window_cm?.[1], 2)} cm: `
        + `${pct(o.below_fraction)} of the pooled energy below and ${pct(o.above_fraction)} above `
        + `(${pct(o.mean_below_fraction)} and ${pct(o.mean_above_fraction)} by the per-shower mean), kept in the normalisers.`);
    }
    const comb = ax.comb;
    if (comb) {
      const verdict = comb.combed === null || comb.combed === undefined
        ? 'not a comb verdict' : (comb.combed ? 'a comb' : 'no comb');
      disclosures.push(`Comb lag-1 ${Number.isFinite(comb.lag1) ? num(comb.lag1, 2) : '—'} against the `
        + `${num(comb.threshold, 2)} threshold, measured on the ${comb.measured_on}: ${verdict}.`);
    }
  }
  if (e.n_single_cell) {
    disclosures.push(`${plural(e.n_single_cell, 'shower')} ${e.n_single_cell === 1 ? 'deposits' : 'deposit'} in a single cell.`);
  }
  if (e.n_dropped) disclosures.push(`${plural(e.n_dropped, 'shower')} left out under this convention.`);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);

  const legend = (payload.marks ?? []).map((m) => `${m.label} (${m.style})${m.drawn ? '' : ', not drawn'}: ${m.meaning}`);
  if (key === 'w' && ax?.w_zero_rule) {
    legend.push('Dashed vertical: w = 0, the shower’s entry point P₀; no bin straddles it.');
  }
  legend.push('Carets at the axis mark a band or interval clipped there; the readout gives every value of the bin under the pointer.');
  notes.section(SECTION.legend, legend);
  return notes.done(hazards(payload, id));
}

/* ------------------------------------------------------- B1, B2, σ/μ -- */

/** The server notes of one response part: the shared ones, then the part's own, prefix dropped. */
function responsePartNotes(payload, prefix) {
  const out = [];
  for (const line of payload?.notes ?? []) {
    const text = String(line);
    const match = PART_NOTE.exec(text);
    if (!match) out.push(text);
    else if (match[1] === prefix) out.push(text.slice(match[0].length));
  }
  return out;
}

/**
 * A server note of a binned part that counts weak and clipped bins over both
 * showers and both σ/μ quantities: the card counts what it draws instead.
 */
const AGGREGATE_BIN_COUNT = /^[\d,]+ bins? with N < \d+ (is|are) weak/;
/** B1's note on bar heights, which says nothing when no bar is drawn. */
const BAR_HEIGHT_NOTE = /^bar heights are/i;

/** The series of a response block the card shows, by the A/B/Both toggle. */
function shownSeries(series, shower) {
  return (series ?? []).filter((s) => !shower || shower === 'both' || s.key === shower);
}

/** A percentage with typographic signs, for the drawer. */
function pctOf(v, digits = 3) {
  return Number.isFinite(v) ? `${num(v, digits)}%` : '—';
}

/**
 * The summary marks of B1 that leave the axis, counted over what the card
 * draws: a histogram series draws only its 1/c rule and interval envelope, a
 * strip series its SD band, mean, interval and 1/c in the band.
 */
function b1ClippedMarks(b1, shown) {
  const lo = b1.axis?.lo;
  const hi = b1.axis?.hi;
  const out = [];
  for (const s of shown) {
    const names = [];
    const r = s.reference;
    if (r && Number.isFinite(r.value)) {
      const cut = clampInterval(r.ci95_lo, r.ci95_hi, lo, hi);
      if (r.value < lo || r.value > hi || cut.cutLo || cut.cutHi) names.push('1/c');
    }
    const m = s.markers;
    if (s.draw !== 'histogram' && m && Number.isFinite(m.mu)) {
      const sd = clampInterval(m.dispersion_lo, m.dispersion_hi, lo, hi);
      const ci = clampInterval(m.ci95_lo, m.ci95_hi, lo, hi);
      if (sd.cutLo || sd.cutHi) names.push('SD band');
      if (ci.cutLo || ci.cutHi) names.push('mean interval');
      if (m.mu < lo || m.mu > hi) names.push('mean');
    }
    if (names.length) out.push(`${s.label}: ${names.join(', ')}`);
  }
  return out;
}

/** Weak and clipped bins of the binned parts, over the series the card draws (addBinPointMarks' test). */
function binnedCounts(series, y, valueOf, { sdBoxes = false } = {}) {
  let bins = 0;
  let weak = 0;
  let clipped = 0;
  for (const s of series) {
    for (const b of s.bins ?? []) {
      const v = valueOf(b);
      if (!Number.isFinite(v)) continue;
      bins += 1;
      if (b.weak) weak += 1;
      const ci = clampInterval(b.ci95?.[0], b.ci95?.[1], y.lo, y.hi);
      let cut = ci.cutLo || ci.cutHi || v < y.lo || v > y.hi;
      if (sdBoxes && Number.isFinite(b.sd)) {
        const sd = clampInterval(v - b.sd, v + b.sd, y.lo, y.hi);
        cut = cut || sd.cutLo || sd.cutHi;
      }
      if (cut) clipped += 1;
    }
  }
  return { bins, weak, clipped };
}

/** The drawer's sentence on a binned part's weak and clipped bins, as the card draws them. */
function binnedSentence(counts, y) {
  const parts = [`${plural(counts.weak, 'drawn bin')} of ${formatInt(counts.bins)} ${counts.weak === 1 ? 'has' : 'have'} N < 20 `
    + '(weak: faded, never below 3:1).'];
  parts.push(y?.provisional
    ? 'The y range is provisional: no bin reaches N = 20.'
    : 'The y range follows the bins with N ≥ 20.');
  parts.push(counts.clipped
    ? `${plural(counts.clipped, 'drawn bin')} ${counts.clipped === 1 ? 'draws a mark' : 'draw a mark'} beyond it, clipped with a caret `
      + '(not rescaled; the true values are in the tooltip).'
    : 'No drawn mark leaves it.');
  return parts.join(' ');
}

/**
 * The notes of one response card. `mode` is 'b1' | 'b2' | 'resolution';
 * `quantity` the σ/μ series kind the card draws, `shower` the A/B/Both
 * toggle. Counts are taken over the marks the card draws.
 */
export function responseNotes({
  payload, mode = 'b1', state = null, experiment = null, quantity = 'calibrated_energy', title = null, shower = 'both',
}) {
  if (!payload) return null;
  const part = RESPONSE_PARTS[mode] ?? RESPONSE_PARTS.b1;
  const notes = new Notes(title ?? PHYSICS_TITLES[part.id]);
  const selection = [physicsSelection(state, experiment)];
  let drawn = responsePartNotes(payload, part.prefix);
  const disclosures = [];
  const legend = [];
  // The Details flag follows the card: a weak or clipped mark it does not draw raises nothing.
  const flags = new Set(hazards(payload, part.id));
  const flag = (name, on) => (on ? flags.add(name) : flags.delete(name));

  if (mode === 'b1' && payload.b1) {
    const b1 = payload.b1;
    const shown = shownSeries(b1.series, shower);
    const anyHistogram = shown.some((s) => s.draw === 'histogram' && s.histogram);
    const anyStrip = shown.some((s) => s.draw !== 'histogram' || !s.histogram);
    if (!anyHistogram) drawn = drawn.filter((line) => !BAR_HEIGHT_NOTE.test(line));
    for (const s of shown) {
      selection.push(`${s.label}: N = ${formatInt(s.n)} events, ${s.draw === 'histogram' ? 'density histogram' : 'individual events'}.`);
      // The numbers a reader takes away, σ below N = 15 with its SE, χ² interval and c₄.
      const m = s.markers ?? {};
      const sigma = sigmaText(s.fit, { unit: '%' });
      if (Number.isFinite(m.mu)) {
        drawn.push(`${s.label}: mean of the per-event fractions ${pctOf(m.mu)}, 95% interval ${pctOf(m.ci95_lo)} … ${pctOf(m.ci95_hi)} `
          + `(Student-t)${sigma ? `; ${sigma} (sample SD, ddof = 1)` : ''}.`);
      }
      if (s.n_dropped) disclosures.push(`${s.label}: ${plural(s.n_dropped, 'event')} dropped for a non-finite or negative deposit or a non-positive momentum.`);
      if (s.n_absent) disclosures.push(`${s.label}: ${plural(s.n_absent, 'selected event')} hold no hit of this shower and are not in the series.`);
      if (s.message) disclosures.push(`${s.label}: ${s.message}`);
    }
    if (b1.axis?.clipping?.note) disclosures.push(b1.axis.clipping.note);
    if (b1.axis?.provisional) disclosures.push('The sampling-fraction axis is provisional: no series reaches N = 20.');
    const clipped = b1ClippedMarks(b1, shown);
    flag('low-statistics bins', anyStrip);
    flag('marks clipped at the axis', clipped.length > 0);
    disclosures.push(clipped.length
      ? `Summary marks that leave the axis are clipped with a caret, the true values in their tooltips (${clipped.join('; ')}).`
      : 'Every summary mark drawn lies inside the axis.');
    // The server names the whisker and the band; they are drawn only for a series below the floor.
    if (anyStrip) legend.push(b1.whisker?.label ?? '', b1.dispersion ?? '');
    if (anyHistogram) {
      legend.push('A series of N ≥ 15 is drawn as its density histogram, which is its own distribution, so no band covers '
        + 'it: its SD is the histogram\'s spread, quoted in its tooltip and above. Two verticals rise from the baseline: '
        + 'the long-dashed one is the mean of the per-event fractions (the notebook\'s estimator) and the dotted one is '
        + '1/c = Σ E_dep / Σ p, the ratio of sums; the two hairlines beside each are its 95% interval, a thin envelope '
        + '(Student-t for the mean, the cluster ratio interval for 1/c). They are two different numbers.');
    }
    if (anyStrip) {
      legend.push('Below N = 15 a series is drawn as its events, ticks in a tinted band at the foot of the plot, captioned '
        + 'there: their heights are drawing offsets, not densities. The band also holds that series\' mean with its capped '
        + '95% Student-t interval, its ± 1 SD as an uncapped shaded bar with dashed edges, and 1/c as an open diamond with '
        + 'its capped 95% interval, from which the dotted 1/c rule rises.');
    }
    if (!anyHistogram) {
      legend.push('No series reaches the histogram floor, so no density is estimable: the density axis carries no name and '
        + 'no scale, and the plot says so.');
    }
  } else if (mode === 'b2' && payload.b2) {
    const b2 = payload.b2;
    const shown = shownSeries(b2.series, shower);
    for (const s of shown) {
      const n = s.bins.reduce((sum, b) => sum + (b.n ?? 0), 0);
      selection.push(`${s.label}: ${plural(s.bins.length, 'momentum bin')}, ${plural(n, 'event')}.`);
    }
    drawn = drawn.filter((line) => !AGGREGATE_BIN_COUNT.test(line));
    const counts = binnedCounts(shown, b2.y ?? {}, (b) => b.mean, { sdBoxes: true });
    flag('low-statistics bins', counts.weak > 0);
    flag('marks clipped at the axis', counts.clipped > 0);
    disclosures.push(binnedSentence(counts, b2.y));
    legend.push(b2.whisker?.label ?? '', b2.dispersion ?? '');
    legend.push('Each SD box is the sample dispersion of its bin, mean ± 1 SD (ddof = 1): uncapped, a wash with a dashed '
      + 'outline. With both showers shown each takes its own half of the bin, A left and B right.');
    legend.push('Dotted horizontal: the selection’s 1/c = Σ E_dep / Σ p, the calibration the energy panel applies, with its '
      + '95% interval as a capped whisker at the rule’s right end. A faded mark is a weak bin (N < 20); an open circle is a '
      + 'bin of one event, with no spread or interval.');
  } else if (mode === 'resolution' && payload.resolution) {
    const r = payload.resolution;
    const shown = shownSeries((r.series ?? []).filter((s) => s.kind === quantity), shower);
    for (const s of shown) {
      const n = s.bins.reduce((sum, b) => sum + (b.n ?? 0), 0);
      selection.push(`${s.label}: ${plural(s.bins.length, 'momentum bin')}, ${plural(n, 'event')}.`);
    }
    drawn = drawn.filter((line) => !AGGREGATE_BIN_COUNT.test(line));
    if (r.note) drawn.push(r.note);
    const counts = binnedCounts(shown, r.y ?? {}, (b) => b.value);
    flag('low-statistics bins', counts.weak > 0);
    flag('marks clipped at the axis', counts.clipped > 0);
    if (counts.bins) {
      disclosures.push(binnedSentence(counts, r.y));
    } else {
      disclosures.push('No drawn bin holds two showers, so no σ/μ is estimable and no scale is shown for one.');
    }
    const dof = shown.flatMap((s) => s.bins.filter((b) => b.dof_note && Number.isFinite(b.value)).map((b) => `${s.label}, ${b.label}: ${b.dof_note}`));
    if (dof.length) disclosures.push(`Low-N bins: ${dof.join('; ')}.`);
    legend.push(r.whisker?.label ?? '');
    legend.push('A faded mark is a weak bin (N < 20); an open circle is a bin with one degree of freedom (N = 2).');
  }
  for (const cal of Object.values(payload.calibration ?? {})) if (cal?.label) drawn.push(cal.label);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.selection, selection);
  notes.section(SECTION.drawn, drawn);
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, legend);
  return notes.done([...flags]);
}

/* ---------------------------------------------------------------- B3 -- */

/** The notes of the B3 small multiples (the response card, or plot 4 of a single-shower experiment). */
export function responseGridNotes({ payload, state = null, experiment = null, shower = 'both', title = null }) {
  if (!payload) return null;
  const notes = new Notes(title ?? RESPONSE_TITLE);
  const slicing = payload.slicing ?? {};
  const sliceText = slicing.mode === 'notebook'
    ? `the notebook's windows ${(slicing.centres ?? []).map((c) => num(c, 0)).join(', ')} ± ${num(slicing.half_width, 1)} GeV`
    : (slicing.mode === 'bins' ? 'the producer\'s 1 GeV momentum bins' : 'the requested momentum windows');
  notes.section(SECTION.selection, [
    physicsSelection(state, experiment),
    `${plural(payload.n_events ?? 0, 'event')}; slices by ${slicing.role ?? 'incident momentum p'} in ${sliceText}; `
      + `every count is of ${payload.counted ?? 'showers'}.`,
  ]);

  const drawn = [];
  if (payload.calibration?.method) drawn.push(`Calibration: ${payload.calibration.method}.`);
  if (payload.segmentation_frame) {
    drawn.push(`Truth and prediction come from the segmentation network of the ${payload.segmentation_frame} frame.`);
  }
  drawn.push('One sub-plot per slice, each on its own energy axis: a density histogram and fitted Gaussian from '
    + `N = ${payload.thresholds?.histogram ?? 15}, a thinner, fainter fitted curve from N = ${payload.thresholds?.curve ?? 8} `
    + 'that does not set the density axis, and below that the events and summary marks only.');
  if (payload.axis?.grid) drawn.push(`Grid: ${payload.axis.grid}.`);
  notes.section(SECTION.drawn, drawn);

  const disclosures = [];
  const slices = gridSlices(payload);
  const two = payload.slice_counts_by_shower?.b != null;
  // The route's warnings state the provisional axes, the values beyond them,
  // the empty slices, the showers in no slice and those with no deposit, per
  // shower (routes_energy.py); the drawer repeats none of them. A payload
  // without a warnings block gets the same facts from its structured fields.
  const serverStates = Array.isArray(payload.meta?.warnings);
  if (!serverStates) {
    const provisional = slices.filter(({ axis }) => axis.provisional).map(({ slice }) => slice.label);
    if (provisional.length) disclosures.push(`Provisional energy axes (no series reaches N = ${payload.thresholds?.histogram ?? 15}): ${provisional.join('; ')}.`);
    for (const { slice, axis } of slices) {
      if (axis.n_outside_axis > 0) disclosures.push(`${slice.label}: ${axis.clipping?.note ?? `${plural(axis.n_outside_axis, 'value')} beyond the axis.`}`);
    }
  }
  let clipped = 0;
  let provisionalY = 0;
  for (const { slice } of slices) {
    const entries = (payload.series ?? []).filter((e) => e.slice === slice.index && (shower === 'both' || e.shower === shower));
    const scale = subplotScale(entries);
    if (scale.provisional) provisionalY += 1;
    clipped += entries.filter((e) => !e.drives_scale && (e.curve_peak ?? 0) > scale.yMax).length;
  }
  if (clipped) disclosures.push(`${plural(clipped, 'low-N curve')} clipped at the top of its sub-plot, with a caret carrying the true peak: the density axis is set by the N ≥ ${payload.thresholds?.histogram ?? 15} series.`);
  if (provisionalY) disclosures.push(`${plural(provisionalY, 'sub-plot')} take their density axis from low-N curves alone and say "provisional" on it.`);
  if (!serverStates) {
    const empty = (payload.slices ?? []).filter((s) => !slices.some(({ slice }) => slice.index === s.index)).map((s) => s.label);
    if (empty.length) disclosures.push(`No showers in: ${empty.join('; ')} (no sub-plot).`);
    // Each shower named when there are two, so a count of A never reads as all showers.
    for (const [key, n] of Object.entries(payload.outside_slices ?? {})) {
      if (n) disclosures.push(`${plural(n, 'shower')}${two ? ` (${key.toUpperCase()})` : ''} fall in no slice: counted and calibrated, drawn nowhere.`);
    }
    for (const [key, n] of Object.entries(payload.no_deposit ?? {})) {
      if (n) disclosures.push(`${plural(n, 'shower')}${two ? ` (${key.toUpperCase()})` : ''} deposited nothing and are left out of the calibration.`);
    }
  }
  const lowN = (payload.series ?? []).filter((e) => e.draw !== 'histogram' && (shower === 'both' || e.shower === shower));
  const messages = new Set(lowN.map((e) => seriesMessage(payload, e)?.replace(/^N = [^:]+: /, '')).filter(Boolean));
  for (const m of messages) disclosures.push(`Low-N series: ${m}`);
  const notesSeen = new Set(lowN.map((e) => estimatorNote(payload, e)).filter(Boolean));
  for (const m of notesSeen) disclosures.push(m);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);

  const marker = payload.momentum_marker ?? {};
  notes.section(SECTION.legend, [
    'Colour is the shower (one shower takes the accent); a network prediction is dashed. Fitted curves are solid; a '
      + 'thinner, fainter curve is a low-N slice that adapts to the axis rather than setting it.',
    'A sub-plot holding a series below the histogram floor has a tinted, captioned band at its foot, whose marks sit at '
      + 'heights that are drawing offsets, not densities: that series\' events as ticks, its mean with the capped 95% '
      + 'Student-t interval and its ± 1 SD as an uncapped shaded bar with dashed edges. A sub-plot of histograms alone '
      + 'has no band.',
    'The dotted vertical in each sub-plot is the slice\'s measured mean incident momentum p, in the shower\'s colour; '
      + 'the two hairlines beside it are its 95% Student-t interval, a thin envelope (often narrower than the line). The '
      + 'SD of p and, at low N, its χ² interval are in its tooltip.',
    [marker.mean, marker.ci95?.label, marker.sd, marker.sd_ci95?.label].filter(Boolean).join(' '),
    `μ and σ of every series are in the fit table: σ with its standard error and, below N = ${payload.thresholds?.core ?? 15}, `
      + 'its asymmetric χ² 95% interval and its bias factor c₄(N).',
  ]);
  notes.section(SECTION.density, [DENSITY_EXPLAINER]);
  return notes.done(hazards(payload, 'response-b3'));
}

/* ---------------------------------------------------------------- C4 -- */

/** The notes of the distribution card; `yScale` is 'linear' | 'log'. */
export function distributionNotes({ payload, yScale = 'linear', state = null, experiment = null, title = null }) {
  if (!payload) return null;
  const notes = new Notes(title ?? PHYSICS_TITLES.distribution);
  const q = payload.quantity ?? {};
  const list = payload.series ?? [];
  notes.section(SECTION.selection, [
    physicsSelection(state, experiment),
    `${q.label ?? q.key}${q.unit ? ` [${q.unit}]` : ''}, weighted by ${q.weighting ?? 'count'}; `
      + `${plural(list.length, 'momentum bin')}${payload.shower && payload.shower !== 'both' ? `, shower ${payload.shower.toUpperCase()} only` : ''}.`,
  ]);
  const drawn = [...(payload.notes ?? [])];
  drawn.push(yScale === 'log'
    ? 'Log count axis: each run of non-empty bins is outlined from the axis floor, and an empty bin is not drawn.'
    : 'Linear count axis from zero: each outline closes at zero.');
  notes.section(SECTION.drawn, drawn);

  const d = payload.display ?? {};
  const disclosures = [d.note ?? ''];
  if (d.coarsened && d.coarsened > 1) disclosures.push(`Display bins merged ${d.coarsened} at a time to keep the response within its budget.`);
  if (d.provisional) disclosures.push('The display range is provisional: set from few entries.');
  const comb = payload.comb;
  if (comb) {
    disclosures.push(comb.combed === null || comb.combed === undefined
      ? `Comb lag-1 on ${comb.axis}: unmeasurable on this selection (${comb.measured_on}).`
      : `Comb lag-1 on ${comb.axis}: ${num(comb.lag1, 2)} against ${num(comb.threshold, 2)}, ${comb.combed ? 'a comb' : 'no comb'} (${comb.measured_on}).`);
  }
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);

  notes.section(SECTION.legend, [
    'Step outlines, one per momentum bin, coloured in momentum order on the chosen sequential ramp (every colour clears '
      + `3:1 against the card). A dashed outline holds fewer than ${SHAPE_FLOOR_SHOWERS} showers: exact counts, not a distribution.`,
    'A caret at an end of the axis carries the counts beyond the display range, per series.',
  ]);
  // A card's own sections follow the four every drawer shares, in their order.
  if (q.key === 'phi') {
    notes.section(PHYSICS_HEADINGS.circular, [
      'φ wraps, so it is shown over its full period and never averaged: each series carries its mean resultant length '
        + 'R̄ and Rayleigh p in its tooltip.',
      ...list.filter((s) => Number.isFinite(s.resultant)).map((s) => `${s.label}: R̄ = ${num(s.resultant, 3)}, Rayleigh p = ${formatSci(s.rayleigh_p, 2)}.`),
    ]);
  }
  return notes.done(hazards(payload, 'distribution'));
}

/* ---------------------------------------------------------------- C8 -- */

/** The notes of a correlation matrix (C8; D3 passes its own `title`). */
export function correlationNotes({ payload, title = null, state = null, experiment = null }) {
  if (!payload) return null;
  const notes = new Notes(title ?? PHYSICS_TITLES.correlation);
  const vars = payload.variables ?? [];
  notes.section(SECTION.selection, [
    physicsSelection(state, experiment),
    [payload.coord_system ? `Frame: ${payload.coord_system}` : '', payload.energy_scale ? `hit energy ${payload.energy_scale}` : '',
      Array.isArray(payload.showers) && payload.showers.length ? payload.showers.join(' and ') : '']
      .filter(Boolean).join('; ')
      + `. N = ${formatInt(payload.n_hits)} hits, ${formatInt(payload.n_showers)} showers, ${formatInt(payload.n_events)} events.`,
  ]);
  notes.section(SECTION.drawn, [
    'Pearson r, lower triangle only (the matrix is symmetric and its diagonal is 1), on PuOr symmetric about zero: '
      + 'linear on [−1, +1], folded on the dark screen and standard in print.',
    ...(payload.notes ?? []),
  ]);
  const disclosures = [];
  if (payload.method) disclosures.push(`Method: ${payload.method}.`);
  if (payload.interval) disclosures.push(`Interval: ${payload.interval}.`);
  if (payload.weak) disclosures.push(`Weak: few independent events (${formatInt(payload.n_events)}); read r with its interval.`);
  const untestable = lowerCells(payload).filter((c) => !c.hatched && Number.isFinite(c.r) && !c.ci95).length;
  if (untestable) disclosures.push(`${plural(untestable, 'cell')} carry r without an interval (too few events for one).`);
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'Each cell prints its r; its tooltip gives the 95% interval, the sample size, n_eff and the weighting. A hatched cell '
      + 'pairs a circular variable; "—" marks an r not estimable below N = 3.',
  ]);
  // A card's own sections follow the four every drawer shares, in their order.
  const circular = vars.filter((v) => v.circular === true || v.circular === 'derived');
  if (circular.length) {
    notes.section(PHYSICS_HEADINGS.circular, [
      `${circular.map((v) => v.label).join(', ')}: circular, so no linear correlation is computed or coloured; the cells are hatched.`,
      payload.mardia?.reason ?? '',
      Number.isFinite(payload.mardia?.null_R2) ? `With no association R² averages ${num(payload.mardia.null_R2, 4)} (null_R2).` : '',
    ]);
  }
  if (payload.weightings) {
    notes.section(PHYSICS_HEADINGS.weightings, Object.entries(payload.weightings).map(([k, v]) => `${k}: ${v}`));
  }
  return notes.done(hazards(payload, 'correlation'));
}

/* ----------------------------------------------------------- C1 + C9 -- */

/** The drawer lines of a C9 negative-depth block (`/api/statistics` or the Local frame). */
export function negativeDepthLines(block) {
  if (!block) return [];
  if (block.available === false) return [block.reason ?? '', block.summary ?? ''];
  const lines = [block.summary ?? ''];
  for (const s of block.splits ?? []) {
    if (!s.n_events) {
      lines.push(`${s.label}: ${s.note || 'no events'}.`);
      continue;
    }
    const share = (k, n, ci) => (Number.isFinite(k) && n ? `${pct(k / n, 1)}${ci ? ` [${pct(ci[0], 1)}, ${pct(ci[1], 1)}]` : ''}` : '—');
    lines.push(`${s.label} (${plural(s.n_events, 'event')}): ${pct(s.energy_fraction)} of the energy, ${pct(s.hits_fraction)} of the hits; `
      + `${share(s.events_with_any, s.n_events, s.events_with_any_ci95)} of events with any`
      + `${s.showers_with_any_ci95 ? `, ${share(s.showers_with_any, s.n_showers, s.showers_with_any_ci95)} of showers` : ''}`
      + `${s.note ? ` (${s.note})` : ''}.`);
  }
  const a = block.affected;
  if (a && a.n) {
    lines.push(`Among the ${plural(a.n, 'shower')} with any such hit, the share of their hits behind the entry plane: `
      + `mean ${pct(a.mean, 1)}, median ${pct(a.q50, 1)}, max ${pct(a.max, 1)}; ${plural(a.n_over_half, 'shower')} above one half.`);
  }
  for (const [k, v] of Object.entries(block.intervals ?? {})) lines.push(`${k.replace(/_/g, ' ')}: ${v}.`);
  return lines;
}

/** The notes of the statistics card. */
export function statisticsNotes({ payload, state = null, experiment = null, title = null }) {
  if (!payload) return null;
  const notes = new Notes(title ?? PHYSICS_TITLES.statistics);
  const describe = payload.describe ?? {};
  notes.section(SECTION.selection, [
    physicsSelection(state, experiment),
    `${plural(describe.n_hits ?? 0, 'hit')} in ${plural(payload.n_events ?? 0, 'event')}; frame ${describe.coord_system ?? '—'}.`,
  ]);
  notes.section(SECTION.drawn, [...(payload.notes ?? [])]);
  const disclosures = [];
  for (const row of [...(describe.rows ?? []), ...(describe.shifted_row ? [describe.shifted_row] : [])]) {
    if (row.note) disclosures.push(`${row.label}: ${row.note}`);
    if (Number.isFinite(row.display_offset_mm)) {
      disclosures.push(`${row.label} is the reference notebook's display offset of ${num(row.display_offset_mm, 0)} mm, a labelled row, not another coordinate.`);
    }
  }
  disclosures.push(...metaDisclosures(payload));
  notes.section(SECTION.disclosures, disclosures);
  notes.section(SECTION.legend, [
    'A table, not a chart: the first eight columns are unweighted (every hit one observation), the last four '
      + 'weight every hit by its energy. ⚑ flags a row computed from few hits; its note is on the label. In the '
      + 'negative-depth table every fraction carries its 95% interval in brackets.',
  ]);
  // A card's own sections follow the four every drawer shares, in their order.
  notes.section(PHYSICS_HEADINGS.estimators, [describe.estimator ?? '', describe.weighting_note ?? '']);
  notes.section(PHYSICS_HEADINGS.negative, negativeDepthLines(payload.negative_w));
  return notes.done(hazards(payload, 'statistics'));
}

/* ----------------------------------------------------------- hazards -- */

/** Structural hazards of the physics cards, by card id; never text matching. */
const PHYSICS_HAZARDS = {
  'profile-w': (payload) => profileHazards(payload, 'depth'),
  'profile-r': (payload) => profileHazards(payload, 'r'),
  'response-b1': (payload) => {
    const out = [];
    const series = payload.b1?.series ?? [];
    if (series.some((s) => s.draw !== 'histogram')) out.push('low-statistics bins');
    if (series.some((s) => s.n_dropped > 0)) out.push('non-finite ratios dropped');
    if (payload.b1?.axis?.n_clipped_marks) out.push('marks clipped at the axis');
    if (payload.b1?.axis?.provisional) out.push('provisional range');
    return out;
  },
  'response-b2': (payload) => binnedHazards(payload, payload.b2),
  'response-res': (payload) => binnedHazards(payload, payload.resolution),
  'response-b3': (payload) => {
    const out = hazards(payload, 'energy');
    const axes = payload.slice_axes ?? [];
    if (axes.some((a) => a.n_outside_axis > 0) && !out.includes('clipped energy range')) out.push('clipped energy range');
    if (axes.some((a) => a.provisional)) out.push('provisional range');
    return out;
  },
  distribution: (payload) => {
    const out = [];
    if ((payload.display?.n_outside ?? 0) > 0) out.push('clipped range');
    if (payload.meta?.exact === false) out.push('sampled');
    if (payload.comb?.combed === true) out.push('measured comb');
    return out;
  },
  correlation: (payload) => {
    const out = [];
    if ((payload.variables ?? []).some((v) => v.circular === true || v.circular === 'derived')) out.push('circular variable');
    if (lowerCells(payload).some((c) => !c.hatched && Number.isFinite(c.r) && !c.ci95)) out.push('interval untestable');
    if (payload.weak) out.push('weak sample');
    if (payload.meta?.exact === false) out.push('sampled');
    return out;
  },
  statistics: (payload) => {
    const out = [];
    if (payload.meta?.exact === false) out.push('approximate quantiles');
    const rows = [...(payload.describe?.rows ?? []), ...(payload.describe?.shifted_row ? [payload.describe.shifted_row] : [])];
    if (rows.some((r) => r.note)) out.push('small sample');
    if (payload.negative_w?.available === false) out.push('negative depth unavailable');
    return out;
  },
};

/** The cells a correlation matrix draws: below the diagonal (the diagonal is 1 by construction). */
function lowerCells(payload) {
  const out = [];
  (payload?.matrix ?? []).forEach((row, i) => row.forEach((cell, j) => { if (j < i && cell) out.push(cell); }));
  return out;
}

function profileHazards(payload, axis) {
  const out = [];
  const key = profileAxisKey(payload, axis);
  const ax = key ? payload.axes?.[key] : null;
  const n = payload.ensemble?.n_showers ?? 0;
  if (n === 1) out.push('single shower');
  if (ax?.y?.provisional || payload.ensemble?.provisional) out.push('provisional range');
  const o = ax?.outside ?? {};
  if ((o.below_fraction ?? 0) > 0 || (o.above_fraction ?? 0) > 0) out.push('energy beyond the profile range');
  if (ax?.comb?.combed === true) out.push('measured comb');
  if (payload.meta?.exact === false) out.push('sampled preview');
  return out;
}

function binnedHazards(payload, block) {
  const out = [];
  const bins = (block?.series ?? []).flatMap((s) => s.bins ?? []);
  if (bins.some((b) => b.weak)) out.push('low-statistics bins');
  if (block?.y?.n_clipped) out.push('marks clipped at the axis');
  if (block?.y?.provisional) out.push('provisional range');
  if ((payload.b1?.series ?? []).some((s) => s.n_dropped > 0)) out.push('non-finite ratios dropped');
  return out;
}
