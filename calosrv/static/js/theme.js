/* The light / dark theme switch.
 *
 * The theme is a per-browser convenience, kept in localStorage under
 * 'calosrv.theme' and never in state.js, the URL hash, the Admin defaults or
 * any request, exactly as the sidebar's collapsed state is (shell.js): a
 * bookmark must not carry the reader's screen preference. Every storage
 * access is in try, because a private window or blocked site data throws.
 *
 * With nothing stored the page follows the operating system, live. A click
 * switches to the other theme and stores it, except when the other theme is
 * the system's own: then the stored value is removed and the page follows
 * the system again. Clicking back to the OS theme clears the choice; that is
 * the product decision, so there is never a stored value that merely repeats
 * what the system already says and would stop following it.
 *
 * Switching is synchronous, and in this order: `data-theme` on <html>, then
 * `applyTokens(name)`, then `onChange(name)`. The CSS variables and the
 * canvases' colour tokens (the entries inject chart_panel `applyTokens`)
 * therefore change in one frame, and `onChange` repaints with the new
 * tokens already in place. `onChange` is not called at init: the boot script
 * has already set the attribute, nothing is painted yet, and the entries
 * build their charts afterwards with the right tokens.
 *
 * A leaf module: it imports nothing from the chart code. The boot script
 * (theme_boot.js) sets the attribute before first paint; `resolveTheme`
 * here must agree with it on every input.
 */

export const THEME_STORAGE_KEY = 'calosrv.theme';
export const THEMES = Object.freeze(['dark', 'light']);

const LIGHT_QUERY = '(prefers-color-scheme: light)';
const isTheme = (value) => value === 'light' || value === 'dark';

/** The stored theme, 'light' | 'dark' | null. */
export function readThemePreference(key = THEME_STORAGE_KEY) {
  try {
    const value = window.localStorage.getItem(key);
    return isTheme(value) ? value : null;
  } catch {
    // A private window or blocked storage: the page follows the system.
    return null;
  }
}

/** Stores 'light' or 'dark'; null removes the choice so the page follows the system. */
export function writeThemePreference(value, key = THEME_STORAGE_KEY) {
  try {
    const storage = window.localStorage;
    if (isTheme(value)) storage.setItem(key, value);
    else if (value === null) storage.removeItem(key);
  } catch {
    // Nothing to do: the preference is a convenience, not state.
  }
}

/** The system's theme: 'light' when it asks for light, else 'dark'. */
export function systemTheme() {
  try {
    return window.matchMedia(LIGHT_QUERY).matches ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

/** A valid stored value, else a valid system value, else 'dark'. */
export function resolveTheme(stored, system) {
  if (isTheme(stored)) return stored;
  if (isTheme(system)) return system;
  return 'dark';
}

/** The theme on <html>, normalised. */
export function currentTheme() {
  try {
    return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

function labels(theme, stored) {
  const next = theme === 'light' ? 'dark' : 'light';
  const action = `Switch to the ${next} theme`;
  const state = stored
    ? `You chose this theme here; choosing the system's theme follows the system again.`
    : `Following the system setting; choosing the system's theme follows it again.`;
  return { action, title: `${action}. ${state}` };
}

/**
 * Adopts the theme and wires the button, the system query and other tabs.
 * Returns `{ theme(), toggle(), dispose() }`.
 */
export function initTheme({ applyTokens = () => {}, onChange = () => {}, toggle } = {}) {
  const button = toggle === undefined ? document.getElementById('theme-toggle') : toggle;

  const boot = document.documentElement.dataset.theme;
  const initial = isTheme(boot) ? boot : resolveTheme(readThemePreference(), systemTheme());
  document.documentElement.dataset.theme = initial;
  applyTokens(initial);

  const relabel = () => {
    if (!button) return;
    const { action, title } = labels(currentTheme(), readThemePreference() !== null);
    button.setAttribute('aria-label', action);
    button.setAttribute('title', title);
  };
  relabel();

  const apply = (name) => {
    if (name !== currentTheme()) {
      document.documentElement.dataset.theme = name;
      applyTokens(name);
      relabel();
      onChange(name);
    } else {
      relabel();
    }
  };

  const flip = () => {
    const next = currentTheme() === 'light' ? 'dark' : 'light';
    writeThemePreference(next === systemTheme() ? null : next);
    apply(next);
  };

  let query = null;
  try {
    query = window.matchMedia(LIGHT_QUERY);
  } catch {
    query = null;
  }
  const onSystem = () => {
    if (readThemePreference() === null) apply(systemTheme());
    else relabel();
  };
  const onStorage = (event) => {
    if (event && event.key === THEME_STORAGE_KEY) apply(resolveTheme(event.newValue, systemTheme()));
  };

  if (button) button.addEventListener('click', flip);
  if (query && query.addEventListener) query.addEventListener('change', onSystem);
  if (window.addEventListener) window.addEventListener('storage', onStorage);

  return {
    theme: currentTheme,
    toggle: flip,
    dispose() {
      if (button) button.removeEventListener('click', flip);
      if (query && query.removeEventListener) query.removeEventListener('change', onSystem);
      if (window.removeEventListener) window.removeEventListener('storage', onStorage);
    },
  };
}
