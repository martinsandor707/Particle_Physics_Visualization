/* The upload modal: naming, mode, streaming upload or server-side ingest, job polling.
 *
 * Large uploads are deliberately permitted - collaborators outside the
 * organisation have no shell access to the server and the browser is their only
 * route in. What they get instead of a size limit is an honest warning: a
 * browser upload cannot resume, and ingestion needs free disk space several
 * times the file's size.
 *
 * Every refusal the server would make is asked here first, before a byte is
 * sent: an unsupported file type, a name the server rejects, an append to an
 * experiment that does not exist, and a new experiment onto a name already
 * taken. The last is allowed only with Replace ticked, because replacing drops
 * the old experiment before the new file is read.
 */

import { ApiError, getJson, postForm, uploadDataset } from '../api.js';
import { formatBytes, formatInt } from '../scale.js';
import { ModalShell } from './modal.js';

const POLL_INTERVAL_MS = 1200;

/* The server's naming rules (calosrv/db/naming.py), checked before sending. */
const NAME_PATTERN = /^[a-z][a-z0-9_]{0,47}$/;
const SAMPLE_SUFFIX = '_s10';
const RESERVED = new Set(['experiment', 'experiment_registry', 'main', 'temp', 'system']);

/* The file types the server reads, by suffix; the content decides the format. */
const SUFFIX_FORMAT = { csv: 'csv', txt: 'csv', parquet: 'parquet' };

function formatOfName(name) {
  const dot = name.lastIndexOf('.');
  if (dot < 0) return 'csv';
  return SUFFIX_FORMAT[name.slice(dot + 1).toLowerCase()] ?? null;
}

function nameProblem(table) {
  if (!table) return 'Enter an experiment name.';
  if (!NAME_PATTERN.test(table)) {
    return 'Experiment names must start with a lowercase letter and contain only '
      + 'lowercase letters, digits and underscores (at most 48 characters).';
  }
  if (table.endsWith(SAMPLE_SUFFIX)) {
    return `Experiment names may not end in ${SAMPLE_SUFFIX}: that suffix is reserved for `
      + 'preview-sample tables.';
  }
  if (RESERVED.has(table)) return `The name ${table} is reserved.`;
  return null;
}

export class UploadModal {
  constructor({ onComplete, getExperiments }) {
    this.backdrop = document.getElementById('upload-modal');
    this.tableInput = document.getElementById('upload-table');
    this.displayInput = document.getElementById('upload-display');
    this.replaceRow = document.getElementById('upload-replace-row');
    this.replaceBox = document.getElementById('upload-replace');
    this.replaceText = document.getElementById('upload-replace-text');
    this.offsetRow = document.getElementById('upload-offset-row');
    this.offsetInput = document.getElementById('upload-offset');
    this.fileInput = document.getElementById('upload-file');
    this.fileInfo = document.getElementById('upload-file-info');
    this.warning = document.getElementById('upload-warning');
    this.progressRow = document.getElementById('upload-progress-row');
    this.progressBar = document.getElementById('upload-progress-bar');
    this.status = document.getElementById('upload-status');
    this.submit = document.getElementById('upload-submit');
    this.cancel = document.getElementById('upload-cancel');
    this.serverSelect = document.getElementById('upload-server-file');
    this.serverInfo = document.getElementById('upload-server-info');
    this.browserRow = document.getElementById('upload-browser-row');
    this.serverRow = document.getElementById('upload-server-row');
    this.onComplete = onComplete || (() => {});
    this.getExperiments = getExperiments || (() => []);
    this.info = null;
    // True from the moment a transfer or server-side ingest starts until its
    // job finishes. Closing the modal does not stop either, so reopening it
    // must not re-arm Submit while one is still running.
    this.busy = false;

    // Hiding the modal never stops the job poll: the ingest carries on
    // server-side, and onComplete is what brings its experiment on screen.
    this.shell = new ModalShell(this.backdrop, { initialFocus: () => this.tableInput });

    for (const input of document.querySelectorAll('input[name="upload-source"]')) {
      input.addEventListener('change', () => this.setSource(input.value));
    }
    for (const input of document.querySelectorAll('input[name="upload-mode"]')) {
      input.addEventListener('change', () => this.describeTarget());
    }
    this.tableInput.addEventListener('input', () => this.describeTarget());

    document.getElementById('open-upload').addEventListener('click', () => this.open());
    this.cancel.addEventListener('click', () => this.shell.close());
    this.submit.addEventListener('click', () => this.start());
    this.fileInput.addEventListener('change', () => this.describeFile());
  }

