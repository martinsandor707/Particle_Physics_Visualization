/* The energy resolution against 1/√E: the `res-scaling` card of the Models page.
 *
 * `/api/resolution-scaling` (query/resolution_scaling.py) ships one series per
 * (estimator, shower): the detector's calibrated deposit c·E_dep, and where the
 * experiment has one the energy network of the selected frame or the XGBoost
 * momentum regressor on its validation split. Each series carries σ/E per
 * 1 GeV momentum window - s(R)/R̄ of the per-event ratio R = E_est / p, in
 * percent - and, for both window modes, three weighted least-squares fits: the
 * affine a/√E + b, the origin-pinned a₀/√E and the quadrature √(a²/E + b²).
 * Everything here is drawn from those fields; nothing is refitted or rescaled
 * in the browser, and the window mode and the shower choice only repaint.
 *
 * ## A reversed 1/√E axis that ends at the origin
 *
 * The stochastic term a/√E is a straight line through the origin in
 * x = 1/√E, and x = 0 is E → ∞. The bottom axis therefore runs from 0.5 at the
 * left to exactly 0 at the right border (`inverse`), and the y axis starts at
 * zero, so the bottom-right corner is the origin a pure stochastic term runs
 * into. A window below 4 GeV has x > 0.5 and lies off the axis: it is never
 * drawn, and the drawer lists it with its value.
 *
 * The top axis is a second x axis with the same range and direction whose
 * ticks sit at x = 1/√E for round energies, labelled E = 1/x², and ∞ at
 * x = 0. It is an exact relabelling of the bottom axis - a deterministic unit
 * conversion, the one kind of second axis CLAUDE.md section 2 allows - and no
 * series is plotted against it.
 *
 * ## The whisker is the uncertainty of the window's σ/E
 *
 * A window's marker carries a capped whisker, the χ²_{N−1} 95% interval of s
 * divided by R̄, only from N = 8 (the curve floor of the low-N table): it is
 * the uncertainty of the plotted aggregate, never the spread of the events.
 * The whisker is the series' colour on a casing, so it reads over the bands
 * and the lines behind it. From N = 2 to 7 the window is a faded hollow ring
 * with a dashed outline and no whisker, and its tooltip names the N = 8 floor.
 * A window below N = 20 is faded (`legibleOpacity`, never below 3:1 against
 * the card) and fitted only by a provisional fit, where a series has fewer
 * than two windows of N ≥ 20; it never sets the y range. A mark
 * beyond the server's range is clipped at the axis with a caret whose tooltip
 * gives the true value. Series whose windows share an x (a detector and a
 * network series read the same events) are set a few pixels apart.
 *
 * ## The fits are lines with their 95% confidence bands
 *
 * The affine fit is a line and the origin-pinned fit a thinner dotted one, each
 * with its 95% confidence band from the parameter covariance: ±1.96 √(gᵀΣg)
 * while the windows' own standard errors stand, ±t₀.₉₇₅,ν √(gᵀΣg) once the PDG
 * factor S = √(χ²/ν) > 1 scales Σ (S is then estimated from the fit's own ν;
 * the server ships the quantile). It is the uncertainty of the fitted line, not
 * the spread of the events, and the band's tooltip says so. The affine band is
 * a wash at `bandAlpha`, the pinned one at half of it. A line and its band are
 * clipped to the plot: an affine fit with a negative intercept runs down to the
 * axis and stops there. A line or band that leaves the top of the plot (a
 * provisional fit never sets the range, and a band may be far wider than its
 * line) is clipped and said so, as a weak window is: a caret where it leaves,
 * its true values in the caret's tooltip, and a count in the drawer. A
 * provisional fit (fewer than two windows of N ≥ 20, so it runs through
 * windows of N ≥ 8) is drawn faded. A fit whose iterated weights did not
 * settle says so in its tooltip, the table and the drawer. On this view the
 * quadrature fit is never drawn; it is tabled. The E view draws it (below).
 *
 * ## Colour is the estimator, fill and dash are the shower
 *
 * The detector series is drawn in ink (`THEME.text`), the neutral reference;
 * a model series takes the hue E2 gives its source (perf_bins.js
 * `sourceColours`, in the order absolute, translated, Local, XGBoost), so a
 * network keeps its colour across the cards. Shower A is a filled marker and a
 * solid affine line, shower B a hollow marker and a dashed affine line, so the
 * two read apart in greyscale too. Every mark of a series - markers, whiskers,
 * carets, lines and bands - carries the series' name, so its legend entry
 * shows and hides all of it.
 *
 * ## The fit table
 *
 * Under the plot, on screen only, the panel keeps a table of the fits of the
 * mode in force: one row group per series drawn, one row per fit (affine,
 * origin-pinned, quadrature), each with its a and b (or the undefined
 * quadrature term with its standard error), χ²/ν with its p, the scale factor
 * S and its status; the series and the windows it fitted, with their
 * substitutions, span the group. Its text columns wrap, so it keeps to the
 * card's width. It is built with `createElement` and `textContent` only, from
 * the pure `fitTableRows`. The export is the chart alone.
 *
 * ## The E view: σ/E against E in GeV, with a ratio panel
 *
 * `opts.view === 'energy'` draws the same response a second way
 * (`energyViewOption`, Martin's decisions of 2026-11-10); every other view is
 * the 1/√E view above, whose option and table do not change. Nothing is
 * refitted: each window sits at E = 1/x² of the very x = ⟨1/√p⟩ the fits used,
 * one exact bijection, so a window on its line in one view is on its curve in
 * the other (its ⟨p⟩, larger by Jensen's inequality, is in its tooltip). The
 * axis is linear from 0 to `axis.energy.x.max`; the windows below 4 GeV, off
 * the 1/√E axis, are on it as points no fit uses. σ/E runs from zero to the
 * server's E-view top, which windows below 2 GeV never set.
 *
 * Two fits are drawn, evaluated from their blocks' params alone
 * (`fitCurveE`, held to the server's `curve` rows and `rfit.band` by the
 * tests): the origin-pinned a₀/√E ⊕ 0 always, and the quadrature a/√E ⊕ b
 * only where both of its terms are defined (`quadratureDrawable`; otherwise
 * the model and the table say why). Its band is √ of the z = A/E + B band,
 * exact because z is linear in (A, B) and √ is monotone, its lower edge cut at
 * 0 where ẑ − h < 0. The affine fit, whose negative b would run below zero
 * when extrapolated, stays on the 1/√E view. The width is the form (1.6 px
 * quadrature, 1 px pinned) and the dash is extrapolation: a curve is solid
 * over its mode's `span_gev`, the edges of the windows it was fitted to,
 * dashed [6, 4] beyond, from 4 GeV to the axis end, with its band at a third
 * of its strength there, and never drawn below 4 GeV. So shower B, hollow as
 * ever, gives up its long dash here and draws its lines at 70% strength
 * (never below 3:1). A curve or band leaving the top gets one caret at its
 * first exit scanning up in E, its true values in the caret's tooltip.
 *
 * Under a literature reference both catalogue curves (catalog/resolution_refs.js,
 * "no interval reported") are drawn dotted in the muted ink with direct
 * labels at the right end: a reference, not a series, so never in a series
 * hue, and never setting a range. A note band between the legend and the
 * plot, part of the canvas and the export, lists the windows above the top
 * and states the extrapolation rule.
 *
 * The ratio panel underneath shares the E axis and a linked crosshair (no
 * zoom, no axis tooltip). It divides every window and drawn fit by the
 * reference in force: each shower's deposit a/√E ⊕ b fit, or its a₀/√E where
 * that is undefined, evaluated only where curves are drawn; or a literature
 * curve over the whole axis. A ratio's interval is conditional on the
 * reference; the deposit reference's own band is a neutral wash about 1. The
 * axis is logarithmic and symmetric about 1 over [1/k, k], so ×2 and ÷2 lie at
 * equal distances and a linear axis's impossible negative ratios never arise;
 * k is the first `RATIO_STEPS` value covering the robust ratio marks
 * (`ratioRange`), provisional without them, and marks beyond it get carets.
 * The panel's plot is `ENERGY_VIEW_PX` tall in this view (`syncHeight`), and
 * its export keeps the two panels' proportions (`energyExportMetrics`).
 * `energyModel` decides all of it once, for the chart and the drawer.
 */

import { THEME, axisPadding, formatNumber, formatInt, typographic } from '../scale.js';
import { measureText, wrapText } from '../textfit.js';
import {
  REFERENCE_KEYS, RESOLUTION_REFERENCES, referenceOf, referenceValue, referenceEquation, referenceLabel,
} from '../catalog/resolution_refs.js';
import { customWhiskers, customPolyline, customBand } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries, clampInterval,
  withColour, wrappedLegend, legendTop, legibleOpacity, emptyChartOption, sigFigs,
} from './chart_panel.js';
import { SOURCE_ORDER, sourceColours } from './perf_bins.js';

/** The window modes the card offers: the fits' anchors, or every eligible window. */
export const RES_WINDOW_MODES = Object.freeze(['anchors', 'all']);

/** The gates the payload states, as the server's constants (`gates`) default them. */
const DEFAULT_GATES = Object.freeze({
  report_n: 2, whisker_n: 8, fit_n: 20, e_min_gev: 4, anchor_low_gev: 5, n_anchors: 3,
});

/** The fits drawn as lines; the quadrature form is tabled only. */
export const DRAWN_FORMS = Object.freeze(['affine', 'pinned']);

/** Marker radii (px): an anchor window of the series, and any other. */
const ANCHOR_PX = 4.4;
const MARKER_PX = 3.2;
/** The dot inside shower A's sub-floor ring (px). */
const CORE_PX = 1.2;
const CAP_PX = 3;
const CASING_PX = 3;
/** Horizontal pitch between series measured at one x (px). */
const SERIES_OFFSET_PX = 3.5;
/** Opacities asked of a weak window (N < 20) and a sub-floor one (N < 8); raised to 3:1 where needed. */
const WEAK_OPACITY = 0.6;
const SUB_FLOOR_OPACITY = 0.45;
/** Opacity asked of a provisional fit's line. */
const PROVISIONAL_OPACITY = 0.55;
/** Shower B's affine dash, the pinned fit's dots, and a sub-floor ring's dash. */
const DASH_B = [6, 4];
const DASH_PINNED = [1.5, 3];
const DASH_RING = [2, 2];

const X_UNIT = 'GeV⁻¹ᐟ²';
const A_UNIT = '%·√GeV';

const pct = (v) => (Number.isFinite(v) ? `${sigFigs(v, 3)}%` : '—');
const sig = (v, d = 3) => sigFigs(v, d);
const plural = (n, word, many = `${word}s`) => `${formatInt(n)} ${n === 1 ? word : many}`;

/** The mode in force: 'anchors' unless 'all' is asked for. */
export function windowMode(windows) {
  return windows === 'all' ? 'all' : 'anchors';
}

/** The mode as a reader names it. */
export function modeLabel(mode, gates = DEFAULT_GATES) {
  return mode === 'all'
    ? `every window from ${formatNumber(gates.e_min_gev)} GeV with N ≥ ${formatInt(gates.fit_n)}`
    : `the ${formatInt(gates.n_anchors)} anchor windows`;
}

/** The series one shower choice admits; one-shower data admit theirs whatever is asked. */
export function shownSeries(payload, shower = 'both') {
  const all = payload?.series ?? [];
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  if (!shower || shower === 'both' || nShowers < 2) return all;
  return all.filter((s) => s.shower === shower);
}

/** Each series' colour: the detector in ink, a model in its E2 hue, measured against the card in force. */
export function seriesColours(series) {
  const slots = [...new Set(series.map((s) => s.colour_slot).filter((k) => k && k !== 'detector'))];
  // A known source keeps its E2 place (SOURCE_ORDER); sourceColours measures each hue against the card.
  const hues = sourceColours(slots.sort((a, b) => SOURCE_ORDER.indexOf(a) - SOURCE_ORDER.indexOf(b)));
  const out = {};
  for (const s of series) out[s.key] = s.colour_slot === 'detector' || !s.colour_slot ? THEME.text : (hues[s.colour_slot] ?? THEME.text);
  return out;
}

/** The label of window `bin` in a series, or of a nominal anchor from the payload. */
function binLabel(payload, series, bin) {
  const w = (series?.windows ?? []).find((x) => x.bin === bin);
  if (w?.label) return w.label;
  const nominal = payload?.anchors?.nominal_bins ?? [];
  const i = nominal.indexOf(bin);
  if (i >= 0 && payload.anchors.labels?.[i]) return payload.anchors.labels[i];
  return `bin ${bin}`;
}

/**
 * The polyline `points` ([x, y] pairs) cut to the horizontal strip lo ≤ y ≤ hi:
 * the runs inside it, each with at least two points. A run leaves the strip
 * where the line crosses an edge, so a line with a negative intercept stops at
 * the axis instead of running under it.
 */
export function clipPolyline(points, lo, hi) {
  const pts = (points ?? []).filter((p) => Number.isFinite(p?.[0]) && Number.isFinite(p?.[1]));
  const runs = [];
  let run = [];
  const flush = () => {
    if (run.length > 1) runs.push(run);
    run = [];
  };
  const add = (p) => {
    const last = run[run.length - 1];
    if (!last || last[0] !== p[0] || last[1] !== p[1]) run.push(p);
  };
  for (let i = 0; i + 1 < pts.length; i += 1) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const dy = y1 - y0;
    let t0 = 0;
    let t1 = 1;
    if (dy === 0) {
      if (y0 < lo || y0 > hi) { t0 = 1; t1 = 0; }
    } else {
      const ta = (lo - y0) / dy;
      const tb = (hi - y0) / dy;
      t0 = Math.max(0, Math.min(ta, tb));
      t1 = Math.min(1, Math.max(ta, tb));
    }
    if (t0 > t1) { flush(); continue; }
    if (t0 > 0) flush();
    add([x0 + t0 * (x1 - x0), y0 + t0 * dy]);
    add([x0 + t1 * (x1 - x0), y0 + t1 * dy]);
    if (t1 < 1) flush();
  }
  flush();
  return runs;
}

/**
 * Where a fit leaves the top of the plot, or null where it stays inside:
 * `{at, lineAt, bandAt, peak}`. `lineAt` and `bandAt` are the x where the
 * line and the band's upper edge first rise above `hi`, scanning from x = 0
 * (null where one stays inside); `at` is where the caret goes, the line's exit
 * where the line leaves, else the band's; `peak` is the curve point
 * `[x, y, lo, hi]` whose band reaches highest, its true values.
 */
function cutAbove(curve, hi) {
  if (!Number.isFinite(hi) || !curve.length) return null;
  const exit = (index) => {
    for (let i = 0; i < curve.length; i += 1) {
      const v = curve[i][index];
      if (!(v > hi)) continue;
      if (i === 0) return curve[0][0];
      const before = curve[i - 1][index];
      const t = (hi - before) / (v - before);
      return curve[i - 1][0] + t * (curve[i][0] - curve[i - 1][0]);
    }
    return null;
  };
  const lineAt = exit(1);
  const bandAt = exit(3);
  if (lineAt === null && bandAt === null) return null;
  const peak = curve.reduce((a, c) => (c[3] > a[3] ? c : a), curve[0]);
  return { at: lineAt ?? bandAt, lineAt, bandAt, peak };
}

