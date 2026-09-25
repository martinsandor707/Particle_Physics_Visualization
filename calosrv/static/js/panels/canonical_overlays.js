/* Anchor and centroid marks of the canonical centre-of-separation frame.
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
 */

import { THEME } from '../scale.js';
import { customLine, symbolOf } from './marks.js';

/** Marker size of an anchor, before `THEME.markerScale`. */
const ANCHOR_SIZE = 13;
/** Marker size of a centroid, before `THEME.markerScale`. */
const CENTROID_SIZE = 7;
/** Opacity of the uncapped spread bar. */
const SPREAD_OPACITY = 0.3;

/** A filled plus, scaled by the symbol size. */
const PLUS = 'path://M2,0H4V2H6V4H4V6H2V4H0V2H2Z';

/** How each canonical centroid set is drawn. `open` means outline only. */
export const CANONICAL_CENTROID_STYLE = {
  truth_voxel: { symbol: 'circle', open: false, shape: 'filled dot' },
  pred_voxel: { symbol: 'circle', open: true, shape: 'open ring' },
  canonical_mean: { symbol: PLUS, open: false, shape: '+' },
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
  if (!Number.isFinite(value)) return '—';
  return value < 0 ? `−${Math.abs(value).toFixed(1)}` : value.toFixed(1);
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
 * The two canonical anchors, their spread bars and the separation rule.
 *
 * X′Y′: both anchors at (∓⟨D_entry⟩/2, 0), each with a horizontal spread bar,
 * and the dashed rule between them. X′Z′: both at z′ = 0 on the x′ axis, with
 * the bars vertical along x′. Y′Z′: both project onto the origin, so one merged
 * open circle stands for the two instead of a circle hiding a diamond.
 */
export function addCanonicalAnchors(series, anchors, frame, col, row) {
  if (!anchors) return;
  const depthPanel = col.name === 'z';

  if (depthPanel && row.name !== 'x' && anchors.a && anchors.b) {
    series.push({
      type: 'scatter',
      name: 'Anchors A and B',
      symbol: 'circle',
      symbolSize: ANCHOR_SIZE * THEME.markerScale,
      data: [[0.0, 0.0]],
      itemStyle: openStyle(THEME.text, 1.5 * THEME.lineAxis),
      z: 11,
      tooltip: {
        formatter: () =>
          'Canonical anchors — showers A and B<br/>'
          + 'both entry points lie on the shower plane y′ = 0; they are separated along x′, '
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
        width: 2.5 * THEME.lineAxis,
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
      symbolSize: ANCHOR_SIZE * THEME.markerScale,
      data: [place(anchor)],
      itemStyle: openStyle(colour, 1.5 * THEME.lineAxis),
      z: 11,
      // The spread is restated here: at a small ⟨D_entry⟩ spread the bar is
      // shorter than this outline's hover band (6.5 px radius plus the 2.5 px
      // stroke threshold) and its own tooltip is reachable only zoomed in.
      tooltip: {
        formatter: () =>
          `Canonical anchor — shower ${label}<br/>`
          + `back-projected entry point at ${shower === 'a' ? '−' : '+'}⟨D_entry⟩/2 = ${mm1(anchor.x)} mm`
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
 */
export function addCanonicalCentroids(series, centroids, col, row) {
  if (!centroids) return;
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
        symbolSize: CENTROID_SIZE * THEME.markerScale,
        data: [[cx, cy]],
        itemStyle: style.open
          ? openStyle(colour, 1.2 * THEME.lineAxis)
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
            + `${symbolOf(col)} = ${mm1(cx)} mm<br/>`
            + `${symbolOf(row)} = ${mm1(cy)} mm`,
        },
      });
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
    items.push(`${style.shape} = ${pair.label}`);
  }
  if (!items.length) return '';
  return `Centroids (magenta A, blue B): ${items.join('; ')}.`;
}
