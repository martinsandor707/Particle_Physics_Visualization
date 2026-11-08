/* Anchor and centroid marks of the co-registered frames.
 *
 * Written for the canonical centre-of-separation frame and shared by the
 * translated and local frames, whose centroid sets are drawn the same way;
 * the file keeps its name because tests pin it. The anchors are canonical
 * only. The per-shower frames add `frame_mean` - the mean per-event centroid
 * relative to each shower's own entry point - with its sample SD as a faint
 * uncapped cross and its Student-t 95% interval as capped whiskers.
 *
 * ## Why they are light
 *
 * Every event is co-registered so shower A enters at (−⟨D_entry⟩/2, 0) and B
 * at (+⟨D_entry⟩/2, 0): the anchors sit, by construction, on the two brightest
 * places in the picture. The previous marks - 15 px filled markers, a 6 px
 * spread bar and a floating ⟨D_entry⟩ badge - covered exactly the bins the
 * panel exists to show. So the anchors are open outlines at reduced opacity,
 * the spread bar is thin and faint, the separation is a 1 px dashed rule, and
 * the numbers the badge carried move into the rule's tooltip and the panel tag.
 *
 * ## What is kept, and why
 *
 * The spread bar stays. It is the sample dispersion of D_entry/2 across the
 * events, and CLAUDE.md section 2 requires dispersion to be encoded wherever an
 * aggregate is drawn; it is an uncapped bar because a capped whisker is
 * reserved for the uncertainty of the mean, and each says which in its tooltip.
 *
 * ## Centroid sets
 *
 * Three measured centroid sets can be drawn beside the anchors. On the lab
 * panel they are told apart by size, which at a 1:1 canonical crop makes the
 * largest a blob over the core. Here they are all small (7 px) and told apart
 * by *shape* - filled dot, open ring, plus - with the shower carried by colour.
 * `centroidLegend` names each set by the payload's own label, and the footnote
 * and the exported figure both use it, so the three never disagree.
 *
 * Open markers are `symbol: 'circle' | 'diamond'` with a transparent fill, not
 * ECharts' `emptyCircle` / `emptyDiamond`: those are filled white and forced to
 * a 2 px stroke whatever the item style says.
 *
 * ## Strips
 *
 * At 1:1 the entrance panel of a widely separated pair is a strip: where D
 * spans some six times the y′ window, the plot is a few dozen pixels tall and
 * the two anchors can sit within 40 px of each other. On the light screen its
 * marks are drawn small there (`stripMarks`), so the rings, centroids and bars
 * of the two showers never meet across that gap and the cores stay in view.
 *
 * ## Drawn bins beyond the window
 *
 * The D-frame's x′ window may be capped at the drawn field's connected extent
 * rather than its 0.1st–99.9th percentile half-width (the server's
 * `frame.fit.<panel>.<axis>.cap`). Drawn bins it leaves outside are a clipping,
 * and CLAUDE.md section 2 says to clip it and say so: `addWindowOverflow`
 * draws an out-of-bounds caret on the window edge they lie beyond, at their
 * energy-weighted position along the other axis, its tooltip naming how many,
 * where and what share of the panel's energy. It is a disclosure, not an
 * overlay: the Marks toggle leaves it, and the export draws it.
 */

import { THEME, floorLabel, formatInt } from '../scale.js';
import { customCaret, customLine, customWhisker, symbolOf } from './marks.js';
import { isPrintTheme, onLightCard } from './chart_panel.js';
import { formatSigned } from '../format.js';

/** Marker size of an anchor, before `THEME.markerScale`. */
const ANCHOR_SIZE = 13;
/** Marker size of a centroid, before `THEME.markerScale`. */
const CENTROID_SIZE = 7;
/** Opacity of the uncapped spread bar. */
const SPREAD_OPACITY = 0.3;

/** Plot height (px) below which a light-screen panel is a strip and draws `STRIP_MARKS`. */
export const STRIP_HEIGHT_PX = 70;

