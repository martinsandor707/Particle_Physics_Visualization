/* LaTeX to MathML Core, for the Methodology page's equations.
 *
 * The page draws every equation as native MathML Core: no third-party code,
 * no web fonts, no CDN and no markup parsed from a string. This module is the
 * compiler: a recursive-descent parser that reads the source directly (the
 * scanner and the parser are one pass, because \text needs the raw characters
 * a token stream would already have thrown away) and builds a pure node tree,
 * which `mountMath` turns into elements.
 *
 * The contract:
 *
 * - `texToTree(tex, {display})` returns a pure node tree, `{tag, attrs?,
 *   children?, text?}`: a node carries either `children` or `text` (the
 *   token elements mi, mn, mo, mtext and the annotation). The root is
 *   `<math display="block|inline">` holding `<semantics>`, whose last child is
 *   `<annotation encoding="application/x-tex">` with the source verbatim.
 * - `mountMath(tree, doc)` builds it with `createElementNS` in the MathML
 *   namespace: elements and text nodes only, never markup parsed from a string.
 * - A command outside `SUPPORTED_COMMANDS`, or an environment outside
 *   `SUPPORTED_ENVIRONMENTS`, throws `MathSyntaxError`, so a typo fails a test
 *   instead of rendering garbage. So do unbalanced braces, `&` or `\\` outside
 *   an environment, and an unescaped `%`, `#` or `$`.
 * - Every rendered minus is U+2212: `-` in the source becomes `<mo>−</mo>`.
 *   The annotation keeps the source as written.
 *
 * Only MathML Core elements and attributes are emitted. MathML Core has no
 * `columnalign`, so the left- and right-aligned columns of `cases` and
 * `aligned` are set with CSS `text-align` on the cell. CSS is used in three
 * more places, each because Chromium draws the Core markup wrongly: the
 * negative space `\!` (a negative mspace width is clamped to zero), the rules
 * of `\overline` / `\underline` (no operator stretches along the inline axis)
 * and the slant and weight of `\textit` / `\textbf`. `\widehat` and
 * `\widetilde` stay stretchy accents and so draw a centred, unstretched mark in
 * Chromium.
 */

export const MATHML_NS = 'http://www.w3.org/1998/Math/MathML';

/** The LaTeX commands the compiler accepts, without the backslash. */
export const SUPPORTED_COMMANDS = Object.freeze([
  // Greek, lower and upper case.
  'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon', 'zeta', 'eta', 'theta', 'vartheta', 'iota',
  'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'varpi', 'rho', 'varrho', 'sigma', 'varsigma', 'tau', 'upsilon',
  'phi', 'varphi', 'chi', 'psi', 'omega',
  'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon', 'Phi', 'Psi', 'Omega',
  // Fractions, roots, binomials, stacking.
  'frac', 'dfrac', 'tfrac', 'sqrt', 'binom', 'overset', 'underset', 'stackrel',
  // Large operators and named functions.
  'sum', 'prod', 'int', 'lim', 'max', 'min', 'sup', 'inf', 'det', 'Pr',
  'log', 'ln', 'exp', 'sin', 'cos', 'tan', 'arctan', 'sinh', 'cosh', 'tanh',
  'operatorname', 'limits', 'nolimits', 'bmod', 'pmod', 'mod',
  // Relations and arrows.
  'le', 'leq', 'ge', 'geq', 'ne', 'neq', 'approx', 'sim', 'simeq', 'equiv', 'propto', 'coloneqq',
  'in', 'notin', 'subset', 'subseteq', 'll', 'gg', 'to', 'rightarrow', 'leftarrow', 'mapsto',
  'Rightarrow', 'Leftrightarrow', 'iff', 'implies',
  // Binary operators.
  'pm', 'mp', 'times', 'cdot', 'div', 'ast', 'star', 'circ', 'otimes', 'oplus', 'setminus', 'cup', 'cap',
  'wedge', 'vee',
  // Symbols.
  'infty', 'partial', 'nabla', 'ell', 'hbar', 'prime', 'emptyset', 'varnothing', 'forall', 'exists', 'neg',
  'angle', 'top', 'ldots', 'cdots', 'dots', 'vdots', 'ddots', 'quad', 'qquad',
  // Delimiters and sizes.
  'left', 'right', 'big', 'Big', 'bigg', 'Bigg', 'langle', 'rangle', 'lceil', 'rceil', 'lfloor', 'rfloor',
  'lvert', 'rvert', 'lVert', 'rVert', 'vert', 'Vert', 'mid', 'lbrace', 'rbrace',
  // Accents.
  'hat', 'bar', 'tilde', 'vec', 'dot', 'ddot', 'overline', 'underline', 'widehat', 'widetilde',
  // Fonts and text.
  'mathrm', 'mathbf', 'mathbb', 'mathcal', 'mathit', 'mathsf', 'mathtt', 'boldsymbol',
  'text', 'textrm', 'textit', 'textbf', 'displaystyle', 'textstyle',
  // Environments.
  'begin', 'end',
]);

/** Commands spelt with a single non-letter: spacing, escaped characters and the row break. */
export const SUPPORTED_SYMBOL_COMMANDS = Object.freeze([',', ';', ':', '!', ' ', '{', '}', '|', '%', '#', '&', '_', '\\']);

