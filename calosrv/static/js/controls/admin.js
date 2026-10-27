/* The Admin Settings panel: the view a new session opens on, the dataset
 * upload form and the drop-folder ingest.
 *
 * It reads GET /api/admin/config and saves with POST. Beside every control a
 * chip says where the current value comes from - saved here, the deployment's
 * environment, or the built-in view - and Reset lets the layer beneath show
 * through again. Nothing is stored until Save, and saving never changes the
 * view of the session that saved it: the defaults apply only to links that
 * carry no view state (State.applyDefaults). The lower sections hold the
 * upload form (controls/upload.js, readied by `prepare()` on every open and
 * covered by this panel's focus trap and Escape) and the automatic ingest of
 * the drop folder, with live job status and a rescan.
 *
 * The last section lists each experiment's derived tables. One built by an
 * earlier release is served as before, with the panels that need the newer
 * tables shut and the server's reason on them; "Rebuild derived tables"
 * re-derives every table from the experiment's archive (POST
 * /api/admin/experiments/{name}/rebuild) on the ingest worker, in one
 * transaction - the experiment stays served from its old tables until the new
 * ones have verified - and the row follows the job until it is done.
 *
 * Below it, the XGBoost model runs: each event-level aggregate paired with
 * the shipped models of its species and seed (GET /api/admin/model-runs,
 * read-only: it reports an analysis stale and queues nothing), where its
 * analysis stands, a Rescan models action (POST /api/admin/model-runs/scan)
 * that rescans the models folder and queues every missing or stale analysis,
 * and a Re-analyse action per row (POST
 * /api/admin/model-runs/{table_name}/analyse) that queues one again.
 * The section is built here rather than in the markup, so the page needs no
 * ids for it.
 * The Models page has no Admin Settings of its own: its header link opens
 * this panel on the Physics page (`/?admin=1`, main.js).
 */

import { ApiError, getJson, sendJson } from '../api.js';
import { CHOICE_LABELS, DISPLAY_CHOICES } from '../labels.js';
import { formatInt } from '../scale.js';
import { DEFAULTS } from '../state.js';
import { ModalShell } from './modal.js';

const JOB_POLL_MS = 1500;

/** Each field: its radio choices, and what the chosen experiment must offer. */
const FIELDS = {
  default_dataset: {},
  default_coord_system: { choices: CHOICE_LABELS.frame, offered: 'frames' },
  default_model: { choices: CHOICE_LABELS.model, offered: 'models' },
  default_channel: { choices: CHOICE_LABELS.channel, offered: 'channels' },
  default_display_mode: { choices: DISPLAY_CHOICES },
  default_rho_norm: { choices: CHOICE_LABELS.rho_norm },
};

/** Each field's built-in value: the interface's own view (state.js). */
const BUILTIN = {
  default_dataset: null, // the oldest ready experiment
  default_coord_system: DEFAULTS.frame,
  default_model: DEFAULTS.model,
  default_channel: DEFAULTS.channel,
  default_display_mode: null, // each frame's own
  default_rho_norm: DEFAULTS.rho_norm,
};

/** Chip text and tooltip for each source of a value. */
const SOURCE = {
  admin: ['set here', 'Saved in this panel.'],
  env: ['from environment', 'Set by the deployment, through a CALOSRV_DEFAULT_* variable.'],
  builtin: ['built-in', "The interface's own default."],
  fallback: ['fallback',
    'The saved experiment is not ready, so the oldest ready one is used until it is.'],
};

/** What each automatic-ingest outcome means, in the table's Result column. */
const RESULT = {
  submitted: 'queued for ingest',
  exists: 'already an experiment',
  queued: 'already queued',
  same_source: 'already ingested',
  name_collision: 'skipped: name taken by another file',
  invalid_name: 'skipped: no valid experiment name',
  unsettled: 'skipped: still being written',
  rejected: 'rejected',
  no_space: 'skipped: not enough disk space',
};

/** Where each XGBoost analysis stands, as the model-runs table says it. */
const RUN_STATUS = {
  queued: 'queued for analysis',
  running: 'analysing',
  done: 'done',
  failed: 'failed',
  stale: 'stale: the models or the data changed since the analysis',
  unpaired: 'not paired',
  not_ready: 'waiting for the experiment to be ready',
};

/** A run whose analysis is under way: the list is polled while one is. */
function runPending(row) {
  return row.status === 'queued' || row.status === 'running';
}

