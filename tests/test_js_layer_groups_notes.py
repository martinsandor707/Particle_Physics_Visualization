"""The Details drawers of the depth panels: the Z convention and the Longitudinal Channels.

One Node script builds the drawers (`panel_notes.js` `projectionNotes`,
`eventNotes`, `profileNotes`; `voxel_notes.js` `voxelProjectionNotes` and the
3-D notes) on the recorded fixtures, with specs from `layer_groups.js`
`panelGroupSpec`, and dumps their sections. Each test then reads one sentence
family. Every number a sentence quotes is recomputed here from the fixture.
Skipped without `node`.
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

#: An ASCII hyphen signing a number: every rendered negative must use U+2212.
HYPHEN_NUMBER = re.compile(r"(?<![\w])-(?=[\d.∞])")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


_SCRIPT = r"""
import fs from 'node:fs';

const [jsRoot, fixtureDir] = JSON.parse(process.argv.at(-1));
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const lg = await imp('layer_groups.js');
const pn = await imp('panel_notes.js');
const vn = await imp('voxel_notes.js');
const fv = await imp('frame_views.js');

const dump = (notes) => (notes ? { title: notes.title, hazards: notes.hazards,
  sections: Object.fromEntries(notes.sections.map((s) => [s.heading, s.lines])) } : null);

const out = {};

/* ---- ensemble projections ---- */
const proj = (name) => load(name);
const spec = (payload, panelId, mode, counts, extra = {}) => lg.panelGroupSpec({
  mode, counts, panelId, depthLayers: payload.depth_layers, nEvents: payload.selection?.n_events ?? null, ...extra });
const notes = (payload, panelId, layerGroups, extra = {}) => dump(pn.projectionNotes({
  payload, panelId, layerGroups, ...extra }));

const lab = proj('projections_base_lab');
const L = lab.depth_layers.partition_layers;
const uniform = lg.uniformCounts(L);
out.L = L;
out.uniform = uniform;
out.lab_off = { yz: notes(lab, 'yz', null), xz: notes(lab, 'xz', null), xy: notes(lab, 'xy', null) };
out.lab_bounds = notes(lab, 'yz', spec(lab, 'yz', 'bounds', uniform));
out.lab_bounds_hidden = notes(lab, 'yz', spec(lab, 'yz', 'bounds', uniform), { marksShown: false });
out.lab_bounds_spec = { seams: spec(lab, 'yz', 'bounds', uniform).seams.length };
out.lab_xy_with_spec = notes(lab, 'xy', spec(lab, 'yz', 'bounds', uniform));

const pooled = proj('projections_base_lab_pooled');
const pc = pooled.depth_layers.groups.counts;
out.pooled_counts = pc;
out.lab_pooled = notes(pooled, 'yz', spec(pooled, 'yz', 'pool', pc));
const draftCounts = lg.setGroupEnd(pc, 1, pc[0] + 1).counts;
out.draft_counts = draftCounts;
out.lab_draft = notes(pooled, 'yz', spec(pooled, 'yz', 'pool', draftCounts));
out.lab_pool_not_arrived = notes(lab, 'yz', spec(lab, 'yz', 'pool', uniform));

const trans = proj('projections_base_trans');
out.trans = notes(trans, 'yz', spec(trans, 'yz', 'bounds', lg.uniformCounts(trans.depth_layers.partition_layers)));
out.trans_off = notes(trans, 'yz', null);
const canon = proj('projections_base_canonical');
out.canon = notes(canon, 'yz', spec(canon, 'yz', 'bounds', lg.uniformCounts(canon.depth_layers.partition_layers)));
out.canon_off = notes(canon, 'xz', null);
const local = proj('projections_single_local');
out.local = notes(local, 'yz', spec(local, 'yz', 'bounds', null));
out.local_xy = notes(local, 'xy', null);