/**
 * The marks of a strip: an 8 px anchor ring, 6 px centroids, lines no wider
 * than 1.2 px and no outline wider than 1 px (Martin's directive of 2026-10-30).
 */
export const STRIP_MARKS = Object.freeze({ anchor: 8, centroid: 6, line: 1.2, border: 1 });

/**
 * `STRIP_MARKS` for a plot `plotHeight` px tall on the light screen, else
 * null: the dark card and print draw their marks at the sizes they always had.
 */
export function stripMarks(plotHeight) {
  if (!(plotHeight < STRIP_HEIGHT_PX) || isPrintTheme() || !onLightCard()) return null;
  return STRIP_MARKS;
}

/** A filled plus, scaled by the symbol size. */
const PLUS = 'path://M2,0H4V2H6V4H4V6H2V4H0V2H2Z';

/** How each canonical centroid set is drawn. `open` means outline only. */
export const CANONICAL_CENTROID_STYLE = {
  truth_voxel: { symbol: 'circle', open: false, shape: 'filled dot' },
  // The single-shower counterpart of truth_voxel: never together with it.
  energy_voxel: { symbol: 'circle', open: false, shape: 'filled dot' },
  pred_voxel: { symbol: 'circle', open: true, shape: 'open ring' },
  canonical_mean: { symbol: PLUS, open: false, shape: '+' },
  // Never together with canonical_mean: one is canonical, the other per-shower.
  frame_mean: { symbol: PLUS, open: false, shape: '+' },
};

const SHOWERS = [['a', 'A'], ['b', 'B']];

function showerColour(shower) {
  return shower === 'a' ? THEME.showerA : THEME.showerB;
}

/** An open outline in the given colour, at the anchor opacity. */
function openStyle(colour, width) {
  return {
    color: 'transparent',
    borderColor: colour,
    borderWidth: width,
    opacity: THEME.anchorOpacity,
  };
}

/** Millimetres to one decimal with a typographic minus. */
function mm1(value) {
  return formatSigned(value, 1);
}

/**
 * The mean entry separation as the rule's tooltip states it.
 *
 * The interval is named, because at N = 2 the Student-t 95% half-width is 12.7
 * standard errors and a bare "±" would mean whatever the reader assumes.
 */
export function entrySeparationText(frame) {
  const entry = frame?.d_entry ?? {};
  if (!Number.isFinite(entry.mean)) return null;
  const n = Number.isFinite(entry.n) ? entry.n : frame?.n_events;
  const mean = Math.round(entry.mean);
  if (n === 1) return `⟨D_entry⟩ = ${mean} mm (single event, no interval)`;
  if (Number.isFinite(entry.ci95_half)) {
    return `⟨D_entry⟩ = ${mean} ± ${Math.round(entry.ci95_half)} mm `
      + `(95% t-interval of the mean, N = ${n})`;
  }
  return `⟨D_entry⟩ = ${mean} mm (N = ${n ?? '—'})`;
}

/**
 * The two D-frame anchors, their spread bars and the separation rule.
 *
 * X′Y′: both anchors at (∓⟨D_entry⟩/2, 0), each with a horizontal spread bar,
 * and the dashed rule between them. X′Z′: both at z′ = 0 on the x′ axis, with
 * the bars vertical along x′. Y′Z′: both project onto the origin, so one merged
 * open circle stands for the two instead of a circle hiding a diamond.
 * `strip` (`stripMarks`) draws the rings and bars small on a strip.
 */