/**
 * The model-runs list as rows, from GET /api/admin/model-runs (and the POST
 * scan, which returns the same body): `payload.runs`, one entry per
 * experiment with its pairing and its analysis flat on it -
 * `{table_name, display_name, paired, species, seed, models: [{path, …}],
 * reason, status, error, step, steps, step_label, progress, duration_s,
 * runs: [{task, split, …}]}` (tests/contracts/model_runs_admin.json).
 * Each row: `{table_name, name, species, seed, models, paired, status,
 * reason, progress, seconds, splits}`. Pure.
 */
export function modelRunRows(payload) {
  const list = Array.isArray(payload?.runs) ? payload.runs : [];
  return list.map((run) => {
    const paired = Boolean(run.paired);
    // The contract's statuses (`payload.statuses`); an unpaired experiment is unpaired whatever else it says.
    const status = paired ? run.status : 'unpaired';
    const models = (Array.isArray(run.models) ? run.models : []).map((m) => m?.path ?? '').filter(Boolean);
    // Each task's split check: {reproduced, ratio_42, max_others, seed_of_max, n_others, margin}.
    const splits = (Array.isArray(run.runs) ? run.runs : [])
      .filter((t) => t?.split && typeof t.split === 'object')
      .map((t) => ({ task: t.task ?? null, ...t.split }));
    // The step the worker is on ('3 of 18: cross-validation fold 1 of 5 (momentum)'), else the fraction done.
    const steps = Number.isFinite(run.step) && Number.isFinite(run.steps) && run.step > 0 ? `${run.step} of ${run.steps}` : null;
    const label = run.step_label || null;
    return {
      table_name: run.table_name ?? null,
      name: run.display_name ?? run.table_name ?? '—',
      species: run.species ?? null,
      seed: run.seed ?? null,
      models,
      paired,
      status,
      reason: (status === 'failed' ? run.error : null) ?? run.reason ?? run.error ?? null,
      progress: (steps && label ? `${steps}: ${label}` : steps ?? label) ?? (Number.isFinite(run.progress) ? run.progress : null),
      seconds: Number.isFinite(run.duration_s) ? run.duration_s : null,
      splits,
    };
  });
}

/** Three significant figures of a positive ratio, as the Models page's drawers print it. */
const ratioText = (value) => (Number.isFinite(value) ? String(Number(value.toPrecision(3))) : '—');

/**
 * The tasks whose training split the analysis could not reproduce, as one
 * clause: seed 42's validation / training MSE against the largest of the other
 * seeds and the margin it had to clear (xgb_notes.js `splitLines` gives the
 * full sentence on every card). Empty when every split was reproduced.
 */
export function splitWarning(row) {
  const failed = (row?.splits ?? []).filter((s) => s.reproduced === false);
  if (!failed.length) return '';
  return `split not reproduced (${failed.map((s) => `${s.task ?? 'model'}: validation / training MSE `
    + `${ratioText(s.ratio_42)} at random_state 42 against at most ${ratioText(s.max_others)}`
    + `${Number.isFinite(s.seed_of_max) ? ` at random_state ${s.seed_of_max}` : ''}${Number.isFinite(s.margin) ? `, ${ratioText(s.margin)}× required` : ''}`)
    .join('; ')})`;
}

/** One row's status, as the table says it. */
export function runStatusText(row) {
  let text = RUN_STATUS[row.status] ?? row.status;
  if (row.status === 'running' && row.progress) {
    text += typeof row.progress === 'number' ? ` (${Math.round(row.progress * 100)}%)` : ` (${row.progress})`;
  }
  if (row.status === 'done' && Number.isFinite(row.seconds)) text += ` in ${Math.round(row.seconds)} s`;
  // A finished analysis whose split check failed is still shown, and its cards carry the hazard.
  if (row.status === 'done' && splitWarning(row)) text += `; ${splitWarning(row)}`;
  if (['failed', 'unpaired', 'stale', 'not_ready'].includes(row.status) && row.reason) text += `: ${row.reason}`;
  return text;
}

/** Timestamps in English whatever the browser's locale (CLAUDE.md: English only). */
const WHEN = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' });

/** A frame's own display mode: the lab keeps its lattice, the others their kernel. */
function ownDisplay(frame) {
  return frame === 'lab' ? 'native' : 'continuous';
}

