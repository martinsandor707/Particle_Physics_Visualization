/* E4: the depth-3 surrogate tree of the shipped booster.
 *
 * `/api/xgboost?view=surrogate&task=momentum|angle` fits, as the notebook
 * does, `DecisionTreeRegressor(max_depth=3, random_state=42)` to the shipped
 * booster's own predictions on every row, and ships sklearn's `tree_` as at
 * most 15 nodes: the split feature, its frame and threshold, the rows that
 * reach the node, and per output the mean of the booster's predictions over
 * them and their SD (the within-node spread). The fidelity R² and MAE say how
 * much of the booster three levels of rules describe.
 *
 * ## A description, not an estimate
 *
 * Every number on a node describes the booster's predictions on the rows that
 * reach it; nothing is inferred about a population, so no node carries a
 * whisker. The spread is printed as "value ± SD" and named the within-node SD
 * in the tooltip. The fidelity is stated on the card (screen) and in the
 * drawer: a tree of R² 0.24 is a sketch of the booster, not the booster.
 *
 * For the angle task the two outputs share the tree; `opts.label` (φ or θ)
 * chooses which output the nodes print and are coloured by - a repaint, not a
 * new request - and the tooltip carries both. A φ node value is sklearn's
 * linear mean of predicted azimuths, which is not a direction (CLAUDE.md
 * section 2: never average a circular quantity). It is kept for notebook
 * parity, printed with the node's mean resultant length R̄ where the payload
 * gives one, never coloured (`labelColoured`), and every φ tooltip says so.
 *
 * ## Colour
 *
 * The node value is coloured on the user's sequential ramp (Viridis by
 * default), narrowed to the run that clears 3:1 against the card in force
 * (`legibleRamp`: Viridis from 0.376 on #1c2128, up to 0.600 on white), over
 * the server's colour domain for the output. Leaves - the rules' outcomes -
 * are filled; an internal node is outlined in its colour. A leaf's text takes
 * whichever ink contrasts more with its fill. A small ramp names the scale.
 * An output that is not coloured (φ) draws every box on the card, leaves
 * outlined in text ink, and the header says why in place of the ramp.
 *
 * ## Two layouts
 *
 * Top-down (root at the top, ≤ to the left, > to the right) when every box's
 * text fits its share of the width; otherwise an indented outline, one node
 * per row in depth-first order with elbow connectors, whose rows wrap to the
 * width. A single-column export (321 px) is always the outline, which
 * `exportMetrics` sizes to its rows, so the tree stays legible at 9 pt.
 */

import { THEME, axisPadding, formatInt, formatPercent } from '../scale.js';
import { SEQUENTIAL_PALETTES } from '../palette.js';
import { measureText, wrapText } from '../textfit.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, mutedLine, escapeHtml, emptyChartOption, fitName,
  sigFigs, isPrintTheme, inkOn, legibleRamp, rampColour,
} from './chart_panel.js';

export const NODE_NAME = 'Surrogate tree nodes';
export const EDGE_NAME = 'Surrogate tree branches';

/** The frame a split feature is computed in, as a node names it. */
export const FRAME_WORDS = Object.freeze({
  absolute: 'absolute frame',
  trans: 'per-shower translated',
  local: 'local frame',
  none: 'no frame',
});

const LABEL_WORDS = Object.freeze({ momentum: 'momentum p', phi: 'azimuth φ', theta: 'polar angle θ' });

/* ---------------------------------------------------------------- model -- */

/** The output the card draws: `wanted` when the tree has it, else its first. */
export function treeLabel(payload, wanted) {
  const labels = payload?.labels ?? [];
  return labels.includes(wanted) ? wanted : (labels[0] ?? null);
}

/**
 * Whether the nodes are coloured by `label`. An azimuth is not: its node
 * values are linear means kept for notebook parity, and a sequential ramp
 * over them would order directions that wrap. The payload's own instruction
 * wins where it gives one (`color.<label>.coloured`, `colour.<label>`,
 * `color_by.<label>`); a label without a colour domain is never coloured.
 */
