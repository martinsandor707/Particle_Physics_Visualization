/* The Methodology article as a LaTeX document and a BibTeX file.
 *
 * The page's Export button (methodology/export.js) hands a reader the article
 * as source they can build and edit: `methodology.tex`, `references.bib` and
 * the figures. This module writes the first two from the same content modules
 * the page renders, so the two outputs cannot say different things:
 *
 * - the inline syntax is split by render.js `tokenize`, so a `$`, a code span
 *   or a cross-reference parses here exactly as it does on the page;
 * - sections, equations, tables and figures are numbered by LaTeX's own
 *   counters in the order the page numbers them (render.js `layout`), so
 *   "Table 3" in the PDF is "Table 3" on the page; tests/test_js_latex.py
 *   counts both;
 * - Appendix B is generated from methodology/constants.js as render.js
 *   `constantsAppendix` generates it, with the same sentence and caption.
 *
 * The output is ASCII only. Every non-ASCII character of the prose goes
 * through one table (`UNICODE`, below) to a LaTeX command, and a character the
 * table does not know is reported in `errors` and written as "?", never
 * passed through: pdfLaTeX with T1 fonts would otherwise stop on it, or drop it
 * with no more than a "Missing character" line in the log. U+2212 becomes a
 * math minus, so the rule that every rendered negative number carries the
 * minus sign holds in the PDF too; the TeX of the equations, which writes `-`,
 * is copied unchanged.
 *
 * The module is pure - no DOM, no network - so it runs under Node in the
 * tests, and it never throws on bad content: a problem is listed in `errors`
 * and the document is still written, as render.js draws a bad block as code.
 * The contract is data/dev/design/methodology/export-brief.md §3-§4.
 */

import { CONSTANTS } from './constants.js';
import { formatValue, REFERENCES_ID, tokenize } from './render.js';

/* ---------------------------------------------------- the Unicode map -- */

/* Greek letters by the command whose glyph matches the page's: the article
 * types U+03C6 for the azimuth, which the page draws as the curly φ, so it is
 * \varphi; U+03D5 is the straight \phi. The micro sign is the letter mu. */
const GREEK = Object.freeze({
  'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'ε': 'varepsilon', 'ϵ': 'epsilon', 'ζ': 'zeta',
  'η': 'eta', 'θ': 'theta', 'ϑ': 'vartheta', 'ι': 'iota', 'κ': 'kappa', 'λ': 'lambda', 'μ': 'mu', 'µ': 'mu',
  'ν': 'nu', 'ξ': 'xi', 'π': 'pi', 'ρ': 'rho', 'ϱ': 'varrho', 'σ': 'sigma', 'ς': 'varsigma', 'τ': 'tau',
  'υ': 'upsilon', 'φ': 'varphi', 'ϕ': 'phi', 'χ': 'chi', 'ψ': 'psi', 'ω': 'omega',
  'Γ': 'Gamma', 'Δ': 'Delta', 'Θ': 'Theta', 'Λ': 'Lambda', 'Ξ': 'Xi', 'Π': 'Pi', 'Σ': 'Sigma',
  'Υ': 'Upsilon', 'Φ': 'Phi', 'Ψ': 'Psi', 'Ω': 'Omega',
});

/* Symbols that only exist in math mode, set through \ensuremath so they work
 * in running text, captions and BibTeX fields alike. */
const MATH_SYMBOLS = Object.freeze({
  '−': '-', '×': '\\times', '±': '\\pm', '∓': '\\mp', '≥': '\\geq', '≤': '\\leq', '≈': '\\approx',
  '≠': '\\neq', '∞': '\\infty', '∈': '\\in', '∝': '\\propto', '∼': '\\sim', '→': '\\rightarrow',
  '←': '\\leftarrow', '↔': '\\leftrightarrow', '⇒': '\\Rightarrow', '⊗': '\\otimes', '√': '\\surd',
  '⟨': '\\langle', '⟩': '\\rangle', '·': '\\cdot', '°': '^{\\circ}', '′': "'", '″': "''", '÷': '\\div',
});

/* Text-mode punctuation and spaces. The quotes become TeX's ligature quotes,
 * which T1 sets as the curly marks the page shows. */
const TEXT_SYMBOLS = Object.freeze({
  '–': '--', '—': '---', '’': "'", '‘': '`', '“': '``', '”': "''", '§': '\\S{}', '›': '\\guilsinglright{}',
  '‹': '\\guilsinglleft{}', '«': '\\guillemotleft{}', '»': '\\guillemotright{}', '…': '\\ldots{}',
  '•': '\\textbullet{}', '\u00a0': '~', '\u2009': '\\,', '\u202f': '\\,', '\u2010': '-', '\u2011': '\\mbox{-}',
});

/* Letters with no decomposition, as text commands. */
const LETTERS = Object.freeze({
  'ß': 'ss', 'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ł': 'l', 'Ł': 'L', 'ı': 'i',
});

