"""An entry whose legend name is chosen by width is left out of an export under the name it takes there.

Review R2-3 (res-emax, 2026-11-17): the Gain Feature Importance card names its envelope in full on a wide card
(about 1100 px) and in short at a single-column figure's 321 px (``xgb_importance.js`` ``envelopeLegend``, a
``fitName`` choice). Switched off on the screen's legend under its long name, it came back in the export under its
short one, with both its series and its legend entry. ``chart_panel.js`` ``legendAlias`` adds the name taken at the
export's width to the export's legend context whenever any other name of the same entry is in it; the three
name-choosing functions call it (the importance envelope, the cross-validation interval and the binary card's other
interval). On screen there is no context, so nothing changes.

Each case builds the option as ``export/figure.js`` does: under the print tokens, ``setExportHidden`` with the
screen's name, then the builder at the export's width; and checks that no series, legend entry or text keeps the
entry under any of its names, that the other entries are untouched, and that with no context the option is today's.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
FIXTURES = ROOT / "tests" / "fixtures" / "payloads"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
globalThis.window = globalThis;
const scale = await import(`${jsRoot}/scale.js`);
const { PRINT_TOKENS } = await import(`${jsRoot}/export/tokens.js`);
const cp = await import(`${jsRoot}/panels/chart_panel.js`);
const imp = await import(`${jsRoot}/panels/xgb_importance.js`);
const cv = await import(`${jsRoot}/panels/xgb_cv.js`);
const bin = await import(`${jsRoot}/panels/xgb_binary.js`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const legendNames = (o) => [o.legend].flat().filter(Boolean).flatMap((l) => (l.data ?? []).map((d) => String(d?.name ?? d)));
const seriesNames = (o) => (o.series ?? []).map((s) => s.name);
const texts = (o) => JSON.stringify(o.graphic ?? []);
const plain = (fn) => JSON.stringify(fn());
// Under the print tokens, with `hidden` left out, the option at the export's width: as export/figure.js builds it.
const exported = (hidden, fn) => {
  Object.assign(scale.THEME, PRINT_TOKENS);
  cp.setExportHidden(hidden);
  try {
    const option = fn();
    return { legend: legendNames(option), series: seriesNames(option), texts: texts(option),
      context: [...(cp.hiddenEntries() ?? [])] };
  } finally {
    cp.setExportHidden(null);
    scale.restoreScreenTheme();
  }
};
const out = {};
for (const name of ['xgb_importance_momentum', 'xgb_importance_angle']) {
  const p = load(name);
  const m = imp.importanceModel(p);
  const wide = imp.envelopeLegend(m, 1100);
  const narrowName = imp.envelopeLegend(m, 321);
  const h = imp.importanceLayout(m, 321, null).height;
  const build = () => imp.xgbImportanceOption(p, {}, { width: 321, height: h });
  out[name] = { wide, narrow: narrowName, before: plain(build), shown: exported([], build),
    hidden: exported([wide], build), after: plain(build) };
}
for (const name of ['xgb_cv_momentum', 'xgb_cv_angle']) {
  const p = load(name);
  const m = cv.cvModel(p);
  const wide = cv.intervalLegend(m, 1100);
  const narrowName = cv.intervalLegend(m, 120);
  const h = cv.cvLayout(m, 120, null).height;
  const build = () => cv.xgbCvOption(p, {}, { width: 120, height: h });
  out[name] = { wide, narrow: narrowName, before: plain(build), shown: exported([], build),
    hidden: exported([wide], build), after: plain(build) };
}
{
  const p = load('xgb_binary');
  const m = bin.binaryModel ? bin.binaryModel(p) : null;
  out.binary = { model: Boolean(m) };
  if (m) {
    const wide = bin.otherIntervalLegend(m, 1100);
    const narrowName = bin.otherIntervalLegend(m, 120);
    out.binary = { ...out.binary, wide, narrow: narrowName };
  }
}
// The helper itself: nothing without a context; the chosen name joins it only when another name is in it.
cp.setExportHidden(['Long name']);
cp.legendAlias(['Long name', 'Short'], 'Short');
const joined = [...cp.hiddenEntries()];
cp.setExportHidden(['Other']);
cp.legendAlias(['Long name', 'Short'], 'Short');
const untouched = [...cp.hiddenEntries()];
cp.setExportHidden(null);
cp.legendAlias(['Long name', 'Short'], 'Short');
out.helper = { joined, untouched, screen: cp.hiddenEntries() };
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result() -> dict:
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_helper_adds_the_chosen_name_only_when_another_name_of_the_entry_is_left_out(result):
    h = result["helper"]
    assert h["joined"] == ["Long name", "Short"]
    assert h["untouched"] == ["Other"]
    assert h["screen"] is None


@pytest.mark.parametrize("name", ["xgb_importance_momentum", "xgb_importance_angle", "xgb_cv_momentum", "xgb_cv_angle"])
def test_an_entry_hidden_under_its_wide_name_is_left_out_of_a_narrow_export(result, name):
    got = result[name]
    wide, narrow = got["wide"], got["narrow"]
    # Shown, the entry is in the export under the name the export's width gives it.
    assert narrow in got["shown"]["legend"] and narrow in got["shown"]["series"], got["shown"]
    # Hidden on the screen under its wide name: under neither name anywhere in the export.
    hidden = got["hidden"]
    for n in {wide, narrow}:
        assert n not in hidden["legend"] and n not in hidden["series"], (n, hidden)
    assert narrow in hidden["context"]
    # The other entries are untouched.
    assert [n for n in got["shown"]["legend"] if n != narrow] == hidden["legend"]
    # No context, no change: the option is today's before and after.
    assert got["before"] == got["after"]


def test_the_cases_really_differ_in_name(result):
    # The importance envelope's full label does not fit a single column: the case is the one the review found.
    for name in ("xgb_importance_momentum", "xgb_importance_angle"):
        assert result[name]["wide"] != result[name]["narrow"], result[name]
