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
 *
 * Between the automatic ingest and the derived tables sits Source files (GET
 * /api/admin/experiments, read-only): each experiment against the file it was
 * ingested from - whether that file changed on disk since, which the hf-sync
 * service makes possible by updating ./ingest at every start. Nothing is
 * re-ingested by itself: Re-ingest (a changed, ready experiment) and Retry
 * ingest (a failed one) post to /api/admin/experiments/{name}/reingest and
 * the row follows the job. The section is skipped when the page has no markup
 * for it. The row models are pure functions of the payload (`sourceRows`,
 * `sourceBadge`, `sourceJobText`, `sourceAction`, `sourcesSummary`), and so
 * are the two rules that follow the jobs: `finishedJobs` (a re-ingest or retry
 * seen active on one read and over on a later one, whoever started it, is
 * reported once) and `nextSourceRead` (when to read again).
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
  changed: 'already an experiment; its file has changed',
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

/* ------------------------------------------------------------ source files */

/** A job still on the ingest worker's books. */
function jobActive(job) {
  return job?.status === 'queued' || job?.status === 'running';
}

/** An ISO timestamp as the server writes its dates in sentences: `2026-11-11 19:40 UTC`. */
function utcText(iso) {
  const date = iso ? new Date(iso) : null;
  if (!date || Number.isNaN(date.getTime())) return '';
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** Bytes with thousands separators, as the server's sentences print them. */
const bytesText = (value) => (Number.isFinite(value) ? `${formatInt(value)} bytes` : '');

/**
 * The experiments against their source files, from GET /api/admin/experiments
 * (`payload.experiments`, tests/contracts/admin_experiments.json): one entry
 * per experiment with its `source` block, the two `actions` the server offers
 * and the newest `job` of that name. Each row: `{table_name, name, file, path,
 * origin, status, state, source_changed, settling, detail, recorded, current,
 * badge: {text, kind}, actions, job, error}`. A missing `source` reads as an
 * untracked experiment. Pure; `null` or `{}` gives no rows.
 */
export function sourceRows(payload) {
  const { experiments } = payload ?? {};
  const list = Array.isArray(experiments) ? experiments : [];
  return list.map((experiment) => {
    const source = experiment.source && typeof experiment.source === 'object' ? experiment.source : {};
    const row = {
      table_name: experiment.table_name ?? null,
      name: experiment.display_name || experiment.table_name || '—',
      file: source.file ?? null,
      path: source.path ?? null,
      origin: source.origin ?? null,
      status: experiment.status ?? null,
      state: source.state ?? 'untracked',
      source_changed: Boolean(experiment.source_changed),
      settling: Boolean(source.settling),
      detail: source.detail || '',
      recorded: source.recorded ?? null,
      current: source.current ?? null,
      actions: experiment.actions ?? {},
      job: experiment.job ?? null,
      error: experiment.error ?? null,
    };
    row.badge = sourceBadge(row);
    return row;
  });
}

/** The state chip, by the first rule that matches (`kind` picks its colour: changed, failed, busy, current, muted). */
export function sourceBadge(row) {
  const job = row?.job;
  if (jobActive(job)) {
    const text = job.mode === 'reingest' ? 'Re-ingesting' : job.mode === 'retry' ? 'Retrying' : 'Ingesting';
    return { text, kind: 'busy' };
  }
  if (row?.status === 'failed') return { text: 'Ingestion failed', kind: 'failed' };
  switch (row?.state) {
    case 'changed': return { text: 'Source updated on disk', kind: 'changed' };
    case 'unchanged': return { text: 'Current', kind: 'current' };
    case 'touched': return { text: 'Timestamp changed; sampled content the same', kind: 'muted' };
    case 'missing': return { text: 'Source file not found', kind: 'muted' };
    default:
      if (row?.origin === 'upload') return { text: 'Uploaded: no file on the server to compare', kind: 'muted' };
      if (row?.origin === 'seed') return { text: 'Demonstration dataset: ships in the image', kind: 'muted' };
      return { text: 'No source recorded', kind: 'muted' };
  }
}

/** A re-ingest error that already says what became of the experiment (pipeline.py, jobs.py). */
const STATED_OUTCOME = /served as it was|are committed|nothing was done|half-finished|interrupted/i;

/** A job's error as a sentence: the server's own text, ended with a full stop. */
function sentence(text) {
  const clean = String(text || 'see the server log').trim();
  return /[.!?]$/.test(clean) ? clean : `${clean}.`;
}

/** The line under a row's state: what its newest job is doing or did ('' without a job). */
export function sourceJobText(row) {
  const job = row?.job;
  if (!job) return '';
  const percent = `${Math.round((job.progress || 0) * 100)}%`;
  switch (job.status) {
    case 'queued':
      return 'Waiting for the ingest worker';
    case 'running':
      if (job.mode === 'reingest') {
        return `Re-ingesting (${percent}) — served from its previous data until the new tables verify`;
      }
      if (job.mode === 'rebuild') return `Rebuilding (${percent})`;
      if (job.mode === 'append') return `Appending (${percent})`;
      return job.mode === 'retry' ? `Retrying (${percent})` : `Ingesting (${percent})`;
    case 'done':
      if (job.mode === 'rebuild') return 'Rebuilt — ready';
      if (job.mode === 'append') return 'Appended — ready';
      return job.mode === 'reingest' ? 'Re-ingested — ready' : 'Ingested — ready';
    case 'failed':
      if (job.mode === 'reingest') {
        // The worker's own message says what became of the experiment when it can: rolled
        // back and served as it was, committed with its manifest pending, refused before
        // anything was done, half-finished, interrupted. Adding "served as it was" would
        // then repeat it, or contradict it. Any other failure was raised before a change.
        if (STATED_OUTCOME.test(job.error || '')) return sentence(job.error);
        return `Re-ingest failed: ${sentence(job.error)} It is served as it was.`;
      }
      if (job.mode === 'rebuild') return `Rebuild failed: ${job.error || 'see the server log'}`;
      if (job.mode === 'append') return `Append failed: ${job.error || 'see the server log'}`;
      return job.mode === 'retry' ? `Retry failed: ${job.error || 'see the server log'}`
        : `Failed: ${job.error || 'see the server log'}`;
    default:
      return '';
  }
}

/**
 * The button a row offers: `{kind: 'reingest' | 'retry' | null, label, disabled, title}`.
 * A failed experiment is retried, a changed one re-ingested, every other row
 * has no button. `starting` holds the names whose request is in flight (a Set
 * or an array); the button is disabled while the name is starting or busy, or
 * the server says the action is not available, and its title then says why.
 */
export function sourceAction(row, starting = null) {
  const name = row?.table_name;
  const isStarting = Boolean(starting?.has?.(name) ?? starting?.includes?.(name));
  const busy = jobActive(row?.job);
  let kind = null;
  if (row?.status === 'failed') kind = 'retry';
  else if (row?.state === 'changed') kind = 'reingest';
  if (!kind) return { kind: null, label: '', disabled: true, title: '' };
  const verdict = row.actions?.[kind] ?? {};
  const label = kind === 'retry' ? 'Retry ingest' : 'Re-ingest';
  const file = row.file ?? 'its source file';
  let title;
  if (!verdict.available) {
    title = verdict.reason || 'The server does not offer this action for this experiment.';
  } else if (isStarting || busy) {
    title = 'A job for this experiment is queued or running.';
  } else if (kind === 'retry') {
    title = `Ingest it again from ${file}; the tables and archive files of the failed attempt are dropped first.`;
  } else {
    title = `Rebuild this experiment from ${file} in one transaction: it stays served from its previous `
      + 'data until the new tables verify, and a failure leaves it as it was.';
  }
  return { kind, label, disabled: !verdict.available || isStarting || busy, title };
}

/** The section's hint line: where the files are, what changed, and the rule that nothing is automatic. */
export function sourcesSummary(rows, roots) {
  const where = roots?.drop_folder ? `Drop folder ${roots.drop_folder}`
    : roots?.local ? `Local folder ${roots.local}` : 'No drop folder is set';
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) return `${where} · No experiment to compare with its source file.`;
  const changed = list.filter((row) => row.state === 'changed').length;
  const failed = list.filter((row) => row.status === 'failed').length;
  if (!changed && !failed) return `${where} · Every experiment with a tracked source matches its file on disk.`;
  const parts = [where];
  if (changed) parts.push(`${formatInt(changed)} experiment${changed === 1 ? ' has' : 's have'} a newer file on disk`);
  if (failed) parts.push(`${formatInt(failed)} failed`);
  return `${parts.join(' · ')}. Nothing is re-ingested until its button is pressed; a re-ingest runs on the `
    + 'ingest worker, and the experiment stays served from its previous data until the new tables have verified.';
}

