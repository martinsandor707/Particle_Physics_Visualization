"""The 3-D voxel views of Page 2, executed under Node on the recorded payloads.

`calosrv/static/js/voxels.js` decodes the two voxel payloads and builds the
echarts-gl option; `voxel_notes.js` writes the Details drawers;
`voxel_views.js` is the section controller; `palette.js` holds the species
palette. A Node script runs all of them against the payloads
`tests/test_payload_fixtures.py` recorded (`tests/fixtures/payloads/`), and the
tests here hold the result to the contracts and to CLAUDE.md section 2:

* every cube sits where the payload's own placement rule puts it, re-derived
  here in Python from the base64 arrays - lattice coordinates minus the
  origin for cells, `x0 + (i + 0.5) × pitch` on a splat grid, the native layer
  coordinates on the D-frame, `z_centres[layer]` on a cloud - never an index
  times a pitch on the irregular lattice;
* codes map to the scale (the 2-D panels' code-to-colour table, zero at border
  grey on the raw Shap-CAM ramp, the folded PuOr arms on the signed log), flags
  decode to shower, primary and below-floor bits, layer runs sum to n;
* the box is 1:1:1 in millimetres from the physical spans, the camera
  orthographic, every cube flat-shaded, every spacer invisible and silent;
* the species palette clears 3:1 against the card (screen) and white (print)
  and keeps every pair apart under simulated deuteranopia and protanopia;
* the drawers quote the recorded exception, the disclosures and the five energy
  fractions, and no rendered number uses a hyphen for a minus;
* the section builds its cards with Export on the 2-D projections only, asks for
  the densest event when the link names none, keeps the 2-D half when the 3-D
  half is refused, holds at most two WebGL charts and says when it has none.

Skipped without `node`.
"""

from __future__ import annotations

import base64
import itertools
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
FIXTURES = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

EVENTS = ["event_voxels_base_lab", "event_voxels_base_canonical", "event_voxels_base_local_shapcam",
          "event_voxels_single_local", "event_voxels_single_species"]
ENSEMBLES = ["voxels_base_local", "voxels_base_canonical_shapcam", "voxels_single_local", "voxels_two_local"]

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")

CARD = (28, 33, 40)       # #1c2128
WHITE = (255, 255, 255)
BORDER = (48, 54, 61)     # #30363d

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const EVENTS = %(events)s;
const ENSEMBLES = %(ensembles)s;

/* ---- a fake DOM, enough for the section to build and draw its cards ------- */
class ClassList {
  constructor() { this.names = new Set(); }
  add(...c) { c.forEach((x) => this.names.add(x)); }
  remove(...c) { c.forEach((x) => this.names.delete(x)); }
  contains(c) { return this.names.has(c); }
  toggle(c, on) {
    const want = on === undefined ? !this.names.has(c) : Boolean(on);
    if (want) this.names.add(c); else this.names.delete(c);
    return want;
  }
}
class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = []; this.dataset = {}; this.attributes = {}; this.style = {}; this.hidden = false;
    this.ownText = ''; this.listeners = {}; this.classList = new ClassList(); this.options = [];
    this.value = ''; this.disabled = false; this.canvases = []; this.id = '';
  }
  set className(v) { this.classList = new ClassList(); String(v).split(/\s+/).filter(Boolean).forEach((c) => this.classList.add(c)); }
  get className() { return [...this.classList.names].join(' '); }
  set textContent(v) { this.ownText = String(v); this.children = []; }
  get textContent() { return this.ownText + this.children.map((c) => c.textContent).join(''); }
  append(...nodes) {
    for (const n of nodes) {
      const node = typeof n === 'string' ? Object.assign(new El('#text'), { ownText: n }) : n;
      this.children.push(node);
      if (this.tagName === 'SELECT' && node.tagName === 'OPTION') this.options.push(node);
    }
  }
  replaceChildren(...nodes) { this.children = []; this.ownText = ''; this.options = []; this.append(...nodes); }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  fire(type) { for (const fn of this.listeners[type] ?? []) fn({ preventDefault() {} }); }
  querySelectorAll(sel) { return sel === 'canvas' ? this.canvases : []; }
  closest() { return null; }
  getContext() { return null; }
  get clientWidth() { return 600; }
  get clientHeight() { return 400; }
  all() { return [this, ...this.children.flatMap((c) => (c.all ? c.all() : []))]; }
}
globalThis.document = { createElement: (t) => new El(t), createTextNode: (t) => Object.assign(new El('#text'), { ownText: t }) };
globalThis.window = { location: { origin: 'http://test.invalid' } };

const v = await imp('voxels.js');
const vv = await imp('voxel_views.js');
const vn = await imp('voxel_notes.js');
const pal = await imp('palette.js');
const scale = await imp('scale.js');
const caps = await imp('capabilities.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');

const out = { events: {}, ensembles: {}, palette: {}, notes: {}, views: {}, section: {} };
const arr = (a) => Array.from(a);

/** Every string a reader can see in an option: axis names, tick labels, legend, graphics. */
function optionStrings(option) {
  const strings = [];
  for (const key of ['xAxis3D', 'yAxis3D', 'zAxis3D']) {
    const a = option[key];
    strings.push(a.name);
    for (const t of [-3000, -1.5, 0, 250.4, 4000]) strings.push(String(a.axisLabel.formatter(t)));
  }
  const vm = option.visualMap;
  if (vm) {
    strings.push(...(vm.text ?? []).map(String));
    if (typeof vm.formatter === 'function') for (const t of [-1, -0.5, 0, 0.5, 1, -6, -12]) strings.push(String(vm.formatter(t)));
  }
  for (const g of option.graphic ?? []) if (g.style?.text) strings.push(g.style.text);
  return strings;
}

function summarise(model, built) {
  const option = built.option;
  return {
    box: built.box,
    bounds: built.bounds,
    drawn: built.drawn, skipped: built.skipped, noValue: built.noValue, hidden: built.hidden,
    translucent: built.translucent, primaries: built.primaries, halos: built.halos,
    roles: built.roles.map((r) => ({ role: r.role, members: r.members })),
    series: option.series.map((s) => ({
      type: s.type, name: s.name, silent: Boolean(s.silent), shading: s.shading ?? null, bevelSize: s.bevelSize ?? null,
      labels: [s.label?.show ?? null, s.emphasis?.label?.show ?? null],
      barSize: s.barSize ?? null, stack: s.stack ?? null, itemOpacity: s.itemStyle?.opacity ?? null,
      lineStyle: s.lineStyle ?? null,
      data: s.data.map((d) => (Array.isArray(d) ? d : { value: d.value, color: d.itemStyle?.color, opacity: d.itemStyle?.opacity })),
    })),
    grid3D: { ...option.grid3D, viewControl: option.grid3D.viewControl },
    axes: ['xAxis3D', 'yAxis3D', 'zAxis3D'].map((k) => ({ name: option[k].name, min: option[k].min, max: option[k].max })),
    visualMap: option.visualMap ? { seriesIndex: option.visualMap.seriesIndex, text: option.visualMap.text, min: option.visualMap.min, max: option.visualMap.max } : null,
    strings: optionStrings(option),
    tooltipConfine: option.tooltip.confine, tooltipAppendTo: option.tooltip.appendTo,
  };
}

