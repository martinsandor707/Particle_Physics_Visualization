/* Where the Methodology explains each card of the Physics and Models pages.
 *
 * Every Details drawer of the two dashboard pages links to the section of the
 * article that says how its panel is computed and drawn (shell.js
 * `sectionOf`). The pages must not load the article: its content, renderer
 * and figures are the Methodology page's alone (test_api.py keeps the module
 * graphs apart), and a drawer needs three strings per card, not the article.
 * So the map is data, in a leaf module with no imports, and
 * tests/test_article_sections.py keeps it in step with the article: it lays
 * the article out, derives the map below from it and fails on any drift,
 * printing the entries to paste here.
 *
 * Each entry is `{at, section, title}`: the element of the article to land
 * on (a badge row, or a section), the number of the section holding it and
 * that section's title as plain text. The rules that choose `at`:
 *
 * - a card a badge names in §3 (Results) lands on the first §3 badge row
 *   naming it, since Results is where each encoding is audited;
 * - a badged card absent from §3 lands on its first badge row anywhere;
 * - a card no badge names takes its family's place: the compare-frames cells
 *   the row of `compare-lab-xy`, the 3-D event's projections (`vproj-*`) that
 *   of `vox-event`, the ensemble's (`eproj-*`) that of `vox-ensemble`, and
 *   the Event Inspector's nine cells (`event-*`) the section describing it.
 */

const ENTRIES = {
  physics: {
    xy: { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    yz: { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    xz: { at: 'lnk-frames-local', section: '2.1.5', title: 'Per-shower frames: Local and the legacy translated frame' },
    energy: { at: 'lnk-results-response', section: '3.4', title: 'Response, sampling fraction and resolution (plot 4, B1–B3)' },
    'profile-w': { at: 'lnk-results-profiles', section: '3.3', title: 'Longitudinal and radial profiles (C7)' },
    'profile-r': { at: 'lnk-results-profiles', section: '3.3', title: 'Longitudinal and radial profiles (C7)' },
    'response-b1': { at: 'lnk-results-response', section: '3.4', title: 'Response, sampling fraction and resolution (plot 4, B1–B3)' },
    'response-b2': { at: 'lnk-results-response', section: '3.4', title: 'Response, sampling fraction and resolution (plot 4, B1–B3)' },
    'response-res': { at: 'lnk-results-response', section: '3.4', title: 'Response, sampling fraction and resolution (plot 4, B1–B3)' },
    'response-b3': { at: 'lnk-results-response', section: '3.4', title: 'Response, sampling fraction and resolution (plot 4, B1–B3)' },
    distribution: { at: 'lnk-results-distributions', section: '3.5', title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)' },
    correlation: { at: 'lnk-results-colour', section: '3.2', title: 'Perceptual colorimetry, screen against print' },
    statistics: { at: 'lnk-results-distributions', section: '3.5', title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)' },
    'compare-lab-xy': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-lab-xz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-lab-yz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-trans-xy': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-trans-xz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-trans-yz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-local-xy': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-local-xz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'compare-local-yz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'event-lab-xy': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-lab-xz': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-lab-yz': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-trans-xy': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-trans-xz': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-trans-yz': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-local-xy': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-local-xz': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
    'event-local-yz': { at: 'sec-spatial', section: '3.1', title: 'Spatial projections' },
  },
  models: {
    'perf-bins': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'pred-truth': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'pred-residuals': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'xgb-cv': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'xgb-binary': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'xgb-surrogate': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'xgb-importance': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'feat-table': { at: 'lnk-results-distributions', section: '3.5', title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)' },
    'feat-corr': { at: 'lnk-results-distributions', section: '3.5', title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)' },
    'feat-hist': { at: 'lnk-results-distributions', section: '3.5', title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)' },
    'feat-hist2d': { at: 'lnk-results-distributions', section: '3.5', title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)' },
    'prim-rate': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'vox-event': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'vproj-xy': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'vproj-xz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'vproj-yz': { at: 'lnk-results-spatial', section: '3.1', title: 'Spatial projections' },
    'vox-ensemble': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'eproj-xy': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'eproj-yz': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
    'eproj-xz': { at: 'lnk-results-models', section: '3.6', title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)' },
  },
};

function freeze(value) {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}

/** `{physics: {<card id>: {at, section, title}}, models: {...}}`, frozen. */
export const ARTICLE_SECTIONS = freeze(ENTRIES);

/**
 * The place in the article that explains `panelId` of `page` ('physics' or
 * 'models'): `{at, section, title}`, or null for a card the map does not
 * name. Own keys only, so no inherited property is mistaken for a card.
 */
export function articleSection(page, panelId) {
  const cards = Object.hasOwn(ARTICLE_SECTIONS, page) ? ARTICLE_SECTIONS[page] : null;
  return cards && Object.hasOwn(cards, panelId) ? cards[panelId] : null;
}