/** What one window is in the mode in force: the role line(s) its tooltip states. */
function roleOf(payload, s, mf, mode, w, gates) {
  const fitted = (mf?.points ?? []).includes(w.bin);
  const roles = [];
  if (fitted) {
    if (mode === 'anchors') {
      const sub = (mf.substitutions ?? []).find((x) => x.used === w.bin);
      roles.push(sub
        ? `anchor of this mode, standing in for the nominal anchor ${binLabel(payload, s, sub.nominal)}, which holds too few events for this series`
        : 'anchor of this mode (a nominal anchor)');
    } else {
      roles.push('fitted in this mode');
    }
    if (mf.provisional) {
      roles.push(`part of a provisional fit: fewer than two windows reach N = ${formatInt(gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(gates.whisker_n)}`);
    }
  } else if (w.n < gates.whisker_n) {
    roles.push(`below the whisker floor N = ${formatInt(gates.whisker_n)}: drawn as a faded ring, not fitted`);
  } else if (w.n < gates.fit_n) {
    roles.push(`not fitted because N < ${formatInt(gates.fit_n)}, the fit and range floor: drawn faded`);
  } else {
    roles.push('not fitted in this mode');
  }
  const anchors = s.fits?.anchors?.points ?? [];
  if (mode === 'all' && anchors.includes(w.bin)) roles.push('an anchor of the 3-anchor mode (the larger marker)');
  return roles;
}

/**
 * Everything the chart, its tooltips, the table and the drawer need, decided
 * once. Pure. `opts` = {windows, shower}. Null without a resolution payload.
 *
 * {mode, gates, y: {lo, hi, interval, provisional, name, n_clipped}, nShowers,
 * series: [{key, label, raw, colour, isB, offsetPx, mf, provisional, points,
 * fits: {affine, pinned}, unreported}], clipped: {markers, whiskers, fits},
 * nPoints, nLines}. A point is {w, x, value, lo, hi, n, whisker, weak,
 * subFloor, anchor, fitted, opacity, clip, over, roles}; a fit is {form, fit,
 * runs, band, provisional, cut, floorCut, converged}, `cut` (`cutAbove`) where
 * its line or band leaves the top of the plot; `unreported` the on-axis
 * windows with no σ/E.
 */
export function resolutionModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series) || !payload.axis) return null;
  const mode = windowMode(opts.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
  const ya = payload.axis.y ?? {};
  const y = {
    lo: 0, hi: ya.hi, interval: ya.interval, provisional: Boolean(ya.provisional),
    name: ya.name ?? 'σ/E [%]', n_clipped: ya.n_clipped ?? 0,
  };
  const all = payload.series;
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  const shown = shownSeries(payload, opts.shower);
  const colours = seriesColours(shown);
  const clipped = { markers: 0, whiskers: 0, fits: 0 };
  const hi = Number.isFinite(y.hi) ? y.hi : Infinity;

  const series = shown.map((s, k) => {
    const colour = colours[s.key];
    const isB = s.shower === 'b' && nShowers > 1;
    const mf = s.fits?.[mode] ?? null;
    const fittedBins = new Set(mf?.points ?? []);
    const anchorBins = new Set(s.fits?.anchors?.points ?? []);
    const onAxis = (s.windows ?? []).filter((w) => Number.isFinite(w.value) && !w.off_axis
      && Number.isFinite(w.x) && (w.p_lo ?? 0) >= gates.e_min_gev && (w.n ?? 0) >= gates.report_n);
    const drawn = mode === 'anchors' ? onAxis.filter((w) => fittedBins.has(w.bin)) : onAxis;
    const points = drawn.map((w) => {
      const ci = Array.isArray(w.ci95) && Number.isFinite(w.ci95[0]) && Number.isFinite(w.ci95[1]) ? w.ci95 : null;
      const whisker = Boolean(w.whisker) && ci !== null;
      const weak = (w.n ?? 0) < gates.fit_n;
      const subFloor = !whisker;
      const opacity = subFloor ? legibleOpacity(colour, SUB_FLOOR_OPACITY) : (weak ? legibleOpacity(colour, WEAK_OPACITY) : 1);
      const clip = whisker ? clampInterval(ci[0], ci[1], y.lo, hi) : null;
      const over = w.value > hi || w.value < y.lo;
      if (over) clipped.markers += 1;
      if (clip && (clip.cutLo || clip.cutHi)) clipped.whiskers += 1;
      return {
        w, x: w.x, value: w.value, lo: ci?.[0] ?? null, hi: ci?.[1] ?? null, n: w.n, whisker, weak, subFloor,
        anchor: anchorBins.has(w.bin), fitted: fittedBins.has(w.bin), opacity, clip, over,
        roles: roleOf(payload, s, mf, mode, w, gates),
      };
    });
    // Windows on the axis that report no σ/E (one event, or R̄ ≤ 0): never drawn, and named in the drawer.
    const unreported = (s.windows ?? []).filter((w) => !w.off_axis && (w.p_lo ?? 0) >= gates.e_min_gev
      && !((w.n ?? 0) >= gates.report_n && Number.isFinite(w.value)));
    const fits = {};
    for (const form of DRAWN_FORMS) {
      const fit = mf?.[form] ?? null;
      if (!fit || !Array.isArray(fit.curve) || !fit.curve.length) { fits[form] = null; continue; }
      const curve = fit.curve.filter((c) => Array.isArray(c) && c.every(Number.isFinite));
      const clampY = (v) => Math.min(Math.max(v, y.lo), hi);
      const cut = cutAbove(curve, hi);
      if (cut) clipped.fits += 1;
      fits[form] = {
        form, fit,
        runs: clipPolyline(curve.map(([cx, cy]) => [cx, cy]), y.lo, hi),
        band: curve.map(([cx, , lo, up]) => [cx, clampY(lo), clampY(up)]),
        provisional: Boolean(fit.provisional ?? mf.provisional),
        cut,
        floorCut: curve.some((c) => c[2] < y.lo),
        converged: fit.converged !== false,
      };
    }
    return {
      key: s.key, label: s.label ?? s.key, raw: s, colour, isB,
      offsetPx: (k - (shown.length - 1) / 2) * SERIES_OFFSET_PX,
      mf, provisional: Boolean(mf?.provisional), points, fits, unreported,
    };
  });
  return {
    mode, gates, y, nShowers, series, clipped,
    nPoints: series.reduce((a, s) => a + s.points.length, 0),
    nLines: series.reduce((a, s) => a + DRAWN_FORMS.filter((f) => s.fits[f]).length, 0),
  };
}

/* ------------------------------------------------------------ tooltips -- */

/** The tooltip of one window of one series. */
export function pointTip(model, s, p) {
  return pointTipLines(model, s, p).join('<br/>');
}

/** The lines of `pointTip`, which the E view extends; its last line is the clipping note where one applies. */
function pointTipLines(model, s, p) {
  const { gates } = model;
  const w = p.w;
  const lines = [`<b>${escapeHtml(s.label)}</b>`];
  lines.push(`${escapeHtml(w.label ?? `bin ${w.bin}`)} · N = ${plural(w.n, 'event')}`);
  lines.push(`⟨p⟩ = ${formatNumber(w.p_mean, 2)} GeV · x = ⟨1/√p⟩ = ${formatNumber(w.x, 4)} ${X_UNIT}`);
  let value = `σ/E = ${pct(w.value)}`;
  if (Number.isFinite(p.lo) && Number.isFinite(p.hi)) value += `, 95% χ² interval [${pct(p.lo)}, ${pct(p.hi)}]`;
  lines.push(value);
  if (Number.isFinite(w.se_delta)) {
    lines.push(mutedLine(`delta-method SE ${pct(w.se_delta)} (R̄'s error included): the fit weight 1/se², recomputed at the fitted value`));
  }
  if (Number.isFinite(w.c4)) lines.push(mutedLine(`bias factor c₄(N) = ${formatNumber(w.c4, 4)}: below N = 15 the sample SD runs low by this factor`));
  if (Number.isFinite(w.bias)) lines.push(mutedLine(`bias R̄ − 1 = ${pct(w.bias)}: the estimator's own bias, divided out of σ/E`));
  if (Number.isFinite(w.momentum_spread)) {
    lines.push(mutedLine(`momentum spread σ_p/⟨p⟩ = ${pct(w.momentum_spread)} in the window, divided out event by event by R = E_est / p`));
  }
  if (w.dof_note) lines.push(mutedLine(String(w.dof_note)));
  for (const role of p.roles) lines.push(`Role: ${escapeHtml(role)}`);
  lines.push(p.whisker
    ? mutedLine('Whisker: the 95% χ² interval of this window\'s σ/E (N − 1 degrees of freedom), the uncertainty of the aggregate, not the spread of its events.')
    : mutedLine(`No whisker: N = ${formatInt(w.n)} is below the N = ${formatInt(gates.whisker_n)} floor for a drawn interval; σ/E is reported from N = ${formatInt(gates.report_n)}.`));
  if (p.over || p.clip?.cutLo || p.clip?.cutHi) {
    lines.push(mutedLine(`clipped at the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}); the values above are the true ones`));
  }
  return lines;
}

/** A fit's equation as written on the card. */
function equationOf(form) {
  if (form === 'affine') return 'Affine fit σ/E = a/√E + b';
  if (form === 'pinned') return 'Origin-pinned fit σ/E = a₀/√E';
  return 'Quadrature fit σ/E = √(a²/E + b²)';
}

/** The χ² sentence of a fit: χ²/ν with p, or ν = 0 said. */
export function chi2Text(fit) {
  if (!fit) return '—';
  if (!(fit.ndf > 0) || !Number.isFinite(fit.p_value)) return 'ν = 0: no χ² test';
  return `χ²/ν = ${sig(fit.chi2)}/${formatInt(fit.ndf)}, p = ${sig(fit.p_value)}`;
}

/** The windows a fit ran through, by label, with the substitutions of the anchors mode. */
function windowsText(payload, s, mf) {
  if (!mf) return '—';
  const subs = mf.substitutions ?? [];
  const parts = (mf.points ?? []).map((bin) => {
    const sub = subs.find((x) => x.used === bin);
    const label = binLabel(payload, s, bin);
    return sub ? `${label} (for ${binLabel(payload, s, sub.nominal)})` : label;
  });
  for (const sub of subs.filter((x) => x.used === null || x.used === undefined)) {
    parts.push(`${binLabel(payload, s, sub.nominal)} dropped`);
  }
  return parts.length ? parts.join(', ') : 'none';
}

/** The tooltip of one fitted line. */
export function lineTip(model, s, f, payload = null) {
  const { fit, form } = f;
  const p = fit.params ?? {};
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const lines = [`<b>${escapeHtml(s.label)}</b>`, escapeHtml(equationOf(form))];
  if (form === 'affine') {
    lines.push(`a = ${sig(p.a)} ± ${sig(p.se_a)} ${A_UNIT}; b = ${sig(p.b)} ± ${sig(p.se_b)}%`
      + (Number.isFinite(p.rho_ab) ? `; ρ(a, b) = ${sig(p.rho_ab)}` : ''));
    if (scaled) lines.push(mutedLine(`errors scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a) = ${sig(p.se_a_stat)}, SE(b) = ${sig(p.se_b_stat)}`));
  } else {
    lines.push(`a₀ = ${sig(p.a0)} ± ${sig(p.se_a0)} ${A_UNIT}`);
    if (scaled) lines.push(mutedLine(`error scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a₀) = ${sig(p.se_a0_stat)}`));
  }
  lines.push(fit.ndf > 0 && Number.isFinite(fit.p_value)
    ? chi2Text(fit)
    : `${chi2Text(fit)}: the line passes through its ${formatInt(fit.n_points)} point${fit.n_points === 1 ? '' : 's'} exactly`);
  lines.push(`Windows fitted (${formatInt(fit.n_points)}): ${escapeHtml(windowsText(payload, s.raw, s.mf))}`);
  if (f.provisional) {
    lines.push(mutedLine(`Provisional: fewer than two windows reach N = ${formatInt(model.gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(model.gates.whisker_n)}; drawn faded.`));
  }
  if (form === 'affine' && (fit.negative_intercept || p.b < 0)) {
    lines.push(mutedLine('b < 0: the points fall faster than a/√E; the line runs down to the axis and stops there.'));
  }
  if (form === 'affine' && Number.isFinite(p.a) && p.a < 0) {
    lines.push(mutedLine('a < 0: σ/E rises with E here, which no stochastic term describes.'));
  }
  if (!f.converged) {
    lines.push(mutedLine(`Not converged: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so this is the last refit's line, not a fixed point.`));
  }
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true values.'));
  lines.push(mutedLine('The shaded band beside it is the line\'s 95% confidence band.'));
  return lines.join('<br/>');
}

/** The band's half-width as the card writes it: ±1.96 √(gᵀΣg), or ±t₀.₉₇₅,ν √(gᵀΣg) once S scales Σ. */
function bandRule(fit) {
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const q = Number.isFinite(fit.band_quantile) ? fit.band_quantile : 1.96;
  return scaled
    ? `±t₀.₉₇₅,${formatInt(fit.ndf)} √(gᵀΣg) = ±${sig(q, 4)} √(gᵀΣg) from the parameter covariance scaled by S = ${sig(fit.scale_factor)}: S is estimated from the fit's own ν = ${formatInt(fit.ndf)}, so Student's t replaces 1.96`
    : '±1.96 √(gᵀΣg) from the parameter covariance';
}

/** The tooltip of one fit's band. */
export function bandTip(s, f) {
  const name = f.form === 'affine' ? 'affine fit a/√E + b' : 'origin-pinned fit a₀/√E';
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    `95% confidence band of the ${name}: ${bandRule(f.fit)}`,
    mutedLine('The uncertainty of the fitted line, not the spread of the events.'),
  ];
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true values.'));
  if (f.floorCut) lines.push(mutedLine('Its lower edge is cut at σ/E = 0, the floor of the axis.'));
  return lines.join('<br/>');
}

/** "x = 0.354 GeV⁻¹ᐟ² (E = 8 GeV)": a place on the bottom axis with its energy. */
function placeText(x) {
  return `x = ${formatNumber(x, 3)} ${X_UNIT} (${x > 0 ? `E = ${sig(1 / (x * x))} GeV` : 'E → ∞'})`;
}

/** The tooltip of the caret where a fit's line or band leaves the top of the plot: its true values. */
export function fitCutTip(model, s, f) {
  const { cut } = f;
  const name = f.form === 'affine' ? 'affine fit a/√E + b' : 'origin-pinned fit a₀/√E';
  const [px, py, plo, pup] = cut.peak;
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    `The ${f.provisional ? 'provisional ' : ''}${name} leaves the top of the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}):`
      + `${cut.lineAt !== null ? ` its line from ${placeText(cut.lineAt)},` : ''} its 95% band from ${placeText(cut.bandAt ?? cut.lineAt)}.`,
    `True values where the band reaches highest, at ${placeText(px)}: the line ${pct(py)}, the band [${pct(plo)}, ${pct(pup)}].`,
    mutedLine(f.provisional
      ? 'Clipped, not rescaled: a provisional fit runs through windows of N < 20 and never sets the range.'
      : 'Clipped, not rescaled: the range follows the windows of N ≥ 20 and the fitted lines through them, not the bands.'),
  ];
  return lines.join('<br/>');
}

/* --------------------------------------------------------------- marks -- */