export class AdminModal {
  constructor({ state, onIngested, upload = null, getExperiments = null }) {
    this.state = state;
    this.onIngested = onIngested || (() => {});
    this.upload = upload;
    // The page's experiment catalogue (GET /api/experiments), which carries
    // each experiment's derived-table status; read at render time.
    this.getExperiments = getExperiments || (() => []);
    this.backdrop = document.getElementById('admin-modal');
    this.datasetSelect = document.getElementById('admin-dataset');
    this.saveButton = document.getElementById('admin-save');
    this.scanButton = document.getElementById('admin-scan');
    this.status = document.getElementById('admin-status');
    this.notice = document.getElementById('admin-notice');
    this.ingestWhere = document.getElementById('admin-ingest-where');
    this.ingestTable = document.getElementById('admin-ingest-table');
    this.ingestRows = document.getElementById('admin-ingest-rows');
    this.rebuildWhere = document.getElementById('admin-rebuild-where');
    this.rebuildTable = document.getElementById('admin-rebuild-table');
    this.rebuildRows = document.getElementById('admin-rebuild-rows');
    this.rebuilds = new Map(); // table_name -> {job, error}
    this.rebuildTimer = null;
    this.rebuildLoop = null; // the polling loop that may schedule the next tick

    this.config = null; // the last GET or POST body
    this.form = {}; // field -> the value the form shows
    this.cleared = new Set(); // fields whose saved value Save removes
    this.jobs = new Map(); // job_id -> its latest status, for the ingest table
    this.announced = new Set(); // job ids already reported as ingested
    this.pollTimer = null;

    this.shell = new ModalShell(this.backdrop, {
      onClose: () => { this.stopPolling(); this.stopRebuildPolling(); this.stopRunPolling(); },
      initialFocus: () => this.datasetSelect,
    });

    this.rows = {};
    for (const [field, spec] of Object.entries(FIELDS)) {
      const row = this.backdrop.querySelector(`[data-field="${field}"]`);
      this.rows[field] = {
        chip: row.querySelector('.chip'),
        reset: row.querySelector('[data-reset]'),
        error: row.querySelector('.admin-error'),
        options: row.querySelector('.admin-options'),
      };
      this.rows[field].reset.addEventListener('click', () => this.reset(field));
      if (spec.choices) this.buildChoices(field, spec.choices);
    }
    this.datasetSelect.addEventListener('change', () => {
      this.pick('default_dataset', this.datasetSelect.value || null);
    });

    document.getElementById('open-admin').addEventListener('click', () => this.open());
    document.getElementById('admin-cancel').addEventListener('click', () => this.shell.close());
    this.saveButton.addEventListener('click', () => this.save());
    document.getElementById('admin-use-current')
      .addEventListener('click', () => this.useCurrentView());
    this.scanButton.addEventListener('click', () => this.scan());

    // The XGBoost model runs, after the derived tables.
    this.runs = { rows: [], error: null, timer: null, starting: new Set() };
    this.buildModelRuns(this.backdrop.querySelector('.modal'));
  }

  /** One radio per choice, labelled exactly as the sidebar labels it. */
  buildChoices(field, choices) {
    this.rows[field].options.replaceChildren(...choices.map((choice) => {
      const label = document.createElement('label');
      label.className = 'choice';
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = `admin-${field}`;
      input.value = choice.value ?? '';
      input.addEventListener('change', () => this.pick(field, choice.value));
      // The text in a span of its own, so a wrapped line hangs under the text
      // rather than restarting beneath the radio.
      const text = document.createElement('span');
      text.append(choice.label);
      if (choice.detail) {
        const muted = document.createElement('span');
        muted.className = 'muted';
        muted.textContent = ` ${choice.detail}`;
        text.append(muted);
      }
      label.append(input, text);
      return label;
    }));
  }

  async open() {
    this.shell.open();
    // Not awaited: the form reports through its own rows.
    this.upload?.prepare();
    this.renderRebuild();
    this.pollRebuilds();
    // Not awaited: the section reports through its own line.
    this.loadModelRuns();
    this.setStatus('Loading the saved defaults…');
    try {
      this.load(await getJson('/api/admin/config', {}, 'admin-config'));
      this.setStatus('');
    } catch (error) {
      this.setStatus(error instanceof ApiError ? error.message : String(error), true);
    }
  }