/* ---- one event ---- */
const ev = load('event_raster_base');
const cEvent = lg.uniformCounts(ev.frames.lab.n_layers === 56 ? 56 : 56);
const evSpecs = {};
for (const kind of ['lab', 'trans', 'local']) {
  evSpecs[kind] = {};
  for (const panelId of ['yz', 'xz']) {
    evSpecs[kind][panelId] = lg.panelGroupSpec({
      mode: 'bounds', counts: cEvent, panelId, layerPlanes: ev.frames[kind].layer_planes, nEvents: 1 });
  }
}
out.event = {};
for (const kind of ['lab', 'trans', 'local']) {
  out.event[kind] = {};
  for (const panelId of ['xy', 'yz', 'xz']) {
    out.event[kind][panelId] = dump(pn.eventNotes({ payload: ev, kind, panelId, layerGroups: evSpecs }));
  }
}
out.event_off = dump(pn.eventNotes({ payload: ev, kind: 'lab', panelId: 'yz' }));
out.event_marks_hidden = dump(pn.eventNotes({ payload: ev, kind: 'lab', panelId: 'yz', layerGroups: evSpecs, marksShown: false }));
out.event_tilt = ev.frames.local.layer_planes.tilt;
out.event_edges = ev.frames.lab.layer_planes.edges_mm.slice(0, 2);

/* ---- C7 ---- */
const native = load('profiles_single_native');
const w = load('profiles_single_w');
out.profile_native_off = dump(pn.profileNotes({ payload: native, axis: 'kt' }));
const nativeBlock = { ...clone(trans.depth_layers), reach: native.depth_layers.reach };
const nativeSpec = lg.panelGroupSpec({ mode: 'bounds', counts: lg.uniformCounts(56), panelId: 'yz', depthLayers: nativeBlock });
out.profile_native = dump(pn.profileNotes({ payload: native, axis: 'kt', layerGroups: nativeSpec }));
const wSpec = lg.panelGroupSpec({ mode: 'bounds', counts: null, panelId: 'yz', depthLayers: w.depth_layers });
out.profile_w_off = dump(pn.profileNotes({ payload: w, axis: 'w' }));
out.profile_w = dump(pn.profileNotes({ payload: w, axis: 'w', layerGroups: wSpec }));

/* ---- the Models page's paired projections and 3-D cards ---- */
out.pair_event = dump(vn.voxelProjectionNotes({
  pair: 'event', payload: ev, panelId: 'yz', frameKind: 'lab', layerGroups: evSpecs.lab.yz, pairing: ['PAIR'] }));
out.pair_event_xy = dump(vn.voxelProjectionNotes({
  pair: 'event', payload: ev, panelId: 'xy', frameKind: 'lab', layerGroups: evSpecs.lab.yz }));
out.pair_event_map = dump(vn.voxelProjectionNotes({
  pair: 'event', payload: ev, panelId: 'yz', frameKind: 'lab', layerGroups: evSpecs }));
out.pair_event_none = dump(vn.voxelProjectionNotes({ pair: 'event', payload: ev, panelId: 'yz', frameKind: 'lab' }));
out.pair_ensemble = dump(vn.voxelProjectionNotes({
  pair: 'ensemble', payload: lab, panelId: 'xz', layerGroups: spec(lab, 'xz', 'bounds', uniform) }));
out.vox_lab = dump(vn.voxelEventNotes({ payload: load('event_voxels_base_lab') }));
out.vox_canonical = dump(vn.voxelEventNotes({ payload: load('event_voxels_base_canonical') }));
out.z_line = [vn.zAxisLine('lab', 'z'), vn.zAxisLine('canonical', 'z′'), vn.zAxisLine('lab', 'w')];