/* ---- one event --------------------------------------------------------- */
for (const name of EVENTS) {
  const payload = load(name);
  const model = v.decodeEventVoxels(payload);
  const built = v.voxelOption(model, { palette: 'viridis' });
  const rgba = v.cubeColours(model, 'viridis');
  const picks = [...new Set([0, Math.floor(model.n / 2), model.n - 1, ...payload.voxels.topk.slice(0, 3).map((t) => t.i)])];
  out.events[name] = {
    n: model.n, x: arr(model.x), y: arr(model.y), z: arr(model.z), code: arr(model.code),
    shower: arr(model.shower), primary: arr(model.primary), below: arr(model.below),
    box: model.box, rgba: arr(rgba),
    values: [0, 1, 128, 255].map((c) => v.codeValue(model, c)),
    tips: picks.map((i) => [i, v.voxelTooltip(model, i)]),
    option: summarise(model, built),
    legend: v.speciesLegend(model),
    notes: vn.voxelEventNotes({ payload, drawn: built }),
  };
}

/* Primary-tagged cubes, set on a copy: halos on the most energetic, at most HALO_LIMIT. */
{
  const payload = clone(load('event_voxels_base_lab'));
  const flags = Buffer.from(payload.voxels.cubes.flags, 'base64');
  const tagged = [];
  for (let i = flags.length - 1; tagged.length < 15; i -= 7) { flags[i] |= 4; tagged.push(i); }
  payload.voxels.cubes.flags = flags.toString('base64');
  const model = v.decodeEventVoxels(payload);
  const built = v.voxelOption(model, {});
  out.primaries = { tagged, option: summarise(model, built), limit: v.HALO_LIMIT, theme: { text: scale.THEME.text, canvas: scale.THEME.canvas },
    notes: vn.voxelEventNotes({ payload, drawn: built }) };
}

/* Species hidden by the isolate toggles. */
{
  const payload = load('event_voxels_single_species');
  const model = v.decodeEventVoxels(payload);
  const hidden = new Set([0, 2]);
  const built = v.voxelOption(model, { hidden });
  out.species = { option: summarise(model, built), legend: v.speciesLegend(model, hidden),
    notes: vn.voxelEventNotes({ payload, drawn: built, hidden: [...hidden] }) };
}

/* ---- the ensemble cloud ------------------------------------------------ */
for (const name of ENSEMBLES) {
  const payload = load(name);
  const model = v.decodeEnsembleVoxels(payload);
  const built = v.voxelOption(model, { palette: 'viridis' });
  out.ensembles[name] = {
    n: model.n, x: arr(model.x), y: arr(model.y), z: arr(model.z), layer: arr(model.layer), code: arr(model.code),
    counts: arr(model.counts), recount: v.layerCounts(model), box: model.box, rgba: arr(v.cubeColours(model, 'viridis')),
    table: arr(v.voxelCodeTable(model, 'viridis')),
    values: [2, 128, 129, 255].map((c) => v.codeValue(model, c)),
    tips: [0, model.n - 1, payload.topk[0].i].map((i) => [i, v.voxelTooltip(model, i)]),
    option: summarise(model, built),
    notes: vn.voxelEnsembleNotes({ payload, drawn: built }),
  };
}

/* The code-to-colour tables the 2-D panels use, for comparison. */
out.tables = {
  viridis: arr(pal.lookupTable('viridis')),
  puor_screen: arr(pal.lookupTable('puor_screen')),
  puor_screen_linear: arr(pal.lookupTable('puor_screen_linear')),
};

/* ---- the palettes ------------------------------------------------------- */
out.palette.qualitative = pal.QUALITATIVE;
out.palette.checked = pal.QUALITATIVE_CHECKED;
out.palette.stops = Object.fromEntries(Object.keys(pal.QUALITATIVE).map((k) => [k, pal.qualitativeStops(k, pal.QUALITATIVE_CHECKED[k])]));
out.palette.refusals = Object.keys(pal.QUALITATIVE).map((k) => {
  try { pal.qualitativeStops(k, pal.QUALITATIVE_CHECKED[k] + 1); return null; } catch (e) { return e.message; }
});
out.palette.unknown = (() => { try { pal.qualitativeStops('jet', 2); return null; } catch (e) { return e.message; } })();

/* ---- projections' notes ---------------------------------------------------- */
out.notes.projection = vn.voxelProjectionNotes({
  pair: 'ensemble', payload: load('projections_single_local'), panelId: 'yz', pairing: ['Paired with the 3-D cloud.'],
  title: 'v–w Projection',
});

/* ---- the section's pure helpers ------------------------------------------ */
const experiments = load('experiments').experiments;
for (const exp of experiments) {
  const plan = caps.page2Plan(exp);
  const offer = vv.normaliseOffer(plan.voxels);
  const views = {};
  for (const frame of ['lab', 'trans', 'local', 'canonical']) {
    for (const [channel, ens] of [['energy', 'density'], ['shapcam', 'shapcam_energy'], ['species', 'gradcam_energy']]) {
      for (const shower of ['a', 'b', 'both']) {
        const ev = vv.resolveEventView({ frame, channel, shower }, offer);
        const en = vv.resolveEnsembleView({ frame, channel: ens }, offer);
        const filters = { table_name: exp.table_name };
        views[`${frame}|${channel}|${shower}`] = {
          event: ev, ensemble: en,
          eventRequests: ev.frame ? vv.eventRequests({ filters, eventNumber: 5, view: ev, model: 'energy' }) : null,
          ensembleRequests: en.frame ? vv.ensembleRequests({ filters, view: en, model: 'energy', anchor: 'p0' }) : null,
          noGl: ev.frame ? vv.eventRequests({ filters, eventNumber: 5, view: ev, gl: false }).voxels : null,
        };
      }
    }
  }
  out.views[exp.table_name] = { offer, wholePlan: vv.normaliseOffer(plan), views };
}
out.pick = vv.pickRequest({ table_name: 't', e1_min: 1 });

