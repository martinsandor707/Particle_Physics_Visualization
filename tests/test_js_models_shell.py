"""The Models page's shell, executed under Node against the recorded payloads.

What the page shows for an experiment is decided from its capability block
(``capabilities.js`` ``page2Plan``), checked on the recorded catalogue of all
three kinds (``tests/fixtures/payloads/experiments.json``) and on a
**hand-made copy** of its event-level aggregate with an XGBoost model run
paired and the ``xgboost`` gate open: the backend's recording of such an
experiment does not exist yet, so the copy states what that block is expected
to carry (``model_runs`` per xgboost.md section 2.4, the ``xgboost`` gate and
the performance gates open). Replace it with the recording once there is one.

Around the plan:

* ``state.js``: the Models page's keys round-trip through the hash, an
  invalid value keeps the default, a default is never written, a link with
  any of them is not a cold boot, and ``event`` is never touched by them;
* ``models_cards.js``: each card's request per kind (routes, parameters,
  abort keys), the segmentation network's notice, the frame fallbacks; on a
  fake document the cards' anatomy, one request shared by the cards that read
  it, a refusal that stays refused, a transient failure that is retried, a
  panel module not built yet, a response that lands after an experiment
  switch, the notes routed by builder name and the export targets;
* ``page_common.js``: the page tabs' hrefs carry the hash at click time;
* ``controls/admin.js``: the model-runs list read defensively.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _path, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: The hand-made aggregate with a paired model run (see the module docstring).
_OPEN_GATE = r"""
const openGate = (catalogue) => {
  const e = structuredClone(catalogue.experiments.find((x) => x.capabilities.kind === 'single_shower_events'));
  e.table_name = 'electron_s1_aggr';
  e.capabilities.model_runs = [
    { task: 'momentum', species: 'electron', seed: 1, model_file: 'xgboost_electron/standalone_momentum_s1_model.json',
      labels: ['incoming_momentum'], n_holdout: 19951, split_reproduced: true, status: 'done' },
    { task: 'angle', species: 'electron', seed: 1, model_file: 'xgboost_electron/standalone_angle_s1_model.json',
      labels: ['incoming_phi', 'incoming_theta'], n_holdout: 19951, split_reproduced: true, status: 'done' },
  ];
  for (const id of ['xgboost', 'perf-bins', 'pred-truth', 'pred-residuals']) {
    e.capabilities.panels[id] = true;
    delete e.capabilities.reasons[id];
  }
  return e;
};
"""

# ----------------------------------------------------------- the plan --

_PLAN_SCRIPT = _FAKE_DOM + _OPEN_GATE + r"""
const [capsUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const caps = await import(capsUrl);
const out = {};
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
out.plans = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, caps.page2Plan(e)]));
out.open = caps.page2Plan(openGate(catalogue));
// A run paired but its analysis still running: the section shows, its cards say why.
const running = openGate(catalogue);
running.capabilities.panels.xgboost = false;
running.capabilities.reasons.xgboost = 'Analysing: 3 of 7 steps.';
running.capabilities.model_runs[0].status = 'running';
out.running = caps.page2Plan(running);
out.legacy = caps.page2Plan({ table_name: 'old', status: 'ready' });
out.none = caps.page2Plan(null);
out.texts = { missing: caps.MODELS_MISSING_PREDICTIONS, instead: caps.MODELS_XGB_INSTEAD, xgb: caps.XGB_NOTICE,
  events: caps.MODELS_EVENTS_ONLY };
const all = ['lab', 'trans', 'local', 'canonical'];
out.frames = {
  featuresCanonical: caps.viewFrame('features', 'canonical', all, 2),
  featuresLocal: caps.viewFrame('features', 'local', all, 2),
  ensembleLab: caps.viewFrame('ensemble', 'lab', all, 2),
  ensembleSingleTrans: caps.viewFrame('ensemble', 'trans', ['lab', 'trans', 'local'], 1),
  eventCanonicalSingle: caps.viewFrame('event', 'canonical', ['lab', 'trans', 'local'], 1),
  network: caps.viewFrame('network', 'canonical', all, 2),
  none: caps.viewFrame('features', 'lab', [], 1),
};
out.sectionIds = caps.PAGE2_SECTIONS;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def plan_results() -> dict:
    return _run(_PLAN_SCRIPT, [(JS / "capabilities.js").as_uri(), _path("experiments")])


PERF = ["perf-bins", "pred-truth", "pred-residuals"]
XGB = ["xgb-cv", "xgb-binary", "xgb-surrogate", "xgb-importance"]
FEATURES = ["feat-table", "feat-corr", "feat-hist", "feat-hist2d"]


def _reason(kind: str, gate: str) -> str:
    """The recorded catalogue's reason for one gate of the experiment of one kind."""
    payload = json.loads(Path(_path("experiments")).read_text(encoding="utf-8"))
    (experiment,) = [e for e in payload["experiments"] if e["capabilities"]["kind"] == kind]
    return experiment["capabilities"]["reasons"][gate]


def test_the_two_shower_plan_offers_every_network_view_and_no_xgboost(plan_results):
    plan = plan_results["plans"]["two_shower_hits"]
    assert plan["sections"] == {"perf": True, "xgb": False, "features": True, "primaries": True, "voxels": True}
    for card in PERF + FEATURES:
        assert plan["cards"][card] == {"shown": True, "enabled": True, "reason": None}, card
    # The primaries need species: the card is on show, shut with the server's reason.
    prim = plan["cards"]["prim-rate"]
    assert prim["shown"] is True and prim["enabled"] is False and "particle_type" in prim["reason"]
    for card in XGB:
        assert plan["cards"][card]["shown"] is False
    assert plan["banner"] is None and plan["networks"] is True
    assert plan["models"] == ["angle", "energy", "segmentation"]
    assert plan["xgbNotice"].startswith(plan_results["texts"]["xgb"])
    # The notice carries the server's own reason, whatever its wording.
    assert _reason("two_shower_hits", "xgboost") in plan["xgbNotice"]
    assert plan["frames"]["offered"] == ["lab", "trans", "local", "canonical"]
    assert plan["frames"]["transPrimary"] is False and plan["frames"]["labels"] is None
    vox = plan["voxels"]
    assert vox["event"]["frames"] == ["lab", "trans", "local", "canonical"]
    assert vox["event"]["channels"] == ["energy", "gradcam", "shapcam", "segerr"]
    assert "species" in vox["event"]["disabledChannels"]
    assert vox["ensemble"]["frames"] == ["local", "canonical"]
    assert vox["ensemble"]["channels"] == ["density", "gradcam_energy", "shapcam_energy"]
    assert plan["xgb"] == {"tasks": [], "labels": {}, "status": "none", "runs": [],
                           "reason": plan["reasons"]["xgboost"], "splitReproduced": True}