  /** Adopt a GET or POST body: the form restarts from what is in effect. */
  load(config) {
    this.config = config;
    this.cleared.clear();
    this.form = {};
    for (const field of Object.keys(FIELDS)) {
      this.form[field] = config.defaults[field]?.value ?? null;
    }
    this.render();
    this.renderIngest();
    this.pollJobs();
  }

  /**
   * Refresh the experiment list and the ingest report without touching the
   * form: an upload that finished while the panel is open must not discard
   * unsaved default edits, as `load()` would.
   */
  async refreshDatasets() {
    if (!this.config) return;
    try {
      const config = await getJson('/api/admin/config', {}, 'admin-datasets');
      this.config.options = config.options;
      this.config.auto_ingest = config.auto_ingest;
      this.render();
      this.renderIngest();
    } catch {
      // The next open reloads everything; nothing to report here.
    }
  }

  pick(field, value) {
    this.form[field] = value;
    this.cleared.delete(field);
    this.render();
  }

  /** Remove this field's saved value on Save, showing the value beneath it now. */
  reset(field) {
    this.cleared.add(field);
    this.form[field] = this.beneath(field);
    this.render();
  }

  /** What a field falls back to once its saved value is gone. */
  beneath(field) {
    const environment = this.config.environment || {};
    if (field in environment) return environment[field];
    if (field === 'default_dataset') {
      const ready = this.config.options.datasets.find((d) => d.status === 'ready');
      return ready ? ready.table_name : null;
    }
    return BUILTIN[field];
  }

  /** Fill the form with the view on screen: the quickest way to set a default. */
  useCurrentView() {
    if (!this.config) return;
    const v = this.state.values;
    const display = this.state.get('display');
    const current = {
      default_dataset: v.table_name,
      default_coord_system: v.frame,
      default_model: v.model,
      default_channel: v.channel,
      // A mode equal to the frame's own is left as "each frame's own".
      default_display_mode: display === ownDisplay(v.frame) ? null : display,
      default_rho_norm: v.rho_norm,
    };
    for (const [field, value] of Object.entries(current)) {
      if (value === undefined || (value === null && field !== 'default_display_mode')) continue;
      this.form[field] = value;
      this.cleared.delete(field);
    }
    this.render();
    this.setStatus('The form now holds the view on screen. Press Save defaults to keep it.');
  }

  isChanged(field) {
    return this.form[field] !== (this.config.defaults[field]?.value ?? null);
  }

  async save() {
    if (!this.config) return;
    const patch = {};
    for (const field of Object.keys(FIELDS)) {
      if (this.cleared.has(field)) patch[field] = null;
      else if (this.isChanged(field)) patch[field] = this.form[field];
    }
    if (!Object.keys(patch).length) {
      this.setStatus('Nothing to save: the form matches the defaults in effect.');
      return;
    }
    this.saveButton.disabled = true;
    try {
      this.load(await sendJson('POST', '/api/admin/config', patch));
      this.setStatus('Saved — new sessions open on this view.');
    } catch (error) {
      const message = error instanceof ApiError ? error.message : String(error);
      const box = this.rows[error?.problem?.field]?.error;
      if (box) {
        box.textContent = message;
        box.hidden = false;
      }
      this.setStatus(message, true);
    } finally {
      this.saveButton.disabled = false;
    }
  }

  render() {
    const config = this.config;
    if (!config) return;
    const datasets = config.options.datasets;
    this.datasetSelect.replaceChildren(...datasets.map((d) => {
      const option = document.createElement('option');
      option.value = d.table_name;
      option.disabled = d.status !== 'ready';
      option.textContent = d.status === 'ready'
        ? `${d.display_name} — ${formatInt(d.n_events)} events`
        : `${d.display_name} — ${d.status}`;
      return option;
    }));
    this.datasetSelect.value = this.form.default_dataset ?? '';

    // What the chosen experiment serves decides which choices are available.
    const chosen = datasets.find((d) => d.table_name === this.form.default_dataset);
    for (const [field, spec] of Object.entries(FIELDS)) {
      const { reset, error, options } = this.rows[field];
      error.hidden = true;
      if (options) {
        const offered = spec.offered && chosen ? chosen[spec.offered] : null;
        for (const input of options.querySelectorAll('input')) {
          const value = input.value === '' ? null : input.value;
          const available = !offered || offered.includes(value);
          input.checked = value === this.form[field];
          input.disabled = !available;
          const label = input.closest('label');
          label.classList.toggle('is-disabled', !available);
          label.title = available ? '' : `Not offered by ${chosen.display_name}.`;
        }
      }
      this.renderChip(field);
      reset.disabled = !(field in config.overrides) || this.cleared.has(field);
      reset.title = reset.disabled
        ? 'Nothing is saved here for this setting.'
        : 'Remove the value saved here, so the environment or built-in default applies.';
    }

    const notices = config.notices || [];
    this.notice.hidden = notices.length === 0;
    this.notice.replaceChildren(...notices.map((text) => {
      const line = document.createElement('div');
      line.textContent = text;
      return line;
    }));
  }

