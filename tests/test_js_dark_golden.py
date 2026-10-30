"""The dark theme's golden: every colour, ramp, option and drawer sentence it produces today, as hashes.

The light theme is an addition, and dark mode must stay byte-identical while it
is built. This file is what makes that checkable. It was recorded at the commit
before any theme work (72e4ec6), under the default `THEME` (the dark screen
theme), and every later change is held to it:

    CALOSRV_WRITE_DARK_GOLDEN=1 .venv/bin/python -m pytest -q tests/test_js_dark_golden.py

regenerates `tests/golden/dark_theme.json`, and only a change of dark mode made
on purpose may do so (the convention of `CALOSRV_WRITE_PAYLOAD_FIXTURES`).

One Node script runs everything the other `test_js_*` files exercise, on the
payloads `tests/test_payload_fixtures.py` recorded (`tests/fixtures/payloads/`),
and prints a table of SHA-256 digests, one per case:

* **THEME.** Every key and value of `scale.js` `SCREEN_THEME`, stored as a
  key-to-value map and not as a hash, so a failure names the token. A later
  commit may add keys; none may change or disappear.
* **Ramps.** The lookup table of every palette; `rampTable` for every sequential
  palette on eight scales (the server's own lab, relative, Grad-CAM, event,
  signed-log and diverging-linear shapes, and every scale block the fixtures
  carry), legible and full, signed and not; `visualMap` with its formatter
  called; `legibleSpan`, `rampMidLabel`, `decode.codeTable`; the colour helpers
  of `chart_panel.js` (`seriesStops`, `legibleRamp`, `legibleRange`,
  `legibleOpacity`) and of `palette.js` (`categoricalStops`, `colorStops`,
  `qualitativeStops`).
* **Options.** Every pure option builder the existing harnesses drive (the
  physics panels, the Models panels, the four XGBoost panels, the energy panel,
  the projection panel on its raster, the voxel options), as canonical JSON, and
  the output of every `renderItem`, tooltip, axis and label formatter the option
  carries, called with the identity coordinate map. Most are also built under
  the print tokens (the case id ends in `@print`), which the light theme must
  not move either.
* **Words.** The drawer-note builders on every payload they accept, their
  constants (`rampStartNote`, `LEGIBLE_RAMP_NOTE`), the frame captions, and the
  Methodology figures' node trees for the screen and the paper medium.

A case is the hash of its canonical JSON: object keys sorted recursively,
functions dropped, numbers as JavaScript prints them. The hash records
behaviour, never code, so a refactor that reorders an object literal or
rewrites a helper passes, and a changed colour, label or number fails by the
case that carries it. The palette lists (`SEQUENTIAL`, `DIVERGING`,
`QUALITATIVE`) are fixed in the script, so a palette added later is no drift
here. The case-id set must match exactly.

The run is deterministic: no clock, no randomness, text widths from the same
estimate `textfit.js` uses without a DOM, and the locale and time zone pinned
(`formatNumber` calls `toLocaleString`). When a case drifts,
`CALOSRV_DARK_GOLDEN_DUMP=<dir>` writes every case's canonical JSON there, to
diff against a dump of the golden commit. Skipped without `node`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "calosrv" / "static" / "js"
FIXTURES = ROOT / "tests" / "fixtures" / "payloads"
GOLDEN_DIR = ROOT / "tests" / "golden"
GOLDEN = GOLDEN_DIR / "dark_theme.json"
NODE = shutil.which("node")
WRITE = os.environ.get("CALOSRV_WRITE_DARK_GOLDEN") == "1"
DUMP = os.environ.get("CALOSRV_DARK_GOLDEN_DUMP", "")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: The families of cases the golden must hold: a harness that quietly stops
#: recording one would otherwise pass against a golden recorded the same way.
FAMILIES = [
    "theme", "palette", "scale", "decode", "chart_panel", "tooltip",
    "physics/profile", "physics/response", "physics/grid", "physics/distribution", "physics/correlation",
    "physics/statistics", "physics/energy", "physics/projection", "physics/marks",
    "models/perf", "models/hist2d", "models/residual", "models/hist", "models/corr", "models/rates", "models/table",
    "xgb/cv", "xgb/binary", "xgb/tree", "xgb/importance", "xgb/variant",
    "voxels/event", "voxels/ensemble", "voxels/crop", "voxels/notes",
    "notes/profile", "notes/response", "notes/grid", "notes/energy", "notes/distribution", "notes/correlation",
    "notes/statistics", "notes/models_perf", "notes/models_pred", "notes/models_features", "notes/xgb", "notes/voxels",
    "text/projection", "text/frame_views", "methodology/exhibit",
]

_SCRIPT = r"""
import fs from 'node:fs';
import crypto from 'node:crypto';

const [jsRoot, fixtureDir, goldenDir, dumpDir] = JSON.parse(process.argv.at(-1));
const imp = (p) => import(`${jsRoot}/${p}`);
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

