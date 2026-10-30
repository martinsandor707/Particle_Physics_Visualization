/* The theme, chosen before the first paint.
 *
 * The pages' colours are CSS custom properties keyed on
 * `html[data-theme]`. If the attribute were set by a module, which runs
 * after the document is parsed and the stylesheet has painted, a reader of
 * the light theme would see one frame of the dark one on every load. This
 * script sits at the top of <head>, blocking, so the attribute is in place
 * before any stylesheet is applied.
 *
 * It is a separate classic file, not an inline script, for three reasons:
 * `app.py` `_page()` stamps its URL with the build fingerprint like every
 * other asset, a test can run its real source under Node, and the three
 * pages share one copy rather than three that could drift apart.
 *
 * The choice: a stored 'light' or 'dark' wins; otherwise the system's
 * `prefers-color-scheme`; otherwise dark. Storage and matchMedia are each
 * guarded, because either may be absent or throw (a private window, blocked
 * site data). `theme.js` `resolveTheme` must give the same answer: a test
 * holds the two to one matrix.
 *
 * ES5 only, no module syntax: nothing here may fail to parse in an old
 * browser, since a syntax error would leave the page unthemed.
 */
(function () {
  var theme = 'dark';
  var stored = null;
  try {
    stored = window.localStorage.getItem('calosrv.theme');
  } catch (error) {
    stored = null;
  }
  if (stored === 'light' || stored === 'dark') {
    theme = stored;
  } else {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) theme = 'light';
    } catch (error) {
      theme = 'dark';
    }
  }
  document.documentElement.setAttribute('data-theme', theme);
})();
