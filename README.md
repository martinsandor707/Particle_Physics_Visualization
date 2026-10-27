# Particle Physics Visualization

Diagnostic tooling for calorimeter shower reconstruction on overlapping two-particle
events. The repository holds two complementary architectures; pick one by dataset size.

| | **`calosrv/`** — out-of-core server | **`calodash/`** — batch compiler |
|---|---|---|
| Deliverable | Dockerised FastAPI + DuckDB service | one standalone `.html` file |
| Dataset size | unbounded (tested at 24 GB / 24.2 M rows × 99 columns) | fits in browser memory |
| Aggregation | server-side in DuckDB | at build time, in pandas |
| Frontend | Apache ECharts, vendored | Plotly, embedded |
| Entry point | `docker compose up --build` | `uv run build_dashboard.py` |

Both honour the same scientific-integrity rules — see [CLAUDE.md](CLAUDE.md).

---

## Quick start

This section is for physicists who want to run the dashboard on their own
computer and have not used Git or Docker before. You need one account, three
programs and six commands. After that the dashboard runs in your web browser.

### What you need

**A GitLab account with access to the data.** The code is public on GitHub, but
its two data files are stored on the University of Debrecen GitLab server,
<https://gitlab.inf.unideb.hu>, in the project `lr/epic`. Downloading them
needs an account there with access to that project. Ask the project
maintainers for access if you do not have it.

When Git downloads the data it asks for a password, and that password must be
a GitLab access token, not your usual password. To create one:

1. Sign in at <https://gitlab.inf.unideb.hu>.
2. Select your avatar, then **Edit profile** (on older GitLab versions,
   **Preferences**), then **Access tokens**.
3. Add a new token: give it any name, tick the **read_repository** scope and
   create it.
4. Copy the token straight away. GitLab shows it only once.

**Three programs.** Install them, then open a new terminal window so that it
finds them.

| Program | Used for | Download |
|---|---|---|
| Git | downloading the code | <https://git-scm.com/downloads> |
| Git LFS | downloading the two large data files | <https://git-lfs.com>, already included in Git for Windows |
| Docker Desktop on Windows and macOS, or Docker Engine with the Compose plugin on Linux | running the dashboard | <https://docs.docker.com/get-started/get-docker/> |

**Room on your computer.** About 12 GB of free disk space: the download takes
5.5 GB, because Git keeps a second copy of each data file, and the loaded
database another 5.2 GB. Docker must also be allowed at least 8 GB of memory:

- **Windows:** Docker Desktop may use half of the computer's memory by default,
  so a computer with 16 GB is enough.
- **macOS:** in Docker Desktop, open **Settings → Resources** and set the
  memory limit to at least 8 GB.
- **Linux:** Docker may use all of the computer's memory.

### Step 1: download the code and the data

Open a terminal: **PowerShell** on Windows, **Terminal** on macOS and Linux.
Every command below is typed the same way on all three systems. A new terminal
starts in your home folder, which is a good place for the project. Run the
commands one at a time and press Enter after each:

```
git lfs install
git -c filter.lfs.smudge= -c filter.lfs.process= -c filter.lfs.required=false clone https://github.com/martinsandor707/Particle_Physics_Visualization.git
cd Particle_Physics_Visualization
git lfs pull
```

1. `git lfs install` switches Git LFS on for your user account. It is needed
   once per computer.
2. The `clone` command downloads the code into a new folder named
   `Particle_Physics_Visualization`. Its three `-c` settings tell Git to leave
   the two large data files for the next step, so that a mistyped password
   cannot leave a broken copy behind.
3. `cd Particle_Physics_Visualization` moves into that folder. Run every later
   command from inside it.
4. `git lfs pull` downloads the two data files, 2.9 GB in all, into the folder
   `ingest`. Git asks for a username and a password for `gitlab.inf.unideb.hu`.
   Enter your GitLab username, then paste the access token as the password.
   Nothing appears on screen while you paste a password, so just press Enter
   afterwards. On Windows a sign-in window may open instead, asking for the
   same two things.

Then check that both files arrived:

```
git lfs ls-files
```

Each line must show an asterisk `*` between the code and the file name:

```
8712280518 * ingest/hits_all_models.parquet
d88d42cc5b * ingest/hits_all_models_dummy.parquet
```

A dash `-` in place of the asterisk means that file was not downloaded. Run
`git lfs pull` again; it is safe to repeat as often as needed.

### Step 2: start the dashboard

On Windows and macOS, start Docker Desktop first and wait until it says that it
is running. Then, in the same terminal:

```
docker compose --env-file laptop.env up --build
```

When the terminal shows `Uvicorn running on http://0.0.0.0:8000`, open
<http://localhost:8000> in your web browser. Leave the terminal open while you
use the dashboard, because it runs for as long as that command does. Press
Ctrl+C in the terminal to stop it.

The file `laptop.env` sets how much memory the dashboard may use, sized for a
computer that can give Docker 8 GB:

```
DUCKDB_MEMORY_GB=4
CONTAINER_MEMORY_LIMIT=7g
```

If Docker may use 24 GB or more, you can leave out `--env-file laptop.env`. The
dashboard then gives its database 16 GB and loads the data faster. Whichever you
choose, use the same command every time you start it.

### Step 3: wait for the first data load

The first start takes a few minutes, and the page opens before it has finished.

1. Docker builds the dashboard. This happens once, and again after an update;
   it takes about a minute on a fast connection, longer on a slow one.
2. The dashboard loads a built-in demonstration dataset of two events within
   seconds, and the page opens on it.
3. It then loads the files in the `ingest` folder, one after the other:
   `hits_all_models.parquet`, the full dataset of 20,325 events, and
   `hits_all_models_dummy.parquet`, the same two demonstration events.

Until the full dataset is ready, a banner at the top of the page says that the
default experiment `'hits_all_models'` is queued or ingesting, and the
**Experiment** menu at the top lists it greyed out. When the terminal prints

```
Verification for 'hits_all_models': PASSED
```

reload the page and choose `hits_all_models — 20,325 events` in the
**Experiment** menu. From then on, opening <http://localhost:8000> starts on it.
On a desktop computer with `laptop.env`, the full dataset was ready 94 s after
the start, and the dashboard used at most 4.6 GB of memory while loading it.
Allow a few minutes on a laptop.

The loaded data is kept in the project's `data` folder, so later starts take a
few seconds and load nothing again. The files in `ingest` are never changed.
After each start, the first view of each reference frame can take several
seconds while it is computed; later views are fast.

### Every day

Run these in the project folder.

- **Start the dashboard:** `docker compose --env-file laptop.env up`
- **Stop it:** press Ctrl+C in its terminal, or run `docker compose down` in
  another terminal.
- **Update to the newest version**, with the same three settings as the clone
  so that a failed data download cannot leave a half-updated copy:

  ```
  git -c filter.lfs.smudge= -c filter.lfs.process= -c filter.lfs.required=false pull
  git lfs pull
  docker compose --env-file laptop.env up --build
  ```

### If something goes wrong

| What you see | What to do |
|---|---|
| `git: 'lfs' is not a git command` | Git LFS is not installed. Install it, open a new terminal, and start again from `git lfs install`. |
| `git lfs pull` reports `Authentication required`, `Access denied` or `credentials … not found` | The username or the token is wrong, the token lacks the **read_repository** scope, or your account has no access to `lr/epic`. Fix that, then run `git lfs pull` again. |
| `Cannot connect to the Docker daemon`, `error during connect`, or `docker` is not found | Docker is not running or not installed. Start Docker Desktop and wait until it is running. On Linux, if you see `permission denied`, put `sudo` in front of the `docker` command. |
| `port is already allocated` | Another program already uses port 8000, possibly an earlier copy of the dashboard. Run `docker compose down`, or close the other program, then start again. |
| Several minutes after the start, the **Experiment** menu still has no `hits_all_models`, even after a reload | The full dataset was not loaded. Open **Admin Settings** at the top right and look under **Automatic ingest**: the line for `hits_all_models.parquet` gives the reason. *Is a Git LFS pointer* means the file was never downloaded: stop the dashboard, run `git lfs pull`, and start it again. |
| The **Experiment** menu shows `hits_all_models — failed`, and a banner gives the reason; the terminal may also have shown `exited with code 137` | Loading usually fails because it ran out of memory. Give Docker more memory, or start with `--env-file laptop.env`, then load the dataset again: in **Admin Settings → Upload dataset**, choose **Already on the server**, pick `ingest/hits_all_models.parquet`, enter `hits_all_models` as the experiment name, tick **Replace the existing experiment**, and select **Upload & Ingest**. |

The rest of this README is for developers and operators: configuration, data
loading, the interface in detail, the API and the code layout. With the data
already in place, `docker compose up --build` on its own does everything above
with the default memory settings.

---

## Configuration

