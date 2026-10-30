/* What the Details drawer says about the 3-D views and their paired 2-D
 * projections, in the four sections of panel_notes.js (Selection / What is
 * drawn / Disclosures / Marks and legend).
 *
 * The 3-D cards never export, so their drawer is the only place a reader
 * finds what the picture leaves out. It therefore states, besides the
 * server's own sentences, what the chart itself decided - how many cubes the
 * taper left transparent or translucent, which species the isolate toggles
 * hide, how many primary-tagged cubes carry a halo - from the summary the
 * option builder returns (voxels.js `voxelOption`), never from the page. The
 * recorded exception the 3-D views live under (CLAUDE.md section 2) is quoted
 * in every 3-D drawer, so a reader knows what the picture may and may not be
 * read for.
 *
 * Each builder takes `{payload, ...}` and returns `{title, hazards,
 * sections}`, or null with no payload; `hazards` are structural, never text
 * matched.
 */

import { Notes, SECTION, eventNotes, projectionNotes, onLightScreen } from './panel_notes.js';
import { legibleRamp } from './panels/chart_panel.js';
import { describeSelection } from './export/caption.js';
import { formatInt, formatSci, formatPercent, screenPalette, typographic } from './scale.js';
import { HALO_LIMIT, referenceTopLabel, speciesLabel } from './voxels.js';

/** The card titles of the section, by card id. */
export const VOXEL_TITLES = Object.freeze({
  'vox-event': 'One Event in 3-D — Detector Cells',
  'vox-ensemble': 'The Selection in 3-D — Voxel Cloud',
});

/** The recorded exception, as every 3-D drawer states it. */
export const VOXEL_EXCEPTION =
  'A 3-D view under the recorded exception to the no-3-D rule: an orthographic camera (no '
  + 'perspective, so no length is foreshortened), one millimetre the same length along all three '
  + 'axes (1:1:1, from the physical spans), every cube the measured size of what it stands for, flat '
  + 'unlit colour (lighting would change the brightness that encodes the value), and always beside '
  + 'the three 2-D projections, which carry the same selection quantitatively. A rotated 3-D picture '
  + 'is not a publication figure, so this card has no export; the projections beside it are the '
  + 'exportable figures.';

/** What hides what in 3-D, and where to read the rest. */
export const VOXEL_OCCLUSION =
  'In 3-D a cube hides whatever lies behind it from the current viewpoint; rotate to look behind it. '
  + 'Nothing is hidden in the 2-D projections beside this card.';

/** The three ensemble-cloud channels, as a reader names them. */
const ENSEMBLE_CHANNELS = {
  density: 'energy density ρ, relative to ρ_ref',
  gradcam_energy: 'Σ E·Grad-CAM, relative to cam_ref',
  shapcam_energy: 'Σ E·Shap-CAM (signed), relative to |cam_ref|',
};

/** The five event channels. */
const EVENT_CHANNELS = {
  energy: 'volumetric energy density E/V',
  gradcam: 'Grad-CAM attention',
  shapcam: 'Shap-CAM attribution (signed)',
  segerr: 'segmentation error |f_A,pred − f_A,true|',
  species: 'particle species',
};

const plural = (n, word, many = `${word}s`) => `${formatInt(n)} ${n === 1 ? word : many}`;

/** The filters line, or nothing under a bare test. */
function filtersLine(state, experiment) {
  return state ? describeSelection(state, experiment, null, null, null, { filtersOnly: true }) : '';
}

/** The server's notices as lines (strings, or `{text}` objects). */
function noticeLines(notices) {
  return (notices ?? []).map((n) => (typeof n === 'string' ? n : n?.text ?? '')).filter(Boolean);
}

