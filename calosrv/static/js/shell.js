/* The page's two side panels: the collapsible configuration sidebar on the
 * left and the Details drawer on the right.
 *
 * Both change the width of the chart column, and every ECharts panel lays
 * itself out from its container - the XY panel letterboxes its plot so a
 * millimetre along x and a millimetre along y are the same number of pixels.
 * So each change of either panel calls `onLayoutChange()` (main.js
 * `relayoutAll`) synchronously, once the class has been toggled: the grid
 * tracks snap - nothing on `.app` or `.sidebar` is animated - so the
 * `clientWidth` the panels read inside `relayout()` is already the final
 * geometry, and each click costs one rebuild per panel rather than a
 * cascade of them across a transition.
 *
 * The drawer renders text only: every sentence it shows comes from a payload
 * through panel_notes.js, so it is written with `textContent`, never
 * `innerHTML`.
 *
 * The collapsed state is a per-browser convenience, kept in localStorage and
 * never in the URL hash: a bookmark must not carry layout, and the built-in
 * view in state.js is frozen for that reason.
 */

export const SIDEBAR_STORAGE_KEY = 'calosrv.sidebar';

/** The stored sidebar preference, 'collapsed' | 'open' | null. */
export function readSidebarPreference() {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
  } catch {
    // A private window or blocked storage: the toggle still works for this page.
    return null;
  }
}

export function writeSidebarPreference(value) {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, value);
  } catch {
    // Nothing to do: the preference is a convenience, not state.
  }
}

const COLLAPSE_LABEL = 'Collapse the configuration sidebar';
const EXPAND_LABEL = 'Expand the configuration sidebar';

export class Shell {
  /**
   * @param {{getNotes: (panelId: string) => object|null, onLayoutChange: () => void}} options
   *   `getNotes` returns the panel's notes (panel_notes.js) or null when the
   *   panel has no data yet; `onLayoutChange` re-lays every chart out.
   */
  constructor({ getNotes, onLayoutChange } = {}) {
    this.getNotes = getNotes || (() => null);
    this.onLayoutChange = onLayoutChange || (() => {});
    this.app = document.querySelector('.app');
    this.sidebar = document.getElementById('sidebar');
    this.toggle = document.getElementById('sidebar-toggle');
    this.inspector = document.getElementById('inspector');
    this.title = document.getElementById('inspector-title');
    this.body = document.getElementById('inspector-body');
    this.closeButton = document.getElementById('inspector-close');
    this.inspected = null;
    this.returnTo = null;

    // Applied before the charts are created (main.js constructs the shell
    // first), so the first layout already has the right width.
    if (readSidebarPreference() === 'collapsed') this.applySidebar(true);

    this.toggle?.addEventListener('click', () => this.toggleSidebar());
    this.closeButton?.addEventListener('click', () => this.closeInspector());

    for (const card of document.querySelectorAll('.card[data-panel]')) {
      const panelId = card.dataset.panel;
      const button = card.querySelector('[data-inspect]');
      button?.addEventListener('click', () => this.toggleInspector(panelId, button));
      // The title row opens the drawer too; its own buttons keep their jobs.
      card.querySelector('h2')?.addEventListener('click', (event) => {
        // The toolbar and its gaps are the buttons' territory, not a trigger.
        if (event.target.closest('button, a, input, .seg, .card-actions')) return;
        this.toggleInspector(panelId, button);
      });
    }

    // Escape closes the drawer, unless an overlay that owns the keypress is
    // open: a modal (which traps focus), a popover or the export menu. Those
    // handlers run in the bubbling phase and remove the elements this checks,
    // so the check runs in the capture phase, before them.
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape' || !this.inspected) return;
      if (document.querySelector('.modal-backdrop:not([hidden]), .popover, .menu')) return;
      this.closeInspector();
    }, { capture: true });
  }

  /* ------------------------------------------------------------ sidebar */

  get sidebarCollapsed() {
    return Boolean(this.app?.classList.contains('is-sidebar-collapsed'));
  }

  applySidebar(collapsed) {
    this.app?.classList.toggle('is-sidebar-collapsed', collapsed);
    if (this.toggle) {
      this.toggle.setAttribute('aria-expanded', String(!collapsed));
      this.toggle.setAttribute('aria-label', collapsed ? EXPAND_LABEL : COLLAPSE_LABEL);
      this.toggle.title = collapsed ? 'Expand the sidebar' : 'Collapse the sidebar';
    }
    if (this.sidebar) {
      // Out of the tab order and the accessibility tree while it has no width.
      this.sidebar.inert = collapsed;
      this.sidebar.setAttribute('aria-hidden', String(collapsed));
    }
  }

  /** Collapse or expand the configuration sidebar; the same button does both. */
  toggleSidebar(collapsed = !this.sidebarCollapsed) {
    this.applySidebar(collapsed);
    writeSidebarPreference(collapsed ? 'collapsed' : 'open');
    this.onLayoutChange();
  }

  /* ------------------------------------------------------------- drawer */

  toggleInspector(panelId, trigger = null) {
    if (this.inspected === panelId) this.closeInspector();
    else this.openInspector(panelId, { trigger });
  }

  /** Show one panel's notes; called again for another panel, it re-targets in place. */
  openInspector(panelId, { trigger = null } = {}) {
    if (!this.inspector) return;
    const retarget = this.inspected !== panelId;
    this.inspected = panelId;
    if (trigger) this.returnTo = trigger;
    this.app?.classList.add('is-inspector-open');
    this.inspector.hidden = false;
    this.markCards(panelId);
    this.renderNotes(this.getNotes(panelId));
    // A new panel starts at its top; a refresh of the same panel keeps the
    // reader's place.
    if (retarget) this.inspector.scrollTop = 0;
    this.title?.focus({ preventScroll: true });
    this.onLayoutChange();
  }

  closeInspector() {
    if (!this.inspected || !this.inspector) return;
    this.inspected = null;
    this.app?.classList.remove('is-inspector-open');
    this.inspector.hidden = true;
    this.markCards(null);
    const back = this.returnTo;
    this.returnTo = null;
    this.onLayoutChange();
    if (back && back.isConnected) back.focus();
  }

  /**
   * Show fresh notes for `panelId` when it is the panel on show; a no-op
   * otherwise. The caller hands the notes over rather than having them fetched
   * again: `getNotes` may itself be what rebuilt them and called this.
   */
  refresh(panelId, notes) {
    if (this.inspected === panelId) this.renderNotes(notes);
  }

  markCards(panelId) {
    for (const card of document.querySelectorAll('.card[data-panel]')) {
      const active = card.dataset.panel === panelId;
      card.classList.toggle('is-inspected', active);
      card.querySelector('[data-inspect]')?.setAttribute('aria-expanded', String(active));
    }
  }

  /** Text nodes only: the sentences come from payloads. */
  renderNotes(notes) {
    if (this.title) this.title.textContent = notes?.title ?? 'Panel details';
    if (!this.body) return;
    const nodes = [];
    if (!notes || !notes.sections?.length) {
      const empty = document.createElement('p');
      empty.className = 'inspector-empty';
      empty.textContent = 'No data for this panel yet.';
      nodes.push(empty);
    }
    for (const section of notes?.sections ?? []) {
      const block = document.createElement('section');
      block.className = 'inspector-section';
      const heading = document.createElement('h3');
      heading.textContent = section.heading;
      block.append(heading);
      for (const line of section.lines) {
        const paragraph = document.createElement('p');
        paragraph.textContent = line;
        block.append(paragraph);
      }
      nodes.push(block);
    }
    this.body.replaceChildren(...nodes);
  }
}
