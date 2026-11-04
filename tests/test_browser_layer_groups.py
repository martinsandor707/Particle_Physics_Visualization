"""The Longitudinal Channels (layer groups) and the Z depth label, in Chromium.

Brief section 8.1 of data/dev/design/layer-groups/brief.md, driven on the
``physics_live_server`` experiments (the two-shower demonstration, whose
lattice has L = 56 layers, the single-shower hits and the event-level
aggregate, which serves no projections). What a reader meets is checked:

1. **The sidebar group** sits after the display-mode group on the Physics
   page and after the frame group on the Models page, is hidden where the
   experiment serves no projections, draws a 13-segment mini bar, and
   disables Pooled, with its reason, on the Models page and in Local.
2. **The modal** opens from Edit Channels…, keeps Tab inside, closes on
   Escape with the focus returned; the arrow keys move a seam one layer and
   stop at a neighbour, the clamp announced; a pointer drag snaps to whole
   seams; End of Ch m and Start of Ch m+1 are one boundary; the shorthand
   takes ranges and counts and shows its error; the presets apply; Apply
   writes ``lgmode=bounds&lgroups=…`` and Uniform writes no ``lgroups``;
   Cancel restores; the dialog fits a 1024 x 700 viewport.
3. **Boundaries** draw 13 strip segments in the band above the YZ and XZ
   plots and 12 seams across them, with no ``/api/`` request for a mode
   change, an edit, a draft or a theme switch; hovering a segment fills
   both panels' spotlight and its tooltip names the channel, its layers,
   its depth span and its energy share; the raster readout ends in
   ``layer k · Ch m [a–b]``.
4. **Pooled** asks exactly one ``/api/projections`` with ``depth_groups``,
   three with the compare grid open (the 2 x 2, Absolute and per-shower
   translated; never Local), and the YZ / XZ raster then has 13 depth
   bins; in Local nothing is asked and the badge shows.
5. **The Z axis**: the Absolute YZ axis is titled ``Z = z − 3649 — depth
   [mm]`` with ``0`` as its first labelled tick, and the D-frame keeps z′.
6. **The Event Inspector**: Local draws the tilted planes on u–w and the
   badge on v–w; the lab and per-shower translated rows draw seams.
7. **The Models page**: the paired projections draw the boundaries beside
   the slice bracket, and no Models request carries ``depth_groups``.
8. **Both themes**: the overlays take the new tokens on a switch, with no
   request; screenshots of the 2 x 2 with Boundaries, the pooled 2 x 2, the
   modal, an inspector row and a Models pair are saved in dark and light to
   ``data/dev/design/layer-groups/screens/`` of the main tree.
10. **Timing**: a Boundaries repaint (every depth panel's ``setLayerGroups``
   and its notes) is measured in the browser against the 50 ms budget.

Item 9 (layout) lives in test_browser_layout.py; the new tooltips' 20 % cap
in test_browser_tooltip.py.

Opt-in (``CALOSRV_BROWSER_TESTS=1``): it needs Playwright's Chromium.
"""

from __future__ import annotations

import json
import os
import re
import statistics
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from conftest import BASELINE_TABLE, SINGLE_EVENTS_TABLE

pytestmark = pytest.mark.skipif(
    os.environ.get("CALOSRV_BROWSER_TESTS") != "1",
    reason="set CALOSRV_BROWSER_TESTS=1 to run the Chromium Longitudinal Channels check",
)

#: The main tree's screenshot folder (brief 8.1 item 8), resolved from this worktree or the main tree.
_ROOT = Path(__file__).resolve().parents[1]
_MAIN = _ROOT.parents[2] if _ROOT.parent.name == "dev" and _ROOT.parents[1].name == "data" else _ROOT
SCREENS = _MAIN / "data" / "dev" / "design" / "layer-groups" / "screens"

#: SwiftShader's software WebGL (test_browser_models.py).
GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
GROUPS = 13
DEPTH = ("plot-yz", "plot-xz")
#: controls/layer_groups_control.js POOL_REASONS.
POOL_REASON = {
    "models": "Pooling re-bins the Physics page’s ensemble panels; this page draws boundaries.",
    "local": "Local: detector layers tilt by each shower’s (θ, φ); there is no common layer grid to pool.",
}
#: The repaint budget of CLAUDE.md §3 (client-side UI latency).
BUDGET_MS = 50.0

# ------------------------------------------------------------------ probes --

#: A depth panel's Longitudinal Channels as its option states them.
_LG = """(plotId) => {
  const host = document.getElementById(plotId);
  const inst = host && echarts.getInstanceByDom(host);
  if (!inst) return null;
  const option = inst.getOption();
  const rect = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
  const series = option.series || [];
  const byId = (id) => series.find((s) => s.id === id) || null;
  const len = (id) => { const s = byId(id); return s ? (s.data || []).length : null; };
  const walk = (items) => (items || []).flatMap((g) => (g ? [g, ...walk(g.elements || g.children)] : []));
  const badge = walk(option.graphic).find((g) => g.id === 'layer-groups-badge');
  const box = host.getBoundingClientRect();
  return {
    grid: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
    host: { left: box.left, top: box.top, width: box.width, height: box.height },
    strip: len('layer-groups-strip'), seams: len('layer-groups-seams'), spot: len('layer-groups-spot'),
    planes: len('layer-groups-planes'),
    stripData: byId('layer-groups-strip')?.data ?? [],
    seamAt: (byId('layer-groups-seams')?.data ?? []).map((d) => d[0]),
    badge: badge ? (badge.style?.text ?? null) : null,
    slab: series.filter((s) => String(s.name || '').startsWith('Depth slice drawn in 3-D')).length,
    xName: option.xAxis?.[0]?.name ?? null,
    yName: option.yAxis?.[0]?.name ?? null,
  };
}"""

#: What the depth panel's zrender display list holds in the channel tokens of `t`:
#: the strip's rectangles (with their fill: a, b or hot), the seams (dashed), the
#: spotlight's faces (solid), the strip's edge ticks and its labels; in viewport px.
_DRAWN = """([plotId, t]) => {
  const host = document.getElementById(plotId);
  const inst = echarts.getInstanceByDom(host);
  const box = host.getBoundingClientRect();
  const out = { rects: [], seams: [], spots: [], edges: 0, texts: [] };
  const fills = { [t.groupStripFillA]: 'a', [t.groupStripFillB]: 'b', [t.groupStripHot]: 'hot' };
  for (const e of inst.getZr().storage.getDisplayList()) {
    const s = e.style || {};
    const r = e.getBoundingRect().clone();
    if (e.transform) r.applyTransform(e.transform);
    const g = { x: r.x, y: r.y, w: r.width, h: r.height, mx: r.x + r.width / 2,
                cx: box.left + r.x + r.width / 2, cy: box.top + r.y + r.height / 2 };
    const dashed = Array.isArray(s.lineDash) && s.lineDash.length > 0;
    if (e.type === 'rect' && fills[s.fill]) out.rects.push({ ...g, fill: fills[s.fill] });
    // The segment under the pointer, in ECharts' own hover (emphasis) state: its fill as drawn.
    else if (e.type === 'rect' && (e.currentStates || []).includes('emphasis')) {
      out.rects.push({ ...g, fill: 'emphasis', raw: String(s.fill) });
    }
    else if (e.type === 'polyline' && s.stroke === t.groupSeam && dashed) out.seams.push(g);
    else if (e.type === 'polyline' && s.stroke === t.groupSpot && !dashed && s.lineWidth > t.lineAxis) out.spots.push(g);
    else if (e.type === 'polyline' && s.stroke === t.groupStripEdge && !dashed) out.edges += 1;
    else if ((e.type === 'text' || e.type === 'tspan') && s.fill === t.groupStripText
             && /^(Rel )?(Ch )?\\d+$/.test(String(s.text))) out.texts.push(String(s.text));
  }
  out.rects.sort((a, b) => a.x - b.x);
  out.seams.sort((a, b) => a.x - b.x);
  return out;
}"""

#: The screen tokens of both themes (scale.js SCREEN_THEMES), and the theme in force.
_TOKENS = """async () => {
  const m = await import(`/static/js/scale.js${new URL(document.querySelector('script[type="module"]').src).search}`);
  return { dark: { ...m.SCREEN_THEMES.dark }, light: { ...m.SCREEN_THEMES.light },
           theme: document.documentElement.dataset.theme ?? null };
}"""

