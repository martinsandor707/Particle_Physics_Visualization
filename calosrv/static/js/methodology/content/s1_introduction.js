/* §1 Introduction: the physical problem, the data, why naive pictures fail at
 * this scale, and the article's map. Content model and rules: index.js.
 *
 * Sources: calosrv/grid/lattice.py and db/ddl.py (the lattice), README
 * "Expected schema" and "Step 3" (the files), CLAUDE.md §1.1 (architecture B),
 * reference_ipynb_notebooks/02_notebook_visualizations_two_page_roadmap.md
 * (the detector's name). */

import { C } from '../constants.js';

const BT = '`';
/** A code span in the article's inline syntax. */
const code = (s) => `${BT}${s}${BT}`;
/** An integer with thousands separators. */
const grouped = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

export default {
  id: 'sec-introduction',
  title: 'Introduction',
  blocks: [
    { kind: 'p', text: String.raw`A sampling calorimeter measures a particle's energy by letting it shower in dense absorber and sampling the shower's deposit in thin active layers; the visible signal is a fraction of the deposited energy, and the fraction depends on the particle species and on how the shower develops [[cite:wigmans2017]] [[cite:fabjan2003]]. When two particles enter close together, their showers overlap, and a cell's deposit can no longer be assigned to either by inspection. Reconstructing such *superimposed* showers, recovering each one's energy, its separation from the other and its incident direction, is the task of the neural networks whose behaviour this article's dashboard exists to diagnose.` },
    { kind: 'p', text: String.raw`The data are simulated showers in a calorimeter that the reference notebooks' roadmap names as the LFHCal. The simulated lattice, as the service measures it at ingest (${code('grid/lattice.py')}, ${code('db/ddl.py')}), has ${C.X_CELLS} × ${C.Y_CELLS} × ${C.N_LAYERS} cells: ${C.N_LAYERS} sampling layers at an exactly uniform ${C.Z_PITCH_MM} mm pitch, the first at $z = ${C.FIRST_LAYER_Z_MM}\,\mathrm{mm}$, and transverse cells of a ${C.CELL_X_MM} × ${C.CELL_Y_MM} mm footprint. The transverse lattice is not regular. Its ${C.X_CELLS} distinct $x$ positions come in tight pairs 4.4 mm apart, with the pitch between pair groups alternating 43.87 and 48.27 mm; the $y$ gaps alternate 48.60 and 52.40 mm; and the rows come in blocks offset by 4.4 mm, so adjacent $x$ columns intersect different subsets of the $y$ cells. A bin index on this detector is therefore an ordinal, never a pitch multiple, and the transverse plane is staggered ([[sec-discretisation]]).` },
    { kind: 'p', text: String.raw`The service ingests three schemas (README "Expected schema"): ${code('hits_all_models')} v1, two showers per event, one row per hit, with three coordinate frames, three networks' predictions and their per-hit Grad-CAM and Shap-CAM maps, 99 columns; ${code('standalone_hits')} v3, one shower per event, one row per cell, 21 columns; and ${code('standalone_events')} v3, the 59-column event-level aggregate of the producer's feature code. The production two-shower file holds 24,161,893 hit rows in 20,325 events; as CSV it was 24 GB, and it is now kept as a 2.9 GB ZSTD-compressed Parquet archive [[cite:parquet]] [[cite:rfc8878]]. The single-shower samples, of the electron (100,000 events in 11,436,422 cell rows), muon, pion and proton, lie on the same lattice. Nothing at this scale can be shipped to a browser, so every spatial transformation, binning and statistical reduction runs on the server, in FastAPI [[cite:fastapi]] over DuckDB [[cite:raasveldt2019]], and the browser, which draws with a vendored copy of Apache ECharts [[cite:li2018]], receives only pre-aggregated payloads under ${grouped(C.RESPONSE_LIMIT)} bytes, never a hit.` },
    { kind: 'p', text: String.raw`Aggregation alone does not make a picture honest. Each of the obvious ways to draw these data fails in a specific, measurable way, and each failure is answered by a rule stated in this article:` },
    { kind: 'list', ordered: false, items: [
      String.raw`**Raw hit scatter.** Twenty-four million points saturate any canvas and cannot be sent; the service aggregates on the server into binned surface densities ([[eq-density]]) and holds every response to the payload contract ([[tab-payload]]).`,
      String.raw`**Uncalibrated deposits.** A sampling calorimeter's visible energy is a fraction of the true one, so deposits of different showers are compared only after a calibration constant per shower, [[eq-calibration]] in [[sec-statistics]] [[cite:wigmans2017]].`,
      String.raw`**Rainbow and Jet colour maps.** Their non-monotonic lightness invents boundaries and hides gradients [[cite:borland2007]] [[cite:crameri2020]]; the dashboard uses perceptually ordered ramps, each measured for contrast against the card it is drawn on ([[sec-colour]]).`,
      String.raw`**Arithmetic means of an azimuth.** The incident azimuth wraps, and over the production file its mean resultant length is $\bar R = 0.012$; its linear mean points nowhere. Directions are summarised by circular statistics ([[eq-resultant]]) and averaged only where a measurement shows them coherent.`,
      String.raw`**Average trajectories in detector coordinates.** For the same reason no averaged trajectory is drawn over the whole detector face; directions are averaged only after a rigid co-registration that makes them coherent, or within a window where they are measured to be ([[sec-frames]]).`,
      String.raw`**Lattice combs.** Point-binning a staggered, irregular lattice leaves a periodic comb of empty or alternating bins that reads as shower structure; the service splats each cell over its footprint and measures the comb on every response ([[sec-discretisation]]).`,
      String.raw`**Curves fitted to a handful of events.** A smooth density drawn through five values asserts a shape the sample cannot constrain; numbers and marks are gated separately by sample size ([[tab-low-n]]).`,
    ] },
    { kind: 'p', text: String.raw`These are not new principles. Data ink should carry data [[cite:tufte2001]], colour should follow perception [[cite:borland2007]] [[cite:crameri2020]], and an estimate should travel with its uncertainty. What is specific here is that each principle had to be turned into an operator that runs on twenty-four million rows in seconds, and into a gate whose threshold is a constant of the code. The rest of this article states those operators and gates.` },
    { kind: 'p', text: String.raw`Our contribution is the methodology itself, written down as the code implements it. §2 states the methods: the reference frames and the SE(3) co-registration ([[sec-frames]]), the spatial discretisation and the conservative display kernels ([[sec-discretisation]]), the attribution channels of the networks ([[sec-attribution]]) and the statistical estimators and their sample-size gates ([[sec-statistics]]). §3 is an audit, not a report of findings: it walks through every encoding of the Physics and Models pages and checks it against the rule it implements ([[sec-results]]). §4 discusses the trade-offs these rules force ([[sec-discussion]]), and §5 concludes. Every constant the prose quotes is read from the code and listed with its source in [[app-constants]]; every measured figure is cited with the file it was measured on, and is evidence for a design decision, not a result of this article.` },
  ],
};
