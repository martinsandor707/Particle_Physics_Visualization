/* The Methodology article's three computed figures, as pure SVG node trees.
 *
 * Each figure is drawn from the code it describes, never from typed values:
 * the ramps from palette.js's lookup tables, their legible spans from
 * chart_panel.js `legibleRamp` (the function the panels paint with), and every
 * contrast ratio from palette.js `contrast`. A change to a palette or to the
 * 3:1 rule redraws the figure, and the article's prose, which quotes the same
 * numbers through methodology/constants.js, is held to them by the tests.
 *
 * A builder returns `{tag, attrs, children}` nodes (text nodes are `{text}`),
 * which render.js mounts in the SVG namespace. Text in a figure is set in the
 * page's own fonts (methodology.css), and a negative number takes U+2212.
 *
 * The ramps and PuOr figures paint their own grounds - the card #1c2128 the
 * screen draws on, and white paper - because the contrast they show is against
 * that ground, so they read the same on screen and in print. The SE(3)
 * schematic has no ground of its own and takes its colours from the page's
 * stylesheet, which has a print variant.
 *
 * ## Two media
 *
 * Every builder takes `medium`. 'screen', the default, is the article's own
 * figure, above. 'paper' is the figure the Export button writes
 * (methodology/export.js): a self-contained SVG for a manuscript, which no
 * stylesheet will ever reach. So it carries every colour as an attribute and
 * one font family on its root, paints a white ground first, and paints no dark
 * one anywhere: the card the screen figures stand on becomes a white panel in a
 * thin grey frame, and the wording says the numbers are measured *against* the
 * screen card, which a key swatch shows. The ramps, swatches and gradient
 * strips are the data and keep their colours. It is drawn for the LaTeX text
 * width, `PAPER_WIDTH_MM`, and included there at 100%, so its type is set in
 * points through export/tokens.js: no text below `MIN_PT`, every text colour
 * at 4.5:1 or more on white. The paper builders share the screen builders'
 * computations (the legible spans, the contrasts, the co-registration), so the
 * two media can only differ in how they draw the same numbers;
 * tests/test_js_methodology_export.py holds them to that.
 */

import { PUOR_ANCHORS, SCREEN_CARD, contrast, lookupTable } from '../palette.js';
import { legibleRamp } from '../panels/chart_panel.js';
import { MINUS } from '../format.js';
import { MIN_PT, PRINT_INK, PRINT_TOKENS } from '../export/tokens.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const WHITE = [255, 255, 255];
const INK = '#111827';
const INK_MUTED = '#4b5563';
const TEXT = '#e6edf3';
const TEXT_MUTED = '#8b949e';
const CARD_HEX = hex(SCREEN_CARD);

/** The four sequential ramps the dashboard offers, in its order. */
export const RAMPS = Object.freeze([
  { palette: 'viridis', name: 'Viridis' },
  { palette: 'cividis', name: 'Cividis' },
  { palette: 'plasma', name: 'Plasma' },
  { palette: 'turbo', name: 'Turbo' },
]);

/** An SVG node. */
function s(tag, attrs = {}, ...children) {
  return { tag, attrs, children: children.flat().filter(Boolean) };
}

/** A text node for an SVG <text>, with every hyphen-minus before a digit set as U+2212. */
function label(x, y, text, attrs = {}) {
  return s('text', { x: round(x), y: round(y), ...attrs }, { text: signed(text) });
}

function signed(text) {
  return String(text).replace(/-(?=\d)/g, MINUS);
}

function round(value) {
  return Math.round(value * 100) / 100;
}