/** The environments `\begin{…}` accepts. */
export const SUPPORTED_ENVIRONMENTS = Object.freeze(['pmatrix', 'bmatrix', 'vmatrix', 'matrix', 'cases', 'aligned']);

/** A source the compiler cannot read: an unknown command, an unbalanced group. */
export class MathSyntaxError extends Error {
  constructor(message, { tex = '', position = null } = {}) {
    super(message);
    this.name = 'MathSyntaxError';
    this.tex = tex;
    this.position = position;
  }
}

// ------------------------------------------------------------ the tables --

const MINUS = '\u2212';
const APPLY = '\u2061';

const GREEK = {
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ϵ', varepsilon: 'ε', zeta: 'ζ', eta: 'η',
  theta: 'θ', vartheta: 'ϑ', iota: 'ι', kappa: 'κ', lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ', pi: 'π',
  varpi: 'ϖ', rho: 'ρ', varrho: 'ϱ', sigma: 'σ', varsigma: 'ς', tau: 'τ', upsilon: 'υ',
  // The article's azimuth is \varphi (φ, U+03C6), as the dashboard's labels draw it; \phi is the loopy ϕ.
  phi: 'ϕ', varphi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω',
  Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ', Pi: 'Π', Sigma: 'Σ', Upsilon: 'Υ', Phi: 'Φ',
  Psi: 'Ψ', Omega: 'Ω',
};

/** Commands drawn as one operator character, with the dictionary's spacing. */
const OPERATORS = {
  le: '≤', leq: '≤', ge: '≥', geq: '≥', ne: '≠', neq: '≠', approx: '≈', sim: '∼', simeq: '≃', equiv: '≡',
  propto: '∝', coloneqq: '≔', in: '∈', notin: '∉', subset: '⊂', subseteq: '⊆', ll: '≪', gg: '≫',
  to: '→', rightarrow: '→', leftarrow: '←', mapsto: '↦', Rightarrow: '⇒', Leftrightarrow: '⇔',
  iff: '⟺', implies: '⟹',
  pm: '±', mp: '∓', times: '×', cdot: '⋅', div: '÷', ast: '∗', star: '⋆', circ: '∘', otimes: '⊗',
  oplus: '⊕', setminus: '∖', cup: '∪', cap: '∩', wedge: '∧', vee: '∨',
  forall: '∀', exists: '∃', neg: '¬', ldots: '…', cdots: '⋯', dots: '…', vdots: '⋮', ddots: '⋱',
  mid: '∣', prime: '′',
};

/** Commands drawn as one ordinary symbol. */
const ORDINARY = {
  infty: '∞', partial: '∂', nabla: '∇', ell: 'ℓ', hbar: 'ℏ', emptyset: '∅', varnothing: '∅', angle: '∠',
  top: '⊤',
};

/** Large operators: their limits go under and over in display style, except the integral's. */
const LARGE = { sum: '∑', prod: '∏', int: '∫' };
const LARGE_CHARS = new Set(Object.values(LARGE));

/** Named functions; the first group takes its limits underneath in display style. */
const LIMIT_FUNCTIONS = new Set(['lim', 'max', 'min', 'sup', 'inf', 'det', 'Pr']);
const FUNCTIONS = new Set([...LIMIT_FUNCTIONS, 'log', 'ln', 'exp', 'sin', 'cos', 'tan', 'arctan', 'sinh', 'cosh',
  'tanh']);

/** Delimiters by command, for \left, \right, \big… and plain use. */
const DELIMITER_COMMANDS = {
  langle: '⟨', rangle: '⟩', lceil: '⌈', rceil: '⌉', lfloor: '⌊', rfloor: '⌋', lvert: '|', rvert: '|',
  vert: '|', lVert: '‖', rVert: '‖', Vert: '‖', lbrace: '{', rbrace: '}',
  '{': '{', '}': '}', '|': '‖',
};
const DELIMITER_CHARS = new Set(['(', ')', '[', ']', '|', '/', '⟨', '⟩', '⌈', '⌉', '⌊', '⌋', '‖', '{', '}']);
const OPENING = new Set(['(', '[', '{', '⟨', '⌈', '⌊']);
const CLOSING = new Set([')', ']', '}', '⟩', '⌉', '⌋']);
const SIGNS = new Set([MINUS, '+', '±', '∓']);

/** Characters TeX treats as ordinary symbols, which the operator dictionary would otherwise space. */
const TIGHT = new Set(['|', '‖', '/', '.']);

/** Explicit spaces, in em (TeX's mu is 1/18 em). */
const SPACES = { ',': 3 / 18, ':': 4 / 18, ';': 5 / 18, '!': -3 / 18, ' ': 6 / 18, quad: 1, qquad: 2 };

/** \big and friends: the delimiter's fixed height. */
const BIG_SIZES = { big: '1.2em', Big: '1.8em', bigg: '2.4em', Bigg: '3em' };

/** Accents: the mark, and whether it stretches over its base. */
const ACCENTS = {
  hat: ['^', false], widehat: ['^', true], tilde: ['~', false], widetilde: ['~', true], bar: ['\u00AF', false],
  vec: ['\u2192', false], dot: ['\u02D9', false], ddot: ['\u00A8', false],
};

const FONTS = {
  mathrm: 'normal', mathbf: 'bold', mathbb: 'double-struck', mathcal: 'script', mathit: 'italic',
  mathsf: 'sans-serif', mathtt: 'monospace', boldsymbol: 'bold-italic',
};

