"""The resolution card's estimator words: one source of truth for the strings shown in several places.

Martin's decisions of 2026-11-12 gave the energy-resolution card (`res-scaling`)
an Estimator control and kept the π± and e± literature curves on under all
three estimators, with one disclosure under the median relative error. That
sentence is written once, as `calosrv.query.resolution_scaling.LITERATURE_WARNING`,
served in the payload (`estimator.literature.warning`) and shown in four places:
the E view's note band, the tooltips (held by `test_js_models_panels.py`), the
drawer's Disclosures and the Methodology article's callout. The article also
quotes the Details hazard and the control's labels. This file holds each copy to
its source, so a rewording in one place fails here instead of drifting:

* the Python constant is the brief's sentence (section 2.7), verbatim, with its
  U+2212 minus, and the four median fixtures serve it, the others none;
* the panel's note band and the drawer's Disclosures line are that sentence;
* the article's callout, rendered by the article's own code
  (`methodology/render.js` `layout`, with its constants), is that sentence, and
  the article's Results paragraph quotes it;
* the hazard `models_notes.js` `modelsHazards` raises is the one the article
  names, twice;
* `labels.js` `MODELS_LABELS.res_estimator` is the brief's table (section 4),
  and the article and the payload use its labels;
* the drawer's default titles are the shell's `cardTitle` per estimator and view.

Runs under plain Node, with no document (text widths by `textfit.js`'s own estimate). Skipped without
``node``.
"""

from __future__ import annotations

import json
import re

import pytest
from test_js_physics_shell import JS, NODE, _path, _run

from calosrv.query import resolution_scaling as rs

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

KINDS = ["two", "xgb", "single_hits", "single_events"]

#: brief section 2.7, verbatim (the minus in "R − 1" is U+2212).
BRIEF_WARNING = ("Note: comparing Median |rel. err.| against a σ/E literature curve (for unbiased Gaussian errors, "
                 "median|R − 1| = 0.6745·σ/E; use Robust σ (IQR) for a σ-scaled comparison).")

#: brief section 4, the control's table, verbatim: value, label, title.
BRIEF_ESTIMATORS = [
    ["median", "Median |rel. err.|",
     "median |E_est − p| / p per window: the Median rel. of Model Error vs. Incident Momentum, same events, seed and "
     "interval. Not a σ: for unbiased Gaussian errors it is 0.6745·σ/E."],
    ["robust", "Robust σ (IQR)",
     "IQR(R) / (1.349 · median R), R = E_est / p: a σ-consistent width that a few badly reconstructed events "
     "cannot inflate; the σ-scaled comparison with the π± and e± curves."],
    ["sample", "Sample σ/μ",
     "s(R) / R̄ over every event of the window, tails included: the Physics page resolution card's estimator."],
]

#: brief section 4, the card titles per estimator: (1/√E view, E view).
BRIEF_TITLES = {
    "median": ["Median Relative Error vs. 1/√E", "Median Relative Error vs. E"],
    "robust": ["Energy Resolution vs. 1/√E", "Energy Resolution vs. E"],
    "sample": ["Energy Resolution vs. 1/√E", "Energy Resolution vs. E"],
}

