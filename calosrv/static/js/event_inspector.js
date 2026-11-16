/* The Event Inspector: one shower of one event in the original, translated
 * and local frames - the reference notebook's comparison figure
 * (`local-coords.ipynb`, cell 6), server-rendered - on the Physics page's
 * Event viewer subpage (physics_subpages.js; "Event Inspector" names the
 * nine-panel figure, "Event viewer" the subpage that holds it).
 *
 * The event and the shower are view state (`#event=…&shower=…`, with
 * `psub=event`), so a link carries the picture. The candidates are the pickers'
 * pool (event_picker.js, `State.eventPoolParams()`): every event of the
 * experiment the frame gate can place, narrowed by the particle filter alone;
 * E₁, E₂ and D never narrow them (Martin's decision of 2026-11-16), so an
 * E₁/E₂/D commit never touches this controller. Every request - the event,
 * the pick, a step, a replacement - is asked under `basis=experiment`. This
 * controller owns the sidebar's picker, the grid's label line, its "Open in
 * 3-D" link and the nine cells' options; what the cells draw comes whole from
 * one `GET /api/event` response (query/event_inspector.py) - nine quantised
 * rasters, the marks as 3-D lines and points - never from hit rows.
 *
 * Two pickers draw from the candidates. "Pick for me" is the uniform rule: a
 * seeded shuffle of the candidates in event-number order (seed 42), each
 * click the next draw, so no event repeats until all have been drawn; the
 * draw counter carries on across particle commits (entry k of a fresh
 * shuffle is as uniform as entry 1, and a restart would replay entry 1 after
 * a commit that left the pool as it was) and starts again only on an
 * experiment switch. Entering the viewer with no event draws the first one by
 * this rule once the count is in (`firstDraw`): draw 0 after a switch, and
 * nothing at N = 0, where the empty state says why. "Most tilted" reproduces
 * the notebook's `_select_events`, a seeded draw from the densest, most tilted
 * candidates, each click the next seed from 42. Every response states its
 * rule, seed and draw, and the caption shows it. The requests are built by
 * event_picker.js `pickParams`, and every sentence comes from there.
 *
 * Where the pinned event came from is remembered in memory (a link, typed, a
 * pick, Most tilted, a step, a replacement). After a particle commit the
 * pinned event's fresh response decides (`followDecision`): kept while it is
 * a candidate, replaced by the next uniform draw when the page chose it
 * itself, else drawn as asked and flagged. A picker asks for a matching shower
 * (`focusShower`) in the event's first request; a shower chosen by hand is
 * drawn as asked. With no candidate (N = 0) the pickers and the steps are
 * shut, their title the reason, and a 404 from the pick is that empty state,
 * never an error.
 *
 * While Entire selection is on show the event is parked (`park` / `unpark`):
 * the event, its shower, origin, rule sentence and replacement are kept in
 * memory, never in the link, and the response in hand is drawn again on the
 * way back, with no request. A response that lands after the event was
 * parked or the experiment switched draws nothing (`epoch`).
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
import { wireLiveLinks, describeError } from './page_common.js';
import {
  FIRST_SEED, pickParams, followDecision, focusShower, emptyLine, placeLine, matchLine, replacedLine, poolLine,
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

/**
 * The Event viewer's empty state when no event is drawn and nothing explains
 * why otherwise: the reader cleared the event number, or no draw was made.
 */
