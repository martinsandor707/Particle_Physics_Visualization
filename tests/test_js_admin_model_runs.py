"""Admin Settings › XGBoost model runs: `controls/admin.js` reads the served list, under Node.

`modelRunRows` reads one shape, the real `GET /api/admin/model-runs` body
(`tests/contracts/model_runs_admin.json`, recorded in
`tests/fixtures/payloads/model_runs_admin.json`): `runs[]`, each with its
pairing and its analysis flat on it and its per-task split checks under
`runs[].runs[]`. The shapes the route had before the backend settled (a bare
array, `pairings`, `experiments`, nested `pairing` / `analysis`) are no
longer read, and nothing says "not available in this build". Skipped without
`node`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
RECORDING = ROOT / "tests" / "fixtures" / "payloads" / "model_runs_admin.json"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
import fs from 'node:fs';
const [adminUrl, recording] = JSON.parse(process.argv[1]);
const admin = await import(adminUrl);
const payload = JSON.parse(fs.readFileSync(recording, 'utf8'));
const out = {};
out.rows = admin.modelRunRows(payload).map((row) => ({ ...row, text: admin.runStatusText(row),
  warning: admin.splitWarning(row) }));
const running = JSON.parse(JSON.stringify(payload.runs.find((r) => r.status === 'done')));
Object.assign(running, { status: 'running', step: 5, steps: 18, step_label: 'cross-validation fold 2 of 5 (momentum)',
  progress: 0.2778, duration_s: null, runs: [] });
const queued = { ...running, status: 'queued', step: 0, step_label: '', progress: 0 };
out.running = admin.modelRunRows({ runs: [running, queued] }).map((row) => [row.progress, admin.runStatusText(row)]);
out.retired = [admin.modelRunRows([running]), admin.modelRunRows({ pairings: [running] }),
  admin.modelRunRows({ experiments: [running] }), admin.modelRunRows({}), admin.modelRunRows(null)];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    args = json.dumps([(JS / "controls" / "admin.js").as_uri(), str(RECORDING)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args], capture_output=True, text=True,
                          timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_recorded_list_reads_into_one_row_per_experiment(out):
    payload = json.loads(RECORDING.read_text(encoding="utf-8"))
    rows = out["rows"]
    assert [r["table_name"] for r in rows] == [r["table_name"] for r in payload["runs"]]
    assert [r["name"] for r in rows] == [r["display_name"] for r in payload["runs"]]
    assert [r["status"] for r in rows] == [r["status"] if r["paired"] else "unpaired" for r in payload["runs"]]
    for row, run in zip(rows, payload["runs"]):
        assert row["models"] == [m["path"] for m in run["models"]]
        assert row["paired"] is run["paired"] and row["species"] == run["species"] and row["seed"] == run["seed"]
        assert row["seconds"] == run["duration_s"]


def test_each_status_says_why(out):
    by = {r["table_name"].split("_")[0]: r for r in out["rows"]}
    assert by["electron"]["text"].startswith("done in 1 s; split not reproduced (angle: ")
    assert by["pion"]["text"] == ("failed: the experiment holds 6 events; the 80/20 split and five folds need "
                                  "at least 10.")
    assert by["muon"]["text"].startswith("not paired: No XGBoost models pair with this experiment: the angle model")
    assert by["aggregate"]["status"] == "unpaired"


def test_the_split_rows_wave_c_added_are_kept(out):
    electron = next(r for r in out["rows"] if r["table_name"].startswith("electron_"))
    assert [s["task"] for s in electron["splits"]] == ["momentum", "angle"]
    assert electron["warning"] == ("split not reproduced (angle: validation / training MSE 1.03 at random_state 42 "
                                   "against at most 1.24 at random_state 55, 1.6× required)")
    assert all(not r["warning"] for r in out["rows"] if r is not electron)


def test_a_running_analysis_names_its_step(out):
    assert out["running"] == [
        ["5 of 18: cross-validation fold 2 of 5 (momentum)", "analysing (5 of 18: cross-validation fold 2 of 5 (momentum))"],
        [0, "queued for analysis"],
    ]


def test_the_retired_shapes_and_the_not_built_scaffolding_are_gone(out):
    assert out["retired"] == [[], [], [], [], []]
    source = (JS / "controls" / "admin.js").read_text(encoding="utf-8")
    assert "not available in this build" not in source.lower()
    for retired in ("payload?.pairings", "payload?.experiments", "run.analysis", "run.pairing", "catalogue?.dir",
                    "status === 404", "model_files"):
        assert retired not in source, retired
