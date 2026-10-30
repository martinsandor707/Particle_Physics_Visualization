"""The light screen theme's colours, and the dark and print themes it must not move, under Node.

The light theme (``scale.js`` ``SCREEN_LIGHT``, ``setScreenTheme``) puts the
charts on a white card. CLAUDE.md section 2 holds there exactly as on the
dark ``#1c2128`` card, and what is checked here, without a browser, is that
it does, measured on the code's own tables:

* the token sets: ``SCREEN`` and ``SCREEN_LIGHT`` have the same keys, both a
  subset of ``PRINT_TOKENS``, the light theme keeps the dark one's type and
  geometry, and ``medium`` is the screen on both and print in print;
* ``setScreenTheme`` / ``screenTheme`` / ``restoreScreenTheme``: one THEME
  object, refilled in place, and the exporter's restore returns to the
  screen theme in force;
* ``isPrintTheme`` is the medium and ``onLightCard`` the ground, so the white
  light card is never taken for paper;
* exports never depend on the screen theme: the print option of a sample of
  builders on recorded payloads, built inside the exporter's swap, is the
  same canonical JSON from either screen theme;
* light sequential ramps ("contrast rises with value"): every opaque code of
  every scale kind clears 3:1 on white, lightness composited on white never
  rises along the codes, the floor taper included, and Turbo is drawn on its
  0.749-1 run alone;
* PuOr's light arms (``puor_light``, ``puor_light_linear``): 3:1 from p = 1/6,
  L* falling outward, mirrored codes matched in contrast, the linear zero at
  the light border ``#d0d7de``, and the 3-D cubes' arms starting at 3:1;
* the correlation matrix on the light card: the light linear PuOr, weak cells
  faded toward white, and its labels' contrast;
* series colours, the qualitative palettes, the species palette and the
  tooltip ground per theme;
* the Methodology exhibits are measured against the dark card by name, so
  their node trees do not depend on the screen theme.

Dark spot checks pin values recorded at 72e4ec6. Skipped when ``node`` is not
on the PATH.
"""

from __future__ import annotations

import json
import subprocess

import pytest
from test_js_physics_shell import JS, NODE, PAYLOADS

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

WHITE = (255, 255, 255)
SEQUENTIAL = ("viridis", "cividis", "plasma", "turbo")
MONOTONE = ("viridis", "cividis", "plasma")

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const pal = await imp('palette.js');
const decode = await imp('decode.js');
const cp = await imp('panels/chart_panel.js');
const tip = await imp('panels/tooltip.js');
const perf = await imp('panels/perf_bins.js');
const imps = await imp('panels/xgb_importance.js');
const h2 = await imp('panels/hist2d.js');
const corr = await imp('panels/correlation.js');
const prof = await imp('panels/profile.js');
const xtree = await imp('panels/xgb_tree.js');
const energy = await imp('panels/energy.js');
const vox = await imp('voxels.js');
const ex = await imp('methodology/exhibits.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const load = (name) => JSON.parse(fs.readFileSync(`${fixtureDir}/${name}.json`, 'utf8'));
const { THEME } = scale;
const W = [255, 255, 255];
const rgbAt = (t, i) => [t[i * 3], t[i * 3 + 1], t[i * 3 + 2]];

/* Canonical JSON of an option: keys sorted, every renderItem drawn with a
 * fake api, every tooltip and label formatter called. */
function canon(x, seen = new WeakSet()) {
  if (typeof x === 'function') return `fn:${x.length}`;
  if (x === null || typeof x !== 'object') return Number.isNaN(x) ? 'NaN' : x;
  if (ArrayBuffer.isView(x)) return Array.from(x);
  if (seen.has(x)) return '[cycle]';
  seen.add(x);
  if (Array.isArray(x)) return x.map((v) => canon(v, seen));
  return Object.fromEntries(Object.keys(x).sort().map((k) => [k, canon(x[k], seen)]));
}
function api(datum) {
  const value = Array.isArray(datum) ? datum : (datum?.value ?? []);
  return {
    coord: (p) => [Number(p?.[0]) * 3 + 1, Number(p?.[1]) * -2 + 400],
    value: (k) => (Array.isArray(value) ? value[k] : value),
    size: (p) => [Math.abs(Number(p?.[0]) || 1) * 3, Math.abs(Number(p?.[1]) || 1) * 2],
    style: (s) => ({ ...(s ?? {}) }), visual: () => '#123456', currentSeriesIndices: () => [0],
    getWidth: () => 640, getHeight: () => 360,
  };
}
function drawn(option) {
  const series = [].concat(option?.series ?? []).map((s) => (Array.isArray(s?.data) ? s.data : []).slice(0, 300).map((d, i) => {
    const rec = {};
    if (typeof s.renderItem === 'function') {
      try { rec.el = canon(s.renderItem({ dataIndex: i, coordSys: { x: 0, y: 0, width: 600, height: 300 } }, api(d))); } catch (e) { rec.err = e.message; }
    }
    if (typeof s.tooltip?.formatter === 'function') {
      try { rec.tip = s.tooltip.formatter({ dataIndex: i, value: Array.isArray(d) ? d : d?.value, data: d }); } catch (e) { rec.tipErr = e.message; }
    }
    return rec;
  }));
  return JSON.stringify({ option: canon(option), series });
}
const same = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));

/* The exporter's synchronous swap (export/figure.js), around one build. */
function printBuild(theme, build) {
  scale.setScreenTheme(theme);
  const saved = { ...THEME };
  let built;
  try {
    Object.assign(THEME, PRINT_TOKENS);
    built = drawn(build());
  } finally {
    scale.restoreScreenTheme();
    Object.assign(THEME, saved);
  }
  const restored = same(THEME, scale.SCREEN_THEMES[theme]);
  return { built, restored };
}
function screenBuild(theme, build) {
  scale.setScreenTheme(theme);
  return drawn(build());
}