const TEXT_STYLES = { text: null, textrm: null, textit: 'font-style: italic', textbf: 'font-weight: bold' };

/** Environments: their fences, their cells' style and their column alignment. */
const ENVIRONMENTS = {
  matrix: { open: null, close: null, display: false, align: null },
  pmatrix: { open: '(', close: ')', display: false, align: null },
  bmatrix: { open: '[', close: ']', display: false, align: null },
  vmatrix: { open: '|', close: '|', display: false, align: null },
  cases: { open: '{', close: null, display: false, align: 'cases' },
  aligned: { open: null, close: null, display: true, align: 'aligned' },
};

// ----------------------------------------- Mathematical Alphanumerics --

/* First code points of each alphabet: [A, a, 0]; null where Unicode has none.
 * The holes Unicode fills from the Letterlike Symbols block are listed apart. */
const ALPHABETS = {
  bold: [0x1D400, 0x1D41A, 0x1D7CE],
  italic: [0x1D434, 0x1D44E, null],
  'bold-italic': [0x1D468, 0x1D482, 0x1D7CE],
  script: [0x1D49C, 0x1D4B6, null],
  'double-struck': [0x1D538, 0x1D552, 0x1D7D8],
  'sans-serif': [0x1D5A0, 0x1D5BA, 0x1D7E2],
  monospace: [0x1D670, 0x1D68A, 0x1D7F6],
};
const HOLES = {
  italic: { h: 'ℎ' },
  script: { B: 'ℬ', E: 'ℰ', F: 'ℱ', H: 'ℋ', I: 'ℐ', L: 'ℒ', M: 'ℳ', R: 'ℛ', e: 'ℯ', g: 'ℊ', o: 'ℴ' },
  'double-struck': { C: 'ℂ', H: 'ℍ', N: 'ℕ', P: 'ℙ', Q: 'ℚ', R: 'ℝ', Z: 'ℤ' },
};
/* Greek: [capital Α, small α, then ∂ ϵ ϑ ϰ ϕ ϱ ϖ and ∇]. LaTeX's \mathbf leaves
 * small Greek alone and sets capitals upright bold; \boldsymbol sets small
 * Greek bold italic; \mathit sets capitals italic. */
const GREEK_ALPHABETS = {
  bold: { capital: 0x1D6A8 },
  italic: { capital: 0x1D6E2 },
  'bold-italic': { capital: 0x1D6A8, small: 0x1D736, extra: 0x1D74F, nabla: 0x1D6C1 },
};
const GREEK_EXTRA = ['∂', 'ϵ', 'ϑ', 'ϰ', 'ϕ', 'ϱ', 'ϖ'];

/** One character in a font's alphabet; characters it has none for are kept. */
function styleChar(ch, font) {
  if (!font || font === 'normal') return ch;
  if (HOLES[font]?.[ch]) return HOLES[font][ch];
  const code = ch.codePointAt(0);
  const [capital, small, digit] = ALPHABETS[font];
  if (code >= 65 && code <= 90) return String.fromCodePoint(capital + code - 65);
  if (code >= 97 && code <= 122) return String.fromCodePoint(small + code - 97);
  if (code >= 48 && code <= 57) return digit === null ? ch : String.fromCodePoint(digit + code - 48);
  const greek = GREEK_ALPHABETS[font];
  if (!greek) return ch;
  if (code >= 0x391 && code <= 0x3A9) return String.fromCodePoint(greek.capital + code - 0x391);
  if (greek.small && code >= 0x3B1 && code <= 0x3C9) return String.fromCodePoint(greek.small + code - 0x3B1);
  if (greek.extra && GREEK_EXTRA.includes(ch)) return String.fromCodePoint(greek.extra + GREEK_EXTRA.indexOf(ch));
  if (greek.nabla && ch === '∇') return String.fromCodePoint(greek.nabla);
  return ch;
}

const styleText = (text, font) => Array.from(text, (ch) => styleChar(ch, font)).join('');

// ------------------------------------------------------------ the nodes --

/* Parser-only marks, kept off the tree's enumerable keys so they never reach
 * JSON or the DOM: what a base does with its scripts, and a function head. */
const LIMITS = Symbol('limits');
const FUNCTION = Symbol('function');

const node = (tag, attrs, children) => (attrs && Object.keys(attrs).length
  ? { tag, attrs, children } : { tag, children });
const token = (tag, text, attrs) => (attrs && Object.keys(attrs).length ? { tag, attrs, text } : { tag, text });
const mo = (text, attrs) => token('mo', text, attrs);
const mrow = (children) => node('mrow', null, children);
const space = (em) => ({ tag: 'mspace', attrs: { width: `${+em.toFixed(4)}em` } });

/** A list of siblings as one node: a lone node stands for itself. */
const group = (children) => (children.length === 1 ? children[0] : mrow(children));

/** A delimiter as an operator. Plain ones never stretch, as in TeX. */
function delimiter(ch, attrs = {}) {
  const out = { ...attrs };
  if (!('stretchy' in out) && DELIMITER_CHARS.has(ch)) out.stretchy = 'false';
  if (TIGHT.has(ch)) Object.assign(out, { lspace: '0', rspace: '0' });
  return mo(ch, out);
}

/** A stretchy fence of \left, \right or an environment. */
function fence(ch, form) {
  return mo(ch, { fence: 'true', form, stretchy: 'true', symmetric: 'true', lspace: '0', rspace: '0' });
}

