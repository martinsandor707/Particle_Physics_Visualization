"""Behaviour of two pure front-end modules, executed under Node.

`test_export_assets.py` pins properties of the *source*: that the fade guard
comes before the division, that the modules are stamped. That catches a guard
being deleted, but not one being rewritten into something that no longer
guards. The two pieces below are pure enough to run outside a browser, so they
are executed here and their output asserted:

* `decode.codeTable`, the 256-entry RGBA table every raster is painted through.
  Guard 8b.1 of the canonical-panel plan: a zero, negative or non-finite fade
  width (print sets it to 0) must give a pure 0/255 alpha step. A NaN would not
  raise - `Uint8ClampedArray` stores it as 0 - so the failure mode is a field
  silently painted transparent, which only an executed check can see. The same
  table must stay byte-identical to the legacy `palette[code]` mapping for
  laboratory payloads.
* `state.State`, whose display mode is held per frame (`display_lab`,
  `display_canonical`) with a legacy `display=` still honoured in old links.

The whole file is skipped when `node` is not on the PATH; the modules need no
packages, only Node's ES-module loader and a stub `window` for the hash.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "calosrv" / "static" / "js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: A canonical density payload: three-decade relative ramp, codes 2..255.
CANONICAL = {
    "scale": {"unit": "a.u.", "scale": "log10", "vmin": -3.0, "vmax": 0.0, "floor_ratio": 1e-3},
    "empty_code": 0, "below_code": 1, "min_code": 2, "max_code": 255,
}
#: A laboratory payload: GeV ramp over codes 1..255, no below-floor code.
LAB = {
    "scale": {"unit": "GeV", "scale": "log10", "vmin": -6.0, "vmax": 0.0},
    "empty_code": 0, "min_code": 1, "max_code": 255,
}
#: A canonical Grad-CAM payload: linear attention, masked bins on code 1.
ATTENTION = {
    "scale": {"unit": "attention", "scale": "linear", "vmin": 0.0, "vmax": 1.0},
    "empty_code": 0, "below_code": 1, "min_code": 2, "max_code": 255,
}

_SCRIPT = """
const [decodeUrl, paletteUrl, stateUrl, payloads] = JSON.parse(process.argv[1]);
const { codeTable } = await import(decodeUrl);
const { lookupTable } = await import(paletteUrl);

const out = {};
const alphas = (table) => Array.from({ length: 256 }, (_, code) => table[code * 4 + 3]);
const rgbOf = (table, code) => Array.from(table.slice(code * 4, code * 4 + 3));
const palette = lookupTable('viridis');

// codeTable: every degenerate fade width, then the screen taper.
out.step = {};
for (const [name, fade] of [
  ['zero', 0], ['negative', -0.5], ['nan', NaN],
  ['inf', Infinity], ['neginf', -Infinity], ['null', null],
]) {
  out.step[name] = alphas(codeTable(payloads.canonical, 'viridis', fade));
}
const tapered = codeTable(payloads.canonical, 'viridis', 0.5);
out.taper = alphas(tapered);
out.canonicalEnds = {
  first: rgbOf(tapered, payloads.canonical.min_code),
  last: rgbOf(tapered, payloads.canonical.max_code),
  palette0: Array.from(palette.slice(0, 3)),
  palette255: Array.from(palette.slice(255 * 3, 256 * 3)),
};
const lab = codeTable(payloads.lab, 'viridis', 0.5);
let identical = lab[3] === 0;
for (let code = 1; code < 256; code += 1) {
  identical = identical
    && lab[code * 4] === palette[code * 3]
    && lab[code * 4 + 1] === palette[code * 3 + 1]
    && lab[code * 4 + 2] === palette[code * 3 + 2]
    && lab[code * 4 + 3] === 255;
}
out.labIdentical = identical;
out.attention = alphas(codeTable(payloads.attention, 'viridis', 0.5));

// State: the hash is read at construction and written on every set().
globalThis.window = {
  location: { hash: '', pathname: '/' },
  history: {
    replaceState(_state, _title, url) {
      const at = url.indexOf('#');
      window.location.hash = at >= 0 ? url.slice(at) : '';
    },
  },
};
const { State } = await import(stateUrl);
const fresh = (hash) => { window.location.hash = hash; return new State(); };
const state = {};