/** One shower of the event block as a line. */
function showerLine(s) {
  const angle = (v) => (Number.isFinite(v) ? `${typographic(Number(v).toFixed(1))}°` : '—');
  const p = Number.isFinite(s.momentum_gev) ? `p = ${typographic(Number(s.momentum_gev).toFixed(2))} GeV, ` : '';
  return `Shower ${s.label ?? String(s.key).toUpperCase()}: ${plural(s.n_hits, 'cell')}, `
    + `${formatSci(s.energy_gev, 3)} GeV deposited, ${p}θ = ${angle(s.theta_deg)}, φ = ${angle(s.phi_deg)}.`;
}

/** The event's place in the selection, and the rule that chose it. */
function eventSelection(event, pick) {
  const lines = [];
  if (!event) return lines;
  const drawn = (event.showers ?? []).map((s) => s.label ?? String(s.key).toUpperCase());
  lines.push(`Event ${formatInt(event.event_number)}`
    + (drawn.length ? `, ${drawn.length > 1 ? 'showers' : 'shower'} ${drawn.join(' and ')} drawn` : '')
    + `; ${event.in_selection === false ? 'outside the current selection, drawn as asked' : 'inside the current selection'}.`);
  for (const s of event.showers ?? []) lines.push(showerLine(s));
  if (pick?.rule) lines.push(`Chosen by rule, not written to the link: ${pick.rule}`);
  return lines;
}

