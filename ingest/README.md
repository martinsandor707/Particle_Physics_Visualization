# Drop folder for automatic ingest

Every CSV or Parquet file placed directly in this folder becomes an experiment
the next time the server starts, or when **Scan now** is pressed in the
**Admin Settings** panel. The container reads it through the repository's
read-only mount at `/app/host/ingest` (`CALOSRV_AUTO_INGEST_DIR` in
`docker-compose.yml`), so nothing here is ever modified or deleted.

- **Name.** The experiment is named after the file: `Production-20k (v2).parquet`
  becomes `production_20k_v2`, and a name starting with a digit gets `exp_` in
  front. Choose the file name to choose the experiment name.
- **Nothing is replaced.** A file whose experiment already exists, in any state,
  is skipped, and so is a file already ingested under another name (same file
  name and size). To replace an experiment, use the upload dialog and tick
  Replace.
- **Large files.** Hard-link rather than copy: `ln ../hits_all_models.csv
  production_hits_all_models.csv` costs no disk. A file modified in the last
  30 seconds is taken to be still copying and waits for the next scan.
- **Skipped.** Hidden files, temporary names (`.part`, `.tmp`, …), sub-folders
  and anything that is not `.csv` or `.parquet`. A file that fails the schema
  check is listed in the panel with the reason, and left alone.

The files themselves are ignored by git; only this note is tracked.
