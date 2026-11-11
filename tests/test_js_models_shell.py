"""The Models page's shell, executed under Node against the recorded payloads.

What the page shows for an experiment is decided from its capability block
(``capabilities.js`` ``page2Plan``), checked on the recorded catalogue of all
three kinds (``tests/fixtures/payloads/experiments.json``) and on the backend's
recording of an event-level aggregate paired with its XGBoost models
(``experiments_xgb.json``, recorded from ``xgb_client``: the electron seed-1
aggregate, both analyses done, the ``xgboost`` gate and the performance gates
open; its angle run honestly "split not reproduced").

Around the plan:

* ``state.js``: the Models page's keys round-trip through the hash, an
  invalid value keeps the default, a default is never written, a link with
  any of them is not a cold boot, and ``event`` and ``shower`` are never
  touched by them (the feature explorer's shower is its own ``fshower``);
* ``models_cards.js``: each card's request per kind (routes, parameters,
  abort keys), the segmentation network's notice, the frame fallbacks; on a
  fake document the cards' anatomy, one request shared by the cards that read
  it, a refusal that stays refused, a transient failure that is retried, a
  panel module that fails to load, a response that lands after an experiment
  switch, the notes routed by builder name and the export targets;
* ``page_common.js``: the page tabs' hrefs carry the hash at click time;
* ``models_subpages.js``: the three subpages (``msub``) and the catalogue's
  species (``bench_species``) in the hash, never written at their defaults
  nor set by the Admin defaults; the subpage of every card; the router on a
  fake page (hidden wrappers, ``aria-selected``, roving ``tabindex``, the
  WAI-ARIA keys, each subpage's scroll position, the hash write, ``onSwitch``
  after it, no card created or removed); the species bar's stored value and
  caption; the sticky head's measured height; and a deep link that switches
  to its card's subpage before it lands;
* ``models_main.js`` itself, run on ``models.html`` parsed into the fake
  document: the boot order (the linked subpage before any request), a deep
  link landing below the sticky head with its drawer and the way back, a
  catalogue card landing with no experiment open, a switch bringing the bench
  bar, the sidebar, the notices and the head's height in line, the bench bar's
  writes, the banner carrying the warnings of the subpage on show only, and the
  page's audit of the ids it writes;
* ``controls/admin.js``: the model-runs list as the route serves it, and Rescan models:
  a POST to the scan route, then the list read again with GET, which queues
  nothing.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _path, _run
from test_layout_assets import _strip_comments

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: The recorded aggregate whose XGBoost analyses are done (see the module docstring).
_OPEN_GATE = r"""
const openGate = () => {
  const recorded = load(globalThis.XGB_CATALOGUE);
  const e = recorded.experiments.find((x) => x.capabilities.kind === 'single_shower_events'
    && x.capabilities.panels.xgboost === true);
  if (!e) throw new Error('experiments_xgb.json holds no aggregate with its XGBoost gate open');
  return structuredClone(e);
};
"""


def _with_xgb(paths: list) -> list:
    """The script arguments, with the recorded XGBoost catalogue's path appended."""
    return [*paths, _path("experiments_xgb")]


#: Where each script reads the recorded XGBoost catalogue's path from (its last argument).
_XGB_ARG = "globalThis.XGB_CATALOGUE = JSON.parse(process.argv[1]).at(-1);\n"

# ----------------------------------------------------------- the plan --

_PLAN_SCRIPT = _FAKE_DOM + _OPEN_GATE + _XGB_ARG + r"""
const [capsUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const caps = await import(capsUrl);
const out = {};
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
out.plans = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, caps.page2Plan(e)]));
out.openExperiment = openGate();
out.open = caps.page2Plan(openGate());
// A run paired but its analysis still running: the section shows, its cards say why.
const running = openGate();
running.capabilities.panels.xgboost = false;
running.capabilities.reasons.xgboost = 'Analysing: 3 of 7 steps.';
running.capabilities.model_runs[0].status = 'running';
out.running = caps.page2Plan(running);
// R-3: the recorded analysis, ready, with every run's split reproduced (a derived clone).
const reproduced = openGate();
for (const run of reproduced.capabilities.model_runs) run.split_reproduced = true;
out.reproduced = caps.page2Plan(reproduced);
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
    return _run(_PLAN_SCRIPT, _with_xgb([(JS / "capabilities.js").as_uri(), _path("experiments")]))


PERF = ["perf-bins", "pred-truth", "pred-residuals"]
XGB_PERF = ["xgb-cv", "xgb-binary"]
XGB_DISTILL = ["xgb-surrogate", "xgb-importance"]
XGB = XGB_PERF + XGB_DISTILL
FEATURES = ["feat-table", "feat-corr", "feat-hist", "feat-hist2d"]


def _reason(kind: str, gate: str) -> str:
    """The recorded catalogue's reason for one gate of the experiment of one kind."""
    payload = json.loads(Path(_path("experiments")).read_text(encoding="utf-8"))
    (experiment,) = [e for e in payload["experiments"] if e["capabilities"]["kind"] == kind]
    return experiment["capabilities"]["reasons"][gate]


def test_the_two_shower_plan_offers_every_network_view_and_no_xgboost(plan_results):
    plan = plan_results["plans"]["two_shower_hits"]
    assert plan["sections"] == {"perf": True, "resolution": True, "xgb": False, "xgbDistill": False, "distill": True,
                                "bench": True, "features": True, "primaries": True, "voxels": True}
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
    assert plan["sections"] == {"perf": False, "resolution": True, "xgb": False, "xgbDistill": False, "distill": True,
                                "bench": True, "features": True, "primaries": True, "voxels": True}
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
    assert plan["sections"] == {"perf": False, "resolution": True, "xgb": False, "xgbDistill": False, "distill": True,
                                "bench": True, "features": True, "primaries": False, "voxels": False}
    for card in FEATURES:
        assert plan["cards"][card]["enabled"] is True
    assert plan["cards"]["vox-event"]["shown"] is False
    assert plan["notices"] == [plan_results["texts"]["events"]]
    assert plan["frames"]["offered"] == [] and plan["spatial"] is False
    assert plan["banner"] == plan_results["texts"]["missing"]
    assert plan["voxels"]["event"]["enabled"] is False and "no hits" in plan["voxels"]["event"]["reason"]


def test_a_paired_aggregate_opens_the_xgboost_section_and_hides_its_notice(plan_results):
    """On the backend's recording of a paired aggregate (experiments_xgb.json)."""
    experiment = plan_results["openExperiment"]
    assert experiment["capabilities"]["kind"] == "single_shower_events"
    assert [r["status"] for r in experiment["capabilities"]["model_runs"]] == ["done", "done"]
    plan = plan_results["open"]
    assert plan["sections"]["xgb"] is True and plan["sections"]["perf"] is True
    # E4 and E5 (Distillations) open with E1 and E3 (Performance): one gate, two sections.
    assert plan["sections"]["xgbDistill"] is True
    assert plan["sections"]["resolution"] is True
    assert plan["cards"]["res-scaling"] == {"shown": True, "enabled": True, "reason": None}
    for card in XGB:
        assert plan["cards"][card] == {"shown": True, "enabled": True, "reason": None}, card
    for card in PERF:
        assert plan["cards"][card] == {"shown": True, "enabled": True, "reason": None}, card
    assert plan["xgbNotice"] is None
    # No networks, but real XGBoost predictions: the banner says which are drawn.
    assert plan["banner"] == plan_results["texts"]["instead"]
    assert plan["xgb"]["tasks"] == ["momentum", "angle"]
    assert plan["xgb"]["labels"] == {"momentum": ["momentum"], "angle": ["phi", "theta"]}
    assert plan["xgb"]["status"] == "ready"
    # The recorded angle model does not reproduce its split (xgb-fixer-report.md, F5): the plan says so.
    runs = {r["task"]: r for r in experiment["capabilities"]["model_runs"]}
    assert runs["momentum"]["split_reproduced"] is True and runs["angle"]["split_reproduced"] is False
    assert plan["xgb"]["splitReproduced"] is False
    # The aggregate has no sidebar frame: its feature cards offer the frames its columns hold.
    assert plan["featureFrames"] == ["lab", "trans", "local"] and plan["frames"]["offered"] == []


def test_a_ready_analysis_with_every_split_reproduced_says_so(plan_results):
    """R-3: the positive branch, on a derived clone of the recording with every split reproduced."""
    plan = plan_results["reproduced"]
    assert plan["xgb"]["status"] == "ready" and plan["xgb"]["runs"]
    assert all(r["split_reproduced"] is True for r in plan["xgb"]["runs"])
    assert plan["xgb"]["splitReproduced"] is True


def test_a_running_analysis_shows_the_xgboost_cards_shut_with_the_servers_sentence(plan_results):
    plan = plan_results["running"]
    assert plan["sections"]["xgb"] is True and plan["sections"]["xgbDistill"] is True and plan["xgbNotice"] is None
    for card in XGB:
        assert plan["cards"][card] == {"shown": True, "enabled": False, "reason": "Analysing: 3 of 7 steps."}
    assert plan["xgb"]["status"] == "pending"


def test_an_experiment_without_the_block_shows_nothing_it_cannot_vouch_for(plan_results):
    """Nothing of the experiment's; the training report's catalogue reads no experiment and always shows."""
    for plan in (plan_results["legacy"], plan_results["none"]):
        catalogue = {key: plan["sections"][key] for key in ("distill", "bench")}
        rest = {key: value for key, value in plan["sections"].items() if key not in catalogue}
        assert catalogue == {"distill": True, "bench": True}
        assert rest and not any(rest.values()), rest


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
const link = '#feature=depth&fclass=label&fshower=b&voxel_event=12&voxel_shower=both&voxel_channel=species'
  + '&ens_channel=gradcam_energy&xgb_task=angle&xgb_label=phi';
let s = fresh(link);
out.read = Object.fromEntries(['feature', 'fclass', 'fshower', 'voxel_event', 'voxel_shower', 'voxel_channel', 'ens_channel',
  'xgb_task', 'xgb_label', 'event', 'shower'].map((k) => [k, s.get(k)]));
out.cold = s.coldBoot;
s.writeHash();
out.written = window.location.hash;
s = fresh('#feature=bogus&fclass=bins&fshower=both&voxel_event=-1&voxel_shower=c&voxel_channel=density&ens_channel=energy'
  + '&xgb_task=energy&xgb_label=psi');
