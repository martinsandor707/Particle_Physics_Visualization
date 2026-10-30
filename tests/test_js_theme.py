"""The theme modules (``js/theme_boot.js``, ``js/theme.js``), executed under Node.

* the boot script and ``resolveTheme`` agree on every cell of the matrix
  stored value x system setting (the boot file's real source runs in a vm
  context with a fake window);
* ``initTheme`` adopts what the boot script set, applies the tokens once,
  never calls ``onChange``, labels the button, and survives missing APIs;
* a click flips, stores only a choice that differs from the system's, applies
  in the order dataset, applyTokens, onChange, and relabels;
* an OS change is followed only while nothing is stored; a storage event for
  the key is applied, other keys are ignored; ``dispose`` removes every
  listener;
* the source: one key literal, every storage access in ``try``, no imports in
  ``theme.js``, nothing of the theme in ``state.js``.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import re

import pytest
from test_js_physics_shell import JS, NODE, _run
from test_layout_assets import _strip_comments

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
const { readFileSync } = await import('node:fs');
const vm = await import('node:vm');
const [themeUrl, bootPath] = JSON.parse(process.argv[1]);
const theme = await import(themeUrl);
const bootSource = readFileSync(bootPath, 'utf8');

// A fake browser. `stored`: undefined (nothing), a string, or 'THROW'.
// `system`: 'light' | 'dark' | 'ABSENT' | 'THROW'. `storage: false` removes localStorage.
function makeEnv({ stored, system = 'dark', storage = true, button = true } = {}) {
  const log = [];
  const store = new Map();
  if (stored !== undefined && stored !== 'THROW') store.set('calosrv.theme', stored);
  const winListeners = [];
  const mqlListeners = [];
  const env = { log, store, winListeners, mqlListeners, mql: null };
  const win = {
    addEventListener: (t, f) => winListeners.push([t, f]),
    removeEventListener: (t, f) => { const i = winListeners.findIndex((e) => e[0] === t && e[1] === f); if (i >= 0) winListeners.splice(i, 1); },
  };
  if (storage) {
    win.localStorage = {
      getItem: (k) => { if (stored === 'THROW') throw new Error('blocked'); return store.has(k) ? store.get(k) : null; },
      setItem: (k, v) => { log.push(['set', k, v]); store.set(k, String(v)); },
      removeItem: (k) => { log.push(['remove', k]); store.delete(k); },
    };
  }
  if (system === 'THROW') win.matchMedia = () => { throw new Error('no'); };
  else if (system !== 'ABSENT') {
    env.mql = { matches: system === 'light',
      addEventListener: (t, f) => mqlListeners.push([t, f]),
      removeEventListener: (t, f) => { const i = mqlListeners.findIndex((e) => e[1] === f); if (i >= 0) mqlListeners.splice(i, 1); } };
    win.matchMedia = (q) => { env.queries = (env.queries || []).concat(q); return env.mql; };
  }
  const attrs = new Map();
  const dataset = {};
  const root = { dataset, setAttribute: (k, v) => { attrs.set(k, v); if (k === 'data-theme') dataset.theme = v; } };
  const btnListeners = [];
  const btn = { attrs: {}, listeners: btnListeners,
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener: (t, f) => btnListeners.push([t, f]),
    removeEventListener: (t, f) => { const i = btnListeners.findIndex((e) => e[0] === t && e[1] === f); if (i >= 0) btnListeners.splice(i, 1); },
    click() { btnListeners.filter((e) => e[0] === 'click').forEach((e) => e[1]()); } };
  const doc = { documentElement: root, getElementById: (id) => (button && id === 'theme-toggle' ? btn : null) };
  Object.assign(env, { win, doc, root, btn, dataset });
  return env;
}
const install = (env) => { globalThis.window = env.win; globalThis.document = env.doc; };

function boot(spec) {
  const env = makeEnv(spec);
  const context = vm.createContext({ window: env.win, document: env.doc });
  vm.runInContext(bootSource, context);
  return env.dataset.theme;
}
function runtime(spec) {
  const env = makeEnv(spec);
  install(env);
  const stored = theme.readThemePreference();
  return theme.resolveTheme(stored, theme.systemTheme());
}

const out = {};

// The boot matrix.
out.matrix = [];
for (const stored of ['light', 'dark', 'garbage', undefined, 'THROW']) {
  for (const system of ['light', 'dark', 'ABSENT', 'THROW']) {
    out.matrix.push({ stored: stored === undefined ? null : stored, system, boot: boot({ stored, system }), runtime: runtime({ stored, system }) });
  }
}
{ // no localStorage at all
  out.noStorageBoot = boot({ storage: false, system: 'light' });
  out.noStorageRuntime = runtime({ storage: false, system: 'light' });
}

// resolveTheme, pure.
out.resolve = [
  theme.resolveTheme('light', 'dark'), theme.resolveTheme('dark', 'light'), theme.resolveTheme(null, 'light'),
  theme.resolveTheme('x', 'dark'), theme.resolveTheme(null, null), theme.resolveTheme(undefined, 'bogus'),
];
{ install(makeEnv({ system: 'light' })); out.queryOk = theme.systemTheme(); }
{ const e = makeEnv({ system: 'dark' }); install(e); theme.writeThemePreference('garbage'); out.garbageWrite = e.log.length; }

// A session: tokens and change recorders that look at the dataset when called.
function session(spec, opts = {}) {
  const env = makeEnv(spec);
  install(env);
  if (opts.boot !== false) env.dataset.theme = spec.boot ?? (spec.system === 'light' ? 'light' : 'dark');
  const order = [];
  const applyTokens = (n) => order.push(['tokens', n, env.dataset.theme]);
  const onChange = (n) => order.push(['change', n, env.dataset.theme]);
  const handle = theme.initTheme({ applyTokens, onChange });
  env.order = order;
  env.handle = handle;
  return env;
}
const label = (env) => ({ aria: env.btn.attrs['aria-label'], title: env.btn.attrs.title });

// init.
{
  const e = session({ system: 'dark' });
  out.initDark = { order: e.order, theme: e.dataset.theme, ...label(e), listeners: e.btn.listeners.length };
  const l = session({ system: 'light' });
  out.initLight = { order: l.order, theme: l.dataset.theme, ...label(l) };
  const s = session({ system: 'dark', stored: 'light', boot: 'light' });
  out.initStored = { theme: s.dataset.theme, ...label(s) };
  // The boot script did not run: resolve.
  const r = session({ system: 'light', stored: 'dark' }, { boot: false });
  out.initNoBoot = { theme: r.dataset.theme, order: r.order };
}
{ // no button, no matchMedia, no localStorage
  const env = makeEnv({ system: 'ABSENT', storage: false, button: false });
  install(env);
  let error = null; let h;
  try { h = theme.initTheme({}); h.toggle(); h.dispose(); } catch (e) { error = String(e); }
  out.bare = { error, theme: env.dataset.theme };
  const env2 = makeEnv({ system: 'THROW', storage: false });
  install(env2);
  try { const h2 = theme.initTheme({}); h2.toggle(); h2.dispose(); out.bare2 = null; } catch (e) { out.bare2 = String(e); }
  out.bare2theme = env2.dataset.theme;
}

// Clicks.
for (const system of ['dark', 'light']) {
  const e = session({ system });
  const before = label(e);
  e.btn.click();
  const first = { theme: e.dataset.theme, log: e.log.slice(), order: e.order.slice(1), stored: e.store.get('calosrv.theme') ?? null, ...label(e) };
  e.log.length = 0;
  e.btn.click();
  const second = { theme: e.dataset.theme, log: e.log.slice(), stored: e.store.get('calosrv.theme') ?? null, ...label(e) };
  out['click_' + system] = { before, first, second, order: e.order.slice(1) };
}
{ // handle.toggle() is the click
  const e = session({ system: 'dark' });
  e.handle.toggle();
  out.handleToggle = { theme: e.dataset.theme, now: e.handle.theme() };
}

// OS changes.
{
  const e = session({ system: 'dark' });
  e.mql.matches = true;
  e.mqlListeners.forEach((l) => l[1]({}));
  out.osFollow = { theme: e.dataset.theme, order: e.order.slice(1), stored: e.store.size };
  const s = session({ system: 'dark', stored: 'dark', boot: 'dark' });
  s.mql.matches = true;
  s.mqlListeners.forEach((l) => l[1]({}));
  out.osIgnored = { theme: s.dataset.theme, order: s.order.slice(1) };
}

// Blocked storage: the page keeps the reader's click while it is open.
{
  const e = session({ system: 'light', storage: false });
  const before = label(e).title;
  e.btn.click();                                   // to dark, which this browser cannot store
  const chose = { theme: e.dataset.theme, title: label(e).title };
  const flip = (light) => { e.mql.matches = light; e.mqlListeners.forEach((l) => l[1]({})); };
  flip(false); flip(true);                         // the OS goes dark, then light again
  const afterFlips = e.dataset.theme;
  e.btn.click();                                   // back onto the OS's light: follow it again
  flip(false);
  out.blocked = { before, chose, afterFlips, followsAgain: e.dataset.theme, writes: e.log.length };
}

// Storage events.
{
  const e = session({ system: 'dark' });
  const fire = (ev) => e.winListeners.filter((l) => l[0] === 'storage').forEach((l) => l[1](ev));
  fire({ key: 'calosrv.sidebar', newValue: 'light' });
  const other = e.dataset.theme;
  fire({ key: 'calosrv.theme', newValue: 'light' });
  const light = e.dataset.theme;
  fire({ key: 'calosrv.theme', newValue: null });          // removed elsewhere: the system's dark
  const cleared = e.dataset.theme;
  e.mql.matches = true;
  fire({ key: 'calosrv.theme', newValue: 'garbage' });     // invalid: the system's light
  out.storageEvent = { other, light, cleared, garbage: e.dataset.theme, changes: e.order.filter((o) => o[0] === 'change').length };
}

// dispose.
{
  const e = session({ system: 'dark' });
  const had = [e.btn.listeners.length, e.winListeners.length, e.mqlListeners.length];
  e.handle.dispose();
  out.dispose = { had, left: [e.btn.listeners.length, e.winListeners.length, e.mqlListeners.length] };
  e.btn.click();
  out.afterDispose = e.dataset.theme;
}

// The default button is #theme-toggle; an explicit null means none.
{
  const env = makeEnv({ system: 'dark' });
  install(env);
  env.dataset.theme = 'dark';
  theme.initTheme({ toggle: null });
  out.nullToggle = env.btn.listeners.length;
}
out.exports = [theme.THEME_STORAGE_KEY, [...theme.THEMES]];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    return _run(_SCRIPT, [(JS / "theme.js").as_uri(), str(JS / "theme_boot.js")])


def _expected(stored, system):
    if stored in ("light", "dark"):
        return stored
    return "light" if system == "light" else "dark"


def test_boot_and_runtime_agree_on_the_whole_matrix(out):
    assert len(out["matrix"]) == 20
    for cell in out["matrix"]:
        want = _expected(cell["stored"], cell["system"])
        assert cell["boot"] == want, cell
        assert cell["runtime"] == want, cell
    assert out["noStorageBoot"] == out["noStorageRuntime"] == "light"


def test_resolve_theme_is_pure_and_total(out):
    assert out["resolve"] == ["light", "dark", "light", "dark", "dark", "dark"]
    assert out["queryOk"] == "light"
    assert out["garbageWrite"] == 0
    assert out["exports"] == ["calosrv.theme", ["dark", "light"]]


def test_init_adopts_the_boot_theme_and_never_calls_on_change(out):
    dark = out["initDark"]
    assert dark["theme"] == "dark" and dark["order"] == [["tokens", "dark", "dark"]]
    assert dark["aria"] == "Switch to the light theme"
    assert dark["listeners"] == 1
    light = out["initLight"]
    assert light["theme"] == "light" and light["order"] == [["tokens", "light", "light"]]
    assert light["aria"] == "Switch to the dark theme"
    assert out["initStored"]["theme"] == "light" and out["initStored"]["aria"] == "Switch to the dark theme"
    assert out["initNoBoot"] == {"theme": "dark", "order": [["tokens", "dark", "dark"]]}


def test_titles_say_what_the_page_follows_and_what_a_click_does(out):
    # Following a dark OS: a click to light is a choice, and it is kept.
    assert out["initDark"]["title"] == (
        "Switch to the light theme. The page follows your system's dark setting. "
        "The choice is kept in this browser.")
    # Light chosen over a dark OS: a click to dark lands on the OS's theme.
    assert out["initStored"]["title"] == (
        "Switch to the dark theme. The light theme was chosen here. "
        "That is your system's setting, so the page will follow the system again.")
    assert out["initDark"]["aria"] == "Switch to the light theme" and "." not in out["initDark"]["aria"]


def test_init_survives_missing_apis(out):
    # init, then one toggle: dark -> light, with nothing to store it in.
    assert out["bare"] == {"error": None, "theme": "light"}
    assert out["bare2"] is None and out["bare2theme"] == "light"
    assert out["nullToggle"] == 0


def test_click_flips_and_stores_only_a_choice_that_differs_from_the_system(out):
    dark_os = out["click_dark"]
    assert dark_os["first"]["theme"] == "light"
    assert dark_os["first"]["log"] == [["set", "calosrv.theme", "light"]]
    assert dark_os["first"]["stored"] == "light"
    # Back to the OS theme: the choice is removed, the page follows the system again.
    assert dark_os["second"]["theme"] == "dark"
    assert dark_os["second"]["log"] == [["remove", "calosrv.theme"]]
    assert dark_os["second"]["stored"] is None

    light_os = out["click_light"]
    assert light_os["first"]["theme"] == "dark"
    assert light_os["first"]["log"] == [["set", "calosrv.theme", "dark"]]
    assert light_os["second"]["theme"] == "light"
    assert light_os["second"]["log"] == [["remove", "calosrv.theme"]]
    assert light_os["second"]["stored"] is None


def test_click_applies_in_order_once_and_relabels(out):
    for system, nxt in (("dark", "light"), ("light", "dark")):
        click = out[f"click_{system}"]
        # tokens and change each ran once, and saw the dataset already switched.
        assert click["first"]["order"] == [["tokens", nxt, nxt], ["change", nxt, nxt]]
        assert click["order"][-2:] == [["tokens", system, system], ["change", system, system]]
        assert len(click["order"]) == 4
        assert click["before"]["aria"] == f"Switch to the {nxt} theme"
        assert click["first"]["aria"] == f"Switch to the {system} theme"
        assert click["second"]["aria"] == f"Switch to the {nxt} theme"
        assert "was chosen here. That is your system's setting" in click["first"]["title"]
        assert f"follows your system's {system} setting. The choice is kept" in click["second"]["title"]
    assert out["handleToggle"] == {"theme": "light", "now": "light"}


def test_an_os_change_is_followed_only_while_nothing_is_stored(out):
    assert out["osFollow"]["theme"] == "light"
    assert out["osFollow"]["order"] == [["tokens", "light", "light"], ["change", "light", "light"]]
    assert out["osFollow"]["stored"] == 0
    assert out["osIgnored"] == {"theme": "dark", "order": []}


def test_a_blocked_storage_keeps_the_click_while_the_page_is_open(out):
    """Where the browser stores nothing, the title must not promise a kept
    choice, and an OS change must not undo the reader's click."""
    blocked = out["blocked"]
    assert blocked["before"].endswith("This browser keeps no choice, so it lasts while this page is open.")
    assert blocked["chose"]["theme"] == "dark"
    assert "The dark theme was chosen here." in blocked["chose"]["title"]
    assert blocked["afterFlips"] == "dark"
    # A click back onto the OS's own theme follows the system again.
    assert blocked["followsAgain"] == "dark"
    assert blocked["writes"] == 0