_SCRIPT = r"""
// No fake document: textfit.js measures text by its own estimate without one, as the golden does.
import fs from 'node:fs';
const load = (path) => JSON.parse(fs.readFileSync(path, 'utf8'));
const [jsRoot, fixtures] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const panel = await imp('panels/resolution_scaling.js');
const mn = await imp('models_notes.js');
const cards = await imp('models_cards.js');
const { MODELS_LABELS } = await imp('labels.js');
const render = await imp('methodology/render.js');
const { ARTICLE } = await imp('methodology/content/index.js');
const { CONSTANTS } = await imp('methodology/constants.js');
const out = { fixtures: {} };
const RE = { width: 760, height: 600 };

// The served sentence, the note band and the drawer, on every fixture with both curves on (the card's default).
for (const [name, path] of Object.entries(fixtures)) {
  const payload = load(path);
  const opts = { view: 'energy', windows: 'all', shower: 'both', literature: ['pi', 'e'] };
  const model = panel.energyModel(payload, opts);
  const option = panel.energyViewOption(payload, opts, RE).option;
  const notes = mn.resolutionScalingNotes({ payload, ...opts });
  const without = (lit) => mn.modelsHazards(payload, 'res-scaling', { ...opts, literature: lit });
  out.fixtures[name] = {
    served: payload.estimator?.literature?.warning ?? null,
    label: payload.estimator?.label ?? null,
    noteBand: model.noteText.warning,
    graphics: (option.graphic ?? []).map((g) => g.style?.text).filter(Boolean).map((t) => t.replace(/\n/g, ' ')),
    disclosures: notes.sections.find((s) => s.heading === 'Disclosures')?.lines ?? [],
    // The hazard the median adds: what a curve raises beyond the same view with no curve on.
    hazards: without(['pi', 'e']).filter((h) => !without([]).includes(h)),
    titles: [mn.resolutionScalingNotes({ payload, windows: 'all' }).title, notes.title],
  };
}

// The article, laid out by its own code with its own constants.
const { tree, errors } = render.layout(ARTICLE, { constants: CONSTANTS });
const callouts = [];
const paragraphs = [];
const walk = (n) => {
  if (!n) return;
  if (Array.isArray(n)) { n.forEach(walk); return; }
  const cls = String(n.attrs?.class ?? '');
  if (n.tag === 'aside' && cls.split(/\s+/).includes('callout')) {
    callouts.push({ cls, title: render.textOf((n.children ?? []).filter((c) => String(c.attrs?.class ?? '') === 'callout-title')),
      body: render.textOf((n.children ?? []).filter((c) => String(c.attrs?.class ?? '') !== 'callout-title')) });
  }
  if (n.tag === 'p') paragraphs.push(render.textOf(n));
  (n.children ?? []).forEach(walk);
};
walk(tree);
out.article = { errors, callouts, paragraphs };

out.labels = { estimator: MODELS_LABELS.res_estimator.map((c) => [c.value, c.label, c.title]) };
out.robustFloor = panel.ROBUST_MIN_N;
out.titles = Object.fromEntries(['median', 'robust', 'sample'].map((name) => [name, ['linear', 'energy'].map((resView) =>
  cards.cardTitle('res-scaling', { ...cards.DEFAULT_CONTROLS, resView, resEstimator: name }))]));
out.noteTitles = { median: [mn.RES_SCALING_MEDIAN_TITLE, mn.RES_SCALING_MEDIAN_ENERGY_TITLE],
  sigma: [mn.RES_SCALING_TITLE, mn.RES_SCALING_ENERGY_TITLE] };
console.log(JSON.stringify(out));
"""

_FIXTURES = {f"{est}_{k}": f"res_scaling_{est}_{k}" for est in ("median", "robust") for k in KINDS}
_FIXTURES.update({f"sample_{k}": f"res_scaling_{k}" for k in KINDS})


@pytest.fixture(scope="module")
def words() -> dict:
    return _run(_SCRIPT, [JS.as_uri(), {name: _path(path) for name, path in _FIXTURES.items()}])


def _estimator(name: str) -> str:
    return name.split("_", 1)[0]


def test_the_python_constant_is_the_briefs_sentence():
    assert rs.LITERATURE_WARNING == BRIEF_WARNING
    assert "−" in rs.LITERATURE_WARNING and not re.search(r"(?<![\w])-(?=[\d.])", rs.LITERATURE_WARNING)


@pytest.mark.parametrize("name", list(_FIXTURES))
def test_the_median_fixtures_serve_the_constant_and_the_others_none(words, name):
    served = words["fixtures"][name]["served"]
    assert served == (rs.LITERATURE_WARNING if _estimator(name) == "median" else None)


