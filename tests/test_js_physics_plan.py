"""The Physics page's plan for the Event viewer and the standalone gating, under Node.

Brief ``data/dev/design/physics-subpages/brief.md`` §7: ``capabilities.js``
``page1Plan`` gains, without changing an existing field,

* ``viewer``: ``{enabled, reason}``, enabled with the Event Inspector, else
  shut with the server's ``event-inspector`` reason;
* ``channelReasons`` / ``modelReasons``: for each display channel and each
  network the experiment does not offer, the attention views' reason
  (``vox-attention``), else the networks' (``energy``), else a generic one;
* ``channelsShut``: the standing line under the channel radios.

Checked on the recorded catalogue ``tests/fixtures/payloads/experiments.json``
(two-shower hits, single-shower hits, the event-level aggregate), and on
variants of it for the cases no recording holds. Skipped when ``node`` is not
on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import _FAKE_DOM, HYPHEN_NUMBER, JS, NODE, _path, _payload, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

CHANNELS = ["density", "gradcam", "gradcam_energy", "shapcam", "shapcam_energy"]
MODELS = ["segmentation", "energy", "angle"]
NO_REASON = "Not available for this experiment."

_SCRIPT = _FAKE_DOM + r"""
const [capsUrl, stateUrl, cataloguePath] = JSON.parse(process.argv[1]);
const catalogue = load(cataloguePath);
const caps = await import(capsUrl);
const st = await import(stateUrl);
const out = { channels: st.CHANNELS, models: st.MODELS };

const exps = Object.fromEntries(catalogue.experiments.map((e) => [e.capabilities.kind, e]));
const pick = (plan) => ({ viewer: plan.viewer, channelReasons: plan.channelReasons, modelReasons: plan.modelReasons,
  channelsShut: plan.channelsShut, eventInspector: plan.eventInspector, channels: plan.channels, models: plan.models,
  keys: Object.keys(plan) });
out.plans = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, pick(caps.page1Plan(e))]));
out.reasons = Object.fromEntries(Object.entries(exps).map(([kind, e]) => [kind, e.capabilities.reasons ?? {}]));