out.invalid = Object.fromEntries(['feature', 'fclass', 'fshower', 'voxel_event', 'voxel_shower', 'voxel_channel', 'ens_channel',
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
s.set({ fshower: 'b' });
out.showerHash = window.location.hash;
s.set({ fshower: 'a' });
out.showerBack = window.location.hash;
// The Physics page's keys survive a write from the Models page, and the reverse.
s = fresh('#event=3&compare=true&feature=width');
s.set({ fclass: 'label' });
out.mixed = window.location.hash;
out.defaults = Object.fromEntries(['feature', 'fclass', 'fshower', 'voxel_event', 'voxel_shower', 'voxel_channel', 'ens_channel',
  'xgb_task', 'xgb_label'].map((k) => [k, DEFAULTS[k]]));
out.featureKeys = [...FEATURE_KEYS];
out.labelKeys = labels.FEATURES.map((f) => f.key);
out.aggregate = labels.featureChoices(false).map((f) => f.key);
out.tabs = labels.PAGE_TABS.map((t) => [t.page, t.href]);
// hashString is writeHash's serialisation, without the write.
s = fresh(link);
out.hashString = s.hashString();
s.writeHash();
out.hashWritten = window.location.hash;
// The Methodology page's own key is no State key: read past, never written.
s = fresh('#at=eq-se3&frame=local');
out.atCold = s.coldBoot;
out.atFrame = s.get('frame');
out.atString = s.hashString();
s = fresh('#at=eq-se3');
out.atOnlyCold = s.coldBoot;
out.atKey = 'at' in DEFAULTS;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def state_results() -> dict:
    return _run(_STATE_SCRIPT, [(JS / "state.js").as_uri(), (JS / "labels.js").as_uri()])


def test_the_models_keys_round_trip_through_the_hash(state_results):
    r = state_results
    assert r["read"] == {"feature": "depth", "fclass": "label", "fshower": "b", "voxel_event": 12,
                         "voxel_shower": "both", "voxel_channel": "species", "ens_channel": "gradcam_energy",
                         "xgb_task": "angle", "xgb_label": "phi", "event": None, "shower": "a"}
    assert r["cold"] is False
    written = dict(part.split("=") for part in r["written"].lstrip("#").split("&"))
    assert written == {"feature": "depth", "fclass": "label", "fshower": "b", "voxel_event": "12",
                       "voxel_shower": "both", "voxel_channel": "species", "ens_channel": "gradcam_energy",
                       "xgb_task": "angle", "xgb_label": "phi"}


def test_an_invalid_models_value_keeps_its_default_but_the_link_is_still_a_view_link(state_results):
    assert state_results["invalid"] == state_results["defaults"]
    assert state_results["invalidCold"] is False
    assert state_results["fraction"] is None


def test_the_models_defaults_are_never_written(state_results):
    r = state_results
    assert r["defaultHash"] == "" and r["cleanCold"] is True
    assert r["setHash"] == "#voxel_event=7&xgb_task=angle"
    assert r["backHash"] == ""
    # The feature explorer's shower: B is written, its default A never is.
    assert r["showerHash"] == "#fshower=b" and r["showerBack"] == ""
    assert r["defaults"] == {"feature": "num_hits", "fclass": "windows", "fshower": "a", "voxel_event": None,
                             "voxel_shower": "a", "voxel_channel": "energy", "ens_channel": "density",
                             "xgb_task": "momentum", "xgb_label": "theta"}


def test_neither_page_strips_the_others_keys(state_results):
    written = dict(part.split("=") for part in state_results["mixed"].lstrip("#").split("&"))
    assert written == {"event": "3", "compare": "true", "feature": "width", "fclass": "label"}


def test_the_feature_names_follow_the_states_feature_keys(state_results):
    r = state_results
    assert r["labelKeys"] == r["featureKeys"] and len(r["featureKeys"]) == 21
    assert len(r["aggregate"]) == 19 and "avg_phi_circ" not in r["aggregate"]
    assert r["tabs"] == [["physics", "/"], ["models", "/models"], ["methodology", "/methodology"]]


def test_hash_string_is_what_write_hash_writes(state_results):
    r = state_results
    assert r["hashString"] and f"#{r['hashString']}" == r["hashWritten"]


def test_the_methodology_key_is_no_state_key(state_results):
    r = state_results
    assert r["atKey"] is False
    # A link with a view key and `at` is a view link; `at` is read past and never written back.
    assert r["atCold"] is False and r["atFrame"] == "local" and r["atString"] == "frame=local"
    # `at` alone carries no view: the saved defaults still apply.
    assert r["atOnlyCold"] is True


# ------------------------------------------------------- the requests --

_REQUEST_SCRIPT = _FAKE_DOM + _OPEN_GATE + _XGB_ARG + r"""
const [cardsUrl, capsUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const cards = await import(cardsUrl);
const caps = await import(capsUrl);
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const plans = Object.fromEntries(Object.entries(exps).map(([k, e]) => [k, caps.page2Plan(e)]));
const recorded = openGate();
plans.open = caps.page2Plan(recorded);
const filters = {
  two: { table_name: 'experiment_baseline', e1_min: 1, e1_max: 20, e2_min: 1, e2_max: 20, d_min: 0, d_max: 900,
    include_undefined_d: false },
  one: { table_name: 'single_hits', e1_min: 1, e1_max: 20 },
  events: { table_name: 'single_events', e1_min: 1, e1_max: 20 },
  open: { table_name: recorded.table_name, e1_min: 1, e1_max: 20 },
};
var out_open_table = recorded.table_name;
const kinds = { two: 'two_shower_hits', one: 'single_shower_hits', events: 'single_shower_events', open: 'open' };
const out = { requests: {}, notices: {}, options: {}, captions: {} };
const view = (extra = {}) => ({ frame: 'lab', model: 'segmentation', feature: 'num_hits', fclass: 'windows',
  fshower: 'a', xgb_task: 'momentum', xgb_label: 'theta', ...extra });
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
  // An aggregate's features in each frame its columns hold, through the shared `frame` key.
  aggregate: Object.fromEntries(['lab', 'trans', 'local', 'canonical'].map((frame) => [frame,
    cards.cardRequest('feat-table', { filters: filters.events, plan: plans.single_shower_events, view: view({ frame }) }).params.coord_system])),
  aggregateCaption: cards.cardCaption('feat-table', { plan: plans.single_shower_events, view: view({ frame: 'canonical' }) }),
};
const frameControl = (plan) => cards.cardControls('feat-corr').find((c) => c.name === 'featureFrame');
const fc = frameControl();
out.frameControl = {
  stateKey: fc.stateKey, choices: fc.choices({}).map((c) => c.value),
  visible: Object.fromEntries(Object.entries(plans).map(([k, plan]) => [k, fc.visible({ plan })])),
  value: fc.get({ plan: plans.single_shower_events, view: view({ frame: 'local' }) }),
  valueCanonical: fc.get({ plan: plans.single_shower_events, view: view({ frame: 'canonical' }) }),
  disabled: ['lab', 'trans', 'local'].map((v) => fc.choiceDisabled({ plan: plans.single_shower_events }, v)),
};
// P-5: the task reads Momentum where the aggregate's XGBoost regressor stands in.
const task = cards.cardControls('perf-bins').find((c) => c.name === 'perfTask');
out.taskLabels = { open: task.choices({ plan: plans.open }).map((c) => [c.value, c.label]),
  two: task.choices({ plan: plans.two_shower_hits }).map((c) => [c.value, c.label]) };
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
  corr: cards.cardOptions('feat-corr', { plan: plans.single_shower_events, view: view({ frame: 'trans' }) }),
};
// The feature explorer's shower: on every feature card of two-shower data, never on one shower.
out.featureShower = {
  b: Object.fromEntries(['feat-table', 'feat-corr', 'feat-hist', 'feat-hist2d'].map((id) => [id,
    cards.cardRequest(id, { filters: filters.two, plan: plans.two_shower_hits, view: view({ fshower: 'b' }) }).params.shower])),
  singleLinkB: cards.cardRequest('feat-hist', { filters: filters.one, plan: plans.single_shower_hits, view: view({ fshower: 'b' }) }).params,
  control: cards.cardControls('feat-hist').map((c) => c.name),
};
out.openTable = out_open_table;
// The resolution card: the selection alone, and on a networked plan the energy network of the frame.
out.resScaling = {
  two: cards.cardRequest('res-scaling', { filters: filters.two, plan: plans.two_shower_hits, view: view({ frame: 'canonical' }) }),
  twoLocal: cards.cardRequest('res-scaling', { filters: filters.two, plan: plans.two_shower_hits,
    view: view({ frame: 'local', model: 'angle' }) }),
  one: cards.cardRequest('res-scaling', { filters: filters.one, plan: plans.single_shower_hits, view: view({ frame: 'local' }) }),
  open: cards.cardRequest('res-scaling', { filters: filters.open, plan: plans.open, view: view() }),
  optionsTwo: cards.cardOptions('res-scaling', { plan: plans.two_shower_hits, view: view(),
    controls: { resWindows: 'all', resScalingShower: 'b' } }),
  optionsOne: cards.cardOptions('res-scaling', { plan: plans.single_shower_hits, view: view(),
    controls: { resScalingShower: 'b' } }),
  notice: cards.cardNotice('res-scaling', { plan: plans.two_shower_hits, view: view() }),
  controls: cards.cardControls('res-scaling').map((c) => c.name),
  views: (() => {
    const ctl = Object.fromEntries(cards.cardControls('res-scaling').map((c) => [c.name, c]));
    const lin = { ...cards.DEFAULT_CONTROLS, resView: 'linear' };
    const en = { ...cards.DEFAULT_CONTROLS, resView: 'energy' };
    const req = (controls) => cards.cardRequest('res-scaling', { filters: filters.two, plan: plans.two_shower_hits,
      view: view({ frame: 'canonical' }), controls });
    return {
      titles: [cards.cardTitle('res-scaling', lin), cards.cardTitle('res-scaling', en),
               cards.cardTitle('res-scaling'), cards.cardTitle('perf-bins', en)],
      refControl: 'resReference' in ctl,
      windows: [ctl.resWindows.choices({ controls: lin }).map((c) => c.label),
                ctl.resWindows.choices({ controls: en }).map((c) => c.label)],
      viewChoices: ctl.resView.choices({}).map((c) => c.value),
      sameRequest: JSON.stringify(req(lin)) === JSON.stringify(req({ ...en, resLiterature: 'e' })),
      opts: cards.cardOptions('res-scaling', { plan: plans.two_shower_hits, view: view(),
        controls: { resView: 'energy', resLiterature: 'e' } }),
      inState: ['resView', 'resLiterature'].map((k) => k in (cards.VIEW_DEFAULTS ?? {})),
      // The literature toggles (Martin's requests of 2026-11-11): one pair, both on by default, also the ratio's reference.
      lit: (() => {
        const at = (resLiterature) => ({ controls: { ...en, resLiterature } });
        return {
          kind: ctl.resLiterature.kind,
          choices: ctl.resLiterature.choices({ controls: en }).map((c) => [c.value, c.label]),
          titles: ctl.resLiterature.choices({ controls: en }).map((c) => c.title),
          visible: [ctl.resLiterature.visible({ controls: lin }), ctl.resLiterature.visible({ controls: en })],
          pressed: ['pi,e', 'e', 'pi', ''].map((l) => ['pi', 'e'].map((c) => ctl.resLiterature.pressed(at(l), c))),
          shut: 'choiceDisabled' in ctl.resLiterature,
          toggle: [['pi,e', 'e'], ['e', 'pi'], ['pi', 'pi'], ['', 'e'], ['', 'pi']].map(([l, c]) => ctl.resLiterature.toggle(at(l), c)),
          keys: [cards.literatureKeys('e,pi'), cards.literatureKeys(''), cards.literatureKeys(undefined), cards.literatureKeys('pi,mu')],
          opts: cards.cardOptions('res-scaling', { plan: plans.two_shower_hits, view: view(), controls: { resView: 'energy' } }),
          defaults: cards.DEFAULT_CONTROLS.resLiterature,
          metas: [
            cards.exportMeta({ meta: {} }, { view: 'energy', literature: ['pi', 'e'] }),
            cards.exportMeta({ meta: {} }, { view: 'energy', literature: ['e'] }),
            cards.exportMeta({ meta: {} }, { view: 'energy', literature: [] }),
            cards.exportMeta({ meta: {} }, { view: 'linear', literature: ['pi', 'e'] }),
          ],
          sameRequest: JSON.stringify(req(lin)) === JSON.stringify(req({ ...en, resLiterature: '' })),
        };
      })(),
    };
  })(),
};
out.abortKeys = cards.ABORT_KEYS;
out.segmentationNotice = cards.SEGMENTATION_NOTICE;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def request_results() -> dict:
    return _run(_REQUEST_SCRIPT, _with_xgb([(JS / "models_cards.js").as_uri(), (JS / "capabilities.js").as_uri(),
                                            _path("experiments")]))


def test_the_abort_keys_are_the_interfaces(request_results):
    assert sorted(request_results["abortKeys"].values()) == sorted([
        "models-perf", "models-pred", "models-res-scaling", "models-feat-table", "models-feat-corr", "models-feat-hist",
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
    table = request_results["openTable"]
    assert table.startswith("electron_m0_20gev_reg_balanced_aggr_s1_v3_")
    r = request_results["xgbAngle"]
    assert r["perf"]["params"]["model"] == "angle"
    assert r["pred"]["params"]["label"] == "phi" and "coord_system" not in r["pred"]["params"]
    assert r["surrogate"] == {"route": "/api/xgboost", "abortKey": "models-xgb-surrogate",
                              "params": {"table_name": table, "view": "surrogate", "task": "angle"}}
    open_ = request_results["requests"]["open"]
    # The momentum model answers the energy task.
    assert open_["perf-bins"]["params"]["model"] == "energy"
    assert open_["xgb-binary"]["params"] == {"table_name": table, "view": "binary"}
    for card in ("xgb-cv", "xgb-importance"):
        assert open_[card]["params"] == {"table_name": table, "view": card.split("-")[1],
                                         "task": "momentum"}, "the XGBoost views take no selection"


def test_the_feature_cards_ask_in_their_frame_with_their_classes(request_results):
    two = request_results["requests"]["two"]
    assert two["feat-table"]["params"] == {**_TWO_FILTERS, "view": "describe", "classes": "windows",
                                           "coord_system": "lab", "shower": "a"}
    assert two["feat-corr"]["params"]["class_index"] == "pooled"
    assert two["feat-hist"]["params"]["feature"] == "num_hits" and "scale" not in two["feat-hist"]["params"]
    assert two["prim-rate"] == {"route": "/api/primaries", "abortKey": "models-prim", "params": _TWO_FILTERS}
    f = request_results["featureFrames"]
    assert f["canonical"]["params"]["coord_system"] == "lab" and f["canonical"]["params"]["scale"] == "linear"
    assert f["canonical"]["params"]["feature"] == "depth"
    assert f["trans"]["params"]["coord_system"] == "trans" and f["trans"]["params"]["class_index"] == "1"
    assert f["trans"]["params"]["classes"] == "label"
    # The aggregate has no hits: only its own nineteen features, in the frame its columns hold.
    assert f["circOnAggregate"]["params"]["coord_system"] == "lab"
    assert f["circOnAggregate"]["params"]["feature"] == "num_hits"


def test_an_aggregates_feature_cards_choose_their_frame_through_the_shared_key(request_results):
    """The events-only kind has no sidebar frame: abs, trn and loc on the cards, never the D-frame."""
    f = request_results["featureFrames"]
    assert f["aggregate"] == {"lab": "lab", "trans": "trans", "local": "local", "canonical": "lab"}
    assert f["aggregateCaption"] and f["aggregateCaption"].startswith("Drawn in Absolute")
    c = request_results["frameControl"]
    assert c["stateKey"] == "frame" and c["choices"] == ["lab", "trans", "local"]
    assert c["visible"] == {"two_shower_hits": False, "single_shower_hits": False,
                            "single_shower_events": True, "open": True}
    assert c["value"] == "local" and c["valueCanonical"] == "lab"
    assert c["disabled"] == [None, None, None]


def test_the_task_reads_momentum_where_the_xgboost_regressor_stands_in(request_results):
    assert request_results["taskLabels"]["open"] == [["energy", "Momentum"], ["angle", "Angle"]]
    assert request_results["taskLabels"]["two"] == [["energy", "Energy"], ["angle", "Angle"]]


def test_every_feature_card_asks_for_the_selected_shower_on_two_shower_data(request_results):
    """The A/B toggle: `fshower` goes with every feat-* request; one-shower data sends none, even from a B link."""
    f = request_results["featureShower"]
    assert f["b"] == {"feat-table": "b", "feat-corr": "b", "feat-hist": "b", "feat-hist2d": "b"}
    for card in FEATURES:
        assert request_results["requests"]["two"][card]["params"]["shower"] == "a", card
    assert "shower" not in f["singleLinkB"], "B does not exist on one shower: the server would refuse it"
    assert f["control"][:2] == ["featureFrame", "fshower"]


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
    assert o["hist"] == {"palette": "viridis", "card": "feat-hist", "classes": "label", "frame": "lab",
                         "feature": "width"}
    assert o["table"] == {"palette": "viridis", "card": "feat-table", "classes": "windows", "frame": "lab",
                          "stat": "mean"}
    # D-10 is the feature card's own: the Physics page's C8 never sets it.
    assert o["corr"] == {"palette": "viridis", "card": "feat-corr", "classes": "windows", "frame": "trans",
                         "fadeNull": True}
    assert o["tree"] == {"palette": "viridis", "card": "xgb-surrogate", "task": "angle", "label": "phi"}
    assert o["binary"] == {"palette": "viridis", "card": "xgb-binary"}


def test_the_resolution_card_asks_with_the_selection_and_the_frames_energy_network(request_results):
    r = request_results["resScaling"]
    assert r["two"]["route"] == "/api/resolution-scaling" and r["two"]["abortKey"] == "models-res-scaling"
    # The D-frame reads the absolute-frame networks; the sidebar's network choice never enters.
    assert r["two"]["params"] == {**_TWO_FILTERS, "coord_system": "lab"}
    assert r["twoLocal"]["params"]["coord_system"] == "local"
    # Without networks the detector series and the XGBoost hold-out need the selection alone.
    assert "coord_system" not in r["one"]["params"] and "coord_system" not in r["open"]["params"]
    # It draws whatever network is selected: no notice, unlike the performance cards.
    assert r["notice"] is None
    assert r["controls"] == ["resView", "resWindows", "resScalingShower", "resLiterature"]
    assert r["optionsTwo"] == {"palette": "viridis", "card": "res-scaling", "view": "linear",
                                "literature": ["pi", "e"], "windows": "all", "shower": "b"}
    # One shower: no shower choice reaches the panel.
    assert r["optionsOne"] == {"palette": "viridis", "card": "res-scaling", "view": "linear",
                                 "literature": ["pi", "e"], "windows": "anchors", "shower": "both"}


def test_the_resolution_card_has_two_views_that_send_nothing(request_results):
    v = request_results["resScaling"]["views"]
    assert v["viewChoices"] == ["linear", "energy"]
    assert v["titles"][0] == v["titles"][2] == "Energy Resolution vs. 1/\u221aE"
    assert v["titles"][1] == "Energy Resolution vs. E"
    assert v["titles"][3] == "Model Error vs. Incident Momentum"
    assert v["refControl"] is False, "one set of literature buttons (Martin, 2026-11-11): no separate reference control"
    assert v["windows"][0] == ["3 anchors", "All \u2265 4 GeV"]
    assert v["windows"][1] == ["3 anchors", "All windows"]
    assert v["sameRequest"] is True
    assert v["opts"]["view"] == "energy" and v["opts"]["literature"] == ["e"] and "reference" not in v["opts"]
    assert v["inState"] == [False, False], "the view and the toggles are never in a link"


def test_the_literature_curves_are_one_pair_of_toggles_both_on_by_default(request_results):
    """Martin's requests of 2026-11-11: one pair of buttons, π± and e±, each a toggle, both on by default. They are
    also the ratio's reference (the curve on; the farther of two; the deposit fit with neither), so nothing is shut
    and no "÷" group remains. No request."""
    lit = request_results["resScaling"]["views"]["lit"]
    assert lit["kind"] == "toggles" and lit["visible"] == [False, True]
    assert lit["choices"] == [["pi", "π±"], ["e", "e±"]]
    for t in lit["titles"]:
        assert t.startswith("Draw or hide σ/E = ") and "no interval reported" in t
        assert "by the one the windows lie farther from when both are, and by each shower's deposit fit when neither is" in t
    assert lit["defaults"] == "pi,e" and lit["opts"]["literature"] == ["pi", "e"]
    assert lit["pressed"] == [[True, True], [False, True], [True, False], [False, False]]
    assert lit["shut"] is False
    # A click adds or takes out one key; the value stays in the catalogue's order; neither may be on.
    assert lit["toggle"] == ["pi", "pi,e", "", "e", "pi"]
    assert lit["keys"] == [["pi", "e"], [], [], ["pi"]]
    # The export names the figure by its curves: both, or the ratio's reference with one or none.
    assert lit["metas"][0] == {"view": "energy", "literature": ["pi", "e"]}
    assert lit["metas"][1] == {"view": "energy", "reference": "e"}
    assert lit["metas"][2] == {"view": "energy", "reference": "deposit"}
    assert lit["metas"][3] == {}
    assert lit["sameRequest"] is True

_TWO_FILTERS = {"table_name": "experiment_baseline", "e1_min": 1, "e1_max": 20, "e2_min": 1, "e2_max": 20,
                "d_min": 0, "d_max": 900, "include_undefined_d": False}


# --------------------------------------------------- the section on a page --

_SECTION_SCRIPT = _FAKE_DOM + r"""
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
// The RatesPanel module fails to load: its loader rejects, as a failed dynamic import does.
const panelModules = { RatesPanel: () => Promise.reject(new TypeError('Failed to fetch dynamically imported module')) };

window.location.hash = '';
const state = new State();
const plan = caps.page2Plan(exps.two_shower_hits);
state.restrictAxes(plan.axes);
state.set({ table_name: 'experiment_baseline' }, { silent: true });
state.adoptSnappedBounds(exps.two_shower_hits.bounds);
const hosts = Object.fromEntries(Object.entries({ perf: 'perf-grid', xgb: 'xgb-grid', xgbDistill: 'xgb-distill-grid',
  features: 'features-grid', primaries: 'primaries-grid' }).map(([k, id]) => {
  const el = document.createElement('section'); el.id = id; return [k, el];
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
const FEATURES_IDS = ['feat-table', 'feat-corr', 'feat-hist', 'feat-hist2d'];
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

// A series the reader switched off on a card's legend: the drawer names it first in Marks and legend, with no
// hazard; the panel's legend callback re-runs the section's onRendered (which rebuilds the drawer), with no request.
{
  const panel = section.cards.get('perf-bins').panel;
  const callsBefore = calls.length;
  const rendersBefore = rendersSeen.length;
  panel.legendSelected = { 'Shower A · network': false, 'An entry of another view': false };
  panel.liveLegend = { data: ['Shower A · network', 'Shower B · network'] };
  out.legendLine = { callback: typeof panel.onLegendChange, notes: section.notes('perf-bins') };
  panel.onLegendChange(panel);
  out.legendLine.renders = rendersSeen.slice(rendersBefore);
  out.legendLine.calls = calls.length - callsBefore;
  panel.legendSelected = { 'Shower A · network': true };
  out.legendLine.back = section.notes('perf-bins');
  // A card with no builder takes the line too (its fallback notes); one whose panel keeps no memory never does.
  const corr = section.cards.get('feat-corr').panel;
  corr.legendSelected = { r: false };
  corr.liveLegend = { data: ['r'] };
  out.legendLine.fallback = section.notes('feat-corr');
  delete corr.legendSelected;
  delete corr.liveLegend;
  out.legendLine.noMemory = section.notes('feat-corr');
  delete panel.legendSelected;
  delete panel.liveLegend;
}
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

// The shower toggle: shown on two-shower data, it writes `fshower` and reloads the four feature cards.
const showerButtons = (id) => cardOf(id).find((el) => el.getAttribute?.('aria-label') === 'Shower');
out.showerToggle = { shown: FEATURES_IDS.map((id) => [id, !showerButtons(id).hidden]) };
const beforeShower = calls.length;
cardOf('feat-corr').find((el) => el.dataset.featureShower === 'b').click();
await settle();
out.showerToggle.calls = calls.slice(beforeShower);
out.showerToggle.state = state.get('fshower');
out.showerToggle.hash = window.location.hash;
out.showerToggle.changes = changes.at(-1);
out.showerToggle.pressed = FEATURES_IDS.map((id) => cardOf(id).find((el) => el.dataset.featureShower === 'b').getAttribute('aria-pressed'));
cardOf('feat-table').find((el) => el.dataset.featureShower === 'a').click();
await settle();
out.showerToggle.back = { state: state.get('fshower'), hash: window.location.hash };

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
out.singleShowerShown = FEATURES_IDS.map((id) => !cardOf(id).find((el) => el.getAttribute?.('aria-label') === 'Shower').hidden);

// A panel module that fails to load: an ordinary failure, said on the card with a Retry.
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
    assert {hosts[c] for c in PERF} == {"perf-grid"}
    # E1 and E3 on Performance, E4 and E5 on Distillations (Martin's decision 4).
    assert {hosts[c] for c in XGB_PERF} == {"xgb-grid"} and {hosts[c] for c in XGB_DISTILL} == {"xgb-distill-grid"}
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


def test_the_drawer_names_what_the_legend_hides_and_a_legend_click_rebuilds_it(section_results):
    """A series switched off on a card's legend is named in the card's drawer (Martin's approval, 2026-11-11): one
    line, first in Marks and legend, naming only what the legend on show lists, and no hazard; the panel's legend
    callback re-runs the section's onRendered, which rebuilds the drawer, and asks the service nothing."""
    got = section_results["legendLine"]
    line = ("Hidden on the legend by the reader: Shower A · network. Click its entry to show it again; "
            "an export leaves it out.")
    assert got["callback"] == "function"
    notes = got["notes"]
    assert [s["heading"] for s in notes["sections"]] == ["What is drawn", "Marks and legend"], notes
    assert notes["sections"][1]["lines"] == [line], notes
    assert notes["hazards"] == section_results["notes"]["perf"]["hazards"] == [], notes
    assert got["renders"] == [["perf-bins", True]] and got["calls"] == 0, got
    # Switched back on: the builder's notes, as before.
    assert got["back"] == section_results["notes"]["perf"], got["back"]
    # The fallback notes take the line too; a panel without a memory never does.
    assert got["fallback"]["sections"][-1] == {"heading": "Marks and legend", "lines": [
        "Hidden on the legend by the reader: r. Click its entry to show it again; an export leaves it out."]}
    assert "Marks and legend" not in [s["heading"] for s in got["noMemory"]["sections"]], got["noMemory"]


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


def test_the_shower_toggle_writes_its_own_key_and_reloads_the_feature_cards(section_results):
    t = section_results["showerToggle"]
    assert all(shown for _, shown in t["shown"]), "shown on two-shower data"
    assert t["state"] == "b" and t["changes"] == {"fshower": "b"} and "fshower=b" in t["hash"]
    assert "event=" not in t["hash"] and "&shower=" not in t["hash"] and not t["hash"].startswith("#shower=")
    views = sorted(c.split("view=")[1].split("&")[0] for c in t["calls"])
    assert views == ["corr", "describe", "hist", "hist2d"]
    assert all("shower=b" in c for c in t["calls"])
    assert t["pressed"] == ["true"] * 4, "every feature card shows the one shared value"
    assert t["back"]["state"] == "a" and "fshower" not in t["back"]["hash"]
    assert section_results["singleShowerShown"] == [False] * 4, "one shower: no toggle"


def test_a_refusal_stays_refused_and_a_transient_failure_is_retried(section_results):
    r = section_results
    assert r["refused"]["hidden"] is False and r["refused"]["retry"] is False and "422" in r["refused"]["text"]
    assert r["refusedAgain"] == 0
    assert r["transient"] == {"retry": True, "kind": "error"} and "503" in r["transientError"]
    assert r["retried"] == {"calls": 1, "hidden": True}


def test_a_response_landing_after_an_experiment_switch_draws_nothing(section_results):
    assert section_results["late"] == {"rendered": 0, "payload": None, "cache": 0, "busy": False}


def test_a_panel_module_that_fails_to_load_is_a_retryable_failure(section_results):
    """Every panel module exists now: a failed import is a load failure like any other, never "not built"."""
    r = section_results
    assert r["notBuilt"]["hidden"] is False and r["notBuilt"]["kind"] == "error"
    assert "dynamically imported module" in r["notBuilt"]["text"] and r["notBuilt"]["retry"] is True
    assert "not built" not in r["notBuilt"]["text"]
    # The response itself was cached: a retry asks for the module again, not the data.
    assert r["notBuiltAgain"] == 0
    assert r["notBuiltLoad"][0] == "Error" and "does not export XgbCvPanel" in r["notBuiltLoad"][1]
    assert [m for _, m in r["errors"]] and all("dynamically imported module" in m for _, m in r["errors"])
    assert r["opened"] == 0


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

// The route as built (calosrv/api/routes_admin.py): pairing and analysis flat on each run.
out.served = admin.modelRunRows({ models: { dir: '/app/xgboost_models' }, runs: [
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
// The backend's recording of the list: each finished run's split checks, per task.
const recordedRuns = admin.modelRunRows(load(JSON.parse(process.argv[1])[2]));
out.recorded = recordedRuns.map((row) => ({ name: row.table_name, status: row.status, splits: row.splits,
  text: admin.runStatusText(row), warning: admin.splitWarning(row) }));
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def tabs_results() -> dict:
    return _run(_TABS_SCRIPT, [(JS / "page_common.js").as_uri(), (JS / "controls" / "admin.js").as_uri(),
                               _path("model_runs_admin")])


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


def test_a_finished_analysis_says_which_split_was_not_reproduced(tabs_results):
    """The admin split block {reproduced, ratio_42, max_others, seed_of_max, n_others, margin}, per task."""
    rows = {r["name"]: r for r in tabs_results["recorded"]}
    (electron,) = [r for name, r in rows.items() if name.startswith("electron_")]
    assert electron["status"] == "done"
    assert [s["task"] for s in electron["splits"]] == ["momentum", "angle"]
    assert set(electron["splits"][0]) == {"task", "reproduced", "ratio_42", "max_others", "seed_of_max", "n_others",
                                          "margin"}
    assert electron["text"].startswith("done in ") and "; split not reproduced (angle: " in electron["text"]
    assert electron["warning"] == ("split not reproduced (angle: validation / training MSE 1.03 at random_state 42 "
                                   "against at most 1.24 at random_state 55, 1.6× required)")
    assert "momentum" not in electron["warning"]
    assert all(not r["warning"] for name, r in rows.items() if not name.startswith("electron_"))


def test_the_model_runs_list_reads_the_served_shape(tabs_results):
    """Pairing and analysis flat on each run, as `GET /api/admin/model-runs` serves them; the shapes from before
    the route settled are no longer read (tests/test_js_admin_model_runs.py holds the reader to the recording)."""
    assert tabs_results["served"] == [[2, "analysing (3 of 7)"], [0, "failed: MemoryError"], [0, "done in 61 s"]]


# ------------------------------------------------------- rescan models --

_RESCAN_SCRIPT = _FAKE_DOM + r"""
const [adminUrl] = JSON.parse(process.argv[1]);
const calls = [];
const run = (status) => ({ table_name: 'electron_s1_aggr', display_name: 'electron', paired: true,
  species: 'electron', seed: 1, models: [], status, reason: null, error: null, step: 0, steps: 18 });
let scanFails = false;
globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url);
  calls.push(`${init.method ?? 'GET'} ${u.pathname}`);
  if (u.pathname === '/api/admin/model-runs/scan') {
    if (scanFails) return { ok: false, status: 500, statusText: 'Server Error', json: async () => ({ detail: 'scan broke' }) };
    return { ok: true, status: 200, json: async () => ({ runs: [run('queued')] }) };
  }
  if (u.pathname === '/api/admin/model-runs') return { ok: true, status: 200, json: async () => ({ runs: [run('running')] }) };
  return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ detail: 'no route' }) };
};
const { AdminModal } = await import(adminUrl);
const status = [];
const fake = Object.create(AdminModal.prototype);
Object.assign(fake, {
  runs: { rows: [], available: null, timer: null, starting: new Set() },
  shell: { isOpen: false },
  setStatus: (text, isError = false) => status.push([text, isError]),
});
const modal = document.createElement('div');
fake.buildModelRuns(modal);
const out = {};
const head = modal.children[0].children[0];
out.buttons = head.children.filter((c) => c.tagName === 'BUTTON').map((b) => b.textContent);
out.hasRescan = fake.runs.rescan?.textContent === 'Rescan models';
fake.runs.rescan.click();
for (let i = 0; i < 20; i += 1) await new Promise((r) => setTimeout(r, 0));
out.calls = [...calls];
out.status = status.slice();
out.rows = fake.runs.rows.map((r) => [r.table_name, r.status]);
out.enabled = !fake.runs.rescan.disabled;
calls.length = 0; status.length = 0; scanFails = true;
await fake.rescanModels();
out.failedCalls = [...calls];
out.failedStatus = status.slice();
out.failedEnabled = !fake.runs.rescan.disabled;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rescan_results() -> dict:
    return _run(_RESCAN_SCRIPT, [(JS / "controls" / "admin.js").as_uri()])


def test_rescan_models_posts_the_scan_then_reads_the_list(rescan_results):
    r = rescan_results
    assert r["hasRescan"] and r["buttons"] == ["Refresh", "Rescan models"]
    # The scan queues; the list is then read from GET, the route that never queues.
    assert r["calls"] == ["POST /api/admin/model-runs/scan", "GET /api/admin/model-runs"]
    assert r["status"] == [["Models rescanned: 1 XGBoost analysis queued or running.", False]]
    assert r["rows"] == [["electron_s1_aggr", "running"]] and r["enabled"]


def test_a_failed_rescan_says_why_and_still_reads_the_list(rescan_results):
    r = rescan_results
    assert r["failedCalls"] == ["POST /api/admin/model-runs/scan", "GET /api/admin/model-runs"]
    assert r["failedStatus"] == [["scan broke", True]] and r["failedEnabled"]


# ------------------------------------------------- the Methodology's deep links --

_DEEP_SCRIPT = _FAKE_DOM + r"""
const [commonUrl] = JSON.parse(process.argv[1]);
const common = await import(commonUrl);
const out = {};
out.hashWith = [
  common.hashWith('#a=1&at=x&b=2', { b: 3, c: 'y' }, { drop: ['at'] }),
  common.hashWith('', { frame: 'local' }),
  common.hashWith('#a=1', { a: null }),
  common.hashWith('#table_name=t&at=eq-old', { at: 'lnk-a' }),
];
out.methodology = [common.methodologyHref('lnk-a', '#table_name=t&at=eq-old'), common.methodologyHref('lnk-a', '')];
out.deep = [
  common.readDeepLink('?panel=xy&from=lnk-frames-axes&from_sec=2.1'),
  common.readDeepLink('?panel=XY&from=bad id&from_sec=2.1.3.4'),
  common.readDeepLink('?admin=1'),
];
out.returns = [
  common.returnLink({ from: 'lnk-frames-axes', section: '2.1' }),
  common.returnLink({ from: 'lnk-frames-axes', section: null }),
  common.returnLink({ from: null, section: '2.1' }),
];
// The tabs drop the page's own key when asked, and carry the hash verbatim otherwise.
const link = (href) => { const a = document.createElement('a'); a.setAttribute('href', href); a.dataset.pageTab = '';
  a.href = href; return a; };
const tabs = [link('/models')];
common.wirePageTabs({ querySelectorAll: () => tabs }, { drop: ['at'] });
window.location.hash = '#x=1&at=eq-a';
tabs[0].dispatch('pointerdown');
out.dropped = tabs[0].href;
const live = link('/methodology');
common.wireLiveLinks([live], () => `/methodology#${window.location.hash.slice(1)}`);
window.location.hash = '#frame=local';
live.dispatch('focus');
out.live = live.href;
// revealPanel: a shown card, a hidden one, an unknown and a malformed id.
const card = (id, hidden = false) => {
  const section = document.createElement('section'); section.hidden = hidden;
  const el = document.createElement('div'); el.className = 'card'; el.dataset.panel = id;
  const inspect = document.createElement('button'); inspect.dataset.inspect = id; el.append(inspect);
  el.querySelector = (sel) => (sel === '[data-inspect]' ? inspect : null);
  el.scrolled = 0; el.scrollIntoView = () => { el.scrolled += 1; };
  section.append(el);
  return el;
};
const shown = card('xy');
const hidden = card('response-b1', true);
const asked = [];
const root = { querySelector: (sel) => { asked.push(sel); return { '.card[data-panel="xy"]': shown, '.card[data-panel="response-b1"]': hidden }[sel] ?? null; } };
const opened = [];
const shell = { openInspector: (id, { trigger }) => opened.push([id, trigger?.dataset.inspect ?? null]) };
const brief = (r) => ({ ok: r.ok, reason: r.reason ?? null });
out.reveal = {
  shown: brief(common.revealPanel('xy', { root, shell })),
  hidden: brief(common.revealPanel('response-b1', { root, shell })),
  unknown: brief(common.revealPanel('zz', { root, shell })),
  malformed: brief(common.revealPanel('xy"],a[href', { root, shell })),
  revealed: brief(common.revealPanel('xy', { root, shell, reveal: (id) => id === 'xy' })),
};
out.scrolled = shown.scrolled;
out.opened = opened;
out.asked = asked;
out.notices = [
  common.revealNotice({ ok: false, reason: 'hidden' }, { title: 'Sampling Fraction — Per-Event Distribution', kind: 'single-shower events' }),
  common.revealNotice({ ok: false, reason: 'unknown' }, { requested: 'zz' }),
  common.revealNotice({ ok: false, reason: 'unknown' }, { requested: '<b>x</b>' }),
  common.revealNotice({ ok: true }),
  common.revealNotice({ ok: false, reason: 'view' }, { title: 'XY Projection — Shower Entry' }),
];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def deep_results() -> dict:
    return _run(_DEEP_SCRIPT, [(JS / "page_common.js").as_uri()])


def test_hash_with_patches_and_drops_keys_in_place(deep_results):
    assert deep_results["hashWith"] == ["a=1&b=3&c=y", "frame=local", "", "table_name=t&at=lnk-a"]
    assert deep_results["methodology"] == ["/methodology#table_name=t&at=lnk-a", "/methodology#at=lnk-a"]


def test_a_deep_link_is_read_and_validated_from_the_query(deep_results):
    good, bad, none = deep_results["deep"]
    assert good == {"panel": "xy", "requested": "xy", "from": "lnk-frames-axes", "section": "2.1"}
    assert bad == {"panel": None, "requested": "XY", "from": None, "section": None}
    assert none is None


def test_the_return_link_names_its_section_when_it_can(deep_results):
    named, plain, none = deep_results["returns"]
    assert named["anchor"] == "lnk-frames-axes" and named["label"] == "↩ Continue reading §2.1 in the Methodology"
    assert plain["label"] == "↩ Continue reading the Methodology"
    assert none is None


def test_tabs_drop_the_methodology_key_and_live_links_follow_the_hash(deep_results):
    assert deep_results["dropped"] == "/models#x=1"
    assert deep_results["live"] == "/methodology#frame=local"


def test_reveal_panel_lands_on_a_shown_card_and_says_why_not_otherwise(deep_results):
    r = deep_results["reveal"]
    assert r["shown"] == {"ok": True, "reason": None}
    assert r["hidden"] == {"ok": False, "reason": "hidden"}
    assert r["unknown"] == {"ok": False, "reason": "unknown"}
    assert r["malformed"] == {"ok": False, "reason": "unknown"}
    assert r["revealed"] == {"ok": True, "reason": None}
    # Scrolled once by revealPanel, not again when the section's own reveal did it.
    assert deep_results["scrolled"] == 1
    assert deep_results["opened"] == [["xy", "xy"], ["xy", "xy"]]
    # A malformed id never reaches the selector.
    assert not any("href" in selector for selector in deep_results["asked"])
    hidden, unknown, hostile, landed, view = deep_results["notices"]
    # A card the view on screen hides is the view's doing, never blamed on the experiment.
    assert view == ("The Methodology linked to the XY Projection — Shower Entry panel, which the view on screen hides "
                    "(an event is pinned, or the frames are compared); go back to the ensemble to see it.")
    assert hidden == ("The Methodology linked to the Sampling Fraction — Per-Event Distribution panel, "
                      "which this experiment (single-shower events) does not show.")
    assert unknown == "The Methodology linked to a panel this page does not have (zz)."
    assert hostile == "The Methodology linked to a panel this page does not have."
    assert landed == ""


# ------------------------------------------------------- the subpages --
#
# The Models page's three subpages (models_subpages.js; state key `msub`) and
# the benchmark catalogue's species (`bench_species`): the two keys in the
# hash, the card→subpage map, the router on the fake document, the bar's
# caption and the deep link that switches to its card's subpage first.

_SUBPAGE_STATE_SCRIPT = _FAKE_DOM + r"""
const [stateUrl] = JSON.parse(process.argv[1]);
const { State, DEFAULTS, MSUBS, BENCH_SPECIES } = await import(stateUrl);
const out = {};
const fresh = (hash) => { window.location.hash = hash; replaced = []; return new State(); };
let s = fresh('#msub=distill&bench_species=muon');
out.read = { msub: s.get('msub'), bench: s.get('bench_species'), cold: s.coldBoot };
s.writeHash();
out.written = window.location.hash;
s = fresh('#msub=extra&bench_species=kaon');
out.invalid = { msub: s.get('msub'), bench: s.get('bench_species'), cold: s.coldBoot };
s = fresh('#bench_species=all');
out.all = s.get('bench_species');
s = fresh('');
s.set({ msub: 'perf' });
out.perfHash = window.location.hash;
s.set({ msub: 'views' });
out.viewsHash = window.location.hash;
s.set({ bench_species: 'electron' });
out.benchHash = window.location.hash;
s.set({ bench_species: null });
out.benchBack = window.location.hash;
// Neither page strips the other's keys: a Physics key and the Models keys survive one another's writes.
s = fresh('#event=3&compare=true&msub=perf&bench_species=pion');
s.set({ channel: 'gradcam' });
out.mixed = window.location.hash;
// Not defaultable: a cold boot takes the Admin defaults, and never these two.
s = fresh('');
out.applied = s.applyDefaults({ table_name: 'alpha', frame: 'trans', msub: 'perf', bench_species: 'muon' });
out.afterDefaults = { msub: s.get('msub'), bench: s.get('bench_species'), frame: s.get('frame') };
out.defaults = { msub: DEFAULTS.msub, bench_species: DEFAULTS.bench_species };
out.enums = { msubs: [...MSUBS], bench: [...BENCH_SPECIES] };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def subpage_state() -> dict:
    return _run(_SUBPAGE_STATE_SCRIPT, [(JS / "state.js").as_uri()])


def test_the_subpage_and_species_keys_round_trip_through_the_hash(subpage_state):
    r = subpage_state
    assert r["read"] == {"msub": "distill", "bench": "muon", "cold": False}
    assert r["written"] == "#msub=distill&bench_species=muon"
    assert r["all"] == "all"
    assert r["enums"] == {"msubs": ["views", "distill", "perf"],
                          "bench": ["proton", "muon", "electron", "pion", "all"]}


def test_the_subpage_and_species_defaults_are_never_written(subpage_state):
    r = subpage_state
    assert r["defaults"] == {"msub": "views", "bench_species": None}
    assert r["perfHash"] == "#msub=perf" and r["viewsHash"] == ""
    assert r["benchHash"] == "#bench_species=electron" and r["benchBack"] == ""


def test_an_invalid_subpage_or_species_keeps_its_default(subpage_state):
    assert subpage_state["invalid"] == {"msub": "views", "bench": None, "cold": False}


def test_neither_page_strips_the_subpage_keys_and_admin_defaults_never_set_them(subpage_state):
    r = subpage_state
    written = dict(part.split("=") for part in r["mixed"].lstrip("#").split("&"))
    assert written == {"event": "3", "compare": "true", "msub": "perf", "bench_species": "pion",
                       "channel": "gradcam"}
    assert r["applied"] is True
    assert r["afterDefaults"] == {"msub": "views", "bench": None, "frame": "trans"}


def _voxel_card_ids() -> list:
    source = (JS / "voxel_views.js").read_text(encoding="utf-8")
    block = source[source.index("export const VOXEL_CARDS"):]
    block = block[:block.index("]);")]
    return re.findall(r"\{ id: '([^']+)'", block)


_ROUTER_SCRIPT = _FAKE_DOM + _OPEN_GATE + _XGB_ARG + r"""
const [stateUrl, subUrl, capsUrl, cardsUrl, commonUrl, voxelIds, cataloguePath] = JSON.parse(process.argv[1]);
const { State } = await import(stateUrl);
const sub = await import(subUrl);
const caps = await import(capsUrl);
const cards = await import(cardsUrl);
const common = await import(commonUrl);
const catalogue = load(cataloguePath);
const out = {};

// The card -> subpage map, for every card of both sections.
out.ofCard = Object.fromEntries([...cards.MODELS_CARDS.map((c) => c.id), ...voxelIds]
  .map((id) => [id, sub.subpageOfCard(id)]));
out.ofUnknown = [sub.subpageOfCard('xy'), sub.subpageOfCard(''), sub.subpageOfCard(null), sub.subpageOfCard('voxels')];
out.voxelFamily = voxelIds.map((id) => sub.VOXEL_FAMILY.test(id));
out.cardsFamily = cards.MODELS_CARDS.filter((c) => sub.VOXEL_FAMILY.test(c.id)).map((c) => c.id);
out.sections = Object.fromEntries(cards.MODELS_CARDS.map((c) => [c.id, c.section]));
out.subpageSections = caps.SUBPAGE_SECTIONS;

// The router on a fake page: three tabs, three wrappers, .app and .main.
let focused = null;
const page = () => {
  const ids = new Map();
  const make = (tag, id) => { const el = document.createElement(tag); if (id) { el.id = id; ids.set(id, el); } return el; };
  const app = make('div'); app.className = 'app';
  const main = make('main'); main.className = 'main'; main.scrollTop = 0;
  app.append(main);
  const nav = make('nav', 'models-subnav'); main.append(nav);
  for (const m of ['views', 'distill', 'perf']) {
    const tab = make('button', `msub-tab-${m}`);
    tab.focus = () => { focused = tab.id; };
    nav.append(tab);
    const panel = make('div', `msub-${m}`);
    panel.hidden = m !== 'views';
    main.append(panel);
  }
  // A card in each wrapper, as the sections hold them.
  const card = (id, wrapper) => {
    const el = make('div'); el.className = 'card'; el.dataset.panel = id;
    const inspect = make('button'); inspect.dataset.inspect = id; el.append(inspect);
    el.querySelector = (sel) => (sel === '[data-inspect]' ? inspect : null);
    el.scrollIntoView = () => {};
    ids.get(wrapper).append(el);
    return el;
  };
  const cardEls = { 'vox-event': card('vox-event', 'msub-views'), 'distill-pysr': card('distill-pysr', 'msub-distill'),
    'xgb-surrogate': card('xgb-surrogate', 'msub-distill'), 'perf-catalog': card('perf-catalog', 'msub-perf') };
  return {
    app, main, ids, cardEls,
    root: {
      getElementById: (id) => ids.get(id) ?? null,
      querySelector: (sel) => {
        if (sel === '.app') return app;
        if (sel === '.main') return main;
        const m = /^\.card\[data-panel="([^"]+)"\]$/.exec(sel);
        return m ? cardEls[m[1]] ?? null : null;
      },
    },
  };
};
const snapshot = (p) => ({
  hidden: ['views', 'distill', 'perf'].map((m) => p.ids.get(`msub-${m}`).hidden),
  selected: ['views', 'distill', 'perf'].map((m) => p.ids.get(`msub-tab-${m}`).getAttribute('aria-selected')),
  tabindex: ['views', 'distill', 'perf'].map((m) => p.ids.get(`msub-tab-${m}`).getAttribute('tabindex')),
  app: p.app.dataset.msub,
  hash: window.location.hash,
  scroll: p.main.scrollTop,
});

window.location.hash = '';
let state = new State();
let p = page();
const children = () => ['views', 'distill', 'perf'].map((m) => p.ids.get(`msub-${m}`).children.length);
const before = children();
const switched = [];
let router = sub.mountSubnav({ state, root: p.root, onSwitch: (m) => switched.push([m, window.location.hash]) });
out.initial = { ...snapshot(p), current: router.current(), switched: [...switched] };

// A click: the wrapper shown, the tab selected, the hash written, onSwitch after the write.
p.main.scrollTop = 420;
p.ids.get('msub-tab-perf').click();
out.click = { ...snapshot(p), current: router.current(), switched: [...switched] };
// Scroll memory: each subpage keeps its own place, restored on return.
p.main.scrollTop = 75;
router.show('views');
out.backToViews = snapshot(p);
router.show('perf');
out.backToPerf = snapshot(p);
// Showing the subpage on show changes nothing and calls no one.
const n = switched.length;
out.same = { changed: router.show('perf'), switched: switched.length - n };
// An unknown subpage means Views.
router.show('bogus');
out.bogus = snapshot(p);
// The keys (WAI-ARIA tabs): arrows wrap, Home and End jump, focus follows the selection.
const key = (m, k) => {
  let prevented = false;
  for (const fn of p.ids.get(`msub-tab-${m}`).listeners.keydown ?? []) fn({ key: k, preventDefault() { prevented = true; } });
  return { current: router.current(), focused, prevented };
};
out.keys = [key('views', 'ArrowLeft'), key('perf', 'ArrowRight'), key('views', 'ArrowRight'), key('distill', 'End'),
  key('perf', 'Home'), key('views', 'Tab')];
out.afterKeys = snapshot(p);
// Write false: no hash write, the switch still made.
router.show('distill', { write: false });
out.noWrite = { ...snapshot(p), state: state.get('msub') };
// The WebGL rule: no switch created or removed a card.
out.children = { before, after: children() };

// A link's subpage is applied at mount, silently: no write, no onSwitch.
window.location.hash = '#msub=distill&frame=local';
state = new State();
p = page();
replaced = [];
const quiet = [];
router = sub.mountSubnav({ state, root: p.root, onSwitch: (m) => quiet.push(m) });
out.linked = { ...snapshot(p), current: router.current(), switched: quiet, writes: replaced.length };

// The deep link: a card on a hidden subpage cannot land; the switch first lets it.
window.location.hash = '';
state = new State();
p = page();
router = sub.mountSubnav({ state, root: p.root });
const opened = [];
const shell = { openInspector: (id) => opened.push(id) };
out.deep = { before: common.revealPanel('perf-catalog', { root: p.root, shell }).ok };
router.show(sub.subpageOfCard('perf-catalog'));
out.deep.after = common.revealPanel('perf-catalog', { root: p.root, shell }).ok;
out.deep.twice = router.show(sub.subpageOfCard('perf-catalog'));
out.deep.opened = [...opened];
out.deep.hash = window.location.hash;
// The 3-D views' card lands on Views.
router.show(sub.subpageOfCard('vox-event'));
out.deep.voxel = common.revealPanel('vox-event', { root: p.root, shell }).ok;

// The catalogue's bar: what a species click stores, and the caption.
const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const two = caps.page2Plan(exps.two_shower_hits);
const electron = caps.page2Plan(openGate());
const none = caps.page2Plan(null);
out.store = {
  electronFollow: sub.benchSpeciesToStore('electron', electron),
  electronMuon: sub.benchSpeciesToStore('muon', electron),
  electronAll: sub.benchSpeciesToStore('all', electron),
  twoAll: sub.benchSpeciesToStore('all', two),
  twoProton: sub.benchSpeciesToStore('proton', two),
};
out.caption = {
  following: sub.benchCaption(null, electron),
  unnamed: sub.benchCaption(null, two),
  closed: sub.benchCaption(null, none, { open: false }),
  chosen: sub.benchCaption('muon', electron),
  chosenUnnamed: sub.benchCaption('muon', two),
  chosenAll: sub.benchCaption('all', electron),
  chosenOwn: sub.benchCaption('electron', electron),
  unknown: sub.benchCaption('kaon', two),
};
out.provenance = sub.BENCH_PROVENANCE;

// The sticky head's height: measured at once, rounded up, again on every resize the observer reports and on demand.
const observers = [];
class RO { constructor(cb) { this.cb = cb; observers.push(this); } observe(t) { this.target = t; } disconnect() { this.gone = true; } }
let height = 57.2;
const headEl = { getBoundingClientRect: () => ({ height }) };
const styled = () => ({ props: {}, setProperty(k, v) { this.props[k] = v; } });
const target = { style: styled() };
const watcher = sub.watchHeadHeight({ head: headEl, target, Observer: RO });
out.head = { first: target.style.props['--models-head-h'], observed: observers[0].target === headEl };
height = 140;
observers[0].cb();
out.head.resized = target.style.props['--models-head-h'];
height = 90.01;
out.head.measured = [watcher.measure(), target.style.props['--models-head-h']];
watcher.disconnect();
out.head.gone = Boolean(observers[0].gone);
const bare = { style: styled() };
sub.watchHeadHeight({ head: headEl, target: bare, Observer: undefined });
out.head.withoutObserver = bare.style.props['--models-head-h'];
out.head.noHead = sub.watchHeadHeight({ head: null, target: bare }).measure();

// What a subpage shows: its own cards' warnings, the Colour Map, the XGBoost notice.
const onPerf = sub.onSubpage('perf');
const onViews = sub.onSubpage('views');
out.onSubpage = { perf: ['perf-catalog', 'pred-residuals', 'xgb-cv', 'distill-pysr', 'vox-event', 'feat-table'].map(onPerf),
  views: ['vox-event', 'vproj-xy', 'feat-table', 'prim-rate', 'pred-residuals'].map(onViews) };
out.colourMap = Object.fromEntries([['two', two], ['electron', electron], ['none', none]].map(([k, plan]) =>
  [k, ['views', 'distill', 'perf'].map((m) => sub.colourMapShown(m, plan))]));
out.xgbNotice = Object.fromEntries([['two', two], ['electron', electron], ['none', none]].map(([k, plan]) =>
  [k, { has: Boolean(plan.xgbNotice), shown: ['views', 'distill', 'perf'].map((m) => sub.xgbNoticeShown(m, plan)) }]));
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def router_results() -> dict:
    return _run(_ROUTER_SCRIPT, _with_xgb([
        (JS / "state.js").as_uri(), (JS / "models_subpages.js").as_uri(), (JS / "capabilities.js").as_uri(),
        (JS / "models_cards.js").as_uri(), (JS / "page_common.js").as_uri(), _voxel_card_ids(), _path("experiments"),
    ]))


def test_every_card_has_its_subpage(router_results):
    r = router_results
    expected = {"views": ["voxels", "features", "primaries"], "distill": ["distill", "xgbDistill"],
                "perf": ["perf", "resolution", "xgb", "bench"]}
    assert r["subpageSections"] == expected
    of_section = {section: msub for msub, sections in expected.items() for section in sections}
    for card, section in r["sections"].items():
        assert r["ofCard"][card] == of_section[section], card
    voxel_ids = _voxel_card_ids()
    assert len(voxel_ids) == 8 and all(r["ofCard"][card] == "views" for card in voxel_ids)
    # E1/E3 on Performance, E4/E5 on Distillations, the catalogue on both (decision 4).
    assert [r["ofCard"][c] for c in ("xgb-cv", "xgb-binary", "xgb-surrogate", "xgb-importance")] == \
        ["perf", "perf", "distill", "distill"]
    assert [r["ofCard"][c] for c in ("distill-pysr", "distill-triangle", "distill-curves")] == ["distill"] * 3
    assert [r["ofCard"][c] for c in ("perf-catalog", "perf-overlap", "perf-momentum-bias", "perf-diagnostics")] == \
        ["perf"] * 4
    assert r["ofUnknown"] == [None, None, None, None]


def test_the_voxel_family_is_the_3d_cards_and_no_other(router_results):
    assert all(router_results["voxelFamily"])
    assert router_results["cardsFamily"] == []


def test_the_router_starts_on_the_states_subpage_silently(router_results):
    r = router_results
    assert r["initial"]["hidden"] == [False, True, True]
    assert r["initial"]["selected"] == ["true", "false", "false"]
    assert r["initial"]["tabindex"] == ["0", "-1", "-1"]
    assert r["initial"]["app"] == "views" and r["initial"]["current"] == "views"
    assert r["initial"]["switched"] == [] and r["initial"]["hash"] == ""
    linked = r["linked"]
    assert linked["hidden"] == [True, False, True] and linked["selected"] == ["false", "true", "false"]
    assert linked["tabindex"] == ["-1", "0", "-1"] and linked["app"] == "distill"
    assert linked["switched"] == [] and linked["writes"] == 0 and linked["current"] == "distill"


def test_a_click_switches_writes_the_hash_and_then_tells_the_page(router_results):
    c = router_results["click"]
    assert c["hidden"] == [True, True, False] and c["selected"] == ["false", "false", "true"]
    assert c["tabindex"] == ["-1", "-1", "0"] and c["app"] == "perf" and c["current"] == "perf"
    assert c["hash"] == "#msub=perf"
    # onSwitch runs after the write: it sees the new hash.
    assert c["switched"] == [["perf", "#msub=perf"]]
    # Views is the default: it leaves the hash.
    assert router_results["backToViews"]["hash"] == ""


def test_each_subpage_keeps_its_own_scroll_position(router_results):
    r = router_results
    assert r["click"]["scroll"] == 0, "Performance had never been scrolled"
    assert r["backToViews"]["scroll"] == 420
    assert r["backToPerf"]["scroll"] == 75


def test_showing_the_subpage_on_show_is_a_no_op_and_an_unknown_one_is_views(router_results):
    r = router_results
    assert r["same"] == {"changed": False, "switched": 0}
    assert r["bogus"]["hidden"] == [False, True, True] and r["bogus"]["app"] == "views"


def test_the_tab_keys_follow_the_wai_aria_pattern(router_results):
    keys = router_results["keys"]
    # Left from the first wraps to the last; right from the last wraps to the first.
    assert keys[0] == {"current": "perf", "focused": "msub-tab-perf", "prevented": True}
    assert keys[1] == {"current": "views", "focused": "msub-tab-views", "prevented": True}
    assert keys[2] == {"current": "distill", "focused": "msub-tab-distill", "prevented": True}
    assert keys[3] == {"current": "perf", "focused": "msub-tab-perf", "prevented": True}
    assert keys[4] == {"current": "views", "focused": "msub-tab-views", "prevented": True}
    # Any other key is the browser's (Tab leaves the tab list).
    assert keys[5] == {"current": "views", "focused": "msub-tab-views", "prevented": False}
    assert router_results["afterKeys"]["tabindex"] == ["0", "-1", "-1"]


def test_a_switch_without_a_write_leaves_the_link_alone(router_results):
    r = router_results["noWrite"]
    assert r["hidden"] == [True, False, True] and r["hash"] == "" and r["state"] == "views"


def test_a_switch_creates_and_removes_no_card(router_results):
    assert router_results["children"]["before"] == router_results["children"]["after"] == [1, 2, 1]
    source = _strip_comments((JS / "models_subpages.js").read_text(encoding="utf-8"))
    for forbidden in ("dispose", "createElement", "innerHTML", "replaceChildren", ".remove(", "echarts"):
        assert forbidden not in source, forbidden


def test_a_deep_link_switches_to_its_cards_subpage_before_it_lands(router_results):
    d = router_results["deep"]
    assert d["before"] is False, "a card on a hidden subpage cannot land"
    assert d["after"] is True and d["twice"] is False and d["opened"] == ["perf-catalog"]
    assert d["hash"] == "#msub=perf" and d["voxel"] is True


def test_a_species_click_on_the_experiments_own_species_follows_it_again(router_results):
    assert router_results["store"] == {"electronFollow": None, "electronMuon": "muon", "electronAll": "all",
                                       "twoAll": None, "twoProton": "proton"}


def test_the_bench_caption_says_whose_species_and_where_it_comes_from(router_results):
    c, provenance = router_results["caption"], router_results["provenance"]
    assert provenance == ("From the training report (models_performance.md; proton results dated 2026-09-24): "
                          "documented point estimates, no intervals reported; the selection and the experiment do "
                          "not apply.")
    assert all(text.endswith(provenance) for text in c.values())
    assert c["following"].startswith("Following the experiment: Electron, the species of its paired XGBoost models.")
    assert c["unnamed"].startswith("This experiment does not name its species, so the catalogue shows all four.")
    assert c["closed"].startswith("No experiment is open, so the catalogue shows all four.")
    assert c["chosen"].startswith("Chosen: Muon. Choose Electron to follow the experiment again.")
    assert c["chosenUnnamed"].startswith("Chosen: Muon. Choose Compare all to follow the experiment again.")
    assert c["chosenAll"].startswith("Chosen: Compare all. Choose Electron to follow the experiment again.")
    assert c["chosenOwn"].startswith("Chosen: Electron, which is also what the experiment would show")
    assert c["unknown"] == c["unnamed"]


def test_the_sticky_heads_height_is_kept_in_a_css_variable(router_results):
    h = router_results["head"]
    assert h["first"] == "58px" and h["observed"], "measured at once, rounded up, and observed"
    assert h["resized"] == "140px" and h["measured"] == [91, "91px"] and h["gone"]
    assert h["withoutObserver"] == "91px" and h["noHead"] is None


def test_a_subpage_shows_its_own_cards_warnings_colour_map_and_xgboost_notice(router_results):
    r = router_results
    assert r["onSubpage"]["perf"] == [True, True, True, False, False, False]
    assert r["onSubpage"]["views"] == [True, True, True, True, False]
    # Decision 3: Views always; Distillations with E4; Performance with the prediction density.
    assert r["colourMap"]["two"] == [True, False, True]
    assert r["colourMap"]["electron"] == [True, True, True]
    assert r["colourMap"]["none"] == [True, False, False]
    # R2-6: the XGBoost notice only where the XGBoost sections live, and only while the plan has it.
    assert r["xgbNotice"]["two"] == {"has": True, "shown": [False, True, True]}
    assert r["xgbNotice"]["electron"] == {"has": False, "shown": [False, False, False]}


# ------------------------------------------------- the page itself, run --

#: models.html parsed into the fake document, so ``models_main.js`` runs as written: its module body, its
#: boot, the router, the bars and the banners, against a stubbed network. A selector engine (compound,
#: descendant, groups, ``:not``), the window (URL with its query, a history that drops it, storage, media),
#: observers that record what they watch, and ``fetch`` from ``routes``/``failures`` by path, each request
#: logged with the subpage on show when it left. ``#models-head`` measures 40 px, and with the bench bar 80 more
#: and 1 px per 10 characters of its caption, so a caption rewritten after a switch changes the head.
_PAGE_DOM = r"""
// ---- The page harness: models.html parsed into the fake document, so models_main.js runs as written. ----
const pageArgs = JSON.parse(process.argv[1]).at(-1);
const camel = (name) => name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
const attrOf = (el, name) => {
  if (name === 'id') return el.id || null;
  if (name === 'class') return el.className || null;
  if (name === 'hidden') return el.hidden ? '' : null;
  if (name === 'title') return el.title || el.attrs.title || null;
  if (name === 'value') return el.value !== '' && el.value !== undefined ? String(el.value) : (el.attrs.value ?? null);
  if (name.startsWith('data-')) { const v = el.dataset[camel(name.slice(5))]; return v === undefined ? null : String(v); }
  return name in el.attrs ? el.attrs[name] : null;
};
// One compound selector: tag, #id, .class, [attr], [attr="v"], :not(<compound>).
const compound = (text) => {
  const parts = [];
  const re = /:not\(([^)]*)\)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]|^([\w-]+|\*)/g;
  for (const m of text.matchAll(re)) {
    if (m[1] !== undefined) { const inner = compound(m[1]); parts.push((el) => !inner(el)); }
    else if (m[2]) parts.push((el) => el.id === m[2]);
    else if (m[3]) parts.push((el) => el.classList.contains(m[3]));
    else if (m[4]) parts.push((el) => (m[5] === undefined ? attrOf(el, m[4]) !== null : attrOf(el, m[4]) === m[5]));
    else if (m[6] && m[6] !== '*') parts.push((el) => el.tagName === m[6].toUpperCase());
  }
  return (el) => parts.every((p) => p(el));
};
const selectorFn = (selector) => {
  const alternatives = selector.split(',').map((s) => s.trim().split(/\s+/).map(compound));
  return (el) => alternatives.some((chain) => {
    if (!chain.at(-1)(el)) return false;
    let node = el.parent; let i = chain.length - 2;
    while (i >= 0 && node) { if (node instanceof FakeElement && chain[i](node)) i -= 1; node = node.parent; }
    return i < 0;
  });
};
const P = FakeElement.prototype;
P.matches = function matches(selector) { return selectorFn(selector)(this); };
P.querySelectorAll = function querySelectorAll(selector) {
  const fn = selectorFn(selector); const out = [];
  for (const c of this.children) c.walk((el) => { if (fn(el)) out.push(el); });
  return out;
};
P.querySelector = function querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; };
P.getElementById = function getElementById(id) { return this.find((el) => el.id === id); };
P.remove = function remove() { if (this.parent) this.parent.childNodes = this.parent.childNodes.filter((c) => c !== this); this.parent = null; };
P.appendChild = function appendChild(node) { this.append(node); return node; };
P.prepend = function prepend(...nodes) { const old = this.childNodes; this.childNodes = []; this.append(...nodes); for (const c of old) { this.childNodes.push(c); } };
P.insertBefore = function insertBefore(node, ref) {
  node.remove?.(); node.parent = this;
  const at = ref ? this.childNodes.indexOf(ref) : -1;
  if (at < 0) this.childNodes.push(node); else this.childNodes.splice(at, 0, node);
  return node;
};
P.after = function after(...nodes) { const parent = this.parent; const at = parent.childNodes.indexOf(this);
  for (const n of nodes) { n.remove?.(); n.parent = parent; } parent.childNodes.splice(at + 1, 0, ...nodes); };
P.before = function before(...nodes) { const parent = this.parent; const at = parent.childNodes.indexOf(this);
  for (const n of nodes) { n.remove?.(); n.parent = parent; } parent.childNodes.splice(at, 0, ...nodes); };
P.contains = function contains(node) { for (let n = node; n; n = n.parent) if (n === this) return true; return false; };
// A 2-D canvas context as far as the text fitters use it: 6 px per character.
P.getContext = function getContext() { return { font: '', measureText: (t) => ({ width: String(t).length * 6 }) }; };
P.focus = function focus() { document.activeElement = this; };
P.blur = function blur() {};
P.scrollIntoView = function scrollIntoView(options) { scrolledTo.push([this.dataset.panel ?? this.id, options ?? null]); };
P.getBoundingClientRect = function getBoundingClientRect() {
  const height = typeof this.measuredHeight === 'function' ? this.measuredHeight() : 0;
  return { top: 0, left: 0, right: 600, bottom: height, width: 600, height, x: 0, y: 0 };
};
P.removeEventListener = function removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn); };
P.dispatchEvent = function dispatchEvent(event) {
  for (let el = this; el; el = el.parent) {
    for (const fn of el.listeners?.[event.type] ?? []) fn({ ...event, type: event.type, detail: event.detail, target: this,
      stopPropagation() {}, preventDefault() {} });
    if (!event.bubbles) break;
  }
  return true;
};
Object.defineProperty(P, 'offsetWidth', { get() { return 600; } });
Object.defineProperty(P, 'offsetHeight', { get() { return 0; } });
Object.defineProperty(P, 'firstChild', { get() { return this.childNodes[0] ?? null; } });
Object.defineProperty(P, 'firstElementChild', { get() { return this.children[0] ?? null; } });
Object.defineProperty(P, 'nextElementSibling', { get() { const s = this.parent?.children ?? []; return s[s.indexOf(this) + 1] ?? null; } });
const styleOf = () => {
  const values = {};
  return new Proxy(values, { get(target, key) {
    if (key === 'setProperty') return (k, v) => { target[k] = String(v); };
    if (key === 'getPropertyValue') return (k) => target[k] ?? '';
    if (key === 'removeProperty') return (k) => { delete target[k]; };
    return target[key] ?? '';
  } });
};

// A small HTML parser: the body of models.html as FakeElements.
const VOID = new Set(['input', 'br', 'img', 'meta', 'link', 'hr', 'source', 'wbr', 'col']);
const ENTITIES = { '&times;': '×', '&mdash;': '—', '&ndash;': '–', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"',
  '&#8217;': '’', '&rarr;': '→', '&nbsp;': ' ' };
const decode = (text) => text.replace(/&[#\w]+;/g, (e) => ENTITIES[e] ?? e);
function makeElement(tag) {
  const el = new FakeElement(tag); el.style = styleOf(); return el;
}
function parseBody(html) {
  const body = makeElement('body');
  const start = html.indexOf('<body>') + 6; const end = html.indexOf('</body>');
  const src = html.slice(start, end).replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>/g, '');
  const stack = [body];
  const re = /<\/?([a-zA-Z][\w-]*)((?:\s+[\w:-]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*\/?>|([^<]+)/g;
  let m;
  while ((m = re.exec(src))) {
    if (m[3] !== undefined) { const text = decode(m[3]); if (text.trim()) stack.at(-1).append(new FakeText(text)); continue; }
    const tag = m[1].toLowerCase();
    if (m[0].startsWith('</')) { while (stack.length > 1 && stack.pop().tagName !== tag.toUpperCase()); continue; }
    const el = makeElement(tag);
    const attrRe = /([\w:-]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?/g;
    let a;
    while ((a = attrRe.exec(m[2] ?? ''))) {
      const name = a[1].toLowerCase();
      const value = a[2] === undefined ? '' : decode(a[2].replace(/^["']|["']$/g, ''));
      if (name === 'id') el.id = value;
      else if (name === 'class') el.className = value;
      else if (name === 'hidden') el.hidden = true;
      else if (name === 'title') el.title = value;
      else if (name === 'value') el.value = value;
      else if (name === 'disabled') el.disabled = true;
      else if (name.startsWith('data-')) el.dataset[camel(name.slice(5))] = value;
      else el.attrs[name] = value;
    }
    if (tag === 'option' && !('value' in el.attrs) && el.value === '') el.valueFromText = true;
    stack.at(-1).append(el);
    if (!VOID.has(tag) && !m[0].endsWith('/>')) stack.push(el);
  }
  return body;
}
const scrolledTo = [];
const html = readFileSync(pageArgs.html, 'utf8');
const body = parseBody(html);
const docEl = makeElement('html');
docEl.append(body);
const docListeners = {};
globalThis.document = {
  body, documentElement: docEl,
  createElement: (tag) => makeElement(tag),
  createElementNS: (_ns, tag) => makeElement(tag),
  createTextNode: (text) => new FakeText(text),
  createDocumentFragment: () => makeElement('fragment'),
  getElementById: (id) => body.getElementById(id),
  querySelector: (s) => body.querySelector(s),
  querySelectorAll: (s) => body.querySelectorAll(s),
  addEventListener: (type, fn) => { (docListeners[type] ??= []).push(fn); },
  removeEventListener() {},
  activeElement: null,
  visibilityState: 'visible',
};
// The window: the page's URL, a history that keeps the query until it is replaced, storage, media, timers.
const storage = new Map();
const url = new URL(pageArgs.url);
const windowListeners = {};
globalThis.window = globalThis;
globalThis.location = { hash: url.hash, search: url.search, pathname: url.pathname, origin: url.origin,
  get href() { return `${url.origin}${this.pathname}${this.search}${this.hash}`; }, assign(u) { assigned.push(u); } };
const assigned = [];
replaced = [];
globalThis.history = {
  replaceState(_s, _t, next) {
    replaced.push(next);
    const u = new URL(next, url.origin);
    location.pathname = u.pathname; location.search = u.search; location.hash = u.hash;
  },
};
globalThis.addEventListener = (type, fn) => { (windowListeners[type] ??= []).push(fn); };
globalThis.removeEventListener = () => {};
globalThis.localStorage = { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, String(v)),
  removeItem: (k) => storage.delete(k) };
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {} });
globalThis.innerWidth = 1600; globalThis.innerHeight = 1000;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });
globalThis.CustomEvent = class CustomEvent { constructor(type, init = {}) { this.type = type; this.detail = init.detail; this.bubbles = Boolean(init.bubbles); } };
globalThis.Event = class Event { constructor(type, init = {}) { this.type = type; this.bubbles = Boolean(init.bubbles); } };
const resizeObservers = [];
globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; this.targets = []; resizeObservers.push(this); }
  observe(t) { this.targets.push(t); } unobserve() {} disconnect() { this.targets = []; } };
const intersections = [];
globalThis.IntersectionObserver = class extends FakeObserver { constructor(cb, o) { super(cb, o); intersections.push(this); } };
// Show cards to every observer that watches them, as scrolling them into view does.
const intersect = (els) => { for (const o of intersections) { const t = els.filter((e) => o.targets.includes(e)); if (t.length) o.show(t); } };
// The network: a log of every request with the subpage on show when it left.
const requests = [];
const routes = pageArgs.routes ?? {};
globalThis.fetch = async (input, init = {}) => {
  const u = new URL(String(input), url.origin);
  requests.push({ path: u.pathname + u.search, msub: document.querySelector('.app')?.dataset.msub ?? null,
    hash: location.hash });
  const failure = (pageArgs.failures ?? {})[u.pathname];
  if (failure) return { ok: false, status: failure, statusText: 'x', json: async () => ({ detail: `refused ${failure}` }) };
  const body = routes[u.pathname];
  if (body === undefined) return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ detail: 'no route' }) };
  return { ok: true, status: 200, json: async () => structuredClone(body) };
};
const consoleErrors = [];
console.error = (...a) => consoleErrors.push(a.map((x) => (x instanceof Error ? `${x.message}\n${x.stack}` : String(x))).join(' '));
// ECharts as far as a card's panel touches it: a chart that takes any option and measures 600 x 330.
const chartStub = (dom) => new Proxy({ getWidth: () => 600, getHeight: () => 330, getDom: () => dom,
  isDisposed: () => false, getZr: () => ({ on() {}, off() {} }) }, {
  get: (target, key) => (key === 'then' ? undefined : (target[key] ?? (() => undefined))) });
globalThis.echarts = { init: (dom) => chartStub(dom), getInstanceByDom: () => null };
const shown = (id) => { const el = document.getElementById(id); if (!el) return null; for (let n = el; n; n = n.parent) if (n.hidden) return false; return true; };
"""

_PAGE_BOOT = r"""
const head = document.getElementById('models-head');
// The head: 40 px of tabs, then the bench bar's 40 px row of buttons, which wraps one more line of 20 px
// while the Details drawer narrows the column (the caption is not in the head: it scrolls away).
if (head) head.measuredHeight = () => 40 + (document.getElementById('bench-bar').hidden ? 0
  : 40 + (document.querySelector('.app').classList.contains('is-inspector-open') ? 20 : 0));
// An id the markup lost: the element stays, with its children, under no id.
for (const id of pageArgs.drop ?? []) { const el = document.getElementById(id); if (el) el.id = ''; }
// When the 3-D views first fill their host, and on which subpage.
const voxelHost = document.getElementById('voxels-grid');
let voxelsMountedOn = null;
for (const name of ['append', 'appendChild', 'replaceChildren']) {
  const original = voxelHost[name].bind(voxelHost);
  voxelHost[name] = (...nodes) => { voxelsMountedOn ??= document.querySelector('.app').dataset.msub; return original(...nodes); };
}
// The scroll margin the card had when it was scrolled to.
const scrollIntoView = P.scrollIntoView;
const marginAtScroll = [];
P.scrollIntoView = function marked(options) {
  marginAtScroll.push(document.querySelector('.main').style['--models-head-h']);
  return scrollIntoView.call(this, options);
};
await import(pageArgs.main);
const idle = async (ms = 400) => { await settle(); await new Promise((r) => setTimeout(r, ms)); await settle(); };
await idle();
const app = document.querySelector('.app');
const main = document.querySelector('.main');
const text = (id) => document.getElementById(id)?.textContent ?? null;
const view = () => ({
  msub: app.dataset.msub, hash: location.hash,
  shown: Object.fromEntries(['bench-bar', 'xgb-notice', 'group-m-colormap', 'banner', 'inspector',
    'msub-views', 'msub-distill', 'msub-perf'].map((id) => [id, !(document.getElementById(id)?.hidden ?? true)])),
  lgroupsHidden: document.getElementById('group-lgroups').hidden,
  headH: main.style['--models-head-h'],
  headNow: `${Math.ceil(head.getBoundingClientRect().height)}px`,
  banner: JSON.parse(document.getElementById('banner').dataset.messages ?? '[]'),
  bannerError: document.getElementById('banner').classList.contains('is-error'),
});
const tab = (msub) => document.getElementById(`msub-tab-${msub}`).click();
const out = { boot: { ...view(), requests: [...requests], scrolledTo: [...scrolledTo], marginAtScroll: [...marginAtScroll],
  voxelsMountedOn, errors: [...consoleErrors], search: location.search,
  inspectorTitle: text('inspector-title'), returnLink: document.querySelector('.inspector-return')?.textContent ?? null,
  headObserved: resizeObservers.some((o) => o.targets.includes(head)) } };
"""


def _page(url: str, script: str, *, experiments: bool = True, drop=(), routes=None, failures=None) -> dict:
    catalogue = json.loads((Path(_path("experiments"))).read_text(encoding="utf-8"))
    if not experiments:
        catalogue = {**catalogue, "experiments": []}
    args = {"html": str(JS.parent / "models.html"), "main": (JS / "models_main.js").as_uri(),
            "url": f"http://calosrv.test{url}", "drop": list(drop),
            "routes": {"/api/experiments": catalogue, **(routes or {})}, "failures": failures or {}}
    return _run(_FAKE_DOM + _PAGE_DOM + _PAGE_BOOT + script + "\nconsole.log(JSON.stringify(out));\n", [args])


_DEEP = "&from=lnk-results-catalogue&from_sec=sec-catalogue"


@pytest.fixture(scope="module")
def page_deep() -> dict:
    return _page(f"/models?panel=perf-catalog{_DEEP}", "")


def test_the_page_switches_to_the_linked_subpage_before_anything_loads(page_deep):
    boot = page_deep["boot"]
    assert boot["errors"] == []
    # The first request left on the linked card's subpage, the hash already saying so; the 3-D views were
    # mounted there too, hidden, so nothing of Views was asked for first.
    assert boot["requests"][0] == {"path": "/api/experiments", "msub": "perf", "hash": "#msub=perf"}
    assert boot["voxelsMountedOn"] == "perf"
    assert boot["msub"] == "perf" and boot["shown"]["msub-perf"] and not boot["shown"]["msub-views"]
    assert boot["search"] == "" and "msub=perf" in boot["hash"]


def test_a_deep_link_lands_below_the_sticky_head_with_its_drawer_and_the_way_back(page_deep):
    boot = page_deep["boot"]
    # The head was measured again just before the card was scrolled to - the bench bar shown, its caption
    # rewritten by the experiment - and again once the drawer had opened and narrowed the column: the head
    # grew, so the card was scrolled to again, below the head at its final height.
    assert boot["scrolledTo"] == [["perf-catalog", {"block": "start"}]] * 2
    first, last = (int(m[:-2]) for m in boot["marginAtScroll"])
    assert last == first + 20 and boot["marginAtScroll"][-1] == boot["headH"] == boot["headNow"]
    assert boot["headObserved"]
    assert int(boot["headNow"][:-2]) > 40, "the bench bar is in the head, beyond the 40 px of tabs"
    assert boot["shown"]["inspector"] and boot["inspectorTitle"]
    assert boot["returnLink"], "the return link is set before the drawer opens"


@pytest.fixture(scope="module")
def page_empty() -> dict:
    catalogue_card = _page(f"/models?panel=distill-pysr{_DEEP}", """
// A switch and the refresh it starts must not erase the no-experiment sentence.
tab('perf');
await idle();
out.afterSwitch = view();
""", experiments=False)
    other_card = _page("/models?panel=pred-truth&from=lnk-results-perf", "", experiments=False)
    return {"catalogue": catalogue_card, "other": other_card}


def test_a_catalogue_card_lands_with_no_experiment_open(page_empty):
    boot = page_empty["catalogue"]["boot"]
    assert boot["errors"] == []
    # R3-5: the catalogue reads the report, so its card lands on an empty service.
    assert boot["msub"] == "distill" and boot["scrolledTo"][-1] == ["distill-pysr", {"block": "start"}]
    assert boot["shown"]["inspector"] and boot["returnLink"]
    assert boot["banner"][0].startswith("No experiment has finished ingesting yet.") and boot["bannerError"]
    after = page_empty["catalogue"]["afterSwitch"]
    assert after["msub"] == "perf" and after["shown"]["banner"]
    assert after["banner"][0].startswith("No experiment has finished ingesting yet.")
    # Any other card needs an experiment: its subpage is shown, nothing is scrolled to, no drawer opens.
    other = page_empty["other"]["boot"]
    assert other["msub"] == "perf" and other["scrolledTo"] == [] and not other["shown"]["inspector"]
    assert other["banner"][0].startswith("No experiment has finished ingesting yet.")


_WIRING = r"""
const states = [];
const at = (label) => states.push([label, view()]);
at('boot');
tab('distill'); at('distill');
tab('perf'); at('perf');
tab('views'); at('views');
tab('perf');
await idle(200);
// The task buttons write the shared model through the sidebar radio's path, and the radio follows.
const pressed = (attr) => [...document.querySelectorAll(`#bench-bar [data-${attr}]`)]
  .filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset[attr === 'bench-task' ? 'benchTask' : 'benchSpecies']);
const radio = (value) => document.querySelector(`#m-model input[value="${value}"]`);
document.querySelector('#bench-bar [data-bench-task="angle"]').click();
await idle(200);
out.task = { hash: location.hash, pressed: pressed('bench-task'), radio: radio('angle').checked,
  others: ['segmentation', 'energy'].map((v) => radio(v).checked) };
radio('energy').checked = true;
radio('energy').dispatch('change');
await idle(200);
out.radio = { hash: location.hash, pressed: pressed('bench-task') };
// The species buttons: a choice is stored, the experiment's own (Compare all here) stores null.
const species = (value) => document.querySelector(`#bench-bar [data-bench-species="${value}"]`).click();
species('electron');
await idle(200);
out.electron = { hash: location.hash, pressed: pressed('bench-species'), caption: text('bench-caption') };
species('all');
await idle(200);
out.all = { hash: location.hash, pressed: pressed('bench-species'), caption: text('bench-caption') };
// A panel that changed its own picture: its notes are rebuilt, the Details button with them.
const details = document.querySelector('[data-inspect="distill-curves"]');
details.title = 'stale';
document.querySelector('.card[data-panel="distill-curves"]').dispatchEvent(
  new CustomEvent('models:panelstate', { bubbles: true, detail: { card: 'distill-curves' } }));
out.panelState = details.title;
// The cards in their sections.
out.hosts = Object.fromEntries(['distill-pysr', 'distill-curves', 'xgb-surrogate', 'xgb-importance', 'xgb-cv',
  'perf-catalog', 'perf-diagnostics', 'pred-truth', 'feat-table', 'prim-rate']
  .map((id) => [id, document.querySelector(`.card[data-panel="${id}"]`)?.parent?.id ?? null]));
out.states = states;
"""


@pytest.fixture(scope="module")
def page_wiring() -> dict:
    return _page("/models", _WIRING)


def test_a_switch_brings_the_bench_bar_the_sidebar_the_notices_and_the_head_in_line(page_wiring):
    states = dict(page_wiring["states"])
    boot, distill, perf, views = states["boot"], states["distill"], states["perf"], states["views"]
    assert page_wiring["boot"]["errors"] == []
    # Views: no bench bar, no XGBoost notice (no XGBoost card there), the Colour Map; the head without the bar.
    assert boot["msub"] == "views" and not boot["shown"]["bench-bar"] and not boot["shown"]["xgb-notice"]
    assert boot["shown"]["group-m-colormap"] and boot["headH"] == boot["headNow"] == "40px"
    # Distillations: the bar, the notice (the two-shower file pairs with no XGBoost run), no Colour Map (no E4);
    # the head measured at once, in the click, with the bar.
    assert distill["shown"]["bench-bar"] and distill["shown"]["xgb-notice"] and not distill["shown"]["group-m-colormap"]
    assert distill["headH"] == distill["headNow"] and int(distill["headNow"][:-2]) > 40
    assert distill["hash"].endswith("msub=distill")
    # Performance: the Colour Map with the prediction density.
    assert perf["shown"]["bench-bar"] and perf["shown"]["xgb-notice"] and perf["shown"]["group-m-colormap"]
    assert views == {**boot, "hash": views["hash"]} and "msub" not in views["hash"]
    # The Longitudinal Channels' hidden attribute is the control's alone: no switch touches it.
    assert len({s["lgroupsHidden"] for s in states.values()}) == 1


def test_the_bench_bar_writes_the_shared_model_and_the_species(page_wiring):
    w = page_wiring
    assert "model=angle" in w["task"]["hash"] and w["task"]["pressed"] == ["angle"]
    assert w["task"]["radio"] and w["task"]["others"] == [False, False]
    assert "model=energy" in w["radio"]["hash"] or "model=" not in w["radio"]["hash"]
    assert w["radio"]["pressed"] == ["energy"]
    assert "bench_species=electron" in w["electron"]["hash"] and w["electron"]["pressed"] == ["electron"]
    assert w["electron"]["caption"].startswith("Chosen: Electron. Choose Compare all to follow the experiment again.")
    assert "bench_species" not in w["all"]["hash"] and w["all"]["pressed"] == ["all"]
    assert w["all"]["caption"].startswith("This experiment does not name its species")


def test_the_page_rebuilds_the_notes_of_a_panel_that_changed_its_own_picture(page_wiring):
    assert page_wiring["panelState"] != "stale"


def test_the_cards_sit_in_their_subpages_sections(page_wiring):
    assert page_wiring["hosts"] == {
        "distill-pysr": "distill-grid", "distill-curves": "distill-grid", "xgb-surrogate": "xgb-distill-grid",
        "xgb-importance": "xgb-distill-grid", "xgb-cv": "xgb-grid", "perf-catalog": "bench-grid",
        "perf-diagnostics": "bench-grid", "pred-truth": "perf-grid", "feat-table": "features-grid",
        "prim-rate": "primaries-grid"}


_BANNERS = r"""
// The residual card loads on Performance with a warning its drawer does not state: the banner carries it there,
// and on Performance only (R2-6: it stood above the 3-D views).
tab('perf');
await idle();
intersect([document.querySelector('.card[data-panel="pred-residuals"]')]);
await idle(300);
for (const msub of ['views', 'distill', 'perf']) {
  tab(msub);
  out[`${msub}AtOnce`] = view();
  await idle();
  out[msub] = view();
}
// An error is not a subpage's: it stays through a switch.
intersect([document.querySelector('.card[data-panel="perf-bins"]')]);
await idle(300);
out.error = view();
tab('distill');
out.errorAfterSwitch = view();
"""


@pytest.fixture(scope="module")
def page_banners() -> dict:
    pred = json.loads(Path(_path("pred_density_two_energy")).read_text(encoding="utf-8"))
    return {"warning": pred["meta"]["warnings"][0],
            **_page("/models#model=energy", _BANNERS, routes={"/api/prediction-density": pred},
                    failures={"/api/model-performance": 503})}


def test_the_page_banner_carries_the_warnings_of_the_subpage_on_show(page_banners):
    b = page_banners
    warning = b["warning"]
    assert warning.startswith("Shower A:")
    for state in ("viewsAtOnce", "views", "distillAtOnce", "distill"):
        assert warning not in b[state]["banner"] and not b[state]["shown"]["banner"], state
    for state in ("perfAtOnce", "perf"):
        assert b[state]["banner"] == [warning] and b[state]["shown"]["banner"], state
    assert b["error"]["bannerError"] and b["error"]["shown"]["banner"]
    assert any("503" in line or "refused" in line for line in b["error"]["banner"]), b["error"]["banner"]
    assert b["errorAfterSwitch"]["banner"] == b["error"]["banner"] and b["errorAfterSwitch"]["shown"]["banner"]


def test_the_page_audits_its_markup_for_every_id_it_writes():
    dropped = ("models-head", "bench-caption", "xgb-distill-grid-title", "msub-tab-perf")
    boot = _page("/models", "", drop=dropped)["boot"]
    assert any("out of step" in line and all(i in line for i in dropped) for line in boot["banner"]), boot["banner"]


def test_the_bench_bar_ends_with_the_catalogues_own_provenance_sentence(router_results):
    # R3-7: one provenance sentence; models_subpages.js may not import the catalogue (nothing of it loads on Views).
    select = _run(r"""
const [url] = JSON.parse(process.argv[1]);
const { PROVENANCE } = await import(url);
console.log(JSON.stringify(PROVENANCE));
""", [(JS / "catalog" / "select.js").as_uri()])
    assert router_results["provenance"] == select
    source = _strip_comments((JS / "models_subpages.js").read_text(encoding="utf-8"))
    assert "catalog/" not in source


# ------------------------------------------------- a deep link's card held --

_PIN_SCRIPT = _FAKE_DOM + r"""
const [subpagesUrl] = JSON.parse(process.argv[1]);
const { pinOnResize, PIN_RELEASE_EVENTS, PIN_MS } = await import(subpagesUrl);
const observers = [];
class Obs { constructor(cb) { this.cb = cb; this.targets = []; this.off = false; observers.push(this); }
  observe(t) { this.targets.push(t); } disconnect() { this.off = true; } }
const scrolled = [];
const card = { scrollIntoView: (o) => scrolled.push(o) };
const listeners = {};
const main = {
  addEventListener: (t, f, o) => { (listeners[t] ??= []).push([f, o]); },
  removeEventListener: (t, f, capture) => { listeners[t] = (listeners[t] ?? []).filter(([g]) => g !== f); },
};
const timers = [];
const setTimer = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
const cleared = [];
const clearTimer = (id) => cleared.push(id);
const watch = { id: 'msub-perf' };
pinOnResize({ card, watch, main, Observer: Obs, setTimer, clearTimer });
const first = observers[0];
const options = Object.fromEntries(Object.entries(listeners).map(([t, l]) => [t, l[0][1]]));
first.cb(); first.cb();                 // the subpage grew twice: the card is scrolled back each time
const afterResizes = scrolled.length;
listeners.wheel[0][0]();                // the reader scrolls: the hold ends
first.cb();
const out = {
  observed: first.targets[0] === watch, afterResizes, afterWheel: scrolled.length, disconnected: first.off,
  scrollOptions: scrolled[0], timer: timers[0].ms, cleared: [...cleared], options, released: PIN_RELEASE_EVENTS, max: PIN_MS,
  remaining: Object.values(listeners).reduce((n, l) => n + l.length, 0),
};
// A second hold ends at its deadline, with no interaction.
pinOnResize({ card, watch, main, Observer: Obs, setTimer, clearTimer });
timers[1].fn();
observers[1].cb();
out.afterDeadline = scrolled.length;
out.secondDisconnected = observers[1].off;
// Without a ResizeObserver (or a card) there is nothing to hold, and nothing throws.
out.noObserver = typeof pinOnResize({ card, watch, main, Observer: undefined }) === 'function';
out.noCard = typeof pinOnResize({ watch, main, Observer: Obs }) === 'function';
console.log(JSON.stringify(out));
"""


def test_a_deep_linked_card_is_held_in_place_until_the_reader_takes_over():
    """T1's 1024 x 768 test: the card above the linked one shows under the sticky head, loads late and grows; the
    browser anchors on it and the linked card slid off the screen. Each resize of the subpage scrolls it back
    until the reader scrolls, touches, clicks or types, or 8 s pass."""
    p = _run(_PIN_SCRIPT, [(JS / "models_subpages.js").as_uri()])
    assert p["observed"] and p["afterResizes"] == 2 and p["scrollOptions"] == {"block": "start"}
    assert p["afterWheel"] == 2 and p["disconnected"] and p["remaining"] == 0 and p["cleared"] == [1]
    assert p["timer"] == p["max"] == 8000
    assert p["released"] == ["wheel", "touchstart", "pointerdown", "keydown"]
    assert all(o == {"capture": True, "passive": True} for o in p["options"].values()) and len(p["options"]) == 4
    assert p["afterDeadline"] == 2 and p["secondDisconnected"]
    assert p["noObserver"] and p["noCard"]


def test_the_page_holds_a_landed_card():
    """models_main.js landDeepLink holds the card it landed on, watching its own subpage's wrapper."""
    source = _strip_comments((JS / "models_main.js").read_text(encoding="utf-8"))
    land = source[source.index("function landDeepLink"):source.index("async function boot")]
    assert "pinOnResize({ card: result.card, watch: document.getElementById(`msub-${" in land
    assert land.index("revealPanel(") < land.index("pinOnResize(")