/** The operator a node is built on (an embellished operator's core), or null. */
function coreOperator(n) {
  if (!n) return null;
  if (n.tag === 'mo') return n;
  if (['msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover'].includes(n.tag)) return coreOperator(n.children[0]);
  return null;
}

/** The first operator a node opens with, looking into rows. */
function leadingOperator(n) {
  if (!n) return null;
  if (n.tag === 'mrow' || n.tag === 'mstyle') return leadingOperator(n.children[0]);
  return coreOperator(n);
}

// ----------------------------------------------------------- the parser --

const LETTER = /^\p{L}$/u;
const ASCII_LETTER = /^[A-Za-z]$/;
const DIGIT = /^[0-9]$/;
const NUMBER = /^[0-9]+(?:\.[0-9]+)?/;
const ROW_SKIP = /^\[\s*-?[0-9.]+\s*(?:pt|em|ex|mm|cm|mu)\s*\]/;
const COMMANDS = new Set(SUPPORTED_COMMANDS);

class Parser {
  constructor(tex, display) {
    this.src = tex;
    this.i = 0;
    this.display = display; // TeX's display style, which decides where limits go
    this.font = null; // the active \math… alphabet
    this.fontDigits = false; // \operatorname: digits join the name (atan2)
  }

  fail(message, position = this.i) {
    throw new MathSyntaxError(`${message} at position ${position} of "${this.src}"`, { tex: this.src, position });
  }

  atEnd() { return this.i >= this.src.length; }

  /** The character (code point) at the cursor. */
  peek() {
    if (this.atEnd()) return '';
    return String.fromCodePoint(this.src.codePointAt(this.i));
  }

  next() {
    const ch = this.peek();
    this.i += ch.length;
    return ch;
  }

  skipSpace() {
    while (!this.atEnd() && /\s/.test(this.src[this.i])) this.i += 1;
  }

  /** The command name at the cursor (after its backslash), without consuming it. */
  peekCommand() {
    if (this.src[this.i] !== '\\') return null;
    const rest = this.src.slice(this.i + 1);
    const word = /^[A-Za-z]+/.exec(rest);
    if (word) return word[0];
    return rest ? String.fromCodePoint(rest.codePointAt(0)) : '';
  }

  readCommand() {
    const name = this.peekCommand();
    if (name === '') this.fail('A lone backslash ends the source');
    this.i += 1 + name.length;
    return name;
  }

  // ------------------------------------------------------ expressions --

  /** Siblings until a closing token, which is left for the caller to judge. */
  parseExpression(ctx = {}) {
    const list = [];
    for (;;) {
      this.skipSpace();
      if (this.atEnd()) break;
      const ch = this.src[this.i];
      if (ch === '}' || ch === '&') break;
      if (ctx.bracket && ch === ']') break;
      const name = this.peekCommand();
      if (name === '\\' || name === 'right' || name === 'end') break;
      if (name === 'displaystyle' || name === 'textstyle') {
        // A style switch lasts to the end of its group: the rest of it goes into one mstyle.
        this.readCommand();
        const saved = this.display;
        this.display = name === 'displaystyle';
        const rest = this.parseExpression(ctx);
        this.display = saved;
        list.push(node('mstyle', { displaystyle: String(name === 'displaystyle'), scriptlevel: '0' }, rest));
        break;
      }
      list.push(...this.parseScripted());
    }
    return spaceFunctions(list);
  }

  /** The stop token after an expression must be `want`; anything else is a structural error. */
  expectStop(want, openedAt) {
    this.skipSpace();
    const at = this.i;
    const ch = this.src[this.i];
    const name = this.peekCommand();
    let found = 'end';
    if (this.atEnd()) found = 'end';
    else if (ch === '}') found = '}';
    else if (ch === '&') found = '&';
    else if (ch === ']') found = ']';
    else if (name === '\\') found = '\\\\';
    else if (name === 'right') found = 'right';
    else if (name === 'end') found = 'endenv';
    if (found === want) return;
    if (found === '}') this.fail('Unbalanced "}" with no group open', at);
    if (found === '&') this.fail('"&" outside an environment cell', at);
    if (found === '\\\\') this.fail('"\\\\" outside an environment', at);
    if (found === 'right') this.fail('"\\right" without a matching "\\left"', at);
    if (found === 'endenv') this.fail('"\\end" without a matching "\\begin"', at);
    if (want === '}') this.fail('Unbalanced "{": the group is never closed', openedAt);
    if (want === 'right') this.fail('"\\left" without a matching "\\right"', openedAt);
    if (want === ']') this.fail('Unclosed "[" of an optional argument', openedAt);
    this.fail('Unexpected end of the source', at);
  }

  /** A brace group, in its own font and style scope. */
  parseGroup() {
    const openedAt = this.i;
    this.i += 1;
    const saved = [this.display, this.font, this.fontDigits];
    const list = this.parseExpression();
    this.expectStop('}', openedAt);
    this.i += 1;
    [this.display, this.font, this.fontDigits] = saved;
    return group(list);
  }

