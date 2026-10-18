/* A 3 x 3 grid of projection panels: three frames by three projections.
 *
 * The reference notebook's comparison figure lays one event (or one
 * ensemble) out as rows of frames - original, translated, local - and columns
 * of projections - X-Y, X-Z, Y-Z. Two views of the dashboard share that
 * layout: the Event Inspector, where every row is one shower of one event in
 * one frame, and the compare-frames view, where every row is one frame's own
 * ensemble response. The grid owns the cards and their nine `ProjectionPanel`s;
 * what each panel draws is the caller's business, through `render()`.
 *
 * The cards are built at construction, so they exist before the shell's
 * Details delegation and the export menu's `[data-export]` wiring run: every
 * cell is a `.card` with `data-panel`, its Details and Export buttons in the
 * toolbar, like the four fixed cards. The ids are `<prefix>-<row>-<col>`, which
 * the drawer keys its notes by and the export file name slugs.
 *
 * The charts are created the first time the grid is shown, not before: a
 * chart initialised inside a hidden section measures a zero-pixel box, and a
 * reader who never opens the inspector should not pay for nine idle charts.
 * Every panel is isometric - the notebook keeps `set_aspect('equal')` on all
 * nine, so a tilt reads at its true angle - and the caller may re-decide a
 * depth panel's aspect exactly as the ensemble grid does.
 */

import { ProjectionPanel } from './projection.js';

export const GRID_ROWS = ['lab', 'trans', 'local'];
export const GRID_COLS = ['xy', 'xz', 'yz'];

const EXPORT_TITLE = 'Export this panel\'s plot as a publication figure (white background, 300 DPI, '
  + 'plot area only — see Details for its disclosures)';

export class FrameGrid {
  /**
   * @param {HTMLElement} host  the rows' container inside a hidden section
   * @param {{prefix: string, onPanelCreated?: (id: string, panel: ProjectionPanel) => void}} options
   */
  constructor(host, { prefix, onPanelCreated = null } = {}) {
    this.host = host;
    this.section = host?.closest('section') ?? host;
    this.prefix = prefix;
    this.onPanelCreated = onPanelCreated;
    this.panels = null;
    this.rowTitles = {};
    this.rows = {};
    if (!host) return;
    for (const row of GRID_ROWS) {
      const band = document.createElement('div');
      band.className = 'frame-grid-row';
      band.dataset.row = row;
      band.hidden = true;
      const head = document.createElement('div');
      head.className = 'frame-grid-row-head';
      const title = document.createElement('span');
      title.className = 'frame-grid-row-title';
      head.append(title);
      band.append(head);
      this.rowTitles[row] = title;
      const cells = document.createElement('div');
      cells.className = 'frame-grid-cells';
      for (const col of GRID_COLS) cells.append(this.buildCard(row, col));
      band.append(cells);
      this.rows[row] = band;
      host.append(band);
    }
  }

  /** The id of one cell, `<prefix>-<row>-<col>`. */
  id(row, col) {
    return `${this.prefix}-${row}-${col}`;
  }

  /** Every cell id, row by row. */
  ids() {
    return GRID_ROWS.flatMap((row) => GRID_COLS.map((col) => this.id(row, col)));
  }

  buildCard(row, col) {
    const id = this.id(row, col);
    const card = document.createElement('div');
    card.className = 'card frame-cell';
    card.dataset.panel = id;
    const heading = document.createElement('h2');
    const title = document.createElement('span');
    title.className = 'title';
    title.id = `title-${id}`;
    title.title = 'Open the panel\'s methodology and disclosures';
    const actions = document.createElement('span');
    actions.className = 'card-actions';
    const details = document.createElement('button');
    details.type = 'button';
    details.className = 'mini';
    details.dataset.inspect = id;
    details.setAttribute('aria-controls', 'inspector');
    details.setAttribute('aria-expanded', 'false');
    details.title = 'Methodology and disclosures for this panel';
    details.textContent = 'Details';
    const reset = document.createElement('button');
    reset.type = 'button';
    reset.className = 'mini';
    reset.dataset.gridReset = id;
    reset.title = 'Restore the full window';
    reset.textContent = 'Reset';
    reset.addEventListener('click', () => this.panelById(id)?.resetView());
    const exporter = document.createElement('button');
    exporter.type = 'button';
    exporter.className = 'mini';
    exporter.dataset.export = id;
    exporter.setAttribute('aria-haspopup', 'menu');
    exporter.title = EXPORT_TITLE;
    exporter.append('Export ', document.createTextNode('▾'));
    actions.append(details, reset, exporter);
    heading.append(title, actions);
    const plot = document.createElement('div');
    plot.className = 'plot';
    plot.id = `plot-${id}`;
    card.append(heading, plot);
    return card;
  }

  /** Create the nine charts, once, while the section is on show. */
  ensurePanels() {
    if (this.panels || !this.host) return;
    this.panels = {};
    for (const row of GRID_ROWS) {
      for (const col of GRID_COLS) {
        const id = this.id(row, col);
        const panel = new ProjectionPanel(`plot-${id}`, { isometric: true });
        panel.gridRow = row;
        panel.gridCol = col;
        this.panels[id] = panel;
        if (typeof this.onPanelCreated === 'function') this.onPanelCreated(id, panel);
      }
    }
  }

  /** The panel of one cell, or null before the grid was first shown. */
  panel(row, col) {
    return this.panels?.[this.id(row, col)] ?? null;
  }

  panelById(id) {
    return this.panels?.[id] ?? null;
  }

  /**
   * Draw the grid. `rows` maps a row key to `{title, cells}`, `cells` a
   * column key to `{title, payload, opts}`; a row left out is hidden, and
   * `isometric` on a cell overrides the panel's aspect before it renders.
   */
  render(rows) {
    this.ensurePanels();
    for (const row of GRID_ROWS) {
      const spec = rows[row];
      this.rows[row].hidden = !spec;
      if (!spec) continue;
      this.rowTitles[row].textContent = spec.title ?? '';
      for (const col of GRID_COLS) {
        const cell = spec.cells?.[col];
        const id = this.id(row, col);
        const title = document.getElementById(`title-${id}`);
        if (title) title.textContent = cell?.title ?? '';
        if (!cell || !this.panels) continue;
        const panel = this.panels[id];
        if (typeof cell.isometric === 'boolean') panel.isometric = cell.isometric;
        panel.render(cell.payload, cell.opts);
      }
    }
  }

  /** Show or hide the whole section; a shown grid gets its charts and a layout. */
  show(visible) {
    if (!this.section) return;
    this.section.hidden = !visible;
    if (visible) {
      this.ensurePanels();
      this.relayout();
    }
  }

  get visible() {
    return Boolean(this.section) && !this.section.hidden;
  }

  relayout() {
    if (!this.panels || !this.visible) return;
    for (const panel of Object.values(this.panels)) panel.relayout();
  }

  setBusy(busy) {
    if (!this.panels) return;
    for (const panel of Object.values(this.panels)) panel.setBusy(busy);
  }
}
