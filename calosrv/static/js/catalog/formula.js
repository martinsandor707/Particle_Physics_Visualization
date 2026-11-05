/*
 * A tiny parser and evaluator for the PySR formulas of the training report (catalog/benchmarks.js).
 *
 * Pure and DOM-free; never `eval`, never `Function`. Two syntaxes are accepted:
 *  - the explicit `ascii` form of the catalogue: decimal points, `^` for powers, `*` for every product
 *    (`61.67*sqrt(E_sum*max_hit_frac)+7.114`);
 *  - the report's implicit form, once `normaliseReportFormula` has turned its decimal commas into points,
 *    `²` into `^2`, `·` into `*` and dropped a leading "p ≈" (`61,67 sqrt(E_sum max_hit_frac)+7,114`).
 *    The prefix root `√` is read as `sqrt` of the factor that follows it (`0,047·√voxelszám`).
 *
 * Grammar (lowest precedence first):
 *   sum     := product (('+' | '-') product)*                         left-associative
 *   product := unary (('*' | '/') unary | <implicit> unary)*            left-associative, one level
 *   unary   := '-' unary | '+' unary | power                           so -x^2 = -(x^2)
 *   power   := postfix ('^' unary)?                                    right-associative
 *   postfix := number | identifier | function '(' sum ')' | '√' postfix | '(' sum ')'
 * Implicit multiplication joins two adjacent factors when the left one ends with a number, an identifier
 * that is not a function name, or ')', and the right one starts with a number, an identifier, a function,
 * '√' or '('. A number never directly follows a number.
 *
 * Identifiers are letters (any script, so the proton's Hungarian names such as `θ_súlypont` parse), digits
 * and underscores, not starting with a digit; the brief's ASCII set is a subset. Functions: sqrt, exp, log
 * (natural). Numbers: `12`, `0.5`, `.5`, `6.713e-7` (an `e` is an exponent only when a digit follows it,
 * with an optional sign).
 *
 * AST nodes (frozen): { type: 'num', value } | { type: 'var', name } | { type: 'neg', arg }
 *   | { type: 'bin', op: '+'|'-'|'*'|'/'|'^', left, right } | { type: 'call', fn: 'sqrt'|'exp'|'log', arg }.
 *
 * evaluate(ast, vars) returns NaN outside the domain (a root or logarithm of a negative, 0^negative, a
 * division by zero, any non-finite intermediate) and throws a ReferenceError for an unbound variable.
 */

export const FUNCTIONS = Object.freeze(['sqrt', 'exp', 'log']);

/** Bad formula text: `position` is the 0-based offset into the parsed text. */
export class FormulaSyntaxError extends Error {
  constructor(message, position = null, text = null) {
    super(position === null ? message : `${message} at position ${position}`);
    this.name = 'FormulaSyntaxError';
    this.position = position;
    this.text = text;
  }
}

const NUMBER = /^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/;
const IDENT = /^[\p{L}_][\p{L}\p{N}_]*/u;
const SPACE = /^\s+/;

function tokenize(text) {
  if (typeof text !== 'string') throw new FormulaSyntaxError('formula text must be a string');
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    const rest = text.slice(i);
    let m = SPACE.exec(rest);
    if (m) { i += m[0].length; continue; }
    m = NUMBER.exec(rest);
    if (m) {
      tokens.push({ kind: 'num', value: Number(m[0]), pos: i });
      i += m[0].length;
      continue;
    }
    m = IDENT.exec(rest);
    if (m) {
      const kind = FUNCTIONS.includes(m[0]) ? 'fn' : 'id';
      tokens.push({ kind, value: m[0], pos: i });
      i += m[0].length;
      continue;
    }
    const ch = text[i];
    if ('+-*/^()'.includes(ch)) {
      tokens.push({ kind: ch, pos: i });
      i += 1;
      continue;
    }
    if (ch === '√') {
      tokens.push({ kind: 'root', pos: i });
      i += 1;
      continue;
    }
    throw new FormulaSyntaxError(`unexpected character "${ch}"`, i, text);
  }
  return tokens;
}

const node = (n) => Object.freeze(n);