  /** One argument: a group, a command, or a single character (one digit, as in TeX's \frac12). */
  parseArg(what = 'argument') {
    this.skipSpace();
    const ch = this.src[this.i];
    if (this.atEnd() || ch === '}' || ch === '&' || ch === '^' || ch === '_') this.fail(`Missing ${what}`);
    if (ch === '{') return this.parseGroup();
    if (ch === '\\') {
      const name = this.peekCommand();
      if (name === '\\' || name === 'right' || name === 'end') this.fail(`Missing ${what}`);
      return this.parseCommand();
    }
    if (DIGIT.test(ch)) {
      this.i += 1;
      return token('mn', styleText(ch, this.font));
    }
    return this.parseAtom();
  }

  /** An argument read in text style, as fractions, scripts and stacked marks are. */
  parseInnerArg(what) {
    const saved = this.display;
    this.display = false;
    const out = this.parseArg(what);
    this.display = saved;
    return out;
  }

  /** An atom with its scripts and primes, as a list (a function adds its application operator). */
  parseScripted() {
    this.skipSpace();
    const ch = this.src[this.i];
    const base = ch === '^' || ch === '_' || ch === "'" ? mrow([]) : this.parseAtom();
    let limits = base[LIMITS] ?? null;
    let sub = null;
    let sup = null;
    let primes = 0;
    for (;;) {
      this.skipSpace();
      const c = this.src[this.i];
      const name = this.peekCommand();
      if (name === 'limits' || name === 'nolimits') {
        if (!limits) this.fail(`"\\${name}" must follow a large operator`);
        this.readCommand();
        limits = name === 'limits' ? 'always' : 'never';
      } else if (c === "'") {
        if (sup || sub) this.fail('A prime after a script (write the prime first: x\'_i)');
        this.i += 1;
        primes += 1;
      } else if (c === '^') {
        if (sup) this.fail('Double superscript');
        this.i += 1;
        sup = this.parseInnerArg('superscript');
      } else if (c === '_') {
        if (sub) this.fail('Double subscript');
        this.i += 1;
        sub = this.parseInnerArg('subscript');
      } else {
        break;
      }
    }
    let out = base;
    if (primes) {
      /* The prime glyph is already drawn at superscript height. Chromium sets
       * a scripted ′ at script size and raises it again (measured: a tiny mark
       * above the base's ascender, math-probe/probe2.png), so the prime
       * follows its base at full size, as TeX's \prime superscript looks, and
       * any further script attaches to base and prime together: x′², x′ᵢ. */
      out = mrow([base, mo(['′', '″', '‴', '⁗'][Math.min(primes, 4) - 1], { lspace: '0', rspace: '0' })]);
    }
    const scriptBase = out;
    const under = limits === 'always' || (limits === 'display' && this.display);
    if (sub || sup) {
      if (under) {
        const op = coreOperator(base);
        if (op && base.tag === 'mo') op.attrs = { ...op.attrs, movablelimits: limits === 'always' ? 'false' : 'true' };
        if (sub && sup) out = node('munderover', null, [scriptBase, sub, sup]);
        else out = sub ? node('munder', null, [scriptBase, sub]) : node('mover', null, [scriptBase, sup]);
      } else if (sub && sup) {
        out = node('msubsup', null, [scriptBase, sub, sup]);
      } else {
        out = sub ? node('msub', null, [scriptBase, sub]) : node('msup', null, [scriptBase, sup]);
      }
    }
    if (!base[FUNCTION]) return [out];
    out[FUNCTION] = true;
    return [out, mo(APPLY)];
  }

  /** One atom: a group, a command, a number, a letter or an operator character. */
  parseAtom() {
    this.skipSpace();
    const at = this.i;
    const ch = this.peek();
    if (ch === '{') return this.parseGroup();
    if (ch === '\\') return this.parseCommand();
    if (ch === '%') this.fail('Unescaped "%" (write "\\%")', at);
    if (ch === '#') this.fail('Unescaped "#" (write "\\#")', at);
    if (ch === '$') this.fail('"$" inside an equation', at);
    if (ch === '}') this.fail('Unbalanced "}" with no group open', at);
    if (DIGIT.test(ch)) {
      const number = NUMBER.exec(this.src.slice(this.i))[0];
      this.i += number.length;
      return token('mn', styleText(number, this.font));
    }
    if (ASCII_LETTER.test(ch) && this.font) {
      // Inside a font command a run of letters is one name: \mathrm{mm}, \operatorname{atan2}.
      const run = (this.fontDigits ? /^[A-Za-z][A-Za-z0-9]*/ : /^[A-Za-z]+/).exec(this.src.slice(this.i))[0];
      this.i += run.length;
      return this.letters(run);
    }
    this.next();
    if (LETTER.test(ch)) return this.letters(ch);
    if (ch === '-' || ch === MINUS) return mo(MINUS);
    if (ch === '*') return mo('∗');
    if (ch === '~') return space(SPACES[' ']);
    if (LARGE_CHARS.has(ch)) return this.large(ch, ch === '∫' ? 'never' : 'display');
    return delimiter(ch);
  }

  /** Letters as an identifier in the active font. */
  letters(text) {
    if (this.font === 'normal') {
      return [...text].length === 1 ? token('mi', text, { mathvariant: 'normal' }) : token('mi', text);
    }
    if (this.font) return token('mi', styleText(text, this.font));
    return token('mi', text);
  }

  large(ch, limits) {
    const op = mo(ch);
    op[LIMITS] = limits;
    return op;
  }

  // --------------------------------------------------------- commands --