const out = {};

/* ---- tokens -------------------------------------------------------------- */
out.themes = { dark: scale.SCREEN_THEMES.dark, light: scale.SCREEN_THEMES.light, print: PRINT_TOKENS,
  screenTheme: scale.SCREEN_THEME };
out.frozen = { themes: Object.isFrozen(scale.SCREEN_THEMES), dark: Object.isFrozen(scale.SCREEN_THEMES.dark),
  light: Object.isFrozen(scale.SCREEN_THEMES.light), screenTheme: Object.isFrozen(scale.SCREEN_THEME) };

/* ---- setScreenTheme / screenTheme / restoreScreenTheme -------------------- */
{
  const ref = THEME;
  const sem = { initial: scale.screenTheme(), initialIsDark: same(THEME, scale.SCREEN_THEMES.dark) };
  sem.setLight = scale.setScreenTheme('light');
  sem.afterLight = scale.screenTheme();
  sem.isLight = same(THEME, scale.SCREEN_THEMES.light);
  sem.keysLight = Object.keys(THEME).sort();
  sem.sameObject = THEME === ref;
  Object.assign(THEME, PRINT_TOKENS);
  sem.printKeys = Object.keys(THEME).sort();
  sem.printIsPrint = same(THEME, PRINT_TOKENS);
  scale.restoreScreenTheme();
  sem.restoredLight = same(THEME, scale.SCREEN_THEMES.light) && scale.screenTheme() === 'light';
  THEME.stray = 1;
  scale.restoreScreenTheme();
  sem.strayGone = !('stray' in THEME);
  sem.names = ['LIGHT', 'Light', '', null, undefined, 'print', 'auto', 'dark', 'light'].map((n) => {
    const applied = scale.setScreenTheme(n);
    return [String(n), applied, scale.screenTheme(), same(THEME, scale.SCREEN_THEMES[applied])];
  });
  scale.setScreenTheme('dark');
  Object.assign(THEME, PRINT_TOKENS);
  scale.restoreScreenTheme();
  sem.restoredDark = same(THEME, scale.SCREEN_THEMES.dark) && scale.screenTheme() === 'dark';
  sem.sameObjectAtEnd = THEME === ref;
  sem.screenThemeIsDark = same(scale.SCREEN_THEME, scale.SCREEN_THEMES.dark);
  out.semantics = sem;
}

/* ---- isPrintTheme / onLightCard ------------------------------------------- */
{
  const table = {};
  for (const theme of ['dark', 'light']) {
    scale.setScreenTheme(theme);
    table[theme] = [cp.isPrintTheme(), cp.onLightCard()];
  }
  scale.setScreenTheme('light');
  Object.assign(THEME, PRINT_TOKENS);
  table.printFromLight = [cp.isPrintTheme(), cp.onLightCard()];
  scale.setScreenTheme('dark');
  Object.assign(THEME, PRINT_TOKENS);
  table.printFromDark = [cp.isPrintTheme(), cp.onLightCard()];
  scale.setScreenTheme('dark');
  table.cards = Object.fromEntries(['#1c2128', '#ffffff', '#FFFFFF', '#f6f8fa', '#30363d', '#0d1117', 'nonsense']
    .map((c) => [c, cp.onLightCard(c)]));
  out.truth = table;
}

/* ---- export invariance ---------------------------------------------------- */
{
  const eventModel = () => vox.decodeEventVoxels(load('event_voxels_base_lab'));
  const speciesModel = () => vox.decodeEventVoxels(load('event_voxels_single_species'));
  const ensembleModel = () => vox.decodeEnsembleVoxels(load('voxels_base_canonical_shapcam'));
  const builders = {
    profile: () => prof.profileOption(load('profiles_single_w'), { axis: 'depth' }, { width: 640, height: 360 }),
    correlation: () => corr.correlationOption(load('correlation_single_lab'), { palette: 'viridis' }, { width: 620, height: 560 }),
    correlationFaded: () => corr.correlationOption(load('features_single_corr'), { palette: 'viridis', fadeNull: true }, { width: 620, height: 560 }),
    xgbTree: () => xtree.xgbTreeOption(load('xgb_surrogate_momentum'), { palette: 'viridis' }, { width: 900, height: 420 }),
    xgbTreeTurbo: () => xtree.xgbTreeOption(load('xgb_surrogate_angle'), { palette: 'turbo' }, { width: 900, height: 420 }),
    voxelEvent: () => vox.voxelOption(eventModel(), { palette: 'viridis', viewport: { width: 600, height: 450 } }).option,
    voxelSpecies: () => vox.voxelOption(speciesModel(), { palette: 'viridis', viewport: { width: 600, height: 450 } }).option,
    voxelShapcam: () => vox.voxelOption(ensembleModel(), { palette: 'viridis', viewport: { width: 600, height: 450 } }).option,
    energy: () => energy.EnergyPanel.prototype.buildOption.call(Object.create(energy.EnergyPanel.prototype), {
      payload: load('energy_d_two'), opts: { palette: 'viridis' }, metrics: { width: 321, height: 300 } }).option,
    hist2d: () => h2.hist2dOption(load('pred_density_two_energy'), { palette: 'viridis' }, { width: 760, height: null }),
    perfBins: () => perf.perfBinsOption(load('perf_two_energy'), { quantity: 'bias' }, { width: 321, height: 300 }),
    importance: () => imps.xgbImportanceOption(load('xgb_importance_momentum'), {}, { width: 321, height: 420 }),
  };
  out.exportInvariance = {};
  for (const [name, build] of Object.entries(builders)) {
    const dark = printBuild('dark', build);
    const light = printBuild('light', build);
    out.exportInvariance[name] = {
      same: dark.built === light.built, restored: dark.restored && light.restored, length: dark.built.length,
      screensDiffer: screenBuild('dark', build) !== screenBuild('light', build),
    };
  }
  scale.setScreenTheme('dark');
}