  renderChip(field) {
    const { chip } = this.rows[field];
    const source = this.config.defaults[field]?.source ?? 'builtin';
    let [text, title] = SOURCE[source] ?? [source, ''];
    let kind = source;
    if (this.cleared.has(field)) {
      [text, title, kind] = ['reset on save',
        'Save removes the value saved here, so the layer beneath applies.', 'pending'];
    } else if (this.isChanged(field)) {
      [text, title, kind] = ['not saved', 'Changed here; press Save defaults to keep it.', 'pending'];
    }
    chip.textContent = text;
    chip.title = title;
    chip.dataset.source = kind;
  }

  /* ---------------------------------------------------- automatic ingest */

  renderIngest() {
    const ingest = this.config?.auto_ingest;
    if (!ingest || !ingest.enabled) {
      // A configured folder that is missing says so; an unset one says how to set it.
      this.ingestWhere.textContent = ingest?.dir
        ? `Automatic ingest is off: ${ingest.reason || 'the drop folder is unavailable.'}`
        : 'Automatic ingest is off. Set CALOSRV_AUTO_INGEST_DIR to a folder (the compose '
          + 'file uses /app/host/ingest, which is ./ingest on the host) and every CSV or '
          + 'Parquet file dropped there becomes an experiment at the next start.';
      this.ingestTable.hidden = true;
      this.scanButton.disabled = true;
      return;
    }
    this.scanButton.disabled = false;
    const when = ingest.scanned_at ? WHEN.format(new Date(ingest.scanned_at)) : 'not yet';
    const entries = ingest.entries || [];
    this.ingestWhere.textContent = `Folder ${ingest.dir} · last scan ${when}`
      + (entries.length ? '' : ' · no CSV or Parquet files found');
    this.ingestTable.hidden = entries.length === 0;
    this.ingestRows.replaceChildren(...entries.map((entry) => {
      const row = document.createElement('tr');
      for (const text of [entry.file, entry.table_name || '—', this.resultOf(entry)]) {
        const cell = document.createElement('td');
        cell.textContent = text;
        row.append(cell);
      }
      if (entry.detail) row.title = entry.detail;
      return row;
    }));
  }

  resultOf(entry) {
    const job = entry.job_id ? this.jobs.get(entry.job_id) : null;
    if (job) {
      if (job.status === 'queued') return 'waiting for the ingest worker';
      if (job.status === 'running') return `ingesting (${Math.round(job.progress * 100)}%)`;
      if (job.status === 'done') return 'ingested — ready';
      if (job.status === 'failed') return `failed: ${job.error || 'see the server log'}`;
    }
    const label = RESULT[entry.action] || entry.action;
    return entry.detail && entry.action !== 'submitted' ? `${label} — ${entry.detail}` : label;
  }

  /** Follow the scan's jobs while the panel is open; the rows show their progress. */
  pollJobs() {
    this.stopPolling();
    const ids = (this.config?.auto_ingest?.entries || [])
      .filter((entry) => entry.job_id).map((entry) => entry.job_id);
    if (!ids.length || !this.shell.isOpen) return;
    const tick = async () => {
      let pending = false;
      for (const id of ids) {
        const known = this.jobs.get(id);
        if (known && (known.status === 'done' || known.status === 'failed')) continue;
        try {
          const job = await getJson(`/api/upload/${id}`, {}, `admin-job-${id}`);
          this.jobs.set(id, job);
          if (job.status === 'queued' || job.status === 'running') pending = true;
          if (job.status === 'done' && !this.announced.has(id)) {
            this.announced.add(id);
            this.onIngested(job);
          }
        } catch {
          // A restart forgets its jobs; the row keeps the scan's own result.
        }
      }
      this.renderIngest();
      if (pending && this.shell.isOpen) this.pollTimer = setTimeout(tick, JOB_POLL_MS);
    };
    tick();
  }