/** '#rrggbb' of an [r, g, b] triple. */
export function hex(rgb) {
  return `#${rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;
}

/** The colour at index `i` of a 256-entry table. */
function tableColour(table, i) {
  const k = Math.max(0, Math.min(255, Math.round(i)));
  return [table[k * 3], table[k * 3 + 1], table[k * 3 + 2]];
}

/** A contrast ratio as the figures print it: two decimals. */
export function ratioText(value) {
  return value.toFixed(2);
}

/**
 * A horizontal gradient drawing a table between fractions `from` and `to`:
 * one stop per table entry would be 256, so 65 evenly spaced stops are used,
 * well inside one colour step of the 8-bit table.
 */
function gradient(id, table, { from = 0, to = 1, stops = 65 } = {}) {
  const children = [];
  for (let k = 0; k < stops; k += 1) {
    const f = k / (stops - 1);
    const t = from + f * (to - from);
    children.push(s('stop', { offset: `${round(f * 100)}%`, 'stop-color': hex(tableColour(table, t * 255)) }));
  }
  return s('linearGradient', { id, x1: '0', y1: '0', x2: '1', y2: '0' }, children);
}

function svgRoot(id, width, height, title, children) {
  return s('svg', {
    xmlns: SVG_NS, viewBox: `0 0 ${width} ${height}`, width: '100%', role: 'img',
    'aria-labelledby': `${id}-title`, class: `exhibit-svg exhibit-${id.replace(/^fig-/, '')}`,
  }, s('title', { id: `${id}-title` }, { text: title }), children);
}

/* ------------------------------------------------------------- ramps -- */

/**
 * The four sequential ramps on the card, each marked at the first and last
 * colour that clears 3:1 against it (`legibleRamp`: the span the screen
 * paints), and the same ramps in full on white, as print draws them.
 */
export function rampsExhibit(id = 'fig-ramps', { medium = 'screen' } = {}) {
  if (medium === 'paper') return rampsPaper(id);
  const width = 640;
  const x0 = 104;
  const x1 = 612;
  const span = x1 - x0;
  const screenRow = 46;
  const printRow = 26;
  const top = 8;
  const screenTop = top + 22;
  const screenBottom = screenTop + RAMPS.length * screenRow + 6;
  const printTop = screenBottom + 30;
  const printBottom = printTop + RAMPS.length * printRow + 8;
  const height = printBottom + 30;
  const defs = [];
  const nodes = [];
  const markers = [];

  nodes.push(label(x0, top + 14, 'On screen: the card #1c2128. Brackets: the span painted, from the first to the last colour at ≥ 3:1.',
    { class: 'exhibit-caption-text', fill: 'currentColor', 'font-size': 11 }));
  nodes.push(s('rect', { x: 0, y: screenTop - 4, width, height: screenBottom - screenTop + 4, fill: CARD_HEX, rx: 4 }));
  RAMPS.forEach(({ palette, name }, i) => {
    const table = lookupTable(palette);
    const ramp = legibleRamp(palette);
    const y = screenTop + i * screenRow + 4;
    const gid = `${id}-screen-${palette}`;
    defs.push(gradient(gid, table));
    nodes.push(label(12, y + 12, name, { fill: TEXT, 'font-size': 12 }));
    nodes.push(s('rect', { x: x0, y, width: span, height: 16, fill: `url(#${gid})` }));
    const a = x0 + ramp.from * span;
    const b = x0 + ramp.to * span;
    const by = y + 22;
    const marker = s('g', {
      class: 'ramp-legible', 'data-palette': palette,
      'data-from': ramp.from.toFixed(3), 'data-to': ramp.to.toFixed(3),
    },
    s('line', { x1: round(a), y1: by, x2: round(b), y2: by, stroke: TEXT, 'stroke-width': 1.5 }),
    s('line', { x1: round(a), y1: y - 2, x2: round(a), y2: by, stroke: TEXT, 'stroke-width': 1.5 }),
    s('line', { x1: round(b), y1: y - 2, x2: round(b), y2: by, stroke: TEXT, 'stroke-width': 1.5 }),
    label(a + 3, by + 11, `from ${ramp.from.toFixed(3)}`, { fill: TEXT, 'font-size': 10.5 }),
    label(b - 3, by + 11, `to ${ramp.to.toFixed(3)}`, { fill: TEXT, 'font-size': 10.5, 'text-anchor': 'end' }));
    markers.push(marker);
  });
  nodes.push(...markers);

  nodes.push(label(x0, printTop - 10, 'In print: white paper, the full ramp from 0 to 1.',
    { class: 'exhibit-caption-text', fill: 'currentColor', 'font-size': 11 }));
  nodes.push(s('rect', { x: 0, y: printTop - 4, width, height: printBottom - printTop + 4, fill: '#ffffff', rx: 4,
    stroke: '#30363d', 'stroke-width': 0.5 }));
  RAMPS.forEach(({ palette, name }, i) => {
    const y = printTop + i * printRow + 4;
    const gid = `${id}-print-${palette}`;
    defs.push(gradient(gid, lookupTable(palette)));
    nodes.push(label(12, y + 12, name, { fill: INK, 'font-size': 12 }));
    nodes.push(s('rect', { x: x0, y, width: span, height: 16, fill: `url(#${gid})` }));
  });
  // The ramp's own axis, once, under the print block.
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    const x = x0 + t * span;
    nodes.push(s('line', { x1: round(x), y1: printBottom + 2, x2: round(x), y2: printBottom + 6, stroke: 'currentColor', 'stroke-width': 1 }));
    nodes.push(label(x, printBottom + 18, t.toFixed(2), {
      fill: 'currentColor', 'font-size': 10.5, 'text-anchor': t === 0 ? 'start' : (t === 1 ? 'end' : 'middle'),
    }));
  }
  nodes.push(label(12, printBottom + 18, 'position t', { fill: 'currentColor', 'font-size': 10.5, class: 'exhibit-muted' }));

  return svgRoot(id, width, height,
    'Viridis, Cividis, Plasma and Turbo on the card with the span of colours at 3:1 or more marked, and in full on white.',
    [s('defs', {}, defs), ...nodes]);
}

/* -------------------------------------------------------------- puor -- */

/** The first table index, walking out from zero along one arm, whose colour clears `floor` against the card. */
function firstLegible(table, arm, floor = 3) {
  const indices = arm === 'neg' ? [...Array(128).keys()].map((k) => 127 - k) : [...Array(128).keys()].map((k) => 128 + k);
  return indices.find((i) => contrast(tableColour(table, i), SCREEN_CARD) >= floor) ?? null;
}

/**
 * The standard 11-class PuOr (the print ramp) with each anchor's WCAG
 * contrast against the card #1c2128 and against white, and the folded screen
 * ramp on the card with the first 3:1 colour of each arm marked.
 */