let s = fresh('');
state.defaults = { canonical: s.get('display'), sent: s.projectionParams().display };
s.set({ frame: 'lab' });
state.defaults.lab = s.get('display');
state.defaults.sentLab = s.projectionParams().display;

s = fresh('#display=native');
state.legacyCanonical = { canonical: s.get('display'), lab: s.values.display_lab };
s = fresh('#frame=lab&display=continuous');
state.legacyLab = { lab: s.get('display'), canonical: s.values.display_canonical };
s = fresh('#display=native&display_canonical=continuous');
state.specificWins = s.get('display');
s = fresh('#display_canonical=bogus&display=bogus');
state.invalid = { canonical: s.get('display'), lab: s.values.display_lab };

s = fresh('');
s.set({ display: 'native' });
const hashCanonical = window.location.hash;
s.set({ frame: 'lab' });
const labAfterSwitch = s.get('display');
s.set({ display: 'continuous' });
const hashBoth = window.location.hash;
s.set({ frame: 'canonical' });
state.roundTrip = { hashCanonical, labAfterSwitch, hashBoth, canonicalAfterReturn: s.get('display') };
const reloaded = fresh(hashBoth);
state.reload = { frame: reloaded.get('frame'), canonical: reloaded.values.display_canonical, lab: reloaded.get('display') };

s = fresh('');
s.set({ display: 'continuous', frame: 'lab' });
state.keyOrder = { frame: s.get('frame'), lab: s.values.display_lab, canonical: s.values.display_canonical };
out.state = state;

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def results() -> dict:
    """Run the script once; every test below reads its part of the output."""
    args = json.dumps([
        (JS / "decode.js").as_uri(),
        (JS / "palette.js").as_uri(),
        (JS / "state.js").as_uri(),
        {"canonical": CANONICAL, "lab": LAB, "attention": ATTENTION},
    ])
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _SCRIPT, args],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# ------------------------------------------------------------- codeTable --


@pytest.mark.parametrize("fade", ["zero", "negative", "nan", "inf", "neginf", "null"])
def test_a_degenerate_fade_width_gives_a_pure_alpha_step(results, fade):
    alpha = results["step"][fade]
    assert set(alpha) <= {0, 255}
    assert alpha[0] == 0 and alpha[1] == 0, "empty and below-floor codes must stay transparent"
    assert all(a == 255 for a in alpha[2:]), "every ramp code must be opaque when there is no taper"


def test_the_screen_taper_rises_monotonically_over_the_bottom_half_decade(results):
    alpha = results["taper"]
    ramp = alpha[2:]
    assert alpha[0] == alpha[1] == 0
    assert ramp[0] == 0, "the floor itself fades to nothing"
    assert all(b >= a for a, b in zip(ramp, ramp[1:])), "the taper is not monotone"
    assert any(0 < a < 255 for a in ramp), "no intermediate alpha: the taper is a step"
    first_opaque = next(code for code in range(2, 256) if alpha[code] == 255)
    value = CANONICAL["scale"]["vmin"] + (first_opaque - 2) / 253 * 3.0
    assert -2.51 <= value <= -2.48, f"fully opaque from 10^{value:.3f}, expected 10^-2.5"


def test_a_canonical_ramp_spans_the_whole_palette(results):
    ends = results["canonicalEnds"]
    assert ends["first"] == ends["palette0"]
    assert ends["last"] == ends["palette255"]


def test_the_lab_table_is_the_legacy_palette_mapping(results):
    assert results["labIdentical"]


def test_attention_is_never_tapered(results):
    alpha = results["attention"]
    assert alpha[0] == alpha[1] == 0
    assert all(a == 255 for a in alpha[2:])


# ------------------------------------------------------------------ state --


def test_each_frame_opens_in_its_own_display_mode(results):
    defaults = results["state"]["defaults"]
    assert defaults == {
        "canonical": "continuous", "sent": "continuous", "lab": "native", "sentLab": "native",
    }


def test_a_legacy_display_link_applies_to_the_active_frame(results):
    state = results["state"]
    assert state["legacyCanonical"] == {"canonical": "native", "lab": "native"}
    assert state["legacyLab"] == {"lab": "continuous", "canonical": "continuous"}


