"""The energy-resolution card's E max slider, E axis ticks and deposit gate (``res_axis.js``), executed under Node.

Martin's decisions of 2026-11-17: the E view opens at the data's top edge and
extends, in 5 GeV steps, to the server's axis end; the deposit is a card toggle,
off by default, except where it is the response's only series.

Pinned here:

* ``eMaxRange`` on the recorded two-shower response (``data_max_gev`` 18 GeV,
  so the slider runs 20-80 GeV) and on the single-shower response
  (``data_max_gev`` 20 GeV, 20-80 GeV); a response without ``data_max_gev``
  (the ends meet), one without ``axis.energy`` (null);
* ``eMaxOf``: null, undefined and NaN take the lower end; a value below or
  above the slider is clamped; an off-grid value snaps to the grid, a half
  step rounding up; a response without a slider gives null;
* ``eTickStep`` and ``eAxisTicks``: every 5 GeV up to 40 GeV, every 10 GeV
  above, the server's interval at its own end, an off-grid end ticked too;
* ``isDepositSeries``, ``hasModelSeries``, ``depositShown`` and
  ``depositForced`` on both responses: hidden when asked on the two-shower
  response, forced on the single-shower one, whose only series is the deposit.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import JS, NODE, PAYLOADS, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const ra = await import(`${jsRoot}/res_axis.js`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const two = load('res_scaling_median_two');
const single = load('res_scaling_median_single_events');
// A response with an axis end and no data edge, and one with no E axis at all.
const noEdge = { axis: { energy: { x: { min: 0, max: 80, interval: 10 } } }, series: two.series };
const noEnergy = { axis: { y: { min: 0, max: 30 } }, series: two.series };
const out = {
  constants: { step: ra.E_MAX_STEP_GEV, fine: ra.E_TICK_FINE_MAX_GEV },
  fixtures: {
    two: { x: two.axis.energy.x, dataMax: two.axis.energy.data_max_gev },
    single: { x: single.axis.energy.x, dataMax: single.axis.energy.data_max_gev },
  },
  range: {
    two: ra.eMaxRange(two), single: ra.eMaxRange(single), noEdge: ra.eMaxRange(noEdge),
    noEnergy: ra.eMaxRange(noEnergy), none: [ra.eMaxRange(null), ra.eMaxRange(undefined), ra.eMaxRange({})],
    nanMax: ra.eMaxRange({ axis: { energy: { x: { max: null }, data_max_gev: 18 } } }),
    // An edge at or beyond the axis end: the ends meet at the axis end. A tiny edge: never below one step.
    edgeBeyond: ra.eMaxRange({ axis: { energy: { x: { max: 80 }, data_max_gev: 93 } } }),
    edgeTiny: ra.eMaxRange({ axis: { energy: { x: { max: 80 }, data_max_gev: 0.5 } } }),
    edgeOnGrid: ra.eMaxRange({ axis: { energy: { x: { max: 80 }, data_max_gev: 25 } } }),
  },
  of: {
    lower: [null, undefined, Number.NaN, Number.POSITIVE_INFINITY].map((v) => ra.eMaxOf(two, v)),
    below: [ra.eMaxOf(two, 5), ra.eMaxOf(two, -10), ra.eMaxOf(two, 0)],
    above: [ra.eMaxOf(two, 95), ra.eMaxOf(two, 1e6), ra.eMaxOf(two, 80.0001)],
    onGrid: [20, 25, 40, 75, 80].map((v) => ra.eMaxOf(two, v)),
    snap: [22, 22.4, 22.5, 22.6, 27.49, 27.5, 77.5, 78].map((v) => [v, ra.eMaxOf(two, v)]),
    noEdge: [ra.eMaxOf(noEdge, null), ra.eMaxOf(noEdge, 40)],
    none: [ra.eMaxOf(null, 40), ra.eMaxOf(noEnergy, 40), ra.eMaxOf(undefined, null)],
  },
  ticks: {
    20: ra.eAxisTicks(20), 40: ra.eAxisTicks(40), 45: ra.eAxisTicks(45), 75: ra.eAxisTicks(75),
    server80: ra.eAxisTicks(80, 80, 10), server100: ra.eAxisTicks(100, 100, 10),
    // The slider below the server's end: the slider's own step, not the server's interval.
    belowServer: ra.eAxisTicks(60, 80, 10), fineBelowServer: ra.eAxisTicks(30, 80, 10),
    badServerInterval: ra.eAxisTicks(80, 80, 0),
  },
  step: {
    20: ra.eTickStep(20), 40: ra.eTickStep(40), 45: ra.eTickStep(45), 75: ra.eTickStep(75),
    server80: ra.eTickStep(80, 80, 10), server100: ra.eTickStep(100, 100, 10), server80by20: ra.eTickStep(80, 80, 20),
    belowServer: ra.eTickStep(30, 80, 10), badServerInterval: ra.eTickStep(80, 80, -5),
  },
  deposit: {
    isDeposit: two.series.map((s) => [s.key, ra.isDepositSeries(s)]),
    bySlot: [ra.isDepositSeries({ colour_slot: 'detector' }), ra.isDepositSeries({ source: null, colour_slot: 'detector' }),
      ra.isDepositSeries({ source: 'network', colour_slot: 'detector' }), ra.isDepositSeries({ colour_slot: 'absolute' }),
      ra.isDepositSeries(null), ra.isDepositSeries(undefined)],
    hasModel: { two: ra.hasModelSeries(two), single: ra.hasModelSeries(single), none: ra.hasModelSeries(null),
      empty: ra.hasModelSeries({ series: [] }) },
    shown: {
      two: [undefined, true, false].map((asked) => ra.depositShown(two, asked)),
      single: [undefined, true, false].map((asked) => ra.depositShown(single, asked)),
      // Only `false` asks to hide: anything else shows it.
      loose: [null, 0, '', 'off'].map((asked) => ra.depositShown(two, asked)),
    },
    forced: { two: ra.depositForced(two), single: ra.depositForced(single), empty: ra.depositForced({ series: [] }),
      none: ra.depositForced(null) },
    singleSeries: single.series.map((s) => [s.key, s.source ?? null, s.colour_slot ?? null]),
  },
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result() -> dict:
    return _run(_SCRIPT, [JS.as_uri(), str(PAYLOADS)])


def test_the_constants(result):
    assert result["constants"] == {"step": 5, "fine": 40}


def test_the_recorded_payloads_are_the_ones_described(result):
    """The two fixtures end the server's axis at 80 GeV, every 10 GeV; their data reach 18 and 20 GeV."""
    for key, data_max in (("two", 18), ("single", 20)):
        got = result["fixtures"][key]
        assert got["x"]["max"] == 80 and got["x"]["interval"] == 10, got
        assert got["dataMax"] == data_max, got