export function puorExhibit(id = 'fig-puor', { medium = 'screen' } = {}) {
  if (medium === 'paper') return puorPaper(id);
  const width = 640;
  const x0 = 104;
  const cell = 46;
  const sw = 42;
  const top = 8;
  const nodes = [];
  const defs = [];
  const bands = [
    { key: 'card', ground: CARD_HEX, rgb: SCREEN_CARD, ink: TEXT, muted: TEXT_MUTED, name: 'on #1c2128' },
    { key: 'white', ground: '#ffffff', rgb: WHITE, ink: INK, muted: INK_MUTED, name: 'on #FFFFFF' },
  ];
  nodes.push(label(x0, top + 14, 'Print: ColorBrewer PuOr, 11 classes, most negative first, with each class’s contrast against the ground.',
    { class: 'exhibit-caption-text', fill: 'currentColor', 'font-size': 11 }));
  let y = top + 26;
  const swatches = [];
  for (const band of bands) {
    nodes.push(s('rect', { x: 0, y, width, height: 58, fill: band.ground, rx: 4, stroke: '#30363d', 'stroke-width': 0.5 }));
    nodes.push(label(12, y + 20, band.name, { fill: band.ink, 'font-size': 11.5 }));
    nodes.push(label(12, y + 44, 'contrast', { fill: band.muted, 'font-size': 10.5 }));
    PUOR_ANCHORS.forEach((rgb, i) => {
      const x = x0 + i * cell;
      const ratio = contrast(rgb, band.rgb);
      const legible = ratio >= 3;
      swatches.push(s('g', {
        class: 'puor-anchor', 'data-ground': band.key, 'data-hex': hex(rgb), 'data-index': i,
        'data-contrast': ratioText(ratio),
      },
      s('title', {}, { text: `${hex(rgb)}: ${ratioText(ratio)}:1 against ${band.name.slice(3)}` }),
      s('rect', { x, y: y + 8, width: sw, height: 20, fill: hex(rgb) }),
      label(x + sw / 2, y + 44, ratioText(ratio), {
        fill: legible ? band.ink : band.muted, 'font-size': 10.5, 'text-anchor': 'middle',
        'font-weight': legible ? 600 : 400,
      })));
    });
    y += 64;
  }
  nodes.push(...swatches);
  nodes.push(label(x0, y + 12, 'Bold: at least 3:1. Classes −5 … +5 from the most negative (orange) to the most positive (purple).',
    { fill: 'currentColor', 'font-size': 10.5, class: 'exhibit-muted' }));

  // The folded screen ramp.
  y += 34;
  nodes.push(label(x0, y, 'Screen: PuOr folded on the card (signed log), brightness rising with |value|, hue giving the sign.',
    { class: 'exhibit-caption-text', fill: 'currentColor', 'font-size': 11 }));
  y += 8;
  const table = lookupTable('puor_screen');
  const span = cell * 11 - (cell - sw);
  const gid = `${id}-screen`;
  defs.push(gradient(gid, table));
  nodes.push(s('rect', { x: 0, y, width, height: 72, fill: CARD_HEX, rx: 4 }));
  nodes.push(label(12, y + 22, 'folded', { fill: TEXT, 'font-size': 11.5 }));
  nodes.push(s('rect', { x: x0, y: y + 10, width: span, height: 20, fill: `url(#${gid})` }));
  const ends = [[0, '−peak', 'start'], [0.5, '0', 'middle'], [1, '+peak', 'end']];
  for (const [t, text, anchor] of ends) {
    nodes.push(label(x0 + t * span, y + 64, text, { fill: TEXT_MUTED, 'font-size': 10.5, 'text-anchor': anchor }));
  }
  for (const arm of ['neg', 'pos']) {
    const i = firstLegible(table, arm);
    if (i === null) continue;
    const rgb = tableColour(table, i);
    const x = x0 + (i / 255) * span;
    nodes.push(s('g', { class: 'puor-first-legible', 'data-arm': arm, 'data-index': i,
      'data-contrast': ratioText(contrast(rgb, SCREEN_CARD)) },
    s('line', { x1: round(x), y1: y + 6, x2: round(x), y2: y + 36, stroke: TEXT, 'stroke-width': 1.5 }),
    label(x + (arm === 'neg' ? -4 : 4), y + 48, `${ratioText(contrast(rgb, SCREEN_CARD))}:1 from here`, {
      fill: TEXT, 'font-size': 10.5, 'text-anchor': arm === 'neg' ? 'end' : 'start',
    })));
  }
  const height = y + 80;
  return svgRoot(id, width, height,
    'The 11 classes of ColorBrewer PuOr with their contrast against the card and against white, and the folded screen ramp.',
    [s('defs', {}, defs), ...nodes]);
}

/* --------------------------------------------------------------- se3 -- */

/** The two schematic events: entry points of A and B, in millimetres. Illustrative, not measured. */
export const SE3_EVENTS = Object.freeze([
  { n: 1, a: [-190, 20], b: [-60, 110], cls: 'is-first' },
  { n: 2, a: [150, -140], b: [40, 60], cls: 'is-second' },
]);

/** One event's motion: the midpoint m of its entry points, the A→B azimuth ψ and the separation D_entry. */
export function motionOf({ a, b }) {
  return {
    m: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
    psi: Math.atan2(b[1] - a[1], b[0] - a[0]),
    d: Math.hypot(b[0] - a[0], b[1] - a[1]),
  };
}

const SUB = ['₀', '₁', '₂', '₃', '₄', '₅', '₆', '₇', '₈', '₉'];
const sub = (n) => String(n).split('').map((d) => SUB[Number(d)]).join('');

/**
 * A schematic of the D-frame's co-registration: two events in the absolute
 * frame, each with its entry points, their midpoint m and the A→B azimuth ψ;
 * then both after the motion (translate by −m, rotate by −ψ), superimposed
 * with A at −D_entry/2 and B at +D_entry/2. One scale on both axes of both
 * panels.
 */
