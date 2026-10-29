/* The Methodology article: from its content modules to the page.
 *
 * Two layers, so the article can be checked without a browser:
 *
 * 1. `layout(article)` is pure. It numbers the sections (1, 2, 2.1, …; the
 *    appendices A, B; the References unnumbered), the equations, tables and
 *    figures in document order; checks every id (unique, with its kind's
 *    prefix); resolves the inline syntax - `$…$` TeX, `` `code` ``,
 *    `*emphasis*`, `**strong**`, `[[id]]` cross-references and
 *    `[[cite:key]]` citations, numbered by first citation - and compiles every
 *    TeX string through math.js `texToTree`. It returns `{tree, outline,
 *    errors}`: a plain node tree (`{tag, attrs, children}`, text as `{text}`,
 *    MathML as math.js builds it), the outline the TOC is drawn from, and one
 *    message per problem. One bad block never stops the article: its source is
 *    shown as code and the problem is listed in `errors`.
 * 2. `mount(tree)` builds the DOM from the tree with `createElement`,
 *    `createElementNS` (MathML through math.js `mountMath`, SVG figures) and
 *    text nodes - never markup parsed from a string, because every sentence
 *    here is data. `wireArticle` then gives the equations their TeX panels and
 *    the in-article links their behaviour.
 *
 * The content model and the inline syntax are the shared brief's
 * (data/dev/design/methodology/brief.md, §3-§7); the numbers the prose quotes
 * come from methodology/constants.js, and Appendix B is generated from it.
 */

import { mountMath, texToTree } from '../math.js';
import { methodologyHref } from '../page_common.js';
import { MINUS } from '../format.js';
import { CONSTANTS } from './constants.js';
import { EXHIBITS } from './exhibits.js';
import { badgeBase, badgeText } from './links.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const SUPERSCRIPT = ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹'];

/** The id prefix each kind of target must carry. */
export const ID_PREFIX = Object.freeze({
  section: /^sec-[a-z0-9-]+$/,
  appendix: /^app-[a-z0-9-]+$/,
  eq: /^eq-[a-z0-9-]+$/,
  table: /^tab-[a-z0-9-]+$/,
  figure: /^fig-[a-z0-9-]+$/,
  links: /^lnk-[a-z0-9-]+$/,
});

export const REFERENCES_ID = 'sec-references';
const BLOCK_KINDS = new Set(['p', 'eq', 'list', 'table', 'figure', 'callout', 'links']);
const CALLOUT_TONES = new Set(['rule', 'note', 'caution']);
const CALLOUT_TITLES = { rule: 'Rule', note: 'Note', caution: 'Caution' };

/* ------------------------------------------------------------- nodes -- */

/** An element node: `h('p', {class: 'x'}, child, …)`; strings become text nodes. */
export function h(tag, attrs = {}, ...children) {
  return {
    tag,
    attrs: attrs ?? {},
    children: children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false)
      .map((c) => (typeof c === 'string' ? { text: c } : c)),
  };
}

/** Every text a node tree holds, in order, as one string. */
export function textOf(node) {
  if (!node) return '';
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node.tag === 'annotation') return '';
  if (typeof node.text === 'string') return node.text;
  return (node.children ?? []).map(textOf).join('');
}

/** A deep copy with every link turned into a span: a title shown inside another link. */
function unlinked(nodes) {
  return nodes.map((node) => {
    if (!node.tag || node.tag === 'math') return node;
    return { ...node, tag: node.tag === 'a' ? 'span' : node.tag, attrs: node.tag === 'a' ? { class: 'xref' } : node.attrs,
      children: unlinked(node.children ?? []) };
  });
}

/** A number as the article prints it: U+2212 for a negative, ten significant figures. */
export function formatValue(value) {
  if (typeof value === 'number') {
    const shown = Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(10)));
    return shown.replace(/^-/, MINUS).replace(/e([+-]?)(\d+)$/,
      (_, sign, exp) => ` × 10${sign === '-' ? '⁻' : ''}${[...exp].map((d) => SUPERSCRIPT[Number(d)]).join('')}`);
  }
  if (Array.isArray(value)) return value.map(formatValue).join(', ');
  return String(value);
}