/** The markers of one series: filled (A) or hollow (B); a dashed ring below the whisker floor. */
function markerSeries(model, s) {
  const { y } = model;
  const pts = s.points.filter((p) => !p.over);
  return {
    type: 'custom',
    id: `${s.key}|markers`,
    name: s.label,
    clip: true,
    z: 8,
    data: pts.map((p, index) => [p.x, p.value, index]),
    renderItem: (params, api) => {
      const p = pts[params.dataIndex];
      const c = api.coord([p.x, Math.min(p.value, y.hi)]);
      const cx = c[0] + s.offsetPx;
      const r = p.anchor ? ANCHOR_PX : MARKER_PX;
      if (p.subFloor) {
        const ring = {
          type: 'circle', shape: { cx, cy: c[1], r },
          style: { fill: THEME.card, stroke: s.colour, lineWidth: 1.2 * THEME.lineAxis, lineDash: DASH_RING, opacity: p.opacity },
        };
        if (s.isB) return ring;
        // Shower A keeps a dot at the centre, so its sub-floor ring is not taken for shower B's.
        return { type: 'group', children: [ring, { type: 'circle', shape: { cx, cy: c[1], r: CORE_PX }, style: { fill: s.colour, opacity: p.opacity } }] };
      }
      return {
        type: 'circle',
        shape: { cx, cy: c[1], r },
        style: s.isB
          ? { fill: THEME.card, stroke: s.colour, lineWidth: 1.4 * THEME.lineAxis, opacity: p.opacity }
          : { fill: s.colour, stroke: THEME.card, lineWidth: 0.6 * THEME.lineAxis, opacity: p.opacity },
      };
    },
    tooltip: { formatter: (prm) => pointTip(model, s, pts[prm.dataIndex]) },
  };
}

/** The legend swatch and item colour of a series: shower B's is hollow, as its markers are. */
function itemStyleOf(s) {
  return s.isB ? { color: THEME.card, borderColor: s.colour, borderWidth: 1.4 * THEME.lineAxis } : { color: s.colour };
}

/** Every mark of one series, each named after it, so its legend entry shows and hides all of them. */
function seriesMarks(model, s, payload) {
  const { y } = model;
  const out = [];
  const style = itemStyleOf(s);
  const named = (x) => ({ ...withColour(x, s.colour), name: s.label, itemStyle: { ...style } });

  // Markers first: the legend takes its swatch from the first series of a name.
  out.push(named(markerSeries(model, s)));

  const whiskers = s.points
    .filter((p) => p.whisker && p.clip && p.clip.lo !== null && p.clip.hi !== null && p.clip.hi > p.clip.lo)
    .map((p) => [p.x, p.clip.lo, p.clip.hi, { caps: p.clip.caps, opacity: p.opacity === 1 ? 1 : legibleOpacity(s.colour, WEAK_OPACITY), point: p }]);
  if (whiskers.length) {
    out.push(named({
      ...customWhiskers({
        name: s.label, points: whiskers, capPx: CAP_PX, color: s.colour, width: 1.2 * THEME.lineAxis,
        offsetPx: s.offsetPx, z: 7, casing: { color: THEME.canvas, width: CASING_PX },
        tooltip: (d) => pointTip(model, s, d.point),
      }),
      id: `${s.key}|whiskers`,
    }));
  }

  const carets = [];
  for (const p of s.points) {
    const tip = pointTip(model, s, p);
    if (p.value > y.hi || p.clip?.cutHi) carets.push({ at: [p.x, y.hi], dir: 'up', tooltip: tip });
    if (p.value < y.lo || p.clip?.cutLo) carets.push({ at: [p.x, y.lo], dir: 'down', tooltip: tip });
  }
  // A line or band that leaves the top of the plot: one caret where it leaves, with its true values.
  for (const form of DRAWN_FORMS) {
    const f = s.fits[form];
    if (f?.cut) carets.push({ at: [f.cut.at, y.hi], dir: 'up', tooltip: fitCutTip(model, s, f) });
  }
  if (carets.length) {
    out.push(named({ ...caretSeries({ name: s.label, carets, color: s.colour, offsetPx: s.offsetPx }), id: `${s.key}|carets` }));
  }

  for (const form of DRAWN_FORMS) {
    const f = s.fits[form];
    if (!f) continue;
    const affine = form === 'affine';
    const opacity = f.provisional ? legibleOpacity(s.colour, PROVISIONAL_OPACITY) : 1;
    f.runs.forEach((run, i) => {
      out.push(named({
        ...customPolyline({
          name: s.label, points: run, color: s.colour, opacity, z: 5,
          width: (affine ? 1.6 : 1) * THEME.lineAxis,
          dash: affine ? (s.isB ? DASH_B : null) : DASH_PINNED,
          tooltip: () => lineTip(model, s, f, payload),
        }),
        id: `${s.key}|${form}|line|${i}`,
      }));
    });
    out.push(named({
      ...customBand({
        name: s.label, points: f.band, color: s.colour, z: 2,
        opacity: (affine ? 1 : 0.5) * THEME.bandAlpha * (f.provisional ? 0.6 : 1),
      }),
      id: `${s.key}|${form}|band`,
      silent: false,
      tooltip: { formatter: () => bandTip(s, f) },
    }));
  }
  return out;
}

/** The top axis: the bottom one relabelled, E = 1/x², ticks at the payload's energies and ∞ at 0. */
function energyAxis(top, xMin, xMax) {
  const ticks = (top?.ticks ?? []).filter((t) => Number.isFinite(t.x) && t.x >= xMin && t.x <= xMax);
  const xs = ticks.map((t) => t.x);
  const labelOf = (v) => {
    const t = ticks.find((k) => Math.abs(k.x - v) < 1e-6);
    return t ? typographic(String(t.label)) : '';
  };
  const base = valueAxis({ name: top?.name ?? 'Energy (GeV) ⟶', min: xMin, max: xMax, nameGap: 1.8 * THEME.fontLabel + 4 });
  return {
    ...base,
    position: 'top',
    inverse: true,
    axisTick: { ...base.axisTick, customValues: xs },
    axisLabel: { ...base.axisLabel, customValues: xs, formatter: labelOf },
    splitLine: { show: false },
  };
}

/** The headroom the top axis's labels and name take above the plot (px). */
function topAxisPx() {
  return 3.6 * THEME.fontLabel;
}

/**
 * The card's option. Pure: `opts` = {view?: 'linear' | 'energy', windows:
 * 'anchors' | 'all', shower: 'a' | 'b' | 'both', reference?, palette, card,
 * tooltipPosition?}; `metrics` = {width, height}. `view: 'energy'` is the E
 * view (`energyViewOption`); any other view is the 1/√E view, unchanged.
 */
export function resolutionScalingOption(payload, opts = {}, metrics = {}) {
  if (opts?.view === 'energy') return energyViewOption(payload, opts, metrics).option;
  const model = resolutionModel(payload, opts);
  if (!model) return emptyChartOption(opts, metrics, 'This response carries no energy-resolution series.');
  if (!model.series.length) {
    return emptyChartOption(opts, metrics, 'No series of the chosen shower in this response.');
  }
  if (!model.nPoints || !(model.y.hi > 0)) {
    const { gates } = model;
    const offAxis = model.series.reduce((a, s) => a + (s.raw.windows ?? []).filter((w) => w.off_axis && Number.isFinite(w.value)).length, 0);
    const listed = offAxis ? ` ${plural(offAxis, 'window')} below ${formatNumber(gates.e_min_gev)} GeV ${offAxis === 1 ? 'is' : 'are'} listed in the Details drawer.` : '';
    // Windows that report σ/E (N ≥ 2) but cannot anchor a fit (N < 8): the anchors mode draws none of them.
    const reportable = model.series.reduce((a, s) => a + (s.raw.windows ?? []).filter((w) => !w.off_axis
      && (w.p_lo ?? 0) >= gates.e_min_gev && (w.n ?? 0) >= gates.report_n && Number.isFinite(w.value)).length, 0);
    if (model.mode === 'anchors' && reportable && model.y.hi > 0) {
      return emptyChartOption(opts, metrics, `No window from ${formatNumber(gates.anchor_low_gev)} GeV reaches N = ${formatInt(gates.whisker_n)}, `
        + `the fewest an anchor fit runs through, so the 3-anchor mode draws nothing. "All ≥ ${formatNumber(gates.e_min_gev)} GeV" draws the `
        + `${plural(reportable, 'window')} from ${formatNumber(gates.e_min_gev)} GeV that report σ/E (N ≥ ${formatInt(gates.report_n)}).${listed}`);
    }
    const mode = model.mode === 'anchors' ? ' No series has a window its anchors fit can run through.' : '';
    return emptyChartOption(opts, metrics, `No momentum window from ${formatNumber(gates.e_min_gev)} GeV holds two events in this selection, so no σ/E can be drawn on this axis.${mode}${listed}`);
  }
  const pad = axisPadding();
  const width = metrics.width || 760;
  const height = metrics.height || 420;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const axis = payload.axis;
  const xMin = axis.x?.min ?? 0;
  const xMax = axis.x?.max ?? 0.5;

  const series = [];
  const legend = [];
  for (const s of model.series) {
    const marks = seriesMarks(model, s, payload);
    if (!s.points.length && !DRAWN_FORMS.some((f) => s.fits[f])) continue;
    series.push(...marks);
    legend.push({ name: s.label, icon: 'circle' });
  }

  const top = legendTop(legend, plotWidthPx, { wrap: true }) + topAxisPx();
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  const yBase = model.y.name;
  const yName = fitName(model.y.provisional
    ? [`${yBase} — provisional, no window reaches N = ${formatInt(model.gates.fit_n)}`, `${yBase} — provisional`]
    : [yBase], plotHeightPx);
  const bottom = valueAxis({
    name: axis.x?.name ?? '⟵ 1/√E [GeV⁻¹ᐟ²]', min: xMin, max: xMax, interval: axis.x?.interval ?? 0.1,
  });
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: wrappedLegend(legend, { left: pad.left, right: pad.right }),
    xAxis: [{ ...bottom, position: 'bottom', inverse: true }, energyAxis(axis.top, xMin, xMax)],
    yAxis: valueAxis({
      name: yName, min: 0, max: model.y.hi, interval: model.y.interval, split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    series,
  };
}

/* ---------------------------------------------------------- fit table -- */

/** The column heads of the fit table: one row per fit, the series and its windows spanning its rows. */
export const FIT_TABLE_COLUMNS = Object.freeze([
  'Series', 'Fit', `a ± SE [${A_UNIT}]`, 'b ± SE [%]', 'χ²/ν (p)', 'S', 'Windows fitted', 'Status',
]);

/** The left-aligned text columns; the rest are right-aligned numbers, each value kept whole by `NBSP`. */
export const FIT_TABLE_TEXT_COLUMNS = Object.freeze([0, 1, 6, 7]);

/** The fits of one series, in the table's order, with the name its Fit cell gives each. */
const TABLE_FORMS = Object.freeze([
  ['affine', 'Affine a/√E + b'],
  ['pinned', 'Origin-pinned a₀/√E'],
  ['quadrature', 'Quadrature √(a²/E + b²), tabled only'],
]);

/** No-break space: a value and its SE, or p and its value, never split across lines as the table wraps. */
const NBSP = '\u00a0';

const pm = (v, se) => (Number.isFinite(v) ? `${sig(v)}${NBSP}±${NBSP}${sig(se)}` : '—');

/** A χ² cell: χ²/ν (p), or ν = 0 said. */
function chi2Cell(fit) {
  if (!fit) return '—';
  return fit.ndf > 0 && Number.isFinite(fit.p_value)
    ? `${sig(fit.chi2)}/${formatInt(fit.ndf)} (p${NBSP}=${NBSP}${sig(fit.p_value)})`
    : 'ν = 0: no χ² test';
}

/** The scale factor cell: S where it scaled the errors, 1 where they stand, — without a test. */
function scaleCell(fit) {
  if (!fit || !(fit.ndf > 0)) return '—';
  return Number.isFinite(fit.scale_factor) && fit.scale_factor > 1 ? sig(fit.scale_factor) : '1';
}

/** The a and b cells of one fit: the pinned b is zero by construction; an undefined quadrature term is its square. */
function termCells(fit) {
  if (!fit) return ['—', '—'];
  const p = fit.params ?? {};
  if (fit.form === 'affine') return [pm(p.a, p.se_a), pm(p.b, p.se_b)];
  if (fit.form === 'pinned') return [pm(p.a0, p.se_a0), '0 (through the origin)'];
  const a = p.a_defined === false || !Number.isFinite(p.a)
    ? `A${NBSP}=${NBSP}${pm(p.a2, p.se_a2)}${NBSP}%²·GeV: a undefined`
    : pm(p.a, p.se_a);
  const b = p.b_defined === false || !Number.isFinite(p.b)
    ? `B${NBSP}=${NBSP}${pm(p.b2, p.se_b2)}${NBSP}%²: b undefined`
    : pm(p.b, p.se_b);
  return [a, b];
}

/** The status of one fit: provisional, not converged, a negative intercept, or robust. */
function statusCell(fit, mf, gates) {
  if (!fit) return 'too few windows';
  const status = [];
  if (mf?.provisional) status.push(`provisional (windows of N ≥ ${formatInt(gates.whisker_n)})`);
  if (fit.converged === false) status.push(`not converged in ${formatInt(fit.iterations)} refits`);
  if (fit.form === 'affine' && fit.negative_intercept) status.push('b < 0');
  return status.length ? status.join('; ') : `robust (N ≥ ${formatInt(gates.fit_n)})`;
}

/**
 * The fit table of the mode in force. Pure: {mode, caption, columns, rows:
 * [{key, label, windows, fits: [{form, cells: [string]}]}]}, one row group per
 * series the shower choice admits and one row per fit; `cells` are the Fit
 * column onwards except the windows, which span the group (`windows`). Every
 * cell is a string with U+2212 for a minus. Null without a payload.
 *
 * `opts.view === 'energy'` names the fits as the E view draws them (the
 * origin-pinned a₀/√E ⊕ 0 drawn; the quadrature a/√E ⊕ b drawn, or not drawn
 * with its reason; the affine fit drawn in the 1/√E view), with a caption
 * saying so, and adds `view: 'energy'`. The rows, their order and every other
 * cell are the 1/√E view's; without it the output is that view's, unchanged.
 */
export function fitTableRows(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series)) return null;
  const mode = windowMode(opts?.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
  const energy = resolutionView(opts?.view) === 'energy';
  const text = (c) => typographic(String(c));
  const rows = shownSeries(payload, opts?.shower).map((s) => {
    const mf = s.fits?.[mode] ?? null;
    return {
      key: s.key,
      label: s.label ?? s.key,
      windows: text(windowsText(payload, s, mf)),
      fits: TABLE_FORMS.map(([form, name]) => {
        const fit = mf?.[form] ?? null;
        const [a, b] = termCells(fit);
        const cellName = energy ? energyTableName(form, fit) : name;
        return { form, cells: [cellName, a, b, chi2Cell(fit), scaleCell(fit), statusCell(fit, mf, gates)].map(text) };
      }),
    };
  });
  if (energy) {
    return {
      mode,
      view: 'energy',
      caption: typographic(`Fits through ${modeLabel(mode, gates)}. This view draws the origin-pinned a₀/√E ⊕ 0 and, where both `
        + 'of its terms are defined, the quadrature a/√E ⊕ b, each solid over the windows it was fitted to and dashed beyond; '
        + 'the affine a/√E + b is drawn in the 1/√E view. '
        + 'S = √(χ²/ν) scales a fit\'s standard errors where χ²/ν > 1 (PDG), and its band then takes Student\'s t of its ν; '
        + 'S = 1 where the windows\' own errors stand.'),
      columns: [...FIT_TABLE_COLUMNS],
      rows,
    };
  }
  return {
    mode,
    caption: typographic(`Fits through ${modeLabel(mode, gates)}; the quadrature form is tabled, not drawn. `
      + 'S = √(χ²/ν) scales a fit\'s standard errors where χ²/ν > 1 (PDG), and its band then takes Student\'s t of its ν; '
      + 'S = 1 where the windows\' own errors stand.'),
    columns: [...FIT_TABLE_COLUMNS],
    rows,
  };
}