export function labelColoured(payload, label) {
  const said = [
    payload?.color?.[label]?.coloured, payload?.color?.[label]?.colored, payload?.colour?.[label]?.coloured,
    payload?.colour?.[label], payload?.color_by?.[label],
  ].find((v) => typeof v === 'boolean');
  if (typeof said === 'boolean') return said;
  const domain = payload?.color_domain?.[label];
  if (!Array.isArray(domain) || !domain.every(Number.isFinite)) return false;
  return label !== 'phi';
}

/** The palette the nodes are coloured on: the user's sequential ramp, else Viridis. */
export function treePalette(palette) {
  return SEQUENTIAL_PALETTES.includes(palette) ? palette : 'viridis';
}

/**
 * The tree, decided once. Pure: `{task, label, labels, unit, domain, ramp,
 * root, nodes: [{id, depth, leaf, feature, frame, threshold, n, share, value,
 * sd, values, sds, impurity, left, right, parent, branch, path, colour}],
 * maxDepth, fidelity: {r2, mae, unit}, nRows}`. Null without nodes.
 */
export function treeModel(payload, opts = {}) {
  const raw = payload?.nodes;
  if (!Array.isArray(raw) || !raw.length) return null;
  const label = treeLabel(payload, opts.label);
  const unit = payload.units?.[label] ?? payload.run?.label_units?.[label] ?? '';
  const byId = new Map(raw.map((n) => [n.id, n]));
  const root = raw.find((n) => n.depth === 0) ?? raw[0];
  const values = raw.map((n) => n.values?.[label]).filter(Number.isFinite);
  const coloured = labelColoured(payload, label);
  const domain = Array.isArray(payload.color_domain?.[label]) && payload.color_domain[label].every(Number.isFinite)
    ? payload.color_domain[label]
    : [Math.min(...values), Math.max(...values)];
  const ramp = legibleRamp(treePalette(opts.palette));
  const span = domain[1] - domain[0];
  const fraction = (v) => (span > 0 ? (v - domain[0]) / span : 0.5);
  const nRows = payload.tree?.n_rows ?? root.n;
  const nodes = new Map();
  const visit = (id, parent, branch, path) => {
    const n = byId.get(id);
    if (!n || nodes.has(id)) return;
    const value = n.values?.[label] ?? null;
    const node = {
      id: n.id,
      depth: n.depth,
      leaf: Boolean(n.leaf) || (n.left === null && n.right === null),
      feature: n.feature,
      frame: n.frame,
      threshold: n.threshold,
      n: n.n,
      share: nRows > 0 ? n.n / nRows : null,
      value,
      sd: n.sd?.[label] ?? null,
      values: n.values ?? {},
      sds: n.sd ?? {},
      circular: n.circular ?? {},
      resultant: n.circular?.[label]?.resultant ?? null,
      impurity: n.impurity,
      left: n.left,
      right: n.right,
      parent,
      branch,
      path,
      colour: coloured && Number.isFinite(value) ? rampColour(ramp, fraction(value)) : null,
    };
    nodes.set(id, node);
    if (!node.leaf) {
      const rule = ruleText(node);
      visit(n.left, id, '≤', [...path, { text: rule, branch: 'true' }]);
      visit(n.right, id, '>', [...path, { text: rule, branch: 'false' }]);
    }
  };
  visit(root.id, null, null, []);
  const list = [...nodes.values()];
  const fid = payload.fidelity ?? {};
  const own = fid.outputs?.[label] ?? null;
  return {
    task: payload.task,
    label,
    labels: payload.labels ?? [label],
    unit,
    units: payload.units ?? payload.run?.label_units ?? {},
    coloured,
    domain,
    ramp,
    root: root.id,
    nodes: list,
    byId: nodes,
    maxDepth: Math.max(...list.map((n) => n.depth)),
    fidelity: { r2: own?.r2 ?? fid.r2 ?? null, mae: own?.mae ?? fid.mae ?? null, unit: own ? unit : (fid.unit ?? unit), overall: fid },
    nRows,
  };
}

/** "feature ≤ threshold" of a split node. */
export function ruleText(node) {
  return `${node.feature} ≤ ${sigFigs(node.threshold, 4)}`;
}

/** "value ± SD" of a node, without the unit (the ramp's title carries it). */
export function valueText(node) {
  const r = Number.isFinite(node.resultant) ? ` · R̄ ${sigFigs(node.resultant, 2)}` : '';
  return `${sigFigs(node.value, 3)} ± ${sigFigs(node.sd, 3)}${r}`;
}

