/* The caption block drawn inside an exported figure.
 *
 * ## Why the figure carries its own disclosures
 *
 * The panel footnotes are not decoration. They carry the percentile-clipping
 * count, the staggered-lattice comb warning, the "provisional" density-axis
 * basis and the true peak of any clipped low-N curve - the disclosures
 * CLAUDE.md section 2 makes mandatory, each of which exists because the picture
 * alone would otherwise mislead. `main.js` already reasons this way about the
 * screen, putting the comb warning on the panel rather than in a banner
 * "because the panel is what gets screenshotted into a discussion".
 *
 * An export that cropped to the plot area would strip exactly those sentences
 * off exactly the artifact that ends up in print. So the live footnote text
 * travels inside the image, along with the selection it was measured on.
 *
 * ## Why it is drawn as chart graphics
 *
 * Compositing the caption after serialisation would need two implementations -
 * splicing <text> into the SVG and painting onto the canvas for the PNG - that
 * could drift apart. Drawing it as ECharts `graphic` text elements gives one
 * path for both, and the SVG renderer emits them as real <text>, which is what
 * the vector requirement is about.
 */

import { measureText, wrapText } from '../textfit.js';
import { THEME } from '../scale.js';

/** Gap between the plot area and the first caption line. */
const TOP_GAP = 10;
/** Left and right inset of the caption text. */
const SIDE_INSET = 4;

/**
 * Lay out a caption and report the height it needs.
 *
 * Returns `{ graphic, height }`. The caller reserves `height` at the foot of
 * the chart and passes `graphic` straight into the option, so the two can never
 * disagree about how much room the text takes.
 */
export function buildCaption({ title, provenance, footnote, table = [] }, width) {
  const bodyWidth = width - 2 * SIDE_INSET;
  const titlePx = THEME.fontName;
  const bodyPx = THEME.fontSmall;
  const lineHeight = 1.42 * bodyPx;

  const graphic = [];
  let y = TOP_GAP;

  const push = (text, { size, colour, weight = 'normal', family }) => {
    graphic.push({
      type: 'text',
      left: SIDE_INSET,
      top: y,
      silent: true,
      style: {
        text,
        fill: colour,
        fontSize: size,
        fontWeight: weight,
        fontFamily: family || THEME.fontFamily,
        lineHeight: 1.42 * size,
      },
    });
    y += 1.42 * size;
  };

  if (title) {
    for (const line of wrapText(title, bodyWidth, titlePx, THEME.fontFamily)) {
      push(line, { size: titlePx, colour: THEME.text, weight: 'bold' });
    }
    y += 2;
  }

  if (provenance) {
    for (const line of wrapText(provenance, bodyWidth, bodyPx, THEME.fontFamily)) {
      push(line, { size: bodyPx, colour: THEME.text });
    }
    y += 2;
  }

  /* The μ/σ table. CLAUDE.md section 5 requires the energy panel to embed its
   * fitted parameters, and on screen they live in an HTML table outside the
   * chart - which an image export would leave behind. Rendered as aligned
   * monospace rows so the columns line up without a grid to draw. */
  if (table.length) {
    const mono = THEME.fontMono;
    const monoPx = bodyPx * 0.95;
    for (const row of table) {
      push(row, { size: monoPx, colour: THEME.muted, family: mono });
    }
    y += 2;
  }

  if (footnote) {
    for (const line of wrapText(footnote, bodyWidth, bodyPx, THEME.fontFamily)) {
      push(line, { size: bodyPx, colour: THEME.muted });
    }
  }

  return { graphic, height: Math.ceil(y + lineHeight * 0.4) };
}

/**
 * One sentence naming the selection the figure was measured on.
 *
 * Only axes the user actually narrowed are named. An untouched axis spans the
 * whole dataset and says nothing, and printing three redundant full ranges
 * would bury the one bound that matters - the same reasoning `state.writeHash`
 * applies to keeping a shareable link short.
 */