/** The Fit cell of one form in the E view: what the view draws of it, and why not where it does not. */
function energyTableName(form, fit) {
  if (form === 'affine') return 'Affine a/√E + b — drawn in the 1/√E view';
  if (form === 'pinned') {
    return pinnedDrawable(fit) ? 'Origin-pinned a₀/√E ⊕ 0 — drawn' : 'Origin-pinned a₀/√E ⊕ 0 — not drawn: too few windows';
  }
  const reason = quadratureReason(fit);
  return reason ? `Quadrature a/√E ⊕ b — not drawn: ${reason}` : 'Quadrature a/√E ⊕ b — drawn';
}

/* ========================================================== the E view == */

/** The card's two views: σ/E against a reversed 1/√E axis, and against E in GeV with a ratio panel. */
export const RES_VIEWS = Object.freeze(['linear', 'energy']);

/** The view in force: 'energy' when asked for, 'linear' otherwise. */
export function resolutionView(view) {
  return view === 'energy' ? 'energy' : 'linear';
}

/** What the ratio panel divides by: each shower's deposit fit (the default), or a literature curve of the catalogue. */
export const RATIO_REFERENCES = Object.freeze(['deposit', ...REFERENCE_KEYS]);

/** The half-ranges k of the log-symmetric ratio axis [1/k, k]: the first that covers the robust marks. */
export const RATIO_STEPS = Object.freeze([1.1, 1.25, 1.5, 2, 3, 4, 5, 8, 10]);

/** The step of the energies a curve is evaluated at (GeV). */
export const E_GRID_STEP_GEV = 0.25;

/** The plot's height in each view (px): the CSS height of the 1/√E view, and the E view's two panels. */
export const LINEAR_VIEW_PX = 420;
export const ENERGY_VIEW_PX = 600;

/** The fits the E view draws, the wider line first; the affine fit stays on the 1/√E view. */
export const ENERGY_FORMS = Object.freeze(['quadrature', 'pinned']);

/** The ratio panel's share of the two grids' height, and the gap between the grids (px). */
const RATIO_SHARE = 0.26;
const GRID_GAP_PX = 10;
/** A band's alpha beyond its fitted windows, as a share of its alpha over them. */
const OUT_ALPHA = 1 / 3;
/** Shower B's line and band strength on this view, where the dash means extrapolation. */
const B_STRENGTH = 0.7;
/** An extrapolated part, and a literature curve. */
const DASH_EXTRAPOLATED = [6, 4];
const DASH_LITERATURE = [1.5, 3];
/** The band quantile of a fit block that carries none. */
const DEFAULT_QUANTILE = 1.96;
/** A ratio band's alpha as a share of its band on the main panel: faint, since it is conditional. */
const RATIO_BAND_SHARE = 0.5;
/** The deposit reference's own band about 1, as a share of `bandAlpha`: a neutral background wash. */
const REFERENCE_BAND_SHARE = 0.7;
/** A literature curve's legend swatch: three dots, as the curve is drawn. */
const LITERATURE_ICON = 'path://M0,4h2.4v2.4h-2.4zM5,4h2.4v2.4h-2.4zM10,4h2.4v2.4h-2.4z';
/** What the literature curves' tooltips and the drawer say of their provenance. */
export const LITERATURE_PROVENANCE = 'as printed in the legend of the supplied figure (ECCE G4 simulation, dual-readout '
  + 'inlay, 2.55 < η < 3.98); no interval reported; it describes that simulation\'s particles, not this detector';

/* --------------------------------------------------------- evaluators -- */

/**
 * One fit block at one energy, in %, from its params alone: {y, lo, hi,
 * cutLo}, or null where the fit has no value there. x = 1/√E and q the
 * block's `band_quantile` (1.96 when absent).
 *
 * - pinned: y = a₀·x, half-width q·SE(a₀)·x;
 * - affine: y = a·x + b, half-width q·√((x·SE(a))² + 2ρ·x·SE(a)·SE(b) + SE(b)²);
 * - quadrature: z = A·u + B with u = 1/E, half-width h = q·√max((u·SE(A))² +
 *   2ρ·u·SE(A)·SE(B) + SE(B)², 0), returned through √ as (√max(z, 0),
 *   √max(z − h, 0), √max(z + h, 0)): the exact 95% band of √(A/E + B), since z
 *   is linear in (A, B) and √ is monotone; `cutLo` where z − h < 0.
 *
 * The SEs are the block's scaled ones and ρ its correlation (S cancels in it),
 * so the covariance is the server's (`stats/resolution_fit.band`).
 */
function evalFitAt(fit, energy) {
  if (!fit || !Number.isFinite(energy) || !(energy > 0)) return null;
  const p = fit.params ?? {};
  const q = Number.isFinite(fit.band_quantile) ? fit.band_quantile : DEFAULT_QUANTILE;
  const num = (v) => (Number.isFinite(v) ? v : 0);
  const x = 1 / Math.sqrt(energy);
  if (fit.form === 'pinned') {
    if (!Number.isFinite(p.a0)) return null;
    const y = p.a0 * x;
    const half = q * num(p.se_a0) * x;
    return { y, lo: y - half, hi: y + half, cutLo: y - half < 0 };
  }
  if (fit.form === 'affine') {
    if (!Number.isFinite(p.a) || !Number.isFinite(p.b)) return null;
    const sa = num(p.se_a);
    const sb = num(p.se_b);
    const y = p.a * x + p.b;
    const half = q * Math.sqrt(Math.max((x * sa) ** 2 + 2 * num(p.rho_ab) * x * sa * sb + sb * sb, 0));
    return { y, lo: y - half, hi: y + half, cutLo: y - half < 0 };
  }
  if (fit.form === 'quadrature') {
    if (!Number.isFinite(p.a2) || !Number.isFinite(p.b2)) return null;
    const sa = num(p.se_a2);
    const sb = num(p.se_b2);
    const u = 1 / energy;
    const z = p.a2 * u + p.b2;
    const half = q * Math.sqrt(Math.max((u * sa) ** 2 + 2 * num(p.rho_a2b2) * u * sa * sb + sb * sb, 0));
    return {
      y: Math.sqrt(Math.max(z, 0)), lo: Math.sqrt(Math.max(z - half, 0)), hi: Math.sqrt(Math.max(z + half, 0)),
      cutLo: z - half < 0,
    };
  }
  return null;
}

/** `[[E, y, lo, hi], …]` in % at `energies` (GeV), from the fit block alone (`evalFitAt`). */
export function fitCurveE(fit, energies) {
  const out = [];
  for (const e of energies ?? []) {
    const v = evalFitAt(fit, e);
    if (v && Number.isFinite(v.y)) out.push([e, v.y, v.lo, v.hi]);
  }
  return out;
}

/** Why the E view does not draw a quadrature fit block, or null where it does. */
function quadratureReason(fit) {
  if (!fit) return 'too few windows';
  const p = fit.params ?? {};
  const reasons = [];
  if (p.a_defined !== true) reasons.push('A ≤ 0: σ/E rises with E');
  if (p.b_defined !== true) reasons.push('B ≤ 0: σ/E falls faster than 1/√E, so there is no real constant term');
  if (reasons.length) return reasons.join('; ');
  if (!Number.isFinite(p.rho_a2b2) || !Number.isFinite(p.a2) || !Number.isFinite(p.b2)) {
    return 'the correlation of A and B is not in the response, so its band cannot be built';
  }
  return null;
}

/** Whether the E view draws a quadrature fit: both terms defined, and its band buildable (a finite ρ(A, B)). */
export function quadratureDrawable(fit) {
  return quadratureReason(fit) === null;
}

/** Whether an origin-pinned fit block has a slope to draw. */
function pinnedDrawable(fit) {
  return Number.isFinite(fit?.params?.a0);
}

/**
 * Uniform `E_GRID_STEP_GEV` steps from `min` to `max`, `max` itself, and the
 * `extra` energies inside [min, max] (the span edges, so the solid and the
 * dashed part of a curve meet at a shared point), sorted and unique.
 */
export function energyGrid(min, max, extra = []) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max < min) return [];
  const steps = Math.floor((max - min) / E_GRID_STEP_GEV + 1e-9);
  const out = [];
  for (let i = 0; i <= steps; i += 1) out.push(Number((min + i * E_GRID_STEP_GEV).toFixed(9)));
  out.push(max);
  for (const e of extra ?? []) if (Number.isFinite(e) && e >= min && e <= max) out.push(e);
  out.sort((a, b) => a - b);
  return out.filter((e, i) => i === 0 || e - out[i - 1] > 1e-9);
}

/**
 * The ratio axis's half-range: `{k, provisional}` with k the first of
 * `RATIO_STEPS` that covers the robust marks (1/k ≤ every value ≤ k, whiskers
 * included), the last step where none does (the rest get carets). A mark is
 * `{value, lo?, hi?, robust?, marker?}`. Without a robust mark the range is
 * provisional and k covers the markers' values alone (`marker: true`); without
 * those, k = 2.
 */
export function ratioRange(marks) {
  const dev = (v) => (Number.isFinite(v) && v > 0 ? Math.max(v, 1 / v) : null);
  const reach = (list, ends) => {
    let m = 1;
    for (const mark of list) {
      for (const v of ends ? [mark.value, mark.lo, mark.hi] : [mark.value]) {
        const d = dev(v);
        if (d !== null) m = Math.max(m, d);
      }
    }
    return m;
  };
  const step = (m) => RATIO_STEPS.find((s) => s >= m * (1 - 1e-9)) ?? RATIO_STEPS[RATIO_STEPS.length - 1];
  const robust = (marks ?? []).filter((m) => m?.robust && dev(m.value) !== null);
  if (robust.length) return { k: step(reach(robust, true)), provisional: false };
  const markers = (marks ?? []).filter((m) => m?.marker && dev(m.value) !== null);
  if (markers.length) return { k: step(reach(markers, false)), provisional: true };
  return { k: 2, provisional: true };
}

/* ------------------------------------------------------------- model -- */

/** A fit's mode span [lo, hi] (GeV): the payload's `span_gev`, else its fitted windows' edges; null without. */
function spanOf(mf, s) {
  const span = mf?.span_gev;
  if (Array.isArray(span) && Number.isFinite(span[0]) && Number.isFinite(span[1])) return [span[0], span[1]];
  const chosen = new Set(mf?.points ?? []);
  const fitted = (s?.windows ?? []).filter((w) => chosen.has(w.bin) && Number.isFinite(w.p_lo) && Number.isFinite(w.p_hi));
  return fitted.length ? [Math.min(...fitted.map((w) => w.p_lo)), Math.max(...fitted.map((w) => w.p_hi))] : null;
}

/** "7–16 GeV". */
function spanText(span) {
  return span ? `${formatNumber(span[0])}–${formatNumber(span[1])} GeV` : 'no window';
}

/** Rows `[E, …]` split at a span: {below, inside, above}, each sharing its edge row with the next. */
function splitAtSpan(rows, span) {
  if (!span) return { below: [], inside: [], above: rows };
  const [lo, hi] = span;
  return {
    below: rows.filter((r) => r[0] <= lo),
    inside: rows.filter((r) => r[0] >= lo && r[0] <= hi),
    above: rows.filter((r) => r[0] >= hi),
  };
}

/** Ratio points `[E, r]` cut to [1/k, k] in log r, the scale the panel draws them on. */
function clipLog(points, k) {
  const lk = Math.log(k);
  const runs = [];
  let chunk = [];
  const flush = () => {
    if (chunk.length > 1) runs.push(...clipPolyline(chunk, -lk, lk));
    chunk = [];
  };
  for (const [e, r] of points) {
    if (Number.isFinite(r) && r > 0) chunk.push([e, Math.log(r)]);
    else flush();
  }
  flush();
  return runs.map((run) => run.map(([e, l]) => [e, Math.min(k, Math.max(1 / k, Math.exp(l)))]));
}

/**
 * Where ratio rows `[E, r, lo, hi]` first leave [1/k, k], scanning up in E, or
 * null: {at, dir, lineAt, bandAt, peak}, `peak` the row that deviates most
 * (its true values).
 */
function ratioCut(rows, k) {
  const lk = Math.log(k);
  const dev = (v) => (Number.isFinite(v) && v > 0 ? Math.abs(Math.log(v)) : Infinity);
  const devRows = rows.map(([e, r, lo, up]) => [e, dev(r), 0, Math.max(dev(r), dev(lo), dev(up))]);
  const cut = cutAbove(devRows, lk);
  if (!cut) return null;
  // The first row beyond the axis, by the mark the caret follows (the line where it leaves, else the band).
  const line = cut.lineAt !== null;
  const row = rows[Math.max(0, devRows.findIndex((d) => (line ? d[1] : d[3]) > lk))];
  const up = line ? row[1] > 1 : row[3] > k;
  return { at: cut.at, dir: up ? 'up' : 'down', lineAt: cut.lineAt, bandAt: cut.bandAt, peak: rows[devRows.indexOf(cut.peak)] ?? row };
}

/** A series' short name on the canvas note: the shower letter (two showers only) and the estimator. */
function shortName(s, nShowers) {
  const source = { detector: 'deposit', network: 'network', xgb: 'XGBoost' }[s.source]
    ?? (s.colour_slot === 'detector' ? 'deposit' : 'network');
  return nShowers > 1 && s.shower ? `${String(s.shower).toUpperCase()} ${source}` : source;
}

/** The ratio's reference for one shower under 'deposit': its detector series' a/√E ⊕ b fit, else its a₀/√E. */
function depositReference(all, shower, mode, nShowers, curveMin, xMax) {
  const owner = nShowers > 1 ? `shower ${String(shower).toUpperCase()}'s deposit` : 'the deposit';
  const det = all.find((s) => s.source === 'detector' && (s.shower ?? 'a') === shower) ?? null;
  const base = {
    key: 'deposit', shower, literature: null, interval: 'band', series: det?.key ?? null, seriesLabel: det?.label ?? null,
    form: null, fit: null, span: null, provisional: false, band: null, bandClipped: false, why: null, valueAt: () => null,
  };
  if (!det) return { ...base, label: `${owner} fit`, reason: 'this shower has no calibrated-deposit series' };
  const mf = det.fits?.[mode] ?? null;
  const quad = mf?.quadrature ?? null;
  const pinned = mf?.pinned ?? null;
  const fit = quadratureDrawable(quad) ? quad : (pinnedDrawable(pinned) ? pinned : null);
  if (!fit) {
    return { ...base, label: `${owner} fit`, reason: `${owner} series has no a/√E ⊕ b or a₀/√E fit in this mode, so this shower has no ratio marks` };
  }
  const form = fit.form;
  const span = spanOf(mf, det);
  const valueAt = (e) => {
    if (!(e >= curveMin - 1e-9 && e <= xMax + 1e-9)) return null;
    const v = evalFitAt(fit, e);
    return v && v.y > 0 ? v.y : null;
  };
  const rel = fitCurveE(fit, energyGrid(curveMin, xMax, span ?? []))
    .filter((r) => r[1] > 0).map(([e, yv, lo, up]) => [e, 1, lo / yv, up / yv]);
  return {
    ...base,
    label: form === 'quadrature' ? `${owner} a/√E ⊕ b fit` : `${owner} a₀/√E fit`,
    why: form === 'quadrature'
      ? `its a/√E ⊕ b fit, both of whose terms are defined`
      : `its a₀/√E fit, since its a/√E ⊕ b fit is not drawn (${quadratureReason(quad)})`,
    form, fit, span, provisional: Boolean(fit.provisional ?? mf?.provisional), valueAt, band: splitAtSpan(rel, span),
    reason: null,
  };
}

