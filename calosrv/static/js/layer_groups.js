/* Longitudinal Channels: the 13-group partition of the detector's depth layers.
 *
 * A pure engine, a leaf (it imports only format.js), so it runs under Node for
 * the tests and both pages share it. The UI says "Longitudinal Channels",
 * "Ch m" for detector numbering and "Rel Ch m" for relative numbering; every
 * identifier here says layer group, because "channel" is the display channel
 * (density, Grad-CAM, ...) everywhere else in the service.
 *
 * ## The partition
 *
 * `counts`: 13 positive integers summing to L, the experiment's lattice layer
 * count (`lattice.z.n`: 60 on production, 56 on the demo table, whose lattice
 * skips four layers). The boundary b_m is the last layer of group m (1-based),
 * b_13 = L. A partition numbers **lattice ordinals**, the 3-D slice mode's
 * numbering; it never asserts a layer that the lattice does not hold.
 *
 * ## Geometry: stored edges, never index × pitch
 *
 * A seam is drawn at the **stored edge** between the native depth bins b and
 * b + 1 of the axis it is drawn on: the lattice's own cell edges on the
 * Absolute frame (raw z: 3652.15 + 20.5·b on production), (b − ½)·p as the
 * server states it on the D-frame and the per-shower translated frame. A
 * group or seam beyond the axis is not drawn and is counted. Group 13 always
 * runs to the end of the axis, which matters when an axis has more bins than
 * L (the per-shower translated frame on a gapped lattice).
 *
 * One shower in Local: the detector's layer planes tilt by the shower's own
 * R(θ, φ), whose normal is R·ê_z = (−sin θ, 0, cos θ) for every φ. A plane
 * n·x′ = s has an exact line image only on a panel whose summed axis has a
 * zero normal component: u–w (`xz`), where w = s / cos θ + u · tan θ. On v–w
 * the plane spans a band tan θ × the shower's u-extent wide, so nothing is
 * drawn there and the spec says why (`planeLine`).
 *
 * `panelGroupSpec` is the one way a caller builds a panel's spec, from either
 * an ensemble response's `depth_layers` block or one event frame's
 * `layer_planes` block (brief section 2.2 and 2.3). The spec is plain data -
 * positions in millimetres of the panel's own depth coordinate and every
 * tooltip already written - so the ECharts builders (`panels/depth_groups.js`)
 * only draw it.
 */

import { MINUS, formatSigned, typographic } from './format.js';

/** The number of groups in a partition. */
export const GROUP_COUNT = 13;

/** The presets, in the order the editor lists them. */
export const PRESET_KEYS = Object.freeze(['uniform', 'em_hadron', 'log']);

/** The presets' names as the UI writes them. */
export const PRESET_LABELS = Object.freeze({
  uniform: 'Uniform', em_hadron: 'EM-Fine / Hadron-Coarse', log: 'Logarithmic Depth',
});

/** EM-Fine / Hadron-Coarse on the 60-layer production lattice: fine where an electromagnetic shower peaks. */
export const EM_HADRON_60 = Object.freeze([2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 8, 8]);

/** The sentence that replaces every line on a Local ensemble panel: its conclusion first, so a cut keeps it. */
export const LOCAL_BADGE = 'No common layer grid: layers tilt with each shower’s (θ, φ)';

/** The Local badge's short form, for a plot too narrow for the sentence (depth_groups.js `localBadge`). */
export const LOCAL_BADGE_SHORT = 'Local: no common layer grid';

/** The line that replaces the shares (and the reach) of a block the server trimmed to keep a response under 100 KB. */
export const TRIMMED_SHARES = 'shares left out: this response sat at the 100 KB guard';
export const TRIMMED_SHARES_REACH = 'shares and reach left out: this response sat at the 100 KB guard';

/* ---------------------------------------------------------------- numbers -- */

const isWhole = (v) => Number.isInteger(v);
const validL = (L) => isWhole(L) && L >= GROUP_COUNT;

/** A whole number with thousands separators, fixed (no locale), U+2212 for a minus. */
export function intText(value) {
  if (!Number.isFinite(value)) return '—';
  const n = Math.round(value);
  const digits = String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return n < 0 ? `${MINUS}${digits}` : digits;
}

/** A fraction as a percentage, "12.3%". */
export function percentText(fraction, digits = 1) {
  if (!Number.isFinite(fraction)) return '—';
  return typographic(`${(fraction * 100).toFixed(digits)}%`);
}

/** An energy in GeV to three significant figures, "1.23 GeV". */
export function gevText(value) {
  if (!Number.isFinite(value)) return '— GeV';
  if (value === 0) return '0 GeV';
  const a = Math.abs(value);
  const text = a >= 1e-3 && a < 1e4 ? value.toPrecision(3) : value.toExponential(2);
  return `${typographic(text)} GeV`;
}

/** A depth in mm to the given decimals, U+2212 for a minus. */
const mm = (v, digits = 1) => formatSigned(v, digits);

/** "lo–hi", or "lo to hi" where an end is negative (an en dash after a minus sign reads as one mark). */
export function spanText(lo, hi, digits = 1) {
  return lo < 0 || hi < 0 ? `${mm(lo, digits)} to ${mm(hi, digits)}` : `${mm(lo, digits)}–${mm(hi, digits)}`;
}

/**
 * The largest-remainder apportionment of L whole layers to `weights`, each
 * group at least one layer; ties go to the lower group. Returns null when L
 * cannot give every group a layer.
 */