#: The text of the last visible tooltip, or null.
_TIP = """() => {
  const tips = [...document.querySelectorAll('.calo-tooltip')].filter((t) => {
    const cs = getComputedStyle(t);
    const b = t.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) > 0.5
      && b.width > 0 && b.height > 0 && t.innerText.trim().length > 0;
  });
  return tips.length ? tips[tips.length - 1].innerText.trim() : null;
}"""

#: The depth axis's drawn tick labels and title.
_DEPTH_AXIS = """(plotId) => {
  const inst = echarts.getInstanceByDom(document.getElementById(plotId));
  const axis = inst.getModel().getComponent('xAxis', 0).axis;
  return { name: inst.getOption().xAxis[0].name,
           labels: axis.getViewLabels().map((l) => String(l.formattedLabel ?? '')) };
}"""

#: The sidebar group and its neighbours, its mini bar and the Pooled radio.
_SIDEBAR = """() => {
  const group = document.getElementById('group-lgroups');
  const pool = document.getElementById('lgmode-pool');
  const label = document.getElementById('lgmode-pool-label');
  const notice = document.getElementById('lgroups-notice');
  const sibling = (el, dir) => { let s = el; do { s = s[dir]; } while (s && !s.classList.contains('sidebar-group')); return s?.id ?? null; };
  return {
    hidden: group.hidden, shown: !group.hidden && group.offsetParent !== null,
    reason: group.dataset.reason ?? null,
    before: sibling(group, 'previousElementSibling'), after: sibling(group, 'nextElementSibling'),
    segments: [...document.querySelectorAll('#lgroups-bar .lg-bar-seg')].map((s) => ({
      title: s.title, grow: Number(s.style.flexGrow), alt: s.classList.contains('is-alt') })),
    summary: document.getElementById('lgroups-summary').textContent.trim(),
    poolDisabled: pool.disabled, poolChecked: pool.checked,
    poolTitle: label.getAttribute('title'), poolLabelDisabled: label.classList.contains('is-disabled'),
    notice: notice.hidden ? null : notice.textContent.trim(),
    mode: document.querySelector('input[name="lgmode"]:checked')?.value ?? null,
  };
}"""

#: The modal's draft as its table shows it, its handles, its live region and its focus.
_MODAL = """() => {
  const modal = document.getElementById('lgroups-modal');
  const rows = [...document.querySelectorAll('#lgroups-rows tr')].map((tr) => ({
    name: tr.children[0].textContent.trim(),
    start: Number(tr.querySelector('.lg-start input').value),
    end: Number(tr.querySelector('.lg-end input').value),
    n: Number(tr.querySelector('.lg-num').textContent),
    startLocked: tr.querySelector('.lg-start input').disabled,
    endLocked: tr.querySelector('.lg-end input').disabled,
  }));
  const ribbon = document.getElementById('lgroups-ribbon').getBoundingClientRect();
  const handles = [...document.querySelectorAll('#lgroups-ribbon .lg-handle')].map((h) => {
    const b = h.getBoundingClientRect();
    return { now: Number(h.getAttribute('aria-valuenow')), min: Number(h.getAttribute('aria-valuemin')),
             max: Number(h.getAttribute('aria-valuemax')), text: h.getAttribute('aria-valuetext'),
             label: h.getAttribute('aria-label'), role: h.getAttribute('role'),
             cx: b.left + b.width / 2, cy: b.top + b.height / 2, w: b.width, h: b.height };
  });
  const box = modal.querySelector('.lg-modal').getBoundingClientRect();
  const active = document.activeElement;
  const pressed = [...document.querySelectorAll('#lgroups-presets [data-preset]')]
    .filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.preset);
  const error = document.getElementById('lgroups-shorthand-error');
  return {
    open: !modal.hidden, rows, handles, pressed,
    ribbon: { left: ribbon.left, width: ribbon.width, top: ribbon.top, height: ribbon.height },
    cells: document.querySelectorAll('#lgroups-ribbon .lg-cell').length,
    live: document.getElementById('lgroups-live').textContent.trim(),
    error: error.hidden ? null : error.textContent.trim(),
    shorthand: document.getElementById('lgroups-shorthand').value,
    box: { left: box.left, top: box.top, right: box.right, bottom: box.bottom },
    viewport: [document.documentElement.clientWidth, document.documentElement.clientHeight],
    scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
    focusInside: Boolean(active && modal.contains(active)),
    focusId: active?.id || null,
    focusClass: active?.className || null,
  };
}"""

#: The engine's presets for L (layer_groups.js), from the module the page itself loaded.
_PRESETS = """async (L) => {
  const m = await import(`/static/js/layer_groups.js${new URL(document.querySelector('script[type="module"]').src).search}`);
  return Object.fromEntries(m.PRESET_KEYS.map((k) => [k, m.presetCounts(k, L)]));
}"""

#: Time a Boundaries repaint: Off -> Boundaries through the radio, `n` times, with every
#: ProjectionPanel.setLayerGroups call timed (the module instance the page loaded).
_TIME_REPAINT = """async (n) => {
  const { ProjectionPanel } = await import(`/static/js/panels/projection.js${new URL(document.querySelector('script[type="module"]').src).search}`);
  const proto = ProjectionPanel.prototype;
  if (!proto.__lgTimed) {
    const original = proto.setLayerGroups;
    proto.setLayerGroups = function (spec) {
      const t = performance.now();
      const result = original.call(this, spec);
      (window.__lgCalls ??= []).push(performance.now() - t);
      return result;
    };
    proto.__lgTimed = true;
  }
  const radio = (m) => document.getElementById(`lgmode-${m}`);
  const pick = (m) => { const r = radio(m); r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); };
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const out = [];
  for (let i = 0; i < n; i += 1) {
    pick('off');
    await frame();
    window.__lgCalls = [];
    const t0 = performance.now();
    pick('bounds');
    const sync = performance.now() - t0;
    const calls = [...window.__lgCalls];
    await frame();
    out.push({ sync, painted: performance.now() - t0, calls });
  }
  return out;
}"""


# ----------------------------------------------------------------- helpers --


def _open(p, base, *, path="/", table=BASELINE_TABLE, fragment="", viewport=(1600, 900), gl=False, browser=None):
    """A page on `table`, its console errors, page errors and failed requests, and every /api/ request."""
    browser = browser or p.chromium.launch(args=GL_ARGS if gl else [])
    page = browser.new_page(color_scheme="dark", viewport={"width": viewport[0], "height": viewport[1]})
    problems, requests = [], []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    page.on("request", lambda r: requests.append(r.url) if "/api/" in r.url else None)
    page.goto(f"{base}{path}#table_name={table}{fragment}")
    page.wait_for_function(
        "(table) => document.getElementById('experiment-select')?.value === table "
        "&& (!document.getElementById('stat-kind') || document.getElementById('stat-kind').textContent.trim() !== '—')",
        arg=table, timeout=30_000,
    )
    if path == "/":
        page.wait_for_function("() => document.getElementById('stat-events').textContent !== '—'", timeout=30_000)
    _quiet(page, requests)
    return browser, page, problems, requests


def _quiet(page, requests, settle_ms=700, rounds=40):
    """Wait until no /api/ request has been sent for `settle_ms` (the lazy and debounced cards settle)."""
    for _ in range(rounds):
        n = len(requests)
        page.wait_for_timeout(settle_ms)
        if len(requests) == n:
            return
    raise AssertionError(f"the page kept asking: {requests[-5:]}")


def _query(url):
    parsed = urlparse(url)
    return parsed.path, {k: v[0] for k, v in parse_qs(parsed.query).items()}


def _projections(requests):
    return [q for path, q in map(_query, requests) if path == "/api/projections"]


def _frame_of(q):
    """The frame a projections request asks: the D-frame by `frame`, else `coord_system`."""
    return "canonical" if q.get("frame") == "canonical" else q.get("coord_system", "lab")


def _hash(page):
    return {k: v[0] for k, v in parse_qs(page.evaluate("() => location.hash.slice(1)")).items()}


def _lg(page, plot_id):
    return page.evaluate(_LG, plot_id)


def _tokens(page):
    return page.evaluate(_TOKENS)


