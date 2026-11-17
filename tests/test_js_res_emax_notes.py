"""The energy-resolution card's Details drawer under the Deposit toggle and the E max slider, run under Node.

Martin's decisions of 2026-11-17 (brief res-emax, section 8): the drawer is built from the panel's models with
`deposit` and `eMax` passed through. While the calibrated deposit is hidden no line of either view's drawer
describes it, apart from the one Selection line that says it is hidden; the range's basis is the server's
`y_model.note`; with no reference on show (the deposit hidden and no literature curve on) the ratio panel is said to
draw nothing, with no sentence on a reference, a ratio axis or k; an E max gives the E view its slider line, the
tick step in force and, where the end is off the step grid, the end ticked too. Without either option every note,
title and hazard is exactly what it was (the dark golden's promise, held from this side).

The script runs `resolutionScalingNotes` and `modelsHazards` on every recorded `res_scaling*` payload
(`tests/fixtures/payloads/`) in both views. Skipped without `node`.
"""

from __future__ import annotations

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

#: The recordings with a model series beside the deposit (two showers, or the XGBoost hold-out), by estimator.
WITH_MODELS = ["res_scaling_two", "res_scaling_xgb", "res_scaling_median_two", "res_scaling_median_xgb",
               "res_scaling_robust_two", "res_scaling_robust_xgb"]
#: The recordings whose only series is the deposit: the toggle cannot hide it there.
DEPOSIT_ONLY = ["res_scaling_single_hits", "res_scaling_single_events", "res_scaling_median_single_hits",
                "res_scaling_median_single_events", "res_scaling_robust_single_hits", "res_scaling_robust_single_events"]
ALL = WITH_MODELS + DEPOSIT_ONLY

HIDDEN_LINE = ("Calibrated deposit: hidden by the card's Deposit toggle. Its windows, its fitted curve and its fit-table "
               "rows are not drawn, and the error-scale range follows the model series alone.")
FORCED_LINE = "Calibrated deposit: drawn; it is this response's only series, so the Deposit toggle is shut."
NONE_RATIO_TO = ("Ratio to: none. The deposit is hidden and no literature curve is on, so the ratio panel draws no mark; "
                 "switch on π±, e± or the deposit to draw one.")
NONE_DRAWN = ("The ratio panel shares the energy axis but draws no mark, no 1.0 rule and no scale: no reference is on show "
              "(the deposit is hidden and no literature curve is on).")
NONE_MARKS = ("The ratio panel draws no 1.0 rule and no scale: with no reference on show it holds only its frame, the "
              "shared energy axis and one sentence saying so.")

#: What names the deposit series, its calibration or its reference. None of it may survive a hidden deposit.
DEPOSIT_WORDS = re.compile(r"Calibrated deposit c·E_dep|c·E_dep|c_sum|c̃|E_dep|The detector series|"
                           r"deposit's (?:a/√E|a₀/√E|noise)|each shower's deposit|ratio divides by its deposit|by its own deposit fit")
