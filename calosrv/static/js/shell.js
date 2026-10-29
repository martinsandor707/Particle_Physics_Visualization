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
 * view in state.js is frozen for that reason. The Methodology page's outline
 * sits in the same track under a key of its own (`storageKey`), so folding
 * it away does not fold the configuration sidebar of the other two pages.
 *
 * A panel opened from a Methodology badge carries a way back: its drawer
 * starts with a link to the place in the article the reader left
 * (`setReturnLink`), whose href is computed when it is followed, so a view
 * changed on this page travels back with the reader.
 *
 * Every drawer of a panel the article explains carries a second, permanent
 * link: to the section that says how that panel is computed and drawn
 * (`sectionOf`, article_sections.js), live in the same way. Where the return
 * link already lands on that very place, it is the only one shown.
 */

import { methodologyHref, wireLiveLinks } from './page_common.js';

export const SIDEBAR_STORAGE_KEY = 'calosrv.sidebar';

/** The stored sidebar preference, 'collapsed' | 'open' | null. */
export function readSidebarPreference(key = SIDEBAR_STORAGE_KEY) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // A private window or blocked storage: the toggle still works for this page.
    return null;
  }
}

export function writeSidebarPreference(value, key = SIDEBAR_STORAGE_KEY) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Nothing to do: the preference is a convenience, not state.
  }
}

/** The toggle's names for the configuration sidebar; a page with another sidebar passes its own. */
const SIDEBAR_LABELS = Object.freeze({
  collapse: 'Collapse the configuration sidebar',
  expand: 'Expand the configuration sidebar',
  collapseTitle: 'Collapse the sidebar',
  expandTitle: 'Expand the sidebar',
});

