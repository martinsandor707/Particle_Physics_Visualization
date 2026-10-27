"""The models-folder scan never fails on a bad file, and a source name pairs only when it ends at its version.

``calosrv/modelruns/discovery.py`` reads every ``xgboost_<species>/standalone_<task>_s<seed>_model.json``
header with the standard library. A file that is not a model - JSON of the wrong shape, JSON
nested too deeply to parse, bytes that are not UTF-8, a symbolic link, a file over the size
cap - must come back as a rejection with its reason, never an exception: one bad file would
otherwise fail the Admin Settings list, Re-analyse and the boot check for every species.
No database and no XGBoost model: the headers are written here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from calosrv.db.registry import ExperimentRecord
from calosrv.modelruns import discovery, pairing

#: A header with everything the scan reads: a two-feature momentum model.
HEADER = {
    "version": [3, 2, 0],
    "learner": {
        "feature_names": ["num_hits", "mean_r"],
        "feature_types": ["int", "float"],
        "learner_model_param": {"num_target": "1", "base_score": "5E0"},
        "objective": {"name": "reg:squarederror"},
        "gradient_booster": {"model": {"gbtree_model_param": {"num_trees": "3"}}},
    },
}


def _folder(tmp_path: Path, files: dict[str, bytes | str]) -> Path:
    root = tmp_path / "models"
    target = root / "xgboost_electron"
    target.mkdir(parents=True)
    for name, body in files.items():
        data = body.encode("utf-8") if isinstance(body, str) else body
        (target / name).write_bytes(data)
    return root


def _scan(tmp_path: Path, body: bytes | str, name: str = "standalone_momentum_s1_model.json"):
    catalogue = discovery.scan(_folder(tmp_path, {name: body}))
    return catalogue, {r.relative.split("/")[-1]: r.reason for r in catalogue.rejected}


def test_a_well_formed_header_is_read_and_hashed_from_the_same_bytes(tmp_path):
    body = json.dumps(HEADER)
    catalogue, rejected = _scan(tmp_path, body)
    assert rejected == {}
    model = catalogue.get("electron", 1, "momentum")
    assert model.feature_names == ("num_hits", "mean_r") and model.num_trees == 3
    assert model.sha256 == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert model.size == len(body.encode("utf-8")) and model.xgboost_version == "3.2.0"


@pytest.mark.parametrize("body,why", [
    (json.dumps({"learner": []}), "malformed 'learner'"),
    (json.dumps({**HEADER, "learner": {**HEADER["learner"], "learner_model_param": []}}),
     "learner_model_param"),
    (json.dumps({**HEADER, "learner": {**HEADER["learner"], "objective": "reg:squarederror"}}),
     "objective"),
    (json.dumps({**HEADER, "learner": {**HEADER["learner"], "gradient_booster": {"model": 3}}}),
     "model"),
    (json.dumps({**HEADER, "learner": {**HEADER["learner"], "feature_names": "num_hits"}}),
     "must be lists"),
    (json.dumps({**HEADER, "learner": {**HEADER["learner"],
                                       "learner_model_param": {"num_target": [1]}}}),
     "not an XGBoost gbtree model file"),
    (json.dumps([HEADER]), "malformed 'learner'"),
    ("[" * 100_000 + "]" * 100_000, "nested too deeply"),
    ("{not json", "is not valid JSON"),
    (b"\xff\xfe\x00{", "could not be read"),
    ("", "is not valid JSON"),
])
def test_a_malformed_file_is_a_rejection_with_its_reason(tmp_path, body, why):
    catalogue, rejected = _scan(tmp_path, body)
    assert catalogue.models == {}
    (reason,) = rejected.values()
    assert why in reason, reason


def test_one_bad_file_leaves_the_others_paired(tmp_path):
    angle = json.loads(json.dumps(HEADER))
    angle["learner"]["learner_model_param"]["num_target"] = "2"
    root = _folder(tmp_path, {"standalone_momentum_s1_model.json": json.dumps(HEADER),
                              "standalone_angle_s1_model.json": json.dumps({"learner": []}),
                              "standalone_angle_s2_model.json": json.dumps(angle)})
    catalogue = discovery.scan(root)
    assert set(catalogue.models) == {("electron", 1, "momentum"), ("electron", 2, "angle")}
    assert [r.relative for r in catalogue.rejected] == ["xgboost_electron/standalone_angle_s1_model.json"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links on this platform")
def test_a_symbolic_link_is_never_followed(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(HEADER), encoding="utf-8")
    root = _folder(tmp_path, {})
    (root / "xgboost_electron" / "standalone_momentum_s1_model.json").symlink_to(outside)
    (root / "xgboost_electron" / "standalone_angle_s1_model.json").symlink_to("/dev/zero")
    (root / "xgboost_muon").symlink_to(root / "xgboost_electron", target_is_directory=True)
    catalogue = discovery.scan(root)
    assert catalogue.models == {}
    reasons = {r.relative: r.reason for r in catalogue.rejected}
    assert "symbolic link" in reasons["xgboost_electron/standalone_momentum_s1_model.json"]
    assert "symbolic link" in reasons["xgboost_electron/standalone_angle_s1_model.json"]
    assert "symbolic link" in reasons["xgboost_muon"]


def test_a_file_over_the_cap_is_refused_before_it_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "MAX_BYTES", 64)
    catalogue, rejected = _scan(tmp_path, json.dumps(HEADER))
    assert catalogue.models == {}
    (reason,) = rejected.values()
    assert "over the 64-byte cap" in reason


def test_a_directory_named_like_a_model_is_not_a_file(tmp_path):
    root = _folder(tmp_path, {})
    (root / "xgboost_electron" / "standalone_momentum_s1_model.json").mkdir()
    catalogue = discovery.scan(root)
    assert catalogue.models == {}
    (reason,) = [r.reason for r in catalogue.rejected]
    assert "not a regular file" in reason


# ----------------------------------------------------------------- pairing --


def _record(source: str) -> ExperimentRecord:
    return ExperimentRecord(table_name="x", display_name="x", source_files=[source],
                            status="ready")


@pytest.mark.parametrize("source,species,seed", [
    ("electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.parquet", "electron", 1),
    ("electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3.csv", "electron", 1),
    ("muon_standalone_N100000_M0_20GeV_reg_balanced_aggr_s2_v12", "muon", 2),
])
def test_a_source_name_ending_at_its_version_names_its_species_and_seed(source, species, seed):
    found = pairing.parse_source(_record(source))
    assert (found.species, found.seed, found.reason) == (species, seed, None)


@pytest.mark.parametrize("source", [
    "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3_head.parquet",
    "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3_head",
    "electron_standalone_N100000_M0_20GeV_reg_balanced_aggr_s1_v3x.csv",
])
def test_a_cut_of_the_source_does_not_pair(source):
    """A ``..._v3_head`` file holds other rows: the notebook's split means nothing on them."""
    found = pairing.parse_source(_record(source))
    assert found.species is None and "does not name a species and seed" in found.reason
