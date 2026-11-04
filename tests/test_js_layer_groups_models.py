"""Longitudinal Channels on the Models page (Page 2), under Node.

Stage 2 of the layer-groups work (brief section 7): the page draws boundaries
only, beside the slice bracket, and never pools.

* ``models_main.js`` mounts the control once with page ``models``, feeds it the
  lattice's layer count, the frame, the 3-D cards' availability and the depth
  block of the payload in hand, and wires ``#info-lgroups``; the control,
  mounted that way, disables Pooled with the page's reason and keeps the
  stored mode;
* ``voxel_views.js`` gives every paired depth projection its options from the
  payload in hand: the event pair's from the frame's ``layer_planes``, the
  selection's (and the cloud's) from ``depth_layers``; a link with
  ``lgmode=pool`` still draws boundaries (never a pooled spec); the strip and
  seams are not drawn for ``off``, where ``layerAxis`` still names the layer;
* no request of the page carries ``depth_groups``;
* a change of mode, of partition or a live draft repaints the depth panels
  with zero requests and without touching the XY panel, and the hover of one
  depth panel spotlights the same group on its partner.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest
from test_js_layer_groups_state import _CONTROL_SCRIPT
from test_js_physics_shell import JS, NODE, PAYLOADS
from test_js_voxels import _SCRIPT as _VOXEL_SCRIPT

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

ROOT = JS.parent.parent.parent
EM_56 = [2, 2, 3, 3, 3, 4, 4, 4, 4, 4, 5, 6, 12]

# The voxel harness up to its first import: the fake DOM and the file helpers.
_VOXEL_HEAD = _VOXEL_SCRIPT.split("const v = await imp('voxels.js');")[0] % {"events": "[]", "ensembles": "[]"}

_SECTION_SCRIPT = _VOXEL_HEAD + r"""
const vv = await imp('voxel_views.js');
const caps = await imp('capabilities.js');
const eventBody = load('event_raster_base');
const exp = load('experiments').experiments.find((e) => e.table_name === 'experiment_baseline');

class FakeProjection {
  constructor(id, opts) { this.id = id; this.isometric = opts.isometric; this.element = { clientWidth: 600, clientHeight: 400 }; this.lastOpts = null; this.calls = []; this.highlights = []; }
  render(payload, opts) { this.payload = payload; this.lastOpts = opts; this.calls.push('render'); }
  setLayerGroups(spec, extra = {}) {
    this.lastOpts = { ...this.lastOpts, layerGroups: spec ?? null };
    if ('reserveTop' in extra) this.lastOpts.reserveTop = extra.reserveTop;
    this.calls.push('setLayerGroups');
  }
  // The pair's shared band (UI-6) is recorded, not counted as a repaint of the XY panel.
  setReserveTop(r) { this.lastOpts = { ...this.lastOpts, reserveTop: r ?? null }; this.reserves = [...(this.reserves ?? []), r ?? null]; }
  setGroupHighlight(g) { this.highlights.push(g); }
  setOverlay() {} clear() {} relayout() {} setBusy() {} currentView() { return null; }
}