/* ---- light sequential ramps ----------------------------------------------- */
const SCALES = {
  gev: { scale: 'log10', unit: 'GeV', vmin: -6, vmax: 0 },
  areal: { scale: 'log10', unit: 'GeV/mm^2', vmin: -7.2, vmax: -1.1 },
  gevFloor: { scale: 'log10', unit: 'GeV', vmin: -5, vmax: 0, floor: 'transparent' },
  relative: { scale: 'log10', unit: 'a.u.', vmin: -3, vmax: 0, floor: 'transparent', floor_ratio: 1e-3, quantity: 'density' },
  relativeHigh: { scale: 'log10', unit: 'a.u.', vmin: -3, vmax: 0.5, floor_ratio: 1e-3, quantity: 'gradcam_energy' },
  gradcam: { scale: 'linear', vmin: 0, vmax: 1 },
};
const LAYOUTS = {
  plain: { empty_code: 0, min_code: 1, max_code: 255 },
  below: { empty_code: 0, below_code: 1, min_code: 2, max_code: 255 },
};
function codes(payload, palette) {
  const t = decode.codeTable(payload, palette);
  const order = [...(Number.isInteger(payload.below_code) ? [payload.below_code] : []),
    ...Array.from({ length: payload.max_code - payload.min_code + 1 }, (_, i) => payload.min_code + i)];
  return order.map((c) => [t[c * 4], t[c * 4 + 1], t[c * 4 + 2], t[c * 4 + 3]]);
}
scale.setScreenTheme('light');
out.lightRamps = {};
for (const p of pal.SEQUENTIAL_PALETTES) {
  out.lightRamps[p] = { ramp: cp.legibleRamp(p), table: Array.from(pal.lookupTable(p)), cases: {} };
  for (const [sk, sc] of Object.entries(SCALES)) {
    for (const [lk, layout] of Object.entries(LAYOUTS)) {
      out.lightRamps[p].cases[`${sk}:${lk}`] = codes({ scale: sc, ...layout }, p);
    }
  }
}
out.lightLegend = {
  relative: (() => { const vm = scale.visualMap(SCALES.relative, 'viridis'); return { stops: vm.inRange.color, text: vm.text }; })(),
  gev: (() => { const vm = scale.visualMap(SCALES.gev, 'viridis'); return { stops: vm.inRange.color, text: vm.text }; })(),
  span: scale.legibleSpan(SCALES.relative, 'viridis'),
};
out.lightSeries = Object.fromEntries(pal.SEQUENTIAL_PALETTES.map((p) => [p,
  Array.from({ length: 19 }, (_, k) => cp.seriesStops(p, k + 1))]));
out.lightCount = Object.fromEntries(pal.SEQUENTIAL_PALETTES.map((p) => [p, [
  h2.countRamp(p), h2.countRamp(p, load('pred_density_two_energy').color.ramp.by_palette[p])]]));
scale.setScreenTheme('dark');
out.darkCount = Object.fromEntries(pal.SEQUENTIAL_PALETTES.map((p) => [p,
  h2.countRamp(p, load('pred_density_two_energy').color.ramp.by_palette[p])]));

/* ---- dark spot checks ----------------------------------------------------- */
{
  const rel = SCALES.relative;
  const t = scale.rampTable(rel, 'viridis');
  const g = scale.rampTable(SCALES.gev, 'turbo');
  const shap = { scale: 'linear', diverging: true, vmin: -1, vmax: 1 };
  const s = scale.rampTable(shap, 'puor_screen_linear', { signed: true });
  const vm = scale.visualMap(rel, 'viridis');
  const ct = decode.codeTable({ scale: SCALES.gev, ...LAYOUTS.below }, 'viridis');
  out.dark = {
    ramps: Object.fromEntries(pal.SEQUENTIAL_PALETTES.map((p) => [p, cp.legibleRamp(p)])),
    span: scale.legibleSpan(rel, 'viridis'),
    relTable: [0, 1, 40, 41, 42, 128, 255].map((i) => rgbAt(t, i)),
    turboTable: [0, 128, 255].map((i) => rgbAt(g, i)),
    shapArms: [0, 127, 128, 255].map((i) => rgbAt(s, i)),
    legend: { first: vm.inRange.color.slice(0, 3), last: vm.inRange.color.slice(-1), text: vm.text },
    series: [cp.seriesStops('viridis', 4), cp.seriesStops('turbo', 3)],
    codes: [2, 255].map((c) => [ct[c * 4], ct[c * 4 + 1], ct[c * 4 + 2], ct[c * 4 + 3]]),
    palettes: [THEME.divergingPalette, THEME.divergingLinearPalette],
  };
}

