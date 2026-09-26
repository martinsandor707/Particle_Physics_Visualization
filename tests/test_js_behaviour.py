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
const { State, API_FRAME, FRAMES } = await import(stateUrl);
const fresh = (hash) => { window.location.hash = hash; return new State(); };
const state = {};

let s = fresh('');
const cold = s.projectionParams();
state.cold = { frame: s.get('frame'), coord_system: cold.coord_system, apiFrame: cold.frame,
               channel: cold.channel, model: cold.model, mode: cold.mode ?? null,
               display: cold.display, rho_norm: cold.rho_norm ?? null, lock_scale: cold.lock_scale };
state.defaults = {};
for (const frame of FRAMES) {
  s.set({ frame });
  state.defaults[frame] = { display: s.get('display'), sent: s.projectionParams().display };
}
state.mapping = {};
for (const frame of FRAMES) {
  s = fresh(`#frame=${frame}`);
  const params = s.projectionParams();
  state.mapping[frame] = { coord_system: params.coord_system, frame: params.frame,
                           energy: s.energyParams().coord_system,
                           performance: s.performanceParams(), lock: params.lock_scale ?? null,
                           rho: params.rho_norm ?? null };
}

s = fresh('#frame=canonical&display=native');
state.legacyCanonical = { canonical: s.get('display'), lab: s.values.display_lab };
s = fresh('#display=native');
state.legacyLab = { lab: s.get('display'), canonical: s.values.display_canonical };
s = fresh('#frame=lab&display=continuous');
state.legacyLabContinuous = { lab: s.get('display'), canonical: s.values.display_canonical };
s = fresh('#frame=canonical&display=native&display_canonical=continuous');
state.specificWins = s.get('display');
s = fresh('#frame=canonical&display_canonical=bogus&display=bogus&display_trans=x&display_local=y');
state.invalid = { canonical: s.get('display'), lab: s.values.display_lab,
                  trans: s.values.display_trans, local: s.values.display_local };
s = fresh('#frame=hologram&channel=bogus&model=gpt&palette=jet&rho_norm=peak&weighting=x&resolution=10000');
state.enums = { frame: s.values.frame, channel: s.values.channel, model: s.values.model,
                palette: s.values.palette, rho_norm: s.values.rho_norm,
                weighting: s.values.weighting, resolution: s.values.resolution };
s = fresh('#palette=puor');
state.puorRejected = s.values.palette;

s = fresh('#frame=canonical');
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
s.set({ display: 'native', frame: 'trans' });
state.keyOrder = { frame: s.get('frame'), trans: s.values.display_trans, lab: s.values.display_lab };

s = fresh('');
s.set({ frame: 'trans' });
s.set({ frame: 'lab' });
state.emptyHash = window.location.hash;
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


def test_the_interface_opens_in_the_laboratory_frame(results):
    assert results["state"]["cold"] == {
        "frame": "lab", "coord_system": "lab", "apiFrame": "lab", "channel": "density",
        "model": "segmentation", "mode": None, "display": "native", "rho_norm": None,
        "lock_scale": True,
    }


def test_each_frame_opens_in_its_own_display_mode(results):
    defaults = results["state"]["defaults"]
    expected = {"lab": "native", "trans": "continuous", "local": "continuous",
                "canonical": "continuous"}
    assert {k: v["display"] for k, v in defaults.items()} == expected
    assert {k: v["sent"] for k, v in defaults.items()} == expected


def test_each_reference_frame_maps_onto_coord_system_and_frame(results):
    mapping = results["state"]["mapping"]
    assert {k: (v["coord_system"], v["frame"]) for k, v in mapping.items()} == {
        "lab": ("lab", "lab"), "trans": ("trans", "lab"), "local": ("local", "lab"),
        "canonical": ("lab", "canonical"),
    }
    # The energy panel and the cards follow the network frame; canonical is lab.
    assert {k: v["energy"] for k, v in mapping.items()} == {
        "lab": "lab", "trans": "trans", "local": "local", "canonical": "lab"}
    assert all(v["performance"]["model"] == "segmentation" for v in mapping.values())


def test_lock_scale_is_sent_only_in_the_lab_and_rho_norm_only_when_co_registered(results):
    mapping = results["state"]["mapping"]
    assert mapping["lab"]["lock"] is True and mapping["lab"]["rho"] is None
    for frame in ("trans", "local", "canonical"):
        assert mapping[frame]["lock"] is None and mapping[frame]["rho"] == "selection"