/* Combining marks (the second half of an NFD decomposition) by accent command. */
const ACCENTS = Object.freeze({
  '\u0300': '`', '\u0301': "'", '\u0302': '^', '\u0303': '~', '\u0304': '=', '\u0306': 'u', '\u0307': '.',
  '\u0308': '"', '\u030a': 'r', '\u030b': 'H', '\u030c': 'v', '\u0327': 'c', '\u0328': 'k',
});

const SUPERSCRIPTS = Object.freeze({
  '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁺': '+', '⁻': '-',
});
const SUBSCRIPTS = Object.freeze({
  '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9', '₊': '+', '₋': '-',
});

/* ASCII characters LaTeX reads as markup, in running text. `<`, `>` and `|`
 * are commands because T1 would set `<<` as a guillemet and `|` as a dash. */
const TEXT_ESCAPES = Object.freeze({
  '\\': '\\textbackslash{}', '{': '\\{', '}': '\\}', '$': '\\$', '&': '\\&', '#': '\\#', '%': '\\%', '_': '\\_',
  '~': '\\textasciitilde{}', '^': '\\textasciicircum{}', '<': '\\textless{}', '>': '\\textgreater{}',
  '|': '\\textbar{}', '`': '\\textasciigrave{}',
});

/* The same in a code span, where the quotes must stay straight. */
const CODE_ESCAPES = Object.freeze({
  ...TEXT_ESCAPES, '"': '\\textquotedbl{}', "'": '\\textquotesingle{}',
});

/* After these a long identifier or path may break across lines; after a hyphen
 * too, so a card id such as pred-residuals fits a narrow table column. */
const CODE_BREAKS = new Set(['/', '.', '_', ':', ',', '-']);

/** An accented letter (by NFD) as LaTeX: `\'{a}`, `\'{\i}`, `\H{o}`; null if it is not one. */
function accented(c) {
  const [base, ...marks] = [...c.normalize('NFD')];
  if (!marks.length || !/^[A-Za-z]$/.test(base) || marks.some((m) => !ACCENTS[m])) return null;
  // An accent sits on the dotless i and j, as \'{\i}.
  let out = base === 'i' ? '\\i' : base === 'j' ? '\\j' : base;
  for (const mark of marks) out = `\\${ACCENTS[mark]}{${out}}`;
  return out;
}

/* ------------------------------------------------------- text escapes -- */

/** Whether a quote mark after `prev` opens a quotation: at the start, after a space or an opening bracket. */
const opensQuote = (prev) => prev === '' || /\s/.test(prev) || '([{“‘–—'.includes(prev);

/**
 * Running text as LaTeX. `q.prev` carries the last character written across
 * calls, so a quote after a code span or an emphasis closes as it should;
 * `bib` braces every accent and letter command, as BibTeX needs to keep them
 * whole when it changes case or abbreviates names.
 */
function escapeText(source, ctx, where, q = { prev: '' }, { bib = false } = {}) {
  const chars = [...String(source ?? '')];
  let out = '';
  // The Greek letter just written, so that a superscript run after it shares its math group (σ² -> \sigma^{2}).
  let greek = null;
  for (let i = 0; i < chars.length; i += 1) {
    const c = chars[i];
    const scripts = SUPERSCRIPTS[c] !== undefined ? SUPERSCRIPTS : SUBSCRIPTS[c] !== undefined ? SUBSCRIPTS : null;
    if (scripts) {
      let run = '';
      while (i < chars.length && scripts[chars[i]] !== undefined) {
        run += scripts[chars[i]];
        i += 1;
      }
      i -= 1;
      const script = `${scripts === SUPERSCRIPTS ? '^' : '_'}{${run}}`;
      if (greek) out = `${out.slice(0, -greek.length)}\\ensuremath{\\${GREEK[greek.char]}${script}}`;
      else out += `\\ensuremath{${script}}`;
      greek = null;
      q.prev = 'x';
      continue;
    }
    greek = null;
    let piece;
    if (c === '"') {
      piece = opensQuote(q.prev) ? '``' : "''";
    } else if (c === "'") {
      piece = opensQuote(q.prev) && chars[i + 1] !== undefined && !/\s/.test(chars[i + 1]) ? '`' : "'";
    } else if (TEXT_ESCAPES[c]) {
      piece = TEXT_ESCAPES[c];
    } else if (c.charCodeAt(0) < 128) {
      piece = c;
    } else if (GREEK[c]) {
      piece = `\\ensuremath{\\${GREEK[c]}}`;
      greek = { char: c, length: piece.length };
    } else if (MATH_SYMBOLS[c] !== undefined) {
      piece = `\\ensuremath{${MATH_SYMBOLS[c]}}`;
    } else if (TEXT_SYMBOLS[c] !== undefined) {
      piece = TEXT_SYMBOLS[c];
    } else if (LETTERS[c]) {
      piece = bib ? `{\\${LETTERS[c]}}` : `\\${LETTERS[c]}{}`;
    } else {
      const letter = accented(c);
      if (letter) {
        piece = bib ? `{${letter}}` : letter;
      } else {
        const code = c.codePointAt(0).toString(16).toUpperCase().padStart(4, '0');
        ctx.error(`${where}: no LaTeX for U+${code} "${c}"`);
        piece = '?';
      }
    }
    // An opening quote after ? or ! would make T1's inverted-mark ligature.
    if (piece.startsWith('`') && /[?!]$/.test(out)) out += '{}';
    out += piece;
    q.prev = c;
  }
  return out;
}