export function addCanonicalAnchors(series, anchors, frame, col, row, symbols = null, strip = null) {
  if (!anchors) return;
  const depthPanel = col.name === 'z';
  const ringSize = strip ? strip.anchor : ANCHOR_SIZE * THEME.markerScale;
  const ringWidth = strip ? strip.border : 1.5 * THEME.lineAxis;
  // The axis the anchors sit on, as the panel writes it: D on the entry
  // panel, x′ on the X′Z′ panel (axis_symbols.js).
  const axisName = symbols?.[depthPanel ? 'row' : 'col'] ?? 'x′';

  if (depthPanel && row.name !== 'x' && anchors.a && anchors.b) {
    series.push({
      type: 'scatter',
      name: 'Anchors A and B',
      symbol: 'circle',
      symbolSize: ringSize,
      data: [[0.0, 0.0]],
      itemStyle: openStyle(THEME.text, ringWidth),
      z: 11,
      tooltip: {
        formatter: () =>
          'D-frame anchors — showers A and B<br/>'
          + 'both entry points lie on the shower plane y′ = 0; they are separated along D (the x′ axis), '
          + `at ∓⟨D_entry⟩/2 = ∓${Math.abs(anchors.b.x).toFixed(1)} mm, which this panel projects out.`,
      },
    });
    return;
  }

  const place = (anchor) => (depthPanel ? [0.0, anchor.x] : [anchor.x, anchor.y]);
  const spreadEnds = (anchor) => {
    if (!Array.isArray(anchor.spread) || anchor.spread.length < 2) return null;
    if (!anchor.spread.every(Number.isFinite)) return null;
    return depthPanel
      ? [[0.0, anchor.spread[0]], [0.0, anchor.spread[1]]]
      : [[anchor.spread[0], anchor.y], [anchor.spread[1], anchor.y]];
  };

  for (const [shower, label] of SHOWERS) {
    const anchor = anchors[shower];
    if (!anchor || !Number.isFinite(anchor.x)) continue;
    const colour = showerColour(shower);

    const ends = spreadEnds(anchor);
    const sd = ends ? Math.abs(anchor.spread[1] - anchor.spread[0]) / 2 : null;
    if (ends) {
      series.push(customLine({
        name: `Anchor ${label} — spread`,
        from: ends[0],
        to: ends[1],
        color: colour,
        width: strip ? strip.line : 2.5 * THEME.lineAxis,
        opacity: SPREAD_OPACITY,
        z: 9,
        tooltip: `Anchor ${label} — ± ${sd.toFixed(1)} mm<br/>`
          + '± sample SD of D_entry/2 across events (dispersion, not the uncertainty of the mean)'
          + (anchor.dof_note ? `<br/><i>${anchor.dof_note}</i>` : ''),
      }));
    }

    series.push({
      type: 'scatter',
      name: `Anchor ${label}`,
      symbol: shower === 'a' ? 'diamond' : 'circle',
      symbolSize: ringSize,
      data: [place(anchor)],
      itemStyle: openStyle(colour, ringWidth),
      z: 11,
      // The spread is restated here: at a small ⟨D_entry⟩ spread the bar is
      // shorter than this outline's hover band (6.5 px radius plus the 2.5 px
      // stroke threshold) and its own tooltip is reachable only zoomed in.
      tooltip: {
        formatter: () =>
          `D-frame anchor — shower ${label}<br/>`
          + `back-projected entry point at ${axisName} = ${shower === 'a' ? '−' : '+'}⟨D_entry⟩/2 = ${mm1(anchor.x)} mm`
          + (Number.isFinite(anchor.se95)
            ? `<br/>95% interval of the mean anchor ± ${anchor.se95.toFixed(1)} mm (N = ${anchor.n})`
            : '')
          + (Number.isFinite(sd) && sd > 0
            ? `<br/>faint bar: ± ${sd.toFixed(1)} mm, the sample SD of D_entry/2 (dispersion)`
            : ''),
      },
    });
  }

  if (depthPanel || !anchors.a || !anchors.b) return;
  const entry = entrySeparationText(frame);
  const dataset = Number.isFinite(frame?.d_dataset?.mean)
    ? `⟨D⟩ = ${Math.round(frame.d_dataset.mean)} mm (dataset, 3-D centroid distance)`
    : null;
  series.push(customLine({
    name: 'Mean entry separation',
    from: [anchors.a.x, anchors.a.y],
    to: [anchors.b.x, anchors.b.y],
    color: THEME.separationRule,
    width: THEME.lineAxis,
    dash: 'dashed',
    z: 10,
    tooltip: ['Mean entry separation', entry, dataset].filter(Boolean).join('<br/>'),
  }));
}