/* ------------------------------------------------------------ layout -- */

/**
 * Lay the article out: `{tree, outline, errors}` (see the header). `compile`
 * is the TeX compiler, math.js `texToTree` unless a test passes another.
 */
export function layout(article, { compile = texToTree, constants = CONSTANTS } = {}) {
  const ctx = {
    compile,
    errors: [],
    targets: new Map(),   // id -> {kind, label}
    cites: new Map(),     // key -> number, in order of first citation
    references: new Map((article?.references ?? []).map((r) => [r.key, r.text])),
    section: null,        // the number of the section being rendered
    mathCount: 0,
  };
  const error = (message) => ctx.errors.push(message);
  ctx.error = error;

  for (const ref of article?.references ?? []) {
    if (!ref?.key || !ref?.text) error(`references: an entry needs a key and a text (${JSON.stringify(ref)})`);
  }

  // Pass 1: number every target, so a reference may point forward.
  const counters = { eq: 0, table: 0, figure: 0 };
  const plan = [];
  const register = (id, kind, label, where) => {
    if (!id) return;
    if (ctx.targets.has(id)) {
      error(`${where}: duplicate id ${id}`);
      return;
    }
    ctx.targets.set(id, { kind, label });
  };
  const checkId = (id, kind, where) => {
    if (!id) {
      error(`${where}: a ${kind} without an id`);
      return false;
    }
    if (!ID_PREFIX[kind].test(id)) error(`${where}: id ${id} does not have the ${kind} prefix`);
    return true;
  };
  const numberBlocks = (blocks, where, section) => {
    (blocks ?? []).forEach((block, i) => {
      const at = `${where} block ${i} (${block?.kind})`;
      if (block?.kind === 'eq' && block.numbered !== false) {
        counters.eq += 1;
        block.__number = counters.eq;
        if (checkId(block.id, 'eq', at)) register(block.id, 'eq', `(${counters.eq})`, at);
      } else if (block?.kind === 'table') {
        counters.table += 1;
        block.__number = counters.table;
        if (checkId(block.id, 'table', at)) register(block.id, 'table', `Table ${counters.table}`, at);
      } else if (block?.kind === 'figure') {
        counters.figure += 1;
        block.__number = counters.figure;
        if (checkId(block.id, 'figure', at)) register(block.id, 'figure', `Figure ${counters.figure}`, at);
      } else if (block?.kind === 'links') {
        if (checkId(block.id, 'links', at)) register(block.id, 'links', section.ref, at);
      }
    });
  };
  const numberSection = (part, number, level, appendix) => {
    const where = part?.id ?? `section ${number}`;
    const ref = appendix ? `Appendix ${number}` : `§${number}`;
    const entry = { part: part ?? {}, number, level, appendix, ref, children: [] };
    if (checkId(part?.id, appendix && level === 1 ? 'appendix' : 'section', where)) register(part.id, 'section', ref, where);
    if (!part?.generated) numberBlocks(part?.blocks, where, entry);
    else if (part.generated === 'constants') {
      counters.table += 1;
      entry.constantsTable = counters.table;
      register('tab-constants', 'table', `Table ${counters.table}`, where);
    }
    (part?.sections ?? []).forEach((child, i) => {
      entry.children.push(numberSection(child, `${number}.${i + 1}`, level + 1, appendix));
    });
    return entry;
  };
  // Blocks are annotated with their numbers on copies, never on the content modules.
  const copy = (part) => (part ? {
    ...part,
    blocks: (part.blocks ?? []).map((b) => (b && typeof b === 'object' ? { ...b } : b)),
    sections: (part.sections ?? []).map(copy),
  } : part);
  (article?.sections ?? []).forEach((part, i) => plan.push(numberSection(copy(part), String(i + 1), 1, false)));
  const references = { part: { id: REFERENCES_ID, title: 'References' }, number: '', level: 1, ref: 'References', children: [] };
  register(REFERENCES_ID, 'section', 'References', 'references');
  const appendices = (article?.appendices ?? []).map((part, i) => numberSection(copy(part), String.fromCharCode(65 + i), 1, true));

  // Pass 2: render in document order. References are listed last, once every citation is known.
  const front = renderFront(article?.front ?? {}, ctx);
  const body = plan.map((entry) => renderSection(entry, ctx, constants));
  const tail = appendices.map((entry) => renderSection(entry, ctx, constants));
  const referencesNode = renderReferences(references, ctx);

  const outline = [...plan, references, ...appendices].map(outlineOf);
  const tree = h('div', { class: 'article' }, front, body, referencesNode, tail);
  return { tree, outline, errors: ctx.errors };
}

