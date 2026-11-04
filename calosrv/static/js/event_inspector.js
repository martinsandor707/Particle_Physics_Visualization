/* The Event Inspector: one shower of one event in the original, translated
 * and local frames - the reference notebook's comparison figure
 * (`local-coords.ipynb`, cell 6), server-rendered.
 *
 * The event and the shower are view state (`#event=…&shower=…`), so a link
 * carries the picture; the filters still apply, and the previous / next
 * controls walk the selection. This controller owns the sidebar's picker, the
 * grid's label line and the nine cells' options; what the cells draw comes
 * whole from one `GET /api/event` response (query/event_inspector.py) - nine
 * quantised rasters, the marks as 3-D lines and points - never from hit rows.
 *
 * "Pick for me" reproduces the notebook's `_select_events`: a seeded draw
 * from the densest, most tilted events of the selection. The first click
 * uses the notebook's seed (42) and each later click the next one, so
 * repeated picks walk different events while every pick stays reproducible;
 * the response states the rule and the seed, and the sidebar shows it.
 *
 * Each row's two depth panels draw the Longitudinal Channels from the frame's
 * own `layer_planes`: detector layers in the original frame, relative layers
 * from the shower's first in the translated one, and in the local frame the
 * tilted layer planes on u-w with a badge on v-w, where a tilted plane has no
 * line image. One event is never pooled (the engine never pools an event
 * spec), and a new mode or partition is drawn from the response in hand.
 */

import { getJson } from './api.js';
import { setText, setHidden } from './dom.js';
import { eventRowLabel, eventSelectionLine } from './frame_views.js';
import { GRID_ROWS, GRID_COLS, DEPTH_COLS } from './panels/frame_grid.js';
import { gridReserve } from './panels/depth_groups.js';
import { EVENT_PANEL_AXES, eventCellTitle, eventCellOptions, eventLayerOptions } from './event_cells.js';

/* The cells' options and titles have one owner, event_cells.js, which the
 * Models page's 3-D event view shares; they keep their names here. Each
 * panel's two axes as semantic names: column (horizontal), row (vertical). */
export const PANEL_AXES = EVENT_PANEL_AXES;
/** The two symbols of a panel, in the panel's own order (X-Y, X-Z, Y-Z). */
export const cellTitle = eventCellTitle;
/**
 * The options one cell renders with: the frame's equal half-width window
 * for this panel's two axes, the frame's marks, the shower's colour, and a
 * framed, isometric plot (event_cells.js `eventCellOptions`).
 */
export const cellOptions = eventCellOptions;

/** The notebook's seed for the first pick; later picks take the next seeds. */
const FIRST_SEED = 42;

export class EventInspector {
  /**
   * @param {object} options
   *   `state` the interface State; `grid` the event `FrameGrid`; `palette()`
   *   the active colour map; `onRendered(payload)` after the nine panels are
   *   drawn; `onError(error, context)`; `onViewMode()` after the pinned state
   *   changed, so the page can swap the grids; `layerGroups(kind)` the
   *   Longitudinal Channels the page draws in that row's frame, `{mode,
   *   counts}`, or null for none.
   */
  constructor({ state, grid, palette, onRendered, onError, onViewMode, layerGroups }) {
    this.state = state;
    this.grid = grid;
    this.palette = palette || (() => 'viridis');
    this.onRendered = onRendered || (() => {});
    this.onError = onError || (() => {});
    this.onViewMode = onViewMode || (() => {});
    this.layerGroups = layerGroups || (() => null);
    this.payload = null;
    this.seed = FIRST_SEED;
    this.pickRule = null;
    this.dom = {
      number: document.getElementById('event-number'),
      prev: document.getElementById('event-prev'),
      next: document.getElementById('event-next'),
      pick: document.getElementById('event-pick'),
      close: document.getElementById('event-close'),
      gridClose: document.getElementById('event-grid-close'),
    };
    this.wire();
  }

  get pinned() {
    return this.state.get('event') !== null;
  }

  wire() {
    this.dom.number?.addEventListener('change', () => {
      const raw = this.dom.number.value.trim();
      if (raw === '') {
        this.unpin();
        return;
      }
      const n = Number(raw);
      if (Number.isInteger(n) && n >= 0) this.pin(n);
      else this.syncControls();
    });
    this.dom.prev?.addEventListener('click', () => this.step('prev'));
    this.dom.next?.addEventListener('click', () => this.step('next'));
    this.dom.pick?.addEventListener('click', () => this.pick());
    this.dom.close?.addEventListener('click', () => this.unpin());
    this.dom.gridClose?.addEventListener('click', () => this.unpin());
    for (const input of document.querySelectorAll('input[name="event-shower"]')) {
      input.addEventListener('change', () => {
        this.state.set({ shower: input.value });
        if (this.pinned) this.refresh();
      });
    }
  }

  /** Pin an event: the grid replaces the ensemble panels and the event is fetched. */
  pin(eventNumber, { rule = null } = {}) {
    this.pickRule = rule;
    this.state.set({ event: eventNumber });
    this.onViewMode();
    return this.refresh();
  }

  /** Back to the ensemble panels; the link loses its event. */
  unpin() {
    this.state.set({ event: null });
    this.pickRule = null;
    this.onViewMode();
  }

  /** The neighbouring event within the selection, as the last response named it. */
  step(direction) {
    const n = this.current?.event?.[direction];
    if (Number.isInteger(n)) this.pin(n);
  }

  /** The response on screen, if it is the pinned event's. */
  get current() {
    const event = this.state.get('event');
    return this.payload && this.payload.event?.event_number === event
      && this.payload.event?.shower?.key === this.state.get('shower') ? this.payload : null;
  }

