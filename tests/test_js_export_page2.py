"""An export of a Models-page chart describes only what is on show (res-emax brief, section 7).

`export/figure.js` sets the export's legend context (`chart_panel.js`
`setExportHidden`) to the legend entries the reader switched off, then builds
the figure. Every exportable Page 2 builder of this suite must then leave out
each left-out entry together with every mark that belongs to it - its own
series and its companions (`<entry> · 95% interval`, `<entry> (clipped)`, a
hidden frame's catalogue marks, a connector drawn for a hidden end) - lay its
legend rows out without it, and print no canvas text naming it. With no
context (on screen, and once the export has cleared it) every builder returns
exactly what it returned before.

The recipe, per builder and recorded payload (screen and print tokens): build
the option with no context (A); then, for each legend entry N, under
`setExportHidden([N])` (B):

* B's legends list no N and mark N false in `selected`;
* no series of B is named N or starts with `N ` / `N·` (a companion);
* no graphic, custom-series text or category-axis label of B contains N;
* B's grid tops are never below A's, and the figure is never taller;
* after `setExportHidden(null)` the option is A again, value for value.

The payloads are those the other Node suites draw: the recorded
`tests/fixtures/payloads/perf_*.json` and `xgb_*.json`, and the catalogue
cards' static payloads from `catalog/select.js`. Skipped without `node`.
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
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const cp = await imp('panels/chart_panel.js');
const sel = await imp('catalog/select.js');
const perf = await imp('panels/perf_bins.js');
const cv = await imp('panels/xgb_cv.js');
const bin = await imp('panels/xgb_binary.js');
const imps = await imp('panels/xgb_importance.js');
const cat = await imp('panels/bench_catalog.js');
const ovl = await imp('panels/bench_overlap.js');
const diag = await imp('panels/bench_diagnostics.js');
const tri = await imp('panels/distill_triangle.js');
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

const api = { coord: (p) => [Number(p[0]), Number(p[1])], size: () => [10, 10] };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };
const SAMPLES = [-2.5, -0.25, 0, 0.5, 1, 6, 1500, 0.1, 100];
const entryName = (e) => String(e !== null && typeof e === 'object' ? e.name : e);

/* Every leaf of a rendered element, text included. */
function leaves(el, out = []) {
  if (!el) return out;
  if (el.type === 'group') { for (const c of el.children ?? []) leaves(c, out); return out; }
  out.push(el);
  return out;
}

/* A value with every function evaluated where it draws or prints, so two builds compare value for value. */
function canon(value, key = '', parent = null) {
  if (typeof value === 'function') {
    if (key === 'renderItem') {
      return (parent.data ?? []).map((d, i) => canon(value({ dataIndex: i, coordSys }, api)));
    }
    if (key === 'formatter' && parent && parent.__axis) {
      return (parent.__axis.data ?? SAMPLES).map((d, i) => String(value(d, i)));
    }
    if (key === 'formatter' && parent && parent.__series) {
      return (parent.__series.data ?? []).map((d, i) => String(value({ dataIndex: i, value: d })));
    }
    return '[fn]';
  }
  if (Array.isArray(value)) return value.map((v) => canon(v));
  if (value && typeof value === 'object') {
    const out = {};
    for (const k of Object.keys(value).sort()) {
      if (k.startsWith('__')) continue;
      out[k] = canon(value[k], k, value);
    }
    return out;
  }
  return value;
}

/* The option, its axis label and series tooltip formatters bound to their data. */
function canonOption(option) {
  const o = { ...option };
  const bind = (axes) => [].concat(axes ?? []).map((a) => ({ ...a, axisLabel: a.axisLabel ? { ...a.axisLabel, __axis: a } : a.axisLabel }));
  if (o.xAxis) o.xAxis = bind(o.xAxis);
  if (o.yAxis) o.yAxis = bind(o.yAxis);
  if (o.series) o.series = o.series.map((s) => ({ ...s, tooltip: s.tooltip ? { ...s.tooltip, __series: s } : s.tooltip }));
  return JSON.stringify(canon(o));
}

/* The texts drawn on the canvas: graphics, custom-series leaves and category-axis labels. */
function canvasTexts(option) {
  const out = [];
  for (const g of [].concat(option.graphic ?? [])) for (const l of leaves(g)) if (l.style?.text) out.push(String(l.style.text));
  for (const s of option.series ?? []) {
    if (typeof s.renderItem !== 'function') continue;
    (s.data ?? []).forEach((d, i) => {
      for (const l of leaves(s.renderItem({ dataIndex: i, coordSys }, api))) if (l?.style?.text) out.push(String(l.style.text));
    });
  }
  for (const a of [].concat(option.xAxis ?? [], option.yAxis ?? [])) {
    if (a.type !== 'category' || a.axisLabel?.show === false) continue;
    const f = a.axisLabel?.formatter;
    (a.data ?? []).forEach((d, i) => out.push(typeof f === 'function' ? String(f(d, i)) : String(d)));
  }
  return out;
}

/* The names every legend on show lists. */
function legendNames(option) {
  const out = [];
  for (const l of [].concat(option.legend ?? [])) {
    if (!l || l.show === false) continue;
    for (const d of l.data ?? []) if (!out.includes(entryName(d))) out.push(entryName(d));
  }
  return out;
}

const gridTops = (option) => [].concat(option.grid ?? []).map((g) => Number(g.top));

/* One builder on one payload: the recipe of the brief's section 7. */
function check(build, height = () => null) {
  cp.setExportHidden(null);
  const a = build();
  const aCanon = canonOption(a);
  const aHeight = height();
  const names = legendNames(a);
  const entries = [];
  for (const n of names) {
    cp.setExportHidden([n]);
    const b = build();
    const bHeight = height();
    const legends = [].concat(b.legend ?? []);
    cp.setExportHidden(null);
    const listed = legends.some((l) => (l.data ?? []).some((d) => entryName(d) === n));
    const markedOff = legends.length > 0 && legends.every((l) => l.selected?.[n] === false);
    const named = (b.series ?? []).map((s) => String(s.name ?? '')).filter((s) => s === n || s.startsWith(`${n} `) || s.startsWith(`${n}·`));
    cp.setExportHidden([n]);
    const texts = canvasTexts(b).filter((t) => t.includes(n));
    cp.setExportHidden(null);
    const ta = gridTops(a);
    const tb = gridTops(b);
    const higher = ta.length === tb.length ? tb.filter((t, i) => t > ta[i] + 1e-9).length
      : (Math.min(...tb) > Math.min(...ta) + 1e-9 ? 1 : 0);
    entries.push({ name: n, listed, markedOff, named, texts, higher, seriesA: (a.series ?? []).length, seriesB: (b.series ?? []).length,
      taller: aHeight !== null && bHeight !== null && bHeight > aHeight + 1e-9 });
  }
  const restored = canonOption(build()) === aCanon;
  return { names, entries, restored };
}

function cases() {
  const out = {};
  const W = { width: 760, height: 340 };
  for (const name of ['perf_two_energy', 'perf_two_angle', 'perf_xgb_energy', 'perf_xgb_angle']) {
    const p = load(name);
    for (const q of perf.perfQuantities(p)) {
      out[`perf_bins:${name}:${q.key}`] = check(() => perf.perfBinsOption(p, { quantity: q.key }, W));
    }
  }
  {
    // A provisional range a point overflows: '(clipped)' carets beside the bars and whiskers.
    const clipped = clone(load('perf_two_energy'));
    const y = clipped.by_momentum_bin.y_max.rmse;
    y.value = 10; y.provisional = true; y.n_overflow = 3; y.note = 'Provisional: no point reaches N = 15.';
    y.overflow = [{ series: 'absolute:a', bin: 3, n: 20, value: 13.54, lo: 11.5, hi: 15.3 }];
    out['perf_bins:clipped'] = check(() => perf.perfBinsOption(clipped, { quantity: 'rmse' }, W));
    out['perf_bins:clipped:narrow'] = check(() => perf.perfBinsOption(clipped, { quantity: 'rmse' }, { width: 321, height: 340 }));
  }
  for (const name of ['xgb_cv_momentum', 'xgb_cv_angle']) {
    const p = load(name);
    for (const width of [560, 321]) {
      out[`xgb_cv:${name}:${width}`] = check(() => cv.xgbCvOption(p, {}, { width, height: cv.cvLayout(cv.cvModel(p), width, null).height }),
        () => cv.cvLayout(cv.cvModel(p), width, null).height);
    }
  }
  {
    const p = load('xgb_binary');
    for (const width of [560, 321]) {
      out[`xgb_binary:${width}`] = check(() => bin.xgbBinaryOption(p, {}, { width, height: bin.binaryLayout(bin.binaryModel(p), width, null).height }),
        () => bin.binaryLayout(bin.binaryModel(p), width, null).height);
    }
    // A second interval method: three legend entries.
    const mover = clone(p);
    const ba = (mover.rates ?? []).find((r) => /balanced/i.test(String(r.key ?? r.label ?? '')));
    if (ba) { ba.method = 'mover'; ba.interval_label = '95% MOVER interval'; }
    out['xgb_binary:mover'] = check(() => bin.xgbBinaryOption(mover, {}, { width: 560, height: 330 }));
  }
  for (const name of ['xgb_importance_momentum', 'xgb_importance_angle']) {
    const p = load(name);
    for (const width of [1100, 321]) {
      const m = imps.importanceModel(p);
      out[`xgb_importance:${name}:${width}`] = check(() => imps.xgbImportanceOption(p, {}, { width, height: imps.importanceLayout(m, width, null).height }),
        () => imps.importanceLayout(imps.importanceModel(p), width, null).height);
    }
  }
  const builders = {
    'perf-catalog': [cat.benchCatalogOption, cat.plotHeight],
    'perf-overlap': [ovl.benchOverlapOption, ovl.plotHeight],
    'perf-diagnostics': [diag.benchDiagnosticsOption, diag.plotHeight],
    'distill-triangle': [tri.distillTriangleOption, tri.plotHeight],
  };
  for (const [card, [option, plotHeight]] of Object.entries(builders)) {
    for (const species of ['proton', 'muon', 'all']) {
      for (const task of ['segmentation', 'angle', 'energy']) {
        const p = sel.catalogPayload(card, { species, task });
        const opts = card === 'distill-triangle' ? { species, task } : {};
        for (const width of [1100, 321]) {
          out[`${card}:${species}:${task}:${width}`] = check(() => option(p, opts, { width, height: plotHeight(p, opts, width) }).option,
            () => plotHeight(p, opts, width));
        }
      }
    }
  }
  return out;
}

const out = { screen: cases() };
Object.assign(scale.THEME, PRINT_TOKENS);
out.print = cases();
scale.restoreScreenTheme();
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    """Run the harness once; every test reads its part."""
    args = json.dumps([JS.as_uri(), str(FIXTURES)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _cases(out: dict):
    for theme in ("screen", "print"):
        for key, case in out[theme].items():
            yield f"{theme}:{key}", case


def _entries(out: dict):
    for label, case in _cases(out):
        for entry in case["entries"]:
            yield label, entry


BUILDERS = ["perf_bins", "xgb_cv", "xgb_binary", "xgb_importance",
            "perf-catalog", "perf-overlap", "perf-diagnostics", "distill-triangle"]


@pytest.mark.parametrize("builder", BUILDERS)
def test_every_owned_builder_is_exercised_with_legend_entries(out, builder):
    cases = [c for label, c in _cases(out) if label.split(":")[1] == builder]
    assert cases, builder
    assert sum(len(c["names"]) for c in cases) > 0, builder


def test_a_left_out_entry_is_not_listed_and_is_marked_off(out):
    bad = [(label, e["name"]) for label, e in _entries(out) if e["listed"] or not e["markedOff"]]
    assert not bad, bad[:10]


def test_no_series_or_companion_of_a_left_out_entry_is_drawn(out):
    bad = [(label, e["name"], e["named"]) for label, e in _entries(out) if e["named"]]
    assert not bad, bad[:10]


def test_a_left_out_entry_leaves_fewer_series(out):
    bad = [(label, e["name"]) for label, e in _entries(out) if e["seriesB"] >= e["seriesA"]]
    assert not bad, bad[:10]


def test_no_canvas_text_names_a_left_out_entry(out):
    bad = [(label, e["name"], e["texts"][:3]) for label, e in _entries(out) if e["texts"]]
    assert not bad, bad[:10]


def test_the_legend_rows_and_figure_never_grow(out):
    bad = [(label, e["name"]) for label, e in _entries(out) if e["higher"] or e["taller"]]
    assert not bad, bad[:10]


def test_clearing_the_context_restores_the_screen_option(out):
    bad = [label for label, case in _cases(out) if not case["restored"]]
    assert not bad, bad


def test_perf_bins_companions_are_left_out_with_their_series(out):
    case = out["print"]["perf_bins:clipped"]
    assert case["names"], case
    # Every companion name is gone, the whiskers and the carets included (the recipe asserts none starts with N).
    for e in case["entries"]:
        assert not e["named"]
        assert e["seriesA"] - e["seriesB"] >= 2, e


def test_a_hidden_frame_takes_its_catalogue_row_label_and_marks(out):
    entries = {e["name"]: e for e in out["print"]["perf-catalog:proton:segmentation:1100"]["entries"]}
    assert entries, "no legend entries on the proton catalogue card"
    for name, e in entries.items():
        assert not e["texts"], (name, e["texts"])