export function se3Exhibit(id = 'fig-se3', { medium = 'screen' } = {}) {
  if (medium === 'paper') return se3Paper(id);
  const scale = 0.6;               // px per mm, on both axes of both panels
  const half = [220, 170];         // the world box, ± mm
  const pw = 2 * half[0] * scale;
  const ph = 2 * half[1] * scale;
  const top = 28;
  const panels = [{ x: 16, title: 'Absolute frame (x, y)', axes: ['x', 'y'] },
    { x: 16 + pw + 76, title: 'D-frame (x′, y′)', axes: ['x′', 'y′'] }];
  const width = panels[1].x + pw + 16;
  const height = top + ph + 46;
  const nodes = [];
  const toPx = (panel, [x, y]) => [panel.x + (x + half[0]) * scale, top + (half[1] - y) * scale];

  for (const panel of panels) {
    const [cx, cy] = toPx(panel, [0, 0]);
    nodes.push(label(panel.x, top - 12, panel.title, { class: 'se3-title', 'font-size': 12 }));
    nodes.push(s('rect', { x: panel.x, y: top, width: round(pw), height: round(ph), class: 'se3-frame' }));
    nodes.push(s('line', { x1: panel.x, y1: round(cy), x2: round(panel.x + pw), y2: round(cy), class: 'se3-axis' }));
    nodes.push(s('line', { x1: round(cx), y1: top, x2: round(cx), y2: round(top + ph), class: 'se3-axis' }));
    nodes.push(label(panel.x + pw - 4, cy - 5, panel.axes[0], { class: 'se3-muted', 'font-size': 11, 'text-anchor': 'end' }));
    nodes.push(label(cx + 5, top + 12, panel.axes[1], { class: 'se3-muted', 'font-size': 11 }));
  }

  const point = (panel, p, shower, text, dx = 7, dy = -7) => {
    const [x, y] = toPx(panel, p);
    const shape = shower === 'a'
      ? s('path', { d: `M${round(x)} ${round(y - 6)} L${round(x + 6)} ${round(y)} L${round(x)} ${round(y + 6)} L${round(x - 6)} ${round(y)} Z`, class: 'se3-a' })
      : s('circle', { cx: round(x), cy: round(y), r: 5, class: 'se3-b' });
    return [shape, label(x + dx, y + dy, text, { class: 'se3-label', 'font-size': 11, 'text-anchor': dx < 0 ? 'end' : 'start' })];
  };
  const segment = (panel, p, q, cls) => {
    const [x1, y1] = toPx(panel, p);
    const [x2, y2] = toPx(panel, q);
    return s('line', { x1: round(x1), y1: round(y1), x2: round(x2), y2: round(y2), class: `se3-line ${cls}` });
  };

  const [left, right] = panels;
  for (const event of SE3_EVENTS) {
    const { a, b, n, cls } = event;
    const { m, psi, d } = motionOf(event);
    const k = sub(n);
    // Before: the event where it entered.
    nodes.push(segment(left, a, b, cls));
    const [mx, my] = toPx(left, m);
    nodes.push(s('line', { x1: round(mx), y1: round(my), x2: round(mx + 34), y2: round(my), class: `se3-ref ${cls}` }));
    const r = 22;
    const end = [mx + r * Math.cos(psi), my - r * Math.sin(psi)];
    nodes.push(s('path', {
      // Screen y points down: a positive ψ turns anticlockwise on screen (sweep 0), a negative one
      // clockwise (sweep 1); atan2 never exceeds π, so the arc is never the large one.
      d: `M${round(mx + r)} ${round(my)} A${r} ${r} 0 0 ${psi < 0 ? 1 : 0} ${round(end[0])} ${round(end[1])}`,
      class: `se3-arc ${cls}`,
    }));
    const mid = psi / 2;
    nodes.push(label(mx + (r + 12) * Math.cos(mid), my - (r + 12) * Math.sin(mid) + 4, `ψ${k}`, { class: 'se3-label', 'font-size': 11, 'text-anchor': 'middle' }));
    nodes.push(s('rect', { x: round(mx - 3), y: round(my - 3), width: 6, height: 6, class: 'se3-m' }));
    nodes.push(label(mx - 6, my + 14, `m${k}`, { class: 'se3-label', 'font-size': 11, 'text-anchor': 'end' }));
    nodes.push(...point(left, a, 'a', `A${k}`, -8, -8), ...point(left, b, 'b', `B${k}`, 8, -8));
    // After: A at −D/2, B at +D/2 on the x′ axis.
    const lift = n === 1 ? 14 : -14;
    nodes.push(segment(right, [-d / 2, 0], [d / 2, 0], cls));
    nodes.push(...point(right, [-d / 2, 0], 'a', `A${k}`, -4, lift < 0 ? 18 : -9),
      ...point(right, [d / 2, 0], 'b', `B${k}`, 4, lift < 0 ? 18 : -9));
    const [, ty] = toPx(right, [0, 0]);
    const [ax] = toPx(right, [-d / 2, 0]);
    const [bx] = toPx(right, [d / 2, 0]);
    nodes.push(label(ax, ty + (n === 1 ? -26 : 34), `−D${k}/2`, { class: 'se3-muted', 'font-size': 10.5, 'text-anchor': 'middle' }));
    nodes.push(label(bx, ty + (n === 1 ? -26 : 34), `+D${k}/2`, { class: 'se3-muted', 'font-size': 10.5, 'text-anchor': 'middle' }));
  }
  const [ox, oy] = toPx(right, [0, 0]);
  nodes.push(s('rect', { x: round(ox - 3), y: round(oy - 3), width: 6, height: 6, class: 'se3-m' }));

  // The motion between the panels.
  const ay = top + ph / 2;
  const ax0 = left.x + pw + 10;
  const ax1 = right.x - 10;
  nodes.push(s('line', { x1: round(ax0), y1: round(ay), x2: round(ax1), y2: round(ay), class: 'se3-motion' }));
  nodes.push(s('path', { d: `M${round(ax1)} ${round(ay)} l-8 -4 l0 8 Z`, class: 'se3-motion-head' }));
  nodes.push(label((ax0 + ax1) / 2, ay - 22, 'translate', { class: 'se3-label', 'font-size': 10.5, 'text-anchor': 'middle' }));
  nodes.push(label((ax0 + ax1) / 2, ay - 9, 'by −m, rotate', { class: 'se3-label', 'font-size': 10.5, 'text-anchor': 'middle' }));
  nodes.push(label((ax0 + ax1) / 2, ay + 18, 'by −ψ', { class: 'se3-label', 'font-size': 10.5, 'text-anchor': 'middle' }));

  nodes.push(label(16, top + ph + 20, 'Schematic, not measured data: two events, one scale on both axes of both panels.',
    { class: 'se3-muted', 'font-size': 10.5 }));
  nodes.push(label(16, top + ph + 36, '◆ shower A, ● shower B, □ the midpoint m; event 1 solid, event 2 dashed.',
    { class: 'se3-muted', 'font-size': 10.5 }));
  return svgRoot(id, width, height,
    'Schematic of the D-frame co-registration: two events before and after the SE(3) motion.', nodes);
}

