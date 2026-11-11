"""The literature curves' identity colours, measured again on what the code ships.

Martin's decision of 2026-11-11: the energy-resolution card's E view draws only
the literature curve its ratio panel divides by, in a colour of its own, the
same in every state of the card (`palette.js` `LITERATURE_COLOURS`, picked by
`THEME.qualitativePalette`, so no THEME key is added). `palette.js` records
how the two pairs were chosen; a Node script reads the colours the panel draws
on each card (the dark screen, the light screen and print) with that card's
tokens, and the measurements are taken here again, with the functions
`tests/test_js_voxels.py` uses for the species palette (WCAG contrast;
Machado, Oliveira & Fernandes 2009, severity 1, in linear RGB; CIEDE2000,
checked there against Sharma, Wu & Dalal's reference pairs):

* every colour is a ColorBrewer qualitative colour, and the panel draws the
  pair of its card: Set2's card (dark) the dark pair, Dark2's (light, print)
  the white pair, with no THEME key of its own;
* each clears 3:1 against the card it is drawn on;
* under normal vision, deuteranopia and protanopia the two curves stay apart,
  and each stays apart from every series colour that can share its card: the
  deposit ink (THEME.text) and the four hues E2 gives the model series
  (`perf_bins.sourceColours`), to the worst pair palette.js records;
* each curve keeps one hue on both cards, the one the drawer names;
* the recorded choice is the selection rule's: the white card binds the hue
  families, the largest worst pair within them wins, a tie within 0.1 ΔE00 going
  to the higher contrast; the dark card's unconstrained optimum is the one
  palette.js says was given up.

Skipped without `node`.
"""

from __future__ import annotations

import itertools
import json
import math
import subprocess

import pytest
from test_js_voxels import CVD, JS, NODE, _contrast, _de2000, _hex, _lab, _simulate

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: The ColorBrewer qualitative schemes at their largest class counts: the union the species and the literature
#: colours were chosen from (palette.js).
COLORBREWER_QUALITATIVE = {
    "Accent": ["#7fc97f", "#beaed4", "#fdc086", "#ffff99", "#386cb0", "#f0027f", "#bf5b17", "#666666"],
    "Dark2": ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d", "#666666"],
    "Paired": ["#a6cee3", "#1f78b4", "#b2df8a", "#33a02c", "#fb9a99", "#e31a1c", "#fdbf6f", "#ff7f00",
               "#cab2d6", "#6a3d9a", "#ffff99", "#b15928"],
    "Pastel1": ["#fbb4ae", "#b3cde3", "#ccebc5", "#decbe4", "#fed9a6", "#ffffcc", "#e5d8bd", "#fddaec", "#f2f2f2"],
    "Pastel2": ["#b3e2cd", "#fdcdac", "#cbd5e8", "#f4cae4", "#e6f5c9", "#fff2ae", "#f1e2cc", "#cccccc"],
    "Set1": ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#ffff33", "#a65628", "#f781bf", "#999999"],
    "Set2": ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3"],
    "Set3": ["#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462", "#b3de69", "#fccde5",
             "#d9d9d9", "#bc80bd", "#ccebc5", "#ffed6f"],
}
UNION = sorted({c for colours in COLORBREWER_QUALITATIVE.values() for c in colours})

#: What palette.js records, per card: the pair, and the worst CIEDE2000 distance (over the three visions) of the
#: pair and of each colour against the five series colours, with the pair that sets it.
RECORDED = {
    "set2": {"pair": {"pi": "#b15928", "e": "#984ea3"}, "worst": 17.16, "at": ("#984ea3", "#8da0cb", "deuteranopia")},
    "dark2": {"pair": {"pi": "#a65628", "e": "#6a3d9a"}, "worst": 8.79, "at": ("#a65628", "#d95f02", "protanopia")},
}
#: The drawn media: the card each is drawn on and the series palette that picks its pair.
MEDIA = {"dark": ("#1c2128", "set2"), "light": ("#ffffff", "dark2"), "print": ("#ffffff", "dark2")}
#: Within this many ΔE00 two worst pairs tie, and the higher contrast takes the tie (palette.js).
TIE = 0.1

