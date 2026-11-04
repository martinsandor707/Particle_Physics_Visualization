/* The Longitudinal Channels control: the sidebar block and its editor modal,
 * shared by the Physics and the Models page (brief §4.2).
 *
 * The partition itself - 13 contiguous groups of the experiment's L depth
 * layers - is the engine's (layer_groups.js); the view state that carries it
 * is state.js (`lgmode`, `lgroups`). This module only edits them:
 *
 * - **The sidebar.** Three mode radios (Off, Boundaries, Pooled), a mini bar
 *   of 13 segments whose widths are proportional to the layer counts, a
 *   summary line, and a notice. Pooled is disabled, with its reason, on the
 *   Models page (which draws boundaries only) and while the frame is Local
 *   (no common layer grid); the stored mode is kept either way, so a link
 *   means the same on both pages.
 * - **The modal.** A ribbon of L layer cells with 12 seam handles (role
 *   slider: pointer drag snapping to whole seams, the arrow, Home/End and
 *   Page keys), the selection's per-layer energy drawn faintly behind it, a
 *   layer scale above and a depth scale below in the frame's own symbol (Z
 *   for the Absolute frame); a 13-row table whose Start and End fields edit
 *   the same seams, clamping announced in the live region; presets, the
 *   last custom partition and a shorthand field. Every edit is a draft passed
 *   to `onDraft` - the page repaints from the payload in hand, with no
 *   request - until Apply writes the state; Cancel and Escape drop it.
 *
 * Positions on the ribbon are layer ordinals, and every depth printed is read
 * from the payload's stored edges, never an index times a pitch: on the demo
 * lattice some layers are 41 mm cells.
 *
 * The pure helpers are exported so Node can test them without a DOM; the
 * controller is driven by the browser tests. Imports no page module.
 */

import { ModalShell } from './modal.js';
import {
  GROUP_COUNT, PRESET_KEYS, PRESET_LABELS, countsToBoundaries, formatCounts, formatRanges,
  groupLabel, groupRanges, isValidCounts, parseCounts, parseShorthand, presetCounts, sameCounts,
  setGroupEnd, setGroupStart, uniformCounts,
} from '../layer_groups.js';
import { MINUS, typographic } from '../format.js';
import { LG_MODES } from '../state.js';

/** localStorage key of the viewer's last custom partition, one per layer count L. */
export const LG_STORAGE_KEY = 'calosrv.layerGroups.custom';

/** Why Pooled is not offered, by cause. */
export const POOL_REASONS = Object.freeze({
  models: 'Pooling re-bins the Physics page’s ensemble panels; this page draws boundaries.',
  local: 'Local: detector layers tilt by each shower’s (θ, φ); there is no common layer grid to pool.',
});

/** How far a Page key moves a seam, in layers. */
export const PAGE_STEP = 5;

/** How long a clamped field keeps its emphasis (no transition: the snap rule). */
const CLAMP_EMPHASIS_MS = 1500;

/* --------------------------------------------------------------- pure helpers */

/** Whether Pooled can be offered on `page` in `frame`, and why not. */
export function poolAvailability({ page, frame }) {
  if (page === 'models') return { enabled: false, reason: POOL_REASONS.models };
  if (frame === 'local') return { enabled: false, reason: POOL_REASONS.local };
  return { enabled: true, reason: null };
}

/**
 * The mode the panels draw: the stored mode, except that a page or frame that
 * cannot pool draws Boundaries in its place. The stored mode is not changed.
 */
export function effectiveMode(mode, context) {
  if (!LG_MODES.includes(mode)) return 'off';
  return mode === 'pool' && !poolAvailability(context).enabled ? 'bounds' : mode;
}

/** The numbering the labels use: the payload's, else the frame's (brief §1). */
export function numberingOf(context, frame) {
  if (context?.numbering) return context.numbering;
  if (frame === 'trans') return 'relative';
  if (frame === 'local') return 'none';
  return 'detector';
}

/** "Ch m" or "Rel Ch m"; the Local ensemble, with no layer grid, keeps "Ch m". */
export function channelLabel(numbering, m) {
  return groupLabel(numbering === 'relative' ? 'relative' : 'detector', m);
}

/** The preset a partition equals for L, or null for a custom one. */
export function matchPreset(counts, L) {
  if (!isValidCounts(counts, L)) return null;
  return PRESET_KEYS.find((key) => sameCounts(presetCounts(key, L), counts)) ?? null;
}

function layerSpan(first, last) {
  return first === last ? `layer ${first}` : `layers ${first}–${last}`;
}

/** The mini bar's 13 segments: flex weight ∝ layer count, alternating fills, a title each. */
export function barSegments(counts, { numbering = 'detector' } = {}) {
  return groupRanges(counts).map(({ group, first, last, n }) => ({
    group, first, last, n,
    grow: n,
    alt: group % 2 === 0,
    title: `${channelLabel(numbering, group)} · ${layerSpan(first, last)}`,
  }));
}

/** The sidebar's summary line, e.g. "13 channels over 60 layers · Uniform". */
export function summaryText(counts, L) {
  if (!isValidCounts(counts, L)) return '—';
  const preset = matchPreset(counts, L);
  return `${GROUP_COUNT} channels over ${L} layers · ${preset ? PRESET_LABELS[preset] : 'custom'}`;
}