/** The lines a node's box prints. */
export function nodeLines(node) {
  if (node.leaf) return [`n = ${formatInt(node.n)}`, valueText(node)];
  return [ruleText(node), `${FRAME_WORDS[node.frame] ?? 'no frame'} · n = ${formatInt(node.n)}`, valueText(node)];
}

/* --------------------------------------------------------------- layout -- */

/** Leaf slots in order: each node's centre in slot units (in-order, parents over their children). */
function slotPositions(model) {
  const pos = new Map();
  const span = new Map();
  let next = 0;
  const place = (id) => {
    const node = model.byId.get(id);
    if (!node) return null;
    if (node.leaf) {
      pos.set(id, next + 0.5);
      span.set(id, [next, next + 1]);
      next += 1;
      return pos.get(id);
    }
    const a = place(node.left);
    const b = place(node.right);
    pos.set(id, ((a ?? b) + (b ?? a)) / 2);
    span.set(id, [span.get(node.left)?.[0] ?? 0, span.get(node.right)?.[1] ?? next]);
    return pos.get(id);
  };
  place(model.root);
  return { pos, span, leaves: next };
}

/** The header block's height: the screen subtitle and the colour ramp. */
function headerHeight(width) {
  const f = THEME.fontLabel;
  const rows = width < 560 ? 2 : 1;
  return (isPrintTheme() ? 1 : rows) * 2.2 * f + 2.4 * f;
}

/**
 * The top-down layout at `width` × `height`, or null when a box's text does
 * not fit its share of the width (or the levels do not fit the height).
 * `height` null sizes it from the font.
 */
export function topDownLayout(model, width, height = null) {
  const f = THEME.fontLabel;
  const side = axisPadding().right;
  const top = headerHeight(width);
  const { pos, span, leaves } = slotPositions(model);
  const slotW = (width - 2 * side) / Math.max(1, leaves);
  const lineH = 1.3 * f;
  const padX = 0.5 * f;
  const padY = 0.4 * f;
  const boxes = new Map();
  let tallest = 0;
  for (const node of model.nodes) {
    const [a, b] = span.get(node.id) ?? [0, 1];
    const avail = (b - a) * slotW - 0.6 * f;
    const need = Math.max(...nodeLines(node).map((t) => measureText(t, THEME.fontLabel, THEME.fontFamily))) + 2 * padX;
    if (need > avail) return null;
    const lines = nodeLines(node).length;
    const h = lines * lineH + 2 * padY;
    tallest = Math.max(tallest, h);
    boxes.set(node.id, { w: Math.min(avail, Math.max(need, node.leaf ? 0 : need)), h, lines });
  }
  const levels = model.maxDepth + 1;
  const minLevel = tallest + 1.8 * f;
  const levelH = height === null ? minLevel + 0.6 * f : (height - top - 0.6 * f) / levels;
  if (levelH < minLevel) return null;
  const placed = model.nodes.map((node) => {
    const box = boxes.get(node.id);
    const cx = side + pos.get(node.id) * slotW;
    const y = top + node.depth * levelH + (levelH - box.h) / 2 - 0.4 * f;
    return { node, x: cx - box.w / 2, y, w: box.w, h: box.h };
  });
  return {
    kind: 'top-down', top, placed, lineH, padX, padY,
    height: Math.ceil(height ?? top + levels * levelH + 0.6 * f),
    plot: { left: side, top, width: width - 2 * side, height: levels * levelH },
  };
}