# ---------------------------------------------------------------- eMaxRange --


def test_the_slider_runs_from_the_data_edge_rounded_up_to_the_axis_end(result):
    got = result["range"]
    assert got["two"] == {"min": 20, "max": 80, "step": 5}
    assert got["single"] == {"min": 20, "max": 80, "step": 5}


def test_without_a_data_edge_the_slider_ends_meet(result):
    assert result["range"]["noEdge"] == {"min": 80, "max": 80, "step": 5}


def test_without_an_e_axis_there_is_no_slider(result):
    got = result["range"]
    assert got["noEnergy"] is None
    assert got["none"] == [None, None, None]
    assert got["nanMax"] is None


def test_the_lower_end_is_at_least_one_step_and_at_most_the_axis_end(result):
    got = result["range"]
    assert got["edgeBeyond"] == {"min": 80, "max": 80, "step": 5}
    assert got["edgeTiny"] == {"min": 5, "max": 80, "step": 5}
    assert got["edgeOnGrid"] == {"min": 25, "max": 80, "step": 5}


# ------------------------------------------------------------------- eMaxOf --


def test_a_value_that_is_no_number_takes_the_lower_end(result):
    # Any non-finite value, infinity included (the brief's rule): the slider's lower end, the data's top edge.
    assert result["of"]["lower"] == [20, 20, 20, 20]


def test_a_value_beyond_the_slider_is_clamped(result):
    got = result["of"]
    assert got["below"] == [20, 20, 20]
    assert got["above"] == [80, 80, 80]
    assert got["onGrid"] == [20, 25, 40, 75, 80]


def test_an_off_grid_value_snaps_to_the_grid_half_up(result):
    assert result["of"]["snap"] == [[22, 20], [22.4, 20], [22.5, 25], [22.6, 25], [27.49, 25], [27.5, 30],
                                    [77.5, 80], [78, 80]]


def test_eMaxOf_follows_the_range(result):
    got = result["of"]
    assert got["noEdge"] == [80, 80]
    assert got["none"] == [None, None, None]


# ----------------------------------------------------------- the E axis ticks --


def test_the_ticks_every_5_gev_to_40_and_every_10_above(result):
    got = result["ticks"]
    assert got["20"] == [0, 5, 10, 15, 20]
    assert got["40"] == [0, 5, 10, 15, 20, 25, 30, 35, 40]
    assert got["45"] == [0, 10, 20, 30, 40, 45]
    assert got["75"] == [0, 10, 20, 30, 40, 50, 60, 70, 75]


def test_the_servers_own_end_keeps_its_interval(result):
    got = result["ticks"]
    assert got["server80"] == [0, 10, 20, 30, 40, 50, 60, 70, 80]
    assert got["server100"] == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert got["belowServer"] == [0, 10, 20, 30, 40, 50, 60]
    assert got["fineBelowServer"] == [0, 5, 10, 15, 20, 25, 30]
    # A server interval that is no positive number is ignored.
    assert got["badServerInterval"] == [0, 10, 20, 30, 40, 50, 60, 70, 80]


def test_the_tick_step(result):
    got = result["step"]
    assert (got["20"], got["40"], got["45"], got["75"]) == (5, 5, 10, 10)
    assert (got["server80"], got["server100"], got["server80by20"]) == (10, 10, 20)
    assert got["belowServer"] == 5
    assert got["badServerInterval"] == 10


# ------------------------------------------------------------- the deposit gate --


def test_which_series_is_the_deposit(result):
    got = result["deposit"]
    assert got["isDeposit"] == [["detector:a", True], ["network:a", False], ["detector:b", True], ["network:b", False]]
    # No source: the colour slot decides; a source decides over the slot.
    assert got["bySlot"] == [True, True, False, False, False, False]


def test_model_series(result):
    assert result["deposit"]["hasModel"] == {"two": True, "single": False, "none": False, "empty": False}


def test_the_deposit_hides_when_asked_on_the_two_shower_response(result):
    got = result["deposit"]
    assert got["shown"]["two"] == [True, True, False]
    assert got["shown"]["loose"] == [True, True, True, True]
    assert got["forced"]["two"] is False


def test_the_deposit_is_forced_where_it_is_the_only_series(result):
    got = result["deposit"]
    assert got["singleSeries"] == [["detector:a", "detector", "detector"]]
    assert got["shown"]["single"] == [True, True, True]
    assert got["forced"]["single"] is True
    # No series at all: nothing to force.
    assert got["forced"]["empty"] is False and got["forced"]["none"] is False