/** A millimetre value as printed: at most two decimals, U+2212 for a negative. */
export function formatMm(value) {
  if (!Number.isFinite(value)) return '—';
  const rounded = Number(value.toFixed(2));
  return typographic(String(Object.is(rounded, -0) ? 0 : rounded));
}

/** The depth symbol printed: Z for raw z with a display offset, else the payload's own. */
export function depthSymbol(context) {
  if (!context) return null;
  if (context.symbol === 'z' && Number.isFinite(context.displayOffsetMm)) return 'Z';
  return context.symbol ?? null;
}

/**
 * The depth of the seam after `boundary` layers (0..L) in the printed
 * coordinate: the stored edge, less the display offset. Null without edges.
 */
export function depthAt(context, boundary) {
  const edges = context?.edgesMm;
  if (!Array.isArray(edges)) return null;
  const index = boundary - ((context.firstLayer ?? 1) - 1);
  const edge = edges[index];
  if (!Number.isFinite(edge)) return null;
  return edge - (Number.isFinite(context.displayOffsetMm) ? context.displayOffsetMm : 0);
}

/** "Z = 105.65 mm" for the seam after `boundary`, or null without edges. */
export function depthText(context, boundary) {
  const at = depthAt(context, boundary);
  const symbol = depthSymbol(context);
  return at === null || !symbol ? null : `${symbol} = ${formatMm(at)} mm`;
}

/**
 * The table's 13 rows: the group's layers, which of its fields are locked,
 * the range each editable field accepts, and its thickness from the stored
 * edges (null without them, never a count times a pitch).
 */
export function tableRows(counts, L, context = null) {
  const b = countsToBoundaries(counts);
  const numbering = context?.numbering ?? 'detector';
  return groupRanges(counts).map(({ group, first, last, n }) => {
    const lo = depthAt(context, first - 1);
    const hi = depthAt(context, last);
    const thickness = lo === null || hi === null ? null : hi - lo;
    return {
      group, first, last, n,
      label: channelLabel(numbering, group),
      alt: group % 2 === 0,
      startLocked: group === 1,
      endLocked: group === GROUP_COUNT,
      // Start of group m moves the seam after group m − 1; End of group m the seam after m.
      startMin: group === 1 ? 1 : (group >= 3 ? b[group - 3] : 0) + 2,
      startMax: group === 1 ? 1 : last,
      endMin: group === GROUP_COUNT ? L : first,
      endMax: group === GROUP_COUNT ? L : b[group] - 1,
      thicknessMm: thickness,
      thicknessText: thickness === null ? '—' : `${formatMm(thickness)} mm`,
    };
  });
}

/**
 * One seam handle (1..12, after group `seam`): its value (the last layer of
 * that group), its limits (each neighbour keeps a layer) and its ARIA text.
 */
export function seamModel(counts, seam, context = null) {
  const b = countsToBoundaries(counts);
  const numbering = context?.numbering ?? 'detector';
  const value = b[seam - 1];
  const min = (seam >= 2 ? b[seam - 2] : 0) + 1;
  const max = b[seam] - 1;
  const before = channelLabel(numbering, seam);
  const after = channelLabel(numbering, seam + 1);
  const depth = depthText(context, value);
  return {
    seam, value, min, max,
    label: `Seam between ${before} and ${after}`,
    valueText: `${before} ends at layer ${value}, ${after} starts at layer ${value + 1}`
      + (depth ? ` · seam at ${depth}` : ''),
  };
}

/**
 * The seam a key asks for, unclamped (the engine clamps and says so), or
 * null for a key the slider does not take. Arrows move one layer, Page keys
 * five, Home and End go to the neighbours' limits.
 */
export function seamKeyTarget(model, key) {
  switch (key) {
    case 'ArrowLeft': case 'ArrowDown': return model.value - 1;
    case 'ArrowRight': case 'ArrowUp': return model.value + 1;
    case 'PageDown': return model.value - PAGE_STEP;
    case 'PageUp': return model.value + PAGE_STEP;
    case 'Home': return model.min;
    case 'End': return model.max;
    default: return null;
  }
}

/** The whole seam nearest a pointer at `fraction` (0..1) along an L-cell ribbon. */
export function snapSeam(fraction, L) {
  if (!Number.isFinite(fraction)) return null;
  return Math.min(L, Math.max(0, Math.round(fraction * L)));
}

/**
 * What the live region says after an edit of one seam: the new layers of the
 * two groups it divides, or, when the engine clamped the request, the value
 * kept and why. `field` names what the reader edited ('end', 'start' or
 * 'seam'); `requested` is the layer they asked for.
 */
export function editAnnouncement(result, { seam, requested, field = 'end', numbering = 'detector' }) {
  const ranges = groupRanges(result.counts);
  const before = ranges[seam - 1];
  const after = ranges[seam];
  const left = channelLabel(numbering, seam);
  const right = channelLabel(numbering, seam + 1);
  if (result.clamped) {
    const kept = field === 'start'
      ? `${right} starts at layer ${after.first}`
      : `${left} ends at layer ${before.last}`;
    const asked = Number.isFinite(requested) ? `layer ${requested} was asked for` : 'the request was out of range';
    return `${kept}: ${asked}, but every channel keeps at least one layer.`;
  }
  return `${left}: ${layerSpan(before.first, before.last)}; ${right}: ${layerSpan(after.first, after.last)}.`;
}

