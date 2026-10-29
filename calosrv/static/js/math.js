/* LaTeX to MathML Core, for the Methodology page's equations.
 *
 * STUB. This module fixes the API and the supported LaTeX subset; the
 * compiler behind `texToTree` is still to come. Until it lands, every equation
 * is drawn as its own source in an <mtext>, inside the same <semantics> and
 * <annotation encoding="application/x-tex"> wrapper the compiler will emit,
 * so the page can be built and tested against the final shape.
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
 *   instead of rendering garbage.
 * - Every rendered minus is U+2212: `-` in the source becomes `<mo>−</mo>`.
 *   The annotation keeps the source as written.
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

/**
 * The equation `tex` as a MathML node tree (see the header). STUB: the body is
 * the source itself in an <mtext>; the compiler replaces it.
 */
export function texToTree(tex, { display = false } = {}) {
  const source = String(tex ?? '');
  return {
    tag: 'math',
    attrs: { display: display ? 'block' : 'inline' },
    children: [{
      tag: 'semantics',
      children: [
        { tag: 'mrow', children: [{ tag: 'mtext', text: source }] },
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