/* ---- the section, on the fake DOM, a fake ECharts and a fake server -------- */
function raster(eventNumber) {
  const frame = (title, symbols) => ({
    title, symbols, window: { x: [-500, 500], y: [-500, 500], z: [-100, 900] }, marks: [],
    panels: { xy: { axes: {} }, xz: { axes: {} }, yz: { axes: {} } },
  });
  return {
    meta: { table_name: 'experiment_baseline', warnings: [] },
    event: { event_number: eventNumber, prev: null, next: eventNumber + 1, shower: { key: 'a' } },
    frames: { lab: frame('Original', { x: 'x', y: 'y', z: 'z' }), trans: frame('Translated', { x: 'Δx', y: 'Δy', z: 'Δz' }),
      local: frame('Local', { x: 'u', y: 'v', z: 'w' }) },
  };
}

async function runSection({ table, values = {}, webgl = true, refuse3d = false }) {
  const exp = experiments.find((e) => e.table_name === table);
  const requests = [];
  globalThis.fetch = async (url) => {
    const u = new URL(String(url));
    const q = Object.fromEntries(u.searchParams.entries());
    requests.push([u.pathname, q]);
    const json = (body, status = 200) => ({ ok: status < 400, status, statusText: '', json: async () => body });
    if (u.pathname === '/api/event/pick') {
      return json(table === 'single_hits' ? load('pick_single_densest') : { event_number: 0, rule: 'densest rule', rule_id: 'densest' });
    }
    if (u.pathname === '/api/event' && q.format === 'voxels') {
      if (refuse3d) return json({ title: 'Unsupported capability', detail: 'The 3-D view is shut for this test.' }, 422);
      const name = q.channel === 'species' ? 'event_voxels_single_species'
        : table === 'single_hits' ? 'event_voxels_single_local'
        : ({ lab: 'event_voxels_base_lab', trans: 'event_voxels_base_lab', local: 'event_voxels_base_local_shapcam' }[q.frame]);
      return json(load(name));
    }
    if (u.pathname === '/api/event') return json(raster(Number(q.event_number)));
    if (u.pathname === '/api/voxels') {
      return json(load(table === 'single_hits' ? 'voxels_single_local' : (q.frame === 'canonical' ? 'voxels_base_canonical_shapcam' : 'voxels_base_local')));
    }
    if (u.pathname === '/api/projections') return json(load(table === 'single_hits' ? 'projections_single_local' : 'projections_base_lab'));
    return json({ detail: 'no such route' }, 404);
  };
  const charts = [];
  const lib = {
    init: (el) => {
      const chart = {
        el, options: [], disposed: false, cleared: 0,
        setOption(option, flags) { this.options.push([option, flags]); },
        getWidth: () => 600, getHeight: () => 400, getDom: () => el,
        clear() { this.cleared += 1; }, resize() {}, dispose() { this.disposed = true; }, dispatchAction() {},
      };
      charts.push(chart);
      return chart;
    },
  };
  const renders = [];
  class FakeProjection {
    constructor(id, opts) { this.id = id; this.isometric = opts.isometric; this.element = { clientWidth: 600, clientHeight: 400 }; }
    render(payload, opts) { this.payload = payload; renders.push([this.id, Object.keys(opts).sort()]); }
    clear() {} relayout() {} setBusy() {} currentView() { return null; }
  }
  const state = {
    values: { table_name: table, voxel_event: null, voxel_shower: 'a', voxel_channel: 'energy', ens_channel: 'density',
      frame: 'lab', model: 'segmentation', palette: 'viridis', anchor: 'backprojected', ...values },
    get(k) { return this.values[k]; },
    set(patch) { Object.assign(this.values, patch); return true; },
    filterParams() { return { table_name: this.values.table_name }; },
    isTouched: () => false,
  };
  const host = new El('section');
  const rendered = [];
  const errors = [];
  const section = new vv.VoxelSection(host, {
    state, getExperiment: () => exp, onRendered: (id, p) => rendered.push([id, Boolean(p)]),
    onError: (e, c) => errors.push(`${c}: ${e.message}`), webgl, echarts: lib, ProjectionClass: FakeProjection,
  });
  const plan = caps.page2Plan(exp);
  section.applyPlan(plan.voxels);
  let refreshError = null;
  try { await section.refresh(); } catch (e) { refreshError = e.message; }
  const cards = {};
  for (const id of section.ids()) {
    const rec = section.cards.get(id);
    const nodes = rec.element.all();
    cards[id] = {
      hidden: rec.element.hidden, pairHidden: section.pairs[rec.spec.pair].element.hidden,
      classes: rec.element.className, panel: rec.element.dataset.panel,
      exportButtons: nodes.filter((n) => n.dataset?.export !== undefined).length,
      inspect: nodes.filter((n) => n.dataset?.inspect === id).length,
      plotId: rec.plot.id, titleId: rec.title.id, title: rec.title.textContent,
      message: rec.message.hidden ? null : rec.message.textContent, kind: rec.message.dataset.kind ?? null,
      caption: rec.caption.hidden ? null : rec.caption.textContent,
      exportTarget: section.exportTarget(id) ? Object.keys(section.exportTarget(id)) : section.exportTarget(id),
      notes: section.notes(id) ? { title: section.notes(id).title, hazards: section.notes(id).hazards,
        headings: section.notes(id).sections.map((s) => s.heading) } : null,
      sparse: rec.sparse ? (rec.sparse.hidden ? null : rec.sparse.textContent) : undefined,
      options: rec.controls.channel ? rec.controls.channel.options.map((o) => [o.value, o.disabled, o.title]) : null,
      showersHidden: rec.controls.showers ? rec.controls.showers.hidden : null,
    };
  }
  const result = { requests, cards, rendered, errors, refreshError, renders, charts: charts.length,
    glOptions: charts.map((c) => c.options.length), foreign: section.exportTarget('xy'), has: section.has('vox-event') };
  // A lost WebGL context says so; a restored one rebuilds the chart from the payload in hand.
  const gl = section.cards.get('vox-event');
  if (gl.chart) {
    const canvas = new El('canvas');
    gl.plot.canvases.push(canvas);
    section.paintGl(section.pairs.event);
    canvas.fire('webglcontextlost');
    result.lost = { message: gl.message.hidden ? null : gl.message.textContent, kind: gl.message.dataset.kind,
      hazards: section.notes('vox-event').hazards };
    canvas.fire('webglcontextrestored');
    result.restored = { message: gl.message.hidden ? null : gl.message.textContent, charts: charts.length,
      disposed: charts.filter((c) => c.disposed).length };
  }
  section.reset();
  result.afterReset = { cleared: charts.map((c) => (c.disposed ? null : c.cleared)), notes: section.notes('vox-event') };
  result.warnings = section.warnings();
  return result;
}

