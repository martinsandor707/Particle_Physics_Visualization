"""The benchmark catalogue in the Models page's card machinery, executed under Node.

Brief section 4 (``data/dev/design/models-subpages/brief.md``):

* ``capabilities.js``: the Models page's sections, with the XGBoost analysis split
  into ``xgb`` (E1, E3) and ``xgbDistill`` (E4, E5) behind one gate, and the
  catalogue's ``distill`` and ``bench`` sections shown and enabled for every
  recorded experiment, a legacy one and none at all; the subpages and the
  section each holds; the catalogue's species (``experimentSpecies``,
  ``effectiveSpecies``);
* ``models_cards.js``: the seven catalogue card specs, their requests (the
  ``catalog`` route, no abort key, independent of the experiment and of the
  filters), their render options and the accuracy card's render-only angle
  axis; on a fake document, the cards' anatomy and hosts, the catalogue
  answered from ``catalog/select.js`` with no request ever sent (a ``fetch``
  counter stays 0) and the module loaded once, a failed module load retried,
  the drawer's ``panelState``, the export targets (the PySR table has none);
* ``labels.js``: the species, subpage, task and angle-axis choices and the
  catalogue's frame and task names, held to ``catalog/select.js``.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import re

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _path, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

DISTILL = ["distill-pysr", "distill-triangle", "distill-curves"]
BENCH = ["perf-catalog", "perf-overlap", "perf-momentum-bias", "perf-diagnostics"]
CATALOG = DISTILL + BENCH
XGB_PERF = ["xgb-cv", "xgb-binary"]
XGB_DISTILL = ["xgb-surrogate", "xgb-importance"]
SPECIES = ["proton", "muon", "electron", "pion"]

#: Brief section 4's table: id, section, title, panel, group, notes, exportable, wide, table.
SPECS = [
    ("distill-pysr", "distill", "PySR Formulas and Top Features", "PysrMatrixPanel", "catalog-pysr",
     ["catalogDistill", "pysrNotes"], False, True, True),
    ("distill-triangle", "distill", "Distillation Fidelity — Tree, Formula and Network", "DistillTrianglePanel",
     "catalog-triangle", ["catalogDistill", "triangleNotes"], True, True, None),
    ("distill-curves", "distill", "Distilled Energy Response p̂(E_sum)", "DistillCurvesPanel", "catalog-curves",
     ["catalogDistill", "curvesNotes"], True, True, None),
    ("perf-catalog", "bench", "Validation Accuracy by Species, Task and Frame", "BenchCatalogPanel",
     "catalog-accuracy", ["catalogPerf", "accuracyNotes"], True, True, None),
    ("perf-overlap", "bench", "Error by Overlap Bin", "BenchOverlapPanel", "catalog-overlap",
     ["catalogPerf", "overlapNotes"], True, True, None),
    ("perf-momentum-bias", "bench", "Momentum Error and Bias near 5, 10 and 15 GeV (Absolute)", "BenchMomentumPanel",
     "catalog-momentum", ["catalogPerf", "momentumNotes"], True, True, None),
    ("perf-diagnostics", "bench", "Segmentation Indecision, Throughput and Caveats", "BenchDiagnosticsPanel",
     "catalog-diagnostics", ["catalogPerf", "diagnosticsNotes"], True, True, None),
]

# ------------------------------------------------- the plan and the labels --

_PLAN_SCRIPT = _FAKE_DOM + r"""
const [capsUrl, cardsUrl, labelsUrl, selectUrl, benchUrl, cataloguePath, xgbPath] = JSON.parse(process.argv[1]);
const caps = await import(capsUrl);
const cards = await import(cardsUrl);
const labels = await import(labelsUrl);
const select = await import(selectUrl);
const bench = await import(benchUrl);
const out = {};
const experiments = [...load(cataloguePath).experiments, ...load(xgbPath).experiments];
const brief = (plan) => ({
  sections: plan.sections,
  cards: Object.fromEntries([...caps.PAGE2_SECTIONS.distill, ...caps.PAGE2_SECTIONS.bench,
    ...caps.PAGE2_SECTIONS.xgb, ...caps.PAGE2_SECTIONS.xgbDistill].map((id) => [id, plan.cards[id]])),
  species: caps.experimentSpecies(plan),
});
out.plans = experiments.map((e) => ({ name: e.table_name, ...brief(caps.page2Plan(e)) }));
out.plans.push({ name: '(legacy)', ...brief(caps.page2Plan({ table_name: 'old', status: 'ready' })) });
out.plans.push({ name: '(none)', ...brief(caps.page2Plan(null)) });
// A paired run whose analysis is still running: both XGBoost halves show, shut with the server's sentence.
const xgbExps = load(xgbPath).experiments;
const open = structuredClone(xgbExps.find((e) => e.capabilities?.panels?.xgboost === true));
out.open = brief(caps.page2Plan(open));
const running = structuredClone(open);
running.capabilities.panels.xgboost = false;
running.capabilities.reasons.xgboost = 'Analysing: 3 of 7 steps.';
out.running = brief(caps.page2Plan(running));
out.sections = caps.PAGE2_SECTIONS;
out.subpages = caps.SUBPAGES;
out.subpageSections = caps.SUBPAGE_SECTIONS;
out.subpageOf = Object.fromEntries([...Object.keys(caps.PAGE2_SECTIONS), 'bogus', null].map((s) => [String(s),
  caps.subpageOfSection(s)]));
