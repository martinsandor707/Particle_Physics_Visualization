# Drop folder for automatic ingest

Every CSV or Parquet file placed directly in this folder becomes an experiment
the next time the server starts, or when **Scan now** is pressed in the
**Admin Settings** panel. The container reads it through the repository's
read-only mount at `/app/host/ingest` (`CALOSRV_AUTO_INGEST_DIR` in
`docker-compose.yml`), so nothing here is ever modified or deleted.

- **Name.** The experiment is named after the file: `Production-20k (v2).parquet`
  becomes `production_20k_v2`, and a name starting with a digit gets `exp_` in
  front. Choose the file name to choose the experiment name.
- **Long names.** A name over 48 characters keeps its first word and as many of
  its last words as fit, around a six-character fingerprint of the whole name,
  so files that differ only at the end stay apart:
  `electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet`
  becomes `electron_m0_20gev_reg_balanced_aggr_s1_v3_82c5d8`, and
  `electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.parquet` becomes
  `electron_m0_20gev_reg_balanced_s1_v3_25e581`. A name of 48 characters or
  fewer is unchanged.
- **Schemas.** Three are recognised, from the file's content rather than its
  name: `hits_all_models` (99 columns, two showers per event), `standalone_hits`
  v3 (21 columns, one shower per event, one row per cell) and `standalone_events`
  v3 (59 columns, the producer's event-level aggregate). An aggregate becomes an
  experiment with no hits, no lattice and no frames: the Physics page shows its
  response and distribution cards and the Models page its analysis. A file of
  any other schema is listed with the reason and left alone.
- **The four s1 aggregates are ingested from here.** The electron, muon, pion
  and proton files `<species>_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet`
  (59 columns each, ZSTD-3 Parquet) are `standalone_events` files, ingested like
  any other and named by the rule above (`electron_…_82c5d8`, `muon_…_0df210`,
  `pion_…_3f0dfc`, `proton_…_12ed5c`). The electron file omits the 249 events with
  a single hit.
- **Parquet.** Every dataset in the repository is ZSTD-3 Parquet. CSV is still
  accepted, and its columns must then come in the schema's exact order; a Parquet
  file may carry them in any order.
- **Not in Git LFS.** The aggregates, and any file you add, are not stored in Git
  LFS or in git at all: the datasets are moving to a Hugging Face dataset, and
  until then you copy them in. The two `hits_all_models` files that the
  README's Quick start downloads are the exception today, tracked with Git LFS
  until that move.
- **Nothing is replaced.** A file whose experiment already exists, in any state,
  is skipped, and so is a file already ingested under another name (same file
  name and size). To replace an experiment, use the Upload dataset section of Admin
  Settings and tick Replace.
- **Large files.** Hard-link rather than copy: `ln ~/datasets/run_2026_10.parquet
  run_2026_10.parquet` costs no disk (the two paths must be on one filesystem).
  A file modified in the last
  30 seconds is taken to be still copying; the server scans again by itself
  once it has been unchanged that long.
- **Skipped.** Hidden files, temporary names (`.part`, `.tmp`, …), sub-folders
  and anything that is not `.csv` or `.parquet`. A file that fails the schema
  check is listed in the panel with the reason, and left alone.

The files themselves are ignored by git, apart from the two LFS-tracked ones
above; only this note is otherwise tracked.