def test_a_single_shower_plan_hides_the_network_cards_and_says_so(plan_results):
    plan = plan_results["plans"]["single_shower_hits"]
    assert plan["sections"] == {"perf": False, "xgb": False, "features": True, "primaries": True, "voxels": True}
    assert plan["cards"]["prim-rate"] == {"shown": True, "enabled": True, "reason": None}
    assert plan["banner"] == plan_results["texts"]["missing"]
    assert plan["networks"] is False and plan["models"] == []
    assert plan["frames"]["offered"] == ["lab", "trans", "local"]
    assert "canonical" in plan["frames"]["disabled"] and "two showers" in plan["frames"]["disabled"]["canonical"]
    assert plan["frames"]["transPrimary"] is True and plan["frames"]["labels"]["trans"]["label"] == "Translated"
    vox = plan["voxels"]
    assert vox["species"] is True and vox["nShowers"] == 1 and vox["showers"] == ["a"]
    assert vox["event"]["channels"] == ["energy", "species"]
    assert set(vox["event"]["disabledChannels"]) == {"gradcam", "shapcam", "segerr"}
    assert vox["ensemble"]["frames"] == ["local"] and vox["ensemble"]["channels"] == ["density"]
    assert [a["key"] for a in plan["axes"]] == ["e1"]


def test_the_events_only_plan_keeps_the_features_and_hides_the_hit_sections(plan_results):
    plan = plan_results["plans"]["single_shower_events"]
    assert plan["sections"] == {"perf": False, "xgb": False, "features": True, "primaries": False, "voxels": False}
    for card in FEATURES:
        assert plan["cards"][card]["enabled"] is True
    assert plan["cards"]["vox-event"]["shown"] is False
    assert plan["notices"] == [plan_results["texts"]["events"]]
    assert plan["frames"]["offered"] == [] and plan["spatial"] is False
    assert plan["banner"] == plan_results["texts"]["missing"]
    assert plan["voxels"]["event"]["enabled"] is False and "no hits" in plan["voxels"]["event"]["reason"]


def test_a_paired_aggregate_opens_the_xgboost_section_and_hides_its_notice(plan_results):
    """On the hand-made copy with the gate open (module docstring)."""
    plan = plan_results["open"]
    assert plan["sections"]["xgb"] is True and plan["sections"]["perf"] is True
    for card in XGB:
        assert plan["cards"][card] == {"shown": True, "enabled": True, "reason": None}, card
    assert plan["xgbNotice"] is None
    # No networks, but real XGBoost predictions: the banner says which are drawn.
    assert plan["banner"] == plan_results["texts"]["instead"]
    assert plan["xgb"]["tasks"] == ["momentum", "angle"]
    assert plan["xgb"]["labels"] == {"momentum": ["momentum"], "angle": ["phi", "theta"]}
    assert plan["xgb"]["status"] == "ready" and plan["xgb"]["splitReproduced"] is True


def test_a_running_analysis_shows_the_xgboost_cards_shut_with_the_servers_sentence(plan_results):
    plan = plan_results["running"]
    assert plan["sections"]["xgb"] is True and plan["xgbNotice"] is None
    for card in XGB:
        assert plan["cards"][card] == {"shown": True, "enabled": False, "reason": "Analysing: 3 of 7 steps."}
    assert plan["xgb"]["status"] == "pending"


def test_an_experiment_without_the_block_shows_nothing_it_cannot_vouch_for(plan_results):
    for plan in (plan_results["legacy"], plan_results["none"]):
        assert not any(plan["sections"].values())


def test_each_view_falls_back_to_a_frame_it_can_draw_in_and_says_so(plan_results):
    f = plan_results["frames"]
    assert f["featuresCanonical"]["frame"] == "lab" and f["featuresCanonical"]["fallback"] is True
    assert "Separation-Aligned (D-Frame) › Translated" in f["featuresCanonical"]["note"]
    assert f["featuresLocal"] == {"frame": "local", "fallback": False, "note": None}
    assert f["ensembleLab"]["frame"] == "local" and f["ensembleLab"]["fallback"] is True
    assert f["ensembleSingleTrans"]["frame"] == "local"
    assert "Shower-Aligned › Local" in f["ensembleSingleTrans"]["note"]
    assert f["eventCanonicalSingle"]["frame"] == "lab"
    # The D-frame's networks are the absolute frame's, by definition, not a fallback.
    assert f["network"] == {"frame": "lab", "fallback": False, "note": None}
    assert f["none"]["frame"] is None
    assert plan_results["sectionIds"]["voxels"] == ["vox-event", "vox-ensemble"]


# ------------------------------------------------------------ the state --

