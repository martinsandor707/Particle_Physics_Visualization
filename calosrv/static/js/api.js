/* HTTP client.
 *
 * Two behaviours matter for interactivity beyond just calling fetch:
 *
 * Debouncing. Slider inputs fire continuously while dragging. Every request is
 * held for the debounce interval the server advertises (150 ms) so one gesture
 * produces one query instead of sixty.
 *
 * Abort on supersede. If a newer request for the same endpoint starts while an
 * older one is in flight, the older one is aborted. Without this, a slow
 * response from an earlier slider position can land after a faster later one
 * and repaint the panel with stale data - a race that shows up as the display
 * briefly flicking back to the previous selection.
 */

export const DEBOUNCE_MS = 150;

const inFlight = new Map();

function buildUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  return url;
}

export class ApiError extends Error {
  constructor(problem, status) {
    super(problem.detail || problem.title || `Request failed (${status})`);
    this.problem = problem;
    this.status = status;
  }
}

/** GET a JSON endpoint, aborting any earlier request under the same key. */
export async function getJson(path, params = {}, key = path) {
  const previous = inFlight.get(key);
  if (previous) previous.abort();

  const controller = new AbortController();
  inFlight.set(key, controller);

  let response;
  try {
    response = await fetch(buildUrl(path, params), { signal: controller.signal });
  } finally {
    if (inFlight.get(key) === controller) inFlight.delete(key);
  }

  if (!response.ok) {
    let problem = { detail: `${response.status} ${response.statusText}` };
    try {
      problem = await response.json();
    } catch {
      /* a non-JSON error body is still worth reporting by status alone */
    }
    throw new ApiError(problem, response.status);
  }
  return response.json();
}

/** Wrap a function so rapid calls collapse into one trailing invocation. */
export function debounce(fn, wait = DEBOUNCE_MS) {
  let timer = null;
  const wrapped = (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, wait);
  };
  wrapped.flush = (...args) => {
    if (timer) clearTimeout(timer);
    timer = null;
    fn(...args);
  };
  wrapped.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  return wrapped;
}

/**
 * Upload a file with progress.
 *
 * XMLHttpRequest rather than fetch: fetch still has no upload progress event,
 * and a multi-gigabyte transfer with no progress indication is indistinguishable
 * from a hung browser.
 */
export function uploadDataset(formData, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', '/api/upload');

    request.upload.addEventListener('progress', (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(event.loaded / event.total, event.loaded, event.total);
      }
    });

    request.addEventListener('load', () => {
      let body = {};
      try {
        body = JSON.parse(request.responseText);
      } catch {
        body = { detail: request.responseText || 'Malformed server response.' };
      }
      if (request.status >= 200 && request.status < 300) resolve(body);
      else reject(new ApiError(body, request.status));
    });

    request.addEventListener('error', () =>
      reject(new ApiError({ detail: 'Network error during upload.' }, 0)));
    request.addEventListener('abort', () =>
      reject(new ApiError({ detail: 'Upload cancelled.' }, 0)));

    request.send(formData);
  });
}