def test_the_frame_specific_key_wins_over_a_legacy_display(results):
    assert results["state"]["specificWins"] == "continuous"


def test_an_unknown_display_mode_in_a_link_keeps_the_default(results):
    assert results["state"]["invalid"] == {"canonical": "continuous", "lab": "native"}


def test_switching_frames_keeps_each_frames_mode_and_the_hash_round_trips(results):
    trip = results["state"]["roundTrip"]
    assert "display_canonical=native" in trip["hashCanonical"]
    assert "display_lab" not in trip["hashCanonical"], "a default must not be written"
    assert trip["labAfterSwitch"] == "native"
    assert "display_lab=continuous" in trip["hashBoth"]
    assert "display_canonical=native" in trip["hashBoth"]
    assert trip["canonicalAfterReturn"] == "native"
    assert results["state"]["reload"] == {"frame": "lab", "canonical": "native", "lab": "continuous"}


def test_a_patch_carrying_frame_and_display_does_not_depend_on_key_order(results):
    assert results["state"]["keyOrder"] == {
        "frame": "lab", "lab": "continuous", "canonical": "continuous",
    }


# --------------------------------------------------------------- tooltip --

_TOOLTIP_SCRIPT = """
const [tooltipUrl] = JSON.parse(process.argv[1]);
const { tooltipOption, readoutPosition, READOUT_GAP_PX } = await import(tooltipUrl);
const size = (w, h, vw, vh) => ({ contentSize: [w, h], viewSize: [vw, vh] });
const out = { option: tooltipOption(), gap: READOUT_GAP_PX, cases: {} };
// The measured readout: 372 px wide on a 586 px XY chart.
for (const [name, point, s] of [
  ['fitsRight', [100, 50], size(372, 60, 586, 330)],
  ['flipsLeft', [450, 50], size(372, 60, 586, 330)],
  ['neitherLeftHalf', [150, 200], size(372, 60, 500, 330)],
  ['neitherRightHalf', [350, 200], size(372, 60, 500, 330)],
  ['neitherNearTop', [350, 20], size(372, 60, 500, 330)],
  ['noSize', [10, 5], undefined],
]) {
  out.cases[name] = { point, size: s, at: readoutPosition(point, null, null, null, s) };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def tooltip_results() -> dict:
    args = json.dumps([(JS / "panels" / "tooltip.js").as_uri()])
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _TOOLTIP_SCRIPT, args],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_every_chart_tooltip_is_confined_to_its_chart(tooltip_results):
    """`confine` is the fix: the tip stays inside the chart, right of the sidebar."""
    option = tooltip_results["option"]
    assert option["confine"] is True
    assert option["className"] == "calo-tooltip"
    assert option["trigger"] == "item"


def _contains(box_at, size, point) -> bool:
    x, y = box_at
    w, h = size["contentSize"]
    return x <= point[0] <= x + w and y <= point[1] <= y + h


def test_the_bin_readout_sits_right_of_the_pointer_when_it_fits(tooltip_results):
    case = tooltip_results["cases"]["fitsRight"]
    gap = tooltip_results["gap"]
    assert case["at"] == [case["point"][0] + gap, case["point"][1] - 8]
    assert not _contains(case["at"], case["size"], case["point"])


def test_the_bin_readout_flips_left_only_when_the_right_side_overflows(tooltip_results):
    case = tooltip_results["cases"]["flipsLeft"]
    gap = tooltip_results["gap"]
    width = case["size"]["contentSize"][0]
    assert case["at"][0] == case["point"][0] - gap - width
    assert case["at"][0] >= 0
    assert not _contains(case["at"], case["size"], case["point"])


def test_a_readout_wider_than_either_side_moves_off_the_pointer_vertically(tooltip_results):
    for name in ("neitherLeftHalf", "neitherRightHalf", "neitherNearTop"):
        case = tooltip_results["cases"][name]
        assert not _contains(case["at"], case["size"], case["point"]), name
        view_w = case["size"]["viewSize"][0]
        width = case["size"]["contentSize"][0]
        assert 0 <= case["at"][0] <= max(0, view_w - width), name


def test_the_readout_position_is_finite_without_a_measured_size(tooltip_results):
    at = tooltip_results["cases"]["noSize"]["at"]
    assert all(isinstance(v, (int, float)) for v in at)