/**
 * The measured centroid sets on the X′Y′ panel, told apart by shape.
 *
 * No separation vector: the anchors and their rule already state the
 * separation, and a second dashed line would sit on top of the first.
 * `strip` (`stripMarks`) draws them small on a strip.
 */
export function addCanonicalCentroids(series, centroids, col, row, symbols = null, strip = null) {
  if (!centroids) return;
  const colName = symbols?.col ?? symbolOf(col);
  const rowName = symbols?.row ?? symbolOf(row);
  for (const [key, style] of Object.entries(CANONICAL_CENTROID_STYLE)) {
    const pair = centroids[key];
    if (!pair || !pair.a) continue;
    for (const [shower, label] of SHOWERS) {
      const point = pair[shower];
      if (!point) continue;
      const cx = point[col.name];
      const cy = point[row.name];
      if (!Number.isFinite(cx) || !Number.isFinite(cy)) continue;
      const colour = showerColour(shower);
      series.push({
        type: 'scatter',
        name: `${pair.label} — ${label}`,
        symbol: style.symbol,
        symbolSize: strip ? strip.centroid : CENTROID_SIZE * THEME.markerScale,
        data: [[cx, cy]],
        itemStyle: style.open
          ? openStyle(colour, strip ? strip.border : 1.2 * THEME.lineAxis)
          : {
            color: colour,
            borderColor: THEME.canvas,
            borderWidth: 0.6 * THEME.lineAxis,
            opacity: THEME.anchorOpacity,
          },
        z: 10,
        tooltip: {
          formatter: () =>
            `${pair.label}<br/>Shower ${label} (${style.shape})<br/>`
            + `${colName} = ${mm1(cx)} mm<br/>`
            + `${rowName} = ${mm1(cy)} mm`
            + (key === 'frame_mean' && pair.n < 2 && pair.dof_note ? `<br/><i>${pair.dof_note}</i>` : '')
            + (Number.isFinite(pair.offset_mm)
              ? `<br/>A–B offset = ${mm1(pair.offset_mm)} mm (superimposed centroids, not a separation)`
              : ''),
        },
      });
    }
  }
}

/**
 * The ends of the `frame_mean` marks, clamped to the panel window.
 *
 * One entry per mark - a shower's SD bar or 95% interval along one axis - with
 * its true half-width and its ends clamped to `col`/`row`. An end that runs
 * past the window is flagged: the panel draws it on the edge with a caret and
 * the true interval in its tooltip, and the footnote counts it (CLAUDE.md
 * section 2: clip it and say so). Both read this one list, so the carets and
 * the count cannot disagree. Empty at N = 1, where neither quantity exists.
 */
export function frameMeanMarks(pair, col, row) {
  const marks = [];
  if (!pair || !(pair.n >= 2) || !col || !row) return marks;
  for (const [shower, label] of SHOWERS) {
    const point = pair[shower];
    const sd = pair.sd?.[shower];
    const ci = pair.ci95_half?.[shower];
    if (!point || !sd || !ci) continue;
    const cx = point[col.name];
    const cy = point[row.name];
    if (!Number.isFinite(cx) || !Number.isFinite(cy)) continue;
    for (const [axis, value, horizontal] of [[col.name, cx, true], [row.name, cy, false]]) {
      const bounds = horizontal ? col : row;
      // A mean outside its own window leaves nothing on the panel to attach to.
      if (!(value >= bounds.lo && value <= bounds.hi)) continue;
      for (const [quantity, half] of [['sd', sd[axis]], ['ci', ci[axis]]]) {
        if (!(Number.isFinite(half) && half > 0)) continue;
        marks.push({
          shower, label, quantity, horizontal, value, half, cx, cy,
          sym: symbolOf(bounds),
          lo: Math.max(value - half, bounds.lo),
          hi: Math.min(value + half, bounds.hi),
          clipLo: value - half < bounds.lo,
          clipHi: value + half > bounds.hi,
        });
      }
    }
  }
  return marks;
}