function apportion(weights, L) {
  const n = weights.length;
  if (!validL(L) || L < n) return null;
  const total = weights.reduce((a, b) => a + b, 0);
  const raw = weights.map((w) => (w / total) * L);
  const counts = raw.map((r) => Math.max(1, Math.floor(r)));
  let left = L - counts.reduce((a, b) => a + b, 0);
  const order = (key) => [...Array(n).keys()].sort((a, b) => key(b) - key(a) || a - b);
  while (left > 0) {
    for (const i of order((i) => raw[i] - counts[i])) {
      if (left === 0) break;
      counts[i] += 1;
      left -= 1;
    }
  }
  while (left < 0) {
    // A floor raised to 1 overspent: take back from the groups furthest above their share.
    for (const i of order((i) => counts[i] - raw[i])) {
      if (left === 0) break;
      if (counts[i] > 1) {
        counts[i] -= 1;
        left += 1;
      }
    }
  }
  return counts;
}

/* ---------------------------------------------------------------- presets -- */

/** Uniform: L = 13q + r gives r groups of q + 1 first, then q (60 → 8 × 5 + 5 × 4). Null for L < 13. */
export function uniformCounts(L) {
  if (!validL(L)) return null;
  const q = Math.floor(L / GROUP_COUNT);
  const r = L % GROUP_COUNT;
  return Array.from({ length: GROUP_COUNT }, (_, m) => (m < r ? q + 1 : q));
}

/**
 * The ratio r of a geometric run of 13 widths r^(m−1) summing to L (r = 1 at
 * L = 13), by bisection: for 60, r ≈ 1.2305.
 */