  async open() {
    this.shell.open();
    if (!this.busy) this.reset();
    this.describeTarget();
    try {
      this.info = await getJson('/api/upload-info', {}, 'upload-info');
      this.warning.textContent = this.info.warning;
      this.warning.hidden = false;
      this.describeFile();
    } catch {
      this.warning.hidden = true;
    }

    try {
      const local = await getJson('/api/local-files', {}, 'local-files');
      this.localRoot = local.root;
      this.serverSelect.innerHTML = local.files.length
        ? local.files.map((f) =>
          `<option value="${escapeAttribute(f.path)}">${escapeAttribute(f.relative)}` +
          ` — ${formatBytes(f.size_bytes)}</option>`).join('')
        : '<option value="">No CSV or Parquet files found on the server</option>';
      this.serverInfo.textContent = local.enabled
        ? `Read in place from ${local.root}. Nothing is transferred, so this is ` +
          'the right route for multi-gigabyte datasets.'
        : 'Server-side ingestion is not enabled on this deployment.';
      for (const input of document.querySelectorAll('input[name="upload-source"][value="server"]')) {
        input.disabled = !local.enabled || !local.files.length;
      }
    } catch {
      this.serverInfo.textContent = 'Could not list server-side files.';
    }
  }

  setSource(source) {
    this.source = source;
    this.browserRow.hidden = source !== 'browser';
    this.serverRow.hidden = source !== 'server';
  }

  mode() {
    return document.querySelector('input[name="upload-mode"]:checked').value;
  }

  /** The experiment the typed name already refers to, if any. */
  existing() {
    const table = this.tableInput.value.trim();
    return this.getExperiments().find((e) => e.table_name === table) || null;
  }

  /** Show Replace for a new experiment onto a taken name, and the offset for an append. */
  describeTarget() {
    const append = this.mode() === 'append';
    const taken = this.existing();
    const replaceable = !append && Boolean(taken);
    if (!replaceable) this.replaceBox.checked = false;
    this.replaceRow.hidden = !replaceable;
    if (taken) {
      this.replaceText.textContent = `Replace the existing experiment ${taken.table_name} `
        + `(${taken.status === 'ready' ? `${formatInt(taken.n_events)} events` : taken.status})`;
    }
    this.offsetRow.hidden = !append;
  }

  reset() {
    this.busy = false;
    this.progressRow.hidden = true;
    this.progressBar.style.width = '0';
    this.submit.disabled = false;
    this.submit.textContent = 'Upload & Ingest';
  }

  describeFile() {
    const file = this.fileInput.files && this.fileInput.files[0];
    if (!file) {
      const n = this.info?.schema?.n_columns;
      this.fileInfo.textContent =
        `Select an all-models inference CSV or Parquet file${n ? ` (${n} columns)` : ''}.`;
      return;
    }
    const format = formatOfName(file.name);
    const parts = [`${file.name} — ${formatBytes(file.size)}`];
    if (!format) {
      parts.push('⚠ Not a CSV or Parquet file: the server reads .csv, .txt and .parquet only.');
    } else if (this.info) {
      const factor = this.info.headroom_factors?.[format] ?? this.info.headroom_factor;
      const needed = file.size * factor;
      parts.push(
        `Ingestion needs about ${formatBytes(needed)} free; ` +
        `${formatBytes(this.info.free_bytes)} available.`
      );
      if (needed > this.info.free_bytes) {
        parts.push('⚠ Not enough free disk space on the data volume.');
      } else if (file.size >= this.info.large_upload_warn_bytes) {
        parts.push(
          '⚠ Large file: the transfer cannot resume if the connection drops. ' +
          'If this dataset is already on the server, the offline CLI avoids ' +
          'the upload entirely.'
        );
      }
    }
    this.fileInfo.innerHTML = parts.map(escapeAttribute).join('<br/>');
  }

  /** The refusal the server would make, as a sentence, or null when there is none. */
  refusal() {
    const table = this.tableInput.value.trim();
    const problem = nameProblem(table);
    if (problem) return problem;
    const mode = this.mode();
    const taken = this.existing();
    if (mode === 'append' && !taken) {
      return `Cannot append to ${table}: no experiment of that name exists. `
        + 'Use CREATE_NEW for its first file.';
    }
    if (mode === 'create_new' && taken && !this.replaceBox.checked) {
      return `An experiment named ${table} already exists. Tick Replace to overwrite it, `
        + 'or choose another name.';
    }
    const offset = Number(this.offsetInput.value || 0);
    if (mode === 'append' && (!Number.isInteger(offset) || offset < 0)) {
      return 'The event offset must be a whole number, zero or more.';
    }
    return null;
  }

