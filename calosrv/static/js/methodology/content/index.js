/* The Methodology article, composed from its parts.
 *
 * Each part is a module of plain data - no DOM, no imports but
 * `../constants.js` - and the renderer (`methodology/render.js`) numbers the
 * sections, equations, tables, figures and references in the order they
 * appear here, so no part ever types a number of its own.
 *
 * ## The content model
 *
 * A part exports one section, `{id, title, blocks, sections?}`; `sections`
 * nests sub-sections of the same shape. Blocks:
 *
 * - `{kind: 'p', text}` - a paragraph;
 * - `{kind: 'eq', id, tex}` - a numbered display equation; `numbered: false`
 *   draws one without a number;
 * - `{kind: 'list', ordered?, items}`;
 * - `{kind: 'table', id, caption, head, rows, note?}` - the caption goes above;
 * - `{kind: 'figure', id, exhibit, caption}` - a figure drawn from the code by
 *   `methodology/exhibits.js` (`ramps`, `puor`, `se3`);
 * - `{kind: 'callout', tone: 'rule' | 'note' | 'caution', title?, text}`;
 * - `{kind: 'links', id, items: [{page: 'physics' | 'models', panel, set?,
 *   label}]}` - a row of "Open in Physics/Models →" badges. `panel` is a card
 *   id of that page; `set` patches view keys of state.js (the frame or channel
 *   the section is about) and is validated against it. The row's id is where
 *   the Details drawer's return link lands.
 *
 * Ids carry their kind as a prefix - `sec-`, `app-`, `eq-`, `tab-`, `fig-`,
 * `lnk-` - and are unique across the article.
 *
 * ## Inline syntax (text, list items, table cells, captions, callouts)
 *
 * - `$…$` inline TeX, from the subset `math.js` accepts (an unknown command
 *   throws). Display TeX has no `$`. A prime comes before a subscript:
 *   `x'_i`, not `x_i'`, which throws as a double superscript would.
 * - `\$`, `\*`, `` \` `` and `\[` write the character itself.
 * - `[[<id>]]` a cross-reference, written by kind: (3), Table 2, Figure 1,
 *   §2.1, Appendix A. `[[cite:<key>]]` a citation of `references.js`,
 *   numbered by first citation.
 * - `` `code` `` an identifier, file, key or column; `*emphasis*`, `**strong**`.
 *
 * ## The rules the parts keep
 *
 * - The article follows the code. Every number the code defines comes from
 *   `C` (`../constants.js`), pinned to its source by
 *   tests/test_methodology_constants.py; a measured figure is cited with its
 *   dataset and source, never typed as a constant.
 * - The notation is Appendix A's (`appendix_notation.js`): one symbol, one
 *   meaning across all parts.
 * - The vocabulary is CLAUDE.md's: the frames' names, British spelling, U+2212
 *   for every negative number in prose (TeX writes `-`, drawn as U+2212), and
 *   none of the retired phrases the asset tests reject.
 * - Strings holding TeX are `String.raw`, so backslashes survive; never write
 *   `${` as text, which starts a template substitution.
 *
 * tests/test_js_methodology.py builds the whole article and fails on an
 * unknown id or citation, an equation that does not compile, a badge that
 * names no card, or an ASCII hyphen before a digit in the rendered text.
 */

import front from './front.js';
import introduction from './s1_introduction.js';
import methods from './s2_methods.js';
import frames from './s2_1_frames.js';
import discretisation from './s2_2_discretisation.js';
import attribution from './s2_3_attribution.js';
import statistics from './s2_4_statistics.js';
import results from './s3_results.js';
import discussion from './s4_discussion.js';
import conclusion from './s5_conclusion.js';
import references from './references.js';
import notation from './appendix_notation.js';

export const ARTICLE = Object.freeze({
  front,
  sections: [
    introduction,
    { ...methods, sections: [frames, discretisation, attribution, statistics] },
    results,
    discussion,
    conclusion,
  ],
  references,
  // Appendix B is generated from methodology/constants.js by the renderer.
  appendices: [
    notation,
    { id: 'app-constants', title: 'Constants', generated: 'constants' },
  ],
});