_SCRIPT = r"""
import fs from 'node:fs';
const [jsRoot, fixtureDir] = JSON.parse(process.argv[1]);
const imp = (p) => import(`${jsRoot}/${p}`);
const scale = await imp('scale.js');
const palette = await imp('palette.js');
const perf = await imp('panels/perf_bins.js');
const rs = await imp('panels/resolution_scaling.js');
const { PRINT_TOKENS } = await imp('export/tokens.js');
const payload = JSON.parse(fs.readFileSync(`${fixtureDir}/res_scaling_two.json`, 'utf8'));
const W = { width: 760, height: rs.ENERGY_VIEW_PX };

/* What one card draws: its tokens, E2's four hues there, and the literature curve the E view draws under each reference,
 * read off the option as painted (the line's strokes, the end label's fill, the swatch, the caret). */
function card() {
  const T = scale.THEME;
  const drawn = {};
  for (const reference of ['deposit', 'pi', 'e']) {
    const opts = { view: 'energy', windows: 'all', shower: 'both', reference };
    const model = rs.energyModel(payload, opts);
    const { option } = rs.energyViewOption(payload, opts, W);
    const api = { coord: (p) => [Number(p[0]), Number(p[1])] };
    const lit = option.series.filter((s) => (s.id ?? '').startsWith('literature|'));
    drawn[reference] = {
      model: model.literature.map((l) => ({ key: l.key, colour: l.colour })),
      ids: lit.map((s) => s.id),
      strokes: [...new Set(lit.filter((s) => !/\|(endlabels|caret)$/.test(s.id))
        .flatMap((s) => s.renderItem({ dataIndex: 0 }, api).children.map((c) => c.style.stroke)))],
      labels: lit.filter((s) => s.id.endsWith('|endlabels')).flatMap((s) => s.renderItem({ dataIndex: 0 }, api).children
        .map((c) => [c.style.text, c.style.fill])),
      swatches: [].concat(option.legend ?? []).flatMap((l) => l.data ?? []).filter((d) => / lit\. — /.test(d?.name ?? ''))
        .map((d) => d.itemStyle?.color ?? null),
    };
  }
  return { card: T.card, text: T.text, muted: T.muted, palette: T.qualitativePalette,
    hues: Object.values(perf.sourceColours(perf.SOURCE_ORDER)), drawn };
}

const out = { colours: palette.LITERATURE_COLOURS, hues: palette.LITERATURE_HUES, themeKeys: Object.keys(scale.SCREEN_THEME),
  lightKeys: Object.keys(scale.SCREEN_THEMES.light), media: {} };
scale.setScreenTheme('dark');
out.media.dark = card();
scale.setScreenTheme('light');
out.media.light = card();
scale.setScreenTheme('dark');
// The exporter's swap (export/figure.js): the print tokens over the screen theme for one synchronous build.
const saved = { ...scale.THEME };
Object.assign(scale.THEME, PRINT_TOKENS);
out.media.print = card();
scale.restoreScreenTheme();
Object.assign(scale.THEME, saved);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    fixtures = JS.parent.parent.parent / "tests" / "fixtures" / "payloads"
    done = subprocess.run([NODE, "--input-type=module", "-e", _SCRIPT, json.dumps([JS.as_uri(), str(fixtures)])],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _de(a: str, b: str, vision: str) -> float:
    matrix = CVD[vision]
    return _de2000(_lab(tuple(round(c) for c in _simulate(_hex(a), matrix))),
                   _lab(tuple(round(c) for c in _simulate(_hex(b), matrix))))


def _worst(pairs) -> tuple[float, tuple[str, str, str]]:
    return min(((_de(a, b, v), (a, b, v)) for a, b in pairs for v in CVD), key=lambda t: t[0])


def _series(medium: dict) -> list[str]:
    """Every series colour that can share the card: the deposit ink and E2's four hues."""
    return [medium["text"], *medium["hues"]]


