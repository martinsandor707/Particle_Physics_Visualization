/* The Admin Settings panel: the view a new session opens on.
 *
 * It reads GET /api/admin/config and saves with POST. Beside every control a
 * chip says where the current value comes from - saved here, the deployment's
 * environment, or the built-in view - and Reset lets the layer beneath show
 * through again. Nothing is stored until Save, and saving never changes the
 * view of the session that saved it: the defaults apply only to links that
 * carry no view state (State.applyDefaults). The lower section reports the
 * automatic ingest of the drop folder, with live job status, and can rescan it.
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

/** Timestamps in English whatever the browser's locale (CLAUDE.md: English only). */
const WHEN = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' });

/** A frame's own display mode: the lab keeps its lattice, the others their kernel. */
function ownDisplay(frame) {
  return frame === 'lab' ? 'native' : 'continuous';
}

export class AdminModal {
  constructor({ state, onIngested }) {
    this.state = state;
    this.onIngested = onIngested || (() => {});
    this.backdrop = document.getElementById('admin-modal');
    this.datasetSelect = document.getElementById('admin-dataset');
    this.saveButton = document.getElementById('admin-save');
    this.scanButton = document.getElementById('admin-scan');
    this.status = document.getElementById('admin-status');
    this.notice = document.getElementById('admin-notice');
    this.ingestWhere = document.getElementById('admin-ingest-where');
    this.ingestTable = document.getElementById('admin-ingest-table');
    this.ingestRows = document.getElementById('admin-ingest-rows');

    this.config = null; // the last GET or POST body
    this.form = {}; // field -> the value the form shows
    this.cleared = new Set(); // fields whose saved value Save removes
    this.jobs = new Map(); // job_id -> its latest status, for the ingest table
    this.announced = new Set(); // job ids already reported as ingested
    this.pollTimer = null;

    this.shell = new ModalShell(this.backdrop, {
      onClose: () => this.stopPolling(),
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
      this.ingestWhere.textContent = 'Automatic ingest is off. Set CALOSRV_AUTO_INGEST_DIR '
        + 'to a folder (the compose file uses /app/host/ingest, which is ./ingest on the host) '
        + 'and every CSV or Parquet file dropped there becomes an experiment at the next start.';
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
}