def test_a_legacy_display_link_applies_to_the_active_frame(results):
    state = results["state"]
    assert state["legacyCanonical"] == {"canonical": "native", "lab": "native"}
    assert state["legacyLab"] == {"lab": "native", "canonical": "continuous"}
    assert state["legacyLabContinuous"] == {"lab": "continuous", "canonical": "continuous"}


def test_the_frame_specific_key_wins_over_a_legacy_display(results):
    assert results["state"]["specificWins"] == "continuous"


def test_an_unknown_display_mode_in_a_link_keeps_the_default(results):
    assert results["state"]["invalid"] == {
        "canonical": "continuous", "lab": "native", "trans": "continuous", "local": "continuous"}


def test_unknown_enum_values_in_a_link_keep_their_defaults(results):
    assert results["state"]["enums"] == {
        "frame": "lab", "channel": "density", "model": "segmentation", "palette": "viridis",
        "rho_norm": "selection", "weighting": "energy", "resolution": 150,
    }
    assert results["state"]["puorRejected"] == "viridis", "PuOr is not a selectable ramp"


def test_switching_frames_keeps_each_frames_mode_and_the_hash_round_trips(results):
    trip = results["state"]["roundTrip"]
    assert "display_canonical=native" in trip["hashCanonical"]
    assert "frame=canonical" in trip["hashCanonical"]
    assert "display_lab" not in trip["hashCanonical"], "a default must not be written"
    assert trip["labAfterSwitch"] == "native"
    assert "display_lab=continuous" in trip["hashBoth"]
    assert "display_canonical=native" in trip["hashBoth"]
    assert trip["canonicalAfterReturn"] == "native"
    assert results["state"]["reload"] == {"frame": "lab", "canonical": "native", "lab": "continuous"}


def test_a_patch_carrying_frame_and_display_does_not_depend_on_key_order(results):
    assert results["state"]["keyOrder"] == {"frame": "trans", "trans": "native", "lab": "native"}


def test_defaults_are_not_written_to_the_hash(results):
    assert results["state"]["emptyHash"] == ""


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


# ------------------------------------------------------ signed channels --

#: Raw Shap-CAM on a co-registered path: linear -1..1, masked bins on code 1.
SHAP_LINEAR = {
    "scale": {"unit": "attribution", "scale": "linear", "vmin": -1.0, "vmax": 1.0,
              "diverging": True, "quantity": "shapcam"},
    "empty_code": 0, "below_code": 1, "min_code": 2, "max_code": 255,
}
#: Energy-weighted Shap-CAM: signed log +-(10^-3 .. 10^0), split at 129.
SIGNED_LOG = {
    "scale": {"unit": "a.u.", "scale": "signed_log10", "vmin": -3.0, "vmax": 0.0,
              "floor": "transparent", "floor_ratio": 1e-3, "quantity": "shapcam_energy",
              "diverging": True},
    "empty_code": 0, "below_code": 1, "min_code": 2, "max_code": 255, "split_code": 129,
}
#: Energy-weighted Grad-CAM on the lab path.
GRADCAM_E = {
    "scale": {"unit": "a.u.", "scale": "log10", "vmin": -3.0, "vmax": 0.0,
              "floor": "transparent", "floor_ratio": 1e-3, "quantity": "gradcam_energy"},
    "empty_code": 0, "below_code": 1, "min_code": 2, "max_code": 255,
}

