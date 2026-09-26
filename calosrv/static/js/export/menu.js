/* The per-panel export dropdown.
 *
 * Wired by `data-export` attribute rather than by element id, so the markup can
 * gain a panel without the id audit in `tests/test_api.py` having to learn
 * about it - the same delegation the Auto-fit RoI and A/B/Both controls use.
 *
 * The rasterisation is synchronous and blocks the main thread for a fraction of
 * a second at double-column PNG, because ECharts needs a real DOM node and so
 * cannot be moved to a worker. What the feedback below buys is not concurrency
 * but honesty: the button disables and relabels, and two animation frames are
 * yielded so that paints before the block begins, rather than the interface
 * appearing to ignore the click and then producing a file.
 */

import { exportPanel } from './figure.js';
import { WIDTH_MM } from './tokens.js';

const CHOICES = [
  {
    label: 'SVG — single column (85 mm)',
    hint: 'Vector, for LaTeX',
    format: 'svg',
    widthMm: WIDTH_MM.single,
  },
  {
    label: 'SVG — double column (175 mm)',
    hint: 'Vector, full width',
    format: 'svg',
    widthMm: WIDTH_MM.double,
  },
  {
    label: 'PNG 300 DPI — single column',
    hint: 'Raster, for slides',
    format: 'png',
    widthMm: WIDTH_MM.single,
  },
  {
    label: 'PNG 300 DPI — double column',
    hint: 'Raster, full width',
    format: 'png',
    widthMm: WIDTH_MM.double,
  },
];

let open = null;

export function closeExportMenu() {
  if (open) {
    open.remove();
    open = null;
  }
}

/**
 * Wire every `[data-export]` button on the page.
 *
 * `resolve(panelId)` returns `{ panel, title, footnote, selection, disclosure }`
 * for the panel that button belongs to, or null when there is nothing to
 * export yet. `disclosure` is the structured sentence list from
 * `export/disclosure.js` and may be absent.
 */
export function attachExportMenus({ resolve, state, getExperiment, onError }) {
  for (const button of document.querySelectorAll('[data-export]')) {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      if (open) { closeExportMenu(); return; }
      openMenu(button, { resolve, state, getExperiment, onError });
    });
  }
  document.addEventListener('click', closeExportMenu);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeExportMenu();
  });
}

function openMenu(button, context) {
  const panelId = button.dataset.export;
  const node = document.createElement('div');
  node.className = 'menu';
  node.setAttribute('role', 'menu');

  for (const choice of CHOICES) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'menu-item';
    item.setAttribute('role', 'menuitem');
    item.innerHTML = `<span>${choice.label}</span><small>${choice.hint}</small>`;
    item.addEventListener('click', (event) => {
      event.stopPropagation();
      closeExportMenu();
      run(button, panelId, choice, context);
    });
    node.appendChild(item);
  }

  document.body.appendChild(node);
  const box = button.getBoundingClientRect();
  node.style.top = `${Math.min(
    window.innerHeight - node.offsetHeight - 8, box.bottom + 6,
  )}px`;
  node.style.left = `${Math.max(8, Math.min(
    window.innerWidth - node.offsetWidth - 8, box.right - node.offsetWidth,
  ))}px`;
  open = node;
}

function run(button, panelId, choice, { resolve, state, getExperiment, onError }) {
  const target = resolve(panelId);
  if (!target || !target.panel) {
    onError('Nothing to export yet — the panel has no data.');
    return;
  }

  const label = button.textContent;
  button.disabled = true;
  button.textContent = 'Exporting…';

  // Two frames: one for the style change to be computed, one for it to paint.
  // A single frame can land before the browser has flushed the label change,
  // leaving the button looking untouched for the whole blocking render.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    try {
      exportPanel(target.panel, {
        panelId,
        format: choice.format,
        widthMm: choice.widthMm,
        title: target.title,
        footnote: target.footnote,
        selection: target.selection,
        frame: target.frame,
        meta: target.meta ?? null,
        disclosure: target.disclosure,
        state,
        experiment: getExperiment(),
      });
    } catch (error) {
      console.error('[calosrv] export failed', error);
      onError(`Could not export this panel: ${error.message || error}`);
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }));
}