out.section.base = await runSection({ table: 'experiment_baseline' });
out.section.single = await runSection({ table: 'single_hits', values: { voxel_channel: 'species', ens_channel: 'shapcam_energy' } });
out.section.noGl = await runSection({ table: 'experiment_baseline', webgl: false });
out.section.refused = await runSection({ table: 'experiment_baseline', refuse3d: true });
out.section.events = await runSection({ table: 'single_events' });
out.section.pinned = await runSection({ table: 'experiment_baseline', values: { voxel_event: 7, frame: 'local', voxel_channel: 'shapcam', model: 'angle' } });

console.log(JSON.stringify(out));
"""


def _script() -> str:
    return _SCRIPT % {"events": json.dumps(EVENTS), "ensembles": json.dumps(ENSEMBLES)}


@pytest.fixture(scope="module")
def out() -> dict:
    """Run the harness once; every test reads its part."""
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _script(), args],
                          capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _ordinals(b64: str, dtype: str = "u8") -> list[int]:
    raw = base64.b64decode(b64)
    if dtype == "u8":
        return list(raw)
    assert dtype == "u16le" and len(raw) % 2 == 0
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def _no_hyphen_numbers(strings) -> None:
    for text in strings:
        visible = re.sub(r"<[^>]+>", " ", str(text))
        assert not HYPHEN_NUMBER.search(visible), f"hyphen-minus before a digit in: {visible!r}"


def _note_lines(notes: dict) -> list[str]:
    return [line for section in notes["sections"] for line in section["lines"]]


def _hex(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[k:k + 2], 16) for k in (1, 3, 5))


# --------------------------------------------------------------- decoding --


@pytest.mark.parametrize("name", EVENTS)
def test_event_cubes_sit_where_the_payloads_placement_rule_puts_them(out, name):
    payload = _load(name)
    vox = payload["voxels"]
    cubes = vox["cubes"]
    geometry = vox["geometry"]
    ix = _ordinals(cubes["ix"], cubes["dtype"]["ix"])
    iy = _ordinals(cubes["iy"], cubes["dtype"]["iy"])
    iz = _ordinals(cubes["iz"], cubes["dtype"]["iz"])
    got = out["events"][name]
    assert got["n"] == cubes["n"] == len(ix)
    if vox["regime"] == "cells":
        origin = geometry["origin_mm"]
        want = [[geometry["axes"][a]["coords"][index] - origin[k] for index in idx]
                for k, (a, idx) in enumerate(zip("xyz", (ix, iy, iz)))]
    else:
        grid = geometry["grid"]
        want = [[grid["x0"] + (i + 0.5) * grid["pitch_mm"] for i in ix],
                [grid["y0"] + (i + 0.5) * grid["pitch_mm"] for i in iy]]
        if grid["z_axis"] == "uniform":
            want.append([grid["z0"] + (i + 0.5) * grid["pitch_z_mm"] for i in iz])
        else:
            assert grid["z0"] is None
            want.append([geometry["axes"]["z"]["coords"][i] for i in iz])
    for axis, expected in zip("xyz", want):
        assert got[axis] == pytest.approx(expected, abs=1e-9), axis
    assert [got["box"][a] for a in "xyz"] == geometry["cube_mm"]


@pytest.mark.parametrize("name", EVENTS)
def test_event_flags_decode_to_shower_primary_and_below_floor(out, name):
    payload = _load(name)
    cubes = payload["voxels"]["cubes"]
    flags = _ordinals(cubes["flags"])
    bits = cubes["flag_bits"]
    got = out["events"][name]
    assert got["shower"] == [((f >> bits["shower"][0]) & 1) | (((f >> bits["shower"][1]) & 1) << 1) for f in flags]
    assert got["primary"] == [(f >> bits["primary"]) & 1 for f in flags]
    assert got["below"] == [(f >> bits["below_floor"]) & 1 for f in flags]
    assert sum(got["below"]) == payload["voxels"]["below_floor"]["n"]
    # A below-floor cube is drawn at the lowest colour: the ramp's first code.
    codes = _ordinals(cubes["code"])
    assert all(codes[i] == 1 for i, b in enumerate(got["below"]) if b)


@pytest.mark.parametrize("name", ENSEMBLES)
def test_ensemble_voxels_decode_from_their_layer_runs(out, name):
    payload = _load(name)
    vox, grid = payload["voxels"], payload["grid"]
    counts = _ordinals(vox["layer_counts"], "u16le")
    xy = _ordinals(vox["xy"], vox["dtype"]["xy"])
    got = out["ensembles"][name]
    assert len(counts) == grid["n"][2] == len(grid["z_centres"])
    assert sum(counts) == vox["n"] == got["n"]
    assert got["counts"] == counts == got["recount"]
    layers = [layer for layer, c in enumerate(counts) for _ in range(c)]
    assert got["layer"] == layers
    vx, vy, _ = grid["voxel_mm"]
    assert got["x"] == pytest.approx([grid["x_centre0"] + vx * xy[2 * i] for i in range(vox["n"])], abs=1e-9)
    assert got["y"] == pytest.approx([grid["y_centre0"] + vy * xy[2 * i + 1] for i in range(vox["n"])], abs=1e-9)
    # Depth from the grid's own centres: never assumed uniform.
    assert got["z"] == pytest.approx([grid["z_centres"][layer] for layer in layers], abs=1e-9)
    assert [got["box"][a] for a in "xyz"] == grid["voxel_mm"]


def test_the_d_frame_depth_is_native_and_not_uniform():
    payload = _load("voxels_base_canonical_shapcam")
    assert payload["grid"]["z_uniform"] is False
    event = _load("event_voxels_base_canonical")["voxels"]["geometry"]["grid"]
    assert event["z_axis"] == "native_layers" and event["z0"] is None


# ------------------------------------------------------------------ colour --


def _rgb_at(table: list[int], index: int) -> list[int]:
    return table[index * 3:index * 3 + 3]


@pytest.mark.parametrize("name", [n for n in EVENTS if n != "event_voxels_single_species"])
def test_event_codes_take_the_2d_panels_colour_at_the_same_index(out, name):
    payload = _load(name)
    scale = payload["voxels"]["scale"]
    got = out["events"][name]
    table = out["tables"]["puor_screen_linear" if scale.get("diverging") else "viridis"]
    for i, code in enumerate(got["code"]):
        rgba = got["rgba"][i * 4:i * 4 + 4]
        if code == 0:
            assert rgba[3] == 0, "code 0 carries no colour"
            continue
        assert rgba[:3] == _rgb_at(table, code) and rgba[3] == 255
    if scale.get("diverging"):
        # Zero sits at border grey, so a populated zero stays distinct from an empty voxel.
        assert scale["zero_code"] == 128
        assert tuple(_rgb_at(table, 128)) == BORDER
    values = got["values"]
    assert values[0] is None
    if scale["scale"] == "log10":
        assert values[1] == pytest.approx(10 ** scale["vmin"])
        assert values[3] == pytest.approx(10 ** scale["vmax"])
    else:
        assert values[1] == pytest.approx(scale["vmin"]) and values[3] == pytest.approx(scale["vmax"])


@pytest.mark.parametrize("name", ENSEMBLES)
def test_ensemble_codes_span_three_decades_and_fade_at_the_floor(out, name):
    payload = _load(name)
    scale = payload["scale"]
    got = out["ensembles"][name]
    signed = scale["scale"] == "signed_log10"
    table = out["tables"]["puor_screen" if signed else "viridis"]
    assert min(got["code"]) >= 2, "no undrawn code is shipped"
    for i, code in enumerate(got["code"]):
        rgba = got["rgba"][i * 4:i * 4 + 4]
        assert rgba == got["table"][code * 4:code * 4 + 4]
        assert rgba[:3] == _rgb_at(table, round((code - 2) / 253 * 255))
    # The taper: alpha rises from 0 at the floor to opaque half a decade above it.
    alpha = [got["table"][c * 4 + 3] for c in range(256)]
    assert alpha[0] == alpha[1] == 0 and alpha[255] == 255
    if signed:
        assert scale["split_code"] == 129
        assert alpha[128] == alpha[129] == 0 and alpha[2] == 255
        assert got["values"][0] == pytest.approx(-1.0) and got["values"][3] == pytest.approx(1.0)
        assert got["values"][1] == pytest.approx(-1e-3) and got["values"][2] == pytest.approx(1e-3)
        # Orange arm negative, purple arm positive.
        neg, pos = _rgb_at(table, 0), _rgb_at(table, 255)
        assert neg[0] > neg[2] and pos[2] > pos[1]
    else:
        assert got["values"][0] == pytest.approx(1e-3) and got["values"][3] == pytest.approx(1.0)


def test_species_take_the_qualitative_palette_with_grey_for_other(out):
    payload = _load("event_voxels_single_species")
    got = out["events"]["event_voxels_single_species"]
    palette = out["palette"]["qualitative"]["species"]
    for i, code in enumerate(got["code"]):
        rgba = got["rgba"][i * 4:i * 4 + 4]
        assert tuple(rgba[:3]) == _hex(palette[min(code, 7)]) and rgba[3] == 255
    assert payload["voxels"]["scale"]["other_code"] == 7
    other = _hex(palette[7])
    assert other[0] == other[1] == other[2], "other is a neutral grey"
    # The legend's counts are the server's, and the cubes it says are drawn are the decoded ones.
    legend = got["legend"]
    assert [row["code"] for row in legend] == [e["code"] for e in payload["voxels"]["species"]["legend"]]
    for row, entry in zip(legend, payload["voxels"]["species"]["legend"]):
        assert (row["cells"], row["primaryCells"], row["energyFraction"]) == (
            entry["cells"], entry["primary_cells"], entry["energy_fraction"])
        assert row["drawn"] == got["code"].count(row["code"]) == entry["cubes"]
    assert [row["label"] for row in legend] == ["e⁻", "e⁺", "γ", "n", "p"]


# ------------------------------------------------------------------ option --


@pytest.mark.parametrize("name", EVENTS + ENSEMBLES)
def test_the_box_is_one_to_one_to_one_in_millimetres(out, name):
    got = (out["events"] if name in out["events"] else out["ensembles"])[name]
    option = got["option"]
    span = option["bounds"]["span"]
    box = option["box"]
    s = box["S"]
    assert box["boxWidth"] == pytest.approx(s * span["z"])
    assert box["boxDepth"] == pytest.approx(s * span["x"])
    assert box["boxHeight"] == pytest.approx(s * span["y"])
    assert max(box["boxWidth"], box["boxDepth"], box["boxHeight"]) == pytest.approx(100)
    # The axes run over the shifted spans, labelled back in the frame's own millimetres.
    assert [(a["min"], a["max"]) for a in option["axes"]] == [(0, span["z"]), (0, span["x"]), (0, span["y"])]
    # The physical box: the server's window or grid extent, widened only to hold whole cubes.
    payload = _load(name)
    base = payload["window"]["axes"] if name in out["events"] else payload["grid"]["extent_mm"]
    lo, hi = option["bounds"]["lo"], option["bounds"]["hi"]
    for a in "xyz":
        assert lo[a] <= base[a][0] + 1e-9 and hi[a] >= base[a][1] - 1e-9
    if name not in out["events"]:
        for a in "xyz":
            assert (lo[a], hi[a]) == pytest.approx(tuple(base[a])), "the grid extent holds every voxel"


@pytest.mark.parametrize("name", EVENTS + ENSEMBLES)
def test_orthographic_unlit_cubes_float_on_invisible_silent_spacers(out, name):
    got = (out["events"] if name in out["events"] else out["ensembles"])[name]
    option = got["option"]
    grid = option["grid3D"]
    assert grid["viewControl"]["projection"] == "orthographic"
    assert grid["light"]["main"]["intensity"] == 0 and grid["postEffect"]["enable"] is False
    assert grid["environment"] == "none"
    lo = option["bounds"]["lo"]
    series = option["series"]
    roles = option["roles"]
    model_box = got["box"]
    bars = [s for s in series if s["type"] == "bar3D"]
    assert bars and all(s["shading"] == "color" and s["bevelSize"] == 0 for s in bars)
    # No raw value label beside a cube, at rest or on hover.
    assert all(s["labels"] == [False, False] for s in bars)
    drawn = []
    for k, role in enumerate(roles):
        s = series[k]
        if role["role"] == "spacer":
            assert s["silent"] and s["itemOpacity"] == 0
            cubes = series[k + 1]
            assert roles[k + 1]["role"] == "cube" and cubes["stack"] == s["stack"]
            assert roles[k + 1]["members"] == role["members"]
            for j, i in enumerate(role["members"]):
                spacer = s["data"][j]
                cube = cubes["data"][j]["value"]
                assert spacer[2] >= 0, "a spacer is never negative"
                assert spacer[2] + model_box["y"] / 2 + lo["y"] == pytest.approx(got["y"][i])
                assert cube[0] == pytest.approx(got["z"][i] - lo["z"]) and cube[1] == pytest.approx(got["x"][i] - lo["x"])
                assert cube[2] == pytest.approx(model_box["y"]) and cube[3] == i
                assert spacer[:2] == cube[:2]
            assert s["barSize"] == pytest.approx([option["box"]["S"] * model_box["z"], option["box"]["S"] * model_box["x"]])
            drawn += role["members"]
        if role["role"] == "cube":
            assert not s["silent"]
            for j, i in enumerate(role["members"]):
                item = s["data"][j]
                rgba = got["rgba"][i * 4:i * 4 + 4]
                assert item["color"] == f"rgb({rgba[0]},{rgba[1]},{rgba[2]})"
                assert item["opacity"] == pytest.approx(rgba[3] / 255)
    # Payload order (ascending energy) within each series, every coloured cube drawn once.
    for role in roles:
        assert role["members"] == sorted(role["members"])
    coloured = [i for i in range(got["n"]) if got["rgba"][i * 4 + 3] > 0]
    assert sorted(drawn) == coloured
    assert option["drawn"] == len(coloured) and option["noValue"] == got["n"] - len(coloured)
    # Translucent cubes live in their own series, so the opaque ones keep their depth writes.
    for role in roles:
        if role["role"] != "cube":
            continue
        alphas = {got["rgba"][i * 4 + 3] for i in role["members"]}
        assert all(a >= 0.99 * 255 for a in alphas) or all(a < 0.99 * 255 for a in alphas)


@pytest.mark.parametrize("name", EVENTS + ENSEMBLES)
def test_the_legend_recolours_nothing_and_says_provisional_where_the_payload_does(out, name):
    got = (out["events"] if name in out["events"] else out["ensembles"])[name]
    option = got["option"]
    payload = _load(name)
    scale = payload["voxels"]["scale"] if name in out["events"] else payload["scale"]
    if scale["scale"] == "categorical" or scale.get("degenerate"):
        assert option["visualMap"] is None
        return
    vm = option["visualMap"]
    assert vm["seriesIndex"] == []
    provisional = name not in out["events"] and bool(payload["frame"]["provisional"] or payload["rho"]["provisional"])
    assert vm["text"][0].startswith("provisional\n") == provisional
    _no_hyphen_numbers(option["strings"])
    assert option["tooltipConfine"] is False and option["tooltipAppendTo"] == "#tooltip-layer"


def test_primary_cubes_get_a_light_and_dark_halo_on_the_most_energetic(out):
    got = out["primaries"]
    option = got["option"]
    limit = got["limit"]
    assert option["primaries"] == 15 and option["halos"] == limit
    halos = [(s, r) for s, r in zip(option["series"], option["roles"]) if r["role"] == "halo"]
    assert len(halos) == 2 * limit
    tagged = sorted(got["tagged"], reverse=True)[:limit]
    assert [r["members"][0] for _, r in halos[::2]] == tagged
    for k, (s, _) in enumerate(halos):
        assert s["type"] == "line3D" and s["silent"] and len(s["data"]) == 16
        assert s["data"][0] == s["data"][4], "the path closes its first face"
        colour, width = (got["theme"]["text"], 3) if k % 2 == 0 else (got["theme"]["canvas"], 1.2)
        assert (s["lineStyle"]["color"], s["lineStyle"]["width"]) == (colour, width)
        # The 16-point path walks all 12 edges of one padded box.
        edges = {tuple(sorted((tuple(a), tuple(b)))) for a, b in zip(s["data"], s["data"][1:])}
        assert len(edges) == 12
    disclosed = " ".join(_note_lines(got["notes"]))
    assert "15 primary-tagged cubes drawn" in disclosed and f"at most {limit}" in disclosed


def test_hidden_species_are_not_drawn_and_are_disclosed(out):
    got = out["species"]
    base = out["events"]["event_voxels_single_species"]
    hidden_count = sum(1 for c in base["code"] if c in (0, 2))
    assert got["option"]["hidden"] == hidden_count
    assert got["option"]["drawn"] == base["n"] - hidden_count
    drawn = [i for r in got["option"]["roles"] if r["role"] == "cube" for i in r["members"]]
    assert all(base["code"][i] not in (0, 2) for i in drawn)
    assert [row["hidden"] for row in got["legend"]] == [row["code"] in (0, 2) for row in got["legend"]]
    lines = " ".join(_note_lines(got["notes"]))
    assert "the species toggles hide e⁻ and γ" in lines
    assert "species hidden" in got["notes"]["hazards"]


# ---------------------------------------------------------------- tooltips --


@pytest.mark.parametrize("name", EVENTS)
def test_event_tooltips_are_exact_for_the_brightest_and_say_so_otherwise(out, name):
    payload = _load(name)
    topk = {t["i"]: t for t in payload["voxels"]["topk"]}
    symbols = payload["voxels"]["symbols"]
    for i, tip in out["events"][name]["tips"]:
        assert tip.startswith(f"({symbols['x']}, {symbols['y']}, {symbols['z']}) = (")
        if payload["voxels"]["channel"] == "species":
            assert "Species " in tip
        elif i in topk:
            assert "(exact)" in tip
        else:
            assert "(from the colour code)" in tip or ": no value" in tip
        _no_hyphen_numbers([tip])


@pytest.mark.parametrize("name", ENSEMBLES)
def test_ensemble_tooltips_read_the_value_against_its_reference(out, name):
    payload = _load(name)
    ref = "cam_ref" if payload["scale"].get("ref_name") == "cam_ref" else "ρ_ref"
    tips = out["ensembles"][name]["tips"]
    exact = [tip for i, tip in tips if i == payload["topk"][0]["i"]]
    assert exact and "(exact)" in exact[0] and ref in exact[0] and "GeV mm⁻³ per event" in exact[0]
    for _, tip in tips:
        assert ref in tip
        _no_hyphen_numbers([tip])


# ----------------------------------------------------------------- palette --


def _lin(c: int) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _unlin(v: float) -> float:
    v = min(1.0, max(0.0, v))
    return 255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)


def _contrast(a, b) -> float:
    def lum(rgb):
        r, g, bb = (_lin(c) for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * bb
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


#: Machado, Oliveira & Fernandes (2009), severity 1, applied in linear RGB.
CVD = {
    "normal": None,
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
}


def _simulate(rgb, matrix):
    if matrix is None:
        return rgb
    linear = [_lin(c) for c in rgb]
    return tuple(_unlin(sum(m * c for m, c in zip(row, linear))) for row in matrix)


def _lab(rgb):
    r, g, b = (_lin(c) for c in rgb) if all(isinstance(c, int) for c in rgb) else (_lin(round(c)) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _de2000(lab1, lab2) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cb = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(cb ** 7 / (cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0
    dlp, dcp = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    else:
        dh = h2p - h1p
        dhp = dh if abs(dh) <= 180 else (dh - 360 if dh > 180 else dh + 360)
    dhhp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    lbp, cbp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dth = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cbp ** 7 / (cbp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / math.sqrt(20 + (lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * cbp, 1 + 0.015 * cbp * t
    rt = -math.sin(math.radians(2 * dth)) * rc
    return math.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dhhp / sh) ** 2 + rt * (dcp / sc) * (dhhp / sh))


def test_de2000_matches_the_published_reference_pairs():
    # Sharma, Wu & Dalal (2005), pairs 1, 7 and 17 of their test data.
    pairs = [((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
             ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
             ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492)]
    for lab1, lab2, want in pairs:
        assert _de2000(lab1, lab2) == pytest.approx(want, abs=1e-4)


#: Each palette: the surface it is drawn on, its 3:1 floor, and the worst pair
#: CIEDE2000 distance it must keep under every vision. The screen species
#: palette was chosen at 3.5:1 so no species is a dim cube in 3-D; print's
#: weaker figure is the most any eight ColorBrewer colours at 3:1 on white
#: reach, and no figure carries it (the 3-D cards never export).
PALETTE_CHECKS = {
    "species": (CARD, 3.5, 15.0),
    "species_print": (WHITE, 3.0, 5.5),
    "set2": (CARD, 3.0, 12.0),
    "dark2": (WHITE, 3.0, 12.0),
}


@pytest.mark.parametrize("name", sorted(PALETTE_CHECKS))
def test_every_checked_colour_clears_its_contrast_floor(out, name):
    surface, floor, _ = PALETTE_CHECKS[name]
    stops = out["palette"]["stops"][name]
    assert len(stops) == out["palette"]["checked"][name]
    for colour in stops:
        assert _contrast(_hex(colour), surface) >= floor, (name, colour)


@pytest.mark.parametrize("name", sorted(PALETTE_CHECKS))
def test_every_pair_stays_apart_under_simulated_colour_vision_deficiency(out, name):
    _, _, threshold = PALETTE_CHECKS[name]
    stops = [_hex(c) for c in out["palette"]["stops"][name]]
    worst = math.inf
    for vision, matrix in CVD.items():
        labs = [_lab(tuple(round(c) for c in _simulate(rgb, matrix))) for rgb in stops]
        for (i, a), (j, b) in itertools.combinations(enumerate(labs), 2):
            distance = _de2000(a, b)
            worst = min(worst, distance)
            assert distance >= threshold, (name, vision, stops[i], stops[j], round(distance, 2))
    assert worst < math.inf


def test_qualitative_stops_refuse_colours_nobody_measured(out):
    assert all(message and "checked" in message for message in out["palette"]["refusals"])
    assert "Unknown qualitative palette" in out["palette"]["unknown"]
    # Set2 and Dark2 keep ColorBrewer's first three in place.
    assert out["palette"]["stops"]["set2"][:3] == ["#66c2a5", "#fc8d62", "#8da0cb"]
    assert out["palette"]["stops"]["dark2"][:3] == ["#1b9e77", "#d95f02", "#7570b3"]
    assert len(out["palette"]["qualitative"]["species"]) == 8


# ------------------------------------------------------------------- notes --


@pytest.mark.parametrize("name", EVENTS)
def test_the_event_drawer_quotes_the_exception_and_the_servers_disclosures(out, name):
    notes = out["events"][name]["notes"]
    payload = _load(name)
    assert [s["heading"] for s in notes["sections"]] == ["Selection", "What is drawn", "Disclosures", "Marks and legend"]
    lines = " ".join(_note_lines(notes))
    assert "orthographic camera" in lines and "1:1:1" in lines and "no export" in lines
    for note in payload["voxels"]["notes"]:
        assert re.sub(r"\s+", " ", note).strip() in lines
    assert re.sub(r"\s+", " ", payload["voxels"]["scale"]["floor_rule"]).strip() in lines
    assert "hides whatever lies behind it" in lines
    if payload["voxels"]["cap"]["n_beyond"]:
        assert "cap reached" in notes["hazards"]
    _no_hyphen_numbers(_note_lines(notes))


@pytest.mark.parametrize("name", ENSEMBLES)
def test_the_ensemble_drawer_states_the_five_energy_fractions_and_no_axis(out, name):
    notes = out["ensembles"][name]["notes"]
    payload = _load(name)
    lines = " ".join(_note_lines(notes))
    for part in ("drawn", "below the 10⁻³ floor", "beyond the cap", "half-width edge voxels", "outside the grid"):
        assert part in lines
    assert "No ensemble direction is drawn on the cloud" in lines
    for notice in payload["meta"]["notices"]:
        assert re.sub(r"\s+", " ", notice).strip() in lines
    assert payload["frame"]["comb_source"] in lines
    assert ("provisional range" in notes["hazards"]) == bool(payload["frame"]["provisional"] or payload["rho"]["provisional"])
    if payload["frame"]["n_label"]:
        assert payload["frame"]["n_label"] in lines
    _no_hyphen_numbers(_note_lines(notes))


def test_a_projection_drawer_keeps_the_panels_notes_and_adds_the_pairing(out):
    notes = out["notes"]["projection"]
    assert notes["title"] == "v–w Projection"
    drawn = next(s for s in notes["sections"] if s["heading"] == "What is drawn")
    assert drawn["lines"][-1] == "Paired with the 3-D cloud."
    assert len(drawn["lines"]) > 1


# --------------------------------------------------------- views and plans --


def test_the_event_view_pairs_with_a_raster_frame_and_one_raster_shower(out):
    base = out["views"]["experiment_baseline"]
    assert base["offer"] == base["wholePlan"], "the voxels block or the whole plan"
    canonical = base["views"]["canonical|energy|both"]["event"]
    assert canonical["frame"] == "lab" and any("no D-frame raster" in n for n in canonical["notes"])
    assert canonical["shower"] == "both" and canonical["rasterShower"] == "a" and canonical["projectionNote"]
    local = base["views"]["local|energy|both"]["event"]
    assert local["shower"] == "a" and any("Absolute frame only" in n for n in local["notes"])
    for key, view in base["views"].items():
        requests = view["eventRequests"]
        raster, voxels = requests["raster"], requests["voxels"]
        assert raster["params"]["shower"] in ("a", "b") and "format" not in raster["params"]
        assert voxels["params"]["format"] == "voxels" and voxels["params"]["frame"] in ("lab", "trans", "local")
        assert voxels["params"]["frame"] == view["event"]["frame"]
        assert (voxels["params"].get("model") == "energy") == (voxels["params"]["channel"] in ("gradcam", "shapcam"))
        assert "coordinates" not in voxels["params"] and "cap" not in voxels["params"]
        assert (raster["abortKey"], voxels["abortKey"]) == ("vox-event-2d", "vox-event-3d")
        assert view["noGl"] is None


def test_the_ensemble_view_is_co_registered_and_gates_its_parameters(out):
    for table in ("experiment_baseline", "single_hits"):
        for key, view in out["views"][table]["views"].items():
            requests = view["ensembleRequests"]
            voxels, projections = requests["voxels"], requests["projections"]
            frame = voxels["params"]["frame"]
            assert frame in ("local", "canonical"), "never trans, never lab"
            assert ("anchor" in voxels["params"]) == (frame == "canonical") == ("anchor" in projections["params"])
            assert "coordinates" not in voxels["params"]
            assert projections["params"]["display"] == "native" and projections["params"]["rho_norm"] == "selection"
            assert projections["params"]["channel"] == voxels["params"]["channel"]
            assert (voxels["abortKey"], projections["abortKey"]) == ("vox-ens-3d", "vox-ens-2d")
    single = out["views"]["single_hits"]
    for view in single["views"].values():
        assert view["ensemble"]["frame"] == "local" and view["ensemble"]["channel"] == "density"
        assert view["event"]["channel"] in ("energy", "species") and view["event"]["shower"] == "a"
    assert single["views"]["lab|shapcam|a"]["event"]["notes"][0].startswith("Drawn by Deposited energy")
    events_only = out["views"]["single_events"]
    assert events_only["offer"]["shown"] is False
    assert all(v["eventRequests"] is None and v["ensembleRequests"] is None for v in events_only["views"].values())
    assert out["pick"] == {"route": "/api/event/pick", "abortKey": "vox-pick",
                           "params": {"table_name": "t", "e1_min": 1, "rule": "densest"}}


# ----------------------------------------------------------------- section --


def test_the_section_builds_its_cards_with_export_on_the_projections_only(out):
    cards = out["section"]["base"]["cards"]
    assert list(cards) == ["vox-event", "vproj-xy", "vproj-xz", "vproj-yz",
                           "vox-ensemble", "eproj-xy", "eproj-yz", "eproj-xz"]
    for card_id, card in cards.items():
        gl = card_id.startswith("vox-")
        assert card["panel"] == card_id and card["inspect"] == 1
        assert card["plotId"] == f"plot-{card_id}" and card["titleId"] == f"title-{card_id}"
        assert card["exportButtons"] == (0 if gl else 1)
        assert ("voxel-3d" in card["classes"]) == gl
        assert card["exportTarget"] is None if gl else card["exportTarget"] == ["panel", "meta"]
    # A foreign id is not this section's: undefined, which JSON drops.
    assert "foreign" not in out["section"]["base"]
    assert out["section"]["base"]["has"] is True


def test_the_densest_event_is_asked_for_when_the_link_names_none(out):
    base = out["section"]["base"]
    paths = [(path, q) for path, q in base["requests"]]
    assert paths[0] == ("/api/event/pick", {"table_name": "experiment_baseline", "rule": "densest"})
    event = [q for path, q in paths if path == "/api/event"]
    assert {q.get("event_number") for q in event} == {"0"}
    assert any(q.get("format") == "voxels" for q in event) and any("format" not in q for q in event)
    assert {path for path, _ in paths} == {"/api/event/pick", "/api/event", "/api/voxels", "/api/projections"}
    cards = base["cards"]
    assert "the densest event of the selection" in cards["vox-event"]["sparse"]
    assert cards["vox-event"]["notes"]["headings"] == ["Selection", "What is drawn", "Disclosures", "Marks and legend"]
    assert base["refreshError"] is None and base["errors"] == []
    # A pinned event is never re-picked, and the network is named for a CAM channel.
    pinned = out["section"]["pinned"]["requests"]
    assert not any(path == "/api/event/pick" for path, _ in pinned)
    voxels = next(q for path, q in pinned if path == "/api/event" and q.get("format") == "voxels")
    assert (voxels["event_number"], voxels["frame"], voxels["channel"], voxels["model"]) == ("7", "local", "shapcam", "angle")


def test_at_most_two_webgl_charts_and_a_lost_context_says_so(out):
    base = out["section"]["base"]
    assert base["charts"] == 2 and all(n >= 1 for n in base["glOptions"])
    assert base["lost"]["kind"] == "notice" and "withdrew this view's WebGL context" in base["lost"]["message"]
    assert "3-D view not drawn" in base["lost"]["hazards"]
    # Restored: the dead chart is disposed and one new chart takes its place.
    assert base["restored"]["message"] is None
    assert base["restored"]["disposed"] == 1 and base["restored"]["charts"] == 3
    # An experiment change clears the charts and forgets the payloads.
    live = [n for n in base["afterReset"]["cleared"] if n is not None]
    assert len(live) == 2 and all(n >= 1 for n in live)
    assert base["afterReset"]["notes"] is None


def test_without_webgl_the_3d_cards_say_so_and_the_projections_still_load(out):
    no_gl = out["section"]["noGl"]
    assert no_gl["charts"] == 0
    assert not any(q.get("format") == "voxels" for path, q in no_gl["requests"])
    assert not any(path == "/api/voxels" for path, _ in no_gl["requests"])
    for card_id in ("vox-event", "vox-ensemble"):
        card = no_gl["cards"][card_id]
        assert card["kind"] == "notice" and "WebGL is not available" in card["message"]
    rendered = {card_id for card_id, _ in no_gl["renders"]}
    assert len(no_gl["renders"]) == 6 and len({r[0] for r in no_gl["renders"]}) == 6
    assert rendered


def test_a_refused_3d_half_shows_its_reason_beside_the_card_and_keeps_the_projections(out):
    refused = out["section"]["refused"]
    card = refused["cards"]["vox-event"]
    assert card["kind"] == "error" and card["message"] == "The 3-D view is shut for this test."
    assert all(refused["cards"][f"vproj-{c}"]["message"] is None for c in ("xy", "xz", "yz"))
    assert refused["cards"]["vox-ensemble"]["message"] is None
    assert refused["refreshError"] and "shut for this test" in refused["refreshError"]


def test_a_single_shower_offers_its_own_channels_and_no_shower_toggle(out):
    single = out["section"]["single"]
    cards = single["cards"]
    event = cards["vox-event"]
    assert event["showersHidden"] is True
    options = {value: (disabled, title) for value, disabled, title in event["options"]}
    assert options["species"][0] is False and options["energy"][0] is False
    assert options["gradcam"][0] is True and "no reconstruction-network outputs" in options["gradcam"][1]
    ensemble = cards["vox-ensemble"]
    assert ensemble["caption"] and "Drawn by" in ensemble["caption"]
    channels = {q.get("channel") for path, q in single["requests"] if path == "/api/voxels"}
    assert channels == {"density"}
    species = next(q for path, q in single["requests"] if path == "/api/event" and q.get("format") == "voxels")
    assert species["channel"] == "species" and species["event_number"] == "3"


def test_an_events_only_experiment_shows_no_3d_views_and_asks_for_nothing(out):
    events = out["section"]["events"]
    assert events["requests"] == []
    assert all(card["pairHidden"] for card in events["cards"].values())
    assert events["charts"] == 0
