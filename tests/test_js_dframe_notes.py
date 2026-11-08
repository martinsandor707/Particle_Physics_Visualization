"""The D-frame's ill-conditioning chip, its hazards and its Details-drawer sentences.

One Node script runs `frame_views.js` (`entryTag`, `windowPhrase`,
`canonicalFootnotes`) and `panel_notes.js` (`hazards`, `projectionNotes`) on
the recorded canonical fixture with the server's `ill_conditioned_*` and
`fit.*.cap` fields injected, as the live service sends them for the electron
and muon two-shower datasets. Skipped without `node`.
"""

from __future__ import annotations

import json
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

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")

_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixture] = JSON.parse(process.argv.at(-1));
const fv = await import(`${jsRoot}/frame_views.js`);
const pn = await import(`${jsRoot}/panel_notes.js`);
const clone = (o) => JSON.parse(JSON.stringify(o));
const base = JSON.parse(fs.readFileSync(fixture, 'utf8'));

const ELECTRON = { n_events: 19998, n_ill_conditioned: 19326, ill_conditioned_threshold_mm: 80,
  ill_conditioned_share: 19326 / 19998, ill_conditioned_majority: true };
const withFrame = (extra, mutate) => {
  const p = clone(base);
  Object.assign(p.frame, extra);
  if (mutate) mutate(p);
  return p;
};
const entryOf = (p) => ({ ...p.frame, d_entry: { mean: 58, ci95_half: 3, n: p.frame.n_events } });
const electron = withFrame(ELECTRON);
const minority = withFrame({ ...ELECTRON, n_ill_conditioned: 5000, ill_conditioned_share: 5000 / 19998,
  ill_conditioned_majority: false });
const legacy = withFrame({ n_events: 19998, n_ill_conditioned: 19326 });   // an older payload: no new fields

const CAP_XY = { rule: 'drawn_extent', applied: true, percentile_half_width: 1740, drawn_half_width: 186,
  reach_mm: 20, limit: 220, gap_mm: 48.6, floor_ratio: 0.001, rho_ref: 7.26e-5,
  outside: { bins: 0, energy_fraction: 0, sides: [] } };
const ISLANDS = { bins: 2, energy_fraction: 0.00012,
  sides: [{ side: 1, bins: 2, energy_fraction: 0.00012, range: [1260, 1300], at: 4 }] };
const NEG_ISLANDS = { bins: 3, energy_fraction: 0.0031,
  sides: [{ side: -1, bins: 1, energy_fraction: 0.001, range: [-1300, -1260], at: 4 },
          { side: 1, bins: 2, energy_fraction: 0.0021, range: [1260, 1300], at: 4 }] };
const capped = (outside, cap = {}) => withFrame({}, (p) => {
  const fit = p.frame.fit;
  fit.xy.col.range = [-200, 200]; fit.xy.col.half_width = 200;
  fit.xz = fit.xz || {}; fit.xz.row = { ...(fit.xz.row || {}), applied: true, range: [-200, 200], half_width: 200 };
  fit.xy.col.cap = { ...CAP_XY, ...cap, outside };
  fit.xz.row.cap = { ...CAP_XY, ...cap, outside };
});

const out = {};
out.tag = {
  electron: fv.entryTag(entryOf(electron)),
  minority: fv.entryTag(entryOf(minority)),
  legacy: fv.entryTag(entryOf(legacy)),
  single: fv.entryTag({ ...entryOf(electron), n_events: 1, d_entry: { mean: 58, n: 1 } }),
  noCi: fv.entryTag({ ...entryOf(electron), d_entry: { mean: 58, n: 19998 } }),
  nearAll: fv.entryTag({ ...entryOf(electron), n_events: 2000, n_ill_conditioned: 1999,
    ill_conditioned_share: 0.9995 }),
  empty: fv.entryTag({ ...electron.frame, n_events: 0 }),
};

const hz = (p, id) => pn.hazards(p, id);
out.hazards = {};
for (const [name, p] of Object.entries({
  base, electron, minority, legacy,
  islandsXy: capped(ISLANDS), islandsNone: capped({ bins: 0, energy_fraction: 0, sides: [] }),
  both: withFrame(ELECTRON, (q) => {
    q.frame.fit.xy.col.cap = { ...CAP_XY, outside: ISLANDS };
    q.frame.fit.xz = { row: { applied: true, range: [-200, 200], half_width: 200, cap: { ...CAP_XY, outside: ISLANDS } } };
  }),
  trans: withFrame({ ...ELECTRON, kind: 'trans' }),
})) {
  out.hazards[name] = Object.fromEntries(['xy', 'yz', 'xz'].map((id) => [id, hz(p, id)]));
}
// Per-shower frame carrying a cap anyway: hazards unchanged.
out.hazards.transCap = hz(withFrame({ kind: 'trans' }, (p) => { p.frame.fit.xy.col.cap = { ...CAP_XY, outside: ISLANDS }; }), 'xy');