def test_a_storage_event_for_the_key_is_applied_and_others_are_ignored(out):
    event = out["storageEvent"]
    assert event["other"] == "dark"
    assert event["light"] == "light"
    assert event["cleared"] == "dark"
    assert event["garbage"] == "light"
    assert event["changes"] == 3


def test_dispose_removes_every_listener(out):
    assert out["dispose"]["had"] == [1, 1, 1]
    assert out["dispose"]["left"] == [0, 0, 0]
    assert out["afterDispose"] == "dark"


# ------------------------------------------------------------- the source --


def _source(name: str) -> str:
    return _strip_comments((JS / name).read_text(encoding="utf-8"))


def test_the_key_literal_is_in_both_files():
    assert "'calosrv.theme'" in _source("theme_boot.js")
    assert "'calosrv.theme'" in _source("theme.js")


@pytest.mark.parametrize("name", ["theme_boot.js", "theme.js"])
def test_every_storage_access_is_guarded(name):
    source = _source(name)
    uses = list(re.finditer(r"localStorage", source))
    assert uses
    for match in uses:
        assert "try {" in source[max(0, match.start() - 80):match.start()], (name, match.start())
    for match in re.finditer(r"matchMedia", source):
        assert "try {" in source[max(0, match.start() - 120):match.start()] or "typeof" in source[match.start() - 40:match.start()], name


def test_theme_js_is_a_leaf_and_the_boot_script_is_classic():
    theme = _source("theme.js")
    assert not re.search(r"^\s*import\b|\bimport\s*\(", theme, flags=re.MULTILINE)
    boot = _source("theme_boot.js")
    assert not re.search(r"\b(import|export|const|let)\b|=>|`", boot), "ES5 only, no module syntax"
    assert boot.lstrip().startswith("(function")


def test_the_theme_is_never_part_of_the_stored_view():
    assert "calosrv.theme" not in (JS / "state.js").read_text(encoding="utf-8")