/** How many `frame_mean` mark ends run past the window and are clipped to it. */
export function frameMeanOverflow(pair, col, row) {
  return frameMeanMarks(pair, col, row)
    .reduce((n, mark) => n + (mark.clipLo ? 1 : 0) + (mark.clipHi ? 1 : 0), 0);
}

/**
 * The footnote sentence for clipped `frame_mean` ends on the XY panel, or ''.
 * Read from the same marks the panel draws, for the screen and the export.
 */
export function frameMeanOverflowText(payload) {
  const axes = payload?.panels?.xy?.axes;
  const n = frameMeanOverflow(payload?.centroids?.frame_mean, axes?.col, axes?.row);
  if (!n) return '';
  return `${n} end${n === 1 ? '' : 's'} of the mean-centroid SD and 95% interval marks `
    + `run${n === 1 ? 's' : ''} past the window and ${n === 1 ? 'is' : 'are'} clipped at its edge `
    + '(caret, no cap); the tooltip gives the full range.';
}

/**
 * The spread and uncertainty of `frame_mean`, per shower, on the XY panel.
 *
 * Two quantities, two marks (CLAUDE.md section 2): the sample SD of the
 * per-event centroid offsets as a faint uncapped cross - where the events
 * scatter - and the Student-t 95% interval of the mean as capped whiskers -
 * how well the mean is known. Nothing is drawn at N = 1, where neither exists.
 * An end clipped to the window loses its cap and gets a caret. `strip`
 * (`stripMarks`) draws the spread bar thin on a strip.
 */
export function addFrameMeanSpread(series, pair, col, row, strip = null) {
  for (const mark of frameMeanMarks(pair, col, row)) {
    const { shower, label, quantity, horizontal, value, half, cx, cy, sym } = mark;
    const colour = showerColour(shower);
    const at = (v) => (horizontal ? [v, cy] : [cx, v]);
    const clipped = mark.clipLo || mark.clipHi;
    const full = `${formatSigned(value - half, 1)} to ${formatSigned(value + half, 1)} mm`;
    const clipNote = clipped
      ? `<br/>clipped at the window edge: the full range is ${full}` : '';
    let text;
    if (quantity === 'sd') {
      text = `Mean centroid ${label} — ± ${half.toFixed(1)} mm in ${sym}<br/>`
        + '± sample SD of the per-event centroid offsets from P₀ (dispersion, not the '
        + `uncertainty of the mean)${clipNote}`;
      series.push(customLine({
        name: `Mean centroid ${label} — spread in ${sym}`,
        from: at(mark.lo),
        to: at(mark.hi),
        color: colour,
        width: strip ? strip.line : 2.5 * THEME.lineAxis,
        opacity: SPREAD_OPACITY,
        z: 8,
        tooltip: text,
      }));
    } else {
      text = `Mean centroid ${label} — ${formatSigned(value, 1)} ± ${half.toFixed(1)} mm in ${sym}<br/>`
        + `95% Student-t interval of the mean, N = ${pair.n}`
        + (pair.dof_note ? `<br/><i>${pair.dof_note}</i>` : '') + clipNote;
      series.push(customWhisker({
        name: `Mean centroid ${label} — 95% interval in ${sym}`,
        from: at(mark.lo),
        to: at(mark.hi),
        caps: [!mark.clipLo, !mark.clipHi],
        color: colour,
        width: THEME.lineAxis,
        z: 9,
        tooltip: text,
      }));
    }
    for (const [end, other, isClipped] of [[mark.lo, mark.hi, mark.clipLo], [mark.hi, mark.lo, mark.clipHi]]) {
      if (!isClipped) continue;
      series.push(customCaret({
        name: `Mean centroid ${label} — ${quantity === 'sd' ? 'spread' : '95% interval'} in ${sym} (clipped)`,
        from: at(other),
        to: at(end),
        color: colour,
        opacity: quantity === 'sd' ? Math.max(SPREAD_OPACITY, 0.6) : 1,
        z: 9,
        tooltip: text,
      }));
    }
  }
}

