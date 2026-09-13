/* Defensive DOM writers.
 *
 * Every one of these used to be a direct property assignment, which is fine
 * until markup and script disagree about what exists. That disagreement is not
 * hypothetical: the page and its scripts are separate downloads with
 * independent cache lifetimes, so a browser can hold a stale script against
 * fresh markup. When it did, the script still expected the readout spans the
 * numeric inputs had replaced and threw
 *
 *     TypeError: Cannot set properties of null (setting 'textContent')
 *
 * during initialisation - before ECharts was configured or any data fetched, so
 * the entire interface was dead with nothing on screen to explain why.
 *
 * The versioned asset URLs in `app.py` stop those two ever being mismatched
 * again. These helpers are the second line: if an element is genuinely missing,
 * one readout goes unwritten and is reported once to the console, instead of a
 * single null reference taking the dashboard down.
 */

/** Elements already reported missing, so one absent id logs once, not per frame. */
const reported = new Set();

function resolve(id) {
  const el = document.getElementById(id);
  if (!el && !reported.has(id)) {
    reported.add(id);
    console.warn(
      `[calosrv] no element with id "${id}"; skipping this update. The page `
      + 'and its scripts may be out of step - a hard reload should fix it.',
    );
  }
  return el;
}

export function setText(id, value) {
  const el = resolve(id);
  if (el) el.textContent = value;
  return el;
}

export function setHtml(id, value) {
  const el = resolve(id);
  if (el) el.innerHTML = value;
  return el;
}

export function setVal(id, value) {
  const el = resolve(id);
  if (el) el.value = value;
  return el;
}

export function setHidden(id, hidden) {
  const el = resolve(id);
  if (el) el.hidden = hidden;
  return el;
}

export function setChecked(id, checked) {
  const el = resolve(id);
  if (el) el.checked = checked;
  return el;
}

/** Ids that are absent from the document, for a one-time startup audit. */
export function missingIds(ids) {
  return ids.filter((id) => !document.getElementById(id));
}