@pytest.mark.parametrize("name", list(_FIXTURES))
def test_the_note_band_and_the_drawer_print_the_served_sentence(words, name):
    f = words["fixtures"][name]
    on = _estimator(name) == "median"
    assert f["noteBand"] == (rs.LITERATURE_WARNING if on else "")
    assert f["graphics"].count(rs.LITERATURE_WARNING) == (1 if on else 0)
    assert f["disclosures"].count(rs.LITERATURE_WARNING) == (1 if on else 0)


def test_the_articles_callout_is_the_served_sentence(words):
    a = words["article"]
    assert a["errors"] == []
    (callout,) = [c for c in a["callouts"] if "The disclosure under the median estimator" in c["title"]]
    assert "callout-caution" in callout["cls"]
    assert callout["body"] == rs.LITERATURE_WARNING
    # The callout's own paragraph, and the Results paragraph, which quotes the sentence inside its own and so
    # without the closing full stop: "… for a σ-scaled comparison) appears, verbatim, in the E view's note band …".
    assert sum(p == rs.LITERATURE_WARNING for p in a["paragraphs"]) == 1
    quoted = [p for p in a["paragraphs"] if p != rs.LITERATURE_WARNING and rs.LITERATURE_WARNING.rstrip(".") in p]
    assert len(quoted) == 1 and f"{rs.LITERATURE_WARNING.rstrip('.')} appears, verbatim," in quoted[0]


@pytest.mark.parametrize("name", list(_FIXTURES))
def test_the_hazard_is_raised_under_the_median_only(words, name):
    hazards = words["fixtures"][name]["hazards"]
    assert ("median rel. against σ/E curve" in hazards) == (_estimator(name) == "median")


def test_the_article_names_the_hazard_the_drawer_raises(words):
    (hazard,) = {h for name, f in words["fixtures"].items() if _estimator(name) == "median" for h in f["hazards"]
                 if h != "no interval reported"}
    quoted = [m for p in words["article"]["paragraphs"]
              for m in re.findall(r"carries the hazard (.+?) beside no interval reported", p)]
    assert len(quoted) == 2 and set(quoted) == {hazard}


def test_the_estimator_control_is_the_briefs_table(words):
    assert words["labels"]["estimator"] == BRIEF_ESTIMATORS


@pytest.mark.parametrize("name", list(_FIXTURES))
def test_the_payload_labels_the_estimator_as_the_control_does(words, name):
    labels = {value: label for value, label, _ in BRIEF_ESTIMATORS}
    assert words["fixtures"][name]["label"] == labels[_estimator(name)]
    assert rs.ESTIMATOR_LABELS[_estimator(name)] == labels[_estimator(name)]


def test_the_article_uses_the_controls_labels(words):
    text = " ".join(words["article"]["paragraphs"])
    for _, label, _ in BRIEF_ESTIMATORS:
        assert label in text, label


def test_the_titles_agree_between_the_shell_and_the_drawer(words):
    assert words["titles"] == BRIEF_TITLES
    assert words["noteTitles"]["median"] == BRIEF_TITLES["median"]
    assert words["noteTitles"]["sigma"] == BRIEF_TITLES["robust"]
    for name, f in words["fixtures"].items():
        assert f["titles"] == BRIEF_TITLES[_estimator(name)], name


def test_the_brief_tables_are_json_round_trippable():
    """Guards the literals above against an editor's smart quotes: every string survives JSON unchanged."""
    assert json.loads(json.dumps(BRIEF_ESTIMATORS, ensure_ascii=False)) == BRIEF_ESTIMATORS


def test_the_panels_robust_floor_is_the_servers_gate(words):
    """The panel says "not reported below N = 20" itself, for the cross-references; the server gates the robust width."""
    gate = rs.ESTIMATOR_GATES[rs.ROBUST]
    assert words["robustFloor"] == gate["report_n"] == gate["whisker_n"] == gate["fit_n"]