/** The profile behind the ribbon: one height in [0, 1] per layer, or null with nothing to draw. */
export function profileHeights(profile, L, firstLayer = 1) {
  const values = profile?.energy_gev;
  if (!Array.isArray(values) || !Number.isInteger(L) || L < 1) return null;
  const offset = firstLayer - 1;
  const heights = Array.from({ length: L }, (_, k) => {
    const v = values[k - offset];
    return Number.isFinite(v) && v > 0 ? v : 0;
  });
  const peak = Math.max(...heights);
  return peak > 0 ? heights.map((v) => v / peak) : null;
}

/** The layer scale above the ribbon: layer 1, every tenth (fifth below 30 layers) and L. */
export function layerTicks(L, { numbering = 'detector' } = {}) {
  if (!Number.isInteger(L) || L < 1) return [];
  const step = L <= 30 ? 5 : 10;
  const layers = [1];
  for (let k = step; k <= L; k += step) layers.push(k);
  if (L - layers[layers.length - 1] >= Math.ceil(step / 2)) layers.push(L);
  const word = numbering === 'relative' ? 'rel. layer' : 'layer';
  return layers.map((layer, i) => ({ layer, at: (layer - 0.5) / L, text: i === 0 ? `${word} ${layer}` : String(layer) }));
}

/**
 * The depth scale below the ribbon: the seams at 0, every tenth layer (fifth
 * below 30) and L, each at its stored edge in the printed coordinate. The
 * first names the symbol and the unit. Empty without edges.
 */
export function depthTicks(context, L) {
  const symbol = depthSymbol(context);
  if (!symbol || !Number.isInteger(L) || L < 1) return [];
  const step = L <= 30 ? 5 : 10;
  const seams = [0];
  for (let b = step; b <= L; b += step) seams.push(b);
  if (L - seams[seams.length - 1] >= Math.ceil(step / 2)) seams.push(L);
  const ticks = [];
  for (const boundary of seams) {
    const at = depthAt(context, boundary);
    if (at === null) continue;
    ticks.push({ boundary, at: boundary / L, text: formatMm(at) });
  }
  if (ticks.length) ticks[0].text = `${symbol} = ${ticks[0].text} mm`;
  return ticks;
}

/** The modal's note on what the layers and the depth scale are, and what the background shows. */
export function depthNote(context, L, { frame = 'lab' } = {}) {
  const numbering = numberingOf(context, frame);
  const parts = [];
  if (numbering === 'none') {
    parts.push('Local: detector layers tilt by each shower’s (θ, φ), so the ensemble panels have no common layer grid and draw no seams; one shower’s views draw its own tilted layers.');
  } else if (numbering === 'relative') {
    parts.push(`Relative layers 1–${L}, counted from each shower’s own first layer.`);
  } else {
    parts.push(`Detector layers 1–${L}, counted along the lattice’s ordinals.`);
  }
  if (context?.contiguous === false) {
    parts.push('The lattice skips unpopulated layers, so a layer number is an ordinal, not a depth.');
  }
  const symbol = depthSymbol(context);
  if (symbol && Array.isArray(context?.edgesMm)) {
    const offset = Number.isFinite(context.displayOffsetMm)
      ? ` (Z = z ${MINUS} ${formatMm(context.displayOffsetMm)} mm)` : '';
    parts.push(`Seams sit at the stored cell edges; the lower scale gives their depth in ${symbol}${offset}.`);
  }
  const heights = profileHeights(context?.profile, L, context?.firstLayer ?? 1);
  if (heights) {
    parts.push(`The faint background is the selection’s energy per layer, relative to its peak layer${context.profile.exact === false ? ', from the preview sample' : ''}.`);
  }
  return parts.join(' ');
}

/**
 * The control's depth context from a payload in hand: an ensemble response's
 * `depth_layers` (brief §2.2) or one event frame's `layer_planes` (§2.3), as
 * the server spells them. Null for anything else. Local's ensemble block
 * (numbering `none`) carries no edges, so its ribbon has no depth scale.
 */
export function depthContextFromPayload(block) {
  if (!block || typeof block !== 'object' || !block.numbering) return null;
  const profile = block.profile
    ?? (Array.isArray(block.energy_gev) ? { energy_gev: block.energy_gev, exact: true } : null);
  // An event frame names no symbol: raw z with the lab offset, Δz along an
  // untilted normal; a tilted Local normal has no depth scale on this ribbon.
  const untilted = Array.isArray(block.normal) && block.normal[0] === 0 && block.normal[1] === 0;
  let symbol = block.symbol ?? null;
  if (!symbol && Number.isFinite(block.display_offset_mm)) symbol = 'z';
  else if (!symbol && block.numbering === 'relative' && untilted) symbol = 'Δz';
  return {
    numbering: block.numbering,
    edgesMm: Array.isArray(block.edges_mm) ? block.edges_mm : null,
    displayOffsetMm: Number.isFinite(block.display_offset_mm) ? block.display_offset_mm : null,
    symbol,
    profile,
    firstLayer: Number.isInteger(block.first_layer) ? block.first_layer : 1,
    contiguous: typeof block.contiguous === 'boolean' ? block.contiguous : null,
  };
}