  parseCommand() {
    const at = this.i;
    const name = this.readCommand();
    if (!/^[A-Za-z]+$/.test(name)) return this.symbolCommand(name, at);
    if (!COMMANDS.has(name)) this.fail(`Unknown command "\\${name}"`, at);

    if (name in GREEK) {
      const ch = GREEK[name];
      const upper = ch === ch.toUpperCase() && ch !== ch.toLowerCase();
      if (this.font && this.font !== 'normal') return token('mi', styleChar(ch, this.font));
      return upper ? token('mi', ch, { mathvariant: 'normal' }) : token('mi', ch);
    }
    if (name in ORDINARY) return token('mi', styleChar(ORDINARY[name], this.font));
    if (name in OPERATORS) {
      const text = OPERATORS[name];
      return name === 'prime' ? mo(text, { lspace: '0', rspace: '0' }) : mo(text);
    }
    if (name in DELIMITER_COMMANDS) return delimiter(DELIMITER_COMMANDS[name]);
    if (name in LARGE) return this.large(LARGE[name], name === 'int' ? 'never' : 'display');
    if (FUNCTIONS.has(name)) return this.functionHead(name, LIMIT_FUNCTIONS.has(name));
    if (name in SPACES) return space(SPACES[name]);
    if (name in ACCENTS) {
      const [mark, stretchy] = ACCENTS[name];
      const base = this.parseArg(`argument of "\\${name}"`);
      return node('mover', { accent: 'true' }, [base, mo(mark, { stretchy: String(stretchy) })]);
    }
    if (name in FONTS) return this.font_(FONTS[name], false, name);
    if (name in TEXT_STYLES) return this.text(name);
    if (name in BIG_SIZES) {
      const ch = this.parseDelimiter(name);
      if (ch === null) return mrow([]);
      const attrs = { stretchy: 'true', symmetric: 'true', minsize: BIG_SIZES[name], maxsize: BIG_SIZES[name] };
      if (OPENING.has(ch)) attrs.form = 'prefix';
      if (CLOSING.has(ch)) attrs.form = 'postfix';
      return delimiter(ch, attrs);
    }

    switch (name) {
      case 'frac':
      case 'dfrac':
      case 'tfrac': {
        const num = this.parseInnerArg('numerator');
        const den = this.parseInnerArg('denominator');
        const frac = node('mfrac', null, [num, den]);
        if (name === 'frac') return frac;
        return node('mstyle', { displaystyle: String(name === 'dfrac'), scriptlevel: '0' }, [frac]);
      }
      case 'binom': {
        const top = this.parseInnerArg('first argument of "\\binom"');
        const bottom = this.parseInnerArg('second argument of "\\binom"');
        return mrow([fence('(', 'prefix'), node('mfrac', { linethickness: '0' }, [top, bottom]), fence(')', 'postfix')]);
      }
      case 'sqrt': {
        this.skipSpace();
        if (this.src[this.i] === '[') {
          const openedAt = this.i;
          this.i += 1;
          const saved = this.display;
          this.display = false;
          const index = this.parseExpression({ bracket: true });
          this.display = saved;
          this.expectStop(']', openedAt);
          this.i += 1;
          const radicand = this.parseArg('argument of "\\sqrt"');
          return node('mroot', null, [radicand, group(index)]);
        }
        return node('msqrt', null, [this.parseArg('argument of "\\sqrt"')]);
      }
      case 'overset':
      case 'stackrel': {
        const over = this.parseInnerArg(`first argument of "\\${name}"`);
        return node('mover', null, [this.parseArg(`second argument of "\\${name}"`), over]);
      }
      case 'underset': {
        const under = this.parseInnerArg('first argument of "\\underset"');
        return node('munder', null, [this.parseArg('second argument of "\\underset"'), under]);
      }
      case 'overline':
      case 'underline': {
        /* Chromium stretches no operator along the inline axis (measured: a
         * stretchy U+203E, U+005F, U+0332, even U+2192, keeps its natural
         * width over a wide base), so a rule over or under a group would be
         * a short dash in the middle of it. A border on the group is drawn
         * at exactly its width, and MathML Core lays out the CSS box model. */
        const base = this.parseArg(`argument of "\\${name}"`);
        const style = name === 'overline'
          ? 'border-top: 0.06em solid; padding-top: 0.1em'
          : 'border-bottom: 0.06em solid; padding-bottom: 0.06em';
        return node('mrow', { style }, [base]);
      }
      case 'operatorname': {
        const starred = this.src[this.i] === '*';
        if (starred) this.i += 1;
        const saved = [this.font, this.fontDigits];
        this.font = 'normal';
        this.fontDigits = true;
        const head = this.parseArg('argument of "\\operatorname"');
        [this.font, this.fontDigits] = saved;
        head[FUNCTION] = true;
        if (starred) head[LIMITS] = 'display';
        return head;
      }
      case 'bmod':
        return mo('mod', { lspace: '0.2778em', rspace: '0.2778em' });
      case 'pmod':
      case 'mod': {
        const arg = this.parseArg(`argument of "\\${name}"`);
        const body = [space(1), token('mi', 'mod'), space(1 / 3), arg];
        if (name === 'mod') return mrow(body);
        return mrow([space(1), delimiter('('), token('mi', 'mod'), space(1 / 3), arg, delimiter(')')]);
      }
      case 'left':
        return this.leftRight(at);
      case 'begin':
        return this.environment(at);
      case 'right':
        this.fail('"\\right" without a matching "\\left"', at);
      // eslint-disable-next-line no-fallthrough
      case 'end':
        this.fail('"\\end" without a matching "\\begin"', at);
      // eslint-disable-next-line no-fallthrough
      case 'limits':
      case 'nolimits':
        this.fail(`"\\${name}" must follow a large operator`, at);
      // eslint-disable-next-line no-fallthrough
      case 'displaystyle':
      case 'textstyle':
        // Reached only as a lone argument (\frac\displaystyle…), where it switches nothing.
        return mrow([]);
      default:
        this.fail(`Command "\\${name}" is whitelisted but not implemented`, at);
    }
    return null;
  }