const phrase = (p, id, sides) => fv.windowPhrase(p.frame.fit, id, sides);
const XY = [['col', 'D'], ['row', 'y′']];
out.phrase = {
  none: phrase(base, 'xy', XY),
  capNull: phrase(withFrame({}, (p) => { p.frame.fit.xy.col.cap = null; }), 'xy', XY),
  notApplied: phrase(capped({ bins: 0, energy_fraction: 0, sides: [] }, { applied: false }), 'xy', XY),
  applied: phrase(capped({ bins: 0, energy_fraction: 0, sides: [] }), 'xy', XY),
  islands: phrase(capped(ISLANDS), 'xy', XY),
  negIslands: phrase(capped(NEG_ISLANDS), 'xy', XY),
  xz: phrase(capped(ISLANDS), 'xz', [['row', 'x′']]),
};

const notesOf = (p, id) => {
  const n = pn.projectionNotes({ payload: p, panelId: id, isometric: {}, experiment: { display_name: 'Demo' } });
  return n.sections.flatMap((s) => s.lines).join(' ');
};
out.notes = {};
for (const [name, p] of Object.entries({
  base, electron, minority, legacy, islands: capped(ISLANDS),
  both: withFrame(ELECTRON, (q) => { q.frame.fit.xy.col.cap = { ...CAP_XY, outside: ISLANDS }; }),
})) {
  out.notes[name] = Object.fromEntries(['xy', 'yz', 'xz'].map((id) => [id, notesOf(p, id)]));
}
out.detailsHazard = pn.projectionNotes({ payload: electron, panelId: 'yz', isometric: {} }).hazards;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def results() -> dict:
    args = json.dumps([JS.as_uri(), str(FIXTURES / "projections_base_canonical.json")])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


ELECTRON_CHIP = '<span class="tag-warn" title="'
ELECTRON_TITLE = (
    "19,326 of 19,998 events (96.6%) enter closer than 80 mm apart: their A→B direction is set by "
    "the anchor uncertainty, so this frame cannot separate their showers and draws them superimposed "
    "about the origin. Ill-conditioning is judged on the entry separation D_entry; raising D’s lower "
    "bound (the 3-D centroid distance) selects better-separated pairs."
)


# ------------------------------------------------------------------ the chip


def test_the_chip_follows_the_entry_text_only_with_the_majority_flag(results):
    tag = results["tag"]
    assert tag["electron"].startswith("⟨D<sub>entry</sub>⟩ 58 ± 3 mm (95% t, N = 19,998) · ")
    assert tag["electron"].endswith(">97% enter &lt; 80 mm apart</span>")
    assert f'{ELECTRON_CHIP}{ELECTRON_TITLE}">' in tag["electron"]
    for name in ("minority", "legacy", "empty"):
        assert "tag-warn" not in tag[name], name


def test_the_chip_follows_a_single_event_and_an_unbounded_interval(results):
    assert results["tag"]["single"].startswith("⟨D<sub>entry</sub>⟩ 58 mm (single event) · <span")
    assert results["tag"]["noCi"].startswith("⟨D<sub>entry</sub>⟩ 58 mm (N = 19,998) · <span")


def test_the_share_takes_a_decimal_where_a_whole_percent_would_say_all(results):
    near = results["tag"]["nearAll"]
    assert ">99.9% enter &lt; 80 mm apart<" in near and "(99.9%)" in near
    assert "100" not in re.sub(r"[\d,]*2,000", "", near)


def test_the_chip_is_well_formed_html(results):
    """The title attribute holds no raw markup, and the visible text writes its < as an entity."""
    chip = results["tag"]["electron"]
    title = re.search(r'title="([^"]*)"', chip).group(1)
    assert "<" not in title and ">" not in title
    assert chip.count('title="') == 1 and chip.count("<span") == 1 and chip.count("</span>") == 1
    assert chip.endswith("&lt; 80 mm apart</span>")


# ------------------------------------------------------------------- hazards


def test_the_ill_conditioned_hazard_is_on_the_three_spatial_panels_only_with_the_flag(results):
    h = results["hazards"]
    for panel in ("xy", "yz", "xz"):
        assert "mostly ill-conditioned frame" in h["electron"][panel]
        assert "mostly ill-conditioned frame" not in h["minority"][panel]
        assert "mostly ill-conditioned frame" not in h["legacy"][panel]
        assert "mostly ill-conditioned frame" not in h["base"][panel]
        assert "mostly ill-conditioned frame" not in h["trans"][panel]