_STATE_SCRIPT = _FAKE_DOM + r"""
const [stateUrl, labelsUrl] = JSON.parse(process.argv[1]);
const { State, DEFAULTS, FEATURE_KEYS } = await import(stateUrl);
const labels = await import(labelsUrl);
const out = {};
const fresh = (hash) => { window.location.hash = hash; replaced = []; return new State(); };
const link = '#feature=depth&fclass=label&voxel_event=12&voxel_shower=both&voxel_channel=species'
  + '&ens_channel=gradcam_energy&xgb_task=angle&xgb_label=phi';
let s = fresh(link);
out.read = Object.fromEntries(['feature', 'fclass', 'voxel_event', 'voxel_shower', 'voxel_channel', 'ens_channel',
  'xgb_task', 'xgb_label', 'event', 'shower'].map((k) => [k, s.get(k)]));
out.cold = s.coldBoot;
s.writeHash();
out.written = window.location.hash;
s = fresh('#feature=bogus&fclass=bins&voxel_event=-1&voxel_shower=c&voxel_channel=density&ens_channel=energy'
  + '&xgb_task=energy&xgb_label=psi');
out.invalid = Object.fromEntries(['feature', 'fclass', 'voxel_event', 'voxel_shower', 'voxel_channel', 'ens_channel',
  'xgb_task', 'xgb_label'].map((k) => [k, s.get(k)]));
out.invalidCold = s.coldBoot;
s = fresh('#voxel_event=1.5');
out.fraction = s.get('voxel_event');
s = fresh('');
s.writeHash();
out.defaultHash = window.location.hash;
out.cleanCold = s.coldBoot;
s.set({ xgb_task: 'angle', voxel_event: 7 });
out.setHash = window.location.hash;
s.set({ xgb_task: 'momentum', voxel_event: null });
out.backHash = window.location.hash;
// The Physics page's keys survive a write from the Models page, and the reverse.
s = fresh('#event=3&compare=true&feature=width');
s.set({ fclass: 'label' });
out.mixed = window.location.hash;
out.defaults = Object.fromEntries(['feature', 'fclass', 'voxel_event', 'voxel_shower', 'voxel_channel', 'ens_channel',
  'xgb_task', 'xgb_label'].map((k) => [k, DEFAULTS[k]]));
out.featureKeys = [...FEATURE_KEYS];
out.labelKeys = labels.FEATURES.map((f) => f.key);
out.aggregate = labels.featureChoices(false).map((f) => f.key);
out.tabs = labels.PAGE_TABS.map((t) => [t.page, t.href]);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def state_results() -> dict:
    return _run(_STATE_SCRIPT, [(JS / "state.js").as_uri(), (JS / "labels.js").as_uri()])


def test_the_models_keys_round_trip_through_the_hash(state_results):
    r = state_results
    assert r["read"] == {"feature": "depth", "fclass": "label", "voxel_event": 12, "voxel_shower": "both",
                         "voxel_channel": "species", "ens_channel": "gradcam_energy", "xgb_task": "angle",
                         "xgb_label": "phi", "event": None, "shower": "a"}
    assert r["cold"] is False
    written = dict(part.split("=") for part in r["written"].lstrip("#").split("&"))
    assert written == {"feature": "depth", "fclass": "label", "voxel_event": "12", "voxel_shower": "both",
                       "voxel_channel": "species", "ens_channel": "gradcam_energy", "xgb_task": "angle",
                       "xgb_label": "phi"}


def test_an_invalid_models_value_keeps_its_default_but_the_link_is_still_a_view_link(state_results):
    assert state_results["invalid"] == state_results["defaults"]
    assert state_results["invalidCold"] is False
    assert state_results["fraction"] is None


def test_the_models_defaults_are_never_written(state_results):
    r = state_results
    assert r["defaultHash"] == "" and r["cleanCold"] is True
    assert r["setHash"] == "#voxel_event=7&xgb_task=angle"
    assert r["backHash"] == ""
    assert r["defaults"] == {"feature": "num_hits", "fclass": "windows", "voxel_event": None, "voxel_shower": "a",
                             "voxel_channel": "energy", "ens_channel": "density", "xgb_task": "momentum",
                             "xgb_label": "theta"}


def test_neither_page_strips_the_others_keys(state_results):
    written = dict(part.split("=") for part in state_results["mixed"].lstrip("#").split("&"))
    assert written == {"event": "3", "compare": "true", "feature": "width", "fclass": "label"}


def test_the_feature_names_follow_the_states_feature_keys(state_results):
    r = state_results
    assert r["labelKeys"] == r["featureKeys"] and len(r["featureKeys"]) == 21
    assert len(r["aggregate"]) == 19 and "avg_phi_circ" not in r["aggregate"]
    assert r["tabs"] == [["physics", "/"], ["models", "/models"]]


# ------------------------------------------------------- the requests --

_REQUEST_SCRIPT = _FAKE_DOM + _OPEN_GATE + r"""
const [cardsUrl, capsUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const cards = await import(cardsUrl);
const caps = await import(capsUrl);
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const plans = Object.fromEntries(Object.entries(exps).map(([k, e]) => [k, caps.page2Plan(e)]));
plans.open = caps.page2Plan(openGate(catalogue));
const filters = {
  two: { table_name: 'experiment_baseline', e1_min: 1, e1_max: 20, e2_min: 1, e2_max: 20, d_min: 0, d_max: 900,
    include_undefined_d: false },
  one: { table_name: 'single_hits', e1_min: 1, e1_max: 20 },
  events: { table_name: 'single_events', e1_min: 1, e1_max: 20 },
  open: { table_name: 'electron_s1_aggr', e1_min: 1, e1_max: 20 },
};
const kinds = { two: 'two_shower_hits', one: 'single_shower_hits', events: 'single_shower_events', open: 'open' };
const out = { requests: {}, notices: {}, options: {}, captions: {} };
const view = (extra = {}) => ({ frame: 'lab', model: 'segmentation', feature: 'num_hits', fclass: 'windows',
  xgb_task: 'momentum', xgb_label: 'theta', ...extra });
for (const [k, kind] of Object.entries(kinds)) {
  out.requests[k] = {};
  for (const spec of cards.MODELS_CARDS) {
    out.requests[k][spec.id] = cards.cardRequest(spec.id, { filters: filters[k], plan: plans[kind], view: view() });
  }
}
out.energy = {
  perf: cards.cardRequest('perf-bins', { filters: filters.two, plan: plans.two_shower_hits, view: view({ model: 'energy' }) }),
  pred: cards.cardRequest('pred-truth', { filters: filters.two, plan: plans.two_shower_hits,
    view: view({ model: 'angle', frame: 'canonical' }) }),
  residuals: cards.cardRequest('pred-residuals', { filters: filters.two, plan: plans.two_shower_hits,
    view: view({ model: 'angle', frame: 'canonical' }) }),
  predLocal: cards.cardRequest('pred-truth', { filters: filters.two, plan: plans.two_shower_hits,
    view: view({ model: 'energy', frame: 'local' }) }),
};
out.xgbAngle = {
  perf: cards.cardRequest('perf-bins', { filters: filters.open, plan: plans.open, view: view({ xgb_task: 'angle' }) }),
  pred: cards.cardRequest('pred-truth', { filters: filters.open, plan: plans.open,
    view: view({ xgb_task: 'angle', xgb_label: 'phi' }) }),
  surrogate: cards.cardRequest('xgb-surrogate', { filters: filters.open, plan: plans.open,
    view: view({ xgb_task: 'angle' }) }),
};
out.featureFrames = {
  canonical: cards.cardRequest('feat-hist', { filters: filters.two, plan: plans.two_shower_hits,
    view: view({ frame: 'canonical', feature: 'depth' }), controls: { histScale: 'linear' } }),
  trans: cards.cardRequest('feat-corr', { filters: filters.two, plan: plans.two_shower_hits,
    view: view({ frame: 'trans', fclass: 'label' }), controls: { corrClass: '1' } }),
  circOnAggregate: cards.cardRequest('feat-hist2d', { filters: filters.events, plan: plans.single_shower_events,
    view: view({ feature: 'avg_phi_circ' }) }),
};
out.notices = {
  segmentation: cards.cardNotice('perf-bins', { plan: plans.two_shower_hits, view: view() }),
  energy: cards.cardNotice('perf-bins', { plan: plans.two_shower_hits, view: view({ model: 'energy' }) }),
  features: cards.cardNotice('feat-table', { plan: plans.two_shower_hits, view: view() }),
};
out.captions = {
  canonical: cards.cardCaption('feat-table', { plan: plans.two_shower_hits, view: view({ frame: 'canonical' }) }),
  lab: cards.cardCaption('feat-table', { plan: plans.two_shower_hits, view: view() }),
  perf: cards.cardCaption('perf-bins', { plan: plans.two_shower_hits, view: view({ frame: 'canonical' }) }),
};
out.options = {
  perf: cards.cardOptions('perf-bins', { plan: plans.two_shower_hits, view: view({ model: 'angle' }),
    controls: { perfStat: 'mae', perfShower: 'b' }, palette: 'cividis' }),
  table: cards.cardOptions('feat-table', { plan: plans.two_shower_hits, view: view(), controls: { tableStat: 'mean' } }),
  pred: cards.cardOptions('pred-truth', { plan: plans.open, view: view({ xgb_task: 'angle', xgb_label: 'phi' }) }),
  hist: cards.cardOptions('feat-hist', { plan: plans.two_shower_hits, view: view({ feature: 'width', fclass: 'label' }) }),
  tree: cards.cardOptions('xgb-surrogate', { plan: plans.open, view: view({ xgb_task: 'angle', xgb_label: 'phi' }) }),
  binary: cards.cardOptions('xgb-binary', { plan: plans.open, view: view({ xgb_task: 'angle' }) }),
};
out.abortKeys = cards.ABORT_KEYS;
out.segmentationNotice = cards.SEGMENTATION_NOTICE;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def request_results() -> dict:
    return _run(_REQUEST_SCRIPT, [(JS / "models_cards.js").as_uri(), (JS / "capabilities.js").as_uri(),
                                  _path("experiments")])


def test_the_abort_keys_are_the_interfaces(request_results):
    assert sorted(request_results["abortKeys"].values()) == sorted([
        "models-perf", "models-pred", "models-feat-table", "models-feat-corr", "models-feat-hist",
        "models-feat-hist2d", "models-prim", "models-xgb-cv", "models-xgb-binary", "models-xgb-surrogate",
        "models-xgb-importance",
    ])


def test_the_segmentation_network_asks_for_no_performance_card(request_results):
    two = request_results["requests"]["two"]
    for card in PERF:
        assert two[card] is None, card
    assert request_results["notices"]["segmentation"] == request_results["segmentationNotice"]
    assert request_results["notices"]["energy"] is None and request_results["notices"]["features"] is None


def test_the_performance_cards_ask_for_the_selected_task(request_results):
    r = request_results["energy"]
    assert r["perf"]["route"] == "/api/model-performance" and r["perf"]["abortKey"] == "models-perf"
    assert r["perf"]["params"]["slice_by"] == "momentum_bin" and r["perf"]["params"]["model"] == "energy"
    assert "coord_system" not in r["perf"]["params"], "the breakdown covers every network frame at once"
    # The two prediction cards read one response; the D-frame reads the absolute networks.
    assert r["pred"] == r["residuals"]
    assert r["pred"]["route"] == "/api/prediction-density" and r["pred"]["abortKey"] == "models-pred"
    assert r["pred"]["params"]["model"] == "angle" and r["pred"]["params"]["coord_system"] == "lab"
    assert "label" not in r["pred"]["params"]
    assert r["predLocal"]["params"]["coord_system"] == "local"


def test_a_paired_aggregate_asks_for_the_xgboost_task_and_output(request_results):
    r = request_results["xgbAngle"]
    assert r["perf"]["params"]["model"] == "angle"
    assert r["pred"]["params"]["label"] == "phi" and "coord_system" not in r["pred"]["params"]
    assert r["surrogate"] == {"route": "/api/xgboost", "abortKey": "models-xgb-surrogate",
                              "params": {"table_name": "electron_s1_aggr", "view": "surrogate", "task": "angle"}}
    open_ = request_results["requests"]["open"]
    # The momentum model answers the energy task.
    assert open_["perf-bins"]["params"]["model"] == "energy"
    assert open_["xgb-binary"]["params"] == {"table_name": "electron_s1_aggr", "view": "binary"}
    for card in ("xgb-cv", "xgb-importance"):
        assert open_[card]["params"] == {"table_name": "electron_s1_aggr", "view": card.split("-")[1],
                                         "task": "momentum"}, "the XGBoost views take no selection"


def test_the_feature_cards_ask_in_their_frame_with_their_classes(request_results):
    two = request_results["requests"]["two"]
    assert two["feat-table"]["params"] == {**_TWO_FILTERS, "view": "describe", "classes": "windows",
                                           "coord_system": "lab"}
    assert two["feat-corr"]["params"]["class_index"] == "pooled"
    assert two["feat-hist"]["params"]["feature"] == "num_hits" and "scale" not in two["feat-hist"]["params"]
    assert two["prim-rate"] == {"route": "/api/primaries", "abortKey": "models-prim", "params": _TWO_FILTERS}
    f = request_results["featureFrames"]
    assert f["canonical"]["params"]["coord_system"] == "lab" and f["canonical"]["params"]["scale"] == "linear"
    assert f["canonical"]["params"]["feature"] == "depth"
    assert f["trans"]["params"]["coord_system"] == "trans" and f["trans"]["params"]["class_index"] == "1"
    assert f["trans"]["params"]["classes"] == "label"
    # The aggregate has no hits: no frame, and only its own nineteen features.
    assert "coord_system" not in f["circOnAggregate"]["params"]
    assert f["circOnAggregate"]["params"]["feature"] == "num_hits"


def test_a_single_shower_request_carries_no_second_shower_axis(request_results):
    for kind in ("one", "events"):
        for card, request in request_results["requests"][kind].items():
            if request is None:
                continue
            params = request["params"]
            for key in ("e2_min", "e2_max", "d_min", "d_max", "include_undefined_d", "shower"):
                assert key not in params, (kind, card, key)


def test_a_card_drawn_in_another_frame_says_so(request_results):
    c = request_results["captions"]
    assert c["canonical"] and c["canonical"].startswith("Drawn in Absolute")
    assert c["lab"] is None and c["perf"] is None


def test_the_render_options_are_the_interfaces(request_results):
    o = request_results["options"]
    assert o["perf"] == {"palette": "cividis", "card": "perf-bins", "task": "angle", "quantity": "mae",
                         "shower": "b"}
    assert o["pred"] == {"palette": "viridis", "card": "pred-truth", "task": "angle", "label": "phi", "shower": "both"}
    assert o["hist"] == {"palette": "viridis", "card": "feat-hist", "classes": "label", "feature": "width"}
    assert o["table"] == {"palette": "viridis", "card": "feat-table", "classes": "windows", "stat": "mean"}
    assert o["tree"] == {"palette": "viridis", "card": "xgb-surrogate", "task": "angle", "label": "phi"}
    assert o["binary"] == {"palette": "viridis", "card": "xgb-binary"}


_TWO_FILTERS = {"table_name": "experiment_baseline", "e1_min": 1, "e1_max": 20, "e2_min": 1, "e2_max": 20,
                "d_min": 0, "d_max": 900, "include_undefined_d": False}


# --------------------------------------------------- the section on a page --

_SECTION_SCRIPT = _FAKE_DOM + _OPEN_GATE + r"""
const [cardsUrl, stateUrl, capsUrl, cataloguePath, fixturePaths] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const fixtures = loadAll(fixturePaths);
const calls = [];
let failNext = null;
let delay = null;
globalThis.fetch = async (url) => {
  const u = new URL(url);
  calls.push(u.pathname + u.search);
  const q = u.searchParams;
  if (failNext && u.pathname === failNext.path) {
    const status = failNext.status;
    failNext = null;
    return { ok: false, status, statusText: 'x', json: async () => ({ detail: `refused ${status}` }) };
  }
  if (delay && u.pathname === delay.path) await delay.promise;
  let body;
  if (u.pathname === '/api/model-performance') body = fixtures.perf;
  else if (u.pathname === '/api/prediction-density') body = fixtures.pred;
  else if (u.pathname === '/api/features') body = { describe: fixtures.describe, corr: fixtures.corr,
    hist: fixtures.hist, hist2d: fixtures.hist2d }[q.get('view')];
  else if (u.pathname === '/api/primaries') body = fixtures.primaries;
  else return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ detail: 'no route' }) };
  return { ok: true, status: 200, json: async () => body };
};
const cards = await import(cardsUrl);
const { State } = await import(stateUrl);
const caps = await import(capsUrl);
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const out = {};

const rendered = [];
class FakePanel {
  constructor(element, options) { this.element = element; this.options = options; this.kind = 'fake'; }
  render(payload, opts) { this.lastPayload = payload; this.lastOpts = opts; rendered.push([this.element.id, opts]); }
  clear() { this.cleared = (this.cleared ?? 0) + 1; this.lastPayload = null; }
  relayout() { this.relaid = (this.relaid ?? 0) + 1; }
  setBusy() {}
}
const names = ['PerfBinsPanel', 'Hist2dPanel', 'DistributionPanel', 'FeatureTablePanel', 'CorrelationPanel',
  'XgbCvPanel', 'XgbBinaryPanel', 'XgbTreePanel', 'XgbImportancePanel'];
const panelClasses = Object.fromEntries(names.map((n) => [n, FakePanel]));
const built = [];
const notesModules = {
  models: {
    featureTableNotes: (ctx) => { built.push(['featureTableNotes', ctx.card, ctx.title, Boolean(ctx.payload)]);
      return { title: ctx.title, hazards: ['few events'], sections: [{ heading: 'Selection', lines: ['table'] }] }; },
    perfBinsNotes: (ctx) => ({ title: ctx.title, hazards: [], sections: [{ heading: 'What is drawn',
      lines: [`quantity ${ctx.quantity} task ${ctx.task}`] }] }),
  },
  xgb: {},
};
// The RatesPanel module is "not built yet": its loader rejects, as a 404 import does.
const panelModules = { RatesPanel: () => Promise.reject(new TypeError('Failed to fetch dynamically imported module')) };

window.location.hash = '';
const state = new State();
const plan = caps.page2Plan(exps.two_shower_hits);
state.restrictAxes(plan.axes);
state.set({ table_name: 'experiment_baseline' }, { silent: true });
state.adoptSnappedBounds(exps.two_shower_hits.bounds);
const hosts = Object.fromEntries(['perf', 'xgb', 'features', 'primaries'].map((k) => {
  const el = document.createElement('section'); el.id = `${k}-grid`; return [k, el];
}));
const rendersSeen = [];
const errors = [];
const changes = [];
let opened = 0;
const section = new cards.ModelsSection(hosts, {
  state, panelClasses, notesModules, panelModules, root: 'MAIN',
  onRendered: (id, payload) => rendersSeen.push([id, Boolean(payload)]),
  onError: (error, context) => errors.push([context, error.message]),
  onStateChange: (patch) => changes.push(patch),
  onOpenAdmin: () => { opened += 1; },
});
const all = Object.values(hosts).flatMap((h) => h.children);
const cardOf = (id) => all.find((c) => c.dataset.panel === id);
out.anatomy = all.map((card) => {
  const h2 = card.children[0];
  const buttons = h2.children[1].children;
  const exporter = buttons.find((b) => b.dataset.export);
  return {
    panel: card.dataset.panel,
    host: card.parent.id,
    firstInspect: buttons[0].dataset.inspect,
    firstControls: buttons[0].getAttribute('aria-controls'),
    lastExport: buttons[buttons.length - 1].dataset.export ?? null,
    exportTitle: exporter ? exporter.title : null,
    caption: card.children[1].className,
    plotId: card.children[2].children[0].id,
    plotClass: card.children[2].children[0].className,
    wide: card.classList.contains('is-wide'),
  };
});
out.observer = FakeObserver.last.options;

section.applyPlan(plan);
out.hidden = Object.fromEntries(all.map((c) => [c.dataset.panel, c.hidden]));
const message = (id) => cardOf(id).find((el) => el.classList.contains('card-error'));
out.perfNotice = { hidden: message('perf-bins').hidden, kind: message('perf-bins').dataset.kind,
  text: message('perf-bins').children[0]?.textContent, key: section.keyOf('perf-bins') };
FakeObserver.last.show(all.filter((c) => !c.hidden));
await settle();
out.firstCalls = [...calls];
out.renders = rendersSeen.map(([id]) => id);
const prim = message('prim-rate');
out.primShut = { hidden: prim.hidden, kind: prim.dataset.kind, text: prim.children[0].textContent };

// The task control on the card writes the shared `model` and loads both performance requests.
const before = calls.length;
const energy = cardOf('perf-bins').find((el) => el.dataset.modelsTask === 'energy');
energy.click();
await settle();
out.afterTask = { calls: calls.slice(before), model: state.get('model'), hash: window.location.hash, changes: [...changes],
  noticeHidden: message('perf-bins').hidden };
// The prediction cards share one request: two cards, one call.
out.predCalls = calls.filter((c) => c.startsWith('/api/prediction-density')).length;
out.predRendered = rendered.filter(([id]) => id === 'plot-pred-truth' || id === 'plot-pred-residuals').map(([id]) => id);
// A render-only control repaints: no request.
const beforeStat = calls.length;
cardOf('perf-bins').find((el) => el.dataset.perfStatistic === 'mae').click();
await settle();
out.afterStat = { calls: calls.length - beforeStat, quantity: rendered.filter(([id]) => id === 'plot-perf-bins').pop()[1].quantity };

// Notes: the builder by name, with the card's render options; else the payload's own lines.
out.notes = {
  table: section.notes('feat-table'),
  perf: section.notes('perf-bins'),
  corrFallback: section.notes('feat-corr'),
  prim: section.notes('prim-rate'),
};
out.built = built;
out.exportTargets = {
  perf: Boolean(section.exportTarget('perf-bins')?.panel),
  table: section.exportTarget('feat-table'),
  foreign: section.exportTarget('vproj-xy') === undefined,
  meta: section.exportTarget('feat-corr')?.meta ?? null,
};

// A feature change goes to the shared State and reloads the two histogram cards only.
const beforeFeature = calls.length;
const select = cardOf('feat-hist').find((el) => el.tagName === 'SELECT' && el.dataset.featureId !== undefined);
out.featureOptions = select.options.length;
select.value = 'depth';
select.dispatch('change');
await settle();
out.afterFeature = { calls: calls.slice(beforeFeature), feature: state.get('feature') };

// A refusal stays refused; a transient failure offers a Retry and is asked again.
failNext = { path: '/api/features', status: 422 };
section.controls = { ...section.controls, corrClass: '2' };
section.refreshVisible();
await settle();
const corr = message('feat-corr');
out.refused = { hidden: corr.hidden, retry: Boolean(corr.find((el) => el.dataset.retry !== undefined)),
  text: corr.children[0].textContent };
const beforeAgain = calls.length;
await section.refresh().catch(() => {});
out.refusedAgain = calls.length - beforeAgain;
failNext = { path: '/api/features', status: 503 };
section.controls = { ...section.controls, corrClass: '3' };
await section.refresh().catch((e) => { out.transientError = e.message; });
const retry = message('feat-corr').find((el) => el.dataset.retry !== undefined);
out.transient = { retry: Boolean(retry), kind: message('feat-corr').dataset.kind };
const beforeRetry = calls.length;
retry.click();
await settle();
out.retried = { calls: calls.length - beforeRetry, hidden: message('feat-corr').hidden };

// A response that lands after an experiment switch draws nothing and is not kept.
let release;
delay = { path: '/api/primaries', promise: new Promise((r) => { release = r; }) };
const single = caps.page2Plan(exps.single_shower_hits);
section.reset();
section.applyPlan(single);
state.restrictAxes(single.axes);
state.set({ table_name: 'single_hits' }, { silent: true });
FakeObserver.last.show(all.filter((c) => !c.hidden));
await settle();
const primCard = cardOf('prim-rate');
section.reset();
state.set({ table_name: 'other' }, { silent: true });
const rendersBefore = rendered.length;
release();
delay = null;
await settle();
out.late = { rendered: rendered.length - rendersBefore, payload: section.payloadOf('prim-rate'),
  cache: section.cache.size, busy: primCard.classList.contains('is-loading') };
out.singleHidden = Object.fromEntries(all.map((c) => [c.dataset.panel, c.hidden]));

// A panel module not built yet: the card says so, without a Retry, and is not asked again.
state.set({ table_name: 'single_hits' }, { silent: true });
section.applyPlan(single);
FakeObserver.last.show(all.filter((c) => !c.hidden));
await settle();
const pending = message('prim-rate');
out.notBuilt = { hidden: pending.hidden, kind: pending.dataset.kind, text: pending.children[0].textContent,
  retry: Boolean(pending.find((el) => el.dataset.retry !== undefined)) };
const beforePending = calls.length;
await section.refresh().catch(() => {});
out.notBuiltAgain = calls.slice(beforePending).filter((c) => c.startsWith('/api/primaries')).length;
out.notBuiltLoad = await cards.loadPanelClass('XgbCvPanel', null, { XgbCvPanel: async () => ({}) })
  .then(() => 'loaded', (e) => [e.name, e.message, e.status]);
out.errors = errors.filter(([, m]) => !m.includes('refused 422'));
out.opened = opened;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def section_results() -> dict:
    fixtures = {
        "perf": _path("perf_two_energy"), "pred": _path("pred_density_two_energy"),
        "describe": _path("features_single_describe"), "corr": _path("features_two_corr"),
        "hist": _path("features_single_hist"), "hist2d": _path("features_single_hist2d"),
        "primaries": _path("primaries_single"),
    }
    return _run(_SECTION_SCRIPT, [
        (JS / "models_cards.js").as_uri(), (JS / "state.js").as_uri(), (JS / "capabilities.js").as_uri(),
        _path("experiments"), fixtures,
    ])


def test_every_card_has_the_page_anatomy(section_results):
    anatomy = {a["panel"]: a for a in section_results["anatomy"]}
    assert list(anatomy) == PERF + XGB + FEATURES + ["prim-rate"]
    for card, a in anatomy.items():
        assert a["firstInspect"] == card and a["firstControls"] == "inspector", card
        assert a["plotId"] == f"plot-{card}" and a["caption"] == "card-caption", card
        if card == "feat-table":
            assert a["lastExport"] is None and a["plotClass"] == "card-table"
        else:
            assert a["lastExport"] == card and "plot area only" in a["exportTitle"], card
    hosts = {card: a["host"] for card, a in anatomy.items()}
    assert {hosts[c] for c in PERF} == {"perf-grid"} and {hosts[c] for c in XGB} == {"xgb-grid"}
    assert {hosts[c] for c in FEATURES} == {"features-grid"} and hosts["prim-rate"] == "primaries-grid"
    assert {c for c, a in anatomy.items() if a["wide"]} == {"perf-bins", "xgb-surrogate", "xgb-importance",
                                                            "feat-table", "feat-hist2d"}
    assert section_results["observer"]["rootMargin"] == "0px"


def test_the_plan_decides_which_cards_show(section_results):
    hidden = section_results["hidden"]
    assert all(hidden[c] is False for c in PERF + FEATURES + ["prim-rate"])
    assert all(hidden[c] is True for c in XGB)
    single = section_results["singleHidden"]
    assert all(single[c] is True for c in PERF + XGB)


def test_the_segmentation_network_shows_a_notice_and_asks_nothing(section_results):
    r = section_results
    assert r["perfNotice"]["hidden"] is False and r["perfNotice"]["kind"] == "notice"
    assert r["perfNotice"]["key"] is None
    assert not any(c.startswith(("/api/model-performance", "/api/prediction-density")) for c in r["firstCalls"])
    # The visible feature cards load, each once.
    views = sorted(c.split("view=")[1].split("&")[0] for c in r["firstCalls"] if c.startswith("/api/features"))
    assert views == ["corr", "describe", "hist", "hist2d"]


def test_a_shut_card_states_the_servers_reason(section_results):
    shut = section_results["primShut"]
    assert shut["hidden"] is False and shut["kind"] == "disabled" and "particle_type" in shut["text"]


def test_the_task_control_writes_the_shared_model_and_loads_its_cards(section_results):
    r = section_results["afterTask"]
    assert r["model"] == "energy" and r["changes"] == [{"model": "energy"}]
    assert r["hash"].endswith("&model=energy"), r["hash"]
    assert r["noticeHidden"] is True
    routes = sorted(c.split("?")[0] for c in r["calls"])
    assert routes == ["/api/model-performance", "/api/prediction-density"]
    assert section_results["predCalls"] == 1
    assert sorted(set(section_results["predRendered"])) == ["plot-pred-residuals", "plot-pred-truth"]


def test_a_render_only_control_repaints_without_a_request(section_results):
    assert section_results["afterStat"] == {"calls": 0, "quantity": "mae"}


def test_notes_come_from_the_named_builder_or_the_payloads_own_lines(section_results):
    notes = section_results["notes"]
    assert notes["table"]["hazards"] == ["few events"]
    assert section_results["built"][0] == ["featureTableNotes", "feat-table", "Event Features — describe()", True]
    assert notes["perf"]["sections"][0]["lines"] == ["quantity mae task energy"]
    # No builder yet: the payload's own notes, under the drawer's heading.
    assert notes["corrFallback"]["sections"][0]["heading"] == "What is drawn"
    assert notes["corrFallback"]["sections"][0]["lines"]
    assert "particle_type" in notes["prim"]["sections"][0]["lines"][0]


def test_export_targets_are_the_drawn_charts_only(section_results):
    t = section_results["exportTargets"]
    assert t["perf"] is True and t["table"] is None and t["foreign"] is True
    assert t["meta"]["view"] == "corr"


def test_a_feature_change_reloads_only_the_cards_that_read_it(section_results):
    r = section_results["afterFeature"]
    assert r["feature"] == "depth"
    assert sorted(c.split("view=")[1].split("&")[0] for c in r["calls"]) == ["hist", "hist2d"]
    assert all("feature=depth" in c for c in r["calls"])
    assert section_results["featureOptions"] == 21


def test_a_refusal_stays_refused_and_a_transient_failure_is_retried(section_results):
    r = section_results
    assert r["refused"]["hidden"] is False and r["refused"]["retry"] is False and "422" in r["refused"]["text"]
    assert r["refusedAgain"] == 0
    assert r["transient"] == {"retry": True, "kind": "error"} and "503" in r["transientError"]
    assert r["retried"] == {"calls": 1, "hidden": True}


def test_a_response_landing_after_an_experiment_switch_draws_nothing(section_results):
    assert section_results["late"] == {"rendered": 0, "payload": None, "cache": 0, "busy": False}


def test_a_panel_not_built_yet_says_so_and_is_not_asked_again(section_results):
    r = section_results
    assert r["notBuilt"]["hidden"] is False and r["notBuilt"]["kind"] == "pending"
    assert r["notBuilt"]["text"] == "This panel is not built yet in this release." and r["notBuilt"]["retry"] is False
    assert r["notBuiltAgain"] == 0
    assert r["notBuiltLoad"] == ["NotBuiltError", "This panel is not built yet in this release.", 404]
    assert r["errors"] == [] and r["opened"] == 0


# ----------------------------------------------------- tabs and admin --

_TABS_SCRIPT = _FAKE_DOM + r"""
const [commonUrl, adminUrl] = JSON.parse(process.argv[1]);
const common = await import(commonUrl);
const admin = await import(adminUrl);
const out = {};
out.hrefs = [
  common.tabHref('/models', '#e1_min=2&frame=local'),
  common.tabHref('/', 'feature=depth'),
  common.tabHref('/?admin=1', '#frame=canonical'),
  common.tabHref('/models#stale=1', ''),
  common.tabHref('/', ''),
];
const link = (href) => { const a = document.createElement('a'); a.setAttribute('href', href); a.dataset.pageTab = '';
  a.href = href; return a; };
const links = [link('/models'), link('/?admin=1')];
const wired = common.wirePageTabs({ querySelectorAll: () => links });
window.location.hash = '#xgb_task=angle';
links[0].dispatch('pointerdown');
links[1].dispatch('contextmenu');
out.wired = { n: wired.length, bases: links.map((a) => a.dataset.base), hrefs: links.map((a) => a.href),
  events: Object.keys(links[0].listeners).sort() };
window.location.hash = '';
links[0].dispatch('click');
out.cleared = links[0].href;

const group = common.choiceGroup(document.createElement('fieldset'), {
  name: 'm-model', value: 'energy',
  choices: [{ value: 'segmentation', label: 'Segmentation Model' }, { value: 'energy', label: 'Energy Estimation Model' }],
  disabled: { segmentation: 'Not in this experiment.' }, onChange: (v) => { out.changed = v; },
});
out.group = [...group.inputs].map(([v, input]) => [v, input.checked, input.disabled, input.parent.title]);

out.runs = admin.modelRunRows({ dir: '/app/host/xgboost_models', runs: [
  { table_name: 'electron_s1_aggr', display_name: 'electron', paired: true, species: 'electron', seed: 1,
    models: [{ path: 'xgboost_electron/standalone_momentum_s1_model.json' }], status: 'running', progress: 0.4 },
  { table_name: 'single_hits', paired: false, reason: 'Not an event-level aggregate.' },
  { experiment: 'muon_s1_aggr', pairing: { paired: true, species: 'muon', seed: 1, models: [] },
    analysis: { status: 'failed', error: 'boom' } },
] });
out.status = out.runs.map((row) => admin.runStatusText(row));
out.flat = admin.modelRunRows([{ table_name: 'x', paired: true, status: 'done', seconds: 41.6 }]).map(admin.runStatusText);
// The route as built (calosrv/api/routes_admin.py): pairing and analysis flat on each run.
out.served = admin.modelRunRows({ models: { dir: '/app/host/xgboost_models' }, runs: [
  { table_name: 'electron_s1_aggr', display_name: 'electron', paired: true, species: 'electron', seed: 1,
    models: [{ path: 'xgboost_electron/standalone_momentum_s1_model.json' },
      { path: 'xgboost_electron/standalone_angle_s1_model.json' }],
    status: 'running', reason: 'Analysing: 3 of 7 steps.', error: null, step: 3, steps: 7, step_label: null,
    progress: 0.4286, duration_s: null },
  { table_name: 'pion_s1_aggr', display_name: 'pion', paired: true, species: 'pion', seed: 1, models: [],
    status: 'failed', reason: 'The analysis failed.', error: 'MemoryError', step: 2, steps: 7, duration_s: 12.5 },
  { table_name: 'muon_s1_aggr', paired: true, species: 'muon', seed: 1, models: [], status: 'done', reason: null,
    error: null, step: 7, steps: 7, progress: 1, duration_s: 61.2 },
] }).map((row) => [row.models.length, admin.runStatusText(row)]);
out.empty = admin.modelRunRows({});
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def tabs_results() -> dict:
    return _run(_TABS_SCRIPT, [(JS / "page_common.js").as_uri(), (JS / "controls" / "admin.js").as_uri()])


def test_a_tab_href_carries_the_hash_and_keeps_its_query(tabs_results):
    assert tabs_results["hrefs"] == ["/models#e1_min=2&frame=local", "/#feature=depth",
                                     "/?admin=1#frame=canonical", "/models", "/"]


def test_the_tabs_compute_their_href_when_followed(tabs_results):
    w = tabs_results["wired"]
    assert w["n"] == 2 and w["bases"] == ["/models", "/?admin=1"]
    assert w["hrefs"] == ["/models#xgb_task=angle", "/?admin=1#xgb_task=angle"]
    assert w["events"] == ["auxclick", "click", "contextmenu", "focus", "pointerdown"]
    assert tabs_results["cleared"] == "/models"


def test_a_choice_group_is_built_from_labels(tabs_results):
    assert tabs_results["group"] == [["segmentation", False, True, "Not in this experiment."],
                                     ["energy", True, False, ""]]


def test_the_model_runs_list_is_read_defensively(tabs_results):
    rows = tabs_results["runs"]
    assert [r["table_name"] for r in rows] == ["electron_s1_aggr", "single_hits", "muon_s1_aggr"]
    assert rows[0]["models"] == ["xgboost_electron/standalone_momentum_s1_model.json"]
    assert [r["status"] for r in rows] == ["running", "unpaired", "failed"]
    assert tabs_results["status"] == ["analysing (40%)", "not paired: Not an event-level aggregate.", "failed: boom"]
    assert tabs_results["flat"] == ["done in 42 s"]
    assert tabs_results["served"] == [[2, "analysing (3 of 7)"], [0, "failed: MemoryError"], [0, "done in 61 s"]]
    assert tabs_results["empty"] == []