/** The viewer's localStorage, or null where it is blocked (every access may throw). */
export function viewerStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function readCustomMap(storage) {
  try {
    const raw = storage?.getItem(LG_STORAGE_KEY);
    if (!raw) return {};
    const map = JSON.parse(raw);
    return map && typeof map === 'object' && !Array.isArray(map) ? map : {};
  } catch {
    return {};
  }
}

/** The last custom partition saved for L, or null (absent, blocked, corrupt or not fitting L). */
export function readLastCustom(storage, L) {
  try {
    const text = readCustomMap(storage)[String(L)];
    return typeof text === 'string' ? parseCounts(text, L) : null;
  } catch {
    return null;
  }
}

/** Remember `counts` as L's last custom partition. Returns whether it was stored. */
export function writeLastCustom(storage, counts, L) {
  if (!storage || !isValidCounts(counts, L)) return false;
  try {
    const map = readCustomMap(storage);
    map[String(L)] = formatCounts(counts);
    storage.setItem(LG_STORAGE_KEY, JSON.stringify(map));
    return true;
  } catch {
    return false;
  }
}

/** The patch Apply writes: null for Uniform, and Off becomes Boundaries. */
export function applyPatch(counts, L, mode) {
  const patch = { lgroups: sameCounts(counts, uniformCounts(L)) ? null : formatCounts(counts) };
  if (mode === 'off' || !LG_MODES.includes(mode)) patch.lgmode = 'bounds';
  return patch;
}

/** The sidebar's notices: the fallback of a link that did not fit L, and why Pooled is not offered. */
export function sidebarNotices(resolved, stored, { page, frame }) {
  const notices = [];
  if (resolved?.fallback) {
    notices.push(`This link’s channels (${stored}) do not fit this experiment’s ${resolved.L} layers: Uniform is drawn.`);
  }
  const pool = poolAvailability({ page, frame });
  if (!pool.enabled) {
    notices.push(resolved?.mode === 'pool' ? `${pool.reason} Boundaries are drawn instead.` : pool.reason);
  }
  return notices;
}

/* ----------------------------------------------------------------- controller */

class LayerGroupControl {
  constructor({ state, page, doc, onDraft }) {
    this.state = state;
    this.page = page === 'models' ? 'models' : 'physics';
    this.doc = doc;
    this.onDraft = typeof onDraft === 'function' ? onDraft : null;
    this.frame = state.get('frame');
    this.L = null;
    this.hiddenReason = 'The experiment has not been adopted yet.';
    this.available = true;
    this.unavailableReason = null;
    this.context = null;
    this.draft = null;
    this.builtFor = null;
    this.handles = [];
    this.cells = [];
    this.rowFields = [];
    this.dragging = null;
    this.dragClamped = false;
    this.destroyed = false;
    this.clampTimers = new Set();
    this.abort = new AbortController();

    this.el = {
      group: doc.getElementById('group-lgroups'),
      info: doc.getElementById('info-lgroups'),
      modes: {
        off: doc.getElementById('lgmode-off'),
        bounds: doc.getElementById('lgmode-bounds'),
        pool: doc.getElementById('lgmode-pool'),
      },
      poolLabel: doc.getElementById('lgmode-pool-label'),
      bar: doc.getElementById('lgroups-bar'),
      edit: doc.getElementById('lgroups-edit'),
      summary: doc.getElementById('lgroups-summary'),
      notice: doc.getElementById('lgroups-notice'),
      modal: doc.getElementById('lgroups-modal'),
      depthNote: doc.getElementById('lgroups-depth-note'),
      ribbonTop: doc.getElementById('lgroups-ribbon-top'),
      ribbon: doc.getElementById('lgroups-ribbon'),
      ribbonBottom: doc.getElementById('lgroups-ribbon-bottom'),
      presets: doc.getElementById('lgroups-presets'),
      presetCustom: doc.getElementById('lgroups-preset-custom'),
      shorthand: doc.getElementById('lgroups-shorthand'),
      shorthandApply: doc.getElementById('lgroups-shorthand-apply'),
      shorthandError: doc.getElementById('lgroups-shorthand-error'),
      rows: doc.getElementById('lgroups-rows'),
      live: doc.getElementById('lgroups-live'),
      reset: doc.getElementById('lgroups-reset'),
      cancel: doc.getElementById('lgroups-cancel'),
      apply: doc.getElementById('lgroups-apply'),
    };
    this.poolTitle = this.el.poolLabel?.getAttribute('title') ?? null;
    this.barLabel = this.el.bar?.getAttribute('aria-label') ?? null;

    this.shell = this.el.modal
      ? new ModalShell(this.el.modal, {
        onClose: () => this.endDraft(),
        initialFocus: () => this.handles[0] ?? null,
      })
      : null;

    this.wire();
    this.unsubscribe = state.subscribe((values, patch) => {
      if ('frame' in patch) this.frame = values.frame;
      if ('lgmode' in patch || 'lgroups' in patch || 'frame' in patch) this.sync();
    });
    this.sync();
  }