/** The indented outline at `width`: one row per node, depth-first, rows wrapped to the width. */
export function outlineLayout(model, width, height = null) {
  const f = THEME.fontLabel;
  const side = axisPadding().right;
  const top = headerHeight(width);
  const indent = measureText('≤ ', THEME.fontLabel, THEME.fontFamily) + 1.2 * f;
  const lineH = 1.3 * f;
  const padX = 0.5 * f;
  const padY = 0.3 * f;
  const rowGap = 0.35 * f;
  const order = [];
  const walk = (id) => {
    const node = model.byId.get(id);
    if (!node) return;
    order.push(node);
    if (!node.leaf) {
      walk(node.left);
      walk(node.right);
    }
  };
  walk(model.root);
  let y = top;
  const placed = order.map((node) => {
    const x = side + indent * node.depth;
    const w = Math.max(60, width - side - x);
    const text = node.leaf
      ? [`n = ${formatInt(node.n)} · ${valueText(node)}`]
      : [ruleText(node), `${FRAME_WORDS[node.frame] ?? 'no frame'} · n = ${formatInt(node.n)} · ${valueText(node)}`];
    const lines = text.flatMap((t) => (measureText(t, THEME.fontLabel, THEME.fontFamily) + 2 * padX <= w
      ? [t] : wrapText(t, w - 2 * padX, THEME.fontLabel, THEME.fontFamily)));
    const h = lines.length * lineH + 2 * padY;
    const box = { node, x, y, w, h, lines };
    y += h + rowGap;
    return box;
  });
  const natural = y - rowGap + 0.6 * f;
  return {
    kind: 'outline', top, placed, lineH, padX, padY, indent,
    height: Math.ceil(height ?? natural),
    overflow: height !== null && natural > height,
    plot: { left: side, top, width: width - 2 * side, height: natural - top },
  };
}

/** The layout drawn at `width` × `height`: top-down when it fits, else the outline. */
export function treeLayout(model, width, height = null) {
  return topDownLayout(model, width, height) ?? outlineLayout(model, width, height);
}

/* ------------------------------------------------------------- tooltips -- */

/** The tooltip of one node: its rule, its path, every output's value and SD. */
export function nodeTip(model, node) {
  const lines = [];
  lines.push(node.leaf
    ? `<b>Leaf: ${formatInt(node.n)} rows (${formatPercent(node.share, 1)} of ${formatInt(model.nRows)})</b>`
    : `<b>${escapeHtml(ruleText(node))}</b> ${mutedLine(`(${FRAME_WORDS[node.frame] ?? 'no frame'}; true goes left)`)}`);
  if (!node.leaf) lines.push(`${formatInt(node.n)} rows reach this split (${formatPercent(node.share, 1)} of ${formatInt(model.nRows)})`);
  if (node.path.length) {
    lines.push(`path: ${node.path.map((p) => `${escapeHtml(p.text)} ${p.branch}`).join(' → ')}`);
  }
  for (const label of model.labels) {
    const unit = model.units?.[label] ?? (label === model.label ? model.unit : '');
    const v = node.values?.[label];
    const s = node.sds?.[label];
    const linear = label === 'phi' ? 'linear mean' : 'mean';
    lines.push(`${escapeHtml(LABEL_WORDS[label] ?? label)}: ${linear} of the booster's predictions ${sigFigs(v, 4)}`
      + ` ± ${sigFigs(s, 4)}${unit ? ` ${escapeHtml(unit)}` : ''} (within-node SD)${label === model.label ? '' : ` ${mutedLine('(not drawn)')}`}`);
    const circ = node.circular?.[label];
    if (circ && (Number.isFinite(circ.resultant) || Number.isFinite(circ.mean))) {
      lines.push(`${escapeHtml(LABEL_WORDS[label] ?? label)}: circular mean ${sigFigs(circ.mean, 4)}, mean resultant length R̄ = ${sigFigs(circ.resultant, 3)}`
        + ` ${mutedLine('(R̄ near 1: the predictions point one way; near 0: no common direction)')}`);
    }
  }
  if (Number.isFinite(node.impurity)) lines.push(mutedLine(`impurity ${sigFigs(node.impurity, 4)} (sklearn's: the variance, averaged over the outputs)`));
  lines.push(mutedLine('a description of the booster on these rows: no interval'));
  if (model.labels.includes('phi')) {
    lines.push(mutedLine('φ: sklearn\'s linear mean of predicted azimuths, kept for notebook parity - not a mean direction; never coloured'));
  }
  return lines.join('<br/>');
}

/* --------------------------------------------------------------- option -- */

/** The ramp's title for the drawn output. */
export function rampTitle(model) {
  const what = model.task === 'momentum' ? 'predicted momentum' : `predicted ${LABEL_WORDS[model.label] ?? model.label}`;
  return `Node mean of the ${what}${model.unit ? ` [${model.unit}]` : ''}`;
}