/** The modes whose end the page reports: a re-ingest and a retry change an experiment under the panels. */
const REPORTED_MODES = new Set(['reingest', 'retry']);

/**
 * Which re-ingest or retry jobs ended since the last read. `previouslyActive` is
 * a Map (table name -> job id) of the jobs seen queued or running, `rows` the
 * rows of the read just made. Returns `{finished, active}`: `finished` lists
 * `{row, job}` for each tracked job that is now done or failed, and `active` is
 * the Map to keep (the tracked jobs still running, plus every such job this read
 * sees queued or running, however it was started). A job leaves the Map when it
 * is reported, so it is reported once; a job that is no longer the experiment's
 * newest is forgotten, since its outcome cannot be read any more. Pure; the
 * Map passed in is not changed.
 */
export function finishedJobs(previouslyActive, rows) {
  const active = new Map(previouslyActive ?? []);
  const finished = [];
  for (const row of Array.isArray(rows) ? rows : []) {
    const name = row?.table_name;
    const job = row?.job;
    if (!name) continue;
    const tracked = active.get(name);
    if (!job) {
      active.delete(name);
      continue;
    }
    if (jobActive(job)) {
      if (REPORTED_MODES.has(job.mode)) active.set(name, job.job_id);
      else active.delete(name);
    } else if (tracked !== undefined) {
      active.delete(name);
      if (tracked === job.job_id && (job.status === 'done' || job.status === 'failed')) finished.push({ row, job });
    }
  }
  return { finished, active };
}

