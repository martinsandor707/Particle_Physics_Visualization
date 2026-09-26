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
 * ## Why it is laid out once, as chart graphics
 *
 * One layout serves both formats. The PNG draws the laid-out lines as ECharts
 * `graphic` text elements. The SVG cannot: zrender's SVG painter flattens the
 * display list, so `graphic` items never become a `<g>` a reader could
 * isolate, and the vector deliverable wants an addressable
 * `<g id="figure-disclosure">`. `captionToSvg` therefore turns the *same*
 * laid-out items into `<text>` elements from their own styles and positions,
 * so the two formats cannot drift: every x, y, size and colour in the SVG band
 * is the one the PNG painted.
 *
 * ## Two kinds of sentence
 *
 * `footnote` is the live prose the reader saw on the panel. `disclosure` is the
 * list `export/disclosure.js` derives from the payload's structured fields -
 * counts, windows, references - and it is printed first because it is the
 * part that will still be correct after the screen wording changes. A
 * disclosure sentence the footnote already contains verbatim is dropped.
 */

import { measureText, wrapText } from '../textfit.js';
import { THEME, typographic } from '../scale.js';

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
export function buildCaption({
  title, provenance, footnote, table = [], disclosure = [],
}, width) {
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

  /* Structured disclosures, one sentence per paragraph so a reader can find
   * the count or the window they are after without parsing a run-on block.
   * Same size and ink as the footnote: they are the same kind of statement. */
  const fresh = dedupeDisclosure(disclosure, footnote);
  if (fresh.length) {
    for (const sentence of fresh) {
      for (const line of wrapText(sentence, bodyWidth, bodyPx, THEME.fontFamily)) {
        push(line, { size: bodyPx, colour: THEME.muted });
      }
    }
    if (footnote) y += 2;
  }

  if (footnote) {
    for (const line of wrapText(footnote, bodyWidth, bodyPx, THEME.fontFamily)) {
      push(line, { size: bodyPx, colour: THEME.muted });
    }
  }

  return { graphic, height: Math.ceil(y + lineHeight * 0.4) };
}

/**
 * Disclosure sentences not already present verbatim in the live footnote.
 *
 * Compared on collapsed whitespace, because the footnote is `textContent`
 * joined from several DOM nodes and may carry line breaks the payload's
 * sentence does not.
 */
function dedupeDisclosure(disclosure, footnote) {
  const haystack = collapse(footnote);
  const seen = new Set();
  const out = [];
  for (const item of Array.isArray(disclosure) ? disclosure : []) {
    const sentence = collapse(item);
    if (!sentence || seen.has(sentence)) continue;
    if (haystack && haystack.includes(sentence)) continue;
    seen.add(sentence);
    out.push(sentence);
  }
  return out;
}

function collapse(text) {
  return String(text ?? '').replace(/\s+/g, ' ').trim();
}

/**
 * The caption band as an SVG fragment, built from the laid-out items.
 *
 * `graphic` is the array `buildCaption` returned, with `top` relative to the
 * band's own origin; `offsetY` is the plot height it sits below. zrender draws
 * text centred on its line box, so the baseline is placed with
 * `dominant-baseline="central"` at the line's vertical middle - `top` plus
 * 0.71 x the font size, which is where a 1.42 x line height puts its centre.
 *
 * Styles are read from each item, never from `THEME`: by the time this runs
 * the screen theme has been restored, and the print ink lives only in the
 * items the layout captured. Returns '' for an empty band.
 */
export function captionToSvg(graphic, offsetY) {
  const items = Array.isArray(graphic) ? graphic.filter((g) => g && g.type === 'text') : [];
  if (!items.length) return '';

  const base = Number.isFinite(offsetY) ? offsetY : 0;
  const texts = items.map((item) => {
    const style = item.style || {};
    const fontSize = Number.isFinite(style.fontSize) ? style.fontSize : 12;
    const x = Number.isFinite(item.left) ? item.left : 0;
    const y = base + (Number.isFinite(item.top) ? item.top : 0) + 0.71 * fontSize;
    const attrs = [
      `x="${fmt(x)}"`,
      `y="${fmt(y)}"`,
      'dominant-baseline="central"',
      `font-size="${fmt(fontSize)}"`,
    ];
    if (style.fontFamily) attrs.push(`font-family="${escapeXml(style.fontFamily)}"`);
    if (style.fontWeight) attrs.push(`font-weight="${escapeXml(style.fontWeight)}"`);
    if (style.fill) attrs.push(`fill="${escapeXml(style.fill)}"`);
    return `<text ${attrs.join(' ')}>${escapeXml(style.text)}</text>`;
  });

  return `<g id="figure-disclosure">${texts.join('')}</g>`;
}

