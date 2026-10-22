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
import re
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


def test_the_interface_opens_in_the_absolute_frame(results):
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

# Geometry measured on the real stylesheet: at 1600 x 900 the sidebar is 330 px
# wide under a 50 px header and the panels sit two to a row; at 1024 x 768 the
# sidebar is 280 px and the panels stack in one column.
_TOOLTIP_SCRIPT = """
const [tooltipUrl] = JSON.parse(process.argv[1]);
const t = await import(tooltipUrl);
const R = (left, top, right, bottom) => ({ left, top, right, bottom });
const wide = { viewport: R(0, 0, 1600, 900), usable: R(330, 50, 1600, 900) };
const panel1 = { chart: R(360, 110, 950, 440), plot: R(410, 130, 880, 400) };
const panel2 = { chart: R(978, 110, 1568, 440), plot: R(1028, 130, 1498, 400) };
const narrow = { viewport: R(0, 0, 1024, 768), usable: R(280, 50, 1024, 768) };
const stacked = { chart: R(310, 110, 994, 440), plot: R(360, 130, 944, 400) };
const readout = [240, 73];
const bigReadout = [323, 115];
const overlay = [363, 184];
const small = [198, 150];
const out = {
  option: t.tooltipOption(), withPosition: typeof t.tooltipOption(() => [0, 0]).position,
  gap: t.READOUT_GAP_PX, edge: t.EDGE_MARGIN_PX, layer: t.TOOLTIP_LAYER, cases: {},
};
const run = (name, layout, geom, pointer, size, prefer) => {
  const g = { ...layout, ...geom, pointer, size, ...(prefer ? { prefer } : {}) };
  out.cases[name] = { ...g, at: t.placeTooltip(g) };
};
run('readout', wide, panel1, [600, 250], readout, 'pointer');
run('bigReadout', wide, panel1, [600, 250], bigReadout, 'pointer');
run('readoutFlips', wide, panel2, [1450, 250], readout, 'pointer');
run('smallExplanation', wide, panel1, [600, 250], small);
run('overlayLeftColumn', wide, panel1, [600, 250], overlay);
run('overlayRightColumn', wide, panel2, [1200, 250], overlay);
run('overlayStacked', narrow, stacked, [600, 250], overlay);
run('overlayStackedLow', narrow, { chart: R(310, 400, 994, 730), plot: R(360, 420, 944, 690) }, [600, 550], overlay);
// A viewport too small for the tip anywhere off the chart: the least plot covered.
run('cramped', { viewport: R(0, 0, 700, 420), usable: R(200, 40, 700, 420) },
    { chart: R(210, 50, 690, 410), plot: R(250, 60, 680, 380) }, [450, 200], [420, 300]);
// The review's case: a zoomed one-column panel, pointer resting on the y-axis labels.
run('margin', { viewport: R(0, 0, 1024, 480), usable: R(280, 50, 1024, 480) },
    { chart: R(309, 110, 995, 440), plot: R(464, 122, 757, 400) }, [434, 250], bigReadout);
// A readout sweep along one row: the readout must follow the pointer, never jump off the chart.
const sweep = [];
for (let x = 1030; x < 1498; x += 6) {
  for (const size of [readout, bigReadout, [269, 77]]) {
    const at = t.placeTooltip({ ...wide, ...panel2, pointer: [x, 250], size, prefer: 'pointer' });
    sweep.push({ x, mode: at.mode, dx: at.x - x, right: at.x + size[0] - x });
  }
}
out.sweep = sweep;
out.grid = {
  pixels: t.plotBoxFromGrid({ left: 60, top: 40, width: 400, height: 300 }, 600, 400),
  insets: t.plotBoxFromGrid({ left: 50, right: 20, top: 30, bottom: 40 }, 600, 400),
  percent: t.plotBoxFromGrid([{ left: '10%', right: '10%', top: 20, bottom: '25%' }], 600, 400),
  none: t.plotBoxFromGrid(null, 600, 400),
};
// Random layouts, pointers inside the plot and in the chart's margins: the
// invariants must hold for any geometry, not just the measured ones.
let seed = 12345;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const violations = [];
const modes = {};
const ov = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
  * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
for (let i = 0; i < 6000; i++) {
  const vw = 600 + rnd() * 1400, vh = 400 + rnd() * 800;
  const side = 150 + rnd() * 250, head = 20 + rnd() * 60;
  const usable = R(side, head, vw, vh);
  const cl = side + rnd() * (vw - side) * 0.6, ct = head + rnd() * (vh - head) * 0.6;
  const chart = R(cl, ct, Math.min(vw, cl + 150 + rnd() * 700), Math.min(vh, ct + 120 + rnd() * 400));
  const plot = R(chart.left + 20 + rnd() * 120, chart.top + 15, chart.right - 20, chart.bottom - 25);
  if (plot.right - plot.left < 40 || plot.bottom - plot.top < 40) continue;
  const inMargin = rnd() < 0.3;
  const pointer = inMargin
    ? [chart.left + rnd() * (plot.left - chart.left), plot.top + rnd() * (plot.bottom - plot.top)]
    : [plot.left + rnd() * (plot.right - plot.left), plot.top + rnd() * (plot.bottom - plot.top)];
  const size = [100 + rnd() * 400, 50 + rnd() * 220];
  const prefer = rnd() < 0.5 ? 'pointer' : 'outside';
  const at = t.placeTooltip({ pointer, size, chart, plot, usable, viewport: R(0, 0, vw, vh), prefer });
  modes[at.mode] = (modes[at.mode] || 0) + 1;
  const tip = R(at.x, at.y, at.x + size[0], at.y + size[1]);
  const bad = [];
  if (![at.x, at.y].every(Number.isFinite)) bad.push('not finite');
  const room = size[0] <= vw - 2 * t.EDGE_MARGIN_PX && size[1] <= vh - 2 * t.EDGE_MARGIN_PX;
  if (room && (tip.left < -0.5 || tip.top < -0.5 || tip.right > vw + 0.5 || tip.bottom > vh + 0.5)) bad.push('off screen');
  const onPointer = pointer[0] >= tip.left && pointer[0] <= tip.right && pointer[1] >= tip.top && pointer[1] <= tip.bottom;
  if (at.mode !== 'least-overlap' && onPointer) bad.push('on the pointer');
  if (at.mode === 'pointer' && prefer !== 'pointer') bad.push('explanation left at the pointer');
  if (at.mode === 'outside-chart' && ov(tip, chart) > 0.5) bad.push('overlaps the chart');
  if (at.mode === 'outside-plot' && ov(tip, plot) > 0.5) bad.push('overlaps the plot');
  if (bad.length) violations.push({ i, bad, at, size, chart, pointer, prefer });
}
out.random = { violations: violations.slice(0, 5), count: violations.length, modes };
// The DOM glue, with stand-ins for the chart, its host, .main and the document.
const saved = { srcCoords: [1], trans: [2], invTrans: [3] };
const root = { ___zrEVENTSAVED: saved };
let listener = null;
const actions = [];
const main = { getBoundingClientRect: () => R(330, 50, 1600, 900),
  addEventListener: (type, fn) => { if (type === 'scroll') listener = fn; } };
const host = { getBoundingClientRect: () => ({ ...R(360, 110, 950, 440), width: 590, height: 330 }),
  closest: (sel) => (sel === '.main' ? main : null) };
const chart = { getDom: () => host, getZr: () => ({ painter: { getViewportRoot: () => root } }),
  dispatchAction: (a) => actions.push(a) };
globalThis.document = { documentElement: { clientWidth: 1600, clientHeight: 900 } };
const plotBox = () => ({ left: 50, top: 20, width: 470, height: 270 });
const sizeOf = (w, h) => ({ contentSize: [w, h], viewSize: [590, 330] });
out.glue = {
  readout: t.tooltipPosition(chart, plotBox, { prefer: 'pointer' })([240, 140], null, null, null, sizeOf(240, 73)),
  explanation: t.tooltipPosition(chart, plotBox)([240, 140], null, null, null, sizeOf(363, 184)),
  cleared: [saved.srcCoords, saved.trans, saved.invTrans],
};
saved.srcCoords = [9]; saved.trans = [9]; saved.invTrans = [9];
t.hideTooltipOnScroll(chart);
listener();
out.scroll = { actions, cleared: [saved.srcCoords, saved.trans, saved.invTrans] };
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


def _tip(case) -> dict:
    at, (w, h) = case["at"], case["size"]
    return {"left": at["x"], "top": at["y"], "right": at["x"] + w, "bottom": at["y"] + h}


def _overlap(a, b) -> float:
    return max(0.0, min(a["right"], b["right"]) - max(a["left"], b["left"])) * max(
        0.0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))


def _inside(a, b) -> bool:
    return (a["left"] >= b["left"] - 0.5 and a["top"] >= b["top"] - 0.5
            and a["right"] <= b["right"] + 0.5 and a["bottom"] <= b["bottom"] + 0.5)


def _covers(r, point) -> bool:
    return r["left"] <= point[0] <= r["right"] and r["top"] <= point[1] <= r["bottom"]


def test_every_chart_tooltip_is_mounted_where_nothing_clips_it(tooltip_results):
    """On the fixed layer, out of `.main`'s overflow clip, never confined, hidden at once."""
    option = tooltip_results["option"]
    assert option["appendTo"] == tooltip_results["layer"] == "#tooltip-layer"
    assert option["confine"] is False
    assert option["className"] == "calo-tooltip"
    assert option["trigger"] == "item"
    assert option["transitionDuration"] == 0 and option["hideDelay"] == 0
    assert "position" not in option and tooltip_results["withPosition"] == "function"


def test_the_bin_readout_stays_beside_the_pointer_whatever_its_size(tooltip_results):
    gap = tooltip_results["gap"]
    for name in ("readout", "bigReadout"):
        case = tooltip_results["cases"][name]
        assert case["at"]["mode"] == "pointer", name
        assert [case["at"]["x"], case["at"]["y"]] == [case["pointer"][0] + gap, case["pointer"][1] - 8], name


def test_the_bin_readout_flips_left_at_the_edge_of_the_content(tooltip_results):
    case = tooltip_results["cases"]["readoutFlips"]
    gap = tooltip_results["gap"]
    assert case["at"]["mode"] == "pointer"
    assert case["at"]["x"] == case["pointer"][0] - gap - case["size"][0]


def test_a_readout_sweep_never_jumps_off_the_chart(tooltip_results):
    """The review's hop: readouts of three sizes along a row stay beside the pointer."""
    gap = tooltip_results["gap"]
    for step in tooltip_results["sweep"]:
        assert step["mode"] == "pointer", step
        assert step["dx"] == gap or step["right"] == -gap, step


def test_every_explanation_leaves_the_chart_however_small(tooltip_results):
    case = tooltip_results["cases"]["smallExplanation"]
    assert case["at"]["mode"] == "outside-chart"
    assert _overlap(_tip(case), case["chart"]) == 0


def test_a_large_tip_moves_over_the_neighbouring_panel(tooltip_results):
    """Hovering panel 1 puts the tip over panel 2, and the other way round."""
    for name, side in (("overlayLeftColumn", "right"), ("overlayRightColumn", "left")):
        case = tooltip_results["cases"][name]
        tip = _tip(case)
        assert case["at"]["mode"] == "outside-chart", name
        assert _overlap(tip, case["chart"]) == 0, name
        assert _inside(tip, case["usable"]), f"{name}: over the sidebar or off screen"
        if side == "right":
            assert tip["left"] == case["chart"]["right"] + tooltip_results["gap"]
        else:
            assert tip["right"] == case["chart"]["left"] - tooltip_results["gap"]


def test_a_large_tip_goes_above_or_below_a_stacked_panel(tooltip_results):
    below = tooltip_results["cases"]["overlayStacked"]
    above = tooltip_results["cases"]["overlayStackedLow"]
    for case in (below, above):
        assert case["at"]["mode"] == "outside-chart"
        assert _overlap(_tip(case), case["chart"]) == 0
        assert _inside(_tip(case), case["usable"])
    assert _tip(below)["top"] >= below["chart"]["bottom"]
    assert _tip(above)["bottom"] <= above["chart"]["top"]


def test_with_no_room_off_the_chart_the_tip_covers_the_least_plot(tooltip_results):
    case = tooltip_results["cases"]["cramped"]
    tip = _tip(case)
    assert case["at"]["mode"] in ("outside-plot", "least-overlap")
    assert _inside(tip, case["viewport"])
    plot = case["plot"]
    plot_area = (plot["right"] - plot["left"]) * (plot["bottom"] - plot["top"])
    # Centred on the pointer the 420 x 300 tip would hide 97% of this plot.
    assert _overlap(tip, plot) / plot_area < 0.8


