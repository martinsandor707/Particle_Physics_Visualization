/* The Methodology page (/methodology): bootstrap.
 *
 * The article is drawn first, from its content modules alone
 * (methodology/render.js): it needs no network, so it is readable when the
 * service is not. Then the page asks the service two things - the catalogue
 * (/api/experiments), for the compute badge and the view the badges open, and
 * /api/health, for the provenance line - and says on the banner when either
 * fails; the badges then carry the address bar's hash as it stands.
 *
 * The page never writes a view key into the hash. It carries the reader's
 * view to the badges and the tabs, and keeps its own place in one key of its
 * own, `at`, written only when the reader clicks a TOC entry, a heading's
 * anchor or an equation's number (methodology/links.js `writeAt`). The tabs
 * drop `at`, which the other pages have no use for.
 */

import { ARTICLE } from './methodology/content/index.js';
import { layout, mount, tocTree, wireArticle, wireGoto } from './methodology/render.js';
import { badgeHref, readAt, viewChipText, writeAt } from './methodology/links.js';
import { getJson } from './api.js';
import { Banner, describeError, fillComputeBadges, methodologyHref, wireLiveLinks, wirePageTabs } from './page_common.js';
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
const paper = document.getElementById('paper');
const toc = document.getElementById('toc');
const main = document.getElementById('main');
const chip = document.getElementById('view-chip-text');

/** The catalogue, once loaded: the badges then write out the view a cold boot would open. */
let catalogue = null;
/** Problems for the banner: the article's own, then the service's. */
const problems = { article: [], service: [] };

function showProblems() {
  banner.show([...problems.article, ...problems.service], true);
}

/** Move the reader to `id`: instantly, inside the article column, focus on the target. */
function goTo(id, { mark = false } = {}) {
  const target = document.getElementById(id);
  if (!target) return;
  target.scrollIntoView({ block: 'start', behavior: 'instant' });
  target.focus({ preventScroll: true });
  if (mark) writeAt(id);
}

/** Every badge's href, for the view in hand. */
function badgeHrefOf(link) {
  let set = {};
  try {
    set = JSON.parse(link.dataset.set || '{}');
  } catch {
    set = {};
  }
  return badgeHref({ page: link.dataset.page, panel: link.dataset.panel, set },
    { from: link.dataset.from ?? null, section: link.dataset.fromSec ?? null, catalogue });
}

const gotoHrefOf = (link) => methodologyHref(link.dataset.goto, window.location.hash);

/** Refresh every live href now (the live wiring refreshes each again as it is followed). */
function refreshLinks() {
  for (const link of document.querySelectorAll('a[data-badge]')) link.href = badgeHrefOf(link);
  for (const link of document.querySelectorAll('a[data-goto]')) link.href = gotoHrefOf(link);
}

function refreshChip() {
  const text = viewChipText({ catalogue }) ?? 'the default view';
  if (chip) chip.textContent = text;
  chip?.parentElement?.setAttribute('title', `The view the article’s links open on the other pages: ${text}`);
}

/* Scroll-spy: the TOC marks the deepest section whose top part is in the
 * upper fifth of the article column. Reading never writes the hash. */
function spy() {
  const sections = [...paper.querySelectorAll('section[data-section]')];
  const links = new Map([...toc.querySelectorAll('a[data-goto]')].map((link) => [link.dataset.goto, link]));
  const visible = new Set();
  let current = null;
  const mark = () => {
    const last = sections.filter((section) => visible.has(section)).pop();
    if (!last) return;
    const link = links.get(last.dataset.section) ?? null;
    if (link === current) return;
    current?.removeAttribute('aria-current');
    link?.setAttribute('aria-current', 'location');
    // Keep the marked entry in sight in a long outline; the sidebar scrolls, the article does not.
    link?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    current = link;
  };
  if (typeof IntersectionObserver !== 'function') return;
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) visible.add(entry.target);
      else visible.delete(entry.target);
    }
    mark();
  }, { root: main, rootMargin: '0px 0px -80% 0px', threshold: 0 });
  for (const section of sections) observer.observe(section);
}

function render() {
  const { tree, outline, errors } = layout(ARTICLE);
  paper.replaceChildren(mount(tree));
  toc.replaceChildren(mount(tocTree(outline)));
  for (const message of errors) console.warn('[calosrv] methodology:', message);
  if (errors.length) {
    problems.article = [`The article's source has ${errors.length} problem${errors.length === 1 ? '' : 's'}; `
      + `the first: ${errors[0]}`];
  }

  // The provenance line: the date now, the build from this module's own stamp, the version from the service.
  const stamp = new URL(import.meta.url).searchParams.get('v');
  fillProvenance('stamp', stamp || 'unstamped');
  fillProvenance('date', new Date().toISOString().slice(0, 10));

  wireArticle(paper, { goTo });
  wireGoto(toc, goTo);
  wireLiveLinks(document.querySelectorAll('a[data-goto]'), gotoHrefOf);
  wireLiveLinks(document.querySelectorAll('a[data-badge]'), badgeHrefOf);
  refreshLinks();
  spy();

  // A link that names a place opens there.
  const at = readAt();
  const target = at ? document.getElementById(at) : null;
  if (target && paper.contains(target)) {
    target.scrollIntoView({ block: 'start', behavior: 'instant' });
    target.focus({ preventScroll: true });
  }
}

function fillProvenance(part, text) {
  const element = paper.querySelector(`[data-provenance="${part}"]`);
  if (element) element.textContent = text;
}

// The tabs carry the view across, without this page's own key.
wirePageTabs(document, { drop: ['at'] });

try {
  render();
} catch (error) {
  console.error('[calosrv] methodology', error);
  problems.article = [`The article could not be drawn: ${describeError(error)}`];
}
refreshChip();
showProblems();
window.addEventListener('hashchange', () => {
  refreshChip();
  refreshLinks();
});

const [experiments, health] = await Promise.allSettled([
  getJson('/api/experiments', {}, 'experiments'),
  getJson('/api/health', {}, 'health'),
]);
if (experiments.status === 'fulfilled') {
  catalogue = experiments.value;
  fillComputeBadges(catalogue.compute);
} else {
  console.error('[calosrv] experiments', experiments.reason);
  problems.service.push(`The experiment catalogue could not be loaded (${describeError(experiments.reason)}); `
    + 'the article is complete, and its links carry the view in the address bar as it stands.');
}
if (health.status === 'fulfilled') {
  fillProvenance('version', String(health.value?.version ?? 'unknown version'));
} else {
  console.error('[calosrv] health', health.reason);
  fillProvenance('version', '(version unavailable)');
  problems.service.push(`The service's version could not be read (${describeError(health.reason)}).`);
}
refreshChip();
refreshLinks();
showProblems();