  /** Fetch and draw the pinned event, reporting a failure without blanking the page. */
  async refresh() {
    if (!this.pinned) return null;
    this.grid.setBusy(true);
    try {
      return await this.load();
    } catch (error) {
      if (error?.name !== 'AbortError') this.onError(error, 'event inspector');
      this.syncControls();
      return null;
    } finally {
      this.grid.setBusy(false);
    }
  }

  async load() {
    if (!this.pinned) return null;
    let payload;
    try {
      payload = await getJson('/api/event', this.state.eventParams(), 'event');
    } catch (error) {
      // A refused event (another experiment's number, a shower with no cell)
      // must not leave the previous event's panels standing under the new
      // picker state: the rows are emptied and the label says what failed.
      if (error?.name !== 'AbortError') {
        this.payload = null;
        this.grid.render({});
        setText('event-grid-label', `Event ${this.state.get('event')} could not be drawn: ${error?.message ?? error}`);
        this.syncControls();
      }
      throw error;
    }
    this.payload = payload;
    this.render(payload);
    this.onRendered(payload);
    return payload;
  }

  /** The notebook's seeded selection rule, on the current filters. */
  async pick() {
    try {
      const payload = await getJson('/api/event/pick', { ...this.state.filterParams(), seed: this.seed }, 'event-pick');
      this.seed += 1;
      await this.pin(payload.event_number, { rule: payload.rule });
    } catch (error) {
      if (error?.name !== 'AbortError') this.onError(error, 'pick an event');
    }
  }

  /**
   * The `layer` argument of one row's cells (event_cells.js): the page's
   * mode and partition for the row's frame, and a hover that spotlights the
   * channel on the row's two depth panels together. Null for none.
   */
  layerOf(kind) {
    const drawn = this.layerGroups(kind);
    if (!drawn) return null;
    return { ...drawn, highlight: null, onHover: (group) => this.grid.highlightRow(kind, group) };
  }

  /**
   * Redraw every row's Longitudinal Channels from the response in hand - a
   * new mode, partition or live draft - with no request; each panel keeps
   * its displayed window.
   */
  repaintLayerGroups() {
    const payload = this.payload;
    if (!payload) return;
    const rows = this.rowSpecs(payload);
    this.grid.setLayerGroups(rows, gridReserve(Object.values(rows).flatMap((specs) => Object.values(specs))));
  }

  /** Each drawn row's depth specs, `{<kind>: {xz, yz}}`, under the page's mode and partition. */
  rowSpecs(payload) {
    const rows = {};
    for (const kind of GRID_ROWS) {
      if (!payload.frames?.[kind]) continue;
      const layer = this.layerOf(kind);
      const specs = {};
      for (const col of DEPTH_COLS) specs[col] = eventLayerOptions(payload, kind, col, layer).layerGroups ?? null;
      rows[kind] = specs;
    }
    return rows;
  }

  /** The specs the depth cells are drawn with, `{<kind>: {xz, yz}}`, for the drawer (panel_notes.js `eventNotes`). */
  layerSpecs() {
    const out = {};
    for (const kind of GRID_ROWS) {
      if (this.payload?.frames?.[kind]) out[kind] = this.grid.rowLayerGroups(kind);
    }
    return out;
  }

  /** Draw the nine panels from a response, and label the grid. */
  render(payload) {
    const palette = this.palette();
    const rows = {};
    // One band above all nine plots, the largest any depth spec reserves, so
    // the panels keep one millimetre-per-pixel scale with Boundaries on (UI-6).
    const reserveTop = gridReserve(Object.values(this.rowSpecs(payload)).flatMap((specs) => Object.values(specs)));
    for (const kind of GRID_ROWS) {
      const frame = payload.frames?.[kind];
      if (!frame) continue;
      const layer = this.layerOf(kind);
      const cells = {};
      for (const col of GRID_COLS) {
        cells[col] = {
          title: cellTitle(frame, col),
          payload: frame.panels[col],
          opts: { ...cellOptions(payload, kind, col, palette, layer), reserveTop },
          isometric: true,
        };
      }
      rows[kind] = { title: frame.title, cells };
    }
    this.grid.show(true);
    this.grid.render(rows);
    setText('event-grid-label', eventRowLabel(payload.event));
    this.syncControls();
  }

  /** What the export names the figure by: the response's meta, with the row's frame. */
  exportMeta(kind) {
    const payload = this.payload;
    if (!payload) return null;
    return {
      ...payload.meta,
      frame: kind === 'lab' ? undefined : kind,
      channel: 'density',
      event: payload.event.event_number,
      shower: payload.event.shower.key,
    };
  }

  /** Bring the picker into line with the state and the last response. */
  syncControls() {
    const event = this.state.get('event');
    const pinned = event !== null;
    if (this.dom.number) this.dom.number.value = pinned ? String(event) : '';
    for (const input of document.querySelectorAll('input[name="event-shower"]')) {
      input.checked = input.value === this.state.get('shower');
    }
    setText('event-status', pinned ? `event ${event}` : 'off');
    setHidden('event-close', !pinned);
    const current = this.current;
    if (this.dom.prev) this.dom.prev.disabled = !Number.isInteger(current?.event?.prev);
    if (this.dom.next) this.dom.next.disabled = !Number.isInteger(current?.event?.next);
    const lines = [];
    if (current) lines.push(eventSelectionLine(current.event));
    if (pinned && this.pickRule) lines.push(this.pickRule);
    setText('event-caption', lines.join(' '));
    setHidden('event-caption', lines.length === 0);
  }
}