Set in `docker-compose.yml`. The two memory values are read from the
environment, so they change without editing the file: from an env file
(`docker compose --env-file laptop.env up`, as the [Quick start](#quick-start)
does) or from the shell.

| Variable | Default | Meaning |
|---|---|---|
| `DUCKDB_MEMORY_GB` | `16` | Integer memory ceiling for DuckDB. `laptop.env` sets `4`; the production server sets `100`. |
| `CONTAINER_MEMORY_LIMIT` | `20g` | Compose only: the container's `mem_limit` and `memswap_limit`, kept at least 3 GB above `DUCKDB_MEMORY_GB` (a test holds every profile to that). `laptop.env` sets `7g`. |
| `PORT` | `8000` | HTTP listen port. |
| `CALOSRV_DATA_DIR` | `/app/data` | Database, upload staging and DuckDB temp spill. |
| `CALOSRV_SEED_CSV` | — | Override the baseline seed file. The seed is Parquet now (`hits_all_models_dummy.parquet`), and the variable takes a CSV or a Parquet file, as every ingest does; the name is kept for existing deployments. Unset, the first of `/app/seed/hits_all_models_dummy.parquet`, `<data dir>/hits_all_models_dummy.parquet` and the repository root's copy that exists. |
| `CALOSRV_DB_PATH` | `<data dir>/calorimeter.duckdb` | The DuckDB database file. |
| `CALOSRV_HOST` | `0.0.0.0` | HTTP listen address. |
| `CALOSRV_CORS_ORIGINS` | unset | Comma-separated origins allowed to call the API from another site. Unset, no cross-origin middleware is installed. |
| `CALOSRV_DEBOUNCE_MS` | `150` | The debounce the server advertises to the frontend (`compute.debounce_ms` in `GET /api/experiments`). |
| `CALOSRV_SERVER_URL` | `http://127.0.0.1:<PORT>` | Where `python -m calosrv.ingest` looks for a running server to delegate to. |
| `CALOSRV_LOCAL_INGEST_DIR` | `/app/host` | The one root that server-side ingest (**Already on the server**, `POST /api/ingest-local`) may read. Empty, or a directory that does not exist, turns it off. |
| `CALOSRV_MODEL_DIR` | `xgboost_models/` beside `calosrv` when it exists (or when the container's mount does not); otherwise `/app/host/xgboost_models`, where compose mounts the repository read-only | The folder scanned for shipped XGBoost models (see [The XGBoost analysis](#the-xgboost-analysis)). One directory per species, `xgboost_<species>/` (lowercase letters and digits, starting with a letter), holding `standalone_<task>_s<seed>_model.json` with `<task>` `momentum` or `angle` and `<seed>` an integer. Any other `.json` in a species directory, a symbolic link, a file over 256 MB, or a file that is not an XGBoost `reg:squarederror` gbtree model with named features (one target for momentum, two for angle) is listed in Admin Settings with its reason and left out. A folder that does not exist is reported there and is not fatal. |
| `CALOSRV_CACHE_ENTRIES` | `128` | Native-resolution matrix bundles held in the LRU. |
| `CALOSRV_CANONICAL_CACHE_ENTRIES` | `32` | Entries of each co-registered bundle LRU (canonical, translated, local) and of the ensemble voxel-cloud LRU. |
| `CALOSRV_AUTO_INGEST_DIR` | unset (off) | The [drop folder](#drop-folder-automatic-ingest) scanned at every start. Compose: `/app/host/ingest`, the repository's `./ingest`, read-only. |
| `CALOSRV_AUTO_INGEST_SETTLE_S` | `30` | A dropped file modified more recently is taken to be still copying; the scan runs again by itself one second after the window closes. |
| `CALOSRV_CONFIG_PATH` | `<data dir>/config.json` | Where the [Admin Settings](#admin-settings-the-default-view) panel saves the default view. |
| `CALOSRV_DEFAULT_DATASET`, `…_COORD_SYSTEM`, `…_MODEL`, `…_CHANNEL`, `…_DISPLAY_MODE`, `…_RHO_NORM` | unset | The default view's environment layer, beneath what the panel saves. Compose sets `CALOSRV_DEFAULT_DATASET=hits_all_models`, the experiment the drop folder creates from the tracked `ingest/hits_all_models.parquet`. An invalid value is ignored with a warning. |
| `CALOSRV_ALLOW_RAM_STORAGE` | unset | `1` lets the database, temp and archive directories sit on tmpfs/ramfs/zram. The test suite sets it for its throw-away databases; nothing else should. |
| `TMPDIR` | `/app/data/staging` | Where Starlette spools uploads before they are staged; kept on the data volume, never in a tmpfs `/tmp`. |

> **Give the container more memory than DuckDB's ceiling, and no more swap.**
> `DUCKDB_MEMORY_GB` bounds DuckDB's buffer manager only — not the Python heap,
> the NumPy result conversion, or the bundle caches. The caches are budgeted in
> bytes (lab and canonical 256 MB each, translated, local and voxel 128 MB
> each, the hit-level physics scans 64 MB, `query/cache.py`; the physics and
> voxel caches add no variable of their own), and `docker-compose.yml` sets
> `mem_limit` to `CONTAINER_MEMORY_LIMIT` (20 GB) against the 16 GB ceiling. It
> sets `memswap_limit` to the same value, so the container gets no swap on top:
> on a host whose swap is zram, that swap is
> compressed RAM. Measured outside a memory cgroup, streaming the 24 GB CSV
> through the page cache pushed 6.2 GB of *other* processes' pages into zram;
> inside a 14 GB cgroup with no swap the same ingest peaked at 5.9 GB RSS with
> no swap at all.

Threads are derived, not configured: `min(32, max(2, cores // 2 if mem >= 64 else cores - 1))`,
and never more than the memory ceiling in GB, because every thread holds its
own CSV buffers, row-group write buffers and aggregate partitions. A large
memory ceiling implies a shared production host, so only half the cores are
claimed.

**Start-up refuses RAM-backed storage.** The database file, DuckDB's
`temp_directory` and the Parquet archive must sit on a disk: `db/storage_guard.py`
reads `/proc/self/mountinfo` and refuses tmpfs, ramfs and zram, because a
spill into a tmpfs `/tmp` is what once exhausted the 31 GB development machine.
Every session also sets `preserve_insertion_order = false` and
`allocator_background_threads = true`, and `duckdb` is pinned to 1.5.5.

---

## Loading data

Every dataset in the repository is a ZSTD-3 Parquet file. CSV is still accepted
everywhere a file is: the format is read from the content, and the ingest
archives either as Parquet. **Three input schemas** are recognised, one per
kind of experiment: `hits_all_models` (two showers per event, 99 columns),
`standalone_hits` v3 (one shower per event, one row per cell, 21 columns) and
`standalone_events` v3 (the producer's event-level aggregate, 59 columns, no
hits). [Expected schema](#expected-schema) lists them, and the
[kind table](#what-each-kind-serves) says what each one can show.

### Large files already on the server (preferred)

```bash
docker compose exec calorimeter-dashboard \
    python -m calosrv.ingest --input /app/host/ingest/hits_all_models.parquet --table all_models
```

The repository is mounted read-only at `/app/host`, so a multi-gigabyte file is
read in place and never traverses HTTP. Measured on the 24 GB / 24,161,893-row
production **CSV** with `DUCKDB_MEMORY_GB=10` inside a 14 GB cgroup, by the
pipeline of that time: **61 s**, peak RSS 5.9 GB (DuckDB's own buffers 2.8 GB,
nothing spilled), producing a 2.5 GB database beside a 2.7 GB Parquet archive.
Stage times: archive 17 s, projection table 5 s, event table 17 s, preview
sample 5 s, verification 16 s.

Measured on the same data as the 2.87 GB **Parquet** file
(`ingest/hits_all_models.parquet`), with the current pipeline, under the same
`DUCKDB_MEMORY_GB=10` and 14 GB cgroup (10 threads; `data/dev/single/r3_production.log`,
2026-10-25): **73.0 s**, peak RSS 6.3 GiB (6,451 MiB), nothing spilled,
verification passed. The two are not like for like: this pipeline also builds
the Group-1 event columns and the `layers_` and `profiles_` tables (see
[Storage](#storage-duckdb-tables-and-the-parquet-archive)). Stage times: archive
8.3 s, projection table 5.7 s, event table with Group-1 32.5 s, layers 0.6 s,
profiles 17.7 s (1.74 × 10⁹ sub-deposits), preview sample 4.6 s, verification
3.5 s. The single-shower electron hit file (3.33 GB CSV, 11,436,422 rows,
100,000 events) measured **19.9 s** with a peak RSS of 4,374 MiB in the same
setting, 8.2 s of it the profiles (`data/dev/single/r2_hits.log`).

```
--input / -i        path to the CSV or Parquet file (not with --rebuild)
--table / -t        experiment name (lowercase letters, digits, underscores)
--mode / -m         create_new (default) | append
--force-reingest    with create_new, replace an existing experiment of this name
--display-name      label shown in the experiment dropdown
--event-offset      shift incoming event numbers when appending
--no-sample         skip the 10% preview-sample table
--rebuild           rebuild the derived tables from the experiment's Parquet archive,
                    without re-reading the source file (see Rebuilding derived tables)
--compare-features HITS EVENTS
                    check a single-shower hit experiment's features against an
                    aggregated experiment's (see Comparing features with the aggregate)
--direct            always open the database directly (see below)
--server-url        base URL of a running server
```

> **How this reaches the database.** DuckDB holds its lock on the database file
> *across processes*, not merely within one, so a second process cannot open it
> while the server is running — the attempt fails immediately rather than
> waiting its turn. The command therefore detects a running server and **posts
> the path** to `POST /api/ingest-local`, letting the server process (which
> already owns the lock) do the work on the same background worker an upload
> uses, while following the job to completion. Only the path crosses HTTP; the
> file is still read in place. With no server running it opens the database
> itself. `--direct` forces the second mode and fails loudly if the database is
> locked.

The same route is available from the interface: the **Source** selector of the
**Upload dataset** form in [Admin Settings](#admin-settings-the-default-view)
offers "Already on the server", which lists the CSV and Parquet files
under the mounted root. Paths are confined to that one directory — every request is resolved
(following symlinks, collapsing `..`) and rejected if it lands outside — so the
endpoint cannot be used to read arbitrary server files.

### Drop folder (automatic ingest)

Put a CSV or Parquet file in `./ingest/` and it becomes an experiment the next
time the server starts, or at once with **Scan now** in the
[Admin Settings](#admin-settings-the-default-view) panel. The container reads
the folder through the read-only repository mount
(`CALOSRV_AUTO_INGEST_DIR=/app/host/ingest`), so a dropped file is never
modified or deleted, and the folder stays yours on the host.

```bash
ln ~/datasets/run_2026_10.parquet ingest/run_2026_10.parquet   # a hard link costs no disk (same filesystem only)
```

- **The file name is the experiment name**: lower-cased, every other run of
  characters one underscore, `exp_` before a leading digit, at most 48
  characters. `Production-20k (v2).parquet` becomes `production_20k_v2`. A name
  the rules refuse (a reserved word, the `_s10` suffix) is reported, not bent.
- **A long name is shortened, not cut.** A stem that makes a name over 48
  characters keeps its first word and as many of its trailing words as fit,
  then a six-hex-digit blake2b fingerprint of the whole name. Simulation files
  differ at the end of long names (`…_s1_v3` against `…_aggr_s1_v3`), so a
  plain cut would make them one experiment. Generated by
  `calosrv.db.naming.derive_experiment_name`:
  `electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet`
  becomes `electron_m0_20gev_reg_balanced_aggr_s1_v3_82c5d8`, and
  `electron_standalone_N100000_M0_20GeV_reg_balanced_s1_v3.parquet` becomes
  `electron_m0_20gev_reg_balanced_s1_v3_25e581`. A name of 48 characters or
  fewer is unchanged, and the result still has to pass the rules above.
- **Any of the three schemas.** The schema is recognised from the file's
  content; the experiment's kind follows from it. A file of none is reported
  with the reason (see [Through the browser](#through-the-browser)).
- **Idempotent.** A file is skipped when its experiment already exists in any
  form, whether a registry row in any status, a table or an archive. That is
  logged as `Table '<name>' already exists in database catalog. Skipping
  automatic ingestion.`. A file is also skipped when:
  - a job for that name is already queued;
  - the same file (name and size) is already archived as another experiment;
  - a second file claims the same name.

  Nothing is ever replaced: that is the upload form's **Replace** in Admin
  Settings.
- **Reported, not failed.** A file that fails its schema check is listed in the
  panel with the reason and left alone, instead of adding a failed experiment
  at every boot. A file modified within the settle window is taken to be still
  copying, and the scan runs again by itself one second after the window
  closes (`autoingest.SettleWatch`), so a dataset that `git lfs pull` wrote
  moments before the start is still loaded at that start. A Git LFS pointer, a
  tracked dataset that was never downloaded, is named as such, with the
  command that downloads it.
- **Never in the way.** The scan only decides and queues. The ingests run one
  at a time on the worker an upload uses, so the server answers at once. An
  ingest that crashes leaves a failed registry row, which the next boot treats
  as existing, so a bad file cannot loop a restarting container.

Only the folder's top level is scanned. Hidden files, temporary names (`.part`,
`.tmp`, …) and anything that is not `.csv` or `.parquet` are passed over.
`ingest/README.md` repeats these rules beside the files.

**The whole folder, measured.** The six files of the repository's `ingest/`
folder (the production Parquet file, the four 100,000-event aggregates and the
1000-row dummy, 3.05 GB together) were linked into a drop folder and ingested by
one start of the service on an empty data directory, with `DUCKDB_MEMORY_GB=10`
and 10 threads (the log's `memory_limit=9.3 GiB threads=10`), at commit `c6e54b1`
(`data/dev/r8/r8.json`, driver `data/dev/tools/measure_r8_drop.py`). Nothing
failed.

| Experiment | Hits | Events | Ready after boot |
|---|---|---|---|
| `experiment_baseline` (the seed) and the electron aggregate | 1,000 and none | 2 and 99,751 | 5.4 s |
| `hits_all_models` (production) | 24,161,893 | 20,325 | 80.6 s |
| muon, pion and proton aggregates | none | 99,417, 99,687 and 99,089 | 85.6 s |

The wait ended 95.7 s after the boot, once three polls five seconds apart found
nothing pending. The four model analyses (see [The XGBoost
analysis](#the-xgboost-analysis)) were queued as each aggregate became ready and
all four were done 21.2 s after that wait. The process peaked at 7,413 MiB, and the
data directory (every file under it: the database, the Parquet archive, the staging
and spill folders) holds 5,970,208,451 bytes. The catalogue measured 48,380 B with the six
experiments. The scan asked again answered `exists` for the five real files and
**`same_source`** for the dummy: "This file (141,866 bytes) is already archived
as experiment 'experiment_baseline'", so the seed was never ingested twice under
another name. A request sweep of 52 routes over the six experiments (the
production file's projections, D-frame, energy panel, 3-D cloud, features and
momentum-bin performance, and each aggregate's features, response, XGBoost views
and prediction density) answered 200 every time, the largest body 89,539 B (the
production file's Absolute projections) and the slowest request 3,172.6 ms (its
Local 3-D cloud, a cold scan).

### Through the browser

The **Upload dataset** form lives inside the **Admin Settings** panel, between
the default-view form and the Automatic ingest section; there is no separate
header button any more, the header's **Admin Settings** button opens both. Its
fields are the experiment name, an optional display name, the `CREATE_NEW` /
`APPEND` mode, the event offset, the source — a file from this computer or one
already on the server — and **Replace** (`force_reingest`), with a **Clear
form** button that empties every field and re-arms **Upload & Ingest**. The
form streams a file to disk in 8 MiB chunks and hands it to a background ingest
job, polled for progress. The panel's **Close** button closes it; a running
upload or ingest survives closing the panel, and its report stays until
**Clear form** or the next open. Large uploads are permitted — external
collaborators have no shell access and this is their only route — but the form
warns that a browser upload cannot resume, and that ingestion needs about three
times a CSV's size, or three and a half times a Parquet file's, in free disk
space. The Parquet figure is provisional until measured on the production
file.

`CREATE_NEW` builds a clean, isolated experiment.

- **An existing name is refused.** Onto a name that already holds an experiment
  (in any state, including tables or an archive a crash left behind) it returns
  **409** unless **Replace** is ticked. That is `force_reingest=true` in the
  API and `--force-reingest` on the CLI.
- **Every check runs before the drop.** Replacing drops the old experiment
  before the new file is read, so a refused file never costs the experiment it
  would have replaced. A failure later in the load still does, and the form
  says so.
- **A queued name is refused even when forced.**
- **The form asks first.** Each of these, the file type and the naming rules
  are checked before a byte is sent.

`APPEND` adds rows, and is **rejected** if the incoming event numbers overlap
those already stored; merging two files that each number events from zero would
fuse distinct physics events. Enter an event offset to shift them clear. An
append must also match the schema of the experiment's archive.

**A file of no accepted schema is refused at once.** `POST /api/upload` and
`POST /api/ingest-local` check the CSV header, or the Parquet footer and its
typed columns, before a job is queued: a wrong-schema file is a synchronous
**400**, not a failed experiment minutes later, and a staged upload is deleted.
The problem body (`application/problem+json`) carries:

- `detail`: one sentence naming the missing and the unexpected columns against
  the schema the file most resembles, and the list of accepted inputs. "Most
  resembles" is judged by the columns that only one schema has, because the
  coordinates and `energy` say nothing about which was meant; a file that
  resembles none is reported against `hits_all_models`, which keeps the
  long-standing wording. A v37 file and a 29-column v2 aggregate get a sentence
  of their own;
- `expected`, the columns of that schema, and `found`, the file's own;
- `schema` (`name`, `version`, `kind`) and `accepted`, every accepted schema
  with its column count.

`GET /api/upload-info` lists the schemas the same way in `schemas` (each with
`name`, `version`, `kind`, `label`, `summary`, `n_columns`, `columns` and a
`note`) beside `accepted`, the one-sentence list. Its `schema` key still
describes `hits_all_models` alone, for clients that read only that.

### Rebuilding derived tables

An experiment's query tables are derived from its Parquet archive, and the
registry's `derived_version` records which layout built them (see
[Storage](#storage-duckdb-tables-and-the-parquet-archive)). An experiment built
by an earlier release is served as before, with the cards that need the newer
tables shut and the reason shown; a rebuild re-derives every table from the
archive without reading the source file again:

```bash
docker compose exec calorimeter-dashboard \
    python -m calosrv.ingest --rebuild --table <name>
```

The same thing is `POST /api/admin/experiments/{name}/rebuild` and the
**Rebuild derived tables** button in the Derived tables section of
[Admin Settings](#admin-settings-the-default-view), which lists each experiment's
version and follows the job.

- **The route** answers **202** with `{job, poll}` and runs on the ingest worker
  an upload uses, so one job runs at a time. It is a **404** for an unknown
  experiment, a **409** while a job for that name is queued or running, and a
  **400** for an experiment with no archive to rebuild from.
- **Atomic.** The rebuild runs in one transaction. Readers keep the old tables
  and the old registry row for as long as it takes, so the experiment stays
  served; it commits only if verification passes, and a rebuild that fails
  verification or raises is rolled back to exactly what was there. Until then
  the disk holds the old and the new derived tables side by side.
- **The CLI** hands the rebuild to a running server through that route and
  follows the job, as an ingest does, and opens the database itself otherwise
  (`--direct` forces that). `--no-sample` skips the preview sample.
- **Only the application's own demonstration experiment** (`experiment_baseline`)
  rebuilds itself at start-up when an earlier release derived it. A user's
  experiment never does: an operator rebuilds it. This matters for a deployment
  whose production experiment predates the new tables (derived version 1): it
  keeps serving, and the new cards stay shut until that rebuild is run.

### Comparing features with the aggregate

`python -m calosrv.ingest --compare-features HITS EVENTS` takes the names of a
single-shower hit experiment and an aggregated one. It compares, event by event,
the features the hit experiment rebuilds in SQL from its Group-1 sums with the
producer's own values in the aggregate: the 17 `calc_all_features_v3` features in
each of the three frames. The momentum, θ, φ, bin and hit count must be equal
exactly and the deposit to 10⁻¹². It opens the database itself (direct mode, so
with the server stopped) and needs no `--table`. Each feature's difference is
relative to the larger of the two values and of the feature's median magnitude,
so a centroid that is zero to rounding on both sides does not report an error
of order one. The exit code is 0 when every feature agrees to 10⁻⁹. Measured on
the electron files: 99,751 shared events, 249 in the hit file only (its
single-hit events, which the aggregate omits) and none in the aggregate only,
the worst feature at 5.2 × 10⁻¹⁴.

### Expected schema

Three schemas are accepted, one per kind of experiment (`db/ddl.py` holds their
columns and `db/schemas.py` their detection; both are the single source of
truth, and a header is checked against them before a byte is parsed):

| Schema | Kind (`kind`) | Holds | Columns |
|---|---|---|---|
| `hits_all_models` v1 | `two_shower_hits` | two showers per event; one row per hit, with three coordinate frames and three networks' predictions and per-hit CAM maps | 99 |
| `standalone_hits` v3 | `single_shower_hits` | one shower per event; one row per cell, with the cell's attributed particle | 21 |
| `standalone_events` v3 | `single_shower_events` | one shower per event as the producer's precomputed event features; no hits | 59 |

A **CSV** is recognised by its exact header, because the reader is positional:
the same names in another order are refused with a sentence saying so rather
than read into the wrong columns. A **Parquet** file is recognised by its set of
column names, in any order; pandas index columns are ignored. A file that is
neither is refused naming the schema it most resembles (see
[Through the browser](#through-the-browser)).

#### `hits_all_models` v1: two showers, 99 columns

In this exact order:

```
event_number, overlap, cellID,
x, y, z, x_local, y_local, z_local, x_trans, y_trans, z_trans,
energy, particle_origin,
earliest_contribution_time_A/B, incoming_momentum_A/B, incoming_momentum_bin_A/B,
incoming_theta_A/B, incoming_phi_A/B,
centroid_{A,B}_{x,y,z}, centroid_AB_distance            (and the same seven with
centroid_{A,B}_{x,y,z}_trans, centroid_AB_distance_trans  _trans and _local)
{angle,energy,segmentation}_{absolute,local,trans}_{pred,true,gradcam,gradcam_energy,shapcam,shapcam_energy}
```

Three coordinate systems per hit (absolute, the detector's own `x, y, z`;
*trans*, shifted by the hit's own
shower's entry point; *local*, then rotated by that shower's own R(θ, φ)), and
nine networks — three tasks × three input frames — each with a prediction,
its truth and per-hit Grad-CAM and Shap-CAM maps. Measured facts that shape
the service:

- **A cell shared by both showers is two rows**, one A and one B (1,629,316
  such cells on the production file). Only 422 rows remain labelled `'A+B'`;
  they sit at the origin of the per-shower translated and local frames and are counted
  with shower B. `cellID` is therefore not unique within an event, and row
  counts are not cell counts.
- **The segmentation truth is fractional** (E_A / E_voxel) on 45% of hits.
- **Angle and energy predictions are per shower**: one value per (event, A)
  and per (event, not A), stored in the event table rather than per hit. The
  angle networks predict θ only.
- **CAM maps are normalised per shower** (angle, energy) **or per event**
  (segmentation). Shap-CAM is signed, on [−1, +1].
- **`*_gradcam_energy` and `*_shapcam_energy` are archived and never
  plotted.** They are CAM × E_voxel rescaled per event or shower, so summing
  them over hits double-counts. The energy-weighted channels are computed
  from the raw CAM columns instead (see [Display channels](#display-channels)).
- **D is always `centroid_AB_distance`**, the absolute-frame 3-D centroid distance.
  `centroid_AB_distance_trans` / `_local` compare centroids expressed in two
  different frames and are not a separation (their correlation with D is 0.11
  and −0.001).

Types are pinned rather than sniffed. `energy` is DOUBLE, because per-hit
energies span fifteen decades and a single-precision accumulator loses the low
tail; every coordinate, centroid and model column is REAL. Empty fields are read
as NULL; rows with a missing coordinate or a non-positive energy are excluded
from the projections and counted in the ingest report.

#### `standalone_hits` v3: one shower, one row per cell, 21 columns

The producer's single-shower Geant4 hit file, in this exact order:

```
event_number, cellID,
x, y, z, x_local, y_local, z_local, x_trans, y_trans, z_trans,
energy, earliest_contribution_time,
incoming_momentum, incoming_theta, incoming_phi, incoming_momentum_bin,
particle_type, is_secondary, parent_type, daughter_type
```

The three coordinate systems are the same as the two-shower file's, per hit.
Types, and why:

- `x, y, z` and `earliest_contribution_time` are REAL. The producer writes
  float32 positions widened to float64, which single precision holds exactly,
  so the measured lattice is bit-identical to the production file's.
- The `_trans` and `_local` coordinates, `energy` and the incident kinematics
  are DOUBLE: they are genuine float64 values, checked against the producer's
  aggregate at 10⁻⁹, and `incoming_momentum_bin` is checked against ⌊p⌋ on
  integer boundaries that float32 rounding can cross.
- `incoming_momentum_bin` and `is_secondary` are UTINYINT; a Parquet BOOLEAN is
  accepted for `is_secondary`.
- `particle_type`, `parent_type` and `daughter_type` are free text. The
  vocabulary of `particle_type` is open (ions are written `PDG_100ZZZAAA0`),
  `daughter_type` is a `;`-joined list, and an empty field, the absent parent
  of a primary-tagged cell or an empty daughter list, is read as NULL.
- Archive parts are written `ORDER BY event_number, cellID`, so the filters
  prune row groups by zone map and the archive is deterministic.

Measured on the electron file (seed s1, 5,000 events per 1 GeV bin over 0–20 GeV
at `incoming_momentum_bin` 0–19; 11,436,422 rows, 100,000 events):

- **Its lattice is production's**: 212 × 104 × 60, the first layer at
  3662.4 mm, the cell footprint 48.27 × 48.60 mm.
- **73.83% of events have no primary-tagged row** (`is_secondary = 0`), 64–80%
  by momentum bin, so a missing primary is the usual case, not a data fault.
- **95.1% of events hold at least one hit behind their shower's entry plane**
  (`z_local < −10⁻⁶ mm`), carrying 3.98% of the energy.
- **249 events have a single hit**, whose spatial SDs are undefined.

Ingest verifies, among others, that `(event_number, cellID)` is unique, that
`incoming_momentum_bin` is ⌊`incoming_momentum`⌋ on every row, that each event
has one entry point P₀ and one set of incident kinematics, and that the local
coordinates are R(θ, φ) applied to the translated ones.

#### `standalone_events` v3: the event-level aggregate, 59 columns

One row per event, in this exact order:

```
event_id, incoming_momentum, incoming_theta, incoming_phi, incoming_momentum_bin,
num_hits, total_hit_energy,
width, height, depth, depth_range, volume, centroid_x, centroid_y, centroid_z,
  mean_r, std_r, max_r, weighted_r_mean, avg_theta, avg_phi, angular_spread
                                       (these 15, then the same 15 with _trans, then with _local)
numerical_density, energy_density      (then both again with _trans, then with _local)
energy
```

That is `core.calc_all_features_v3` from the physics group's `core.py` (kept in
`reference_ipynb_notebooks/`, which nothing imports), computed on raw z:
7 base columns, 15 features in each of three frames, two densities in each, and
a last column. `event_id` and `num_hits` are integers, the bin is UTINYINT and
every feature is DOUBLE. What the data are, measured on the electron file and
read from `core.py`:

- **The last column, `energy`, is a label and not an energy**: 1{p ≥ 2 GeV}.
  The archive keeps the file's name; the event table stores it as `energy_class`
  (UTINYINT). On the electron file 89,956 events carry label 1 and 9,795 label 0.
- **The aggregate is a censored sample.** It leaves out the 249 events with a
  single hit, whose spatial SDs are undefined: 99,751 of the 100,000 events
  remain, 4,807 to 5,000 per momentum bin (bin 0 loses 193), and the mean
  sampling fraction of bin 0 is biased high by +2.7% because single-hit showers
  deposit the least. It is never called balanced, and every panel on this kind
  says so.
- **Centroids are energy-weighted** (`core.py:491-497`); an unweighted `cx_mean`
  would be wrong. `std_r` and `angular_spread` use ddof = 1,
  `angular_spread = SD(θ) + SD(φ)`, and `num_hits` is the row count of the hit
  file. `width`, `height`, `depth` and `depth_range` are floored at 10⁻⁶ by
  `core.py`; ingest counts the values at the floor.
- **φ is circular and the file's `avg_phi` is its arithmetic mean**, so it is
  never read as a direction, and `angular_spread` carries the same flaw through
  SD(φ).
- **Ingest refuses duplicate `event_id`s** before any table is created (one
  event counted twice in every statistic) and reads a non-finite value as NULL,
  counted per column, never as zero.
- **The 29-column v2 aggregate, with its `gnn_*` node features, is not
  accepted**; the refusal says so.

An experiment of this kind has no hits, no lattice and no frames; what it
serves is in [What each kind serves](#what-each-kind-serves).

#### Parquet files, and what every schema shares

A Parquet column is read by name; only a CSV is positional. Each column is cast
to its pinned type, so a Parquet-sourced archive part is interchangeable with a
CSV-sourced one: the same types, readable together, appendable to each other.

- **Refused before anything is dropped,** naming the column:
  - a column missing, or an extra one (a pandas index column is ignored);
  - an incompatible type, such as text into a number or a floating-point event
    number;
  - integers outside the pinned range.
- **Narrowing is reported.** A DOUBLE column narrowed to the schema's REAL is
  noted in the ingest report. Float32 round-off is at most 2⁻²⁴ ≈ 6 × 10⁻⁸ of
  the value. Measured on the demonstration file:
  - lab `x, y, z` are exact, because the file prints float32 values;
  - momenta move by at most 5.9 × 10⁻⁷ GeV;
  - local coordinates move by at most 1.2 × 10⁻⁴ mm.
- **NaN.** In `hits_all_models`' twelve undefined-separation columns, NaN is
  read as NULL (as an empty CSV field is) and counted. In the aggregate a
  non-finite feature is NULL, counted per column. NaN anywhere else fails
  verification.
- **Scope.** A single file only, with no globs or hive partitions. DuckDB reads
  it without pyarrow.

The format is taken from the file's content, not its name. A Parquet file
begins and ends with `PAR1`, which also tells a half-copied file (no footer yet)
from a whole one, and a gzip or zip file is refused with a reason.

#### The z convention

Every file, the Parquet archive and every derived table keep the detector's
**raw z**, for both hit schemas: the first layer at z = 3662.4 mm, 60 layers
at 20.5 mm, on the one 212 × 104 × 60 lattice the two share. The producer's
aggregate was computed on raw z. Measured, raw z reproduces all 17
absolute-frame features to ≤ 10⁻¹¹ and `z − 3649` is off in every event, so the
Group-1 columns use raw z and reproduce the aggregate to ≤ 10⁻⁹ relative (worst
5.2 × 10⁻¹⁴ over 99,751 events).

`core.SHIFT_Z = 3649` mm (`ddl.CORE_SHIFT_Z_MM`) is only a **display offset**,
applied where a card quotes depth below the calorimeter front face and labelled
`z − 3649 mm` there: the absolute-frame z row of the statistics card, and the
Models page's `depth` feature. Volumes, densities and `centroid_z` stay raw,
and the drawer says so. The per-shower frames' z = 0 is unchanged: each
shower's first populated layer.

### What each kind serves

The kind decides the tables an experiment has and, through them, what the
interface can show (`query/capabilities.py` is the one owner of every gate):

| | `two_shower_hits` | `single_shower_hits` | `single_shower_events` |
|---|---|---|---|
| Input schema | `hits_all_models` v1, 99 columns | `standalone_hits` v3, 21 columns | `standalone_events` v3, 59 columns |
| Tables | `proj_`, `proj_…_s10`, `event_` (derived v2: 99 columns + Group-1 for both showers = 239), `layers_`, `profiles_` | `proj_` (17 columns, species kept), `proj_…_s10`, `event_` (100 columns, Group-1 for one shower), `layers_`, `profiles_` | `event_` only (59 columns) |
| Showers | A and B (`'A+B'` rows count with B) | one, shower A | one, shower A |
| Filters | E₁, E₂, D | p (sent as `e1`) | p (sent as `e1`) |
| Frames | Absolute, Separation-Aligned (Translated, Local), legacy per-shower translated | Absolute, Translated (per shower, API `trans`), Local; no D-frame (it needs two showers) | none |
| Channels, networks | five channels, three networks | density only, no network | none |
| Page 1 | the 2 × 2 and all nine physics cards | the 2 × 2, whose plot 4 is the response grid, and all nine cards | a notice in place of the 2 × 2, and the five cards that read the event table |

A card the kind cannot serve is shut with the server's own sentence, never
filled with a substitute. [Page 1 for each kind of
experiment](#page-1-for-each-kind-of-experiment) says how the interface shows
that, and `GET /api/experiments` publishes every gate ([API](#api)).

### Storage: DuckDB tables and the Parquet archive

Ingest writes the source, CSV or Parquet, **once** into an immutable Parquet archive,
`${data_dir}/archive/<experiment>/part-<n>.parquet`, and builds the query
tables from it:

- **The archive.** One part per ingest, written as `part-<n>.parquet.tmp` and
  renamed into place, listed in a `manifest.json` that readers take instead of
  globbing. Every `COPY` uses `ROW_GROUP_SIZE 100000, COMPRESSION zstd,
  COMPRESSION_LEVEL 3`; `ROW_GROUP_SIZE` is a target, and DuckDB's parallel
  writer overshoots it by up to 2% (241 row groups of 11,448–102,040 rows on the
  production file, 2.7 GB). An append adds a part; `DELETE /api/experiments/{name}`
  removes the directory. Notebooks can read the archive while the server runs.
- **The hot tables** live in `calorimeter.duckdb`, per kind (the
  [kind table](#what-each-kind-serves)). There is no `hit_` table any more. The
  production database measured 2.5 GB before Group-1, `layers_` and `profiles_`
  existed.
  - `proj_<name>` is one row per hit. Two-shower: 40 columns — lab lattice
    ordinals, the translated and local coordinates, energy, the 18 raw CAM
    columns, the segmentation fractions of the three frames. Single-shower: 17
    columns, the same names with the shower as shower A and the four species
    columns kept. Its 10% sample is `proj_<name>_s10`.
  - `event_<name>` holds per-event additive sufficient statistics: for every
    network and frame on two-shower data, and on a single-shower hit experiment
    the shower-A names, the species and consistency counts and the incident
    kinematics. An aggregated experiment's is the file's 59 columns, with the
    seven base columns renamed to the shared names (`event_number`, `e1`,
    `theta_a`, `phi_a`, `e1_bin`, `n_hits`, `e_dep`) and `energy` stored as
    `energy_class`.
  - **Group-1 per-event columns** are appended to every hit kind's event table
    (from derived version 2 on two-shower data): per shower, `n_hits`, `e_dep`,
    `n_cells`, the hits and energy at negative depth, and Σ E·ρ and Σ E·ρ²;
    per shower and frame (absolute, translated, local), the x, y, z extremes,
    Σ E·x, Σ E·y, Σ E·z, Σ r, Σ r², its SD, the maximum r, Σ E·r, Σ θ, Σ θ² and
    its SD, Σ φ and its SD, and Σ cos φ, Σ sin φ. That is 70 columns per shower,
    named `{stem}_{shower}_{frame}` through `ddl.group1_column` and nowhere else.
    From them SQL rebuilds every `calc_all_features_v3` feature (`db/group1.py`).
    The SDs are stored `stddev_samp` values, because recovering them from Σr and
    Σr² loses about 10⁻⁵ to cancellation where a shower is narrow and far from
    the origin; ρ is the 2-D transverse radius √(u² + v²), never `core.py`'s 3-D
    `r_local`; the linear φ sums exist only to reproduce its arithmetic
    `avg_phi`.
  - `layers_<name>` has one row per (event, shower, own-shower layer `kt`):
    the deposit, the cell count and Σ E·u, Σ E·v, Σ E·ρ, Σ E·ρ² in the Local
    frame. `kt` is `round(z_trans / layer pitch)`, so a shower's layers count
    from its first.
  - `profiles_<name>` has one row per (event, shower, axis, bin): each shower's
    energy along its depth w (axis 0, bins of the 20.5 mm layer pitch anchored
    at w = 0) and its transverse radius ρ (axis 1, 10 mm bins 0–49 and an
    overflow bin, 50). It is the Local-frame footprint splat, k × k × k_z
    sub-deposits with k = 6 and k_z = 2 (72 per hit) over the 48.27 × 48.6 mm
    footprint and the layer pitch, rotated by R(θ, φ). Its `e_wneg` column is
    the part from hits at `z_local < −10⁻⁶ mm`, so the notebook's convention
    (drop those hits) is a subtraction rather than a second key. The comb is
    measured at ingest on the pooled profiles, against a threshold of lag-1
    < −0.10: none on the production file (+0.78 along w, +0.90 along ρ) or on the
    electron file (+0.80, +0.67).
- **The XGBoost analysis tables.** An event-level aggregate paired with shipped
  models also has six `xgb*_<name>` tables (`xgbrun_`, `xgbpred_`, `xgbfold_`,
  `xgbimp_`, `xgbbin_`, `xgbtree_`), written by the background analysis in one
  transaction and dropped with the experiment ([What it
  stores](#what-it-stores)).
- **The registry** (`experiment`) gained two columns, appended, so an older
  database migrates by `ALTER TABLE` alone. `derived_version` is the layout
  generation of the derived tables (a NULL reads as 1; the current ones are 2
  for `two_shower_hits` and 1 for the others, `db/schemas.py`
  `DERIVED_VERSION`). `capabilities` is JSON: what ingest measured that the API
  advertises, namely the cell footprint, the profile splat and its comb, the
  momentum-bin range and the rule it follows, the species facts and the
  aggregate's label rule.
- **A stale derived version stays READY.** A two-shower experiment ingested
  before Group-1, `layers_` and `profiles_` existed has `derived_version` 1: it
  is served exactly as before, and bootstrap logs that a rebuild would enable
  the rest, with nothing heavy at boot. `capabilities.derived` in
  `GET /api/experiments` reports `{version, current, status, notice}`; the
  cards that need the newer tables (the two profile cards, the negative-depth
  block and, for the hit kinds, the feature explorer) are shut with that notice
  as their reason, and every other card works as before. A
  [rebuild](#rebuilding-derived-tables) is atomic. A ready experiment that lacks
  a table its kind needs is marked failed at start-up, naming the table.
- **Verification** is per kind (`verify`, `verify_single`, `verify_events`). For
  two-shower data it compares the archive's rows with the CSV's, confirms that
  P₀ is each shower's first-layer energy-weighted centroid (`p0_definition`),
  measures the two D-frame anchor definitions against each other
  (`anchor_residual`, a notice), and checks the
  data contracts the frames rely on: P₀ constant per shower (spread 0.00037 mm),
  the local coordinates equal to R(θ, φ) applied to the translated ones
  (residual 0.00066 mm), `z_trans` on whole 20.5 mm layers, the `*_true` columns
  equal to the own shower's momentum and θ, the split cells, the 'A+B' rows at
  the origin.
  A single-shower hit experiment is checked for the same frame contracts and
  for its own: unique cells, the bin rule, the species domain, the Group-1
  partition and the conservation of energy by the layers and profiles. An
  aggregated one is checked for its own consistency (the densities are the hit
  count and the deposit over the volume, the label follows 1{p ≥ 2 GeV}).
- **`python -m calosrv.ingest --rebuild -t <name>`** rebuilds the derived tables
  from the archive without re-reading the source file
  ([Rebuilding derived tables](#rebuilding-derived-tables)).

### Retired: the v37 schema

The 29-column `hits_with_gradcam_v37.csv` format is retired. An experiment
ingested under it is marked failed at start-up with the error
`unsupported schema (v37, retired): delete and re-ingest`; its tables are left
unread until it is deleted, and a retired demonstration baseline is reseeded in
the new format. The new file shares v37's lattice and incident kinematics, so
figures credited to production v37 below were measured on that file and are
kept with that provenance.

---

## Admin Settings: the default view

**Admin Settings** in the header opens a panel that sets what a new session
opens on:

- the experiment;
- the reference frame (the sidebar's two tiers composed into one list:
  *Absolute*, *Separation-Aligned (D-Frame) › Translated*, *Separation-Aligned
  (D-Frame) › Local*, and the legacy *Per-shower translated*, which has no
  sidebar radio);
- the reconstruction model;
- the display channel;
- the display mode;
- the density normalisation.

Choose them, or press **Use current view** to copy the sidebar, then press
**Save defaults**. **Open default view ↗** starts a fresh session to check the
result. The panel also holds the **Upload dataset** form (see
[Through the browser](#through-the-browser)) and shows the
[drop folder](#drop-folder-automatic-ingest)'s last scan, with live job status
and **Scan now**; its Derived tables section lists each experiment's
derived-table version and runs a [rebuild](#rebuilding-derived-tables); its
**XGBoost model runs** section, after it, lists the [XGBoost
analysis](#the-xgboost-analysis) of every event-level aggregate and holds the
**Rescan models** action; its **Close** button closes the whole panel, and a
running ingest survives that.

Each setting resolves through four layers, highest first:

| Layer | Set by | Chip |
|---|---|---|
| URL hash | a link or bookmark carrying view state | — |
| Saved | the panel: `config.json` on the data volume, written atomically | "set here" |
| Environment | `CALOSRV_DEFAULT_*` in `docker-compose.yml` | "from environment" |
| Built-in | Absolute / segmentation / density / each frame's own display mode / selection; the oldest ready experiment | "built-in" |

- **Chips and Reset.** The chip beside every control names its layer. **Reset**
  removes the saved value, so the layer beneath shows through; like every
  change it takes effect on **Save defaults**.
- **Fallback.** A saved experiment that is not ready yields to the oldest ready
  one, and says so ("fallback").
- **Unavailable choices.** A frame, model or channel the chosen experiment does
  not serve is disabled.
- **Display mode.** The display-mode setting applies to the default frame.
  "Frame's own" keeps native in the Absolute frame and the Continuous Field
  elsewhere.

**Bookmarks never change meaning.**

- **Absent means built-in.** The interface writes into the URL hash every view
  value that differs from the built-in view, and omits the rest, so an absent
  key means "built-in".
- **Only an empty link takes the defaults.** A link with any recognised key
  opens exactly as written.
- **New links stand alone.** The first link a session writes records every
  non-built-in value, so it does not depend on the defaults either.
- **The built-in view is frozen.** It is `state.js` `DEFAULTS`, held equal to
  `calosrv/admin/schema.py` by a test. The team's view changes in the panel,
  never by editing the built-in values, which would silently re-read every
  saved link.

**Why the built-in view is the Absolute (detector) frame.**

- **It is the only frame computable from measured quantities.**
  - The legacy per-shower translated frame subtracts each shower's entry point
    P₀, recovered from its truth-labelled hits.
  - The Separation-Aligned Local frame also rotates by the truth (θ, φ).
  - The Separation-Aligned Translated frame — the D-frame — back-projects along
    the truth (θ, φ).
- **It carries the networks that apply to real data.** The network follows the
  frame, so the absolute-frame networks, the only ones whose inputs exist on
  detector data, appear only in the Absolute frame and the D-frame.
- **Any other frame can still be the team's default.** Choose it in the panel.

**Scope.** Saving never changes the view of the session that saved it. An API
call is still a function of its parameters: the defaults govern the interface's
cold boot, plus one API case, where a request naming no experiment opens the
default one.

**XGBoost model runs.** Below the Derived tables, a section lists the models
folder and, per event-level aggregate experiment, its pairing with the shipped
models (species, seed and the two model files, or the reason none pairs) and
where its [analysis](#the-xgboost-analysis) stands: queued; analysing, with the
step it is on (*n* of 18); done, with its duration; failed, with the error; stale,
with what changed; waiting for the experiment; or not paired. A task whose
training split was not reproduced is named on the row, so a "done" analysis never
hides it. The list is the read-only `GET /api/admin/model-runs` (its **Refresh**
button reads it again, and it polls itself while an analysis is queued or
running). The panel reads only the shape the route serves: `runs[]`, one entry
per experiment with its pairing and its analysis flat on it, the step shown as
"*n* of 18: step label" (`step`, `steps`, `step_label`) and the duration from
`duration_s`. The older shapes it once read defensively (a bare array, nested
`pairing` and `analysis`, `seconds`, a 404 "not available in this build") are
gone, and `tests/test_js_admin_model_runs.py` pins the reader against the
recorded body. **Rescan models** is `POST /api/admin/model-runs/scan`: it rescans the
folder, re-pairs every aggregate, compares each stored analysis with everything
it was computed from, the feature and label values included, and queues every
missing or stale one; a failed analysis whose inputs have not changed is left
alone, and one already queued or running is never queued twice. **Re-analyse** on
a row (`POST /api/admin/model-runs/{table_name}/analyse`) queues that
experiment's analysis even when the stored one is current, and is disabled while
one is under way. The Models page has no Admin Settings of its own; its link goes
to `/?admin=1`.

**Trust model.** No endpoint of this service is authenticated, and the panel is
no exception. Like upload and delete, it is open to anyone who can reach the
port, which compose publishes on all interfaces. Keep the port on a trusted
network.

## The interface

**Two pages, one API and one view state.** *Physics* at `/` holds the 2 × 2
diagnostic of the next sections with the [physics section](#the-physics-section)
below it. *Models* at `/models` holds the network and feature analysis, the XGBoost
model views and the 3-D views, and is documented in [The Models
page](#the-models-page). The header's page tabs link between them, and each link carries the
view: its `href` takes `location.hash` when it is clicked, because the interface
writes the hash with `history.replaceState`, which fires no event. Both pages
read the same `/api/experiments` catalogue and the same hash. Admin Settings
live on the Physics page: the Models page's link to it goes to `/?admin=1`,
which opens the panel there and then drops the query. Everything below on the
Physics page applies to the three kinds of experiment alike, except where
[Page 1 for each kind of experiment](#page-1-for-each-kind-of-experiment) says
otherwise.

**Header** — a sidebar toggle (one icon button, `#sidebar-toggle`, reporting
`aria-expanded`), the page tabs, the experiment dropdown, a compute badge
showing the active `DUCKDB_MEMORY_GB` and thread count, an exact/preview badge,
and the **Admin Settings** button, whose panel also holds the upload form.

**Sidebar** — filters for E₁ (`incoming_momentum_A`), E₂ (`incoming_momentum_B`)
and D (`centroid_AB_distance`), combined with chained boolean AND and debounced
by 150 ms; a two-tier **Reference Frame** control — a primary radio
*Absolute (detector coordinates)*, the default, or *Separation-Aligned
(D-Frame)* (`name="frame-view"`, values `absolute` | `aligned`), and under the
latter a nested radio *Translated* or *Local (shower-fixed)*
(`name="frame-sub"`, values `canonical` | `local`); entering Separation-Aligned
lands on Translated. The legacy per-shower translated frame has no radio: a
`#frame=trans` link or a saved admin default opens it and reveals a hidden
*Per-shower translated (legacy)* sub-option while it is active. The stored
value, the URL hash (`#frame=lab|canonical|local|trans`) and the admin
`default_coord_system` stay the flat four-value frame key, and `js/labels.js`
`FRAME_TREE` is the one definition of the tree (see
[Reference frames](#reference-frames)) — with a caption stating what the frame
does; the display-mode and resolution control, whose labels, default and hint
follow the frame (see [Display modes in the Separation-Aligned frames](#display-modes-in-the-separation-aligned-frames));
the five-way **display channel** selector (see [Display channels](#display-channels)),
under which a **Density normalisation** radio (relative to this selection's
peak, or to the dataset peak) appears in the co-registered frames, where it
replaces the lock-scale checkbox; the **model** selector, which drives both the
CAM channels of the spatial panels and the metric cards; and the
[metric cards](#model-performance-cards); under the Reference Frame caption a
**Compare frames side by side** checkbox, and below it the **Event Inspector**
picker (an event number, Prev / Next within the selection, a shower radio,
*Pick for me* and *Back to the ensemble*; see
[The Event Inspector and the compare-frames view](#the-event-inspector-and-the-compare-frames-view)).
Every control travels in the URL
hash — `frame`, `channel`, `model`, `rho_norm`, `anchor`, the four per-frame display
modes (`display_lab`, `display_trans`, `display_local`, `display_canonical`),
`compare`, `event` and `shower`
among them — and a link carrying an unknown value for any enumerated control
falls back to its default rather than to a 422. **Old canonical links:** the
D-frame (`frame=canonical`) used to be the default, which a link never wrote
down, so such links now open in the Absolute frame; add `#frame=canonical`.

**Collapsing the sidebar.** The header's icon button collapses and re-expands
the configuration sidebar. The state is kept in `localStorage`
(`calosrv.sidebar`), never in the URL: a bookmark must not carry layout. The
grid tracks snap — no CSS transition — and every chart re-lays itself out
synchronously once the class has toggled, so the XY panel stays 1:1 px/mm at
the new width rather than measuring a half-way geometry.

**The Details drawer.** The four on-card footnotes are gone. Each card has a
**Details** button — its title row is clickable too — that opens a right-hand
drawer (`<aside id="inspector">`, `js/shell.js`) with that panel's methodology
and statistical disclosures in sections: *Selection*, *What is drawn*,
*Disclosures*, *Marks and legend*, and for the energy panel *Reading the
density axis*. `js/panel_notes.js` builds them from the same pure functions
that wrote the footnotes — `frame_views.js` `footnotes()`,
`export/disclosure.js` `figureDisclosure()`, `exportLegend()`, `caption.js`
`describeSelection()` / `describeView()` — so nothing a footnote said has gone
anywhere else. The Details button is the keyboard trigger: it reports
`aria-expanded`, Escape closes the drawer, and focus returns to it. It carries
a warning dot when the panel holds a hazard a reader should not miss — a
provisional fitted range, a measured comb, a sampled preview, an empty frame;
on the energy panel a low-statistics series, a clipped energy range or
uncalibrated energies. Opening the drawer narrows the chart column, and every
panel re-lays itself out. Still on screen without opening it: ρ_ref and a
**Clipped** readout in the status bar (`#stat-clipped`: the entry panel's
cells clipped to the ends of the colour ramp in the Absolute frame, or its
bins below the display floor in a co-registered frame), the energy card's
low-statistics notices (`#energy-sparse`, which also carry the energy-axis
clipping note), and the sidebar's ⓘ dots (the comb and frame notices).

Each filter carries **both a numeric pair and a slider, on one shared grid**.
The slider's integer domain *is* the numeric step — 0.05 GeV for the energies,
1 mm for D — with the range snapped outward to whole multiples, so typing 2.05
and dragging to 2.05 reach the same value and the URL needs no rounding. (The
earlier fixed 1000-step slider put one step at 0.0196 GeV, so a typed 2.05 could
only land on 2.0455.) Typing a lower bound above the current upper bound pushes
the upper one along rather than swapping the two.

Persistent explanations — the staggered-lattice comb, the depth-lock caveat, the
undefined-D count — appear as **ⓘ popovers beside the control they concern**.
The banner across the plots carries only transient, actionable messages and can
be dismissed; dismissal is keyed by message text, so a warning re-sent on the
next response stays dismissed.

**2×2 canvas**

1. **XY Projection — shower entry.** The entrance slab (first six sampling
   layers, 120 mm from the front face at z = 3662.4 mm). Centroid markers and the
   labelled separation vector D. Locked to a 1:1 metric aspect so D can be read
   off the picture.
2. **YZ Projection — longitudinal evolution** along depth.
3. **XZ Projection — lateral profile**, sharing the YZ colour scale so the two
   are directly comparable.
4. **Reconstructed energy vs. separation D**, with layered Gaussian fits,
   isolated-shower reference markers, and an embedded (μ, σ) table.

In a co-registered frame the three spatial panels are retitled and their axes
carry the frame's own symbols, with their meaning spelled out, so a reader
cannot mistake a co-registered picture for detector coordinates:

| Frame | Panels | Axis symbols |
|---|---|---|
| Absolute | XY / YZ / XZ | x, y, z |
| Separation-Aligned › Translated (the D-frame, API `canonical`) | D–Y′ (the server's X′Y′) / Y′Z′ / X′Z′ | the entry panel's horizontal axis is written **D**: the signed x′ coordinate along the A→B separation, with the anchors at D = ∓⟨D_entry⟩/2 and tick values in mm; y′ normal to the shower plane, z′ from the front face; the depth panels keep x′, y′, z′ |
| Separation-Aligned › Local (API `local`) | u–v / v–w / u–w | u, v lateral; w depth along the incident direction |
| Per-shower translated (legacy, API `trans`) | Δx–Δy / Δy–Δz / Δx–Δz | Δx, Δy from the shower's entry point; Δz depth from its first layer |

The server sends the symbol with each axis; the name stays `x`, `y`, `z`, and
the server's symbols and panel names (X′Y′, Y′Z′, X′Z′) are not renamed. The
D label is the one client-side exception, made in `js/axis_symbols.js` and
read from there by every consumer that names the axis — the axis title, the
hover readout, the window phrase, the drawer's provenance line, the centroid
tooltips — so the screen cannot disagree with itself about what the axis is
called. Each panel's Details drawer carries every disclosure the frame
generates; see
[Separation-Aligned (D-Frame): the Translated view (API canonical)](#separation-aligned-d-frame-the-translated-view-api-canonical) and
[Per-shower frames: Local, and the legacy translated frame](#per-shower-frames-local-and-the-legacy-translated-frame).

All three spatial panels **scroll to zoom and drag to pan**, with an *Auto-fit
RoI* button that frames the box holding 99% of the selected energy (bounded by
energy percentile, not by the outermost hit, so one stray cell cannot define the
view) and a *Reset*. Both axes always scale by the same factor, so the 1:1
metric aspect survives zooming — verified at 4.974 mm/px on both axes after four
wheel notches. When the selected showers already span the detector, as most
multi-event selections do, the fit says so rather than appearing inert.

### Overlay and layout behaviour shared by every frame

These fixes were found while reworking the D-frame panels. They were applied
to the Absolute frame too. The `lab` *server* payload did not change: the
golden test pins it byte for byte.

- **The colour bar colours the raster and nothing else** (`visualMap`
  `seriesIndex: 0`). Without a series index ECharts coloured *every* series by
  its data value. So the lab's pink and blue centroid diamonds came out in
  whatever ramp colour their coordinates mapped to, measured as a fill of
  `rgb(253,231,37)`, the top of Viridis. They are pink and blue again.
- **Every overlay line that names its quantity now shows its tooltip.** A
  `line` series drawn with `symbol: 'none'` never fires an item tooltip, so the
  wording CLAUDE.md requires was attached and never seen. These lines are now
  custom series from `static/js/panels/marks.js`: the spread bar, the
  separation rule, the ensemble axes, the depth-face rules and the lab's
  measured shower axes. Two settings in those series are load-bearing:
  - `clip: true`, because a custom series is unclipped by default and would
    run out of a zoomed plot across the axes;
  - `style.fill: 'none'`, because otherwise zrender fills the path. The hover
    test then covers only the 1 px stroke instead of a ±2.5 px band.

  The lab's dashed incident trajectories stay silent.
- **The bin readout answers everywhere, and an overlay adds to it on its ink.**
  The raster is `silent`, so any element under the pointer is an overlay. But a
  mark's hit area is wider than its ink: the open anchor rings hit-test their
  whole 13 px disc on the shower cores, a face rule's ±2.5 px band covers most
  of a 6.6 px first or last layer, and the axis lines run through the cores.
  Standing aside for every hit target hid the bin readout, the only place the
  exact top-k values and the below-floor wording appear, over the brightest bin
  in 10 of 12 panel × selection cases. So `marks.js: onInk` tests the pointer
  against the drawn ink: within half the stroke plus 1 px of a line, on the
  outline of an open marker, anywhere on a filled one. Off the ink the handler
  shows the bin alone. On the ink it shows the overlay's own text, read from its
  series, followed by the bin. The ensemble wedges are silent, because at small
  N they are wide areas over the data (the N = 3 Y′Z′ envelope spans
  −1172…+636 mm of a ±720 mm window). The bin readout names the wedges the
  pointer is inside instead, each with its quantity: the dispersion band as
  ± the sample SD of the per-event slopes, and the envelope as the 95% interval
  of the mean. Measured on production v37 over five selections: the brightest
  bin of each of the 15 panels shows its readout, and so do all 63 points of a
  9 × 7 grid over each plot; anchors, rules and axis lines still name
  themselves when hovered on their ink.
- **Tooltips are never clipped, and explanations leave the panel they explain.**
  A hover readout used to be cut off where it met the left sidebar. Measured in
  Chromium with the real stylesheet, it was clipped rather than stacked under
  the sidebar: `.main` is an `overflow-y: auto` scroll container, and a tooltip
  that ECharts flipped left of the pointer was cut at its padding box, 41 px
  short. The first fix, `confine: true`, kept every tip inside its own chart.
  But that pushed a rich tip back over the plot it explains. On a centroid, an
  overlay's explanation sits above the bin readout, about 360 × 180 px. Such a
  tip covered a median 35% of the plot area at 1600 × 900, up to 98% at
  1280 × 800, and often sat on the pointer.

  Every tip is now mounted on `#tooltip-layer`, a `position: fixed`,
  viewport-sized layer outside `.main` (`index.html`, `layout.css`). Nothing
  clips it there, and it draws above the sidebar and the header. The layer is
  fixed rather than plain `<body>` because ECharts hides a tip without moving
  it: on `<body>`, a hidden tip left near the old bottom edge made the document
  taller once the window shrank.

  One placement module (`static/js/panels/tooltip.js: placeTooltip`) decides
  where a tip goes, by the kind of tip rather than its size:

  - **The plain bin readout stays beside the pointer, up to 20% of the plot.**
    That is the coordinates and the bin's value: right of the pointer, or left
    at the edge. It sits there only where the box covers at most 20% of the
    hovered plot's area (`READOUT_SHARE`, `panels/tooltip.js`). A readout that
    would cover more leaves the plot and is placed as an explanation is, below.
    The cap is on overlap, not on size, so every Page 1 readout that already
    met it stays exactly where it was; on the Models page's paired projections
    the five-line readout covers about a third of the plot mid-panel, so it
    leaves. Near a plot's edge, where less of the box overlaps, it may still sit
    beside the pointer. Every `ChartPanel` readout on both pages follows the
    same rule.
  - **Every explanation leaves the hovered chart.** That covers a mark's or an
    overlay's explanation, and every tip on plot 4. It goes to the side with
    the most room: over the neighbouring panel in the two-column layout, or
    above or below in the one-column one. It stays inside the visible content
    area, then the viewport.
  - **With no room anywhere**, an explanation goes outside the plot area, and
    as a last resort to the position that covers the least of the plot.

  A threshold on the readout's own size was tried first and dropped: readout
  sizes straddled it from bin to bin, so the readout jumped to the next panel
  and back as the pointer moved. The 20% cap above is measured on the box's
  overlap with the plot, which leaves a Page 1 readout where it was. The side
  follows the layout, not the pointer. A tip neither
  glides (`transitionDuration: 0`) nor lingers (`hideDelay: 0`), and it hides
  when the content scrolls.

  One ECharts internal is involved. zrender caches the chart's client
  transforms on `___zrEVENTSAVED`, and a scroll followed by a drag once left one
  of them stale, drawing a tip 120-240 px from its place. The cache is
  dropped before every placement, and a test pins it in the vendored bundle.

  Measured on the demonstration data over 3,039 tooltips, at four viewports
  from 1024 × 768 to 1920 × 1080 in six views, before the 20% cap was added:

  - all 2,646 plain readouts sat beside the pointer;
  - none of the 393 explanations covered any part of its chart;
  - no tip was clipped, covered, off-screen or on the pointer.

  The opt-in Playwright test (`CALOSRV_BROWSER_TESTS=1 pytest
  tests/test_browser_tooltip.py`) asserts those properties, and since the cap
  it also asserts that a readout beside the pointer covers at most 20% of the
  plot and that one which left does not overlap it; `tests/test_browser_models.py`
  holds the Models page's paired projections to the same cap
  (`PROJECTION_READOUT_SHARE`). It hovers a 9 × 7
  grid, a row sweep and every centroid and anchor marker, on all four charts,
  in all four frames, at 1600 × 900, 1280 × 800 and 1024 × 768. It also
  replays three cases on their own: a scroll then a drag, a window that
  shrinks, and a scroll while a tip shows.
- **Auto-fit RoI weights bins by energy, not by colour code.** Codes are
  monotone in energy but not proportional to it. On the three-decade D-frame
  ramp a bin a tenth as bright as the peak carried two thirds of the peak's
  weight, so the "99% of the energy" box swelled towards the halo. On an
  isometric panel the fitted box is now slid inside the panel rather than
  truncated at its edge, so it keeps 1:1.
- **The isometric letterbox follows the container, not only the window.** Each
  panel has one `ResizeObserver`, debounced to an animation frame. On a resize
  it rebuilds the option from the retained payload and view, and the depth
  panels re-decide whether they can be drawn isometric. `chart.resize()` alone
  left a stale letterbox. Measured: shrinking a card from 234 to 160 px now
  keeps 1:1.

### Direction overlays on the depth panels

This section describes the **Absolute (detector) frame**. In the D-frame (next
section) both overlays give way to two ensemble axes; the legacy per-shower
translated frame draws the individual trajectories from the origin and nothing
else; the Separation-Aligned Local frame draws no direction at all (see
[Per-shower frames: Local, and the legacy translated frame](#per-shower-frames-local-and-the-legacy-translated-frame)).
In the Absolute frame the two overlays are complements, and only one is honest
at a time.

*Selections of 50 events or fewer* get the **individual incident trajectories**,
projected from each event's centroid and (θ, φ) across the fiducial depth.

*Larger selections* get the **centre of deposited energy per depth layer** —
the energy-weighted transverse centroid of the selection's summed deposit in
each layer, measured from the binned data on screen. It is a property of the
summed picture, named as such on the panel and in the drawer, and never a
direction: over many events struck at many places it traces the pooled centre
of the deposit at each depth.

> **No averaged trajectory is drawn over the whole face.** Azimuth is circular,
> and its mean resultant length R̄ is 0.012 over the full dataset, 0.042 for a
> 122-event window and 0.178 even for 7 events: the direction is near-uniform at
> every reachable selection size, so an "average" would point somewhere
> arbitrary while looking authoritative. The panel states the measured R̄
> instead. For the same reason the energy centre is withheld below the
> trajectory threshold — averaging the position of a handful of showers that
> sit in different places has no common centre to converge on.

**Where the directions point.** The azimuth is uniform over the face, but not
random. Measured on the production event table (`overlays.pointing`, printed
on the depth panels and in their drawers): every shower's incident direction
points back at the detector origin — its azimuth equals the azimuth of its own
position, φ = atan2(y, x), with a resultant length of 1.000, and tan θ · z = r
(the 3-D centroid's r / tan θ is 3,860 mm against its own z of 3,892 mm). The
residual against the radial line through the centroid is 1.8° SD. The azimuth
is uniform only because the entry positions are; conditioned on position it is
nearly deterministic.

**The windowed ensemble axis** (`GET /api/window-axis`,
`query/window_axis.py`) follows from that. When a depth panel is zoomed to a
transverse window narrower than the detector, the client asks for the selected
events whose entry point — the 3-D centroid back-projected to the front face
along its incident direction, as the per-event trajectories are drawn — lies in
the window, and draws their **mean trajectory** through their mean entry point
(dashed), the **sample SD of their per-event trajectories at each depth** as an
uncapped band (entry spread, slope spread and their covariance, exact at nine
depth stations) and the **Student-t 95 % interval of the mean** as a thin
envelope — two quantities, two marks, each named in its tooltip. Measured on
production in 300 mm windows of the entry position: 262 windows hold 20 events
or more, the median azimuth resultant is 0.999, the mean lean over the 1,210 mm
depth 346 mm against a 33 mm dispersion band, and the 95 % envelope of the mean
about 8 mm at N = 65. The **gate is the lean against the fan**: the axis is
drawn in full when |mean slope| ≥ SD of the slopes and faded otherwise, with
the reason stated ("these showers go straight on average within that fan"). A
Rayleigh test on the azimuth is reported but not used as the gate, because a
strip across the face flips the azimuth between 0 and π while every projected
slope stays coherent. One event gets its own trajectory, labelled as such and
without a band; two get a band with one degree of freedom, said so; fewer than
twenty are labelled weak. Nothing of the kind is drawn at full extent, and
Reset drops it. The request is debounced like the sliders and costs one scan
of the event table.

### Separation-Aligned (D-Frame): the Translated view (API canonical)

The **Reference Frame** control offers this view as *Separation-Aligned
(D-Frame) › Translated*, beside the Absolute one; the API calls it
`frame=canonical`, and the rest of this document calls it the D-frame
(formerly "the canonical centre-of-separation frame"). In the absolute
(detector) frame every event's two showers land wherever the particles struck,
so a multi-event selection is a smear across the 5.2 m face, and the
prohibition above holds with no exception: with φ uniform, nothing can be
averaged. The D-frame changes the premise rather than bending the rule. Every selected event is moved
by one **rigid-body motion** — an element of SE(3), so distances, transverse
widths and longitudinal profiles are preserved exactly — such that its two
showers sit at the same place as every other event's, and only then is anything
summed or averaged. Whether the result is coherent is then *measured*, and the
measurement is printed beside every mark it licenses.

**The transform.** The dataset's `centroid_A/B_*` columns are
**three-dimensional whole-shower centroids** — their z sits a median 253 mm
behind the front face — and `centroid_AB_distance` is their 3-D distance, so
neither is an entry point. Each centroid is therefore back-projected to the
front face z_f along its own incident direction:

```
entry_S = c_S − (c_S,z − z_f) · tan θ_S · (cos φ_S, sin φ_S)          S ∈ {A, B}
```

The sign is fixed by the data, not by convention: this lands a median 82 mm (A)
and 69 mm (B) from the per-event energy-weighted entrance-slab centroid, the
opposite sign 181 mm. The midpoint of the two entry points becomes the origin,
ψ = atan2(entry_B − entry_A) turns the A→B separation onto +x′ by the passive
rotation R_z(−ψ) — `x′ = cos ψ·(x − x₀) + sin ψ·(y − y₀)`,
`y′ = −sin ψ·(x − x₀) + cos ψ·(y − y₀)` — and z′ = z − z_f puts the front face
at zero. B then sits at (+D_entry/2, 0) and A at (−D_entry/2, 0); direction
vectors transform by the linear part alone. Because the rotation is per event
it cannot be applied to a cached lab bundle after the fact, so it runs **inside
DuckDB**: each hit row joins a 20 k-row CTE of frame parameters, and the
rotated position is binned with the same single-scan `GROUPING SETS` pattern as
the lab query. Bin indices become millimetres only through the coordinate
arrays measured at ingest, bound as list parameters — never by multiplying a
pitch.

The frame is checked on the data it is applied to. Per-event D-frame slab
centroids sit at y′ = +0.3 / −0.0 mm (median), and at x′ + D_entry/2 = +19 mm
(A), x′ − D_entry/2 = +17 mm (B). That x′ offset is a **mixture, not a
constant** — outward by −22 / +24 mm for D_entry > 500 mm, and +44 / +9 mm for
D_entry < 80 mm, where overlapping deposits drag the A slab centroid toward B —
so the payload reports the measured anchor–centroid offsets per selection
(`frame.anchor_offsets`) and the entry panel's Details drawer prints them.

**The anchor is a stated, measured choice.** The frame shipped anchored on
each shower's 3-D centroid back-projected to the front face along its incident
direction; the reference notebook's origin is the shower's first-layer entry
point P₀ (the energy-weighted centroid of its first populated layer, at that
layer's z). Both are in the event table, so `anchor=backprojected|p0` on
`frame=canonical` (the sidebar's *Entry anchor* radio under Translated, whose
ⓘ button opens a popup with both definitions, their formulas, the distance
measured between them on the current selection and what switching changes;
`frame_views.js: anchorExplainer`) picks either: with `p0` the origin is the midpoint of the two P₀, each back-projected
the short distance (z₀ − z_f) tan θ to the front face, and ψ the azimuth
between them; `z′ = z − z_f` is untouched. The two definitions are measured
against each other on every dataset — at ingest (`anchor_residual` in the
verification report) and on every D-frame response (`frame.anchor_residual`,
printed by the entry panel's Details drawer and named in the export file name
as `canonical_p0`). On production `hits_all_models.csv` they land a median
46.5 mm (A) / 45.2 mm (B) apart at the face, p90 133.5 / 132.6 mm, with
9,620 / 9,382 of 20,268 showers more than one 48.6 mm cell footprint apart;
on the two-event demonstration file, 178 / 180 mm. The payload's
`frame.anchor` names the definition in use (`entry_backprojection` or
`p0_backprojection`), and D_entry is reported for whichever is in use. The
default stays the back-projected centroid.

**Part of the ensemble band is geometry.** In detector coordinates the incident
directions point at the origin (see [Direction overlays on the depth
panels](#direction-overlays-on-the-depth-panels)), so a shower's lean grows with
its radius; the dispersion band around each D-frame axis therefore mixes the
spread of entry radii across the selected events with anything physical. The
response measures the pointing residual per selection (`overlays.pointing`)
and the depth panels' drawers say so.

**D_entry is not D.** The transverse separation of the two entry points at the
face is the frame's own separation; it differs from the slider's 3-D centroid
distance by up to 726 mm per event — over the full dataset ⟨D_entry⟩ = 757 mm
against ⟨D⟩ = 842 mm (production v37: 765 / 854 mm, and 157 / 249 mm in the
D 240–260 mm slice). Both
are always printed side by side, the mean D_entry with the Student-t 95 %
interval of the mean, named as such (the payload also carries the bare standard
error; at N = 2 the two differ by a factor 12.7). The entry panel writes its
horizontal axis as **D** — the signed x′ coordinate along the A→B separation,
with the anchors at D = ∓⟨D_entry⟩/2 and tick values in mm — while D itself,
the slider's quantity, stays the absolute-frame 3-D centroid distance
`centroid_AB_distance`; the depth panels keep x′, y′ and z′. The 57 events
(0.28%) with no
A centroid have no frame and are excluded from N and counted, even when
*include undefined D* admits them elsewhere. Below D_entry = 80 mm — 32.3% of
all events — the rotation angle is dominated by the ~80 mm anchor residual and
is effectively random: those events' energy enters ⟨ρ⟩ averaged over azimuth,
and their randomly oriented directions enter the ensemble-axis statistics (R̄′,
the Rayleigh p, the dispersion band) as noise that lowers R̄′ and raises p. The
count is disclosed in the panel's Details drawer.

**A hit is a cell, and rotation does not smooth the lattice.** The physical
footprint is measured from the populated `(ix, iy)` occupancy of the projection
table — the pitch between adjacent cells sharing a row or a column, read from
the lowest gap cluster — as **48.27 mm in x and 48.6 mm in y**, on the
production lattice and on the demonstration file alike. The sorted union of x
coordinates shows 4.4 mm "twins" because rows come in blocks of four offset by
4.4 mm between blocks; those twins are not cells, and the ~24 mm midpoint tiles
of the one-dimensional lattice axes are bookkeeping, not footprint. (A
lattice-only fallback exists for a table with no two cells in one row; it
over-estimates a sparse lattice, which is why occupancy is preferred.) Each
cell's energy is split into k × k equal sub-deposits over that footprint before
rotation and binning into a 20 mm grid, which conserves the total exactly for
any k and leaves no hole under a rotated footprint from k = 4. The obvious
shortcut — point-binning the rotated centres (k = 1) and trusting 20 000
near-uniform rotation angles (R̄(ψ) = 0.014) to fill the gaps — was tried and
**measured**: a real comb remains, with a lag-1 autocorrelation of the
shower-core row of −0.26 over 20 143 co-registered events and −0.47 on a
221-event slice, against +0.4 to +0.7 at k ≥ 2. So k ≥ 2 is enforced, k rises
to 6 as the selection shrinks under a 3 × 10⁷ sub-row budget. The comb is
measured on **every response**, with two instruments run on the uncropped
accumulation raster:

- the occupancy lag-1 that the lab XY panel uses;
- the lag-1 of the detrended energy profiles of the brightest row and of the
  column sums. This second one is needed because a footprint splat fills every
  bin under a cell by construction, so occupancy alone cannot see a residual
  *intensity* comb.

Either below −0.10 is reported as a comb, with one fixed wording in
`meta.stagger` and `frame.comb`. The measurement is taken on the **raw grid,
before any display smoothing**, and `frame.comb.measured_on` says so. The
verdict is therefore identical in both display modes. This order matters:
smoothing was measured to hide a real k = 1 comb in 7 of 7 tests. Native Grid
shows a comb as measured. Continuous Field smooths it for display, which hides
it without removing it, so the note never advises smoothing it away. The payload
also states whether the splat is gap-free at the chosen k
(`frame.subsample_regime`: `sub-cell-sampling-gapless` or
`sub-cell-sampling-partial`). That field was called `frame.smoothing` before the
display kernels existed, and was renamed so the two cannot be confused.

**What a bin holds.** The value is the ensemble-averaged projected surface
density ⟨ρ⟩ = ΣE / (N · ΔA) in **GeV mm⁻² per event**:

- dividing by N makes selections of different size comparable;
- dividing by the bin area makes the value independent of the display
  resolution;
- every display operator conserves the sum and cannot raise any bin above the
  raw peak. Those operators are Native Grid's box merge and both Continuous
  Field kernels (see [Display modes in the Separation-Aligned frames](#display-modes-in-the-separation-aligned-frames)).
  Each is a non-negative partition of unity on the uniform grid, so a displayed
  bin is a weighted *mean* of raw 20 mm bins.

Colour is ⟨ρ⟩ / ρ_ref on a log₁₀ ramp over [−3, max(0, log₁₀ of the peak ratio)],
labelled **Average hit density (a.u.)**. The reference is always a **raw 20 mm
accumulation-grid peak** (`frame.rho.basis`), never the peak of the displayed
field. It is a proven upper bound on everything drawn, and it does not depend on
R, the kernel or the window, so a normalisation stays comparable across
selections. Which peak is chosen in the sidebar:

- the selection's own peak (default, `rho_norm=selection`, badge *Autoscaled*),
  so every selection uses the whole ramp;
- the dataset's peak (`rho_norm=dataset`, computed once from the cached
  full-range bundle), so colours compare across D slices. There, superposed
  showers reach about twice an isolated peak, and the ramp extends above 10⁰
  rather than saturating.

Because vmax always covers the peak, `clipped_high` is omitted in this mode.
`frame.rho` also reports each panel's `displayed_peak`, its `displayed_over_ref`,
and `kernel_attenuation`, the displayed peak over that panel's own raw peak.
Measured at R = 150:

| Selection | X′Y′ `kernel_attenuation` | X′Z′ `kernel_attenuation` |
|---|---|---|
| D 257–258 mm, N = 5 | 0.756 | 0.884 |
| full production range | 0.912 | 0.978 |
| Native Grid, any selection | 1.0 | 1.0 |

Under dataset normalisation a notice quotes `kernel_attenuation`, because part
of a colour difference between two selections can then be the display rather
than the physics. It does not quote `displayed_over_ref`, which is dominated by
how bright the selection is relative to the dataset. For example, the ratio is
1.95 on X′Y′ for the N = 5 slice, whose ramp top therefore rises to 10⁰·²⁹.

ρ_ref is kept in the status bar, and every panel's Details drawer states it
with its reference.
The exact `topk` values ship in physical units and `total` keeps its GeV
meaning, so the physical density can always be recovered from a picture drawn in
a.u. Tooltips show both. The top-k list is the *displayed* field, labelled
"(exact, reconstructed)" in Continuous Field, and never offers a bin that is not
drawn.

**The display floor is transparent.** Bins below 10⁻³ of ρ_ref are **not
drawn**. They used to be clamped into colour code 1, the opaque bottom of the
ramp, which painted the whole crop as a dark-purple rectangle around the
showers.

- **Codes.** A co-registered panel now reserves code 1 (`below_code`) for them. The
  ramp starts at `min_code` 2 with 253 levels, and code 0 still means empty.
- **Counts.** The payload counts the undrawn bins (`below_floor_cells`, equal to
  `scale.clipped_low`) and gives the share of the panel's in-window
  reconstructed energy they hold (`below_floor_energy_fraction`). It states the
  rule as `scale.floor: "transparent"` and `scale.floor_ratio: 0.001`.
- **The fade on screen.** A hard edge would still draw a rim. The dark end of
  Viridis against the `#1c2128` card is only 1.06:1 in WCAG contrast but
  ΔE76 ≈ 49 in colour. So the bottom half decade, 10⁻³ to 10⁻²·⁵, fades
  linearly in alpha (`THEME.floorFadeDecades` 0.5), and the field dissolves into
  the card. The legend mirrors the fade with translucent stops and reads
  "10⁻³ a.u. — fades to not drawn".
- **Nothing opaque is drawn below 3:1.** Over that fade the colour climbs from
  the palette's first colour to its first colour with 3:1 contrast against the
  card (Viridis `#2c728e`, 3.01:1, at t = 0.376), and reaches it where the fade
  turns opaque, less one code step (`TAPER_LEGIBLE` 0.97: without that step an
  8-bit code at 99.6% alpha rounded onto a 2.97:1 colour). Everything above the
  fade runs from that colour to the end of the palette's 3:1 run. This is the screen rule for
  every sequential ramp (see [Display channels](#display-channels)); print keeps
  the full ramp.
- **Print.** The token is 0 in print, which gives a hard contour. The exported
  figure carries no caption, so the drawer's floor sentence — the edge of the
  colour is the display floor, not the edge of the shower — is what the
  manuscript caption must repeat; the ramp's print title names the floor.
- **Grad-CAM** keeps the lab's fixed 0–1 scale and gets an `attention_mask`
  block instead:
  - *Continuous Field* masks attention where the *reconstructed* energy density
    is below the same floor, because the kernel tails carry attention into bins
    no measured energy reached. At N = 5, 8,753 X′Y′ bins are masked, holding
    20% of the reconstructed hit count.
  - *Native Grid* leaves only hitless bins transparent, as the lab does. The
    audit view never hides attention measured on real hits.

**Where the picture is cropped.** The accumulation window is planned from the
selection's own kinematics — `half_x = max(D_entry)/2 + M`, `half_y = M`,
`M = depth · tan θ_max + 500 mm` (twice the p90 energy-weighted RMS radius of a
shower about its axis), snapped up to whole bins — so it is lossless up to a
counted remainder: on the full production selection **±3980 × ±1380 mm**
(398 × 138 bins) with 0.008% of the energy outside. What is *sent* is narrower.
Each panel is cropped along each transverse axis to a window **symmetric about
the origin**, x′ ∈ ±Δx and y′ ∈ ±Δy (`query/window.py: symmetric_axis`).
X′Y′ uses the slab energy; the depth panels use their own full-depth energy.

1. Δ is the larger excursion of the energy-weighted **0.1st–99.9th**
   percentile.
2. It is raised to a floor. While the range is provisional (N < 20) the floor
   is **200 mm**, the median single-shower |y′| p98 of the entrance slab, so a
   handful of events cannot shrink the view below one shower's own extent.
   Above that it is **two cell footprints**, 2 × 48.6 mm snapped to 100 mm,
   the physical resolution. The robust floor is lower on purpose. D-only
   slices at N ≥ 20 measure y′ ±360 mm or more, but energy cuts go well below
   200 mm: E₁, E₂ < 2 GeV (N = 691) measures ±160 mm, < 1.5 GeV (N = 643)
   ±100 mm and < 1 GeV (N = 468) ±80 mm, which the 100 mm floor holds. A fixed
   200 mm floor would widen them 1.25–2.5× for no statistical reason.
3. It is snapped outward to whole 20 mm bins.
4. It is clamped to the accumulation window.

The origin is the midpoint of the two anchors, so a centred window keeps it in
the middle of the panel. The X′Y′ panel's 1:1 aspect comes from the letterbox,
not from forcing a square. `frame.fit.<panel>.<row|col>` carries the
`percentile_range` before centring, `half_width`, `floored` and `clamped`; the
Details drawer prints the window as `D ±480 mm` on the entry panel and
`x′ ±480 mm` on X′Z′, and names a floor or a clamp where one applied. Measured on production v37:

| Selection | N | X′Y′ window | X′Y′ energy outside (raw grid) |
|---|---|---|---|
| D 243.63–243.85 mm | 5 | ±480 × ±380 mm | 0.18% |
| D 20–40 mm | 549 | ±360 × ±380 mm | 0.33% |
| full range | 20,143 | ±2420 × ±520 mm | 0.33% |

This is a recorded exception to the CLAUDE.md 1st–99th default. The panels do
not draw below 10⁻³ ρ_ref, and a 1–99 crop cut the halo where it was still
15–110× above that floor. The colour then ended at the window edge and looked
like the edge of the shower: 14–99% of the X′Y′ boundary bins were above the
floor, against 2–11% now.

The disclosure is unchanged in kind. The energy outside each window is reported
in its Details drawer, measured *after* display reconstruction
(`energy_fraction_outside_window`), because a kernel moves a little energy
across the window edge in both directions. The raw-grid figure travels beside
it (`energy_fraction_outside_window_raw`). Across seven production selections
the two differ by at most 0.007 percentage points.

Depth is never cropped: the longitudinal profile, leakage into the back layers
included, is what the depth panels exist to show. Below 20 co-registered events
the fitted range is labelled **provisional** on the axis itself.

**The 100 KB budget covers the whole response.**

- **The panel guard.** It lowers R in 25% steps in continuous mode, or merges
  transverse bins pairwise in native mode: 2 × 2 on X′Y′, 2 × 1 on the depth
  panels, because depth layers are never merged. It allows twelve attempts.
  It degrades only when another attempt follows, so every notice describes a
  step the returned panels actually took. If the last attempt is still over,
  it says so.
- **Why the guard is not enough.** The envelope around the panels (frame block,
  meta, centroids, notices) adds 13–16 KB. Panels that passed their own guard
  still gave a 108,775-byte response for the five-event slice D 257–258 mm.
- **The whole-response check.** `api/frame_canonical.py` measures the assembled
  response exactly as FastAPI serialises it (`density.wire_size`: compact,
  UTF-8, no ASCII escapes). If it reaches 100,000 bytes, the panels are
  re-rendered from the cached bundle one guard step at a time, continuing the
  guard's sequence from the state it served, and each candidate is measured
  the same way until one fits. That slice then ships at R = 112. Every step is
  disclosed as a notice.
- **Why each candidate is measured.** An earlier version derived a panel limit
  from the compact wire size and compared it with the guard's deliberately
  over-counted panel measure. On D 20–40 mm that stepped any request above
  R = 150 past 150 to R = 112, although R = 150 serves 98,377 bytes, so asking
  for more detail served less. Measuring what is actually served keeps a
  higher request at or above the R the default request gets.

**What is drawn.** Exactly two dashed ensemble axes on the depth panels, from
(∓⟨D_entry⟩/2, 0, 0) along the mean per-event projected slope s = u′_t / u′_z.
Each carries two separate marks, because they answer different questions and
differ by √N: a shaded wedge for the **sample SD** of the per-event slopes
(dispersion — where individual showers go) and a thin envelope for the
**Student-t 95% interval of the mean** (uncertainty — how well the axis is
known), from the same t table the energy panel uses. R̄′, the Rayleigh
p = exp(−N R̄′²) and N are printed beside each axis; an axis with p > 0.05 is
drawn **faded, never hidden**, because there are always exactly two. The
coherence that licenses the mark is measured, not assumed. On the all-models
file R̄′_A / R̄′_B is 0.779 / 0.819 for D 2700–3000 mm (N = 500; ⟨û′_A⟩ → −x′ and
⟨û′_B⟩ → +x′: the two showers diverge with depth), 0.123 / 0.125 for D 20–40 mm
(N = 950, every event below the 80 mm ill-conditioning threshold, still
Rayleigh p ≈ 5 × 10⁻⁷), and 0.156 / 0.237 over the full selection, against 0.012
in the absolute (detector) frame. (Production v37: 0.779 / 0.819, 0.339 / 0.340 and
0.024 / 0.371.)

**The marks near the cores are deliberately light.** By construction the anchors
sit on the two brightest places in the picture. The earlier marks were 15 px
filled markers, a 6 px spread bar and a floating ⟨D_entry⟩ badge, and they
covered exactly the bins the panel exists to show. They are drawn by
`static/js/panels/canonical_overlays.js`:

- **Anchors** (diamond A, circle B) are 13 px open outlines, with a transparent
  fill and the shower's colour at 0.75 opacity. They are not ECharts'
  `emptyDiamond` / `emptyCircle`, which are filled white and forced to a 2 px
  stroke. On Y′Z′, where both anchors project onto the origin, one merged open
  circle stands for the two. The tooltip gives the t-based 95% interval of the
  mean anchor.
- **The spread bar** stays, because CLAUDE.md requires dispersion to be
  encoded. It is uncapped, 2.5 px wide at 0.3 opacity, and its tooltip names it
  as the sample SD of D_entry/2 across events: dispersion, not the uncertainty
  of the mean.
- **The separation rule** between the anchors is a 1 px dashed line,
  translucent white on screen and `#6b7280` in print. Its tooltip carries
  ⟨D_entry⟩ with its Student-t 95% interval and N, and ⟨D⟩ beside it. The badge
  is gone. The same ⟨D_entry⟩ ± interval is printed in the X′Y′ panel tag, in a
  `.sym` span so the tag's uppercase transform leaves the symbols alone.
- **The measured centroid sets** are all small (7 px) and told apart by shape,
  with the shower carried by colour:
  - a filled dot for the ground-truth `truth_voxel`;
  - an open ring for the prediction `pred_voxel`;
  - a plus for `canonical_mean`, the dataset centroids averaged *after*
    co-registration.

  The drawer's *What is drawn* and *Marks and legend* sections name each set
  by the payload's own label (`centroidLegend`), so the tooltips and the
  drawer never disagree. `truth_dataset`, an
  absolute-frame mean of positions, is omitted here, because averaging positions
  across events that sit in different places is exactly what this frame exists
  to avoid.
- **Plot chrome.** The co-registered plots are framed by a thin border drawn above
  the raster. The axis lines no longer sit on zero: a symmetric window would
  otherwise put a crosshair through the middle of both showers.

Thin rules mark the front and back faces at z′ = 0 and 1209.5 mm. **Not drawn**:
individual trajectories (the ensemble axes replace them), and the transverse
detector outline, which rotates with each event and has no ensemble image. The
Details drawer says so.

**Low N.** Numbers are reported from N ≥ 2 and marks are gated separately, as
in plot 4. With no framed event the panels are empty and say so. A single event
gets its own two incident lines labelled *single event, not an ensemble*, no
band, and R̄′, p and σ stated as undefined. From N = 2 the axes, band and
envelope are drawn, with R̄′ / p labelled `weak (N = …)` below 20 and σ labelled
`1 d.o.f.` at N = 2. Because ρ_ref defaults to the selection peak, a low-N slice
never rescales any other view.

**Cost.** k = 1 would have answered the full 22.5 M-row v37 selection in
0.54 s and was rejected on the comb measurement above. At k = 2 the full
24.2 M-row all-models selection (~97 M sub-deposit rows) costs **1.7 s cold**
and its 10% drag preview 0.27 s. The scan runs as two queries, the entrance
slab and the depth grouping sets, with every plane divided by k² once per hit
and outside sub-deposits keyed −1: the earlier single pass with `FILTER`
aggregates, which DuckDB evaluates in every grouping set, measured 5.9–6.3 s.
Bundles are cached per network under a key that includes the window, k and
footprint, and the full-range bundle is **pre-warmed in a background thread** at
server start-up and after each successful ingest, before the translated and
local ones, one scan at a time. Sampled drag previews cap k at 2.
Depth panels are drawn at a 1:1 metric aspect when the fitted spans allow it
(the letterboxed plot keeps at least 45% of the card width and the span ratio
lies within [0.45, 1.3]), otherwise with true extents and the Details drawer
saying so;
the decision is re-taken whenever the card resizes.
The zoom window survives slider ticks within one frame — the fitted extents
move on every tick, and resetting the view each time would make zooming during
a drag impossible — and is reset only on a change of frame or experiment.

**API.**

- **Parameters.** `GET /api/projections?frame=lab|canonical` defaults to `lab`.
  `frame=canonical` requires `coord_system=lab`: the D-frame is built
  from absolute (detector) coordinates, and its CAM channels read the absolute-frame
  networks (`model=`). It also takes
  `rho_norm=selection|dataset` and `display=native|continuous`, whose server
  default stays `native` in every frame. The interface always sends `display`
  explicitly. `lock_scale` and `scale_mode` are accepted but ignored in the
  D-frame.
- **The envelope.** The `frame=canonical` envelope keeps every `lab` key and adds:
  - a `frame` block: anchor definition, window, fit, footprint, k,
    `subsample_regime`, comb (with `measured_on`), ρ_ref (with `basis`,
    `displayed_peak`, `displayed_over_ref`, `kernel_attenuation`),
    `reconstruction`, D_entry / D moments, per-shower slopes with SD, R̄′ and p,
    and anchor offsets;
  - `overlays.ensemble_axes` and `overlays.anchors`;
  - an axis `symbol` (x′ / y′ / z′);
  - `scale.rho_ref / rho_unit / decades / norm / floor / floor_ratio`;
  - per panel: `below_code`, `min_code` 2, `below_floor_cells`,
    `below_floor_energy_fraction`, `kernel`, `total` (in-window GeV after
    reconstruction), `total_energy_all_gev`, `energy_outside_window_gev`,
    `energy_fraction_outside_window` and its `_raw` twin, `n_events`,
    `topk_unit`, `bin_area_mm2` and `rho_peak`; Grad-CAM panels also carry
    `attention_mask {rule, cells, hit_fraction, max_attention}`;
  - `meta.resolution.kernel`: `{type, sigma_mm, bin_spread_rms_mm, separable,
    conservative, non_negative}`.
- **`frame.reconstruction`** states what the display did to the raw grid:
  - `display`, `kernel`, `label`;
  - `sigma_mm`, null unless Gaussian, and `bin_spread_rms_mm`;
  - `blur_rms_mm {x, y}`, the RMS spread of one cell's energy on the display
    about the cell centre, √(w²(1 − 1/k²)/12 + p²/12 + spread²): the discrete
    k × k footprint term (the continuous w/√12 would overstate it by 15% at
    k = 2), the point binning of each sub-deposit into its p = 20 mm bin, and
    the kernel's spread per bin. A Monte Carlo of randomly rotated cells,
    binned as the scan bins them, reproduces it to 0.1 mm for the box, tent
    and Gaussian; without the binning term it ran 5–8% low;
  - `subsample_k`, `gaussian_below_n` 50, and `axes ["x′","y′"]`;
  - `depth`, which is always "native sampling layers, never smoothed or
    interpolated";
  - `conservative`, `floor_ratio`;
  - per-panel `energy_fraction_outside` and `below_floor`;
  - a one-sentence `note`.

  The per-panel figures are read back from the rendered payloads, so the block
  cannot disagree with them.
- **Other endpoints.** `GET /api/experiments` lists per experiment the
  `frames`, `coord_systems`, `models` and `channels` it serves, its `schema`
  and its `archive` (parts, rows, bytes), and the co-registered caches under
  `compute.canonical_cache`, `trans_cache` and `local_cache`.
  `CALOSRV_CANONICAL_CACHE_ENTRIES` (default 32) sizes each LRU.

### Reference frames

| Interface label | API `(coord_system, frame)` | Coordinates | Co-registers | Accumulation | Direction overlay | D |
|---|---|---|---|---|---|---|
| **Absolute** (default) | `(lab, lab)` | `x, y, z` | nothing | the detector lattice, one bin per cell | trajectories ≤ 50 events, else measured shower axes | `centroid_AB_distance` |
| **Separation-Aligned › Translated** (the D-frame) | `(lab, canonical)` | absolute, co-registered in SE(3) | each event on the midpoint of its entry points | 20 mm grid, k × k sub-deposits | two ensemble axes with band and envelope | the same; D_entry reported beside it, and the entry panel's horizontal axis written D |
| **Separation-Aligned › Local** | `(local, lab)` | `x_local, y_local, z_local` | each shower on P₀ and its own R(θ, φ) | 20 mm × 20.5 mm grid, rotated k × k × k_z sub-deposits | none: w is the direction by construction | the same |
| **Per-shower translated** (legacy, link-only: `#frame=trans` or a saved default) | `(trans, lab)` | `x_trans, y_trans`, own-shower layer | each shower on its own entry point P₀ | 20 mm grid, exact box overlap | trajectories from the origin ≤ 50 events, else R̄ stated | the same |

`state.js: apiFrame` is the only UI → API mapping, so the two parameters can
never disagree; `labels.js: FRAME_TREE` maps the flat key to the sidebar's two
tiers and back. The network behind the CAM channels, the metric cards and the
energy panel follows the coordinate system: absolute-frame networks for the
Absolute frame and the D-frame, the `trans` and `local` networks for the two
per-shower frames.

### Per-shower frames: Local, and the legacy translated frame

**What they are.** Two frames superimpose the showers at their own entry
points: *Local* — the sidebar's *Separation-Aligned (D-Frame) › Local*, API
`local` — and *Per-shower translated* — the legacy frame, API `trans`, with no
sidebar radio of its own; plain "Translated" in the sidebar now names the
D-frame. *Per-shower translated* moves every hit by its own shower's entry
point P₀ — the energy-weighted (x, y) centroid of that shower's first populated
layer, at that layer's z — without rotation. *Local* then rotates it by that
shower's own R(θ, φ), so its incident direction lies along +w. Both are the input file's
own `*_trans` / `*_local` coordinates, verified at ingest to be exactly that
transform. The two showers of every event are therefore **superimposed at the
origin**; the 422 `'A+B'` rows sit there too and are counted with shower B.

**Coordinates: the file's, or the motions'.** Both frames are rigid motions
of the laboratory lattice — `p − P₀`, and `R(θ, φ)(p − P₀)` with
`R = R_y(θ) R_z(φ)`, the notebook's — and `grid/frame.py` holds that SE(3)
element (`Se3`, `rotation_matrix`, `per_shower_translated`, `per_shower_local`,
`per_event_canonical` for the D-frame's `R(0, ψ)`). Every per-shower scan
joins one shared frame CTE (`query/frame_sql.py`) that applies the motion to
the lattice ordinals beside the file's own `*_trans` / `*_local` columns, and
each response reports the largest difference between the two over the
selection (`frame.coordinates`: source, residual, the 0.01 mm tolerance, and
whether it is met; the drawer prints it). `coordinates=file` (the default)
bins the file's columns; `coordinates=computed` bins the motion's, for a file
that carries no such columns or one whose columns are in doubt. On production
the residual is 0.05 µm over 40,650 showers; at ingest the same check is
`local_rotation`, and `p0_definition` now verifies that P₀ *is* the
first-layer energy-weighted centroid (an 'A+B' cell counts for both showers),
failing above 0.01 mm on a file the sanitiser left whole and warning, since
it cannot be confirmed, on one it did not.

**Accumulation, by footprint rather than point.** A hit is a 48.27 × 48.6 mm
cell, and point-binning a co-registered centre combs (CLAUDE.md section 2):

- *Per-shower translated* does not rotate, so a footprint stays an axis-aligned box and its
  area-weighted overlap with the 20 mm grid is computed **exactly**. The overlap
  of a box with the bins it touches is affine in the position of its left edge
  within its first bin, so the SQL aggregates four moments per hit keyed by
  (first bin, side) and NumPy expands them with two coefficient matrices per
  axis (`query/shower_frames.py: box_overlap_operator`). It matches a
  brute-force overlap to 10⁻¹² of the total.
- *Local* splits each cell's footprint box — including the 20.5 mm layer
  pitch — into k × k × k_z sub-deposits (k ≥ 2 from the row budget, k_z = 2)
  and rotates their offsets with the shower before binning. Depth w is binned at
  the layer pitch, so near-normal incidence maps each layer onto one bin.

Depth is each shower's own sampling layers counted from its first in
*Per-shower translated*, and uniform w bins in *Local*; neither is ever smoothed. The grid
is planned per dataset from the ingest-time energy-weighted 10⁻⁴ and 0.9999
quantiles plus half a footprint (`grid/bounds.py`), so every selection shares
its bin boundaries; 0.027% (*Per-shower translated*) and 0.035% (*Local*) of
the production energy falls outside it, counted. A hit whose footprint is not
wholly inside the per-shower translated grid is counted outside in every panel
alike.

**Everything else is the D-frame's rules:** symmetric display windows at
the energy-weighted 0.1st–99.9th percentile with the same floors and 20 mm
snapping; the Continuous Field kernel on the transverse axes only, Gaussian
below N = 50 and tent above; ⟨ρ⟩ = ΣE / (N·ΔA), which here sums both showers of
an event; and the comb measured on every response on the raw uncropped raster —
along both transverse axes, and along w in *Local*.

**No separation, an offset.** The voxel-weighted centroid pair measures the A–B
offset of two ensembles each relative to its own entry point: `offset_mm`, never
a separation, which stays the absolute-frame D. `centroids.frame_mean` is the mean
per-event centroid (`centroid_*_trans` / `_local`) with its sample SD, drawn as a
faint uncapped cross, and its Student-t 95% interval of the mean, drawn as capped
whiskers — two quantities, two marks. At N = 1 the marker is labelled as that
single event's own centroid and no cross or whisker is drawn. A mark end that
would leave the window is clamped to its edge, with a caret in place of the
cap and the full range in the tooltip, and the Details drawer counts such ends.
Energy that falls outside the accumulation grid altogether
(`frame.window.energy_fraction_outside`, `hits_outside`) is stated beside each
panel's window share.

**Directions.** *Per-shower translated* keeps every shower's absolute-frame
azimuth, which is
near-uniform (R̄ = 0.012), so it draws the individual incident directions from
the origin for ≤ 50 events and otherwise states R̄. In *Local* every direction
is +w by construction, so an axis or a Rayleigh statistic could carry no
information, and the Details drawer says so.

**Measured on production** (seven selections, N = 3 … 20,268):

| | 1st–99th window | 0.1st–99.9th window (used) |
|---|---|---|
| Entrance-panel boundary bins above the 10⁻³ floor | 22–95% (up to 21 × the floor) | 0–6.4% |
| Energy outside the window | 2.3–3.3% | 0.15–0.31% |

| Comb (worst lag-1 per axis; a comb is < −0.10) | Transverse | Depth |
|---|---|---|
| Per-shower translated, box overlap | +0.14 … +0.59 | — |
| Local, k × k × 2 | +0.05 … +0.67 | +0.11 … +0.92 |
| Local, k × k × 1 | −0.018 … +0.63 | +0.0003 … +0.49 |

No comb is measured at any N, but at k_z = 1 the depth lag-1 falls to +0.0003
(N = 5), so k_z = 2 is kept; it costs 1.1 s on the full selection.

**Cost** on the full selection (DuckDB 10 GB, 10 threads): *Per-shower
translated* 0.9–1.0 s
cold and 0.23 s for the drag preview; *Local* 2.5–2.7 s cold and 0.40 s for the
preview; a cached re-render (channel, display mode, R) 23–34 ms. Both are
pre-warmed after the D-frame at start-up. Bundles are 2.7 MB
(*Per-shower translated*, 162 × 132 × 60) and 2.9 MB (*Local*, 150 × 128 × 85).

### The Event Inspector and the compare-frames view

Two views lay nine panels out as the reference notebook's figures do — three
rows of frames by three projections (X–Y, X–Z, Y–Z) — in place of the 2 × 2
ensemble grid (`js/panels/frame_grid.js`; the cards are ordinary cards with
their own Details and Export buttons, ids `event-<frame>-<panel>` and
`compare-<frame>-<panel>`).

**The Event Inspector** (`#event=<n>&shower=a|b`, `GET /api/event`,
`query/event_inspector.py`) is the notebook's per-event comparison figure:
one shower of one event in the original detector coordinates, translated only
(every cell moved by −P₀) and local (moved and rotated by R(θ, φ)). What it
draws:

- **Rasters, not scatters.** The laboratory row is the native lattice, one
  bin per populated cell; the translated row integrates each cell's
  48.27 × 48.6 mm footprint onto a 20 mm grid by exact box overlap; the local
  row splits each footprint (with the 20.5 mm layer pitch) into
  k × k × k_z = 4 × 4 × 2 sub-deposits rotated with the shower, on a 20 mm
  grid with depth at the layer pitch. Every panel projects the whole depth
  (no entrance slab), as the notebook's do, and conserves the shower's energy
  (a test asserts it in all nine). The grids coarsen by doubling, disclosed,
  until the response fits the 100 KB contract; on the demonstration file a
  response is 18–69 KB in about 5 ms.
- **One window.** One half-width for all nine panels: the widest
  energy-weighted 0.1st–99.9th percentile range of the event's cells over x, y,
  z, u, v and w (u and v about the shower's own axis), plus one cell footprint
  so the cells at either end are drawn whole, snapped outward to 20 mm and never
  below 150 mm. Every panel is 1:1, so the tilt reads at its true angle. This is
  the co-registered frames' window (see CLAUDE.md §2) applied to one event. The
  notebook's rule, 1.15 × half the largest extent of the cloud, let one stray
  cell set the window: a single-shower event spanned 3.7 times the detector's
  depth (`query/event_inspector.py`). The cells beyond the window are **counted and not drawn**:
  `frames.<f>.outside_window` gives each frame's cells and energy, `window.rule`
  names them, and each panel's drawer states the energy it leaves out; both
  recorded two-shower events lose none, in any frame. The raster covers only the
  populated part, so a stray cell costs the window, not the payload. Depth is
  cropped to the event, which the ensemble frames never do, and the drawer says
  so. **The Event Inspector keeps this one shared half-width** so its nine panels
  stay square and directly comparable; `GET /api/event?window=per_axis` is the
  Models page's alternative (see [The 3-D views](#the-3-d-views)).
- **One ramp.** Every panel is the projected energy *surface density* in
  GeV per mm² — a cell's energy over its own lattice area, a bin's over its
  grid area — on one logarithmic ramp from the 1st percentile of the shower's
  positive cell densities (the notebook's `vmin`) to its brightest bin; bins
  below the floor are counted and drawn at the lowest colour, which on screen is
  the first colour of the palette that clears 3:1 against the card (see
  [Display channels](#display-channels)); the exported figure keeps the full
  ramp. No per-event *density* claim is made beyond that.
- **Marks.** The incident direction forward (dashed) and extrapolated
  backward (dotted) from the origin; the first-layer plane as a dash-dot rule
  at z = z₀ (original) and Δz = 0 (translated), and on the local X′Z′ panel
  the tilted line w = tan θ · u it maps to; the origin ✕ in the shower's
  colour. They travel as 3-D lines and points in each frame's coordinates and
  the client projects them (`panels/marks.js: projectMarks`). The
  principal-axis tilt — the angle between the energy-weighted principal axis
  of the local cloud and +w, the notebook's check on the rotation — is printed
  in the row label with the event's θ, φ, cell count and P₀, never drawn, and
  is untestable below three cells. No ensemble statistic appears anywhere.
- **The picker.** An event number, Prev / Next within the current selection,
  a shower radio, and *Pick for me*, which reproduces the notebook's
  `_select_events` (`GET /api/event/pick`: events with more hits than the
  selection's mean, the 20 with the largest incident angle, one drawn at
  random; seed 42 first, then the next seed per click) and prints the rule. An
  event outside the current filters is drawn as asked and flagged. The
  coordinates note, the window rule, the ramp rule and any coarsening are the
  panel's Details drawer; the export is the plot alone, named
  `event-<frame>-<panel>_ev<n><A|B>_…`.

**Compare frames** (`#compare=true`, the sidebar checkbox) is the notebook's
ensemble figure: the selection in the Absolute, per-shower translated and
Local frames, one row each, three `/api/projections` requests. Every row is
exactly that frame's own response — its own display mode (native lattice for
Absolute, the Continuous Field for the two co-registered frames), window,
ramp, overlays and Details drawer — so nothing is re-derived for the layout. A
frame the experiment does not serve is named as missing. A pinned event takes
precedence over the comparison; closing it returns to whichever view was on.

### Display channels

| Channel | Per-bin value | Scale | Palette | Floor and clipping | Conserved |
|---|---|---|---|---|---|
| Average Hit Density | ΣE (lab, GeV); ⟨ρ⟩ = ΣE/(N·ΔA) (co-registered) | log₁₀: six decades below the brightest cell (lab); three decades of ρ_ref (co-registered) | the chosen sequential ramp | lab: clipped to the ramp ends, counted; co-registered: below 10⁻³ transparent, counted | yes |
| Grad-CAM Model Attention | energy-weighted mean Grad-CAM, ΣE·G / ΣE (or count-weighted) | linear, fixed 0–1 | sequential | nothing clipped; co-registered Continuous Field masks bins below 10⁻³ ρ_ref, counted | ratio of conserved sums |
| Energy-weighted Grad-CAM | ΣE·G (lab, GeV; co-registered, per event and mm²) | log₁₀, three decades below this selection's raw-grid peak | sequential | below 10⁻³ transparent, counted | yes |
| Shap-CAM Attribution | energy-weighted mean Shap-CAM | linear, −1 … +1 | PuOr | nothing clipped; masking as Grad-CAM | ratio of conserved sums |
| Energy-weighted Shap-CAM | ΣE·S, positive and negative parts kept as separate planes | signed log₁₀, ±(10⁻³ … 1) of the peak \|value\| | PuOr | \|v\| below 10⁻³ transparent, counted | each sign separately |

The CAM column read is `{model}_{absolute|trans|local}_{gradcam|shapcam}`, the
network of the selected model in the selected frame, the D-frame taking
the absolute networks; `meta.cam` names it with its normalisation. Angle- and
energy-network maps are normalised per shower and segmentation maps per event,
so an ensemble map mixes independently normalised maps: it shows *where* a
network attends, not how strongly one event compares with another, and every
CAM caption says so.

**On screen, every sequential ramp starts at its first 3:1 colour.** Viridis'
own first colour, `#440154`, is 1.06:1 against the `#1c2128` card, so a bin at
the bottom of the ramp was drawn and could not be seen. Each sequential ramp is
therefore re-indexed onto the run of its palette that clears 3:1 against the
card (`static/js/scale.js` `legibleSpan` and `rampTable`, built on
`chart_panel.legibleRamp`):

| Palette | 3:1 run on screen (of the palette's range) | First colour of the run |
|---|---|---|
| Viridis | 0.376 – 1 | `#2c728e`, 3.01:1 |
| Cividis | 0.482 – 1 | `#686b6f`, 3.02:1 |
| Plasma | 0.431 – 1 | `#b93389`, 3.00:1 |
| Turbo | 0.102 – 0.859 | `#4464d5`, 3.11:1 (its dark-red top, `#cc2c07` at 3.03:1, is dropped on screen) |

- **Untapered ramps** run over that span alone: the Absolute frame's GeV ramp
  (its code 1 is `#2b738e`, 3.04:1), the Event Inspector's areal densities, the
  3-D cubes' volumetric densities and Grad-CAM's fixed [0, 1].
- **Tapered relative ramps** (the D-frame, the per-shower frames and the 3-D
  ensemble cloud) climb from the palette's first colour to its first 3:1 colour
  across the faded half decade, as described under [the display floor](#separation-aligned-d-frame-the-translated-view-api-canonical).
- **The folded PuOr ramps are unchanged**: they are legible by construction. The
  2-D raw Shap-CAM ramp keeps its border-grey zero, since the number is in the
  readout. The 3-D cubes print no number, so a raw Shap-CAM cube near zero takes
  its sign's first 3:1 colour instead (`#a7550b`, 3.04:1, orange negative;
  `#7560a3`, 3.05:1, purple positive).
- **The colour bar and the raster agree**: the legend's stops are sampled from the
  same table the raster is painted through (`rampTable`; `decode.js` `codeTable`),
  so a bin, a cube and the bar show one colour for one value. Every spatial raster
  of both pages (the 2 × 2, compare-frames, the Event Inspector and the Models
  page's paired projections) is drawn through it.
- **Print and the exporter keep the full ramp**, from the palette's first colour,
  on white: `renderRaster` passes `legible` only for the screen, and the exported
  figure is the plot canvas alone.
- **Disclosure.** The Details drawers say where the screen ramp starts
  (`panel_notes.js` `rampStartNote`, taken from the same `legibleSpan` that paints
  the raster, so the sentence cannot drift from the colours): that the lowest
  drawn colour is the bottom of the colour scale, a bin below the ramp floor
  included, and not the palette's darkest colour. A tapered ramp says it fades in
  across 0.5 decade and reaches its 3:1 colour where the fade turns opaque. It
  appears in the *Marks and legend* section of the 2 × 2 and compare-frames
  panels (the Absolute entry panel's legend section holds only this line) and of
  the Event Inspector. A signed PuOr ramp adds nothing.
- **Why it matters.** In the recorded payloads of the Models page's 3-D event
  (`tests/fixtures/payloads/event_voxels_*.json`), 3,495 of the D-frame event's
  6,000 cubes and every cube of the raw Shap-CAM event were opaque and under 3:1
  before the change; none is now (the smallest is 3.04:1).

**Conservation, measured on production.** ΣE·Grad-CAM and the positive and
negative ΣE·Shap-CAM parts, inside plus outside each grid, equal direct DuckDB
sums over the selected hits to ≤ 3.3 × 10⁻¹³ in all four frames and all three
networks; the served totals are identical at R = 50, 150, 300, 400 and in both
display modes.

**Shap-CAM is signed, so it takes a diverging ramp.** 11–64% of the angle- and
energy-network attributions are negative. ColorBrewer PuOr is used — orange
negative, purple positive — and a signed payload is painted with it whatever
sequential ramp is chosen (the colour-map control is disabled and says why).

- **In print** it is the standard 11-class scheme, whose light centre marks
  zero on white paper.
- **On the dark screen it is folded.** The standard scheme's strongest colours
  vanish into the `#1c2128` card (`#2d004b` at 1.07:1 and `#7f3b08` at 1.95:1
  WCAG contrast), and its `#f7f7f7` centre makes a bright halo round every
  near-zero bin. Each arm therefore runs from the card outwards through PuOr's
  own colours, brightness rising with |value| and hue alone giving the sign.
  The first 3:1 colour of each arm (`#b35806` 3.3:1, `#8073ac` 3.8:1) sits at
  10^−2.5 of the peak, where the taper above the 10⁻³ band reaches full
  opacity, so nothing a reader is asked to see is drawn below 3:1. Raw Shap-CAM
  puts zero at border grey `#30363d`, so a populated bin with zero attribution
  stays distinct from an empty one. The other anchors of both arms are placed
  by CIE lightness, so equal |value| of either sign reads equally bright:
  mirrored codes agree to 15% in contrast on the signed log and 9% on the
  linear ramp. (Spaced evenly, the purple arm of the linear ramp had stayed
  below 3:1 until |v| = 0.43 while the orange one crossed it at 0.24.)

The legends mark both signs and zero (`+10⁰ a.u.`, `±10⁻³`, `−10⁰ a.u.`; `+1.00`,
`0`, `−1.00`). Every rendered negative number in the interface and the exported
figures — ticks, legend ends, tooltips, captions, the Details drawer — is set
with the
minus sign U+2212, never a hyphen (`static/js/format.js`, `calosrv/text.py`).

### Model performance cards

`GET /api/model-performance?model=&coord_system=` evaluates one of the nine
networks over the selection and returns self-describing `cards[]`: value, unit,
standard error, a 95% interval named by its method, N and a note. Below N = 15 a
card shows its interval beside its SE, and its small-sample caveats (the c₄ bias
of σ, an untestable shape) under the label.

| Model | Cards (headline in bold) | Uncertainty |
|---|---|---|
| Segmentation | **voxel accuracy**, **energy-weighted MAE**, MAE, RMSE, F1 (shower A), split cells | ratios of sums over hits, with the events as clusters: linearised-ratio SE and Student-t interval, from five sums per metric in one pass over the event table |
| Energy | **σ of (pred − true)/true** per shower, relative bias, RMSE (GeV), correlation | σ: ddof = 1 with its χ² interval and the c₄ note below N = 15; bias: Student-t; RMSE: t-interval on the mean squared residual; correlation: Fisher z |
| Angle | **σ of θ_pred − θ_true** per shower (mrad), bias, RMSE | as for energy; θ does not wrap, so its mean is a meaningful bias |

Showers A and B are reported separately, each with its own N; an event without
shower-A hits has no A prediction and is dropped from A, never zero-filled.
"Split cells" is a property of the data, not of the network: every such cell is
two rows, so the unweighted per-hit counts see it twice. On the full production
selection (20,268 events):

| | Absolute (`absolute`) | Per-shower translated (`trans`) | Local (`local`) |
|---|---|---|---|
| Voxel accuracy | 76.92% | 69.69% | 67.40% |
| Energy-weighted MAE | 16.47% | 22.79% | 24.25% |
| Energy σ_rel A / B | 23.95% / 34.43% | 17.56% / 23.76% | 23.67% / 29.69% |
| θ σ A / B | 3.43 / 7.34 mrad | 73.1 / 81.1 mrad | 23.1 / 31.3 mrad |

Each value was checked against an independent recomputation from the Parquet
archive. The cards answer in 7–11 ms.

The energy panel (plot 4) stays the **segmentation** reconstruction in every
model view, built from the selected frame's segmentation network, and names
that network in `meta.network`. Its response is measured as served: at the
maximum of eight D slices the fitted curves alone reached 67 KB of a 120 KB
response, so while it is over 100 KB the curves are re-sampled at 150, 100, 75
or 50 points — each point still the exact fitted Gaussian — and the step is
stated in the energy panel's Details drawer. A synthetic file with 1, 2, 7, 8, 14, 15, 19, 20
and 200 events per slice (`tests/synthetic_all_models.py`) checks every
low-N rung against the budget.

### The physics section

Under the 2 × 2 sit nine cards, the reference notebooks' physics figures. Each
has the anatomy of every other card on the page (Details first in the toolbar,
the plot-only Export last, which the statistics table lacks), and each **loads
when it scrolls into view**: one
`IntersectionObserver` over the scrolling column (`rootMargin: '0px'`, so
nothing is requested before the reader could see it, at the cost of an empty
plot for the length of a cold query) asks for a card the first time it is
visible, and again only when its request changes. A filter change therefore
re-asks the visible cards and leaves the others to load when they scroll in
(`js/lazy_cards.js`, `js/physics_section.js`). A request the server refuses with
a 4xx, the 422 of a shut capability above all, counts as answered: the card
shows the server's reason, since asking again would only repeat it. The section
is hidden together with the 2 × 2 while the Event Inspector or the compare view
replaces it.

| Card id | Title | Request | What it draws |
|---|---|---|---|
| `profile-w`, `profile-r` | Longitudinal Profile along w; Radial Profile along ρ | `/api/profiles`, one request for both | each shower's fraction of its energy per cm, along depth w (bins of the 20.5 mm layer pitch) and along transverse radius ρ (10 mm bins): the per-shower mean, its SD band, its Student-t envelope and the pooled ratio of sums |
| `response-b1` | Sampling Fraction — Per-Event Distribution | `/api/response`, one request for the three | the distribution of f = E_dep / p per event, with its mean, SD and the calibration's 1/c |
| `response-b2` | Sampling Fraction vs. Incident Momentum | | the mean of f per 1 GeV momentum bin with its 95% interval and SD |
| `response-res` | Relative Resolution σ/μ vs. Incident Momentum | | σ/μ per 1 GeV bin, of c · E_dep and of E_dep / p |
| `response-b3` | Response vs. Incident Momentum p | `/api/energy-distribution?slice_by=momentum` | the reconstructed energy in momentum slices, one sub-plot and one energy axis per slice, with the energy panel's fits and low-N ladder |
| `distribution` | Distributions by Momentum Bin | `/api/distributions` | one step outline per 1 GeV bin of u, v, w, hit energy, θ, φ or p |
| `correlation` | Hit-level Pearson Correlation | `/api/correlations` | the lower triangle of the correlation matrix of seven variables, with intervals |
| `statistics` | Selection Statistics — describe() | `/api/statistics` | a table, not a chart: pandas `describe()` of the hit coordinates and energy, and the negative-depth block |

What the marks mean, per card:

- **Profiles.** The primary line is the per-shower mean (every shower weighs the
  same); the uncapped shaded band is the SD of the per-shower fractions
  (ddof = 1), where individual showers lie; the thin capped envelope is the 95%
  Student-t interval of the mean, cluster-robust with the event as the cluster
  where two showers of an event are pooled; and a dashed line is the pooled
  ratio of sums, the notebook's estimator, with its own capped interval. They
  are four quantities and four marks, and each tooltip names its own. Depth is
  along each shower's incident direction (`w`, the Local frame) or each
  shower's own native layers (`native`, per-shower translated); the **Notebook
  convention** toggle drops hits behind the entry plane (`w < −10⁻⁶ mm`) from
  every bin *and* from each shower's normaliser, and is refused with native
  layers because it is defined along w. The y axis is set from the two lines
  alone and starts at zero; a band or interval that leaves it is clipped with a
  caret and counted in the drawer.
- **Response cards.** B1 draws the mean of the per-event fractions with its
  Student-t interval and the calibration's `1/c = Σ E_dep / Σ p` with its own
  interval, as two different quantities (see
  [Energy calibration](#energy-calibration)). B2 draws, per 1 GeV bin, the mean
  with its 95% Student-t whisker (at every N and in every bin, so a whisker never
  changes meaning along the axis) and the SD as an uncapped box. The resolution
  σ/μ takes the **χ² interval of σ divided by μ** as its whisker: it is never
  negative and carries the skew of σ's sampling distribution, which dominates at
  small N. μ's own uncertainty is neglected, which the payload says, and the
  delta-method standard error travels beside it for the tooltip. It has two
  series because the resolution of the calibrated energy in a 1 GeV bin includes
  the momentum spread inside the bin (a uniform 0–1 GeV momentum alone gives
  σ/μ = 0.58 in bin 0): E_dep / p divides it out.
- **B3, the response grid.** It lives on the energy panel's route, so it has the
  same machinery and the same payload guard. `p_slices=notebook` is the
  CALIBRATION notebook's windows 1, 2, 5, 10, 15 and 19 GeV ± 0.5 GeV (set
  `p_half_width`, up to 10 GeV); `p_slices=bins` is the producer's 1 GeV bins; a
  comma list gives window centres. Each slice gets its own energy axis, because
  a 1 GeV and a 19 GeV slice share no useful range, and the grid never shares
  one x axis. Two showers per event are placed each by its own momentum, and
  the `series` choice (`truth`, `model`, `all`) selects the deposit split by the
  true segmentation fraction, the network's split, or both. The card grows to
  hold every slice. Each slice's core Gaussian is on its histogram's
  normalisation (see [Low statistics in plot 4](#low-statistics-in-plot-4)), and
  its drawer carries the same *Reading the density axis* section as plot 4's.
- **Distributions.** u, v and w are the Local-frame hit coordinates as
  footprint-splatted counts (each hit's footprint is split into k = 2
  sub-deposits per axis and depth, gap-free, so a count can be a multiple of 1/8;
  40 mm bins for u and v, the 20.5 mm layer pitch for w), with the comb measured
  on the pooled raw profile and named; hit energy is on
  log-spaced bins over the 1st–99th percentile; θ, φ and p are the showers'
  incident kinematics, each shower once (`weighting=shower`) or weighted by its
  hit count (`weighting=hit`, the notebook's hit sample computed exactly). φ is
  drawn over its full period (−π, π], never cropped and never averaged: each
  series' R̄ and Rayleigh p are in its tooltip. A series below 15 showers is
  dashed. Counts outside the display range are counted per series, never
  dropped.
- **Correlations.** r is on PuOr, symmetric about zero and linear on [−1, +1]
  (the folded variant on the dark card), with the value printed in each cell.
  Hits of one shower are not independent pairs, so the interval is a Fisher-z
  with an **event-grouped jackknife** (64 groups of `event_number` mod 64, or
  one per event below 64), whose method, group count and effective N the tooltip
  names beside the naive hit count. An azimuth has no linear correlation: its
  cells are hatched, off the colour scale, and carry Mardia's circular–linear R
  where the server quotes one.
- **Statistics.** Count, mean, SD (ddof = 1), min, quartiles and max are
  unweighted, one observation per hit, as pandas does; the energy-weighted mean
  and quartiles sit under their own header. No standard error of a hit-level mean is
  quoted, because the hits of a shower are correlated and a hit count would claim
  a precision the events lack. The absolute frame adds the notebook's
  `z − 3649 mm` row (see [The z convention](#the-z-convention)). The
  **negative-depth block** (C9) is the share of energy, of hits and of events
  (or showers) with a hit at `w < −10⁻⁶ mm`, by momentum split (p < 1, 1–10 and
  > 10 GeV), each with the interval the server names: a cluster ratio interval
  for the fractions, Wilson for the share of events. On the electron file 95.10%
  of events hold such a hit, and they carry 3.98% of the energy. The Local
  frame's `/api/projections` response carries the same block as
  `frame.negative_w`, and the status bar's **w < 0** readout reads it.

Every card keeps to CLAUDE.md §2: a display range follows the robust series
(N ≥ 20) and starts at zero, a mark that leaves it is clipped with a caret and
counted in the Details drawer, and a density that cannot be estimated leaves its
axis unlabelled. Which mark each sample size supports is in
[Low statistics](#low-statistics-in-plot-4).

### Page 1 for each kind of experiment

The Physics page is planned from the experiment's capability block
(`js/capabilities.js`, `page1Plan`), never from a guess about its kind, and the
block is the server's (`query/capabilities.py`):

- **Two-shower hits**: everything described above, with an **A / B / Both**
  toggle on the cards that have two showers to show.
- **Single-shower hits** have one shower per event.
  - *Filters.* The sidebar has one slider, **p — incident momentum [GeV]**, the
    shower's own `incoming_momentum`, sent as `e1_min` and `e1_max`; E₂, D and
    the undefined-D option are hidden and never sent, and the status bar has no
    separation readouts. The Event Inspector's shower radio offers only the one
    shower of the event.
  - *Frames and channels.* Absolute, and under *Shower-Aligned* the per-shower
    *Translated* (API `trans`, which here is a radio of its own) and *Local*. The
    D-frame radio is disabled with the server's reason (it needs two showers).
    The channel is density; there is no network, so the model selector has
    nothing to drive.
  - *Plot 4* is the **response grid** (B3) on the notebook's six windows, titled
    "Response vs. Incident Momentum p", with the fitted μ and σ table below it.
    Those six windows fit the 2 × 2 cell. The full-width
    **Response vs. Incident Momentum p** card below opens on the producer's
    1 GeV bins and grows to fit every slice, and a link under plot 4 leads to it.
  - *The missing-predictions banner.* CLAUDE.md §3 asks for a prominent warning
    when predictions are absent and ground-truth baselines are shown instead. A
    kind with no networks gets one, leading with the server's reason: no model
    predictions in this experiment, the panels show ground-truth baselines only
    (deposited energy, incident momenta and their distributions), the attention
    channels, model cards and network energy reconstruction are unavailable, and
    no prediction is substituted. It stays until the experiment changes.
- **Events only** (the aggregate) has no hits.
  - *Notice.* The 2 × 2 is replaced by **No hits to project**, with the server's
    reason and a sentence saying that the cards below are computed from the
    per-event table.
  - *Controls.* The spatial control groups are hidden rather than left
    disabled: the reference-frame tier with its **Compare frames** checkbox and
    the Event Inspector picker, the display resolution, the display channel and
    the colour map. The notice says why.
  - *Cards.* The four hit-level cards (both profiles, correlations, statistics)
    are not built; B1, B2, the resolution, B3 and the distributions of θ, φ and
    p are. Each carries the aggregate's censored-sample notice into its drawer
    (see [Expected schema](#expected-schema)).
- **A frame the new experiment lacks falls back to Absolute**, with a one-line
  notice in the kind banner, when the experiment is switched to one of another
  kind: the D-frame has no radio on a single shower, and a single shower's
  *Translated* is the legacy per-shower frame on two. *Local* carries over both
  ways. Opening a `#frame=trans` link or a saved default is not a switch, so
  those still open the legacy frame; nor is a switch between experiments of one
  kind, or to the events-only kind, whose frame tier is hidden.
- **A stale experiment** (derived tables from an earlier release, see
  [Storage](#storage-duckdb-tables-and-the-parquet-archive)) keeps working
  where it always did. Each card that needs the newer tables is shut with the
  server's reason on it and a **Rebuild derived tables…** button that opens
  Admin Settings, whose Derived tables section lists every experiment's version
  and runs the [rebuild](#rebuilding-derived-tables). The kind banner carries
  the same notice. The cards come back when the rebuild commits.

### Low statistics in plot 4

**Reported numbers and drawn marks are gated separately.** A table cell makes no
claim about the shape of a distribution; a smooth curve does. So μ, σ and σ/μ are
reported from **N = 2** — with their standard errors and, on hover, their
asymmetric 95% intervals — while each mark on the canvas waits for the sample
size that supports it:

| Floor | What it gates |
|---|---|
| N ≥ 2 | μ, σ, σ/μ as reported numbers (at N = 2, flagged `moments (1 d.o.f.)`) |
| N ≥ 8 | the continuous parametric density curve |
| N ≥ 15 | the density histogram, and the iterated ±2.5σ core refit |
| N ≥ 20 | the robust width and the Gaussian-shape verdict |

The histogram has the highest floor for a reason specific to the estimator: a
`density=True` histogram normalises by `N × bin_width`, so once the bins are
finer than the spacing between events each occupied bin holds exactly one and
reports a height set by the binning rather than by the distribution — the tall
narrow spikes the panel used to show at small N. That argument is about the
histogram and does not extend to the mean and width of the same events.

Below the histogram floor the panel draws the individual events as baseline
ticks, the sample dispersion as an uncapped shaded band, and the mean with its
**95% confidence interval** (Student-t, not a normal approximation) as a capped
whisker. The band and the whisker are deliberately different marks: they differ
by a factor of √N and answer opposite questions — how spread out the events are,
against how precisely the mean is known — and each tooltip says which it is.
These marks sit in a tinted, captioned band at the foot of the plot whose
vertical positions are drawing offsets rather than densities, which the caption
and every tooltip in it state.

Above the histogram floor the bin count follows the sample size (Rice rule,
clamped to 8–120) driven by the smallest slice whose histogram is drawn, so all
slices share one binning and none is finer than its own statistics support.

**The y-axis is scaled from the statistically robust slices only.** A fitted
curve peaks at `1/(σ√2π)`, so a thin slice with a poorly determined σ would
flatten every well-measured slice beside it — measured on a test set, two
10-event slices peaked at 2.52 and 2.09 GeV⁻¹ against a robust maximum of 0.38.
Thin curves are therefore drawn de-weighted, adapt to the established range, and
where one overflows it is clipped with a caret at the axis top and named, with
its true peak, in the energy card's notice (`#energy-sparse`) and the Details
drawer. If no slice reaches N = 15 the axis is labelled
*provisional*; if nothing estimable is drawn at all the density axis is left
unlabelled rather than showing a 0–1 grid nothing is measured against.

Widths are the unbiased sample estimator (`ddof = 1`) in both architectures; the
population form understates σ by 18% at N = 3 and below 0.3% above a few hundred
events. `calosrv` also reports a `ddof = 0` width so the reference notebook stays
directly comparable.

The x-axis range is rounded outward to clean tick boundaries *before* anything
is binned, so bars, curve and labels share one range and a raw percentile bound
such as `9.197060758` can never reach a tick. The y-axis is labelled
**Probability Density [GeV⁻¹]** with an ⓘ explaining that a density integrates
to 1.0 and legitimately exceeds 1.0 when the distribution is narrow. (The
explainer says "*A* density integrates to 1.0", not "the curve": see the next
paragraphs.)

**A curve drawn over a histogram shares its normalisation.** A
`density=True` histogram divides by the events it holds, so a Gaussian beside it
must carry the same unit per event or the two disagree about how much of the
sample it describes. The core Gaussian's area is therefore the number of events
it describes divided by the count the histogram normalises by
(`calosrv/query/energy.py` `build_series`, `stats/gaussian.py` `curve_area`):

- **When the ±2.5σ core refit cut events,** the Gaussian describes
  n_core / 0.98078 events. The window sits at 2.5 × the *truncated* width, while
  the curve is drawn with the de-biased σ (`sigma_core`, the window over
  k = 0.93656), so in units of the drawn σ the window is ±2.341, and its coverage
  is 2Φ(2.341) − 1 = 0.98078, not 2Φ(2.5) − 1 = 0.98758. Measured on 10⁶ Gaussian
  events with a 5% uniform tail, 0.98078 recovers the Gaussian count to
  6 × 10⁻⁵ and 0.98758 leaves the area 0.7% short (a test pins it). The area is
  then below 1 by the tail the curve does not describe. On the XGBoost momentum
  residuals in `tests/fixtures/payloads/pred_density_xgb_energy.json`, 47 core events divided by 0.981
  give 47.9 described events over the 61 the histogram holds, an area of 0.786,
  and the curve's peak falls from 12.11 to 9.51.
- **When the window cut nothing** the area is 1, or n / n_in_range, slightly
  above 1, when events beyond the energy axis are not in the histogram (shower B
  of slice 4 in the `energy_synthetic_trans` golden: 268 events, 260 inside the
  axis, area 1.031).
- **Without a histogram** (the `curve+strip` regime below N = 15, where no core
  refit runs) there are no bars to share a normalisation with and the curve keeps
  unit area.

`curve_peak` is the drawn curve's peak, so every scale and clipping reader sees
the curve as drawn; the axis rule is unchanged, and only series with N ≥ 15 set
the range. The same ladder serves Page 1's separation slices, the momentum view,
B3 and the Models page's residual cards. Disclosure: the drawers of the energy
panel and of B3 carry the sentence under *Reading the density axis*
(`panel_notes.js` `CURVE_AREA_NOTE`), and the tooltip of a residual card's curve
names its area ("area = share of showers in the Gaussian core, 79%: it describes
47.9 of the 61 showers the histogram holds"), read back client-side as
`curve_peak · σ_core · √(2π)` so that no payload field was added. The
tooltips of Page 1's energy panel and B3 do not print the area.

Separation slice is carried by colour, shower identity by line style (A solid,
B dashed), and the isolated references by dotted vertical markers at μ with a
shaded μ ± σ band — drawn as position-and-width rather than as density curves,
because their stated 5% resolution is an order of magnitude narrower than the
reconstructed distributions and a curve that narrow takes the y-axis with it.
An **A / B / Both** toggle filters by shower without a round trip.

**The physics cards use the same floors, and add these gates.** The
reported number and the drawn mark are gated separately there too, and the
density histogram and curve of B3 and of the distribution cards follow the table
above. What the cards add:

| Floor | What it gates |
|---|---|
| N = 1 | a single shower or event is drawn as itself, with no SD band and no envelope: the profile card says "single shower, not an ensemble" |
| N ≥ 1 | a **Wilson** score interval of a proportion (the share of events with a hit at negative depth); events are the unit, and showers only where each event holds one |
| N ≥ 2 | the **SD band**, an uncapped shaded range, ddof = 1, and the **Student-t envelope** of a mean, a capped whisker on N − 1 degrees of freedom (the event as the cluster where two showers share it); at N = 2 both are labelled "1 d.o.f." |
| N < 20 | such a summary is labelled *weak* (`weak (N = n)`) and its display range *provisional* on the axis |
| N ≥ 4 | a **Fisher-z** interval of a Pearson r (N events; r itself from N = 3, the event-grouped jackknife from 4 groups); Mardia's circular–linear R of a correlation with an azimuth from 8 distinct azimuths |
| N ≥ 6 | the distribution-free **order-statistic interval** of a median; below 6 even [x₍₁₎, x₍ₙ₎] covers less than 95%, so none is quoted |
| N ≥ 8 | a Gaussian **KDE** (Silverman bandwidth), the same floor as the parametric curve |
| N ≥ 20 | the seeded **bootstrap** interval of a median (2,000 replicates), beside the order-statistic one as a cross-check |

The SD band and the envelope answer different questions and differ by √N: the
envelope is wider than the band for N ≤ 6, because t(0.975, N − 1)/√N exceeds 1
up to that N, and narrower from 7. Each tooltip names which one it is.

### Spatial resolution: two modes

**Native Detector Lattice** gives one bin per real calorimeter cell —
212 × 104 transverse, 60 depth layers on the production file. Because a bin index
is an *ordinal* over the cell coordinates that actually occur, every
one-dimensional bin corresponds to a cell that exists, so the depth axes carry no
empty-bin comb.

> **The XY panel is the exception, and the interface says so.** That panel is a
> product of two ordinal axes, and the populated `(x, y)` pairs are *not* the
> full product: this detector's transverse cells are staggered, so adjacent x
> columns intersect different subsets of the y cells. Measured on the production
> file, adjacent native columns alternate between 46.2% and 42.3% occupancy, and
> the lag-1 autocorrelation of the detrended column profile is −0.25. The result
> is a fine vertical comb which is **detector segmentation, not shower
> structure**. The server measures this per request; the XY panel's Details
> button is flagged and its drawer names it, as does the ⓘ beside Spatial
> Resolution. Switching to Continuous Field merges the staggered pairs: the same
> selection at R = 150 measures +0.05 with 90% occupancy, and at R = 104 it is
> +0.85 with 94%. This is the same effect `calodash/constants.py` documented for
> the batch pipeline, where a 50.5 mm transverse bin was chosen for exactly this
> reason.

**Continuous Field** builds a uniform grid at resolution R: `R_x = R`,
`R_y = round(R · n_y / n_x)`, and `R_z` **locked** to the native sampling layers,
because there is no measurement between two scintillator layers 20.5 mm apart.
Energy is distributed by *geometric overlap*, not point-binned, so the image
refines as R rises without picket-fencing. Resampling runs in NumPy against a
cached native-resolution bundle, so changing R costs no database access.

> The transverse x lattice is **not** uniformly spaced — cells sit in tight pairs
> 4.4 mm apart with a group pitch alternating 43.87 / 48.27 mm. Panels are
> therefore positioned from physical millimetre extents, never from matrix shape.

### Display modes in the Separation-Aligned frames

In the D-frame the two modes act on the uniform 20 mm accumulation grid,
not on the lattice. They mean different things there, so the radios are
relabelled and each frame keeps its own mode.

**Native Grid** *(raw 20 mm bins, audit)* sends the cropped accumulation bins
as they are. `r_x` and `r_y` are the cropped shape, and the kernel is `none`.
The payload guard may box-merge bins pairwise. It is the audit view:

- it shows a cell-footprint comb exactly as measured;
- its Grad-CAM leaves only hitless bins transparent;
- `kernel_attenuation` is 1.0 on every panel.

A handful of rotated events shows each 48 mm cell as a tilted block, so this is
not the view the frame opens in. On screen a Native Grid raster is first
enlarged by an integer nearest-neighbour factor, up to about 2048 px and at most
×32, before the browser scales it. The raw bins then read as crisp blocks rather
than a bilinear blur of a 33 × 20 bitmap that the payload does not contain.
A Continuous Field Y′Z′ or X′Z′ raster gets the same enlargement along its 60
depth columns only (60 → 1920 px, rows untouched), so the browser's smooth
upscale acts along the transverse rows, which the kernel reconstructed, and
never blends two sampling layers.

**Continuous Field** *(kernel reconstruction)* is where the D-frame
opens. It reconstructs **x′ and y′ only** with a conservative kernel
(`grid/kernel.py`, applied by `query/reconstruct.py`). R sets the display bins
across the entry-panel (D–Y′) window. The kernel, not R, sets the resolution: no detail exists
below the 20 mm grid or the 48 mm cell.

| Selection | Kernel | Spread per 20 mm bin (RMS) | Total x′ blur, with the k × k footprint splat and the 20 mm binning |
|---|---|---|---|
| N < 50 | Gaussian, σ = 10 mm, over each uniform bin | 11.5 mm | 17.7 mm at k = 2, 18.9 mm at k = 6 |
| N ≥ 50 | bilinear tent: exact linear interpolation between bin centres | 8.2 mm | 15.7 mm at k = 2, 17.0 mm at k = 6 |

- **Why two kernels.** A handful of events leaves rotated cell blocks that the
  tent alone would still show. From 50 events the ensemble of rotation angles
  fills the footprint.
- **The switch at N = 50.** The tent is 29% narrower. Re-rendering the
  production N = 49 and N = 50 bundles with both kernels shows that the switch
  raises the displayed X′Y′ peak by 6–7% and the depth peaks by 4–5%. The
  kernel sentence (`frame.reconstruction.note`, in the notices and the panel's
  Details drawer) discloses it.
- **Which source bins.** Each axis is reconstructed from the full accumulation
  axis sliced to the window plus the kernel's reach: one bin for the tent,
  ⌈9σ/p⌉ + 1 for the Gaussian, whose tail is exactly zero past 9σ. Energy just
  outside the window therefore blurs in, and energy leaving it is counted. On
  X′Y′ the in-window total agrees with the row and column inside-weights applied
  to the raw grid to 3.5 × 10⁻¹⁶ relative.
- **Grad-CAM** uses the same operator on the numerator and the denominator (a
  normalised convolution), so a constant attention field stays exactly
  constant.
- **Depth** keeps its 60 native sampling layers in both modes and is never
  smoothed or interpolated. There is no measurement between two layers 20.5 mm
  apart.

Bicubic interpolation was rejected: its negative lobes give negative density and
overshoot the peak. Point interpolation was rejected because it does not
conserve energy. The display caption names the kernel, σ, its RMS spread, the
total blur, the display pitch and the N gate.

The Local and the legacy per-shower translated frames use the same two modes on
their own 20 mm grids, with the same labels.

**One mode per frame.** The state holds `display_lab` (default `native`, the
hardware lattice), and `display_trans`, `display_local` and `display_canonical`
(default `continuous`).
`state.get('display')` and `set({display})` address the active frame's key.
Switching frame and back returns each frame to the mode it was left in, and
re-syncs the radios, their per-frame labels, the R control and its hint. The
hash writes each key only when it differs from its default. A pre-split
`#display=native` link still works: it is applied to the active frame, unless
the link also carries that frame's own key. Canonical links written before the
split never carried `display`, because Native was the default, so they would
open in Continuous Field — and, since the Absolute frame became the default,
they open in the Absolute frame unless they name `frame=canonical`.

**Switching costs no scan.** A co-registered cache key names the frame kind,
the selection, the sampling, the accumulation grid, k (and k_z), the footprint
and the network. It says nothing about the channel, the display mode, R or the
kernel, all of which are applied afterwards to the cached raw grid. A channel,
mode or R change is therefore a re-render: 23–47 ms for the whole request on the
production file. A model change scans once per selection; a density request is
served from any network's bundle, since density reads no CAM plane.

### Energy calibration

A sampling calorimeter records only a fraction of a particle's energy. Summed
deposits are of order 0.05 GeV per event while incident momenta are 0.4–20 GeV,
so the two are not comparable without calibration. Per-shower constants are
fitted from ground truth over the active selection:

```
c_A = Σ(incoming_momentum_A) / Σ(energy · segmentation_{f}_true)
E_reco_A = Σ(energy · segmentation_{f}_pred) · c_A
```

where `{f}` is the selected frame's segmentation network (`absolute` for the
Absolute frame and the D-frame, `trans`, `local`).

Summing before dividing, rather than averaging per-event ratios, is deliberate: a
per-event normalisation would force each event onto its own truth exactly and
erase the containment scatter the resolution measurement exists to quantify.
Pass `calibrated=false` to see the raw deposited sums, in which case the
benchmark curves are hidden because they would not be comparable.

**Two estimators of one number, kept apart.** The sampling fraction has two
honest estimates, and B1 draws both, each with its own interval and named as what
it is. The *mean of the per-event ratios*, f = E_dep / p averaged over events, is
the notebook's estimator, with a Student-t interval. The *sum before dividing*,
100 Σ E_dep / Σ p = 100 / c, is the fraction the calibration above implies, with
the linearised cluster-ratio interval, events as the clusters. A ratio of sums
weights an event by its momentum and a mean of ratios weights every event alike,
and the fraction depends on the momentum, so the two differ: on the electron
file 3.041% (mean of ratios) against 3.113% (sum before dividing). Neither is
*the* sampling fraction. c is fitted once over the whole selection and never per
momentum bin, which would force every bin onto its own truth and erase the
response curve B2 and the resolution exist to show.

**The calibration runs over the showers present.** A shower that deposited
nothing has no response to calibrate: on the production file 57 of 20,325 events
have no shower-A hit. Such a shower is left out of both sums, so
c = Σ p / Σ E_dep is taken over the showers present, and it is one constant
everywhere: the energy panel in separation mode and in momentum mode, and
`/api/response`. The default two-shower view is unchanged, because it excludes
the events with an undefined D. With **Include events with undefined D** the
constant moves (by about 0.3% for shower A on production), and
a notice names how many selected events have no hits for that shower and that it
is left out of the calibration; its zero deposit is still counted in its slice.

**The resolution σ/μ** is a ratio of two estimates. Its whisker on the resolution
card is the χ² interval of σ divided by μ, [σ_lo/μ, σ_hi/μ]: it is never negative
and carries σ's skewed sampling distribution, which dominates at small N. μ's own
uncertainty is smaller by a factor of about σ/μ and is neglected, which the
payload says; the delta-method standard error, which includes it, travels beside
it for the tooltip.

### Exporting figures for publication

Every panel header carries an **Export ▾** control offering lossless SVG or
300 DPI PNG, at 85 mm (single column) or 175 mm (double column). The figure is
whatever is on screen at that moment: the active zoom window, the A / B / Both
selection, the filters, the display mode and the colour map.

Figures are authored in millimetres converted at 96 DPI, so 85 mm is 321 logical
pixels and rasterising at ×3.125 lands on 300 DPI by construction — a
double-column PNG measures 2065 px. The same convention makes a point
meaningful, since 1 pt is then 4/3 logical px.

> **Print type is larger than screen type, not smaller.** Legibility is the
> font's share of the figure width, and the interface's 9–10 px labels in a
> ~600 px panel become 6.8 pt when reproduced literally in an 85 mm figure.
> Nine points is 12 logical px here, so every print size is quoted in points and
> converted. Each colour drawn as text or axis chrome clears 4.5:1 against white,
> asserted by `tests/test_export_assets.py` rather than judged by eye.

**The figure is the plot canvas only.** By directive, an exported figure holds
the axes, the data raster, the vector overlays and the colour-scale legend, on
`#FFFFFF` in `#111827` ink, and nothing else: no caption band is laid out under
the plot, no height is reserved for one, nothing is spliced into the SVG after
serialisation (there is no `<g id="figure-disclosure">` any more; the only
post-processing is the `image-rendering: pixelated` hint on the embedded
raster), and the energy figure carries no μ/σ table rows. This overrides the
earlier rule that the figure carries its own disclosures. The methodology and
the statistical disclosures a reader needs — the percentile-clipping counts,
the staggered-comb warning, the display window and the energy it leaves out,
ρ_ref with its reference, the display floor, the reconstruction note, the
footprint and k, the ill-conditioned count, R̄′ / Rayleigh p / N for each
ensemble axis, the *provisional* flag, the true peak of any clipped low-N
curve, and whether the values came from the 10% sample — are the panel's
**Details drawer** (`js/panel_notes.js`), which is what an author carries into
the manuscript caption. The drawer's *Disclosures* section is read
**structurally from the payload** (`static/js/export/disclosure.js`), not
scraped from the prose: prose is assembled for a card and may be shortened or
rounded, whereas a caption must state what was *computed*. The one sentence
the figure keeps is the ramp's print title, which names the display floor.

`export/caption.js` now holds only the provenance sentences
(`describeSelection`, `describeView`) and the display descriptor (`displayOf`,
`kernelPhrase`); nothing in it is drawn into a figure.

**The drawer's provenance line and the file name read the display from the
payload, not from the controls.** Both use R, the merge and the kernel
(`caption.displayOf`, from `meta.resolution` and `frame.reconstruction`). The
payload guard can lower R below the slider, and a figure labelled R150 that
holds R112 bins is mislabelled. The provenance line names the grid, for example
"Separation-Aligned (D-Frame), Translated, Gaussian kernel, σ = 10 mm on 7.5 mm
display bins (R = 112)" or "Separation-Aligned (D-Frame), Translated, raw 20 mm
bins (Native Grid, no reconstruction)".

Two things change for white paper beyond the obvious inversion:

- **The categorical sub-range flips.** `categoricalStops` samples the *upper*
  ramp on screen because Viridis begins at `#440154`, invisible as a one-pixel
  line on `#0d1117`. On white the failure is the mirror image — the `#fde725` end
  vanishes — so print samples [0, 0.75]. The ramp's identity and its lightness
  ordering are untouched; this is a sub-range change, not a palette inversion.
- **The colour bar moves below the x axis.** A vertical bar costs about seven
  label widths, which on a 321 px figure is a quarter of the canvas.

The co-registered overlays change for print as well:

- **The display floor is a hard contour.** `floorFadeDecades` is 0 in print, so
  the alpha is a pure step and never a division by zero. A gradient could band
  or drop out on a printer. The figure carries no caption to say so, which is
  why the drawer's floor sentence — the edge of the colour is the display
  floor, not the edge of the shower — belongs in the manuscript caption; the
  ramp title appends "· below 10⁻³ not drawn", shortened to "· <10⁻³ not drawn"
  where a single column has no room.
- **The separation rule** is `#6b7280` instead of translucent white, which
  vanishes on paper and carries an alpha that PDF renderers composite
  unpredictably.
- **Anchors** print at full opacity.

None of these three tokens is text, so none is held to the 4.5:1 ink floor.

> **The spatial panels' density field stays a raster.** The SVG embeds it as
> an `<image>`. The axes, overlays, legend and every label are true vector
> `<text>` and `<path>`, which is what LaTeX compilation turns on. The bitmap
> is upscaled by an **integer** factor with smoothing off. Each pixel block is
> one **payload bin**:
>
> - a detector cell in the Absolute frame;
> - a raw 20 mm accumulation bin in a co-registered Native Grid;
> - a reconstructed display bin in the Continuous Field.
>
> Every one of them is a value the server computed, and interpolating between
> them would invent values the payload does not contain. On the detector lattice that
> would be resampling by point interpolation, which CLAUDE.md forbids. The
> smoothing a Continuous Field figure shows was done on the server by the kernel
> the drawer names, not by the image scaler. Print takes the raster at one
> pixel per payload bin, without either on-screen enlargement, and applies one
> integer factor to both axes. The factor fills the printed width at 300 dpi
> but keeps the long side at or below 4096 px, so a 60-layer depth raster a few
> hundred rows tall is no longer enlarged by its width alone.
> The energy panel is line and path geometry throughout and vectorises
> completely.

Exports never touch the live charts: the panel is re-rendered into a detached
off-screen instance under a swapped theme, so the screen does not flash and no
zoom, filter or toggle is reset. The render is synchronous and blocks the main
thread for a fraction of a second at double-column PNG — ECharts needs a real
DOM node and cannot be moved to a worker — so the button disables and relabels
first rather than appearing to ignore the click.

Names are deterministic: `[panel-id]_[slice]_[YYYYMMDD_HHMMSS].[svg|png]`, where
the slice names only the axes actually narrowed, for the same reason the URL
hash omits untouched bounds. The slice then names the display (`native` or
`R112`, the payload's own), a non-Absolute frame (`trans`, `local`,
`canonical`), and for a CAM channel the channel and its network (`gradcam`,
`gradcamE`, `shapcam`, `shapcamE`; `seg`, `energy`, `angle`) — a density figure
belongs to no network. A co-registered Continuous Field export appends the
kernel last, as `gauss10` or `tent`, so the 90-character cap drops the kernel
first. The energy panel names a non-absolute segmentation frame. For example:
`xy_D-257-258_R112_local_shapcamE_seg_gauss10_20260924_101500.svg`.

---

## The Models page

*Models* at `/models` is the second page of the interface. Page 1 asks how a
reconstruction behaves in the detector; this page asks how well a model
predicted, which per-event features separate the momentum classes, and what one
event or the whole selection looks like in three dimensions. It shares the
experiment, the filters, the reference frame and the reconstruction model with
Page 1 through the URL hash, so a tab switch carries the view across (see [The
interface](#the-interface)). Its own state keys are `feature`, `fclass`,
`fshower`, `voxel_event`, `voxel_shower`, `voxel_channel`, `ens_channel`,
`xgb_task` and `xgb_label`; like every key they are written only when they
differ from the built-in value, and none reuses a Page 1 key (`event` and
`shower` pin Page 1's Event Inspector and are never read here).

Every card on the page follows the anatomy of a Page 1 card: Details first in
the toolbar (the same [drawer](#the-interface), with the same four sections plus
a card's own headings), a plot-only Export where the card is a chart, tooltips
mounted on `#tooltip-layer` that never cover the hovered plot, and every
negative number set with U+2212. A card loads when it scrolls into view and
again only when its request changes. A request the server refused (a 422 from a
shut gate) stays refused for that request; a transient failure shows its error
with a Retry. Switching experiment aborts the requests in flight, drops every
cached response and blanks every card before anything is drawn, and each card
checks its request key after its response lands, so a late response never draws
the previous experiment's data under the new one's name.

The sections, in page order: **Model performance** (three cards), **XGBoost
model** (four cards), **Event features** (four cards), **Primaries** (one card)
and the **3-D views** (two pairs of a 3-D card and three 2-D projections).

### What each kind of experiment shows

The page is planned from the experiment's capability block
(`static/js/capabilities.js`, `page2Plan`, the Models twin of Page 1's
`page1Plan`), never from a guess about its kind, and the block is the server's
(`query/capabilities.py`, [The capability block](#the-capability-block)). A card
the experiment cannot serve is shut with the server's sentence, or its section
is left out; nothing is substituted for what is missing.

| Section | `two_shower_hits` | `single_shower_hits` | `single_shower_events` (aggregate) |
|---|---|---|---|
| Model performance | The energy and angle networks' per-shower predictions, in every input frame at once (segmentation has no per-shower prediction) | Absent: no networks | The **XGBoost** hold-out series, once an analysis is done; otherwise absent |
| XGBoost model | Absent | Absent | Shown when a model run pairs with the experiment; its cards open when the analysis is done and current |
| Event features | Both showers, each in its own right, in the Absolute, per-shower translated and Local frames, rebuilt from the per-event Group-1 sums | Shower A, same frames | The producer's own feature columns, as stored |
| Primaries | Absent: the species columns are not in the two-shower export | The share of events with no primary-tagged hit | Absent: no hits |
| 3-D views | One event (Absolute, per-shower translated, Local) and the ensemble cloud (Local, D-frame); attention channels from the networks | One event (Absolute, per-shower translated, Local) with the species channel; the ensemble cloud in the Local frame | Absent: no hits |

The reasons are the capability block's: a hit-level gate that needs the derived
tables is shut on a [stale experiment](#rebuilding-derived-tables) with the
rebuild sentence, and the features section stays on show for it so the sentence
has somewhere to be read. Two banners and a caption say what the experiment lacks.

- **No network predictions** (CLAUDE.md §3). An experiment without
  reconstruction-network outputs says so in a prominent banner: the network
  performance cards and the attention channels of the 3-D views are unavailable,
  and no prediction is substituted. Where an XGBoost regressor pairs with the
  experiment, the banner says instead that the performance cards draw that
  regressor on its 20% validation split.
- **No model run is loaded.** An experiment with no paired model run, of any
  kind, carries an info banner naming the four XGBoost views and saying why none
  pairs with it: its kind, or the [pairing](#the-xgboost-analysis)'s reason. It
  disappears as soon as a model run pairs.
- **Caption: another frame was drawn.** A view that has no data in the selected frame
  draws in a fallback and says so under its title, and the fallback is never
  written back to the link. The feature cards serve the Absolute, per-shower
  translated and Local frames; the D-frame has no per-event feature sums, so the
  cards fall back to Absolute. The ensemble cloud is co-registered only, so
  Absolute and per-shower translated fall back to Local. The event pair falls
  back to Absolute when the D-frame is selected (see [The 3-D
  views](#the-3-d-views)). A network reads the frame it was trained on, and the
  D-frame uses the absolute-frame networks; that is the definition of the
  D-frame's networks, not a fallback. An aggregate has no sidebar frame, but its
  columns hold the Absolute, per-shower translated and Local features (the
  capability block's `group1_frames`), so each feature card carries its own
  **Frame** choice, first in its toolbar and shown only for an experiment
  without hits (see [The feature explorer](#the-feature-explorer)). A link that
  names the D-frame falls back to Absolute there, and the caption says so.

### Network performance by momentum bin (E2)

`GET /api/model-performance?slice_by=momentum_bin` asks the question Page 1's
separation slices do not: how a network behaves across the momentum range. An
event holds two showers of two momenta, so it has no single momentum bin; each
shower is placed by its own producer bin (`e1_bin` for A, `e2_bin` for B, never
`floor(p)` recomputed) and the two are separate series with their own N. The bin
axis comes from the whole event table, so it does not move with the selection.
A shower without a prediction is counted per bin and dropped, never
zero-filled. The segmentation network is refused here: its quality belongs to the
whole event.

**What is drawn.** One statistic at a time (RMSE, MAE, median relative error,
bias; the angle task adds the median absolute error), as grouped bars that start
at zero (a signed bias runs down from zero) at fixed offsets inside their
1 GeV bin, so the x axis stays the momentum in GeV and an empty bin is a gap.
Colour is the input frame (ColorBrewer Set2 on the dark screen, its Dark2
partner in print: Absolute, per-shower translated, Local, then XGBoost, the order
the importance card uses for frames); a solid bar is shower A and a light wash
with a solid outline shower B, and shower B's legend swatch is that wash and
outline, a `rect` like A's, so the legend matches the bars. The legend wraps
over the plot's width (`chart_panel.js` `wrappedLegend`) instead of paging.

**Whiskers are intervals of the plotted statistic**, never the spread of the
showers in the bin:

| Statistic | Whisker | From |
|---|---|---|
| RMSE | a 95% **χ² interval** of the RMS under normal residuals centred on zero, n degrees of freedom: [RMSE·√(n/χ²₀.₉₇₅,ₙ), RMSE·√(n/χ²₀.₀₂₅,ₙ)] (`stats/rmse.py`) | N = 2 – 19 |
| RMSE | a seeded percentile **bootstrap** of the RMSE (B = 2,000; the seed rule of the median's, below) | N ≥ 20 |
| MAE, bias | Student-t interval of the mean absolute / signed residual (MAE clipped at zero) | N ≥ 2 |
| Median relative error | distribution-free order-statistic interval | N ≥ 6 |
| Median relative error | seeded percentile bootstrap (B = 2,000; each group seeds its own, `SeedSequence([42, frame, shower, bin, quantity])`, so an interval never depends on which other series a request asked for), the order-statistic interval kept beside it as a cross-check | N ≥ 20 |

The RMSE intervals are the momentum-bin cards' own and replace the square root
of the Student-t interval of the mean squared residual, whose lower end collapses
to 0 at N ≤ 8. The χ² interval is exact for normal residuals and approximate
otherwise (the RMS is taken about zero, not the sample mean, hence n and not
n − 1 degrees of freedom); its label states that assumption, which the drawer
prints under *Marks and legend* and *Estimators*, and each point's tooltip names
which of the two intervals it carries (`rmse_method`: `chi2_rmse` or
`bootstrap_percentile`; the XGBoost angle series' φ carries `phi_rmse_method`).
Page 1's metric cards and the residual card below keep the older estimator.

A value is reported from N = 1 without an interval, because a value claims
something about a sample and an interval something about its population.

- **One shower is a dot.** A bin of a single shower (or, for the XGBoost series,
  a single event) is an observation, not an aggregate: it is drawn as a dot of
  3.5 px radius at its value (shower A a solid fill with a card-coloured rim,
  shower B the wash with an outline) and never as a bar. It has no whisker, a
  dot beyond the axis gets the same caret as a bar, and its tooltip says "one
  shower: drawn as a dot, an observation, not as a bar".
- **A point without an interval is faded.** A point is *weak* exactly when the
  server gave it no interval, whatever its N, so no aggregate is ever a naked
  solid bar: the bar is drawn at reduced opacity with a dashed outline, and its
  tooltip names the floor of its own quantity: N = 6 for the median statistics
  (their order-statistic interval), N = 2 for the others. The drawer counts the
  faded bars against that floor.
- **The whisker is light ink on a card-coloured casing** (`marks.js`
  `customWhiskers` `casing`, opt-in; square caps, so the caps are cased too), so
  it clears 3:1 over any bar fill and over the card.

**The y range follows robust evidence.** A bin drives the scale only from
N = 15 (the core-refit floor); `y_max` is the largest interval end among the
driving bins, rounded outward to m × 10ᵏ with m in 1, 1.2, 1.5, 2, 2.5, 3, 4, 5,
6, 8 (`performance_bins.nice_top`), each a whole number of round ticks, so the
axis top lands on a tick (the chart's own step, `dividingInterval`, takes the
finest 1-2-2.5-5 step for a top off that grid: 0.22 gives 0.05 and 0.11 gives
0.02). The two-shower RMSE top went from 16 to 20 and the XGBoost one from 0.22
to 0.3 in the recorded payloads. An under-powered bar or whisker
above it is clipped at the axis with a caret, its true values in the tooltip and
its count in the drawer. When no bin reaches N = 15 the range comes from the weak
bins' values alone, never their whiskers, and is labelled provisional on the
axis.

**The angle network predicts θ only.** Residuals are in milliradians and a
relative error |Δθ|/θ grows like 1/θ at small θ, so each angle point also
carries the median |Δθ| in mrad, the smallest true θ and how many showers lie
below 0.1 rad; the drawer states them.

**The XGBoost series (aggregate experiments).** With `model=energy|angle` the
route answers the shipped regressor's hold-out as one series of the same shape
(code `xgb`, no cards, no separation slices). Only the 20% validation rows are
drawn, because the other 80% trained the model and would flatter it; the
selection applies to them, and the training rows it selects are counted in
`split.n_training_excluded` and not drawn. The momentum model answers
`model=energy` and carries no frame, because it reads the features of all three
frames at once. It predicts a **momentum**, not an energy, and the card says so:
the y axis reads "RMSE of the momentum [GeV]", the task toggle "Momentum", the
series counts "events" rather than "showers", and the drawer and the split
warning say "momentum prediction" (the networks keep "energy"; the x axis stays
the incident momentum p, true of both). The angle task adds **φ as a quantity
group of its own**: RMSE, MAE and median |Δφ| of the residual wrapped to
(−π, π], in mrad, with no
relative error (meaningless for an azimuth) and no bias (the mean of a wrapped
residual averages a circular quantity). The statistic control disables what a
series does not report.

The payload is measured as served and a body over 100 KB sheds the
order-statistic arrays, then two significant figures, and says so; the whiskers
keep their meaning at every step.

**Cost of the bootstrap.** The RMSE bootstrap is O(B·n) where the median's is
O(B), so the (frame, shower, bin) groups of one request run on a thread pool
(`performance_bins.map_groups`): one `ThreadPoolExecutor` per request, never per
group, bounded by the service's own thread allocation (`settings.threads`, the
figure `/api/health` reports; `os.cpu_count()` is never read), none at all for
one worker, and results kept in task order. Every group keeps its own
`SeedSequence([42, frame, shower, bin, quantity])` and no generator is shared
between threads, so the output equals the serial path exactly; a test builds a
production-sized case (20,325 events, 19 bins, 3 frames × 2 showers, 114 groups)
with 1 and with 8 workers and asserts the two bodies equal. Timed on that
synthetic case on a 24-core machine (not on real data, and without the DuckDB
read), warm: 0.07 s before the bootstrap, 0.84 s serial, 0.21 s on 12 workers
(the allocation a 64 GB host resolves) for energy, and 0.11, 0.90 and 0.26 s for
the angle task. Two simultaneous requests each build their own pool.

### Prediction against truth, and residuals

`GET /api/prediction-density` feeds two cards from one request: **predicted
against true** (a density of pairs) and the **residual histogram** beneath it.
The energy and angle networks predict one number per shower, so an event
contributes two pairs, A and B, kept apart; the segmentation network is refused
by name, its reconstruction being Page 1's energy panel.

- **Axes that do not move.** Truth and prediction share one range, taken from
  the whole event table whatever the selection (outward 1-2-5 rounding; the
  energy axis floored at zero), and the panel is square at 1:1, so the identity
  line is the diagonal and the picture does not shift as a filter changes.
  Pairs beyond the axes are counted per side in `outside`, so
  `n_in_range + outside.total == n`.
- **Density from N = 15.** A shower with fewer than 15 pairs gets its individual
  pairs drawn instead of a density: one or two showers per cell would be a
  statement about the binning. Counts are on a log₁₀ ramp that starts at the
  first position clearing 3:1 against the card, because Viridis' own first
  colour is 1.06:1 against `#1c2128` and a cell of a single shower would vanish
  while being "drawn"; the payload states that colour. Bins per axis are 64 by
  default (16 to 128) and step down, with a notice, if the body would pass
  100 KB.
- **The residual** is the quantity of Page 1's cards: (pred − true)/true for
  energy and Δθ in mrad for angle. It goes through the energy panel's ladder:
  the range is the 1st to 99th percentile of the showers with statistical weight
  (N ≥ 15; every shower, labelled provisional, when none has), rounded outward
  and disclosed; a density
  histogram from N = 15, the core-refit Gaussian from N = 8, the individual
  events below that; every mean carries its Student-t whisker apart from the
  sample's σ band; bias, σ and RMSE carry their own intervals
  (`metrics.residual_summary`, whose RMSE is still the square root of the t
  interval of the mean squared residual: the χ² and bootstrap intervals of E2
  are for its momentum bins only).
- **The residual's bins are Freedman–Diaconis, the one exception to the Rice
  rule.** The width is 2 · IQR · N^(−1/3) of each drawn shower and the widest is
  taken, so all showers share one binning, as Rice's "smallest drawn slice" does;
  the count is ⌈(hi − lo)/w⌉ over the display axis, clamped to 8–120, and Rice
  on the smallest sample again where no shower has an interquartile range
  (`stats/histogram.py` `freedman_diaconis_bins`). A residual's heavy tail
  stretches the 1st–99th display range, and Rice's count then put the whole
  Gaussian core into one bin: on the recorded XGBoost momentum residuals
  (`pred_density_xgb_energy`) 8 bins of 0.25 against σ_core = 0.033, now 87 bins
  of 0.023, so the core spans about three. The two-shower energy residual went
  from 14 bins to 16 and the φ residual stays at 8. The payload names the rule
  (`residual.axis.bin_rule`) and the width drawn (`bin_width`), and the drawer
  states the exception ("Here N bins of w").
- **The core Gaussian is on the histogram's normalisation.** Its area is the core's
  share, so it stands below the bars by the tail it does not describe (peak 12.11
  to 9.51 on `pred_density_xgb_energy`, area 0.786); see [Low statistics in plot
  4](#low-statistics-in-plot-4). The curve's tooltip names the area, as "area =
  share of showers in the Gaussian core"; the Models page's residual drawer
  does not yet.
- **φ residuals are circular.** The XGBoost angle regressor predicts φ as well,
  chosen with `label=phi` (θ by default; the networks predict θ only, so
  `label=phi` is a 422 on two-shower data). The wrapped residual keeps its
  histogram and its RMSE, but its arithmetic mean, the mean's whisker and the σ
  band, the bias, σ/μ and the moment σ are withheld: null with a note, never
  numbers, because the arithmetic mean of a wrapped quantity is not its centre.
  Its centre and spread are the circular **mean direction** (with Fisher's
  large-sample 95% interval from N = 25, `fisher_large_sample`), the mean
  resultant length R̄, the circular SD √(−2 ln R̄) and the Rayleigh p, all in
  mrad. A Gaussian curve is drawn only as a *fit of the core* (the iterated
  ±2.5σ window, N ≥ 15, only where the window does not wrap) and is named so. The
  card draws no mean marker, whisker or σ band for φ.
- **XGBoost on an aggregate** draws one series: the hold-out rows within the
  selection, labelled as the validation split (`source` `xgb`, `network.frame`
  `xgb`), with the split check's warning on the card when it failed. The
  momentum regressor's axes and residual are labelled for what it predicts:
  "Predicted momentum" and "Relative momentum residual (pred − true) / true"
  (the networks keep "Predicted energy").
- **φ spans its whole period.** The prediction-against-truth axes of φ are fixed
  at ±π (±3,141.59 mrad, `PHI_AXIS_MRAD`) whatever the data, with ticks at −π,
  −π/2, 0, π/2 and π (`hist2d.js` `radianScale`, which accepts a circular axis in
  rad or mrad). They were a rounding of the data before. The residual's one unit
  is mrad: "Azimuth residual φ_pred − φ_true, wrapped to (−3142, 3142]".
- **Shower colour is the Physics page's.** A pink and B blue and dashed on
  two-shower data, a single shower in the accent blue (`chart_panel.showerColour`),
  and the residual drawer says so.

### The feature explorer

`GET /api/features` serves four cards from one cached per-event bundle: a
`catalog` of the features and class sizes, then `describe`, `corr`, `hist` and
`hist2d`. One request reads the event table once, with no hit scan, and
everything a view varies (classes, feature, scale, the floor exclusion) is a
NumPy step over the cached arrays; each view is its card's gate, so a
two-shower experiment built before the Group-1 columns is refused with the
rebuild sentence rather than failing in SQL. Every response is measured on the
wire against 100 KB and sheds resolution in stated steps (curve points, then
bins; the describe intervals).

**The features.** The nineteen the notebooks give XGBoost (`core.calc_all_features_v3`:
width, height, depth, depth range, volume, hit count, deposited energy, the
three centroid coordinates, mean, SD, maximum and energy-weighted radius, mean
θ, mean φ, angular spread and the two densities), plus two hit-kind companions,
`avg_phi_circ` and `angular_spread_circ`, which only per-hit sums can give. A hit
kind rebuilds them from the Group-1 sums through the one copy of core.py's
formulas; the aggregate reads the producer's values under the file's names. Each
feature carries what a reader must know before trusting a number:

- **Circular.** `avg_phi` is core.py's *arithmetic* mean of the hits' φ, kept
  because the producer's file and the XGBoost inputs use it; it is not a
  direction and is never drawn as one. `angular_spread` contains a *linear* SD of
  φ, which the ±π cut inflates (70.6% of the electron file's tail above 0.5 rad
  sits at a centroid azimuth beyond ±2.5 rad); the `_circ` companions use the
  circular mean and SD.
- **Floored.** core.py floors width, height, depth and depth range at 10⁻⁶ mm, so
  a floored factor makes the volume tiny and both densities enormous (up to
  2 × 10⁹ hits/mm³ against a median of 2 × 10⁻⁷ on the electron file).
- **Quantised.** Depth and depth range in the Absolute and per-shower translated
  frames are whole numbers of the 20.5 mm layer, and the hit count is an integer:
  their histogram bins align to that quantum, and no log axis is offered. Width
  and height take values on the irregular x and y lattice differences, where no
  quantum exists, so their histograms measure a comb.
- **Display offset.** The Absolute-frame depth is quoted below the front face,
  `z − 3649 mm`; volumes, densities and `centroid_z` stay raw.

**The frame of an aggregate.** An experiment without hits has no sidebar frame,
but the producer's file holds the features of the Absolute, per-shower translated
and Local frames, which `GET /api/features` serves (`coord_system=lab|trans|local`,
through the capability block's `group1_frames`). Each feature card therefore
carries a **Frame** choice, first in its toolbar, visible only for an experiment
without hits: *Absolute*, *Per-shower translated* or *Local*, never the D-frame.
It is the shared `frame` key, so a link restores it, and the feature requests now
carry `coord_system` on an aggregate (they carried none before, and so always
served Absolute). A link naming the D-frame falls back to Absolute, and the card's
caption says so. Every feature drawer names its frame ("frame: Per-shower
translated"), hit experiments included.

**Showers, frames, classes.** Showers with fewer than two hits are left out on
every kind, as the producer's aggregate leaves them out (their SDs do not
exist), and are counted. Features are per shower and the two showers are never
pooled: on two-shower data a **Shower A / B toggle** (`fshower`, default `a`,
never written to the hash) is on all four cards and a `shower` parameter goes on
every feature request; a single-shower experiment sends none and has only A (B is
refused). The momentum **classes** are the features notebook's windows
(1, 2, 5, 10 and 19.5 GeV, each ± 0.5 GeV), or the binary label p < 2 GeV against
p ≥ 2 GeV (an aggregate's stored label, with a notice if it disagrees with p);
the API also takes the producer's 1 GeV bins (`classes=bins`, which needs a
`class_index` for the correlation view). Events outside every class are counted,
never drawn.

**describe (D2, a table).** pandas' `describe()` per class, with the cell
statistic chosen between median [IQR], mean ± SD and min … max. Each cell's
tooltip carries N, the mean's Student-t interval, the SD's χ² interval and its
standard error, c₄(N) and the low-N notes taken at the N that feature actually
used. A cell from fewer than 20 showers is flagged; "mean ± SD" quotes the
spread of the showers, not an interval, and N = 2 is marked as one degree of
freedom. A circular feature gets the mean direction and R̄ in place of a linear
mean, SD or quartile. It is a DOM table, so it has no export.

**corr (D3).** Pearson r per class (or pooled) with its Fisher-z 95% interval,
from N = 4 (SE = 1/√(N − 3)), each event one independent observation, on PuOr
symmetric about zero, linear on [−1, +1] (folded on the dark screen, standard in
print, as on Page 1), lower triangle only. Floored volume factors are left out
only of the pairs whose values they corrupt (the volume and the two densities;
on by default for this view, off elsewhere, where the floored events are counted
instead). An azimuth has no linear r: its cells are hatched, never on the colour
scale, and carry Mardia's circular-linear R, or the circular-circular r_c of two
azimuths, with event-grouped jackknife uncertainties; the notebook's linear r of
`avg_phi` is in its tooltip for parity only. **A cell whose 95% interval contains 0,
or that has no interval, is faded** (opacity 0.35, `correlation.js`
`containsZero`), the r label colour chosen against the faded fill and the tooltip
saying why; the drawer counts the faded cells under *Disclosures* and explains
them under *Marks and legend*. The fading is opt-in: only this card asks for it
(`fadeNull`), and Page 1's C8 matrix, which never passes the option, is drawn as
before.

**hist (D4).** Integer counts on edges every class shares: the Rice count of the
smallest drawn class, aligned to the lattice quantum where values are quantised.
The CLAUDE.md ladder applies per class: the events themselves below N = 15 (at
most 14, in the tinted, captioned band whose heights are drawing offsets), a
density histogram from N = 15, a Gaussian KDE (Silverman bandwidth) from N = 8,
and a KDE is never drawn on an azimuth, which is shown on its full period
(−π, π]. The scale is automatic (logarithmic for a positive feature spanning a
decade or more) or chosen. The range and the density axis follow the measured
values of the series with weight, so events at core.py's floor are a counted
underflow, not the end of the axis; an under-powered curve above the range is
clipped with a caret carrying its true peak; a range from weak evidence is
labelled provisional. The lag-1 comb statistic of the pooled counts is measured
against counting noise (−10/72, derived for independent counts and not the
occupancy threshold of the staggered lattice) and reported.

**hist2d (D5).** Each class as a small multiple of the feature against the
deposited energy, on edges and one log colour scale shared by every multiple (48
bins per axis, 32 beyond six classes, fewer if the budget demands), an empty bin
transparent, and the events themselves below N = 15. The y axis is named
"E [GeV]" when the payload names none, never "y", and a log axis labels an end
only where it is a whole decade (`hist2d.js` `withDecadeEnds`).

### The primary-tag rate

`GET /api/primaries` (single-shower hit experiments, whose files tag each hit
row with the particle attributed to its cell and flag the primary with
`is_secondary = 0`) draws, per 1 GeV bin, the fraction of selected events that
hold no primary-tagged hit row. An event is the unit, so the fraction is a
binomial proportion of independent events and its capped, asymmetric whisker is
the 95% Wilson score interval, never the Wald interval, which collapses to a
point at zero events and leaves [0, 1] at small N. It is quoted from N = 1,
honestly wide, and a bin below N = 20 is called out. The y axis is the whole
0–100% a proportion can take. The selection's overall fraction is a dotted rule;
its interval is in its tooltip, not drawn, so the rule does not read as a band of
dispersion. How many tagged rows an event holds (0 to 10, the last bucket "10 or
more") is exact counts with no whisker, in the drawer. The payload quotes a
reference measurement of the electron file (most events hold no primary-tagged
row, reversing the roadmap's expectation), labelled as a measurement of that file
and not of the selection on screen. The card reads the event table only; no hit
is scanned.

### The 3-D views

**A recorded exception.** CLAUDE.md forbids 3-D projections as chartjunk; the
reference notebooks' 3-D event and species displays are kept under a stated
exception, and every 3-D drawer quotes it. The view is **orthographic** (no
perspective, so no length is foreshortened), draws **one millimetre the same
length on all three axes** (1:1:1 from the physical spans, never from a matrix
shape), draws every cube at the **measured size** of what it stands for, uses
**flat, unlit colour** (`shading: 'color'`; lighting would modulate the
brightness that encodes the value), and stands **always beside three paired 2-D
projections** that carry the same selection quantitatively. A rotated 3-D
picture is not a publication figure, so a 3-D card has **no export**; the
projections beside it are the exportable figures, and the drawer says so. A cube
hides whatever lies behind it from the current viewpoint, and the drawer says
that too. Cubes are placed through the payload's coordinates, never by
`index × pitch` (the x lattice is irregular).

**Rendering.** The 3-D views draw with the vendored `echarts-gl`, loaded by this
page only. At most **two WebGL contexts** exist, one for the event chart and one
for the ensemble chart, created the first time their pair draws and never
disposed (a change of experiment clears them). Availability is probed once with
a transient context; without WebGL, or without the renderer, a 3-D card says so
in a notice and asks the server for nothing, and its projections still load. A
lost context shows a notice of the same kind and the chart is rebuilt from the
payload in hand when it is restored. echarts-gl's bar3D draws columns from zero,
so a floating cube is an invisible spacer bar of the cube's base height with the
cube stacked on it; cubes the colour taper makes translucent are a series of
their own, because echarts-gl turns a series' depth writes off once any item is
translucent. The camera opens at the angles `alpha` 25° and `beta` 40°.

**The opening zoom is fitted to the card's width.** An orthographic camera fixes
its height and takes its width from the viewport, so a card narrower than the box
cut the view's sides (the vertical axis title first). `orthographicFit` measures
the card: the box, its ticks and its axis titles span 1.134 times the viewport
height (measured in Chromium on a 100-unit cube, the widest box), so a plot area
narrower than 1.16 times its height (the card's width less the 60 px of the colour
legend) widens the opening size from 160 just enough to keep them inside. A resize
refits the zoom only and keeps the reader's rotation and pan; a blank or lost
chart is never refitted.

**The plot's height follows the card's width, and the ticks are round.** The
3-D plot is h = clamp(round((w − 60) / 1.16), 360, 560) px tall for a plot area
w px wide (`voxels.js` `glPlotHeight`): the height at which the opening view
fills the viewport left of the 60 px colour legend, so a narrow card no longer
leaves an empty band above and below the box. `voxel_views.js` `fitPlotHeight`
sets it inline before the chart is created and on every resize, never through
CSS, so the layout snaps with no transition. Measured at windows 1440, 1600 and
1920 px wide, the plot is 506 × 384, 586 × 453 and 746 × 560 px. The axes take
ECharts' own step, `nice(span / splitNumber)` (`niceStep`), with each axis's
origin rounded to floor(lo / step) · step so the cubes, spacers and halos sit at
mm − origin and the ticks fall on round millimetres. Three facts about
echarts-gl, measured in Chromium, shape this: an explicit axis `interval` starts
its ticks at the axis *minimum* (680, 880, …), so `axis3D` sets `splitNumber`
alone and lets ECharts put its ticks on multiples of the step; `showMinLabel`
and `showMaxLabel` are ignored, so the formatter blanks any value off the step
grid, which stops an off-grid end printing over a tick ("1840" over "1800");
and an axis title's `nameGap` is in *world units*, not pixels, so
`AXIS_NAME_GAP` is 30 (at the default 20 "y [mm]" touched its middle tick). A
side whose ticks are closer than 10 box units (`MIN_LABEL_UNITS`) labels only
the multiples of a whole-number multiple of the step (`axisTicks().labelStep`);
every tick is still drawn. The labels are GL sprites, so no browser assertion can
measure their boxes: the gap is pinned in a Node test and the three widths were
checked by eye.

**One event (C5, C6).** `GET /api/event?format=voxels` draws one event as cubes in
one frame. The cubes need hits and the lattice; a raster request is never refused
over a cube-only parameter (`frame`, `channel`, `model`, `cap`), and the cubes
refuse a `cap` outside 100 to 15,000 (default 6,000).

- *Two regimes.* In the Absolute and per-shower translated frames one cube is one
  detector cell at its measured lattice coordinates, sized by the measured cell
  footprint (48.27 × 48.60 mm) and the 20.5 mm layer pitch. The rows of one cell
  are merged (energies summed, network values energy-weighted) and a 2-bit code
  records whose rows the cell holds (A, B, an `'A+B'` row, or a split cell). In
  the Local frame and the D-frame a cell is tilted or turned, which a bar3D cube
  cannot be, so each footprint is split into k × k (× k_z) equal sub-deposits that
  move with the frame and are binned onto axis-aligned voxels of a 20 mm grid,
  the Event Inspector's own energy-conserving splat. k is chosen by convergence
  (k = 12, k_z = 4 in Local, k_z = 1 in the D-frame, measured against a k = 32
  reference), not by the 2-D gap-free rule written for panels that sum an axis;
  the pitch coarsens only while a transverse axis would pass 256 voxels, and
  then as the size budget demands.
- *Channels.* Volumetric energy density E/V (GeV/mm³) on a log ramp from a floor
  to the brightest drawn cube: the floor is the 1st percentile of the positive
  densities *of what is drawn*, not of the detector's cells (a voxel holds only
  the part of a tilted footprint that overlaps it, so voxel densities run below
  cell densities); a cube below the floor is drawn at the lowest colour and
  counted, and a frame whose cubes all share one density says its ramp is
  degenerate. On screen the lowest colour is the ramp's first colour with 3:1
  contrast against the card, not the palette's darkest, so no opaque cube is
  drawn below 3:1 (see [Display channels](#display-channels)); the drawer says so. Grad-CAM and the segmentation error |f_A,pred − f_A,true| are linear
  on [0, 1]; Shap-CAM is signed, linear on [−1, +1] on the folded PuOr, and a raw
  Shap-CAM cube near zero takes its sign's first 3:1 colour where the 2-D panels
  draw zero in border grey, since a cube prints no number; these
  three need the networks' columns. The **species** channel (single-shower hit
  files) takes stable global codes (e⁻, e⁺, γ, n, p, π⁺, π⁻, then "other" in
  grey) on a qualitative palette whose every pair stays apart under simulated
  deuteranopia and protanopia, never the notebook's per-event assignment; a
  species legend hides a species or isolates one; primary-tagged cubes get a halo
  (at most the 12 most energetic, the rest named in their tooltips).
- *Cap and window.* Cubes are ranked by energy and the `cap` most energetic are
  drawn, in ascending energy (the notebook's draw order, bright cubes last); the
  energy beyond the cap is counted beside the energy outside the window. **The
  window takes one half-width per axis** (`window=per_axis`, the cubes' default
  and what the Models page asks for on both of its requests), on the drawn
  frame's own coordinates:
  - each axis takes its own energy-weighted 0.1st–99.9th percentile range of the
    cells, padded by one cell footprint across the beam and one layer pitch along
    depth (in Local, whose rotation tilts a cell into depth, each axis takes the
    larger of the two), snapped outward to 20 mm and never below 150 mm;
  - u, v (Local) and x′, y′ (D-frame) stay symmetric about the origin;
  - the box stays 1:1:1, its sides as long as the spans (`boxSizes`). Under one
    shared half-width a shower with a few far stray cells was drawn in a box
    metres deeper than the detector: the synthetic single-shower event 3 in the
    Absolute frame, with a detector 1,230 mm deep, was a box of 4,040 × 4,040 ×
    4,040 mm (z 1700–5740 mm) and is now 4,040 × 1,480 × 300 mm (z 3570–3870 mm);
  - the cells outside are counted, not drawn: `cap.cells_outside_window`, with
    the energy and its share in the cap note, and `window.rule` names every
    half-width ("detector x 2,020 mm, y 740 mm, z 150 mm; …"). Each axis cuts its
    own 0.1% tails, so more cells fall outside than under a shared half-width: in
    the two-shower baseline's Absolute frame 10 of 921 cells and 0.162% of the
    energy (9 and 0.069% under the shared rule);
  - the Event Inspector keeps one shared half-width for its nine panels.
- *Which event.* The link's `voxel_event`, or, with none, the densest event of
  the selection (`GET /api/event/pick?rule=densest`, the High-energy notebook's
  rule: most cells, ties to the lowest number), never written to the link. The
  card has an event box, previous and next, **Densest**, and **Pick**, which draws
  seeded from the most tilted of the dense events (the local-coords notebook's
  rule; each click takes the next seed) and states the rule in the drawer.
  Showers: A, B or both, **both only in the Absolute frame** (each per-shower
  frame holds one shower at its own entry point). The API also serves the
  D-frame's cubes (two showers per event), but the pair draws Absolute there, as
  below.
- *The pair.* The three projections are the Event Inspector's rasters
  (`GET /api/event`, Page 1) of the same event in the same frame and shower, so
  the pair shows one picture twice. Both requests carry `window=per_axis`, so the
  box and its projections span the same millimetres in the Absolute, per-shower
  translated and Local frames (a test holds them equal on event 3 and on
  two-shower event 0). Each projection is sized from its two millimetre spans and
  letterboxed, so unequal windows give honest, unequal panels: event 3's x–z
  projection is a tall narrow strip, 4,040 × 300 mm. The drawer then says "Axes
  1:1 (isometric), per-axis half-widths u 700 mm, v 660 mm, w 560 mm on all three
  projections" (Page 1's sentence is unchanged for its shared window). One edge
  case: the per-shower translated depth raster is the shower's own native layers,
  and its pad is one layer pitch, so a first layer whose centre sits exactly on
  the window edge is drawn whole, half a layer past the axis; a channel change asks for new cubes only,
  because the raster is energy density in every channel. The D-frame has no
  per-event raster, so the pair draws Absolute there and says so under its
  titles. When the cubes show both showers, the projections show shower A and
  say so.
- *Budget.* The whole body is measured as served against 100 KB
  (`api/budget.serve_measured`): while it is over, the splat pitch is lowered and
  then the cube cap, with a stated sentence. The cubes are integers and a
  quantised colour code packed as base64, never a hit row; the 64 brightest carry
  exact values and every other value is read back from its 8-bit code and labelled
  so.

**The selection (the ensemble cloud).** `GET /api/voxels` draws the whole
selection's energy as a cloud of axis-aligned **40 mm voxels** in the Local frame
(every shower on its own entry point and incident direction) or the D-frame
(two showers per event). The per-shower translated frame is refused (its exact
box-overlap splat has no 3-D accumulation) and so is the D-frame on one shower
per event.

- *One scan, two levels.* The keyed sub-deposits of the 2-D panels' frames are
  aggregated to the raw 20 mm 3-D grid and, in the same query, to 40 mm voxels
  that keep each voxel's raw fine-bin *peaks*, so the reference density is the raw
  grid's maximum. The fine bins of each transverse axis are paired across the
  origin, so the origin (each shower's entry point, or the midpoint of the two)
  runs through the middle of a voxel column rather than along an edge, where it
  would split the shower core over four columns.
- *Density, floor, cap.* ρ_v = E_v/(N·dV_v) in GeV/mm³ per event, relative to the
  raw 20 mm grid's 3-D peak ρ_ref (a voxel is the mean of its four fine bins, so
  ρ_v ≤ ρ_ref always). The legend's top reads "1 = ρ_ref" (or "1 = cam_ref" for
  an attention channel) where the ramp tops out at the reference, and "N × ρ_ref"
  where the selection is brighter (`voxels.js` `referenceTopLabel`), not an
  exponent such as "10⁰·⁰ a.u."; the drawer quotes it. A voxel is drawn iff ρ_v ≥ 10⁻³ ρ_ref (the energy-weighted
  CAM channels: |value| ≥ 10⁻³ of the channel's own raw peak, diverging on PuOr
  for the signed one). Of those voxels the brightest `cap` by energy are shipped
  (default 15,000, 1,000 to 15,000), one stated rule for every channel. Every
  joule lands in exactly one of *drawn*, *below the floor*, *beyond the cap*,
  *half-width edge voxel* or *outside the grid*, and the five fractions sum to one.
- *Packing.* Layer runs: one u16 count per depth layer, then an (x, y) ordinal pair
  and one colour code per voxel, three bytes a voxel, about 60 KB of base64 at the
  full cap. Depth is the grid's own layer centres, never assumed uniform (the
  D-frame's are the native layers). The whole body is guarded against 100 KB like
  every route's: a step is priced from what a voxel costs, then measured, and the
  cap moves to the largest that fits, with the sentence.
- *Comb.* The comb is never re-measured here, since a merged grid would hide it.
  The route quotes the matching 2-D bundle's raw-grid measurement, with its source,
  when that bundle is cached, and otherwise says the 2-D panels measure it.
- *D-frame disclosures travel with the cloud*: events entering closer than 80 mm
  apart have a rotation fixed by anchor noise and enter averaged over azimuth;
  the Local frame carries the selection's negative-depth summary. **No ensemble
  direction is drawn** on the cloud in either frame; the D-frame's 2-D projections
  carry its measured axes with their band and envelope.
- *The box is cropped to the projections' window.* The cloud is paired with the
  Physics page's Native Grid projections of the same frame and channel, so the 2-D
  bins are the cloud's raw accumulation bins. The 3-D box is cropped to the union
  of the three projections' axis ranges (`pairedWindow`: each transverse axis
  symmetric about the origin at the energy-weighted 0.1st to 99.9th percentile, the
  recorded window of the co-registered frames), so the cloud and its projections
  show one region. A voxel is placed by its centre; those outside are counted with
  their share of the shipped cloud's value (read back from the colour codes, and
  the drawer says so) and are not drawn, the box extent in the drawer being the
  full accumulation grid. If the projections did not load, the box is the whole
  grid and says so.
- *Controls.* The channel (density, energy-weighted Grad-CAM, energy-weighted
  Shap-CAM) and a camera reset; the frame is the page's (Absolute and per-shower
  translated fall back to Local).

### The XGBoost cards

Four cards read `GET /api/xgboost?view=cv|binary|surrogate|importance` (with
`task=momentum|angle`; `binary` is the momentum task only and a 422 for angle).
Each reproduces what the `XGBoost-Reg-*` notebooks compute, on the experiment's
own event table, from the stored [analysis](#the-xgboost-analysis). **They are
dataset-wide, as the notebook computes them**: the selection does not apply, the
payload says so (`filtered: false` and one sentence), and the card sends only
the experiment and the task. The Selection section of each drawer therefore
leads with that sentence and the run (species, seed, model file and its
sha256, XGBoost version, analysis version, the rows and the split), and every
card carries the [split check](#the-training-split-check) as a disclosure and,
when it fails, a hazard flag. Task and, for the surrogate, the output (φ or θ)
are page state in the link.

**E1, five-fold cross-validation.** `KFold(5, shuffle=True, random_state=42)` over
all rows; each fold refits the notebook's regressor (`reg:squarederror`, 100
trees, learning rate 0.1, `random_state=42`) on four fifths and scores the fifth,
with MAE, MSE, RMSE and R². One small multiple per metric, each on its own scale.

- *Two marks, two quantities.* A fold value is one observation, so it is an open
  ring. The aggregate is the mean of the five, a filled diamond with a capped
  whisker that is the uncertainty of the mean: **Nadeau and Bengio's corrected
  resampled t interval** with 4 degrees of freedom (t = 2.776). Any two folds
  share three quarters of their training rows, so their values are not
  independent and s²/k would understate the variance of their mean; the
  correction uses SE² = (1/k + n_test/n_train)·s² = 0.45 s² instead of s²/5. The
  plain sample SD of the folds is a different quantity (their spread), is in the
  mean's tooltip beside the SE, and has no mark since the folds are drawn.
- *Scales.* The error metrics are magnitudes and start at zero. R² is read near 1,
  where folds differ in the third decimal, so its axis runs from a round value
  below the lowest fold or interval end up to 1, with a break mark on the axis and
  the start in the panel title (the offset label CLAUDE.md asks of a truncated
  scale); an R² at or below zero, or a spread over half the unit range, gets the
  plain axis from zero. Intervals are clipped to the range a metric can take
  (errors ≥ 0, R² ≤ 1) and the card says which were.
- *The angle task* has two rows. The top is the notebook's parity numbers
  (sklearn's uniform average over φ and θ, φ unwrapped, in rad), labelled so and
  never on one axis with the per-label values, since an unwrapped azimuth error of
  2π − ε would set the scale and flatten θ. The bottom is per label, in mrad: θ's
  MAE, RMSE and R², and φ's MAE and RMSE of the residual wrapped to (−π, π], with
  no R², which is undefined for an azimuth. This notebook cell fits the angle
  task on `[incoming_theta, incoming_phi]`, whereas the shipped model predicts
  `[incoming_phi, incoming_theta]`; the drawer says so.
- *The refits are what the notebook computed*: refitting on the reproduced 80%
  recreates the shipped electron momentum model exactly (max |Δpred| = 0), and
  XGBoost's result does not depend on the thread count.
- *The legend uses short names.* The diamond's entry reads "95% NB-corrected t
  CI of the mean" (the payload's `corrected_resampled_t`; "95% t CI of the mean"
  for any other method) and wraps between the card's side insets
  (`xgb_cv.js` `intervalShortName`, `wrappedLegend`). The tooltips and the
  drawer keep the payload's full label, and the drawer says "(legend: …)".

**E3, Binary Thresholding at 2 GeV, on a 99 : 1 sample.** From the validation split,
class 0 is p < 2 GeV and class 1 p > 10 GeV (p > 2 GeV when fewer than 50
validation rows lie above 10, and the card says so); pandas' seeded sampler draws
1,980 and 20 rows (fewer where a pool is short), shuffled, and the shipped
momentum regressor is thresholded at 2 GeV. The **confusion matrix is counts**,
which carry no interval and no colour ramp (at 99 : 1 a ramp would say only that
class 0 is large); each cell prints its count and its share of the true class.
Beside it, accuracy and the per-class recall and precision are proportions k/n of
independent rows, each a point with a capped, asymmetric **95% Wilson score
interval**, which never leaves [0, 1] and does not collapse at 0 or 1 (a perfect
recall of 20 of 20 has a lower limit of 0.839). The **balanced accuracy**, the
mean of the two recalls with the class sizes fixed by the sample design, carries
**Newcombe's MOVER interval** built from the two recalls' Wilson limits and
clipped to [0, 1], named in its own legend entry so the methods never mix: a
class classified perfectly still contributes its Wilson half-width, which a
bootstrap of the rows or a Wald interval loses. A rate whose denominator is empty
is undefined and drawn as no point. The notebook's support-weighted precision,
recall and F1 are in the drawer for parity, labelled as dominated by the majority
class and given without intervals. The minority class has at most 20 rows and
the card states its size and that its intervals are correspondingly wide.

- *The ratio actually drawn is stated.* "99 : 1" is the design, and a short pool
  or a small validation split can fall short of it. A third line of the matrix's
  key gives "class 0 : class 1 = n0 : n1 (designed 99 : 1)" from the payload's
  `counts` (shortened to "class 0 : 1 = …" or "n0 : n1 (designed 99 : 1)" where
  the card is narrow), and the drawer's Selection section says, for example,
  "Realised: class 0 : class 1 = 27 : 20 (designed 99 : 1)" and repeats it under
  *Drawn* and *Legend*.
- *Which rates depend on the class ratio.* Accuracy and the two precisions are
  functions of the mix of classes the design fixed and do not transfer to another
  mix; the recalls and the balanced accuracy do not depend on it
  (`views.PREVALENCE_DEPENDENT`, each rate's `prevalence_dependent`). Each rate's
  tooltip says which, each Rates line of the drawer ends "depends / does not
  depend on the class ratio", and `notes.prevalence` explains it. Accuracy's
  Wilson interval treats the rows as one binomial sample although the class
  sizes are fixed; the stratified variance Σ (n_c/N)² r_c(1 − r_c)/n_c is never
  larger, so the interval is conservative, and its label says so ("95% Wilson
  score interval (binomial; conservative under the fixed class sizes)").
- *The legend* names the balanced accuracy's interval "95% MOVER CI (from Wilson
  limits)" (or "95% Newcombe CI (from Wilson limits)") and wraps like E1's.

**E4, the depth-3 surrogate tree.** `DecisionTreeRegressor(max_depth=3,
random_state=42)` is fitted, as in the notebook, to the shipped booster's own
predictions on all rows, in-sample. It is **a description of the booster, not an
estimate**: each of its at most 15 nodes prints its rule (feature, the feature's
frame, threshold), the rows that reach it, and the mean of the booster's
predictions over them ± the within-node SD, an uncapped spread with no whisker.

- *Fidelity is judged per output, and φ on a circular R².* The tree is fitted to
  every output at once and sklearn's score averages them, which can hide an output
  the tree does not describe at all. Each output's own fidelity is printed, a "low
  surrogate fidelity" warning is raised for each output whose **judged** number is
  below **0.5**, and the average is never judged nor printed alone (an R² that
  rounds to 1 while its MAE is above 0 prints as "> 0.999999"). The judged number
  is the R² for θ and the momentum, and for φ the **circular R²**,
  1 − Σ(1 − cos Δ) / Σ(1 − cos(φ − φ̄)), with Δ the booster-to-tree residual
  wrapped to (−π, π] and φ̄ the booster's circular mean, beside the **wrapped
  MAE**, the mean of |Δ| (`analysis.circular_fidelity`). A linear R² of φ counts a
  disagreement across the ±π seam as about 2π, so it is kept, with the linear
  MAE, as notebook parity and says so ("φ circular R² 0.966, linear R² 0.978 for
  parity; θ R² 0.00391 (sklearn's average over the outputs 0.491, which no single
  output has)"). Each output carries `judged_on` (`r2_circular` or `r2`) and `low`,
  the payload `fidelity.threshold` 0.5, and the `fidelity` note defines both
  measures.
- *The tree's criterion explains θ.* The splits minimise the summed squared error
  of the outputs, φ (unwrapped, in rad) and θ together; φ spans about 2π rad and
  θ a few tenths of a radian, so φ's variance dominates every split and θ is
  barely described. Every angle drawer says so (`notes.criterion`).
- *φ is never coloured and never averaged linearly.* A sequential ramp would put
  −2.7 and +2.7 rad, 0.8 rad apart on the circle, at its two ends, and CLAUDE.md
  sanctions no cyclic ramp. A φ box prints the **circular mean** of the booster's
  predicted azimuths over its rows ± the circular SD √(−2 ln R̄), with R̄; where the
  Rayleigh p = exp(−n R̄²) exceeds 0.05 the rows share no direction and the box
  says "no common direction" instead of a mean (**boxes behind a Rayleigh gate**).
  sklearn's linear mean, which the notebook printed, is only in the tooltip and the
  drawer, named as parity.
- *Within-node SDs are ddof 1, and a node under 20 rows is weak.* A node's ±SD is
  the unbiased sample SD of the booster's predictions over its rows, null where
  the node holds one row ("undefined for one row"); the impurity stays sklearn's
  own (ddof 0), as the tree's. Every tooltip names the estimator ("within-node SD,
  ddof = 1") and adds "; n < 20: weak" under 20 rows (the payload's
  `weak_below_n` 20, CLAUDE.md's robust floor), each node line in the drawer says
  "(weak: under 20 rows)", and the drawer lists the weak nodes.
- *The colour domain comes from nodes of 20 rows or more.* A tree's extremes are
  its leaves, often its smallest, so a domain over every node was set by the
  least-supported values. `colour_domain` takes the nodes with n ≥ 20, and a node
  beyond the domain takes its end colour, is marked ▲ (above) or ▼ (below) after
  its value, and is counted and named in the drawer; its tooltip says "▲ above the
  colour domain … drawn in its top colour". When fewer than two distinct values
  come from such nodes (a tiny experiment) every node sets the domain and the ramp
  title says "(provisional)". The payload's `color_domain_basis` gives `min_n`,
  `n_nodes`, `provisional`, `n_above` and `n_below`. On the recorded momentum tree
  the domain is 1.21–11.27 GeV from 9 nodes (it was 1.21–18.07), and the leaves of
  5, 3 and 2 rows are marked ▲.
- *Units.* A φ box, which is not coloured, prints its unit: "circ. 1.45 ± 1.3 rad
  · R̄ 0.43", and the drawer's legend says "Values are in rad."
- *Colour and layout.* θ and the momentum are coloured by the node value on the
  user's sequential ramp narrowed to the run that clears 3:1 against the card in
  force (Viridis from 0.376 on `#1c2128`, up to 0.600 on white), leaves filled and
  splits outlined in their value's colour. The tree is drawn top-down (≤ left,
  > right) when every box's text fits its share of the width, otherwise as an
  indented outline in depth-first order, which a single-column export always is.

**E5, gain importance.** The bar, from zero, is the shipped booster's
`feature_importances_`, the notebooks' own measure: its **average split gain**,
normalised to sum to 1, labelled so on the axis ("Share of the summed average
split gain [%] (XGBoost feature_importances_)"): one model, never the folds' mean.
That is a different ranking from the **total gain** (average gain × number of
splits, which `get_score('total_gain')` returns and a test checks equals gain ×
weight for every feature): a feature split on rarely but strongly leads one and
not the other. Each feature's share of the total gain and its rank by it are
therefore in its tooltip ("share of the total gain (average gain × splits): …%
(rank n by total gain) — not drawn") and in its drawer line, and where the top
feature differs between the two the drawer sets the rankings side by side: on the
recorded momentum importance, "energy_density_trans 40.2%, num_hits 33.3%,
energy_density 26.5%, against the bar's num_hits 44.4%". The payload carries
`features[].total_gain_share`, `total_gain_rank`, `measure.total_gain` and
`notes.average`.

On a line of its own under the bar, the five refits' normalised gains are open dots
(five observations) and their mean is a short tick inside a thin capped bracket,
its corrected resampled t interval (as E1, with the short legend name "Fold mean ·
95% NB-corrected t CI" where the card is narrow), clipped to [0, 1], the range of a
share, with a per-feature flag. The bar and the bracket never share a line.
Colour is the feature's frame (Absolute, per-shower translated, Local, or none for
a count) in ColorBrewer qualitative hues, in the order the performance card uses.
The plot is a fixed 330 px that holds about fifteen readable rows, so the card
draws the **top 15** of the features that carry any gain, in the shipped order,
and **counts the rest on the plot**: the used features beyond fifteen, and the
features no model ever split on. The Details drawer **lists every one of the 52
features** with its numbers (the average-gain share and the total-gain share with
its rank, the fold gains, mean, SD, interval, and the raw `get_score` gain, weight
and cover). A gain importance says how much a
feature's splits reduced the training loss, not how much the prediction depends
on it, and correlated features share or swap their gain between refits.

### The XGBoost analysis

#### Where the models come from

The repository ships the regressors the notebooks trained, one momentum and one angle model per species and seed, each reading the
52 event-level features of the v3 aggregate. The service finds them by scanning
a folder, `CALOSRV_MODEL_DIR` (see [Configuration](#configuration)), and computes
every card itself from the model and the experiment's data, once, in the
background. It does not ship precomputed figures. The folder looks like this:

```
xgboost_models/
  xgboost_electron/
    standalone_momentum_s1_model.json     # one target: the incident momentum
    standalone_angle_s1_model.json        # two targets: [incoming_phi, incoming_theta]
  xgboost_muon/ …    xgboost_pion/ …    xgboost_proton/ …
```

The libraries are `xgboost-cpu==3.2.0` and `scikit-learn`; the CPU wheel avoids the NCCL payload of
the plain `xgboost` wheel. Everything is keyed by (species, seed), and the
pairing takes whatever seed the source file's name declares. Only seed-1 models
and aggregates ship today.

#### What is refused, and why

The scan never raises: an unusable file is listed with its reason and left out, so one bad file cannot stop the server.

| Refused | Because |
|---|---|
| a file or directory that does not follow `xgboost_<species>/standalone_<task>_s<seed>_model.json` | the name is the only declaration of species, task and seed |
| a task other than `momentum` or `angle` | those are what the notebooks trained |
| a symbolic link (file or species directory), a non-regular file, a file over 256 MB (checked before reading) | the folder is mounted from the host; a link out of it, to `/dev/zero` say, would hang the boot scan or publish a file nobody meant to |
| invalid JSON, JSON nested too deeply to parse, or a header that is not an XGBoost gbtree model | one bad file must not stop the scan of the others |
| no feature names, or a feature named twice | the columns could not be matched to the event table |
| an objective other than `reg:squarederror` | the notebooks and the refits use it |
| a momentum model with other than one target, an angle model with other than two | the task names the output count |

An experiment pairs only when all of these hold; otherwise the pairing is refused
with a sentence naming what is missing, which travels to the capability block and
Admin Settings.

- it is the event-level aggregate kind (the models read its 52 v3 features);
- it was built from **one** source file, whose name parses as
  `<species>_standalone_…_aggr_s<seed>_v<n>` and ends there (a cut such as
  `…_aggr_s1_v3_head` is a different set of rows, on which the notebook's split
  means nothing);
- both tasks' models exist for that species and seed;
- every feature of both models maps, through the `ddl` vocabulary, to a column of
  the event table (an angle model that needs a feature the table lacks refuses
  the pairing, naming it).

A run itself fails, with its reason, when the experiment holds fewer than ten
events (the 80/20 split and five folds need that), when a label is missing or not
finite (dropping rows would move the notebook's split), or when the [output order
check](#the-training-split-check) finds the angle model's φ and θ outputs swapped.

#### The background analysis

One analysis runs at a time, on a worker of its own with a single slot, never on the ingest worker (which would hold every upload
behind it) and never under the write lock (which would stall every write in the
process). It reads the event table through a read cursor, computes with half the
cores (`nthread = max(1, cores // 2)`) so the server keeps answering, and takes the
write lock only for the one transaction that stores the result. It is queued

- after an aggregate experiment becomes ready (an ingest, the drop folder or a
  rebuild);
- at every start, for each ready paired experiment whose stored analysis is
  missing or stale (never at import time);
- by **Rescan models** and **Re-analyse** in Admin Settings.

Queueing is a test-and-set under one lock: an analysis already queued or running
is never queued twice nor reset to "queued", whichever of the boot check, a scan,
the ingest hook and Re-analyse gets there first. There are eighteen steps (the
read, the split check and hold-out predictions of each task, five fold refits per
task, the 99 : 1 sample, a surrogate per task, the gain importances, the write);
the capability block's reason reads "Analysing: *n* of 18 steps" while it runs, so
the cards say why they are shut. Each experiment's status is held in memory:
`unpaired`, `not_ready`, `queued`, `running`, `done`, `failed` and `stale`, tied
to the registry row's creation time, so an experiment replaced by a new ingest is
a new experiment and a deleted one is forgotten. A server shutdown cancels what
is queued and lets the run in progress stop at its next step boundary, so it never
queries a database the application is closing.

#### What it stores

Six tables per experiment, written together, under the write lock, in one transaction (drop, create, insert, commit), so a reader sees the
previous analysis or the new one and a failed write leaves the previous one in
place. `DELETE /api/experiments/{name}` drops them with the experiment.

| Table | Holds |
|---|---|
| `xgbrun_<name>` | one row per task: species, seed, model file and sha256, labels, features, library versions, analysis version, row counts, the split check, surrogate fidelity, timings |
| `xgbpred_<name>` | the shipped models' predictions on the 20% validation rows (E2, prediction against truth) |
| `xgbfold_<name>` | E1: every fold's metrics, overall and per label |
| `xgbimp_<name>` | E5: the shipped booster's gain, weight and cover, and each fold's normalised gain |
| `xgbbin_<name>` | E3: the 2,000-row sample (class, prediction, thresholded class) |
| `xgbtree_<name>` | E4: the tree's nodes with their per-output means and variances |

#### Staleness and re-analysis

A stored analysis is current while every input it was computed from is unchanged, and its stamp records them all: the analysis
version (`ANALYSIS_VERSION`, bumped whenever a change would change a stored
number; it is 3, which stored the surrogate's within-node variance at ddof 1 and
φ's circular fidelity in `details.surrogate_outputs.phi`, so an analysis of
version 2 reads stale and the boot queues it again), each model file's sha256, the versions of XGBoost, scikit-learn, numpy
and pandas, the event count with a sha256 of the `event_number` column in order,
and a sha256 of every value the analysis reads (the momentum bins, the labels and
each model's features, with their names, dtypes and shapes). Any difference makes
it stale and `stale_reasons` says which. The value hash needs the whole feature
table read, so it is compared only where an analysis may be queued: the worker
before it recomputes, the boot check and **Rescan models**. A rebuild that
re-derives the event table byte for byte leaves the analysis current and costs one
read.

- `GET /api/admin/model-runs` is **read-only**: it rescans the folder (headers are
  cached by size and modification time), re-pairs every aggregate experiment,
  compares the cheap part of the stamp and may report an analysis `stale`, but
  queues nothing.
- `POST /api/admin/model-runs/scan` (**Rescan models**) compares the whole stamp
  and queues every missing or stale analysis, unless its last attempt failed on
  exactly these inputs; it answers with the list the `GET` reads.
- `POST /api/admin/model-runs/{table_name}/analyse` (**Re-analyse**) recomputes
  even a current analysis. A failed analysis is not retried by a scan while its
  inputs are unchanged, only by Re-analyse, a restart or a changed input, so a
  broken model does not fail in a loop. It is a 404 for an unregistered
  experiment, a 422 with the pairing's reason for one that does not pair or is not
  ready, and a 409 while an analysis of it is queued or running.
- A stored table this release cannot read (written by a release whose columns
  differ) reads as missing and is re-run; an event table that cannot be read for
  the check is recorded as a failed analysis with the reason, never a 500.

#### The training-split check

The hold-out cards are only honest if the 20% validation rows are rows the shipped model never saw. The notebook's split is
`train_test_split(test_size=0.2, random_state=42)` over the rows in file order, and
the analysis checks that it reproduced it: a model predicts the rows it was
trained on better than the rest, so its **validation/training MSE at
`random_state` 42 must exceed that same ratio at every other seed**. The per-row
errors are computed once, from one prediction of every row, and each seed only
re-indexes them; the others are the **99 seeds 0 to 99 without 42**. The check
passes only when `ratio_42 > margin × max(ratio at the 99 others)`, with a
**margin of 1.05 for momentum and 1.6 for angle**. The angle margin is larger
because its per-row errors are dominated by a few rows whose unwrapped φ residual
is near 2π, so its ratio varies far more from seed to seed (the errors are the
training loss's own, unwrapped; wrapping φ was measured to separate worse). On
errors permuted across rows, which is what a split not reproduced looks like,
the check fails 99.995% of trials for momentum and 99.975% for angle (20,000 per
task; the largest permuted ratio was 1.067 and 2.311); the earlier rule, above
seeds 0 and 7 only, passed about one in three.

When it fails the run is flagged *split not reproduced*, with the three numbers in
the sentence, on every card that draws the model's predictions (the XGBoost cards,
E2, prediction against truth, and the Admin Settings row, per task). It is never
hidden by a "done" status. The payload carries `ratio_42`, the maximum of the
others and the seed that gave it, `n_others`, the median, the `margin` and the
`headroom` (`ratio_42` over that maximum), with every one of the 99 other ratios
and their seeds (`ratio_others`, `seeds_others`). The archive's event order is also
recorded: if `event_number` was not strictly increasing in the archive, the cards
say that the event order may not be the file order the notebook split.

**The output order check.** The angle model's outputs are stored as φ then θ. Each
output's mean squared error against both labels is computed (φ's wrapped) before
anything is stored, and the diagonal must be the smaller of its row; a swap fails
the run, rather than storing and serving the two under the wrong labels.

#### Measured on real data

The four seed-1 aggregates in `ingest/` (electron 99,751 events, muon 99,417,
pion 99,687, proton 99,089) were ingested through the drop folder (see [Drop
folder](#drop-folder-automatic-ingest)), analysed through the application's own
queue at analysis version 3 (the stored version-2 analyses were queued again,
"analysis version 2 against 3"), and every XGBoost-related route was then called
once per task and aggregate: 48 requests, all answered 200
(`data/dev/r8/r5_xgboost_v3.json`, `facts` and `runs`). These replace the figures
of an earlier measurement (`data/dev/single/r5_xgboost.json`), which was taken on
an older electron experiment.

| | Electron | Muon | Pion | Proton |
|---|---|---|---|---|
| Analysis time (18 steps, one worker) | 15.9 s | 9.0 s | 9.8 s | 9.5 s |

All four queued together finished in 44.5 s. The largest response of the 48 was
25,907 B (the prediction density of the proton's φ output); the XGBoost views
were 5,525 to 21,456 B (the angle importance the largest), E2 11,565 to 18,223 B
and the prediction densities 23,804 to 25,907 B, each answered in at most
122.8 ms (E2's angle series), all well under the 100 KB contract.

**The split check** (validation/training MSE at `random_state` 42, against the
largest of the 99 other seeds and the seed that gave it; headroom is their ratio,
to be read against the margin):

| Species | Momentum (margin 1.05) | Headroom | Angle (margin 1.6) | Headroom |
|---|---|---|---|---|
| electron | 1.497 vs 1.068 (seed 71) | 1.402 | 17.87 vs 5.158 (seed 27) | 3.465 |
| muon | 1.106 vs 1.018 (seed 27) | 1.087 | 33.39 vs 2.781 (seed 9) | 12.01 |
| pion | 1.277 vs 1.056 (seed 62) | 1.210 | 6.450 vs 1.709 (seed 75) | 3.775 |
| proton | 1.262 vs 1.078 (seed 87) | 1.170 | 3.303 vs 1.526 (seed 51) | 2.165 |

Every shipped model passes; the least margin is the muon momentum model, 1.087
against 1.05.

**E3, the 99 : 1 sample** (class 1 is 20 rows for every species and was recalled
in full; class 0 is 1,980 rows, 1,932 for the pion and 1,841 for the proton, whose
pools were shorter):

| | Accuracy | Recall, class 0 | Precision, class 1 | Balanced accuracy |
|---|---|---|---|---|
| electron | 0.8815 | 0.8803 | 0.0778 | 0.9402 |
| muon | 0.4265 | 0.4207 | 0.0171 | 0.7104 |
| pion | 0.7065 | 0.7034 | 0.0337 | 0.8517 |
| proton | 0.7829 | 0.7806 | 0.0472 | 0.8903 |

For the electron (20 of 20 and 1,743 of 1,980 correct) the balanced accuracy is
0.9402 with a MOVER interval of [0.8592, 0.9469]; the bootstrap interval it
replaced was [0.933, 0.947], which discarded the uncertainty of the 20-row class
that was classified perfectly. Precision of class 1 is low for every species (0.017 to 0.078) although its recall is 1: at 99 : 1 even the electron's 237 false positives (of 1,980 class-0 rows) swamp its 20 true ones, which is why the card draws the per-class rates and keeps the weighted metrics for parity only.

**E4, fidelity per output** (R² of the surrogate against the booster; MAE in the
output's unit; φ is judged on its **circular** R², beside which the linear R² is
kept for parity). The electron angle surrogate is why the warning is judged per
output:

| | Momentum R² (MAE, GeV) | φ circular R² (wrapped MAE, rad) | φ linear R² (parity) | θ R² | sklearn's average |
|---|---|---|---|---|---|
| electron | 0.859 (1.595) | 0.966 (0.210) | 0.978 | 0.0039 | 0.491 |
| muon | 0.462 (1.323) | 0.973 (0.197) | 0.981 | 0.0002 | 0.491 |
| pion | 0.664 (2.427) | 0.956 (0.236) | 0.965 | 0.0505 | 0.508 |
| proton | 0.784 (1.924) | 0.954 (0.231) | 0.963 | 0.0171 | 0.490 |

Every angle surrogate describes φ (circular R² 0.954 to 0.973, linear 0.963 to
0.981) and says almost nothing about θ (0.0002 to 0.05), yet sklearn's average
sits at 0.490 to 0.508, straddling the 0.5 threshold: judged on the average the
pion surrogate would pass and the other three fail, by chance, and none would be
told which output is the problem. Judged per output, on φ's circular R² and θ's
R², θ is flagged for all four and φ for none. The muon momentum surrogate (R²
0.462) is flagged too, the only momentum surrogate under 0.5. For the electron
angle model the root node's linear φ mean is −0.002 but its R̄ is 0.003, so it has
no direction; the leaves have R̄ 0.94 to 0.98.

**φ residuals are circular, and the numbers show it.** The electron φ residual has
an arithmetic mean of −0.020 mrad with a moment SD of 67.1 mrad, whereas its
circular mean is +0.079 mrad, R̄ 0.99853 and circular SD 54.3 mrad.

**What the other cards read** (E1 means over the five folds, R² for the momentum
task / for the angle parity average): electron 0.955 / 0.998, muon 0.254 / 0.998,
pion 0.856 / 0.990, proton 0.875 / 0.989. E5's largest gain: the electron
momentum booster puts 58.0% of its average split gain on `num_hits` (then `mean_r`
6.95% and `weighted_r_mean` 5.28%) and the muon's puts 22.0% on `max_r`; the angle models'
largest are `avg_phi` for the electron (61.0%) and muon (80.6%) and `centroid_y`
for the pion (70.2%) and proton (65.9%).

---

## API

All endpoints return pre-aggregated payloads; none returns a raw hit array.

Every data route takes `table_name` and the kinematic selection
(`e1_min`, `e1_max`, `e2_min`, `e2_max`, `d_min`, `d_max`,
`include_undefined_d`), chained with AND. A single-shower experiment has one
axis, `e1`, the shower's own momentum: a bound on `e2` or `d`, or
`include_undefined_d`, is a 422 naming the field, never ignored. The data routes
are gated by what the experiment can serve: a view its kind, its lattice or its
derived tables cannot serve is refused with a **422**
`/problems/unsupported-capability`, whose body carries `field`, `capability` (the
gate, which is the card id), `kind`, `reason` (the sentence the interface shows
on the card) and `table_name` (`tests/contracts/capability_problem.json`).
Parameters and payload fields below are the ones the checked-in contracts in
`tests/contracts/` pin.

| Endpoint | Purpose |
|---|---|
| `GET /`, `GET /models` | The two pages, Physics and Models. Both stamp their asset URLs and are served `no-cache` (see [Static assets and caching](#static-assets-and-caching)). |
| `GET /api/experiments` | Registered tables, row/event counts, kinematic bounds, the frames/coordinate systems/models/channels each serves (always present, possibly empty), `schema`, archive, the `capabilities` block ([below](#the-capability-block)), compute allocation, and the cold-boot `defaults`. Each distinct detector lattice is sent once, in a top-level `lattices` map keyed by the id each experiment's `lattice.id` names; the catalogue measured 26,582 B on the three-experiment development database. A failed experiment carries its `error`. |
| `DELETE /api/experiments/{table_name}` | Drop an experiment, its tables and its archive. |
| `GET /api/admin/config` | The default view: every value with its source, the saved and environment layers, the options each experiment offers, the drop folder's last scan. |
| `POST /api/admin/config` | Save any subset of the six defaults; `null` clears one. A 422 names the field for an unknown value, experiment or capability. |
| `POST /api/admin/auto-ingest/scan` | Scan the drop folder now. A 409 when it is off. |
| `POST /api/upload` | Streamed multipart ingest of a CSV or Parquet file of any of the three schemas. `force_reingest=true` replaces an existing experiment, which is a 409 without it. A file of no accepted schema is a synchronous **400** carrying `expected` and `found` ([Through the browser](#through-the-browser)). Returns a job id. |
| `POST /api/ingest-local` | Ingest a CSV or Parquet file already under the mounted root, by path, with the same fields and the same 400. |
| `GET /api/local-files` | The CSV and Parquet files under that root. |
| `GET /api/upload/{job_id}`, `GET /api/upload` | Ingest progress and result of one job, and the recent jobs. |
| `GET /api/upload-info` | Upload limits and the disk headroom per format, and the accepted schemas: `schemas` (each with `name`, `version`, `kind`, `label`, `summary`, `n_columns`, `columns`, `note`) and `accepted`, the one-sentence list. `schema` still describes `hits_all_models` alone. |
| `POST /api/admin/experiments/{table_name}/rebuild` | Rebuild an experiment's derived tables from its archive, atomically, on the ingest worker ([Rebuilding derived tables](#rebuilding-derived-tables)). 202 with `{job, poll}`; 404, 409 or 400 as described there. |
| `GET /api/projections` | The three spatial panels as quantised rasters, every response budgeted whole under 100 KB. `coord_system=lab\|trans\|local`, `frame=lab\|canonical` (canonical needs `coord_system=lab`), `model=segmentation\|energy\|angle`, `channel=density\|gradcam\|gradcam_energy\|shapcam\|shapcam_energy` (`mode` is a deprecated alias), `display=native\|continuous`, `rho_norm=selection\|dataset` in the co-registered frames, `anchor=backprojected\|p0` with `frame=canonical` (the D-frame's entry anchor), `coordinates=file\|computed` with `coord_system=trans\|local` (the file's own per-shower columns, or the SE(3) motions applied to the lattice inside the scan; the residual between the two is reported either way). The `local` frame's response carries `frame.negative_w`, the negative-depth block of the statistics card (`available`, `splits`, `affected`, `summary`); the lab payload is unchanged and has no `frame` key. The D-frame (`frame=canonical`) is a 422 on a single-shower experiment, and the whole route on the events-only kind. Unknown values return 422 naming the field. **Payload compaction** (so the 900-view matrix stays under the guard, see [Performance](#performance)): `topk[].value` travels at 7 significant figures, rounded toward zero (the float32 source's precision, so a shipped value never exceeds the cell's own and the brightest value never passes the panel's peak); `meta.stagger` is sent **in the Absolute frame only**, the co-registered frames' comb being `frame.comb` (`measured_on` unchanged); and the per-shower frames' `frame.coordinates.note` is no longer copied into `meta.notices`, the client putting it back in the same position (`frame_views.js` `frameNotices`). Together they save 1.6–3.05 KB a response. |
| `GET /api/event` | The Event Inspector: one shower (`shower=a\|b`) of one event (`event_number`) as nine quantised rasters — original, translated-only and local frames by X–Y, X–Z, Y–Z — with the marks (incident direction, first-layer plane, origin) as 3-D lines and points, the principal-axis tilt, one shared ramp, one window, under the same filters and the 100 KB contract. `coordinates=file\|computed` as above. A 404 names an event the experiment does not hold or a shower with no cell. `format=voxels` is the Models page's 3-D event view instead: the event as cubes in one frame, gate `vox-event`, a body under the same 100 KB contract measured as served. `frame=lab\|trans\|local\|canonical` (default `local`; `canonical` needs two showers), `channel=energy\|gradcam\|shapcam\|segerr\|species` (`gradcam`, `shapcam` and `segerr` need the networks' columns, `species` the single-shower species columns), `model`, `cap` (an integer 100–15,000, default 6,000, read only for the cubes), and `shower=a\|b\|both` (`both` only in the Absolute frame and the D-frame; a single-shower experiment has only `a`). A raster request is never refused over any of these ([The 3-D views](#the-3-d-views)). `window=shared\|per_axis` is the window rule, read by both formats and a 422 naming `window` for any other value: `shared` (the raster's default, and the only rule of the Event Inspector) is one half-width for every axis of every panel, so the body is byte for byte what it was; `per_axis` (the cubes' default, and what the Models page asks for on both its requests) is one half-width per axis of each frame and adds `window.mode`, `window.half_mm_axes` (`lab\|trans\|local`, each `{x, y, z}`) and `frames.<f>.half_mm_axes`, `window.half_mm` then being the largest. Either way the body carries `window.percentiles` (0.1 and 99.9, energy-weighted), `window.rule` naming every half-width and the cells left outside, and each frame's `outside_window` (cells and energy not drawn). The voxel response echoes the rule in `meta.notes.window`. |
| `GET /api/event/pick` | The reference notebook's event selection rule on the current filters: events with more hits than the selection's mean, the `pool_size` (20) with the largest incident angle, one drawn with `seed` (42). Returns the event, the pool and the rule in words. `rule=tilted` (the default, and the only one a request naming none gets, byte for byte as before) or `densest`: the event with the most cells, ties to the lowest event number, which the 3-D event view opens on. |
| `GET /api/window-axis` | The windowed ensemble axis of an absolute-frame depth panel: `panel=yz\|xz`, `t_min`, `t_max` (the displayed transverse window, mm) under the same filters. Per shower the mean trajectory of the events whose entry point lies in the window, the exact dispersion band and the 95 % t-envelope at nine depth stations, the lean / fan gate, the azimuth resultant and its Rayleigh p, and the notes the drawer prints. |
| `GET /api/energy-distribution` | Per-slice Gaussian fits, histograms and benchmarks. `slice_by=d` (the default on two-shower data) slices by the A–B separation, with `d_edges`, from the `coord_system`'s segmentation network (`meta.network`). `slice_by=momentum` (the only slicing of a single-shower experiment, and the B3 card's) places each shower by its own incident momentum: `p_slices=notebook` (default: windows 1, 2, 5, 10, 15 and 19 GeV), `bins` (the producer's 1 GeV bins) or comma-separated window centres in GeV; `p_half_width` (0.5 GeV, up to 10, refused with `bins`); `series=truth\|model\|all` on two-shower data (the deposit split by the true segmentation fraction, the network's, or both). Each slice carries its own axis (`slice_axes`). A parameter of the other slicing is a 422 naming it. **Two-shower `p_slices=bins` with `series=all` is refused (422 on `series`)**: 80 fitted series measured 148,703 B on the synthetic two-shower fixture and about 167 KB on a constructed production-sized sample, over the 100 KB contract at the coarsest rendering the guard reaches; truth or model alone fits, and the notebook windows with `series=all` still serve. More than 40 fitted series (slices × series) on two-shower data is a 422 on `p_slices`. The default `slice_by=d` payload is byte-identical to the one before momentum slicing (pinned by `tests/golden/energy_default.json`). |
| `GET /api/profiles` | C7, the longitudinal and radial profile cards. `shower=a\|b\|both`, `depth=w\|native`, `notebook=false\|true` (the notebook convention is defined along w: a 422 with `depth=native`). Per-bin sums come from `profiles_` and `layers_`, so the response is about 15 KB on every selection. A stale experiment is refused with the rebuild it needs. |
| `GET /api/response` | The sampling-fraction cards B1 and B2 and the resolution σ/μ. `parts=b1,b2,resolution` (default all three; a part not asked for is `null`), `shower=a\|b\|both`, `clip_low` and `clip_high` (the percentiles of B1's displayed axis, which is zero-based, so they are reported, not applied), `bins` (8–500, B1's histogram, default adapted to the smallest drawn series). Also `calibration` and `n_events`. Every kind answers, the aggregate from its event table. The body is measured as served: while it is over 100 KB the numbers are written at fewer significant figures and B1's histogram coarsened, and the step is disclosed; no statistic changes. |
| `GET /api/distributions` | C4. `quantity=u\|v\|w\|energy\|theta\|phi\|p` (default `theta`), `weighting=shower\|hit` (theta, phi and p only: the hit quantities are counted per hit, and `weighting=shower` with them is a 422), `shower`, `clip_low`, `clip_high`, `preview`. One series per 1 GeV momentum bin (up to 20) on shared display bins, exact counts. u, v, w and energy need hits (a 422 on the events-only kind). The display bins coarsen 2× then 4× if a response would reach 100 KB, and say so. |
| `GET /api/correlations` | C8. `coord_system=local\|trans\|lab` (default `local`), `shower`, `energy_scale=linear\|log10`, `preview`. The Pearson matrix of seven variables with event-grouped jackknife intervals, `mardia`, `groups`, `dof` and the method named in the payload. |
| `GET /api/statistics` | C1 and C9. `coord_system=local\|trans\|lab` (default `local`; the absolute frame adds the `z − 3649 mm` row), `shower`, `preview`. `describe` (unweighted and energy-weighted), `n_events` and `negative_w` (a stale experiment gets `available: false` with the reason). |
| `GET /api/model-performance` | `cards[]` of the network `model` (`segmentation` default, `energy`, `angle`) in `coord_system`, each with SE and a named 95% interval, and the per-slice breakdown. `slice_by=d` (default; `d_edges`) gives the separation slices; `slice_by=momentum_bin` adds `by_momentum_bin`, the Models page's E2: per shower, in its own producer momentum bin, for every network frame the experiment offers (RMSE, MAE, median relative error, bias; the angle task adds the median absolute error), and is a 422 on `slice_by` for `segmentation`. An experiment without networks is refused, **except** an aggregate whose XGBoost analysis is done: `slice_by=momentum_bin` with `model=energy\|angle` answers the shipped regressor's 20% validation split as one series (code `xgb`, `cards: []`, `run`, `split`), the angle task adding φ as its own quantity group; any other request on an aggregate is a 422 naming the field ([E2](#network-performance-by-momentum-bin-e2)). |
| `GET /api/prediction-density` | The Models page's prediction-against-truth and residual cards. `model=energy\|angle` (default `energy`; `segmentation` is a 422), `coord_system=lab\|trans\|local` (the network's input frame; unused by an aggregate), `bins` (16–128, default 64; stepped down with a notice when the body would reach 100 KB), `label=theta\|phi` (the XGBoost angle regressor's output, θ by default; the networks predict θ only, so `phi` is a 422 on two-shower data). Per shower (A and B kept apart), a count density on dataset-wide axes, the identity line, and the residual block on the energy panel's ladder; `residual.statistics` is `linear` or `circular` (φ). On an aggregate with its analysis done: the hold-out rows within the selection, one shower, `source` `xgb` ([Prediction](#prediction-against-truth-and-residuals)). |
| `GET /api/features` | The feature explorer, one cached per-event bundle. `view=catalog\|describe\|corr\|hist\|hist2d` (default `catalog`: the features, flags, class sizes and which views the experiment serves), `coord_system=lab\|trans\|local` (default `lab`), `shower=a\|b` (default `a`; `b` is refused where there is one shower), `classes=windows\|bins\|label`, `class_index` (`corr`: a class index or `pooled`, the default; required with `classes=bins`), `feature` (`hist` and `hist2d`, an id from the catalog), `scale=auto\|linear\|log`, `y_scale=auto\|linear\|log` (`hist2d`), `exclude_eps` (leave out events whose value involves core.py's 10⁻⁶ mm floor; default true for `corr`, false elsewhere). Each view is its card's capability gate (`feat-table`, `feat-corr`, `feat-hist`, `feat-hist2d`); a body that could reach 100 KB sheds resolution in stated steps and says which, and `meta.budget` gives its measured size ([The feature explorer](#the-feature-explorer)). |
| `GET /api/primaries` | C11, single-shower hit experiments only (a 422 on any other kind): per 1 GeV bin, the events with no primary-tagged hit row, with their 95% Wilson interval, the whole selection's fraction, and the exact count of primary-tagged rows per event. Filters only. |
| `GET /api/voxels` | The ensemble 3-D cloud of a co-registered frame: 40 mm voxels, floored at 10⁻³ of the raw peak, capped by energy, layer-run packed under the 100 KB contract. `frame=local\|canonical` (default `local`; `trans` is refused; `canonical` needs two showers), `channel=density\|gradcam_energy\|shapcam_energy` (the attention channels need the networks), `model` (the network whose CAM an attention channel reads), `anchor` (`frame=canonical`) and `coordinates` (`frame=local`) as `/api/projections`, `cap` (1,000–15,000, default 15,000; lowered, with a sentence, when the body would pass 100 KB), `preview`. Needs the frame extents (`vox-ensemble`) ([The 3-D views](#the-3-d-views)). |
| `GET /api/xgboost` | The XGBoost views, read from the stored analysis; dataset-wide (`filtered: false`), the selection's parameters being accepted and not applied. `view` (required) `cv\|binary\|surrogate\|importance` (E1, E3, E4, E5), `task=momentum\|angle` (default `momentum`; `view=binary` with `angle` is a 422). Every payload carries a `run` block (species, seed, model file, sha256, the split check) and warns when the split was not reproduced. Refused (422, capability `xgboost`) with the analysis's own sentence while the analysis is queued, running, failed or stale, and for an experiment that pairs with no models ([The XGBoost cards](#the-xgboost-cards)). |
| `GET /api/admin/model-runs` | **Read-only.** The models folder's scan (`models`: its files and the rejected ones with reasons), and, in `runs[]`, one flat entry per aggregate experiment: its pairing (`paired`, `species`, `seed`, `models`, `reason`), `status`, `step`, `steps`, `step_label`, `progress`, `duration_s`, `timings` and the stored runs, one per task (`analysis_version`, `split`: `reproduced`, `ratio_42`, `max_others`, `seed_of_max`, `n_others`, `margin`). It re-pairs and compares the cheap part of the stamp, may report an analysis `stale`, and queues nothing. |
| `POST /api/admin/model-runs/scan` | Rescan models: re-pair, compare the whole stamp (the values included) and queue every missing or stale analysis; answers with the list the `GET` reads. Idempotent. |
| `POST /api/admin/model-runs/{table_name}/analyse` | Re-analyse: queue one experiment's analysis even when current. 202 with `{run, poll}`; 404 for an unregistered experiment, 422 (with the pairing's reason) for one that does not pair or is not ready, 409 while an analysis of it is queued or running. |
| `GET /api/health`, `GET /api/health/db` | Liveness with the resolved memory and thread allocation; database readiness. |

The routes of the Models page are the `slice_by=momentum_bin` mode of
`/api/model-performance`, `/api/prediction-density`, `/api/features`,
`/api/primaries`, `/api/voxels`, `/api/event?format=voxels` with the `densest`
rule of `/api/event/pick`, `/api/xgboost` and the model-run admin routes; each
row above links to the card it serves, and [The Models page](#the-models-page)
documents what they draw and the rule behind every mark.

Interactive documentation at <http://localhost:8000/docs>.

#### The capability block

`GET /api/experiments` publishes, in `experiments[].capabilities`, everything the
interface needs to decide what to show, built by `query/capabilities.py` and
always present (`tests/contracts/experiments.json`):

- `kind`, `kind_label`, `n_showers`, `showers`, `has_hits`, `has_lattice`,
  `has_frame_bounds`;
- `networks` (the models the experiment has, empty for the single-shower kinds),
  `species` (whether the particle columns exist) and `filters` (`e1`, `e2`,
  `d`);
- `group1_frames`, the frames the Group-1 features exist in;
- `pages`: `physics`, `spatial` and `models`, whether each page has a card to show;
- `panels`: one boolean per gate, the card ids `xy`, `yz`, `xz`, `energy`,
  `profile-w`, `profile-r`, `response-b1`, `response-b2`, `response-res`,
  `response-b3`, `distribution`, `correlation` and `statistics`, plus the frame
  gates (`frame-lab`, `frame-trans`, `frame-local`, `frame-canonical`) and the
  views built on them (`window-axis`, `event-inspector`, `compare`,
  `negative-depth`), and the Models page's: its cards (`perf-bins`, `pred-truth`,
  `pred-residuals`, `feat-table`, `feat-corr`, `feat-hist`, `feat-hist2d`,
  `prim-rate`, `vox-event`, `vox-ensemble`), the 3-D channels (`vox-attention`,
  `vox-species`) and `xgboost`, one gate for the four XGBoost cards, open while
  the experiment's analysis is done and current; on an aggregate it also opens the
  performance and prediction cards, which draw the XGBoost series there;
- `reasons`: for each shut gate, the sentence the card shows;
- `derived`: `{version, current, status, notice}` of the derived tables;
- `measured`: what ingest measured (cell footprint, profile splat and its comb,
  the momentum-bin range and rule, the species facts, the label rule);
- `model_runs`: the XGBoost models paired with an aggregate experiment, one entry
  per task (`task`, `species`, `seed`, `model_file`, `labels`, `status`, and
  `n_holdout` and `split_reproduced`, null until the analysis is done); empty
  when nothing pairs. It is read from the worker's state in memory, so the block
  stays free of SQL. See [The XGBoost analysis](#the-xgboost-analysis).

The lists `frames`, `coord_systems`, `models` and `channels` beside it are always
present too, possibly empty, so the browser's two-shower fallbacks never fire.
A gate opens only in the change that lands its route, so the catalogue never
advertises a view that would answer 404.

Projection payloads ship as `log10 → uint8 → base64` rasters with the scale
constants attached. The brightest 64 cells also carry their value, at seven
significant figures rounded toward zero (`encode/topk.py` `SIGNIFICANT`, the
float32 source's precision; `/api/event` ships whole values, because its 3-D
ramp quotes the brightest cube's value as its top), so tooltips stay quotable.
The payloads use the 8-bit codes differently:

| Payload | Code 0 | Code 1 | Ramp | Step |
|---|---|---|---|---|
| Lab density | empty | bottom of the ramp | 254 levels from code 1 over six decades | 5.6% |
| Co-registered density, and every energy-weighted Grad-CAM | empty | populated but below the 10⁻³ display floor (`below_code`), drawn transparent | 253 levels from `min_code` 2 over three decades | 2.8% |
| Grad-CAM, Shap-CAM (linear) | empty | lab: bottom of the ramp; co-registered: masked below the floor | linear over 0…1 or −1…+1 | — |
| Energy-weighted Shap-CAM (`signed_log10`) | empty | \|v\| below 10⁻³ of the peak | codes 2–128 negative (2 = −10⁰, 128 = −10⁻³), 129–255 positive (129 = +10⁻³, 255 = +10⁰); `split_code` 129 | 2.4% per sign |

The steps are finer than the eye resolves. The lab quantiser is byte-identical
to its old formula. The client indexes a co-registered payload's colour table at
`round((code − min_code)/(max_code − min_code) · 255)`, so a drawn colour sits
where the legend and `dequantize` put it.

---

## Performance

Measured on the 24.2 M-row production file (`DUCKDB_MEMORY_GB=10`, 10 threads,
full kinematic range; `data/dev/design/measurements.md` has every figure):

| Request class | p50 |
|---|---|
| Event-level endpoints: metric cards, energy panel | 7–13 ms |
| Cache hit — channel, display mode, R, palette change (whole response) | 23–47 ms |
| Absolute frame, cold scan | 0.26–0.28 s |
| Per-shower translated frame (legacy, `trans`), cold / drag preview | 0.9–1.0 s / 0.23 s |
| D-frame (Separation-Aligned › Translated, `canonical`), cold (k = 2) / drag preview | 1.7 s / 0.27 s |
| Separation-Aligned › Local (`local`), cold (k = 2, k_z = 2) / drag preview | 2.5–2.7 s / 0.40 s |

The full-range bundles of the three co-registered frames are pre-warmed at
start-up and after each ingest, one at a time. Every scan is plain sums in two
queries — the entrance slab, then the depth panels by `GROUPING SETS` — because
`FILTER` aggregates are evaluated in every grouping set: the single-pass forms
measured 0.57 s (lab), 5.9–6.3 s (canonical) and 15.9 s (local).

**The 100 KB guard, over the full view matrix.** 4 frames × 3 models × 5
channels × Native and Continuous R 50, 150, 300, 400, at three selection sizes
(the full range, about 200 events and 5) make 900 responses, each measured as
served (`data/dev/tools/measure_matrix_r6.py`). The matrix was run twice on the
production experiment, once on a database holding it alone
(`data/dev/full/r6_matrix_v2.json`) and once on the one that also holds the
single-shower experiments (`data/dev/single/r6_matrix_v2.json`), after the
payload was compacted (`topk` at seven significant figures, no `meta.stagger`
outside the Absolute frame, no copy of the coordinates notice; see
[API](#api)), and set against the September matrix
(`data/dev/matrix-measurements.json`):

- **All 900 views of each run answered 200.** The largest body is 99,722 B on
  the first database and 99,910 B on the second, against 99,967 B in September.
- **Resolution served.** The run before the compaction (`r6_matrix.json`, largest
  body 99,962 B and 99,977 B) served 34 views at a lower resolution than
  September's on each database. After it, none is served below September's on the
  first database and 11 are served higher. On the second, 6 are higher and **7
  are still lower**, one step: R 150 where September served R 168, all for the
  Local frame at about 200 events (energy-weighted Grad-CAM at R 300 and 400 on
  each of the three models' maps, and energy-weighted Shap-CAM on the energy model
  at R 300). Those are the negative-depth block of a derived-v2 experiment
  (`frame.negative_w`), a disclosure that must stay, not payload to trim.
- **Energy conservation held.** For every frame and model, the served Grad-CAM
  and signed Shap-CAM totals, inside plus outside the grid, equal direct DuckDB
  sums over the selected hits, and are identical at every R and display mode: the
  worst relative difference is 3.2 × 10⁻¹³ on both databases.

**The drop folder at scale** (all six experiments of `ingest/`, 52 requests, the
production file's Local 3-D cloud the slowest at 3.2 s cold) is measured under
[Drop folder](#drop-folder-automatic-ingest).

**The physics routes** (Page 1's cards) were swept on the three real experiments
(the electron hit file, the electron aggregate and the production file) in a
14 GB cgroup, alone, at the backend commit `c4f7b20`: 1,855 requests, each at
the full selection, one 1 GeV bin and selections of about 200, 20 and 5 events
(`data/dev/single/r5_physics.json`). Every one answered 200 and none reached
100,000 B; the largest, 95,925 B, is the two-shower response grid (B3) at the full
selection. The slowest cold request was `/api/statistics` at 4.95 s on the
production file, then the projections at 2.7 s and every other route under
1.2 s. The hit-level scans share one cache with single flight and run one at a
time. The experiment catalogue measured 26,582 B.

This comes from a 150 ms debounce that fires on release rather than drag, an LRU
of native-resolution matrix bundles, a 10% Bernoulli sample served during drags
(marked `exact: false` in the payload and flagged in the header), and ingest in
file order so the D slider prunes row groups via zone maps.

---

## Development

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

CALOSRV_DATA_DIR=./data DUCKDB_MEMORY_GB=4 .venv/bin/python -m calosrv
.venv/bin/python -m pytest
```

#### Test data

- **The seed.** The suite ingests the 1000-row `hits_all_models_dummy.parquet`
  at the repository root (the image's seed, kept in plain git so a fresh clone
  builds and tests without Git LFS; its coordinate, momentum and network columns
  are float32). `tests/seed.py` reads it back as text rows for the generators
  that copy template rows verbatim, and writes the CSV copy the tests of the CSV
  reader use under `data/dev/test-seed/` on first use.
- **Synthetic files**, written into pytest's temporary directories from the
  seed, so the tests that must always run need no real data.
  `tests/synthetic_all_models.py` makes two-shower files with chosen event counts
  per D slice, and `tests/synthetic_single_shower.py` single-shower hit files and
  their 59-column aggregate: both give bins of 1, 2, 7, 8, 14, 15, 19, 20 and
  200 events, one per rung of the low-N ladder. The aggregate is written by
  `tests/core_port.py`, a verbatim port of `calc_all_features_v3`, because
  `reference_ipynb_notebooks/core.py` imports TensorFlow and cannot be imported
  by a test. Nothing in them is a measurement: they test shapes, gates and
  parity, never physics.
- **XGBoost fixtures.** `xgb_sources` (session scope, read-only) writes five
  aggregates from `synthetic_single_shower` with the same bins as above, and
  trains tiny regressors (20 trees of depth 4, the notebook's objective and 80%
  split, the momentum and the `[phi, theta]` angle task) into a models folder laid
  out as `xgboost_<species>/…`, so the whole [XGBoost
  analysis](#the-xgboost-analysis) runs on files built in the test. The aggregates
  exercise each outcome of the pairing and the job: electron seed 1 pairs and is
  analysed; muon seed 1 pairs with an angle model that needs a feature the event
  table lacks, so the pairing is refused naming it; proton seed 2 has no models;
  pion seed 1 pairs but holds too few events, so its analysis fails; a plainly
  named file pairs with nothing. The models folder also holds a stray text
  file, which the scanner ignores, and a file naming a task it rejects. `tests/test_xgboost_{discovery,analysis,api,
  staleness}.py` run on it, and compare the stored predictions and fold values row
  for row with `analysis.run` on the source file.
- **Real-data cuts** are git-ignored and small, and the tests that read them skip
  without them. `tests/make_all_models_fixture.py fixture` cuts
  `hits_all_models_fixture.csv` (split cells, `'A+B'` rows, an overlap-100
  event, events without shower A, an all-zero Shap-CAM map; CSV on purpose, for
  the CSV-against-Parquet comparison) from `ingest/hits_all_models.parquet`, and
  `subset` a production subset for `CALOSRV_TEST_SUBSET_CSV`.
  `tests/make_single_shower_fixture.py` cuts `electron_hits_fixture.parquet`,
  `electron_events_fixture.parquet` and the two 20-row heads of the electron
  files (`electron_standalone_…_s1_v3_head.parquet` and `…_aggr_s1_v3_head.parquet`,
  which `tests/test_schemas.py` reads to pin the producer's column names) from
  ingest's electron aggregate and the dev archive of the electron hits under
  `data/dev/single/archive/` (the original hit file is gone). Run them alone, in
  the capped scope below.
- **Payload recordings**, `tests/fixtures/payloads/`: each route's real response
  on a booted fixture, validated against its contract and compared on every run
  (up to timing fields and the byte counts a guard quotes). They are the Node
  tests' source of truth, so the frontend is tested against the backend's own
  payloads. When a payload changes on purpose, regenerate them with
  `CALOSRV_WRITE_PAYLOAD_FIXTURES=1 .venv/bin/python -m pytest -q tests/test_payload_fixtures.py`
  and read the diff first, narrowed with `-k` to the recordings that should move
  (`-k event_voxels`, `-k "perf_ or pred_density_"`, and so on), so an unrelated
  recording is never rewritten. The recordings the Page 2 review changed, and
  why: `perf_*` and `pred_density_*` (the χ² and bootstrap RMSE intervals, the
  axis-top rounding, Freedman–Diaconis bins, φ's period axes, the momentum
  labels and the core curve's area); `event_voxels_*` (the per-axis windows and
  the cells outside them, the 3-D ramp's drawer text); `projections_*` (the
  compaction); and the XGBoost recordings (`analysis_version` 3 in all of them,
  and in the E1, E3, E4 and E5 ones the fields listed under [The XGBoost
  cards](#the-xgboost-cards)). Blocks that describe the serving process rather
  than the data are masked on comparison: the volatile timing keys, and the
  `compute` block of the `experiments` and `experiments_xgb` recordings, whose
  cache counters race the request (`VOLATILE_BY_NAME` in
  `tests/test_payload_fixtures.py`).
- **Contracts**, `tests/contracts/*.json`: one checked-in JSON schema per route,
  the frozen shape of its response (`tests/contract_check.py` validates against
  them with the subset of JSON Schema they use; the project has no `jsonschema`
  dependency). The contract is the source of truth: where a design note and a
  contract disagree, the contract wins. Two things to know when editing one:
  the checker's `anyOf` returns on its own result and checks nothing else in the
  same schema object, so `prediction_density.json` is two complete branches
  (`response_network`: both showers, a string `network.frame` that is not `xgb`;
  `response_xgb`: `network.frame` `xgb`, `source` required, one shower) and a
  body that drops shower B from a network response fails; and
  `event_voxels.json` requires `window.mode`, `window.half_mm_axes`,
  `window.percentiles`, `cap.cells_outside_window` and `meta.window`.
- **Goldens**, `tests/golden/`: the Absolute-frame and default-D payloads, pinned
  byte for byte (below). A golden moves only on purpose, and
  `tests/make_golden_two_shower.py` records each deliberate change in its
  `DELIBERATE` list. The Page 2 review's changes to them were: the Event
  Inspector's window and its `outside_window` counts (`two_shower_api.json`, the
  `/api/event` entries only); the `/api/projections` compaction (`topk` at seven
  significant figures: 384 values in `lab_demo.json`; 36 `topk` hashes, ten
  `meta.stagger` and ten coordinates notices fewer in the 14
  `/api/projections` entries of `two_shower_api.json`); and the core curve's area
  (one series of `energy_synthetic_trans.json`, its 268-event slice against 260
  inside the axis). Everything else in them is unchanged.

#### Opt-in and write modes

| Variable | Effect |
|---|---|
| `CALOSRV_BROWSER_TESTS=1` | runs the browser modules (`tests/test_browser_*.py`: admin, anchor, event, layout, models, physics, tooltip, upload, window axis) against a live server, in Playwright's Chromium. `test_browser_physics.py` drives the Physics page on a seeded single-shower server, and `test_browser_models.py` the Models page on the `models_live_server` fixture (see below); the 3-D cards draw there in Chromium's SwiftShader WebGL (`--use-angle=swiftshader`) |
| `CALOSRV_TEST_SUBSET_CSV=<path>` | runs `tests/test_canonical_subset.py` on a production subset |
| `CALOSRV_XGB_REAL=1` | runs `tests/test_xgboost_real.py`, which reads the four 100,000-event aggregates in `ingest/` |
| `CALOSRV_WRITE_PAYLOAD_FIXTURES=1` | rewrites `tests/fixtures/payloads/` instead of comparing |
| `CALOSRV_WRITE_GOLDEN=1` | rewrites the energy panel's golden (`tests/test_energy_momentum_api.py::test_default_d_payload_is_byte_identical`) |

**The browser tests need Playwright and its Chromium.** The `playwright` package
is not in the `dev` extras: the live-server fixtures `importorskip` it, so
without it the browser modules skip. Install the package into the virtual
environment and then fetch the browser it drives:

```bash
uv pip install --python .venv/bin/python playwright
.venv/bin/python -m playwright install chromium
CALOSRV_BROWSER_TESTS=1 .venv/bin/python -m pytest -q tests/test_browser_models.py
```

The Node tests need `node` on the `PATH` and skip silently without it, so check
`command -v node` first. The booted fixtures share one process-wide DuckDB, and
each boot resets it: group a module's tests by fixture, and never interleave two.
`conftest.py` orders the collected tests by fixture for exactly this reason.

| Fixture | What it boots |
|---|---|
| `client` | the app booted against an empty database, so seeding the two-shower demonstration is exercised; through `TestClient` |
| `synthetic_client` | a server seeded from the synthetic low-N two-shower file of `synthetic_all_models` |
| `single_client` | all three kinds: the baseline, a single-shower hit experiment and an aggregate |
| `xgb_client` | the baseline and the five XGBoost aggregates of `xgb_sources`, which arrive through the drop folder so the whole lifecycle runs (the ingest worker builds each, the queue hook hands the paired ones to the model-run worker); it waits until every analysis has settled. The models folder is `CALOSRV_MODEL_DIR` |
| `xgb_boot` | no server: it only cleans the environment, for a test that boots, stops and boots again itself through the `booted_app` context manager |
| `live_server`, `physics_live_server`, `models_live_server` | the real app on a real port in a thread of this process, for Playwright. `live_server` holds the seeded baseline and `physics_live_server` every kind the Physics page draws. `models_live_server` holds the two-shower demonstration, the synthetic single-shower hits and the electron aggregate paired with its models, whose analysis has finished before the first page opens; `start_models_server` and `stop_models_server` are plain functions so a scratch script can boot the same server |

`wait_for_model_runs` polls the read-only admin list until the named analyses
have settled, and `train_xgb_models` trains the tiny models.

**Real-data runs are serial and capped.** A full-dataset job runs alone, never
beside another, in a memory-capped scope with an explicit `DUCKDB_MEMORY_GB`, a
data directory of its own and DuckDB's spill on disk (the storage guard refuses
a RAM-backed temp directory; on the development machine `/tmp` is tmpfs):

```bash
systemd-run --user --scope -q -p MemoryMax=14G -p MemorySwapMax=0 \
    env CALOSRV_DATA_DIR=$PWD/data/dev/single DUCKDB_MEMORY_GB=10 <command>
```

Never point one at `data/calorimeter.duckdb`. The drivers that measured this
README's figures live in the git-ignored `data/dev/tools/`.

The JavaScript tests run the pure modules under Node.
`tests/test_layout_assets.py` pins the markup and CSS of the page shell from the
source alone: the on-card footnotes gone, the sidebar
toggle, the Details drawer, the two-tier frame control and the upload form
inside Admin Settings. The browser tests include the tooltip, admin
panel and upload checks, and `tests/test_browser_layout.py`, which drives the
sidebar toggle, the Details drawer, the frame selector (a `#frame=trans` link
included), the entry panel's D axis and a plot-only export download.

The Page 2 review's tests, by what they pin (the modules named exist beside the
others in `tests/`):

- **E2's estimators and cost.** `test_performance_bins_rmse.py`: the χ² interval
  against scipy at N = 2, 3, 8 and 19, the bootstrap against numpy with the
  documented seed and the same draws whatever the chunking, N = 0 and 1, that
  the old lower end collapsed to 0 where the new one is positive, and that Page 1
  keeps its estimator; the threaded groups equal the serial path exactly on a
  production-sized synthetic case (`workers=1` against `8`, energy and angle),
  `map_groups` keeps task order and its bound, and the route's workers equal
  `/api/health`'s `threads`.
- **The core curve.** `test_encode_and_safety.py`: the core share (400 Gaussian
  and 50 tail events: the bars integrate to 1 and the curve to
  `n_core / 0.98078 / n_in_range` to 10⁻⁶, `curve_peak` agreeing), the coverage
  constant on 10⁶ events, the untruncated cases, and `topk`'s rounding toward
  zero and its opt-in default.
- **The event window.** `test_event_inspector.py` recomputes every frame's
  per-axis half-width from the database (pads, centring, energy conserved, rasters
  inside their windows) and checks that the shared body gains no key and that
  `window=widest` is a 422 naming `window` in both formats; `test_event_voxels.py`
  holds the box and its projections to the same millimetres in three frames, and
  event 3's box to the detector's depth.
- **The Node tests.** `test_js_voxels.py`: no opaque cube or raster colour is
  drawn under 3:1 on the card (nine payloads, and the lab, D-frame, attention,
  Cividis, Plasma and Turbo tables), Viridis' run starts at 0.376 and print keeps
  the full ramp, round ticks and `labelStep`, `AXIS_NAME_GAP`, and the per-axis
  drawer sentence. `test_js_xgb_panels.py`: no " - " remains in any rendered
  string or drawer line of the four cards, in either theme, plus the realised
  ratio, prevalence, ▲/▼ marks, ddof and weak nodes, φ's unit, per-output
  fidelity, E5 on both recordings and the wrapped legends. `test_js_admin_model_runs.py`
  reads the model-runs list against the recording.
- **No source pinned.** The test that `main.js` takes `depthIsometric` and
  `ensembleCellOptions` from `event_cells.js` reads the module structurally,
  comments stripped, rather than matching its text.
- **The browser tests** hold both pages to the 20% readout cap, the Models page's
  3-D plot height to `glPlotHeight(w)`, and (`test_browser_models.py`) φ's axis
  text "wrapped to (−3142, 3142]".

`tests/test_canonical_subset.py` runs only when `CALOSRV_TEST_SUBSET_CSV` points
at a 99-column subset of the production file (`tests/make_all_models_fixture.py
subset`): the k = 1 comb measurement, the row
budget on a realistic window, the dataset-reference ρ_ref, R̄′ rising on a
wide-D slice, the kernel a sampled Continuous preview picks from the exact N and
the whole-response budget at R = 150 cannot be exercised on the two-event
demonstration file, so without the variable those tests are skipped, not
passed. `tests/test_kernel.py` needs no database at all: it pins every operator
property the display relies on (columns telescope, W ≥ 0, energy conserved,
σ → 0 is the box, the tent is `np.interp`, no displayed bin above the raw peak
over 100 random matrices, flat fields stay flat, float32 input gives the
float64 result) and the symmetric window on hand-computed cases. `tests/test_golden_lab.py`
asserts that the Absolute-frame (`frame=lab`) output on the demonstration dataset is
**byte-identical** to `tests/golden/lab_demo.json`, so the shared code the
D-frame touches (`NativeBundle.axis`, `centroids`, `panels.shower_axes`)
cannot move the lab picture unnoticed. It was regenerated once, deliberately,
when the schema changed: on a 29-column derivation of the all-models dummy, before
any code changed, so the new pipeline had to reproduce it unregenerated. It pins
density, centroids and axes; the `gradcam` channel now reads the raw `*_gradcam`
column where the old one read `gradcam_energy`. Regenerate it with
`.venv/bin/python tests/make_golden.py` only when the lab output is *meant* to
change.

### Static assets and caching

Asset URLs are stamped with a hash of the static tree (`/static/js/main.js?v=…`)
and served `immutable`; the page itself is `no-cache`, and any unstamped asset —
which includes the relative ES module imports inside `main.js` — revalidates
against its ETag. Both pages, `/` (`index.html`) and `/models` (`models.html`),
go through the one stamping helper.

**Vendored third-party scripts.** Nothing is loaded from a CDN, so the interface
works offline and air-gapped:

| File | Version | Licence | sha256 | Loaded by |
|---|---|---|---|---|
| `static/js/vendor/echarts.min.js` | Apache ECharts 5.5.1 | Apache-2.0 (header of the file) | `e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf` | both pages |
| `static/js/vendor/echarts-gl.min.js` | echarts-gl 2.0.9 | BSD-3-Clause (Baidu Inc., 2017), as read from `echarts-gl.LICENSE.txt` | `bfba1b87b8c3c06e5c7ed7741002586c747b00e4efdaa92077d15c2dc721bda0` | `models.html` only, after `echarts.min.js` |

`echarts-gl` is the package's own `dist/echarts-gl.min.js`, byte-identical
(640,694 bytes), its integrity checked against the registry's `dist.integrity`
when it was vendored. `static/js/vendor/echarts-gl.LICENSE.txt` reproduces the
package's `LICENSE` and the Apache-2.0 notice of the `tslib` code the bundle
carries; the npm registry's metadata for the same version says MIT, and the
`LICENSE` file shipped in the package, which is the one reproduced, says
BSD-3-Clause. The bundle contains claygl and zrender. The Physics page does not
load it, so that page's weight does not change.

This is not housekeeping. The page and its scripts are separate downloads with
independent cache lifetimes, so a browser can hold a **stale script against
fresh markup**. When that happened here, the cached script still expected the
readout spans that the numeric inputs replaced and threw

```
TypeError: Cannot set properties of null (setting 'textContent')
```

during module initialisation — before ECharts was configured or any data
fetched, so the interface was dead with nothing on screen to explain why. The
same stale stylesheet lacked the rules for the new inputs and buttons, which
rendered them as browser-default white boxes. Stamping the URLs makes that
pairing impossible; `dom.js` and the startup id audit make it survivable and
self-explaining if it ever recurs.

### Module layout

```
calosrv/
  config.py logging_setup.py errors.py app.py text.py fsutil.py
  admin/   schema store
  db/      connection settings storage_guard ddl naming schemas group1 registry bootstrap
           archive catalog
  ingest/  stream formats csv_spec parquet_spec source_check load local pipeline recipes
           lattice_fit derive_proj derive_events derive_events_single derive_features
           derive_layers derive_profiles verify verify_single verify_events frame_checks
           feature_parity result jobs autoingest cli
  grid/    lattice splat resolution slab frame bounds kernel footprint
  query/   filters showers capabilities planes projections panels centroids summary energy
           performance sampling cache experiments stagger canonical shower_frames window
           reconstruct density ensemble canonical_cache warming frame_sql hit_sql physics_cache
           event_inspector window_axis
           profiles response shower_distributions hit_distributions correlations statistics
           negative_depth
           performance_bins prediction_density primaries features features_catalog
           feature_axes feature_corr feature_describe feature_hist voxels voxel_event
  modelruns/ discovery pairing analysis store jobs views
  stats/   gaussian histogram slices metrics clip shape
           describe median kde momentum profile circular jackknife rmse
  encode/  scale quantize matrix topk numbers voxels
  api/     deps budget routes_* frame_canonical frame_shower
  static/  index.html models.html css/ js/
             js/      main api state labels scale palette decode dom textfit format frame_views
                      axis_symbols panel_notes shell event_inspector
                      capabilities lazy_cards physics_section page_common
                      models_main models_cards models_notes xgb_notes
                      voxels voxel_views voxel_notes event_cells
             js/panels/   projection canonical_overlays marks tooltip energy metrics frame_grid
                          chart_panel profile response response_grid distribution correlation
                          statistics perf_bins hist2d feature_table rates
                          xgb_cv xgb_binary xgb_tree xgb_importance
             js/controls/ range_slider upload admin modal filter_block
             js/export/   tokens figure caption disclosure filename download menu
             js/vendor/   echarts.min.js echarts-gl.min.js echarts-gl.LICENSE.txt
```

The Models page (`/models`, [documented above](#the-models-page)) has its own
modules, listed here ahead of the D-frame's:

**Server (Page 2):**

| File | Responsibility |
|---|---|
| `modelruns/discovery.py` | the scan of the models folder: header parse with the standard library, sha256, the rejected files with their reasons; never raises, reads only regular files under 256 MB, caches headers by path, size and modification time |
| `modelruns/pairing.py` | an aggregate experiment against the catalogue: species and seed from the source file name, both tasks present, every model feature mapped through the `ddl` vocabulary to an event-table column; pure |
| `modelruns/analysis.py` | the notebooks' E1–E5 on arrays (numpy, pandas, XGBoost, scikit-learn; no HTTP, no database): the split and its check, the output-order check, the fold refits, the 99 : 1 sample, the surrogate trees (within-node variance at ddof 1, φ's circular fidelity), the importances; `ANALYSIS_VERSION` (3) |
| `modelruns/store.py` | the six `xgb*_` tables, the read the analysis starts from, the one transactional write, and the stamp (`stale_reasons`) |
| `modelruns/jobs.py` | the single-slot worker, the per-experiment statuses, the boot, ingest and Rescan hooks, the test-and-set queue |
| `modelruns/views.py` | the payloads of `GET /api/xgboost`: the run and split blocks, E1's corrected resampled t, E3's Wilson and MOVER intervals and its prevalence flags, the surrogate's per-output fidelity (judged on the circular R² for φ), colour domain from nodes of 20 rows or more and circular nodes, E5's folds with each feature's total-gain share and rank |
| `query/performance_bins.py` | E2: per shower and momentum bin, the statistics with their intervals (the RMSE's from `stats/rmse.py`), the robust y range with its rounding (`nice_top`), the XGBoost series with φ, and `map_groups`, the per-request thread pool the groups run on |
| `stats/rmse.py` | the RMSE and its 95% interval by sample size: one residual an observation, a χ² interval under normal residuals from N = 2, a seeded percentile bootstrap from N = 20, the draws independent of their chunking |
| `query/prediction_density.py` | the pairs' density on dataset-wide axes, the residual on the energy panel's ladder with Freedman–Diaconis bins (`stats/histogram.py`), the circular φ block and φ's period axes, the XGBoost hold-out and its momentum labels |
| `query/features.py`, `features_catalog.py`, `feature_axes.py`, `feature_describe.py`, `feature_corr.py`, `feature_hist.py` | the feature explorer: the cached bundle and its classes; the catalogue and each feature's flags; the axis plans and the comb verdict; D2; D3; D4 and D5 |
| `query/primaries.py` | C11, from the event table's `n_primary_rows` |
| `query/voxels.py`, `query/voxel_event.py`, `encode/voxels.py` | the ensemble cloud (two-level scan, floor, cap, layer-run packing) and one event's cubes (cell and splat regimes, channels, window); the byte packing |
| `api/routes_features.py`, `routes_prediction.py`, `routes_primaries.py`, `routes_voxels.py`, `routes_xgboost.py` | the Models page's routes; `routes_performance.py`, `routes_event.py` and `routes_admin.py` carry its other modes |

**Client (Page 2):**

| File | Responsibility |
|---|---|
| `static/models.html`, `static/css/models.css` | the page, which loads `echarts-gl` as well as ECharts, and its card and 3-D layout |
| `static/js/models_main.js` | the bootstrap: the experiment switch that clears every picture, the banners, the sidebar controls, the drawer |
| `static/js/models_cards.js` | the 2-D cards: their requests, shared where two cards read one, their controls, lazy loading, refusals and retries |
| `static/js/models_notes.js`, `xgb_notes.js` | the Details drawer's text for the network, feature and primaries cards, and for the four XGBoost cards, with their structural hazards |
| `static/js/panels/perf_bins.js`, `hist2d.js`, `feature_table.js`, `rates.js` | E2's grouped bars; the density of pairs and the feature small multiples; the describe table; the Wilson rate; the residual and feature histograms reuse `distribution.js` and the matrix `correlation.js` |
| `static/js/panels/xgb_cv.js`, `xgb_binary.js`, `xgb_tree.js`, `xgb_importance.js` | E1, E3, E4, E5 |
| `static/js/voxels.js` | the 3-D payload decoders and the echarts-gl option, pure: placement through the payload's coordinates, floating cubes by stacking, the opening zoom, the crop to the projections' window |
| `static/js/voxel_views.js`, `voxel_notes.js`, `event_cells.js` | the two 3-D pairs and their controls and WebGL handling; their drawers; the 2-D cells' helpers shared with the Event Inspector |

The D-frame is its own column of that layout, one responsibility per
file. The two tables below are Page 1's.

**Server:**

| File | Responsibility |
|---|---|
| `grid/frame.py` | the pure-NumPy SE(3) mathematics, the footprint measurement, the window planner and the sub-sampling rule; the display constants (`SMOOTH_SIGMA_MM`, `GAUSSIAN_KERNEL_BELOW_N`, the window percentiles and floors), each citing its measurement |
| `grid/kernel.py` | the conservative reconstruction operators, maths only: the Numerical Recipes `erfcc` (numpy has no erf and scipy is not a dependency); the box ⊗ Gaussian operator computed inside its 9σ band; the tent, which refuses a non-uniform source; all float64 throughout |
| `query/canonical.py` | the per-event frame statistics and the DuckDB accumulation scan |
| `query/window.py` | the symmetric crop and its floors |
| `query/reconstruct.py` | the policy: which kernel a display mode and N get, each panel axis as an `AxisMap` (native crop, kernel from the full axis plus reach, or depth passthrough), and the `frame.reconstruction` report |
| `query/density.py` | the crop → reconstruct → ⟨ρ⟩ → encode step, the energy bookkeeping and the panel budget guard |
| `query/ensemble.py` | the two axes with their band and envelope |
| `query/canonical_cache.py` | the cached bundle and its start-up warmer |
| `api/frame_canonical.py` | the envelope assembly and the whole-response budget (`serve_within_budget`, shared by every co-registered frame) |
| `query/planes.py` | the nine measurement planes every bundle carries and how each channel reads them |
| `query/shower_frames.py` | the per-shower (`trans`, `local`) frames: statistics, the exact box-overlap and rotated sub-deposit scans, their caches and warmer |
| `api/frame_shower.py` | the per-shower (`trans`, `local`) envelope: comb on both axes, superimposed centroids, `frame_mean`, directions |
| `grid/bounds.py` | the dataset-wide frame extents measured at ingest, from which their grids are planned |
| `grid/frame.py: Se3` | the one SE(3) element every co-registered view is an instance of: `rotation_matrix` (the notebook's R_y(θ) R_z(φ)), `per_shower_translated`, `per_shower_local`, `per_event_canonical` |
| `query/frame_sql.py` | the shared frame CTE: the same motions as SQL, applied to the lattice ordinals inside every per-shower and D-frame scan; the anchor and coordinate-source vocabulary |
| `ingest/frame_checks.py` | the `p0_definition` check and the anchor residual δ between the two D-frame anchors |
| `grid/footprint.py` | exact box overlap of a cell footprint with a grid, and rotated sub-deposits binned on one |
| `stats/shape.py` | the energy-weighted principal axis of one cloud and its tilt from +w |
| `query/event_inspector.py` | the Event Inspector: one shower of one event as nine rasters, its window (shared by default, per axis through `frame_window`, which the 3-D cubes call too), one ramp, the marks, the seeded pick |
| `api/routes_event.py` | `GET /api/event` and `GET /api/event/pick` |
| `query/window_axis.py`, `api/routes_window_axis.py` | the windowed ensemble axis of the absolute frame's depth panels: the events entering a window, their mean trajectory, the exact dispersion band, the t-envelope and the lean / fan gate; `summary.pointing` measures where the directions point |
| `db/archive.py`, `db/storage_guard.py` | the Parquet archive and its manifest; the refusal of RAM-backed storage |
| `stats/metrics.py` | the card estimators: clustered ratios, residual summaries, Fisher-z correlation |
| `admin/schema.py`, `admin/store.py` | the six defaults of the Admin Settings panel, validated against the API's own tuples; the layered store (saved, environment, built-in) that reports each value's source |
| `db/catalog.py` | what already exists under a name, or from a source file: the one answer the 409 and the drop folder share |
| `ingest/formats.py`, `ingest/parquet_spec.py` | the format read from the file's content, and every branch on it; the Parquet schema, type and range checks and the SELECT that reads it |
| `ingest/autoingest.py` | the drop-folder scan: decides and queues, never forces |
| `fsutil.py` | crash-safe file replacement (the saved defaults, the archive manifests) |
| `db/schemas.py` | the three accepted schemas and their kinds (`InputSchema`, `KindTraits`), detection from a CSV header (exact) or a Parquet column set, the one-sentence refusal with its `expected` and `found`, `DERIVED_VERSION`, and the tables each kind must have |
| `db/group1.py` | Group-1: the per-shower sums of the event table and the SQL that rebuilds every `calc_all_features_v3` feature from them |
| `db/naming.py` | the only place a name becomes SQL, with the prefixes of `layers_` and `profiles_`, and `derive_experiment_name`, which shortens a long file name around a fingerprint |
| `ingest/recipes.py` | the derive recipe of each kind: which tables, in which order, with which stage weights, checked how |
| `ingest/derive_events_single.py`, `derive_features.py`, `derive_layers.py`, `derive_profiles.py` | a single-shower hit experiment's event table; an aggregate's event table (duplicate ids refused, non-finite values NULL); `layers_`; `profiles_` from the Local footprint splat |
| `ingest/verify_single.py`, `verify_events.py`, `feature_parity.py` | the per-kind post-ingest assertions; the features rebuilt from hits against the producer's aggregate (`--compare-features`) |
| `query/capabilities.py` | the one owner of every per-experiment gate and of the capability block; `require` refuses with the `CapabilityError` 422 |
| `query/showers.py` | the per-shower column vocabulary of each kind, so one query reads one shower or two |
| `query/hit_sql.py`, `query/physics_cache.py` | the SQL fragments the hit-level scans share; their cache, single flight and one-heavy-scan-at-a-time gate |
| `query/profiles.py` | C7: the longitudinal and radial profiles |
| `query/response.py` | B1, B2 and the resolution, from the event table of any kind |
| `query/shower_distributions.py`, `query/hit_distributions.py` | C4: the showers' θ, φ and p, and the hits' u, v, w and energy |
| `query/correlations.py` | C8: the correlation matrix from moment sums, with the event-grouped jackknife |
| `query/statistics.py`, `query/negative_depth.py` | C1: exact `describe()` beside energy-weighted quantiles; C9: the negative-depth block, from the event table alone (it is also what the Local frame embeds) |
| `stats/profile.py`, `jackknife.py`, `circular.py` | the SD band and cluster-robust t envelope of a profile; correlations from moment sums with the grouped jackknife and Mardia's R; wrap, resultant sums and circular SD |
| `stats/describe.py`, `median.py`, `kde.py`, `momentum.py` | descriptive statistics (ddof 1 and 0) and weighted quantiles; the median with its seeded bootstrap and order-statistic interval; a binned Gaussian KDE with Silverman's bandwidth; the momentum windows, 1 GeV bins and the label |
| `encode/numbers.py` | numbers as payloads ship them: six significant figures, plain Python types, non-finite as null |
| `api/budget.py` | one measured whole-body size guard (`serve_measured`), used by the voxel routes; each Page 1 route measures its own response the same way |

**Client:**

| File | Responsibility |
|---|---|
| `static/js/panels/canonical_overlays.js` | the light anchors, spread bars, separation rule and shape-coded centroids, with the legend sentence the drawer's *What is drawn* and *Marks and legend* sections share |
| `static/js/panels/marks.js` | the clipped, hit-testable custom-series lines every frame draws its named overlays with, and the capped whisker of an interval of the mean |
| `static/js/export/disclosure.js` | the structured disclosures of the Details drawer, per frame kind and quantity, read from the payload's fields rather than from the prose |
| `static/js/export/caption.js` | the provenance sentences (`describeSelection`, `describeView`) and the display descriptor (`displayOf`, `kernelPhrase`), read from the payload; nothing in it is drawn into a figure |
| `static/js/export/figure.js` | the off-screen print render and its serialisation: the plot canvas only, under the swapped theme, in one synchronous block |
| `static/js/frame_views.js` | every frame's titles, captions, display captions and the per-panel prose the drawer shows (`footnotes()`, `exportLegend()`), as pure strings |
| `static/js/axis_symbols.js` | the symbol each spatial axis is written with, and the one client-side rule that writes the D-frame entry panel's horizontal axis as D; a leaf module every consumer that names an axis reads |
| `static/js/panel_notes.js` | the Details drawer's text: one panel's methodology and disclosures as sections (*Selection*, *What is drawn*, *Disclosures*, *Marks and legend*, *Reading the density axis*), built from the functions above; `hazards()` flags the trigger |
| `static/js/shell.js` | the collapsible sidebar (`localStorage`, never the hash) and the Details drawer: grid tracks snap, every chart re-lays itself out synchronously, text nodes only |
| `static/js/format.js` | the typographic minus |
| `static/js/controls/admin.js`, `static/js/controls/modal.js` | the Admin Settings panel — the default view, the upload form (`controls/upload.js`) and the automatic-ingest report; the dialog shell (focus, Escape, ARIA) |
| `static/js/controls/upload.js` | the upload form inside Admin Settings: naming checks before a byte is sent, the streaming upload or server-side ingest, and the job poll, which carries on after the panel is closed |
| `static/js/labels.js` | every choice's label and `FRAME_TREE`, the one definition of the two-tier frame control; the admin panel builds from it and a test holds it equal to the sidebar's markup |
| `static/js/panels/tooltip.js` | the one tooltip option (mounted on the fixed `#tooltip-layer`) and `placeTooltip`: the bin readout at the pointer where it covers at most 20% of the plot (`READOUT_SHARE`), every other tip off the hovered chart |
| `static/js/scale.js` | the colour scale of a payload (`visualMap`) and the legible ramp: `legibleSpan` and `rampTable` re-index a palette onto its 3:1 run, and the legend stops and `decode.js`'s `codeTable` read the same table; print keeps the full ramp |
| `static/js/panels/frame_grid.js` | the 3 × 3 grid of cards and projection panels the Event Inspector and the compare-frames view share; charts created on first show |
| `static/js/event_inspector.js` | the Event Inspector's controller: the picker, the pinned event in the link, the nine cells' options and the export meta |
| `static/js/capabilities.js` | the Physics page's plan from the capability block: which cards show and which are shut with the server's reason, the frames offered, the missing-predictions banner, the stale notice and the frame carried across a change of kind; pure, tested under Node against the recorded catalogue of all three kinds |
| `static/js/lazy_cards.js` | when a card loads: visible, and its request key differs from the one it holds; pure |
| `static/js/physics_section.js` | the nine physics cards: their anatomy and controls, the requests they share, and the shut state with its Rebuild offer |
| `static/js/page_common.js` | what both pages share: the banner, error wording, the experiment picker, runtime relabelling, and the page tabs that carry the hash |
| `static/js/controls/filter_block.js` | the sidebar's filter block adopted per kind: E₁, E₂ and D, or the single-shower p alone |
| `static/js/panels/chart_panel.js` | the base of every 2-D physics panel and the helpers they share; each panel is a pure option builder plus a thin subclass |
| `static/js/panels/profile.js`, `response.js`, `response_grid.js`, `distribution.js`, `correlation.js`, `statistics.js` | C7; B1, B2 and σ/μ; B3's small multiples; C4; C8 on PuOr; the C1 and C9 table |

Three structural rules the layout exists to enforce:

- **`db/naming.py` is the only place a table name becomes SQL identifier text.**
  DuckDB cannot parameterise identifiers, so interpolation is unavoidable;
  confining it to one validated function keeps the injection surface auditable in
  one file.
- **No SQL string lives outside `query/` and `db/ddl.py`.** Route modules build a
  `FilterSpec` and call a query module.
- **A panel builds its chart option from `metrics`, never from its own element,
  and styles it from `THEME` tokens, never from literals.** Both exist so one set
  of option builders can serve the screen and a publication figure. `THEME` is a
  mutable singleton the exporter swaps for the duration of *one synchronous
  block* — swap, render, serialise, restore, with no `await` between — which is
  what keeps a global style change invisible to the live charts. A hardcoded
  `fontSize: 10` or a read of `this.element.clientHeight` inside an option
  builder silently reintroduces the screen's geometry into the exported figure.
- **The Absolute-frame (`lab`) path is never edited to add a frame.** The D-frame
  response is assembled beside the route in `api/frame_canonical.py`, the
  per-shower (`trans`, `local`) ones in `api/frame_shower.py`, through the frame-generic
  co-registered path and never through the lab route, and the only shared code
  they reach (`NativeBundle.axis`, `centroids`, `panels.shower_axes`) is pinned
  byte-identical by the golden snapshot test. The lab path changed twice,
  deliberately — for the single schema, and to split its scan in two — and the
  golden passed unregenerated both times. A change that moves the lab picture
  must move `tests/golden/lab_demo.json` on purpose.

### The legacy batch compiler

`build_dashboard.py` and `calodash/` are untouched and still work. The two
packages deliberately share no imports: the estimators `calosrv` needs are
re-implemented so neither path can break the other.
`calosrv/stats/gaussian.py` documents where it must stay numerically identical to
`calodash/stats.py`.