def test_the_beyond_window_hazard_is_per_axis_and_needs_drawn_bins(results):
    h = results["hazards"]
    assert "drawn bins beyond the window" in h["islandsXy"]["xy"]
    assert "drawn bins beyond the window" in h["islandsXy"]["xz"]
    assert "drawn bins beyond the window" not in h["islandsXy"]["yz"]
    assert all("drawn bins beyond the window" not in v for v in h["islandsNone"].values())
    assert h["both"]["xy"] == [*h["base"]["xy"], "mostly ill-conditioned frame", "drawn bins beyond the window"]
    assert "drawn bins beyond the window" not in h["both"]["yz"]
    assert results["hazards"]["transCap"] == h["base"]["xy"]


def test_the_drawer_carries_the_hazard(results):
    assert results["detailsHazard"] == [*results["hazards"]["base"]["yz"], "mostly ill-conditioned frame"]


# --------------------------------------------------------------- the window


def test_a_window_without_a_cap_reads_as_before(results):
    p = results["phrase"]
    assert p["none"].startswith("Window D ±")
    assert "capped" not in p["none"] and "beyond" not in p["none"]
    assert p["capNull"] == p["none"]
    assert "capped" not in p["capNull"]
    assert "capped" not in p["notApplied"] and "beyond" not in p["notApplied"]


def test_an_applied_cap_names_the_drawn_extent_the_reach_and_the_percentile_rule(results):
    applied = results["phrase"]["applied"]
    assert "D capped at the drawn field’s extent (±186 mm drawn plus the 20 mm kernel reach, snapped to ±200 mm)" in applied
    assert "below the ±1,740 mm the percentile rule gives" in applied
    assert "because beyond it nothing is drawn at 10⁻³ of ρ_ref" in applied
    assert applied.startswith("Window D ±200 mm, y′ ±")
    assert "drawn bin" not in applied


def test_islands_beyond_the_window_are_counted_placed_and_marked(results):
    islands = results["phrase"]["islands"]
    assert islands.endswith(", with 2 drawn bins (0.012% of the panel’s energy) beyond it at x′ 1,260 to 1,300 mm, "
                            "marked at the window edge")
    assert results["phrase"]["xz"].startswith("Window x′ ±200 mm")


def test_negative_islands_use_the_true_minus_sign_and_both_sides(results):
    text = results["phrase"]["negIslands"]
    assert "3 drawn bins (0.310% of the panel’s energy)" in text
    assert "at x′ −1,300 to −1,260 mm and 1,260 to 1,300 mm" in text
    assert not HYPHEN_NUMBER.search(text)


# ------------------------------------------------------------------- drawers


def test_the_ill_sentence_states_the_share(results):
    for panel in ("xy",):
        text = results["notes"]["electron"][panel]
        assert "19,326 of 19,998 events (96.6%) enter closer than 80 mm apart, so their orientation is effectively random" in text
    minority = results["notes"]["minority"]["xy"]
    assert "5,000 of 19,998 events (25.0%) enter closer than 80 mm apart, so their orientation" in minority
    assert "Most of the selection is ill-conditioned" not in minority


def test_the_majority_sentence_is_in_the_entry_drawer_and_the_depth_drawers_say_what_it_does_to_the_axes(results):
    electron = results["notes"]["electron"]
    assert ("Most of the selection is ill-conditioned (judged on D_entry), so the panels show the showers "
            "superimposed about the origin rather than separated") in electron["xy"]
    assert "need not remove every ill-conditioned event" in electron["xy"]
    for panel in ("yz", "xz"):
        assert ("Most of the selection (96.6%) is ill-conditioned (D_entry < 80 mm): the two ensemble axes and "
                "their wedges are then dominated by randomly oriented directions.") in electron[panel]
    assert "dominated by randomly oriented directions" not in electron["xy"]
    for name in ("base", "minority"):
        for panel in ("xy", "yz", "xz"):
            assert "Most of the selection" not in results["notes"][name][panel], (name, panel)
            assert "dominated by randomly" not in results["notes"][name][panel]


def test_the_cap_reaches_the_entry_and_lateral_drawers_only(results):
    islands = results["notes"]["islands"]
    assert "capped at the drawn field’s extent" in islands["xy"] and "capped at the drawn field’s extent" in islands["xz"]
    assert "capped at the drawn field’s extent" not in islands["yz"]
    assert "marked at the window edge" in islands["xy"]


def test_an_older_payload_reads_as_before(results):
    legacy = results["notes"]["legacy"]["xy"]
    assert "19,326 of 19,998 events" in legacy  # the count is computed from n_ill_conditioned / n_events
    assert "Most of the selection" not in legacy


def test_no_new_sentence_carries_a_hyphen_minus(results):
    for panels in results["notes"].values():
        for text in panels.values():
            assert not HYPHEN_NUMBER.search(text)
