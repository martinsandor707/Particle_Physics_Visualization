/* The Methodology article, composed from its parts.
 *
 * Each part is a module of plain data (data/dev/design/methodology/brief.md
 * holds the content model): sections of blocks, with inline cross-references
 * by id. The renderer (methodology/render.js) numbers the sections,
 * equations, tables and figures in the order they appear here, so no part
 * ever types a number of its own.
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
