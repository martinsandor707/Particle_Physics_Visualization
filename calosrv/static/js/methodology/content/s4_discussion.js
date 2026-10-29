/* §4 Discussion: the engineering and epistemic trade-offs behind the service.
 *
 * Content model and rules: index.js. Every number
 * the code defines comes from `C`; the measured figures are quoted with their
 * dataset and source (README "Performance", the design evaluations of October
 * 2026, the ingest checks' docstrings), never as findings of this article. */

import { C } from '../constants.js';

/* String.raw keeps TeX backslashes; this tag also turns an escaped backtick
 * back into a plain one, so a paragraph can carry TeX and code spans at once. */
const tx = (strings, ...values) => String.raw(strings, ...values).replace(/\\`/g, '`');

/** A count as the prose writes it: 100,000. */
const num = (value) => Number(value).toLocaleString('en-US');

/** The value step of one colour code on a log ramp of `decades` over `steps`, in per cent. */
const stepPercent = (decades, steps) => ((10 ** (decades / steps) - 1) * 100).toFixed(1);

/** The same step in decades. */
const stepDecades = (decades, steps) => (decades / steps).toFixed(4);

const KB = C.RESPONSE_LIMIT / 1000;
const RAMP_LEVELS = C.MAX_CODE - (C.BELOW_CODE + 1); // steps of a co-registered ramp, codes 2–255
const SIGNED_CODES = C.SPLIT_CODE - C.SIGNED_MIN_CODE; // codes per sign of the signed-log ramp
const SIGNED_STEPS = SIGNED_CODES - 1;

export default {
  id: 'sec-discussion',
  title: 'Discussion',
  blocks: [
    { kind: 'p', text: tx`The methods of [[sec-methods]] fix what each panel computes; this section discusses where it is computed and what that costs. Three choices shape every panel: the reduction runs in an embedded column store beside an immutable archive, never in the browser; every response obeys a size contract that decides how a raster is encoded; and a publication figure is the plot canvas alone, its disclosures read from the payload. A fourth matter is epistemic rather than technical: several views rest on simulation truth that a detector would not record.` },
  ],
  sections: [
    {
      id: 'sec-discussion-storage',
      title: 'Why DuckDB, not PostgreSQL',
      blocks: [
        { kind: 'p', text: tx`The production file holds 24,161,893 hit rows over 20,325 events in 99 columns (24 GB as CSV, CLAUDE.md §1.1); every panel is a sum over a selection of those rows. The service therefore stores them in DuckDB, an embedded columnar engine with vectorised, parallel execution [[cite:raasveldt2019]]. Two alternatives were weighed in the design evaluation (October 2026): PostgreSQL, the obvious server database, and ClickHouse. Both were rejected for this workload.` },
        { kind: 'p', text: tx`**One scan for two panels.** The two depth panels come out of one scan of the projection table, with \`GROUP BY GROUPING SETS ((iy, iz), (ix, iz))\` (\`calosrv/query/projections.py\`). DuckDB's hash aggregate keeps one hash table per grouping set and distributes each streamed tuple into all of them, so the table is read once for both panels and the selection is never materialised. PostgreSQL's planner declines partial aggregation whenever a query involves grouping sets [[cite:postgresql]], so the same statement would aggregate the 24 million rows, and the hundreds of millions of sub-deposit rows of a co-registered frame, on a single core; recovering parallelism would mean three scans or a larger result summed down in NumPy. The entrance slab is a second, plain-sum query: \`FILTER\` aggregates are evaluated in every grouping set, and the single-pass form measured 565 ms against 270 ms for the two plain scans on the production table (\`projections.py\` docstring).` },
        { kind: 'p', text: tx`**One memory ceiling.** DuckDB's \`memory_limit\` is a single, process-wide bound on its buffer manager, set once with the thread count (\`calosrv/db/settings.py\`, where every setting is GLOBAL), with spill files directed to the data volume and capped. PostgreSQL's \`work_mem\` applies per sort or hash operation, per worker and per session, multiplied for hashes by \`hash_mem_multiplier\` [[cite:postgresql]], so it gives no total cap. The bound has known edges, and the service is sized around them: results converted to NumPy, the Python heap and the bundle caches sit outside it [[cite:duckdbdocs]]. Measured in the design evaluation (October 2026), converting a 224 MB result to NumPy under a 100 MB limit raised the process from 103 MB to 887 MB while DuckDB reported 1.8 MB buffer-managed; the container therefore carries headroom above the ceiling, and no route returns hit-level rows. The ceiling and the thread count the service started with are shown in the header's compute badge on every page.` },
        { kind: 'p', text: tx`**Storage.** PostgreSQL stores rows uncompressed, with a per-row header and line pointer and every per-event constant repeated on each hit. Estimated from its page layout in the design evaluation (October 2026), it would hold the same data 4–6× larger, and the full 99-column table 9–16× larger; a row store also reads the full row width on every scan, so the hot projection table would have to stay cached in RAM to remain interactive.` },
        { kind: 'p', text: tx`**The archive.** The raw rows never enter the database. Ingest writes each validated input once as an immutable, ZSTD-compressed Parquet part (\`calosrv/db/archive.py\`: row groups of ${num(C.ARCHIVE_ROW_GROUP)} rows, level ${C.ARCHIVE_ZSTD_LEVEL}) [[cite:parquet]], [[cite:rfc8878]], listed in a manifest that readers take instead of a directory glob, and builds the narrow query tables from it. At level ${C.ARCHIVE_ZSTD_LEVEL} the 24 GB production CSV converts to 2.9 GB of Parquet (CLAUDE.md §1.1). The archive serves three purposes: other processes (a notebook, Polars, pyarrow) can read it while the server holds the database's single-writer lock; rebuilding a derived table re-reads a few Parquet columns instead of re-parsing 24 GB of text; and the 99-column rows stay out of the buffer pool the interactive queries share.` },
        { kind: 'p', text: tx`The evaluation names the limits of this choice too. DuckDB has no per-query memory limit or statement timeout, so concurrency is bounded in the application: the hit-level physics scans run one at a time behind a semaphore, and identical requests share one scan (\`calosrv/query/physics_cache.py\`). ClickHouse is the one alternative with per-query memory caps, at a migration and operations cost the evaluation judged unwarranted at one machine and a handful of users.` },
      ],
    },
    {
      id: 'sec-discussion-payload',
      title: 'The response-size contract',
      blocks: [
        { kind: 'p', text: tx`Every response is held under ${num(C.RESPONSE_LIMIT)} bytes, the ${KB} KB contract of CLAUDE.md §1.1 (\`RESPONSE_LIMIT\` in \`calosrv/query/density.py\`). The bound is on the JSON itself, measured as the route serialises it (\`wire_size\`); the transport additionally compresses it with GZip [[cite:rfc1952]], but a response that fits only after compression breaks the contract. The browser never receives a raw hit array: every route returns pre-aggregated rasters, histograms, fitted parameters and counts.` },
        { kind: 'p', text: tx`**The guard degrades deterministically and says so.** When a wide, flat window would push a fine raster over the limit, the co-registered frames' guard lowers the display resolution $R$ by a quarter per step in Continuous Field, or, in Native Grid, merges transverse bins pairwise and never depth layers; after rendering it measures the whole response and continues the same sequence if the envelope pushes it over (\`density.py\`, \`api/frame_canonical.py\`). Every other route shrinks through one measured guard that states each step in the body it produced (\`calosrv/api/budget.py\`). Nothing is withheld silently: a coarser picture arrives with the sentence that explains it, and no statistic changes. Measured over 900 views of the production experiment (4 frames × 3 models × 5 channels × two display modes at four resolutions, three selection sizes; README "Performance"), every view answered and the largest body was 99,722 B.` },
        { kind: 'p', text: tx`**Eight-bit codes.** A raster travels as one byte per bin ([[eq-quantise]], [[eq-signed-log]]). Code ${C.EMPTY_CODE} is reserved for a bin with no deposit, because an empty cell and the faintest measurable deposit are different statements and folding both into the bottom colour makes an unlit region look like a faint halo. In the co-registered frames, and on every energy-weighted CAM ramp, code ${C.BELOW_CODE} additionally means *populated, but below the display floor*: such a bin is drawn transparent and counted, and the ramp starts one code higher. On a log ramp spanning $n_{\mathrm d}$ decades in $L$ steps, one code is a fixed ratio in value,` },
        { kind: 'eq', id: 'eq-code-step', tex: String.raw`\Delta\ell = \frac{n_{\mathrm d}}{L}, \qquad \frac{\Delta\rho}{\rho} = 10^{\Delta\ell} - 1` },
        { kind: 'p', text: tx`which [[tab-payload]] evaluates for each encoding. Every step is finer than the roughly one hundred just-noticeable differences a continuous colour map resolves (\`calosrv/encode/quantize.py\`), so the image loses nothing visible; what it loses is the precision of a tooltip.` },
        {
          kind: 'table',
          id: 'tab-payload',
          caption: tx`The raster encodings of the spatial panels. Codes are bytes; $L$ is the number of steps between a ramp's two end codes, as in [[eq-code-step]], so a ramp has $L + 1$ codes. The step is in decades of value on a log ramp and in units of the quantity on a linear one.`,
          head: ['Encoding (where)', 'Codes', 'Steps $L$', 'Step per code', 'Travels exactly'],
          rows: [
            [
              tx`Density, $\log_{10}$, ${C.LAB_DECADES} decades below the brightest cell (Absolute frame)`,
              tx`${C.EMPTY_CODE} empty; ${C.MIN_CODE}–${C.MAX_CODE} ramp; cells below the floor folded into ${C.MIN_CODE} and counted`,
              `${C.LEVELS}`,
              tx`${stepDecades(C.LAB_DECADES, C.LEVELS)} decades, ${stepPercent(C.LAB_DECADES, C.LEVELS)}% in value`,
              tx`top ${C.TOPK} cells in GeV; panel total; scale ends; clipped and empty counts`,
            ],
            [
              tx`Density relative to $\rho_{\mathrm{ref}}$, $\log_{10}$, ${C.RAMP_DECADES} decades (co-registered frames)`,
              tx`${C.EMPTY_CODE} empty; ${C.BELOW_CODE} below the $10^{-${C.RAMP_DECADES}}$ floor; ${C.BELOW_CODE + 1}–${C.MAX_CODE} ramp`,
              `${RAMP_LEVELS}`,
              tx`${stepDecades(C.RAMP_DECADES, RAMP_LEVELS)} decades, ${stepPercent(C.RAMP_DECADES, RAMP_LEVELS)}% in value`,
              tx`top ${C.TOPK} drawn bins in GeV mm⁻² per event; $\rho_{\mathrm{ref}}$; in-window energy; below-floor count`,
            ],
            [
              tx`Energy-weighted Grad-CAM, $\log_{10}$, ${C.CAM_ENERGY_DECADES} decades below the stated peak (every frame)`,
              tx`${C.EMPTY_CODE} empty; ${C.BELOW_CODE} below the floor; ${C.BELOW_CODE + 1}–${C.MAX_CODE} ramp`,
              `${RAMP_LEVELS}`,
              tx`${stepDecades(C.CAM_ENERGY_DECADES, RAMP_LEVELS)} decades, ${stepPercent(C.CAM_ENERGY_DECADES, RAMP_LEVELS)}% in value`,
              tx`top ${C.TOPK} values of $\sum E\,\mathcal G$ in physical units; the peak; below-floor count`,
            ],
            [
              tx`Energy-weighted Shap-CAM, signed $\log_{10}$, ${C.CAM_ENERGY_DECADES} decades per sign`,
              tx`${C.EMPTY_CODE} empty; ${C.BELOW_CODE} below the floor; ${C.SIGNED_MIN_CODE}–${C.SPLIT_CODE - 1} negative (${C.SIGNED_MIN_CODE} = −1); ${C.SPLIT_CODE}–${C.MAX_CODE} positive (${C.MAX_CODE} = +1)`,
              `${SIGNED_STEPS} per sign (${SIGNED_CODES} codes)`,
              tx`${stepDecades(C.CAM_ENERGY_DECADES, SIGNED_STEPS)} decades, ${stepPercent(C.CAM_ENERGY_DECADES, SIGNED_STEPS)}% in value`,
              tx`top ${C.TOPK} signed values; the peak $|\text{value}|$; positive and negative totals`,
            ],
            [
              tx`Mean Grad-CAM, linear on $[0, 1]$`,
              tx`${C.EMPTY_CODE} empty; Absolute: ${C.MIN_CODE}–${C.MAX_CODE}; co-registered: ${C.BELOW_CODE + 1}–${C.MAX_CODE}, with ${C.BELOW_CODE} in Continuous Field where the reconstructed density is below the floor (Native Grid masks no bin)`,
              tx`${C.LEVELS} / ${RAMP_LEVELS}`,
              tx`${(1 / C.LEVELS).toFixed(4)} / ${(1 / RAMP_LEVELS).toFixed(4)} attention`,
              tx`top ${C.TOPK} values; out-of-range counts (zero by construction, reported)`,
            ],
            [
              tx`Mean Shap-CAM, linear on $[-1, +1]$`,
              tx`as mean Grad-CAM`,
              tx`${C.LEVELS} / ${RAMP_LEVELS}`,
              tx`${(2 / C.LEVELS).toFixed(4)} / ${(2 / RAMP_LEVELS).toFixed(4)} attribution`,
              tx`top ${C.TOPK} signed values; out-of-range counts`,
            ],
          ],
          note: tx`Sources: \`calosrv/encode/quantize.py\`, \`encode/scale.py\`, \`encode/matrix.py\`, \`encode/topk.py\`, \`query/panels.py\`, \`query/density.py\`. Where two values are given they are Absolute / co-registered. Exact values are rounded toward zero at ${C.TOPK_SIGNIFICANT} significant figures.`,
        },
        { kind: 'p', text: tx`**The exact values.** The cells a reader hovers over are the ones about to be written down, so each panel also ships its ${C.TOPK} brightest cells exactly (\`calosrv/encode/topk.py\`), at ${C.TOPK_SIGNIFICANT} significant figures: the precision of the float32 source columns, and twice what a tooltip prints (review decision R6; the values had travelled at 17 digits). They are rounded toward zero, never to nearest, so a shipped magnitude never exceeds the cell's own and the brightest value can never exceed the panel's peak. Together with dropping two redundant fields, this compaction saved 1.6–3.05 KB a response (README "API").` },
      ],
    },
    {
      id: 'sec-discussion-interaction',
      title: 'Server-side reduction and interactivity',
      blocks: [
        { kind: 'p', text: tx`A cold scan cannot be interactive: measured on the production file, the Absolute frame's cold scan takes 0.26–0.28 s and the D-frame's 1.7 s at $k = ${C.MIN_SUBSAMPLE}$ (README "Performance"). Three mechanisms recover an interactive feel without moving computation into the browser, which only draws the payload with Apache ECharts [[cite:li2018]] behind a FastAPI service [[cite:fastapi]]. First, slider input is debounced for ${C.DEBOUNCE_MS} ms and a superseded request is aborted, so one gesture issues one query and a stale response cannot repaint a newer selection (\`static/js/api.js\`). Second, the scan's result is cached at native resolution: the resolution, the display mode, the palette and the centroid weighting are downstream NumPy steps, so changing them costs 23–47 ms rather than another scan (\`calosrv/query/cache.py\`; README "Performance").` },
        { kind: 'p', text: tx`Third, while a slider is dragged on a table of at least ${num(C.SAMPLE_THRESHOLD_ROWS)} rows, the panels are drawn from a seeded ${C.SAMPLE_PERCENT}% Bernoulli sample of the projection table and replaced by the exact scan on release (\`calosrv/query/sampling.py\`). Each hit $h$ enters the sample independently with probability $f_{\mathrm s}$, $I_h \sim \text{Bernoulli}(f_{\mathrm s})$. Every plane the scan accumulates is a sum, so dividing the sampled sum in a cell $c$ by the known inclusion probability is an unbiased estimate of the full sum, with a relative error set by the hits in the cell:` },
        { kind: 'eq', id: 'eq-preview', tex: String.raw`\begin{aligned} \hat S_c &= \frac{1}{f_{\mathrm s}} \sum_{h \in c} I_h\, E_h, \qquad \operatorname{E}\big[\hat S_c\big] = \sum_{h \in c} E_h \\ \frac{\operatorname{SD}(\hat S_c)}{\operatorname{E}[\hat S_c]} &= \sqrt{\frac{1 - f_{\mathrm s}}{f_{\mathrm s}}}\; \frac{\big(\sum_{h \in c} E_h^2\big)^{1/2}}{\sum_{h \in c} E_h} = \sqrt{\frac{1 - f_{\mathrm s}}{f_{\mathrm s}\, n_{\mathrm{eff}}}}, \qquad n_{\mathrm{eff}} = \frac{\big(\sum_{h \in c} E_h\big)^2}{\sum_{h \in c} E_h^2} \le n_{\mathrm c} \end{aligned}` },
        { kind: 'p', text: tx`The preview is unbiased, and its relative error falls with the effective number of hits $n_{\mathrm{eff}}$ of the cell, which equals the hit count $n_{\mathrm c}$ only for equal hit energies; on these data, whose hit energies span many decades, it is far below the hit count. At $f_{\mathrm s} = ${C.SAMPLE_PERCENT / 100}$ the factor $(1 - f_{\mathrm s})/f_{\mathrm s}$ is ${(100 - C.SAMPLE_PERCENT) / C.SAMPLE_PERCENT}. The preview is a statistical estimate of the picture, not a crop of the data. Every sampled payload is marked \`exact: false\` and the header says so. Measured on the production file, the D-frame's drag preview takes 0.27 s against 1.7 s cold (README "Performance").` },
        { kind: 'links', id: 'lnk-discussion-xy', items: [
          { page: 'physics', panel: 'xy', label: 'Entry panel: drag a slider to see the sampled preview' },
        ] },
      ],
    },
    {
      id: 'sec-discussion-exports',
      title: 'Exported figures and their captions',
      blocks: [
        { kind: 'p', text: tx`A publication figure is the plot canvas only: the axes, the raster, the vector overlays and the colour-scale legend on white \`#FFFFFF\` in \`#111827\` ink, as SVG or as PNG at ${C.EXPORT_DPI} DPI, with no caption band, no reserved height and no disclosure footer (\`static/js/export/figure.js\`; CLAUDE.md §5). The disclosures that CLAUDE.md §2 makes mandatory — the clipping counts, the display window and the energy it leaves out, the density reference, the measured comb, the ensemble statistics behind a drawn axis — live in the panel's Details drawer, and the drawer is what an author carries into a manuscript caption.` },
        { kind: 'p', text: tx`The drawer's disclosures are read from the payload's structured fields, not from the prose on screen (\`static/js/export/disclosure.js\`). Screen prose is assembled for a card: a sentence may be shortened for a narrow layout and a number rounded for a tooltip, and a later edit to it would silently change what the panel discloses. Reading the numbers from the JSON means the caption states what was *computed*, not what happened to be rendered; and because the drawer reads the displayed bins from the payload rather than from the controls, a resolution lowered by the size guard is named as served (\`export/caption.js\`).` },
      ],
    },
    {
      id: 'sec-discussion-observables',
      title: 'What is observable, and what is simulation truth',
      blocks: [
        { kind: 'p', text: tx`The dashboard was built on simulated files, and several of its views use quantities a detector does not record. We state which, because a reader applying the method to detector data must know which pictures survive.` },
        { kind: 'list', ordered: false, items: [
          tx`**The Absolute (detector) frame** rasters need nothing but measured cells: positions, energies, and the networks' per-hit maps, whose inputs exist on detector data. This is why it is the built-in view (README "Admin Settings"). Its overlays are not all observable, however: the per-shower centroids $\mathbf c_j$ and the separation $D$ come from the producer's \`centroid_*\` columns, which split each event's hits between the showers by their simulated origin (\`particle_origin\`), and the direction overlays draw the true incident $(\theta, \varphi)$.`,
          tx`**The per-shower translated frame (legacy)** moves every hit by its shower's entry point $P_0$ ([[eq-p0-anchor]]). $P_0$ is itself measured, the energy-weighted centroid of the shower's first populated layer, but over that shower's truth-labelled hits.`,
          tx`**Local (shower-fixed)** additionally rotates each shower by $\mathbf R(\theta, \varphi)$ of its true incident direction, \`incoming_theta\` and \`incoming_phi\` ([[eq-local-rotation]]).`,
          tx`**The D-frame** back-projects each shower's centroid to the front face along the true direction ([[eq-backproject]]), so both its anchors and its rotation $\psi$ inherit the truth.`,
        ] },
        { kind: 'p', text: tx`On detector data, the shower assignment would come from the segmentation network and the direction from a reconstructed $(\hat\theta, \hat\varphi)$, such as the angle network's estimate or a fitted shower axis, each with an uncertainty of its own. That uncertainty would propagate into every co-registered view: the anchors would scatter by the projection of the angular error over the 253 mm median centroid depth behind the front face (measured on the production file; \`grid/frame.py\`), and the D-frame's ensemble axis, whose coherence licenses the averaged direction of CLAUDE.md §2, would be measured on reconstructed rather than true directions. The co-registered frames as built are therefore a study of shower structure under ideal alignment, an upper bound on what an aligned view can show; this is a limitation of the present work, not a property the method guarantees.` },
      ],
    },
    {
      id: 'sec-discussion-limitations',
      title: 'Limitations and threats to validity',
      blocks: [
        { kind: 'list', ordered: false, items: [
          tx`**Simulated data.** Every measured figure the article quotes, from the comb statistics to the payload sizes and latencies, comes from simulated files: the production \`hits_all_models\` file and the single-shower experiments. They describe that simulation and lattice, and must be re-measured before they are relied on for another detector, another generator or detector data.`,
          tx`**Provisional ranges.** Below $N = ${C.PROVISIONAL_N}$ co-registered events, a fitted display window is labelled provisional and falls back to a ${C.SHOWER_RADIUS_MIN_MM} mm floor, one shower's own extent; the low-N ladder of [[tab-low-n]] gates every number and mark. These are honest pictures of small samples, not estimates of the population, and the labels exist so they are not read as such.`,
          tx`**Independently normalised attention maps.** The networks' CAM maps arrive normalised per shower (angle and energy networks) or per event (segmentation) (README "Expected schema"). An ensemble CAM map therefore mixes independently normalised maps: it shows *where* a network attends, not how strongly one event's attention compares with another's, and every CAM caption says so ([[sec-attribution]]).`,
          tx`**Trust in the producer's centroids.** $D$ and the D-frame anchors are read from the producer's \`centroid_*\` columns rather than recomputed from the hits. Ingest checks what it can (\`calosrv/ingest/verify.py\`, \`frame_checks.py\`): an undefined separation must coincide exactly with an event that has no shower-A hit (57 events on the production file), and the two D-frame anchor definitions, the back-projected centroid and the back-projected $P_0$, are measured against each other on every ingest and reported, never judged (a median 46 mm and a p90 of 133 mm apart on the production file). $P_0$, by contrast, is verified against its definition: on the production file its largest residual over 40,650 showers is 0.05 µm. A producer whose centroids follow another definition would pass the first check and show up only in the second.`,
          tx`**Engine configuration.** The memory behaviour discussed in [[sec-discussion-storage]] was established on one host and one DuckDB release; the evaluation records a regression report in another 1.5.x release. The bound is a configuration, and a redeployment must re-check it.`,
        ] },
      ],
    },
  ],
};