export function logRatio(L) {
  if (!validL(L)) return null;
  if (L === GROUP_COUNT) return 1;
  const sum = (r) => {
    let s = 0;
    for (let m = 0; m < GROUP_COUNT; m += 1) s += r ** m;
    return s;
  };
  let lo = 1;
  let hi = 2;
  while (sum(hi) < L) hi *= 2;
  for (let i = 0; i < 200; i += 1) {
    const mid = (lo + hi) / 2;
    if (sum(mid) < L) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

/**
 * A preset's counts for L layers:
 * - `uniform`: `uniformCounts`;
 * - `em_hadron`: EM_HADRON_60 scaled to L by largest remainder, each ≥ 1;
 * - `log`: widths r^(m−1) with Σ = L, by largest remainder, each ≥ 1
 *   (60 → [1, 1, 2, 2, 2, 3, 4, 4, 5, 6, 8, 10, 12]).
 * Null for an unknown key or L < 13.
 */
export function presetCounts(key, L) {
  if (!validL(L)) return null;
  if (key === 'uniform') return uniformCounts(L);
  if (key === 'em_hadron') return L === 60 ? [...EM_HADRON_60] : apportion(EM_HADRON_60, L);
  if (key === 'log') {
    const r = logRatio(L);
    return apportion(Array.from({ length: GROUP_COUNT }, (_, m) => r ** m), L);
  }
  return null;
}

/** The preset a partition equals for L, or null (a custom partition). */
export function presetOf(counts, L) {
  for (const key of PRESET_KEYS) if (sameCounts(counts, presetCounts(key, L))) return key;
  return null;
}

/* ------------------------------------------------------- codec and editing -- */

/** 13 positive integers, summing to L when L is given. */
export function isValidCounts(counts, L = null) {
  if (!Array.isArray(counts) || counts.length !== GROUP_COUNT) return false;
  if (!counts.every((c) => isWhole(c) && c >= 1)) return false;
  return L === null || L === undefined || counts.reduce((a, b) => a + b, 0) === L;
}

/** The boundaries b_1..b_13: the last layer of each group, 1-based. */
export function countsToBoundaries(counts) {
  let b = 0;
  return counts.map((c) => (b += c));
}

/** The counts of boundaries b_1..b_13 (each the last layer of its group). */
export function boundariesToCounts(boundaries) {
  return boundaries.map((b, m) => b - (m ? boundaries[m - 1] : 0));
}

/** The wire and hash form, "5.5.5.5.5.5.5.5.4.4.4.4.4". */
export function formatCounts(counts) {
  return counts.join('.');
}

/** The counts of a wire string, or null when it is not 13 positive integers (summing to L when given). */
export function parseCounts(text, L = null) {
  if (typeof text !== 'string' || !/^\d+(\.\d+){12}$/.test(text)) return null;
  const counts = text.split('.').map(Number);
  return isValidCounts(counts, L) ? counts : null;
}

/** Whether two partitions are the same. */
export function sameCounts(a, b) {
  return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => v === b[i]);
}

/** Each group's layers, `[{group, first, last, n}]`, 1-based. */
export function groupRanges(counts) {
  let first = 1;
  return counts.map((n, m) => {
    const range = { group: m + 1, first, last: first + n - 1, n };
    first += n;
    return range;
  });
}

/** "1–5, 6–10, …": the ranges with en dashes. */
export function formatRanges(counts) {
  return groupRanges(counts).map((g) => (g.first === g.last ? `${g.first}` : `${g.first}–${g.last}`)).join(', ');
}

/** The group (1..13) that holds `layer` (1-based), or null off the partition. */
export function groupOfLayer(counts, layer) {
  if (!isWhole(layer) || layer < 1) return null;
  for (const g of groupRanges(counts)) if (layer <= g.last) return g.group;
  return null;
}

const DASHES = /[-‐‑–—−]/;

/**
 * The counts of a typed shorthand, `{counts}` or `{error}` with a sentence:
 * - ranges, "1-3, 4-5, …" (a hyphen, an en dash or U+2212), 13 of them,
 *   contiguous from layer 1 to layer L; a lone number is a one-layer range;
 * - or counts, "3, 2, …" (commas or spaces), 13 positive whole numbers summing to L.
 */
export function parseShorthand(text, L) {
  if (!validL(L)) return { error: `The lattice has no layer count to partition (L = ${L ?? '—'}).` };
  const source = String(text ?? '').trim();
  const example = `Type 13 ranges (1–5, 6–10, …) or 13 layer counts (5, 5, …) summing to ${L}.`;
  if (!source) return { error: example };
  if (DASHES.test(source)) {
    const items = source.split(/[,;]+/).map((s) => s.trim()).filter(Boolean);
    if (items.length !== GROUP_COUNT) {
      return { error: `Found ${items.length} range${items.length === 1 ? '' : 's'}; a partition has 13. ${example}` };
    }
    const counts = [];
    let next = 1;
    for (const [i, item] of items.entries()) {
      const match = /^(\d+)\s*(?:[-‐‑–—−]\s*(\d+))?$/.exec(item);
      if (!match) return { error: `Range ${i + 1}, “${item}”, is not of the form a–b.` };
      const a = Number(match[1]);
      const b = match[2] === undefined ? a : Number(match[2]);
      if (b < a) return { error: `Range ${i + 1}, “${item}”, ends before it starts.` };
      if (a !== next) {
        return { error: `Range ${i + 1} starts at layer ${a}; it must start at layer ${next}, `
          + `right after the one before, so every layer belongs to one channel.` };
      }
      counts.push(b - a + 1);
      next = b + 1;
    }
    if (next - 1 !== L) return { error: `The ranges end at layer ${next - 1}; they must end at layer ${L}.` };
    return { counts };
  }
  const items = source.split(/[\s,;]+/).filter(Boolean);
  if (!items.every((s) => /^\d+$/.test(s))) return { error: `Counts must be whole numbers. ${example}` };
  const counts = items.map(Number);
  if (counts.length !== GROUP_COUNT) {
    return { error: `Found ${counts.length} count${counts.length === 1 ? '' : 's'}; a partition has 13. ${example}` };
  }
  if (counts.some((c) => c < 1)) return { error: 'Every channel needs at least one layer.' };
  const sum = counts.reduce((a, b) => a + b, 0);
  if (sum !== L) return { error: `The counts sum to ${sum}; they must sum to the lattice’s ${L} layers.` };
  return { counts };
}

/**
 * Set the last layer of group m (1..12), moving the first layer of group
 * m + 1 with it: the coupled edit. Clamped so groups m and m + 1 keep at least
 * one layer each. Returns `{counts, clamped, message}`; `message` says what
 * the clamp held, or is ''. Invalid input returns the counts unchanged.
 */
export function setGroupEnd(counts, m, end) {
  if (!isValidCounts(counts) || !isWhole(m) || m < 1 || m > GROUP_COUNT - 1 || !Number.isFinite(Number(end))) {
    return { counts: Array.isArray(counts) ? [...counts] : counts, clamped: false, message: '' };
  }
  const b = countsToBoundaries(counts);
  const lo = (m >= 2 ? b[m - 2] : 0) + 1;
  const hi = b[m] - 1;
  const want = Math.round(Number(end));
  const value = Math.min(hi, Math.max(lo, want));
  b[m - 1] = value;
  const clamped = value !== want;
  let message = '';
  if (clamped) {
    message = want < lo
      ? `Ch ${m} must keep at least one layer: its end was held at layer ${value}.`
      : `Ch ${m + 1} must keep at least one layer: Ch ${m} was held to end at layer ${value}.`;
  }
  return { counts: boundariesToCounts(b), clamped, message };
}

/**
 * Set the first layer of group m (2..13), moving the last layer of group
 * m − 1 with it. Clamped as `setGroupEnd`; returns `{counts, clamped, message}`.
 */
export function setGroupStart(counts, m, start) {
  if (!isValidCounts(counts) || !isWhole(m) || m < 2 || m > GROUP_COUNT || !Number.isFinite(Number(start))) {
    return { counts: Array.isArray(counts) ? [...counts] : counts, clamped: false, message: '' };
  }
  const want = Math.round(Number(start));
  const result = setGroupEnd(counts, m - 1, want - 1);
  if (!result.clamped) return result;
  const b = countsToBoundaries(result.counts);
  const value = b[m - 2] + 1;
  const message = want - 1 < b[m - 2]
    ? `Ch ${m - 1} must keep at least one layer: Ch ${m} was held to start at layer ${value}.`
    : `Ch ${m} must keep at least one layer: its start was held at layer ${value}.`;
  return { counts: result.counts, clamped: true, message };
}

/** Move seam s (1..12, the boundary after group s) by `delta` layers: the keyboard edit. */
export function moveSeam(counts, seam, delta) {
  if (!isValidCounts(counts) || !isWhole(seam) || seam < 1 || seam > GROUP_COUNT - 1) {
    return { counts: Array.isArray(counts) ? [...counts] : counts, clamped: false, message: '' };
  }
  const b = countsToBoundaries(counts);
  return setGroupEnd(counts, seam, b[seam - 1] + Math.round(Number(delta) || 0));
}

/* ---------------------------------------------------------------- geometry -- */

/**
 * The bin edges of a payload axis `{lo, hi, n, uniform, edges?}`: its stored
 * `edges` when present (the irregular lattice), else the uniform grid the
 * axis states over [lo, hi]. Null when neither is usable.
 */
export function axisEdges(axis) {
  if (!axis) return null;
  const n = axis.n;
  if (Array.isArray(axis.edges) && axis.edges.length >= 2 && axis.edges.every(Number.isFinite)) {
    if (isWhole(n) && axis.edges.length !== n + 1) return null;
    for (let i = 1; i < axis.edges.length; i += 1) if (!(axis.edges[i] > axis.edges[i - 1])) return null;
    return [...axis.edges];
  }
  if (axis.uniform && isWhole(n) && n >= 1 && Number.isFinite(axis.lo) && Number.isFinite(axis.hi) && axis.hi > axis.lo) {
    return Array.from({ length: n + 1 }, (_, i) => (i === n ? axis.hi : axis.lo + ((axis.hi - axis.lo) * i) / n));
  }
  return null;
}

/**
 * The seams of a partition on an axis of `edges.length − 1` native bins,
 * whose bin 0 holds layer `firstLayer`: `[{seam, after, at}]`, seam m after
 * layer b_m at the stored edge between its bins. A seam beyond either end of
 * the axis is not returned (count them as 12 − length).
 */
export function seamsOnAxis(edges, counts, { firstLayer = 1 } = {}) {
  if (!Array.isArray(edges) || edges.length < 2 || !isValidCounts(counts)) return [];
  const b = countsToBoundaries(counts);
  const seams = [];
  for (let m = 1; m < GROUP_COUNT; m += 1) {
    const index = b[m - 1] - firstLayer + 1;
    if (index <= 0 || index >= edges.length - 1) continue;
    seams.push({ seam: m, after: b[m - 1], at: edges[index] });
  }
  return seams;
}

/**
 * The groups' spans on an axis: `[{group, first, last, n, bins: [j0, j1], lo,
 * hi, partial, extended, axisFirst, axisLast, nAxis}]` for every group with a
 * bin on it. `first`/`last`/`n` are the partition's; `axisFirst`/`axisLast`/
 * `nAxis` the layers the span holds on this axis, which differ where the axis
 * cuts the group (`partial`) or where group 13 runs past layer L to the end
 * of a longer axis (`extended`). `lo`/`hi` are the stored edges. Groups
 * wholly beyond the axis are left out (`groupsBeyond` counts them).
 */
export function groupSpansOnAxis(edges, counts, { firstLayer = 1 } = {}) {
  if (!Array.isArray(edges) || edges.length < 2 || !isValidCounts(counts)) return [];
  const nBins = edges.length - 1;
  const spans = [];
  for (const g of groupRanges(counts)) {
    const j0 = g.first - firstLayer;
    let j1 = g.last - firstLayer;
    let extended = false;
    if (g.group === GROUP_COUNT && j1 < nBins - 1) {
      j1 = nBins - 1;
      extended = true;
    }
    if (j0 > nBins - 1 || j1 < 0) continue;
    const a = Math.max(0, j0);
    const b = Math.min(nBins - 1, j1);
    spans.push({
      group: g.group, first: g.first, last: g.last, n: g.n, bins: [a, b],
      lo: edges[a], hi: edges[b + 1], partial: a !== j0 || b !== j1, extended,
      axisFirst: firstLayer + a, axisLast: firstLayer + b, nAxis: b - a + 1,
    });
  }
  return spans;
}

/** The groups of a partition wholly beyond an axis of `nBins` bins. */
export function groupsBeyondAxis(nBins, counts, { firstLayer = 1 } = {}) {
  if (!isValidCounts(counts)) return [];
  return groupRanges(counts)
    .filter((g) => g.first - firstLayer > nBins - 1 || (g.group !== GROUP_COUNT && g.last - firstLayer < 0))
    .map((g) => g.group);
}

const EPS = 1e-9;

/**
 * The segment a plane n·x = `at` draws on a panel, or null when it has no
 * line image there: `xz` (column z, row x, summed y) and `yz` (column z, row
 * y, summed x) need the summed component of n to be zero. `rowRange` is the
 * row axis's [lo, hi]; the result is `{from, to}` as [column, row] points.
 */
export function planeLine(normal, at, panelId, rowRange) {
  if (!Array.isArray(normal) || normal.length !== 3 || !normal.every(Number.isFinite) || !Number.isFinite(at)) return null;
  if (!Array.isArray(rowRange) || !rowRange.every(Number.isFinite)) return null;
  const [nx, ny, nz] = normal;
  let nr;
  if (panelId === 'xz') {
    if (Math.abs(ny) > EPS) return null;
    nr = nx;
  } else if (panelId === 'yz') {
    if (Math.abs(nx) > EPS) return null;
    nr = ny;
  } else {
    return null;
  }
  if (Math.abs(nz) <= EPS) return null;
  const depth = (r) => (at - nr * r) / nz;
  return { from: [depth(rowRange[0]), rowRange[0]], to: [depth(rowRange[1]), rowRange[1]] };
}

/** The native bin of a sorted edge list holding `value`, or null off the axis. */
export function binOf(edges, value) {
  if (!Array.isArray(edges) || edges.length < 2 || !Number.isFinite(value)) return null;
  if (value < edges[0] || value > edges[edges.length - 1]) return null;
  let lo = 0;
  let hi = edges.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (edges[mid] <= value) lo = mid; else hi = mid - 1;
  }
  return lo;
}