/** A plain list "a, b and c". */
function listText(items) {
  if (items.length < 2) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** What every on-screen sequential ramp of the 3-D cards does (decision D-2, scale.js `rampTable`). */
export const LEGIBLE_RAMP_NOTE = 'On screen the ramp starts at its first colour with at least 3:1 contrast '
  + 'against the card (Viridis from 0.376 of its range; the measured 3:1 run of the other palettes), so no '
  + 'opaque cube - a cube below the ramp floor included - is drawn darker than the card can show.';

/**
 * `LEGIBLE_RAMP_NOTE` for the card in force. The constant is the dark card's
 * sentence and stays byte for byte (the dark golden records it). On the light
 * screen a slot draws its white-grounded ramp (palette.js), and a cube takes
 * that ramp's run at 3:1 or more, so what the card cannot show is a cube
 * drawn too faint.
 */
export function legibleRampNote() {
  if (!onLightScreen()) return LEGIBLE_RAMP_NOTE;
  const { from } = legibleRamp(screenPalette('viridis'));
  return 'On the light screen each colour-map slot draws a ramp made for a white card, and a cube, which stands '
    + 'alone on the card, takes only its run at 3:1 or more (the Viridis slot from '
    + `${from.toFixed(3)} of its aqua-to-indigo ramp; the measured run of the others), so no opaque cube - a cube `
    + 'below the ramp floor included - is drawn fainter than the card can show.';
}

/* -------------------------------------------------------------- event -- */

/**
 * The notes of the 3-D event card.
 *
 * `payload` is the `/api/event?format=voxels` response; `drawn` the option
 * builder's summary (`{drawn, skipped, translucent, primaries, halos}`);
 * `hidden` the species codes the isolate toggles hide; `pick` the densest
 * pick when the link names no event; `fallbacks` the sentences of a frame,
 * channel or shower drawn in place of the selected one; `gl` null when the
 * view is drawn, else the notice that says why it is not.
 */
export function voxelEventNotes({
  payload, drawn = null, hidden = [], pick = null, fallbacks = [], gl = null,
  state = null, experiment = null, title = null,
}) {
  const vox = payload?.voxels;
  if (!vox) return null;
  const notes = new Notes(title ?? VOXEL_TITLES['vox-event']);
  const event = payload.event ?? {};
  notes.section(SECTION.selection, [...eventSelection(event, pick), filtersLine(state, experiment)]);

  const scale = vox.scale ?? {};
  const channel = EVENT_CHANNELS[vox.channel] ?? vox.channel;
  const network = vox.model ? `, read from the ${vox.model} network` : '';
  notes.section(SECTION.drawn, [
    VOXEL_EXCEPTION,
    `Coloured by ${channel}${network}.`,
    vox.geometry?.note ?? '',
    vox.geometry?.depth?.note ? `Depth: ${vox.geometry.depth.note}.` : '',
    scale.floor_rule ?? '',
    payload.meta?.cam?.note ?? '',
    vox.species?.rule ?? '',
    payload.coordinates?.note ?? '',
    payload.window?.rule ?? '',
    ...fallbacks,
  ]);

  const disclosures = [...noticeLines(payload.meta?.notices), ...(vox.notes ?? [])];
  if (gl) disclosures.push(gl);
  if (drawn) {
    if (drawn.skipped > 0) {
      const byToggle = hidden.length
        ? `the species toggles hide ${listText(hidden.map((code) => speciesLabel(
          vox.scale?.codes?.find((c) => c.code === code)?.name ?? String(code))))}`
        : '';
      const noValue = drawn.noValue > 0 ? `${plural(drawn.noValue, 'cube')} carry no value (code 0)` : '';
      disclosures.push(`${plural(drawn.skipped, 'cube')} of the ${formatInt(vox.cubes?.n ?? 0)} shipped `
        + `${drawn.skipped === 1 ? 'is' : 'are'} not drawn: ${[noValue, byToggle].filter(Boolean).join('; ')}.`);
    }
    if (drawn.primaries > drawn.halos) {
      disclosures.push(`${plural(drawn.primaries, 'primary-tagged cube')} drawn; halos mark the `
        + `${formatInt(drawn.halos)} most energetic (at most ${HALO_LIMIT}), the rest say so in their tooltips.`);
    }
  }
  if (event.primary_note) disclosures.push(event.primary_note);
  if (event.d_frame?.ill_conditioned) {
    disclosures.push('The two entry points of this event lie closer than the D-frame\'s ill-conditioning '
      + 'threshold, so its A→B rotation ψ is poorly defined.');
  }
  disclosures.push(VOXEL_OCCLUSION);
  disclosures.push(...(payload.meta?.warnings ?? []));
  notes.section(SECTION.disclosures, disclosures);

  const legend = [];
  if (scale.scale === 'categorical') {
    legend.push('Each cube takes the colour of its species in the legend under the plot: stable codes across '
      + 'events (e⁻, e⁺, γ, n, p, π⁺, π⁻, then every other particle as "other", in grey), on a qualitative '
      + 'palette whose every pair stays apart under simulated deuteranopia and protanopia. The tick boxes '
      + 'hide a species; "only" isolates one.');
  } else if (scale.degenerate) {
    legend.push('Every drawn cube holds the same density, so the ramp has no range and no legend: every cube is '
      + 'drawn in its top colour.');
  } else {
    legend.push('The colour bar at the right is the ramp the cubes are painted with, labelled in the channel\'s '
      + 'own units; it is the 2-D panels\' code-to-colour table, so a cube and the bin beside it agree.');
    legend.push(legibleRampNote() + (scale.diverging
      ? ' A raw Shap-CAM cube near zero takes its sign\'s first 3:1 colour (orange or purple) where the 2-D '
        + 'panels draw zero in border grey: a cube prints no number, so none may vanish.'
      : ''));
  }
  legend.push(`A halo - a ${onLightScreen() ? 'dark outer and a light inner' : 'light outer and a dark inner'} outline - marks a primary-tagged cube (is_secondary = 0).`);
  if ((vox.cubes?.shower_codes ?? []).filter((c) => c && c !== '—').length > 1) {
    legend.push(`Each cube's tooltip names whose rows it holds: ${listText(vox.cubes.shower_codes)}.`);
  }
  legend.push(`The ${formatInt((vox.topk ?? []).length)} ${onLightScreen() ? 'highest-valued' : 'brightest'} cubes carry exact values in their tooltips; `
    + 'every other value is read back from its 8-bit colour code and labelled so.');
  notes.section(SECTION.legend, legend);

  const hazards = [];
  if (gl) hazards.push('3-D view not drawn');
  if (event.in_selection === false) hazards.push('event outside the selection');
  if ((vox.cap?.n_beyond ?? 0) > 0) hazards.push('cap reached');
  if (scale.degenerate) hazards.push('degenerate ramp');
  if (hidden.length) hazards.push('species hidden');
  if (fallbacks.length) hazards.push('drawn in another frame or channel');
  if (event.d_frame?.ill_conditioned) hazards.push('ill-conditioned D-frame');
  return notes.done(hazards);
}

/* ----------------------------------------------------------- ensemble -- */

/** The five energy categories of the budget, as one sentence. */
export function energyFractionSentence(budget) {
  const f = budget?.energy_fraction;
  if (!f) return '';
  const total = Number.isFinite(budget.energy_total_gev) ? ` ${formatSci(budget.energy_total_gev, 4)} GeV` : '';
  return `Of the selection's${total} deposited energy: ${formatPercent(f.drawn, 2)} drawn, `
    + `${formatPercent(f.below_floor, 2)} in voxels below the 10⁻³ floor, ${formatPercent(f.beyond_cap, 2)} beyond `
    + `the cap of ${formatInt(budget.cap)} voxels, ${formatPercent(f.partial_edge, 4)} in half-width edge voxels `
    + `and ${formatPercent(f.outside_grid, 4)} outside the grid - every category counted, none dropped.`;
}

/** The attention channel's own budget (its signed sum by category), when it has one. */
function camBudgetSentence(cam) {
  if (!cam || !Number.isFinite(cam.total)) return '';
  return `Of the selection's ${formatSci(cam.total, 4)} ${cam.unit ?? ''} of ${cam.quantity}: `
    + `${formatSci(cam.drawn, 4)} drawn, ${formatSci(cam.below_floor, 4)} below the floor, `
    + `${formatSci(cam.beyond_cap, 4)} beyond the cap, ${formatSci(cam.outside_grid, 4)} outside the grid.`;
}

/** An axis range in mm, "−940 to 940 mm", with the frame's symbol. */
function rangeText(symbol, range) {
  if (!Array.isArray(range) || !range.every(Number.isFinite)) return `${symbol} —`;
  const fmt = (v) => typographic(Number.isInteger(v) ? String(v) : Number(v).toFixed(2).replace(/\.?0+$/, ''));
  return `${symbol} ${fmt(range[0])} to ${fmt(range[1])} mm`;
}

/**
 * The crop of the ensemble box (voxels.js `cropToWindow`), as disclosures:
 * the window it took from the paired projections, the full accumulation-grid
 * extent, and the cubes it leaves out with their share. Empty without a crop
 * record (a bare test of the notes).
 */
export function cropLines(crop, symbols = {}, channel = 'density') {
  if (!crop) return [];
  const axes = ['x', 'y', 'z'];
  const sym = (a) => symbols[a] ?? a;
  const extent = crop.extent
    ? `The accumulation grid spans ${axes.map((a) => rangeText(sym(a), crop.extent[a])).join(', ')}.` : '';
  if (!crop.window) {
    return ['The paired projections did not load, so the box is the whole accumulation grid, not their window.', extent];
  }
  const quantity = { density: 'summed density ρ (its energy, the voxels being of one volume)',
    gradcam_energy: 'summed Σ E·Grad-CAM', shapcam_energy: 'summed |Σ E·Shap-CAM|' }[channel] ?? 'summed value';
  return [
    `The box is cropped to the paired projections' window: ${axes.map((a) => rangeText(sym(a), crop.window[a])).join(', ')} - `
      + 'on each axis the widest of the 2-D panels that show it, each symmetric about the origin on the transverse axes at '
      + 'the energy-weighted 0.1st-99.9th percentile (the recorded window of the co-registered frames), so the cloud and '
      + 'its projections show one region.',
    extent,
    crop.nOutside > 0
      ? `${plural(crop.nOutside, 'voxel')} above the floor ${crop.nOutside === 1 ? 'lies' : 'lie'} outside that window and `
        + `${crop.nOutside === 1 ? 'is' : 'are'} not drawn: ${formatPercent(crop.shareOutside, 2)} of the shipped cloud's ${quantity}, `
        + 'read back from the colour codes; counted, never dropped silently.'
      : 'Every voxel above the floor lies inside that window.',
  ];
}

/**
 * The notes of the 3-D ensemble card: the `/api/voxels` response, the option
 * builder's summary `drawn`, the frame and channel fallbacks, `gl` as for the
 * event card, and `crop` the box's crop to the paired projections' window
 * (voxels.js `cropToWindow`).
 */
export function voxelEnsembleNotes({
  payload, drawn = null, fallbacks = [], gl = null, state = null, experiment = null, title = null, crop = null,
}) {
  if (!payload?.voxels || !payload.grid) return null;
  const notes = new Notes(title ?? VOXEL_TITLES['vox-ensemble']);
  const frame = payload.frame ?? {};
  const grid = payload.grid;
  const scale = payload.scale ?? {};
  const rho = payload.rho ?? {};
  const meta = payload.meta ?? {};

  notes.section(SECTION.selection, [
    filtersLine(state, experiment),
    `${plural(frame.n_events ?? 0, 'event')}, ${plural(frame.n_showers ?? 0, 'shower')} in the ${frame.title ?? frame.kind} frame`
      + (frame.n_excluded_no_frame ? `; ${plural(frame.n_excluded_no_frame, 'event')} without a frame excluded and counted` : '')
      + '.',
    frame.n_label ?? '',
  ]);

  const [vx, vy, vz] = grid.voxel_mm ?? [];
  const symbols = frame.symbols ?? {};
  notes.section(SECTION.drawn, [
    VOXEL_EXCEPTION,
    `Coloured by ${ENSEMBLE_CHANNELS[meta.channel] ?? meta.channel}; voxels ${vx} × ${vy} × ${vz} mm `
      + `along (${symbols.x}, ${symbols.y}, ${symbols.z}).`,
    grid.alignment ?? '',
    frame.depth?.text ? `Depth: ${frame.depth.text}.` : '',
    grid.z_uniform === false
      ? 'The depth axis is the native layers, placed at their own centres, never assumed uniform.' : '',
    scale.floor_rule ? `Drawn ${scale.floor_rule}.` : '',
    rho.basis ? `ρ_ref is the ${rho.basis}${Number.isFinite(rho.rho_ref) ? ` (${formatSci(rho.rho_ref, 3)} GeV mm⁻³ per event)` : ''}.` : '',
    rho.bound ?? '',
    rho.norm_note ?? '',
    rho.floor_note ?? '',
    meta.cam?.note ?? '',
    'No ensemble direction is drawn on the cloud in either frame: the 2-D D-frame projections carry its '
      + 'measured axes with their dispersion and interval, and in the Local frame every incident direction is '
      + '+w by construction.',
    ...fallbacks,
  ]);

  const disclosures = [...noticeLines(meta.notices)];
  disclosures.push(energyFractionSentence(payload.budget));
  disclosures.push(camBudgetSentence(payload.budget?.cam));
  if ((payload.budget?.n_beyond_cap ?? 0) > 0) {
    disclosures.push(`${plural(payload.budget.n_beyond_cap, 'voxel')} above the floor lie beyond the cap of `
      + `${formatInt(payload.budget.cap)}, ranked by energy, and are counted, not drawn.`);
  }
  disclosures.push(grid.partial_edge?.note ?? '');
  disclosures.push(...cropLines(crop, frame.symbols ?? {}, meta.channel));
  disclosures.push(frame.comb_source ?? '');
  if (frame.comb?.note) disclosures.push(frame.comb.note);
  if (frame.coordinate_check?.note) disclosures.push(frame.coordinate_check.note);
  if (frame.negative_w?.summary) disclosures.push(`Behind the entry plane (${frame.negative_w.summary}).`);
  if (gl) disclosures.push(gl);
  if (drawn?.skipped > 0) {
    disclosures.push(`${plural(drawn.skipped, 'voxel')} at the bottom of the floor taper ${drawn.skipped === 1 ? 'is' : 'are'} `
      + 'fully transparent, as the same bins are in the 2-D projections.');
  }
  if (drawn?.translucent > 0) {
    disclosures.push(`${plural(drawn.translucent, 'voxel')} within half a decade of the floor ${drawn.translucent === 1 ? 'is' : 'are'} `
      + 'drawn translucent, fading into the card as the 2-D rasters do, so the halo ends without a rim.');
  }
  disclosures.push(VOXEL_OCCLUSION);
  disclosures.push(...(meta.warnings ?? []));
  if (meta.exact === false) disclosures.push('Sampled preview: the exact cloud follows.');
  notes.section(SECTION.disclosures, disclosures);

  const provisional = Boolean(frame.provisional || rho.provisional);
  const topLabel = referenceTopLabel({ kind: 'ensemble', scale, refName: scale.ref_name ?? 'rho_ref' });
  notes.section(SECTION.legend, [
    'The colour bar at the right is the 2-D panels\' relative ramp (three decades below the reference, '
      + 'fading to transparent at the floor, and reaching its first 3:1 colour where the fade turns opaque, '
      + '10⁻²·⁵ of the reference'
      + (topLabel ? `; its top is labelled "${topLabel}"` : '')
      + ')'
      + (scale.scale === 'signed_log10' ? ', diverging on PuOr: orange negative, purple positive' : '')
      + (provisional ? '; it is labelled provisional because the selection is too small to fix its reference.' : '.'),
    `The ${formatInt((payload.topk ?? []).length)} ${onLightScreen() ? 'highest-valued' : 'brightest'} voxels carry exact values in their tooltips; every `
      + 'other value is read back from its 8-bit colour code and labelled so.',
  ]);

  const hazards = [];
  if (gl) hazards.push('3-D view not drawn');
  if (provisional) hazards.push('provisional range');
  if (frame.comb?.staggered) hazards.push('measured comb');
  if ((payload.budget?.n_beyond_cap ?? 0) > 0) hazards.push('cap reached');
  if (meta.exact === false) hazards.push('sampled preview');
  if ((frame.n_events ?? 0) === 0) hazards.push('empty selection');
  if (fallbacks.length) hazards.push('drawn in another frame or channel');
  return notes.done(hazards);
}

/* --------------------------------------------------------- projections -- */

/** A notes object with lines added to one section (created when absent). */
function withLines(notes, heading, lines) {
  if (!notes) return notes;
  const kept = lines.filter(Boolean);
  if (!kept.length) return notes;
  const sections = notes.sections.map((s) => (s.heading === heading ? { ...s, lines: [...s.lines, ...kept] } : s));
  if (!sections.some((s) => s.heading === heading)) sections.push({ heading, lines: kept });
  return { ...notes, sections };
}

/**
 * The notes of one paired 2-D projection.
 *
 * `pair` 'event': `payload` is the Event Inspector's `/api/event` raster
 * response, `frameKind` the frame drawn (lab | trans | local). `pair`
 * 'ensemble': `payload` is the `/api/projections` response. `panelId` is
 * xy | xz | yz; `pairing` the sentences that tie the cell to its 3-D view
 * (what it shares, what it draws differently).
 */
export function voxelProjectionNotes({
  pair, payload, panelId, frameKind = 'lab', view = null, isometric = {}, pairing = [],
  state = null, experiment = null, title = null,
}) {
  if (!payload) return null;
  let notes = null;
  if (pair === 'event') {
    // The inspector's window is shared by its nine panels; this pair has three, and asks for
    // per-axis half-widths (`window=per_axis`), which eventNotes names axis by axis.
    notes = eventNotes({
      payload, kind: frameKind, panelId, view, state, experiment, windowScope: 'all three projections',
    });
  } else {
    notes = projectionNotes({ payload, panelId, isometric, view, state, experiment });
  }
  if (!notes) return null;
  if (title) notes = { ...notes, title };
  return withLines(notes, SECTION.drawn, pairing);
}