/** The screen subtitle: the fidelity, the depth and the rows. */
export function fidelityText(model) {
  const fid = model.fidelity;
  const mae = Number.isFinite(fid.mae) ? `, MAE ${sigFigs(fid.mae, 3)}${fid.unit ? ` ${fid.unit}` : ''}` : '';
  const which = model.labels.length > 1 ? ` (${LABEL_WORDS[model.label] ?? model.label})` : '';
  return `Fidelity to the booster${which}: R² ${sigFigs(fid.r2, 3)}${mae}; in-sample on ${formatInt(model.nRows)} rows`;
}

/** The header: subtitle (screen only) and the colour ramp, as graphic elements. */
function headerGraphics(model, width) {
  const f = THEME.fontLabel;
  const side = axisPadding().right;
  const out = [];
  const twoRows = width < 560;
  const rampW = Math.min(140, 0.3 * width);
  const rampY = isPrintTheme() ? 0.6 * f : (twoRows ? 2.4 * f : 0.6 * f);
  if (!isPrintTheme()) {
    out.push({
      type: 'text', silent: true,
      style: {
        x: side, y: 0.6 * f, fill: THEME.text, fontSize: THEME.fontLabel, fontFamily: THEME.fontFamily,
        text: fitName([fidelityText(model), `R² ${sigFigs(model.fidelity.r2, 3)} to the booster`],
          twoRows ? width - 2 * side : width - 2 * side - rampW - 12 * f),
      },
    });
  }
  if (!model.coloured) {
    const text = model.label === 'phi'
      ? ['φ is not coloured: its node values are linear means kept for notebook parity, and an azimuth wraps', 'φ: not coloured (an azimuth wraps)']
      : ['This output is not coloured', 'Not coloured'];
    out.push({
      type: 'text', silent: true,
      style: { x: width - side, y: rampY, textAlign: 'right', fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily,
        text: fitName(text, twoRows || isPrintTheme() ? width - 2 * side : 0.45 * width) },
    });
    return out;
  }
  const rampX = width - side - rampW;
  const stops = Array.from({ length: 9 }, (_, k) => ({ offset: k / 8, color: rampColour(model.ramp, k / 8) }));
  out.push({
    type: 'rect', silent: true,
    shape: { x: rampX, y: rampY, width: rampW, height: 0.8 * f },
    style: { fill: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: stops, global: false } },
  });
  const small = { fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily };
  out.push({ type: 'text', silent: true, style: { ...small, x: rampX, y: rampY + 1.0 * f, text: sigFigs(model.domain[0], 3) } });
  out.push({ type: 'text', silent: true, style: { ...small, x: rampX + rampW, y: rampY + 1.0 * f, textAlign: 'right', text: sigFigs(model.domain[1], 3) } });
  out.push({
    type: 'text', silent: true,
    style: {
      ...small, x: rampX - 0.6 * f, y: rampY - 0.1 * f, textAlign: 'right',
      text: fitName([rampTitle(model), model.unit ? `Node mean [${model.unit}]` : 'Node mean'], rampX - side - (twoRows || isPrintTheme() ? 0 : 0.55 * width)),
    },
  });
  return out;
}

/** The branches as one silent custom series: elbows (outline) or straight edges with ≤ / > (top-down). */
function edgeSeries(model, layout) {
  const at = new Map(layout.placed.map((b) => [b.node.id, b]));
  const stroke = { stroke: THEME.muted, lineWidth: THEME.lineAxis, fill: 'none' };
  const tag = { fill: THEME.muted, fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily };
  return {
    type: 'custom',
    name: EDGE_NAME,
    coordinateSystem: 'none',
    silent: true,
    z: 3,
    data: [[0]],
    renderItem: () => {
      const children = [];
      for (const b of layout.placed) {
        const parent = b.node.parent === null ? null : at.get(b.node.parent);
        if (!parent) continue;
        if (layout.kind === 'top-down') {
          const x1 = parent.x + parent.w / 2;
          const y1 = parent.y + parent.h;
          const x2 = b.x + b.w / 2;
          const y2 = b.y;
          children.push({ type: 'line', shape: { x1, y1, x2, y2 }, style: stroke });
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          children.push({
            type: 'text',
            style: { ...tag, x: mx + (b.node.branch === '≤' ? -4 : 4), y: my, text: b.node.branch,
              textAlign: b.node.branch === '≤' ? 'right' : 'left', textVerticalAlign: 'middle' },
          });
        } else {
          const x0 = parent.x + 0.5 * layout.indent - 2;
          const ym = b.y + Math.min(b.h / 2, layout.lineH);
          children.push({
            type: 'polyline',
            shape: { points: [[x0, parent.y + parent.h], [x0, ym], [b.x, ym]] },
            style: stroke,
          });
          children.push({
            type: 'text',
            style: { ...tag, x: b.x - 2, y: ym - 1, text: b.node.branch, textAlign: 'right', textVerticalAlign: 'bottom' },
          });
        }
      }
      return { type: 'group', children };
    },
  };
}