out.catalogSpecies = caps.CATALOG_SPECIES;
out.benchSpecies = bench.SPECIES;
// effectiveSpecies: the stored choice, else the experiment's, else Compare all.
const openPlan = caps.page2Plan(open);
const twoPlan = caps.page2Plan(load(cataloguePath).experiments.find((e) => e.capabilities.kind === 'two_shower_hits'));
const runPlan = (runs) => ({ xgb: { runs } });
out.effective = {
  storedMuon: caps.effectiveSpecies('muon', openPlan),
  storedAll: caps.effectiveSpecies('all', openPlan),
  followElectron: caps.effectiveSpecies(null, openPlan),
  followUndefined: caps.effectiveSpecies(undefined, openPlan),
  twoShower: caps.effectiveSpecies(null, twoPlan),
  noPlan: caps.effectiveSpecies(null, null),
  storedOnNoPlan: caps.effectiveSpecies('pion', null),
  bogus: caps.effectiveSpecies('kaon', openPlan),
  firstKnown: caps.experimentSpecies(runPlan([{ species: 'kaon' }, { species: 'Pion' }, { species: 'muon' }])),
  unknownOnly: caps.experimentSpecies(runPlan([{ species: 'kaon' }, {}])),
};
out.specs = cards.MODELS_CARDS.map((s) => [s.id, s.section, s.title, s.panel, s.group, s.notes, s.exportable,
  s.wide ?? null, s.table ?? null]);