function parseTokens(tokens, text) {
  let k = 0;
  const peek = () => tokens[k];
  const fail = (message, tok = peek()) => {
    throw new FormulaSyntaxError(message, tok ? tok.pos : text.length, text);
  };
  const expect = (kind) => {
    const tok = peek();
    if (!tok || tok.kind !== kind) fail(`expected "${kind}"`);
    k += 1;
    return tok;
  };
  const startsFactor = (tok) => tok && ['num', 'id', 'fn', 'root', '('].includes(tok.kind);

  function sum() {
    let left = product();
    while (peek() && (peek().kind === '+' || peek().kind === '-')) {
      const op = tokens[k++].kind;
      left = node({ type: 'bin', op, left, right: product() });
    }
    return left;
  }

  function product() {
    let left = unary();
    for (;;) {
      const tok = peek();
      if (tok && (tok.kind === '*' || tok.kind === '/')) {
        k += 1;
        left = node({ type: 'bin', op: tok.kind, left, right: unary() });
        continue;
      }
      // Implicit multiplication: the previous token ended a factor, this one starts one.
      const prev = tokens[k - 1];
      if (startsFactor(tok) && prev && ['num', 'id', ')'].includes(prev.kind)) {
        if (prev.kind === 'num' && tok.kind === 'num') fail('two numbers in a row');
        left = node({ type: 'bin', op: '*', left, right: unary() });
        continue;
      }
      return left;
    }
  }

  function unary() {
    const tok = peek();
    if (tok && tok.kind === '-') { k += 1; return node({ type: 'neg', arg: unary() }); }
    if (tok && tok.kind === '+') { k += 1; return unary(); }
    return power();
  }

  function power() {
    const base = postfix();
    if (peek() && peek().kind === '^') {
      k += 1;
      return node({ type: 'bin', op: '^', left: base, right: unary() });
    }
    return base;
  }

  function postfix() {
    const tok = peek();
    if (!tok) fail('unexpected end of formula');
    if (tok.kind === 'num') { k += 1; return node({ type: 'num', value: tok.value }); }
    if (tok.kind === 'id') { k += 1; return node({ type: 'var', name: tok.value }); }
    if (tok.kind === 'fn') {
      k += 1;
      expect('(');
      const arg = sum();
      expect(')');
      return node({ type: 'call', fn: tok.value, arg });
    }
    if (tok.kind === 'root') {
      k += 1;
      return node({ type: 'call', fn: 'sqrt', arg: postfix() });
    }
    if (tok.kind === '(') {
      k += 1;
      const inner = sum();
      expect(')');
      return inner;
    }
    return fail(`unexpected "${tok.kind}"`);
  }

  if (tokens.length === 0) throw new FormulaSyntaxError('empty formula', 0, text);
  const ast = sum();
  if (k < tokens.length) fail(`unexpected "${peek().kind}"`);
  return ast;
}

/** Parse a formula in the explicit or the (normalised) implicit syntax into a frozen AST. */
export function parseFormula(text) {
  return parseTokens(tokenize(text), text);
}

/**
 * The report's own formula text made parseable: a leading "p ≈" / "θ ≈" / "y =" dropped, decimal commas
 * to points (the formulas have no argument lists, so a comma is always decimal), the superscripts ² and ³
 * to ^2 and ^3, `·` and `×` to `*`, and the typographic minus U+2212 to `-`.
 */
export function normaliseReportFormula(source) {
  if (typeof source !== 'string') throw new FormulaSyntaxError('formula text must be a string');
  return source
    .replace(/^[^≈=]*[≈=]\s*/u, '')
    .replace(/(\d),(\d)/g, '$1.$2')
    .replace(/²/g, '^2')
    .replace(/³/g, '^3')
    .replace(/[·×]/g, '*')
    .replace(/−/g, '-')
    .trim();
}

/** Parse the report's implicit form (see normaliseReportFormula). */
export function parseReportFormula(source) {
  return parseFormula(normaliseReportFormula(source));
}

const finite = (x) => (Number.isFinite(x) ? x : NaN);

/** Evaluate an AST with `vars` ({ name: number }). NaN outside the domain; ReferenceError when unbound. */
export function evaluate(ast, vars = {}) {
  switch (ast.type) {
    case 'num': return ast.value;
    case 'var': {
      if (!Object.prototype.hasOwnProperty.call(vars, ast.name)) {
        throw new ReferenceError(`formula variable "${ast.name}" has no value`);
      }
      return finite(Number(vars[ast.name]));
    }
    case 'neg': return -evaluate(ast.arg, vars);
    case 'call': {
      const x = evaluate(ast.arg, vars);
      if (ast.fn === 'sqrt') return x < 0 ? NaN : Math.sqrt(x);
      if (ast.fn === 'log') return x > 0 ? Math.log(x) : NaN;
      if (ast.fn === 'exp') return finite(Math.exp(x));
      throw new FormulaSyntaxError(`unknown function "${ast.fn}"`);
    }
    case 'bin': {
      const a = evaluate(ast.left, vars);
      const b = evaluate(ast.right, vars);
      switch (ast.op) {
        case '+': return finite(a + b);
        case '-': return finite(a - b);
        case '*': return finite(a * b);
        case '/': return b === 0 ? NaN : finite(a / b);
        case '^': return finite(Math.pow(a, b));
        default: throw new FormulaSyntaxError(`unknown operator "${ast.op}"`);
      }
    }
    default: throw new FormulaSyntaxError(`unknown node "${ast.type}"`);
  }
}

/** The variables an AST reads, sorted and unique. */
export function variables(ast) {
  const seen = new Set();
  const walk = (n) => {
    if (n.type === 'var') seen.add(n.name);
    else if (n.type === 'neg' || n.type === 'call') walk(n.arg);
    else if (n.type === 'bin') { walk(n.left); walk(n.right); }
  };
  walk(ast);
  return [...seen].sort();
}

/** Parse once, evaluate many: `compileFormula(text)(vars)`. */
export function compileFormula(text) {
  const ast = parseFormula(text);
  const fn = (vars) => evaluate(ast, vars);
  return Object.freeze(Object.assign(fn, { ast, variables: variables(ast) }));
}