/* ------------------------------------------------------------- paper -- */

/** The LaTeX text width (a4paper, 25 mm margins): the paper figures are drawn for it and included at 100%. */
export const PAPER_WIDTH_MM = 160;

/** Every paper figure's viewBox is this wide, so one unit is a quarter millimetre on the page. */
const PAPER_UNITS = 640;
const UNITS_PER_MM = PAPER_UNITS / PAPER_WIDTH_MM;
/** The smallest type a paper figure may set: `MIN_PT` at 100%, in viewBox units (12.7). */
export const PAPER_MIN_FONT = MIN_PT * (25.4 / 72) * UNITS_PER_MM;
/* The two type sizes, a little above the floor so rounding never takes one below it. */
const SMALL = 13;
const NAME = 14;

/* Ink on white: export/tokens.js's print text and muted ink (17.7:1 and 10.3:1).
 * The SE(3) schematic takes the article's print palette (methodology.css
 * `@media print`), so a printed page and its exported figure agree. */
const PAPER = Object.freeze({
  ground: '#ffffff',
  ink: PRINT_INK.text,
  muted: PRINT_INK.muted,
  frame: '#9ca3af',
  schematicMuted: '#4b5563',
  showerA: '#a3175f',
  showerB: '#1d4ed8',
});

/*
 * Advance widths of Arial (and its metric twin Liberation Sans, which
 * Chromium substitutes for it on Linux), in ems, enough to wrap a caption
 * line before it is drawn. A 6% margin covers DejaVu Sans, the stack's last
 * resort, whose glyphs are wider; the browser test measures what is drawn.
 */
const NARROW = new Set([...' il.,:;|!\'’‘()[]/']);
const SEMI = new Set([...'fjtrI-−']);
const WIDE = new Set([...'mwMW@%']);
function charWidth(ch) {
  if (NARROW.has(ch)) return 0.27;
  if (SEMI.has(ch)) return 0.33;
  if (WIDE.has(ch)) return 0.86;
  if (/[0-9]/.test(ch)) return 0.556;
  if (/[A-Z]/.test(ch)) return 0.68;
  if (/[a-z]/.test(ch)) return 0.53;
  return 0.6;
}

/** The estimated drawn width of `text` at `size`, in viewBox units. */
export function textWidth(text, size, { bold = false } = {}) {
  let ems = 0;
  for (const ch of signed(text)) ems += charWidth(ch);
  return ems * size * 1.06 * (bold ? 1.07 : 1);
}

