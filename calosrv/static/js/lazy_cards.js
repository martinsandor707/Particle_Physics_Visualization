/* Load a card when it scrolls into view, and again only when its request changes.
 *
 * The physics section sits below the 2 x 2 diagnostic and holds up to nine
 * cards, three of them hit-level scans. Asking for all of them at boot, and on
 * every slider release, would multiply the server's work for cards nobody has
 * scrolled to. So each card is watched by one IntersectionObserver over the
 * page's scroll container (`.main`, rootMargin '0px': in view means in view)
 * and loads the first time it is visible. The margin is the plan's decision
 * D3 (Martin): no card is asked for before the reader can see it, at the
 * cost of an empty plot for the length of a cold query.
 *
 * A card's *key* is its request - route and parameters - as canonical JSON
 * (`requestKey`). A card is stale when its key differs from the key it last
 * loaded; `refresh()` loads the visible stale cards, and a stale card out of
 * view loads when it scrolls in. A palette change changes no key, so it is a
 * repaint (the caller's), never a request. A key of null means the card does
 * not apply and is never loaded.
 *
 * A load the server refused (`isRefusal`: a 4xx, the 422 capability refusal
 * in particular) counts as loaded for its key: the card shows the server's
 * reason, and asking again for the same request would only repeat it. Any
 * other failure - the network, a 5xx - may pass, so it does not: the card
 * shows its error and the next visibility, `refresh()` or key change asks
 * again. An aborted load (superseded by a newer key) never counts.
 * `forget()` makes every card stale, for an experiment change.
 *
 * Without IntersectionObserver every card counts as visible: correct, merely
 * no longer lazy.
 */

/**
 * Whether a card should load now.
 *
 * Pure: visible, applicable, not already loading this key, and not already
 * holding it.
 */
export function shouldLoad({ visible, key, loadedKey = null, pendingKey = null }) {
  if (!visible || key === null || key === undefined) return false;
  if (key === pendingKey) return false;
  return key !== loadedKey;
}

/**
 * Whether a failed load is the server's deliberate answer to its request - a
 * refusal (a 4xx; the 422 a shut capability gate raises in particular) - that
 * a second identical request would only repeat. A network failure, a 5xx, a
 * 408 or a 429 may pass on its own and is not. Duck-typed on the error's HTTP
 * status (api.js `ApiError`), so this module imports nothing.
 */
export function isRefusal(error) {
  const status = Number(error?.status);
  return status >= 400 && status < 500 && status !== 408 && status !== 429;
}

/**
 * A request as canonical JSON: the route, then the parameters in sorted key
 * order, without the empty values the HTTP client drops (null, undefined,
 * ''). Two cards asking for the same response build the same key.
 */
export function requestKey(route, params = {}) {
  const kept = Object.keys(params).sort()
    .filter((k) => params[k] !== null && params[k] !== undefined && params[k] !== '')
    .map((k) => [k, params[k]]);
  return JSON.stringify([route, kept]);
}

export class LazyCards {
  /**
   * @param {{root?: Element|null, rootMargin?: string, onError?: Function}} options
   *   `root` is the scroll container the cards scroll in (`.main`);
   *   `onError(error, element)` hears of a load that scrolling started, which
   *   no caller awaits (a superseded one is not reported).
   */
  constructor({ root = null, rootMargin = '0px', onError = null } = {}) {
    this.entries = new Map(); // element -> entry
    this.onError = onError;
    this.observer = typeof IntersectionObserver === 'function'
      ? new IntersectionObserver((records) => this.onIntersect(records), { root, rootMargin, threshold: 0 })
      : null;
  }

  /**
   * Watch one card. `key()` returns its current request key, or null when the
   * card does not apply; `load(key)` performs the load and settles when it is
   * drawn (or has failed).
   */
  watch(element, { key, load }) {
    const entry = {
      element, key, load,
      visible: this.observer === null,
      loadedKey: null,
      pendingKey: null,
      promise: null,
      token: null,
    };
    this.entries.set(element, entry);
    this.observer?.observe(element);
    return entry;
  }

  onIntersect(records) {
    for (const record of records) {
      const entry = this.entries.get(record.target);
      if (!entry) continue;
      entry.visible = record.isIntersecting;
      if (!entry.visible) continue;
      this.check(entry)?.catch((error) => {
        if (error?.name !== 'AbortError' && typeof this.onError === 'function') this.onError(error, entry.element);
      });
    }
  }

  /** Whether a watched card is in view now. */
  isVisible(element) {
    return Boolean(this.entries.get(element)?.visible);
  }

  /** Whether a watched card holds the response for its current key. */
  isCurrent(element) {
    const entry = this.entries.get(element);
    return Boolean(entry) && entry.loadedKey !== null && entry.loadedKey === entry.key();
  }

  /** Load one card if it should; returns the load's promise, or null. */
  check(entry) {
    const key = entry.key();
    if (!shouldLoad({ visible: entry.visible, key, loadedKey: entry.loadedKey, pendingKey: entry.pendingKey })) {
      return entry.pendingKey !== null && entry.pendingKey === key ? entry.promise : null;
    }
    // A load is current while it is the entry's latest: a newer key, or a
    // `forget()`, supersedes it, and its result then marks nothing.
    const token = {};
    entry.token = token;
    entry.pendingKey = key;
    const current = () => entry.token === token;
    const promise = (async () => {
      try {
        await entry.load(key);
        if (current()) entry.loadedKey = key;
      } catch (error) {
        // A refusal is loaded for its key; a superseded request or a fault
        // that may pass (network, 5xx) is not, so the card is asked again.
        if (error?.name !== 'AbortError' && current() && isRefusal(error)) entry.loadedKey = key;
        throw error;
      } finally {
        if (current()) {
          entry.pendingKey = null;
          entry.token = null;
        }
      }
    })();
    entry.promise = promise;
    return promise;
  }

  /**
   * Load every visible stale card. Settles when all of them have; the result
   * is `Promise.allSettled`'s, one record per load started, each carrying the
   * card's element.
   */
  async refresh() {
    const started = [];
    for (const entry of this.entries.values()) {
      const promise = this.check(entry);
      if (promise) started.push([entry.element, promise]);
    }
    const results = await Promise.allSettled(started.map(([, promise]) => promise));
    return results.map((result, index) => ({ ...result, element: started[index][0] }));
  }

  /**
   * Every card stale: an experiment change, or the plan of one that changed.
   *
   * Visibility is measured again too: a new plan shows and hides cards and
   * moves the rest, so a card that was in view under the last plan may not be
   * now. Each card is observed afresh, and the observer reports where it is
   * (asynchronously, as it does on the first observe); until it does, no card
   * counts as visible.
   */
  forget() {
    for (const entry of this.entries.values()) {
      entry.loadedKey = null;
      entry.pendingKey = null;
      entry.promise = null;
      entry.token = null;
      if (this.observer) {
        entry.visible = false;
        this.observer.unobserve(entry.element);
        this.observer.observe(entry.element);
      }
    }
  }

  /** Mark one card stale without forgetting the others (its own controls changed). */
  invalidate(element) {
    const entry = this.entries.get(element);
    if (entry) entry.loadedKey = null;
  }

  disconnect() {
    this.observer?.disconnect();
  }
}