def _drawn(page, plot_id, theme=None):
    tokens = _tokens(page)
    return page.evaluate(_DRAWN, [plot_id, tokens[theme or tokens["theme"] or "dark"]])


def _mode(page, mode):
    page.check(f"#lgmode-{mode}")


def _wait_strip(page, plot_ids, n=GROUPS):
    page.wait_for_function(
        "([ids, n]) => ids.every((id) => { const i = echarts.getInstanceByDom(document.getElementById(id));"
        " const s = i && (i.getOption().series || []).find((x) => x.id === 'layer-groups-strip');"
        " return s && s.data.length === n; })",
        arg=[list(plot_ids), n], timeout=30_000,
    )


def _experiment(base, table=BASELINE_TABLE):
    listed = httpx.get(f"{base}/api/experiments", timeout=30).json()["experiments"]
    return next(e for e in listed if e["table_name"] == table)


def _layers(base, table=BASELINE_TABLE) -> int:
    return int(_experiment(base, table)["lattice"]["z"]["n"])


def _uniform(L):
    q, r = divmod(L, GROUPS)
    return [q + 1] * r + [q] * (GROUPS - r)


def _bounds(counts):
    out, total = [], 0
    for c in counts:
        total += c
        out.append(total)
    return out


def _hover(page, x, y):
    page.mouse.move(x - 3, y - 2)
    page.mouse.move(x, y, steps=3)
    page.wait_for_timeout(120)
    return page.evaluate(_TIP)


def _readouts(page, plot_id, want=4, columns=23, rows=9):
    """Sweep the plot until `want` bin readouts showed (an empty lab bin shows none, a seam its
    own explanation); their first lines."""
    lg = _lg(page, plot_id)
    g, h = lg["grid"], lg["host"]
    found = []
    for j in range(rows):
        for i in range(columns):
            x = h["left"] + g["x"] + (i + 0.5) / columns * g["w"]
            y = h["top"] + g["y"] + (j + 0.5) / rows * g["h"]
            page.mouse.move(x, y)
            page.wait_for_timeout(40)
            tip = page.evaluate(_TIP)
            if tip and not tip.startswith(("Seam ", "Layer plane ")):
                line = tip.splitlines()[0]
                if line not in found:
                    found.append(line)
            if len(found) >= want:
                page.mouse.move(2, 2)
                return found
    page.mouse.move(2, 2)
    return found


def _toggle_theme(page):
    before = page.evaluate("() => document.documentElement.dataset.theme")
    page.click("#theme-toggle")
    page.wait_for_function("(b) => document.documentElement.dataset.theme !== b", arg=before, timeout=10_000)
    page.wait_for_timeout(400)
    return page.evaluate("() => document.documentElement.dataset.theme")


def _open_modal(page):
    page.click("#lgroups-edit")
    page.wait_for_function("() => !document.getElementById('lgroups-modal').hidden", timeout=10_000)
    page.wait_for_timeout(100)
    return page.evaluate(_MODAL)


def _counts_of(state):
    return [r["n"] for r in state["rows"]]


def _screen(page, locator, name):
    SCREENS.mkdir(parents=True, exist_ok=True)
    target = SCREENS / f"{name}.png"
    locator.screenshot(path=str(target))
    assert target.stat().st_size > 2000, target
    return target


# ---------------------------------------------------------- 1. the sidebar --


def test_the_sidebar_group_sits_in_place_draws_13_segments_and_withholds_pooled_with_its_reason(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base)
        side = page.evaluate(_SIDEBAR)
        assert side["shown"], side
        # After the display-mode group (Native Grid / Continuous Field), before the display channel.
        assert side["before"] == "group-resolution" and side["after"] == "group-channel", side
        assert len(side["segments"]) == GROUPS, side
        assert [s["grow"] for s in side["segments"]] == _uniform(L), side
        assert [s["alt"] for s in side["segments"]] == [g % 2 == 0 for g in range(1, GROUPS + 1)]
        assert side["segments"][0]["title"].startswith("Ch 1 · layers 1–"), side["segments"][0]
        assert side["summary"] == f"13 channels over {L} layers · Uniform", side
        assert not side["poolDisabled"] and side["notice"] is None and side["mode"] == "off", side

        # Local: Pooled is shut, with the reason in its label's title and the notice.
        page.check('input[name="frame-view"][value="aligned"]')
        page.check('input[name="frame-sub"][value="local"]')
        page.wait_for_function("() => document.getElementById('lgmode-pool').disabled", timeout=10_000)
        side = page.evaluate(_SIDEBAR)
        assert side["poolDisabled"] and side["poolLabelDisabled"], side
        assert side["poolTitle"] == POOL_REASON["local"] and side["notice"] == POOL_REASON["local"], side
        assert len(side["segments"]) == GROUPS, side
        browser.close()
        assert problems == [], problems

        # A stored Pooled stays checked in Local and is drawn as Boundaries, which the notice says.
        browser, page, problems, _ = _open(p, base, fragment="&frame=local&lgmode=pool")
        side = page.evaluate(_SIDEBAR)
        assert side["poolDisabled"] and side["poolChecked"], side
        assert side["notice"] == f"{POOL_REASON['local']} Boundaries are drawn instead.", side
        browser.close()

        # The Models page: after its frame group, Pooled shut with the page's reason.
        browser, page, problems, _ = _open(p, base, path="/models", fragment="&model=energy")
        side = page.evaluate(_SIDEBAR)
        assert side["shown"] and side["before"] == "group-m-frame", side
        assert len(side["segments"]) == GROUPS, side
        assert side["poolDisabled"] and side["poolTitle"] == POOL_REASON["models"], side
        assert side["notice"] == POOL_REASON["models"], side
        browser.close()
        assert problems == [], problems

        # The event-level aggregate serves no projections: the group is hidden on both pages.
        for path in ("/", "/models"):
            browser, page, problems, _ = _open(p, base, path=path, table=SINGLE_EVENTS_TABLE)
            side = page.evaluate(_SIDEBAR)
            assert side["hidden"] and not side["shown"], (path, side)
            assert side["reason"], (path, side)
            assert page.is_disabled("#lgroups-edit"), path
            browser.close()
            assert problems == [], (path, problems)


# ------------------------------------------------------------ 2. the modal --


def test_the_modal_opens_keeps_the_focus_and_closes_on_escape(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, viewport=(1024, 700))
        before = len(requests)
        state = _open_modal(page)
        assert state["open"] and state["focusInside"], state
        assert state["cells"] == L and len(state["handles"]) == GROUPS - 1, state
        assert all(h["role"] == "slider" and h["label"].startswith("Seam between Ch ") for h in state["handles"])
        assert "lg-handle" in state["focusClass"], "the first seam handle takes the focus"
        assert len(state["rows"]) == GROUPS and state["rows"][0]["startLocked"] and state["rows"][-1]["endLocked"]
        assert _counts_of(state) == _uniform(L), state["rows"]

        # It fits a 1024 x 700 viewport, and the page gains no horizontal scroll.
        vw, vh = state["viewport"]
        box = state["box"]
        assert box["left"] >= 0 and box["top"] >= 0 and box["right"] <= vw + 0.5 and box["bottom"] <= vh + 0.5, state
        assert state["scroll"][0] <= vw, state

        # Tab, and Shift+Tab, never leave the dialog.
        for key in ["Tab"] * 70 + ["Shift+Tab"] * 30:
            page.keyboard.press(key)
            assert page.evaluate("() => document.getElementById('lgroups-modal').contains(document.activeElement)"), key

        page.keyboard.press("Escape")
        page.wait_for_function("() => document.getElementById('lgroups-modal').hidden", timeout=5_000)
        assert page.evaluate("() => document.activeElement.id") == "lgroups-edit"
        assert requests[before:] == [], requests[before:]
        assert "lgroups" not in _hash(page) and "lgmode" not in _hash(page)
        browser.close()
        assert problems == [], problems


