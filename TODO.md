# TODO — deferred views and the files that unlock them

calosrv draws only what the ingested data supports and never fabricates an inference output (CLAUDE.md §3, "Never fabricate unverified inference outputs"). The XGBoost analyses run in the service from the shipped models, which reproduce their notebooks' training split (§1). Every remaining entry is deferred because a file does not exist in this repository, or is a deliberate engineering change waiting for its own review. Each names the views it unlocks, the exact files and format, and what calosrv will check when they arrive.

The figures quoted were measured on the electron files on 2026-10-24 (data characterisation), on 2026-10-25 (the ingest runs of the three-schema release), and on 2026-10-27 (the drop-folder ingest of the current Parquet files and the XGBoost analyses, `data/dev/r8/`). Every ingest re-measures the ones that matter and writes them into the experiment's ingest report (`GET /api/experiments` → `ingest_report.verification`).

## Summary

| Deferred view or change | Page | Blocked by | § |
|---|---|---|---|
| B1–B3 and feature distributions by particle species, from hit-level data | / and /models | proton, pion, muon v3 hit files | 2 |
| Seed consistency, s1 against s2 (the s2 models are shipped, unpaired) | / and /models | s2 files | 3 |
| Fixed-energy class comparisons (1, 2, 5, 10, 20 GeV) | /models | ddsim proton files | 4 |
| C6 species voxels and C11 on two-shower events | /models | hits_all_models schema v2 | 5 |
| Engineering follow-ups (shared size guard, inspector splat k, D-frame cloud cap, φ-spread fixture) | — | nothing; review each | 8 |
| Follow-ups from the Page 2 review (estimator and fading consistency on Page 1, contracts generator, re-measurements) | both | nothing; review each | 9 |

The XGBoost views E1, E3, E4 and E5 and the XGBoost series of E2 and of the prediction density are live (§1). An aggregate experiment shows them once its species' s1 models are paired and analysed; until then the cards say why.

## 1. XGBoost: done in the service (2026-10-27)

- **What replaced the bundle.** The bundle format `calosrv-model-run` this section used to specify is no longer
  needed. The notebooks' regressors ship in `xgboost_models/` (one per species, task and seed). A background job
  per aggregate experiment reproduces every notebook view from them (`calosrv/modelruns/`):
  - the 80/20 hold-out predictions;
  - E1 by refitting the five folds;
  - E3's 2,000-row sample;
  - E4's depth-3 surrogate;
  - E5 from the booster.
  README "The XGBoost analysis" documents it.
- **The training split.** Each shipped model is checked against its split: the validation/training MSE at
  `random_state` 42 must clear the largest of 99 other seeds by a margin. Every s1 model passes on the current
  files; the least headroom is the muon momentum model's, 1.087 against 1.05.
- **The training data.** The old caveat that the notebooks trained on the v2 aggregates no longer applies. The
  shipped models take the v3 aggregate's 52 features, and their training split reproduces on the v3 files.
- **Still open from the old list:** the notebooks' xgboost and scikit-learn versions (§6.10). The service runs
  xgboost-cpu 3.2.0, and a refit on the reproduced 80% recreates the shipped electron model exactly.

## 2. Single-shower files for proton, pion and muon

- **Arrived 2026-10-27:** the four s1 aggregates (electron, muon, pion, proton; 59-column v3, ZSTD Parquet in
  `ingest/`). They drive the feature explorer and the XGBoost cards per species.
- **Still missing:** the hit-level files (21-column v3) of proton, pion and muon. The original list of both kinds:
  - `proton_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.csv` and `…_aggr_s1_v3.csv`;
  - the same two names for `pion_…` and `muon_…`.
- The notebooks reference proton and pion hit files on the team's storage (`data/simulations/regression-{proton,pion}/`):
  - proton: s1 54,740,548 hits, s2 54,822,842;
  - pion: s1 49,110,973, s2 48,965,087.
- Nothing references a muon hit file or any non-electron 59-column aggregate.
- About 55 M rows is 4.8 times the electron file, roughly 16 GB as CSV. Please export Parquet; calosrv ingests it directly. (On the development workstation, with a 10 GB DuckDB budget, the 11.4 M-row electron hit file ingests in 20 s with a 4.4 GB peak and the 24 M-row two-shower file in 73 s with a 6.5 GB peak.)
- Unlocks:
  - B1–B3 by species; the notebooks give the sampling fraction as proton 1.9999 % (1/SF 50.0026) and pion 2.4597 % (40.6558);
  - species comparisons of C4, C7, C8 and the Feature Explorer;
  - C6/C11 per species.

