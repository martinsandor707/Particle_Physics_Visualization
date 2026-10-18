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
 */

import {
  footnotes, exportLegend, kindOf, panelTitle, energyNetworkSentence,
  eventRowLabel, eventSelectionLine, eventFrameSentence, num, pct,
} from './frame_views.js';
import { figureDisclosure } from './export/disclosure.js';
import { describeSelection, describeView, displayOf } from './export/caption.js';
import { panelSymbols } from './axis_symbols.js';
import { formatSci, formatInt } from './scale.js';

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
class Notes {
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
 * under a bare Node test, which then gets no selection line).
 */
export function projectionNotes({
  payload, panelId, isometric = {}, view = null, state = null, experiment = null,
}) {
  const panel = payload?.panels?.[panelId];
  if (!panel) return null;
  const kind = kindOf(payload);
  const frame = payload.frame ?? null;
  const notes = new Notes(panelTitle(panelId, kind));

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

  const footnote = footnotes(payload, { isometric })[panelId] ?? '';
  notes.section(SECTION.drawn, [footnote]);
  notes.section(SECTION.disclosures, figureDisclosure(
    payload, panelId, state, { isometric: Boolean(isometric[panelId]) },
  ));
  if (kind !== 'lab') notes.section(SECTION.legend, [exportLegend(panelId, payload)]);
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
 * yz). `payload` is the whole `/api/event` response.
 */
export function eventNotes({
  payload, kind, panelId, view = null, state = null, experiment = null,
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

  const half = Number.isFinite(frame.half_mm) ? `${num(frame.half_mm, 0)} mm` : 'one';
  notes.section(SECTION.drawn, [
    eventFrameSentence(payload, kind),
    payload.window?.rule ?? '',
    `Axes 1:1 (isometric), ${half} half-width on every axis of all nine panels, so the tilt reads at `
    + 'its true angle; the raster covers the populated part of the window and the rest is empty.',
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