/**
 * One sentence naming the centroid sets drawn, by their payload labels.
 *
 * Only sets actually present are listed, so the legend never explains a mark
 * that is not on the panel. Returns '' when none is drawn.
 */
export function centroidLegend(centroids) {
  if (!centroids) return '';
  const items = [];
  for (const [key, style] of Object.entries(CANONICAL_CENTROID_STYLE)) {
    const pair = centroids[key];
    if (!pair || !pair.a || !pair.label) continue;
    let whiskers = '';
    if (key === 'frame_mean' && pair.n >= 2) {
      whiskers = ` (faint cross ± SD, capped whiskers 95% t-interval, N = ${pair.n})`;
    } else if (key === 'frame_mean' && pair.dof_note) {
      whiskers = ` (${pair.dof_note.replace(/\.$/, '')})`;
    }
    items.push(`${style.shape} = ${pair.label}${whiskers}`);
  }
  if (!items.length) return '';
  return `Centroids (magenta A, blue B): ${items.join('; ')}.`;
}

/* ------------------------------------------------ drawn bins beyond the window -- */

/** Caret length (px) of a window-overflow indicator, tip to base. */
export const OVERFLOW_CARET_PX = 9;

/** The series id of the window-overflow carets. */
export const OVERFLOW_ID = 'window-overflow';

/**
 * The clipped sides of a panel's capped window axes, from the response's
 * `frame.fit[panelId]`: one entry per side of an axis whose `cap.outside.sides`
 * is non-empty, `axisKey` 'col' or 'row' naming the payload axis the cap is on
 * (x′: the entry panel's columns, the X′Z′ panel's rows). Empty when nothing
 * is capped or nothing lies outside.
 */
export function windowOverflow(frame, panelId) {
  const fit = frame?.fit?.[panelId];
  const out = [];
  if (!fit) return out;
  for (const axisKey of ['col', 'row']) {
    const cap = fit[axisKey]?.cap;
    const sides = cap?.outside?.sides;
    if (!cap || cap.applied === false || !Array.isArray(sides)) continue;
    for (const side of sides) {
      if (!(side?.bins > 0) || !(side.side === 1 || side.side === -1)) continue;
      out.push({ axisKey, cap, ...side });
    }
  }
  return out;
}

/** A share of the panel's energy as a percentage with two significant figures. */
function sharePercent(fraction) {
  if (!Number.isFinite(fraction)) return '—';
  const percent = 100 * fraction;
  if (percent > 0 && percent < 0.001) return '< 0.001%';
  return `${Number(percent.toPrecision(2))}%`;
}

/** A millimetre range, with a typographic minus and "to" when either end is signed. */
function mmRange([lo, hi]) {
  if (!(Number.isFinite(lo) && Number.isFinite(hi))) return '—';
  return lo < 0 || hi < 0 ? `${formatInt(lo)} to ${formatInt(hi)} mm` : `${formatInt(lo)}–${formatInt(hi)} mm`;
}

/**
 * The tooltip of one clipped side: how many drawn bins lie beyond which edge,
 * where, what share of the panel's energy they hold, and why the window stops
 * there. `symbol` is the capped axis as the panel writes it (D on the entry
 * panel, x′ on X′Z′), `other` the other axis's, `edge` the window edge (mm).
 */
export function windowOverflowText(item, { symbol = 'x′', other = '', edge = null } = {}) {
  const { cap } = item;
  const n = item.bins;
  const bins = `${formatInt(n)} drawn bin${n === 1 ? '' : 's'}`;
  const floor = Number.isFinite(cap?.floor_ratio) ? ` (above ${floorLabel({ floor_ratio: cap.floor_ratio })} of ρ<sub>ref</sub>)` : '';
  const edgeText = Number.isFinite(edge) ? ` at ${symbol} = ${formatInt(edge)} mm` : '';
  const at = Number.isFinite(item.at) && other ? `; energy-weighted ${other} = ${formatSigned(item.at, 1)} mm` : '';
  const why = [];
  if (Number.isFinite(cap?.drawn_half_width)) why.push(`drawn field ± ${formatInt(cap.drawn_half_width)} mm`);
  if (Number.isFinite(cap?.percentile_half_width)) {
    why.push(`0.1st–99.9th percentile half-width ± ${formatInt(cap.percentile_half_width)} mm`);
  }
  return `Drawn bins beyond the window edge${edgeText}<br/>`
    + `${bins}${floor} ${n === 1 ? 'lies' : 'lie'} beyond the window at ${symbol} = ${mmRange(item.range)}, `
    + `holding ${sharePercent(item.energy_fraction)} of this panel’s energy${at}<br/>`
    + 'the window is capped at the drawn field’s connected extent'
    + (why.length ? ` (${why.join('; ')})` : '')
    + ': clipped and counted, see Details';
}