/** `text` broken at spaces into lines no wider than `width` at `size`. */
function wrap(text, width, size, options = {}) {
  const lines = [];
  let line = '';
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word;
    if (line && textWidth(next, size, options) > width) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** A paper text: explicit ink and size, nothing left to a stylesheet. */
function ink(x, y, text, { size = SMALL, fill = PAPER.ink, bold = false, anchor = null, ...rest } = {}) {
  return label(x, y, text, {
    fill, 'font-size': size, ...(bold ? { 'font-weight': 700 } : {}), ...(anchor ? { 'text-anchor': anchor } : {}), ...rest,
  });
}

/** A wrapped paragraph from (x, y), the first baseline; returns its nodes and the next free y. */
function paragraph(x, y, text, width, { size = SMALL, lead = 1.3, ...options } = {}) {
  const lines = wrap(text, width, size, options);
  const nodes = lines.map((line, i) => ink(x, y + i * size * lead, line, { size, ...options }));
  return { nodes, next: y + (lines.length - 1) * size * lead + size * 0.45 };
}

/** The white panel that replaces the screen card on paper: a thin grey frame, no fill of its own. */
function panel(x, y, width, height) {
  return s('rect', { x: round(x), y: round(y), width: round(width), height: round(height), fill: PAPER.ground,
    stroke: PAPER.frame, 'stroke-width': 1 });
}

/** The key that shows the screen card's colour: a swatch of the data the ratios are measured against. */
function cardKey(x, y, text) {
  return [
    s('rect', { x: round(x), y: round(y - 11), width: 26, height: 14, fill: CARD_HEX, 'data-key': 'screen-card' }),
    ink(x + 32, y, text),
  ];
}

function paperRoot(id, height, title, children) {
  const h = round(height);
  return s('svg', {
    xmlns: SVG_NS, viewBox: `0 0 ${PAPER_UNITS} ${h}`,
    width: `${PAPER_WIDTH_MM}mm`, height: `${round(h / UNITS_PER_MM)}mm`,
    role: 'img', 'aria-labelledby': `${id}-title`, 'font-family': PRINT_TOKENS.fontFamily,
    'data-medium': 'paper',
  },
  s('title', { id: `${id}-title` }, { text: title }),
  s('rect', { x: 0, y: 0, width: PAPER_UNITS, height: h, fill: PAPER.ground, 'data-ground': 'paper' }),
  children);
}

/**
 * Figure 1 on paper. The screen half keeps its numbers - each ramp's span at
 * 3:1 or more against the screen card, from `legibleRamp` - but stands in a
 * white panel, with the card shown as a key swatch and the wording "against
 * the screen card"; the print half is the full ramp on white, as before.
 */
function rampsPaper(id) {
  const x0 = 104;
  const x1 = PAPER_UNITS - 16;
  const span = x1 - x0;
  const textWidthMax = PAPER_UNITS - 24;
  const defs = [];
  const nodes = [];

  let y = 18;
  const head = paragraph(12, y, 'On screen: each ramp is painted only over its bracketed span, from the first to the '
    + 'last colour at ≥ 3:1 against the screen card, the dark ground of the dashboard’s panels.', textWidthMax);
  nodes.push(...head.nodes);
  y = head.next + 20;
  nodes.push(...cardKey(12, y, 'the screen card #1c2128, against which the 3:1 spans are measured'));
  y += 14;

  const screenRow = 50;
  const screenTop = y;
  nodes.push(panel(0.5, screenTop, PAPER_UNITS - 1, RAMPS.length * screenRow + 10));
  const markers = [];
  RAMPS.forEach(({ palette, name }, i) => {
    const table = lookupTable(palette);
    const ramp = legibleRamp(palette);
    const top = screenTop + 10 + i * screenRow;
    const gid = `${id}-screen-${palette}`;
    defs.push(gradient(gid, table));
    nodes.push(ink(12, top + 13, name, { size: NAME }));
    nodes.push(s('rect', { x: x0, y: top, width: span, height: 18, fill: `url(#${gid})` }));
    const a = x0 + ramp.from * span;
    const b = x0 + ramp.to * span;
    const by = top + 24;
    markers.push(s('g', {
      class: 'ramp-legible', 'data-palette': palette,
      'data-from': ramp.from.toFixed(3), 'data-to': ramp.to.toFixed(3),
    },
    s('line', { x1: round(a), y1: by, x2: round(b), y2: by, stroke: PAPER.ink, 'stroke-width': 1.5 }),
    s('line', { x1: round(a), y1: top - 2, x2: round(a), y2: by, stroke: PAPER.ink, 'stroke-width': 1.5 }),
    s('line', { x1: round(b), y1: top - 2, x2: round(b), y2: by, stroke: PAPER.ink, 'stroke-width': 1.5 }),
    ink(a + 3, by + 14, `from ${ramp.from.toFixed(3)}`),
    ink(b - 3, by + 14, `to ${ramp.to.toFixed(3)}`, { anchor: 'end' })));
  });
  nodes.push(...markers);
  y = screenTop + RAMPS.length * screenRow + 10;

  y += 26;
  nodes.push(ink(12, y, 'In print: white paper, the full ramp from 0 to 1.'));
  y += 10;
  const printRow = 28;
  const printTop = y;
  const printBottom = printTop + RAMPS.length * printRow + 8;
  nodes.push(panel(0.5, printTop, PAPER_UNITS - 1, printBottom - printTop));
  RAMPS.forEach(({ palette, name }, i) => {
    const top = printTop + 8 + i * printRow;
    const gid = `${id}-print-${palette}`;
    defs.push(gradient(gid, lookupTable(palette)));
    nodes.push(ink(12, top + 13, name, { size: NAME }));
    nodes.push(s('rect', { x: x0, y: top, width: span, height: 18, fill: `url(#${gid})` }));
  });
  // The ramp's own axis, once, under the print block.
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    const x = x0 + t * span;
    nodes.push(s('line', { x1: round(x), y1: printBottom + 2, x2: round(x), y2: printBottom + 7, stroke: PAPER.ink, 'stroke-width': 1 }));
    nodes.push(ink(x, printBottom + 22, t.toFixed(2), { anchor: t === 0 ? 'start' : (t === 1 ? 'end' : 'middle') }));
  }
  nodes.push(ink(12, printBottom + 22, 'position t', { fill: PAPER.muted }));

  return paperRoot(id, printBottom + 32,
    'Viridis, Cividis, Plasma and Turbo with the span of colours at 3:1 or more against the screen card marked, and in full on white.',
    [s('defs', {}, defs), ...nodes]);
}

/**
 * Figure 2 on paper. Both rows of contrasts keep their numbers; the card row
 * stands in a white panel headed "against the screen card #1c2128", beside
 * its key swatch. The folded strip keeps its dark centre: that is the screen
 * ramp, not a ground.
 */