/* ---- modules (imported before any fake global exists) ---------------------- */
const scale = await imp('scale.js');
const palette = await imp('palette.js');
const decode = await imp('decode.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const cp = await imp('panels/chart_panel.js');
const tip = await imp('panels/tooltip.js');
const marks = await imp('panels/marks.js');
const prof = await imp('panels/profile.js');
const resp = await imp('panels/response.js');
const grid = await imp('panels/response_grid.js');
const dist = await imp('panels/distribution.js');
const corr = await imp('panels/correlation.js');
const stats = await imp('panels/statistics.js');
const perf = await imp('panels/perf_bins.js');
const h2 = await imp('panels/hist2d.js');
const rates = await imp('panels/rates.js');
const ft = await imp('panels/feature_table.js');
const cv = await imp('panels/xgb_cv.js');
const bin = await imp('panels/xgb_binary.js');
const tree = await imp('panels/xgb_tree.js');
const imps = await imp('panels/xgb_importance.js');
const energyMod = await imp('panels/energy.js');
const projMod = await imp('panels/projection.js');
const overlays = await imp('panels/canonical_overlays.js');
const cells = await imp('event_cells.js');
const fv = await imp('frame_views.js');
const pn = await imp('panel_notes.js');
const mn = await imp('models_notes.js');
const vn = await imp('voxel_notes.js');
const xn = await imp('xgb_notes.js');
const v = await imp('voxels.js');
const exhibits = await imp('methodology/exhibits.js');
const exportMod = await imp('methodology/export.js');

const { THEME } = scale;

/* ---- canonical JSON, hashes, the case table --------------------------------- */

const BIG_TYPED = 4096;
const sha = (text) => crypto.createHash('sha256').update(text).digest('hex');

/**
 * Canonical JSON of any value: object keys sorted recursively, functions and
 * undefined dropped (null inside an array), numbers as JavaScript prints them
 * (-0, NaN and the infinities spelled out, since JSON has no word for them),
 * typed arrays as arrays (a long one as its length and digest), Maps and Sets
 * as tagged lists, an object with `toJSON` as what that returns.
 */
function canon(value, stack = []) {
  switch (typeof value) {
    case 'undefined': case 'function': case 'symbol': return undefined;
    case 'boolean': return value ? 'true' : 'false';
    case 'bigint': return `"${value}n"`;
    case 'string': return JSON.stringify(value);
    case 'number':
      if (Number.isNaN(value)) return '"NaN"';
      if (value === Infinity) return '"Infinity"';
      if (value === -Infinity) return '"-Infinity"';
      return Object.is(value, -0) ? '"-0"' : String(value);
    default: break;
  }
  if (value === null) return 'null';
  if (stack.includes(value)) return '"[cycle]"';
  stack.push(value);
  let out;
  if (ArrayBuffer.isView(value) && !(value instanceof DataView)) {
    if (value.length > BIG_TYPED) {
      const bytes = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
      out = `{"__typed":"${value.constructor.name}","len":${value.length},"sha256":"${sha(Buffer.from(bytes))}"}`;
    } else {
      out = `{"__typed":"${value.constructor.name}","v":[${Array.from(value, (x) => canon(x, stack)).join(',')}]}`;
    }
  } else if (Array.isArray(value)) {
    out = `[${value.map((x) => canon(x, stack) ?? 'null').join(',')}]`;
  } else if (value instanceof Map) {
    out = `{"__map":[${[...value].map(([k, x]) => `[${canon(k, stack) ?? 'null'},${canon(x, stack) ?? 'null'}]`).join(',')}]}`;
  } else if (value instanceof Set) {
    out = `{"__set":[${[...value].map((x) => canon(x, stack) ?? 'null').join(',')}]}`;
  } else if (typeof value.toJSON === 'function') {
    out = canon(value.toJSON(), stack) ?? 'null';
  } else {
    const parts = [];
    for (const key of Object.keys(value).sort()) {
      const c = canon(value[key], stack);
      if (c !== undefined) parts.push(`${JSON.stringify(key)}:${c}`);
    }
    out = `{${parts.join(',')}}`;
  }
  stack.pop();
  return out;
}

const cases = {};
function put(id, value) {
  if (id in cases) throw new Error(`duplicate case ${id}`);
  const text = canon(value) ?? 'null';
  cases[id] = sha(text);
  if (dumpDir) fs.writeFileSync(`${dumpDir}/${id.replace(/[^A-Za-z0-9_.@-]+/g, '__')}.json`, text);
}

const attempt = (fn) => {
  try { return { value: fn() }; } catch (e) { return { error: String(e?.message ?? e) }; }
};

/* ---- exercising every function an option carries ---------------------------- */

const api = { coord: (p) => [Number(p[0]), Number(p[1])], value: (i) => 0, size: () => [1, 1] };
const coordSys = { x: 0, y: 0, width: 100, height: 100 };
const SAMPLES = [-2.5, -0.25, 0, 0.5, 1e-5, -3.14159, 1e-10, 12345, -1, 1, 0.975, -Math.PI, -Math.PI / 2, Math.PI / 2, Math.PI, -3000, 250.4, 4000];
const PER_SERIES_CAP = 5000;

/**
 * The outputs of every renderItem, tooltip, label and axis formatter in an
 * option, in a stable order, keyed by their path. renderItem and tooltips are
 * called per data item with the identity coordinate map; axis, legend and
 * visual-map formatters on a fixed list of values; the top-level tooltip with
 * one parameter per series. Functions that are neither (a position, a colour
 * callback) are not called.
 */
function exercise(option) {
  const calls = {};
  const seriesList = [].concat(option.series ?? []);
  const record = (path, fn, ...argsList) => {
    calls[path] = argsList.map((args) => attempt(() => fn(...args)));
  };
  const itemParam = (s, i, k) => {
    const datum = s.data?.[i];
    const value = Array.isArray(datum) ? datum : (datum && typeof datum === 'object' ? datum.value : datum);
    return { dataIndex: i, value, data: datum, seriesIndex: k, seriesName: s.name, name: datum?.name ?? s.name,
      componentType: 'series', seriesType: s.type, color: '#abcdef', marker: '' };
  };
  const visit = (node, path, ctx) => {
    if (Array.isArray(node)) {
      node.forEach((x, i) => {
        if (!x || typeof x !== 'object') return;
        const here = `${path}[${i}]`;
        let next = ctx;
        if (path === 'option.series') next = { ...ctx, series: { s: x, k: i }, datum: undefined };
        else if (/^option\.series\[\d+\]\.data$/.test(path)) next = { ...ctx, datum: i };
        visit(x, here, next);
      });
      return;
    }
    for (const key of Object.keys(node).sort()) {
      const x = node[key];
      const here = `${path}.${key}`;
      if (typeof x === 'function') {
        if (key === 'renderItem') {
          const n = Math.min(PER_SERIES_CAP, node.data?.length ?? 0);
          calls[here] = [];
          for (let i = 0; i < n; i += 1) calls[here].push(attempt(() => x({ dataIndex: i, coordSys }, api)));
        } else if (key === 'formatter' && ctx.series) {
          const { s, k } = ctx.series;
          if (ctx.datum !== undefined) {
            record(here, x, [itemParam(s, ctx.datum, k)]);
          } else {
            const n = Math.min(PER_SERIES_CAP, s.data?.length ?? 0);
            calls[here] = [];
            for (let i = 0; i < n; i += 1) calls[here].push(attempt(() => x(itemParam(s, i, k))));
          }
        } else if (key === 'formatter' && path === 'option.tooltip') {
          calls[here] = [];
          seriesList.forEach((s, k) => {
            calls[here].push(attempt(() => x(itemParam(s, 0, k))));
            calls[here].push(attempt(() => x([itemParam(s, 0, k)])));
          });
          calls[here].push(attempt(() => x({ dataIndex: 0, value: [1, 2] })));
        } else if (key === 'formatter') {
          // axis, legend, visual map: numbers, and the category names of the axis
          const names = [].concat(node.data ?? []).filter((d) => typeof d === 'string').slice(0, 30);
          record(here, x, ...SAMPLES.map((q, j) => [q, j]), ...names.map((q, j) => [q, j]));
        }
        continue;
      }
      if (x && typeof x === 'object') visit(x, here, ctx);
    }
  };
  // Series data can be thousands of points: only series and the items that carry their own functions
  // matter, so descend into `data` only for datum-level formatters.
  visit(option, 'option', {});
  return calls;
}

/** Record one chart option: the option as canonical JSON, and what its functions return. */
function optionCase(id, option) {
  put(id, { option, calls: exercise(option) });
}

/** Run `make` under the screen theme and under the print tokens, recording both. */
function both(id, make, record = (id2, out) => optionCase(id2, out)) {
  record(id, make());
  Object.assign(THEME, PRINT_TOKENS);
  try {
    record(`${id}@print`, make());
  } finally {
    scale.restoreScreenTheme();
  }
}

/* ======================================================================== */
/*  a. THEME                                                                */
/* ======================================================================== */

const themeMap = {};
for (const key of Object.keys(scale.SCREEN_THEME).sort()) themeMap[key] = JSON.parse(canon(scale.SCREEN_THEME[key]));
put('theme/active_equals_screen', Object.keys(scale.SCREEN_THEME).sort().map((k) => [k, canon(THEME[k]) === canon(scale.SCREEN_THEME[k])]));
put('theme/axis_padding', [scale.axisPadding(), scale.axisPadding({ ramp: true }), scale.axisPadding({ wideRamp: true })]);

/* ======================================================================== */
/*  b. ramps                                                                */
/* ======================================================================== */

// The palette names of this commit, fixed: a later palette is a new case of its own, never a drift here.
const SEQUENTIAL = ['viridis', 'cividis', 'plasma', 'turbo'];
const DIVERGING = ['puor', 'puor_screen', 'puor_screen_linear'];
const QUALITATIVE = ['set2', 'dark2', 'species', 'species_print'];

for (const name of [...SEQUENTIAL, ...DIVERGING]) {
  put(`palette/table/${name}`, palette.lookupTable(name));
  put(`palette/colorStops/${name}`, [palette.colorStops(name), palette.colorStops(name, 5), palette.colorStops(name, 49),
    palette.colorStops(name, 24, (t) => Math.min(1, t * 3))]);
}
for (const name of SEQUENTIAL) {
  put(`palette/categorical/${name}`, [1, 2, 3, 4, 5, 8, 12, 19, 20].map((n) => [
    palette.categoricalStops(name, n), palette.categoricalStops(name, n, THEME.categorical),
    palette.categoricalStops(name, n, { min: 0.1, max: 0.9 })]));
}
for (const name of QUALITATIVE) {
  put(`palette/qualitative/${name}`, [1, 2, 3, 4, 5, 6, 7, 8].map((n) => attempt(() => palette.qualitativeStops(name, n))));
}
put('palette/constants', { qualitative: palette.QUALITATIVE, checked: palette.QUALITATIVE_CHECKED, anchors: palette.PUOR_ANCHORS,
  card: palette.SCREEN_CARD });
put('palette/contrast', [[[28, 33, 40], [255, 255, 255]], [[0, 0, 0], [255, 255, 255]], [[68, 1, 84], [28, 33, 40]],
  [[253, 231, 37], [28, 33, 40]], [[179, 88, 6], [28, 33, 40]]].map(([a, b]) => [palette.contrast(a, b), palette.luminance(a)]));

// Scales the way the server builds them (calosrv/encode/scale.py `as_dict`, the fixtures' own blocks).
const SCALES = {
  lab_gev_log: { scale: 'log10', vmin: -6.0, vmax: 0.0, unit: 'GeV', mode: 'decades', locked: true, global_vmax: 1.0,
    clipped_low: 0, clipped_high: 0, empty_cells: 10 },
  rel_au_log_tapered: { scale: 'log10', vmin: -3.0, vmax: 0.0, unit: 'a.u.', mode: 'relative', locked: false,
    global_vmax: 1.58e-6, clipped_low: 242, empty_cells: 3945, rho_ref: 1.58e-6, rho_unit: 'GeV/mm^2/event',
    decades: 3.0, norm: 'selection', floor: 'transparent', floor_ratio: 0.001 },
  gradcam_linear: { scale: 'linear', vmin: 0.0, vmax: 1.0, unit: 'attention', mode: 'fixed', locked: true, global_vmax: 1.0,
    clipped_low: 0, clipped_high: 0, empty_cells: 0, quantity: 'gradcam' },
  event_gev_mm2: { scale: 'log10', vmin: -9.0, vmax: -5.0, unit: 'GeV/mm^2', mode: 'percentile', locked: true,
    global_vmax: 1e-5, clipped_low: 5, clipped_high: 0, empty_cells: 0, quantity: 'energy_density' },
  signed_log: { scale: 'signed_log10', vmin: -3.0, vmax: 0.0, unit: 'a.u.', mode: 'relative', locked: false,
    floor: 'transparent', floor_ratio: 0.001, quantity: 'shapcam_energy', diverging: true, split_code: 129 },
  shapcam_linear: { scale: 'linear', vmin: -1.0, vmax: 1.0, unit: 'attribution', mode: 'fixed', locked: true,
    global_vmax: 1.0, quantity: 'shapcam', diverging: true },
  gradcam_energy: { scale: 'log10', vmin: -3.0, vmax: 0.0, unit: 'a.u.', mode: 'relative', floor: 'transparent',
    floor_ratio: 0.001, quantity: 'gradcam_energy' },
  voxel_gev_mm3: { scale: 'log10', vmin: -10.7, vmax: -6.27, unit: 'GeV/mm^3', mode: 'percentile', locked: true,
    quantity: 'energy_density', floor_density: 1.9e-11 },
};
// Every distinct scale block the recorded payloads carry.
{
  const found = {};
  const walk = (o, where) => {
    if (Array.isArray(o)) { o.slice(0, 4).forEach((x, i) => walk(x, `${where}[${i}]`)); return; }
    if (!o || typeof o !== 'object') return;
    if (o.scale && typeof o.scale === 'object' && typeof o.scale.scale === 'string' && o.scale.scale !== 'categorical'
        && 'vmin' in o.scale) {
      const key = canon(o.scale);
      if (!(key in found)) found[key] = { where, scale: o.scale };
    }
    for (const [k, x] of Object.entries(o)) if (k !== 'data') walk(x, `${where}/${k}`);
  };
  for (const file of fs.readdirSync(fixtureDir).sort()) {
    if (!file.endsWith('.json')) continue;
    walk(JSON.parse(fs.readFileSync(`${fixtureDir}/${file}`, 'utf8')), file.replace('.json', ''));
  }
  const dedup = Object.values(found);
  dedup.forEach((entry, i) => { SCALES[`fixture_${String(i).padStart(2, '0')}_${entry.where.replace(/[^A-Za-z0-9]+/g, '_')}`] = entry.scale; });
}
put('scale/names', Object.keys(SCALES));

const RAMP_METRICS = [{}, { width: 600, reservedBottom: 40 }, { width: 120 }];
for (const [sname, sc] of Object.entries(SCALES)) {
  put(`scale/meta/${sname}`, {
    diverging: scale.isDiverging(sc), fades: scale.fadesAtFloor(sc), floorExp: scale.floorExponent(sc), floorLabel: scale.floorLabel(sc),
    title: scale.rampTitleText(sc), unit: scale.unitSuffix(sc.unit), mid: RAMP_METRICS.map((m) => scale.rampMidLabel(sc, m)),
    rampTitle: RAMP_METRICS.map((m) => scale.rampTitle(sc, m)),
    notes: SEQUENTIAL.map((p) => pn.rampStartNote(sc, p)),
  });
  for (const pal of SEQUENTIAL) {
    const ramp = scale.rampPalette(sc, pal);
    const tables = {};
    const spans = {};
    for (const legible of [true, false]) {
      spans[legible] = scale.legibleSpan(sc, ramp, { legible });
      for (const signed of [false, true]) tables[`legible=${legible},signed=${signed}`] = scale.rampTable(sc, ramp, { legible, signed });
    }
    spans.noFade = scale.legibleSpan(sc, ramp, { fadeDecades: 0 });
    tables.noFade = scale.rampTable(sc, ramp, { fadeDecades: 0 });
    put(`scale/ramp/${sname}/${pal}`, { ramp, tables, spans, mid: scale.rampMidLabel(sc), defaultTable: scale.rampTable(sc, ramp) });
    const vmOpts = [{}, { bottomInset: 20, seriesIndex: 2 }, { legible: false }, { signed: true }, { legible: false, signed: true }];
    const vms = vmOpts.map((o) => {
      const vm = scale.visualMap(sc, ramp, o);
      const f = vm.formatter;
      const calls = typeof f === 'function' ? [vm.min, vm.max, (vm.min + vm.max) / 2, -1, -0.5, 0, 0.5, 1, -3, -2.5, -6.0, 1e-3].map((x) => attempt(() => f(x))) : null;
      return { vm, calls };
    });
    put(`scale/visualMap/${sname}/${pal}`, vms);
    both(`scale/visualMap_print/${sname}/${pal}`, () => scale.visualMap(sc, scale.rampPalette(sc, pal)),
      (id, vm) => put(id, { vm, calls: typeof vm.formatter === 'function' ? [vm.min, vm.max, 0, 0.5].map((x) => attempt(() => vm.formatter(x))) : null,
        table: scale.rampTable(sc, scale.rampPalette(sc, pal)), span: scale.legibleSpan(sc, scale.rampPalette(sc, pal)),
        mid: scale.rampMidLabel(sc), title: scale.rampTitle(sc, { width: 600 }) }));
  }
}

// decode.codeTable on every payload that carries codes: the tests' stand-ins and the fixtures'.
{
  const CODES = {
    canonical: { scale: SCALES.rel_au_log_tapered, empty_code: 0, below_code: 1, min_code: 2, max_code: 255 },
    lab: { scale: SCALES.lab_gev_log, empty_code: 0, min_code: 1, max_code: 255 },
    attention: { scale: SCALES.gradcam_linear, empty_code: 0, below_code: 1, min_code: 2, max_code: 255 },
    shap_linear: { scale: SCALES.shapcam_linear, empty_code: 0, below_code: 1, min_code: 2, max_code: 255 },
    signed_log: { scale: SCALES.signed_log, empty_code: 0, below_code: 1, min_code: 2, max_code: 255, split_code: 129 },
    gradcam_energy: { scale: SCALES.gradcam_energy, empty_code: 0, below_code: 1, min_code: 2, max_code: 255 },
    event: { scale: SCALES.event_gev_mm2, empty_code: 0, below_code: 1, min_code: 2, max_code: 255 },
  };
  const walk = (o, where) => {
    if (Array.isArray(o)) { o.slice(0, 3).forEach((x, i) => walk(x, `${where}[${i}]`)); return; }
    if (!o || typeof o !== 'object') return;
    if (o.scale && typeof o.scale === 'object' && 'min_code' in o && 'max_code' in o) {
      CODES[`fixture_${where.replace(/[^A-Za-z0-9]+/g, '_')}`] = { scale: o.scale, empty_code: o.empty_code, below_code: o.below_code,
        min_code: o.min_code, max_code: o.max_code, split_code: o.split_code };
    }
    for (const [k, x] of Object.entries(o)) if (k !== 'data') walk(x, `${where}/${k}`);
  };
  for (const file of fs.readdirSync(fixtureDir).sort()) {
    if (file.endsWith('.json')) walk(JSON.parse(fs.readFileSync(`${fixtureDir}/${file}`, 'utf8')), file.replace('.json', ''));
  }
  for (const [name, payload] of Object.entries(CODES)) {
    for (const pal of SEQUENTIAL) {
      put(`decode/codeTable/${name}/${pal}`, {
        tapered: decode.codeTable(payload, pal, 0.5), step: decode.codeTable(payload, pal, 0),
        full: decode.codeTable(payload, pal, 0.5, { legible: false }), def: decode.codeTable(payload, pal),
        exponents: [0, 1, 2, 64, 128, 129, 200, 255].map((c) => attempt(() => decode.codeExponent(c, payload.scale, payload))),
        values: [0, 1, 2, 64, 128, 129, 255].map((c) => attempt(() => decode.dequantize(c, payload.scale, payload))),
      });
    }
  }
  both('decode/codeTable_print/lab_viridis', () => ({ lab: decode.codeTable(CODES.lab, 'viridis', 0.5), canon: decode.codeTable(CODES.canonical, 'viridis', 0),
    signed: decode.codeTable(CODES.signed_log, 'viridis', 0), lin: decode.codeTable(CODES.shap_linear, 'viridis', 0) }),
  (id, out) => put(id, out));
}

// chart_panel.js colour helpers
put('chart_panel/colours', {
  seriesStops: Object.fromEntries(SEQUENTIAL.map((p) => [p, [1, 2, 3, 4, 5, 8, 12, 19, 20].map((n) => cp.seriesStops(p, n))])),
  legibleRamp: Object.fromEntries(SEQUENTIAL.map((p) => [p, cp.legibleRamp(p)])),
  legibleRange: Object.fromEntries(SEQUENTIAL.flatMap((p) => ['#1c2128', '#ffffff', '#0d1117'].flatMap((bg) => [
    [`${p}|${bg}`, cp.legibleRange(p, bg)], [`${p}|${bg}|0.25-1`, cp.legibleRange(p, bg, { min: 0.25, max: 1 })],
    [`${p}|${bg}|0-0.5|4.5`, cp.legibleRange(p, bg, { min: 0, max: 0.5 }, 4.5)]]))),
  legibleOpacity: Object.fromEntries(['showerA', 'showerB', 'accent', 'muted', 'text', 'warn'].map((k) => [k,
    [0.1, 0.18, 0.45, 0.6, 0.7, 0.85, 1].map((w) => cp.legibleOpacity(THEME[k], w))])),
  blendOver: [['#58a6ff', 0.5], ['#f778ba', 0.25], ['#8b949e', 0.07]].map(([c, a]) => cp.blendOver(c, a)),
  rampColour: Object.fromEntries(SEQUENTIAL.map((p) => [p, [0, 0.25, 0.5, 0.75, 1, NaN].map((f) => cp.rampColour(cp.legibleRamp(p), f))])),
  inkOn: ['#440154', '#21908c', '#fde725', '#b35806', '#1c2128', '#ffffff'].map((c) => cp.inkOn(c)),
  showerColour: [cp.showerColour('a'), cp.showerColour('b'), cp.showerColour('a', 1)],
  rgbOf: ['#58a6ff', '#fff', 'rgb(1, 2, 3)', 'rgba(1,2,3,0.5)', 'nope'].map((c) => cp.rgbOf(c)),
  isPrint: cp.isPrintTheme(),
  sigFigs: [0, 1.2345, 12345678, 1e-7, -0.00123].map((x) => cp.sigFigs(x)),
});
both('chart_panel/colours_print', () => ({
  seriesStops: SEQUENTIAL.map((p) => cp.seriesStops(p, 6)), legibleRamp: SEQUENTIAL.map((p) => cp.legibleRamp(p)),
  legibleOpacity: ['showerA', 'showerB', 'accent', 'muted', 'text'].map((k) => [0.18, 0.45, 0.7].map((w) => cp.legibleOpacity(THEME[k], w))),
  isPrint: cp.isPrintTheme(), inkOn: ['#440154', '#21908c', '#fde725'].map((c) => cp.inkOn(c)),
  blend: cp.blendOver('#58a6ff', 0.5), sigFigs: cp.sigFigs(0.00123),
}), (id, out) => put(id, out));

// scale.js formatting helpers
put('scale/format', {
  sci: [-3.2e-5, -0.25, 0, 12345.6].map((x) => scale.formatSci(x)), number: [-1234.5, 0.0005, 3].map((x) => scale.formatNumber(x)),
  int: [-7, 1234567].map((x) => scale.formatInt(x)), percent: [-0.031, 0.5].map((x) => scale.formatPercent(x)),
  signed: [scale.formatSigned(-0.083, 3), scale.formatSigned(0.23, 2, { plus: true }), scale.formatSigned(-0.0001, 2)],
  bytes: [0, 1500, 5e9].map((x) => scale.formatBytes(x)), typo: scale.typographic('[-480, 480] and 1e-3'),
  axis: scale.spatialAxis('x', -500, 500).axisLabel.formatter(-480),
});
both('scale/spatialAxis', () => [scale.spatialAxis('x [mm]', -500, 500), scale.spatialAxis('z', 0, 1200, { onZero: false })],
  (id, out) => put(id, { out, calls: out.map((a) => SAMPLES.map((s) => a.axisLabel.formatter(s))) }));
put('scale/ramp_titles', { titles: scale.RAMP_TITLES, relative: scale.RAMP_TITLE_RELATIVE, contrast: scale.RAMP_CONTRAST, taper: scale.TAPER_LEGIBLE });
put('scale/tableStops', SEQUENTIAL.map((p) => [scale.tableStops(palette.lookupTable(p)), scale.tableStops(palette.lookupTable(p), 48, (t) => t),
  scale.tableStops(palette.lookupTable('puor_screen_linear'), 24, null, { arms: true })]));

/* ---- tooltip.js ------------------------------------------------------------ */
{
  const R = (left, top, right, bottom) => ({ left, top, right, bottom });
  const wide = { viewport: R(0, 0, 1600, 900), usable: R(330, 50, 1600, 900) };
  const panel1 = { chart: R(360, 110, 950, 440), plot: R(410, 130, 880, 400) };
  const opt = tip.tooltipOption();
  put('tooltip/option', { option: opt, withPosition: tip.tooltipOption(() => [0, 0]), formatterCalls: opt.formatter ? exercise({ tooltip: opt }) : null,
    consts: [tip.TOOLTIP_CLASS, tip.TOOLTIP_LAYER, tip.READOUT_GAP_PX, tip.EDGE_MARGIN_PX, tip.READOUT_SHARE, tip.PREFER_POINTER, tip.PREFER_OUTSIDE] });
  both('tooltip/option_print', () => tip.tooltipOption(), (id, o) => put(id, o));
  put('tooltip/place', [
    [[600, 250], [240, 73], 'pointer'], [[600, 250], [323, 115], 'pointer'], [[600, 250], [198, 150], undefined], [[600, 250], [363, 184], undefined],
  ].map(([pointer, size, prefer]) => tip.placeTooltip({ ...wide, ...panel1, pointer, size, ...(prefer ? { prefer } : {}) })));
  put('tooltip/plotBox', [tip.plotBoxFromGrid({ left: 60, top: 40, width: 400, height: 300 }, 600, 400),
    tip.plotBoxFromGrid([{ left: '10%', right: '10%', top: 20, bottom: '25%' }], 600, 400), tip.plotBoxFromGrid(null, 600, 400)]);
}

/* ======================================================================== */
/*  c. option builders                                                      */
/* ======================================================================== */

const W = { width: 640, height: 340 };

/* ---- profiles ------------------------------------------------------------- */
for (const name of ['profiles_single_w', 'profiles_single_native', 'profiles_two_w']) {
  const payload = load(name);
  for (const axis of ['depth', 'r']) {
    both(`physics/profile/${name}/${axis}`, () => prof.profileOption(payload, { axis }, { width: 640, height: 360 }));
    both(`physics/profile/${name}/${axis}/narrow`, () => prof.profileOption(payload, { axis }, { width: 321, height: 240 }));
  }
  put(`physics/profile/${name}/colours`, [prof.profileColours(payload), prof.profileColours({ ...payload, shower: 'a' })]);
}
{
  const base = load('profiles_single_w');
  const single = clone(base);
  single.ensemble = { ...single.ensemble, n_showers: 1, n_events: 1, label: 'single shower, not an ensemble', provisional: true };
  for (const m of single.marks) m.drawn = m.key === 'mean';
  for (const ax of Object.values(single.axes)) { ax.band = null; ax.envelope = null; ax.y.provisional = true; }
  optionCase('physics/profile/variant/single', prof.profileOption(single, { axis: 'depth' }, { width: 640, height: 360 }));
  const weak = clone(base);
  weak.ensemble = { ...weak.ensemble, n_showers: 2, n_events: 2, label: 'weak (N = 2)', dof_note: '1 d.o.f.', provisional: true };
  for (const ax of Object.values(weak.axes)) ax.y.provisional = true;
  optionCase('physics/profile/variant/weak', prof.profileOption(weak, { axis: 'r' }, { width: 640, height: 360 }));
  optionCase('physics/profile/variant/empty', prof.profileOption({ ...clone(base), ensemble: { ...base.ensemble, n_showers: 0 } }, { axis: 'depth' }, { width: 640, height: 360 }));
}

/* ---- B1, B2, resolution ----------------------------------------------------- */
for (const name of ['response_single_hits', 'response_single_events', 'response_two']) {
  const payload = load(name);
  for (const mode of ['b1', 'b2', 'resolution']) {
    both(`physics/response/${name}/${mode}`, () => resp.responseOption(payload, { mode }, { width: 640, height: 340 }));
  }
  both(`physics/response/${name}/ratio`, () => resp.responseOption(payload, { mode: 'resolution', quantity: 'response_ratio' }, { width: 640, height: 340 }));
  optionCase(`physics/response/${name}/showerA`, resp.responseOption(payload, { mode: 'b2', shower: 'a' }, { width: 640, height: 340 }));
  for (const mode of ['b1', 'b2', 'resolution']) {
    optionCase(`physics/response/${name}/${mode}/print_width`, resp.responseOption(payload, { mode }, { width: 321, height: 300 }));
  }
}
{
  const strip = clone(load('response_single_hits'));
  const s = strip.b1.series[0];
  s.draw = 'strip'; s.histogram = null; s.n = 6;
  s.strip = { values: [0.2, 0.5, 0.9, 1.1, 1.7, 2.6], n_shown: 6, truncated: false };
  s.message = 'N = 6: below the histogram floor; the events and the summary marks are drawn.';
  s.fit = { ...s.fit, n: 6, sigma: 0.9, sigma_error: 0.2915, sigma_ci95: [0.5618, 2.2074], sigma_bias_factor: 0.9515, estimator: 'moments' };
  optionCase('physics/response/variant/strip', resp.responseOption(strip, { mode: 'b1' }, { width: 640, height: 340 }));
  put('notes/physics/variant/b1Strip', pn.responseNotes({ payload: strip, mode: 'b1' }));
  const prov = clone(load('response_single_hits'));
  prov.b2.y.provisional = true; prov.resolution.y.provisional = true;
  optionCase('physics/response/variant/provisional_b2', resp.responseOption(prov, { mode: 'b2' }, { width: 640, height: 340 }));
  optionCase('physics/response/variant/provisional_res', resp.responseOption(prov, { mode: 'resolution' }, { width: 640, height: 340 }));
  const one = clone(load('response_single_hits'));
  for (const ser of one.resolution.series) for (const b of ser.bins) { b.value = null; b.ci95 = null; b.n = 1; }
  optionCase('physics/response/variant/resEmpty', resp.responseOption(one, { mode: 'resolution' }, { width: 640, height: 340 }));
  put('notes/physics/variant/resEmpty', pn.responseNotes({ payload: one, mode: 'resolution' }));
  put('physics/response/b2Tips', load('response_two').b2.series[0].bins.slice(0, 3).map((b) => resp.b2Tip(b, 'Shower A')));
  put('physics/response/calInterval', resp.calibrationInterval(load('response_two').calibration.a));
}

/* ---- B3 --------------------------------------------------------------------- */
const B3 = ['b3_single_notebook', 'b3_single_bins', 'b3_events_bins', 'b3_two_truth'];
for (const name of B3) {
  const payload = load(name);
  put(`physics/grid/${name}/tables`, { rows: grid.responseGridRows(payload), table: grid.responseGridTable(payload), sparse: grid.responseGridSparse(payload),
    slices: grid.gridSlices(payload).map(({ slice, axis }) => ({ index: slice.index, label: slice.label, axis })),
    messages: payload.series.map((e) => [grid.seriesMessage(payload, e), grid.estimatorNote(payload, e)]) });
  both(`physics/grid/${name}/option`, () => grid.responseGridOption(payload, {}, { width: 760, height: null }));
  optionCase(`physics/grid/${name}/fixed`, grid.responseGridOption(payload, { shower: 'a' }, { width: 600, height: 380 }));
  optionCase(`physics/grid/${name}/narrow`, grid.responseGridOption(payload, {}, { width: 321, height: null }));
  put(`physics/grid/${name}/layout`, [grid.responseGridLayout(payload.slice_axes?.length ?? payload.series.length, 760, null, {}),
    grid.responseGridLayout(payload.series.length, 600, 380, {}), grid.responseGridLayout(16, 321, null, { legend: ['Shower A - truth', 'Shower B - truth'] })]);
}
put('physics/grid/sweep', [300, 330, 380].flatMap((height) => [300, 450, 600, 750, 900].flatMap((width) => [1, 2, 6, 10, 20].map((n) => {
  const L = grid.responseGridLayout(n, width, height, { legend: ['Shower - deposit'] });
  return { height, width, n, shown: L.shown, hidden: L.hidden, cells: L.cells.length, layoutHeight: L.height, noticeY: L.noticeY };
}))));
{
  const two = load('b3_two_truth');
  put('physics/grid/titles', { a: grid.responseGridOption(two, { shower: 'a' }, { width: 760, height: null }).graphic?.map((g) => g.style?.text),
    sparseA: grid.responseGridSparse(two, 'a'), hidden: grid.responseGridSparse(load('b3_single_bins'), 'both', { hidden: 4, shown: 6 }) });
  optionCase('physics/grid/variant/hidden_chart', grid.responseGridOption(load('b3_single_bins'), {}, { width: 450, height: 330 }));
  const empty = clone(two);
  empty.slice_axes = []; empty.series = [];
  optionCase('physics/grid/variant/empty', grid.responseGridOption(empty, {}, { width: 760, height: null }));
  const none = clone(load('b3_single_notebook'));
  none.series = none.series.map((e) => ({ ...e, draw: 'strip', histogram: null, curve: null, drives_scale: false }));
  optionCase('physics/grid/variant/noDensity', grid.responseGridOption(none, {}, { width: 760, height: null }));
}

/* ---- C4 distribution --------------------------------------------------------- */
for (const name of ['distribution_single_u', 'distribution_single_energy', 'distribution_single_phi', 'distribution_single_theta_hit',
  'distribution_events_p', 'distribution_two_p']) {
  const payload = load(name);
  for (const yScale of ['linear', 'log']) {
    both(`physics/distribution/${name}/${yScale}`, () => dist.distributionOption(payload, { palette: 'viridis', yScale }, { width: 640, height: 340 }));
  }
  for (const palette_ of ['cividis', 'turbo']) {
    optionCase(`physics/distribution/${name}/${palette_}`, dist.distributionOption(payload, { palette: palette_, yScale: 'linear' }, { width: 640, height: 340 }));
  }
  put(`physics/distribution/${name}/readout`, attempt(() => [0, 1].map((i) => dist.distributionReadout(payload, ['#58a6ff', '#f778ba'], i))));
  put(`physics/distribution/${name}/outside`, attempt(() => dist.distributionOutside(payload)));
}

/* ---- C8 correlation ----------------------------------------------------------- */
for (const name of ['correlation_single_lab', 'correlation_single_local', 'correlation_two_lab']) {
  const payload = load(name);
  both(`physics/correlation/${name}`, () => corr.correlationOption(payload, { palette: 'viridis' }, { width: 560, height: 460 }));
  optionCase(`physics/correlation/${name}/narrow`, corr.correlationOption(payload, { palette: 'viridis' }, { width: 320, height: 300 }));
  optionCase(`physics/correlation/${name}/fade`, corr.correlationOption(payload, { palette: 'viridis', fadeNull: true }, { width: 560, height: 460 }));
}
{
  const quoted = clone(load('correlation_single_lab'));
  const k = quoted.variables.length;
  quoted.matrix[k - 1][4].mardia = { R: 0.21, se: 0.04, per_shower_R: 0.18, per_shower_se: 0.05, null_R2: 0.007 };
  quoted.matrix[3][1].ci95 = null;
  optionCase('physics/correlation/variant/quoted', corr.correlationOption(quoted, { palette: 'viridis' }, { width: 560, height: 460 }));
  put('notes/physics/variant/correlationHazards', pn.hazards(quoted, 'correlation'));
  const weak = clone(load('correlation_two_lab'));
  weak.weak = true; weak.n_events = 2;
  optionCase('physics/correlation/variant/weak', corr.correlationOption(weak, { palette: 'viridis' }, { width: 560, height: 460 }));
  const pal = scale.rampPalette(corr.R_SCALE, 'viridis');
  const rs = [];
  for (let r = -1; r <= 1.0001; r += 0.05) { const rgb = corr.cellColour(r, pal); rs.push([rgb, corr.labelColour(rgb)]); }
  put('physics/correlation/cellColours', { pal, rs, hatch: corr.hatchDecal(), scaleDef: corr.R_SCALE });
  both('physics/correlation/hatch_print', () => corr.hatchDecal(), (id, o) => put(id, o));
}

/* ---- statistics ---------------------------------------------------------------- */
for (const name of ['statistics_single_lab', 'statistics_single_local', 'statistics_two_local']) {
  const payload = load(name);
  put(`physics/statistics/${name}`, { rows: stats.statisticsRows(payload), lines: pn.negativeDepthLines(payload.negative_w),
    rowsNegative: attempt(() => stats.negativeRows(payload.negative_w)) });
}
put('physics/statistics/negative', [pn.negativeDepthLines(load('projections_single_local').frame.negative_w),
  pn.negativeDepthLines({ available: false, reason: 'Derived tables to rebuild.', summary: 'w < −10⁻⁶ mm: —' })]);
put('physics/statistics/consts', { columns: stats.STAT_COLUMNS, formats: [[0.123456, 'GeV', 'mean'], [-12, 'mm', 'median']].map(([x, u, k]) => stats.formatStat(x, u, k)),
  fraction: stats.fractionText(0.25, [0.2, 0.3]) });

/* ---- marks.js ------------------------------------------------------------------ */
{
  const w = marks.customWhiskers({ name: 'w', points: [[1, 2, 3, {}], [4, 5, 6, { caps: [false, true] }], [7, NaN, 8, {}]], color: '#fff', width: 1, tooltip: (d, i) => `item ${i}` });
  const h = marks.customWhiskers({ name: 'h', points: [[0, 2, 5, {}]], horizontal: true, offsetPx: 10, color: '#fff', width: 1 });
  const hover = marks.binHoverSeries({ name: 'r', edges: [0, 1, 2.5, 4], tooltip: (i) => `bin ${i}`, position: () => [0, 0] });
  put('physics/marks/custom', { w: exercise({ series: [w] }), h: exercise({ series: [h] }), hover: exercise({ series: [hover] }), w1: w, h1: h, hover1: hover });
}

/* ---- energy panel ---------------------------------------------------------------- */
const fakeChart = { getWidth: () => 640, getHeight: () => 360, setOption() {}, resize() {}, clear() {}, getDom: () => fakeEl(), dispatchAction() {},
  on() {}, getZr: () => ({ on() {}, off() {} }) };
function fakeEl() { return fakeElBody(); }
const fakeElBody = () => ({ clientWidth: 640, clientHeight: 360, style: {}, classList: { toggle() {} }, closest: () => null, append() {}, replaceChildren() {},
  appendChild() {}, hidden: false, addEventListener() {} });
globalThis.window = { addEventListener() {}, location: { origin: 'http://test.invalid' } };
globalThis.echarts = { init: () => fakeChart };
globalThis.document = { createElement: (t) => (t === 'canvas' ? fakeCanvas() : fakeEl()), getElementById: () => fakeEl(),
  createTextNode: (t) => ({ textContent: t }) };

function fakeCanvas() {
  const c = { width: 0, height: 0, pixels: null, scaledFrom: null };
  c.getContext = () => ({
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
    putImageData(image) { c.pixels = image.data; },
    drawImage(src, x, y, w, h) { c.scaledFrom = { w, h, src: src.pixels ? sha(Buffer.from(src.pixels)) : null }; },
    set imageSmoothingEnabled(_) {},
    // The same estimate textfit.js falls back on without a DOM, so a measured width is the same everywhere.
    font: '',
    measureText(text) { const px = Number(/(\d+(?:\.\d+)?)px/.exec(this.font)?.[1] ?? 10); return { width: String(text).length * px * 0.55 }; },
  });
  c.toJSON = () => ({ canvas: { width: c.width, height: c.height, pixels: c.pixels ? sha(Buffer.from(c.pixels)) : null, scaledFrom: c.scaledFrom } });
  return c;
}

for (const name of ['energy_d_two', ...B3]) {
  const payload = load(name);
  const make = (opts, metrics) => {
    const panel = new energyMod.EnergyPanel('plot-energy', 'fit-table', 'energy-sparse');
    const built = panel.buildOption({ payload, opts, metrics });
    return built;
  };
  const record = (id, built) => {
    put(id, { option: built.option, calls: exercise(built.option), notices: built.notices, table: built.table });
  };
  both(`physics/energy/${name}`, () => make({ palette: 'viridis' }, { width: 760, height: 380 }), record);
  record(`physics/energy/${name}/narrow`, make({ palette: 'viridis' }, { width: 321, height: 400 }));
  record(`physics/energy/${name}/cividis_a`, make({ palette: 'cividis', shower: 'a' }, { width: 760, height: 380 }));
  record(`physics/energy/${name}/truth`, make({ palette: 'plasma', kind: 'truth' }, { width: 760, height: 380 }));
}

/* ---- projections and the event cells ------------------------------------------------ */
function panelRecord(id, payload, optsOf, metrics = { width: 600, height: 400 }) {
  for (const panelId of ['xy', 'xz', 'yz']) {
    const sub = payload.panels?.[panelId];
    if (!sub) continue;
    const make = () => {
      const panel = new projMod.ProjectionPanel('plot-xy', { isometric: true });
      const opts = optsOf(panelId);
      const raster = decode.renderRaster(sub, opts.palette);
      const option = panel.buildOption({ payload: sub, opts, raster, metrics });
      return { option, extent: projMod.extentOf(sub, opts), symbols: undefined };
    };
    both(`physics/projection/${id}/${panelId}`, make, (id2, out) => put(id2, { option: out.option, calls: exercise(out.option), extent: out.extent }));
  }
}
for (const name of ['projections_base_lab', 'projections_single_lab', 'projections_single_local']) {
  const payload = load(name);
  panelRecord(name, payload, (panelId) => cells.ensembleCellOptions(payload, panelId, 'viridis'));
  put(`text/projection/${name}`, textOfProjection(payload));
}
const twoShower = JSON.parse(fs.readFileSync(`${goldenDir}/two_shower_api.json`, 'utf8'));
// tests/golden/two_shower_api.json keeps arrays as {n, sha256}, so its bodies feed the text builders only.
for (const [key, entry] of Object.entries(twoShower)) {
  if (!key.startsWith('/api/projections')) continue;
  const slug = key.replace('/api/projections ', '').replace(/[^A-Za-z0-9]+/g, '_');
  put(`text/projection/golden/${slug}`, textOfProjection(entry.body));
}

function textOfProjection(payload) {
  const kind = fv.kindOf(payload);
  const text = {
    kind, caption: fv.frameCaption(kind), caption1: fv.frameCaption(kind, 1), titles: ['xy', 'xz', 'yz'].map((id) => fv.panelTitle(id, kind)),
    footnotes: attempt(() => fv.footnotes(payload, { isometric: {} })), labLegend: attempt(() => fv.labLegend(payload)),
    exportLegend: ['xy', 'xz', 'yz'].map((id) => attempt(() => fv.exportLegend(id, payload))),
    notices: attempt(() => fv.frameNotices(payload)), coordinates: attempt(() => fv.coordinatesSentence(payload.frame ?? {})),
    anchors: attempt(() => fv.anchorSentence(payload.frame ?? {})),
    notes: ['xy', 'xz', 'yz'].map((id) => attempt(() => pn.projectionNotes({ payload, panelId: id, isometric: {}, experiment: { display_name: 'Demo' } }))),
    hazards: ['xy', 'xz', 'yz'].map((id) => attempt(() => pn.hazards(payload, id))),
  };
  return text;
}
put('text/frame_views/static', { views: Object.fromEntries(['lab', 'trans', 'local', 'canonical'].map((k) => [k, fv.frameView(k)])),
  explainer: [fv.anchorExplainer(), fv.anchorExplainer({ kind: 'canonical' }, 'p0')],
  channels: ['density', 'gradcam', 'gradcam_energy', 'shapcam', 'shapcam_energy'].flatMap((channel) => ['lab', 'canonical', 'local'].map((frame) => attempt(() => fv.channelCaption({ channel, frame })))),
  pct: [fv.num(1234.5, 1), fv.pct(0.1234)] });
put('text/canonical_overlays/static', { style: overlays.CANONICAL_CENTROID_STYLE, legend: attempt(() => overlays.centroidLegend({ energy_voxel: { label: 'Energy-weighted centroid', a: { x: 0, y: 0 }, b: null } })) });

// The windowed axis's captions, from the golden body's scalars.
for (const [key, entry] of Object.entries(twoShower)) {
  if (!key.startsWith('/api/window-axis')) continue;
  const slug = key.replace('/api/window-axis ', '').replace(/[^A-Za-z0-9]+/g, '_');
  put(`text/window_axis/${slug}`, { legend: attempt(() => fv.windowAxisLegend(entry.body)), disclosures: attempt(() => fv.windowAxisDisclosures(entry.body)) });
}

/* ---- Models: E2, pred-truth, residual, D4, D5, D3, C11, D2 ----------------------------------- */
const MW = { width: 760, height: 340 };
for (const name of ['perf_two_energy', 'perf_two_angle', 'perf_xgb_energy', 'perf_xgb_angle']) {
  const payload = load(name);
  put(`models/perf/${name}/model`, { quantities: perf.perfQuantities(payload), model: perf.perfModel(payload, { quantity: 'rmse' }) });
  for (const q of perf.perfQuantities(payload)) {
    both(`models/perf/${name}/${q.key}`, () => perf.perfBinsOption(payload, { quantity: q.key }, MW));
  }
  optionCase(`models/perf/${name}/showerA`, perf.perfBinsOption(payload, { quantity: 'rmse', shower: 'a' }, MW));
  optionCase(`models/perf/${name}/narrow`, perf.perfBinsOption(payload, { quantity: 'rmse' }, { width: 360, height: 340 }));
  optionCase(`models/perf/${name}/print_width`, perf.perfBinsOption(payload, { quantity: 'bias' }, { width: 321, height: 300 }));
}
{
  const weak = clone(load('perf_two_energy'));
  const s = weak.by_momentum_bin.series[0];
  s.n[0] = 1; s.rmse_lo[0] = null; s.rmse_hi[0] = null; s.drives_scale[0] = false;
  optionCase('models/perf/variant/weak', perf.perfBinsOption(weak, { quantity: 'rmse' }, MW));
  const clipped = clone(load('perf_two_energy'));
  const y = clipped.by_momentum_bin.y_max.rmse;
  y.value = 10; y.provisional = true; y.n_overflow = 3; y.note = 'Provisional: no point reaches N = 15.';
  y.overflow = [{ series: 'absolute:a', bin: 3, n: 20, value: 13.54, lo: 11.5, hi: 15.3 }];
  optionCase('models/perf/variant/clipped', perf.perfBinsOption(clipped, { quantity: 'rmse' }, MW));
  put('notes/models/variant/perfClipped', mn.perfBinsNotes({ payload: clipped, quantity: 'rmse' }));
  const xgb = clone(load('perf_two_angle'));
  const src = clone(xgb.by_momentum_bin.series[0]);
  delete src.median_rel; delete src.median_rel_lo; delete src.median_rel_hi; delete src.median_rel_method;
  xgb.by_momentum_bin.series.push({ ...src, key: 'xgb:a', code: 'xgb', label: 'XGBoost (20 % validation split)', network: null });
  optionCase('models/perf/variant/xgb_rmse', perf.perfBinsOption(xgb, { quantity: 'rmse' }, MW));
  optionCase('models/perf/variant/xgb_rel', perf.perfBinsOption(xgb, { quantity: 'median_rel' }, MW));
  put('notes/models/variant/perfXgb', mn.perfBinsNotes({ payload: xgb, quantity: 'median_rel' }));
  put('models/perf/geometry', { geometry: perf.groupedBarGeometry(16, 6, 1),
    intervals: [[0, 16], [0, 140], [0, 0.35], [-16, 16], [0, 7], [0, 0.12], [0, 1.5], [-1.2, 1.2], [0, 6], [0, 0.3], [0, 8], [0, 0.22], [0, 0.11]].map(([a, b]) => perf.dividingInterval(a, b)),
    sources: perf.sourceColours(['absolute', 'trans', 'local', 'xgb']), order: [perf.SOURCE_ORDER, perf.SOURCE_LABELS] });
  both('models/perf/sourceColours', () => perf.sourceColours(['xgb', 'local', 'absolute', 'trans']), (id, o) => put(id, o));
  const m = perf.perfModel(load('perf_xgb_energy'), { quantity: 'median_rel' });
  put('models/perf/tips', m.series.flatMap((x) => x.points.map((pt) => perf.perfTip(m, x, pt))));
}

for (const name of ['pred_density_two_energy', 'pred_density_two_angle', 'pred_density_xgb_energy', 'pred_density_xgb_phi', 'pred_density_xgb_theta']) {
  const payload = load(name);
  for (const p of ['viridis', 'cividis', 'plasma', 'turbo']) {
    both(`models/hist2d/${name}/${p}`, () => h2.hist2dOption(payload, { palette: p }, { width: 760, height: null }));
  }
  put(`models/hist2d/${name}/ramps`, { layout: h2.hist2dLayout(2, 760, { square: true }),
    firstLevel: attempt(() => ['viridis', 'cividis', 'plasma', 'turbo'].map((p) => h2.countColour(1, h2.countRamp(p, payload.color?.ramp?.by_palette?.[p]), payload.color.vmin, payload.color.vmax))),
    ramps: ['viridis', 'cividis', 'plasma', 'turbo'].map((p) => [h2.countRamp(p, null), h2.countRamp(p, payload.color?.ramp?.by_palette?.[p] ?? null)]) });
  both(`models/residual/${name}`, () => dist.residualOption(payload, {}, MW));
  optionCase(`models/residual/${name}/narrow`, dist.residualOption(payload, {}, { width: 321, height: 300 }));
}
{
  const few = clone(load('pred_density_two_energy'));
  few.density.a = { encoding: 'pairs', pairs: [[3, 3.4], [5, 4.1], [9, 30.0], [12, 11.6]], n: 4, n_in_range: 3,
    outside: { truth_below: 0, truth_above: 0, pred_below: 0, pred_above: 1, total: 1 }, n_missing: { total: 0, prediction: 0, truth: 0 } };
  optionCase('models/hist2d/variant/pairs', h2.hist2dOption(few, { palette: 'viridis' }, { width: 760, height: null }));
  put('notes/models/variant/predPairs', mn.predTruthNotes({ payload: few }));
  const strip = clone(load('pred_density_two_energy'));
  const a = strip.residual.series.a;
  a.draw = 'strip'; a.histogram = null; a.curve = null; a.drives_scale = false;
  a.strip = { values: [-0.4, -0.1, 0.05, 0.3, 0.9, 7.5], n_shown: 6, truncated: false };
  a.fit = { ...a.fit, n: 6, sigma: 0.9, sigma_error: 0.2915, sigma_ci95: [0.5618, 2.2074], sigma_bias_factor: 0.9515, estimator: 'moments' };
  a.markers = { mu: 0.2, ci95_lo: -0.3, ci95_hi: 0.7, dispersion_lo: -0.7, dispersion_hi: 1.1 };
  a.message = 'N = 6: below the 8-event floor for a density curve; the events and summary marks are drawn.';
  optionCase('models/residual/variant/strip', dist.residualOption(strip, {}, MW));
  const thin = clone(load('pred_density_two_angle'));
  for (const s of Object.values(thin.residual.series)) {
    s.draw = 'curve+strip'; s.histogram = null; s.drives_scale = false; s.strip = { values: [-12, -3, 0.1, 0.2], n_shown: 4, truncated: false };
  }
  optionCase('models/residual/variant/thin', dist.residualOption(thin, {}, MW));
  const over = clone(load('pred_density_two_angle'));
  const b = over.residual.series.b;
  b.draw = 'curve+strip'; b.histogram = null; b.drives_scale = false; b.strip = { values: [0.1, 0.2], n_shown: 2, truncated: false };
  optionCase('models/residual/variant/over', dist.residualOption(over, {}, MW));
  const none = clone(load('pred_density_two_energy'));
  for (const s of Object.values(none.residual.series)) {
    s.draw = 'strip'; s.histogram = null; s.curve = null; s.drives_scale = false; s.strip = { values: [0.1, 0.5], n_shown: 2, truncated: false };
  }
  optionCase('models/residual/variant/none', dist.residualOption(none, {}, MW));
  const phi = load('pred_density_xgb_phi');
  const few2 = clone(phi);
  const pa = few2.residual.series.a;
  pa.draw = 'strip'; pa.histogram = null; pa.curve = { y: null }; pa.curve_peak = null; pa.drives_scale = false;
  pa.core_fit = null; pa.strip = { values: [-30, -2, 0.5, 4, 2900], n_shown: 5, truncated: false };
  pa.fit = { ...pa.fit, n: 5, mu_core: null, sigma_core: null };
  optionCase('models/residual/variant/phiStrip', dist.residualOption(few2, {}, MW));
  const stray = clone(few2);
  stray.residual.series.a.markers = { mu: 0.1, ci95_lo: -0.2, ci95_hi: 0.4, dispersion_lo: -1, dispersion_hi: 1.2 };
  optionCase('models/residual/variant/phiStray', dist.residualOption(stray, {}, MW));
  const feat = load('features_single_hist2d');
  optionCase('models/hist2d/variant/tiny', h2.hist2dOption(feat, { palette: 'viridis' }, { width: 230, height: null }));
  put('models/hist2d/many', h2.hist2dLayout(19, 1100, { square: false }));
}
for (const name of ['features_single_hist', 'features_single_hist_phi']) {
  const payload = load(name);
  both(`models/hist/${name}/density`, () => dist.featureHistOption(payload, { palette: 'viridis' }, MW));
  optionCase(`models/hist/${name}/count`, dist.featureHistOption(payload, { palette: 'viridis', quantity: 'count' }, MW));
  put(`models/hist/${name}/stops`, cp.seriesStops('viridis', payload.series.length));
}
{
  const tall = clone(load('features_single_hist'));
  tall.series[1].kde.pdf = tall.series[1].kde.pdf.map((x) => x * 20);
  optionCase('models/hist/variant/tall', dist.featureHistOption(tall, { palette: 'viridis' }, MW));
  both('models/hist2d/features_single_hist2d', () => h2.hist2dOption(load('features_single_hist2d'), { palette: 'viridis' }, { width: 760, height: null }));
}
for (const name of ['features_single_corr', 'features_two_corr']) {
  const payload = load(name);
  both(`models/corr/${name}`, () => corr.correlationOption(payload, { palette: 'viridis' }, { width: 620, height: 560 }));
  optionCase(`models/corr/${name}/fade`, corr.correlationOption(payload, { palette: 'viridis', fadeNull: true }, { width: 620, height: 560 }));
  put(`models/corr/${name}/matrix`, attempt(() => corr.featureCorrMatrix(payload)));
}
both('models/rates/primaries_single', () => rates.ratesOption(load('primaries_single'), {}, { width: 640, height: 320 }));
for (const name of ['features_single_describe', 'features_events_describe']) {
  put(`models/table/${name}`, ['median', 'mean', 'range'].map((stat) => ft.featureRows(load(name), stat)));
}

/* ---- XGBoost --------------------------------------------------------------------------------- */
const XW = { width: 560, height: 330 };
const narrow = (h) => ({ width: 321, height: h });
for (const name of ['xgb_cv_momentum', 'xgb_cv_angle']) {
  const p = load(name);
  both(`xgb/cv/${name}`, () => cv.xgbCvOption(p, {}, XW));
  both(`xgb/cv/${name}/export`, () => cv.xgbCvOption(p, {}, narrow(cv.cvLayout(cv.cvModel(p), 321, null).height)));
  put(`xgb/cv/${name}/model`, { axes: cv.cvModel(p).rows.flatMap((r) => r.panels.map((q) => ({ id: q.id, ...cv.cvAxis(q) }))),
    lines: cv.cvLayout(cv.cvModel(p), 321, null).lines.map((l) => l.panels.length) });
}
{
  const p = load('xgb_binary');
  const h = bin.binaryLayout(bin.binaryModel(p), 321, null).height;
  both('xgb/binary/xgb_binary', () => bin.xgbBinaryOption(p, {}, XW));
  both('xgb/binary/xgb_binary/export', () => bin.xgbBinaryOption(p, {}, narrow(h)));
  put('xgb/binary/xgb_binary/layout', [bin.binaryLayout(bin.binaryModel(p), 321, null), bin.binaryLayout(bin.binaryModel(p), 560, 330)]);
}
for (const name of ['xgb_surrogate_momentum', 'xgb_surrogate_angle']) {
  const p = load(name);
  for (const label of p.labels) {
    const opts = { label, palette: 'viridis' };
    const m = tree.treeModel(p, opts);
    for (const width of [1100, 700, 321]) {
      const lay = tree.treeLayout(m, width, width === 321 ? null : 330);
      both(`xgb/tree/${name}/${label}/${width}`, () => tree.xgbTreeOption(p, opts, { width, height: lay.height }));
    }
    put(`xgb/tree/${name}/${label}/model`, { coloured: m.coloured, leaf: m.nodes.filter((n) => n.leaf).map((n) => n.colour), all: m.nodes.map((n) => n.colour),
      lines: m.nodes.map((n) => tree.nodeLines(n)), tips: m.nodes.map((n) => tree.nodeTip(m, n)), ramp: attempt(() => tree.rampTitle(m)),
      fid: tree.fidelityTexts(m), palette: tree.treePalette('viridis') });
    for (const palette_ of ['cividis', 'turbo']) {
      optionCase(`xgb/tree/${name}/${label}/${palette_}`, tree.xgbTreeOption(p, { label, palette: palette_ }, { width: 1100, height: 330 }));
    }
  }
}
for (const name of ['xgb_importance_momentum', 'xgb_importance_angle']) {
  const p = load(name);
  const m = imps.importanceModel(p);
  both(`xgb/importance/${name}`, () => imps.xgbImportanceOption(p, {}, { width: 1100, height: 330 }));
  both(`xgb/importance/${name}/export`, () => imps.xgbImportanceOption(p, {}, { width: 321, height: imps.importanceLayout(m, 321, null).height }));
  put(`xgb/importance/${name}/model`, { shown: m.shown.map((f) => f.name), colours: m.colours, hidden: m.hiddenUsed.length });
}
both('xgb/importance/frameColours', () => imps.frameColours(), (id, o) => put(id, o));
{
  const corrected = clone(load('xgb_cv_momentum'));
  corrected.interval.label = '95% Nadeau–Bengio corrected Student-t interval of the mean (4 d.o.f.)';
  optionCase('xgb/variant/cvCorrected', cv.xgbCvOption(corrected, {}, XW));
  const newcombe = clone(load('xgb_binary'));
  const ba = newcombe.rates.find((r) => r.id === 'balanced_accuracy');
  ba.interval = { ...ba.interval, method: 'newcombe', label: '95% Newcombe (MOVER) interval from the two Wilson limits' };
  optionCase('xgb/variant/binaryNewcombe', bin.xgbBinaryOption(newcombe, {}, XW));
  const undef = clone(load('xgb_binary'));
  const prec = undef.rates.find((r) => r.id === 'precision_1');
  prec.value = null; prec.k = 0; prec.n = 0; prec.interval = null;
  optionCase('xgb/variant/binaryUndefined', bin.xgbBinaryOption(undef, {}, XW));
  put('notes/xgb/variant/binaryUndefined', xn.xgbBinaryNotes({ payload: undef }));
  const short = clone(load('xgb_binary'));
  short.counts = { class_0: 1932, class_1: 20, n: 1952 };
  put('xgb/variant/binaryRatio', { texts: bin.ratioTexts(bin.binaryModel(short)), option: bin.xgbBinaryOption(short, {}, XW) });
  const circ = clone(load('xgb_surrogate_angle'));
  for (const n of circ.nodes) n.circular = { phi: { mean: n.values.phi, resultant: 0.9 } };
  optionCase('xgb/variant/treeCircular', tree.xgbTreeOption(circ, { label: 'phi' }, { width: 1100, height: 330 }));
  put('notes/xgb/variant/treeCircular', xn.xgbTreeNotes({ payload: circ, label: 'phi' }));
  const noCirc = clone(load('xgb_surrogate_angle'));
  for (const n of noCirc.nodes) delete n.circular;
  put('xgb/variant/treeNoCircular', { boxes: tree.treeModel(noCirc, { label: 'phi' }).nodes.map((n) => tree.nodeLines(n).at(-1)), notes: xn.xgbTreeNotes({ payload: noCirc, label: 'phi' }) });
  const real = clone(load('xgb_surrogate_angle'));
  real.fidelity.outputs = { phi: { r2: 0.978, mae: 0.0503 }, theta: { r2: 0.004, mae: 0.0118 } };
  real.fidelity.r2 = 0.491;
  for (const label of ['phi', 'theta']) {
    optionCase(`xgb/variant/treeFidelity_${label}`, tree.xgbTreeOption(real, { label }, { width: 1100, height: 330 }));
    put(`notes/xgb/variant/treeFidelity_${label}`, xn.xgbTreeNotes({ payload: real, label }));
  }
  const circFid = clone(load('xgb_surrogate_angle'));
  circFid.fidelity.outputs = {
    phi: { r2: 0.978, mae: 0.31, r2_circular: 0.41, mae_wrapped: 0.0503, judged_on: 'r2_circular', low: true },
    theta: { r2: 0.62, mae: 0.0118, judged_on: 'r2', low: false },
  };
  circFid.fidelity.r2 = 0.8;
  put('xgb/variant/treeCircularFidelity', { texts: tree.fidelityTexts(tree.treeModel(circFid, { label: 'phi' })), hazards: xn.xgbHazards(circFid, 'xgb-surrogate', { label: 'phi' }),
    notes: xn.xgbTreeNotes({ payload: circFid, label: 'phi' }) });
  const spread = clone(load('xgb_surrogate_angle'));
  spread.nodes[0].circular.phi = { mean: 2.5, resultant: 0.05 };
  spread.nodes[0].n = 100;
  const sm = tree.treeModel(spread, { label: 'phi' });
  const root = sm.nodes.find((n) => n.depth === 0);
  put('xgb/variant/treeRayleigh', { box: tree.nodeLines(root).at(-1), tip: tree.nodeTip(sm, root), circ: tree.circularOf(root, 'phi') });
  const clipped = clone(load('xgb_importance_momentum'));
  clipped.features[4].clipped = true;
  optionCase('xgb/variant/importanceClipped', imps.xgbImportanceOption(clipped, { }, { width: 1100, height: 330 }));
  put('notes/xgb/variant/importanceClipped', xn.xgbImportanceNotes({ payload: clipped }));
  const many = clone(load('xgb_importance_momentum'));
  many.features.forEach((f, i) => { f.shipped = (52 - i) / 1378; });
  optionCase('xgb/variant/importanceMany', imps.xgbImportanceOption(many, {}, { width: 1100, height: 330 }));
  put('notes/xgb/variant/importanceMany', xn.xgbImportanceNotes({ payload: many }));
  const broken = {};
  for (const name of ['xgb_cv_momentum', 'xgb_binary', 'xgb_surrogate_momentum', 'xgb_importance_momentum']) {
    const p = clone(load(name));
    p.run.split.reproduced = false;
    p.run.split.warning = 'validation / training MSE at random_state 42 does not exceed the others: split not reproduced';
    p.meta.warnings = [p.run.split.warning];
    broken[name] = p;
  }
  put('notes/xgb/variant/splitBroken', { cv: xn.xgbCvNotes({ payload: broken.xgb_cv_momentum }), binary: xn.xgbBinaryNotes({ payload: broken.xgb_binary }),
    tree: xn.xgbTreeNotes({ payload: broken.xgb_surrogate_momentum }), importance: xn.xgbImportanceNotes({ payload: broken.xgb_importance_momentum }) });
  put('xgb/variant/empty', [cv.xgbCvOption({}, {}, {}), bin.xgbBinaryOption({}, {}, {}), tree.xgbTreeOption({}, {}, {}), imps.xgbImportanceOption({}, {}, {})]);
}

/* ---- voxels ------------------------------------------------------------------------------------- */
const arr = (a) => Array.from(a);
function voxelSummary(built) {
  const option = built.option;
  return {
    option, calls: exercise(option), box: built.box, bounds: built.bounds, drawn: built.drawn, skipped: built.skipped,
    noValue: built.noValue, hidden: built.hidden, translucent: built.translucent, primaries: built.primaries, halos: built.halos,
    roles: built.roles?.map((r) => ({ role: r.role, members: r.members })), ticks: built.ticks, cropped: built.cropped, fit: built.fit,
    strings: ['xAxis3D', 'yAxis3D', 'zAxis3D'].map((k) => [option[k].name, [-3000, -1.5, 0, 250.4, 4000].map((t) => option[k].axisLabel.formatter(t))]),
  };
}
for (const name of ['event_voxels_base_lab', 'event_voxels_base_canonical', 'event_voxels_base_local_shapcam', 'event_voxels_single_local', 'event_voxels_single_species']) {
  const payload = load(name);
  const model = v.decodeEventVoxels(payload);
  for (const pal of ['viridis', 'turbo']) {
    const built = v.voxelOption(model, { palette: pal });
    put(`voxels/event/${name}/${pal}/option`, voxelSummary(built));
    put(`voxels/event/${name}/${pal}/colours`, { rgba: v.cubeColours(model, pal), table: v.voxelCodeTable(model, pal), legend: v.voxelLegend(model, pal),
      legible: scale.rampTable(model.scale, scale.rampPalette(model.scale, pal), { signed: true }), ref: v.referenceTopLabel(model) });
  }
  const picks = [...new Set([0, Math.floor(model.n / 2), model.n - 1, ...payload.voxels.topk.slice(0, 3).map((t) => t.i)])];
  put(`voxels/event/${name}/text`, { legend: v.speciesLegend(model), legendHidden: v.speciesLegend(model, new Set([0, 2])), values: [0, 1, 128, 255].map((c) => v.codeValue(model, c)),
    tips: picks.map((i) => v.voxelTooltip(model, i)), notes: vn.voxelEventNotes({ payload, drawn: v.voxelOption(model, { palette: 'viridis' }) }),
    viewport: v.voxelOption(model, { palette: 'viridis', viewport: { width: 588, height: 560 } }).option.grid3D });
  both(`voxels/event/${name}/colours_print`, () => ({ rgba: v.cubeColours(model, 'viridis'), table: v.voxelCodeTable(model, 'viridis'), legend: v.voxelLegend(model, 'viridis') }),
    (id, out) => put(id, out));
  optionCase(`voxels/event/${name}/hidden_species`, v.voxelOption(model, { hidden: new Set([0, 2]) }).option);
}
for (const name of ['voxels_base_local', 'voxels_base_canonical_shapcam', 'voxels_single_local', 'voxels_two_local']) {
  const payload = load(name);
  const model = v.decodeEnsembleVoxels(payload);
  for (const pal of ['viridis', 'cividis']) {
    const built = v.voxelOption(model, { palette: pal });
    put(`voxels/ensemble/${name}/${pal}/option`, voxelSummary(built));
    put(`voxels/ensemble/${name}/${pal}/colours`, { rgba: v.cubeColours(model, pal), table: v.voxelCodeTable(model, pal), legend: v.voxelLegend(model, pal),
      stops: v.voxelLegend(model, pal)?.inRange?.color ?? null,
      legible: scale.rampTable(model.scale, scale.rampPalette(model.scale, pal), { signed: true }) });
  }
  put(`voxels/ensemble/${name}/text`, { counts: arr(model.counts), values: [2, 128, 129, 255].map((c) => v.codeValue(model, c)),
    tips: [0, model.n - 1, payload.topk[0].i].map((i) => v.voxelTooltip(model, i)),
    notes: vn.voxelEnsembleNotes({ payload, drawn: v.voxelOption(model, { palette: 'viridis' }) }) });
  both(`voxels/ensemble/${name}/colours_print`, () => ({ rgba: v.cubeColours(model, 'viridis'), table: v.voxelCodeTable(model, 'viridis'), legend: v.voxelLegend(model, 'viridis') }),
    (id, out) => put(id, out));
}
put('voxels/palettes', { species: palette.qualitativeStops('species', 8), speciesPrint: palette.qualitativeStops('species_print', 8), labels: v.SPECIES_LABELS });
put('voxels/geometry', { camera: v.CAMERA, axes: v.cameraAxes(), heights: [300, 400, 506, 586, 640, 746, 900].map((w) => v.glPlotHeight(w)),
  ticks: [[0, 1000], [-300, 300], [0, 4040]].map(([a, b]) => v.axisTicks(a, b)), names: v.axisNames({ x: 'u', y: 'v', z: 'w' }), consts: [v.BOX_UNITS, v.LEGEND_RIGHT, v.FIT_PAD, v.OPAQUE_ALPHA, v.HALO_LIMIT] });
{
  const projections = load('projections_single_local');
  const window_ = v.pairedWindow(projections);
  const base = v.decodeEnsembleVoxels(load('voxels_single_local'));
  for (const [name, w] of Object.entries({ paired: window_, narrow: { ...window_, y: [-200, 200] }, none: null })) {
    const model = v.cropToWindow(base, w);
    put(`voxels/crop/${name}`, { crop: model.crop, built: voxelSummary(v.voxelOption(model, { palette: 'viridis' })), lines: vn.cropLines(model.crop, { x: 'u', y: 'v', z: 'w' }, 'density') });
  }
  put('voxels/notes/projection', vn.voxelProjectionNotes({ pair: 'ensemble', payload: projections, panelId: 'yz', pairing: ['Paired with the 3-D cloud.'], title: 'v–w Projection' }));
  const body = twoShower['/api/event {"event_number": 0, "shower": "a"}'].body;
  put('voxels/notes/eventProjection', Object.fromEntries(['lab', 'trans', 'local'].flatMap((kind) => ['xy', 'xz', 'yz'].map(
    (panelId) => [`${kind}:${panelId}`, vn.voxelProjectionNotes({ pair: 'event', payload: body, panelId, frameKind: kind })]))));
  const perAxis = clone(body);
  perAxis.frames.local.half_mm_axes = { x: 700, y: 660, z: 560 };
  put('voxels/notes/perAxis', vn.voxelProjectionNotes({ pair: 'event', payload: perAxis, panelId: 'xz', frameKind: 'local' }));
  put('notes/physics/eventInspector', Object.fromEntries(['lab', 'trans', 'local'].flatMap((kind) => ['xy', 'xz', 'yz'].map(
    (panelId) => [`${kind}:${panelId}`, pn.eventNotes({ payload: body, kind, panelId })]))));
}

/* ---- drawer notes ---------------------------------------------------------------------------------- */
{
  const stub = { isTouched: (a) => a === 'e1', get: (k) => ({ e1_min: 2, e1_max: 5 })[k] ?? null };
  const experiment = { display_name: 'Demo' };
  const N = {
    profile: ['profiles_single_w', 'profiles_single_native', 'profiles_two_w'].flatMap((n) => ['depth', 'r'].map((axis) => [`profile/${n}/${axis}`,
      pn.profileNotes({ payload: load(n), state: stub, experiment, axis })])),
    response: ['response_single_hits', 'response_single_events', 'response_two'].flatMap((n) => ['b1', 'b2', 'resolution'].flatMap((mode) => ['both', 'a', 'b'].map((shower) => [`response/${n}/${mode}/${shower}`,
      pn.responseNotes({ payload: load(n), mode, shower, state: stub, experiment })]))),
    grid: B3.flatMap((n) => [['both', 'both'], ['a', 'a']].map(([s, shower]) => [`grid/${n}/${s}`, pn.responseGridNotes({ payload: load(n), shower, state: stub, experiment })])),
    energy: ['b3_single_notebook', 'b3_single_bins', 'energy_d_two'].map((n) => [`energy/${n}`, pn.energyNotes({ payload: load(n), state: stub, experiment })]),
    distribution: ['distribution_single_u', 'distribution_single_energy', 'distribution_single_phi', 'distribution_single_theta_hit', 'distribution_events_p', 'distribution_two_p'].flatMap((n) => ['linear', 'log'].map((yScale) => [`distribution/${n}/${yScale}`,
      pn.distributionNotes({ payload: load(n), yScale, state: stub, experiment })])),
    correlation: ['correlation_single_lab', 'correlation_single_local', 'correlation_two_lab'].map((n) => [`correlation/${n}`, pn.correlationNotes({ payload: load(n), state: stub, experiment })]),
    statistics: ['statistics_single_lab', 'statistics_single_local', 'statistics_two_local'].map((n) => [`statistics/${n}`, pn.statisticsNotes({ payload: load(n), state: stub, experiment })]),
    models_perf: ['perf_two_energy', 'perf_two_angle', 'perf_xgb_energy', 'perf_xgb_angle'].map((n) => [`perf/${n}`, mn.perfBinsNotes({ payload: load(n), state: stub, experiment: experiment, quantity: 'median_rel' })]),
    models_pred: ['pred_density_two_energy', 'pred_density_two_angle', 'pred_density_xgb_energy', 'pred_density_xgb_phi', 'pred_density_xgb_theta'].flatMap((n) => [
      [`pred/${n}`, mn.predTruthNotes({ payload: load(n), palette: 'plasma' })], [`residual/${n}`, mn.residualNotes({ payload: load(n) })]]),
    models_features: [
      ...['features_single_describe', 'features_events_describe'].map((n) => [`table/${n}`, mn.featureTableNotes({ payload: load(n), stat: 'mean' })]),
      ...['features_single_corr', 'features_two_corr'].map((n) => [`corr/${n}`, mn.featureCorrNotes({ payload: load(n) })]),
      ...['features_single_hist', 'features_single_hist_phi'].map((n) => [`hist/${n}`, mn.featureHistNotes({ payload: load(n) })]),
      ['hist2d', mn.featureHist2dNotes({ payload: load('features_single_hist2d') })], ['primaries', mn.primariesNotes({ payload: load('primaries_single') })],
      ['empty', [mn.perfBinsNotes({}), mn.residualNotes({ payload: null })]],
    ],
    xgb: [
      ...['xgb_cv_momentum', 'xgb_cv_angle'].map((n) => [`cv/${n}`, xn.xgbCvNotes({ payload: load(n), experiment })]),
      ['binary', xn.xgbBinaryNotes({ payload: load('xgb_binary'), experiment })],
      ...['xgb_surrogate_momentum', 'xgb_surrogate_angle'].flatMap((n) => load(n).labels.map((l) => [`tree/${n}/${l}`, xn.xgbTreeNotes({ payload: load(n), label: l })])),
      ...['xgb_importance_momentum', 'xgb_importance_angle'].map((n) => [`importance/${n}`, xn.xgbImportanceNotes({ payload: load(n) })]),
      ['empty', [xn.xgbCvNotes({}), xn.xgbTreeNotes({ payload: null })]],
    ],
  };
  for (const [family, list] of Object.entries(N)) for (const [id, value] of list) put(`notes/${family}/${id}`, value);
  const hz = {
    profileR: pn.hazards(load('profiles_single_w'), 'profile-r'), b1: pn.hazards(load('response_two'), 'response-b1'), b2: pn.hazards(load('response_two'), 'response-b2'),
    res: pn.hazards(load('response_single_hits'), 'response-res'), b3: pn.hazards(load('b3_single_bins'), 'response-b3'),
    distribution: pn.hazards(load('distribution_single_phi'), 'distribution'), correlation: pn.hazards(load('correlation_single_lab'), 'correlation'),
    statistics: pn.hazards(load('statistics_single_lab'), 'statistics'),
    energy: pn.hazards({ calibration: { applied: true }, series: [{ draw: 'strip' }] }, 'energy'),
    generic: pn.hazards({ meta: { exact: false }, frame: { kind: 'canonical', comb: { staggered: true } }, panels: {} }, 'yz'),
  };
  put('notes/physics/hazards', hz);
  put('notes/physics/consts', { section: pn.SECTION, energyTitle: pn.ENERGY_TITLE, energyMarks: pn.ENERGY_MARKS, density: pn.DENSITY_EXPLAINER, curveArea: pn.CURVE_AREA_NOTE,
    eventMarks: pn.EVENT_MARKS, titles: pn.PHYSICS_TITLES, headings: pn.PHYSICS_HEADINGS, response: pn.RESPONSE_TITLE });
  put('notes/models/consts', { titles: mn.MODELS_TITLES, headings: mn.MODELS_HEADINGS, builders: mn.MODELS_NOTE_BUILDERS });
  put('notes/voxels/consts', { titles: vn.VOXEL_TITLES, exception: vn.VOXEL_EXCEPTION, occlusion: vn.VOXEL_OCCLUSION, legible: vn.LEGIBLE_RAMP_NOTE });
  put('notes/xgb/consts', { titles: xn.XGB_TITLES, headings: xn.XGB_HEADINGS, builders: xn.XGB_NOTE_BUILDERS, low: xn.LOW_FIDELITY_R2 });
}

/* ---- the Methodology figures --------------------------------------------------------------------------- */
for (const name of Object.keys(exhibits.EXHIBITS).sort()) {
  const build = exhibits.EXHIBITS[name];
  put(`methodology/exhibit/${name}/screen`, build(`fig-${name}`));
  put(`methodology/exhibit/${name}/screen_explicit`, build(`fig-${name}`, { medium: 'screen' }));
  put(`methodology/exhibit/${name}/paper`, build(`fig-${name}`, { medium: 'paper' }));
  put(`methodology/exhibit/${name}/paper_svg`, { svg: exportMod.serialiseSvg(build(`fig-${name}`, { medium: 'paper' })), size: exportMod.paperSize(build(`fig-${name}`, { medium: 'paper' })) });
  put(`methodology/exhibit/${name}/screen_svg`, exportMod.serialiseSvg(build(`fig-${name}`)));
}
put('methodology/exhibit/consts', { paperWidth: exhibits.PAPER_WIDTH_MM, minFont: exhibits.PAPER_MIN_FONT });

/* ---- out ------------------------------------------------------------------------------------------------------ */
// Sorted, so two runs print the same bytes.
const sortedCases = Object.fromEntries(Object.keys(cases).sort().map((k) => [k, cases[k]]));
console.log(JSON.stringify({ theme: themeMap, cases: sortedCases }));
"""


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("LANGUAGE", "LC_ALL", "LC_NUMERIC", "LC_TIME", "TZ")}
    env.update({"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8", "TZ": "UTC"})
    return env


def _run() -> dict:
    """The harness's table: {"theme": {token: value}, "cases": {case id: sha256}}."""
    args = json.dumps([JS.as_uri(), str(FIXTURES), str(GOLDEN_DIR), DUMP])
    if DUMP:
        Path(DUMP).mkdir(parents=True, exist_ok=True)
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=300, check=False, env=_env())
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _write(table: dict) -> None:
    GOLDEN.write_text(json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def measured() -> dict:
    """Run the harness once; with CALOSRV_WRITE_DARK_GOLDEN=1 it also rewrites the golden."""
    table = _run()
    if WRITE:
        _write(table)
    return table


@pytest.fixture(scope="module")
def golden() -> dict:
    assert GOLDEN.exists(), (
        f"{GOLDEN.relative_to(ROOT)} is missing: record it with CALOSRV_WRITE_DARK_GOLDEN=1")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_every_dark_token_keeps_its_value(measured, golden):
    """A later commit may add a token to the dark theme; none may change or go."""
    old, new = golden["theme"], measured["theme"]
    missing = sorted(k for k in old if k not in new)
    changed = {k: (old[k], new[k]) for k in sorted(old) if k in new and not _same(old[k], new[k])}
    report = [f"missing token {k!r} (was {old[k]!r})" for k in missing]
    report += [f"token {k!r}: {o!r} -> {n!r}" for k, (o, n) in changed.items()]
    assert not report, "the dark theme's tokens moved:\n  " + "\n  ".join(report)


def test_the_set_of_cases_is_the_one_recorded(measured, golden):
    old, new = set(golden["cases"]), set(measured["cases"])
    report = [f"case no longer recorded: {c}" for c in sorted(old - new)]
    report += [f"case not in the golden: {c}" for c in sorted(new - old)]
    assert not report, "the dark golden's case ids differ:\n  " + "\n  ".join(report)


def test_every_dark_case_is_byte_identical(measured, golden):
    """Each failing case is named; dump both sides with CALOSRV_DARK_GOLDEN_DUMP to see how."""
    old, new = golden["cases"], measured["cases"]
    differing = sorted(c for c in old if c in new and old[c] != new[c])
    assert not differing, (
        f"{len(differing)} of {len(old)} dark cases changed:\n  " + "\n  ".join(differing))


def test_the_harness_is_deterministic(measured):
    """Two runs print the same bytes: no clock, no randomness, no locale."""
    assert _run() == measured


def test_the_golden_has_every_family_and_well_formed_digests(golden):
    cases = golden["cases"]
    assert set(golden) == {"theme", "cases"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in cases.values())
    for family in FAMILIES:
        assert any(c == family or c.startswith(family + "/") for c in cases), f"no case of family {family}"
    # The theme map is the screen theme's tokens, readable by name.
    for token in ("text", "muted", "card", "canvas", "border", "accent", "showerA", "showerB", "divergingPalette", "categorical"):
        assert token in golden["theme"], token
    assert golden["theme"]["card"] == "#1c2128" and golden["theme"]["canvas"] == "#0d1117"
    assert len(set(cases.values())) > 0.6 * len(cases), "most cases must hash differently: the harness is recording nothing"