def test_the_seams_move_by_keys_and_drags_and_the_table_couples_them(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    uniform = _uniform(L)
    b = _bounds(uniform)
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment="&lgmode=bounds")
        _wait_strip(page, DEPTH)
        before = len(requests)
        _open_modal(page)

        # The first seam: ArrowRight moves it one layer, the table follows.
        handle = page.locator("#lgroups-ribbon .lg-handle").nth(0)
        handle.focus()
        page.keyboard.press("ArrowRight")
        state = page.evaluate(_MODAL)
        assert state["handles"][0]["now"] == b[0] + 1, state["handles"][0]
        assert state["rows"][0]["end"] == b[0] + 1 and state["rows"][1]["start"] == b[0] + 2, state["rows"][:2]
        assert _counts_of(state)[:2] == [uniform[0] + 1, uniform[1] - 1]
        # ArrowLeft to its lower limit (Ch 1 keeps one layer), then once more: it stops, and says why.
        for _ in range(b[0] + 1 - 1):
            page.keyboard.press("ArrowLeft")
        state = page.evaluate(_MODAL)
        assert state["handles"][0]["now"] == 1 == state["handles"][0]["min"], state["handles"][0]
        page.keyboard.press("ArrowLeft")
        state = page.evaluate(_MODAL)
        assert state["handles"][0]["now"] == 1, "the seam passed its neighbour"
        assert "every channel keeps at least one layer" in state["live"], state["live"]
        assert "Ch 1 ends at layer 1" in state["live"], state["live"]
        # End jumps to the neighbour's limit; one more ArrowRight stops there too.
        page.keyboard.press("End")
        state = page.evaluate(_MODAL)
        assert state["handles"][0]["now"] == b[1] - 1 == state["handles"][0]["max"], state["handles"][0]
        page.keyboard.press("ArrowRight")
        state = page.evaluate(_MODAL)
        assert state["handles"][0]["now"] == b[1] - 1 and "every channel keeps at least one layer" in state["live"]
        assert _counts_of(state)[1] == 1 and sum(_counts_of(state)) == L
        page.keyboard.press("Home")
        assert page.evaluate(_MODAL)["handles"][0]["now"] == 1

        # A pointer drag snaps to a whole seam: the 6th seam dragged to 0.4 of a cell past layer 30.
        page.click("#lgroups-reset")
        state = page.evaluate(_MODAL)
        assert _counts_of(state) == uniform
        h = state["handles"][5]
        ribbon = state["ribbon"]
        target = 30
        x = ribbon["left"] + (target + 0.4) / L * ribbon["width"]
        page.mouse.move(h["cx"], h["cy"])
        page.mouse.down()
        page.mouse.move((h["cx"] + x) / 2, h["cy"], steps=4)
        page.mouse.move(x, h["cy"], steps=4)
        page.mouse.up()
        state = page.evaluate(_MODAL)
        assert state["handles"][5]["now"] == target, state["handles"][5]
        expected_cx = ribbon["left"] + target / L * ribbon["width"]
        assert state["handles"][5]["cx"] == pytest.approx(expected_cx, abs=1.5), (state["handles"][5], expected_cx)
        assert state["rows"][5]["end"] == target and state["rows"][6]["start"] == target + 1
        # A drag past the neighbour stops a layer short of it, and the release announces it.
        h = state["handles"][5]
        page.mouse.move(h["cx"], h["cy"])
        page.mouse.down()
        page.mouse.move(ribbon["left"] + ribbon["width"] * 0.98, h["cy"], steps=8)
        page.mouse.up()
        state = page.evaluate(_MODAL)
        assert state["handles"][5]["now"] == state["handles"][6]["now"] - 1, state["handles"][5:7]
        assert "every channel keeps at least one layer" in state["live"], state["live"]

        # The table: End of Ch 3 moves Start of Ch 4, and Start of Ch 9 moves End of Ch 8.
        page.click("#lgroups-reset")
        end3 = page.locator("#lgroups-rows tr").nth(2).locator(".lg-end input")
        end3.fill(str(b[2] - 2))
        end3.dispatch_event("change")
        state = page.evaluate(_MODAL)
        assert state["rows"][2]["end"] == b[2] - 2 and state["rows"][3]["start"] == b[2] - 1, state["rows"][2:4]
        assert state["handles"][2]["now"] == b[2] - 2
        start9 = page.locator("#lgroups-rows tr").nth(8).locator(".lg-start input")
        start9.fill(str(b[7] + 3))
        start9.dispatch_event("change")
        state = page.evaluate(_MODAL)
        assert state["rows"][8]["start"] == b[7] + 3 and state["rows"][7]["end"] == b[7] + 2, state["rows"][7:9]
        # A Start that would empty the channel before it is clamped and announced.
        start9.fill(str(b[6]))
        start9.dispatch_event("change")
        state = page.evaluate(_MODAL)
        assert state["rows"][7]["n"] == 1 and state["rows"][8]["start"] == b[6] + 2, state["rows"][7:9]
        assert "every channel keeps at least one layer" in state["live"], state["live"]
        assert sum(_counts_of(state)) == L

        page.click("#lgroups-cancel")
        page.wait_for_function("() => document.getElementById('lgroups-modal').hidden", timeout=5_000)
        assert requests[before:] == [], f"an edit or a draft asked the server: {requests[before:]}"
        browser.close()
        assert problems == [], problems


def test_the_shorthand_presets_apply_and_cancel(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    uniform = _uniform(L)
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base)
        presets = page.evaluate(_PRESETS, L)
        assert presets["uniform"] == uniform and sum(presets["log"]) == L and sum(presets["em_hadron"]) == L
        before = len(requests)
        _open_modal(page)
        assert page.evaluate(_MODAL)["pressed"] == ["uniform"]

        # Ranges, with en dashes and hyphens mixed.
        custom = [3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 6, 6, L - 50]
        ranges, first = [], 1
        for i, n in enumerate(custom):
            ranges.append(f"{first}{'–' if i % 2 else '-'}{first + n - 1}")
            first += n
        page.fill("#lgroups-shorthand", ", ".join(ranges))
        page.click("#lgroups-shorthand-apply")
        state = page.evaluate(_MODAL)
        assert state["error"] is None and _counts_of(state) == custom, state
        assert state["pressed"] == [], state["pressed"]
        assert state["shorthand"] == ", ".join(r.replace("-", "–") for r in ranges)
        # Counts, by spaces, through Enter.
        counts = list(reversed(custom))
        page.fill("#lgroups-shorthand", " ".join(map(str, counts)))
        page.press("#lgroups-shorthand", "Enter")
        state = page.evaluate(_MODAL)
        assert state["error"] is None and _counts_of(state) == counts, state
        # An error is shown, and the draft kept.
        page.fill("#lgroups-shorthand", "1, 2, 3")
        page.click("#lgroups-shorthand-apply")
        state = page.evaluate(_MODAL)
        assert state["error"], state
        assert page.get_attribute("#lgroups-shorthand", "aria-invalid") == "true"
        assert _counts_of(state) == counts
        page.fill("#lgroups-shorthand", "1-3, 4-60")
        page.click("#lgroups-shorthand-apply")
        assert page.evaluate(_MODAL)["error"], "a partition of the wrong length is refused"

        # The presets apply, and say so.
        for key in ("log", "em_hadron", "uniform"):
            page.click(f'#lgroups-presets [data-preset="{key}"]')
            state = page.evaluate(_MODAL)
            assert _counts_of(state) == presets[key] and state["pressed"] == [key], (key, state["pressed"])

        # Apply a preset: Boundaries and the partition go in the link.
        page.click('#lgroups-presets [data-preset="log"]')
        page.click("#lgroups-apply")
        page.wait_for_function("() => document.getElementById('lgroups-modal').hidden", timeout=5_000)
        h = _hash(page)
        assert h.get("lgmode") == "bounds" and h.get("lgroups") == ".".join(map(str, presets["log"])), h
        _wait_strip(page, DEPTH)
        assert page.evaluate(_SIDEBAR)["summary"] == f"13 channels over {L} layers · Logarithmic Depth"
        assert [s["grow"] for s in page.evaluate(_SIDEBAR)["segments"]] == presets["log"]

        # Cancel restores: a draft redraws the strip, and Cancel puts the applied partition back.
        log_rects = [r["w"] for r in _drawn(page, "plot-yz")["rects"]]
        _open_modal(page)
        assert _counts_of(page.evaluate(_MODAL)) == presets["log"]
        page.click('#lgroups-presets [data-preset="em_hadron"]')
        page.wait_for_timeout(150)
        draft_rects = [r["w"] for r in _drawn(page, "plot-yz")["rects"]]
        assert draft_rects != log_rects, "the live draft is not drawn"
        page.click("#lgroups-cancel")
        page.wait_for_function("() => document.getElementById('lgroups-modal').hidden", timeout=5_000)
        page.wait_for_timeout(150)
        assert _hash(page).get("lgroups") == ".".join(map(str, presets["log"]))
        assert [r["w"] for r in _drawn(page, "plot-yz")["rects"]] == pytest.approx(log_rects, abs=0.01)
        _open_modal(page)
        assert _counts_of(page.evaluate(_MODAL)) == presets["log"], "Cancel kept the draft"

        # Uniform writes no partition into the link; the mode stays.
        page.click("#lgroups-reset")
        page.click("#lgroups-apply")
        page.wait_for_function("() => document.getElementById('lgroups-modal').hidden", timeout=5_000)
        h = _hash(page)
        assert "lgroups" not in h and h.get("lgmode") == "bounds", h

        # A custom partition is remembered as Last custom (never applied by itself).
        _open_modal(page)
        page.fill("#lgroups-shorthand", " ".join(map(str, custom)))
        page.click("#lgroups-shorthand-apply")
        page.click("#lgroups-apply")
        page.wait_for_function("() => document.getElementById('lgroups-modal').hidden", timeout=5_000)
        assert _hash(page).get("lgroups") == ".".join(map(str, custom))
        stored = json.loads(page.evaluate("() => localStorage.getItem('calosrv.layerGroups.custom')"))
        assert stored == {str(L): ".".join(map(str, custom))}, stored
        _open_modal(page)
        page.click("#lgroups-reset")
        assert page.is_visible("#lgroups-preset-custom")
        page.click("#lgroups-preset-custom")
        state = page.evaluate(_MODAL)
        assert _counts_of(state) == custom and state["pressed"] == ["custom"], state["pressed"]
        page.keyboard.press("Escape")

        assert requests[before:] == [], f"the editor asked the server: {requests[before:]}"
        browser.close()
        assert problems == [], problems