/* ---- PuOr's light arms ---------------------------------------------------- */
out.puor = {};
for (const name of ['puor_light', 'puor_light_linear']) {
  out.puor[name] = { table: Array.from(pal.lookupTable(name)), arms: pal.PUOR_LIGHT_ARMS[name] };
}
out.lightCard = pal.LIGHT_CARD;
{
  scale.setScreenTheme('light');
  const signed = { scale: { unit: 'a.u.', scale: 'signed_log10', vmin: -3, vmax: 0, floor: 'transparent', floor_ratio: 1e-3,
    quantity: 'shapcam_energy' }, empty_code: 0, min_code: 2, max_code: 255, split_code: 129 };
  const ct = decode.codeTable(signed, 'viridis');
  out.signedLight = {
    palette: scale.rampPalette(signed.scale, 'viridis'),
    codes: Array.from({ length: 256 }, (_, c) => [ct[c * 4], ct[c * 4 + 1], ct[c * 4 + 2], ct[c * 4 + 3],
      decode.codeExponent(c, signed.scale, signed)]),
    legend: scale.visualMap(signed.scale, 'puor_light').inRange.color,
    mid: scale.rampMidLabel(signed.scale)?.style.text,
  };
  const shap = { scale: 'linear', diverging: true, vmin: -1, vmax: 1 };
  out.shapLight = {
    palette: scale.rampPalette(shap, 'viridis'),
    cubes: Array.from(scale.rampTable(shap, 'puor_light_linear', { signed: true })),
    flat: Array.from(scale.rampTable(shap, 'puor_light_linear')),
    mid: scale.rampMidLabel(shap)?.style.text,
  };
  scale.setScreenTheme('dark');
}

/* ---- the correlation matrix on the light card ----------------------------- */
{
  scale.setScreenTheme('light');
  const cells = (option) => option.series[0].data.map((d) => {
    const rgb = corr.cellColour(d.value[2], THEME.divergingLinearPalette);
    const shown = cp.blendOver(`rgb(${rgb.join(',')})`, corr.NULL_OPACITY);
    return { r: d.value[2], label: d.label?.color ?? null, opacity: d.itemStyle?.opacity ?? null,
      plainLabel: corr.labelColour(rgb), fadedLabel: corr.labelColour(shown), shown };
  });
  const plain = corr.correlationOption(load('correlation_single_lab'), { palette: 'viridis' }, { width: 620, height: 560 });
  const faded = corr.correlationOption(load('features_single_corr'), { palette: 'viridis', fadeNull: true }, { width: 620, height: 560 });
  const sweep = Array.from({ length: 401 }, (_, i) => {
    const r = -1 + i / 200;
    const rgb = corr.cellColour(r, THEME.divergingLinearPalette);
    const shown = cp.blendOver(`rgb(${rgb.join(',')})`, corr.NULL_OPACITY);
    return { r, rgb, label: corr.labelColour(rgb), shown, shownLabel: corr.labelColour(shown) };
  });
  out.correlation = {
    palette: scale.rampPalette(corr.R_SCALE, 'viridis'),
    legend: plain.visualMap.inRange.color,
    plain: cells(plain), faded: cells(faded), sweep, nullOpacity: corr.NULL_OPACITY,
    ink: { text: THEME.text, canvas: THEME.canvas },
  };
  scale.setScreenTheme('dark');
  out.correlationDark = Array.from({ length: 401 }, (_, i) => {
    const rgb = corr.cellColour(-1 + i / 200, THEME.divergingLinearPalette);
    return { rgb, label: corr.labelColour(rgb) };
  });
}

/* ---- qualitative palettes, species, tooltip -------------------------------- */
{
  const per = {};
  const species = () => vox.speciesLegend(vox.decodeEventVoxels(load('event_voxels_single_species'))).map((r) => [r.code, r.colour]);
  const speciesTable = () => {
    const model = vox.decodeEventVoxels(load('event_voxels_single_species'));
    const t = vox.voxelCodeTable(model, 'viridis');
    return Array.from({ length: 8 }, (_, c) => [t[c * 4], t[c * 4 + 1], t[c * 4 + 2]]);
  };
  const snap = () => ({
    sources: perf.sourceColours(['absolute', 'trans', 'local', 'xgb']), frames: imps.frameColours(),
    tooltip: tip.tooltipOption(null).backgroundColor, tooltipBorder: tip.tooltipOption(null).borderColor,
    species: species(), speciesTable: speciesTable(), palette: THEME.qualitativePalette,
  });
  scale.setScreenTheme('dark'); per.dark = snap();
  scale.setScreenTheme('light'); per.light = snap();
  for (const theme of ['dark', 'light']) {
    scale.setScreenTheme(theme);
    const saved = { ...THEME };
    Object.assign(THEME, PRINT_TOKENS);
    per[`printFrom_${theme}`] = snap();
    scale.restoreScreenTheme();
    Object.assign(THEME, saved);
  }
  scale.setScreenTheme('dark');
  out.qualitative = { per, palettes: pal.QUALITATIVE };
}

/* ---- the Methodology exhibits --------------------------------------------- */
{
  const trees = () => Object.fromEntries(['ramps', 'puor'].flatMap((name) => [
    [`${name}:screen`, JSON.stringify(ex.EXHIBITS[name](`fig-${name}`))],
    [`${name}:paper`, JSON.stringify(ex.EXHIBITS[name](`fig-${name}`, { medium: 'paper' }))],
  ]));
  scale.setScreenTheme('dark'); const dark = trees();
  scale.setScreenTheme('light'); const light = trees();
  scale.setScreenTheme('dark');
  Object.assign(THEME, PRINT_TOKENS); const print = trees();
  scale.restoreScreenTheme();
  out.exhibits = Object.fromEntries(Object.keys(dark).map((k) => [k, { light: dark[k] === light[k], print: dark[k] === print[k] }]));
  const source = fs.readFileSync(new URL(`${jsRoot}/methodology/exhibits.js`), 'utf8');
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  out.exhibitsSource = { readsTheme: /\bTHEME\b/.test(code), calls: code.match(/legibleRamp\([^)]*\)/g) };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def theme_results() -> dict:
    args = json.dumps([JS.as_uri(), str(PAYLOADS)])
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, args],
                          capture_output=True, text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# ------------------------------------------------------------- colour maths --


