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
 * settle says so in its tooltip, the table and the drawer. The quadrature fit
 * is never drawn; it is tabled.
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
 */

import { THEME, axisPadding, formatNumber, formatInt, typographic } from '../scale.js';
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
  return lines.join('<br/>');
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
 * The card's option. Pure: `opts` = {windows: 'anchors' | 'all', shower: 'a'
 * | 'b' | 'both', palette, card, tooltipPosition?}; `metrics` = {width, height}.
 */
export function resolutionScalingOption(payload, opts = {}, metrics = {}) {
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
 */
export function fitTableRows(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series)) return null;
  const mode = windowMode(opts?.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
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
        return { form, cells: [name, a, b, chi2Cell(fit), scaleCell(fit), statusCell(fit, mf, gates)].map(text) };
      }),
    };
  });
  return {
    mode,
    caption: typographic(`Fits through ${modeLabel(mode, gates)}; the quadrature form is tabled, not drawn. `
      + 'S = √(χ²/ν) scales a fit\'s standard errors where χ²/ν > 1 (PDG), and its band then takes Student\'s t of its ν; '
      + 'S = 1 where the windows\' own errors stand.'),
    columns: [...FIT_TABLE_COLUMNS],
    rows,
  };
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
    return { option: resolutionScalingOption(payload, opts, metrics) };
  }

  render(payload, opts = {}) {
    super.render(payload, opts);
    this.renderTable();
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