function puorPaper(id) {
  const x0 = 104;
  const cell = 46;
  const sw = 42;
  const textWidthMax = PAPER_UNITS - 24;
  const nodes = [];
  const defs = [];
  const bands = [
    { key: 'card', rgb: SCREEN_CARD, name: 'Against the screen card #1c2128 (the swatch on the right)', swatch: true },
    { key: 'white', rgb: WHITE, name: 'Against white paper #FFFFFF', swatch: false },
  ];

  let y = 18;
  const head = paragraph(12, y, 'Print: ColorBrewer PuOr, 11 classes, most negative first, with each class’s WCAG '
    + 'contrast against two grounds.', textWidthMax);
  nodes.push(...head.nodes);
  y = head.next + 12;

  const swatches = [];
  const bandHeight = 80;
  for (const band of bands) {
    nodes.push(panel(0.5, y, PAPER_UNITS - 1, bandHeight));
    nodes.push(ink(12, y + 19, band.name, { size: NAME }));
    if (band.swatch) {
      nodes.push(s('rect', { x: PAPER_UNITS - 12 - 26, y: y + 7, width: 26, height: 14, fill: CARD_HEX, 'data-key': 'screen-card' }));
    }
    nodes.push(ink(12, y + 69, 'contrast', { fill: PAPER.muted }));
    PUOR_ANCHORS.forEach((rgb, i) => {
      const x = x0 + i * cell;
      const ratio = contrast(rgb, band.rgb);
      const legible = ratio >= 3;
      swatches.push(s('g', {
        class: 'puor-anchor', 'data-ground': band.key, 'data-hex': hex(rgb), 'data-index': i,
        'data-contrast': ratioText(ratio),
      },
      s('title', {}, { text: `${hex(rgb)}: ${ratioText(ratio)}:1 against ${band.key === 'card' ? 'the screen card #1c2128' : 'white #FFFFFF'}` }),
      s('rect', { x, y: y + 30, width: sw, height: 22, fill: hex(rgb) }),
      ink(x + sw / 2, y + 69, ratioText(ratio), {
        fill: legible ? PAPER.ink : PAPER.muted, anchor: 'middle', bold: legible,
      })));
    });
    y += bandHeight + 8;
  }
  nodes.push(...swatches);
  const legend = paragraph(12, y + 12, 'Bold: at least 3:1. Classes −5 … +5 run from the most negative (orange) to the '
    + 'most positive (purple).', textWidthMax, { fill: PAPER.muted });
  nodes.push(...legend.nodes);
  y = legend.next + 26;

  // The folded screen ramp.
  const fold = paragraph(12, y, 'Screen: PuOr folded for the screen card (signed log), brightness rising with |value|, '
    + 'hue giving the sign. Marked: the first colour of each arm at ≥ 3:1 against the screen card.', textWidthMax);
  nodes.push(...fold.nodes);
  y = fold.next + 10;
  const table = lookupTable('puor_screen');
  const span = cell * 11 - (cell - sw);
  const gid = `${id}-screen`;
  defs.push(gradient(gid, table));
  nodes.push(panel(0.5, y, PAPER_UNITS - 1, 84));
  nodes.push(ink(12, y + 27, 'folded', { size: NAME }));
  nodes.push(s('rect', { x: x0, y: y + 12, width: span, height: 22, fill: `url(#${gid})` }));
  const ends = [[0, '−peak', 'start'], [0.5, '0', 'middle'], [1, '+peak', 'end']];
  for (const [t, text, anchor] of ends) {
    nodes.push(ink(x0 + t * span, y + 74, text, { fill: PAPER.muted, anchor }));
  }
  for (const arm of ['neg', 'pos']) {
    const i = firstLegible(table, arm);
    if (i === null) continue;
    const rgb = tableColour(table, i);
    const x = x0 + (i / 255) * span;
    nodes.push(s('g', { class: 'puor-first-legible', 'data-arm': arm, 'data-index': i,
      'data-contrast': ratioText(contrast(rgb, SCREEN_CARD)) },
    s('line', { x1: round(x), y1: y + 7, x2: round(x), y2: y + 40, stroke: PAPER.ink, 'stroke-width': 1.5 }),
    ink(x + (arm === 'neg' ? -4 : 4), y + 54, `${ratioText(contrast(rgb, SCREEN_CARD))}:1 from here`, {
      anchor: arm === 'neg' ? 'end' : 'start',
    })));
  }
  return paperRoot(id, y + 92,
    'The 11 classes of ColorBrewer PuOr with their contrast against the screen card and against white, and the folded screen ramp.',
    [s('defs', {}, defs), ...nodes]);
}

/**
 * Figure 3 on paper: the same two events and the same motion, at one scale
 * on both axes of both panels, in the article's print palette, with the
 * motion's words on four short lines and a legend of the drawn marks
 * themselves (the screen figure names them with glyphs).
 */
