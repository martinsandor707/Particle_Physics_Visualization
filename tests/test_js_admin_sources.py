"""Admin Settings › Source files: `controls/admin.js` builds its rows under Node.

The section compares each experiment with the file it was ingested from
(`GET /api/admin/experiments`, `tests/contracts/admin_experiments.json`,
recorded in `tests/fixtures/payloads/admin_experiments.json`). `sourceRows`,
`sourceBadge`, `sourceJobText`, `sourceAction` and `sourcesSummary` are pure
functions of that payload, so every state is proved here without a browser.

The recording holds whatever the booted server happened to have, which may be
only untracked or unchanged rows. Every variant is therefore derived in the
script from `payload.experiments[0]`, so the tests do not depend on what the
recording contains. Skipped without `node`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
RECORDING = ROOT / "tests" / "fixtures" / "payloads" / "admin_experiments.json"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
import fs from 'node:fs';
const [adminUrl, recording] = JSON.parse(process.argv[1]);
const admin = await import(adminUrl);
const payload = JSON.parse(fs.readFileSync(recording, 'utf8'));
const base = payload.experiments[0];

const ROOT = '/app/ingest';
const recorded = { bytes: 2873386592, modified: '2026-10-28T16:47:08+00:00' };
const current = { bytes: 2911002110, modified: '2026-11-11T19:40:31+00:00' };
const OFFER = { available: true, reason: null };
const refuse = (reason) => ({ available: false, reason });

/** One experiment, derived from the recording's first. */
function variant({ status = 'ready', state = 'changed', origin = 'drop_folder', settling = false, job = null,
  reingest = OFFER, retry = refuse('Only a failed experiment is retried.'), detail = 'A sentence.',
  file = 'hits_all_models.parquet', name = 'Changed one', table = 'changed_one' } = {}) {
  const e = JSON.parse(JSON.stringify(base));
  e.table_name = table;
  e.display_name = name;
  e.status = status;
  e.error = status === 'failed' ? 'Ingestion was interrupted before it completed.' : null;
  e.source_changed = state === 'changed';
  e.source = { origin, file, path: `${ROOT}/${file}`, state, basis: 'recorded', settling, recorded, current, detail };
  e.actions = { reingest, retry };
  e.job = job;
  return e;
}
const job = (mode, status, over = {}) => ({ job_id: 'j1', mode, status, progress: 0.42, stage_label: '', error: null,
  finished_at: null, ...over });
const rows = (...experiments) => admin.sourceRows({ roots: payload.roots, experiments });
const one = (e) => rows(e)[0];

const out = {};

// The recording itself reads into one row per experiment, in order.
out.recorded = admin.sourceRows(payload).map((r) => [r.table_name, r.name, r.state, r.badge, r.actions]);
out.recordedNames = payload.experiments.map((e) => [e.table_name, e.display_name]);
out.empty = [admin.sourceRows(null), admin.sourceRows({}), admin.sourceRows(undefined), admin.sourceRows({ experiments: null })];

// A row's model.
const changed = one(variant());
out.model = Object.fromEntries(['table_name', 'name', 'file', 'path', 'status', 'state', 'source_changed', 'settling',
  'detail', 'badge', 'job', 'error'].map((k) => [k, changed[k]]));
out.modelActions = changed.actions;
out.noSource = (() => { const e = variant(); delete e.source; const r = one(e); return [r.state, r.badge, r.file]; })();

// Badges, one per rule.
const badge = (o) => one(variant(o)).badge;
out.badges = {
  changed: badge({ state: 'changed' }),
  unchanged: badge({ state: 'unchanged' }),
  touched: badge({ state: 'touched' }),
  missing: badge({ state: 'missing' }),
  upload: badge({ state: 'untracked', origin: 'upload' }),
  seed: badge({ state: 'untracked', origin: 'seed' }),
  none: badge({ state: 'untracked', origin: 'drop_folder' }),
  cli: badge({ state: 'untracked', origin: 'cli' }),
  failed: badge({ status: 'failed', state: 'unchanged' }),
  failedAndChanged: badge({ status: 'failed', state: 'changed' }),
  queuedReingest: badge({ job: job('reingest', 'queued') }),
  runningReingest: badge({ job: job('reingest', 'running') }),
  runningRetry: badge({ status: 'failed', job: job('retry', 'running') }),
  runningOther: badge({ state: 'unchanged', job: job('create_new', 'running') }),
  queuedOther: badge({ state: 'unchanged', job: job('append', 'queued') }),
  doneJobChanged: badge({ job: job('reingest', 'done') }),
  failedJobOnReady: badge({ state: 'unchanged', job: job('reingest', 'failed', { error: 'x' }) }),
};

// Job lines, every mode and status.
const text = (j) => admin.sourceJobText(one(variant({ job: j })));
out.jobText = {
  none: text(null),
  queued: text(job('reingest', 'queued', { progress: 0 })),
  queuedRetry: text(job('retry', 'queued', { progress: 0 })),
  runningReingest: text(job('reingest', 'running')),
  runningRetry: text(job('retry', 'running')),
  runningOther: text(job('create_new', 'running')),
  runningZero: text(job('reingest', 'running', { progress: 0 })),
  doneReingest: text(job('reingest', 'done', { progress: 1 })),
  doneRetry: text(job('retry', 'done', { progress: 1 })),
  doneOther: text(job('create_new', 'done', { progress: 1 })),
  failedReingest: text(job('reingest', 'failed', { error: 'The schema changed.' })),
  failedReingestNoStop: text(job('reingest', 'failed', { error: 'boom' })),
  failedReingestNoError: text(job('reingest', 'failed')),
  failedReingestServer: text(job('reingest', 'failed', { error: "The re-ingest of 'x' from x.parquet failed "
    + "(boom) and was rolled back; the experiment is served as it was." })),
  failedRetry: text(job('retry', 'failed', { error: 'No space left.' })),
  failedOther: text(job('create_new', 'failed', { error: 'Bad schema.' })),
  failedOtherNoError: text(job('create_new', 'failed')),
  queuedRebuild: text(job('rebuild', 'queued', { progress: 0 })),
  runningRebuild: text(job('rebuild', 'running')),
  doneRebuild: text(job('rebuild', 'done', { progress: 1 })),
  failedRebuild: text(job('rebuild', 'failed', { error: 'No space left.' })),
  failedRebuildNoError: text(job('rebuild', 'failed')),
  runningAppend: text(job('append', 'running')),
  doneAppend: text(job('append', 'done', { progress: 1 })),
  failedAppend: text(job('append', 'failed', { error: 'Bad schema.' })),
};

// finishedJobs: which re-ingest or retry jobs ended between two reads.
const withJob = (table, j, over = {}) => ({ ...one(variant({ table, name: table, job: j, ...over })) });
const entries = (map) => [...map.entries()];
const fin = (previous, ...rs) => {
  const before = previous === null ? null : new Map(previous);
  const r = admin.finishedJobs(before, rs);
  return { finished: r.finished.map((f) => [f.row.table_name, f.job.job_id, f.job.status]), active: entries(r.active),
    inputKept: before === null ? null : entries(before) };
};
const run = (mode, status, id) => job(mode, status, { job_id: id });
out.finished = {
  // Seen running on one read and done on the next, though nobody here started it (another tab, a reload).
  seenThenDone: [fin(null, withJob('a', run('reingest', 'running', 'j1'))),
    fin([['a', 'j1']], withJob('a', run('reingest', 'done', 'j1')))],
  seenQueuedRetryThenFailed: [fin(null, withJob('a', run('retry', 'queued', 'j2'))),
    fin([['a', 'j2']], withJob('a', run('retry', 'failed', 'j2')))],
  // Seeded by the POST reply alone (the Map is filled before the first read).
  seededByThePost: fin([['a', 'j3']], withJob('a', run('reingest', 'done', 'j3'))),
  // Once per job id: the same finished job on the next read is not reported again.
  once: (() => {
    const first = fin([['a', 'j1']], withJob('a', run('reingest', 'done', 'j1')));
    return [first.finished.length, fin(first.active, withJob('a', run('reingest', 'done', 'j1'))).finished.length];
  })(),
  // A job that was already over when the page first read it was never seen active.
  alreadyDone: fin(null, withJob('a', run('reingest', 'done', 'j1'))),
  // Still running: kept, not reported.
  stillRunning: fin([['a', 'j1']], withJob('a', run('reingest', 'running', 'j1'))),
  // Other modes are not this section's to report.
  rebuildIgnored: fin(null, withJob('a', run('rebuild', 'running', 'j4'))),
  rebuildThenDone: fin([['a', 'j1']], withJob('a', run('rebuild', 'done', 'j4'))),
  createNewIgnored: fin(null, withJob('a', run('create_new', 'queued', 'j5'))),
  // The tracked job was replaced by another one, whose outcome is not the tracked job's.
  superseded: fin([['a', 'j1']], withJob('a', run('reingest', 'done', 'j9'))),
  // The experiment's job is gone (the registry was cleared): forgotten.
  noJob: fin([['a', 'j1']], withJob('a', null)),
  // Two experiments, one finished and one running; a third unseen row changes nothing.
  mixed: fin([['a', 'j1'], ['b', 'j2'], ['gone', 'j7']], withJob('a', run('reingest', 'done', 'j1')),
    withJob('b', run('retry', 'running', 'j2')), withJob('c', null)),
  nullRows: [admin.finishedJobs(null, null), admin.finishedJobs(undefined, undefined)]
    .map((r) => [r.finished, entries(r.active)]),
};

// nextSourceRead: when to read the files again.
const next = (rs, roots, open) => admin.nextSourceRead(rs, roots, open);
const settlingRow = (extra) => one(variant({ settling: true, reingest: refuse('Just written.'), ...extra }));
out.next = {
  idle: next(rows(variant({ state: 'unchanged' })), { settle_s: 30 }, true),
  job: next(rows(variant({ job: job('reingest', 'running') })), { settle_s: 30 }, true),
  queued: next(rows(variant({ job: job('retry', 'queued') })), { settle_s: 30 }, true),
  settling: next([settlingRow()], { settle_s: 30 }, true),
  settlingDefault: next([settlingRow()], { settle_s: 30 }),
  settlingNoRoots: next([settlingRow()], null, true),
  settlingZero: next([settlingRow()], { settle_s: 0 }, true),
  settlingFraction: next([settlingRow()], { settle_s: 2.5 }, true),
  jobOutranksSettling: next([settlingRow({ job: job('reingest', 'running') })], { settle_s: 30 }, true),
  closed: next([settlingRow()], { settle_s: 30 }, false),
  closedJob: next(rows(variant({ job: job('reingest', 'running') })), { settle_s: 30 }, false),
  none: [next([], null, true), next(null, null, true)],
};

// Actions.
const act = (o, starting) => admin.sourceAction(one(variant(o)), starting);
const failedOffer = { status: 'failed', state: 'unchanged', reingest: refuse('A failed experiment is retried, not re-ingested.'),
  retry: OFFER };
out.actions = {
  changed: act({}),
  changedStartingSet: act({}, new Set(['changed_one'])),
  changedStartingArray: act({}, ['changed_one']),
  changedOtherStarting: act({}, new Set(['another'])),
  changedBusy: act({ job: job('reingest', 'running') }),
  changedSettling: act({ settling: true, reingest: refuse('The file was modified 4 s ago; Re-ingest is offered once it has been unchanged for 30 s.') }),
  changedMissingFile: act({ file: 'x.parquet' }),
  failed: act(failedOffer),
  failedStarting: act(failedOffer, new Set(['changed_one'])),
  failedBusy: act({ ...failedOffer, job: job('retry', 'queued') }),
  failedUnavailable: act({ ...failedOffer, retry: refuse('Its source file hits_all_models.parquet is not in /app/ingest; ingest it again from Upload dataset with Replace ticked.') }),
  unchanged: act({ state: 'unchanged' }),
  touched: act({ state: 'touched' }),
  missing: act({ state: 'missing' }),
  untracked: act({ state: 'untracked', origin: 'upload' }),
  noArg: admin.sourceAction(one(variant())),
};
out.noReason = act({ reingest: { available: false, reason: null } });

// Summaries.
const sum = (...experiments) => admin.sourcesSummary(rows(...experiments), payload.roots);
const failedRow = variant({ status: 'failed', state: 'unchanged', ...failedOffer, name: 'F', table: 'f' });
const changedRow = (t) => variant({ table: t, name: t });
out.summary = {
  oneChangedOneFailed: admin.sourcesSummary(rows(changedRow('a'), failedRow, variant({ state: 'unchanged', table: 'c' })),
    { drop_folder: ROOT, local: ROOT, settle_s: 30 }),
  twoChanged: admin.sourcesSummary(rows(changedRow('a'), changedRow('b')), { drop_folder: ROOT }),
  onlyFailed: admin.sourcesSummary(rows(failedRow), { drop_folder: ROOT }),
  clean: admin.sourcesSummary(rows(variant({ state: 'unchanged' }), variant({ state: 'untracked', origin: 'seed', table: 's' })),
    { drop_folder: ROOT }),
  touchedIsClean: admin.sourcesSummary(rows(variant({ state: 'touched' })), { drop_folder: ROOT }),
  noExperiments: admin.sourcesSummary([], { drop_folder: ROOT }),
  noRoots: admin.sourcesSummary(rows(variant({ state: 'unchanged' })), { drop_folder: null, local: null }),
  localOnly: admin.sourcesSummary(rows(variant({ state: 'unchanged' })), { drop_folder: null, local: '/app/local' }),
  noRootsObject: admin.sourcesSummary(rows(variant({ state: 'unchanged' })), null),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    args = json.dumps([(JS / "controls" / "admin.js").as_uri(), str(RECORDING)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args], capture_output=True, text=True,
                          timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_recording_reads_into_one_row_per_experiment(out):
    assert [[r[0], r[1]] for r in out["recorded"]] == out["recordedNames"]
    for _table, _name, state, badge, actions in out["recorded"]:
        assert state in ("unchanged", "touched", "changed", "missing", "untracked")
        assert badge["kind"] in ("changed", "failed", "busy", "current", "muted")
        assert set(actions) == {"reingest", "retry"}


def test_a_missing_or_empty_payload_gives_no_rows(out):
    assert out["empty"] == [[], [], [], []]


def test_a_row_carries_what_the_table_and_the_buttons_need(out):
    assert out["model"] == {
        "table_name": "changed_one", "name": "Changed one", "file": "hits_all_models.parquet",
        "path": "/app/ingest/hits_all_models.parquet", "status": "ready", "state": "changed",
        "source_changed": True, "settling": False, "detail": "A sentence.",
        "badge": {"text": "Source updated on disk", "kind": "changed"}, "job": None, "error": None,
    }
    assert out["modelActions"]["reingest"] == {"available": True, "reason": None}
    assert out["modelActions"]["retry"]["available"] is False
    # An experiment the server sends no source block for is untracked, never an error.
    state, badge, file = out["noSource"]
    assert (state, file) == ("untracked", None)
    assert badge == {"text": "No source recorded", "kind": "muted"}


def test_every_badge(out):
    b = out["badges"]
    assert b["changed"] == {"text": "Source updated on disk", "kind": "changed"}
    assert b["unchanged"] == {"text": "Current", "kind": "current"}
    assert b["touched"] == {"text": "Timestamp changed; sampled content the same", "kind": "muted"}
    assert b["missing"] == {"text": "Source file not found", "kind": "muted"}
    assert b["upload"] == {"text": "Uploaded: no file on the server to compare", "kind": "muted"}
    assert b["seed"] == {"text": "Demonstration dataset: ships in the image", "kind": "muted"}
    assert b["none"] == {"text": "No source recorded", "kind": "muted"}
    assert b["cli"] == {"text": "No source recorded", "kind": "muted"}
    assert b["failed"] == {"text": "Ingestion failed", "kind": "failed"}


def test_a_failed_experiment_is_failed_before_it_is_changed(out):
    assert out["badges"]["failedAndChanged"] == {"text": "Ingestion failed", "kind": "failed"}


def test_an_active_job_outranks_every_other_rule(out):
    b = out["badges"]
    assert b["queuedReingest"] == {"text": "Re-ingesting", "kind": "busy"}
    assert b["runningReingest"] == {"text": "Re-ingesting", "kind": "busy"}
    assert b["runningRetry"] == {"text": "Retrying", "kind": "busy"}
    assert b["runningOther"] == {"text": "Ingesting", "kind": "busy"}
    assert b["queuedOther"] == {"text": "Ingesting", "kind": "busy"}


def test_a_finished_job_leaves_the_badge_to_the_state(out):
    b = out["badges"]
    assert b["doneJobChanged"]["kind"] == "changed"
    # A rolled-back re-ingest leaves the experiment as it was: ready and current.
    assert b["failedJobOnReady"] == {"text": "Current", "kind": "current"}


def test_every_job_line(out):
    t = out["jobText"]
    assert t["none"] == ""
    assert t["queued"] == t["queuedRetry"] == "Waiting for the ingest worker"
    assert t["runningReingest"] == "Re-ingesting (42%) — served from its previous data until the new tables verify"
    assert t["runningZero"].startswith("Re-ingesting (0%)")
    assert t["runningRetry"] == "Retrying (42%)"
    assert t["runningOther"] == "Ingesting (42%)"
    assert t["doneReingest"] == "Re-ingested — ready"
    assert t["doneRetry"] == t["doneOther"] == "Ingested — ready"
    assert t["failedReingest"] == "Re-ingest failed: The schema changed. It is served as it was."
    assert t["failedReingestNoStop"] == "Re-ingest failed: boom. It is served as it was."
    assert t["failedReingestNoError"] == "Re-ingest failed: see the server log. It is served as it was."
    # The worker's message already says it was rolled back: shown once, not repeated.
    assert t["failedReingestServer"] == ("The re-ingest of 'x' from x.parquet failed (boom) and was rolled "
                                         "back; the experiment is served as it was.")
    assert t["failedRetry"] == "Retry failed: No space left."
    assert t["failedOther"] == "Failed: Bad schema."
    assert t["failedOtherNoError"] == "Failed: see the server log"


def test_a_rebuild_or_append_job_is_not_called_an_ingest(out):
    t = out["jobText"]
    assert t["queuedRebuild"] == "Waiting for the ingest worker"
    assert t["runningRebuild"] == "Rebuilding (42%)"
    assert t["doneRebuild"] == "Rebuilt — ready"
    assert t["failedRebuild"] == "Rebuild failed: No space left."
    assert t["failedRebuildNoError"] == "Rebuild failed: see the server log"
    assert t["runningAppend"] == "Appending (42%)"
    assert t["doneAppend"] == "Appended — ready"
    assert t["failedAppend"] == "Append failed: Bad schema."
    for key in ("runningRebuild", "doneRebuild", "failedRebuild", "runningAppend", "doneAppend", "failedAppend"):
        assert "ngest" not in t[key], key


def test_a_job_seen_active_on_any_read_is_reported_when_it_ends(out):
    f = out["finished"]
    # Another tab started it, or the page was reloaded during it: nothing was posted here.
    seen, ended = f["seenThenDone"]
    assert seen == {"finished": [], "active": [["a", "j1"]], "inputKept": None}
    assert ended["finished"] == [["a", "j1", "done"]] and ended["active"] == []
    seen, ended = f["seenQueuedRetryThenFailed"]
    assert seen["active"] == [["a", "j2"]]
    assert ended["finished"] == [["a", "j2", "failed"]] and ended["active"] == []
    # The POST reply seeds the Map, so a job that ends before the first read is still reported.
    assert f["seededByThePost"]["finished"] == [["a", "j3", "done"]]


def test_a_finished_job_is_reported_once_and_only_if_it_was_seen_active(out):
    f = out["finished"]
    assert f["once"] == [1, 0]
    assert f["alreadyDone"]["finished"] == [] and f["alreadyDone"]["active"] == []
    assert f["stillRunning"]["finished"] == [] and f["stillRunning"]["active"] == [["a", "j1"]]


def test_only_a_reingest_or_a_retry_is_followed(out):
    f = out["finished"]
    for key in ("rebuildIgnored", "createNewIgnored"):
        assert f[key]["finished"] == [] and f[key]["active"] == [], key
    # A rebuild that replaced the tracked job ends the tracking without reporting a re-ingest.
    assert f["rebuildThenDone"]["finished"] == [] and f["rebuildThenDone"]["active"] == []
    assert f["superseded"]["finished"] == [] and f["superseded"]["active"] == []
    assert f["noJob"]["finished"] == [] and f["noJob"]["active"] == []


def test_finished_jobs_leaves_its_input_alone_and_tolerates_nothing(out):
    f = out["finished"]
    mixed = f["mixed"]
    assert mixed["finished"] == [["a", "j1", "done"]]
    # A name this read did not carry is left as it was.
    assert mixed["active"] == [["b", "j2"], ["gone", "j7"]]
    assert mixed["inputKept"] == [["a", "j1"], ["b", "j2"], ["gone", "j7"]]
    assert f["nullRows"] == [[[], []], [[], []]]


def test_the_next_read_follows_a_job_and_a_settling_file(out):
    n = out["next"]
    assert n["idle"] is None
    assert n["job"] == n["queued"] == 1500
    # settle_s + 1 s, so the file has just become re-ingestable when it is read.
    assert n["settling"] == n["settlingDefault"] == 31_000
    assert n["settlingNoRoots"] == n["settlingZero"] == 1_000
    assert n["settlingFraction"] == 3_500
    assert n["jobOutranksSettling"] == 1500
    assert n["closed"] is None and n["closedJob"] is None
    assert n["none"] == [None, None]


def test_a_changed_experiment_gets_re_ingest_enabled_by_the_server(out):
    a = out["actions"]["changed"]
    assert a["kind"] == "reingest" and a["label"] == "Re-ingest" and a["disabled"] is False
    assert a["title"] == ("Rebuild this experiment from hits_all_models.parquet in one transaction: it stays "
                          "served from its previous data until the new tables verify, and a failure leaves it as it was.")


def test_the_button_is_disabled_while_its_request_or_job_runs(out):
    a = out["actions"]
    for key in ("changedStartingSet", "changedStartingArray", "changedBusy"):
        assert a[key]["kind"] == "reingest" and a[key]["disabled"] is True, key
        assert a[key]["title"] == "A job for this experiment is queued or running.", key
    # Another experiment's request leaves this one alone.
    assert a["changedOtherStarting"]["disabled"] is False


def test_an_unavailable_action_is_disabled_and_says_why(out):
    a = out["actions"]
    assert a["changedSettling"]["disabled"] is True
    assert a["changedSettling"]["title"].startswith("The file was modified 4 s ago; Re-ingest is offered once")
    assert a["failedUnavailable"]["kind"] == "retry" and a["failedUnavailable"]["disabled"] is True
    assert a["failedUnavailable"]["title"].endswith("with Replace ticked.")
    # A refusal without a reason still gets a sentence.
    assert out["noReason"]["disabled"] is True and out["noReason"]["title"]


def test_a_failed_experiment_gets_retry_ingest(out):
    a = out["actions"]["failed"]
    assert a["kind"] == "retry" and a["label"] == "Retry ingest" and a["disabled"] is False
    assert a["title"] == ("Ingest it again from hits_all_models.parquet; the tables and archive files of the "
                          "failed attempt are dropped first.")
    assert out["actions"]["failedStarting"]["disabled"] is True
    assert out["actions"]["failedBusy"]["disabled"] is True


def test_every_other_row_has_no_button(out):
    for key in ("unchanged", "touched", "missing", "untracked"):
        assert out["actions"][key] == {"kind": None, "label": "", "disabled": True, "title": ""}, key
    assert out["actions"]["noArg"]["kind"] == "reingest"


def test_the_summary_line(out):
    s = out["summary"]
    assert s["oneChangedOneFailed"] == (
        "Drop folder /app/ingest · 1 experiment has a newer file on disk · 1 failed. Nothing is re-ingested until "
        "its button is pressed; a re-ingest runs on the ingest worker, and the experiment stays served from its "
        "previous data until the new tables have verified.")
    assert s["twoChanged"].startswith("Drop folder /app/ingest · 2 experiments have a newer file on disk. Nothing")
    assert "failed" not in s["twoChanged"].split("Nothing")[0]
    assert s["onlyFailed"].startswith("Drop folder /app/ingest · 1 failed. Nothing")
    assert "newer file" not in s["onlyFailed"]


def test_the_summary_line_when_nothing_changed_and_nothing_failed(out):
    s = out["summary"]
    clean = "Every experiment with a tracked source matches its file on disk."
    assert s["clean"] == f"Drop folder /app/ingest · {clean}"
    # A touched file (same content, newer time) is not a change.
    assert s["touchedIsClean"].endswith(clean)
    assert s["noExperiments"] == "Drop folder /app/ingest · No experiment to compare with its source file."


def test_the_summary_line_names_the_folder_it_has(out):
    s = out["summary"]
    assert s["noRoots"].startswith("No drop folder is set · ")
    assert s["noRootsObject"].startswith("No drop folder is set · ")
    assert s["localOnly"].startswith("Local folder /app/local · ")