/* ---------------------------------------------------------- shares, reach -- */

/**
 * Each group's sum of per-bin `values` (the native depth axis: bin j holds
 * layer firstLayer + j) and its share of `total` (default the sum of the
 * values): `[{group, first, last, sum, share, beyond}]`, every group listed.
 */
export function groupShares(values, counts, { firstLayer = 1, total = null } = {}) {
  if (!Array.isArray(values) || !isValidCounts(counts)) return [];
  const finite = values.map((v) => (Number.isFinite(v) ? v : 0));
  const denominator = Number.isFinite(total) ? total : finite.reduce((a, b) => a + b, 0);
  const edges = Array.from({ length: finite.length + 1 }, (_, i) => i);
  const spans = new Map(groupSpansOnAxis(edges, counts, { firstLayer }).map((s) => [s.group, s]));
  return groupRanges(counts).map((g) => {
    const span = spans.get(g.group);
    let sum = 0;
    if (span) for (let j = span.bins[0]; j <= span.bins[1]; j += 1) sum += finite[j];
    return {
      group: g.group, first: g.first, last: g.last, sum,
      share: denominator > 0 ? sum / denominator : null, beyond: !span,
    };
  });
}

/**
 * How many showers reach a group of relative layers [first, last]: from the
 * server's `reach` block, where counts[k] is the number of showers whose
 * depth extends to relative layer k + 1. `{reached, full, of, share}`, or null.
 */