/** A code span: monospace, every special escaped, a break allowed after / . _ : , - */
function codeLatex(value, ctx, where) {
  let out = '';
  for (const c of String(value)) {
    if (CODE_ESCAPES[c]) out += CODE_ESCAPES[c];
    else if (c.charCodeAt(0) < 128) out += c;
    else out += escapeText(c, ctx, where);
    if (CODE_BREAKS.has(c)) out += '\\allowbreak{}';
  }
  return `\\texttt{${out}}`;
}

/** Inline TeX, copied verbatim; only what pdfLaTeX would misread is reported. */
function mathLatex(tex, ctx, where) {
  const source = String(tex).replace(/\n\s*\n/g, '\n');
  if (/[^\x00-\x7f]/.test(source)) ctx.error(`${where}: non-ASCII character in TeX: ${tex}`);
  // A bare % would comment out the rest of the line in the .tex file.
  if (/(^|[^\\])%/.test(source)) ctx.error(`${where}: an unescaped % in TeX: ${tex}`);
  return source;
}

/* ------------------------------------------------------------ inline -- */

/**
 * The inline syntax of `text` as LaTeX: render.js `inline`, emitting LaTeX
 * instead of nodes. Emphasis follows the page's rule for delimiters - an
 * unclosed one is a literal asterisk - and adjacent citations share one
 * \cite, as they share one bracket on the page.
 */