/** The nodes as one custom series, one hover target per node. */
function nodeSeries(model, layout) {
  return {
    type: 'custom',
    name: NODE_NAME,
    coordinateSystem: 'none',
    silent: false,
    z: 5,
    data: layout.placed.map((b, i) => [i]),
    renderItem: (params) => {
      const b = layout.placed[params.dataIndex];
      const node = b.node;
      const colour = node.colour ?? THEME.muted;
      const fill = node.leaf && node.colour ? node.colour : THEME.card;
      const ink = node.leaf && node.colour ? inkOn(node.colour) : THEME.text;
      const lines = b.lines ?? nodeLines(node);
      const children = [{
        type: 'rect',
        shape: { x: b.x, y: b.y, width: b.w, height: b.h, r: 2 },
        style: {
          fill,
          stroke: node.colour ? colour : (node.leaf ? THEME.text : THEME.muted),
          lineWidth: node.leaf || !node.colour ? THEME.lineAxis : 1.6 * THEME.lineAxis,
        },
      }];
      lines.forEach((text, i) => {
        children.push({
          type: 'text',
          style: {
            x: layout.kind === 'top-down' ? b.x + b.w / 2 : b.x + layout.padX,
            y: b.y + layout.padY + (i + 0.5) * layout.lineH,
            text,
            textAlign: layout.kind === 'top-down' ? 'center' : 'left',
            textVerticalAlign: 'middle',
            fill: ink,
            fontSize: THEME.fontLabel,
            fontFamily: THEME.fontFamily,
            fontWeight: !node.leaf && i === 0 ? 'bold' : 'normal',
          },
        });
      });
      return { type: 'group', children };
    },
    tooltip: { formatter: (p) => nodeTip(model, layout.placed[p.dataIndex].node) },
  };
}

/**
 * The E4 option. Pure: `opts` = {label?, palette?, tooltipPosition?};
 * `metrics` = {width, height}. Everything is drawn in pixels (no axes).
 */
export function xgbTreeOption(payload, opts = {}, metrics = {}) {
  const model = treeModel(payload, opts);
  if (!model) return emptyChartOption(opts, metrics, 'This response carries no surrogate tree.');
  const width = metrics.width || 900;
  const height = metrics.height || 330;
  const layout = treeLayout(model, width, height);
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    graphic: headerGraphics(model, width),
    series: [edgeSeries(model, layout), nodeSeries(model, layout)],
  };
}

/** The area the tips stay off: the tree. */
export function treePlotGrid(payload, opts, metrics) {
  const model = treeModel(payload, opts);
  if (!model) return null;
  const layout = treeLayout(model, metrics.width || 900, metrics.height || 330);
  return { ...layout.plot };
}

export class XgbTreePanel extends ChartPanel {
  constructor(elementOrId, { aspect } = {}) {
    super(elementOrId, { kind: 'xgb-tree', aspect });
  }

  buildOption({ payload, opts = {}, metrics }) {
    return { option: xgbTreeOption(payload, opts, metrics), plotGrid: treePlotGrid(payload, opts, metrics) };
  }

  /** A figure as tall as the tree needs at `width`: the outline below the top-down width. */
  exportMetrics(width) {
    const model = treeModel(this.lastPayload, this.lastOpts ?? {});
    if (!model) return super.exportMetrics(width);
    return { width, height: treeLayout(model, width, null).height };
  }
}