// Variants no recording holds.
const single = exps.single_shower_hits;
const noAttention = structuredClone(single);
delete noAttention.capabilities.reasons['vox-attention'];
out.energyOnly = pick(caps.page1Plan(noAttention));
const noReason = structuredClone(single);
noReason.capabilities.reasons = {};
out.noReason = pick(caps.page1Plan(noReason));
const shutViewer = structuredClone(exps.two_shower_hits);
shutViewer.capabilities.panels['event-inspector'] = false;
shutViewer.capabilities.reasons['event-inspector'] = 'The inspector is shut for this test.';
out.shutViewer = pick(caps.page1Plan(shutViewer));
const shutViewerBare = structuredClone(exps.two_shower_hits);
shutViewerBare.capabilities.panels['event-inspector'] = false;
out.shutViewerBare = pick(caps.page1Plan(shutViewerBare));
const partial = structuredClone(exps.two_shower_hits);
partial.channels = ['density', 'gradcam', 'gradcam_energy'];
partial.models = ['segmentation'];
partial.capabilities.reasons['vox-attention'] = 'Shap-CAM columns are missing.';
out.partial = pick(caps.page1Plan(partial));
out.legacy = pick(caps.page1Plan({ table_name: 'old', status: 'ready', bounds: {} }));
out.legacyNull = pick(caps.page1Plan(null));
out.line = {
  none: caps.channelsShutLine([], 'Why.'),
  attention: caps.channelsShutLine(['shapcam_energy', 'gradcam', 'shapcam', 'gradcam_energy'], 'Why.'),
  two: caps.channelsShutLine(['shapcam', 'gradcam'], 'Why.'),
};
console.log(JSON.stringify(out));
"""

#: The fields page1Plan carried before this change, in order: none may move or vanish.
EXISTING_KEYS = ["kind", "kindLabel", "legacy", "nShowers", "showers", "hasHits", "axes", "spatial", "notice", "plot4",
                 "plot4Title", "plot4Reason", "frames", "coordSystems", "channels", "models", "performance", "banner",
                 "status", "eventInspector", "compare", "windowAxis", "physics", "disabled", "reasons", "quantities",
                 "stale"]
NEW_KEYS = ["viewer", "channelReasons", "modelReasons", "channelsShut"]


@pytest.fixture(scope="module")
def r() -> dict:
    return _run(_SCRIPT, [(JS / "capabilities.js").as_uri(), (JS / "state.js").as_uri(), _path("experiments")])


def _attention_line(reason: str) -> str:
    return ("Grad-CAM and Shap-CAM, raw and energy-weighted, are not available for this experiment: "
            f"{reason} The panels show the summed energy density.")


def test_the_catalogue_holds_the_three_kinds():
    kinds = [e["capabilities"]["kind"] for e in _payload("experiments")["experiments"]]
    assert sorted(kinds) == ["single_shower_events", "single_shower_hits", "two_shower_hits"]


def test_the_new_fields_follow_the_existing_ones_unchanged(r):
    assert r["channels"] == CHANNELS and r["models"] == MODELS
    for kind, plan in r["plans"].items():
        assert plan["keys"] == EXISTING_KEYS + NEW_KEYS, kind


def test_two_showers_offer_everything(r):
    plan = r["plans"]["two_shower_hits"]
    assert plan["viewer"] == {"enabled": True, "reason": None}
    assert plan["viewer"]["enabled"] == plan["eventInspector"]
    assert plan["channelReasons"] == {} and plan["modelReasons"] == {}
    assert plan["channelsShut"] is None


def test_single_shower_hits_grey_the_attention_channels_and_every_network(r):
    plan = r["plans"]["single_shower_hits"]
    reason = r["reasons"]["single_shower_hits"]["vox-attention"]
    assert reason.endswith("."), "the line relies on the reason's own full stop"
    assert plan["viewer"] == {"enabled": True, "reason": None}, "single-shower hits get the same viewer"
    assert plan["channels"] == ["density"]
    assert plan["channelReasons"] == dict.fromkeys(CHANNELS[1:], reason)
    assert plan["modelReasons"] == dict.fromkeys(MODELS, reason)
    assert plan["channelsShut"] == _attention_line(reason)


def test_the_aggregate_shuts_the_viewer_with_the_servers_reason(r):
    plan = r["plans"]["single_shower_events"]
    reason = r["reasons"]["single_shower_events"]["event-inspector"]
    assert plan["viewer"] == {"enabled": False, "reason": reason}
    assert "no hits" in reason
    assert plan["eventInspector"] is False
    # Every channel and network is shut, each with its reason; there are no spatial panels to name a channel in.
    attention = r["reasons"]["single_shower_events"]["vox-attention"]
    assert plan["channelReasons"] == dict.fromkeys(CHANNELS, attention)
    assert plan["modelReasons"] == dict.fromkeys(MODELS, attention)
    assert plan["channelsShut"] is None


def test_the_reason_falls_back_to_the_networks_then_a_generic_one(r):
    energy = r["reasons"]["single_shower_hits"]["energy"]
    assert r["energyOnly"]["channelReasons"]["gradcam"] == energy
    assert r["energyOnly"]["modelReasons"]["energy"] == energy
    assert r["energyOnly"]["channelsShut"] == _attention_line(energy)
    assert set(r["noReason"]["channelReasons"].values()) == {NO_REASON}
    assert set(r["noReason"]["modelReasons"].values()) == {NO_REASON}
    assert r["noReason"]["channelsShut"] == _attention_line(NO_REASON)


def test_a_shut_inspector_shuts_the_viewer_with_its_reason(r):
    assert r["shutViewer"]["viewer"] == {"enabled": False, "reason": "The inspector is shut for this test."}
    assert r["shutViewerBare"]["viewer"] == {"enabled": False, "reason": NO_REASON}


def test_a_partial_set_is_named_channel_by_channel(r):
    """Not in the brief's sentence, which names all four attention channels: a set short of them is named exactly."""
    plan = r["partial"]
    assert plan["channelReasons"] == {"shapcam": "Shap-CAM columns are missing.",
                                      "shapcam_energy": "Shap-CAM columns are missing."}
    assert plan["modelReasons"] == {"energy": "Shap-CAM columns are missing.", "angle": "Shap-CAM columns are missing."}
    assert plan["channelsShut"] == ("Not available for this experiment: Shap-CAM Attribution, Energy-weighted "
                                    "Shap-CAM. Shap-CAM columns are missing.")
    line = r["line"]
    assert line["none"] is None
    assert line["attention"] == _attention_line("Why.")
    assert line["two"] == "Not available for this experiment: Grad-CAM Model Attention, Shap-CAM Attribution. Why."


def test_a_server_without_the_capability_block(r):
    """A legacy server serves the Event Inspector; its default channels lack the three newer ones."""
    for plan in (r["legacy"], r["legacyNull"]):
        assert plan["viewer"] == {"enabled": True, "reason": None}
        assert set(plan["channelReasons"]) == {"gradcam_energy", "shapcam", "shapcam_energy"}
        assert set(plan["channelReasons"].values()) == {NO_REASON}
        assert plan["channelsShut"].startswith("Not available for this experiment: Energy-weighted Grad-CAM")


def test_no_line_signs_a_number_with_a_hyphen(r):
    texts = [p["channelsShut"] for p in r["plans"].values() if p["channelsShut"]]
    texts += [p["viewer"]["reason"] for p in r["plans"].values() if p["viewer"]["reason"]]
    assert texts
    for text in texts:
        assert not HYPHEN_NUMBER.search(text), text