function outlineOf(entry) {
  return {
    id: entry.part.id,
    number: entry.number,
    level: entry.level,
    appendix: Boolean(entry.appendix),
    title: entry.titleNodes ? unlinked(entry.titleNodes) : [{ text: String(entry.part.title ?? '') }],
    children: entry.children.map(outlineOf),
  };
}

/* ------------------------------------------------------------ inline -- */

/** Split inline text into tokens: text, code, math, reference, citation and emphasis delimiters. */
export function tokenize(text) {
  const source = String(text ?? '');
  const tokens = [];
  let buffer = '';
  const flush = () => {
    if (buffer) tokens.push({ type: 'text', value: buffer });
    buffer = '';
  };
  let i = 0;
  while (i < source.length) {
    const c = source[i];
    if (c === '\\' && source[i + 1] === '$') {
      buffer += '$';
      i += 2;
      continue;
    }
    if (c === '`') {
      const end = source.indexOf('`', i + 1);
      if (end > i) {
        flush();
        tokens.push({ type: 'code', value: source.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (c === '$') {
      let end = i + 1;
      while (end < source.length && !(source[end] === '$' && source[end - 1] !== '\\')) end += 1;
      if (end < source.length) {
        flush();
        tokens.push({ type: 'math', value: source.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
      flush();
      tokens.push({ type: 'unpaired', value: '$' });
      i += 1;
      continue;
    }
    if (c === '[' && source[i + 1] === '[') {
      const end = source.indexOf(']]', i + 2);
      if (end > i) {
        flush();
        const target = source.slice(i + 2, end).trim();
        tokens.push(target.startsWith('cite:') ? { type: 'cite', value: target.slice(5).trim() } : { type: 'ref', value: target });
        i = end + 2;
        continue;
      }
    }
    if (c === '*') {
      const delim = source[i + 1] === '*' ? '**' : '*';
      const before = source[i - 1];
      const after = source[i + delim.length];
      const canOpen = after !== undefined && !/\s/.test(after);
      const canClose = before !== undefined && !/\s/.test(before);
      if (canOpen || canClose) {
        flush();
        tokens.push({ type: 'delim', value: delim, canOpen, canClose });
        i += delim.length;
        continue;
      }
    }
    buffer += c;
    i += 1;
  }
  flush();
  return tokens;
}

/** The inline nodes of `text`; `where` names it in an error. */
export function inline(text, ctx, where) {
  if (typeof text !== 'string') {
    ctx.error(`${where}: text is not a string`);
    return [{ text: String(text ?? '') }];
  }
  const tokens = tokenize(text);
  const root = { delim: null, children: [] };
  const stack = [root];
  const top = () => stack[stack.length - 1];
  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    switch (token.type) {
      case 'text':
        top().children.push({ text: token.value });
        break;
      case 'code':
        top().children.push(h('code', {}, token.value));
        break;
      case 'math':
        top().children.push(inlineMath(token.value, ctx, where));
        break;
      case 'unpaired':
        ctx.error(`${where}: an unpaired $ (write \\$ for a dollar sign)`);
        top().children.push({ text: '$' });
        break;
      case 'ref': {
        // "([[eq-se3]])" reads "(3)", not "((3))": an equation's own brackets give way to the prose's.
        const bracketed = tokens[i - 1]?.type === 'text' && tokens[i - 1].value.endsWith('(')
          && tokens[i + 1]?.type === 'text' && tokens[i + 1].value.startsWith(')');
        top().children.push(crossReference(token.value, ctx, where, { bracketed }));
        break;
      }
      case 'cite': {
        // Adjacent citations share one bracket: [3, 5].
        const keys = [token.value];
        while (tokens[i + 1]?.type === 'cite') {
          i += 1;
          keys.push(tokens[i].value);
        }
        top().children.push(citation(keys, ctx, where));
        break;
      }
      case 'delim': {
        const frame = top();
        if (frame.delim === token.value && token.canClose) {
          stack.pop();
          top().children.push(h(token.value === '**' ? 'strong' : 'em', {}, frame.children));
        } else if (token.canOpen) {
          stack.push({ delim: token.value, children: [] });
        } else {
          frame.children.push({ text: token.value });
        }
        break;
      }
      default:
        break;
    }
  }
  // An unclosed delimiter was a literal asterisk.
  while (stack.length > 1) {
    const frame = stack.pop();
    top().children.push({ text: frame.delim }, ...frame.children);
  }
  return mergeText(root.children);
}

function mergeText(nodes) {
  const out = [];
  for (const node of nodes) {
    const last = out[out.length - 1];
    if (node.tag === undefined && last && last.tag === undefined) last.text += node.text;
    else out.push(node.tag === undefined ? { text: node.text } : node);
  }
  return out;
}

/** Inline TeX: its MathML, or its source as code when it does not compile. */
function inlineMath(tex, ctx, where) {
  try {
    return ctx.compile(tex, { display: false });
  } catch (error) {
    ctx.error(`${where}: TeX does not compile (${error?.message ?? error}): ${tex}`);
    return h('code', { class: 'tex-error', title: String(error?.message ?? error) }, tex);
  }
}

/** An in-article link: live href, scrolls in place (wireArticle). */
function gotoLink(id, label, { cls = 'xref', mark = false } = {}) {
  const attrs = { class: cls, href: methodologyHref(id, ''), 'data-goto': id };
  if (mark) attrs['data-mark'] = '';
  return h('a', attrs, label);
}

function crossReference(id, ctx, where, { bracketed = false } = {}) {
  const target = ctx.targets.get(id);
  if (!target) {
    ctx.error(`${where}: unknown reference [[${id}]]`);
    return h('span', { class: 'ref-missing', title: 'Unknown reference' }, `[[${id}]]`);
  }
  const label = bracketed && target.kind === 'eq' ? target.label.slice(1, -1) : target.label;
  return gotoLink(id, label);
}

function citation(keys, ctx, where) {
  const parts = [];
  keys.forEach((key, i) => {
    if (i) parts.push(', ');
    if (!ctx.references.has(key)) {
      ctx.error(`${where}: unknown citation [[cite:${key}]]`);
      parts.push(h('span', { class: 'ref-missing', title: `Unknown citation ${key}` }, '?'));
      return;
    }
    if (!ctx.cites.has(key)) ctx.cites.set(key, ctx.cites.size + 1);
    parts.push(gotoLink(`ref-${key}`, String(ctx.cites.get(key)), { cls: 'cite-link' }));
  });
  return h('span', { class: 'cite' }, '[', parts, ']');
}

/* ------------------------------------------------------------- front -- */

function renderFront(front, ctx) {
  const authors = (front.authors ?? []).map((author, i) => [
    i ? ', ' : '',
    h('span', { class: 'author' }, author.name, h('sup', {}, (author.affiliations ?? []).join(','))),
  ]);
  const affiliations = (front.affiliations ?? []).map((a) => h('li', {}, h('sup', {}, String(a.id)), ' ', a.text));
  const abstract = (front.abstract ?? []).map((text, i) => h('p', {}, inline(text, ctx, `abstract ${i}`)));
  const keywords = (front.keywords ?? []).filter(Boolean);
  return h('header', { class: 'front' },
    h('h1', { class: 'article-title' }, inline(front.title ?? '', ctx, 'title')),
    h('p', { class: 'authors' }, authors),
    affiliations.length ? h('ol', { class: 'affiliations' }, affiliations) : null,
    h('p', { class: 'provenance' },
      'calosrv ', h('span', { 'data-provenance': 'version' }, '…'),
      ' · static build ', h('span', { 'data-provenance': 'stamp' }, '…'),
      ' · rendered ', h('span', { 'data-provenance': 'date' }, '…')),
    abstract.length ? h('section', { class: 'abstract', 'aria-label': 'Abstract' },
      h('h2', { class: 'abstract-heading' }, 'Abstract'), abstract) : null,
    keywords.length ? h('p', { class: 'keywords' }, h('span', { class: 'keywords-label' }, 'Keywords'), ' ',
      keywords.map((k, i) => [i ? ' · ' : '', inline(k, ctx, `keyword ${i}`)])) : null);
}

/* ---------------------------------------------------------- sections -- */

function heading(entry, ctx) {
  const { part, number, level, appendix } = entry;
  const where = part.id ?? `section ${number}`;
  entry.titleNodes = inline(part.title ?? '', ctx, `${where} title`);
  if (!part.title) ctx.error(`${where}: a section without a title`);
  const tag = `h${Math.min(level + 1, 6)}`;
  const shown = appendix && level === 1 ? `Appendix ${number}` : number;
  return h(tag, { id: part.id, tabindex: '-1', class: 'section-heading' },
    shown ? h('span', { class: 'sec-number' }, shown) : null,
    shown ? ' ' : null,
    h('span', { class: 'sec-title' }, entry.titleNodes),
    ' ',
    gotoLink(part.id, '¶', { cls: 'heading-anchor', mark: true }));
}

function renderSection(entry, ctx, constants) {
  const { part, level } = entry;
  ctx.section = entry;
  const blocks = part.generated === 'constants'
    ? constantsAppendix(entry, constants, ctx)
    : (part.blocks ?? []).map((block, i) => renderBlock(block, ctx, `${part.id} block ${i}`));
  const children = entry.children.map((child) => renderSection(child, ctx, constants));
  ctx.section = entry;
  return h('section', { class: `article-section level-${level}`, 'data-section': part.id, 'aria-labelledby': part.id },
    heading(entry, ctx), blocks, children);
}

function renderBlock(block, ctx, where) {
  const at = `${where} (${block?.kind})`;
  try {
    if (!block || !BLOCK_KINDS.has(block.kind)) throw new Error(`unknown block kind ${block?.kind}`);
    switch (block.kind) {
      case 'p': return h('p', {}, inline(block.text, ctx, at));
      case 'eq': return equation(block, ctx, at);
      case 'list': return h(block.ordered ? 'ol' : 'ul', { class: 'article-list' },
        (block.items ?? []).map((item, i) => h('li', {}, inline(item, ctx, `${at} item ${i}`))));
      case 'table': return table(block, ctx, at);
      case 'figure': return figure(block, ctx, at);
      case 'callout': return callout(block, ctx, at);
      case 'links': return linksRow(block, ctx, at);
      default: return null;
    }
  } catch (error) {
    ctx.error(`${at}: ${error?.message ?? error}`);
    return h('pre', { class: 'block-error' }, h('code', {}, safeJson(block)));
  }
}

function safeJson(value) {
  try {
    return JSON.stringify(value, (k, v) => (k.startsWith('__') ? undefined : v), 2);
  } catch {
    return String(value);
  }
}

/** A display equation: the math, its number, and the TeX source behind a toggle. */
function equation(block, ctx, where) {
  const numbered = block.numbered !== false;
  ctx.mathCount += 1;
  const id = numbered && block.id ? block.id : `math-${ctx.mathCount}`;
  const panelId = `${id}-tex`;
  const tex = String(block.tex ?? '');
  let math;
  try {
    math = ctx.compile(tex, { display: true });
  } catch (error) {
    ctx.error(`${where}: TeX does not compile (${error?.message ?? error}): ${tex}`);
    math = h('pre', { class: 'tex-error' }, h('code', {}, tex));
  }
  const attrs = { class: numbered ? 'math-display equation' : 'math-display', tabindex: '-1' };
  if (numbered && block.id) attrs.id = block.id;
  return h('figure', attrs,
    h('div', { class: 'eq-row' },
      h('div', { class: 'eq-math', title: 'Show the LaTeX source', 'data-tex-math': panelId }, math),
      numbered ? gotoLink(id, `(${block.__number})`, { cls: 'eq-number', mark: true }) : null,
      h('button', {
        type: 'button', class: 'tex-toggle', 'aria-expanded': 'false', 'aria-controls': panelId,
        'data-tex-toggle': panelId, title: 'Show the LaTeX source',
      }, 'TeX')),
    h('div', { class: 'tex-panel', id: panelId, hidden: true },
      h('pre', {}, h('code', {}, tex)),
      h('div', { class: 'tex-actions' },
        h('button', { type: 'button', class: 'tex-copy', 'data-tex-copy': panelId }, 'Copy'),
        h('span', { class: 'tex-status', role: 'status', 'aria-live': 'polite' }))));
}

/** A table: caption above, booktabs rules (methodology.css), an optional note below. */
function table(block, ctx, where, { cells = null, cls = '' } = {}) {
  const captionId = `${block.id ?? `table-${block.__number}`}-caption`;
  const cell = (value, at) => (Array.isArray(value) ? value : inline(String(value ?? ''), ctx, at));
  const head = (block.head ?? []).map((value, j) => h('th', { scope: 'col' }, cell(value, `${where} head ${j}`)));
  const width = head.length;
  const rows = (cells ?? block.rows ?? []).map((row, r) => {
    if (!Array.isArray(row)) throw new Error(`row ${r} is not a list`);
    if (width && row.length !== width) ctx.error(`${where}: row ${r} has ${row.length} cells, the head ${width}`);
    return h('tr', {}, row.map((value, j) => h('td', {}, cell(value, `${where} row ${r} cell ${j}`))));
  });
  return h('figure', { class: `article-table${cls ? ` ${cls}` : ''}`, id: block.id, tabindex: '-1' },
    h('figcaption', { id: captionId },
      h('span', { class: 'caption-label' }, `Table ${block.__number}.`), ' ',
      inline(block.caption ?? '', ctx, `${where} caption`)),
    h('div', { class: 'table-scroll' },
      h('table', { 'aria-labelledby': captionId },
        width ? h('thead', {}, h('tr', {}, head)) : null,
        h('tbody', {}, rows))),
    block.note ? h('p', { class: 'table-note' }, inline(block.note, ctx, `${where} note`)) : null);
}

/** A computed figure: the exhibit's SVG, the caption below. */
function figure(block, ctx, where) {
  const build = EXHIBITS[block.exhibit];
  let body;
  if (!build) {
    ctx.error(`${where}: unknown exhibit ${block.exhibit}`);
    body = h('p', { class: 'block-error' }, `Unknown exhibit: ${block.exhibit}`);
  } else {
    body = build(block.id ?? `fig-${block.__number}`);
  }
  return h('figure', { class: 'article-figure', id: block.id, tabindex: '-1' },
    h('div', { class: 'exhibit' }, body),
    h('figcaption', {},
      h('span', { class: 'caption-label' }, `Figure ${block.__number}.`), ' ',
      inline(block.caption ?? '', ctx, `${where} caption`)));
}

function callout(block, ctx, where) {
  const tone = CALLOUT_TONES.has(block.tone) ? block.tone : 'note';
  if (!CALLOUT_TONES.has(block.tone)) ctx.error(`${where}: unknown callout tone ${block.tone}`);
  const paragraphs = String(block.text ?? '').split(/\n\s*\n/).map((text, i) => h('p', {}, inline(text, ctx, `${where} paragraph ${i}`)));
  return h('aside', { class: `callout callout-${tone}` },
    h('p', { class: 'callout-title' }, h('span', { class: 'callout-tone' }, CALLOUT_TITLES[tone]),
      block.title ? [' · ', inline(block.title, ctx, `${where} title`)] : null),
    paragraphs);
}

/** A badge row: one link per panel, each opening the live panel with the reader's view (links.js). */
function linksRow(block, ctx, where) {
  const section = ctx.section?.appendix ? null : ctx.section?.number ?? null;
  const items = (block.items ?? []).map((item, i) => {
    if (!item?.page || !item?.panel || !item?.label) ctx.error(`${where} item ${i}: a badge needs page, panel and label`);
    const attrs = {
      class: 'link-badge', href: badgeBase(item, { from: block.id, section }), 'data-badge': '',
      'data-page': item.page, 'data-panel': item.panel, 'data-set': JSON.stringify(item.set ?? {}),
    };
    if (block.id) attrs['data-from'] = block.id;
    if (section) attrs['data-from-sec'] = section;
    return h('a', attrs, badgeText(item));
  });
  return h('div', { class: 'links-row', id: block.id, tabindex: '-1', role: 'group', 'aria-label': 'Open the live panels' }, items);
}

/* -------------------------------------------------------- references -- */

function renderReferences(entry, ctx) {
  const cited = [...ctx.cites.entries()].sort((a, b) => a[1] - b[1]);
  entry.titleNodes = [{ text: 'References' }];
  const list = cited.map(([key, n]) => h('li', { id: `ref-${key}`, tabindex: '-1' },
    h('span', { class: 'ref-number' }, `[${n}]`), ' ', ctx.references.get(key)));
  return h('section', { class: 'article-section level-1 references', 'data-section': REFERENCES_ID, 'aria-labelledby': REFERENCES_ID },
    h('h2', { id: REFERENCES_ID, tabindex: '-1', class: 'section-heading' },
      h('span', { class: 'sec-title' }, 'References'), ' ',
      gotoLink(REFERENCES_ID, '¶', { cls: 'heading-anchor', mark: true })),
    list.length ? h('ol', { class: 'reference-list' }, list) : h('p', { class: 'muted' }, 'No work is cited yet.'));
}

/* -------------------------------------------------------- appendix B -- */

/** Appendix B: one row per constant the prose may quote, with the code it is read from. */
function constantsAppendix(entry, constants, ctx) {
  const rows = Object.entries(constants).map(([name, { value, source, meaning }]) => [
    [h('code', {}, name)],
    typeof value === 'string' ? [h('code', {}, value)] : [{ text: formatValue(value) }],
    [{ text: String(meaning ?? '') }],
    [h('code', {}, String(source ?? ''))],
  ]);
  const block = { id: 'tab-constants', __number: entry.constantsTable, head: ['Name', 'Value', 'Meaning', 'Source'],
    caption: 'Every constant of the code the article quotes, with the module and expression it is read from.' };
  return [
    h('p', {}, 'The prose never types one of these numbers: it reads each from ', h('code', {}, 'methodology/constants.js'), ', and ',
      h('code', {}, 'tests/test_methodology_constants.py'),
      ' resolves every source below against the running code, so the article cannot drift from what the service does. '
      + 'A source is a Python expression in a module (py), a JavaScript expression under static/js (js), or a snippet '
      + 'the value must appear in (text).'),
    table(block, ctx, 'app-constants', { cells: rows, cls: 'constants-table' }),
  ];
}

/* -------------------------------------------------------------- mount -- */

/** Build `node` as DOM nodes of `doc`: elements, SVG, MathML and text nodes only. */
export function mount(node, doc = document, ns = null) {
  if (node.tag === undefined) return doc.createTextNode(String(node.text ?? ''));
  if (node.tag === 'math') return mountMath(node, doc);
  const svg = ns === SVG_NS || node.tag === 'svg';
  const element = svg ? doc.createElementNS(SVG_NS, node.tag) : doc.createElement(node.tag);
  for (const [name, value] of Object.entries(node.attrs ?? {})) {
    if (value === null || value === undefined || value === false || name === 'xmlns') continue;
    element.setAttribute(name, value === true ? '' : String(value));
  }
  if (typeof node.text === 'string') element.append(doc.createTextNode(node.text));
  for (const child of node.children ?? []) element.append(mount(child, doc, svg ? SVG_NS : null));
  return element;
}

/** The TOC's nested list, from the outline: numbered entries that move the reader and mark `at`. */
export function tocTree(outline) {
  const list = (entries) => h('ol', { class: 'toc-list' }, entries.map((entry) => h('li', {},
    h('a', { class: 'toc-link', href: methodologyHref(entry.id, ''), 'data-goto': entry.id, 'data-mark': '' },
      entry.number ? h('span', { class: 'toc-number' }, entry.number) : null,
      h('span', { class: 'toc-title' }, entry.title)),
    entry.children.length ? list(entry.children) : null)));
  return list(outline);
}

/* ------------------------------------------------------------- wiring -- */

/**
 * Behaviour of a mounted article: the TeX panels (the toggle, a click on the
 * math, Copy, Escape) and the in-article links (`goTo(id, {mark})` for a
 * plain click; a modified click keeps the browser's own behaviour, on the
 * live href the caller keeps current).
 */
export function wireArticle(root, { goTo = () => {}, doc = document } = {}) {
  const toggles = new Map();
  for (const button of root.querySelectorAll('[data-tex-toggle]')) {
    toggles.set(button.dataset.texToggle, button);
    button.addEventListener('click', () => setPanel(button, null, doc));
  }
  for (const math of root.querySelectorAll('[data-tex-math]')) {
    math.addEventListener('click', (event) => {
      // A click that ends a text selection is a selection, not a toggle.
      if (String(doc.getSelection?.() ?? '').length) return;
      const button = toggles.get(math.dataset.texMath);
      if (button) setPanel(button, null, doc);
      event.stopPropagation();
    });
  }
  for (const copy of root.querySelectorAll('[data-tex-copy]')) {
    copy.addEventListener('click', () => copySource(doc.getElementById(copy.dataset.texCopy), doc));
  }
  doc.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    for (const button of toggles.values()) {
      if (button.getAttribute('aria-expanded') !== 'true') continue;
      const panel = doc.getElementById(button.dataset.texToggle);
      const inside = panel?.contains(doc.activeElement);
      setPanel(button, false, doc);
      if (inside) button.focus();
    }
  });
  wireGoto(root, goTo);
}

/**
 * The in-article links under `root` (`a[data-goto]`): a plain click calls
 * `goTo(id, {mark})`, `mark` set on the links that record the reader's place
 * (a TOC entry, a heading's anchor, an equation's number). A modified click
 * - a new tab, a copied address - keeps the browser's own behaviour.
 */
export function wireGoto(root, goTo) {
  for (const link of root.querySelectorAll('a[data-goto]')) {
    link.addEventListener('click', (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      goTo(link.dataset.goto, { mark: link.hasAttribute('data-mark') });
    });
  }
}

/** Open (true), close (false) or toggle (null) one equation's TeX panel. */
function setPanel(button, open, doc) {
  const panel = doc.getElementById(button.dataset.texToggle);
  if (!panel) return;
  const show = open === null ? panel.hidden : open;
  panel.hidden = !show;
  button.setAttribute('aria-expanded', String(show));
  const title = show ? 'Hide the LaTeX source' : 'Show the LaTeX source';
  button.title = title;
  const math = panel.parentElement?.querySelector('[data-tex-math]');
  if (math) math.title = title;
}

/** Copy a panel's source; where the clipboard is refused, select it for the reader to copy. */
async function copySource(panel, doc) {
  const code = panel?.querySelector('code');
  const status = panel?.querySelector('.tex-status');
  if (!code) return;
  const say = (text) => { if (status) status.textContent = text; };
  try {
    await navigator.clipboard.writeText(code.textContent);
    say('Copied.');
  } catch {
    const selection = doc.getSelection?.();
    selection?.selectAllChildren(code);
    say('Selected: press Ctrl+C (⌘C) to copy.');
  }
}