/** The ratio's reference for one shower under a literature curve: the same curve for every shower, over the whole axis. */
function literatureReference(entry, shower) {
  return {
    key: entry.key, shower, literature: entry, interval: null, series: null, seriesLabel: null, form: 'literature', fit: null,
    span: null, provisional: false, band: null, bandClipped: false, label: referenceLabel(entry), equation: referenceEquation(entry),
    why: `${referenceEquation(entry)}, ${LITERATURE_PROVENANCE}`, reason: null,
    valueAt: (e) => referenceValue(entry, e),
  };
}

/** The roles of a window below the curves' floor: drawn as a point, never fitted. */
function belowRoles(w, gates, curveMin) {
  const roles = [`below ${formatNumber(curveMin)} GeV: no fit uses it; drawn as a point only`];
  if ((w.n ?? 0) < gates.whisker_n) roles.push(`below the whisker floor N = ${formatInt(gates.whisker_n)}: drawn as a faded ring`);
  else if ((w.n ?? 0) < gates.fit_n) roles.push(`N < ${formatInt(gates.fit_n)}: drawn faded`);
  return roles;
}

/**
 * Everything the E view's chart, its tooltips and the drawer need, decided
 * once. Pure. `opts` = {windows, shower, reference: 'deposit' | 'pi' | 'e'}.
 * Null without a resolution payload that carries `axis.energy`.
 *
 * The returned shape (models_notes.js builds the E view's drawer from it):
 *
 * - `view` 'energy', `mode`, `gates`, `nShowers`, `payload`;
 * - `x` {min, max, interval, name} and `y` {lo, hi, interval, provisional,
 *   name, n_clipped}: `axis.energy`'s, the y range the server's 2 GeV rule;
 *   `curveMinGev` (no curve below it), `yMinGev`, `dataMaxGev`, `rule` and
 *   `notes` (the server's sentences);
 * - `reference` {key: 'deposit' | 'pi' | 'e', label (the ratio axis's
 *   wording), literature: the catalogue entry or null, interval: 'band' for
 *   the deposit, null for literature, flag: 'no interval reported' under a
 *   literature reference (else null), byShower: {a, b}}. Each shower's entry is {key, shower, label, form ('quadrature' |
 *   'pinned' | 'literature' | null), fit, series (the deposit series' key),
 *   seriesLabel, span, provisional, why (which fit and why), reason (null, or
 *   why that shower has no ratio marks), band ({below, inside, above} rows
 *   [E, 1, lo/ŷ, hi/ŷ], deposit only), bandClipped (that band is wider than
 *   the ratio axis and clamped at it), valueAt(E) (the reference in %, null
 *   outside its domain); a literature entry adds `equation`};
 * - `series`: [{key, label, short (the canvas note's name), raw, colour, isB,
 *   offsetPx, lineOpacity (the strength its lines take: shower B 70%), mf,
 *   provisional, span, points, fits: {quadrature, pinned}, unreported,
 *   reference (its shower's entry)}];
 * - a point: {w, E (= 1/x², x = ⟨1/√p⟩), x, value, ci, lo, hi, n, whisker,
 *   weak, subFloor, below4, anchor, fitted, robust, opacity, clip, over,
 *   roles, ratio}; `ratio` {drawn, reason, ref (the reference in % at E),
 *   value, lo, hi (the whisker divided, null without one), robust, clip,
 *   over};
 * - a fit: {form, fit, drawable, reason (why not drawn, else null), span,
 *   domain [curveMinGev, x.max], curve [[E, y, lo, hi]], solid (the runs over
 *   the span, clipped to [0, y.hi]), dashed (the runs beyond it), band
 *   {below, inside, above} (rows [E, lo, hi], clamped), cut (where its curve
 *   or band leaves the top, scanning up in E: {at, lineAt, bandAt, peak}),
 *   floorCut, provisional, converged, isReference (the deposit reference
 *   itself: its ratio ≡ 1 is not drawn), ratio {rows, solid, dashed, band,
 *   cut} (null for the reference or without one)};
 * - `literature`: [] under the deposit reference, else both catalogue curves
 *   [{key, entry, label ("π± lit."), legend, inForce, curve [[E, %]], runs,
 *   cut {at, peak} | null}];
 * - `ratio` {k, provisional, reference (key), clipped {markers, whiskers,
 *   fits (each with a caret), bands (deposit reference bands clamped at the
 *   axis, a wash with no caret)}, belowNotDrawn (windows below the curve
 *   floor left off the ratio panel under the deposit reference), noReference
 *   ([{shower, reason}])};
 * - `clipped` {markers, whiskers, fits, literature, ratio}: the marks
 *   clipped at the main axis, each with a caret (`literature`: the curves
 *   crossing its top), and the ratio panel's carets in total (markers +
 *   whiskers + fits);
 * - `offScale`: [{label, E, entries: [{key, short, value, n}]}], the drawn
 *   windows above y.hi grouped by window, in E order;
 * - `spans` {shared, span, bySeries: [{key, label, form, span}]}: the drawn
 *   fits' fitted spans, `shared` when they are one;
 * - `noteText` {offScale, extrapolation}: the canvas note's two strings
 *   before they are fitted to its width ('' where there is nothing to say);
 * - `nPoints`, `nLines`.
 */
export function energyModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series) || !payload.axis?.energy) return null;
  const ea = payload.axis.energy;
  const mode = windowMode(opts.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
  const xa = ea.x ?? {};
  const x = {
    min: Number.isFinite(xa.min) ? xa.min : 0, max: Number.isFinite(xa.max) ? xa.max : 80,
    interval: Number.isFinite(xa.interval) ? xa.interval : 10, name: xa.name ?? 'Energy E [GeV]',
  };
  const ya = ea.y ?? {};
  const y = {
    lo: 0, hi: ya.hi, interval: ya.interval, provisional: Boolean(ya.provisional),
    name: ya.name ?? 'σ/E [%]', n_clipped: ya.n_clipped ?? 0,
  };
  const hi = Number.isFinite(y.hi) ? y.hi : Infinity;
  const curveMin = Number.isFinite(ea.curve_min_gev) ? ea.curve_min_gev : gates.e_min_gev;
  const yMinGev = Number.isFinite(ea.y_min_gev) ? ea.y_min_gev : 2;
  const all = payload.series;
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  const shown = shownSeries(payload, opts.shower);
  const colours = seriesColours(shown);
  const referenceKey = RATIO_REFERENCES.includes(opts.reference) ? opts.reference : 'deposit';
  const entry = referenceKey === 'deposit' ? null : referenceOf(referenceKey);
  const clipped = { markers: 0, whiskers: 0, fits: 0, literature: 0, ratio: 0 };
  const clampY = (v) => Math.min(Math.max(v, 0), hi);
  const energyOf = (w) => (Number.isFinite(w.x) && w.x > 0 ? 1 / (w.x * w.x) : (w.p_mean ?? w.p_lo ?? null));

  const byShower = {};
  for (const sh of new Set(shown.map((s) => s.shower ?? 'a'))) {
    byShower[sh] = entry ? literatureReference(entry, sh) : depositReference(all, sh, mode, nShowers, curveMin, x.max);
  }
  let belowNotDrawn = 0;

  const series = shown.map((s, k) => {
    const colour = colours[s.key];
    const isB = s.shower === 'b' && nShowers > 1;
    const mf = s.fits?.[mode] ?? null;
    const ref = byShower[s.shower ?? 'a'] ?? null;
    const fittedBins = new Set(mf?.points ?? []);
    const anchorBins = new Set(s.fits?.anchors?.points ?? []);
    // Every window on [0, x.max] that reports σ/E; the anchors mode draws its fitted ones only.
    const eligible = (s.windows ?? []).filter((w) => Number.isFinite(w.value) && Number.isFinite(w.x) && w.x > 0
      && (w.n ?? 0) >= gates.report_n && 1 / (w.x * w.x) <= x.max + 1e-9);
    const drawn = mode === 'anchors' ? eligible.filter((w) => fittedBins.has(w.bin)) : eligible;
    const points = drawn.map((w) => {
      const E = 1 / (w.x * w.x);
      const ci = Array.isArray(w.ci95) && Number.isFinite(w.ci95[0]) && Number.isFinite(w.ci95[1]) ? w.ci95 : null;
      const whisker = Boolean(w.whisker) && ci !== null;
      const weak = (w.n ?? 0) < gates.fit_n;
      const subFloor = !whisker;
      const opacity = subFloor ? legibleOpacity(colour, SUB_FLOOR_OPACITY) : (weak ? legibleOpacity(colour, WEAK_OPACITY) : 1);
      const clip = whisker ? clampInterval(ci[0], ci[1], 0, hi) : null;
      const over = w.value > hi || w.value < 0;
      if (over) clipped.markers += 1;
      if (clip && (clip.cutLo || clip.cutHi)) clipped.whiskers += 1;
      const pLo = Number.isFinite(w.p_lo) ? w.p_lo : E;
      const below4 = pLo < curveMin;
      const robust = (w.n ?? 0) >= gates.fit_n && pLo >= yMinGev;
      let ratio;
      if (!ref || ref.reason) {
        ratio = { drawn: false, reason: ref?.reason ?? 'no reference for this shower', ref: null, value: null, lo: null, hi: null, robust };
      } else {
        const r = ref.valueAt(E);
        if (!(r > 0)) {
          belowNotDrawn += 1;
          ratio = {
            drawn: false, ref: null, value: null, lo: null, hi: null, robust,
            reason: `below ${formatNumber(curveMin)} GeV, where no fit is drawn, so ${ref.label} has no value there`,
          };
        } else {
          ratio = {
            drawn: true, reason: null, ref: r, value: w.value / r,
            lo: whisker ? ci[0] / r : null, hi: whisker ? ci[1] / r : null, robust,
          };
        }
      }
      return {
        w, E, x: w.x, value: w.value, ci, lo: ci?.[0] ?? null, hi: ci?.[1] ?? null, n: w.n, whisker, weak, subFloor, below4,
        anchor: anchorBins.has(w.bin), fitted: fittedBins.has(w.bin), robust, opacity, clip, over,
        roles: below4 ? belowRoles(w, gates, curveMin) : roleOf(payload, s, mf, mode, w, gates),
        ratio,
      };
    });
    const unreported = (s.windows ?? []).filter((w) => {
      const e = energyOf(w);
      return Number.isFinite(e) && e <= x.max && !((w.n ?? 0) >= gates.report_n && Number.isFinite(w.value));
    });
    const span = spanOf(mf, s);
    const grid = energyGrid(curveMin, x.max, span ?? []);
    const lineRuns = (rows) => clipPolyline(rows.map(([e, yv]) => [e, yv]), 0, hi);
    const bandRows = (rows) => rows.map(([e, , lo, up]) => [e, clampY(lo), clampY(up)]);
    const fits = {};
    for (const form of ENERGY_FORMS) {
      const fit = mf?.[form] ?? null;
      const reason = form === 'quadrature' ? quadratureReason(fit) : (pinnedDrawable(fit) ? null : 'too few windows');
      if (reason) {
        fits[form] = { form, fit, drawable: false, reason, span, ratio: null };
        continue;
      }
      const curve = fitCurveE(fit, grid);
      const parts = splitAtSpan(curve, span);
      const cut = cutAbove(curve, hi);
      if (cut) clipped.fits += 1;
      const isReference = Boolean(ref && !ref.reason && ref.series === s.key && ref.form === form);
      let ratio = null;
      if (ref && !ref.reason && !isReference) {
        const rows = curve.map(([e, yv, lo, up]) => {
          const r = ref.valueAt(e);
          return r > 0 ? [e, yv / r, lo / r, up / r] : null;
        }).filter(Boolean);
        ratio = rows.length ? { rows } : null;
      }
      fits[form] = {
        form, fit, drawable: true, reason: null, span, domain: [curveMin, x.max], curve,
        solid: lineRuns(parts.inside), dashed: [...lineRuns(parts.below), ...lineRuns(parts.above)],
        band: { below: bandRows(parts.below), inside: bandRows(parts.inside), above: bandRows(parts.above) },
        cut, floorCut: grid.some((e) => evalFitAt(fit, e)?.cutLo), provisional: Boolean(fit.provisional ?? mf?.provisional),
        converged: fit.converged !== false, isReference, ratio,
      };
    }
    return {
      key: s.key, label: s.label ?? s.key, short: shortName(s, nShowers), raw: s, colour, isB,
      offsetPx: (k - (shown.length - 1) / 2) * SERIES_OFFSET_PX,
      lineOpacity: (provisional) => legibleOpacity(colour, (isB ? B_STRENGTH : 1) * (provisional ? PROVISIONAL_OPACITY : 1)),
      mf, provisional: Boolean(mf?.provisional), span, points, fits, unreported, reference: ref,
    };
  });

  // The ratio axis: k from the robust ratio marks (windows of N ≥ fit_n from y_min_gev, whiskers included,
  // and the drawn non-provisional fits over their spans), then every ratio mark clipped to [1/k, k].
  const marks = [];
  for (const s of series) {
    for (const p of s.points) {
      if (!p.ratio.drawn) continue;
      marks.push(p.ratio.robust
        ? { value: p.ratio.value, lo: p.ratio.lo, hi: p.ratio.hi, robust: true, marker: true }
        : { value: p.ratio.value, marker: true });
    }
    for (const f of ENERGY_FORMS.map((form) => s.fits[form])) {
      if (!f?.drawable || f.provisional || !f.ratio) continue;
      const inside = splitAtSpan(f.ratio.rows, f.span).inside.map((r) => r[1]).filter((v) => v > 0);
      if (inside.length) marks.push({ value: Math.max(...inside), lo: Math.min(...inside), robust: true });
    }
  }
  const { k, provisional: ratioProvisional } = ratioRange(marks);
  const ratioClipped = { markers: 0, whiskers: 0, fits: 0 };
  for (const s of series) {
    for (const p of s.points) {
      const r = p.ratio;
      if (!r.drawn) continue;
      r.over = r.value > k || r.value < 1 / k;
      r.clip = Number.isFinite(r.lo) && Number.isFinite(r.hi) ? clampInterval(r.lo, r.hi, 1 / k, k) : null;
      if (r.over) ratioClipped.markers += 1;
      if (r.clip && (r.clip.cutLo || r.clip.cutHi)) ratioClipped.whiskers += 1;
    }
    for (const f of ENERGY_FORMS.map((form) => s.fits[form])) {
      if (!f?.drawable || !f.ratio) continue;
      const parts = splitAtSpan(f.ratio.rows, f.span);
      const clampR = (v) => (Number.isFinite(v) && v > 0 ? Math.min(Math.max(v, 1 / k), k) : 1 / k);
      const band = (rows) => rows.map(([e, , lo, up]) => [e, clampR(lo), clampR(up)]);
      const line = (rows) => clipLog(rows.map(([e, r]) => [e, r]), k);
      f.ratio.solid = line(parts.inside);
      f.ratio.dashed = [...line(parts.below), ...line(parts.above)];
      f.ratio.band = { below: band(parts.below), inside: band(parts.inside), above: band(parts.above) };
      f.ratio.cut = ratioCut(f.ratio.rows, k);
      if (f.ratio.cut) ratioClipped.fits += 1;
    }
  }
  clipped.ratio = ratioClipped.markers + ratioClipped.whiskers + ratioClipped.fits;
  // A deposit reference's own band wider than the ratio axis is clamped at it: a wash, so no caret, but counted.
  ratioClipped.bands = 0;
  for (const ref of Object.values(byShower)) {
    if (!ref.band) continue;
    ref.bandClipped = [...ref.band.below, ...ref.band.inside, ...ref.band.above].some(([, , lo, up]) => !(lo >= 1 / k) || up > k);
    if (ref.bandClipped) ratioClipped.bands += 1;
  }

  // The literature curves, both, when one of them is the reference; they never set a range.
  const literature = [];
  if (entry) {
    const grid = energyGrid(E_GRID_STEP_GEV, x.max);
    for (const lit of RESOLUTION_REFERENCES) {
      const curve = grid.map((e) => [e, referenceValue(lit, e)]).filter((c) => Number.isFinite(c[1]));
      let cut = null;
      for (let i = 0; i + 1 < curve.length && !cut; i += 1) {
        const [e0, v0] = curve[i];
        const [e1, v1] = curve[i + 1];
        if ((v0 > hi) !== (v1 > hi)) cut = { at: e0 + ((hi - v0) / (v1 - v0)) * (e1 - e0), peak: curve[0] };
      }
      if (!cut && curve.length && curve[0][1] > hi) cut = { at: curve[0][0], peak: curve[0] };
      if (cut) clipped.literature += 1;
      literature.push({
        key: lit.key, entry: lit, label: `${lit.particle} lit.`, legend: `${lit.particle} lit. — ${referenceEquation(lit)}`,
        inForce: lit.key === referenceKey, curve, runs: clipPolyline(curve, 0, hi), cut,
      });
    }
  }

  // The canvas note: the windows above the top by window, and the extrapolation rule.
  const groups = new Map();
  for (const s of series) {
    for (const p of s.points) {
      if (!(p.value > hi)) continue;
      const label = p.w.label ?? `bin ${p.w.bin}`;
      const g = groups.get(label) ?? { label, E: p.E, entries: [] };
      g.E = Math.min(g.E, p.E);
      g.entries.push({ key: s.key, short: s.short, value: p.value, n: p.n });
      groups.set(label, g);
    }
  }
  const offScale = [...groups.values()].sort((a, b) => a.E - b.E);
  const bySeries = series.flatMap((s) => ENERGY_FORMS.map((form) => s.fits[form]).filter((f) => f?.drawable)
    .map((f) => ({ key: s.key, label: s.label, form: f.form, span: f.span })));
  const same = (a, b) => (a === null && b === null) || (a && b && a[0] === b[0] && a[1] === b[1]);
  const shared = bySeries.length > 0 && bySeries.every((b) => same(b.span, bySeries[0].span));
  const noteText = {
    offScale: offScale.length ? `↑ off scale: ${offScale.map(offScaleGroupText).join('; ')}` : '',
    extrapolation: !bySeries.length ? ''
      : (shared && bySeries[0].span
        ? `dashed: fit extrapolated beyond its fitted windows (${spanText(bySeries[0].span)})`
        : 'dashed: each fit extrapolated beyond its own fitted windows (Details)'),
  };

  const refLabel = entry ? referenceLabel(entry)
    : (Object.keys(byShower).length > 1 ? 'each shower\'s deposit fit' : (Object.values(byShower)[0]?.label ?? 'the deposit fit'));
  return {
    view: 'energy', mode, gates, nShowers, payload, x, y,
    curveMinGev: curveMin, yMinGev, dataMaxGev: ea.data_max_gev ?? null, rule: ea.rule ?? null, notes: [...(ea.notes ?? [])],
    reference: {
      key: referenceKey, label: refLabel, literature: entry, interval: entry ? null : 'band',
      flag: entry ? 'no interval reported' : null, byShower,
    },
    series, literature,
    ratio: {
      k, provisional: ratioProvisional, reference: referenceKey, clipped: ratioClipped, belowNotDrawn,
      noReference: Object.values(byShower).filter((r) => r.reason).map((r) => ({ shower: r.shower, reason: r.reason })),
    },
    clipped, offScale,
    spans: { shared, span: shared ? bySeries[0].span : null, bySeries },
    noteText,
    nPoints: series.reduce((a, s) => a + s.points.length, 0),
    nLines: series.reduce((a, s) => a + ENERGY_FORMS.filter((form) => s.fits[form]?.drawable).length, 0),
  };
}

