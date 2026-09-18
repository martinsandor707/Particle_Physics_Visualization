/* Hand a Blob to the browser as a file.
 *
 * The object URL is revoked on a later task rather than immediately: Firefox
 * resolves the download asynchronously after the synthetic click, and revoking
 * in the same tick races it and produces an empty file. The same caveat is
 * recorded against the CSV export in the batch dashboard.
 */

/** Delay before the object URL is released, in milliseconds. */
const REVOKE_DELAY_MS = 2000;

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
}

/**
 * Decode a `data:` URL into a Blob.
 *
 * ECharts returns a data URL, and handing a multi-megabyte one straight to an
 * anchor's href is unreliable - some browsers cap it, and the whole string sits
 * in the DOM. Converting to a Blob keeps the payload out of the markup.
 */
export function dataUrlToBlob(dataUrl) {
  const [header, data] = String(dataUrl).split(',', 2);
  const type = (/data:([^;,]+)/.exec(header) || [])[1] || 'application/octet-stream';
  if (!/;base64/.test(header)) {
    return new Blob([decodeURIComponent(data)], { type });
  }
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type });
}