  /** The request fields every route takes; call after refusal() found none. */
  fields() {
    const table = this.tableInput.value.trim();
    const mode = this.mode();
    return {
      table_name: table,
      mode,
      display_name: this.displayInput.value.trim() || table,
      event_offset: mode === 'append' ? String(Number(this.offsetInput.value || 0)) : '0',
      force_reingest: mode === 'create_new' && this.replaceBox.checked ? 'true' : 'false',
    };
  }

  async start() {
    if (this.busy) return false;
    const refused = this.refusal();
    if (refused) return this.fail(refused);
    const fields = this.fields();

    const source = document.querySelector('input[name="upload-source"]:checked').value;
    if (source === 'server') return this.startServerSide(fields);

    const file = this.fileInput.files && this.fileInput.files[0];
    if (!file) return this.fail('Choose a CSV or Parquet file to upload.');
    if (!formatOfName(file.name)) {
      return this.fail(`${file.name} is not a CSV or Parquet file.`);
    }

    const form = new FormData();
    form.append('file', file);
    for (const [key, value] of Object.entries(fields)) form.append(key, value);

    this.busy = true;
    this.submit.disabled = true;
    this.submit.textContent = 'Uploading…';
    this.progressRow.hidden = false;
    this.warning.hidden = true;

    try {
      const response = await uploadDataset(form, {
        onProgress: (fraction, loaded, total) => {
          this.progressBar.style.width = `${(fraction * 100).toFixed(1)}%`;
          this.status.textContent =
            `Uploading ${formatBytes(loaded)} of ${formatBytes(total)} ` +
            `(${(fraction * 100).toFixed(1)}%)`;
        },
      });
      this.status.textContent = 'Upload complete. Ingesting…';
      this.submit.textContent = 'Ingesting…';
      this.poll(response.job.job_id);
    } catch (error) {
      this.fail(error instanceof ApiError ? error.message : String(error));
      this.reset();
    }
  }

  /**
   * Ingest a file the server already holds.
   *
   * Nothing is transferred: only the path crosses HTTP, and the server process -
   * which owns DuckDB's single write lock - reads the file in place. This is
   * the practical route for the multi-gigabyte datasets.
   */
  async startServerSide(fields) {
    const path = this.serverSelect.value;
    if (!path) return this.fail('No server-side file selected.');

    this.busy = true;
    this.submit.disabled = true;
    this.submit.textContent = 'Ingesting…';
    this.progressRow.hidden = false;
    this.warning.hidden = true;
    this.status.textContent = 'Starting server-side ingest…';

    try {
      const payload = await postForm('/api/ingest-local', { path, ...fields });
      this.poll(payload.job.job_id);
    } catch (error) {
      this.fail(error instanceof ApiError ? error.message : String(error));
      this.reset();
    }
  }

  poll(jobId) {
    const tick = async () => {
      try {
        const job = await getJson(`/api/upload/${jobId}`, {}, `job-${jobId}`);
        this.progressBar.style.width = `${(job.progress * 100).toFixed(1)}%`;
        this.status.textContent = job.stage_label;

        if (job.status === 'done') {
          const result = job.result || {};
          const lines = [`Ingested ${formatInt(result.n_hits)} hits across `
            + `${formatInt(result.n_events)} events.`];
          // What reading the file did, such as a narrowed column: worth a look.
          for (const note of job.warnings || []) lines.push(note);
          this.status.innerHTML = lines.map(escapeAttribute).join('<br/>');
          this.progressBar.style.width = '100%';
          this.submit.textContent = 'Done';
          this.busy = false;
          this.onComplete(job);
          // Long enough to read a warning; a clean ingest closes quickly.
          setTimeout(() => this.shell.close(), (job.warnings || []).length ? 6000 : 1600);
          return;
        }
        if (job.status === 'failed') {
          this.fail(job.error || 'Ingestion failed.');
          this.reset();
          return;
        }
        this.pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
      } catch (error) {
        this.fail(error instanceof ApiError ? error.message : String(error));
        this.reset();
      }
    };
    tick();
  }

  fail(message) {
    this.warning.hidden = false;
    this.warning.classList.add('is-error');
    this.warning.textContent = message;
    setTimeout(() => this.warning.classList.remove('is-error'), 6000);
    return false;
  }
}

function escapeAttribute(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