/** One window's group on the canvas note: "1–2 GeV — A network 79.1%, B network 77.6%". */
function offScaleGroupText(g) {
  return `${g.label} — ${g.entries.map((e) => `${e.short} ${pct(e.value)}`).join(', ')}`;
}

/* ------------------------------------------------------- E-view tips -- */

/** "plotted at E = 1/⟨1/√p⟩² = 5.49 GeV …; ⟨p⟩ = 5.5 GeV": where a window sits on this axis. */
function plottedAtLine(p) {
  return `plotted at E = 1/⟨1/√p⟩² = ${formatNumber(p.E, 2)} GeV (the 1/√E view's x mapped by E = 1/x²); `
    + `⟨p⟩ = ${formatNumber(p.w.p_mean, 2)} GeV`;
}

/** The tooltip of one window on the main panel: the 1/√E view's, with where it is plotted. */
export function energyPointTip(model, s, p) {
  const lines = pointTipLines(model, s, p);
  lines.splice(3, 0, escapeHtml(plottedAtLine(p)));
  return lines.join('<br/>');
}

/** The ratio axis's range as written: "0.5 to 2". */
function ratioRangeText(model) {
  return `${sigFigs(1 / model.ratio.k, 3)} to ${sigFigs(model.ratio.k, 3)}${model.ratio.provisional ? ', provisional' : ''}`;
}

/** The tooltip of one window on the ratio panel: its ratio, named against its reference and said to be conditional. */
export function ratioPointTip(model, s, p) {
  const r = p.ratio;
  const ref = s.reference;
  const lines = pointTipLines(model, s, p);
  if (p.over || p.clip?.cutLo || p.clip?.cutHi) lines.pop();
  lines.splice(3, 0, escapeHtml(plottedAtLine(p)));
  let text = `Ratio to ${ref.label} = ${sig(r.value)}`;
  if (Number.isFinite(r.lo) && Number.isFinite(r.hi)) text += `, interval [${sig(r.lo)}, ${sig(r.hi)}]`;
  lines.splice(5, 0, `<b>${escapeHtml(text)}</b>`);
  lines.push(mutedLine(`The reference reads ${pct(r.ref)} at this E. The interval is conditional on the reference: it is this window's 95% χ² interval divided by it, `
    + (ref.literature ? 'and the literature curve has no interval reported.' : 'and the reference\'s own uncertainty, its band about 1, is not included.')));
  if (r.over || r.clip?.cutLo || r.clip?.cutHi) {
    lines.push(mutedLine(`clipped at the ratio axis (${ratioRangeText(model)}); the values above are the true ones`));
  }
  return lines.join('<br/>');
}

/** A drawn fit's equation, in ⊕ notation, with its parameters. */
function energyEquation(f) {
  const p = f.fit.params ?? {};
  return f.form === 'quadrature'
    ? `Quadrature fit σ/E = (${sig(p.a)} ± ${sig(p.se_a)})%/√E ⊕ (${sig(p.b)} ± ${sig(p.se_b)})%`
    : `Origin-pinned fit σ/E = (${sig(p.a0)} ± ${sig(p.se_a0)})%/√E ⊕ 0 (b ≡ 0, through the origin)`;
}

/** The extrapolation sentence of a dashed part. */
function extrapolatedLine(f) {
  return `Extrapolated: beyond the windows this fit used (${spanText(f.span)}). The band is its parameters' 95% uncertainty only and assumes the form holds.`;
}

/** The tooltip of one drawn fit on the main panel; `part` 'solid' (over its windows) or 'dashed'. */
export function energyFitTip(model, s, f, part = 'solid') {
  const { fit, form } = f;
  const p = fit.params ?? {};
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const lines = [`<b>${escapeHtml(s.label)}</b>`, escapeHtml(energyEquation(f))];
  if (form === 'quadrature') {
    lines.push(mutedLine(`fitted as (σ/E)² = A/E + B: A = ${sig(p.a2)} ± ${sig(p.se_a2)} %²·GeV, B = ${sig(p.b2)} ± ${sig(p.se_b2)} %², ρ(A, B) = ${sig(p.rho_a2b2)}`));
    if (scaled) lines.push(mutedLine(`errors scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a) = ${sig(p.se_a_stat)}, SE(b) = ${sig(p.se_b_stat)}`));
  } else if (scaled) {
    lines.push(mutedLine(`error scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a₀) = ${sig(p.se_a0_stat)}`));
  }
  lines.push(fit.ndf > 0 && Number.isFinite(fit.p_value)
    ? chi2Text(fit)
    : `${chi2Text(fit)}: the curve passes through its ${formatInt(fit.n_points)} point${fit.n_points === 1 ? '' : 's'} exactly`);
  lines.push(`Windows fitted (${formatInt(fit.n_points)}): ${escapeHtml(windowsText(model.payload, s.raw, s.mf))}`);
  lines.push(mutedLine(`Solid over ${spanText(f.span)}, the windows it was fitted to; dashed beyond, from ${formatNumber(model.curveMinGev)} to ${formatNumber(model.x.max)} GeV, where it extrapolates its form.`));
  if (part === 'dashed') lines.push(escapeHtml(extrapolatedLine(f)));
  if (f.provisional) {
    lines.push(mutedLine(`Provisional: fewer than two windows reach N = ${formatInt(model.gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(model.gates.whisker_n)}; drawn faded.`));
  }
  if (!f.converged) {
    lines.push(mutedLine(`Not converged: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so this is the last refit's curve, not a fixed point.`));
  }
  if (s.isB) lines.push(mutedLine('Shower B\'s lines are drawn at 70% strength: on this view the dash means extrapolation, not the shower.'));
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true values.'));
  lines.push(mutedLine('The shaded band beside it is the fit\'s 95% confidence band.'));
  return lines.join('<br/>');
}

/** The tooltip of one fit's band on the main panel; `outside` for its parts beyond the fitted windows. */
export function energyBandTip(model, s, f, outside = false) {
  const fit = f.fit;
  const q = Number.isFinite(fit.band_quantile) ? fit.band_quantile : DEFAULT_QUANTILE;
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const lines = [`<b>${escapeHtml(s.label)}</b>`];
  lines.push(escapeHtml(f.form === 'quadrature'
    ? `95% confidence band of the quadrature fit a/√E ⊕ b: √ of the band of z = (σ/E)² = A/E + B, ẑ ± ${sigFigs(q, 4)} √(gᵀΣg) with g = (1/E, 1). z is linear in (A, B) and √ is monotone, so this is the exact 95% band, with no delta method.`
    : `95% confidence band of the origin-pinned fit a₀/√E ⊕ 0: a₀/√E ± ${sigFigs(q, 4)}·SE(a₀)/√E.`));
  if (scaled) {
    lines.push(mutedLine(`The covariance is scaled by S = ${sig(fit.scale_factor)}; S is estimated from the fit's own ν = ${formatInt(fit.ndf)}, so Student's t₀.₉₇₅,${formatInt(fit.ndf)} = ${sigFigs(q, 4)} replaces 1.96.`));
  }
  lines.push(mutedLine('The uncertainty of the fitted curve, not the spread of the events.'));
  if (outside) lines.push(escapeHtml(`${extrapolatedLine(f)} Drawn at a third of its strength.`));
  if (f.floorCut) {
    lines.push(mutedLine(f.form === 'quadrature'
      ? 'Its lower edge is cut at 0 where ẑ − h < 0: a resolution cannot be negative.'
      : 'Its lower edge is cut at σ/E = 0, the floor of the axis.'));
  }
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true values.'));
  return lines.join('<br/>');
}

/** The tooltip of the caret where a drawn fit's curve or band leaves the top of the main panel. */
export function energyFitCutTip(model, s, f) {
  const { cut } = f;
  const name = f.form === 'quadrature' ? 'quadrature fit a/√E ⊕ b' : 'origin-pinned fit a₀/√E ⊕ 0';
  const [pe, py, plo, pup] = cut.peak;
  const at = (e) => `E = ${sig(e)} GeV`;
  return [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`The ${f.provisional ? 'provisional ' : ''}${name} leaves the top of the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}):`
      + `${cut.lineAt !== null ? ` its curve first at ${at(cut.lineAt)},` : ''} its 95% band first at ${at(cut.bandAt ?? cut.lineAt)}, scanning up in E.`),
    escapeHtml(`True values where the band reaches highest, at ${at(pe)}: the curve ${pct(py)}, the band [${pct(plo)}, ${pct(pup)}].`),
    mutedLine(f.provisional
      ? 'Clipped, not rescaled: a provisional fit runs through windows of N < 20 and never sets the range.'
      : 'Clipped, not rescaled: the range follows the windows of N ≥ 20 from 2 GeV and the fitted curves over their windows, never a band or an extrapolation.'),
  ].join('<br/>');
}

/** The tooltip of one drawn fit on the ratio panel. */
export function ratioFitTip(model, s, f, part = 'solid') {
  const ref = s.reference;
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`${energyEquation(f)} ÷ ${ref.label}`),
    mutedLine('The fitted curve divided by the reference at each E. Its faint band is the fit\'s 95% band divided the same way, '
      + 'conditional on the reference: the reference\'s own uncertainty is not included.'),
  ];
  if (part === 'dashed') lines.push(escapeHtml(extrapolatedLine(f)));
  if (f.ratio?.cut) lines.push(mutedLine('It leaves the ratio axis: the caret there gives its true values.'));
  return lines.join('<br/>');
}

/** The tooltip of the caret where a fit's ratio leaves the ratio axis. */
function ratioFitCutTip(model, s, f) {
  const cut = f.ratio.cut;
  const [pe, pr, plo, pup] = cut.peak;
  const name = f.form === 'quadrature' ? 'quadrature fit a/√E ⊕ b' : 'origin-pinned fit a₀/√E ⊕ 0';
  return [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`The ratio of the ${name} to ${s.reference.label} leaves the ratio axis (${ratioRangeText(model)}) first at E = ${sig(cut.at)} GeV, scanning up in E.`),
    escapeHtml(`True values where it deviates most, at E = ${sig(pe)} GeV: the ratio ${sig(pr)}, its band [${sig(plo)}, ${sig(pup)}].`),
    mutedLine('Clipped, not rescaled: the ratio range follows the windows of N ≥ 20 from 2 GeV and the fits over their windows.'),
  ].join('<br/>');
}

/** The tooltip of a deposit reference's own band about 1 on the ratio panel. */
function referenceBandTip(model, ref, outside) {
  const lines = [
    `<b>${escapeHtml(ref.seriesLabel ?? ref.label)}</b>`,
    escapeHtml(`The reference, ${ref.label}: its own 95% confidence band relative to itself, [lo/ŷ, hi/ŷ] about 1.`),
    mutedLine('The ratio marks\' intervals are conditional on the reference and do not include this band.'),
  ];
  if (outside) lines.push(mutedLine(`Beyond its fitted windows (${spanText(ref.span)}), where the reference extrapolates its form: drawn fainter.`));
  return lines.join('<br/>');
}