async function run({ scope, lgmode = 'off', counts = null, frame = 'lab', projections = null }) {
  const requests = [];
  globalThis.fetch = async (url) => {
    const u = new URL(String(url));
    const q = Object.fromEntries(u.searchParams.entries());
    requests.push([u.pathname, q]);
    const json = (body) => ({ ok: true, status: 200, statusText: '', json: async () => body });
    if (u.pathname === '/api/event/pick') return json({ event_number: 0, rule: 'densest rule', rule_id: 'densest' });
    if (u.pathname === '/api/event' && q.format === 'voxels') return json(load('event_voxels_base_lab'));
    if (u.pathname === '/api/event') return json(eventBody);
    if (u.pathname === '/api/voxels') return json(load('voxels_base_local'));
    if (u.pathname === '/api/projections') return json(projections ?? load('projections_base_lab'));
    if (u.pathname === '/api/selection-cells') return json(load('selection_cells_base'));
    return { ok: false, status: 404, statusText: '', json: async () => ({ detail: 'no such route' }) };
  };
  const state = {
    values: { table_name: 'experiment_baseline', voxel_scope: scope, voxel_event: null, voxel_shower: 'a',
      voxel_channel: 'energy', ens_channel: 'density', frame, model: 'segmentation', palette: 'viridis',
      anchor: 'backprojected', lgmode },
    get(k) { return this.values[k]; },
    set(patch) { Object.assign(this.values, patch); return true; },
    filterParams() { return { table_name: this.values.table_name }; },
    isTouched: () => false,
    layerGroups() {
      const L = 56;
      const u = [5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4];
      return { mode: this.values.lgmode, counts: this.values.lgcounts ?? u, fallback: false, L };
    },
  };
  if (counts) state.values.lgcounts = counts;
  let draft = null;
  const contexts = [];
  const rendered = [];
  const host = new El('section');
  const section = new vv.VoxelSection(host, {
    state, getExperiment: () => exp, webgl: false, ProjectionClass: FakeProjection,
    onRendered: (id) => rendered.push(id), onError: () => {},
    draftCounts: () => draft, onDepthContext: (b) => contexts.push(b ? (b.numbering + ':' + (b.edges_mm?.length ?? 0)) : null),
  });
  section.applyPlan(caps.page2Plan(exp).voxels);
  await section.refresh();
  const panels = Object.fromEntries([['xy', 'm-event-xy'], ['yz', 'm-event-yz'], ['xz', 'm-event-xz']].map(([col]) => [col, null]));
  const depth = (pair) => Object.fromEntries(pair.cells.map((r) => [r.spec.col, r.panel]));
  const describe = (panel) => {
    const spec = panel.lastOpts.layerGroups ?? null;
    return {
      keys: Object.keys(panel.lastOpts).sort(),
      spec: spec && { mode: spec.mode, pooled: spec.pooled, counts: spec.counts, numbering: spec.numbering, groups: spec.groups.length,
        seams: spec.seams.length, basis: spec.axis.source, nEvents: spec.nEvents, highlight: spec.highlight,
        tip: spec.groups[0]?.tooltip ?? null },
      reserveTop: panel.lastOpts.reserveTop ?? null,
      axis: panel.lastOpts.layerAxis ? { source: panel.lastOpts.layerAxis.source, numbering: panel.lastOpts.layerAxis.numbering } : null,
      calls: [...panel.calls],
    };
  };
  const result = { requests: requests.map(([p, q]) => [p, q]), ids: section.ids() };
  const pair = section.pairs.event;
  const cells = depth(pair);
  result.start = Object.fromEntries(Object.entries(cells).map(([c, p]) => [c, describe(p)]));
  result.contexts = [...contexts];
  const before = requests.length;
  const renderedBefore = rendered.length;
  state.set({ lgmode: 'bounds' });
  section.setLayerGroups();
  result.afterBounds = Object.fromEntries(Object.entries(cells).map(([c, p]) => [c, describe(p)]));
  draft = EM_56;
  section.setLayerGroups();
  result.afterDraft = Object.fromEntries(Object.entries(cells).map(([c, p]) => [c, describe(p)]));
  draft = null;
  state.set({ lgmode: 'pool' });
  section.setLayerGroups();
  result.afterPool = describe(cells.yz);
  state.set({ lgmode: 'off' });
  section.setLayerGroups();
  result.afterOff = describe(cells.yz);
  result.repaintRequests = requests.length - before;
  result.repaintNotes = rendered.length - renderedBefore;
  // The pair's hover: the strip's onHover reaches the partner.
  state.set({ lgmode: 'bounds' });
  section.setLayerGroups();
  cells.yz.lastOpts.layerGroups.onHover(3);
  result.highlights = { yz: cells.yz.highlights, xz: cells.xz.highlights, xy: cells.xy.highlights };
  result.notes = section.notes('vox-event-yz') ? true : false;
  result.ensemble = section.pairs.ensemble
    ? Object.fromEntries(section.pairs.ensemble.cells.filter((r) => r.panel).map((r) => [r.spec.col, describe(r.panel)])) : null;
  result.noteIds = section.ids();
  return result;
}