_SIGNED_SCRIPT = """
const [decodeUrl, paletteUrl, scaleUrl, tokensUrl, payloads] = JSON.parse(process.argv[1]);
const { codeTable, dequantize, codeExponent } = await import(decodeUrl);
const { lookupTable, luminance, contrast, SCREEN_CARD } = await import(paletteUrl);
const scale = await import(scaleUrl);
const { PRINT_TOKENS } = await import(tokensUrl);
const rgb = (t, i) => [t[i * 3], t[i * 3 + 1], t[i * 3 + 2]];
const out = {};
const print = lookupTable('puor');
out.print = { first: rgb(print, 0), last: rgb(print, 255), mid: [rgb(print, 127), rgb(print, 128)] };
for (const name of ['puor_screen', 'puor_screen_linear']) {
  const t = lookupTable(name);
  out[name] = { lum: Array.from({ length: 256 }, (_, i) => luminance(rgb(t, i))),
                first: rgb(t, 0), last: rgb(t, 255), mid: [rgb(t, 127), rgb(t, 128)] };
}
const signed = codeTable(payloads.signed, 'viridis', 0.5);
const screen = lookupTable('puor_screen');
out.signed = {
  alpha: Array.from({ length: 256 }, (_, c) => signed[c * 4 + 3]),
  exponent: Array.from({ length: 256 }, (_, c) => codeExponent(c, payloads.signed.scale, payloads.signed)),
  contrast: Array.from({ length: 256 }, (_, c) => contrast(
    [signed[c * 4], signed[c * 4 + 1], signed[c * 4 + 2]], SCREEN_CARD)),
  code2: [signed[8], signed[9], signed[10]], screen0: rgb(screen, 0),
  code255: [signed[1020], signed[1021], signed[1022]], screen255: rgb(screen, 255),
  deq: [2, 128, 129, 255].map((c) => dequantize(c, payloads.signed.scale, payloads.signed)),
};
const linear = codeTable(payloads.linear, 'viridis', 0.5);
const lt = lookupTable('puor_screen_linear');
out.linear = {
  alpha: Array.from({ length: 256 }, (_, c) => linear[c * 4 + 3]),
  code2: [linear[8], linear[9], linear[10]], first: rgb(lt, 0),
  code255: [linear[1020], linear[1021], linear[1022]], last: rgb(lt, 255),
};
out.gradcamE = Array.from({ length: 256 }, (_, c) => codeTable(payloads.gradcamE, 'viridis', 0.5)[c * 4 + 3]);
const vmSigned = scale.visualMap(payloads.signed.scale, scale.rampPalette(payloads.signed.scale, 'viridis'));
const vmLinear = scale.visualMap(payloads.linear.scale, scale.rampPalette(payloads.linear.scale, 'viridis'));
out.legend = { signed: { stops: vmSigned.inRange.color, text: vmSigned.text, min: vmSigned.min, max: vmSigned.max },
               linear: { text: vmLinear.text } };
out.palettes = { signedScreen: scale.rampPalette(payloads.signed.scale, 'viridis'),
                 linearScreen: scale.rampPalette(payloads.linear.scale, 'viridis'),
                 density: scale.rampPalette({ scale: 'log10', unit: 'a.u.' }, 'cividis') };
Object.assign(scale.THEME, PRINT_TOKENS);
out.palettes.signedPrint = scale.rampPalette(payloads.signed.scale, 'viridis');
out.palettes.linearPrint = scale.rampPalette(payloads.linear.scale, 'viridis');
scale.restoreScreenTheme();
out.mid = [scale.rampMidLabel(payloads.linear.scale)?.style.text, scale.rampMidLabel(payloads.signed.scale)?.style.text,
           scale.rampMidLabel({ scale: 'log10' })];
out.formatted = [
  scale.formatSci(-3.2e-5), scale.formatSci(-0.25), scale.formatNumber(-1234.5), scale.formatInt(-7),
  scale.formatPercent(-0.031), scale.formatSigned(-0.083, 3), scale.formatSigned(0.23, 2, { plus: true }),
  scale.formatSigned(-0.0001, 2), scale.typographic('[-480, 480] and 1e-3'),
  scale.spatialAxis('x', -500, 500).axisLabel.formatter(-480),
];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def signed_results() -> dict:
    args = json.dumps([
        (JS / "decode.js").as_uri(), (JS / "palette.js").as_uri(), (JS / "scale.js").as_uri(),
        (JS / "export" / "tokens.js").as_uri(),
        {"signed": SIGNED_LOG, "linear": SHAP_LINEAR, "gradcamE": GRADCAM_E},
    ])
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _SIGNED_SCRIPT, args],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_print_puor_is_the_colorbrewer_scheme(signed_results):
    p = signed_results["print"]
    assert p["first"] == [127, 59, 8] and p["last"] == [45, 0, 75]
    for colour in p["mid"]:
        assert all(abs(c - 247) <= 3 for c in colour)


@pytest.mark.parametrize("name", ["puor_screen", "puor_screen_linear"])
def test_the_folded_screen_arms_brighten_monotonically_with_magnitude(signed_results, name):
    lum = signed_results[name]["lum"]
    negative = lum[:128][::-1]   # from zero outwards
    positive = lum[128:]
    # Within 1e-3: 8-bit rounding wiggles where #30363d and #542788 have
    # nearly the same luminance.
    for arm in (negative, positive):
        assert all(b >= a - 1e-3 for a, b in zip(arm, arm[1:]))
        assert arm[-1] > arm[0] + 0.3
    centre = signed_results[name]["mid"]
    expected = [28, 33, 40] if name == "puor_screen" else [48, 54, 61]
    assert centre[0] == expected and centre[1] == expected


def test_every_drawn_signed_code_clears_three_to_one_against_the_card(signed_results):
    s = signed_results["signed"]
    for code in range(2, 256):
        if s["exponent"][code] >= -2.5 - 1e-9:
            assert s["contrast"][code] >= 3.0, (code, s["exponent"][code], s["contrast"][code])


def test_a_signed_payload_is_painted_with_puor_whatever_is_chosen(signed_results):
    s = signed_results["signed"]
    assert s["code2"] == s["screen0"] and s["code255"] == s["screen255"]
    pal = signed_results["palettes"]
    assert pal == {"signedScreen": "puor_screen", "linearScreen": "puor_screen_linear",
                   "density": "cividis", "signedPrint": "puor", "linearPrint": "puor"}


def test_the_signed_log_fades_both_arms_symmetrically(signed_results):
    alpha = signed_results["signed"]["alpha"]
    exponent = signed_results["signed"]["exponent"]
    assert alpha[0] == alpha[1] == 0
    assert alpha[128] == 0 and alpha[129] == 0, "10^-3 itself is the floor"
    for i in range(127):
        assert alpha[128 - i] == alpha[129 + i]
    for code in range(2, 256):
        if exponent[code] >= -2.5 + 1e-9:
            assert alpha[code] == 255


def test_signed_codes_dequantise_to_signed_ratios(signed_results):
    got = signed_results["signed"]["deq"]
    for value, expected in zip(got, [-1.0, -1e-3, 1e-3, 1.0]):
        assert value == pytest.approx(expected, rel=1e-9)


def test_raw_shap_cam_is_opaque_puor_end_to_end(signed_results):
    s = signed_results["linear"]
    assert s["alpha"][0] == s["alpha"][1] == 0
    assert all(a == 255 for a in s["alpha"][2:])
    assert s["code2"] == s["first"] and s["code255"] == s["last"]


def test_energy_weighted_grad_cam_tapers_like_the_density_floor(signed_results):
    alpha = signed_results["gradcamE"]
    assert alpha[2] == 0 and alpha[255] == 255
    assert any(0 < a < 255 for a in alpha)


def test_the_diverging_legends_mark_both_signs(signed_results):
    signed = signed_results["legend"]["signed"]
    assert (signed["min"], signed["max"]) == (-1, 1)
    stops = signed["stops"]
    assert len(stops) % 2 == 1
    assert stops[0].startswith("rgb(") and stops[-1].startswith("rgb(")
    assert stops[len(stops) // 2].endswith(",0.000)")
    assert "+10⁰" in signed["text"][0] and signed["text"][1].startswith("−10⁰")
    assert signed_results["legend"]["linear"]["text"] == ["+1.00", "−1.00"]
    assert signed_results["mid"] == ["0", "±10⁻³", None]


def test_no_rendered_negative_number_uses_a_hyphen(signed_results):
    import re

    for text in signed_results["formatted"]:
        assert not re.search(r"-\d", text), text
    assert signed_results["formatted"][0] == "−3.20e−5"
    assert signed_results["formatted"][6] == "+0.23"
    assert signed_results["formatted"][7] == "0.00"


# ----------------------------------------------------------- frame views --

_FRAME_VIEWS_SCRIPT = """
const [url] = JSON.parse(process.argv[1]);
const fv = await import(url);
const out = { captions: {}, footnotes: {} };
for (const frame of ['lab', 'trans', 'local', 'canonical']) {
  for (const model of ['segmentation', 'energy', 'angle']) {
    for (const channel of ['density', 'gradcam', 'gradcam_energy', 'shapcam', 'shapcam_energy']) {
      out.captions[`${frame}|${model}|${channel}`] = fv.channelCaption({ channel, model, frame });
    }
  }
}
const panel = (quantity) => ({ scale: { unit: 'a.u.', scale: 'log10', floor: 'transparent',
  floor_ratio: 1e-3, quantity }, rho_unit: 'GeV/mm^2/event', below_floor_cells: 3 });