#: The ribbon's scale ticks and the box they are seen through (the wrap scrolls horizontally).
_SCALE_TICKS = """() => {
  const wrap = document.querySelector('#lgroups-modal .lg-ribbon-wrap').getBoundingClientRect();
  const ticks = (id) => [...document.querySelectorAll(`#${id} .lg-scale-tick`)].map((t) => {
    const b = t.getBoundingClientRect();
    return { text: t.textContent, left: b.left, right: b.right };
  });
  return { wrap: { left: wrap.left, right: wrap.right },
           top: ticks('lgroups-ribbon-top'), bottom: ticks('lgroups-ribbon-bottom') };
}"""


@pytest.mark.xfail(strict=True, reason="lead: LG-3 the ribbon's end ticks are centred on the ends and clipped: "
                                       "the depth scale's 'Z = ' and its last value are cut off")
@pytest.mark.parametrize("viewport", [(1600, 900), (1024, 700)], ids=lambda v: f"{v[0]}x{v[1]}")
def test_the_ribbon_scales_are_read_whole(physics_live_server, viewport):
    """The layer scale above the ribbon and the depth scale below it: every tick label is inside the box
    the reader sees it through, so the depth scale's first tick names its symbol (Z for Absolute)."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, viewport=viewport)
        _open_modal(page)
        ticks = page.evaluate(_SCALE_TICKS)
        browser.close()
    assert ticks["bottom"] and ticks["bottom"][0]["text"].startswith("Z = "), ticks["bottom"][:2]
    wrap = ticks["wrap"]
    cut = [t for t in ticks["top"] + ticks["bottom"] if t["left"] < wrap["left"] - 0.5 or t["right"] > wrap["right"] + 0.5]
    assert cut == [], (wrap, cut)
    assert problems == [], problems


# --------------------------------------------------------- 3. Boundaries --


def test_boundaries_draw_the_strip_above_the_plot_and_the_seams_with_no_request(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    uniform = _uniform(L)
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base)
        for plot in DEPTH:
            assert _lg(page, plot)["strip"] is None, "Off draws nothing"
        depth = httpx.get(f"{base}/api/projections", params={"table_name": BASELINE_TABLE}, timeout=30) \
            .json()["depth_layers"]
        before = len(requests)
        _mode(page, "bounds")
        _wait_strip(page, DEPTH)
        for plot in DEPTH:
            lg = _lg(page, plot)
            assert lg["strip"] == GROUPS and lg["seams"] == GROUPS - 1 and lg["spot"] == 0, (plot, lg)
            assert [d[2] for d in lg["stripData"]] == list(range(1, GROUPS + 1)), (plot, lg["stripData"])
            drawn = _drawn(page, plot)
            grid = lg["grid"]
            # 13 segments, alternating fills, every one in the band above the plot, none over the raster.
            assert len(drawn["rects"]) == GROUPS, (plot, drawn["rects"])
            assert [r["fill"] for r in drawn["rects"]] == ["a" if g % 2 else "b" for g in range(1, GROUPS + 1)]
            for r in drawn["rects"]:
                assert r["y"] >= -0.5 and r["y"] + r["h"] <= grid["y"] + 0.5, (plot, r, grid)
                assert r["x"] >= grid["x"] - 0.5 and r["x"] + r["w"] <= grid["x"] + grid["w"] + 0.5, (plot, r, grid)
            # Each segment spans its channel's stored edges (the demo lattice skips layers, so a
            # channel's millimetres are not its layer count times a pitch).
            edges = depth["edges_mm"]
            b = [0] + _bounds(uniform)
            spans = [edges[b[m]] - edges[b[m - 1]] for m in range(1, GROUPS + 1)]
            scale = [r["w"] / span for r, span in zip(drawn["rects"], spans)]
            assert max(scale) == pytest.approx(min(scale), rel=0.01), (plot, scale)
            # 12 dashed seams across the plot, at the segment joins.
            assert len(drawn["seams"]) == GROUPS - 1, (plot, drawn["seams"])
            for s, r in zip(drawn["seams"], drawn["rects"][1:]):
                assert s["mx"] == pytest.approx(r["x"], abs=1.0), (plot, s, r)
                # Across the plot (the bounds carry the stroke's half-width), never above it in the band.
                assert s["y"] >= grid["y"] - 3 and s["y"] + s["h"] <= grid["y"] + grid["h"] + 3, (plot, s, grid)
                assert s["h"] >= grid["h"] - 2, (plot, s, grid)
            assert drawn["edges"] >= GROUPS + 1, drawn["edges"]
        # The seams sit at the stored edges between layers b and b + 1.
        edges = depth["edges_mm"]
        assert _lg(page, "plot-yz")["seamAt"] == pytest.approx([edges[b] for b in _bounds(uniform)[:-1]], abs=1e-6)
        # Off and back: no request.
        _mode(page, "off")
        page.wait_for_timeout(200)
        assert _lg(page, "plot-yz")["strip"] is None
        _mode(page, "bounds")
        _wait_strip(page, DEPTH)
        # The Marks toggle hides the seams and keeps the strip, which covers no raster bin.
        page.click('button[data-toggle-marks="yz"]')
        page.wait_for_timeout(200)
        lg = _lg(page, "plot-yz")
        assert lg["strip"] == GROUPS and lg["seams"] is None, lg
        page.click('button[data-toggle-marks="yz"]')
        page.wait_for_timeout(200)
        assert _lg(page, "plot-yz")["seams"] == GROUPS - 1
        page.wait_for_timeout(500)
        assert requests[before:] == [], f"Boundaries asked the server: {requests[before:]}"
        browser.close()
        assert problems == [], problems


def test_hovering_a_segment_spotlights_both_panels_and_the_readout_names_the_layer_and_channel(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    uniform = _uniform(L)
    ranges, first = [], 1
    for n in uniform:
        ranges.append((first, first + n - 1))
        first += n
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment="&lgmode=bounds")
        _wait_strip(page, DEPTH)
        before = len(requests)
        tokens = _tokens(page)["dark"]
        for plot, other in (("plot-yz", "plot-xz"), ("plot-xz", "plot-yz")):
            for m in (2, 7):
                rect = _drawn(page, plot)["rects"][m - 1]
                tip = _hover(page, rect["cx"], rect["cy"])
                assert tip, (plot, m)
                a, z = ranges[m - 1]
                assert tip.startswith(f"Ch {m} · layers {a}–{z} ({z - a + 1} layers)"), tip
                assert re.search(r"\nZ [\d.]+–[\d.]+ mm \(z [\d.]+–[\d.]+ mm\) · [\d.]+ mm thick", tip), tip
                assert re.search(r"energy: [\d.]+ ?% of the selection’s energy", tip), tip
                # The spotlight: the channel's two faces on both depth panels; the segment hot.
                for host in (plot, other):
                    assert _lg(page, host)["spot"] == 2, (host, m)
                    drawn = page.evaluate(_DRAWN, [host, tokens])
                    assert len(drawn["spots"]) == 2, (host, drawn["spots"])
                    assert len(drawn["rects"]) == GROUPS, (host, drawn["rects"])
                    fills = [r["fill"] for r in drawn["rects"]]
                    # The linked panel draws the hot token; the hovered segment is in ECharts' hover
                    # state, whose fill is ECharts' lift of the token (LG-2, held exactly below).
                    lit = "hot" if host == other else ("hot", "emphasis")
                    assert fills[m - 1] in lit and sum(f in ("hot", "emphasis") for f in fills) == 1, (host, fills)
                    faces = sorted(s["mx"] for s in drawn["spots"])
                    assert faces[0] == pytest.approx(drawn["rects"][m - 1]["x"], abs=1.5)
                    assert faces[1] == pytest.approx(drawn["rects"][m - 1]["x"] + drawn["rects"][m - 1]["w"], abs=1.5)
            # Leaving the strip clears both.
            page.mouse.move(2, 2)
            page.wait_for_timeout(150)
            assert _lg(page, plot)["spot"] == 0 and _lg(page, other)["spot"] == 0

        # The raster readout appends "· layer k · Ch m [a–b]", and the channel holds the layer.
        pattern = re.compile(r"^Z = [\d.]+ mm \(z = [\d.]+ mm\) · layer (\d+) · Ch (\d+) \[(\d+)(?:–(\d+))?\]$")
        for plot in DEPTH:
            lines = _readouts(page, plot)
            assert len(lines) >= 3, (plot, lines)
            for line in lines:
                match = pattern.match(line)
                assert match, (plot, line)
                k, m, a = (int(match.group(i)) for i in (1, 2, 3))
                z = int(match.group(4) or a)
                assert (a, z) == ranges[m - 1] and a <= k <= z, (plot, line)
        page.mouse.move(2, 2)
        page.wait_for_timeout(200)
        assert requests[before:] == [], f"a hover asked the server: {requests[before:]}"
        browser.close()
        assert problems == [], problems


@pytest.mark.xfail(strict=True, reason="lead: LG-2 the hovered strip segment is drawn in ECharts' emphasis "
                                       "lift of groupStripHot, not in the token")
def test_the_hovered_segment_is_drawn_in_the_hot_token_in_both_themes(physics_live_server):
    """The hovered segment takes `groupStripHot` exactly (brief §3.2), the colour whose contrast with
    `groupStripText` the theme tests measure; ECharts' default hover state lifts it instead."""
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, fragment="&lgmode=bounds")
        _wait_strip(page, DEPTH)
        for theme in ("dark", "light"):
            if theme == "light":
                assert _toggle_theme(page) == "light"
            rect = _drawn(page, "plot-yz")["rects"][2]
            _hover(page, rect["cx"], rect["cy"])
            fills = [r["fill"] for r in _drawn(page, "plot-yz")["rects"]]
            page.mouse.move(2, 2)
            page.wait_for_timeout(150)
            assert fills[2] == "hot", (theme, fills, _drawn(page, "plot-yz"))
        browser.close()
        assert problems == [], problems