export function describeSelection(state, experiment, selection) {
  const parts = [];
  if (experiment) {
    parts.push(`Experiment ${experiment.display_name || experiment.table_name}`);
  }

  const bound = (axis, label, unit, digits) => {
    if (!state.isTouched(axis)) return null;
    const lo = state.get(`${axis}_min`);
    const hi = state.get(`${axis}_max`);
    if (lo === null || hi === null) return null;
    return `${label} ${lo.toFixed(digits)}–${hi.toFixed(digits)} ${unit}`;
  };

  const filters = [
    bound('e1', 'E₁', 'GeV', 2),
    bound('e2', 'E₂', 'GeV', 2),
    bound('d', 'D', 'mm', 0),
  ].filter(Boolean);
  parts.push(filters.length
    ? `selection ${filters.join(', ')}`
    : 'full kinematic range');

  if (state.get('include_undefined_d')) parts.push('including events with undefined D');

  const display = state.get('display') === 'native'
    ? 'native detector lattice'
    : `continuous field, R = ${state.get('resolution')}`;
  parts.push(display);
  parts.push(state.get('channel') === 'density'
    ? 'summed deposited energy'
    : 'Grad-CAM attention');

  if (selection) {
    parts.push(`${plural(selection.n_events, 'event')}, `
      + `${plural(selection.n_hits, 'hit')}`);
  }
  return `${parts.join(' · ')}.`;
}

/** The displayed window, so a zoomed figure states the region it shows. */
export function describeView(view, colName, rowName) {
  if (!view) return '';
  return `View ${colName} ${Math.round(view.col[0])}–${Math.round(view.col[1])} mm, `
    + `${rowName} ${Math.round(view.row[0])}–${Math.round(view.row[1])} mm.`;
}

/**
 * The fitted parameters, as aligned monospace rows.
 *
 * Column widths are measured from the content rather than fixed, so a slice
 * label long enough to overflow pushes the numbers across instead of colliding
 * with them.
 */
export function fitTableRows(payload, shown, counts, maxWidth) {
  if (!shown.length) return [];
  const header = ['Slice', 'N', 'μ [GeV]', 'σ [GeV]', 'σ/μ', 'Estimator'];
  const body = shown.map((entry) => {
    const slice = (payload.slices || []).find((s) => s.index === entry.slice);
    const fit = entry.fit;
    return [
      `${slice ? slice.label : entry.slice} · ${entry.shower.toUpperCase()}`,
      String(counts[String(entry.slice)] ?? fit.n ?? '—'),
      num(fit.mu_core, fit.mu_error),
      num(fit.sigma_core, fit.sigma_error),
      fit.resolution_core == null ? '—' : `${(fit.resolution_core * 100).toFixed(1)}%`,
      estimator(fit),
    ];
  });

  const rows = [header, ...body];
  const widths = header.map((_, i) => Math.max(...rows.map((r) => r[i].length)));
  const monoPx = THEME.fontSmall * 0.95;

  const rendered = rows.map((r) => r
    .map((cell, i) => (i === 0 ? cell.padEnd(widths[i]) : cell.padStart(widths[i])))
    .join('  ')
    .trimEnd());

  // A table that does not fit is worse than no table: the columns would run off
  // the figure and the numbers are already reported in the caption's source
  // panel. Drop the estimator column first, then give up.
  if (measureText(rendered[0], monoPx, THEME.fontMono) > maxWidth) {
    const narrow = rows.map((r) => r.slice(0, 5));
    const w2 = narrow[0].map((_, i) => Math.max(...narrow.map((r) => r[i].length)));
    const retry = narrow.map((r) => r
      .map((cell, i) => (i === 0 ? cell.padEnd(w2[i]) : cell.padStart(w2[i])))
      .join('  ')
      .trimEnd());
    if (measureText(retry[0], monoPx, THEME.fontMono) > maxWidth) return [];
    return retry;
  }
  return rendered;
}

function num(value, error) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const base = value.toFixed(3);
  if (error === null || error === undefined || !Number.isFinite(error)) return base;
  return `${base}±${error.toFixed(3)}`;
}

function estimator(fit) {
  switch (fit.estimator) {
    case 'core_refit': return 'core refit';
    case 'moments': return 'moments';
    case 'moments_1dof': return 'moments 1dof';
    case 'mean_only': return 'mean only';
    case 'degenerate': return 'degenerate';
    default: return '—';
  }
}

function plural(value, noun) {
  if (!Number.isFinite(value)) return `— ${noun}s`;
  const n = Math.round(value);
  return `${n.toLocaleString()} ${noun}${n === 1 ? '' : 's'}`;
}
