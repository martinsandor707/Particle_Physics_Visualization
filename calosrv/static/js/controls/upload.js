/* The upload modal: table naming, mode selection, streaming upload, job polling.
 *
 * Large uploads are deliberately permitted - collaborators outside the
 * organisation have no shell access to the server and the browser is their only
 * route in. What they get instead of a size limit is an honest warning: a
 * browser upload cannot resume, and ingestion needs roughly three times the CSV
 * size in free disk space.
 */

import { getJson, uploadDataset, ApiError } from '../api.js';
import { formatBytes, formatInt } from '../scale.js';

const POLL_INTERVAL_MS = 1200;

export class UploadModal {
  constructor({ onComplete }) {
    this.backdrop = document.getElementById('upload-modal');
    this.tableInput = document.getElementById('upload-table');
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
    this.info = null;

    for (const input of document.querySelectorAll('input[name="upload-source"]')) {
      input.addEventListener('change', () => this.setSource(input.value));
    }

    document.getElementById('open-upload')
      .addEventListener('click', () => this.open());
    this.cancel.addEventListener('click', () => this.close());
    this.backdrop.addEventListener('click', (event) => {
      if (event.target === this.backdrop) this.close();
    });
    this.submit.addEventListener('click', () => this.start());
    this.fileInput.addEventListener('change', () => this.describeFile());
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !this.backdrop.hidden) this.close();
    });
  }

  async open() {
    this.backdrop.hidden = false;
    this.reset();
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
        : '<option value="">No CSV files found on the server</option>';
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

  close() {
    this.backdrop.hidden = true;
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  reset() {
    this.progressRow.hidden = true;
    this.progressBar.style.width = '0';
    this.submit.disabled = false;
    this.submit.textContent = 'Upload & Ingest';
  }

  describeFile() {
    const file = this.fileInput.files && this.fileInput.files[0];
    if (!file) {
      this.fileInfo.textContent = 'Select a 29-column inference CSV.';
      return;
    }
    const parts = [`${file.name} — ${formatBytes(file.size)}`];
    if (this.info) {
      const needed = file.size * this.info.headroom_factor;
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
    this.fileInfo.innerHTML = parts.join('<br/>');
  }

  async start() {
    const table = this.tableInput.value.trim();

    if (!table) return this.fail('Enter an experiment name.');
    if (!/^[a-z][a-z0-9_]{0,47}$/.test(table)) {
      return this.fail(
        'Experiment names must start with a lowercase letter and contain only ' +
        'lowercase letters, digits and underscores.'
      );
    }

    const mode = document.querySelector('input[name="upload-mode"]:checked').value;
    const source = document.querySelector('input[name="upload-source"]:checked').value;

    if (source === 'server') return this.startServerSide(table, mode);

    const file = this.fileInput.files && this.fileInput.files[0];
    if (!file) return this.fail('Choose a CSV file to upload.');

    const form = new FormData();
    form.append('file', file);
    form.append('table_name', table);
    form.append('mode', mode);
    form.append('display_name', table);

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
  async startServerSide(table, mode) {
    const path = this.serverSelect.value;
    if (!path) return this.fail('No server-side file selected.');

    this.submit.disabled = true;
    this.submit.textContent = 'Ingesting…';
    this.progressRow.hidden = false;
    this.warning.hidden = true;
    this.status.textContent = 'Starting server-side ingest…';

    const body = new URLSearchParams({
      path,
      table_name: table,
      mode,
      display_name: table,
      event_offset: '0',
    });

    try {
      const response = await fetch('/api/ingest-local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      const payload = await response.json();
      if (!response.ok) {
        this.fail(payload.detail || 'Server rejected the ingest.');
        this.reset();
        return;
      }
      this.poll(payload.job.job_id);
    } catch (error) {
      this.fail(String(error));
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
          this.status.innerHTML =
            `Ingested ${formatInt(result.n_hits)} hits across ` +
            `${formatInt(result.n_events)} events.`;
          this.progressBar.style.width = '100%';
          this.submit.textContent = 'Done';
          this.onComplete(job);
          setTimeout(() => this.close(), 1600);
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