@pytest.mark.xfail(strict=True, reason="lead: LG-1 a shorthand error stays shown after a preset, the table or "
                                       "a handle has replaced the draft")
def test_a_shorthand_error_clears_once_the_draft_is_edited_otherwise(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base)
        _open_modal(page)
        page.fill("#lgroups-shorthand", "1, 2, 3")
        page.click("#lgroups-shorthand-apply")
        assert page.evaluate(_MODAL)["error"], "the refusal is shown"
        page.click('#lgroups-presets [data-preset="log"]')
        state = page.evaluate(_MODAL)
        # The field now spells the preset's ranges; the sentence about "1, 2, 3" no longer applies.
        assert state["shorthand"].startswith("1–1, 2–2"), state["shorthand"]
        assert state["error"] is None, state["error"]
        assert page.get_attribute("#lgroups-shorthand", "aria-invalid") is None
        browser.close()
        assert problems == [], problems


# ------------------------------------------------------------- 4. Pooled --


def test_pooled_asks_once_and_draws_13_depth_bins(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    wire = ".".join(map(str, _uniform(L)))
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment="&lgmode=bounds")
        _wait_strip(page, DEPTH)
        assert not any("depth_groups" in q for q in _projections(requests)), "Boundaries never pool"
        before = len(requests)
        with page.expect_response(lambda r: "/api/projections" in r.url and "depth_groups=" in r.url) as response:
            _mode(page, "pool")
        payload = response.value.json()
        _quiet(page, requests)
        asked = _projections(requests[before:])
        assert len(asked) == 1 and asked[0].get("depth_groups") == wire, asked
        assert [u for u in requests[before:] if "/api/projections" not in u] == [], requests[before:]
        assert payload["depth_layers"]["groups"]["pooled"] is True
        for panel in ("yz", "xz"):
            assert payload["panels"][panel]["axes"]["col"]["n"] == GROUPS, panel
            assert payload["panels"][panel]["shape"][1] == GROUPS, panel
        assert payload["panels"]["xy"]["axes"]["col"]["name"] != "z"
        _wait_strip(page, DEPTH)
        for plot in DEPTH:
            lg = _lg(page, plot)
            assert lg["strip"] == GROUPS and lg["seams"] is None, (plot, lg)
            lines = _readouts(page, plot, want=2)
            assert lines, plot
            for line in lines:
                assert re.match(r"^Z = [\d.]+ mm \(z = [\d.]+ mm\) · Ch \d+ \[layers \d+–\d+\] · mean of \d+ layers$",
                                line), (plot, line)
        assert "lgmode" in _hash(page) and _hash(page)["lgmode"] == "pool"
        # Leaving Pooled asks once more, without the partition.
        before = len(requests)
        _mode(page, "bounds")
        _quiet(page, requests)
        asked = _projections(requests[before:])
        assert len(asked) == 1 and "depth_groups" not in asked[0], asked
        browser.close()
        assert problems == [], problems


def test_pooled_with_the_compare_grid_asks_the_2x2_and_two_rows_and_never_local(physics_live_server):
    base = physics_live_server["base"]
    L = _layers(base)
    wire = ".".join(map(str, _uniform(L)))
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment="&compare=true")
        page.wait_for_function("() => document.getElementById('compare-grid-label').textContent !== '—'",
                               timeout=30_000)
        _quiet(page, requests)
        rows = [r for r in ("lab", "trans", "local") if not page.evaluate(
            f"() => document.querySelector('#compare-grid-rows [data-row={r}]').hidden")]
        assert {"lab", "trans", "local"} <= set(rows), rows
        before = len(requests)
        _mode(page, "pool")
        _quiet(page, requests)
        asked = _projections(requests[before:])
        assert len(asked) == 3, asked
        assert all(q.get("depth_groups") == wire for q in asked), asked
        assert sorted(_frame_of(q) for q in asked) == ["lab", "lab", "trans"], asked
        assert not any(_frame_of(q) == "local" for q in asked), "Local was asked"
        # The pooled rows draw no seams over their 13 bins; Local draws its badge.
        for row in ("lab", "trans"):
            _wait_strip(page, [f"plot-compare-{row}-xz", f"plot-compare-{row}-yz"])
            assert _lg(page, f"plot-compare-{row}-xz")["seams"] is None
        for col in ("xz", "yz"):
            lg = _lg(page, f"plot-compare-local-{col}")
            assert lg["strip"] is None and lg["badge"], lg
        # A new partition while pooled: three again.
        before = len(requests)
        _open_modal(page)
        page.click('#lgroups-presets [data-preset="log"]')
        page.click("#lgroups-apply")
        _quiet(page, requests)
        asked = _projections(requests[before:])
        assert len(asked) == 3 and sorted(_frame_of(q) for q in asked) == ["lab", "lab", "trans"], asked
        browser.close()
        assert problems == [], problems