## 3. Second-seed (s2) files

`electron_standalone_N100000_M0_20GeV_reg_balanced_s2_v3.csv` and `…_aggr_s2_v3.csv`, and the s2 files of §2. They unlock s1-vs-s2 overlays of B2, C4, C7 and D4, and the two-seed layout of E1–E5. The s2 XGBoost models
already ship in `xgboost_models/`; the model scan lists them unpaired until an s2 aggregate is ingested. The four electron files become four experiments under the long-name rule: a stem longer than 48 characters keeps its first word and as many trailing words as fit, then a six-character digest (`electron_m0_20gev_reg_balanced_s1_v3_25e581`, `electron_m0_20gev_reg_balanced_aggr_s1_v3_82c5d8`, and their s2 twins).

## 4. Fixed-energy ddsim proton files (8-column)

- Files:
  - `ddsim_vertex0_1GeV_proton_N100000_M1GeV.edm4hep.v2.csv`
  - `ddsim_vertex0_2GeV_proton_N100000_M2GeV.edm4hep.v2.csv`
  - `ddsim_vertex0_5GeV_proton_N100000_M5GeV.edm4hep.csv`
  - `ddsim_vertex0_10GeV_proton_N100000_M10GeV.edm4hep.csv`
  - `ddsim_vertex0_20GeV_proton_N100000_M20GeV.edm4hep.csv`