function fmt(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function escapeXml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * One sentence naming the selection the figure was measured on.
 *
 * Only axes the user actually narrowed are named. An untouched axis spans the
 * whole dataset and says nothing, and printing three redundant full ranges
 * would bury the one bound that matters - the same reasoning `state.writeHash`
 * applies to keeping a shareable link short.
 *
 * `frame` is the payload's `frame` block, or null. In the canonical
 * centre-of-separation frame the display phrase names the accumulation grid
 * rather than the detector lattice - there is no lattice to be native to once
 * every event has been rotated - and the channel is a per-event average
 * density in arbitrary units, not a summed energy.
 *
 * `display` is the descriptor `displayOf` reads from the payload. The grid is
 * worded from it rather than from the controls, because the payload guard may
 * have lowered R below the slider, and a figure must name the bins it shows.
 * The controls are consulted only when no descriptor is given.
 *
 * `spatial: false` is for a figure with no spatial bins - the energy panel -
 * whose content depends on neither the frame, the grid, R, the kernel nor the
 * spatial channel: naming them would describe bins the figure does not show.
 */
/** How each co-registered frame is named in a figure caption. */
const FRAME_PHRASE = {
  canonical: 'canonical centre-of-separation frame',
  trans: 'translated frame (each shower at its own P₀, no rotation)',
  local: 'local shower-fixed frame (R(θ, φ))',
};

/** How each CAM channel is named in a figure caption. */
const CHANNEL_PHRASE = {
  gradcam: 'energy-weighted mean Grad-CAM attention',
  gradcam_energy: 'Σ E·Grad-CAM (a.u. of selection peak)',
  shapcam: 'energy-weighted mean Shap-CAM attribution (signed, −1…+1)',
  shapcam_energy: 'Σ E·Shap-CAM (signed log, a.u. of peak |v|)',
};

export function describeSelection(
  state, experiment, selection, frame = null, display = null, { spatial = true, meta = null } = {},
) {
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

  const kind = ['canonical', 'trans', 'local'].includes(frame?.kind) ? frame.kind : 'lab';
  const coregistered = kind !== 'lab';
  const mode = display?.mode ?? state.get('display');
  const r = Number.isFinite(display?.r) ? display.r : state.get('resolution');
  // What the figure holds, from its response's meta where it says: the
  // controls may have moved on while the chart still shows the last payload.
  const uiFrame = ['canonical', 'trans', 'local'].includes(meta?.frame) ? meta.frame
    : (meta?.coord_system ? 'lab' : state.get('frame'));
  const network = meta?.network?.frame
    ?? { lab: 'absolute', canonical: 'absolute', trans: 'trans', local: 'local' }[uiFrame]
    ?? 'absolute';
  if (!spatial) {
    // Only the network describes this figure: the energy panel is the
    // segmentation reconstruction of the selected frame.
    parts.push(`segmentation network, ${network} frame`);
  } else if (coregistered) {
    const name = FRAME_PHRASE[kind];
    const pitch = Number.isFinite(frame.pitch_mm) ? frame.pitch_mm : null;
    const kernel = display ? kernelPhrase(display) : null;
    if (mode === 'native') {
      const merged = display?.merge > 1 && Number.isFinite(display.displayPitch)
        ? `, merged ${display.merge}× to ${fmtMm(display.displayPitch)} mm`
        : '';
      parts.push(`${name}, raw ${pitch ?? 20} mm bins `
        + `(Native Grid, no reconstruction${merged})`);
    } else if (kernel) {
      const bins = Number.isFinite(display.displayPitch)
        ? `${fmtMm(display.displayPitch)} mm display bins` : 'display bins';
      parts.push(`${name}, ${kernel} on ${bins} (R = ${r})`);
    } else {
      // A payload that names no kernel: say what is known, nothing more.
      const grid = pitch !== null ? `${pitch} mm accumulation grid` : 'accumulation grid';
      parts.push(`${name}, ${grid}, Continuous Field at R = ${r}`);
    }
  } else {
    parts.push(mode === 'native'
      ? 'native detector lattice'
      : `continuous field, R = ${r}`);
  }

  const channel = meta?.channel ?? state.get('channel');
  if (!spatial) {
    // The channel colours the spatial panels only.
  } else if (channel && channel !== 'density') {
    const model = meta?.model ?? state.get('model') ?? 'segmentation';
    const count = (meta?.weighting ?? state.get('weighting')) === 'count';
    let phrase = CHANNEL_PHRASE[channel] ?? channel;
    if (count && (channel === 'gradcam' || channel === 'shapcam')) {
      phrase = phrase.replace('energy-weighted', 'count-weighted');
    }
    parts.push(`${model} network (${network}): ${phrase}`);
  } else {
    parts.push(coregistered ? 'average hit density (a.u.)' : 'summed deposited energy');
  }

  if (selection) {
    parts.push(`${plural(selection.n_events, 'event')}, `
      + `${plural(selection.n_hits, 'hit')}`);
  }
  return `${parts.join(' · ')}.`;
}

/**
 * What a displayed bin is, read from the payload rather than from the controls.
 *
 * `resolution` is the response's `meta.resolution` (retained by each panel as
 * `lastOpts.resolution`), `frame` its `frame` block, `panelPayload` the panel.
 * Returns `{mode, r, displayPitch, merge, kernel, sigma, canonical, coregistered,
 * kind}`; any
 * field the payload does not carry is null (merge 1), so callers can fall
 * back field by field. The kernel is 'none' for a raw-bin display.
 */
export function displayOf(resolution, frame = null, panelPayload = null) {
  const res = resolution || {};
  const kind = ['canonical', 'trans', 'local'].includes(frame?.kind) ? frame.kind : 'lab';
  const canonical = kind === 'canonical';
  const coregistered = kind !== 'lab';
  const recon = coregistered ? (frame.reconstruction ?? null) : null;
  const kernel = res.kernel?.type ?? recon?.kernel ?? panelPayload?.kernel ?? null;
  const sigma = res.kernel?.sigma_mm ?? recon?.sigma_mm ?? null;
  return {
    mode: res.mode ?? recon?.display ?? null,
    r: Number.isFinite(res.r_x) ? res.r_x : null,
    displayPitch: Number.isFinite(res.display_pitch_mm) ? res.display_pitch_mm : null,
    merge: Number.isFinite(res.merge) ? res.merge : 1,
    kernel,
    sigma: Number.isFinite(sigma) ? sigma : null,
    canonical,
    coregistered,
    kind,
  };
}

/**
 * The reconstruction kernel as a phrase, or null for a raw-bin display.
 *
 * Gaussian names its σ, since the width is what a reader needs to judge how
 * much the picture was smoothed; the tent's width is fixed by the grid.
 */
export function kernelPhrase(display) {
  switch (display?.kernel) {
    case 'gaussian':
      return Number.isFinite(display.sigma)
        ? `Gaussian kernel, σ = ${fmtMm(display.sigma)} mm`
        : 'Gaussian kernel';
    case 'bilinear': return 'bilinear (tent) kernel';
    case 'box': return 'box (area-weighted) kernel';
    default: return null;
  }
}

/** Millimetres to at most one decimal: 10 → "10", 4.4 → "4.4". */
function fmtMm(value) {
  return Number.isInteger(value) ? String(value) : Number(value).toFixed(1);
}

/** The displayed window, so a zoomed figure states the region it shows. */
export function describeView(view, colName, rowName) {
  if (!view) return '';
  const mm = (v) => typographic(String(Math.round(v)));
  return `View ${colName} ${mm(view.col[0])}–${mm(view.col[1])} mm, `
    + `${rowName} ${mm(view.row[0])}–${mm(view.row[1])} mm.`;
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