const EM_56 = %(em56)s;
const out = {};
out.event = await run({ scope: 'event' });
out.eventPool = await run({ scope: 'event', lgmode: 'pool' });
out.selection = await run({ scope: 'selection' });
// LG-G6: a per-shower translated cloud whose frame co-registered one of the selection's two events.
const transBody = load('projections_base_trans');
transBody.frame.n_events = 1;
transBody.selection.n_events = 2;
out.transCloud = await run({ scope: 'event', frame: 'trans', lgmode: 'bounds', projections: transBody });
console.log(JSON.stringify(out));
"""

_MODELS_CONTROL = _CONTROL_SCRIPT.split("// --- the sidebar on the Physics page")[0] + r"""
build();
const contexts = [];
const s = fresh('#table_name=t&lgmode=pool');
const control = mountLayerGroupControl({ state: s, page: 'models', doc: document });
control.setExperiment({ nLayers: 56 });
const side = () => ({
  hidden: byId('group-lgroups').hidden,
  checked: ['off', 'bounds', 'pool'].filter((m) => byId(`lgmode-${m}`).checked),
  poolDisabled: byId('lgmode-pool').disabled,
  poolTitle: byId('lgmode-pool-label').title,
  notice: byId('lgroups-notice').hidden ? null : byId('lgroups-notice').textContent,
});
const res = { mounted: side(), mode: s.get('lgmode') };
control.setAvailable(false, 'No 3-D views here.');
res.unavailable = side();
control.setAvailable(true);
s.set({ lgmode: 'bounds' });
res.bounds = side();
console.log(JSON.stringify(res));
"""


def _node(script: str, args: list) -> dict:
    done = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(args)],
                          capture_output=True, text=True, timeout=180, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def sections() -> dict:
    script = _SECTION_SCRIPT % {"em56": json.dumps(EM_56)} if "%(em56)s" in _SECTION_SCRIPT else _SECTION_SCRIPT
    return _node(script, [JS.as_uri(), str(PAYLOADS)])


@pytest.fixture(scope="module")
def control() -> dict:
    return _node(_MODELS_CONTROL, [(JS / "state.js").as_uri(), (JS / "controls" / "layer_groups_control.js").as_uri()])


def _source(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


def test_the_page_mounts_the_control_once_for_models_and_feeds_it():
    src = _source("models_main.js")
    assert len(re.findall(r"mountLayerGroupControl\(", src)) == 1
    assert re.search(r"mountLayerGroupControl\(\{[^}]*page: 'models'", src, re.S)
    assert "setExperiment({ nLayers:" in src and "lattice?.z?.n" in src
    for call in ("lgControl.setFrame(", "lgControl.setAvailable(", "lgControl.setDepthContext(", "depthContextFromPayload("):
        assert call in src
    assert "getElementById('info-lgroups')" in src and "dataset.notices" in src
    assert "layerPool" not in src and "depth_groups" not in src.replace("`depth_groups`", "")


def test_the_control_on_the_models_page_disables_pooled_with_its_reason_and_keeps_the_mode(control):
    mounted = control["mounted"]
    assert mounted["hidden"] is False
    assert mounted["poolDisabled"] is True
    assert "Pooling re-bins the Physics page" in mounted["poolTitle"]
    assert mounted["checked"] == ["pool"] and control["mode"] == "pool", "the stored mode is kept"
    assert "Boundaries are drawn instead" in mounted["notice"]
    assert control["unavailable"]["hidden"] is True
    assert control["bounds"]["checked"] == ["bounds"] and control["bounds"]["poolDisabled"] is True


def test_a_link_with_pooled_draws_boundaries_never_a_pooled_spec(sections):
    for col in ("yz", "xz"):
        spec = sections["eventPool"]["start"][col]["spec"]
        assert spec is not None and spec["mode"] == "bounds" and spec["pooled"] is False
        assert spec["groups"] == 13 and spec["seams"] == 12
    assert sections["eventPool"]["start"]["xy"]["spec"] is None


def test_the_event_pair_takes_its_specs_from_layer_planes_and_the_selection_from_depth_layers(sections):
    event = sections["eventPool"]["start"]["yz"]
    assert event["spec"]["basis"] == "event" and event["spec"]["nEvents"] == 1
    assert event["spec"]["numbering"] == "detector"
    selection = sections["selection"]["start"]["yz"]
    assert selection["spec"] is None, "off draws no partition"
    assert selection["axis"]["source"] == "ensemble"
    drawn = sections["selection"]
    assert drawn["contexts"] and drawn["contexts"][-1].startswith("detector:")
    bounds = drawn["afterBounds"]["xz"]["spec"]
    assert bounds["basis"] == "ensemble" and bounds["nEvents"] == 2 and bounds["groups"] == 13


def test_off_draws_no_partition_but_names_the_layer(sections):
    for col in ("yz", "xz"):
        start = sections["event"]["start"][col]
        assert start["spec"] is None
        assert start["axis"] == {"source": "event", "numbering": "detector"}
    assert sections["event"]["start"]["xy"]["axis"] is None
    assert "layerAxis" not in sections["event"]["start"]["xy"]["keys"]


def test_no_request_of_the_page_carries_depth_groups(sections):
    for name in ("event", "eventPool", "selection"):
        assert sections[name]["requests"], name
        for _path, query in sections[name]["requests"]:
            assert "depth_groups" not in query


def test_a_change_of_mode_partition_or_draft_repaints_with_zero_requests(sections):
    for name in ("event", "selection"):
        run = sections[name]
        assert run["repaintRequests"] == 0
        assert run["repaintNotes"] > 0, "the drawers are rebuilt from the same call"
        for col in ("yz", "xz"):
            assert run["afterBounds"][col]["spec"]["mode"] == "bounds"
            assert run["afterBounds"][col]["calls"][-1] == "setLayerGroups"
            assert run["afterDraft"][col]["spec"]["counts"] == EM_56, "a live draft is drawn"
        assert run["afterBounds"]["xy"]["calls"] == ["render"], "the XY panel is never repainted"
        assert run["afterPool"]["spec"]["mode"] == "bounds" and run["afterPool"]["spec"]["pooled"] is False
        assert run["afterOff"]["spec"] is None and run["afterOff"]["axis"] is not None


def test_hovering_a_strip_segment_spotlights_the_partner_depth_panel(sections):
    for name in ("event", "selection"):
        highlights = sections[name]["highlights"]
        assert highlights["yz"] == [3] and highlights["xz"] == [3]
        assert highlights["xy"] == []


def test_the_notes_builder_receives_the_drawn_spec():
    src = _source("voxel_views.js")
    assert "layerGroups: record.panel?.lastOpts?.layerGroups ?? null" in src


def test_ui6_a_pairs_three_projections_reserve_one_band(sections):
    """UI-6: with Boundaries on, the XY projection reserves the depth panels' band, so the pair keeps one scale."""
    for name in ("event", "selection"):
        run = sections[name]
        for col in ("xy", "yz", "xz"):
            assert run["start"][col]["reserveTop"] is None, (name, col)
            assert run["afterBounds"][col]["reserveTop"] == "strip", (name, col)
        assert run["afterOff"]["reserveTop"] is None


def test_lg_g6_the_cloud_projections_print_the_frames_own_event_count(sections):
    ensemble = sections["transCloud"]["ensemble"]
    assert ensemble, "the cloud's projections were drawn"
    for col in ("yz", "xz"):
        spec = ensemble[col]["spec"]
        assert spec["nEvents"] == 1, spec
        assert " · N = 1 event" in spec["tip"]