def test_local_never_pools_and_shows_its_badge(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment="&frame=local")
        before = len(requests)
        _mode(page, "bounds")
        page.wait_for_function(
            "() => ['plot-yz','plot-xz'].every((id) => (echarts.getInstanceByDom(document.getElementById(id))"
            ".getOption().graphic || []).flatMap((g) => g.elements || [g]).some((e) => e.id === 'layer-groups-badge'))",
            timeout=10_000)
        page.wait_for_timeout(400)
        assert requests[before:] == [], requests[before:]
        for plot in DEPTH:
            lg = _lg(page, plot)
            assert lg["strip"] is None and lg["seams"] is None and lg["badge"], (plot, lg)
            assert lg["grid"]["y"] > 14, "the badge's band is reserved above the plot"
        assert page.is_disabled("#lgmode-pool")
        browser.close()
        assert problems == [], problems

        # A stored Pooled in Local: nothing pooled is asked.
        browser, page, problems, requests = _open(p, base, fragment="&frame=local&lgmode=pool")
        assert _projections(requests) and not any("depth_groups" in q for q in _projections(requests)), \
            _projections(requests)
        assert _lg(page, "plot-yz")["badge"]
        # Back to the Absolute frame with Pooled stored: the one request pools.
        before = len(requests)
        page.check('input[name="frame-view"][value="absolute"]')
        _quiet(page, requests)
        pooled = [q for q in _projections(requests[before:]) if "depth_groups" in q]
        assert len(pooled) == 1 and _frame_of(pooled[0]) == "lab", _projections(requests[before:])
        browser.close()
        assert problems == [], problems


# ------------------------------------------------------------- 5. the Z axis --


