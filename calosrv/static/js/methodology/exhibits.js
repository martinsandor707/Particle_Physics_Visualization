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
 */

import { PUOR_ANCHORS, SCREEN_CARD, contrast, lookupTable } from '../palette.js';
import { legibleRamp } from '../panels/chart_panel.js';
import { MINUS } from '../format.js';

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
export function rampsExhibit(id = 'fig-ramps') {
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
export function puorExhibit(id = 'fig-puor') {
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

const SUB = ['₀', '₁', '₂', '₃', '₄', '₅', '₆', '₇', '₈', '₉'];
const sub = (n) => String(n).split('').map((d) => SUB[Number(d)]).join('');

/**
 * A schematic of the D-frame's co-registration: two events in the absolute
 * frame, each with its entry points, their midpoint m and the A→B azimuth ψ;
 * then both after the motion (translate by −m, rotate by −ψ), superimposed
 * with A at −D_entry/2 and B at +D_entry/2. One scale on both axes of both
 * panels.
 */
export function se3Exhibit(id = 'fig-se3') {
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
    const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const psi = Math.atan2(b[1] - a[1], b[0] - a[0]);
    const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const k = sub(n);
    // Before: the event where it entered.
    nodes.push(segment(left, a, b, cls));
    const [mx, my] = toPx(left, m);
    nodes.push(s('line', { x1: round(mx), y1: round(my), x2: round(mx + 34), y2: round(my), class: `se3-ref ${cls}` }));
    const r = 22;
    const end = [mx + r * Math.cos(psi), my - r * Math.sin(psi)];
    nodes.push(s('path', {
      d: `M${round(mx + r)} ${round(my)} A${r} ${r} 0 ${psi > Math.PI ? 1 : 0} 0 ${round(end[0])} ${round(end[1])}`,
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

/** The builders, by the content's `exhibit` name. */
export const EXHIBITS = Object.freeze({ ramps: rampsExhibit, puor: puorExhibit, se3: se3Exhibit });