def _pairs(pair: dict, series: list[str]) -> list[tuple[str, str]]:
    return [(pair["pi"], pair["e"])] + [(c, s) for c in pair.values() for s in series]


def _hue_angle(colour: str) -> float:
    _, a, b = _lab(_hex(colour))
    return math.degrees(math.atan2(b, a)) % 360


def test_the_recorded_pairs_are_colorbrewer_qualitative_colours(out):
    assert out["colours"] == {name: rec["pair"] for name, rec in RECORDED.items()}
    for pair in out["colours"].values():
        assert set(pair) == {"pi", "e"} and pair["pi"] != pair["e"]
        assert all(c in UNION for c in pair.values()), pair


@pytest.mark.parametrize("name", sorted(MEDIA))
def test_each_medium_draws_its_cards_pair_and_only_the_curve_in_force(out, name):
    card, palette = MEDIA[name]
    medium = out["media"][name]
    assert (medium["card"].lower(), medium["palette"]) == (card, palette)
    pair = out["colours"][palette]
    assert medium["drawn"]["deposit"] == {"model": [], "ids": [], "strokes": [], "labels": [], "swatches": []}
    for ref, particle in (("pi", "π±"), ("e", "e±")):
        got = medium["drawn"][ref]
        assert got["model"] == [{"key": ref, "colour": pair[ref]}]
        assert {i.split("|")[1] for i in got["ids"]} == {ref} and f"literature|{ref}" in got["ids"]
        assert got["strokes"] == [pair[ref]] and got["swatches"] == [pair[ref]]
        assert got["labels"] == [[particle, pair[ref]]]
    assert medium["drawn"]["pi"]["strokes"] != medium["drawn"]["e"]["strokes"]


def test_no_theme_key_carries_them(out):
    """The pair is picked by the series palette, so the dark golden's theme record does not move."""
    assert out["themeKeys"] == out["lightKeys"]
    assert not [k for k in out["themeKeys"] if "literature" in k.lower() or k.lower().startswith("lit")]


@pytest.mark.parametrize("name", sorted(MEDIA))
def test_each_colour_clears_three_to_one_against_its_card(out, name):
    medium = out["media"][name]
    for colour in out["colours"][medium["palette"]].values():
        assert _contrast(_hex(colour), _hex(medium["card"].lower())) >= 3.0, (name, colour)


@pytest.mark.parametrize("name", sorted(MEDIA))
def test_the_curves_stay_apart_from_each_other_and_every_series_colour_in_three_visions(out, name):
    medium = out["media"][name]
    rec = RECORDED[medium["palette"]]
    series = _series(medium)
    assert len(series) == 5 and len(set(series)) == 5
    worst, at = _worst(_pairs(out["colours"][medium["palette"]], series))
    assert worst == pytest.approx(rec["worst"], abs=0.01) and at == rec["at"], (name, worst, at)
    # The two curves themselves are far apart in every vision.
    pair = out["colours"][medium["palette"]]
    assert min(_de(pair["pi"], pair["e"], v) for v in CVD) >= 39.0


def test_each_curve_keeps_one_hue_on_both_cards(out):
    """π± a brown and e± a purple on the dark card and on white, as the drawer names them (LITERATURE_HUES)."""
    assert out["hues"] == {"pi": "brown", "e": "purple"}
    dark, white = out["colours"]["set2"], out["colours"]["dark2"]
    for key, (lo, hi) in (("pi", (40, 70)), ("e", (295, 335))):
        angles = [_hue_angle(dark[key]), _hue_angle(white[key])]
        assert all(lo <= a <= hi for a in angles), (key, angles)
        assert abs(angles[0] - angles[1]) <= 15, (key, angles)


def _candidates(card: str, series: list[str]) -> list[str]:
    return [c for c in UNION if _contrast(_hex(c), _hex(card)) >= 3.0 and c not in series]