export function groupReach(reach, first, last) {
  if (!reach || !Array.isArray(reach.counts) || !isWhole(first) || first < 1) return null;
  const at = (layer) => (layer - 1 < reach.counts.length ? reach.counts[layer - 1] : 0);
  const of = reach.n_showers;
  const reached = at(first);
  const full = at(Math.max(first, last));
  return { reached, full, of, share: of > 0 ? reached / of : null };
}

/* -------------------------------------------------------------------- text -- */

/** "Ch m" (detector numbering) or "Rel Ch m" (relative numbering). */
export function groupLabel(numbering, m) {
  return numbering === 'relative' ? `Rel Ch ${m}` : `Ch ${m}`;
}

/** "layer 5" / "layers 5–7", "rel. layer …" in relative numbering. */
export function layersText(numbering, first, last) {
  const word = numbering === 'relative' ? 'rel. layer' : 'layer';
  return first === last ? `${word} ${first}` : `${word}s ${first}–${last}`;
}

/** A group's title, "Ch 3 · layers 5–7". */
export function groupTitle(numbering, group, first, last) {
  return `${groupLabel(numbering, group)} · ${layersText(numbering, first, last)}`;
}

/**
 * A depth range in the frame's own symbol: "Z 3.2–105.7 mm (z 3652.2–3754.7 mm)"
 * on the Absolute frame (Z first, raw z after), "z′ −10.3 to 51.3 mm" elsewhere.
 */
export function depthSpanText(lo, hi, { symbol = 'z', offset = 0 } = {}) {
  if (offset) return `Z ${spanText(lo - offset, hi - offset)} mm (${symbol} ${spanText(lo, hi)} mm)`;
  return `${symbol} ${spanText(lo, hi)} mm`;
}

/** One depth as the readouts write it: "Z = 74.9 mm (z = 3723.9 mm)" with an offset, else "z′ = 51.3 mm". */
export function depthPointText(value, { symbol = 'z', offset = 0 } = {}) {
  if (offset) return `Z = ${mm(value - offset)} mm (${symbol} = ${mm(value)} mm)`;
  return `${symbol} = ${mm(value)} mm`;
}

const attentionBase = (quantity) => String(quantity ?? 'Σ E·CAM').replace(/^Σ E·/, '');

/** The attention lines of a group: unsigned `[share]`, or the signed parts apart. */
function attentionLines(attention, span) {
  if (!attention) return [];
  const sum = (values) => {
    let s = 0;
    for (let j = span.bins[0]; j <= span.bins[1]; j += 1) s += Number.isFinite(values?.[j]) ? values[j] : 0;
    return s;
  };
  const q = attention.quantity ?? 'Σ E·CAM';
  if (attention.signed) {
    const base = attentionBase(q);
    const pos = sum(attention.positive);
    const neg = sum(attention.negative);
    const posShare = attention.positive_total > 0 ? pos / attention.positive_total : null;
    const negShare = attention.negative_total > 0 ? neg / attention.negative_total : null;
    return [`Σ E·${base}⁺: ${percentText(posShare)} of the positive part · `
      + `Σ E·|${base}⁻|: ${percentText(negShare)} of the negative part (kept apart)`];
  }
  const share = attention.total > 0 ? sum(attention.values) / attention.total : null;
  return [`${q}: ${percentText(share)} of the total`];
}

/** "N = 4,812 events", or ''. */
const nText = (n, what = 'event') => (isWhole(n) ? ` · N = ${intText(n)} ${what}${n === 1 ? '' : 's'}` : '');

/**
 * A group's tooltip (HTML lines): its layers, its depth span in the frame's
 * own symbol and its thickness, the exact energy share and the attention
 * share with their basis, the reach for relative numbering, the pooled
 * operator, the tilt for one-shower Local.
 */