def test_a_pointer_in_the_axis_margin_is_never_covered(tooltip_results):
    case = tooltip_results["cases"]["margin"]
    assert not _covers(_tip(case), case["pointer"]), case["at"]
    assert _inside(_tip(case), case["viewport"])


def test_placement_invariants_hold_for_any_layout(tooltip_results):
    """6,000 random layouts: on screen, off the pointer, explanations off the chart."""
    random = tooltip_results["random"]
    assert random["count"] == 0, random["violations"]
    for mode in ("pointer", "outside-chart", "outside-plot", "least-overlap"):
        assert random["modes"].get(mode, 0) > 0, (mode, random["modes"])


def test_the_plot_box_follows_the_grid_option(tooltip_results):
    grid = tooltip_results["grid"]
    assert grid["pixels"] == {"left": 60, "top": 40, "width": 400, "height": 300}
    assert grid["insets"] == {"left": 50, "top": 30, "width": 530, "height": 330}
    assert grid["percent"] == {"left": 60, "top": 20, "width": 480, "height": 280}
    assert grid["none"] == {"left": 0, "top": 0, "width": 600, "height": 400}


def test_the_position_callback_translates_between_chart_and_viewport(tooltip_results):
    """Chart-local in, chart-local out; placed in viewport pixels in between."""
    glue = tooltip_results["glue"]
    gap = tooltip_results["gap"]
    # Pointer at chart (240, 140) = viewport (600, 250); the readout sits right of it.
    assert glue["readout"] == [240 + gap, 140 - 8]
    # The explanation leaves the chart (360..950): x = 950 + gap in the viewport.
    assert glue["explanation"][0] == 950 + gap - 360
    assert glue["cleared"] == [None, None, None], "zrender's cached transforms were kept"


def test_a_scroll_hides_the_tip_and_drops_the_cached_transforms(tooltip_results):
    scroll = tooltip_results["scroll"]
    assert scroll["actions"] == [{"type": "hideTip"}]
    assert scroll["cleared"] == [None, None, None]


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
        assert "laboratory" not in text, key
        if channel != "density":
            cam = "shapcam" if channel.startswith("shapcam") else "gradcam"
            assert f"{model}_{network[frame]}_{cam}" in text, key
            assert "normalised per shower" in text, key
            if network[frame] == "absolute":
                assert "absolute (detector) frame" in text, key


def test_the_per_shower_footnotes_never_call_the_offset_a_separation(frame_views):
    for kind in ("trans", "local"):
        notes = frame_views["footnotes"][kind]
        assert "not a separation" in notes["xy"] and "absolute-frame" in notes["xy"]
        assert "laboratory" not in notes["xy"]
        assert "provisional" in notes["xy"]
        assert "'A+B'" in notes["xy"]
        assert "not a separation" in frame_views["footnotes"][f"{kind}Legend"]
    assert frame_views["footnotes"]["trans"]["xy"].startswith("Slab. Per-shower translated frame (legacy):")
    assert "Separation-Aligned (D-Frame), Local" in frame_views["footnotes"]["local"]["xy"]
    assert "by construction" in frame_views["footnotes"]["local"]["yz"]
    assert "R̄ = 0.012" in frame_views["footnotes"]["trans"]["xz"]
    assert "box overlap" in frame_views["footnotes"]["trans"]["xy"]
    assert "2 × 2 × 2" in frame_views["footnotes"]["local"]["xy"]
    assert "1:1" in frame_views["footnotes"]["trans"]["yz"]


def test_frame_kinds_and_titles(frame_views):
    assert frame_views["kinds"] == ["lab", "local", "lab"]
    assert frame_views["titles"][0].startswith("XY")
    assert frame_views["titles"][1].startswith("Δx–Δy") and frame_views["titles"][2].startswith("u–v")
    assert frame_views["titles"][3].startswith("D–Y′")
    assert "Separation-Aligned (D-Frame)" in frame_views["titles"][3]
    assert "legacy" in frame_views["titles"][1]


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
const labPanel = (quantity) => ({ scale: { quantity, unit: 'a.u.', floor: quantity === 'density' ? undefined : 'transparent',
  floor_ratio: 1e-3 }, below_floor_cells: 3 });
const labPayload = (quantity) => ({ slab: { note: '' }, meta: {}, overlays: {}, selection: { n_events: 90 },
  panels: { xy: labPanel(quantity), yz: labPanel(quantity), xz: labPanel(quantity) } });
out.labFloor = fv.labFootnotes(labPayload('shapcam_energy'));
const beyond = { ...frame('trans'), window: { energy_fraction_outside: 0.0012, hits_outside: 42 } };
out.beyondExport = figureDisclosure({ frame: beyond, panels: { yz: { scale: {} } }, slab: { note: '' }, meta: {} }, 'yz', stubState).join(' ');
out.beyondScreen = fv.footnotes({ frame: beyond, panels: { xy: { scale: {} }, yz: { scale: {} }, xz: { scale: {} } },
  slab: { note: '' }, meta: {}, overlays: {}, centroids: {} });
out.beyondTiny = (await import(disclosureUrl)).beyondGridSentence({ window: { energy_fraction_outside: 1e-6, hits_outside: 1 } });
out.beyondNone = (await import(disclosureUrl)).beyondGridSentence({ window: { energy_fraction_outside: 0, hits_outside: 0 } });
out.labDensity = fv.labFootnotes(labPayload('density'));
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


_MIRROR_SCRIPT = """
const [paletteUrl] = JSON.parse(process.argv[1]);
const { lookupTable, contrast, SCREEN_CARD } = await import(paletteUrl);
const out = {};
for (const name of ['puor_screen', 'puor_screen_linear']) {
  const t = lookupTable(name);
  const c = (i) => contrast([t[i * 3], t[i * 3 + 1], t[i * 3 + 2]], SCREEN_CARD);
  out[name] = Array.from({ length: 128 }, (_, i) => Math.max(c(127 - i), c(128 + i)) / Math.min(c(127 - i), c(128 + i)));
}
console.log(JSON.stringify(out));
"""