/**
 * Out-of-bounds carets for drawn bins a capped D-frame window leaves outside
 * (`windowOverflow`): on the window edge each side lies beyond, pointing out,
 * at the bins' energy-weighted position along the other axis. Placed in pixel
 * space at every render, so a zoom or a pan moves them: a caret whose window
 * edge is out of view is not drawn, and its cross position is kept inside the
 * plot. In the theme's warn ink (3:1 or more on both screen cards and on
 * paper). `extent` is the panel's {col, row} window in mm, `symbols` the axes
 * as the panel writes them.
 */
export function addWindowOverflow(series, frame, panelId, col, row, extent, symbols = null) {
  const sides = windowOverflow(frame, panelId);
  if (!sides.length || !extent) return;
  const names = { col: symbols?.col ?? symbolOf(col), row: symbols?.row ?? symbolOf(row) };
  const items = sides.map((item) => {
    const horizontal = item.axisKey === 'col';
    const range = extent[item.axisKey];
    const edge = item.side < 0 ? range[0] : range[1];
    const otherKey = horizontal ? 'row' : 'col';
    const otherRange = extent[otherKey];
    const cross = Number.isFinite(item.at) ? item.at : (otherRange[0] + otherRange[1]) / 2;
    return {
      horizontal,
      side: item.side,
      at: horizontal ? [edge, cross] : [cross, edge],
      tooltip: windowOverflowText(item, { symbol: names[item.axisKey], other: names[otherKey], edge }),
    };
  });
  const size = OVERFLOW_CARET_PX;
  const wing = 0.6 * size;
  series.push({
    type: 'custom',
    id: OVERFLOW_ID,
    name: 'Drawn bins beyond the window',
    clip: true,
    z: 13,
    silent: false,
    data: items.map((item, index) => [item.at[0], item.at[1], index]),
    renderItem: (params, api) => {
      const item = items[params.dataIndex];
      const box = params.coordSys;
      const p = api.coord(item.at);
      const clamp = (v, lo, hi) => (lo > hi ? (lo + hi) / 2 : Math.min(Math.max(v, lo), hi));
      let tip;
      let dir;
      if (item.horizontal) {
        // The window edge must be on show; a zoom that leaves it out hides the caret.
        if (!(p[0] >= box.x - 0.5 && p[0] <= box.x + box.width + 0.5)) return null;
        tip = [p[0], clamp(p[1], box.y + wing, box.y + box.height - wing)];
        dir = [item.side, 0];
      } else {
        if (!(p[1] >= box.y - 0.5 && p[1] <= box.y + box.height + 0.5)) return null;
        tip = [clamp(p[0], box.x + wing, box.x + box.width - wing), p[1]];
        // Screen y grows downward: the upper edge (+side) points up.
        dir = [0, -item.side];
      }
      const [ux, uy] = dir;
      const base = [tip[0] - ux * size, tip[1] - uy * size];
      return {
        type: 'polygon',
        shape: { points: [tip, [base[0] - uy * wing, base[1] + ux * wing], [base[0] + uy * wing, base[1] - ux * wing]] },
        style: { fill: THEME.warn, opacity: 1 },
      };
    },
    tooltip: { formatter: (p) => items[p?.dataIndex]?.tooltip ?? 'Drawn bins beyond the window' },
  });
}