export const CLEARED_LINE = 'No event drawn: type an event number, or press Pick for me or Most tilted.';

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
   *   changed, so the page can route the viewer (the grid or its empty state);
   *   `layerGroups(kind)` the Longitudinal Channels the page draws in that
   *   row's frame, `{mode, counts}`, or null for none.
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
    // Why the viewer's first draw failed (other than N = 0), for its empty state.
    this.pickFailure = null;
    // The viewer's first draw waits for the count (`armFirstDraw`, `firstDraw`); a first pick in flight.
    this.drawPending = false;
    this.firstInFlight = false;
    // The reader emptied the event number: the viewer says so until an event is drawn.
    this.cleared = false;
    // Whether the viewer has asked for an event of this experiment yet: until then its empty state says nothing.
    this.attempted = false;
    // Bumped when the event is parked or the experiment switches: a response asked before draws nothing.
    this.epoch = 0;
    this.dom = {
      number: document.getElementById('event-number'),
      prev: document.getElementById('event-prev'),
      next: document.getElementById('event-next'),
      pick: document.getElementById('event-pick'),
      tilted: document.getElementById('event-pick-tilted'),
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
        this.unpin({ cleared: true });
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
   * Pin an event: the viewer draws it once fetched. `origin` is where it came
   * from (ORIGINS); `shower` the shower a picker focused, asked for in this
   * first request; `rule` the pick's rule sentence; `replaced` the event a
   * replacement takes the place of.
   */
  pin(eventNumber, { origin = 'typed', shower = null, rule = null, replaced = null } = {}) {
    this.origin = origin;
    this.pickRule = rule;
    this.replaced = replaced === null || replaced === undefined ? null : { old: replaced, now: eventNumber };
    this.followNext = false;
    this.drawPending = false;
    this.cleared = false;
    this.pickFailure = null;
    this.state.set(shower ? { event: eventNumber, shower } : { event: eventNumber });
    this.onViewMode();
    return this.refresh();
  }

  /**
   * No event: the link loses it, and the viewer shows its empty state. With
   * `cleared` the reader emptied the event number, and the empty state says
   * how to draw one again.
   */
  unpin({ cleared = false } = {}) {
    this.attempted = true;
    this.state.set({ event: null });
    this.origin = null;
    this.pickRule = null;
    this.replaced = null;
    this.followNext = false;
    this.drawPending = false;
    this.cleared = cleared;
    this.onViewMode();
  }

  /**
   * Park the event while Entire selection is on show: what it was, its
   * shower, origin, rule sentence and replacement, returned to the page to
   * keep in memory; the state's `event` set to null, so the link carries
   * neither the event nor (Entire selection being the default) the subpage.
   * The response in hand is kept to draw again; anything still in flight is
   * dropped. A first draw in flight is asked again on the way back. Null when
   * no event is drawn.
   */
  park() {
    this.epoch += 1;
    this.followNext = false;
    if (this.firstInFlight) {
      this.firstInFlight = false;
      this.drawPending = true;
    }
    if (!this.pinned) return null;
    const parked = {
      event: this.state.get('event'),
      shower: this.state.get('shower'),
      origin: this.origin,
      pickRule: this.pickRule,
      replaced: this.replaced,
    };
    this.state.set({ event: null });
    return parked;
  }

  /**
   * Bring a parked event back (`park`'s object): the state's `event` and
   * `shower`, its origin, rule sentence and replacement. It is drawn from
   * the response in hand, with no request; only when no response of it is in
   * hand (its load failed or was dropped) is it asked for again.
   */
  unpark(parked) {
    if (!parked || parked.event === null || parked.event === undefined) return Promise.resolve(null);
    this.origin = parked.origin ?? 'typed';
    this.pickRule = parked.pickRule ?? null;
    this.replaced = parked.replaced ?? null;
    this.followNext = false;
    this.drawPending = false;
    this.cleared = false;
    this.state.set({ event: parked.event, shower: parked.shower ?? this.state.get('shower') });
    this.onViewMode();
    if (this.current) {
      this.render(this.payload);
      this.onRendered(this.payload);
      return Promise.resolve(this.payload);
    }
    return this.refresh();
  }

  /**
   * An experiment switch: the previous experiment's event goes - the state's
   * `event` silently (the activation writes the link once), the response in
   * hand, its origin and sentences - and anything in flight is dropped.
   */
  forget() {
    this.epoch += 1;
    if (this.state.get('event') !== null) this.state.set({ event: null }, { silent: true });
    this.payload = null;
    this.origin = null;
    this.pickRule = null;
    this.replaced = null;
    this.followNext = false;
    this.drawPending = false;
    this.firstInFlight = false;
    this.cleared = false;
    this.attempted = false;
    this.pickFailure = null;
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
    this.pickFailure = null;
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

  /** The candidates' count, or null while it is not known (no count yet, or it failed). */
  candidateCount() {
    const n = Number((this.candidates?.candidates ?? this.candidates)?.n_events);
    return this.candidates && Number.isFinite(n) ? n : null;
  }

  /* ----------------------------------------------- the viewer's first draw -- */

  /** The viewer is entered with no event: draw one when the count is in (`firstDraw`). */
  armFirstDraw() {
    if (this.pinned) return;
    this.drawPending = true;
    this.cleared = false;
    this.pickFailure = null;
  }

  /**
   * The viewer's first draw, once the count is in: Pick for me at the current
   * draw (0 after an experiment switch). At N = 0 nothing is asked and the
   * draw stays armed, so a particle commit that widens the pool draws then; a
   * failed count does not stop it, the pick's own answer deciding. Null when
   * nothing was asked.
   */
  firstDraw() {
    if (!this.drawPending) return Promise.resolve(null);
    this.attempted = true;
    if (this.pinned) {
      this.drawPending = false;
      return Promise.resolve(null);
    }
    if (this.candidateCount() === 0) {
      this.syncControls();
      return Promise.resolve(null);
    }
    this.drawPending = false;
    return this.pick('uniform', { first: true });
  }

  /**
   * What the viewer says in place of the grid ('' while an event is pinned,
   * before it has asked for one, or while its first draw is awaited): the
   * empty pool's line at N = 0, the pick's refusal, a failed first draw's
   * reason, else how to draw one (the reader emptied the event number).
   */
  emptyText() {
    if (this.pinned) return '';
    const reason = this.emptyReason() || this.pickFailure;
    if (reason) return reason;
    if (!this.attempted || this.drawPending || this.firstInFlight) return '';
    return CLEARED_LINE;
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
    const epoch = this.epoch;
    let payload;
    try {
      payload = await getJson('/api/event', this.state.eventParams(), 'event');
    } catch (error) {
      // Parked, or another experiment, while it was in flight: nothing to say.
      if (epoch !== this.epoch) return null;
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
    // Parked, or another experiment, while it was in flight: it draws nothing.
    if (epoch !== this.epoch) return null;
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
   * One pick from the candidates - the whole experiment under the particle
   * filter (`State.eventPoolParams()`, `basis=experiment`; never an E₁, E₂ or
   * D key, which the server refuses under that basis): `uniform` (Pick for
   * me) at the next draw of the seeded shuffle, `tilted` (Most tilted) at the
   * next seed. The shower asked for is a matching one. A 404 is the empty
   * state (no candidate), never an error. `first` is the viewer's first draw,
   * whose failure its empty state says rather than the banner.
   */
  async pick(rule = 'uniform', { replacing = null, first = false } = {}) {
    const params = pickParams({
      filters: this.state.eventPoolParams(),
      rule,
      seed: rule === 'uniform' ? FIRST_SEED : this.seed,
      draw: this.draw,
    });
    const epoch = this.epoch;
    let payload;
    this.attempted = true;
    if (first) this.firstInFlight = true;
    try {
      payload = await getJson('/api/event/pick', params, 'event-pick');
    } catch (error) {
      if (epoch !== this.epoch) return null;
      if (first) this.firstInFlight = false;
      if (isAbort(error)) return null;
      if (error?.status === 404) {
        // No candidate: the pickers are shut with the reason, and nothing is pinned.
        this.pickRefused = error.message || 'No candidate event.';
        this.syncControls();
        this.onViewMode();
        return null;
      }
      if (first) {
        // The viewer's empty state says why its first draw failed.
        this.pickFailure = `The first event could not be drawn: ${describeError(error)}`;
        this.syncControls();
        this.onViewMode();
        return null;
      }
      this.onError(error, 'pick an event');
      return null;
    }
    // Parked, or another experiment, while it was in flight: nothing is pinned and the draw is not counted.
    if (epoch !== this.epoch) return null;
    if (first) this.firstInFlight = false;
    // A replacement draw that lands after the reader moved on (typed or stepped
    // to another event while it was in flight) replaces nothing: the event the
    // reader chose is never swapped out. The draw is not counted.
    if (replacing !== null && replacing !== undefined && this.state.get('event') !== replacing) return null;
    // Nor does a first draw land on an event the reader typed or stepped to meanwhile.
    if (first && this.pinned) return null;
    if (rule === 'uniform') this.draw += 1;
    else this.seed += 1;
    this.pickRefused = null;
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
   * The caption under the picker: the event's kinematics (and, on a response
   * without `basis`, whether the selection holds it), the event's place among
   * the candidates, what the candidates are drawn from (the whole experiment,
   * which E₁, E₂ and D do not narrow), how its shower stands against the
   * particle filter, the pick's rule and, after a replacement, what it
   * replaced.
   */
  captionLines() {
    const pinned = this.state.get('event') !== null;
    const current = this.current;
    const lines = [];
    if (current) {
      const event = current.event;
      lines.push(eventSelectionLine(event, { nShowers: this.nShowers }));
      lines.push(placeLine(event, { nShowers: this.nShowers }));
      lines.push(poolLine(event, { nShowers: this.nShowers }));
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