for (const kind of ['trans', 'local']) {
  const payload = {
    frame: { kind, n_events: 5, n_showers: 10, n_selected: 5, n_ab_hits: 2,
      d_dataset: { mean: 2600, ci95_half: 40 }, footprint_mm: [48.3, 48.6], pitch_mm: 20,
      splat: kind === 'trans' ? { regime: 'box_overlap' } : { regime: 'subdeposit3d', k: 2, k_z: 2 },
      depth: { pitch_mm: 20.5 }, fit: { rule: 'symmetric', provisional: true, floor_mm: 200 },
      rho: { norm: 'selection', ref: { xy: 1e-6, depth: 2e-6 } },
      reconstruction: { display: 'continuous', note: 'Kernel.' }, comb: { note: 'No comb.' },
      coherence: { r_a: 0.012 } },
    panels: { xy: panel(undefined), yz: panel('shapcam_energy'), xz: panel('gradcam_energy') },
    slab: { note: 'Slab.' }, centroids: {}, overlays: kind === 'trans' ? { trajectories: [] } : {},
    meta: { resolution: { mode: 'continuous' } },
  };
  out.footnotes[kind] = fv.footnotes(payload, { isometric: { yz: true, xz: false } });
  out.footnotes[`${kind}Legend`] = fv.exportLegend('xy', payload);
}
out.kinds = [fv.kindOf(null), fv.kindOf({ frame: { kind: 'local' } }), fv.kindOf({ frame: { kind: 'x' } })];
out.titles = ['lab', 'trans', 'local', 'canonical'].map((k) => fv.panelTitle('xy', k));
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def frame_views() -> dict:
    args = json.dumps([(JS / "frame_views.js").as_uri()])
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _FRAME_VIEWS_SCRIPT, args],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_every_channel_caption_exists_and_names_its_network(frame_views):
    network = {"lab": "absolute", "canonical": "absolute", "trans": "trans", "local": "local"}
    for key, text in frame_views["captions"].items():
        frame, model, channel = key.split("|")
        assert text and text != "—", key
        if channel != "density":
            cam = "shapcam" if channel.startswith("shapcam") else "gradcam"
            assert f"{model}_{network[frame]}_{cam}" in text, key
            assert "normalised per shower" in text, key