  symbolCommand(name, at) {
    if (!SUPPORTED_SYMBOL_COMMANDS.includes(name)) this.fail(`Unknown command "\\${name}"`, at);
    if (name === '!') {
      /* Chromium clamps a negative mspace width to zero; a negative inline
       * margin on an empty mspace does pull its neighbours together. */
      return { tag: 'mspace', attrs: { width: '0em', style: 'margin-inline-start: -0.1667em' } };
    }
    if (name in SPACES) return space(SPACES[name]);
    if (name in DELIMITER_COMMANDS) return delimiter(DELIMITER_COMMANDS[name]);
    if (name === '\\') this.fail('"\\\\" outside an environment', at);
    return token('mi', name); // \% \# \& \_
  }

  /** The delimiter after \left, \right or \big…; `null` for the empty `.`. */
  parseDelimiter(after) {
    this.skipSpace();
    const at = this.i;
    if (this.atEnd()) this.fail(`Missing delimiter after "\\${after}"`, at);
    if (this.src[this.i] === '\\') {
      const name = this.readCommand();
      if (name in DELIMITER_COMMANDS) return DELIMITER_COMMANDS[name];
      this.fail(`"\\${name}" is not a delimiter (after "\\${after}")`, at);
    }
    const ch = this.next();
    if (ch === '.') return null;
    if (ch === '<') return '⟨';
    if (ch === '>') return '⟩';
    if (DELIMITER_CHARS.has(ch)) return ch;
    this.fail(`"${ch}" is not a delimiter (after "\\${after}")`, at);
    return null;
  }

  leftRight(at) {
    const open = this.parseDelimiter('left');
    const body = this.parseExpression();
    this.expectStop('right', at);
    this.readCommand();
    const close = this.parseDelimiter('right');
    const children = [];
    if (open !== null) children.push(fence(open, 'prefix'));
    children.push(...body);
    if (close !== null) children.push(fence(close, 'postfix'));
    return mrow(children);
  }

  /** A named function: upright, followed (after its scripts) by U+2061 function application. */
  functionHead(name, limits) {
    const head = token('mi', name);
    head[FUNCTION] = true;
    if (limits) head[LIMITS] = 'display';
    return head;
  }

  font_(font, digits, name) {
    const saved = [this.font, this.fontDigits];
    this.font = font;
    this.fontDigits = digits;
    const out = this.parseArg(`argument of "\\${name}"`);
    [this.font, this.fontDigits] = saved;
    return out;
  }

  /** \text and friends: the braces' raw characters, spaces kept. */
  text(name) {
    this.skipSpace();
    const at = this.i;
    if (this.src[this.i] !== '{') this.fail(`"\\${name}" needs a braced argument`, at);
    this.i += 1;
    let depth = 0;
    let out = '';
    for (;;) {
      if (this.atEnd()) this.fail('Unbalanced "{": the group is never closed', at);
      const ch = this.next();
      if (ch === '{') { depth += 1; continue; }
      if (ch === '}') {
        if (depth === 0) break;
        depth -= 1;
        continue;
      }
      if (ch === '\\') {
        const escaped = this.next();
        if ('%#&_{}$ '.includes(escaped) && escaped) { out += escaped; continue; }
        this.fail(`"\\${escaped}…" inside "\\${name}" (only \\% \\# \\& \\_ \\{ \\} \\$ and "\\ " are read there)`, this.i - 2);
      }
      if (ch === '$') this.fail(`"$" inside "\\${name}"`, this.i - 1);
      if (ch === '%') this.fail('Unescaped "%" (write "\\%")', this.i - 1);
      out += ch;
    }
    const style = TEXT_STYLES[name];
    return token('mtext', textGlyphs(out), style ? { style } : null);
  }