  stopPolling() {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  async scan() {
    this.scanButton.disabled = true;
    this.setStatus('Scanning the drop folder…');
    try {
      this.config.auto_ingest = await sendJson('POST', '/api/admin/auto-ingest/scan');
      this.renderIngest();
      this.pollJobs();
      this.setStatus('Scan complete.');
    } catch (error) {
      this.setStatus(error instanceof ApiError ? error.message : String(error), true);
    } finally {
      this.scanButton.disabled = !this.config?.auto_ingest?.enabled;
    }
  }

  setStatus(text, isError = false) {
    this.status.textContent = text;
    this.status.classList.toggle('is-error', isError);
  }

  /* ---------------------------------------------------- derived tables */

  /**
   * One row per ready experiment that states its derived tables: their
   * version, whether they are current, and - for a stale one - the Rebuild
   * action, or the progress of the rebuild under way.
   */
  renderRebuild() {
    if (!this.rebuildRows) return;
    const experiments = (this.getExperiments() || [])
      .filter((e) => e.status === 'ready' && e.capabilities?.derived);
    const stale = experiments.filter((e) => e.capabilities.derived.status === 'stale');
    if (this.rebuildWhere) {
      this.rebuildWhere.textContent = !experiments.length
        ? 'No experiment reports its derived tables.'
        : stale.length
          ? `${formatInt(stale.length)} experiment${stale.length === 1 ? ' was' : 's were'} derived by an earlier `
            + 'release: the panels that need the newer tables stay shut, with the reason shown, until it is '
            + 'rebuilt from its archive. A rebuild runs on the ingest worker in one transaction; the '
            + 'experiment stays served from its old tables until the new ones have verified.'
          : 'Every experiment\'s derived tables are current.';
    }
    if (this.rebuildTable) this.rebuildTable.hidden = experiments.length === 0;
    this.rebuildRows.replaceChildren(...experiments.map((e) => this.rebuildRow(e)));
  }

  rebuildRow(experiment) {
    const derived = experiment.capabilities.derived;
    const name = experiment.table_name;
    const row = document.createElement('tr');
    const label = document.createElement('td');
    label.textContent = experiment.display_name || name;
    label.title = name;
    const status = document.createElement('td');
    const action = document.createElement('td');
    const run = this.rebuilds.get(name);
    const version = `v${derived.version ?? '—'}`;
    if (run?.job && (run.job.status === 'queued' || run.job.status === 'running')) {
      status.textContent = run.job.status === 'queued'
        ? `${version} · rebuild waiting for the ingest worker`
        : `${version} · rebuilding (${Math.round((run.job.progress || 0) * 100)}%)`;
    } else if (run?.error) {
      status.textContent = `${version} · rebuild failed: ${run.error}`;
      status.classList.add('admin-error');
    } else if (derived.status === 'stale') {
      status.textContent = `${version}, current release v${derived.current ?? '—'} · stale`;
      if (derived.notice) status.title = derived.notice;
    } else {
      status.textContent = `${version} · current`;
    }
    const busy = run?.job && (run.job.status === 'queued' || run.job.status === 'running');
    if (derived.status === 'stale' || busy || run?.error) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mini';
      button.dataset.rebuild = name;
      button.textContent = 'Rebuild derived tables';
      button.disabled = Boolean(busy);
      button.title = busy ? 'A rebuild of this experiment is under way.'
        : 'Re-derive every table of this experiment from its Parquet archive, atomically.';
      button.addEventListener('click', () => this.rebuild(name));
      action.append(button);
    }
    row.append(label, status, action);
    return row;
  }

  /** Start one experiment's rebuild and follow its job. */
  async rebuild(name) {
    this.rebuilds.set(name, { job: { status: 'queued', progress: 0 } });
    this.renderRebuild();
    try {
      const reply = await sendJson('POST', `/api/admin/experiments/${encodeURIComponent(name)}/rebuild`);
      this.rebuilds.set(name, { job: reply.job });
      this.setStatus(`Rebuilding the derived tables of ${name} from its archive…`);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : String(error);
      this.rebuilds.set(name, { error: message });
      this.setStatus(message, true);
    }
    this.renderRebuild();
    this.pollRebuilds();
  }

  /** The rebuilds whose job is still queued or running, read afresh. */
  pendingRebuilds() {
    return [...this.rebuilds.entries()]
      .filter(([, run]) => run.job?.job_id && (run.job.status === 'queued' || run.job.status === 'running'));
  }