/**
 * Milliseconds until the next read of the source files, or `null` for none.
 * A queued or running job is followed every `JOB_POLL_MS`. A file that hf-sync
 * just wrote is `settling`, and its Re-ingest stays refused until it has been
 * unchanged for `roots.settle_s`: one more read, a second after that, lets the
 * button enable itself. A closed panel reads nothing. Pure.
 */
export function nextSourceRead(rows, roots, open = true) {
  if (!open) return null;
  const list = Array.isArray(rows) ? rows : [];
  if (list.some((row) => jobActive(row?.job))) return JOB_POLL_MS;
  if (list.some((row) => row?.settling)) {
    const settle = Number.isFinite(roots?.settle_s) ? Math.max(0, roots.settle_s) : 0;
    return Math.round((settle + 1) * 1000);
  }
  return null;
}

/** What a row's file cell says on hover: the full path, and the file as recorded and as found. */
function sourceFileTitle(row) {
  const lines = [row.path || row.file || ''];
  for (const [label, entry] of [['Recorded', row.recorded], ['On disk now', row.current]]) {
    if (!entry) continue;
    const when = utcText(entry.modified);
    lines.push(`${label}: ${bytesText(entry.bytes)}${when ? `, modified ${when}` : ''}`);
  }
  return lines.filter(Boolean).join('\n');
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
    this.sourcesWhere = document.getElementById('admin-sources-where');
    this.sourcesTable = document.getElementById('admin-sources-table');
    this.sourcesRows = document.getElementById('admin-sources-rows');
    this.sourcesRefresh = document.getElementById('admin-sources-refresh');
    // Source files: the rows, the names whose request is in flight, the message
    // under a row, the re-ingest / retry jobs seen active (name -> job_id) so
    // their end is reported once, and the polling loop.
    this.sources = {
      rows: [], payload: null, error: null, starting: new Set(), errors: new Map(),
      active: new Map(), timer: null, loop: null,
    };
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
      onClose: () => {
        this.stopPolling(); this.stopRebuildPolling(); this.stopRunPolling(); this.stopSourcePolling();
      },
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
    this.sourcesRefresh?.addEventListener('click', () => this.loadSources());

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
    // Not awaited: the section reports through its own line.
    this.loadSources();
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
          + 'file uses /app/ingest, which is ./ingest on the host) and every CSV or '
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
      // The scan may have noticed a changed file: the section compares again.
      this.loadSources();
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

  /* ---------------------------------------------------------- source files */

  /**
   * Read the experiments against their source files, report the re-ingest and
   * retry jobs that finished since the last read, and keep polling while a job
   * is queued or running. A newer read supersedes an older one.
   */
  async loadSources() {
    if (!this.sourcesRows || !this.sourcesWhere) return;
    this.stopSourcePolling();
    const loop = {};
    this.sources.loop = loop;
    let payload;
    try {
      payload = await getJson('/api/admin/experiments', {}, 'admin-sources');
    } catch (error) {
      if (error?.name === 'AbortError' || this.sources.loop !== loop) return;
      this.sources.rows = [];
      this.sources.error = error instanceof ApiError ? error.message : String(error?.message ?? error);
      this.renderSources();
      return;
    }
    if (this.sources.loop !== loop) return;
    this.sources.error = null;
    this.sources.payload = payload;
    this.sources.rows = sourceRows(payload);
    await this.reportSourceJobs();
    this.renderSources();
    if (this.sources.loop !== loop) return;
    const wait = nextSourceRead(this.sources.rows, payload?.roots, this.shell.isOpen);
    if (wait !== null) this.sources.timer = setTimeout(() => this.loadSources(), wait);
  }

  stopSourcePolling() {
    if (this.sources.timer) clearTimeout(this.sources.timer);
    this.sources.timer = null;
    this.sources.loop = null;
  }

  /**
   * A re-ingest or retry job seen active on any read, whoever started it (this
   * page, another tab, a page reloaded during the job), that is now done or
   * failed: tell the page, once.
   */
  async reportSourceJobs() {
    const { finished, active } = finishedJobs(this.sources.active, this.sources.rows);
    // Swapped before the first await, so an overlapping read cannot report the same job again.
    this.sources.active = active;
    for (const { row, job } of finished) {
      if (job.status === 'done') {
        await this.onIngested(job);
        this.refreshDatasets();
        this.renderRebuild();
        this.loadModelRuns();
        this.setStatus(job.mode === 'retry' ? `${row.name} was ingested again from ${row.file}.`
          : `${row.name} was re-ingested from ${row.file}.`);
      } else {
        this.setStatus(sourceJobText(row), true);
      }
    }
  }

  renderSources() {
    const { rows, error } = this.sources;
    if (error) {
      this.sourcesWhere.textContent = `The source files could not be read: ${error}`;
      if (this.sourcesTable) this.sourcesTable.hidden = true;
      this.sourcesRows.replaceChildren();
      return;
    }
    this.sourcesWhere.textContent = sourcesSummary(rows, this.sources.payload?.roots);
    if (this.sourcesTable) this.sourcesTable.hidden = rows.length === 0;
    this.sourcesRows.replaceChildren(...rows.map((row) => this.sourceRow(row)));
  }

  sourceRow(row) {
    const tr = document.createElement('tr');
    tr.dataset.table = row.table_name ?? '';
    tr.dataset.state = row.state;

    const name = document.createElement('td');
    name.textContent = row.name;
    if (row.table_name) name.title = row.table_name;

    const file = document.createElement('td');
    file.className = 'source-file';
    file.textContent = row.file ?? '—';
    file.title = sourceFileTitle(row);

    const state = document.createElement('td');
    state.className = 'source-state';
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.dataset.state = row.badge.kind;
    chip.textContent = row.badge.text;
    state.append(chip);
    if (row.detail) {
      const detail = document.createElement('div');
      detail.className = 'source-detail';
      detail.textContent = row.detail;
      state.append(detail);
    }
    const jobText = sourceJobText(row);
    if (jobText) {
      const line = document.createElement('div');
      line.className = 'source-job';
      if (row.job.status === 'failed') line.classList.add('admin-error');
      line.textContent = jobText;
      state.append(line);
    }
    const message = this.sources.errors.get(row.table_name);
    if (message) {
      const line = document.createElement('div');
      line.className = 'source-job admin-error';
      line.textContent = message;
      state.append(line);
    }

    const cell = document.createElement('td');
    cell.className = 'source-action';
    const action = sourceAction(row, this.sources.starting);
    if (action.kind) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mini';
      if (action.kind === 'retry') button.dataset.retry = row.table_name;
      else button.dataset.reingest = row.table_name;
      button.textContent = action.label;
      button.disabled = action.disabled;
      button.title = action.title;
      button.addEventListener('click', () => this.reingest(row.table_name));
      cell.append(button);
    }
    tr.append(name, file, state, cell);
    return tr;
  }

  /** Re-ingest a changed experiment, or retry a failed one, and follow its job. */
  async reingest(name) {
    const row = this.sources.rows.find((r) => r.table_name === name);
    if (!row || this.sources.starting.has(name)) return;
    const retry = row.status === 'failed';
    // Disabled at once, before the request is answered.
    this.sources.starting.add(name);
    this.sources.errors.delete(name);
    this.renderSources();
    this.setStatus(retry ? `Retrying the ingest of ${row.name}…` : `Re-ingesting ${row.name} from ${row.file}…`);
    try {
      const reply = await sendJson('POST', `/api/admin/experiments/${encodeURIComponent(name)}/reingest`, {});
      // Seen from the start, so a job that ends before the first read is still reported.
      if (reply?.job?.job_id) this.sources.active.set(name, reply.job.job_id);
      await this.loadSources();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : String(error?.message ?? error);
      this.sources.errors.set(name, message);
      this.setStatus(message, true);
    } finally {
      this.sources.starting.delete(name);
      this.renderSources();
    }
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