function se3Paper(id) {
  const half = [220, 170];
  const margin = 16;
  const gap = 98;
  const pw = (PAPER_UNITS - 2 * margin - gap) / 2;
  const scale = pw / (2 * half[0]);
  const ph = 2 * half[1] * scale;
  const top = 34;
  const panels = [{ x: margin, title: 'Absolute frame (x, y)', axes: ['x', 'y'] },
    { x: margin + pw + gap, title: 'D-frame (x′, y′)', axes: ['x′', 'y′'] }];
  const nodes = [];
  const toPx = (p, [x, y]) => [p.x + (x + half[0]) * scale, top + (half[1] - y) * scale];
  const muted = PAPER.schematicMuted;

  for (const p of panels) {
    const [cx, cy] = toPx(p, [0, 0]);
    nodes.push(ink(p.x, top - 12, p.title, { size: NAME, bold: true }));
    nodes.push(s('rect', { x: round(p.x), y: top, width: round(pw), height: round(ph), fill: 'none', stroke: PAPER.frame,
      'stroke-width': 1, 'data-mark': 'frame' }));
    nodes.push(s('line', { x1: round(p.x), y1: round(cy), x2: round(p.x + pw), y2: round(cy), stroke: PAPER.frame, 'stroke-width': 1 }));
    nodes.push(s('line', { x1: round(cx), y1: top, x2: round(cx), y2: round(top + ph), stroke: PAPER.frame, 'stroke-width': 1 }));
    nodes.push(ink(p.x + pw - 4, cy - 6, p.axes[0], { fill: muted, anchor: 'end' }));
    nodes.push(ink(cx + 5, top + 15, p.axes[1], { fill: muted }));
  }

  const diamond = (x, y, r = 6) => `M${round(x)} ${round(y - r)} L${round(x + r)} ${round(y)} L${round(x)} ${round(y + r)} L${round(x - r)} ${round(y)} Z`;
  const dash = (n) => (n === 2 ? { 'stroke-dasharray': '5 4' } : {});
  const mark = (x, y, shower, event, frame) => (shower === 'a'
    ? s('path', { d: diamond(x, y), fill: PAPER.showerA, 'data-mark': 'a', 'data-event': event, 'data-frame': frame })
    : s('circle', { cx: round(x), cy: round(y), r: 5, fill: PAPER.showerB, 'data-mark': 'b', 'data-event': event, 'data-frame': frame }));
  const point = (p, xy, shower, text, n, frame, dx, dy, anchor = dx < 0 ? 'end' : 'start') => {
    const [x, y] = toPx(p, xy);
    return [mark(x, y, shower, n, frame), ink(x + dx, y + dy, text, { anchor })];
  };
  /* A label's offset, centred `r` units from its mark, in screen units (y down): `beside` the A→B
   * line on its right (side 1) or its left (side −1), `beyond` B along it. A takes the right, B
   * the far end and the midpoint the left: all three clear of the line and of the ψ arc, which
   * turns from the +x reference towards ψ on the line's right. */
  const beside = (psi, side, r = 17) => [side * r * Math.sin(psi), side * r * Math.cos(psi) + 5];
  const beyond = (psi, r = 17) => [r * Math.cos(psi), -r * Math.sin(psi) + 5];
  const segment = (p, q, r, n) => {
    const [x1, y1] = toPx(p, q);
    const [x2, y2] = toPx(p, r);
    return s('line', { x1: round(x1), y1: round(y1), x2: round(x2), y2: round(y2), stroke: PAPER.ink, 'stroke-width': 1.5, ...dash(n) });
  };
  const square = (x, y) => s('rect', { x: round(x - 3.5), y: round(y - 3.5), width: 7, height: 7, fill: PAPER.ground,
    stroke: PAPER.ink, 'stroke-width': 1.2, 'data-mark': 'm' });

  const [left, right] = panels;
  for (const event of SE3_EVENTS) {
    const { a, b, n } = event;
    const { m, psi, d } = motionOf(event);
    const k = sub(n);
    // Before: the event where it entered.
    nodes.push(segment(left, a, b, n));
    const [mx, my] = toPx(left, m);
    nodes.push(s('line', { x1: round(mx), y1: round(my), x2: round(mx + 34), y2: round(my), stroke: muted, 'stroke-width': 1,
      'stroke-dasharray': '2 3' }));
    const r = 22;
    const end = [mx + r * Math.cos(psi), my - r * Math.sin(psi)];
    nodes.push(s('path', {
      d: `M${round(mx + r)} ${round(my)} A${r} ${r} 0 0 ${psi < 0 ? 1 : 0} ${round(end[0])} ${round(end[1])}`,
      fill: 'none', stroke: muted, 'stroke-width': 1.2, ...dash(n),
    }));
    const mid = psi / 2;
    nodes.push(ink(mx + (r + 13) * Math.cos(mid), my - (r + 13) * Math.sin(mid) + 5, `ψ${k}`, { anchor: 'middle' }));
    nodes.push(square(mx, my));
    const [lx, ly] = beside(psi, -1);
    nodes.push(ink(mx + lx, my + ly, `m${k}`, { anchor: 'middle' }));
    const [px, py] = beside(psi, 1);
    const [qx, qy] = beyond(psi);
    nodes.push(...point(left, a, 'a', `A${k}`, n, 'absolute', px, py, 'middle'),
      ...point(left, b, 'b', `B${k}`, n, 'absolute', qx, qy, 'middle'));
    // After: A at −D/2, B at +D/2 on the x′ axis.
    nodes.push(segment(right, [-d / 2, 0], [d / 2, 0], n));
    const below = n !== 1;
    nodes.push(...point(right, [-d / 2, 0], 'a', `A${k}`, n, 'dframe', -4, below ? 20 : -10),
      ...point(right, [d / 2, 0], 'b', `B${k}`, n, 'dframe', 4, below ? 20 : -10));
    const [, ty] = toPx(right, [0, 0]);
    const [ax] = toPx(right, [-d / 2, 0]);
    const [bx] = toPx(right, [d / 2, 0]);
    nodes.push(ink(ax, ty + (below ? 38 : -28), `−D${k}/2`, { fill: muted, anchor: 'middle' }));
    nodes.push(ink(bx, ty + (below ? 38 : -28), `+D${k}/2`, { fill: muted, anchor: 'middle' }));
  }
  const [ox, oy] = toPx(right, [0, 0]);
  nodes.push(square(ox, oy));

  // The motion between the panels, in four short lines.
  const ay = top + ph / 2;
  const ax0 = left.x + pw + 8;
  const ax1 = right.x - 8;
  const cx = (ax0 + ax1) / 2;
  nodes.push(s('line', { x1: round(ax0), y1: round(ay), x2: round(ax1 - 6), y2: round(ay), stroke: muted, 'stroke-width': 1.5 }));
  nodes.push(s('path', { d: `M${round(ax1)} ${round(ay)} l-9 -4.5 l0 9 Z`, fill: muted }));
  nodes.push(ink(cx, ay - 26, 'translate', { anchor: 'middle' }), ink(cx, ay - 9, 'by −m,', { anchor: 'middle' }));
  nodes.push(ink(cx, ay + 21, 'rotate', { anchor: 'middle' }), ink(cx, ay + 38, 'by −ψ', { anchor: 'middle' }));

  // The legend: the marks themselves.
  let ly = top + ph + 26;
  let lx = margin;
  const item = (draw, text) => {
    nodes.push(draw(lx, ly - 4.5), ink(lx + 26, ly, text, { fill: muted }));
    lx += 26 + textWidth(text, SMALL) + 22;
  };
  item((x, y) => s('path', { d: diamond(x + 10, y), fill: PAPER.showerA }), 'shower A');
  item((x, y) => s('circle', { cx: x + 10, cy: round(y), r: 5, fill: PAPER.showerB }), 'shower B');
  item((x, y) => s('rect', { x: x + 6.5, y: round(y - 3.5), width: 7, height: 7, fill: PAPER.ground, stroke: PAPER.ink, 'stroke-width': 1.2 }), 'midpoint m');
  item((x, y) => s('line', { x1: x, y1: round(y), x2: x + 20, y2: round(y), stroke: PAPER.ink, 'stroke-width': 1.5 }), 'event 1');
  item((x, y) => s('line', { x1: x, y1: round(y), x2: x + 20, y2: round(y), stroke: PAPER.ink, 'stroke-width': 1.5, 'stroke-dasharray': '5 4' }), 'event 2');
  ly += 20;
  nodes.push(ink(margin, ly, 'Schematic, not measured data: two events, one scale on both axes of both panels.', { fill: muted }));

  return paperRoot(id, ly + 10,
    'Schematic of the D-frame co-registration: two events before and after the SE(3) motion.', nodes);
}

/** The builders, by the content's `exhibit` name. */
export const EXHIBITS = Object.freeze({ ramps: rampsExhibit, puor: puorExhibit, se3: se3Exhibit });