function inlineLatex(text, ctx, where) {
  if (typeof text !== 'string') {
    ctx.error(`${where}: text is not a string`);
    return escapeText(String(text ?? ''), ctx, where);
  }
  const tokens = tokenize(text);
  const root = { delim: null, parts: [] };
  const stack = [root];
  const top = () => stack[stack.length - 1];
  const q = { prev: '' };
  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    switch (token.type) {
      case 'text':
        top().parts.push(escapeText(token.value, ctx, where, q));
        break;
      case 'code':
        top().parts.push(codeLatex(token.value, ctx, where));
        q.prev = 'x';
        break;
      case 'math':
        top().parts.push(`$${mathLatex(token.value, ctx, where)}$`);
        q.prev = 'x';
        break;
      case 'unpaired':
        ctx.error(`${where}: an unpaired $ (write \\$ for a dollar sign)`);
        top().parts.push('\\$');
        q.prev = '$';
        break;
      case 'ref': {
        // "([[eq-se3]])" reads "(3)", not "((3))": an equation's own brackets give way to the prose's.
        const bracketed = tokens[i - 1]?.type === 'text' && tokens[i - 1].value.endsWith('(')
          && tokens[i + 1]?.type === 'text' && tokens[i + 1].value.startsWith(')');
        top().parts.push(crossReference(token.value, ctx, where, { bracketed }));
        q.prev = 'x';
        break;
      }
      case 'cite': {
        const keys = [token.value];
        while (tokens[i + 1]?.type === 'cite') {
          i += 1;
          keys.push(tokens[i].value);
        }
        // A citation is never left alone at the start of a line: the space before it becomes a tie.
        const parts = top().parts;
        if (parts.length && parts[parts.length - 1].endsWith(' ')) parts[parts.length - 1] = `${parts[parts.length - 1].slice(0, -1)}~`;
        parts.push(citation(keys, ctx, where));
        q.prev = ']';
        break;
      }
      case 'delim': {
        const frame = top();
        if (frame.delim === token.value && token.canClose) {
          stack.pop();
          top().parts.push(`${token.value === '**' ? '\\textbf' : '\\emph'}{${frame.parts.join('')}}`);
          q.prev = 'x';
        } else if (token.canOpen) {
          stack.push({ delim: token.value, parts: [] });
          q.prev = '';
        } else {
          frame.parts.push(token.value);
          q.prev = '*';
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
    top().parts.push(frame.delim, ...frame.parts);
  }
  return root.parts.join('');
}

/** `[[id]]` as the page prints it, through LaTeX's own numbering. */
function crossReference(id, ctx, where, { bracketed = false } = {}) {
  const target = ctx.targets.get(id);
  if (!target) {
    ctx.error(`${where}: unknown reference [[${id}]]`);
    return '\\textbf{??}';
  }
  switch (target.kind) {
    case 'eq': return bracketed ? `\\ref{${id}}` : `\\eqref{${id}}`;
    case 'table': return `Table~\\ref{${id}}`;
    case 'figure': return `Figure~\\ref{${id}}`;
    case 'references': return 'References';
    // A badge row opens the live dashboard, which a PDF cannot: a reference to it points at its section.
    case 'links': return crossReference(target.section, ctx, where);
    default: return target.appendix ? `Appendix~\\ref{${id}}` : `\\S\\ref{${id}}`;
  }
}

/** Citations, numbered by BibTeX's unsrt in order of first \cite, as the page numbers them. */
function citation(keys, ctx, where) {
  const known = [];
  for (const key of keys) {
    if (!ctx.references.has(key)) {
      ctx.error(`${where}: unknown citation [[cite:${key}]]`);
      continue;
    }
    if (!ctx.cites.includes(key)) ctx.cites.push(key);
    known.push(key);
  }
  return known.length ? `\\cite{${known.join(',')}}` : '[?]';
}

/* ------------------------------------------------------------ targets -- */

/** Every id a [[…]] may name, with its kind: render.js `layout`'s first pass. */
function collectTargets(article, ctx) {
  const register = (id, target, where) => {
    if (!id) return;
    if (ctx.targets.has(id)) ctx.error(`${where}: duplicate id ${id}`);
    else ctx.targets.set(id, target);
  };
  const visit = (part, appendix) => {
    const where = part?.id ?? 'a section';
    register(part?.id, { kind: 'section', appendix }, where);
    if (part?.generated === 'constants') register('tab-constants', { kind: 'table' }, where);
    for (const block of part?.blocks ?? []) {
      if (block?.kind === 'eq' && block.numbered !== false) register(block.id, { kind: 'eq' }, where);
      else if (block?.kind === 'table') register(block.id, { kind: 'table' }, where);
      else if (block?.kind === 'figure') register(block.id, { kind: 'figure' }, where);
      else if (block?.kind === 'links') register(block.id, { kind: 'links', section: part?.id }, where);
    }
    for (const child of part?.sections ?? []) visit(child, appendix);
  };
  for (const part of article?.sections ?? []) visit(part, false);
  register(REFERENCES_ID, { kind: 'references' }, 'references');
  for (const part of article?.appendices ?? []) visit(part, true);
}

/* ------------------------------------------------------------- tables -- */

/* The page geometry the column widths are planned for: an 11 pt article with
 * 25 mm margins on A4 is 160 mm = 455.24 pt wide, and a table is set \small
 * (10 pt), where a monospace character is 5.25 pt, a digit 5 pt, a capital
 * about 7 pt and a lower-case letter 4.2 pt on average (Latin Modern). */
const TEXT_WIDTH_PT = 455.24;
/* LaTeX's column separation, narrowed for a table of WIDE_TABLE columns or more, whose
 * words would otherwise not fit their columns. */
const TABCOLSEP_PT = 6;
const WIDE_TABLE = 6;
const WIDE_TABCOLSEP_PT = 4;
const CODE_CHAR_PT = 5.25;
const textWidthPt = (word) => [...word].reduce((sum, c) => sum + (/[0-9]/.test(c) ? 5 : /[A-Z]/.test(c) ? 7 : 4.2), 0);
/* No column narrower than this share of an even split, however short its text. */
const MIN_EVEN_SHARE = 0.45;

const SPACE_PT = 3.3;

/**
 * A cell's natural width - set on one line - and its widest unbreakable run,
 * both in points, from its inline tokens: text breaks at spaces, dashes and
 * after a hyphen, a code span after / . _ : , - (where codeLatex allows it).
 */
function measureCell(text) {
  let natural = 0;
  let widest = 0;
  for (const token of tokenize(String(text ?? ''))) {
    let words = [];
    let width = textWidthPt;
    if (token.type === 'text') words = token.value.split(/[\s–—]+|(?<=-)/u);
    else if (token.type === 'code') {
      words = token.value.split(/(?<=[/._:,-])|\s+/);
      width = (word) => [...word].length * CODE_CHAR_PT;
    } else if (token.type === 'math') words = [token.value.replace(/\\[a-zA-Z]+/g, 'x').replace(/[{}^_\s]/g, '')];
    else if (token.type === 'ref') words = ['Table 10'];
    else if (token.type === 'cite') words = ['[10]'];
    for (const word of words) {
      natural += width(word) + SPACE_PT;
      widest = Math.max(widest, width(word));
    }
  }
  return { natural, widest };
}

/**
 * Column widths in thousandths of the width left after the column
 * separation, `columns` giving each column's widest natural cell and widest
 * unbreakable word (points). The width is shared in proportion to the
 * natural widths, with every column held between a floor - its widest word,
 * and MIN_EVEN_SHARE of an even split, so no column is starved - and a
 * ceiling, its natural width, so a column of short entries gives what it
 * cannot use to the columns of long ones. Space left once every column is at
 * its ceiling goes to all in proportion, so the table spans the line; floors
 * that overfill the line give way in proportion. The thousandths sum to
 * exactly 1000.
 */
export function columnShares(columns, { tabcolsep = TABCOLSEP_PT } = {}) {
  const n = columns.length;
  if (!n) return [];
  const available = TEXT_WIDTH_PT - 2 * n * tabcolsep;
  const floor = columns.map((c) => Math.max(MIN_EVEN_SHARE / n, (c.widest + 4) / available));
  const ceiling = columns.map((c, j) => Math.max(floor[j], (c.natural + 4) / available));
  const weight = columns.map((c) => Math.max(c.natural, 1));
  // Water-filling: share what the clamped columns leave in proportion to weight, clamp, repeat.
  const fixed = new Array(n).fill(null);
  let shares = [];
  for (let pass = 0; pass <= n; pass += 1) {
    const free = 1 - fixed.reduce((s, f) => s + (f ?? 0), 0);
    const total = weight.reduce((s, w, j) => s + (fixed[j] === null ? w : 0), 0);
    shares = weight.map((w, j) => fixed[j] ?? (total ? (free * w) / total : 0));
    let clamped = false;
    shares.forEach((share, j) => {
      if (fixed[j] !== null) return;
      if (share < floor[j]) { fixed[j] = floor[j]; clamped = true; }
      else if (share > ceiling[j]) { fixed[j] = ceiling[j]; clamped = true; }
    });
    if (!clamped || fixed.every((f) => f !== null)) {
      shares = shares.map((share, j) => fixed[j] ?? share);
      break;
    }
  }
  const sum = shares.reduce((s, x) => s + x, 0);
  const milli = shares.map((s) => Math.max(1, Math.round((1000 * s) / sum)));
  milli[milli.indexOf(Math.max(...milli))] += 1000 - milli.reduce((s, x) => s + x, 0);
  return milli;
}

/** A cell's LaTeX, kept from being read as an optional argument of the \\ or \item before it. */
const guarded = (latex) => (/^[[*]/.test(latex) ? `{}${latex}` : latex);

/**
 * A table as a `longtable`, which breaks across pages: caption above,
 * booktabs rules, the head repeated on every page under "Table n
 * (continued)". `cells` are LaTeX already; `measures` the plain cells the
 * widths are planned from.
 */
function tableLatex({ id, caption, head, cells, measures, note }) {
  const n = head.length;
  const columns = head.map((_, j) => {
    const all = measures.map((row) => row[j]).filter(Boolean);
    return { natural: Math.max(...all.map((m) => m.natural)), widest: Math.max(...all.map((m) => m.widest)) };
  });
  const tabcolsep = n >= WIDE_TABLE ? WIDE_TABCOLSEP_PT : TABCOLSEP_PT;
  const spec = columnShares(columns, { tabcolsep }).map((share) =>
    `>{\\raggedright\\arraybackslash}p{\\dimexpr(\\linewidth-${2 * n}\\tabcolsep)*${share}/1000\\relax}`).join('');
  const headRow = `${head.map(guarded).join(' & ')} \\\\`;
  const lines = [
    '{\\small',
    ...(tabcolsep === TABCOLSEP_PT ? [] : [`\\setlength{\\tabcolsep}{${tabcolsep}pt}`]),
    `\\begin{longtable}{${spec}}`,
    `\\caption{${caption}}\\label{${id}}\\\\`,
    '\\toprule',
    headRow,
    '\\midrule',
    '\\endfirsthead',
    `\\multicolumn{${n}}{@{}l}{Table~\\thetable{} (continued)}\\\\`,
    '\\toprule',
    headRow,
    '\\midrule',
    '\\endhead',
    '\\bottomrule',
    '\\endfoot',
    '\\bottomrule',
    '\\endlastfoot',
    ...cells.map((row) => `${row.map((cell, j) => (j ? cell : guarded(cell))).join(' & ')} \\\\`),
    '\\end{longtable}',
  ];
  if (note) lines.push(`\\noindent ${note}\\par`);
  lines.push('}');
  return lines.join('\n');
}

/* ------------------------------------------------------------- blocks -- */

const CALLOUT_TITLES = Object.freeze({ rule: 'Rule', note: 'Note', caution: 'Caution' });

function blockLatex(block, ctx, where) {
  const at = `${where} (${block?.kind})`;
  switch (block?.kind) {
    case 'p':
      return inlineLatex(block.text, ctx, at);
    case 'eq': {
      const tex = mathLatex(String(block.tex ?? ''), ctx, at).trim();
      if (block.numbered === false) return `\\[\n${tex}\n\\]`;
      return `\\begin{equation}\\label{${block.id}}\n${tex}\n\\end{equation}`;
    }
    case 'list': {
      const env = block.ordered ? 'enumerate' : 'itemize';
      const items = (block.items ?? []).map((item, i) => `\\item ${guarded(inlineLatex(item, ctx, `${at} item ${i}`))}`);
      return [`\\begin{${env}}`, ...items, `\\end{${env}}`].join('\n');
    }
    case 'table': {
      const head = block.head ?? [];
      const rows = (block.rows ?? []).filter((row, r) => {
        if (Array.isArray(row)) return true;
        ctx.error(`${at}: row ${r} is not a list`);
        return false;
      });
      rows.forEach((row, r) => {
        if (row.length !== head.length) ctx.error(`${at}: row ${r} has ${row.length} cells, the head ${head.length}`);
      });
      const fit = (row) => head.map((_, j) => row[j] ?? '');
      return tableLatex({
        id: block.id,
        caption: inlineLatex(block.caption ?? '', ctx, `${at} caption`),
        head: head.map((cell, j) => inlineLatex(String(cell), ctx, `${at} head ${j}`)),
        cells: rows.map((row, r) => fit(row).map((cell, j) => inlineLatex(String(cell), ctx, `${at} row ${r} cell ${j}`))),
        measures: [head, ...rows.map(fit)].map((row) => row.map((cell) => measureCell(cell))),
        note: block.note ? inlineLatex(block.note, ctx, `${at} note`) : null,
      });
    }
    case 'figure': {
      if (!block.id) ctx.error(`${at}: a figure without an id`);
      ctx.figures.push({ id: block.id, exhibit: block.exhibit });
      return [
        '\\begin{figure}[htbp]',
        '\\centering',
        `\\includegraphics[width=\\linewidth]{${ctx.figurePath(block.id)}}`,
        `\\caption{${inlineLatex(block.caption ?? '', ctx, `${at} caption`)}}\\label{${block.id}}`,
        '\\end{figure}',
      ].join('\n');
    }
    case 'callout': {
      if (!CALLOUT_TITLES[block.tone]) ctx.error(`${at}: unknown callout tone ${block.tone}`);
      const opening = `\\textbf{${CALLOUT_TITLES[block.tone] ?? 'Note'}}`
        + (block.title ? ` \\textperiodcentered{} ${inlineLatex(block.title, ctx, `${at} title`)}` : '');
      const paragraphs = String(block.text ?? '').split(/\n\s*\n/)
        .map((text, i) => inlineLatex(text, ctx, `${at} paragraph ${i}`));
      return ['\\begin{quote}', opening, '', paragraphs.join('\n\n'), '\\end{quote}'].join('\n');
    }
    case 'links':
      // The badges open the live dashboard; a PDF has nothing to open them in.
      return null;
    default:
      ctx.error(`${at}: unknown block kind ${block?.kind}`);
      return null;
  }
}

const SECTIONING = ['section', 'subsection', 'subsubsection'];

function sectionLatex(part, level, ctx, out) {
  const where = part?.id ?? 'a section';
  if (!part?.title) ctx.error(`${where}: a section without a title`);
  let command = SECTIONING[level - 1];
  if (!command) {
    ctx.error(`${where}: nested ${level} deep; LaTeX numbers three levels`);
    command = 'paragraph';
  }
  out.push(`\\${command}{${inlineLatex(part?.title ?? '', ctx, `${where} title`)}}\\label{${part?.id}}`, '');
  const blocks = part?.generated === 'constants'
    ? constantsAppendix(ctx)
    : (part?.blocks ?? []).map((block, i) => blockLatex(block, ctx, `${where} block ${i}`));
  for (const block of blocks) if (block) out.push(block, '');
  for (const child of part?.sections ?? []) sectionLatex(child, level + 1, ctx, out);
}

/** Appendix B, as render.js `constantsAppendix` writes it: its sentence, then the four-column table. */
function constantsAppendix(ctx) {
  const where = 'app-constants';
  const code = (text) => codeLatex(String(text ?? ''), ctx, where);
  const text = (value) => escapeText(String(value ?? ''), ctx, where);
  const entries = Object.entries(ctx.constants);
  const sentence = `The prose never types one of these numbers: it reads each from ${code('methodology/constants.js')}, and `
    + `${code('tests/test_methodology_constants.py')} resolves every source below against the running code, so the article `
    + 'cannot drift from what the service does. A source is a Python expression in a module (py), a JavaScript expression '
    + 'under static/js (js), or a snippet the value must appear in (text).';
  const plain = (value, isCode) => (isCode ? measureCell(`\`${value}\``) : measureCell(String(value).replace(/[`$*[]/g, ' ')));
  const head = ['Name', 'Value', 'Meaning', 'Source'];
  return [sentence, tableLatex({
    id: 'tab-constants',
    caption: 'Every constant of the code the article quotes, with the module and expression it is read from.',
    head,
    cells: entries.map(([name, { value, source, meaning }]) => [
      code(name),
      typeof value === 'string' ? code(value) : text(formatValue(value)),
      text(meaning),
      code(source),
    ]),
    measures: [head.map((h) => measureCell(h)), ...entries.map(([name, { value, source, meaning }]) => [
      plain(name, true),
      plain(typeof value === 'string' ? value : formatValue(value), typeof value === 'string'),
      plain(meaning ?? '', false),
      plain(source ?? '', true),
    ])],
    note: null,
  })];
}

/* ----------------------------------------------------------- the front -- */

function frontLatex(front, provenance, ctx) {
  const plain = (value, where) => escapeText(String(value ?? ''), ctx, where);
  const authors = (front.authors ?? []).map((author, i) =>
    `${plain(author.name, `author ${i}`)}\\textsuperscript{${(author.affiliations ?? []).join(',')}}`).join(' \\and ');
  const affiliations = (front.affiliations ?? []).map((a, i) =>
    `\\textsuperscript{${plain(a.id, `affiliation ${i}`)}}${plain(a.text, `affiliation ${i}`)}\\\\`);
  const stamp = (key) => plain(provenance?.[key] || 'unknown', `provenance ${key}`);
  return [
    `\\title{${inlineLatex(front.title ?? '', ctx, 'title')}}`,
    `\\author{${authors}}`,
    '\\date{\\small',
    ...affiliations.map((line, i) => (i === affiliations.length - 1 ? `${line}[1ex]` : line)),
    `calosrv ${stamp('version')} \\textperiodcentered{} static build ${stamp('stamp')} \\textperiodcentered{} exported ${stamp('date')}}`,
  ];
}

/* ---------------------------------------------------------------- BibTeX -- */

const BIB_TYPES = new Set(['article', 'book', 'inproceedings', 'techreport', 'misc']);
/* The fields a `bib` object may carry, in the order they are written; `reporttype` is BibTeX's `type`. */
const BIB_FIELDS = ['author', 'title', 'journal', 'booktitle', 'series', 'edition', 'volume', 'number', 'pages',
  'reporttype', 'institution', 'publisher', 'address', 'howpublished', 'year', 'note', 'doi', 'url'];

/** A URL or DOI is copied as it is; only what would break the .bib or the \url around it is refused. */
function verbatimField(value, ctx, where) {
  const text = String(value);
  if (/[^\x21-\x7e]|[{}\\]/.test(text)) ctx.error(`${where}: a URL or DOI must be printable ASCII without braces or backslashes: ${text}`);
  return text.replace(/[^\x21-\x7e]|[{}\\]/g, '?');
}

/** One reference as a BibTeX entry; an entry without `bib` as @misc with its text as the note. */
function bibEntry(ref, ctx) {
  const where = `references ${ref.key}`;
  const field = (value) => {
    const latex = escapeText(String(value), ctx, where, { prev: '' }, { bib: true });
    // BibTeX counts every brace, escaped or not, so a brace in the data would unbalance the field.
    if (/[{}]/.test(String(value))) ctx.error(`${where}: a brace in a bib field: ${value}`);
    return latex;
  };
  const bib = ref.bib;
  if (!bib) return `@misc{${ref.key},\n  note = {${field(ref.text)}}\n}`;
  let type = bib.type;
  if (!BIB_TYPES.has(type)) {
    ctx.error(`${where}: unknown bib type ${type}`);
    type = 'misc';
  }
  for (const name of Object.keys(bib)) {
    if (name !== 'type' && !BIB_FIELDS.includes(name)) ctx.error(`${where}: unknown bib field ${name}`);
  }
  const fields = [];
  const put = (name, value) => fields.push(`  ${name} = {${value}}`);
  for (const name of BIB_FIELDS) {
    const value = bib[name];
    if (value === undefined || value === null || value === '') continue;
    if (name === 'author') {
      const names = (Array.isArray(value) ? value : [value]).map((author) => {
        // A body's name in braces is one "last name", which BibTeX neither splits nor abbreviates.
        if (author && typeof author === 'object' && author.org) return `{${field(author.org)}}`;
        if (typeof author === 'string') return field(author);
        ctx.error(`${where}: an author is a "Family, Given" string or { org }`);
        return '';
      });
      put('author', names.filter(Boolean).join(' and '));
    } else if (name === 'title') {
      // Double braces keep the title's own capitals ("Grad-CAM", "XGBoost") through unsrt's case change.
      put('title', `{${field(value)}}`);
    } else if (name === 'reporttype') {
      put('type', field(value));
    } else if (name === 'note') {
      put('note', [field(value), bib.doi ? `doi:\\nolinkurl{${verbatimField(bib.doi, ctx, where)}}` : null].filter(Boolean).join(', '));
    } else if (name === 'doi') {
      // unsrt prints the note, not the doi, so the DOI also rides in the note.
      const doi = verbatimField(value, ctx, where);
      if (!bib.note) put('note', `doi:\\nolinkurl{${doi}}`);
      put('doi', doi);
    } else if (name === 'url') {
      const url = verbatimField(value, ctx, where);
      if (!bib.howpublished) put('howpublished', `\\url{${url}}`);
      put('url', url);
    } else {
      put(name, field(value));
    }
  }
  return `@${type}{${ref.key},\n${fields.join(',\n')}\n}`;
}

/* -------------------------------------------------------- the document -- */

const PREAMBLE = [
  '\\documentclass[11pt]{article}',
  '\\usepackage[T1]{fontenc}',
  '\\usepackage{lmodern}',
  '\\usepackage{textcomp}',
  '\\usepackage[a4paper,margin=25mm]{geometry}',
  '\\usepackage{amsmath}',
  '\\usepackage{amssymb}',
  '\\usepackage{array}',
  '\\usepackage{booktabs}',
  '\\usepackage{longtable}',
  '\\usepackage{graphicx}',
  '\\usepackage{microtype}',
  '\\usepackage[hidelinks]{hyperref}',
  '',
  '% A table caption spans the text width, as a figure caption does.',
  '\\setlength{\\LTcapwidth}{\\linewidth}',
  '% Narrow table columns and long identifiers: stretch a line before letting it overflow.',
  '\\setlength{\\emergencystretch}{3em}',
];

/**
 * The article as `{tex, bib, figures, errors}` (export-brief.md §2):
 * `tex` the whole of methodology.tex, `bib` references.bib with the cited
 * entries in order of first citation, `figures` the figure blocks in
 * document order (`{id, exhibit}`), each included from `figurePath(id)`, and
 * `errors` one message per problem found.
 */
export function latexDocument(article, { constants = CONSTANTS, provenance = {}, figurePath = (id) => `figures/${id}.png` } = {}) {
  const ctx = {
    errors: [],
    targets: new Map(),
    references: new Map((article?.references ?? []).filter((r) => r?.key).map((r) => [r.key, r])),
    cites: [],
    figures: [],
    figurePath,
    constants,
  };
  ctx.error = (message) => ctx.errors.push(message);
  collectTargets(article, ctx);

  const front = article?.front ?? {};
  const head = frontLatex(front, provenance, ctx);
  const body = ['\\begin{document}', '', '\\maketitle', ''];
  const abstract = (front.abstract ?? []).map((text, i) => inlineLatex(text, ctx, `abstract ${i}`));
  if (abstract.length) body.push('\\begin{abstract}', abstract.join('\n\n'), '\\end{abstract}', '');
  const keywords = (front.keywords ?? []).filter(Boolean).map((k, i) => inlineLatex(k, ctx, `keyword ${i}`));
  if (keywords.length) body.push(`\\noindent\\textbf{Keywords:} ${keywords.join(' \\textperiodcentered{} ')}`, '');
  for (const part of article?.sections ?? []) sectionLatex(part, 1, ctx, body);
  body.push('\\bibliographystyle{unsrt}', '\\bibliography{references}', '');
  if ((article?.appendices ?? []).length) {
    body.push('\\appendix', '');
    for (const part of article.appendices) sectionLatex(part, 1, ctx, body);
  }
  body.push('\\end{document}', '');

  const comment = (text) => `% ${escapeText(text, ctx, 'header')}`;
  const title = String(front.title ?? 'Methodology').replace(/[*`$]/g, '');
  const stamp = (key) => provenance?.[key] || 'unknown';
  const header = [
    comment(title),
    '%',
    comment(`Exported from the Methodology page of calosrv ${stamp('version')} (static build ${stamp('stamp')}) on ${stamp('date')}.`),
    '% Build: pdflatex methodology && bibtex methodology && pdflatex methodology && pdflatex methodology',
    '% or: latexmk -pdf methodology',
    '% The figures are PNG at 300 dpi, drawn for a 160 mm text width; their SVG sources sit beside them.',
    '',
  ];
  const tex = [...header, ...PREAMBLE, '', ...head, '', ...body].join('\n');
  const bib = ctx.cites.map((key) => bibEntry(ctx.references.get(key), ctx)).join('\n\n') + (ctx.cites.length ? '\n' : '');

  // The contract is ASCII only; the map above should have made it so, and this says where it did not.
  for (const [name, text] of [['methodology.tex', tex], ['references.bib', bib]]) {
    const match = text.match(/[^\x00-\x7f]/u);
    if (match) ctx.error(`${name}: non-ASCII character U+${match[0].codePointAt(0).toString(16).toUpperCase()} in the output`);
  }
  return { tex, bib, figures: ctx.figures, errors: ctx.errors };
}

/** Running text as LaTeX through the article's Unicode map: `{latex, errors}`; `bib` braces the accents. */
export function textToLatex(text, { bib = false } = {}) {
  const ctx = { errors: [] };
  ctx.error = (message) => ctx.errors.push(message);
  const latex = escapeText(text, ctx, 'text', { prev: '' }, { bib });
  return { latex, errors: ctx.errors };
}
