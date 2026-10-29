/* The Methodology page (/methodology): bootstrap.
 *
 * SKELETON. It draws the article's headings, paragraphs and equations as
 * plain text, so the route, the tabs and the module graph can be tested while
 * the renderer (methodology/render.js) is written. The page never writes a
 * view key into the hash; its tabs drop its own key, `at`.
 */

import { ARTICLE } from './methodology/content/index.js';
import { CONSTANTS } from './methodology/constants.js';
import { mountMath, texToTree } from './math.js';
import { getJson } from './api.js';
import { Banner, fillComputeBadges, wirePageTabs } from './page_common.js';
import { Shell } from './shell.js';

/* The outline sits in the configuration sidebar's track, under its own key;
 * the shell wires the header's toggle to it. */
new Shell({
  storageKey: 'calosrv.methodology.outline',
  labels: {
    collapse: 'Collapse the article outline',
    expand: 'Expand the article outline',
    collapseTitle: 'Collapse the outline',
    expandTitle: 'Expand the outline',
  },
});

const banner = new Banner();

function heading(level, text) {
  const element = document.createElement(`h${level}`);
  element.textContent = text;
  return element;
}

function section(part, level) {
  const element = document.createElement('section');
  element.id = part.id;
  element.append(heading(level, part.title));
  for (const block of part.blocks ?? []) {
    if (block.kind === 'eq') {
      element.append(mountMath(texToTree(block.tex, { display: true })));
    } else if (typeof block.text === 'string') {
      const paragraph = document.createElement('p');
      paragraph.textContent = block.text;
      element.append(paragraph);
    }
  }
  for (const child of part.sections ?? []) element.append(section(child, Math.min(level + 1, 6)));
  return element;
}

/* Appendix B: every constant the article quotes, with its source. */
function constantsAppendix() {
  const element = document.createElement('section');
  element.id = 'app-constants';
  element.append(heading(2, 'Constants'));
  const list = document.createElement('ul');
  for (const [name, { value, source, meaning }] of Object.entries(CONSTANTS)) {
    const item = document.createElement('li');
    item.textContent = `${name} = ${Array.isArray(value) ? value.join(', ') : value} — ${meaning} (${source})`;
    list.append(item);
  }
  element.append(list);
  return element;
}

function boot() {
  const paper = document.getElementById('paper');
  if (!paper) return;
  paper.replaceChildren(heading(1, ARTICLE.front.title), ...ARTICLE.sections.map((part) => section(part, 2)),
    constantsAppendix());
}

// The tabs carry the view across, without this page's own key.
wirePageTabs(document, { drop: ['at'] });

try {
  boot();
} catch (error) {
  console.error('[calosrv] methodology', error);
  banner.show([`The article could not be drawn: ${error?.message ?? error}`], true);
}

// The header's compute badge, as on the other two pages.
getJson('/api/experiments', {}, 'experiments')
  .then((payload) => fillComputeBadges(payload.compute))
  .catch((error) => console.error('[calosrv] experiments', error));
