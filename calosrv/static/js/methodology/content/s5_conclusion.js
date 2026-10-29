/* §5 Conclusion: the framework as a reproducible blueprint.
 * Content model and rules: index.js. */

import { C } from '../constants.js';

const tx = (strings, ...values) => String.raw(strings, ...values).replace(/\\`/g, '`');

export default {
  id: 'sec-conclusion',
  title: 'Conclusion',
  blocks: [
    { kind: 'p', text: tx`We have described the methodology of a diagnostic service for overlapping calorimeter showers: a rigid co-registration that makes energy from different events addable ([[sec-frames]]), conservative resampling of an irregular, staggered lattice whose artefacts are measured on every response rather than assumed away ([[sec-discretisation]]), attribution channels that keep a signed quantity signed ([[sec-attribution]]), and a statistical layer that gates every reported number and every drawn mark by the evidence behind it ([[sec-statistics]]). Each rule is enforced where it is computed, on the server, and each panel discloses what it clipped, smoothed, withheld or estimated.` },
    { kind: 'p', text: tx`The framework is offered as a reproducible blueprint, and its reproducibility rests on one convention: **the code is the specification**. Where the directive that asked for a rule and the code that implements it disagree, this article states what the code does. Every constant it quotes, from the low-N ladder that starts at $N = ${C.MIN_MOMENT_SAMPLES}$ to the ${C.RESPONSE_LIMIT / 1000} KB response contract, is read from one table that a test resolves against the live code (\`tests/test_methodology_constants.py\`), so a changed threshold fails the build before it can make the article wrong; [[app-constants]] lists them with their sources. The measured figures it cites are quoted with the dataset they were measured on and are not results of this article.` },
    { kind: 'p', text: tx`Two boundaries remain. The figures were measured on simulated files, and the co-registered views rest on the true incident direction and the true shower assignment, which detector data would replace with reconstructed estimates and their uncertainties ([[sec-discussion-observables]]). Within those boundaries the method transfers: another detector needs its own lattice measured and its own comb re-checked, but not a new set of rules. The article's badges open each live panel with the reader's view, and the panel's Details drawer links back to the passage that sent the reader there, so each claim can be checked against the running service.` },
  ],
};