  /**
   * Follow the rebuilds under way while the panel is open.
   *
   * The list is read again on every tick: a rebuild that finished on the last
   * tick has left `this.rebuilds`, and polling it again would reload the
   * catalogue (and every physics card) once per tick until the other rebuilds
   * finish.
   */
  pollRebuilds() {
    this.stopRebuildPolling();
    if (!this.pendingRebuilds().length || !this.shell.isOpen) return;
    // One polling loop at a time: a rebuild started while a tick is awaiting
    // restarts the loop, and the superseded tick schedules nothing.
    const loop = {};
    this.rebuildLoop = loop;
    const tick = async () => {
      this.rebuildTimer = null;
      for (const [name, run] of this.pendingRebuilds()) {
        try {
          const job = await getJson(`/api/upload/${run.job.job_id}`, {}, `admin-rebuild-${name}`);
          if (job.status === 'done') {
            this.rebuilds.delete(name);
            this.setStatus(`The derived tables of ${name} were rebuilt.`);
            await this.onIngested(job);
          } else if (job.status === 'failed') {
            this.rebuilds.set(name, { error: job.error || 'see the server log' });
          } else {
            this.rebuilds.set(name, { job });
          }
        } catch {
          // A restart forgets its jobs; the next open shows the catalogue's status.
          this.rebuilds.delete(name);
        }
      }
      this.renderRebuild();
      if (this.rebuildLoop !== loop) return;
      if (this.pendingRebuilds().length && this.shell.isOpen) this.rebuildTimer = setTimeout(tick, JOB_POLL_MS);
    };
    tick();
  }

  stopRebuildPolling() {
    if (this.rebuildTimer) clearTimeout(this.rebuildTimer);
    this.rebuildTimer = null;
    this.rebuildLoop = null;
  }

  /* ------------------------------------------------- XGBoost model runs */

  /** The section's markup, built once and appended to the panel. */
  buildModelRuns(modal) {
    if (!modal) return;
    const section = document.createElement('section');
    section.className = 'admin-modelruns';
    // Spaced and ruled like the panel's other lower sections (controls.css).
    section.setAttribute('aria-label', 'XGBoost model runs');
    const head = document.createElement('div');
    head.className = 'admin-head';
    const title = document.createElement('h3');
    title.textContent = 'XGBoost model runs';
    const spacer = document.createElement('span');
    spacer.className = 'spacer';
    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'mini';
    refresh.textContent = 'Refresh';
    refresh.title = 'Read the pairings and the state of each analysis again';
    refresh.addEventListener('click', () => this.loadModelRuns());
    const rescan = document.createElement('button');
    rescan.type = 'button';
    rescan.className = 'mini';
    rescan.dataset.rescanModels = '';
    rescan.textContent = 'Rescan models';
    rescan.title = 'Rescan the models folder and queue the analysis of every experiment whose '
      + 'stored analysis is missing or stale (a changed model file, library or data)';
    rescan.addEventListener('click', () => this.rescanModels());
    head.append(title, spacer, refresh, rescan);
    const where = document.createElement('div');
    where.className = 'hint';
    where.textContent = '—';
    const table = document.createElement('table');
    table.className = 'table';
    table.hidden = true;
    const thead = document.createElement('thead');
    const header = document.createElement('tr');
    for (const text of ['Experiment', 'Models', 'Analysis', '']) {
      const cell = document.createElement('th');
      cell.textContent = text;
      header.append(cell);
    }
    thead.append(header);
    const body = document.createElement('tbody');
    table.append(thead, body);
    section.append(head, where, table);
    // Last in the panel, after the derived tables.
    modal.append(section);
    Object.assign(this.runs, { section, where, table, body, refresh, rescan });
  }

  /** Read the model-runs list. */
  async loadModelRuns() {
    if (!this.runs?.section) return;
    this.stopRunPolling();
    try {
      const payload = await getJson('/api/admin/model-runs', {}, 'admin-model-runs');
      this.runs.error = null;
      this.runs.payload = payload;
      this.runs.rows = modelRunRows(payload);
    } catch (error) {
      if (error?.name === 'AbortError') return;
      this.runs.rows = [];
      this.runs.error = error instanceof ApiError ? error.message : String(error?.message ?? error);
    }
    this.renderModelRuns();
    if (this.runs.rows.some(runPending) && this.shell.isOpen) {
      this.runs.timer = setTimeout(() => this.pollModelRuns(), JOB_POLL_MS);
    }
  }

