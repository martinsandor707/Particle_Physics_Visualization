/* The Event Inspector: one shower of one event in the original, translated
 * and local frames - the reference notebook's comparison figure
 * (`local-coords.ipynb`, cell 6), server-rendered.
 *
 * The event and the shower are view state (`#event=…&shower=…`), so a link
 * carries the picture; the filters still apply, and the previous / next
 * controls walk the candidates - the selection, the frame gate and the
 * particle filter (event_picker.js). This controller owns the sidebar's
 * picker, the grid's label line, its "Open in 3-D" link and the nine cells'
 * options; what the cells draw comes whole from one `GET /api/event` response
 * (query/event_inspector.py) - nine quantised rasters, the marks as 3-D lines
 * and points - never from hit rows.
 *
 * Two pickers draw from the candidates. "Pick for me" is the uniform rule: a
 * seeded shuffle of the candidates in event-number order (seed 42), each
 * click the next draw, so no event repeats until all have been drawn; the
 * draw counter carries on across filter and particle commits (entry k of a
 * fresh shuffle is as uniform as entry 1, and a restart would replay entry 1
 * after a commit that left the pool as it was) and starts again only on an
 * experiment switch. "Most tilted" reproduces the
 * notebook's `_select_events`, a seeded draw from the densest, most tilted
 * candidates, each click the next seed from 42. Every response states its
 * rule, seed and draw, and the caption shows it. The requests are built by
 * event_picker.js `pickParams`, and every sentence comes from there.
 *
 * Where the pinned event came from is remembered in memory (a link, typed, a
 * pick, Most tilted, a step, a replacement). After a filter or particle
 * commit the pinned event's fresh response decides (`followDecision`): kept
 * while it is a candidate, replaced by the next uniform draw when the page
 * chose it itself, else drawn as asked and flagged. A picker asks for a
 * matching shower (`focusShower`) in the event's first request; a shower
 * chosen by hand is drawn as asked. With no candidate (N = 0) the pickers and
 * the steps are shut, their title the reason, and a 404 from the pick is that
 * empty state, never an error.
 *
 * Each row's two depth panels draw the Longitudinal Channels from the frame's
 * own `layer_planes`: detector layers in the original frame, relative layers
 * from the shower's first in the translated one, and in the local frame the
 * tilted layer planes on u-w with a badge on v-w, where a tilted plane has no
 * line image. One event is never pooled (the engine never pools an event
 * spec), and a new mode or partition is drawn from the response in hand.
 */

import { getJson, isAbort } from './api.js';
import { setText, setHidden } from './dom.js';
import { eventRowLabel, eventSelectionLine } from './frame_views.js';
import { wireLiveLinks } from './page_common.js';
import {
  FIRST_SEED, pickParams, followDecision, focusShower, emptyLine, placeLine, matchLine, replacedLine,
  pickerTitle, open3dTitle, eventIn3dHref, STEP_TITLES,
} from './event_picker.js';
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

/** Where a pinned event can come from (brief section 8.1); `link` is the hash at load. */
export const ORIGINS = Object.freeze(['link', 'typed', 'pick', 'tilted', 'step', 'replace']);