  /** \begin{…} … \end{…}: rows of cells, as an mtable inside its fences. */
  environment(at) {
    const envName = this.envName('begin', at);
    const env = ENVIRONMENTS[envName];
    const saved = this.display;
    this.display = env.display;
    const rows = [];
    let row = [];
    for (;;) {
      row.push(this.parseExpression());
      this.skipSpace();
      const ch = this.src[this.i];
      const name = this.peekCommand();
      if (ch === '&') {
        this.i += 1;
        continue;
      }
      if (name === '\\') {
        this.readCommand();
        this.skipSpace();
        const skip = ROW_SKIP.exec(this.src.slice(this.i));
        if (skip) this.i += skip[0].length;
        rows.push(row);
        row = [];
        this.skipSpace();
        // A trailing \\ before \end closes the last row instead of opening an empty one.
        if (this.peekCommand() === 'end') break;
        continue;
      }
      if (name === 'end') {
        rows.push(row);
        break;
      }
      if (this.atEnd()) this.fail(`"\\begin{${envName}}" is never closed`, at);
      this.expectStop('endenv', at);
    }
    const endAt = this.i;
    this.readCommand();
    const closing = this.envName('end', endAt);
    if (closing !== envName) this.fail(`"\\end{${closing}}" closes "\\begin{${envName}}"`, endAt);
    this.display = saved;

    const width = Math.max(...rows.map((r) => r.length));
    const table = node('mtable', { displaystyle: String(env.display) }, rows.map((cells) => node('mtr', null,
      Array.from({ length: width }, (_, c) => {
        const style = cellStyle(env.align, c);
        return node('mtd', style ? { style } : null, cells[c] ?? []);
      }))));
    const children = [];
    if (env.open) children.push(fence(env.open, 'prefix'));
    children.push(table);
    if (env.close) children.push(fence(env.close, 'postfix'));
    return children.length === 1 ? table : mrow(children);
  }

  envName(which, at) {
    this.skipSpace();
    const match = /^\{([A-Za-z*]+)\}/.exec(this.src.slice(this.i));
    if (!match) this.fail(`"\\${which}" needs an environment name in braces`, at);
    this.i += match[0].length;
    if (!SUPPORTED_ENVIRONMENTS.includes(match[1])) this.fail(`Unknown environment "${match[1]}"`, at);
    return match[1];
  }
}

/* CSS for a cell: MathML Core has no columnalign, so cases and aligned set it
 * here. Chromium centres a cell by default and draws any plain text-align
 * value, `right` included, as start-aligned; it right-aligns only for
 * `-webkit-right` (measured in math-probe). The declaration before it is the
 * standard value for an engine that rejects the prefixed one. */
const LEFT = 'text-align: left';
const RIGHT = 'text-align: right; text-align: -webkit-right';

function cellStyle(align, column) {
  if (align === 'cases') return column === 0 ? `${LEFT}; padding-left: 0` : `${LEFT}; padding-left: 1em`;
  if (align === 'aligned') {
    if (column % 2 === 1) return `${LEFT}; padding-left: 0`;
    return column === 0 ? `${RIGHT}; padding-right: 0` : `${RIGHT}; padding-right: 0; padding-left: 2em`;
  }
  return null;
}

/** Text as typeset: a hyphen between words, a minus before a digit, en and em dashes, kept spaces. */
function textGlyphs(text) {
  return text
    .replace(/---/g, '\u2014')
    .replace(/--/g, '\u2013')
    .replace(/(^|[^\p{L}\p{N}])-(?=[0-9])/gu, `$1${MINUS}`)
    .replace(/-/g, '\u2010')
    .replace(/~/g, '\u00A0')
    // Leading and trailing spaces would collapse at the token's edges.
    .replace(/ /g, '\u00A0');
}

/* TeX's thin spaces around a named function: before it when it follows an
 * ordinary symbol or a closing delimiter (Ord–Op, Close–Op), and after it
 * unless an operator or a delimiter follows (sin θ, but sin(θ)). */
function spaceFunctions(list) {
  const out = [];
  for (let i = 0; i < list.length; i += 1) {
    const n = list[i];
    /* A sign after an operator, a relation, a comma or an opening delimiter is
     * unary, as TeX reads it: (−π, < −0.10. The dictionary would otherwise
     * space it as a binary operator once it is not first in its row. */
    if (n.tag === 'mo' && SIGNS.has(n.text) && out.length) {
      const prev = coreOperator(out[out.length - 1]);
      if (prev && !CLOSING.has(prev.text) && prev.text !== '′' && prev.text !== '″') n.attrs = { ...n.attrs, form: 'prefix' };
    }
    if (n[FUNCTION] && out.length) {
      const prev = coreOperator(out[out.length - 1]);
      if (!prev || CLOSING.has(prev.text) || prev.text === '|' || prev.text === '‖') out.push(space(3 / 18));
    }
    if (n.tag === 'mo' && n.text === APPLY) {
      const following = list[i + 1];
      if (following && following.tag !== 'mspace' && !leadingOperator(following)) n.attrs = { rspace: `${(3 / 18).toFixed(4)}em` };
    }
    out.push(n);
  }
  return out;
}

/**
 * The equation `tex` as a MathML node tree (see the header). Throws
 * `MathSyntaxError` for anything outside the supported subset.
 */
export function texToTree(tex, { display = false } = {}) {
  const source = String(tex ?? '');
  const parser = new Parser(source, Boolean(display));
  const body = parser.parseExpression();
  parser.expectStop('end', 0);
  return {
    tag: 'math',
    attrs: { display: display ? 'block' : 'inline' },
    children: [{
      tag: 'semantics',
      children: [
        mrow(body),
        { tag: 'annotation', attrs: { encoding: 'application/x-tex' }, text: source },
      ],
    }],
  };
}

/** Build a node tree as MathML elements of `doc`: elements and text nodes only. */
export function mountMath(tree, doc = document) {
  const element = doc.createElementNS(MATHML_NS, tree.tag);
  for (const [name, value] of Object.entries(tree.attrs ?? {})) element.setAttribute(name, String(value));
  if (typeof tree.text === 'string') element.append(doc.createTextNode(tree.text));
  for (const child of tree.children ?? []) element.append(mountMath(child, doc));
  return element;
}