export function groupTooltip(ctx, span) {
  const { numbering } = ctx;
  const head = `<b>${groupLabel(numbering, span.group)}</b> · `;
  const lines = [];
  if (span.extended) {
    // Group 13 on an axis longer than L: the layers it holds here, then where the partition ends.
    lines.push(`${head}${layersText(numbering, span.first, span.axisLast)} `
      + `(${intText(span.nAxis)} on the axis; the partition ends at layer ${intText(span.last)})`);
    lines.push('runs to the end of the depth axis, past the partition’s last layer');
  } else {
    lines.push(`${head}${layersText(numbering, span.first, span.last)} (${intText(span.n)} layer${span.n === 1 ? '' : 's'})`);
  }
  if (span.partial) {
    lines.push(`the depth axis cuts this channel: only its ${intText(span.nAxis)} layer${span.nAxis === 1 ? '' : 's'} `
      + `on the axis (${layersText(numbering, span.axisFirst, span.axisLast)}) are drawn`);
  }
  if (Number.isFinite(span.lo) && Number.isFinite(span.hi)) {
    const thick = span.hi - span.lo;
    lines.push(`${depthSpanText(span.lo, span.hi, ctx)} · ${mm(thick)} mm thick`);
  }
  if (ctx.tilt) {
    lines.push(`layers tilt by θ = ${typographic(Number(ctx.tilt.theta_deg).toFixed(1))}°: `
      + `pitch along w = p / cos θ = ${mm(ctx.tilt.pitch_along_w_mm, 2)} mm`);
  }
  const energy = ctx.profile?.energy;
  if (Array.isArray(energy)) {
    let sum = 0;
    for (let j = span.bins[0]; j <= span.bins[1]; j += 1) sum += Number.isFinite(energy[j]) ? energy[j] : 0;
    const total = Number.isFinite(ctx.profile.total) ? ctx.profile.total : energy.reduce((a, b) => a + (b || 0), 0);
    const whose = ctx.basis === 'shower' ? 'this shower’s energy' : 'the selection’s energy';
    // A co-registered bundle's outside energy fell outside its 3-D accumulation grid (mostly
    // transversely); only the Absolute frame's lies literally past the depth axis.
    const where = ctx.weighting === 'overlap' ? 'outside the accumulation grid' : 'off the depth axis';
    const outside = Number.isFinite(ctx.profile.outside) && ctx.profile.outside > 0
      ? `; ${gevText(ctx.profile.outside)} ${where} is counted in the total` : '';
    lines.push(`energy: ${percentText(total > 0 ? sum / total : null)} of ${whose} `
      + `(Σ E = ${gevText(sum)} of ${gevText(total)}${outside})${ctx.basis === 'shower' ? '' : nText(ctx.nEvents)}`);
    if (ctx.profile.exact === false) lines.push('<i>preview sample: the shares are of the sampled hits</i>');
  } else if (ctx.trimmed) {
    lines.push(`<i>${ctx.reachTrimmed ? TRIMMED_SHARES_REACH : TRIMMED_SHARES}</i>`);
  }
  for (const line of attentionLines(ctx.profile?.attention, span)) lines.push(line);
  if (ctx.reach) {
    const r = groupReach(ctx.reach, span.first, span.extended ? span.axisLast : span.last);
    if (r) {
      let text = `reached by ${intText(r.reached)} of ${intText(r.of)} showers (${percentText(r.share)})`;
      if (r.full !== r.reached) text += `; ${intText(r.full)} reach its last layer`;
      lines.push(text);
    }
  }
  if (Number.isFinite(ctx.reachLayers) && span.first > ctx.reachLayers) {
    lines.push(`beyond this shower’s reach: the detector ends after rel. layer ${intText(ctx.reachLayers)}`);
  }
  if (ctx.pooled) lines.push(`pooled: this column is ${pooledOperator(ctx.axis, span).tooltip}`);
  return lines.join('<br/>');
}

/** A number of pitches as "6.5", at most two decimals. */
const slotsText = (v) => typographic(String(Number(v.toFixed(2))));

/**
 * What a pooled column is, from the native edges it spans (LG-C5):
 * - the Absolute frame pools Σ E · p / ΔZ (GeV per layer pitch, `per_pitch`):
 *   the mean of its layers only where ΔZ = n · p, else the sum over ΔZ / p
 *   pitches, which a gapped lattice makes larger than n;
 * - a co-registered frame pools the width-weighted mean (`overlap`): the mean
 *   of its layers only where they are equally wide.
 * `{readout, tooltip}`, the short and the long wording.
 */
export function pooledOperator(axis, span) {
  const n = span.nAxis ?? span.bins[1] - span.bins[0] + 1;
  const layers = `${intText(n)} layer${n === 1 ? '' : 's'}`;
  const mean = { readout: `mean of ${layers}`, tooltip: `the mean of its ${layers}` };
  const edges = axis?.edges;
  if (!Array.isArray(edges) || !Number.isFinite(span.lo) || !Number.isFinite(span.hi)) return mean;
  const thick = span.hi - span.lo;
  const tol = 1e-3;
  if (axis.weighting === 'per_pitch') {
    const p = axis.pitch;
    if (!(Number.isFinite(p) && p > 0)) return mean;
    const slots = thick / p;
    if (Math.abs(slots - n) <= tol * Math.max(1, n)) return mean;
    return {
      readout: `Σ E of ${layers} per ${mm(p)} mm (÷ ${slotsText(slots)} pitches)`,
      tooltip: `Σ E of its ${layers} per ${mm(p)} mm of depth: the sum ÷ ${slotsText(slots)} pitches `
        + `(${mm(thick)} mm thick), not their mean`,
    };
  }
  const widths = [];
  for (let j = span.bins[0]; j <= span.bins[1]; j += 1) widths.push(edges[j + 1] - edges[j]);
  const equal = widths.every((w) => Math.abs(w - widths[0]) <= tol * Math.max(1, Math.abs(widths[0])));
  if (equal) return mean;
  return {
    readout: `width-weighted mean of ${layers}`,
    tooltip: `the width-weighted mean of its ${layers} (each layer weighted by its own thickness over the ${mm(thick)} mm)`,
  };
}

/** A seam's tooltip: where it sits, between which layers and channels. */
export function seamTooltip(ctx, seam) {
  const { numbering } = ctx;
  const word = numbering === 'relative' ? 'rel. layers' : 'layers';
  return [
    `<b>Seam ${groupLabel(numbering, seam.seam)} | ${groupLabel(numbering, seam.seam + 1)}</b>`,
    `between ${word} ${seam.after} and ${seam.after + 1}, at ${depthPointText(seam.at, ctx)}`,
    'the stored cell edge between the two layers',
  ].join('<br/>');
}

/** A tilted layer plane's tooltip (one-shower Local, u–w). */
function planeTooltip(ctx, seam) {
  const { numbering } = ctx;
  const deg = typographic(Number(ctx.tilt?.theta_deg ?? 0).toFixed(1));
  return [
    `<b>Layer plane ${groupLabel(numbering, seam.seam)} | ${groupLabel(numbering, seam.seam + 1)}</b>`,
    `between rel. layers ${seam.after} and ${seam.after + 1}, n·x′ = ${mm(seam.at, 2)} mm`,
    `tilted by this shower’s θ = ${deg}°: w = s / cos θ + u · tan θ`,
    'exact on u–w; on v–w the plane spans a band, not a line',
  ].join('<br/>');
}