def test_the_per_shower_footnotes_never_call_the_offset_a_separation(frame_views):
    for kind in ("trans", "local"):
        notes = frame_views["footnotes"][kind]
        assert "not a separation" in notes["xy"] and "laboratory" in notes["xy"]
        assert "provisional" in notes["xy"]
        assert "'A+B'" in notes["xy"]
        assert "not a separation" in frame_views["footnotes"][f"{kind}Legend"]
    assert "by construction" in frame_views["footnotes"]["local"]["yz"]
    assert "R̄ = 0.012" in frame_views["footnotes"]["trans"]["xz"]
    assert "box overlap" in frame_views["footnotes"]["trans"]["xy"]
    assert "2 × 2 × 2" in frame_views["footnotes"]["local"]["xy"]
    assert "1:1" in frame_views["footnotes"]["trans"]["yz"]


def test_frame_kinds_and_titles(frame_views):
    assert frame_views["kinds"] == ["lab", "local", "lab"]
    assert frame_views["titles"][1].startswith("Δx–Δy") and frame_views["titles"][2].startswith("u–v")


def test_no_caption_or_footnote_carries_retired_wording_or_a_hyphen_minus(frame_views):
    import re

    texts = list(frame_views["captions"].values())
    for notes in frame_views["footnotes"].values():
        texts += list(notes.values()) if isinstance(notes, dict) else [notes]
    for text in texts:
        for phrase in ("29-column", "Shared voxels", "No predicted-angle"):
            assert phrase not in text
        assert not re.search(r"(?<![\w])-\d", text), text


# ------------------------------------------------ review regressions --