  /** Poll while an analysis is under way; the catalogue reloads when one finishes. */
  async pollModelRuns() {
    this.runs.timer = null;
    const before = new Set(this.runs.rows.filter(runPending).map((row) => row.table_name));
    await this.loadModelRuns();
    const finished = this.runs.rows.some((row) => before.has(row.table_name) && !runPending(row));
    // A finished analysis opens the experiment's XGBoost gate: the catalogue says so.
    if (finished) await this.onIngested();
  }

  stopRunPolling() {
    if (this.runs?.timer) clearTimeout(this.runs.timer);
    if (this.runs) this.runs.timer = null;
  }

  renderModelRuns() {
    const { where, table, body } = this.runs;
    if (this.runs.error) {
      where.textContent = `The model runs could not be read: ${this.runs.error}`;
      table.hidden = true;
      return;
    }
    const rows = this.runs.rows;
    const folder = this.runs.payload?.models?.dir ?? null;
    const paired = rows.filter((row) => row.paired).length;
    where.textContent = (folder ? `Models folder ${folder} · ` : '')
      + (rows.length
        ? `${formatInt(paired)} of ${formatInt(rows.length)} experiment${rows.length === 1 ? '' : 's'} paired with `
          + 'models of their species and seed. An analysis runs in the background on its own worker; the '
          + 'XGBoost cards of the Models page open once it is done.'
        : 'No event-level aggregate experiment to pair with the XGBoost models.');
    table.hidden = rows.length === 0;
    body.replaceChildren(...rows.map((row) => this.modelRunRow(row)));
  }

  modelRunRow(row) {
    const tr = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = row.name;
    if (row.table_name) name.title = row.table_name;
    const models = document.createElement('td');
    models.textContent = row.paired
      ? `${row.species ?? '—'}, seed ${row.seed ?? '—'}${row.models.length ? ` · ${row.models.join(', ')}` : ''}`
      : '—';
    const status = document.createElement('td');
    status.textContent = runStatusText(row);
    if (row.status === 'failed') status.classList.add('admin-error');
    if (splitWarning(row)) status.classList.add('admin-warning');
    const action = document.createElement('td');
    if (row.paired && row.table_name) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mini';
      button.dataset.analyse = row.table_name;
      button.textContent = 'Re-analyse';
      const busy = runPending(row) || this.runs.starting.has(row.table_name);
      button.disabled = busy;
      button.title = busy ? 'An analysis of this experiment is under way.'
        : 'Queue this experiment\'s XGBoost analysis again: the holdout predictions, the five-fold refits, '
          + 'the binary thresholding, the surrogate trees and the importances.';
      button.addEventListener('click', () => this.analyse(row.table_name));
      action.append(button);
    }
    tr.append(name, models, status, action);
    return tr;
  }

  /**
   * Rescan models: the scan queues every missing or stale analysis; the list
   * is then read again from GET, which follows what was queued.
   */
  async rescanModels() {
    const button = this.runs?.rescan;
    if (button) button.disabled = true;
    try {
      const payload = await sendJson('POST', '/api/admin/model-runs/scan');
      const queued = modelRunRows(payload).filter(runPending).length;
      this.setStatus(queued
        ? `Models rescanned: ${formatInt(queued)} XGBoost analys${queued === 1 ? 'is' : 'es'} queued or running.`
        : 'Models rescanned: every paired analysis is current, failed on unchanged inputs or unpaired.');
    } catch (error) {
      this.setStatus(error instanceof ApiError ? error.message : String(error?.message ?? error), true);
    } finally {
      if (button) button.disabled = false;
    }
    await this.loadModelRuns();
  }

  /** Queue one experiment's analysis again, then follow it. */
  async analyse(name) {
    this.runs.starting.add(name);
    this.renderModelRuns();
    try {
      await sendJson('POST', `/api/admin/model-runs/${encodeURIComponent(name)}/analyse`);
      this.setStatus(`The XGBoost analysis of ${name} is queued.`);
    } catch (error) {
      this.setStatus(error instanceof ApiError ? error.message : String(error?.message ?? error), true);
    } finally {
      this.runs.starting.delete(name);
    }
    await this.loadModelRuns();
  }
}