  /* ---- the sidebar */

  wire() {
    const { signal } = this.abort;
    const el = this.el;
    for (const radio of Object.values(el.modes)) {
      radio?.addEventListener('change', () => {
        if (radio.checked && LG_MODES.includes(radio.value)) this.state.set({ lgmode: radio.value });
      }, { signal });
    }
    el.edit?.addEventListener('click', () => this.open(), { signal });
    el.cancel?.addEventListener('click', () => this.shell?.close(), { signal });
    el.apply?.addEventListener('click', () => this.commit(), { signal });
    el.reset?.addEventListener('click', () => {
      if (!this.draft) return;
      this.setDraft(uniformCounts(this.L));
      this.announce(`Reset to Uniform: ${formatRanges(this.draft)}.`);
    }, { signal });
    el.presets?.addEventListener('click', (event) => {
      const button = event.target.closest?.('[data-preset]');
      if (button && this.draft) this.usePreset(button.dataset.preset);
    }, { signal });
    el.shorthandApply?.addEventListener('click', () => this.useShorthand(), { signal });
    el.shorthand?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        this.useShorthand();
      }
    }, { signal });
    this.doc.defaultView?.addEventListener('resize', () => {
      if (this.shell?.isOpen) this.drawProfile();
    }, { signal });
  }

  get visible() {
    return this.available && this.L !== null;
  }

  sync() {
    if (this.destroyed) return;
    const el = this.el;
    const resolved = this.state.layerGroups();
    if (el.group) {
      el.group.hidden = !this.visible;
      const reason = !this.available ? this.unavailableReason : this.hiddenReason;
      if (this.visible || !reason) delete el.group.dataset.reason;
      else el.group.dataset.reason = reason;
    }
    if (el.edit) el.edit.disabled = !this.visible;
    for (const [mode, radio] of Object.entries(el.modes)) {
      if (radio) radio.checked = resolved.mode === mode;
    }
    const pool = poolAvailability({ page: this.page, frame: this.frame });
    if (el.modes.pool) el.modes.pool.disabled = !pool.enabled;
    if (el.poolLabel) {
      el.poolLabel.classList.toggle('is-disabled', !pool.enabled);
      const title = pool.enabled ? this.poolTitle : pool.reason;
      if (title) el.poolLabel.setAttribute('title', title);
      else el.poolLabel.removeAttribute('title');
    }
    const notices = this.visible
      ? sidebarNotices(resolved, this.state.get('lgroups'), { page: this.page, frame: this.frame }) : [];
    if (el.notice) {
      el.notice.textContent = notices.join(' ');
      el.notice.hidden = notices.length === 0;
    }
    if (el.info) {
      el.info.dataset.notices = JSON.stringify(notices);
      el.info.hidden = notices.length === 0;
    }
    const counts = this.visible && isValidCounts(resolved.counts, this.L) ? resolved.counts : null;
    this.renderBar(counts);
    if (el.summary) el.summary.textContent = counts ? summaryText(counts, this.L) : '—';
  }

  renderBar(counts) {
    const bar = this.el.bar;
    if (!bar) return;
    bar.replaceChildren();
    if (!counts) {
      if (this.barLabel) bar.setAttribute('aria-label', this.barLabel);
      return;
    }
    const numbering = numberingOf(this.context, this.frame);
    for (const segment of barSegments(counts, { numbering })) {
      const node = this.doc.createElement('div');
      node.className = segment.alt ? 'lg-bar-seg is-alt' : 'lg-bar-seg';
      node.style.flexGrow = String(segment.grow);
      node.title = segment.title;
      bar.append(node);
    }
    bar.setAttribute('aria-label', `The 13 Longitudinal Channels: ${numbering === 'relative' ? 'relative ' : ''}layers ${formatRanges(counts)}`);
  }

  /* ---- the controller API */

  setExperiment({ nLayers } = {}) {
    const n = Number.isInteger(nLayers) ? nLayers : null;
    const L = n !== null && n >= GROUP_COUNT ? n : null;
    if (L !== this.L && this.shell?.isOpen) this.shell.close();
    this.L = L;
    this.state.setLayerCount?.(L);
    this.hiddenReason = n === null
      ? 'This experiment has no depth-layer lattice to group.'
      : (L === null ? `This experiment’s lattice has ${n} layers, fewer than the 13 channels.` : null);
    this.builtFor = null;
    this.sync();
  }

  setFrame(frameKey) {
    this.frame = frameKey;
    this.sync();
    if (this.shell?.isOpen) this.renderModal();
  }

  setDepthContext({ numbering = null, edgesMm = null, displayOffsetMm = null, symbol = null, profile = null,
    firstLayer = 1, contiguous = null } = {}) {
    this.context = {
      numbering, edgesMm: Array.isArray(edgesMm) ? edgesMm : null,
      displayOffsetMm: Number.isFinite(displayOffsetMm) ? displayOffsetMm : null,
      symbol, profile, firstLayer: Number.isInteger(firstLayer) ? firstLayer : 1, contiguous,
    };
    this.sync();
    if (this.shell?.isOpen) this.renderModal();
  }

  setAvailable(available, reason = null) {
    this.available = Boolean(available);
    this.unavailableReason = this.available ? null : (reason || 'Not available for this experiment.');
    if (!this.available && this.shell?.isOpen) this.shell.close();
    this.sync();
  }

  resolved() {
    return this.state.layerGroups();
  }

  destroy() {
    if (this.shell?.isOpen) this.shell.close();
    this.destroyed = true;
    this.abort.abort();
    this.unsubscribe?.();
    for (const timer of this.clampTimers) clearTimeout(timer);
    this.clampTimers.clear();
  }

  /* ---- the modal */

  open() {
    if (!this.visible || !this.shell || this.shell.isOpen) return;
    const resolved = this.state.layerGroups();
    this.draft = (isValidCounts(resolved.counts, this.L) ? resolved.counts : uniformCounts(this.L)).slice();
    if (this.builtFor !== this.L) this.build();
    if (this.el.shorthandError) this.el.shorthandError.hidden = true;
    this.el.shorthand?.removeAttribute('aria-invalid');
    if (this.el.presetCustom) this.el.presetCustom.hidden = !readLastCustom(viewerStorage(), this.L);
    if (this.el.live) this.el.live.textContent = '';
    this.renderModal();
    this.shell.open();
    // The canvas has a size only once the dialog is laid out.
    this.drawProfile();
  }

  endDraft() {
    if (this.destroyed) return;
    this.stopDrag();
    this.draft = null;
    this.onDraft?.(null);
  }

  commit() {
    if (!this.draft || !this.visible) return;
    const counts = this.draft.slice();
    if (matchPreset(counts, this.L) === null) writeLastCustom(viewerStorage(), counts, this.L);
    this.state.set(applyPatch(counts, this.L, this.state.get('lgmode')));
    this.shell.close();
  }

  setDraft(counts) {
    if (!isValidCounts(counts, this.L)) return;
    this.draft = counts.slice();
    // A draft from a preset, the table or a handle replaces what the shorthand last refused.
    if (this.el.shorthandError) this.el.shorthandError.hidden = true;
    this.el.shorthand?.removeAttribute('aria-invalid');
    this.renderModal();
    this.onDraft?.(this.draft.slice());
  }

  usePreset(key) {
    const counts = key === 'custom' ? readLastCustom(viewerStorage(), this.L) : presetCounts(key, this.L);
    if (!counts) return;
    this.setDraft(counts);
    this.announce(`${key === 'custom' ? 'Last custom' : PRESET_LABELS[key]}: layers ${formatRanges(counts)}.`);
  }

  useShorthand() {
    const input = this.el.shorthand;
    if (!input || !this.draft) return;
    const result = parseShorthand(input.value, this.L);
    const error = this.el.shorthandError;
    if (result.error) {
      if (error) {
        error.textContent = typographic(result.error);
        error.hidden = false;
      }
      input.setAttribute('aria-invalid', 'true');
      return;
    }
    if (error) error.hidden = true;
    input.removeAttribute('aria-invalid');
    this.setDraft(result.counts);
    input.value = formatRanges(this.draft);
    this.announce(`Shorthand used: layers ${formatRanges(this.draft)}.`);
  }

  announce(text) {
    const live = this.el.live;
    if (!live) return;
    const message = typographic(text);
    // The same sentence twice is still a new announcement.
    live.textContent = live.textContent === message ? `${message} ` : message;
  }

  /** Build the ribbon's cells and handles and the table's rows, once per L. */
  build() {
    const { doc, L } = this;
    const { signal } = this.abort;
    const ribbon = this.el.ribbon;
    this.cells = [];
    this.handles = [];
    this.rowFields = [];
    if (ribbon) {
      ribbon.replaceChildren();
      this.canvas = doc.createElement('canvas');
      this.canvas.className = 'lg-profile';
      this.canvas.setAttribute('aria-hidden', 'true');
      ribbon.append(this.canvas);
      for (let layer = 1; layer <= L; layer += 1) {
        const cell = doc.createElement('div');
        cell.className = 'lg-cell';
        ribbon.append(cell);
        this.cells.push(cell);
      }
      for (let seam = 1; seam < GROUP_COUNT; seam += 1) {
        const handle = doc.createElement('div');
        handle.className = 'lg-handle';
        handle.tabIndex = 0;
        handle.setAttribute('role', 'slider');
        handle.setAttribute('aria-orientation', 'horizontal');
        handle.addEventListener('keydown', (event) => this.onHandleKey(seam, event), { signal });
        handle.addEventListener('pointerdown', (event) => this.startDrag(seam, handle, event), { signal });
        handle.addEventListener('pointermove', (event) => this.moveDrag(seam, event), { signal });
        handle.addEventListener('pointerup', () => this.stopDrag(), { signal });
        handle.addEventListener('pointercancel', () => this.stopDrag(), { signal });
        ribbon.append(handle);
        this.handles.push(handle);
      }
    }
    const rows = this.el.rows;
    if (rows) {
      rows.replaceChildren();
      for (let group = 1; group <= GROUP_COUNT; group += 1) {
        const tr = doc.createElement('tr');
        const name = doc.createElement('td');
        const start = doc.createElement('td');
        const end = doc.createElement('td');
        const num = doc.createElement('td');
        const mm = doc.createElement('td');
        start.className = 'lg-start';
        end.className = 'lg-end';
        num.className = 'lg-num';
        mm.className = 'lg-mm';
        const startInput = this.numberInput(group, 'start', signal);
        const endInput = this.numberInput(group, 'end', signal);
        start.append(startInput);
        end.append(endInput);
        tr.append(name, start, end, num, mm);
        rows.append(tr);
        this.rowFields.push({ tr, name, start, end, num, mm, startInput, endInput });
      }
    }
    this.builtFor = L;
  }

  numberInput(group, field, signal) {
    const input = this.doc.createElement('input');
    input.type = 'number';
    input.step = '1';
    input.inputMode = 'numeric';
    const locked = (field === 'start' && group === 1) || (field === 'end' && group === GROUP_COUNT);
    if (locked) {
      input.disabled = true;
    } else {
      input.addEventListener('change', () => this.onFieldChange(group, field, input), { signal });
    }
    return input;
  }

  renderModal() {
    if (!this.draft || this.builtFor !== this.L) return;
    const { L, draft } = this;
    const context = this.contextForLabels();
    const numbering = context.numbering;
    if (this.el.depthNote) this.el.depthNote.textContent = depthNote(this.context, L, { frame: this.frame });

    const ranges = groupRanges(draft);
    for (const { group, first, last } of ranges) {
      for (let layer = first; layer <= last; layer += 1) {
        const cell = this.cells[layer - 1];
        if (!cell) continue;
        cell.className = group % 2 === 0 ? 'lg-cell is-alt' : 'lg-cell';
        cell.title = `Layer ${layer} · ${channelLabel(numbering, group)}`;
      }
    }
    this.handles.forEach((handle, i) => {
      const model = seamModel(draft, i + 1, context);
      handle.style.left = `${(model.value / L) * 100}%`;
      handle.setAttribute('aria-label', model.label);
      handle.setAttribute('aria-valuemin', String(model.min));
      handle.setAttribute('aria-valuemax', String(model.max));
      handle.setAttribute('aria-valuenow', String(model.value));
      handle.setAttribute('aria-valuetext', typographic(model.valueText));
    });

    tableRows(draft, L, context).forEach((row, i) => {
      const fields = this.rowFields[i];
      if (!fields) return;
      fields.tr.className = row.alt ? 'lg-row is-alt' : 'lg-row';
      fields.name.textContent = row.label;
      fields.start.classList.toggle('lg-locked', row.startLocked);
      fields.end.classList.toggle('lg-locked', row.endLocked);
      this.fillInput(fields.startInput, row.first, row.startMin, row.startMax,
        `${row.label} start layer`, row.startLocked ? `${row.label} always starts at layer 1.` : null);
      this.fillInput(fields.endInput, row.last, row.endMin, row.endMax,
        `${row.label} end layer`, row.endLocked ? `${row.label} always ends at layer ${L}.` : null);
      fields.num.textContent = String(row.n);
      fields.mm.textContent = row.thicknessText;
      fields.mm.title = row.thicknessMm === null
        ? 'Depth thickness appears once a panel payload carries the layer edges.'
        : 'From the stored cell edges of this frame’s depth axis.';
    });

    const preset = matchPreset(draft, L);
    for (const button of this.el.presets?.querySelectorAll('[data-preset]') ?? []) {
      const key = button.dataset.preset;
      const pressed = key === 'custom'
        ? preset === null && sameCounts(readLastCustom(viewerStorage(), L), draft)
        : key === preset;
      button.setAttribute('aria-pressed', pressed ? 'true' : 'false');
    }
    const shorthand = this.el.shorthand;
    if (shorthand && this.doc.activeElement !== shorthand) shorthand.value = formatRanges(draft);

    this.renderScales(numbering);
    this.drawProfile();
  }

  /** The depth context with the frame's numbering filled in, for the labels. */
  contextForLabels() {
    return { ...(this.context ?? {}), numbering: numberingOf(this.context, this.frame) };
  }

  fillInput(input, value, min, max, label, lockedTitle) {
    if (this.doc.activeElement !== input) input.value = String(value);
    input.min = String(min);
    input.max = String(max);
    input.setAttribute('aria-label', label);
    if (lockedTitle) input.title = lockedTitle;
  }

  renderScales(numbering) {
    const tick = (host, { at, text }) => {
      const node = this.doc.createElement('span');
      node.className = 'lg-scale-tick';
      node.style.left = `${at * 100}%`;
      // The end labels anchor inward, so neither is clipped by the ribbon's box.
      if (at <= 0) node.style.transform = 'none';
      else if (at >= 1) node.style.transform = 'translateX(-100%)';
      node.textContent = text;
      host.append(node);
    };
    const top = this.el.ribbonTop;
    if (top) {
      top.replaceChildren();
      for (const t of layerTicks(this.L, { numbering })) tick(top, t);
    }
    const bottom = this.el.ribbonBottom;
    if (bottom) {
      bottom.replaceChildren();
      for (const t of depthTicks(this.context, this.L)) tick(bottom, t);
    }
  }

  drawProfile() {
    const canvas = this.canvas;
    if (!canvas || !this.draft) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const ratio = this.doc.defaultView?.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    const ctx = canvas.getContext?.('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const heights = profileHeights(this.context?.profile, this.L, this.context?.firstLayer ?? 1);
    if (!heights || width <= 0 || height <= 0) return;
    // The colour is the stylesheet's (--lg-profile, through the canvas's `color`).
    ctx.fillStyle = this.doc.defaultView?.getComputedStyle(canvas).color || 'currentColor';
    const cell = canvas.width / this.L;
    heights.forEach((h, k) => {
      if (h <= 0) return;
      const barHeight = h * canvas.height;
      ctx.fillRect(k * cell, canvas.height - barHeight, Math.max(1, cell - ratio), barHeight);
    });
  }

  /* ---- editing */

  editSeam(seam, requested, field) {
    if (!this.draft) return null;
    const result = field === 'start'
      ? setGroupStart(this.draft, seam + 1, requested)
      : setGroupEnd(this.draft, seam, requested);
    if (!isValidCounts(result?.counts, this.L)) return null;
    if (!sameCounts(result.counts, this.draft)) this.setDraft(result.counts);
    else this.renderModal();
    return result;
  }

  onHandleKey(seam, event) {
    if (!this.draft) return;
    const model = seamModel(this.draft, seam, this.contextForLabels());
    const target = seamKeyTarget(model, event.key);
    if (target === null) return;
    event.preventDefault();
    const result = this.editSeam(seam, target, 'seam');
    if (result?.clamped) {
      this.announce(editAnnouncement(result, { seam, requested: target, field: 'end', numbering: this.contextForLabels().numbering }));
    }
  }

  startDrag(seam, handle, event) {
    if (!this.draft || event.button > 0) return;
    event.preventDefault();
    this.dragging = { seam, handle };
    this.dragClamped = null;
    handle.classList.add('is-dragging');
    handle.focus();
    try {
      handle.setPointerCapture(event.pointerId);
    } catch {
      // A synthetic pointer has no capture; the drag still follows the handle's own events.
    }
  }

  moveDrag(seam, event) {
    if (!this.dragging || this.dragging.seam !== seam || !this.draft || !this.el.ribbon) return;
    const rect = this.el.ribbon.getBoundingClientRect();
    if (rect.width <= 0) return;
    const target = snapSeam((event.clientX - rect.left) / rect.width, this.L);
    const current = countsToBoundaries(this.draft)[seam - 1];
    if (target === null || target === current) return;
    const result = this.editSeam(seam, target, 'seam');
    // One announcement per drag, at release, for a drag that ran into a limit.
    if (result?.clamped) this.dragClamped = { result, requested: target };
  }

  stopDrag() {
    const drag = this.dragging;
    if (!drag) return;
    this.dragging = null;
    drag.handle.classList.remove('is-dragging');
    if (this.dragClamped && this.draft) {
      const { requested } = this.dragClamped;
      const result = { counts: this.draft, clamped: true };
      this.announce(editAnnouncement(result, { seam: drag.seam, requested, field: 'end', numbering: this.contextForLabels().numbering }));
    }
    this.dragClamped = null;
  }

  onFieldChange(group, field, input) {
    if (!this.draft) return;
    const raw = input.value.trim();
    const requested = Number(raw);
    const seam = field === 'start' ? group - 1 : group;
    const numbering = this.contextForLabels().numbering;
    if (!raw || !Number.isInteger(requested)) {
      input.value = '';
      this.renderModal();
      this.emphasise(input);
      this.announce(`${channelLabel(numbering, group)} ${field}: enter a whole layer number; it was kept.`);
      return;
    }
    const result = this.editSeam(seam, requested, field);
    if (!result) return;
    // The focused field is skipped by renderModal, so it takes the realised value here.
    const range = groupRanges(this.draft)[group - 1];
    input.value = String(field === 'start' ? range.first : range.last);
    if (result.clamped) this.emphasise(input);
    this.announce(editAnnouncement(result, { seam, requested, field, numbering }));
  }

  /** A brief outline on a field the editor moved, set and cleared with no transition. */
  emphasise(input) {
    const cell = input.closest('td');
    cell?.classList.add('lg-clamped');
    const timer = setTimeout(() => {
      cell?.classList.remove('lg-clamped');
      this.clampTimers.delete(timer);
    }, CLAMP_EMPHASIS_MS);
    this.clampTimers.add(timer);
  }
}

/**
 * Mount the control on a page's markup (brief §5 ids) and return its
 * controller: `setExperiment({nLayers})`, `setFrame(frameKey)`,
 * `setDepthContext({numbering, edgesMm, displayOffsetMm, symbol, profile})`
 * (from the payload in hand; `firstLayer` and `contiguous` are optional),
 * `setAvailable(bool, reason)`, `resolved()` and `destroy()`.
 *
 * `onDraft(counts)` receives every live edit in the modal, and `null` when the
 * modal closes (after Apply has written the state, or on Cancel / Escape):
 * the page then draws from the state again. Neither costs a request.
 */
export function mountLayerGroupControl({ state, page, doc = document, onDraft = null }) {
  return new LayerGroupControl({ state, page, doc, onDraft });
}