export class Shell {
  /**
   * @param {{getNotes: (panelId: string) => object|null, onLayoutChange: () => void,
   *   sectionOf?: (panelId: string) => {at: string, section: string, title: string}|null,
   *   storageKey?: string, labels?: object}} options
   *   `getNotes` returns the panel's notes (panel_notes.js) or null when the
   *   panel has no data yet; `onLayoutChange` re-lays every chart out;
   *   `sectionOf` names the article section explaining a panel
   *   (article_sections.js `articleSection`), or null for none;
   *   `storageKey` is where the sidebar's collapsed state is kept and `labels`
   *   names its toggle (both default to the configuration sidebar's).
   */
  constructor({
    getNotes, onLayoutChange, sectionOf = null, storageKey = SIDEBAR_STORAGE_KEY, labels = null,
  } = {}) {
    this.getNotes = getNotes || (() => null);
    this.sectionOf = sectionOf || (() => null);
    this.onLayoutChange = onLayoutChange || (() => {});
    this.storageKey = storageKey;
    this.labels = { ...SIDEBAR_LABELS, ...(labels ?? {}) };
    this.app = document.querySelector('.app');
    this.sidebar = document.getElementById('sidebar');
    this.toggle = document.getElementById('sidebar-toggle');
    this.inspector = document.getElementById('inspector');
    this.title = document.getElementById('inspector-title');
    this.body = document.getElementById('inspector-body');
    this.closeButton = document.getElementById('inspector-close');
    this.inspected = null;
    this.returnTo = null;
    // The way back to the Methodology: {panelId, anchor, label, title} or null, and its link on show.
    this.returnLink = null;
    this.returnAnchor = null;
    // The drawer's link to the section explaining its panel, while one is shown.
    this.methodAnchor = null;

    // Applied before the charts are created (main.js constructs the shell
    // first), so the first layout already has the right width.
    if (readSidebarPreference(this.storageKey) === 'collapsed') this.applySidebar(true);

    this.toggle?.addEventListener('click', () => this.toggleSidebar());
    this.closeButton?.addEventListener('click', () => this.closeInspector());

    // One delegated listener rather than one per card: the Event Inspector
    // and the compare-frames view build their eighteen cards after the shell
    // exists, and every card with a `data-panel` is a drawer target.
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-inspect]');
      if (button) {
        this.toggleInspector(button.dataset.inspect, button);
        return;
      }
      // The title row opens the drawer too; its own buttons keep their jobs.
      const heading = event.target.closest('.card[data-panel] > h2');
      if (!heading) return;
      // The toolbar and its gaps are the buttons' territory, not a trigger.
      if (event.target.closest('button, a, input, .seg, .card-actions')) return;
      const card = heading.closest('.card[data-panel]');
      this.toggleInspector(card.dataset.panel, card.querySelector('[data-inspect]'));
    });

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
      this.toggle.setAttribute('aria-label', collapsed ? this.labels.expand : this.labels.collapse);
      this.toggle.title = collapsed ? this.labels.expandTitle : this.labels.collapseTitle;
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
    writeSidebarPreference(collapsed ? 'collapsed' : 'open', this.storageKey);
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

  /**
   * Give `panelId`'s drawer a way back to the Methodology, for the rest of
   * this page's life: `link` is page_common.js `returnLink(...)`, or null to
   * remove it. Shown at once when that drawer is the one open.
   */
  setReturnLink(panelId, link) {
    this.returnLink = link && panelId ? { ...link, panelId } : null;
    if (panelId && this.inspected === panelId) this.renderNotes(this.getNotes(panelId));
  }

  /** The return link's paragraph for the drawer on show, or null. */
  returnNode() {
    const link = this.returnLink;
    if (!link || link.panelId !== this.inspected) return null;
    const paragraph = document.createElement('p');
    paragraph.className = 'inspector-return';
    const anchor = document.createElement('a');
    const href = () => methodologyHref(link.anchor, window.location.hash);
    anchor.href = href();
    anchor.title = link.title;
    anchor.textContent = link.label;
    wireLiveLinks([anchor], href);
    paragraph.append(anchor);
    this.returnAnchor = anchor;
    return paragraph;
  }

  /**
   * The paragraph linking the drawer on show to the article section that
   * explains its panel, or null: for a panel the map does not name, or when
   * the return link already lands on the same place.
   */
  methodNode() {
    const place = this.inspected ? this.sectionOf(this.inspected) : null;
    if (!place?.at) return null;
    const back = this.returnLink;
    if (back && back.panelId === this.inspected && back.anchor === place.at) return null;
    const paragraph = document.createElement('p');
    paragraph.className = 'inspector-method';
    const anchor = document.createElement('a');
    const href = () => methodologyHref(place.at, window.location.hash);
    anchor.href = href();
    // One line (layout.css ends a long title with an ellipsis); the tooltip carries it whole.
    const where = `${sectionLabel(place.section)} ${place.title}`;
    anchor.textContent = `How it is drawn: Methodology ${where}`;
    anchor.title = `How this panel is computed and drawn: ${where}, in the Methodology, `
      + 'with the view on screen now';
    wireLiveLinks([anchor], href);
    paragraph.append(anchor);
    this.methodAnchor = anchor;
    return paragraph;
  }

  /** Text nodes only: the sentences come from payloads. */
  renderNotes(notes) {
    if (this.title) this.title.textContent = notes?.title ?? 'Panel details';
    if (!this.body) return;
    // A keyboard reader on either article link keeps their place when the notes refresh under it.
    const active = document.activeElement;
    const hadFocus = Boolean(this.returnAnchor) && active === this.returnAnchor;
    const hadMethodFocus = Boolean(this.methodAnchor) && active === this.methodAnchor;
    this.returnAnchor = null;
    this.methodAnchor = null;
    const nodes = [];
    const back = this.returnNode();
    if (back) nodes.push(back);
    const method = this.methodNode();
    if (method) nodes.push(method);
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
    if (hadFocus) this.returnAnchor?.focus({ preventScroll: true });
    if (hadMethodFocus) this.methodAnchor?.focus({ preventScroll: true });
  }
}

/** A section number as the article prints it: §3.1, or Appendix A. */
function sectionLabel(number) {
  const text = String(number ?? '');
  return /^[A-Z]/.test(text) ? `Appendix ${text}` : `§${text}`;
}