#: The lines that may still say "deposit", "calibrat" or "detector" while it is hidden, each with why it is right.
ALLOWED_REMAINING = [
    re.escape(HIDDEN_LINE),                                      # the one line that says it is hidden
    re.escape(NONE_RATIO_TO), re.escape(NONE_DRAWN),             # the no-reference sentences name what is off
    r"^With the calibrated deposit hidden, ",                    # the server's y_model.note, verbatim
    r"with neither, nothing, since the deposit is hidden",       # the literature legend line
    r"of the model series \(the deposit is hidden\)",            # whose windows chose the ratio's curve (review R1-2)
    r"3 XGBoost and 4 the deposit, shower 0 for A and 1 for B",  # the server's bootstrap seed key, in the whisker's label
    r"not that the detector has none",                           # the held-term caveat: the physical detector
    r"not this dataset's detector",                              # the literature curves' scope: the physical detector
    r"never a statement about this detector",
]

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir, spec] = JSON.parse(process.argv[1]);
const mn = await import(`${jsRoot}/models_notes.js`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const pack = (r) => ({ title: r.title, hazards: r.hazards, sections: r.sections.map((s) => [s.heading, s.lines]) });
const stub = { isTouched: () => false, get: () => null };
const run = (payload, view, windows, opts) => {
  const base = { payload, state: stub, experiment: { display_name: 'Demo' }, view, windows, shower: 'both', ...opts };
  const notes = mn.resolutionScalingNotes(base);
  const hz = mn.modelsHazards(payload, 'res-scaling', { windows, shower: 'both', view, ...opts });
  return { ...pack(notes), hz };
};
const out = {};
if (spec.part === 'grid') {
  for (const name of spec.names) {
    const payload = load(name);
    out[name] = {};
    for (const view of ['linear', 'energy']) for (const windows of ['anchors', 'all']) {
      for (const [vn, opts] of Object.entries(spec.variants)) {
        if (opts.eMax !== undefined && opts.eMax !== null && typeof opts.eMax === 'object') continue;
        out[name][`${view}:${windows}:${vn}`] = run(payload, view, windows, opts);
      }
    }
  }
} else if (spec.part === 'identity') {
  for (const name of spec.names) {
    const payload = load(name);
    out[name] = {};
    for (const view of ['linear', 'energy']) for (const windows of ['anchors', 'all']) for (const shower of ['both', 'a']) {
      const lit = view === 'energy' ? { literature: ['pi', 'e'] } : {};
      const plain = JSON.stringify(mn.resolutionScalingNotes({ payload, view, windows, shower, ...lit }));
      const undef = JSON.stringify(mn.resolutionScalingNotes({ payload, view, windows, shower, ...lit, deposit: undefined, eMax: undefined }));
      const shown = JSON.stringify(mn.resolutionScalingNotes({ payload, view, windows, shower, ...lit, deposit: true }));
      const hzPlain = JSON.stringify(mn.modelsHazards(payload, 'res-scaling', { windows, shower, view, ...lit }));
      const hzUndef = JSON.stringify(mn.modelsHazards(payload, 'res-scaling', { windows, shower, view, ...lit, deposit: undefined, eMax: undefined }));
      out[name][`${view}:${windows}:${shower}`] = { undef: plain === undef, shown: plain === shown, hz: hzPlain === hzUndef };
    }
  }
} else if (spec.part === 'clipped') {
  // The 1/√E view with the model series' range cut low, so the clipped sentence is stated.
  for (const name of spec.names) {
    const payload = load(name);
    payload.axis.y_model.hi = 3; payload.axis.y_model.n_clipped = 7;
    out[name] = { hidden: run(payload, 'linear', 'all', { deposit: false }), shown: run(payload, 'linear', 'all', {}) };
  }
} else if (spec.part === 'provisional') {
  for (const name of spec.names) {
    const payload = load(name);
    for (const k of ['y', 'y_model']) payload.axis.energy[k].provisional = true;
    out[name] = { hidden: run(payload, 'energy', 'all', { deposit: false, literature: [] }),
      shown: run(payload, 'energy', 'all', { literature: ['pi', 'e'] }) };
  }
} else if (spec.part === 'warnings') {
  // The server's warnings on the deposit's own sample, and one on a model series (review R1-5).
  for (const name of spec.names) {
    const payload = load(name);
    payload.meta = { ...(payload.meta ?? {}), warnings: [...spec.deposit, spec.model] };
    out[name] = {};
    for (const view of ['linear', 'energy']) {
      out[name][view] = { hidden: run(payload, view, 'anchors', { deposit: false, literature: ['pi', 'e'] }),
        shown: run(payload, view, 'anchors', { deposit: true, literature: ['pi', 'e'] }) };
    }
  }
}
process.stdout.write(JSON.stringify(out));
"""

VARIANTS = {
    "base": {"literature": ["pi", "e"]},
    "plain": {},
    "dep1": {"deposit": True, "literature": ["pi", "e"]},
    "dep0": {"deposit": False, "literature": ["pi", "e"]},
    "dep0_e": {"deposit": False, "literature": ["e"]},
    "dep0_pi": {"deposit": False, "literature": ["pi"]},
    "none": {"deposit": False, "literature": []},
    "dep1_none": {"deposit": True, "literature": []},
    "emax_null": {"eMax": None, "literature": ["pi", "e"]},
    "emax_20": {"eMax": 20, "literature": ["pi", "e"]},
    "emax_45": {"eMax": 45, "literature": ["pi", "e"]},
    "emax_80": {"eMax": 80, "literature": ["pi", "e"]},
    "emax_null_none": {"eMax": None, "deposit": False, "literature": []},
}


def _run(spec: dict) -> dict:
    args = json.dumps([JS.as_uri(), str(FIXTURES), spec])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=900, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def grid() -> dict:
    return _run({"part": "grid", "names": ALL, "variants": VARIANTS})


@pytest.fixture(scope="module")
def identity() -> dict:
    return _run({"part": "identity", "names": ALL})


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf8"))


def _lines(note: dict, heading: str | None = None) -> list[str]:
    return [line for h, lines in note["sections"] for line in lines if heading is None or h == heading]


def _text(note: dict) -> str:
    return "\n".join(_lines(note))


def _cases(names, views=("linear", "energy"), windows=("anchors", "all")):
    return [(n, v, w) for n in names for v in views for w in windows]


def _deposit_labels(payload: dict) -> list[str]:
    return [s["label"] for s in payload["series"] if s.get("source") == "detector"]


# ------------------------------------------------------------------------------------------------ identity ---


def test_without_deposit_and_e_max_every_note_title_and_hazard_is_todays(identity):
    for name, cases in identity.items():
        for case, got in cases.items():
            assert got["undef"], (name, case)
            assert got["hz"], (name, case)


def test_a_shown_deposit_changes_nothing(identity):
    for name, cases in identity.items():
        for case, got in cases.items():
            assert got["shown"], (name, case)


# ------------------------------------------------------------------------------------- deposit hidden ---


@pytest.mark.parametrize("name,view,windows", _cases(WITH_MODELS))
def test_a_hidden_deposit_is_said_once_in_selection_and_described_nowhere_else(grid, name, view, windows):
    payload = _load(name)
    for variant in ("dep0", "dep0_e", "dep0_pi", "none"):
        note = grid[name][f"{view}:{windows}:{variant}"]
        assert _lines(note, "Selection").count(HIDDEN_LINE) == 1, variant
        assert FORCED_LINE not in _text(note)
        text = _text(note)
        for label in _deposit_labels(payload):
            assert label not in text, (variant, label)
        assert "Calibrated deposit c·E_dep" not in text
        rest = [line for line in _lines(note) if line != HIDDEN_LINE]
        for line in rest:
            assert not DEPOSIT_WORDS.search(line), (variant, line)
        # Every remaining mention of the deposit or the detector is one of the judged lines.
        for line in rest:
            if re.search(r"deposit|detector", line, re.IGNORECASE) is None:
                continue
            body = re.sub(r"\s+", " ", line)
            assert any(re.search(pattern, body) for pattern in ALLOWED_REMAINING), (variant, line)


@pytest.mark.parametrize("name,view,windows", _cases(WITH_MODELS))
def test_the_ranges_basis_is_the_servers_model_only_note_verbatim(grid, name, view, windows):
    payload = _load(name)
    axis = payload["axis"]
    y_model = axis["y_model"] if view == "linear" else axis["energy"]["y_model"]
    note = grid[name][f"{view}:{windows}:dep0"]
    assert y_model["note"] in _lines(note)
    # The full-range sentence the server also ships (payload notes, the E view's axis notes) is not reprinted.
    full = (axis["y"] if view == "linear" else axis["energy"]).get("note")
    assert full is None or full not in _lines(note)
    shown = grid[name][f"{view}:{windows}:base"] if view == "energy" else grid[name][f"{view}:{windows}:plain"]
    assert y_model["note"] not in _lines(shown)


@pytest.mark.parametrize("name,view,windows", _cases(WITH_MODELS))
def test_a_hidden_deposit_leaves_out_its_calibration_and_the_detector_sentences(grid, name, view, windows):
    payload = _load(name)
    shown = grid[name][f"{view}:{windows}:base" if view == "energy" else f"{view}:{windows}:plain"]
    hidden = grid[name][f"{view}:{windows}:dep0"]
    median = payload["estimator"]["name"] == "median"
    # c̃ beside c_sum (median calibration lines) are there with the deposit shown and gone with it hidden.
    if median and view == "energy":
        assert any("c̃ =" in line for line in _lines(shown))
    assert not any("c̃" in line or "c_sum" in line for line in _lines(hidden))
    xgb = (payload.get("model") or {}).get("source") == "xgb"
    sentence = "The detector series uses every selected event"
    assert any(sentence in line for line in _lines(shown)) == xgb or view == "linear"
    assert not any(sentence in line for line in _lines(hidden))
    # The model series' own sentence of the XGBoost note stays.
    if xgb and view == "linear":
        assert any("The model series is the shipped XGBoost momentum regressor" in line for line in _lines(hidden))


@pytest.mark.parametrize("name,view,windows", _cases(WITH_MODELS))
def test_the_colour_sentence_drops_its_deposit_clause(grid, name, view, windows):
    hidden = grid[name][f"{view}:{windows}:dep0"]
    marks = _lines(hidden, "Marks and legend")
    lead = "Colour is the series: a model in the hue E2 gives its source (ColorBrewer qualitative, ≥ 3:1 against the card)."
    assert any(line.startswith(lead) for line in marks)
    assert not any("the detector's calibrated deposit in ink" in line for line in marks)
    shown = grid[name][f"{view}:{windows}:dep1"]
    assert any("Colour is the series: the detector's calibrated deposit in ink, a model in the hue E2" in line
               for line in _lines(shown, "Marks and legend"))


@pytest.mark.parametrize("name", WITH_MODELS)
def test_the_hazards_are_those_of_the_hidden_model(grid, name):
    payload = _load(name)
    for windows in ("anchors", "all"):
        lin = grid[name][f"linear:{windows}:dep0"]
        eng = grid[name][f"energy:{windows}:dep0"]
        assert lin["hazards"] == lin["hz"]
        assert eng["hazards"] == eng["hz"]
        assert ("provisional range" in lin["hazards"]) == bool(payload["axis"]["y_model"]["provisional"])
        assert ("provisional range" in eng["hazards"]) == bool(payload["axis"]["energy"]["y_model"]["provisional"])
        assert "provisional ratio range" not in grid[name][f"energy:{windows}:none"]["hazards"]


@pytest.mark.parametrize("name", WITH_MODELS)
def test_the_1_over_sqrt_e_drawer_drops_the_servers_deposit_notes(grid, name):
    note = grid[name]["linear:all:dep0"]
    payload = _load(name)
    drawn = _lines(note, "What is drawn")
    for label in _deposit_labels(payload):
        assert not any(line.startswith(label) for line in drawn)
    assert not any(line.startswith("The detector series c·E_dep") for line in drawn)
    assert not any("E_dep" in line for line in _lines(note))
    # The estimator's own note stays, without its clause on the deposit's calibration.
    assert any(line.startswith("Each window is the producer's integer momentum bin") for line in drawn)
    assert not any("depends on the deposit's calibration" in line or "does not depend on the calibration" in line
                   for line in _lines(note))


@pytest.mark.parametrize("name", ["res_scaling_two", "res_scaling_xgb"])
def test_the_clipped_count_is_of_every_model_series_while_the_deposit_is_hidden(name):
    got = _run({"part": "clipped", "names": [name]})[name]
    hidden = [line for line in _lines(got["hidden"], "Disclosures") if line.startswith("Clipped at the axis in this view")]
    shown = [line for line in _lines(got["shown"], "Disclosures") if line.startswith("Clipped at the axis in this view")]
    assert hidden and shown
    assert "on-axis window of every model series, both modes: 7)" in hidden[0]
    assert "on-axis window of every series, both modes" in shown[0]


@pytest.mark.parametrize("name", ["res_scaling_xgb", "res_scaling_median_xgb"])
def test_a_provisional_range_counts_the_windows_of_the_series_on_show(name):
    payload = _load(name)
    gates = payload.get("gates", {})
    report_n = gates.get("report_n", 2)
    floor = payload["axis"]["energy"].get("y_min_gev", 2)

    def below(series):
        return sum(1 for s in series for w in s.get("windows", [])
                   if isinstance(w.get("value"), (int, float)) and (w.get("n") or 0) >= report_n and (w.get("p_lo") or 0) < floor)

    model_only = below([s for s in payload["series"] if s.get("source") != "detector"])
    every = below(payload["series"])
    assert every > model_only > 0, "the fixture must hold deposit windows below the floor for the test to tell them apart"
    got = _run({"part": "provisional", "names": [name]})[name]

    def clause(n):
        return f"the markers of the {n} window{'' if n == 1 else 's'} below 2 GeV"

    hidden = _text(got["hidden"])
    shown = _text(got["shown"])
    assert clause(model_only) in hidden and clause(every) not in hidden
    assert clause(every) in shown


# ------------------------------------------------------------------------------------------ deposit forced ---


@pytest.mark.parametrize("name,view,windows", _cases(DEPOSIT_ONLY))
def test_a_deposit_that_is_the_only_series_is_drawn_and_said_forced(grid, name, view, windows):
    forced = grid[name][f"{view}:{windows}:dep0"]
    shown = grid[name][f"{view}:{windows}:dep1"]
    assert _lines(forced, "Selection").count(FORCED_LINE) == 1
    assert HIDDEN_LINE not in _text(forced)
    # Every other line, and every hazard, is as with the deposit shown.
    strip = [(h, [line for line in lines if line != FORCED_LINE]) for h, lines in forced["sections"]]
    assert [(h, lines) for h, lines in strip if lines] == [(h, lines) for h, lines in shown["sections"] if lines]
    assert forced["hazards"] == shown["hazards"]
    assert forced["title"] == shown["title"]
    assert FORCED_LINE not in _text(shown)


def test_a_deposit_shown_by_choice_says_nothing_new(grid):
    for name in WITH_MODELS:
        text = _text(grid[name]["energy:all:dep1"])
        assert HIDDEN_LINE not in text and FORCED_LINE not in text


# ------------------------------------------------------------------------------------------------ E max ---


def _e_max_line(note: dict) -> list[str]:
    return [line for line in _lines(note, "Selection") if line.startswith("E max: ")]


def _emax_range(payload: dict) -> tuple[int, int, int]:
    step = 5
    top = payload["axis"]["energy"]["x"]["max"]
    edge = payload["axis"]["energy"].get("data_max_gev")
    low = min(top, max(step, math.ceil(edge / step) * step)) if isinstance(edge, (int, float)) else top
    return int(low), int(top), step


@pytest.mark.parametrize("name,windows", [(n, w) for n in ALL for w in ("anchors", "all")])
def test_e_max_null_says_the_slider_line_with_its_range_and_a_5_gev_axis(grid, name, windows):
    payload = _load(name)
    low, top, step = _emax_range(payload)
    note = grid[name][f"energy:{windows}:emax_null"]
    # The data's top edge is named where rounding it up to the step moved it (18 GeV on the two-shower files; review R1-6).
    data_top = payload["axis"]["energy"].get("data_max_gev")
    edge = ("the data's highest window edge" if data_top == low
            else f"the data's highest window edge, {data_top:g} GeV, rounded up to {step} GeV")
    line = (f"E max: {low} GeV, set by the card's slider ({low}–{top} GeV in {step} GeV steps; its lower end is {edge}, "
            "so every window is on the axis). Nothing beyond it is drawn on either panel.")
    assert _e_max_line(note) == [line]
    selection = _lines(note, "Selection")
    view = [i for i, s in enumerate(selection) if s.startswith("View: ")]
    assert len(view) == 1 and f"0 to {low} GeV" in selection[view[0]]
    assert selection.index(line) == view[0] + 1
    axis = [s for s in _lines(note, "What is drawn") if s.startswith("The energy axis is linear from 0 to ")]
    assert len(axis) == 1 and axis[0].startswith(f"The energy axis is linear from 0 to {low} GeV in steps of {step} GeV")
    assert "is ticked too" not in axis[0]
    assert note["hazards"] == note["hz"]


@pytest.mark.parametrize("name", ["res_scaling_two", "res_scaling_xgb", "res_scaling_single_hits"])
def test_an_e_max_off_the_step_grid_has_its_end_ticked_too(grid, name):
    note = grid[name]["energy:all:emax_45"]
    assert _e_max_line(note)[0].startswith("E max: 45 GeV, set by the card's slider (")
    axis = [s for s in _lines(note, "What is drawn") if s.startswith("The energy axis is linear from 0 to 45 GeV")][0]
    assert axis.startswith("The energy axis is linear from 0 to 45 GeV in steps of 10 GeV; the end, 45 GeV, is ticked too")
    assert "0 to 45 GeV" in [s for s in _lines(note, "Selection") if s.startswith("View: ")][0]


@pytest.mark.parametrize("name", ["res_scaling_two", "res_scaling_xgb"])
def test_an_e_max_on_the_5_gev_grid_does_not_tick_the_end_twice(grid, name):
    assert "is ticked too" not in _text(grid[name]["energy:all:emax_20"])
    assert "is ticked too" not in _text(grid[name]["energy:all:emax_80"])
    axis = [s for s in _lines(grid[name]["energy:all:emax_80"], "What is drawn") if s.startswith("The energy axis is linear")][0]
    assert "in steps of 10 GeV" in axis  # the server's own interval at its own end


@pytest.mark.parametrize("name", ALL)
def test_without_e_max_there_is_no_slider_line_and_the_servers_axis(grid, name):
    payload = _load(name)
    for variant in ("plain", "base", "dep1", "dep0", "none"):
        note = grid[name][f"energy:all:{variant}"]
        assert _e_max_line(note) == []
        assert "is ticked too" not in _text(note)
        top = payload["axis"]["energy"]["x"]["max"]
        assert any(f"0 to {top:g} GeV" in s for s in _lines(note, "Selection") if s.startswith("View: "))


def test_the_1_over_sqrt_e_drawer_has_no_e_max_line(grid):
    for name in WITH_MODELS:
        assert _e_max_line(grid[name]["linear:all:plain"]) == []


# ------------------------------------------------------------------------------------------ no reference ---


@pytest.mark.parametrize("name,windows", [(n, w) for n in WITH_MODELS for w in ("anchors", "all")])
def test_with_no_reference_the_drawer_says_so_once_and_describes_no_reference(grid, name, windows):
    for variant in ("none", "emax_null_none"):
        note = grid[name][f"energy:{windows}:{variant}"]
        text = _text(note)
        assert _lines(note, "Selection").count(NONE_RATIO_TO) == 1
        assert not any(line.startswith("Ratio to: ") and line != NONE_RATIO_TO for line in _lines(note, "Selection"))
        assert _lines(note, "What is drawn").count(NONE_DRAWN) == 1
        assert _lines(note, "Marks and legend").count(NONE_MARKS) == 1
        for absent in ("k is the first of", "The ratio axis is logarithmic", "The ratio panel shares the energy axis. A window",
                       "The ratio range,", "ratio whisker", "the ratio divides", "The ratio panel: the 1.0 rule",
                       "ratio panel divides each shower", "divides each shower by its own deposit fit",
                       "reference fit is provisional", "not drawn on the ratio panel", "has no ratio marks",
                       "Clipped at the ratio axis", "The ratio axis is capped"):
            assert absent not in text, absent
        assert "provisional ratio range" not in note["hazards"]
        assert note["hazards"] == note["hz"]


@pytest.mark.parametrize("name", WITH_MODELS)
def test_a_literature_curve_keeps_the_ratio_and_its_reference_lines_with_the_deposit_hidden(grid, name):
    for variant, curve in (("dep0_e", "e±"), ("dep0_pi", "π±")):
        note = grid[name][f"energy:all:{variant}"]
        text = _text(note)
        assert NONE_RATIO_TO not in text and NONE_DRAWN not in text and NONE_MARKS not in text
        ratio_to = [line for line in _lines(note, "Selection") if line.startswith("Ratio to: ")]
        assert len(ratio_to) == 1 and "the literature curve" in ratio_to[0]
        assert any(line.startswith("The ratio's reference is the literature curve") for line in _lines(note, "What is drawn"))
        assert any("The ratio axis is logarithmic and symmetric about 1" in line for line in _lines(note, "What is drawn"))
        assert any(line.startswith("The ratio panel: the 1.0 rule in ink marks") for line in _lines(note, "Marks and legend"))
        assert "no interval reported" in note["hazards"]
        marks = [line for line in _lines(note, "Marks and legend") if line.startswith("Literature curves are dotted lines")]
        assert marks and f"the {curve} curve is the ratio's reference" in marks[0]
        assert "with neither, nothing, since the deposit is hidden" in marks[0]
        assert "by each shower's deposit fit" not in marks[0]


@pytest.mark.parametrize("name", WITH_MODELS)
def test_both_curves_on_with_the_deposit_hidden_keep_the_choice_sentence(grid, name):
    note = grid[name]["energy:all:dep0"]
    text = _text(note)
    assert "Ratio to: " in text and NONE_RATIO_TO not in text
    assert any(line.startswith("The ratio's reference is the literature curve") for line in _lines(note, "What is drawn"))


@pytest.mark.parametrize("name", WITH_MODELS)
def test_with_the_deposit_shown_and_no_curve_the_ratio_divides_by_the_deposit_as_before(grid, name):
    note = grid[name]["energy:all:dep1_none"]
    text = _text(note)
    assert NONE_RATIO_TO not in text and NONE_DRAWN not in text and NONE_MARKS not in text
    assert "With no literature curve drawn, the ratio divides each shower by its own deposit fit." in text
    assert "The ratio range, " in text
    assert any("with neither, by each shower's deposit fit" in line for line in _lines(note, "Marks and legend"))


def test_the_deposit_only_recordings_never_state_no_reference(grid):
    for name in DEPOSIT_ONLY:
        for variant in ("dep0", "none", "emax_null_none"):
            text = _text(grid[name][f"energy:all:{variant}"])
            assert NONE_RATIO_TO not in text and NONE_DRAWN not in text and NONE_MARKS not in text, (name, variant)


# ---------------------------------------------------------------------------- the deposit's own warnings ---

#: The server's two warnings on a shower sample, which feeds the deposit alone (query/resolution_scaling.py
#: `warnings`), and one on a model series.
DEPOSIT_WARNINGS = [
    "Shower A: 3 events were dropped before the ratios (a deposit or momentum that is not finite, a negative deposit, "
    "or a momentum that is not positive), counted and never zero-filled.",
    "Shower B: no event of the selection deposits energy (E_dep > 0), so the median calibration c̃ = 1 / median(E_dep / p) "
    "does not exist and the deposit has no windows under Median |rel. err.| (their values are null); Robust σ (IQR) and "
    "Sample σ/μ do not depend on the calibration.",
]
MODEL_WARNING = ("Shower A · Energy network · absolute frame: no event of the selection has a finite prediction and "
                 "truth; every one is counted in n_missing and none is drawn.")


def test_the_hidden_deposits_own_warnings_leave_the_drawer_with_it():
    """Review R1-5: hidden, the server's warnings on the deposit's sample are not stated (the page's banner leaves them
    out too: test_js_models_shell.py); a model series' warning stays; shown, all three are back."""
    names = ["res_scaling_median_two", "res_scaling_two", "res_scaling_median_xgb"]
    got = _run({"part": "warnings", "names": names, "deposit": DEPOSIT_WARNINGS, "model": MODEL_WARNING})
    for name in names:
        for view in ("linear", "energy"):
            hidden = _lines(got[name][view]["hidden"], "Disclosures")
            shown = _lines(got[name][view]["shown"], "Disclosures")
            assert MODEL_WARNING in hidden and MODEL_WARNING in shown, (name, view)
            for w in DEPOSIT_WARNINGS:
                assert w not in hidden, (name, view, w[:40])
                assert w in shown, (name, view, w[:40])