def _lin(c: float) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = (_lin(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def lstar(rgb) -> float:
    y = luminance(rgb)
    return 116 * y ** (1 / 3) - 16 if y > 216 / 24389 else y * 24389 / 27


def rgb_of(text: str) -> tuple[int, ...]:
    text = text.strip()
    if text.startswith("#"):
        return tuple(int(text[k:k + 2], 16) for k in (1, 3, 5))
    inner = text[text.index("(") + 1:text.index(")")].split(",")
    return tuple(round(float(v)) for v in inner[:3])


def over_white(rgba) -> tuple[float, ...]:
    a = rgba[3] / 255
    return tuple(a * c + (1 - a) * 255 for c in rgba[:3])


def table_rgb(table, i):
    return tuple(table[i * 3:i * 3 + 3])


# ------------------------------------------------------------------- tokens --


def test_both_screen_themes_have_the_same_keys_and_print_overrides_all(theme_results):
    themes = theme_results["themes"]
    dark, light, printed = (set(themes[k]) for k in ("dark", "light", "print"))
    assert dark == light
    assert dark <= printed, f"print leaves {sorted(dark - printed)} to the screen theme"


def test_the_light_theme_keeps_the_dark_type_and_geometry(theme_results):
    dark, light = theme_results["themes"]["dark"], theme_results["themes"]["light"]
    for key in ("fontFamily", "fontMono", "fontSmall", "fontLabel", "fontName", "fontTip", "lineAxis", "lineGrid",
                "gridOpacity", "axisOnZero", "markerScale", "rampOrient", "legendWrap", "chartBackground",
                "anchorOpacity", "floorFadeDecades"):
        assert light[key] == dark[key], key
    assert light["rampOrient"] == "vertical" and light["legendWrap"] is False


def test_the_medium_is_the_screen_on_both_screens_and_print_in_print(theme_results):
    themes = theme_results["themes"]
    assert themes["dark"]["medium"] == "screen"
    assert themes["light"]["medium"] == "screen"
    assert themes["print"]["medium"] == "print"


def test_the_light_tokens_are_the_brief_values(theme_results):
    light = theme_results["themes"]["light"]
    assert {k: light[k] for k in ("text", "muted", "border", "grid", "canvas", "card", "accent", "warn", "showerA",
                                  "showerB", "labelBg", "hatch", "separationRule")} == {
        "text": "#111827", "muted": "#59636e", "border": "#d0d7de", "grid": "#d0d7de", "canvas": "#f6f8fa",
        "card": "#ffffff", "accent": "#0b5fbe", "warn": "#8a5a00", "showerA": "#a3186b", "showerB": "#0b5fbe",
        "labelBg": "rgba(255,255,255,0.92)", "hatch": "#6b7280", "separationRule": "rgba(17,24,39,0.55)",
    }
    assert (light["envelopeAlpha"], light["bandAlpha"], light["stripAlpha"]) == (0.18, 0.22, 0.07)
    assert light["categorical"] == {"min": 0.75, "max": 0.0}
    assert (light["divergingPalette"], light["divergingLinearPalette"]) == ("puor_light", "puor_light_linear")
    assert (light["qualitativePalette"], light["speciesPalette"]) == ("dark2", "species_print")
    assert light["tooltipBackground"] == "rgba(255,255,255,0.97)"
    dark = theme_results["themes"]["dark"]
    assert (dark["qualitativePalette"], dark["speciesPalette"], dark["tooltipBackground"]) == (
        "set2", "species", "rgba(22,27,34,0.95)")


def test_the_dark_literal_stays_frozen_and_named(theme_results):
    assert all(theme_results["frozen"].values()), theme_results["frozen"]
    assert theme_results["themes"]["screenTheme"]["card"] == "#1c2128"
    assert theme_results["themes"]["screenTheme"]["floorFadeDecades"] == 0.5
    assert theme_results["semantics"]["screenThemeIsDark"]


# ---------------------------------------------------------------- semantics --


def test_set_screen_theme_refills_the_one_theme_object(theme_results):
    sem = theme_results["semantics"]
    assert sem["initial"] == "dark" and sem["initialIsDark"], "the cold boot is the dark theme"
    assert sem["setLight"] == "light" and sem["afterLight"] == "light" and sem["isLight"]
    assert sem["keysLight"] == sorted(theme_results["themes"]["light"])
    assert sem["sameObject"] and sem["sameObjectAtEnd"], "THEME must stay the same object"


def test_anything_but_light_is_dark(theme_results):
    for name, applied, active, matches in theme_results["semantics"]["names"]:
        assert applied == ("light" if name == "light" else "dark"), name
        assert active == applied and matches, name


def test_restore_returns_to_the_screen_theme_in_force(theme_results):
    sem = theme_results["semantics"]
    assert sem["printIsPrint"], "the print swap over the light theme is exactly the print theme"
    assert sem["printKeys"] == sorted(theme_results["themes"]["print"])
    assert sem["restoredLight"], "restoreScreenTheme after a print render must return to the light theme"
    assert sem["restoredDark"]
    assert sem["strayGone"], "restoreScreenTheme empties THEME before refilling it"


def test_print_is_a_medium_and_the_light_card_is_a_ground(theme_results):
    truth = theme_results["truth"]
    assert truth["dark"] == [False, False]
    assert truth["light"] == [False, True], "the white light card is not paper"
    assert truth["printFromLight"] == [True, True]
    assert truth["printFromDark"] == [True, True]
    assert truth["cards"] == {"#1c2128": False, "#ffffff": True, "#FFFFFF": True, "#f6f8fa": True,
                              "#30363d": False, "#0d1117": False, "nonsense": False}


@pytest.mark.parametrize("name", ["profile", "correlation", "correlationFaded", "xgbTree", "xgbTreeTurbo", "voxelEvent",
                                  "voxelSpecies", "voxelShapcam", "energy", "hist2d", "perfBins", "importance"])
def test_the_print_option_does_not_depend_on_the_screen_theme(theme_results, name):
    """Built inside the exporter's swap, the print option is the same from either screen theme."""
    result = theme_results["exportInvariance"][name]
    assert result["length"] > 200
    assert result["same"], f"{name}: the print option differs between the dark and light screen themes"
    assert result["restored"], f"{name}: the swap did not restore the screen theme in force"
    assert result["screensDiffer"], f"{name}: the screen option did not change with the theme"


# ------------------------------------------------------- light sequential ramps --


@pytest.mark.parametrize("palette", SEQUENTIAL)
def test_every_opaque_light_code_clears_three_to_one_on_white(theme_results, palette):
    for case, codes in theme_results["lightRamps"][palette]["cases"].items():
        opaque = [c for c in codes if c[3] == 255]
        assert opaque, case
        worst = min(contrast(c, WHITE) for c in opaque)
        assert worst >= 3.0, (palette, case, worst)


@pytest.mark.parametrize("palette", MONOTONE)
def test_light_codes_darken_on_white_along_the_ramp(theme_results, palette):
    """Contrast rises with value: lightness composited on white never rises, the taper included."""
    for case, codes in theme_results["lightRamps"][palette]["cases"].items():
        lights = [lstar(over_white(c)) for c in codes]
        rises = [(i, b - a) for i, (a, b) in enumerate(zip(lights, lights[1:])) if b > a + 1e-9]
        assert not rises, (palette, case, rises[:5])
        assert lights[0] - lights[-1] > 30, (palette, case)


def test_light_runs_are_the_measured_dark_ends_oriented_from_the_card(theme_results):
    ramps = {p: theme_results["lightRamps"][p]["ramp"] for p in SEQUENTIAL}
    assert {p: (round(r["from"], 3), round(r["to"], 3)) for p, r in ramps.items()} == {
        "viridis": (0.6, 0.0), "cividis": (0.698, 0.0), "plasma": (0.639, 0.0), "turbo": (0.749, 1.0)}
    for p, r in ramps.items():
        table = theme_results["lightRamps"][p]["table"]
        lo = table_rgb(table, round(r["from"] * 255))
        hi = table_rgb(table, round(r["to"] * 255))
        assert contrast(hi, WHITE) > contrast(lo, WHITE) >= 3.0, p


def test_turbo_is_drawn_on_its_light_run_alone(theme_results):
    """Turbo's 0.749-1 run, contrast rising along it; its taper fades its first colour, no rainbow sweep."""
    entry = theme_results["lightRamps"]["turbo"]
    table = entry["table"]
    run = {table_rgb(table, i) for i in range(round(0.749 * 255), 256)}
    for case, codes in entry["cases"].items():
        coloured = [tuple(c[:3]) for c in codes if c[3] > 0]
        assert set(coloured) <= run, case
        opaque = [contrast(c, WHITE) for c in codes if c[3] == 255]
        assert all(b >= a - 1e-9 for a, b in zip(opaque, opaque[1:])), case
        lights = [lstar(over_white(c)) for c in codes]
        assert all(b <= a + 1e-9 for a, b in zip(lights, lights[1:])), case


def test_the_light_legend_runs_from_the_faded_light_end_to_the_dark_end(theme_results):
    legend = theme_results["lightLegend"]
    stops = legend["relative"]["stops"]
    assert stops[0].startswith("rgba(") and stops[0].endswith(",0.000)")
    assert rgb_of(stops[0]) == (253, 231, 37), "the taper climbs from Viridis' light end"
    assert rgb_of(stops[-1]) == (68, 1, 84), "the top of the light legend is Viridis' darkest colour"
    assert legend["relative"]["text"][1].endswith("fades to not drawn")
    assert rgb_of(legend["gev"]["stops"][0]) == (34, 167, 132) and rgb_of(legend["gev"]["stops"][-1]) == (68, 1, 84)
    span = legend["span"]
    assert span["from"] == pytest.approx(0.6) and span["to"] == 0 and span["taperEnd"] > 0


def test_light_series_colours_clear_three_to_one(theme_results):
    for palette, lists in theme_results["lightSeries"].items():
        for colours in lists:
            worst = min(contrast(rgb_of(c), WHITE) for c in colours)
            assert worst >= 3.0, (palette, len(colours), worst)
        four = [contrast(rgb_of(c), WHITE) for c in lists[3]]
        assert four == sorted(four), f"{palette}: series contrast rises with the series index"


def test_count_ramps_use_the_server_block_only_on_its_own_card(theme_results):
    for palette, (plain, served) in theme_results["lightCount"].items():
        assert not plain["measured"] and not served["measured"], palette
        assert served["from"] == plain["from"] and served["to"] == plain["to"]
    assert theme_results["lightCount"]["viridis"][0]["from"] == pytest.approx(0.6)
    assert theme_results["lightCount"]["viridis"][0]["to"] == 0
    assert all(r["measured"] for r in theme_results["darkCount"].values())


# ------------------------------------------------------------ dark spot checks --


def test_dark_ramps_are_unchanged(theme_results):
    dark = theme_results["dark"]
    assert {p: (round(r["from"], 3), round(r["to"], 3)) for p, r in dark["ramps"].items()} == {
        "viridis": (0.376, 1.0), "cividis": (0.482, 1.0), "plasma": (0.431, 1.0), "turbo": (0.102, 0.859)}
    assert dark["span"] == {"from": pytest.approx(0.3764705882352941, abs=0), "to": 1,
                            "taperEnd": pytest.approx(0.16166666666666663, abs=1e-15)}
    assert dark["relTable"] == [[68, 1, 84], [68, 4, 86], [45, 111, 142], [44, 113, 142], [43, 115, 142],
                                [45, 174, 126], [253, 231, 37]]
    assert dark["turboTable"] == [[68, 100, 213], [162, 247, 55], [204, 44, 7]]
    assert dark["shapArms"] == [[254, 224, 182], [167, 85, 11], [117, 96, 163], [216, 218, 235]]
    assert dark["legend"] == {
        "first": ["rgba(68,1,84,0.000)", "rgba(70,17,99,0.128)", "rgba(72,35,115,0.255)"],
        "last": ["rgb(253,231,37)"],
        "text": ["Average hit density (a.u.)\n10⁰·⁰ a.u.", "10⁻³·⁰ a.u. —\nfades to not drawn"],
    }
    assert dark["series"] == [["rgb(44,114,142)", "rgb(34,163,133)", "rgb(117,208,83)", "rgb(253,231,37)"],
                              ["rgb(42,201,215)", "rgb(211,230,41)", "rgb(204,44,7)"]]
    assert dark["codes"] == [[44, 114, 142, 255], [253, 231, 37, 255]]
    assert dark["palettes"] == ["puor_screen", "puor_screen_linear"]


# ------------------------------------------------------------- PuOr light arms --


def _arm(table, negative: bool):
    """The table's arm from zero outwards: (p, rgb) for k = 0..127."""
    return [(k / 127, table_rgb(table, 127 - k if negative else 128 + k)) for k in range(128)]


@pytest.mark.parametrize("name", ["puor_light", "puor_light_linear"])
def test_light_puor_darkens_outward_on_each_arm(theme_results, name):
    entry = theme_results["puor"][name]
    for side in ("neg", "pos"):
        anchors = entry["arms"][side]
        lights = [lstar(rgb) for _, rgb in anchors]
        assert all(b < a for a, b in zip(lights, lights[1:])), (name, side, lights)
        assert [p for p, _ in anchors] == sorted(p for p, _ in anchors)
    for negative in (True, False):
        lights = [lstar(rgb) for _, rgb in _arm(entry["table"], negative)]
        # Strictly by anchor; along the 8-bit table a colour may repeat, never lighten.
        assert all(b <= a + 1e-9 for a, b in zip(lights, lights[1:])), (name, negative)
        assert lights[0] - lights[-1] > 40


def test_light_signed_log_arms_clear_three_to_one_from_a_sixth(theme_results):
    table = theme_results["puor"]["puor_light"]["table"]
    for negative in (True, False):
        arm = _arm(table, negative)
        assert arm[0][1] == WHITE, "each arm starts at the white card"
        worst = min(contrast(rgb, WHITE) for p, rgb in arm if p >= 1 / 6)
        assert worst >= 3.25, (negative, worst)
    for p, rgb in theme_results["puor"]["puor_light"]["arms"]["neg"] + theme_results["puor"]["puor_light"]["arms"]["pos"]:
        if p == pytest.approx(1 / 6):
            assert contrast(rgb, WHITE) >= 3.25


def test_every_drawn_light_signed_code_clears_three_to_one(theme_results):
    signed = theme_results["signedLight"]
    assert signed["palette"] == "puor_light"
    for code in range(2, 256):
        r, g, b, a, exponent = signed["codes"][code]
        if exponent >= -2.5 - 1e-9:
            assert a == 255 and contrast((r, g, b), WHITE) >= 3.0, (code, exponent)
    assert signed["mid"] == "±10⁻³"


@pytest.mark.parametrize("name,tolerance", [("puor_light", 1.15), ("puor_light_linear", 1.09)])
def test_light_mirrored_codes_are_equally_visible(theme_results, name, tolerance):
    table = theme_results["puor"][name]["table"]
    ratios = []
    for k in range(128):
        a = contrast(table_rgb(table, 127 - k), WHITE)
        b = contrast(table_rgb(table, 128 + k), WHITE)
        ratios.append(max(a, b) / min(a, b))
    assert max(ratios) <= tolerance, (max(ratios), ratios.index(max(ratios)))


def test_the_light_linear_zero_is_the_light_border(theme_results):
    table = theme_results["puor"]["puor_light_linear"]["table"]
    assert table_rgb(table, 127) == table_rgb(table, 128) == (208, 215, 222)
    assert contrast((208, 215, 222), WHITE) == pytest.approx(1.45, abs=0.01)
    assert tuple(theme_results["lightCard"]) == WHITE


def test_the_light_cubes_start_each_arm_at_three_to_one(theme_results):
    shap = theme_results["shapLight"]
    assert shap["palette"] == "puor_light_linear" and shap["mid"] == "0"
    cubes = shap["cubes"]
    assert contrast(table_rgb(cubes, 127), WHITE) >= 3.0 and contrast(table_rgb(cubes, 128), WHITE) >= 3.0
    assert min(contrast(table_rgb(cubes, i), WHITE) for i in range(256)) >= 3.0
    assert table_rgb(shap["flat"], 127) == (208, 215, 222), "the 2-D raster keeps the border-grey zero"


# ------------------------------------------------------------------ correlation --


def test_the_correlation_matrix_takes_the_light_linear_puor(theme_results):
    c = theme_results["correlation"]
    assert c["palette"] == "puor_light_linear"
    table = theme_results["puor"]["puor_light_linear"]["table"]
    # Math.round: half up, as the legend's tableStops rounds.
    expected = [f"rgb({','.join(str(v) for v in table_rgb(table, int(k / 12 * 255 + 0.5)))})" for k in range(13)]
    assert c["legend"] == expected
    assert rgb_of(c["legend"][6]) == (208, 215, 222)


def test_weak_correlation_cells_fade_toward_white(theme_results):
    c = theme_results["correlation"]
    alpha = c["nullOpacity"]
    for cell in c["sweep"]:
        shown = cell["shown"]
        for v, s in zip(cell["rgb"], shown):
            assert s == pytest.approx(alpha * v + (1 - alpha) * 255)
            assert s >= v - 1e-9
    faded = [x for x in c["faded"] if x["opacity"] is not None]
    assert faded, "the recorded feature matrix has weak cells"
    assert all(x["opacity"] == alpha for x in faded)
    for cell in c["faded"]:
        expected = cell["fadedLabel"] if cell["opacity"] is not None else cell["plainLabel"]
        assert cell["label"] == expected, cell
    for cell in faded:
        assert contrast(cell["shown"], rgb_of(cell["label"])) >= 4.5
    assert all(x["opacity"] is None and x["label"] == x["plainLabel"] for x in c["plain"])


def test_correlation_labels_on_the_light_card(theme_results):
    """On the light card a label takes `inkOn`'s ink: the text ink, white or black.

    The text-or-canvas choice of the dark card reached only 4.10:1 on white (at
    r = +0.66, a mid-ramp purple), so the light card asks `inkOn`, which clears
    4.5:1 on every cell (4.59:1 measured). The dark card keeps its text-or-canvas
    choice, unchanged: 4.01:1 at worst (r = -0.41), below the ink floor, and
    recorded in TODO.md rather than changed here, because dark must not move. A
    faded cell's label is set against the faded colour, 9.6:1 or more.
    """
    c = theme_results["correlation"]
    inks = {c["ink"]["text"], c["ink"]["canvas"], "#ffffff", "#000000"}
    worst = min(contrast(cell["rgb"], rgb_of(cell["label"])) for cell in c["sweep"])
    worst_faded = min(contrast(cell["shown"], rgb_of(cell["shownLabel"])) for cell in c["sweep"])
    assert all(cell["label"] in inks and cell["shownLabel"] in inks for cell in c["sweep"])
    assert worst >= 4.5, worst
    dark_worst = min(contrast(cell["rgb"], rgb_of(cell["label"])) for cell in theme_results["correlationDark"])
    assert dark_worst >= 4.0, dark_worst
    assert worst_faded >= 4.5


# --------------------------------------------- qualitative, species, tooltip --


def test_qualitative_hues_follow_the_card(theme_results):
    per = theme_results["qualitative"]["per"]
    q = theme_results["qualitative"]["palettes"]
    order = ["absolute", "trans", "local"]
    assert [per["dark"]["sources"][k] for k in order + ["xgb"]] == q["set2"][:4]
    assert [per["light"]["sources"][k] for k in order + ["xgb"]] == q["dark2"][:4]
    assert list(per["dark"]["frames"].values()) == q["set2"][:4]
    assert list(per["light"]["frames"].values()) == q["dark2"][:4]
    for theme in ("dark", "light"):
        assert per[f"printFrom_{theme}"]["sources"] == per["light"]["sources"]
        assert per[f"printFrom_{theme}"]["frames"] == per["light"]["frames"]
    for hue in q["dark2"][:4]:
        assert contrast(rgb_of(hue), WHITE) >= 3.0


def test_the_species_palette_follows_the_card(theme_results):
    per = theme_results["qualitative"]["per"]
    q = theme_results["qualitative"]["palettes"]
    for theme, name in (("dark", "species"), ("light", "species_print")):
        colours = [rgb_of(q[name][i]) for i in range(8)]
        assert [tuple(x) for x in per[theme]["speciesTable"]] == colours, theme
        for code, colour in per[theme]["species"]:
            assert rgb_of(colour) == colours[min(code, 7)], (theme, code)
    for colour in q["species_print"]:
        assert contrast(rgb_of(colour), WHITE) >= 3.0


def test_the_tooltip_ground_follows_the_theme(theme_results):
    per = theme_results["qualitative"]["per"]
    assert per["dark"]["tooltip"] == "rgba(22,27,34,0.95)" and per["dark"]["tooltipBorder"] == "#30363d"
    assert per["light"]["tooltip"] == "rgba(255,255,255,0.97)" and per["light"]["tooltipBorder"] == "#d0d7de"
    assert per["printFrom_dark"]["tooltip"] == per["printFrom_light"]["tooltip"] == theme_results["themes"]["print"]["tooltipBackground"]
    assert contrast(rgb_of("#111827"), WHITE) >= 4.5


# --------------------------------------------------------------- the exhibits --


@pytest.mark.parametrize("key", ["ramps:screen", "ramps:paper", "puor:screen", "puor:paper"])
def test_the_methodology_exhibits_do_not_depend_on_the_screen_theme(theme_results, key):
    assert theme_results["exhibits"][key] == {"light": True, "print": True}


def test_the_exhibits_name_the_card_they_are_measured_against(theme_results):
    source = theme_results["exhibitsSource"]
    assert not source["readsTheme"]
    assert source["calls"] == ["legibleRamp(palette, CARD_HEX)", "legibleRamp(palette, CARD_HEX)"]