def test_the_absolute_depth_axis_reads_z_from_zero_and_the_d_frame_keeps_z_prime(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, _ = _open(p, base, fragment="&lgmode=bounds")
        for plot in DEPTH:
            axis = page.evaluate(_DEPTH_AXIS, plot)
            assert axis["name"] == "Z = z − 3649 — depth [mm]", (plot, axis)
            labels = [label for label in axis["labels"] if label]
            assert labels and labels[0] == "0", (plot, labels)
            values = [float(label.replace("−", "-")) for label in labels]
            assert values == sorted(values) and all(v == round(v) for v in values), labels
        browser.close()
        assert problems == [], problems

        browser, page, problems, _ = _open(p, base, fragment="&frame=canonical&lgmode=bounds")
        page.wait_for_function("() => document.getElementById('title-xy').textContent.startsWith('D–Y′')",
                               timeout=30_000)
        _wait_strip(page, DEPTH)
        for plot in DEPTH:
            axis = page.evaluate(_DEPTH_AXIS, plot)
            assert axis["name"].startswith("z′") and "3649" not in axis["name"], (plot, axis)
        lines = _readouts(page, "plot-yz", want=2)
        assert lines and all(re.match(r"^z′ = [\d.]+ mm · layer \d+ · Ch \d+ \[", line) for line in lines), lines
        browser.close()
        assert problems == [], problems


# ------------------------------------------------- 6. the Event Inspector --


def test_the_event_inspector_draws_planes_badges_and_seams(physics_live_server):
    base = physics_live_server["base"]
    n = httpx.get(f"{base}/api/event/pick", params={"table_name": BASELINE_TABLE}, timeout=30).json()["event_number"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment=f"&event={n}")
        page.wait_for_function(
            "() => ['lab','trans','local'].every((r) => ['xy','xz','yz'].every((c) => "
            "document.getElementById(`plot-event-${r}-${c}`)?.querySelector('canvas')))", timeout=30_000)
        _quiet(page, requests)
        before = len(requests)
        _mode(page, "bounds")
        _wait_strip(page, ["plot-event-lab-xz", "plot-event-lab-yz", "plot-event-trans-xz", "plot-event-trans-yz"])
        for row in ("lab", "trans"):
            for col in ("xz", "yz"):
                lg = _lg(page, f"plot-event-{row}-{col}")
                assert lg["seams"] == GROUPS - 1 and lg["strip"] == GROUPS, (row, col, lg)
                assert len(_drawn(page, f"plot-event-{row}-{col}")["seams"]) >= 1, (row, col)
        local_xz = _lg(page, "plot-event-local-xz")
        assert local_xz["planes"] and local_xz["planes"] >= 1 and local_xz["seams"] is None, local_xz
        assert local_xz["badge"] is None, local_xz
        local_yz = _lg(page, "plot-event-local-yz")
        assert local_yz["badge"] and local_yz["badge"].startswith("v–w"), local_yz
        assert not local_yz["planes"], local_yz
        # The planes are tilted: their two ends sit at different depths.
        tilted = page.evaluate(
            "() => { const inst = echarts.getInstanceByDom(document.getElementById('plot-event-local-xz'));"
            " const s = inst.getOption().series.find((x) => x.id === 'layer-groups-planes'); return s.data.length; }")
        assert tilted == local_xz["planes"]
        # Lab is detector numbering, trans relative.
        labs = _drawn(page, "plot-event-lab-yz")["rects"]
        tip = _hover(page, labs[0]["cx"], labs[0]["cy"]) if labs else None
        assert tip and tip.startswith("Ch 1 · "), tip
        trans = _drawn(page, "plot-event-trans-yz")["rects"]
        tip = _hover(page, trans[0]["cx"], trans[0]["cy"]) if trans else None
        assert tip and tip.startswith("Rel Ch 1 · "), tip
        page.mouse.move(2, 2)
        page.wait_for_timeout(300)
        assert requests[before:] == [], requests[before:]
        # Pooled draws boundaries on the inspector and asks nothing of /api/event.
        _mode(page, "pool")
        _quiet(page, requests)
        assert not any("/api/event" in u for u in requests[before:]), requests[before:]
        assert _lg(page, "plot-event-lab-yz")["seams"] == GROUPS - 1
        browser.close()
        assert problems == [], problems


# ------------------------------------------------------- 7. the Models page --


def test_the_models_pair_draws_boundaries_beside_the_slice_bracket_and_never_pools(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, path="/models", fragment="&model=energy&lgmode=pool",
                                                  gl=True)
        card = page.locator('.main .card[data-panel="vox-event"]')
        card.scroll_into_view_if_needed()
        page.wait_for_function(
            "() => { const c = echarts.getInstanceByDom(document.getElementById('plot-vox-event'));"
            " return Boolean(c && (c.getOption().series || []).some((s) => s.type === 'bar3D')); }", timeout=60_000)
        for cell in ("vproj-xy", "vproj-xz", "vproj-yz"):
            page.locator(f'.main .card[data-panel="{cell}"]').scroll_into_view_if_needed()
        _wait_strip(page, ["plot-vproj-xz", "plot-vproj-yz"])
        _quiet(page, requests)
        for plot in ("plot-vproj-xz", "plot-vproj-yz"):
            lg = _lg(page, plot)
            assert lg["strip"] == GROUPS and lg["seams"] == GROUPS - 1, (plot, lg)
        assert _lg(page, "plot-vproj-xy")["strip"] is None
        # Slices: K = 4 brackets the first slice on the depth projections, beside the channels.
        before = len(requests)
        count = page.locator('.main .card[data-panel="vox-event"] [data-voxel-slices]')
        count.fill("4")
        count.dispatch_event("change")
        page.wait_for_timeout(400)
        for plot in ("plot-vproj-xz", "plot-vproj-yz"):
            lg = _lg(page, plot)
            assert lg["slab"] == 2 and lg["strip"] == GROUPS and lg["seams"] == GROUPS - 1, (plot, lg)
        # A mode change and a draft repaint the pair with no request.
        _mode(page, "off")
        page.wait_for_timeout(200)
        assert _lg(page, "plot-vproj-yz")["strip"] is None and _lg(page, "plot-vproj-yz")["slab"] == 2
        _mode(page, "bounds")
        _wait_strip(page, ["plot-vproj-xz", "plot-vproj-yz"])
        _open_modal(page)
        page.click('#lgroups-presets [data-preset="log"]')
        page.wait_for_timeout(150)
        page.click("#lgroups-cancel")
        page.wait_for_timeout(300)
        assert requests[before:] == [], requests[before:]
        assert not any("depth_groups" in u for u in requests), [u for u in requests if "depth_groups" in u]
        browser.close()
        assert problems == [], problems


# ---------------------------------------------------- 8. both themes, screens --


def _overlay_colours(page, plot, theme):
    drawn = _drawn(page, plot, theme)
    return len(drawn["rects"]), len(drawn["seams"]), drawn["edges"]


def test_a_theme_switch_recolours_the_channels_from_the_new_tokens_with_no_request(physics_live_server):
    base = physics_live_server["base"]
    with physics_live_server["playwright"].sync_playwright() as p:
        browser, page, problems, requests = _open(p, base, fragment="&lgmode=bounds")
        _wait_strip(page, DEPTH)
        tokens = _tokens(page)
        keys = ("groupStripFillA", "groupStripFillB", "groupStripEdge", "groupStripText", "groupStripHot",
                "groupSeam", "groupSpot")
        assert all(tokens["dark"][k] != tokens["light"][k] for k in ("groupStripFillA", "groupStripFillB",
                                                                     "groupStripHot", "groupSeam"))
        assert all(k in tokens["dark"] and k in tokens["light"] for k in keys)
        before = len(requests)
        for plot in DEPTH:
            assert _overlay_colours(page, plot, "dark")[:2] == (GROUPS, GROUPS - 1), plot
            assert _overlay_colours(page, plot, "light")[:2] == (0, 0), plot
        assert _toggle_theme(page) == "light"
        for plot in DEPTH:
            assert _overlay_colours(page, plot, "light")[:2] == (GROUPS, GROUPS - 1), plot
            assert _overlay_colours(page, plot, "dark")[:2] == (0, 0), plot
            # The hovered segment and the spotlight take the light tokens too.
        rect = _drawn(page, "plot-yz", "light")["rects"][3]
        _hover(page, rect["cx"], rect["cy"])
        for plot in DEPTH:
            drawn = _drawn(page, plot, "light")
            fills = [r["fill"] for r in drawn["rects"]]
            # The hovered segment is in ECharts' hover state (LG-2); the linked one takes the light hot token.
            lit = ("hot",) if plot == "plot-xz" else ("hot", "emphasis")
            assert len(drawn["spots"]) == 2 and fills[3] in lit, (plot, fills)
        page.mouse.move(2, 2)
        assert _toggle_theme(page) == "dark"
        for plot in DEPTH:
            assert _overlay_colours(page, plot, "dark")[:2] == (GROUPS, GROUPS - 1), plot
        page.wait_for_timeout(600)
        assert requests[before:] == [], f"a theme switch asked the server: {requests[before:]}"
        browser.close()
        assert problems == [], problems


def test_screenshots_of_the_channels_in_both_themes(physics_live_server):
    """Brief 8.1 item 8: the 2 x 2 with Boundaries, the pooled 2 x 2, the modal, an inspector row and a
    Models pair, in dark and light, saved for review (the assertions are the views' own)."""
    base = physics_live_server["base"]
    n = httpx.get(f"{base}/api/event/pick", params={"table_name": BASELINE_TABLE}, timeout=30).json()["event_number"]
    saved = []
    with physics_live_server["playwright"].sync_playwright() as p:
        for theme in ("dark", "light"):
            browser, page, problems, requests = _open(p, base, fragment="&lgmode=bounds")
            if theme == "light":
                assert _toggle_theme(page) == "light"
            _wait_strip(page, DEPTH)
            rect = _drawn(page, "plot-yz")["rects"][4]
            _hover(page, rect["cx"], rect["cy"])
            saved.append(_screen(page, page.locator("#ensemble-grid"), f"physics-2x2-boundaries-{theme}"))
            page.mouse.move(2, 2)
            state = _open_modal(page)
            assert state["open"]
            saved.append(_screen(page, page.locator("#lgroups-modal .lg-modal"), f"physics-modal-{theme}"))
            page.keyboard.press("Escape")
            with page.expect_response(lambda r: "/api/projections" in r.url and "depth_groups=" in r.url):
                _mode(page, "pool")
            _quiet(page, requests)
            _wait_strip(page, DEPTH)
            saved.append(_screen(page, page.locator("#ensemble-grid"), f"physics-2x2-pooled-{theme}"))
            browser.close()
            assert problems == [], (theme, problems)

            browser, page, problems, requests = _open(p, base, fragment=f"&event={n}&lgmode=bounds")
            if theme == "light":
                assert _toggle_theme(page) == "light"
            _wait_strip(page, ["plot-event-lab-xz", "plot-event-lab-yz"])
            for row in ("lab", "local"):
                saved.append(_screen(page, page.locator(f"#event-grid-rows [data-row={row}]"),
                                     f"physics-inspector-{row}-row-{theme}"))
            browser.close()
            assert problems == [], (theme, problems)

            browser, page, problems, requests = _open(p, base, path="/models", fragment="&model=energy&lgmode=bounds",
                                                      gl=True)
            if theme == "light":
                assert _toggle_theme(page) == "light"
            page.locator('.main .card[data-panel="vox-event"]').scroll_into_view_if_needed()
            page.wait_for_function(
                "() => { const c = echarts.getInstanceByDom(document.getElementById('plot-vox-event'));"
                " return Boolean(c && (c.getOption().series || []).some((s) => s.type === 'bar3D')); }",
                timeout=60_000)
            for cell in ("vproj-xy", "vproj-xz", "vproj-yz"):
                page.locator(f'.main .card[data-panel="{cell}"]').scroll_into_view_if_needed()
            _wait_strip(page, ["plot-vproj-xz", "plot-vproj-yz"])
            count = page.locator('.main .card[data-panel="vox-event"] [data-voxel-slices]')
            count.fill("4")
            count.dispatch_event("change")
            page.wait_for_timeout(400)
            for cell in ("vproj-xz", "vproj-yz"):
                saved.append(_screen(page, page.locator(f'.main .card[data-panel="{cell}"]'),
                                     f"models-pair-{cell}-{theme}"))
            browser.close()
            assert problems == [], (theme, problems)
    assert len(saved) == 14, saved


# ------------------------------------------------------------- 10. timing --


def test_a_boundaries_repaint_is_within_the_50_ms_budget(physics_live_server, record_property):
    base = physics_live_server["base"]
    n = httpx.get(f"{base}/api/event/pick", params={"table_name": BASELINE_TABLE}, timeout=30).json()["event_number"]
    results = {}
    with physics_live_server["playwright"].sync_playwright() as p:
        for name, fragment, panels in (("2x2", "", 2), ("inspector", f"&event={n}", 6),
                                       ("compare", "&compare=true", 6)):
            browser, page, problems, requests = _open(p, base, fragment=fragment)
            if name == "inspector":
                page.wait_for_function("() => document.getElementById('plot-event-local-yz')?.querySelector('canvas')",
                                       timeout=30_000)
            if name == "compare":
                page.wait_for_function("() => document.getElementById('plot-compare-trans-yz')?.querySelector('canvas')",
                                       timeout=30_000)
            _quiet(page, requests)
            before = len(requests)
            runs = page.evaluate(_TIME_REPAINT, 9)
            assert requests[before:] == [], (name, requests[before:])
            calls = [len(r["calls"]) for r in runs]
            assert min(calls) >= panels, (name, calls)
            sync = sorted(r["sync"] for r in runs)
            painted = sorted(r["painted"] for r in runs)
            per_call = sorted(c for r in runs for c in r["calls"])
            results[name] = {
                "panels": max(calls), "median_ms": round(statistics.median(sync), 2), "max_ms": round(sync[-1], 2),
                "median_to_paint_ms": round(statistics.median(painted), 2),
                "per_panel_median_ms": round(statistics.median(per_call), 2), "per_panel_max_ms": round(per_call[-1], 2),
            }
            browser.close()
            assert problems == [], (name, problems)
    record_property("boundaries_repaint", json.dumps(results))
    print("\nBOUNDARIES REPAINT", json.dumps(results, indent=1))
    for name, r in results.items():
        assert r["median_ms"] < BUDGET_MS, (name, r)