/* ---- captions ---- */
out.captions = {
  lab: fv.labFootnotes(lab),
  eventLab: fv.eventFrameSentence(ev, 'lab'),
  eventTrans: fv.eventFrameSentence(ev, 'trans'),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    run = subprocess.run(
        [NODE, "--input-type=module", "-e", _SCRIPT, json.dumps([JS.as_posix(), FIXTURES.as_posix()])],
        capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _sec(notes: dict, heading: str) -> list[str]:
    return notes["sections"].get(heading, [])


def _text(notes: dict, heading: str | None = None) -> str:
    if heading:
        return " ".join(_sec(notes, heading))
    return " ".join(line for lines in notes["sections"].values() for line in lines)


def _walk(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    elif isinstance(value, str):
        yield value


# ------------------------------------------------------------------ Z ------


@pytest.mark.parametrize("panel", ["yz", "xz"])
def test_the_absolute_depth_panels_state_the_z_convention_without_channels(out, panel):
    lab = _fixture("projections_base_lab")["depth_layers"]
    edges, offset = lab["edges_mm"], lab["display_offset_mm"]
    centre = (edges[0] + edges[1]) / 2
    drawn = _text(out["lab_off"][panel], "What is drawn")
    assert f"Depth is labelled Z = z − {offset:.0f} mm" in drawn
    assert "producer's core.SHIFT_Z display offset" in drawn
    assert "a label on the detector's raw z" in drawn and "stay raw z" in drawn
    assert f"first layer's centre is at Z = {centre - offset:.1f} mm (z = {centre:.1f} mm)" in drawn
    assert f"upstream cell edge at Z = {edges[0] - offset:.2f} mm (z = {edges[0]:.2f} mm)" in drawn
    # An ensemble axis starts at Z = 0: the empty sliver before the first cell edge is named.
    assert f"Z = 0 to {edges[0] - offset:.2f} mm" in drawn
    # No channel sentence without a partition.
    assert "Longitudinal" not in _text(out["lab_off"][panel]) and "Seams are" not in drawn


def test_the_entry_panel_has_no_depth_sentences(out):
    assert "Depth is labelled" not in _text(out["lab_off"]["xy"])
    assert "Depth is labelled" not in _text(out["lab_xy_with_spec"])
    assert "contiguous channels" not in _text(out["lab_xy_with_spec"])


def test_the_z_sentence_is_the_same_with_and_without_a_partition(out):
    off = _sec(out["lab_off"]["yz"], "What is drawn")
    on = _sec(out["lab_bounds"], "What is drawn")
    for line in off[1:]:
        assert line in on


def test_the_d_frame_keeps_z_prime_and_states_its_offset_from_z(out):
    canon = _fixture("projections_base_canonical")
    zf = canon["frame"]["z_front_mm"]
    drawn = _text(out["canon_off"], "What is drawn")
    assert f"z′ = z − z_f, with z_f = {zf:.1f} mm, the first layer's centre" in drawn
    assert f"z′ = Z − {zf - 3649:.1f} mm" in drawn
    assert "Depth is labelled Z" not in drawn


def test_relative_frames_have_no_z_sentence(out):
    assert "Depth is labelled" not in _text(out["trans_off"])
    assert "Depth is labelled" not in _text(out["local"])


# ------------------------------------------------------------ channels ----


def test_what_is_drawn_names_the_strip_the_seams_and_the_detector_numbering(out):
    counts = out["uniform"]
    drawn = _text(out["lab_bounds"], "What is drawn")
    assert f"The {sum(counts)} layers are cut into 13 contiguous channels" in drawn
    assert "Channels are Ch 1–13, numbered by detector layer ordinal" in drawn
    assert "band reserved above the plot, outside the raster and never over it" in drawn
    assert "stored cell edges" in drawn and "clipped to the visible depth range under zoom" in drawn
    assert f"Seams are {out['lab_bounds_spec']['seams']} dashed 1 px lines" in drawn
    assert "never at an index times the pitch" in drawn
    first = counts[0]
    assert f"layers 1–{first}, {first + 1}–" in drawn


def test_disclosures_state_the_share_basis_and_the_energy_off_the_axis(out):
    lab = _fixture("projections_base_lab")
    n = lab["selection"]["n_events"]
    total = lab["depth_layers"]["profile"]["total_gev"]
    text = _text(out["lab_bounds"], "Disclosures")
    assert "exact per-layer sums of the selection's energy on the depth axis" in text
    assert f"over N = {n} events" in text
    assert f"{total:.3g} GeV in all" in text
    assert "no energy falls off the depth axis" in text


def test_the_share_basis_counts_the_energy_off_the_axis_when_there_is_some(out):
    trans = _fixture("projections_base_trans")["depth_layers"]
    outside = trans["profile"]["outside_gev"]
    assert outside > 0
    text = _text(out["trans"], "Disclosures")
    assert "that falls off the depth axis is counted in the total" in text
    mantissa, exp = f"{outside:.2e}".split("e")
    assert f"{mantissa}e−{abs(int(exp))} GeV" in text


def test_a_gapped_lattice_says_its_layer_numbers_are_ordinals(out):
    lab = _fixture("projections_base_lab")["depth_layers"]
    assert lab["contiguous"] is False
    text = _text(out["lab_bounds"], "Disclosures")
    assert f"layer numbers are the lattice's ordinals (1–{lab['partition_layers']}), not physical layer slots" in text
    # The contiguous trans lattice does not.
    assert "ordinals" not in _text(out["trans"], "Disclosures")


def test_relative_frames_are_numbered_from_each_showers_first_layer_with_reach(out):
    reach = _fixture("projections_base_trans")["depth_layers"]["reach"]
    drawn = _text(out["trans"], "What is drawn")
    assert "Rel Ch 1–13: layers are counted from each shower's own first populated layer" in drawn
    text = _text(out["trans"], "Disclosures")
    assert f"first populated layer s ≤ {reach['l_phys']} − 1 − k" in text
    assert "every present shower of the selection" in text
    assert f"{reach['n_showers']} showers" in text
    n_layers = len(reach["counts"])
    last = reach["counts"][-1]
    assert f"Relative layer {n_layers} is reached by {last} of {reach['n_showers']}" in text


def test_the_d_frame_is_numbered_by_hardware_layers_with_no_reach(out):
    drawn = _text(out["canon"], "What is drawn")
    assert "its channels are the detector's own hardware layers (Ch 1–13, by detector ordinal), not relative ones" in drawn
    assert "Reach:" not in _text(out["canon"], "Disclosures")
    assert "Rel Ch" not in drawn


def test_pooled_depth_bins_are_channels_carrying_gev_per_layer_in_the_absolute_frame(out):
    pooled = _fixture("projections_base_lab_pooled")["depth_layers"]
    drawn = _text(out["lab_pooled"], "What is drawn")
    assert f"Pooled: each depth bin is one channel ({len(pooled['groups']['counts'])} bins)" in drawn
    assert f"a channel's summed energy per {pooled['pitch_mm']:.1f} mm layer (GeV" in drawn
    assert "so a wide channel never reads as a dense one" in drawn
    assert "channel's total energy and layer count are in its strip tooltip" in drawn
    assert "Seams are not drawn, because they coincide with the bin edges" in drawn
    assert "dashed 1 px lines" not in drawn
    assert "Seams" not in _text(out["lab_pooled"], "Marks and legend").split("Strip:")[0]


def test_pooled_co_registered_frames_carry_the_mean_density_of_their_layers():
    # The sentence is chosen by the frame's symbol and offset, which a pooled trans response carries.
    script = r"""
import fs from 'node:fs';
const [jsRoot, dir] = JSON.parse(process.argv.at(-1));
const lg = await import(`${jsRoot}/layer_groups.js`);
const pn = await import(`${jsRoot}/panel_notes.js`);
const p = JSON.parse(fs.readFileSync(`${dir}/projections_base_trans_pooled.json`, 'utf8'));
const counts = p.depth_layers.groups.counts;
const spec = lg.panelGroupSpec({ mode: 'pool', counts, panelId: 'yz', depthLayers: p.depth_layers });
const n = pn.projectionNotes({ payload: p, panelId: 'yz', layerGroups: spec });
console.log(JSON.stringify(n.sections.find((s) => s.heading === 'What is drawn').lines));
"""
    run = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps([JS.as_posix(), FIXTURES.as_posix()])],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    text = " ".join(json.loads(run.stdout))
    assert "carrying the mean density of the channel's layers" in text
    assert "GeV, the sum scaled" not in text


def test_a_live_draft_while_pooled_is_boundaries_over_the_pooled_picture(out):
    pooled = _fixture("projections_base_lab_pooled")["depth_layers"]["groups"]["counts"]
    text = _text(out["lab_draft"], "Disclosures")
    assert f"the raster in hand is pooled by {'.'.join(map(str, pooled))}" in text
    assert "boundaries over that picture until Apply, which sends one request" in text
    # Seams are drawn for a draft, so the drawn section names them.
    assert "dashed 1 px lines" in _text(out["lab_draft"], "What is drawn")
    # The applied partition is not a draft.
    assert "until Apply" not in _text(out["lab_pooled"], "Disclosures")
    # Before the pooled response arrives the raster is not pooled.
    assert "the raster in hand is not pooled" in _text(out["lab_pool_not_arrived"], "Disclosures")


def test_marks_and_legend_name_the_strip_seams_and_spotlight_and_the_marks_toggle(out):
    legend = _text(out["lab_bounds"], "Marks and legend")
    assert "Strip: alternating fills" in legend
    assert "Seams: dashed lines between channels" in legend
    assert "Spotlight: hovering a channel draws its two faces as solid lines on every linked depth panel, never a fill" in legend
    assert "The Marks toggle hides the seams and the spotlight; the strip, which lies outside the plot, stays." in legend
    hidden = _text(out["lab_bounds_hidden"], "Marks and legend")
    assert "Seams (hidden now)" in hidden and "Spotlight (hidden now)" in hidden
    assert "Strip: alternating fills" in hidden


def test_a_pooled_legend_has_no_seams(out):
    legend = _text(out["lab_pooled"], "Marks and legend")
    assert "Seams:" not in legend and "Seams (" not in legend
    assert "Spotlight" in legend


# ---------------------------------------------------------------- Local ----


def test_the_local_ensemble_draws_no_lines_and_says_why(out):
    drawn = _text(out["local"], "What is drawn")
    assert "Local ensemble: the badge in the band above the plot" in drawn
    assert "no common layer grid along w, so no strip, no seams and no pooling" in drawn
    local = _fixture("projections_single_local")["depth_layers"]
    assert local["note"] in _text(out["local"], "Disclosures")
    assert "Layers tilt by each shower’s (θ, φ): no common layer grid" in _text(out["local"], "Marks and legend")
    assert "dashed 1 px" not in _text(out["local"])


def test_a_local_entry_panel_states_nothing_of_channels(out):
    assert "Local ensemble" not in _text(out["local_xy"])


def test_one_shower_in_local_draws_planes_on_u_w_with_the_pitch_along_w(out):
    tilt = out["event_tilt"]
    xz = out["event"]["local"]["xz"]
    drawn = _text(xz, "What is drawn")
    assert "layer planes are tilted with that shower, so no strip is drawn along w" in drawn
    assert "boundaries between channels are drawn as lines on u–w only, at the exact tilted planes" in drawn
    text = _text(xz, "Disclosures")
    assert f"θ = {tilt['theta_deg']:.1f}°" in text
    assert f"p / cos θ = {tilt['pitch_along_w_mm']:.2f} mm" in text
    pitch = tilt["pitch_along_w_mm"] * math.cos(tilt["theta"])
    assert f"(p = {pitch:.1f} mm)" in text
    assert "w = s / cos θ + u · tan θ" in text
    assert "On v–w the same plane spans a band" in text
    assert "Dashed lines: the tilted layer planes between channels, on u–w" in _text(xz, "Marks and legend")
    assert "Strip:" not in _text(xz, "Marks and legend")


def test_one_shower_in_local_has_no_line_on_v_w(out):
    yz = out["event"]["local"]["yz"]
    text = _text(yz)
    deg = f"{out['event_tilt']['theta_deg']:.1f}"
    assert f"v–w: a layer plane tilted by θ = {deg}° spans a band here, not a line" in text
    assert "drawn as lines on u–w only" not in text


# --------------------------------------------------------------- events ----


def test_an_absolute_event_states_z_and_its_channels_from_layer_planes(out):
    ev = _fixture("event_raster_base")
    planes = ev["frames"]["lab"]["layer_planes"]
    centre = (planes["edges_mm"][0] + planes["edges_mm"][1]) / 2
    drawn = _text(out["event"]["lab"]["yz"], "What is drawn")
    assert f"Depth is labelled Z = z − {planes['display_offset_mm']:.0f} mm" in drawn
    assert f"first layer's centre is at Z = {centre - planes['display_offset_mm']:.1f} mm" in drawn
    # An event window is not an ensemble axis: it does not start at Z = 0.
    assert "An ensemble depth axis starts at Z = 0" not in drawn
    assert "Channels are Ch 1–13" in drawn
    disclosures = _text(out["event"]["lab"]["yz"], "Disclosures")
    assert "Strip shares are of this shower's energy on the depth axis" in disclosures


def test_an_event_without_a_partition_still_states_z(out):
    assert "Depth is labelled Z = z − 3649 mm" in _text(out["event_off"], "What is drawn")
    assert "Longitudinal" not in _text(out["event_off"]) and "Strip:" not in _text(out["event_off"])


def test_a_relative_event_names_the_detector_end_of_its_reach(out):
    reach = _fixture("event_raster_base")["frames"]["trans"]["layer_planes"]["reach_layers"]
    text = _text(out["event"]["trans"]["yz"], "Disclosures")
    assert f"This shower's detector ends after relative layer {reach}" in text
    assert "Rel Ch 1–13" in _text(out["event"]["trans"]["yz"], "What is drawn")


def test_an_event_marks_toggle_names_hidden_seams(out):
    assert "Seams (hidden now)" in _text(out["event_marks_hidden"], "Marks and legend")


def test_an_event_entry_panel_has_no_channel_text(out):
    for kind in ("lab", "trans", "local"):
        assert "Channels are" not in _text(out["event"][kind]["xy"])
        assert "Depth is labelled" not in _text(out["event"][kind]["xy"])


# ------------------------------------------------------------------ C7 -----


def test_the_native_profile_names_its_channels_and_reach(out):
    reach = _fixture("profiles_single_native")["depth_layers"]["reach"]
    assert "Channels are Rel Ch" not in _text(out["profile_native_off"])
    assert "Reach:" not in _text(out["profile_native_off"])
    drawn = _text(out["profile_native"], "What is drawn")
    assert "Rel Ch 1–13" in drawn
    text = _text(out["profile_native"], "Disclosures")
    assert f"{reach['n_showers']} showers" in text and f"s ≤ {reach['l_phys']} − 1 − k" in text


def test_the_w_profile_says_it_has_no_common_layer_grid(out):
    w = _fixture("profiles_single_w")["depth_layers"]
    assert "Local ensemble" not in _text(out["profile_w_off"])
    assert w["note"] in _text(out["profile_w"], "Disclosures")
    assert "no common layer grid along w" in _text(out["profile_w"], "What is drawn")


# ------------------------------------------------------ Models page / 3-D ---


def test_a_paired_event_projection_draws_boundaries_only_beside_the_slice_bracket(out):
    drawn = _text(out["pair_event"], "What is drawn")
    assert "Longitudinal Channels on this projection are boundaries only" in drawn
    assert "never pools the depth axis" in drawn and "slice bracket" in drawn
    assert "PAIR" in drawn
    # The card hands its own spec; a {kind: {panel: spec}} map reads the same.
    assert _text(out["pair_event_map"]) == _text(out["pair_event"]).replace("PAIR ", "")
    assert "Channels are Ch 1–13" in drawn
    assert "Depth is labelled Z" in drawn


def test_a_paired_entry_projection_and_an_unpartitioned_one_state_no_boundaries(out):
    assert "boundaries only" not in _text(out["pair_event_xy"])
    assert "boundaries only" not in _text(out["pair_event_none"])
    assert "Depth is labelled Z" in _text(out["pair_event_none"], "What is drawn")


def test_a_paired_selection_projection_reads_the_ensemble_blocks(out):
    text = _text(out["pair_ensemble"], "What is drawn")
    assert "Depth is labelled Z" in text and "boundaries only" in text


def test_the_absolute_3d_view_titles_its_depth_axis_z(out):
    z = out["z_line"]
    assert z[0].startswith("The depth axis is titled Z = z − 3649 mm") and "raw z" in z[0]
    assert z[1] == "" and z[2] == ""
    assert z[0] in _text(out["vox_lab"], "What is drawn")
    assert "titled Z" not in _text(out["vox_canonical"], "What is drawn")


# ------------------------------------------------------------ captions -----


def test_the_absolute_captions_name_the_depth_z(out):
    c = out["captions"]
    assert c["lab"]["yz"].startswith("Transverse spread against depth Z = z − 3649 mm.")
    assert c["lab"]["xz"].startswith("Lateral profile against depth Z, sharing the YZ colour scale")
    assert "the depth axes are labelled Z = z − 3649 mm" in c["eventLab"]
    assert "labelled Z" not in c["eventTrans"]


def test_no_drawer_prints_an_ascii_hyphen_as_a_minus_sign(out):
    for text in _walk(out):
        assert not HYPHEN_NUMBER.search(text), text