/** The tooltip of the ratio panel's 1.0 rule. */
function unityTip(model) {
  const ref = model.reference;
  return [
    `<b>ratio = 1</b>`,
    escapeHtml(`σ/E equal to the reference: ${ref.literature ? referenceEquation(ref.literature) : ref.label}.`),
    mutedLine(`A log axis symmetric about 1 (${ratioRangeText(model)}), so ×k and ÷k lie at equal distances from this rule.`),
  ].join('<br/>');
}

/** The tooltip of one literature curve. */
export function literatureTip(model, lit) {
  const lines = [
    `<b>${escapeHtml(`${lit.entry.particle} literature curve`)}</b>`,
    escapeHtml(referenceEquation(lit.entry)),
    mutedLine(LITERATURE_PROVENANCE),
  ];
  if (lit.inForce) lines.push(mutedLine('The ratio panel divides by this curve.'));
  lines.push(mutedLine('A reference, not a measurement: it never sets the range.'));
  return lines.join('<br/>');
}

/** The tooltip of the caret where a literature curve crosses the top of the main panel. */
function literatureCutTip(model, lit) {
  const [pe, pv] = lit.cut.peak;
  return [
    `<b>${escapeHtml(`${lit.entry.particle} literature curve`)}</b>`,
    escapeHtml(`${referenceEquation(lit.entry)} lies above the top of the axis (0 to ${pct(model.y.hi)}) below E = ${sig(lit.cut.at)} GeV; at E = ${sig(pe)} GeV it reads ${pct(pv)}.`),
    mutedLine('Clipped, not rescaled: a literature curve never sets the range.'),
  ].join('<br/>');
}

/* ------------------------------------------------------- E-view marks -- */

/** A series' markers at `items` ({p, at: [E, v]}): filled (A) or hollow (B); a dashed ring below the whisker floor. */
function energyMarkers(s, items, id, tip) {
  return {
    type: 'custom',
    id,
    name: s.label,
    clip: true,
    z: 8,
    data: items.map((it, index) => [it.at[0], it.at[1], index]),
    renderItem: (params, api) => {
      const { p, at } = items[params.dataIndex];
      const c = api.coord(at);
      const cx = c[0] + s.offsetPx;
      const r = p.anchor ? ANCHOR_PX : MARKER_PX;
      if (p.subFloor) {
        const ring = {
          type: 'circle', shape: { cx, cy: c[1], r },
          style: { fill: THEME.card, stroke: s.colour, lineWidth: 1.2 * THEME.lineAxis, lineDash: DASH_RING, opacity: p.opacity },
        };
        if (s.isB) return ring;
        return { type: 'group', children: [ring, { type: 'circle', shape: { cx, cy: c[1], r: CORE_PX }, style: { fill: s.colour, opacity: p.opacity } }] };
      }
      return {
        type: 'circle',
        shape: { cx, cy: c[1], r },
        style: s.isB
          ? { fill: THEME.card, stroke: s.colour, lineWidth: 1.4 * THEME.lineAxis, opacity: p.opacity }
          : { fill: s.colour, stroke: THEME.card, lineWidth: 0.6 * THEME.lineAxis, opacity: p.opacity },
      };
    },
    tooltip: { formatter: (prm) => tip(items[prm.dataIndex].p) },
  };
}

/** A band series on the ratio grid: its one datum a valid point of the log axis (`customBand` draws from its closure). */
function ratioBand(options) {
  const band = customBand(options);
  const first = options.points[0];
  return { ...band, data: [[first[0], first[1]]], xAxisIndex: 1, yAxisIndex: 1 };
}

/** Every mark of one series on both grids, each named after it, so its legend entry shows and hides all of them. */
function energySeriesMarks(model, s) {
  const { y } = model;
  const k = model.ratio.k;
  const out = [];
  const style = itemStyleOf(s);
  const named = (x) => ({ ...withColour(x, s.colour), name: s.label, itemStyle: { ...style } });
  const onRatio = (x) => ({ ...x, xAxisIndex: 1, yAxisIndex: 1 });
  const whiskerOpacity = (p) => (p.opacity === 1 ? 1 : legibleOpacity(s.colour, WEAK_OPACITY));
  const casing = { color: THEME.canvas, width: CASING_PX };

  // ---- the main panel
  out.push(named(energyMarkers(s, s.points.filter((p) => !p.over).map((p) => ({ p, at: [p.E, p.value] })),
    `${s.key}|markers`, (p) => energyPointTip(model, s, p))));
  const whiskers = s.points
    .filter((p) => p.whisker && p.clip && p.clip.lo !== null && p.clip.hi !== null && p.clip.hi > p.clip.lo)
    .map((p) => [p.E, p.clip.lo, p.clip.hi, { caps: p.clip.caps, opacity: whiskerOpacity(p), point: p }]);
  if (whiskers.length) {
    out.push(named({
      ...customWhiskers({
        name: s.label, points: whiskers, capPx: CAP_PX, color: s.colour, width: 1.2 * THEME.lineAxis,
        offsetPx: s.offsetPx, z: 7, casing, tooltip: (d) => energyPointTip(model, s, d.point),
      }),
      id: `${s.key}|whiskers`,
    }));
  }
  const carets = [];
  for (const p of s.points) {
    if (!(p.value > y.hi || p.clip?.cutHi || p.value < 0 || p.clip?.cutLo)) continue;
    const tip = energyPointTip(model, s, p);
    if (p.value > y.hi || p.clip?.cutHi) carets.push({ at: [p.E, y.hi], dir: 'up', tooltip: tip });
    if (p.value < 0 || p.clip?.cutLo) carets.push({ at: [p.E, 0], dir: 'down', tooltip: tip });
  }
  for (const form of ENERGY_FORMS) {
    const f = s.fits[form];
    if (f?.drawable && f.cut) carets.push({ at: [f.cut.at, y.hi], dir: 'up', tooltip: energyFitCutTip(model, s, f) });
  }
  if (carets.length) {
    out.push(named({ ...caretSeries({ name: s.label, carets, color: s.colour, offsetPx: s.offsetPx }), id: `${s.key}|carets` }));
  }
  for (const form of ENERGY_FORMS) {
    const f = s.fits[form];
    if (!f?.drawable) continue;
    const wide = form === 'quadrature';
    const opacity = s.lineOpacity(f.provisional);
    const width = (wide ? 1.6 : 1) * THEME.lineAxis;
    for (const [part, runs] of [['solid', f.solid], ['dashed', f.dashed]]) {
      runs.forEach((run, i) => {
        out.push(named({
          ...customPolyline({
            name: s.label, points: run, color: s.colour, opacity, z: 5, width,
            dash: part === 'dashed' ? DASH_EXTRAPOLATED : null,
            tooltip: () => energyFitTip(model, s, f, part),
          }),
          id: `${s.key}|${form}|${part}|${i}`,
        }));
      });
    }
    const alpha = (wide ? 1 : 0.5) * THEME.bandAlpha * (f.provisional ? 0.6 : 1) * (s.isB ? B_STRENGTH : 1);
    for (const part of ['below', 'inside', 'above']) {
      const points = f.band[part];
      if (points.length < 2) continue;
      out.push(named({
        ...customBand({ name: s.label, points, color: s.colour, z: 2, opacity: part === 'inside' ? alpha : alpha * OUT_ALPHA }),
        id: `${s.key}|${form}|band|${part}`,
        silent: false,
        tooltip: { formatter: () => energyBandTip(model, s, f, part !== 'inside') },
      }));
    }
  }

  // ---- the ratio panel
  const ratioPoints = s.points.filter((p) => p.ratio.drawn);
  const ratioShown = ratioPoints.filter((p) => !p.ratio.over);
  if (ratioShown.length) {
    out.push(named(onRatio(energyMarkers(s, ratioShown.map((p) => ({ p, at: [p.E, p.ratio.value] })),
      `${s.key}|ratio|markers`, (p) => ratioPointTip(model, s, p)))));
  }
  const ratioWhiskers = ratioPoints
    .filter((p) => p.ratio.clip && p.ratio.clip.hi > p.ratio.clip.lo)
    .map((p) => [p.E, p.ratio.clip.lo, p.ratio.clip.hi, { caps: p.ratio.clip.caps, opacity: whiskerOpacity(p), point: p }]);
  if (ratioWhiskers.length) {
    out.push(named(onRatio({
      ...customWhiskers({
        name: s.label, points: ratioWhiskers, capPx: CAP_PX, color: s.colour, width: 1.2 * THEME.lineAxis,
        offsetPx: s.offsetPx, z: 7, casing, tooltip: (d) => ratioPointTip(model, s, d.point),
      }),
      id: `${s.key}|ratio|whiskers`,
    })));
  }
  const ratioCarets = [];
  for (const p of ratioPoints) {
    const r = p.ratio;
    const up = r.value > k || r.clip?.cutHi;
    const down = r.value < 1 / k || r.clip?.cutLo;
    if (!up && !down) continue;
    const tip = ratioPointTip(model, s, p);
    if (up) ratioCarets.push({ at: [p.E, k], dir: 'up', tooltip: tip });
    if (down) ratioCarets.push({ at: [p.E, 1 / k], dir: 'down', tooltip: tip });
  }
  for (const form of ENERGY_FORMS) {
    const f = s.fits[form];
    const cut = f?.drawable ? f.ratio?.cut : null;
    if (cut) ratioCarets.push({ at: [cut.at, cut.dir === 'up' ? k : 1 / k], dir: cut.dir, tooltip: ratioFitCutTip(model, s, f) });
  }
  if (ratioCarets.length) {
    out.push(named(onRatio({ ...caretSeries({ name: s.label, carets: ratioCarets, color: s.colour, offsetPx: s.offsetPx }), id: `${s.key}|ratio|carets` })));
  }
  for (const form of ENERGY_FORMS) {
    const f = s.fits[form];
    if (!f?.drawable || !f.ratio) continue;
    const wide = form === 'quadrature';
    const opacity = s.lineOpacity(f.provisional);
    const width = (wide ? 1.6 : 1) * THEME.lineAxis;
    for (const [part, runs] of [['solid', f.ratio.solid], ['dashed', f.ratio.dashed]]) {
      runs.forEach((run, i) => {
        out.push(named(onRatio({
          ...customPolyline({
            name: s.label, points: run, color: s.colour, opacity, z: 5, width,
            dash: part === 'dashed' ? DASH_EXTRAPOLATED : null,
            tooltip: () => ratioFitTip(model, s, f, part),
          }),
          id: `${s.key}|ratio|${form}|${part}|${i}`,
        })));
      });
    }
    const alpha = RATIO_BAND_SHARE * (wide ? 1 : 0.5) * THEME.bandAlpha * (f.provisional ? 0.6 : 1) * (s.isB ? B_STRENGTH : 1);
    for (const part of ['below', 'inside', 'above']) {
      const points = f.ratio.band[part];
      if (points.length < 2) continue;
      out.push(named({
        ...ratioBand({ name: s.label, points, color: s.colour, z: 2, opacity: part === 'inside' ? alpha : alpha * OUT_ALPHA }),
        id: `${s.key}|ratio|${form}|band|${part}`,
        silent: false,
        tooltip: { formatter: () => ratioFitTip(model, s, f, part === 'inside' ? 'solid' : 'dashed') },
      }));
    }
  }
  // The deposit reference's own band about 1, drawn with its deposit series (and hidden with it).
  const ref = s.reference;
  if (ref && !ref.reason && ref.band && ref.series === s.key) {
    for (const part of ['below', 'inside', 'above']) {
      const points = ref.band[part].map(([e, , lo, up]) => [e, Math.min(Math.max(lo, 1 / k), k), Math.min(Math.max(up, 1 / k), k)]);
      if (points.length < 2) continue;
      out.push({
        ...ratioBand({
          name: s.label, points, color: THEME.muted, z: 1,
          opacity: REFERENCE_BAND_SHARE * THEME.bandAlpha * (part === 'inside' ? 1 : OUT_ALPHA),
        }),
        id: `${s.key}|ratio|reference|band|${part}`,
        itemStyle: { ...style },
        silent: false,
        tooltip: { formatter: () => referenceBandTip(model, ref, part !== 'inside') },
      });
    }
  }
  return out;
}

/** Where each literature curve's direct label sits at the right end, kept apart when the curves run close. */
function literatureLabelPlaces(model, api) {
  const h = THEME.fontSmall + 2;
  const places = model.literature.map((lit) => {
    const v = Math.min(Math.max(referenceValue(lit.entry, model.x.max), 0), model.y.hi);
    const c = api.coord([model.x.max, v]);
    return { key: lit.key, x: c[0] - 4, y: c[1] - 3 };
  });
  // Lowest on the canvas first; each label above it moves up until the two clear.
  places.sort((a, b) => b.y - a.y);
  for (let i = 1; i < places.length; i += 1) places[i].y = Math.min(places[i].y, places[i - 1].y - h);
  return Object.fromEntries(places.map((pl) => [pl.key, pl]));
}

/** One literature curve on the main panel: dotted muted runs with its direct label, and its legend entry. */
function literatureSeries(model, lit) {
  const width = 1.2 * THEME.lineAxis;
  return {
    type: 'custom',
    id: `literature|${lit.key}`,
    name: lit.legend,
    clip: true,
    z: 4,
    silent: false,
    itemStyle: { color: THEME.muted },
    data: [lit.curve[0] ?? [model.x.max, 0]],
    renderItem: (params, api) => {
      const children = lit.runs.map((run) => ({
        type: 'polyline',
        shape: { points: run.map((pt) => api.coord(pt)) },
        style: { fill: 'none', stroke: THEME.muted, lineWidth: width, lineDash: DASH_LITERATURE },
      }));
      const place = literatureLabelPlaces(model, api)[lit.key];
      if (place) {
        children.push({
          type: 'text', silent: true,
          style: {
            x: place.x, y: place.y, text: lit.label, fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
            textAlign: 'right', textVerticalAlign: 'bottom',
          },
        });
      }
      return { type: 'group', children };
    },
    tooltip: { formatter: () => literatureTip(model, lit) },
  };
}

/**
 * The ratio axis's ticks: 1, k and 1/k, and each step of `RATIO_STEPS` below k
 * with its reciprocal where it clears its neighbours by 1.6 label heights on
 * a panel `heightPx` tall: symmetric, so ×s and ÷s sit at equal distances.
 */
export function ratioTicks(k, heightPx) {
  const minPx = 1.6 * THEME.fontLabel;
  const pxOf = (v) => (heightPx * Math.log(v)) / (2 * Math.log(k));
  const kept = [1, k];
  for (const s of [...RATIO_STEPS].filter((v) => v < k).reverse()) {
    if (kept.every((t) => Math.abs(pxOf(t) - pxOf(s)) >= minPx)) kept.push(s);
  }
  const up = kept.filter((t) => t > 1).sort((a, b) => a - b);
  return [...up.map((t) => 1 / t).reverse(), 1, ...up];
}

/** The ratio axis's name at its height: "ratio to …", shortened to fit, "— provisional" when it is. */
function ratioAxisName(model, px) {
  const ref = model.reference;
  const lit = ref.literature;
  const one = Object.keys(ref.byShower).length === 1 ? Object.values(ref.byShower)[0] : null;
  const owner = model.nShowers > 1 ? (one ? `shower ${String(one.shower).toUpperCase()}'s` : 'each shower\'s') : 'the';
  const names = lit
    ? [`ratio to ${referenceLabel(lit)}`, `÷ ${referenceLabel(lit)}`, `÷ ${lit.particle} lit.`]
    : [`ratio to ${owner} deposit fit`, `÷ ${owner} deposit fit`, '÷ deposit fit'];
  return fitName(model.ratio.provisional ? names.map((n) => `${n} — provisional`) : names, px);
}