/* -------------------------------------------------------------------- spec -- */

const DEPTH_PANELS = new Set(['yz', 'xz']);

function isVertical(normal) {
  return Array.isArray(normal) && Math.abs(normal[0]) <= EPS && Math.abs(normal[1]) <= EPS && normal[2] > 0;
}

/**
 * The layer context a depth panel reads its bin readout from - numbering,
 * native edges and the plane normal - whether or not a partition is drawn:
 * from an ensemble `depth_layers` block or an event frame's `layer_planes`.
 * Null for `xy` or with no layer data; `{numbering: 'none'}` for Local.
 */
export function panelLayerAxis({ panelId, depthLayers = null, layerPlanes = null }) {
  if (!DEPTH_PANELS.has(panelId)) return null;
  if (depthLayers) {
    if (depthLayers.numbering === 'none') return { numbering: 'none', symbol: depthLayers.symbol ?? 'w' };
    const edges = depthLayers.edges_mm;
    if (!Array.isArray(edges) || edges.length < 2) return null;
    return {
      source: 'ensemble',
      numbering: depthLayers.numbering === 'relative' ? 'relative' : 'detector',
      edges: [...edges],
      firstLayer: isWhole(depthLayers.first_layer) ? depthLayers.first_layer : 1,
      nBins: edges.length - 1,
      L: isWhole(depthLayers.partition_layers) ? depthLayers.partition_layers : null,
      symbol: depthLayers.symbol ?? 'z',
      offset: Number.isFinite(depthLayers.display_offset_mm) ? depthLayers.display_offset_mm : 0,
      normal: [0, 0, 1],
      geometry: 'vertical',
      contiguous: depthLayers.contiguous !== false,
      // The pooled operator: GeV per pitch on the Absolute frame's raw z, a width-weighted
      // mean in the co-registered frames (grid/layer_groups.py `pooled_operator`).
      weighting: (depthLayers.symbol ?? 'z') === 'z' ? 'per_pitch' : 'overlap',
      pitch: Number.isFinite(depthLayers.pitch_mm) ? depthLayers.pitch_mm : null,
    };
  }
  if (layerPlanes) {
    const edges = layerPlanes.edges_mm;
    if (!Array.isArray(edges) || edges.length < 2) return null;
    const normal = Array.isArray(layerPlanes.normal) && layerPlanes.normal.length === 3 ? [...layerPlanes.normal] : [0, 0, 1];
    const numbering = layerPlanes.numbering === 'relative' ? 'relative' : 'detector';
    const vertical = isVertical(normal);
    return {
      source: 'event',
      numbering,
      edges: [...edges],
      firstLayer: isWhole(layerPlanes.first_layer) ? layerPlanes.first_layer : 1,
      nBins: edges.length - 1,
      L: null,
      symbol: numbering === 'detector' ? 'z' : 'Δz',
      offset: Number.isFinite(layerPlanes.display_offset_mm) ? layerPlanes.display_offset_mm : 0,
      normal,
      geometry: vertical ? 'vertical' : 'tilted',
      linePanels: Array.isArray(layerPlanes.line_panels) ? [...layerPlanes.line_panels] : (vertical ? ['xz', 'yz'] : ['xz']),
      tilt: layerPlanes.tilt ?? null,
      startLayer: layerPlanes.start_layer ?? null,
      reachLayers: Number.isFinite(layerPlanes.reach_layers) ? layerPlanes.reach_layers : null,
    };
  }
  return null;
}

/**
 * The layer at a point of a depth panel, as the readout appends it:
 * " · layer 4", " · rel. layer 4", plus " · Ch 1 [1–5]" under a spec; on a
 * pooled raster " · Ch 1 [layers 1–5] · mean of 5 layers". `col` is the depth
 * (column) coordinate and `row` the row coordinate (used by a tilted plane on
 * u–w). '' where the panel has no layer at that point.
 */
export function layerReadout({ axis = null, spec = null, panelId, col, row }) {
  const ctx = axis ?? spec?.axis ?? null;
  if (!ctx || ctx.numbering === 'none' || !Array.isArray(ctx.edges)) return '';
  let s;
  if (ctx.geometry === 'tilted') {
    if (panelId !== 'xz') return '';
    s = ctx.normal[0] * row + ctx.normal[2] * col;
  } else {
    s = col;
  }
  const numbering = ctx.numbering;
  if (spec?.pooled && Array.isArray(spec.groups)) {
    const span = spec.groups.find((g) => s >= g.lo && s <= g.hi);
    if (!span) return '';
    const last = span.extended ? span.axisLast : span.last;
    return ` · ${groupLabel(numbering, span.group)} [${layersText(numbering, span.first, last)}] · `
      + pooledOperator(ctx, span).readout;
  }
  const bin = binOf(ctx.edges, s);
  if (bin === null) return '';
  const layer = ctx.firstLayer + bin;
  let text = ` · ${numbering === 'relative' ? 'rel. layer' : 'layer'} ${layer}`;
  if (spec && Array.isArray(spec.counts)) {
    const m = groupOfLayer(spec.counts, layer) ?? (layer > 0 ? GROUP_COUNT : null);
    const g = m ? groupRanges(spec.counts)[m - 1] : null;
    // Group 13 extended to the end of a longer axis holds the layers past L too.
    const span = m && Array.isArray(spec.groups) ? spec.groups.find((x) => x.group === m) : null;
    const last = span?.extended ? span.axisLast : g?.last;
    if (g) text += ` · ${groupLabel(numbering, m)} [${g.first === last ? g.first : `${g.first}–${last}`}]`;
  }
  return text;
}