@pytest.mark.parametrize("name,tolerance", [("puor_screen", 1.2), ("puor_screen_linear", 1.12)])
def test_equal_magnitudes_of_either_sign_are_equally_visible(name, tolerance):
    """The two screen arms are matched in lightness: at every |v| the orange and
    purple codes' contrasts against the card agree to within the tolerance."""
    args = json.dumps([(JS / "palette.js").as_uri()])
    done = subprocess.run([NODE, "--input-type=module", "-e", _MIRROR_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    ratios = json.loads(done.stdout)[name]
    assert max(ratios) <= tolerance, (max(ratios), ratios.index(max(ratios)))


# The frame_mean marks of the per-shower frames: which quantity each mark is,
# whether it is capped, and how a window overflow is clipped and disclosed.
_FRAME_MEAN_SCRIPT = """
const [overlaysUrl, disclosureUrl] = JSON.parse(process.argv[1]);
const ov = await import(overlaysUrl);
const { figureDisclosure } = await import(disclosureUrl);
const col = { name: 'x', symbol: 'Δx', lo: -300, hi: 300 };
const row = { name: 'y', symbol: 'Δy', lo: -300, hi: 300 };
const api = { coord: (p) => p };
const drawn = (series) => series.map((s) => {
  const el = s.renderItem({}, api);
  return { name: s.name, type: el.type, points: el.shape.points.length,
           tooltip: s.tooltip ? s.tooltip.formatter() : null };
});
const pair = (n, ax, sdx, cix) => ({
  n, label: 'L', dof_note: n < 2 ? "N = 1: a single event's own centroids; no dispersion or interval is defined." : 'N = 5: dof',
  a: { x: ax, y: 0, z: 0 }, b: { x: -10, y: 5, z: 0 },
  sd: { a: { x: sdx, y: 20, z: 1 }, b: { x: 25, y: 20, z: 1 } },
  ci95_half: { a: { x: cix, y: 8, z: 1 }, b: { x: 9, y: 8, z: 1 } },
});
const out = {};
let series = [];
ov.addFrameMeanSpread(series, { ...pair(1, 10, null, null), sd: { a: {}, b: {} }, ci95_half: { a: {}, b: {} } }, col, row);
out.single = series.length;
out.singleLegend = ov.centroidLegend({ frame_mean: { ...pair(1, 10, 1, 1), label: "This single event's own centroid" } });
series = [];
ov.addFrameMeanSpread(series, pair(5, 10, 30, 12), col, row);
out.inside = drawn(series);
series = [];
const clipped = pair(5, 280, 50, 30);
ov.addFrameMeanSpread(series, clipped, col, row);
out.clipped = drawn(series);
out.overflow = ov.frameMeanOverflow(clipped, col, row);
const payload = {
  frame: { kind: 'trans', n_events: 5, n_showers: 10, n_selected: 5, d_dataset: { mean: 800 }, fit: {},
           splat: { regime: 'box_overlap' }, footprint_mm: [48.3, 48.6], pitch_mm: 20 },
  panels: { xy: { scale: {}, axes: { col, row } } }, slab: { note: '' }, meta: {},
  centroids: { frame_mean: clipped },
};
out.text = ov.frameMeanOverflowText(payload);
out.export = figureDisclosure(payload, 'xy', { get: () => null, isTouched: () => false }).join(' ');
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def frame_mean_results() -> dict:
    args = json.dumps([(JS / "panels" / "canonical_overlays.js").as_uri(),
                       (JS / "export" / "disclosure.js").as_uri()])
    done = subprocess.run([NODE, "--input-type=module", "-e", _FRAME_MEAN_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_single_event_draws_no_spread_and_says_why(frame_mean_results):
    assert frame_mean_results["single"] == 0
    legend = frame_mean_results["singleLegend"]
    assert "This single event's own centroid" in legend and "no dispersion or interval" in legend
    assert "capped whiskers" not in legend


def test_the_sd_is_an_uncapped_bar_and_the_interval_a_capped_whisker(frame_mean_results):
    marks = frame_mean_results["inside"]
    spread = [m for m in marks if "spread in" in m["name"]]
    interval = [m for m in marks if "95% interval in" in m["name"]]
    # Two showers x two transverse axes, one of each mark.
    assert len(spread) == 4 and len(interval) == 4 and len(marks) == 8
    assert all(m["type"] == "polyline" and m["points"] == 2 for m in spread)
    assert all(m["type"] == "polyline" and m["points"] == 6 for m in interval)
    assert all("sample SD" in m["tooltip"] and "not the uncertainty of the mean" in m["tooltip"]
               for m in spread)
    assert all("95% Student-t interval of the mean, N = 5" in m["tooltip"] for m in interval)
    assert not any("clipped" in m["name"] for m in marks)


def test_an_end_past_the_window_is_clamped_with_a_caret_and_counted(frame_mean_results):
    marks = frame_mean_results["clipped"]
    carets = [m for m in marks if m["name"].endswith("(clipped)")]
    # Shower A at x = 280: both its SD (±50) and its interval (±30) overflow +300.
    assert len(carets) == 2 and all(m["type"] == "polygon" for m in carets)
    whisker = next(m for m in marks if m["name"] == "Mean centroid A — 95% interval in Δx")
    assert whisker["points"] == 4  # the clipped end loses its cap
    assert "the full range is 250.0 to 310.0 mm" in whisker["tooltip"]
    assert frame_mean_results["overflow"] == 2
    assert frame_mean_results["text"].startswith("2 ends of the mean-centroid SD and 95% interval")
    assert frame_mean_results["text"] in frame_mean_results["export"]


def test_a_lab_energy_weighted_cam_footnote_states_its_floor(review_results):
    for panel in ("xy", "yz", "xz"):
        text = review_results["labFloor"][panel]
        assert "|Σ E·CAM| is below 10⁻³ of this selection's peak are not drawn (3 bins)" in text
        assert "not drawn" not in review_results["labDensity"][panel]


def test_energy_outside_the_accumulation_grid_is_disclosed(review_results):
    sentence = "A further 0.12% of the selection's energy (42 hits) fell outside the accumulation grid"
    assert sentence in review_results["beyondExport"]
    for panel in ("xy", "yz", "xz"):
        assert sentence in review_results["beyondScreen"][panel]
    assert review_results["beyondTiny"].startswith("A further < 0.01% of the selection's energy (1 hit)")
    assert review_results["beyondNone"] == ""


# ------------------------------------------------ cold boot and defaults --
#
# The Admin Settings panel's defaults reach the interface only through
# State.applyDefaults, and only on a link without view state. Everything the
# bookmark guarantee rests on is pure, so it is executed here.

_COLD_BOOT_SCRIPT = """
const [stateUrl, labelsUrl] = JSON.parse(process.argv[1]);
globalThis.window = {
  location: { hash: '', pathname: '/' },
  history: {
    replaceState(_state, _title, url) {
      const at = url.indexOf('#');
      window.location.hash = at >= 0 ? url.slice(at) : '';
    },
  },
};
const { State, DEFAULTS } = await import(stateUrl);
const { CHOICE_LABELS, FRAME_TREE } = await import(labelsUrl);
const fresh = (hash) => { window.location.hash = hash; return new State(); };
const view = (s) => ({ table_name: s.values.table_name, frame: s.values.frame,
  model: s.values.model, channel: s.values.channel, rho_norm: s.values.rho_norm,
  display: s.get('display') });
const saved = { table_name: 'production', frame: 'trans', model: 'energy', channel: 'gradcam',
                display: null, rho_norm: 'dataset', notices: [] };
const out = {};

let s = fresh('');
out.coldBoot = s.coldBoot;
out.taken = s.applyDefaults(saved);
out.applied = view(s);
out.hashAfterApply = window.location.hash;
out.touched = [...s.touched];
s.writeHash();
out.written = Object.fromEntries(new URLSearchParams(window.location.hash.replace(/^#/, '')));

const reloaded = fresh(window.location.hash);
out.reloadedColdBoot = reloaded.coldBoot;
out.reloadedTakes = reloaded.applyDefaults({ ...saved, frame: 'local', channel: 'shapcam' });
out.reloaded = view(reloaded);

out.blocked = {};
for (const hash of ['#frame=lab', '#table_name=x', '#display=native', '#frame=hologram',
                    '#palette=cividis', '#e1_min=0.5']) {
  const t = fresh(hash);
  out.blocked[hash] = { coldBoot: t.coldBoot, took: t.applyDefaults(saved), frame: t.values.frame };
}
out.unknownKey = fresh('#utm_source=mail').coldBoot;

s = fresh('');
s.applyDefaults({ table_name: 'alpha', frame: DEFAULTS.frame, model: DEFAULTS.model,
                  channel: DEFAULTS.channel, display: null, rho_norm: DEFAULTS.rho_norm });
s.writeHash();
out.builtinHash = window.location.hash;

s = fresh('');
s.applyDefaults({ table_name: 'alpha', frame: 'hologram', model: 'gpt', channel: 'shapcam',
                  display: 'smooth', rho_norm: 'peak' });
out.invalid = view(s);

s = fresh('');
s.applyDefaults({ frame: 'canonical', display: 'native' });
out.displayCanonical = { canonical: s.values.display_canonical, lab: s.values.display_lab,
                         trans: s.values.display_trans };
s = fresh('');
s.applyDefaults({ frame: 'lab', display: 'continuous' });
out.displayLab = { lab: s.values.display_lab, canonical: s.values.display_canonical };

s = fresh('');
out.once = [s.applyDefaults(saved), s.applyDefaults({ ...saved, frame: 'local' }), s.values.frame];

out.defaults = DEFAULTS;
out.frozen = Object.isFrozen(DEFAULTS);
out.labels = CHOICE_LABELS;
out.tree = FRAME_TREE;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def cold_boot() -> dict:
    args = json.dumps([(JS / "state.js").as_uri(), (JS / "labels.js").as_uri()])
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", _COLD_BOOT_SCRIPT, args],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_an_empty_link_opens_on_the_saved_defaults_without_writing_the_link(cold_boot):
    assert cold_boot["coldBoot"] is True and cold_boot["taken"] is True
    assert cold_boot["applied"] == {"table_name": "production", "frame": "trans",
                                    "model": "energy", "channel": "gradcam",
                                    "rho_norm": "dataset", "display": "continuous"}
    assert cold_boot["hashAfterApply"] == ""
    assert cold_boot["touched"] == [], "a default is not a selection the user narrowed"


def test_the_first_link_written_records_every_value_that_is_not_built_in(cold_boot):
    assert cold_boot["written"] == {"table_name": "production", "frame": "trans",
                                    "model": "energy", "channel": "gradcam",
                                    "rho_norm": "dataset"}


def test_a_written_link_reopens_its_own_view_whatever_is_saved_later(cold_boot):
    assert cold_boot["reloadedColdBoot"] is False
    assert cold_boot["reloadedTakes"] is False
    assert cold_boot["reloaded"] == cold_boot["applied"]


@pytest.mark.parametrize("fragment", ["#frame=lab", "#table_name=x", "#display=native",
                                      "#frame=hologram", "#palette=cividis", "#e1_min=0.5"])
def test_any_recognised_key_keeps_the_saved_defaults_out(cold_boot, fragment):
    """An absent key in a link means "built-in": filling it from the saved defaults
    would re-read the bookmark whenever an admin saved new ones."""
    blocked = cold_boot["blocked"][fragment]
    assert blocked == {"coldBoot": False, "took": False, "frame": "lab"}


def test_an_unrecognised_key_alone_is_still_a_cold_boot(cold_boot):
    assert cold_boot["unknownKey"] is True


def test_built_in_equal_defaults_leave_only_the_experiment_in_the_link(cold_boot):
    assert cold_boot["builtinHash"] == "#table_name=alpha"


def test_invalid_saved_values_keep_the_built_in_ones(cold_boot):
    assert cold_boot["invalid"] == {"table_name": "alpha", "frame": "lab",
                                    "model": "segmentation", "channel": "shapcam",
                                    "rho_norm": "selection", "display": "native"}


def test_a_display_default_applies_to_the_default_frame_only(cold_boot):
    assert cold_boot["displayCanonical"] == {"canonical": "native", "lab": "native",
                                             "trans": "continuous"}
    assert cold_boot["displayLab"] == {"lab": "continuous", "canonical": "continuous"}


def test_the_defaults_are_taken_once(cold_boot):
    assert cold_boot["once"] == [True, False, "trans"]


def test_the_built_in_view_is_frozen(cold_boot):
    assert cold_boot["frozen"] is True


def test_the_server_built_ins_are_the_interface_defaults(cold_boot):
    """calosrv/admin/schema.py and state.js describe one built-in view."""
    from calosrv.admin.schema import BUILTIN
    from calosrv.admin.store import own_display_mode

    js = cold_boot["defaults"]
    assert BUILTIN["default_dataset"] is None and js["table_name"] is None
    assert BUILTIN["default_coord_system"] == js["frame"]
    assert BUILTIN["default_model"] == js["model"]
    assert BUILTIN["default_channel"] == js["channel"]
    assert BUILTIN["default_rho_norm"] == js["rho_norm"]
    assert BUILTIN["default_display_mode"] is None
    for frame in ("lab", "trans", "local", "canonical"):
        assert own_display_mode(frame) == js[f"display_{frame}"]


def _sidebar_radio_labels() -> dict[str, dict[str, str]]:
    """Every radio in index.html: group -> value -> its label's visible text."""
    from html.parser import HTMLParser

    class Radios(HTMLParser):
        def __init__(self):
            super().__init__()
            self.current = None
            self.found: dict[str, dict[str, str]] = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "label":
                self.current = {"text": [], "radio": None}
            elif tag == "input" and self.current is not None and attrs.get("type") == "radio":
                self.current["radio"] = (attrs.get("name"), attrs.get("value"))

        def handle_data(self, data):
            if self.current is not None:
                self.current["text"].append(data)

        def handle_endtag(self, tag):
            if tag == "label" and self.current is not None:
                if self.current["radio"]:
                    name, value = self.current["radio"]
                    text = " ".join("".join(self.current["text"]).split())
                    self.found.setdefault(name, {})[value] = text
                self.current = None

    parser = Radios()
    parser.feed((JS.parent / "index.html").read_text(encoding="utf-8"))
    return parser.found


@pytest.mark.parametrize("group", ["model", "channel", "rho_norm"])
def test_the_admin_panel_labels_are_the_sidebar_labels(cold_boot, group):
    sidebar = _sidebar_radio_labels()[group]
    panel = {
        choice["value"]: " ".join(f"{choice['label']} {choice.get('detail', '')}".split())
        for choice in cold_boot["labels"][group]
    }
    assert panel == sidebar


def _labelled(choices) -> dict[str, str]:
    return {c["value"]: " ".join(f"{c['label']} {c.get('detail', '')}".split()) for c in choices}


def test_the_frame_tree_labels_are_the_sidebar_labels(cold_boot):
    """The two tiers in index.html are labels.js FRAME_TREE, word for word and in order.

    The admin panel's flat reference-frame list is the same tree composed, so
    the three places a reader meets a frame name cannot drift apart.
    """
    sidebar = _sidebar_radio_labels()
    tree = cold_boot["tree"]
    assert sidebar["frame-view"] == _labelled(tree["views"])
    assert sidebar["frame-sub"] == _labelled(tree["subs"])
    assert list(sidebar["frame-view"]) == [v["value"] for v in tree["views"]]
    assert list(sidebar["frame-sub"]) == [s["value"] for s in tree["subs"]]
    assert "frame" not in sidebar, "no flat name=frame radio group may remain"
    aligned = next(v for v in tree["views"] if v["value"] == "aligned")["label"]
    assert {c["value"]: c["label"] for c in cold_boot["labels"]["frame"]} == {
        "lab": "Absolute",
        "canonical": f"{aligned} › Translated",
        "local": f"{aligned} › Local",
        "trans": "Per-shower translated",
    }
    assert [c["value"] for c in cold_boot["labels"]["frame"] if c.get("legacy")] == ["trans"]

# ---------------------------------------- the frame tree, the D axis, the notes --

_UI_SCRIPT = """
const [labelsUrl, axisUrl, disclosureUrl, framesUrl, notesUrl, captionUrl, stateUrl, overlaysUrl] = JSON.parse(process.argv[1]);
globalThis.window = { location: { hash: '', pathname: '/' }, history: { replaceState() {} } };
const labels = await import(labelsUrl);
const overlays = await import(overlaysUrl);
const ax = await import(axisUrl);
const { figureDisclosure } = await import(disclosureUrl);
const fv = await import(framesUrl);
const pn = await import(notesUrl);
const caption = await import(captionUrl);
const { FRAMES } = await import(stateUrl);
const out = {};

out.roundTrip = Object.fromEntries(FRAMES.map((f) => {
  const v = labels.viewOf(f); return [f, [v.view, v.sub, labels.frameOf(v.view, v.sub)]];
}));
out.bogusView = labels.viewOf('bogus');
out.frameOf = { alignedBogus: labels.frameOf('aligned', 'bogus'), absoluteLocal: labels.frameOf('absolute', 'local'),
                aligned: labels.frameOf('aligned') };
out.labels = { lab: labels.frameLabel('lab'), trans: labels.frameLabel('trans'), canonical: labels.frameLabel('canonical') };
out.choiceValues = labels.CHOICE_LABELS.frame.map((c) => c.value);
out.offered = { none: labels.offeredFrames(null),
  noBounds: labels.offeredFrames({ frames: ['lab', 'canonical'], coord_systems: ['lab'] }),
  full: labels.offeredFrames({ frames: FRAMES, coord_systems: ['lab', 'trans', 'local'] }) };
out.entering = { both: labels.enteringSub(['lab', 'canonical', 'local', 'trans']),
  noCanonical: labels.enteringSub(['lab', 'local', 'trans']), onlyTrans: labels.enteringSub(['lab', 'trans']),
  none: labels.enteringSub(['lab']) };

out.symbols = {
  xyCol: ax.axisSymbol({ name: 'x', symbol: 'x′' }, 'canonical', 'xy'),
  xzRow: ax.axisSymbol({ name: 'x', symbol: 'x′' }, 'canonical', 'xz'),
  xyRow: ax.axisSymbol({ name: 'y', symbol: 'y′' }, 'canonical', 'xy'),
  trans: ax.axisSymbol({ name: 'x', symbol: 'Δx' }, 'trans', 'xy'),
  local: ax.axisSymbol({ name: 'x' }, 'local', 'xy'),
  lab: ax.axisSymbol({ name: 'x' }, 'lab', 'xy'),
  panels: [ax.panelOf({ col: { name: 'x' }, row: { name: 'y' } }), ax.panelOf({ col: { name: 'z' }, row: { name: 'y' } }),
           ax.panelOf({ col: { name: 'z' }, row: { name: 'x' } })],
  xy: ax.panelSymbols('canonical', 'xy'), xz: ax.panelSymbols('canonical', 'xz'), yz: ax.panelSymbols('canonical', 'yz'),
};

const axesOf = (sx, sy, sz) => ({
  xy: { col: { name: 'x', symbol: sx, lo: -480, hi: 480 }, row: { name: 'y', symbol: sy, lo: -200, hi: 200 } },
  yz: { col: { name: 'z', symbol: sz, lo: 0, hi: 1210 }, row: { name: 'y', symbol: sy, lo: -200, hi: 200 } },
  xz: { col: { name: 'z', symbol: sz, lo: 0, hi: 1210 }, row: { name: 'x', symbol: sx, lo: -480, hi: 480 } },
});
const views = { xy: { col: [-480, 480], row: [-200, 200] }, yz: { col: [0, 1210], row: [-200, 200] },
                xz: { col: [0, 1210], row: [-480, 480] } };
const coPanel = (axes, id) => ({ scale: { unit: 'a.u.', scale: 'log10', floor: 'transparent', floor_ratio: 1e-3 },
  rho_unit: 'GeV/mm^2/event', below_floor_cells: 3, axes: axes[id], energy_fraction_outside_window: 0.002 });
const fitAxis = (half, floored = false) => ({ applied: true, range: [-half, half], half_width: half, floored });
const coFrame = (kind, extra) => ({ kind, n_events: 7, n_showers: 14, n_selected: 9, n_excluded_no_frame: 2, n_ab_hits: 2,
  d_entry: { mean: 800, ci95_half: 40, n: 7 }, d_dataset: { mean: 820, ci95_half: 30 }, subsample_k: 2,
  footprint_mm: [48.3, 48.6], pitch_mm: 20, depth: { pitch_mm: 20.5 },
  fit: { rule: 'symmetric', provisional: true, floor_mm: 200, percentiles: [0.1, 99.9],
    xy: { col: fitAxis(480), row: fitAxis(200, true), energy_fraction_outside: 0.002 },
    yz: { row: fitAxis(200, true), energy_fraction_outside: 0.001 },
    xz: { row: fitAxis(480), energy_fraction_outside: 0.001 } },
  rho: { norm: 'selection', ref: { xy: 1e-6, depth: 2e-6 } },
  reconstruction: { display: 'continuous', note: 'Kernel.' }, comb: { note: 'No comb.', staggered: false },
  notes: [], ensemble: {}, coherence: { r_a: 0.012 }, ...extra });
const coPayload = (kind, axes, extra) => ({ frame: coFrame(kind, extra),
  panels: { xy: coPanel(axes, 'xy'), yz: coPanel(axes, 'yz'), xz: coPanel(axes, 'xz') },
  slab: { note: 'Slab.' }, centroids: {}, overlays: kind === 'trans' ? { trajectories: [] } : {},
  meta: { resolution: { mode: 'continuous' }, exact: true }, selection: { n_events: 7, n_hits: 100 } });
const canonical = coPayload('canonical', axesOf('x′', 'y′', 'z′'), {});
const trans = coPayload('trans', axesOf('Δx', 'Δy', 'Δz'), { splat: { regime: 'box_overlap' } });
const local = coPayload('local', axesOf('u', 'v', 'w'), { splat: { regime: 'subdeposit3d', k: 2, k_z: 2 } });
const labAxes = axesOf('x', 'y', 'z');
const labPanel = (id) => ({ scale: { unit: 'GeV', scale: 'log10', vmin: -6, vmax: 0, clipped_low: 2, clipped_high: 1, locked: true },
  axes: labAxes[id] });
const lab = { slab: { note: 'Slab.' }, meta: { resolution: { mode: 'native' }, stagger: { staggered: true, note: 'Comb note.' }, exact: true },
  overlays: { coherence: { r_a: 0.012 }, trajectories: [] }, selection: { n_events: 90, n_hits: 1000 },
  panels: { xy: labPanel('xy'), yz: labPanel('yz'), xz: labPanel('xz') } };

out.windowXy = figureDisclosure(canonical, 'xy', null).find((s) => s.startsWith('Display window'));
out.windowXz = figureDisclosure(canonical, 'xz', null).find((s) => s.startsWith('Display window'));
out.canonicalXy = fv.canonicalFootnotes(canonical, { isometric: {} }).xy;

const stubState = { isTouched: () => false, get: (key) => ({ display: 'continuous', resolution: 150,
  channel: 'density', frame: 'canonical', weighting: 'energy', model: 'segmentation' })[key] ?? null };
out.notes = {};
out.titles = {};
for (const [kind, payload] of Object.entries({ lab, trans, local, canonical })) {
  for (const id of ['xy', 'yz', 'xz']) {
    const n = pn.projectionNotes({ payload, panelId: id, isometric: { xy: true, yz: true, xz: false },
      view: views[id], state: stubState, experiment: { display_name: 'Demo' } });
    out.notes[`${kind}|${id}`] = { title: n.title, hazards: n.hazards, headings: n.sections.map((s) => s.heading),
      lines: n.sections.flatMap((s) => s.lines) };
    out.titles[`${kind}|${id}`] = fv.panelTitle(id, kind);
  }
}
const energyPayload = { calibration: { applied: true, sampling_fraction_a: 0.0123, sampling_fraction_b: 0.0456 },
  axis: { clipping: { applied: true, n_outside: 3, note: 'Three events lie outside the displayed range.' } },
  meta: { warnings: ['Density curves sampled at 200 points.', 'Something else.'], network: { frame: 'absolute' } },
  series: [{ draw: 'strip' }, { draw: 'histogram' }] };
const energy = pn.energyNotes({ payload: energyPayload, notices: ['Three events lie outside the displayed range.',
  'Low-statistics series — 1 below N = 8.'], selection: { n_events: 7, n_hits: 100 }, state: stubState, experiment: null });
out.energy = { title: energy.title, hazards: energy.hazards, headings: energy.sections.map((s) => s.heading),
  sections: Object.fromEntries(energy.sections.map((s) => [s.heading, s.lines])) };
out.hazards = { provisional: pn.hazards(canonical, 'yz'), labComb: pn.hazards(lab, 'xy'), labYz: pn.hazards(lab, 'yz'),
  sampled: pn.hazards({ ...lab, meta: { ...lab.meta, exact: false, stagger: {} } }, 'xy'),
  plain: pn.hazards({ ...lab, meta: { resolution: { mode: 'continuous' } } }, 'xy'),
  energy: pn.hazards(energyPayload, 'energy'),
  energyPlain: pn.hazards({ calibration: { applied: true }, series: [{ draw: 'histogram' }] }, 'energy') };
// The overlay tooltips name the axes as the panel writes them: D on the
// entry panel, x′ on X′Z′.
const centroids = { truth_voxel: { label: 'Truth centroids', a: { x: 10, y: 5, z: 0 }, b: { x: -10, y: -5, z: 0 } },
  pred_voxel: { label: 'Predicted centroids', a: { x: 12, y: 4, z: 0 }, b: { x: -8, y: -6, z: 0 } },
  canonical_mean: { label: 'Dataset centroids', a: { x: 9, y: 3, z: 0 }, b: { x: -9, y: -3, z: 0 } } };
const anchors = { a: { x: -400, y: 0, n: 7, se95: 10 }, b: { x: 400, y: 0, n: 7, se95: 10 } };
const tips = (series) => series.map((s) => (typeof s.tooltip?.formatter === 'function' ? s.tooltip.formatter() : null)).filter(Boolean);
const panelTips = (id) => {
  const axes = canonical.panels[id].axes;
  const symbols = ax.panelSymbols('canonical', id, axes);
  const series = [];
  overlays.addCanonicalCentroids(series, centroids, axes.col, axes.row, symbols);
  overlays.addCanonicalAnchors(series, anchors, canonical.frame, axes.col, axes.row, symbols);
  return tips(series);
};
out.overlayTips = { xy: panelTips('xy'), xz: panelTips('xz') };
out.warnings = pn.warningsNotShown(['a', 'a', ' b ', 'c', ''], 'x b y');
out.nullText = pn.notesText(null);
out.captionExports = Object.keys(caption).sort();
out.sections = pn.SECTION;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def ui_results() -> dict:
    args = json.dumps([
        (JS / "labels.js").as_uri(), (JS / "axis_symbols.js").as_uri(),
        (JS / "export" / "disclosure.js").as_uri(), (JS / "frame_views.js").as_uri(),
        (JS / "panel_notes.js").as_uri(), (JS / "export" / "caption.js").as_uri(),
        (JS / "state.js").as_uri(), (JS / "panels" / "canonical_overlays.js").as_uri(),
    ])
    done = subprocess.run([NODE, "--input-type=module", "-e", _UI_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


NOTE_ORDER = ["Selection", "What is drawn", "Disclosures", "Marks and legend"]


def test_the_frame_tree_round_trips(ui_results):
    """Every frame key maps to its two tiers and back; the stored key never changes."""
    assert ui_results["roundTrip"] == {
        "lab": ["absolute", None, "lab"], "trans": ["aligned", "trans", "trans"],
        "local": ["aligned", "local", "local"], "canonical": ["aligned", "canonical", "canonical"],
    }
    assert ui_results["bogusView"] == {"view": "absolute", "sub": None}
    assert ui_results["frameOf"] == {"alignedBogus": "canonical", "absoluteLocal": "lab", "aligned": "canonical"}
    assert ui_results["labels"]["lab"] == "Absolute"
    assert ui_results["labels"]["canonical"] == "Separation-Aligned (D-Frame) › Translated"
    assert "legacy" not in ui_results["labels"]["trans"] and "Per-shower" in ui_results["labels"]["trans"]
    assert ui_results["choiceValues"] == ["lab", "canonical", "local", "trans"]


def test_entering_separation_aligned_never_lands_on_the_legacy_frame(ui_results):
    offered = ui_results["offered"]
    assert offered["none"] == ["lab", "canonical"]
    assert offered["noBounds"] == ["lab", "canonical"]
    assert offered["full"] == ["lab", "trans", "local", "canonical"]
    assert ui_results["entering"] == {"both": "canonical", "noCanonical": "local", "onlyTrans": None, "none": None}


def test_the_separation_aligned_entry_panel_writes_x_prime_as_d(ui_results):
    s = ui_results["symbols"]
    assert s["xyCol"] == "D" and s["xzRow"] == "x′" and s["xyRow"] == "y′"
    assert (s["trans"], s["local"], s["lab"]) == ("Δx", "u", "x")
    assert s["panels"] == ["xy", "yz", "xz"]
    assert s["xy"] == {"col": "D", "row": "y′"}
    assert s["xz"] == {"col": "z′", "row": "x′"} and s["yz"] == {"col": "z′", "row": "y′"}
    assert "Display window: D ±480 mm, y′ ±200 mm" in ui_results["windowXy"]
    assert "x′ ±480 mm" in ui_results["windowXz"] and "D ±" not in ui_results["windowXz"]
    xy = ui_results["canonicalXy"]
    assert xy.startswith("Slab. Separation-Aligned (D-Frame), Translated: N = 7")
    assert "Window D ±480 mm, y′ ±200 mm" in xy
    assert "D = ∓⟨D_entry⟩/2" in xy and "written D" in xy


def test_the_overlay_tooltips_write_the_entry_axis_as_d(ui_results):
    tips = ui_results["overlayTips"]
    assert len(tips["xy"]) >= 4 and len(tips["xz"]) >= 4
    for tip in tips["xy"]:
        assert "x′ =" not in tip, tip
    assert any("D = " in tip for tip in tips["xy"])
    assert any("D-frame anchor" in tip and "D = " in tip for tip in tips["xy"])
    assert any("x′ = " in tip for tip in tips["xz"])
    assert not any("D = " in tip for tip in tips["xz"])


def test_projection_notes_are_sectioned_in_a_fixed_order(ui_results):
    for key, notes in ui_results["notes"].items():
        kind = key.split("|")[0]
        positions = [NOTE_ORDER.index(h) for h in notes["headings"]]
        assert positions == sorted(positions), key
        assert notes["headings"][:2] == ["Selection", "What is drawn"], key
        # The lab entry panel's legend is inside its footnote; its depth panels
        # carry one for the energy centres or the trajectories, and the windowed
        # axis when it is drawn. A co-registered entry panel always has one. A
        # depth panel's legend sentence can coincide with a disclosure line,
        # and is then stated once, under Disclosures.
        if kind == "lab":
            assert ("Marks and legend" in notes["headings"]) == (not key.endswith("|xy")), key
        elif key.endswith("|xy"):
            assert "Marks and legend" in notes["headings"], key
        assert notes["title"] == ui_results["titles"][key], key


def test_notes_never_repeat_a_sentence(ui_results):
    for key, notes in ui_results["notes"].items():
        collapsed = [" ".join(line.split()) for line in notes["lines"]]
        assert len(collapsed) == len(set(collapsed)), key


def test_the_notes_carry_the_structural_disclosures(ui_results):
    notes = ui_results["notes"]
    assert any("not a separation" in line for line in notes["trans|xy"]["lines"])
    assert any("1:1" in line for line in notes["canonical|yz"]["lines"])
    assert "View D −480–480 mm, y′ −200–200 mm." in notes["canonical|xy"]["lines"]
    assert "View z′ 0–1210 mm, x′ −480–480 mm." in notes["canonical|xz"]["lines"]
    assert any(line.startswith("Experiment Demo") for line in notes["lab|xy"]["lines"])
    assert any("Comb note." in line for line in notes["lab|xy"]["lines"])
    assert any("not a shower edge" in line for line in notes["canonical|xy"]["lines"])


def test_energy_notes_carry_calibration_clipping_notices_and_the_explainer(ui_results):
    energy = ui_results["energy"]
    assert energy["title"] == "Reconstructed Energy vs. Separation D"
    drawn = energy["sections"]["What is drawn"]
    assert any("sampling fractions" in line for line in drawn)
    assert any("segmentation network" in line for line in drawn)
    assert any("Gaussian fits" in line for line in drawn)
    assert "Density curves sampled at 200 points." in drawn and "Something else." not in drawn
    disclosures = energy["sections"]["Disclosures"]
    assert disclosures == ["Three events lie outside the displayed range.", "Low-statistics series — 1 below N = 8."]
    assert energy["sections"]["Reading the density axis"][0].startswith("A probability density is not a probability.")
    assert energy["headings"][-1] == "Reading the density axis"


def test_hazards_are_structural(ui_results):
    h = ui_results["hazards"]
    assert h["provisional"] == ["provisional fitted range"]
    assert h["labComb"] == ["measured lattice comb"] and h["labYz"] == []
    assert h["sampled"] == ["sampled preview"]
    assert h["plain"] == []
    assert h["energy"] == ["low-statistics series", "clipped energy range"]
    assert h["energyPlain"] == []


def test_warnings_not_shown_drops_what_the_notes_already_say(ui_results):
    assert ui_results["warnings"] == ["a", "c"]
    assert ui_results["nullText"] == ""


def test_the_caption_module_exports_only_provenance_helpers(ui_results):
    assert ui_results["captionExports"] == ["describeSelection", "describeView", "displayOf", "kernelPhrase"]
    assert list(ui_results["sections"].values()) == NOTE_ORDER + ["Reading the density axis"]


def test_no_note_carries_a_hyphen_minus(ui_results):
    import re

    for key, notes in ui_results["notes"].items():
        for line in notes["lines"]:
            assert not re.search(r"(?<![\w])-\d", line), (key, line)


# ------------------------------------ the anchor choice and the coordinate source --

_ANCHOR_SCRIPT = """
const [stateUrl, framesUrl, disclosureUrl, captionUrl, filenameUrl] = JSON.parse(process.argv[1]);
globalThis.window = {
  location: { hash: '', pathname: '/' },
  history: { replaceState(_s, _t, url) { const at = url.indexOf('#'); window.location.hash = at >= 0 ? url.slice(at) : ''; } },
};
const { State, ANCHORS, DEFAULTS } = await import(stateUrl);
const fv = await import(framesUrl);
const { figureDisclosure } = await import(disclosureUrl);
const { describeSelection } = await import(captionUrl);
const { figureName } = await import(filenameUrl);
const out = { anchors: ANCHORS, defaultAnchor: DEFAULTS.anchor };

const fresh = (hash) => { window.location.hash = hash; return new State(); };
let s = fresh('#frame=canonical&anchor=p0');
out.p0 = { anchor: s.get('anchor'), sent: s.projectionParams().anchor ?? null, hash: window.location.hash };
s.set({ frame: 'lab' });
out.labSends = s.projectionParams().anchor ?? null;
s = fresh('#frame=canonical&anchor=centroid');
out.bogus = s.get('anchor');
s = fresh('#frame=canonical');
out.defaultSent = s.projectionParams().anchor ?? null;
out.defaultHash = window.location.hash;

const residual = { a: { median: 46.4, p90: 133.4, over_footprint: 9620 }, b: { median: 45.2, p90: 132.6, over_footprint: 9382 },
  footprint_mm: 48.6, n: 20268 };
const axesOf = (sx, sy, sz) => ({
  xy: { col: { name: 'x', symbol: sx, lo: -480, hi: 480 }, row: { name: 'y', symbol: sy, lo: -200, hi: 200 } },
  yz: { col: { name: 'z', symbol: sz, lo: 0, hi: 1210 }, row: { name: 'y', symbol: sy, lo: -200, hi: 200 } },
  xz: { col: { name: 'z', symbol: sz, lo: 0, hi: 1210 }, row: { name: 'x', symbol: sx, lo: -480, hi: 480 } },
});
const fitAxis = (half) => ({ applied: true, range: [-half, half], half_width: half, floored: false });
const frame = (extra) => ({ kind: 'canonical', n_events: 7, n_selected: 7, n_excluded_no_frame: 0,
  d_entry: { mean: 800, ci95_half: 40, n: 7 }, d_dataset: { mean: 820, ci95_half: 30 }, subsample_k: 2,
  footprint_mm: [48.3, 48.6], pitch_mm: 20, fit: { rule: 'symmetric', provisional: true, floor_mm: 200,
  percentiles: [0.1, 99.9], xy: { col: fitAxis(480), row: fitAxis(200), energy_fraction_outside: 0.002 },
  yz: { row: fitAxis(200), energy_fraction_outside: 0.001 }, xz: { row: fitAxis(480), energy_fraction_outside: 0.001 } },
  rho: { norm: 'selection', ref: { xy: 1e-6, depth: 2e-6 } }, reconstruction: { display: 'continuous', note: 'Kernel.' },
  comb: { note: 'No comb.', staggered: false }, notes: [], ensemble: {}, coherence: { r_a: 0.012 }, ...extra });
const axes = axesOf('x′', 'y′', 'z′');
const panel = (id) => ({ scale: { unit: 'a.u.', scale: 'log10', floor: 'transparent', floor_ratio: 1e-3 },
  rho_unit: 'GeV/mm^2/event', below_floor_cells: 3, axes: axes[id], energy_fraction_outside_window: 0.002 });
const payload = (f) => ({ frame: f, panels: { xy: panel('xy'), yz: panel('yz'), xz: panel('xz') }, slab: { note: 'Slab.' },
  centroids: {}, overlays: {}, meta: { resolution: { mode: 'continuous' }, exact: true, frame: 'canonical', anchor: f.anchor_choice },
  selection: { n_events: 7, n_hits: 100 } });

const withResidual = payload(frame({ anchor_choice: 'backprojected', anchor_residual: residual }));
const onP0 = payload(frame({ anchor_choice: 'p0', anchor_residual: residual }));
const older = payload(frame({}));
out.sentence = { backprojected: fv.anchorSentence(withResidual.frame), p0: fv.anchorSentence(onP0.frame),
  older: fv.anchorSentence(older.frame) };
out.footnote = fv.canonicalFootnotes(withResidual, { isometric: {} }).xy;
out.disclosure = { backprojected: figureDisclosure(withResidual, 'xy', null), p0: figureDisclosure(onP0, 'xy', null),
  depth: figureDisclosure(onP0, 'yz', null) };
const stubState = { isTouched: () => false, get: (key) => ({ display: 'continuous', resolution: 150, channel: 'density',
  frame: 'canonical', weighting: 'energy', model: 'segmentation', anchor: 'p0' })[key] ?? null };
out.caption = { p0: describeSelection(stubState, null, null, onP0.frame, null, { spatial: true, meta: onP0.meta }),
  backprojected: describeSelection(stubState, null, null, withResidual.frame, null, { spatial: true, meta: withResidual.meta }) };
out.names = { p0: figureName('xy', 'svg', { state: stubState, meta: onP0.meta }),
  backprojected: figureName('xy', 'svg', { state: stubState, meta: withResidual.meta }) };

const shower = { kind: 'local', n_events: 7, n_showers: 14, n_selected: 7, n_excluded_no_frame: 0, n_ab_hits: 0,
  d_dataset: { mean: 820, ci95_half: 30 }, footprint_mm: [48.3, 48.6], pitch_mm: 20, depth: { pitch_mm: 20.5 },
  splat: { regime: 'subdeposit3d', k: 2, k_z: 2 }, fit: withResidual.frame.fit, rho: withResidual.frame.rho,
  reconstruction: { display: 'continuous', note: 'Kernel.' }, comb: { note: 'No comb.', staggered: false },
  coordinates: { source: 'computed', residual_max_mm: 0.00023, tolerance_mm: 0.01, within_tolerance: true,
    note: 'Coordinates: recomputed inside the scan as R(θ, φ) applied; over this selection the two differ by at most 0.00023 mm.' } };
const localAxes = axesOf('u', 'v', 'w');
const localPayload = { frame: shower, panels: { xy: { ...panel('xy'), axes: localAxes.xy }, yz: { ...panel('yz'), axes: localAxes.yz },
  xz: { ...panel('xz'), axes: localAxes.xz } }, slab: { note: 'Slab.' }, centroids: {}, overlays: {},
  meta: { resolution: { mode: 'continuous' }, exact: true, frame: 'local' }, selection: { n_events: 7, n_hits: 100 } };
out.coordinates = { sentence: fv.coordinatesSentence(shower), footnote: fv.showerFootnotes(localPayload, { isometric: {} }).xy,
  disclosure: figureDisclosure(localPayload, 'xy', null), none: fv.coordinatesSentence({}) };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def anchor_results() -> dict:
    args = json.dumps([
        (JS / "state.js").as_uri(), (JS / "frame_views.js").as_uri(),
        (JS / "export" / "disclosure.js").as_uri(), (JS / "export" / "caption.js").as_uri(),
        (JS / "export" / "filename.js").as_uri(),
    ])
    done = subprocess.run([NODE, "--input-type=module", "-e", _ANCHOR_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_anchor_is_a_d_frame_key_sent_only_with_the_d_frame(anchor_results):
    r = anchor_results
    assert r["anchors"] == ["backprojected", "p0"] and r["defaultAnchor"] == "backprojected"
    assert r["p0"] == {"anchor": "p0", "sent": "p0", "hash": "#frame=canonical&anchor=p0"}
    assert r["labSends"] is None, "the API refuses an anchor outside the D-frame"
    assert r["bogus"] == "backprojected"
    assert r["defaultSent"] == "backprojected" and r["defaultHash"] == "#frame=canonical"


def test_the_drawer_names_the_anchor_and_the_distance_to_the_other_definition(anchor_results):
    r = anchor_results
    back = r["sentence"]["backprojected"]
    assert back.startswith(" Anchor: each shower’s 3-D centroid, back-projected to the front face.")
    assert "first-layer entry point P₀" in back and "shower A median 46 mm, p90 133 mm" in back
    assert "9,620 more than one cell footprint apart" in back and "N = 20,268" in back
    p0 = r["sentence"]["p0"]
    assert p0.startswith(" Anchor: each shower’s first-layer entry point P₀")
    assert "the back-projected 3-D centroid, lands" in p0
    assert r["sentence"]["older"] == "", "a payload without the choice gets no sentence"
    assert back.strip() in r["footnote"]
    assert any(s.startswith("Anchor = backprojected;") for s in r["disclosure"]["backprojected"])
    assert any(s.startswith("Anchor = p0;") and "3-D centroid" in s for s in r["disclosure"]["p0"])
    assert r["disclosure"]["p0"][0].startswith("Separation-Aligned (D-Frame), Translated, anchored on P₀")
    assert not any(s.startswith("Anchor =") for s in r["disclosure"]["depth"]), "the entry panel alone states it"
    assert "anchored on P₀" in r["caption"]["p0"] and "anchored on P₀" not in r["caption"]["backprojected"]
    assert "_canonical_p0_" in r["names"]["p0"] and "_p0" not in r["names"]["backprojected"]
    for text in (back, p0, *r["disclosure"]["p0"]):
        assert not re.search(r"-\d", text), text


def test_the_per_shower_drawer_states_the_coordinate_source(anchor_results):
    r = anchor_results["coordinates"]
    assert r["sentence"].startswith(" Coordinates: recomputed inside the scan")
    assert r["sentence"].strip() in r["footnote"]
    assert any(s.startswith("Coordinates: recomputed") for s in r["disclosure"])
    assert r["none"] == ""


# ----------------------------------------------------- the Event Inspector --

_EVENT_SCRIPT = """
const [marksUrl, stateUrl, notesUrl, framesUrl, filenameUrl] = JSON.parse(process.argv[1]);
globalThis.window = {
  location: { hash: '', pathname: '/' },
  history: { replaceState(_s, _t, url) { const at = url.indexOf('#'); window.location.hash = at >= 0 ? url.slice(at) : ''; } },
};
const { projectMarks } = await import(marksUrl);
const { State, DEFAULTS, SHOWERS } = await import(stateUrl);
const { eventNotes, hazards, SECTION } = await import(notesUrl);
const { eventRowLabel, eventSelectionLine, eventFrameSentence } = await import(framesUrl);
const { figureName } = await import(filenameUrl);
const out = {};

// The marks of the laboratory and translated frames, and of the local one.
const o = [100, -20, 3662];
const d = [0.1, -0.2, 0.97];
const marks = [
  { type: 'line', style: 'forward', origin: o, direction: d, panels: null, name: 'f', tooltip: 'F' },
  { type: 'line', style: 'backward', origin: o, direction: d.map((v) => -v), panels: null, name: 'b', tooltip: 'B' },
  { type: 'plane', style: 'plane', axis: 'z', at: 3662, panels: ['xz', 'yz'], name: 'p', tooltip: 'P' },
  { type: 'point', style: 'origin', at: o, panels: null, name: 'o', tooltip: 'O' },
];
const tan = Math.tan(0.2);
const localMarks = [
  { type: 'line', style: 'forward', origin: [0, 0, 0], direction: [0, 0, 1], panels: null, name: 'f' },
  { type: 'line', style: 'plane', origin: [0, 0, 0], direction: [1, 0, tan], panels: ['xz'], name: 'p' },
  { type: 'point', style: 'origin', at: [0, 0, 0], panels: null, name: 'o' },
];
const byName = (list) => Object.fromEntries(list.map((m) => [m.name, m]));
out.marks = {
  xy: byName(projectMarks(marks, 'x', 'y', 'xy', 300)),
  xz: byName(projectMarks(marks, 'z', 'x', 'xz', 300)),
  yz: byName(projectMarks(marks, 'z', 'y', 'yz', 300)),
  localXy: byName(projectMarks(localMarks, 'x', 'y', 'xy', 300)),
  localXz: byName(projectMarks(localMarks, 'z', 'x', 'xz', 300)),
  localYz: byName(projectMarks(localMarks, 'z', 'y', 'yz', 300)),
  none: projectMarks(null, 'x', 'y', 'xy', 300),
  tan,
};

// The event, the shower and the comparison are view state.
const fresh = (hash) => { window.location.hash = hash; return new State(); };
let s = fresh('#event=12&shower=b&compare=true');
out.state = { event: s.get('event'), shower: s.get('shower'), compare: s.get('compare'),
              params: s.eventParams(), hash: window.location.hash };
s.set({ event: null });
out.unpinned = window.location.hash;
s = fresh('#event=1.5&shower=c&compare=maybe');
out.invalid = { event: s.get('event'), shower: s.get('shower'), compare: s.get('compare') };
out.negative = fresh('#event=-3').get('event');
s = fresh('');
out.defaults = { event: DEFAULTS.event, shower: DEFAULTS.shower, compare: DEFAULTS.compare, showers: SHOWERS };
s.set({ event: 7 });
out.pinnedHash = window.location.hash;
s = fresh('#frame=canonical&anchor=p0');
const lab = s.projectionParams(false, 'lab');
const local = s.projectionParams(false, 'local');
out.compareParams = { lab: { coord: lab.coord_system, frame: lab.frame, display: lab.display, lock: lab.lock_scale ?? null,
                             rho: lab.rho_norm ?? null, anchor: lab.anchor ?? null },
                      local: { coord: local.coord_system, frame: local.frame, display: local.display,
                               lock: local.lock_scale ?? null, rho: local.rho_norm ?? null, anchor: local.anchor ?? null },
                      active: s.projectionParams().anchor ?? null };

// A response of /api/event, as query/event_inspector.py shapes it.
const axesOf = (sym, win) => ({
  xy: { col: { name: 'x', symbol: sym.x, lo: win.x[0], hi: win.x[1] }, row: { name: 'y', symbol: sym.y, lo: win.y[0], hi: win.y[1] } },
  xz: { col: { name: 'z', symbol: sym.z, lo: win.z[0], hi: win.z[1] }, row: { name: 'x', symbol: sym.x, lo: win.x[0], hi: win.x[1] } },
  yz: { col: { name: 'z', symbol: sym.z, lo: win.z[0], hi: win.z[1] }, row: { name: 'y', symbol: sym.y, lo: win.y[0], hi: win.y[1] } },
});
const panel = (id, axes, below) => ({
  panel: id, axes: axes[id], shape: [30, 30], native: false,
  scale: { unit: 'GeV/mm^2', scale: 'log10', vmin: -6, vmax: -3, locked: true, clipped_low: below, clipped_high: 0 },
  total: 0.012, total_energy_all_gev: 0.0123, energy_outside_window_gev: below ? 0.0003 : 0,
  energy_fraction_outside_window: below ? 0.0244 : 0, kernel: 'none', n_events: 1, rho_unit: 'GeV/mm^2',
});
const frame = (kind, title, sym, win, splat, depth, m) => {
  const axes = axesOf(sym, win);
  return { kind, title, symbols: sym, window: win, raster: win, half_mm: 300,
    panels: { xy: panel('xy', axes, 2), xz: panel('xz', axes, 0), yz: panel('yz', axes, 1) }, marks: m, depth, splat };
};
const labWin = { x: [-200, 400], y: [-320, 280], z: [3362, 3962] };
const localWin = { x: [-300, 300], y: [-300, 300], z: [-100, 500] };
const shower = { key: 'a', label: 'A', n_hits: 310, energy_gev: 0.0123, momentum_gev: 3.2, theta: 0.2, phi: -1.0,
  theta_deg: 11.5, phi_deg: -57.3, p0: [100.5, -20.25, 3662.4], first_layer_z: 3662.4, direction: d,
  principal_axis: { tilt_deg: 3.4, axis: [0, 0, 1], eigenvalues: [1, 2, 3], n: 310 } };
const payload = {
  frames: {
    lab: frame('lab', 'Original — detector coordinates (x, y, z)', { x: 'x', y: 'y', z: 'z' }, labWin,
      { regime: 'native_lattice', pitch_mm: null },
      { policy: 'native_layers', pitch_mm: 20.5, note: "the detector's own sampling layers, cropped to the event" }, marks),
    trans: frame('trans', 'Translated only — origin shifted to P₀, not rotated (Δx, Δy, Δz)', { x: 'Δx', y: 'Δy', z: 'Δz' },
      localWin, { regime: 'box_overlap', pitch_mm: 20, k: null, k_z: null },
      { policy: 'native_layers', pitch_mm: 20.5, note: "the shower's own sampling layers counted from its first, cropped to the event" }, marks),
    local: frame('local', 'Local — translated and rotated by R(θ, φ) (u, v, w)', { x: 'u', y: 'v', z: 'w' }, localWin,
      { regime: 'subdeposit3d', pitch_mm: 20, k: 4, k_z: 2 },
      { policy: 'uniform_bins', pitch_mm: 20.5, note: 'uniform bins of the layer pitch along w, cropped to the event, never smoothed' }, localMarks),
  },
  scale: { unit: 'GeV/mm^2', floor: 1e-6, top: 1e-3, vmin: -6, vmax: -3, floor_percentile: 1, n_below: 9,
    rule: 'One logarithmic ramp for all nine panels: projected energy surface density in GeV per mm², from the 1st percentile of this shower’s positive lattice-cell densities (1e-06) to its brightest bin (0.001); 9 bins below the floor are drawn at the lowest colour.' },
  grid: { pitch_mm: 20, notes: [] },
  event: { event_number: 1234, in_selection: true, prev: 1200, next: 1300, n_hits: 532, d: 412.3, e1: 3.2, e2: 1.1, overlap: 0, shower },
  coordinates: { source: 'file', residual_max_mm: 0.00005, tolerance_mm: 0.01, within_tolerance: true,
    note: 'Coordinates: the file’s own x/y_trans and x/y/z_local; the motions were also applied to every cell here, and the two differ by at most 5e-05 mm (within the 0.01 mm tolerance).' },
  window: { half_mm: 300, pad: 1.15, min_half_mm: 150,
    rule: 'One half-width for all nine panels: 1.15 × half the largest extent of the cloud over x, y, z, u, v and w, never below 150 mm (300 mm here).' },
  footprint_mm: [48.27, 48.6, 20.5],
  meta: { table_name: 'demo', event: 1234, shower: 'a', notices: [] },
};
const stubState = { isTouched: (axis) => axis === 'd',
  get: (key) => ({ d_min: 100, d_max: 500, include_undefined_d: false, display: 'native', resolution: 150,
    channel: 'gradcam', frame: 'canonical', model: 'segmentation' })[key] ?? null };
out.notes = {
  local: eventNotes({ payload, kind: 'local', panelId: 'xz', view: { col: [-50, 450], row: [-100, 100] },
                      state: stubState, experiment: { display_name: 'Demo' } }),
  lab: eventNotes({ payload, kind: 'lab', panelId: 'xy' }),
  missing: eventNotes({ payload, kind: 'canonical', panelId: 'xy' }),
};
const outside = { ...payload,
  event: { ...payload.event, in_selection: false, shower: { ...shower, principal_axis: null } },
  grid: { pitch_mm: 40, notes: ['Grids coarsened from 20 mm to 40 mm to keep the response under the 100,000-byte contract.'] },
  coordinates: { ...payload.coordinates, within_tolerance: false } };
out.hazards = { fine: hazards(payload, 'xy'), bad: hazards(outside, 'yz') };
out.outsideNotes = eventNotes({ payload: outside, kind: 'trans', panelId: 'yz' });
out.label = { full: eventRowLabel(payload.event), noAxis: eventRowLabel(outside.event), none: eventRowLabel(null) };
out.selection = { inside: eventSelectionLine(payload.event), outside: eventSelectionLine(outside.event) };
out.sentences = { lab: eventFrameSentence(payload, 'lab'), trans: eventFrameSentence(payload, 'trans'),
                  local: eventFrameSentence(payload, 'local') };
out.names = {
  local: figureName('event-local-xy', 'svg', { state: stubState, display: { mode: 'native' },
    meta: { frame: 'local', channel: 'density', event: 1234, shower: 'a' } }),
  lab: figureName('event-lab-xz', 'png', { state: stubState, display: { mode: 'native' },
    meta: { channel: 'density', event: 1234, shower: 'b' } }),
  ensemble: figureName('xy', 'svg', { state: stubState, meta: { frame: 'canonical', channel: 'density' } }),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def event_results() -> dict:
    args = json.dumps([
        (JS / "panels" / "marks.js").as_uri(), (JS / "state.js").as_uri(), (JS / "panel_notes.js").as_uri(),
        (JS / "frame_views.js").as_uri(), (JS / "export" / "filename.js").as_uri(),
    ])
    done = subprocess.run([NODE, "--input-type=module", "-e", _EVENT_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _slope(line) -> float:
    (x0, y0), (x1, y1) = line["from"], line["to"]
    return (y1 - y0) / (x1 - x0)


def test_the_marks_project_onto_each_panels_two_axes(event_results):
    m = event_results["marks"]
    xy = m["xy"]
    # The forward line runs from the origin along the direction's (x, y).
    assert xy["f"]["from"] == [100, -20] and xy["f"]["style"] == "forward" and xy["f"]["tooltip"] == "F"
    assert xy["f"]["to"][0] > 100 and _slope(xy["f"]) == pytest.approx(-0.2 / 0.1)
    # Backward is the same line the other way, from the origin too.
    assert xy["b"]["from"] == [100, -20] and xy["b"]["to"][0] < 100 and _slope(xy["b"]) == pytest.approx(-0.2 / 0.1)
    assert "p" not in xy, "the first-layer plane has no image on the entry panel"
    assert xy["o"] == {"type": "point", "at": [100, -20], "name": "o", "tooltip": "O"}
    # The depth panels: z on the column axis, so the plane z = z0 is a vertical rule.
    for panel, row in (("xz", 100), ("yz", -20)):
        p = m[panel]
        assert p["p"]["style"] == "plane" and p["p"]["from"][0] == 3662 == p["p"]["to"][0]
        assert p["p"]["from"][1] < -1000 < 1000 < p["p"]["to"][1], "a rule across the whole panel"
        assert p["f"]["from"] == [3662, row] and p["f"]["to"][0] > 3662
        assert p["b"]["to"][0] < 3662 and p["o"]["at"] == [3662, row]
    assert m["none"] == []


def test_the_local_plane_is_the_tilted_line_on_the_xz_panel_only(event_results):
    m = event_results["marks"]
    tan = m["tan"]
    xz = m["localXz"]
    # z' = tan(theta) x' with z on the column axis: dx/dz = 1/tan, through the origin, both ways.
    assert _slope(xz["p"]) == pytest.approx(1 / tan)
    assert xz["p"]["from"][0] < 0 < xz["p"]["to"][0] and xz["p"]["style"] == "plane"
    assert xz["f"]["from"] == [0, 0] and xz["f"]["to"][1] == 0 and xz["f"]["to"][0] > 0
    assert "p" not in m["localXy"] and "p" not in m["localYz"]
    # The +w direction has no component in the u-v plane, so no line is drawn there; the origin is.
    assert "f" not in m["localXy"] and m["localXy"]["o"]["at"] == [0, 0]
    assert m["localYz"]["f"]["from"] == [0, 0]


def test_the_event_and_shower_are_view_state(event_results):
    r = event_results
    assert r["state"]["event"] == 12 and r["state"]["shower"] == "b" and r["state"]["compare"] is True
    assert r["state"]["params"]["event_number"] == 12 and r["state"]["params"]["shower"] == "b"
    assert "table_name" in r["state"]["params"] and "d_min" in r["state"]["params"]
    assert r["state"]["hash"] == "#event=12&shower=b&compare=true"
    assert "event=" not in r["unpinned"] and "shower=b" in r["unpinned"]
    assert r["invalid"] == {"event": None, "shower": "a", "compare": False}
    assert r["negative"] is None
    assert r["defaults"] == {"event": None, "shower": "a", "compare": False, "showers": ["a", "b"]}
    assert r["pinnedHash"] == "#event=7"


def test_the_comparison_asks_each_frame_in_its_own_display_mode(event_results):
    r = event_results["compareParams"]
    assert r["lab"] == {"coord": "lab", "frame": "lab", "display": "native", "lock": True, "rho": None, "anchor": None}
    assert r["local"] == {"coord": "local", "frame": "lab", "display": "continuous", "lock": None,
                          "rho": "selection", "anchor": None}
    assert r["active"] == "p0", "the active frame's own parameters are unchanged"


def test_event_notes_are_sectioned_and_carry_the_disclosures(event_results):
    notes = event_results["notes"]["local"]
    assert notes["title"] == "Local — translated and rotated by R(θ, φ) (u, v, w): u–w"
    assert [s["heading"] for s in notes["sections"]] == ["Selection", "What is drawn", "Disclosures", "Marks and legend"]
    selection = notes["sections"][0]["lines"]
    assert selection[0].startswith("Event 1,234, shower A: 310 cells, 0.0123 GeV deposited, θ = 11.5°, φ = −57.3°, P₀ = (100.5, −20.3, 3662.4) mm, principal axis 3.4° from +w.")
    assert selection[1].startswith("Event 1,234: 532 hits in all, E₁ = 3.20 GeV, E₂ = 1.10 GeV, D = 412 mm; inside the current selection.")
    assert selection[2] == "Experiment Demo · selection D 100–500 mm."
    assert selection[3] == "View w −50–450 mm, u −100–100 mm."
    drawn = notes["sections"][1]["lines"]
    assert drawn[0].startswith("Local: every cell moved by −P₀ and rotated by its shower's R(θ, φ)")
    assert "k × k × k_z = 4 × 4 × 2" in drawn[0] and "20 mm grid" in drawn[0] and "never smoothed" in drawn[0]
    assert drawn[1].startswith("One half-width for all nine panels")
    assert drawn[2].startswith("Axes 1:1 (isometric), 300 mm half-width")
    disclosures = notes["sections"][2]["lines"]
    assert disclosures[0].startswith("One logarithmic ramp for all nine panels") and "1st percentile" in disclosures[0]
    assert disclosures[1] == "No populated bin of this panel lies below the ramp floor."
    assert disclosures[2] == "Every cell of the shower lies inside this panel's window."
    assert disclosures[3].startswith("Coordinates: the file’s own")
    legend = notes["sections"][3]["lines"]
    assert legend[0].startswith("Dashed line = the incident direction") and "✕ = the shower origin P₀" in legend[0]
    assert legend[1].startswith("Principal axis of the energy-weighted cloud in the local frame: 3.4° from +w over 310 cells")
    assert notes["hazards"] == []
    lab = event_results["notes"]["lab"]
    assert lab["title"] == "Original — detector coordinates (x, y, z): x–y"
    lab_disclosures = lab["sections"][2]["lines"]
    assert lab_disclosures[1] == "2 populated bins of this panel lie below the ramp floor and are drawn at the lowest colour."
    assert lab_disclosures[2].startswith("3.000e−4 GeV (2.44%) of the shower's 0.0123 GeV falls outside this panel's window")
    assert [s["heading"] for s in lab["sections"]] == ["Selection", "What is drawn", "Disclosures", "Marks and legend"]
    assert event_results["notes"]["missing"] is None


def test_event_hazards_are_structural(event_results):
    r = event_results
    assert r["hazards"]["fine"] == []
    assert r["hazards"]["bad"] == ["event outside the selection", "coordinate residual above tolerance",
                                   "coarsened grid", "principal axis untestable"]
    outside = r["outsideNotes"]
    assert outside["hazards"] == r["hazards"]["bad"]
    disclosures = outside["sections"][2]["lines"]
    assert any(line.startswith("Grids coarsened") for line in disclosures)
    assert any("outside the current selection" in line for line in disclosures)
    assert outside["sections"][3]["lines"][1].startswith("Principal axis: untestable below 3 populated cells")
    assert r["label"]["noAxis"].endswith("principal axis untestable (fewer than 3 cells).")
    assert r["label"]["none"] == ""
    assert r["selection"]["outside"].endswith("outside the current selection, drawn as asked; previous / next walk the selection.")


def test_the_frame_sentences_name_the_splat_and_the_depth(event_results):
    s = event_results["sentences"]
    assert s["lab"].startswith("Original detector coordinates: the native lattice, one bin per populated cell")
    assert "no entrance slab" in s["lab"] and "the detector's own sampling layers" in s["lab"]
    assert s["trans"].startswith("Translated only: every cell moved by −P₀ without rotation, its 48.27 × 48.60 mm footprint")
    assert "exact area-weighted box overlap" in s["trans"] and "counted from its first" in s["trans"]
    assert "48.27 × 48.60 mm × 20.5 mm footprint" in s["local"]


def test_the_event_figure_name_leads_with_the_event(event_results):
    names = event_results["names"]
    assert re.fullmatch(r"event-local-xy_ev1234A_D-100-500_native_local_\d{8}_\d{6}\.svg", names["local"]), names["local"]
    assert re.fullmatch(r"event-lab-xz_ev1234B_D-100-500_native_\d{8}_\d{6}\.png", names["lab"]), names["lab"]
    assert "_ev" not in names["ensemble"], "an ensemble figure names no event"


def test_no_event_sentence_carries_a_hyphen_minus(event_results):
    r = event_results
    texts = [r["label"]["full"], r["label"]["noAxis"], *r["selection"].values(), *r["sentences"].values()]
    for notes in (r["notes"]["local"], r["notes"]["lab"], r["outsideNotes"]):
        texts.extend(line for section in notes["sections"] for line in section["lines"])
    for text in texts:
        assert not re.search(r"(?<![\w-])-\d", text), text


# ------------------------------------------------- the windowed ensemble axis --

_WINDOW_SCRIPT = """
const [marksUrl, framesUrl, notesUrl] = JSON.parse(process.argv[1]);
const { insideWedge, customBand } = await import(marksUrl);
const fv = await import(framesUrl);
const { projectionNotes, notesLines } = await import(notesUrl);
const out = {};

const two = [[0, -1, 1], [100, -3, 3]];
const three = [[0, 0, 0], [50, -1, 1], [100, -5, 5]];
out.inside = {
  two: insideWedge(two, 50, 1.5), twoOut: insideWedge(two, 50, 2.5), twoEnd: insideWedge(two, 100, -3),
  three: insideWedge(three, 75, 2.9), threeOut: insideWedge(three, 75, 3.1), threeFirst: insideWedge(three, 25, 0.4),
  beyond: insideWedge(three, 120, 0), before: insideWedge(three, -1, 0), none: insideWedge(null, 0, 0),
  one: insideWedge([[0, -1, 1]], 0, 0),
};
// The band polygon walks the lower edge out and the upper edge back.
const band = customBand({ name: 'b', points: three, color: '#fff', opacity: 0.2 });
const shape = band.renderItem({}, { coord: (p) => p }).shape.points;
out.band = { silent: band.silent, points: shape };

const lab = (overlays) => ({
  slab: { note: 'Slab.' },
  panels: {
    xy: { scale: { unit: 'GeV', scale: 'log10', vmin: -6, vmax: 0, clipped_low: 0, clipped_high: 0 },
          axes: { col: { name: 'x', lo: -2600, hi: 2600 }, row: { name: 'y', lo: -2600, hi: 2600 } } },
    yz: { scale: { unit: 'GeV', scale: 'log10', vmin: -6, vmax: 0, clipped_low: 0, clipped_high: 0 },
          axes: { col: { name: 'z', lo: 3662, hi: 4873 }, row: { name: 'y', lo: -2600, hi: 2600 } } },
    xz: { scale: { unit: 'GeV', scale: 'log10', vmin: -6, vmax: 0, clipped_low: 0, clipped_high: 0 },
          axes: { col: { name: 'z', lo: 3662, hi: 4873 }, row: { name: 'x', lo: -2600, hi: 2600 } } },
  },
  overlays: { axes: {}, trajectories: [], coherence: { r_a: 0.012, r_b: 0.016 }, max_trajectory_events: 50, ...overlays },
  centroids: {}, selection: { n_events: 20268, n_hits: 24000000 },
  meta: { resolution: { mode: 'native', r_x: 212 }, stagger: { staggered: false }, exact: true, coord_system: 'lab' },
});
const pointing = {
  a: { n: 20268, mean_deg: -0.005, sd_deg: 1.799, source_z_mm: 3860, centroid_z_mm: 3892 },
  b: { n: 20268, mean_deg: 0.02, sd_deg: 1.8, source_z_mm: 3862, centroid_z_mm: 3890 },
  note: 'Incident directions point at the detector origin: against the radial line through each shower’s 3-D '
    + 'centroid the residual is A: −0.0° ± 1.8° SD over N = 20,268, r / tan θ = 3,860 mm against a centroid depth '
    + 'of 3,892 mm; B: +0.0° ± 1.8° SD over N = 20,268. The azimuth is uniform over the face only because the '
    + 'entry points are, so the showers entering one window share a direction: zoom a depth panel and the '
    + 'ensemble axis of the events entering its window is drawn.',
};
const payload = lab({ pointing });
out.lab = fv.labFootnotes(payload);
out.labFew = fv.labFootnotes(lab({ pointing, trajectories: [{ event: 1, a: {} }, { event: 2, a: {} }] })).xz;
out.legend = { many: fv.labLegend(payload), few: fv.labLegend(lab({ trajectories: [{ event: 1 }] })) };

const stations = [[3662, 1100, 1200], [3965, 1190, 1300], [4268, 1270, 1410], [4571, 1350, 1520], [4873, 1420, 1640]];
const windowAxis = {
  panel: 'xz', axis: 'x', window: [1000, 1300], z_front: 3662, depth_max: 4873, stations: 5, lean_ratio_min: 1,
  a: { n: 65, n_selection: 20268, anchor: { t: 1150, z: 3662, sd: 86, se95: 21 }, slope: 0.311, slope_sd: 0.023,
       se95: 0.0057, lean_ratio: 13.5, fan_deg: 1.5, resultant_azimuth: 0.7, rayleigh_p: 1e-12, faded: false, label: '',
       dof_note: null, axis: [[3662, 1150], [4873, 1526]], band: stations,
       envelope: stations.map(([z, lo, hi]) => [z, (lo + hi) / 2 - 3, (lo + hi) / 2 + 3]) },
  b: { n: 0, n_selection: 20268, axis: null, band: null, envelope: null, faded: false, label: '' },
  notes: ['Shower A: N = 65 of 20,268 selected events enter the window x ∈ [1000, 1300] mm; mean lean +0.3110 '
          + '± 0.0230 SD, fan ± 1.5°; lean / fan = 13.52 ≥ 1, drawn in full.',
          'Shower B: no selected event enters the window x ∈ [1000, 1300] mm; no axis is drawn.'],
  rule: 'Windowed ensemble axis: the selected events whose entry point lies in this panel’s displayed transverse window.',
};
const view = { col: [3662, 4873], row: [1000, 1300] };
const withAxis = projectionNotes({ payload, panelId: 'xz', isometric: {}, view, windowAxis });
const without = projectionNotes({ payload, panelId: 'xz', isometric: {}, view });
const entry = projectionNotes({ payload, panelId: 'xy', isometric: {}, view, windowAxis });
out.notes = {
  headings: withAxis.sections.map((s) => s.heading),
  legend: notesLines(withAxis, 'Marks and legend'),
  disclosures: notesLines(withAxis, 'Disclosures'),
  withoutLegend: notesLines(without, 'Marks and legend'),
  withoutDisclosures: notesLines(without, 'Disclosures'),
  entryHeadings: entry.sections.map((s) => s.heading),
};
out.windowLegend = { full: fv.windowAxisLegend(windowAxis), none: fv.windowAxisLegend(null) };
out.geometry = { full: fv.geometrySentence(pointing), none: fv.geometrySentence(null), noSd: fv.geometrySentence({ a: { n: 1 } }) };

// The D-frame depth panels state the geometry share of their band.
const fitAxis = (half) => ({ applied: true, range: [-half, half], half_width: half, floored: false });
const frame = { kind: 'canonical', n_events: 7, n_selected: 7, n_excluded_no_frame: 0, anchor_choice: 'backprojected',
  d_entry: { mean: 800, ci95_half: 40, n: 7 }, d_dataset: { mean: 820, ci95_half: 30 }, subsample_k: 2,
  footprint_mm: [48.3, 48.6], pitch_mm: 20, fit: { rule: 'symmetric', provisional: true, floor_mm: 200,
  percentiles: [0.1, 99.9], xy: { col: fitAxis(480), row: fitAxis(200), energy_fraction_outside: 0.002 },
  yz: { row: fitAxis(200), energy_fraction_outside: 0.001 }, xz: { row: fitAxis(480), energy_fraction_outside: 0.001 } },
  rho: { norm: 'selection', ref: { xy: 1e-6, depth: 2e-6 } }, reconstruction: { display: 'continuous', note: 'Kernel.' },
  comb: { note: 'No comb.', staggered: false }, notes: [], ensemble: {}, coherence: { r_a: 0.012 } };
const cpanel = (col, row, sc, sr) => ({ scale: { unit: 'a.u.', scale: 'log10', floor: 'transparent', floor_ratio: 1e-3 },
  rho_unit: 'GeV/mm^2/event', below_floor_cells: 3, energy_fraction_outside_window: 0.002,
  axes: { col: { name: col, symbol: sc, lo: -480, hi: 480 }, row: { name: row, symbol: sr, lo: -200, hi: 200 } } });
const canonical = { frame, panels: { xy: cpanel('x', 'y', 'x′', 'y′'), yz: cpanel('z', 'y', 'z′', 'y′'), xz: cpanel('z', 'x', 'z′', 'x′') },
  slab: { note: 'Slab.' }, centroids: {}, overlays: { pointing },
  meta: { resolution: { mode: 'continuous' }, exact: true, frame: 'canonical' }, selection: { n_events: 7, n_hits: 100 } };
out.canonical = { xz: fv.canonicalFootnotes(canonical, { isometric: {} }).xz,
  single: fv.canonicalFootnotes({ ...canonical, frame: { ...frame, n_events: 1 } }, { isometric: {} }).xz };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def window_results() -> dict:
    args = json.dumps([(JS / "panels" / "marks.js").as_uri(), (JS / "frame_views.js").as_uri(),
                       (JS / "panel_notes.js").as_uri()])
    done = subprocess.run([NODE, "--input-type=module", "-e", _WINDOW_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_band_of_several_stations_is_interpolated_between_them(window_results):
    r = window_results["inside"]
    assert r["two"] is True and r["twoOut"] is False and r["twoEnd"] is True
    assert r["three"] is True and r["threeOut"] is False and r["threeFirst"] is True
    assert r["beyond"] is False and r["before"] is False and r["none"] is False and r["one"] is False
    band = window_results["band"]
    assert band["silent"] is True
    assert band["points"] == [[0, 0], [50, -1], [100, -5], [100, 5], [50, 1], [0, 0]]


def test_the_absolute_frame_names_its_energy_centres_and_where_the_directions_point(window_results):
    lab = window_results["lab"]
    for panel in ("yz", "xz"):
        assert "centres of deposited energy per depth layer" in lab[panel]
        assert "a property of the summed picture, not a direction" in lab[panel]
        assert "No single averaged trajectory is drawn over the whole face" in lab[panel]
        assert "Incident directions point at the detector origin" in lab[panel]
        assert "zoom a depth panel" in lab[panel]
        assert "shower axes" not in lab[panel]
    assert "Incident directions point" not in lab["xy"]
    few = window_results["labFew"]
    assert "2 individual incident trajectories" in few and "centre of deposited energy is withheld" in few
    legend = window_results["legend"]
    assert legend["many"].startswith("Solid lines: the centre of deposited energy per depth layer")
    assert legend["few"].startswith("Dashed lines: the 1 individual incident trajectories")


def test_the_windowed_axis_joins_the_depth_panels_notes(window_results):
    notes = window_results["notes"]
    assert notes["headings"] == ["Selection", "What is drawn", "Disclosures", "Marks and legend"]
    assert notes["entryHeadings"] == ["Selection", "What is drawn", "Disclosures"], "the entry panel draws no axis"
    assert any(line.startswith("Shower A: N = 65 of 20,268 selected events enter the window") for line in notes["disclosures"])
    assert any(line.startswith("Shower B: no selected event enters the window") for line in notes["disclosures"])
    assert any(line.startswith("Windowed ensemble axis: the selected events") for line in notes["disclosures"])
    assert notes["legend"][0].startswith("Solid lines: the centre of deposited energy")
    assert notes["legend"][1].startswith("Windowed ensemble axis for x ∈ [1000, 1300] mm: dashed line = the mean incident trajectory")
    assert "two quantities, two marks" in notes["legend"][1] and "faded axis means the mean lean lies within the fan" in notes["legend"][1]
    assert notes["withoutLegend"] == [notes["legend"][0]]
    assert not any("window" in line for line in notes["withoutDisclosures"])
    assert window_results["windowLegend"]["none"] == ""


def test_the_d_frame_states_the_geometry_share_of_its_band(window_results):
    g = window_results["geometry"]
    assert g["full"].startswith(" Part of that spread is geometry: in detector coordinates the incident directions point at the origin (residual ±1.8° SD")
    assert g["none"] == "" and g["noSd"] == ""
    canonical = window_results["canonical"]
    assert "Part of that spread is geometry" in canonical["xz"]
    assert "Part of that spread is geometry" not in canonical["single"], "one event has no spread"


def test_no_windowed_axis_sentence_carries_a_hyphen_minus(window_results):
    r = window_results
    texts = [*r["lab"].values(), r["labFew"], *r["legend"].values(), r["windowLegend"]["full"], r["geometry"]["full"],
             *r["notes"]["legend"], *r["notes"]["disclosures"], r["canonical"]["xz"]]
    for text in texts:
        assert not re.search(r"(?<![\w-])-\d", text), text


# ------------------------------------------------ the entry-anchor explainer --

_EXPLAINER_SCRIPT = """
const [framesUrl, labelsUrl] = JSON.parse(process.argv[1]);
globalThis.window = { location: { hash: '', pathname: '/' }, history: { replaceState() {} } };
const { anchorExplainer } = await import(framesUrl);
const { CHOICE_LABELS } = await import(labelsUrl);
const residual = { a: { median: 46.4, p90: 133.4, over_footprint: 9620 },
  b: { median: 45.2, p90: 132.6, over_footprint: 9382 }, footprint_mm: 48.6, n: 20268 };
console.log(JSON.stringify({
  labels: CHOICE_LABELS.anchor.map((c) => c.label),
  measured: anchorExplainer({ anchor_choice: 'backprojected', anchor_residual: residual }, 'p0'),
  bare: anchorExplainer(null, null),
  payloadOnly: anchorExplainer({ anchor_choice: 'p0' }, null),
  bogus: anchorExplainer(null, 'centroid'),
}));
"""


@pytest.fixture(scope="module")
def explainer_results() -> dict:
    args = json.dumps([(JS / "frame_views.js").as_uri(), (JS / "labels.js").as_uri()])
    done = subprocess.run([NODE, "--input-type=module", "-e", _EXPLAINER_SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _blocks(explainer, heading_start):
    section = next(s for s in explainer["sections"] if s["heading"].startswith(heading_start))
    return section, [b["text"] for b in section["blocks"]]


def test_the_explainer_states_both_definitions_with_their_formulas(explainer_results):
    r = explainer_results["measured"]
    assert r["title"] == "Entry anchor of the D-frame"
    assert [s["heading"] for s in r["sections"]] == [
        "What the anchor sets", "Back-projected 3-D centroid (default)", "First-layer entry point P₀",
        "How far apart they land", "What switching changes"]
    # The headings are the sidebar's own labels for the two choices.
    back_label, p0_label = explainer_results["labels"]
    assert r["sections"][1]["heading"].startswith(back_label) and r["sections"][2]["heading"] == p0_label
    formulas = [b["text"] for s in r["sections"] for b in s["blocks"] if b["kind"] == "formula"]
    assert formulas == [
        "x′ = cos ψ · (x − m_x) + sin ψ · (y − m_y)\ny′ = −sin ψ · (x − m_x) + cos ψ · (y − m_y)",
        "entry = (c_x, c_y) − (c_z − z_f) · tan θ · (cos φ, sin φ)",
        "entry = P₀ − (z₀ − z_f) · tan θ · (cos φ, sin φ)",
    ]
    _, back = _blocks(r, "Back-projected")
    assert "energy-weighted 3-D centroid" in back[0] and "centroid_A/B_x, _y, _z" in back[0]
    assert "cells labelled A+B count with shower B" in back[0]
    assert "carried unchanged to the front face" in back[2]
    _, p0 = _blocks(r, "First-layer")
    assert "first populated layer" in p0[0] and "count for both showers" in p0[0] and "0.01 mm" in p0[0]
    _, changes = _blocks(r, "What switching")
    assert "does not change the selection, D on the slider" in changes[0]
    assert "closer than 80 mm" in changes[1] and "anchor=p0" in changes[1]


def test_the_explainer_quotes_the_measured_distance_when_it_has_one(explainer_results):
    _, measured = _blocks(explainer_results["measured"], "How far")
    assert measured[0] == (
        "On this selection the two entry points of a shower lie a median 46 mm apart for shower A and "
        "45 mm for shower B at the front face (90th percentile 133 and 133 mm). Of 20,268 events, 9,620 A "
        "showers and 9,382 B showers differ by more than one cell footprint (48.6 mm).")
    assert measured[1].startswith("The file records no true entry point")
    _, bare = _blocks(explainer_results["bare"], "How far")
    assert bare[0].endswith("printed in the entry panel’s Details drawer once the panels have loaded.")
    assert bare[1].startswith("The file records no true entry point")


def test_the_explainer_tags_the_definition_in_use(explainer_results):
    def tagged(explainer):
        return [s["heading"] for s in explainer["sections"] if s["current"]]
    r = explainer_results
    assert tagged(r["measured"]) == ["First-layer entry point P₀"], "the control's value wins"
    assert r["measured"]["current"] == "p0"
    assert tagged(r["bare"]) == ["Back-projected 3-D centroid (default)"]
    assert tagged(r["payloadOnly"]) == ["First-layer entry point P₀"]
    assert tagged(r["bogus"]) == ["Back-projected 3-D centroid (default)"]


def test_no_explainer_sentence_carries_a_hyphen_minus(explainer_results):
    for key in ("measured", "bare"):
        for section in explainer_results[key]["sections"]:
            for block in section["blocks"]:
                assert not re.search(r"(?<![\w-])-\d", block["text"]), block["text"]
                assert " - " not in block["text"], block["text"]