- Columns: event_id, hit_index, x, y, z, hit_energy, contribution_time, contribution_energy. One row per contribution.
- Rows: 4,251,035 / 11,312,306 / 39,832,991 / 97,198,362 / 212,623,531. Events: 100,000 / 100,000 / 96,844 / 99,709 / 99,989.
- Needed only for discrete fixed-energy classes beyond `incoming_momentum_bin` slicing.
- A fourth input schema would be required:
  - contributions folded to cells (the notebook's drop_duplicates on event_id, x, y, z, hit_energy);
  - the contribution_time ≤ 100,000 cut;
  - the energy taken from the file name;
  - no incident angles.

## 5. Two-shower species columns (hits_all_models schema v2)

- Append per hit: `particle_type` (text), `is_secondary` (0/1), and optionally `parent_type`, `daughter_type` (';'-joined).
- Append per event, repeated per hit: `particle_type_A`, `particle_type_B`.
- calosrv would accept it as hits_all_models version 2 beside version 1.
- Unlocks C6 and C11 on two-shower events (today the species views are shut on two-shower data and say why) and per-particle comparisons.

## 6. Questions for the physics team

1. `High_energy_notebook_proton_pion-v5.ipynb` cites `High_energy_notebook_electron_muon.ipynb`, which is not in the repository.
2. The last column of the 59-column aggregate, `energy`, is 1{incoming_momentum ≥ 2 GeV}.
   - Counts: 0 in 9,795 events, 1 in 89,956 (re-measured at every ingest).
   - The largest p with 0 is 1.99831; the smallest p with 1 is 2.00002.
   - calosrv stores it as the class label `energy_class` and never calls it an energy. Please confirm, and consider renaming it in v4.
3. The v2 29-column aggregates and their gnn_logical_node, gnn_arith_node, gnn_msg_log_sum and gnn_msg_arith_sum columns are not supported; no definition exists in core.py. Supply definitions, or re-export as v3.
4. The v3 aggregates use raw z (first layer 3662.4 mm), while the notebooks' hit-level analyses subtract core.SHIFT_Z = 3649. calosrv keeps raw z everywhere and shows "z − 3649 mm" only as a labelled display row. Confirm raw z for v3, and state the v2 convention.
5. The eps = 1e-6 floors produce densities up to:
   - 2.07e9 absolute (83 events above 1e3);
   - 9.76e10 trans (256 events);
   - 6.59e4 local (69 events).
   Intended, or should a degenerate extent be NaN?
6. avg_phi* are arithmetic means of an azimuth, and angular_spread adds SD(φ). Most of the angular_spread tail above 0.5 rad is the ±π branch cut. calosrv shows them for parity, hatched, beside a circular mean and R̄; consider those in v4.
7. C11 for electrons: 73.83 % of events have no is_secondary = 0 row, rising from 64 % in bin 1 to 80 % in bin 18. The notebooks give 27.39 % for proton and 25.35 % for pion. What does is_secondary = 0 tag for electrons?
8. The aggregate omits the 249 single-hit events (193 in bin 0), so its bins hold 4,807–5,000 events. Intended?
9. Units: energy and momentum GeV, angles rad, positions mm. earliest_contribution_time runs 12.2–52,328.7 — ns?
10. The xgboost and scikit-learn versions of the published runs.

## 7. Engineering deferred with the data

- Species and seed layouts (§2, §3), the fixed-energy schema (§4), schema v2 (§5).
- Lab centroid stars, both kinds together (decided 2026-10-25 to keep them as they are for now). The
  energy-weighted centroid of the summed selection is a property of the drawn picture; the dataset-centroid star
  is the mean of the per-event centroids, an aggregate, and drawn without its dispersion or interval. Giving it an
  uncapped SD band and a Student-t interval (CLAUDE.md §2) changes the shared lab payload and the golden lab
  snapshot, so it is one deliberate change for two-shower and single-shower data at once.

## 8. Engineering follow-ups found while building (2026-10-25)

Not blocked by data; each is a deliberate change with its own review.

- **Route-local size guards.** Nine physics routes (correlations, distributions, energy, features, performance,
  prediction, profiles, response, statistics) each carry their own budget loop beside `api/budget.serve_measured`,
  which the two voxel routes use. Moving them onto it gives one owner for the measure-shrink-disclose rule; their
  over-budget sentences are pinned by tests, so each move must keep its wording or change it on purpose.
- **Event-inspector Local panels.** The 2-D Local rasters of the Event Inspector still splat each cell with k = 4,
  k_z = 2 (pinned by the two-shower golden). In 3-D the same k left 1.6–7.8% of the voxels empty against a k = 32
  reference, which is why the voxel cubes use k = 12. The 2-D comb statistic is measured on every response and
  found none on real data (R5), but the 2-D convergence has not been measured the same way.
- **The D-frame cloud at full selection.** At the 15,000-voxel cap the full production D-frame selection leaves
  15.5% of its energy beyond the cap (stated in the payload). A coarser D-frame voxel (60 mm) would draw more of
  it within the same bytes; whether that is the better picture is a display decision.
- **A fixture with azimuth spread.** Every test fixture clones two to four template showers, so none reaches the
  eight distinct azimuths from which Mardia's circular-linear R is quoted; the quoted path is tested on numpy
  samples and with a lowered floor. A fixture with a continuous φ would test it end to end.
- **The C9 block's `hits` count.** `negative_w.splits[].hits` is an integer count, not a hit array, but it is the
  one `hits` key in a 3-D body and the no-hit-array walker exempts it by name; renaming it (e.g. `n_hits`) would
  change the frozen statistics contract and its frontend reader together.

## 9. Follow-ups from the Page 2 review and fix round (2026-10-27)

Not blocked by data; each is a deliberate change with its own review.

- **One RMSE estimator on both pages.**
  - E2's momentum bins give the RMSE a χ² interval below N = 20 and a seeded bootstrap from N = 20
    (`stats/rmse.py`).
  - Page 1's metric cards and the Models residual card keep √ of the t interval of the MSE
    (`metrics.residual_summary`), whose lower end collapses to 0 at small N.
  - Moving them changes Page 1's performance golden.
- **Faded weak correlations on Page 1.** The Models page's feature correlations fade cells whose 95% interval
  contains 0. Page 1's correlation card (C8) shares the panel but keeps every cell at full strength; the option is
  one flag.
- **Seven views still one resolution step below September.**
  - On derived-v2 data: local/lab, about 200 events, energy-weighted Grad-CAM and Shap-CAM, R 300/400 (R6 v2).
  - The extra bytes are the Local frame's negative-depth disclosure (`frame.negative_w`, about 2.5 KB). It must
    stay; compacting its structure changes the statistics contract and its reader together.
- **Re-measure the latency.** R6 v2's p95 of 144 ms on `data/dev/single` was measured while browser tests ran
  beside it (69 ms on `data/dev/full`, and 66–78 ms before).
- **The contracts generator.** `data/dev/design/two-page/build_contracts.py` (git-ignored) predates the fix round,
  which edited `tests/contracts/*.json` directly. The checked-in contracts are authoritative: regenerate the
  generator from them, or retire it.
- **Flat 3-D boxes at a narrow card.** The 3-D plot's height has a 360 px floor, so a very flat box, such as the
  synthetic single-shower event 3 at a 1440 px window, keeps empty bands above and below it.
- **The per-shower translated depth raster** can extend half a layer past its window when its first layer's
  centre sits on the window edge, as the lab lattice already does. The axes clip it.
- **Deployment.** The production experiment stays on derived tables v1 until an operator rebuilds it
  (`python -m calosrv.ingest --rebuild -t <name>`). Until then the cards that need the new tables stay shut and say
  why.