out.catalogIds = cards.CATALOG_CARD_IDS;
out.isCatalog = Object.fromEntries(cards.MODELS_CARDS.map((s) => [s.id, cards.isCatalogCard(s.id)]));
out.selectCards = select.CATALOG_CARDS;
out.labels = {
  bench_species: labels.MODELS_LABELS.bench_species,
  msub: labels.MODELS_LABELS.msub,
  bench_task: labels.MODELS_LABELS.bench_task,
  bench_angle_scale: labels.MODELS_LABELS.bench_angle_scale,
  frames: labels.CATALOG_FRAME_LABELS,
  tasks: labels.CATALOG_TASK_LABELS,
  selectFrames: select.FRAME_LABELS,
  selectTasks: select.TASK_LABELS,
  selectSpecies: select.SPECIES_LABELS,
  benchFrames: bench.FRAMES,
  benchTasks: bench.TASKS,
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def plan_results() -> dict:
    return _run(_PLAN_SCRIPT, [
        (JS / "capabilities.js").as_uri(), (JS / "models_cards.js").as_uri(), (JS / "labels.js").as_uri(),
        (JS / "catalog" / "select.js").as_uri(), (JS / "catalog" / "benchmarks.js").as_uri(),
        _path("experiments"), _path("experiments_xgb"),
    ])


def test_the_sections_split_the_xgboost_analysis_and_add_the_catalogue(plan_results):
    s = plan_results["sections"]
    assert list(s) == ["perf", "resolution", "xgb", "xgbDistill", "distill", "bench", "features", "primaries",
                       "voxels"]
    assert s["xgb"] == XGB_PERF and s["xgbDistill"] == XGB_DISTILL
    assert s["distill"] == DISTILL and s["bench"] == BENCH


def test_every_card_spec_sits_in_its_plan_section(plan_results):
    sections = plan_results["sections"]
    for card_id, section, *_ in plan_results["specs"]:
        assert card_id in sections[section], (card_id, section)
    ids = [c for ids in sections.values() for c in ids]
    assert len(ids) == len(set(ids)), "a card in two sections"


def test_the_catalogue_is_shown_and_enabled_for_every_experiment(plan_results):
    names = [p["name"] for p in plan_results["plans"]]
    assert "(legacy)" in names and "(none)" in names and len(names) >= 9
    for plan in plan_results["plans"]:
        assert plan["sections"]["distill"] is True and plan["sections"]["bench"] is True, plan["name"]
        for card in CATALOG:
            assert plan["cards"][card] == {"shown": True, "enabled": True, "reason": None}, (plan["name"], card)


def test_the_two_xgboost_halves_follow_one_gate(plan_results):
    for plan in [*plan_results["plans"], plan_results["open"], plan_results["running"]]:
        assert plan["sections"]["xgbDistill"] == plan["sections"]["xgb"], plan.get("name")
        for perf, distill in zip(XGB_PERF, XGB_DISTILL):
            assert plan["cards"][distill] == plan["cards"][perf], (plan.get("name"), distill)
    assert plan_results["open"]["sections"]["xgbDistill"] is True
    for card in XGB_PERF + XGB_DISTILL:
        assert plan_results["open"]["cards"][card] == {"shown": True, "enabled": True, "reason": None}
        assert plan_results["running"]["cards"][card] == {"shown": True, "enabled": False,
                                                          "reason": "Analysing: 3 of 7 steps."}
    none = next(p for p in plan_results["plans"] if p["name"] == "(none)")
    assert none["sections"]["xgb"] is False and none["sections"]["xgbDistill"] is False


def test_the_subpages_hold_every_section_once(plan_results):
    assert plan_results["subpages"] == ["views", "distill", "perf"]
    sub = plan_results["subpageSections"]
    assert sub == {"views": ["voxels", "features", "primaries"], "distill": ["distill", "xgbDistill"],
                   "perf": ["perf", "resolution", "xgb", "bench"]}
    held = [s for sections in sub.values() for s in sections]
    assert sorted(held) == sorted(plan_results["sections"]) and len(held) == len(set(held))
    of = plan_results["subpageOf"]
    for msub, sections in sub.items():
        for section in sections:
            assert of[section] == msub
    assert of["bogus"] is None and of["null"] is None


def test_the_catalogue_species_follow_the_stored_choice_then_the_experiment(plan_results):
    assert plan_results["catalogSpecies"] == SPECIES == plan_results["benchSpecies"]
    e = plan_results["effective"]
    assert e["storedMuon"] == "muon" and e["storedAll"] == "all" and e["storedOnNoPlan"] == "pion"
    # The recorded paired aggregate is the electron's: null follows it.
    assert e["followElectron"] == "electron" and e["followUndefined"] == "electron"
    # Decision 2: an experiment naming no species opens on Compare all.
    assert e["twoShower"] == "all" and e["noPlan"] == "all"
    assert e["bogus"] == "electron", "an unknown stored value counts as no choice"
    assert e["firstKnown"] == "pion" and e["unknownOnly"] is None


def test_each_recorded_experiment_names_the_species_of_its_runs(plan_results):
    by_name = {p["name"]: p["species"] for p in plan_results["plans"]}
    for name, species in by_name.items():
        if name.startswith(("electron_", "pion_")):
            assert species == name.split("_")[0], name
        elif name.startswith(("muon_", "proton_")):
            # Unpaired in the recording: nothing is read from the table name.
            assert species is None, name
        else:
            assert species is None, name


def test_the_catalogue_card_specs_are_the_briefs(plan_results):
    specs = {s[0]: s for s in plan_results["specs"]}
    for row in SPECS:
        assert specs[row[0]] == list(row), row[0]
    ids = [s[0] for s in plan_results["specs"]]
    assert ids[-7:] == CATALOG, "the catalogue's cards follow the existing ones"
    assert plan_results["catalogIds"] == CATALOG == plan_results["selectCards"]
    assert {i for i, c in plan_results["isCatalog"].items() if c} == set(CATALOG)
    sections = {s[0]: s[1] for s in plan_results["specs"]}
    assert {sections[c] for c in XGB_PERF} == {"xgb"} and {sections[c] for c in XGB_DISTILL} == {"xgbDistill"}


def test_the_labels_are_english_and_match_the_catalogue(plan_results):
    lab = plan_results["labels"]
    assert [(c["value"], c["label"]) for c in lab["bench_species"]] == [
        ("proton", "Proton"), ("muon", "Muon"), ("electron", "Electron"), ("pion", "Pion"), ("all", "Compare all")]
    assert all(c["title"] for c in lab["bench_species"])
    assert [(c["value"], c["label"], c["title"]) for c in lab["msub"]] == [
        ("views", "Views", "The 3-D views, the event-feature explorer and the primaries"),
        ("distill", "Distillations", "Symbolic formulas, surrogate trees and feature importance"),
        ("perf", "Performance", "Network and XGBoost accuracy, resolution scaling and the benchmark catalogue"),
    ]
    assert lab["frames"] == {"absolute": "Absolute", "trans": "Per-shower translated", "local": "Local"}
    assert lab["frames"] == lab["selectFrames"] and list(lab["frames"]) == lab["benchFrames"]
    assert lab["tasks"] == lab["selectTasks"] and list(lab["tasks"]) == lab["benchTasks"]
    assert [c["value"] for c in lab["bench_task"]] == lab["benchTasks"]
    assert [c["label"] for c in lab["bench_task"]] == [lab["tasks"][t] for t in lab["benchTasks"]]
    assert {c["value"]: c["label"] for c in lab["bench_species"] if c["value"] != "all"} == lab["selectSpecies"]
    assert [(c["value"], c["label"]) for c in lab["bench_angle_scale"]] == [("linear", "Linear"), ("log10", "Log10")]
    # F11: the report's `trans` is never "Translated" alone, which names the D-frame.
    assert "Translated" not in lab["frames"].values()


def test_the_new_text_carries_no_retired_vocabulary():
    retired = ("Laboratory", "laboratory frame", "laboratory 3-D", "laboratory (absolute)",
               "Canonical centre-of-separation", "centre-of-separation frame")
    for name in ("models_cards.js", "capabilities.js", "labels.js"):
        text = (JS / name).read_text(encoding="utf-8")
        for phrase in retired:
            assert phrase not in text, (name, phrase)


def test_the_catalogue_modules_are_literal_imports():
    """The server stamps literal specifiers only, and the module graph is followed through them."""
    source = (JS / "models_cards.js").read_text(encoding="utf-8")
    for module in ("pysr_matrix", "distill_triangle", "distill_curves", "bench_catalog", "bench_overlap",
                   "bench_momentum", "bench_diagnostics"):
        assert f"() => import('./panels/{module}.js')" in source, module
    for module in ("catalog_notes_distill", "catalog_notes_perf"):
        assert f"() => import('./{module}.js')" in source, module
    assert "const loadCatalog = () => import('./catalog/select.js');" in source
    assert not re.search(r"import\(\s*`", source), "no template-literal import"


# ------------------------------------------------------------ the requests --

_REQUEST_SCRIPT = _FAKE_DOM + r"""
const [cardsUrl, capsUrl, cataloguePath, xgbPath] = JSON.parse(process.argv[1]);
const cards = await import(cardsUrl);
const caps = await import(capsUrl);
const recorded = [...load(cataloguePath).experiments, ...load(xgbPath).experiments];
const plans = { none: caps.page2Plan(null), legacy: caps.page2Plan({ table_name: 'old', status: 'ready' }) };
for (const e of recorded) plans[e.table_name] = caps.page2Plan(e);
const view = (extra = {}) => ({ frame: 'lab', model: 'segmentation', feature: 'num_hits', fclass: 'windows',
  fshower: 'a', xgb_task: 'momentum', xgb_label: 'theta', bench_species: null, ...extra });
const filterSets = {
  absent: undefined,
  noTable: { e1_min: 1, e1_max: 20 },
  two: { table_name: 'experiment_baseline', e1_min: 1, e1_max: 20, e2_min: 1, e2_max: 20, d_min: 0, d_max: 900,
    include_undefined_d: false },
  narrow: { table_name: 'other', e1_min: 3, e1_max: 4 },
};
const out = { requests: {}, options: {}, controls: {} };
for (const spec of cards.MODELS_CARDS.filter((s) => cards.isCatalogCard(s.id))) {
  const rows = [];
  for (const [planName, plan] of Object.entries(plans)) {
    for (const [filterName, filters] of Object.entries(filterSets)) {
      rows.push([planName, filterName, cards.cardRequest(spec.id, { filters, plan, view: view() })]);
    }
  }
  out.requests[spec.id] = rows;
}
const open = plans[recorded.find((e) => e.capabilities?.panels?.xgboost === true).table_name];
out.followed = cards.cardRequest('perf-overlap', { filters: filterSets.two, plan: open, view: view({ model: 'angle' }) });
out.chosen = cards.cardRequest('perf-overlap', { filters: filterSets.two, plan: open,
  view: view({ model: 'energy', bench_species: 'muon' }) });
out.chosenAll = cards.cardRequest('distill-pysr', { filters: filterSets.two, plan: open, view: view({ bench_species: 'all' }) });
// Without a view the built-in task and Compare all.
out.bare = cards.cardRequest('perf-catalog', {});
// The existing cards still need an experiment.
out.existingNoTable = cards.MODELS_CARDS.filter((s) => !cards.isCatalogCard(s.id))
  .map((s) => cards.cardRequest(s.id, { filters: filterSets.noTable, plan: plans.none, view: view({ model: 'energy' }) }));
out.abortKeys = cards.ABORT_KEYS;
out.catalogRoute = cards.CATALOG_ROUTE;
for (const id of cards.CATALOG_CARD_IDS) {
  out.options[id] = cards.cardOptions(id, { plan: open, view: view({ model: 'angle' }),
    controls: { benchAngleScale: 'log10' }, palette: 'cividis' });
}
out.options.defaults = cards.cardOptions('perf-catalog', { plan: plans.none });
out.options.chosen = cards.cardOptions('distill-curves', { plan: plans.none, view: view({ bench_species: 'pion', model: 'energy' }) });
// E4 and E5 keep their options in their new section.
out.options.tree = cards.cardOptions('xgb-surrogate', { plan: open, view: view({ xgb_task: 'angle', xgb_label: 'phi' }) });
out.options.importance = cards.cardOptions('xgb-importance', { plan: open, view: view({ xgb_task: 'angle' }) });
out.options.cv = cards.cardOptions('xgb-cv', { plan: open, view: view({ xgb_task: 'angle' }) });
for (const id of cards.CATALOG_CARD_IDS) {
  out.controls[id] = cards.cardControls(id).map((c) => ({ name: c.name, kind: c.kind, attr: c.attr, label: c.label,
    stateKey: c.stateKey ?? null, request: c.request ?? false, choices: c.choices({}).map((x) => x.value) }));
}
out.defaultControls = cards.DEFAULT_CONTROLS;
out.view = cards.viewOf({ get: (k) => ({ bench_species: 'muon', msub: 'perf' })[k] });
out.viewEmpty = cards.viewOf({ get: () => undefined });
out.notices = cards.CATALOG_CARD_IDS.map((id) => [cards.cardNotice(id, { plan: open, view: view() }),
  cards.cardCaption(id, { plan: open, view: view({ frame: 'canonical' }) })]);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def request_results() -> dict:
    return _run(_REQUEST_SCRIPT, [(JS / "models_cards.js").as_uri(), (JS / "capabilities.js").as_uri(),
                                  _path("experiments"), _path("experiments_xgb")])


def test_a_catalogue_request_is_answered_in_the_page_and_never_reads_the_experiment(request_results):
    assert request_results["catalogRoute"] == "catalog"
    for card, rows in request_results["requests"].items():
        assert card in CATALOG
        for plan_name, filter_name, request in rows:
            assert request is not None, (card, plan_name, filter_name)
            assert request["route"] == "catalog" and request["abortKey"] is None
            assert set(request["params"]) == {"card", "species", "task"}, (card, plan_name)
            assert request["params"]["card"] == card and request["params"]["task"] == "segmentation"
        # The filters (an experiment or none, any selection) never enter the request.
        by_plan = {}
        for plan_name, _, request in rows:
            by_plan.setdefault(plan_name, []).append(request)
        for plan_name, requests in by_plan.items():
            assert all(r == requests[0] for r in requests), (card, plan_name)
            expected = "electron" if plan_name.startswith("electron_") else (
                "pion" if plan_name.startswith("pion_") else "all")
            assert requests[0]["params"]["species"] == expected, (card, plan_name)


def test_a_catalogue_request_follows_the_species_and_the_shared_task(request_results):
    r = request_results
    assert r["followed"]["params"] == {"card": "perf-overlap", "species": "electron", "task": "angle"}
    assert r["chosen"]["params"] == {"card": "perf-overlap", "species": "muon", "task": "energy"}
    assert r["chosenAll"]["params"]["species"] == "all"
    assert r["bare"] == {"route": "catalog", "abortKey": None,
                         "params": {"card": "perf-catalog", "species": "all", "task": "segmentation"}}


def test_the_existing_cards_still_need_an_experiment_and_no_abort_key_is_added(request_results):
    assert all(r is None for r in request_results["existingNoTable"])
    assert len(request_results["abortKeys"]) == 12
    assert not any(k.startswith("catalog") for k in request_results["abortKeys"])


def test_the_catalogue_cards_render_with_species_task_and_angle_axis(request_results):
    o = request_results["options"]
    for card in CATALOG:
        assert o[card] == {"palette": "cividis", "card": card, "species": "electron", "task": "angle",
                           "angleScale": "log10"}, card
    assert o["defaults"] == {"palette": "viridis", "card": "perf-catalog", "species": "all",
                             "task": "segmentation", "angleScale": "linear"}
    assert o["chosen"] == {"palette": "viridis", "card": "distill-curves", "species": "pion", "task": "energy",
                           "angleScale": "linear"}


def test_e4_and_e5_keep_their_options_in_their_new_section(request_results):
    o = request_results["options"]
    assert o["tree"] == {"palette": "viridis", "card": "xgb-surrogate", "task": "angle", "label": "phi"}
    assert o["importance"] == {"palette": "viridis", "card": "xgb-importance", "task": "angle"}
    assert o["cv"] == {"palette": "viridis", "card": "xgb-cv", "task": "angle"}


def test_only_the_accuracy_card_carries_a_control_and_it_repaints(request_results):
    c = request_results["controls"]
    assert c["perf-catalog"] == [{"name": "benchAngleScale", "kind": "seg", "attr": "benchScale",
                                  "label": "Angle axis", "stateKey": None, "request": False,
                                  "choices": ["linear", "log10"]}]
    assert all(c[card] == [] for card in CATALOG if card != "perf-catalog")
    assert request_results["defaultControls"]["benchAngleScale"] == "linear"


def test_the_view_reads_the_catalogue_species_and_never_the_subpage(request_results):
    assert request_results["view"]["bench_species"] == "muon" and "msub" not in request_results["view"]
    assert request_results["viewEmpty"]["bench_species"] is None


def test_no_catalogue_card_carries_a_notice_or_a_frame_caption(request_results):
    assert request_results["notices"] == [[None, None]] * 7


# ------------------------------------------------------- the section on a page --

_SECTION_SCRIPT = _FAKE_DOM + r"""
const [cardsUrl, capsUrl, selectUrl, xgbPath] = JSON.parse(process.argv[1]);
let fetched = 0;
globalThis.fetch = async (url) => { fetched += 1; return { ok: false, status: 404, statusText: 'x',
  json: async () => ({ detail: `unexpected request ${url}` }) }; };
const cards = await import(cardsUrl);
const caps = await import(capsUrl);
const select = await import(selectUrl);
const out = {};

// A State stand-in with the keys a card reads: the Models page's keys live in state.js (S1's file).
const makeState = (values) => ({
  values: { palette: 'viridis', frame: 'lab', model: 'segmentation', bench_species: null, ...values },
  get(key) { return this.values[key]; },
  set(patch) { Object.assign(this.values, patch); },
  filterParams() { return this.values.table_name ? { table_name: this.values.table_name } : {}; },
});

const rendered = [];
class FakePanel {
  constructor(element, options) { this.element = element; this.options = options; }
  render(payload, opts) { this.lastPayload = payload; this.lastOpts = opts; rendered.push([this.options.card, payload, opts]); }
  clear() { this.lastPayload = null; }
  relayout() {}
  setBusy() {}
}
class CurvesPanel extends FakePanel {
  notesState() { return { values: { centroid_r: 1200 } }; }
}
const names = ['PysrMatrixPanel', 'DistillTrianglePanel', 'BenchCatalogPanel', 'BenchOverlapPanel',
  'BenchMomentumPanel', 'BenchDiagnosticsPanel', 'XgbCvPanel', 'XgbBinaryPanel', 'XgbTreePanel', 'XgbImportancePanel'];
const panelClasses = { ...Object.fromEntries(names.map((n) => [n, FakePanel])), DistillCurvesPanel: CurvesPanel };
const seen = [];
const builder = (name) => (ctx) => { seen.push({ name, card: ctx.card, species: ctx.species, task: ctx.task,
  angleScale: ctx.angleScale, panelState: ctx.panelState, source: ctx.payload?.meta?.source ?? null });
  return { title: ctx.title, hazards: ['no interval reported'], sections: [] }; };
const notesModules = {
  catalogDistill: { pysrNotes: builder('pysrNotes'), triangleNotes: builder('triangleNotes'), curvesNotes: builder('curvesNotes') },
  catalogPerf: { accuracyNotes: builder('accuracyNotes'), overlapNotes: builder('overlapNotes'),
    momentumNotes: builder('momentumNotes'), diagnosticsNotes: builder('diagnosticsNotes') },
  xgb: {}, models: {},
};
let loads = 0;
const catalogLoader = () => { loads += 1; return import(selectUrl); };

const hostIds = { perf: 'perf-grid', resolution: 'resolution-grid', xgb: 'xgb-grid', xgbDistill: 'xgb-distill-grid',
  distill: 'distill-grid', bench: 'bench-grid', features: 'features-grid', primaries: 'primaries-grid' };
const makeHosts = () => Object.fromEntries(Object.entries(hostIds).map(([k, id]) => {
  const el = document.createElement('section'); el.id = id; return [k, el];
}));

// 1. No experiment at all: the catalogue still draws, from the module, with no request.
let hosts = makeHosts();
let state = makeState({});
const section = new cards.ModelsSection(hosts, { state, panelClasses, notesModules, catalogLoader, root: 'MAIN' });
const all = Object.values(hosts).flatMap((h) => h.children);
const cardOf = (id) => all.find((c) => c.dataset.panel === id);
out.anatomy = all.map((card) => {
  const buttons = card.children[0].children[1].children;
  return {
    panel: card.dataset.panel, host: card.parent.id,
    firstInspect: buttons[0].dataset.inspect, firstControls: buttons[0].getAttribute('aria-controls'),
    lastExport: buttons[buttons.length - 1].dataset.export ?? null,
    plotId: card.children[2].children[0].id, plotClass: card.children[2].children[0].className,
    wide: card.classList.contains('is-wide'),
  };
});
section.applyPlan(caps.page2Plan(null));
out.hiddenNone = Object.fromEntries(all.map((c) => [c.dataset.panel, c.hidden]));
FakeObserver.last.show(all.filter((c) => !c.hidden));
await settle();
out.first = { fetched, loads, rendered: rendered.map(([card, payload, opts]) => [card, payload.meta.source,
  payload.meta.species, payload.meta.task, opts.species]) };
out.samePayload = JSON.stringify(section.payloadOf('perf-overlap'))
  === JSON.stringify(select.catalogPayload('perf-overlap', { species: 'all', task: 'segmentation' }));

// 2. The species and the task change: every catalogue card re-reads the module, nothing is sent.
const before = rendered.length;
state.set({ bench_species: 'muon', model: 'angle' });
await section.refresh();
out.second = { fetched, loads, rendered: rendered.slice(before).map(([card, payload]) => [card, payload.meta.species,
  payload.meta.task]) };

// 3. Back to Compare all: answered from the cache, still no request.
const beforeBack = rendered.length;
state.set({ bench_species: null, model: 'segmentation' });
await section.refresh();
out.back = { fetched, loads, n: rendered.length - beforeBack };

// 4. The angle axis: a render-only repaint of the accuracy card, no State write, no request.
const beforeScale = rendered.length;
const log = cardOf('perf-catalog').find((el) => el.dataset.benchScale === 'log10');
log.click();
await settle();
out.scale = { fetched, cards: rendered.slice(beforeScale).map(([card, , opts]) => [card, opts.angleScale]),
  state: state.values.benchAngleScale ?? null, pressed: log.getAttribute('aria-pressed') };

// 5. The drawer: the builder by name, with the render options and the panel's own state.
out.notes = Object.fromEntries(cards.CATALOG_CARD_IDS.map((id) => [id, section.notes(id)?.hazards ?? null]));
out.seen = seen;
// 6. Export targets: the PySR table has none; the charts export with the catalogue's meta.
out.exports = Object.fromEntries(cards.CATALOG_CARD_IDS.map((id) => {
  const t = section.exportTarget(id);
  return [id, t ? { panel: Boolean(t.panel), source: t.meta.source, card: t.meta.card } : t];
}));

// 7. A paired aggregate: the catalogue follows its species, the XGBoost halves sit in their hosts.
const open = structuredClone(load(xgbPath).experiments.find((e) => e.capabilities?.panels?.xgboost === true));
section.reset();
state.set({ table_name: open.table_name });
section.applyPlan(caps.page2Plan(open));
out.hiddenOpen = Object.fromEntries(all.map((c) => [c.dataset.panel, c.hidden]));
out.openKeys = Object.fromEntries(cards.CATALOG_CARD_IDS.map((id) => [id, section.keyOf(id)]));

// 8. A catalogue module that fails to load: an ordinary failure with a Retry, then the module again.
const failHosts = makeHosts();
let failures = 1;
let failLoads = 0;
const failing = new cards.ModelsSection(failHosts, {
  state: makeState({}), panelClasses, notesModules, root: 'MAIN',
  catalogLoader: () => { failLoads += 1; if (failures > 0) { failures -= 1; return Promise.reject(new TypeError('Failed to fetch dynamically imported module')); } return import(selectUrl); },
});
const failAll = Object.values(failHosts).flatMap((h) => h.children);
failing.applyPlan(caps.page2Plan(null));
const pysr = failAll.find((c) => c.dataset.panel === 'distill-pysr');
FakeObserver.last.show([pysr]);
await settle();
const message = pysr.find((el) => el.classList.contains('card-error'));
const retry = message.find((el) => el.dataset.retry !== undefined);
out.failed = { hidden: message.hidden, kind: message.dataset.kind, retry: Boolean(retry), loads: failLoads };
retry.click();
await settle();
out.retried = { hidden: message.hidden, loads: failLoads, payload: failing.payloadOf('distill-pysr')?.meta?.card ?? null,
  fetched };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def section_results() -> dict:
    return _run(_SECTION_SCRIPT, [(JS / "models_cards.js").as_uri(), (JS / "capabilities.js").as_uri(),
                                  (JS / "catalog" / "select.js").as_uri(), _path("experiments_xgb")])


def test_the_catalogue_cards_have_the_page_anatomy_in_their_hosts(section_results):
    anatomy = {a["panel"]: a for a in section_results["anatomy"]}
    for card in CATALOG + XGB_DISTILL:
        a = anatomy[card]
        assert a["firstInspect"] == card and a["firstControls"] == "inspector", card
        assert a["plotId"] == f"plot-{card}" and a["wide"] is True, card
        if card == "distill-pysr":
            assert a["lastExport"] is None and a["plotClass"] == "card-table"
        else:
            assert a["lastExport"] == card and a["plotClass"] == "plot", card
    hosts = {card: a["host"] for card, a in anatomy.items()}
    assert {hosts[c] for c in DISTILL} == {"distill-grid"} and {hosts[c] for c in BENCH} == {"bench-grid"}
    assert {hosts[c] for c in XGB_DISTILL} == {"xgb-distill-grid"} and {hosts[c] for c in XGB_PERF} == {"xgb-grid"}


def test_without_an_experiment_only_the_catalogue_is_on_show(section_results):
    hidden = section_results["hiddenNone"]
    assert {c for c, h in hidden.items() if not h} == set(CATALOG)


def test_the_catalogue_draws_from_its_module_and_never_asks_the_server(section_results):
    first = section_results["first"]
    assert first["fetched"] == 0 and first["loads"] == 1
    assert sorted(r[0] for r in first["rendered"]) == sorted(CATALOG)
    assert all(r[1:] == ["catalog", "all", "segmentation", "all"] for r in first["rendered"])
    assert section_results["samePayload"] is True
    second = section_results["second"]
    assert second["fetched"] == 0 and second["loads"] == 1, "the module is loaded once"
    assert sorted(r[0] for r in second["rendered"]) == sorted(CATALOG)
    assert all(r[1:] == ["muon", "angle"] for r in second["rendered"])
    back = section_results["back"]
    assert back == {"fetched": 0, "loads": 1, "n": 7}


def test_the_angle_axis_repaints_the_accuracy_card_alone(section_results):
    s = section_results["scale"]
    assert s["fetched"] == 0 and s["cards"] == [["perf-catalog", "log10"]]
    assert s["state"] is None, "the angle axis is the section's own, never in the link"
    assert s["pressed"] == "true"


def test_the_drawer_gets_the_render_options_and_the_panels_own_state(section_results):
    notes = section_results["notes"]
    assert all(notes[c] == ["no interval reported"] for c in CATALOG)
    seen = {s["card"]: s for s in section_results["seen"]}
    assert set(seen) == set(CATALOG)
    for card, s in seen.items():
        assert s["source"] == "catalog" and s["species"] == "all" and s["task"] == "segmentation", card
        assert s["angleScale"] == ("log10" if card == "perf-catalog" else "linear"), card
    assert seen["distill-curves"]["panelState"] == {"values": {"centroid_r": 1200}}
    assert all(seen[c]["panelState"] is None for c in CATALOG if c != "distill-curves")
    assert {s["name"] for s in section_results["seen"]} == {
        "pysrNotes", "triangleNotes", "curvesNotes", "accuracyNotes", "overlapNotes", "momentumNotes",
        "diagnosticsNotes"}


def test_the_pysr_table_has_no_export_and_the_charts_export_their_catalogue_meta(section_results):
    e = section_results["exports"]
    assert e["distill-pysr"] is None
    for card in CATALOG[1:]:
        assert e[card] == {"panel": True, "source": "catalog", "card": card}, card


def test_a_paired_aggregate_shows_both_xgboost_halves_and_the_catalogue_follows_it(section_results):
    hidden = section_results["hiddenOpen"]
    assert all(hidden[c] is False for c in CATALOG + XGB_PERF + XGB_DISTILL)
    for card, key in section_results["openKeys"].items():
        assert key == f'["catalog",[["card","{card}"],["species","electron"],["task","segmentation"]]]', card


def test_a_catalogue_module_that_fails_to_load_is_retried(section_results):
    assert section_results["failed"] == {"hidden": False, "kind": "error", "retry": True, "loads": 1}
    r = section_results["retried"]
    assert r["hidden"] is True and r["loads"] == 2 and r["payload"] == "distill-pysr" and r["fetched"] == 0