def test_the_recorded_choice_follows_the_selection_rule(out):
    dark_medium, white_medium = out["media"]["dark"], out["media"]["light"]
    dark_series, white_series = _series(dark_medium), _series(white_medium)
    # White binds the hue families: two purples and two browns keep more than 7 against Dark2's four and the ink;
    # every other qualitative colour at 3:1 on white falls to 6.0 or below.
    white = {c: _worst([(c, s) for s in white_series])[0] for c in _candidates("#ffffff", white_series)}
    above = {c for c, w in white.items() if w > 7}
    assert above == {"#6a3d9a", "#bc80bd", "#a65628", "#b15928"}, sorted(white.items(), key=lambda t: -t[1])[:6]
    assert max(w for c, w in white.items() if c not in above) <= 6.0
    # The two purples are too close to each other under protanopia to be a pair.
    assert _de("#6a3d9a", "#bc80bd", "protanopia") < 26
    # Within the families (e± a purple, π± a brown), the largest worst pair wins, a tie within 0.1 to the higher contrast.
    for medium, families in ((white_medium, (("#6a3d9a", "#bc80bd"), ("#a65628", "#b15928"))),
                             (dark_medium, None)):
        series = _series(medium)
        cands = _candidates(medium["card"].lower(), series)
        if families is None:
            # On the dark card the families are the white card's hues, read by CIELAB hue angle: a saturated purple,
            # and a brown (darker than Dark2's orange #d95f02, L* 55).
            purples = [c for c in cands if 295 <= _hue_angle(c) <= 335 and math.hypot(*_lab(_hex(c))[1:]) >= 30]
            browns = [c for c in cands if 40 <= _hue_angle(c) <= 70 and _lab(_hex(c))[0] <= 52]
            assert set(purples) == {"#7570b3", "#984ea3", "#bc80bd"} and set(browns) == {"#a65628", "#b15928", "#bf5b17"}
            families = (purples, browns)
        scored = []
        for e, pi in itertools.product(*families):
            worst, _ = _worst(_pairs({"pi": pi, "e": e}, series))
            # The tie-break: the higher contrast, the lower of the two first (the colour that differs decides).
            contrasts = tuple(sorted(_contrast(_hex(c), _hex(medium["card"].lower())) for c in (pi, e)))
            scored.append((worst, contrasts, {"pi": pi, "e": e}))
        best = max(w for w, _, _ in scored)
        tied = [s for s in scored if s[0] >= best - TIE]
        assert len(tied) == 2, tied
        chosen = max(tied, key=lambda s: s[1])[2]
        assert chosen == out["colours"][medium["palette"]], (medium["palette"], sorted(scored, key=lambda s: -s[0])[:4])
    # The dark card's largest worst pair over the whole union takes the blue #386cb0 for e±, 18.6, which white
    # cannot follow (3.4 there): the 1.4 ΔE00 palette.js says was given up for one hue per curve.
    dark_cands = _candidates("#1c2128", dark_series)
    best = max(((_worst(_pairs({"pi": a, "e": b}, dark_series))[0], {a, b})
                for a, b in itertools.combinations(dark_cands, 2)), key=lambda t: t[0])
    assert best[0] == pytest.approx(18.57, abs=0.01) and "#386cb0" in best[1]
    assert _worst([("#386cb0", s) for s in white_series])[0] == pytest.approx(3.42, abs=0.01)
    # White's largest worst pair over the whole union is the two purples, 8.86: a tie within 0.1 with the chosen 8.79.
    white_cands = _candidates("#ffffff", white_series)
    best = max(((_worst(_pairs({"pi": a, "e": b}, white_series))[0], {a, b})
                for a, b in itertools.combinations(white_cands, 2)), key=lambda t: t[0])
    assert best[0] == pytest.approx(8.86, abs=0.01) and best[1] == {"#6a3d9a", "#bc80bd"}
    assert best[0] - RECORDED["dark2"]["worst"] < TIE