/** The current hash, wherever the page runs (a browser, or a test's fake window). */
function currentHash() {
  return globalThis.window?.location?.hash ?? globalThis.location?.hash ?? '';
}

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
    // Most tilted's seed: 42 first, then the next one per click, never reset.
    this.seed = FIRST_SEED;
    // Pick for me's draw: the k-th entry of the seeded shuffle; carried across commits, 0 on an experiment switch.
    this.draw = 0;
    // The pinned event's origin (ORIGINS), in memory only: a link's event is the reader's own.
    this.origin = state.get('event') !== null ? 'link' : null;
    // The pick that pinned the event: its rule sentence, for the caption.
    this.pickRule = null;
    // A replacement's two event numbers, while the replacement is pinned.
    this.replaced = null;
    // Whether the next load follows a commit (the follow policy applies to its response).
    this.followNext = false;
    // The last GET /api/event/candidates payload (the sidebar block's), and the showers per event.
    this.candidates = null;
    this.nShowers = 2;
    // The server's reason when a pick found no candidate (404) before the counts said so.
    this.pickRefused = null;
    this.dom = {
      number: document.getElementById('event-number'),
      prev: document.getElementById('event-prev'),
      next: document.getElementById('event-next'),
      pick: document.getElementById('event-pick'),
      tilted: document.getElementById('event-pick-tilted'),
      close: document.getElementById('event-close'),
      gridClose: document.getElementById('event-grid-close'),
      open3d: document.getElementById('event-open-3d'),
    };
    // The steps' own titles (event_picker.js STEP_TITLES, which the markup
    // carries too), given back when the candidates are no longer empty.
    this.stepTitles = { prev: STEP_TITLES.prev, next: STEP_TITLES.next };
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
      if (Number.isInteger(n) && n >= 0) this.pin(n, { origin: 'typed' });
      else this.syncControls();
    });
    this.dom.prev?.addEventListener('click', () => this.step('prev'));
    this.dom.next?.addEventListener('click', () => this.step('next'));
    this.dom.pick?.addEventListener('click', () => this.pick('uniform'));
    this.dom.tilted?.addEventListener('click', () => this.pick('tilted'));
    this.dom.close?.addEventListener('click', () => this.unpin());
    this.dom.gridClose?.addEventListener('click', () => this.unpin());
    for (const input of document.querySelectorAll('input[name="event-shower"]')) {
      input.addEventListener('change', () => {
        // A shower chosen by hand is drawn as asked; the caption says whether it matches.
        this.state.set({ shower: input.value });
        if (this.pinned) this.refresh();
      });
    }
    // "Open in 3-D": its href is rebuilt from the hash at the moment it is followed or copied.
    if (this.dom.open3d) wireLiveLinks([this.dom.open3d], () => this.open3dHref());
  }

  /**
   * Pin an event: the grid replaces the ensemble panels and the event is
   * fetched. `origin` is where it came from (ORIGINS); `shower` the shower a
   * picker focused, asked for in this first request; `rule` the pick's rule
   * sentence; `replaced` the event a replacement takes the place of.
   */
  pin(eventNumber, { origin = 'typed', shower = null, rule = null, replaced = null } = {}) {
    this.origin = origin;
    this.pickRule = rule;
    this.replaced = replaced === null || replaced === undefined ? null : { old: replaced, now: eventNumber };
    this.followNext = false;
    this.state.set(shower ? { event: eventNumber, shower } : { event: eventNumber });
    this.onViewMode();
    return this.refresh();
  }

  /** Back to the ensemble panels; the link loses its event. */
  unpin() {
    this.state.set({ event: null });
    this.origin = null;
    this.pickRule = null;
    this.replaced = null;
    this.followNext = false;
    this.onViewMode();
  }

  /**
   * The neighbouring candidate, as the last response named it, with a
   * matching shower asked for from the response's `prev_matched` /
   * `next_matched`.
   */
  step(direction) {
    const event = this.current?.event;
    const n = event?.[direction];
    if (!Number.isInteger(n)) return null;
    const matched = event.candidates?.[`${direction}_matched`] ?? null;
    const shower = focusShower({ current: this.state.get('shower'), matched });
    return this.pin(n, { origin: 'step', shower });
  }

  /** The response on screen, if it is the pinned event's. */
  get current() {
    const event = this.state.get('event');
    return this.payload && this.payload.event?.event_number === event
      && this.payload.event?.shower?.key === this.state.get('shower') ? this.payload : null;
  }

  /* -------------------------------------------------- the candidates -- */

  /** The experiment's showers per event, for the caption's sentences; a switch starts the draws again. */
  setExperiment({ nShowers = 2 } = {}) {
    this.nShowers = nShowers === 1 ? 1 : 2;
    this.candidates = null;
    this.pickRefused = null;
    this.draw = 0;
    this.syncControls();
  }

  /** A candidates payload from the sidebar block: N for the place line, N = 0 for the pickers. */
  setCandidates(payload) {
    this.candidates = payload ?? null;
    this.pickRefused = null;
    this.syncControls();
  }

  /**
   * After an E1, E2 or D commit: the candidates may change, so the pinned
   * event's next load (the page's refresh) applies the follow policy. The
   * draw counter carries on; the pick's rule sentence and a replacement's
   * line go, since they named the previous pool.
   */
  filtersCommitted() {
    this.pickRule = null;
    this.replaced = null;
    this.followNext = this.pinned;
  }

  /**
   * After a particle commit (the block has already refreshed its count): the
   * pinned event alone is asked for again, under the follow policy. Nothing
   * else is requested. The draw counter carries on; the pick's rule sentence
   * and a replacement's line go.
   */
  particleCommitted() {
    this.pickRule = null;
    this.replaced = null;
    if (!this.pinned) {
      this.syncControls();
      return Promise.resolve(null);
    }
    this.followNext = true;
    return this.refresh();
  }

  /** The reason every picker is shut ('' while there are candidates): the empty pool's line. */
  emptyReason() {
    const line = this.candidates ? emptyLine(this.candidates, { nShowers: this.nShowers }) : '';
    return line || this.pickRefused || '';
  }

  /** "Open in 3-D"'s href: this event and shower on the Models page, with the hash as it stands. */
  open3dHref() {
    return eventIn3dHref({
      hash: currentHash(),
      event: this.state.get('event'),
      shower: this.state.get('shower'),
      frame: this.state.get('frame'),
    });
  }

  /* ---------------------------------------------------------- loading -- */

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
    const follow = this.followNext;
    this.followNext = false;
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
    // After a commit the fresh response decides: keep, replace or flag (brief section 8.1).
    // A flagged event is drawn as asked; its caption and drawer say it is no candidate.
    if (follow && this.followsAway(payload)) {
      const old = this.state.get('event');
      const replacement = await this.replace(payload.event?.event_number ?? old);
      // Pinned elsewhere: the replacement speaks. Otherwise no draw could be
      // made, and the event stays, drawn as asked.
      if (this.state.get('event') !== old) return replacement;
    }
    this.payload = payload;
    this.render(payload);
    this.onRendered(payload);
    return payload;
  }

  /** Whether the follow policy replaces the event of this response. */
  followsAway(payload) {
    const candidates = payload?.event?.candidates ?? null;
    return followDecision({
      origin: this.origin,
      inPool: candidates?.in_pool ?? null,
      nEvents: candidates?.n_events ?? null,
    }) === 'replace';
  }

  /** The pinned event left the candidates: the next uniform draw takes its place. */
  replace(oldEvent) {
    return this.pick('uniform', { replacing: oldEvent });
  }

  /**
   * One pick under the filters and the particle filter: `uniform` (Pick for
   * me) at the next draw of the seeded shuffle, `tilted` (Most tilted) at the
   * next seed. The shower asked for is a matching one. A 404 is the empty
   * state (no candidate), never an error.
   */
  async pick(rule = 'uniform', { replacing = null } = {}) {
    const params = pickParams({
      filters: this.state.filterParams(),
      particle: this.state.particleParams(),
      rule,
      seed: rule === 'uniform' ? FIRST_SEED : this.seed,
      draw: this.draw,
    });
    let payload;
    try {
      payload = await getJson('/api/event/pick', params, 'event-pick');
    } catch (error) {
      if (isAbort(error)) return null;
      if (error?.status === 404) {
        // No candidate: the pickers are shut with the reason, and nothing is pinned.
        this.pickRefused = error.message || 'No candidate event.';
        this.syncControls();
        return null;
      }
      this.onError(error, 'pick an event');
      return null;
    }
    // A replacement draw that lands after the reader moved on (typed or stepped
    // to another event while it was in flight) replaces nothing: the event the
    // reader chose is never swapped out. The draw is not counted.
    if (replacing !== null && replacing !== undefined && this.state.get('event') !== replacing) return null;
    if (rule === 'uniform') this.draw += 1;
    else this.seed += 1;
    const shower = focusShower({ current: this.state.get('shower'), matched: payload.matched });
    const replaced = replacing === null || replacing === undefined ? null : replacing;
    return this.pin(payload.event_number, {
      origin: replaced !== null ? 'replace' : (rule === 'uniform' ? 'pick' : 'tilted'),
      shower,
      rule: payload.rule,
      replaced,
    });
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

  /** Bring the picker into line with the state, the last response and the candidates. */
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
    // N = 0: every picker and step is shut, its title the reason; the titles return with N > 0.
    const empty = this.emptyReason();
    const shut = (button, disabled, title) => {
      if (!button) return;
      button.disabled = disabled;
      if (title) button.setAttribute('title', title);
      else button.removeAttribute('title');
    };
    shut(this.dom.prev, Boolean(empty) || !Number.isInteger(current?.event?.prev), empty || this.stepTitles.prev);
    shut(this.dom.next, Boolean(empty) || !Number.isInteger(current?.event?.next), empty || this.stepTitles.next);
    const opts = { nShowers: this.nShowers };
    shut(this.dom.pick, Boolean(empty), empty || pickerTitle('uniform', this.candidates, opts));
    shut(this.dom.tilted, Boolean(empty), empty || pickerTitle('tilted', this.candidates, opts));
    // "Open in 3-D" while an event is pinned; its title names the D-frame's fallback.
    if (this.dom.open3d) {
      this.dom.open3d.hidden = !pinned;
      this.dom.open3d.setAttribute('title', open3dTitle({ frame: this.state.get('frame') }));
      if (pinned) this.dom.open3d.setAttribute('href', this.open3dHref());
    }
    const lines = this.captionLines();
    setText('event-caption', lines.join(' '));
    setHidden('event-caption', lines.length === 0);
  }

  /**
   * The caption under the picker: the selection line, the event's place
   * among the candidates, how its shower stands against the particle filter,
   * the pick's rule and, after a replacement, what it replaced.
   */
  captionLines() {
    const pinned = this.state.get('event') !== null;
    const current = this.current;
    const lines = [];
    if (current) {
      const event = current.event;
      lines.push(eventSelectionLine(event));
      lines.push(placeLine(event, { nShowers: this.nShowers }));
      lines.push(matchLine({
        candidates: event.candidates, drawn: event.shower?.key, showers: event.shower, nShowers: this.nShowers,
      }));
    }
    if (pinned && this.pickRule) lines.push(this.pickRule);
    if (pinned && this.replaced && this.replaced.now === this.state.get('event')) {
      lines.push(replacedLine(this.replaced.old, this.replaced.now));
    }
    return lines.filter(Boolean);
  }
}
