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
} from './frame_views.js';
import { figureDisclosure } from './export/disclosure.js';
import { describeSelection, describeView, displayOf } from './export/caption.js';
import { panelSymbols } from './axis_symbols.js';
import { formatSci } from './scale.js';

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