/** The canvas note's lines at a width: the off-scale list (two lines at most, then "+n more in Details"), and the extrapolation rule. */
function noteLayout(model, plotWidthPx) {
  const font = THEME.fontTip;
  const family = THEME.fontFamily;
  const lineH = Math.ceil(1.35 * font);
  const width = (t) => measureText(t, font, family);
  const extrapolation = model.noteText.extrapolation;
  let right = [];
  if (extrapolation) {
    // Beside an off-scale list it keeps under half the width; alone it may take all of it.
    const room = Math.max(80, (model.offScale.length ? 0.45 : 1) * plotWidthPx);
    right = width(extrapolation) <= room ? [extrapolation] : wrapText(extrapolation, room, font, family).slice(0, 2);
  }
  const rightW = right.length ? Math.max(...right.map(width)) : 0;
  const room = Math.max(80, plotWidthPx - rightW - (rightW ? 1.5 * font : 0));
  let left = [];
  if (model.offScale.length) {
    // One token per window and series, so a line never breaks inside "7–8 GeV — A network 91.1%".
    const entries = model.offScale.flatMap((g) => g.entries.map((e, i) => ({
      text: i === 0 ? `${g.label} — ${e.short} ${pct(e.value)}` : `${e.short} ${pct(e.value)}`,
      end: i === g.entries.length - 1,
    })));
    for (let keep = entries.length; keep >= 0; keep -= 1) {
      const more = entries.length - keep;
      const tokens = entries.slice(0, keep).map((x, i) => `${x.text}${i < keep - 1 || more ? (x.end ? ';' : ',') : ''}`);
      if (more) tokens.push(`+${formatInt(more)} more in Details`);
      tokens[0] = `↑ off scale: ${tokens[0]}`;
      left = packTokens(tokens, room, font, family);
      if (left.length <= 2) break;
    }
  }
  const lines = Math.max(left.length, right.length);
  return { left, right, lineH, height: lines ? lines * lineH + Math.round(1.1 * font) : 0 };
}

/** `tokens` joined by spaces into lines no wider than `room`, never breaking inside a token. */
function packTokens(tokens, room, font, family) {
  const lines = [];
  let line = '';
  for (const t of tokens) {
    const candidate = line ? `${line} ${t}` : t;
    if (!line || measureText(candidate, font, family) <= room) {
      line = candidate;
    } else {
      lines.push(line);
      line = t;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/**
 * The σ/E axis's tick interval at a plot `heightPx` tall: the server's,
 * widened by a round factor that still lands on the top when its labels would
 * crowd (a printed single-column figure), else the server's unchanged.
 */
function verticalInterval(top, interval, heightPx) {
  if (!(interval > 0) || !(top > 0)) return interval;
  const allowed = Math.max(2, Math.floor(heightPx / (1.8 * THEME.fontLabel)));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    const n = top / (interval * factor);
    if (n <= allowed && Math.abs(n - Math.round(n)) < 1e-9) return interval * factor;
  }
  return interval;
}

/** The crosshair of both grids, linked: a line at the pointer's E, its label on the bottom axis only, never a tooltip. */
function crosshair(label) {
  return {
    show: true,
    type: 'line',
    snap: false,
    triggerTooltip: false,
    lineStyle: { color: THEME.muted, width: THEME.lineAxis, type: [3, 3] },
    label: label
      ? {
        show: true,
        formatter: (p) => {
          const v = typeof p === 'object' && p !== null ? p.value : p;
          return Number.isFinite(Number(v)) ? `E = ${sigFigs(Number(v), 3)} GeV` : '';
        },
        color: THEME.text, backgroundColor: THEME.labelBg, borderColor: THEME.border, borderWidth: 1,
        fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, padding: [2, 4],
      }
      : { show: false },
  };
}

/** What the E view says when it has nothing to draw. */
function energyEmptyText(model) {
  const { gates } = model;
  const reportable = model.series.reduce((a, s) => a + (s.raw.windows ?? [])
    .filter((w) => (w.n ?? 0) >= gates.report_n && Number.isFinite(w.value)).length, 0);
  if (model.mode === 'anchors' && reportable && model.y.hi > 0) {
    return `No window from ${formatNumber(gates.anchor_low_gev)} GeV reaches N = ${formatInt(gates.whisker_n)}, the fewest an anchor fit runs through, `
      + `so the 3-anchor mode draws nothing. "All windows" draws the ${plural(reportable, 'window')} that report σ/E `
      + `(N ≥ ${formatInt(gates.report_n)}), those below ${formatNumber(model.curveMinGev)} GeV as points only.`;
  }
  return 'No momentum window holds two events in this selection, so no σ/E can be drawn on this axis.';
}

/**
 * The E view's option. Pure: `opts` = {windows, shower, reference, palette,
 * card, tooltipPosition?}; `metrics` = {width, height}. Returns {option,
 * plotGrid}: two grids, the main panel over the ratio panel, on one E axis
 * (`plotGrid` their union for the tooltip placement), and the canvas note
 * between the legend and the main panel.
 */
export function energyViewOption(payload, opts = {}, metrics = {}) {
  const model = energyModel(payload, opts);
  if (!model) return { option: emptyChartOption(opts, metrics, 'This response carries no energy-resolution series for the E view.') };
  if (!model.series.length) return { option: emptyChartOption(opts, metrics, 'No series of the chosen shower in this response.') };
  if ((!model.nPoints && !model.nLines) || !(model.y.hi > 0)) return { option: emptyChartOption(opts, metrics, energyEmptyText(model)) };
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const width = metrics.width || 760;
  const height = metrics.height || ENERGY_VIEW_PX;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);

  const series = [];
  const legend = [];
  for (const s of model.series) {
    if (!s.points.length && !ENERGY_FORMS.some((form) => s.fits[form]?.drawable)) continue;
    series.push(...energySeriesMarks(model, s));
    legend.push({ name: s.label, icon: 'circle' });
  }
  for (const lit of model.literature) {
    series.push(literatureSeries(model, lit));
    if (lit.cut) {
      series.push({
        ...caretSeries({ name: lit.legend, carets: [{ at: [lit.cut.at, model.y.hi], dir: 'up', tooltip: literatureCutTip(model, lit) }], color: THEME.muted }),
        id: `literature|${lit.key}|caret`,
        itemStyle: { color: THEME.muted },
      });
    }
    legend.push({ name: lit.legend, icon: LITERATURE_ICON, itemStyle: { color: THEME.muted } });
  }

  const legendBottom = legendTop(legend, plotWidthPx, { wrap: true });
  const note = noteLayout(model, plotWidthPx);
  const mainTop = legendBottom + note.height;
  const avail = Math.max(140, height - mainTop - pad.bottom - GRID_GAP_PX);
  const ratioH = Math.max(40, Math.round(RATIO_SHARE * avail));
  const mainH = Math.max(60, avail - ratioH);
  const grid = [
    { left: pad.left, right: pad.right, top: mainTop, height: mainH },
    { left: pad.left, right: pad.right, top: mainTop + mainH + GRID_GAP_PX, height: ratioH },
  ];
  const { k } = model.ratio;
  series.push({
    type: 'custom',
    id: 'ratio|unity',
    name: 'ratio = 1',
    xAxisIndex: 1,
    yAxisIndex: 1,
    clip: true,
    z: 3,
    silent: false,
    data: [[model.x.min, 1]],
    renderItem: (params, api) => {
      const a = api.coord([model.x.min, 1]);
      const b = api.coord([model.x.max, 1]);
      return { type: 'line', shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: THEME.text, lineWidth: THEME.lineAxis } };
    },
    tooltip: { formatter: () => unityTip(model) },
  });

  const xRange = { min: model.x.min, max: model.x.max, interval: model.x.interval };
  const top = valueAxis({ ...xRange, gridIndex: 0 });
  const bottom = valueAxis({ ...xRange, gridIndex: 1, name: model.x.name });
  const yBase = model.y.name;
  const yName = fitName(model.y.provisional
    ? [`${yBase} — provisional, no window reaches N = ${formatInt(model.gates.fit_n)}`, `${yBase} — provisional`]
    : [yBase], mainH);
  const ticks = ratioTicks(k, ratioH);
  const ratio = valueAxis({
    type: 'log', gridIndex: 1, name: ratioAxisName(model, ratioH), min: 1 / k, max: k, nameGap: 3.6 * f,
    formatter: (v) => sigFigs(Number(v), 3),
  });
  const noteTop = legendBottom + Math.round(0.2 * THEME.fontTip);
  const noteStyle = {
    fill: THEME.muted, fontSize: THEME.fontTip, fontFamily: THEME.fontFamily, lineHeight: note.lineH, textVerticalAlign: 'top',
  };
  const graphic = [];
  if (note.left.length) graphic.push({ type: 'text', silent: true, style: { ...noteStyle, x: pad.left, y: noteTop, text: note.left.join('\n') } });
  if (note.right.length) {
    graphic.push({ type: 'text', silent: true, style: { ...noteStyle, x: width - pad.right, y: noteTop, text: note.right.join('\n'), textAlign: 'right' } });
  }
  return {
    option: {
      ...baseOption(),
      tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid,
      legend: wrappedLegend(legend, { left: pad.left, right: pad.right }),
      xAxis: [
        { ...top, name: '', axisLabel: { ...top.axisLabel, show: false }, axisPointer: crosshair(false) },
        { ...bottom, axisPointer: crosshair(true) },
      ],
      yAxis: [
        valueAxis({
          name: yName, min: 0, max: model.y.hi, interval: verticalInterval(model.y.hi, model.y.interval, mainH),
          split: true, nameGap: 3.6 * f, gridIndex: 0,
        }),
        { ...ratio, logBase: 10, axisTick: { ...ratio.axisTick, customValues: ticks }, axisLabel: { ...ratio.axisLabel, customValues: ticks } },
      ],
      graphic,
      series,
    },
    plotGrid: grid,
  };
}

/**
 * The E view's figure height at an export `width`: the legend and the canvas
 * note, the main panel at `aspect` of the plot width, the gap, and the ratio
 * panel at its share, so the figure keeps the screen's proportions.
 */
export function energyExportMetrics(payload, opts, width, aspect) {
  const pad = axisPadding();
  const plotWidth = Math.max(80, width - pad.left - pad.right);
  const { option } = energyViewOption(payload, opts, { width, height: ENERGY_VIEW_PX });
  const grids = [].concat(option.grid ?? []);
  const top = Number.isFinite(grids[0]?.top) ? grids[0].top : pad.top;
  const mainH = plotWidth * aspect;
  if (grids.length < 2) return { width, height: Math.round(top + pad.bottom + mainH) };
  const ratioH = (mainH * RATIO_SHARE) / (1 - RATIO_SHARE);
  return { width, height: Math.round(top + mainH + GRID_GAP_PX + ratioH + pad.bottom) };
}

/* --------------------------------------------------------------- class -- */

export class ResolutionScalingPanel extends ChartPanel {
  /** `element` is the plot; the fit table goes after the card's `.plot-frame`. */
  constructor(elementOrId, { card = null, aspect } = {}) {
    super(elementOrId, { kind: 'res-scaling', aspect });
    this.card = card;
    this.tableHost = null;
    this.tableDoc = null;
  }

  buildOption({ payload, opts = {}, metrics }) {
    if (resolutionView(opts.view) === 'energy') return energyViewOption(payload, opts, metrics);
    return { option: resolutionScalingOption(payload, opts, metrics) };
  }

  /**
   * The plot's height for the view in force, set before ECharts measures:
   * `ENERGY_VIEW_PX` in the E view, cleared in the 1/√E view so the CSS 420 px
   * holds. True when it changed. It snaps, never animates (the chart's
   * ResizeObserver must see one size).
   */
  syncHeight() {
    if (!this.element?.style) return false;
    const want = resolutionView(this.lastOpts?.view) === 'energy' ? `${ENERGY_VIEW_PX}px` : '';
    if ((this.element.style.height || '') === want) return false;
    this.element.style.height = want;
    return true;
  }

  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    // A view switch resizes the chart in the same call, so the option is laid out at the new height.
    if (this.syncHeight() && this.chart) this.chart.resize();
    super.render(payload, opts);
    this.renderTable();
  }

  relayout() {
    if (this.syncHeight() && this.chart) this.chart.resize();
    super.relayout();
  }

  /** The E view's figure is two panels tall (`energyExportMetrics`); the 1/√E view's is the base figure. */
  exportMetrics(width) {
    if (!this.lastPayload || resolutionView(this.lastOpts?.view) !== 'energy') return super.exportMetrics(width);
    return energyExportMetrics(this.lastPayload, this.lastOpts ?? {}, width, this.aspect);
  }

  /** The table's host, created once after the card's plot frame; null outside a card. */
  ensureTableHost() {
    if (this.tableHost) return this.tableHost;
    const card = this.element?.closest?.('.card');
    const frame = card?.querySelector?.('.plot-frame');
    if (!frame) return null;
    const doc = frame.ownerDocument ?? globalThis.document;
    const host = doc.createElement('div');
    host.className = 'res-fit-table';
    frame.after(host);
    this.tableHost = host;
    this.tableDoc = doc;
    return host;
  }

  /**
   * Text nodes only: every label comes from a payload. One `tbody` per series:
   * its name (a row-group header) and the windows it fitted span its three
   * fit rows, each headed by the fit's name. Every cell wraps at its spaces;
   * text is left-aligned (`text`) and numbers right-aligned (`num`), a value
   * and its SE held together by no-break spaces.
   */
  renderTable() {
    const host = this.ensureTableHost();
    if (!host) return;
    const model = fitTableRows(this.lastPayload, this.lastOpts ?? {});
    if (!model || !model.rows.length) {
      host.replaceChildren();
      return;
    }
    const doc = this.tableDoc ?? host.ownerDocument ?? globalThis.document;
    const el = (tag, text, column = null) => {
      const node = doc.createElement(tag);
      if (text !== undefined && text !== null) node.textContent = text;
      if (column !== null) node.className = FIT_TABLE_TEXT_COLUMNS.includes(column) ? 'text' : 'num';
      return node;
    };
    const table = el('table');
    table.className = 'fit-table';
    table.append(el('caption', model.caption));
    const head = el('thead');
    const names = el('tr');
    model.columns.forEach((c, i) => {
      const th = el('th', c, i);
      th.setAttribute?.('scope', 'col');
      names.append(th);
    });
    head.append(names);
    table.append(head);
    for (const row of model.rows) {
      const body = el('tbody');
      row.fits.forEach((fit, k) => {
        const tr = el('tr');
        if (k === 0) {
          const series = el('th', row.label, 0);
          series.setAttribute?.('scope', 'rowgroup');
          series.setAttribute?.('rowspan', String(row.fits.length));
          tr.append(series);
        }
        // Fit, a, b, χ²/ν, S, then (once) the windows, then the status.
        const [name, a, b, chi2, scale, status] = fit.cells;
        const fitName = el('th', name, 1);
        fitName.setAttribute?.('scope', 'row');
        tr.append(fitName, el('td', a, 2), el('td', b, 3), el('td', chi2, 4), el('td', scale, 5));
        if (k === 0) {
          const windows = el('td', row.windows, 6);
          windows.setAttribute?.('rowspan', String(row.fits.length));
          tr.append(windows);
        }
        tr.append(el('td', status, 7));
        body.append(tr);
      });
      table.append(body);
    }
    host.replaceChildren(table);
  }

  clear() {
    super.clear();
    this.tableHost?.replaceChildren();
  }
}