_REVIEW_SCRIPT = """
const [disclosureUrl, captionUrl, framesUrl, stateUrl] = JSON.parse(process.argv[1]);
const { figureDisclosure } = await import(disclosureUrl);
const { describeView } = await import(captionUrl);
const fv = await import(framesUrl);
const out = {};
const frame = (kind) => ({ kind, n_events: 7, n_showers: 14, n_selected: 9, n_excluded_no_frame: 2,
  d_dataset: { mean: 800 }, fit: {}, splat: { regime: 'box_overlap' }, footprint_mm: [48.3, 48.6], pitch_mm: 20 });
const stubState = { get: () => null, isTouched: () => false };
out.local = figureDisclosure({ frame: frame('local'), panels: { xy: { scale: {} } }, slab: { note: '' }, meta: {} }, 'xy', stubState).join(' ');
out.trans = figureDisclosure({ frame: frame('trans'), panels: { xy: { scale: {} } }, slab: { note: '' }, meta: {} }, 'xy', stubState).join(' ');
out.labCam = figureDisclosure({ panels: { xy: { scale: { quantity: 'gradcam_energy', unit: 'a.u.', scale: 'log10',
  floor_ratio: 1e-3, ref: 0.153, ref_unit: 'GeV', rho_unit: 'GeV' }, below_floor_cells: 3 } }, meta: {} }, 'xy', stubState).join(' ');
out.view = describeView({ col: [-300, 300], row: [-320.4, 320] }, 'Δx', 'Δy');
out.caption = fv.channelCaption({ channel: 'shapcam', model: 'energy', frame: 'lab',
  payload: { meta: { channel: 'gradcam', model: 'segmentation', cam: { column: 'segmentation_absolute_gradcam', note: 'OLD NOTE' } } } });
globalThis.window = { location: { hash: '', pathname: '/' },
  history: { replaceState(_s, _t, url) { const i = url.indexOf('#'); window.location.hash = i >= 0 ? url.slice(i) : ''; } } };
const { State } = await import(stateUrl);
window.location.hash = '#e1_max=5';
let s = new State();
s.adoptBounds({ e1: [0.408, 18.25], e2: [0.35, 20], d: [0, 5300] });
out.upperOnly = [s.values.e1_min, s.values.e1_max];
window.location.hash = '#d_min=19&d_max=21';
s = new State();
s.adoptBounds({ e1: [0.408, 18.25], e2: [0.35, 20], d: [19.94, 648] });
out.snappedEdge = [s.values.d_min, s.values.d_max];
window.location.hash = '#d_min=9000&d_max=9500';
s = new State();
s.adoptBounds({ e1: [0.408, 18.25], e2: [0.35, 20], d: [19.94, 648] });
out.foreign = [s.values.d_min, s.values.d_max];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def review_results() -> dict:
    args = json.dumps([(JS / "export" / "disclosure.js").as_uri(), (JS / "export" / "caption.js").as_uri(),
                       (JS / "frame_views.js").as_uri(), (JS / "state.js").as_uri()])
    done = subprocess.run([NODE, "--input-type=module", "-e", _REVIEW_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_local_frame_definition_does_not_deny_its_rotation(review_results):
    assert "no rotation" not in review_results["local"]
    assert "R(θ, φ)" in review_results["local"]


def test_a_per_shower_export_states_its_exclusions(review_results):
    assert "2 selected events excluded: no A–B separation" in review_results["trans"]


def test_a_lab_energy_weighted_cam_ref_is_a_per_bin_sum_in_gev(review_results):
    assert "GeV)" in review_results["labCam"] and "mm⁻²" not in review_results["labCam"]


def test_the_exported_view_uses_the_minus_sign(review_results):
    assert review_results["view"] == "View Δx −300–300 mm, Δy −320–320 mm."


def test_a_caption_never_names_the_previous_payloads_network(review_results):
    caption = review_results["caption"]
    assert "energy_absolute_shapcam" in caption
    assert "segmentation_absolute_gradcam" not in caption and "OLD NOTE" not in caption


def test_link_bounds_survive_adoption(review_results):
    assert review_results["upperOnly"] == [0.408, 5], "an upper-only link must keep its maximum"
    assert review_results["snappedEdge"] == [19, 21], "a bound at the snapped edge is in range"
    assert review_results["foreign"] == [19.94, 648], "a bound from another dataset resets"
