/* The article's front matter: title, authors, affiliations, abstract and
 * keywords. The provenance line (the service's version, the static build and
 * the date) is added by the page from the running service, never typed here.
 *
 * The authors and their affiliations are as the first author gave them; do
 * not reword them. */

import { C } from '../constants.js';

/** An integer with thousands separators, as the prose sets it. */
const grouped = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

export default {
  title: 'Rigorous out-of-core visual analytics for superimposed calorimeter showers: the methodology of calosrv',
  authors: [
    { name: 'Martin Tibor Sándor', affiliations: [1] },
    { name: 'Róbert Lakatos', affiliations: [2] },
  ],
  affiliations: [
    { id: 1, text: 'Doctoral School of Informatics, Faculty of Informatics, University of Debrecen, Debrecen, Hungary' },
    { id: 2, text: 'Department of Data Science and Visualization, Faculty of Informatics, University of Debrecen, Debrecen, Hungary' },
  ],
  abstract: [
    String.raw`Two particles that enter a sampling calorimeter close together leave superimposed showers, from which a reconstruction network must recover their energies, their separation and their incident directions, and whose pictures are easily drawn in ways that mislead. We describe the methodology of calosrv, the diagnostic service behind the Physics and Models pages of a dashboard for such data. A FastAPI and DuckDB service reads a ZSTD-compressed Parquet archive of 24,161,893 hits in 20,325 two-shower events, and single-shower samples of the electron (100,000 events), muon, pion and proton. It performs every spatial transformation, binning and statistical reduction on the server, and sends a browser that runs only vendored Apache ECharts pre-aggregated payloads under ${grouped(C.RESPONSE_LIMIT)} bytes each.`,
    String.raw`We state the mathematics behind every panel: four reference frames, among them a separation-aligned frame that co-registers each event by one SE(3) motion; area-weighted splatting and conservative display kernels, whose output can never exceed the raw peak; a ladder of sample-size gates that separates the numbers a panel reports from the shapes it draws; circular statistics for azimuths, whose arithmetic mean is meaningless; and colour ramps measured for contrast against the dark card they are drawn on. The same rules govern the evaluation of explainable networks through their per-hit Grad-CAM and signed Shap-CAM attributions, and of XGBoost regressors through cross-validation, thresholded classification and surrogate trees. Every constant the article quotes is read from the code, every measured figure is cited with the file it was measured on, and every encoding is audited against the rule it implements.`,
  ],
  keywords: [
    'calorimetry',
    'overlapping showers',
    'visual analytics',
    'out-of-core aggregation',
    'SE(3) co-registration',
    'conservative resampling',
    'circular statistics',
    'explainable machine learning',
  ],
};