/**
 * The spec of one depth panel: the one way callers build it.
 *
 * `mode` 'off' | 'bounds' | 'pool'; `counts` the partition; `panelId` 'yz' |
 * 'xz'; `depthLayers` an ensemble response's top-level block (section 2.2) or
 * `layerPlanes` one event frame's (section 2.3); `highlight` the spotlit
 * group or null; `onHover(group | null)` called from the strip; `nEvents`,
 * optional, printed beside the selection's shares. Null for mode 'off', for
 * `xy`, without layer data, or for a partition that does not fit the axis's L.
 */
export function panelGroupSpec({
  mode, counts, panelId, depthLayers = null, layerPlanes = null, highlight = null, onHover = null, nEvents = null,
}) {
  if (mode !== 'bounds' && mode !== 'pool') return null;
  const axis = panelLayerAxis({ panelId, depthLayers, layerPlanes });
  if (!axis) return null;
  const base = {
    kind: 'layer-groups', mode, panelId, highlight: isWhole(highlight) ? highlight : null,
    onHover: typeof onHover === 'function' ? onHover : null, mmPerUnit: 1,
  };
  if (axis.numbering === 'none') {
    return {
      ...base, counts: null, numbering: 'none', axis, pooled: false, strip: false, badge: LOCAL_BADGE,
      badgeShort: LOCAL_BADGE_SHORT, groups: [], seams: [], lines: [], lineReason: LOCAL_BADGE, seamsBeyond: 0, groupsBeyond: [],
    };
  }
  if (!isValidCounts(counts, axis.L)) return null;
  const pooledResponse = depthLayers?.groups?.pooled === true && sameCounts(depthLayers.groups.counts, counts);
  const pooled = mode === 'pool' && pooledResponse;
  const profile = depthLayers
    ? {
      energy: depthLayers.profile?.energy_gev ?? null,
      attention: depthLayers.profile?.attention ?? null,
      outside: depthLayers.profile?.outside_gev ?? null,
      total: depthLayers.profile?.total_gev ?? null,
      exact: depthLayers.profile?.exact !== false,
    }
    : { energy: layerPlanes?.energy_gev ?? null, attention: null, outside: null, total: null, exact: true };
  const ctx = {
    numbering: axis.numbering, symbol: axis.symbol, offset: axis.offset, profile, pooled,
    reach: depthLayers?.reach ?? null, reachLayers: axis.reachLayers ?? null,
    tilt: axis.geometry === 'tilted' ? axis.tilt : null, basis: depthLayers ? 'selection' : 'shower',
    nEvents: isWhole(nEvents) ? nEvents : null, axis, weighting: axis.weighting ?? null,
    // A block the server trimmed under the 100 KB guard (brief 9.1): no per-layer shares, no reach.
    trimmed: (depthLayers ?? layerPlanes)?.trimmed === true,
    reachTrimmed: Boolean(depthLayers) && axis.numbering === 'relative',
  };
  const spans = groupSpansOnAxis(axis.edges, counts, { firstLayer: axis.firstLayer });
  const seamList = seamsOnAxis(axis.edges, counts, { firstLayer: axis.firstLayer });
  const groupsBeyond = groupsBeyondAxis(axis.nBins, counts, { firstLayer: axis.firstLayer });
  const spec = {
    ...base,
    counts: [...counts],
    numbering: axis.numbering,
    axis,
    pooled,
    symbol: axis.symbol,
    offset: axis.offset,
    seamsBeyond: GROUP_COUNT - 1 - seamList.length,
    groupsBeyond,
    badge: null,
    lineReason: null,
    lines: [],
    strip: true,
    nEvents: ctx.nEvents,
    // The server's 100 KB trim (brief 9.1): the drawers quote `trimNote`.
    trimmed: ctx.trimmed,
    trimNote: ctx.trimmed ? ((depthLayers ?? layerPlanes)?.trim_note ?? null) : null,
  };
  if (axis.geometry === 'tilted') {
    // One shower in Local: the strip has no meaning along w, where a layer's w
    // range depends on u. The planes are lines on u–w only.
    // `faces` are the group's two planes along the normal (n·x′ = Δz); the
    // tooltip quotes them, and `lo`/`hi` stay null because no column interval
    // of the panel is the group.
    const groups = spans.map((s) => ({
      ...s, lo: null, hi: null, faces: [s.lo, s.hi], label: groupLabel(axis.numbering, s.group),
      tooltip: groupTooltip(ctx, s),
    }));
    spec.strip = false;
    spec.groups = groups;
    spec.seams = [];
    const lineable = axis.linePanels.includes(panelId) && planeLine(axis.normal, 0, panelId, [0, 1]) !== null;
    if (lineable) {
      spec.lines = seamList.map((s) => ({ ...s, normal: axis.normal, tooltip: planeTooltip(ctx, s) }));
    } else {
      const deg = typographic(Number(axis.tilt?.theta_deg ?? 0).toFixed(1));
      spec.lineReason = `v–w: a layer plane tilted by θ = ${deg}° spans a band here, not a line; `
        + 'the layer planes are drawn on u–w';
      // The badge is the short form, short enough for a narrow inspector panel; the drawer keeps the sentence.
      spec.badge = `v–w: planes tilt by θ = ${deg}°, drawn on u–w`;
    }
    return spec;
  }
  spec.groups = spans.map((s) => ({ ...s, label: groupLabel(axis.numbering, s.group), tooltip: groupTooltip(ctx, s) }));
  spec.seams = seamList.map((s) => ({ ...s, tooltip: seamTooltip(ctx, s) }));
  return spec;
}

/** A spec with another group spotlit (or none): the hover path, no other change. */
export function withHighlight(spec, group) {
  if (!spec) return spec;
  return { ...spec, highlight: isWhole(group) ? group : null };
}
