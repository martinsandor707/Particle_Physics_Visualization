"""The Methodology page's renderer, links and figures, executed under Node.

``methodology/render.js`` lays the article out as a pure node tree, so the
whole article can be checked here without a browser:

* a synthetic article exercising every block kind, nesting, the inline syntax,
  cross-references, citations, an unknown reference and TeX that does not
  compile: numbered, resolved, and every problem reported in ``errors`` with
  the block still drawn (its source as code), never thrown;
* the real ``ARTICLE``: ids unique, sections, equations, tables and figures
  numbered without gaps, every reference resolved and every TeX string
  compiled through ``math.js`` ``texToTree``, no ASCII hyphen-minus before a
  digit in any rendered text, every badge naming a card its page has and
  every badge's view patch surviving a ``State`` read from it;
* ``methodology/links.js``: a badge's href drops ``at``, carries the view keys
  verbatim and, from a cold hash, the view a cold boot would open (on the
  recorded catalogue ``tests/fixtures/payloads/experiments.json``);
* ``methodology/exhibits.js``: the Viridis marker is ``C.VIRIDIS_LEGIBLE_FROM``
  and every PuOr contrast is ``palette.js`` ``contrast``;
* Appendix B: one row per constant.

Runs on the fake document of ``test_js_physics_shell.py``. Skipped when
``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _path, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: A hyphen-minus that signs a number: one that follows no word character or closing bracket.
_HYPHEN = r"/(?<![\w)\]])-(?=\.?\d)/"

_PRELUDE = _FAKE_DOM + r"""
const urls = JSON.parse(process.argv[1]);
window.location.pathname = '/methodology';
window.location.search = '';
const render = await import(urls.render);
const links = await import(urls.links);
const exhibits = await import(urls.exhibits);
const math = await import(urls.math);
const { CONSTANTS, C } = await import(urls.constants);
const { State } = await import(urls.state);
const common = await import(urls.common);
const { contrast, PUOR_ANCHORS, SCREEN_CARD } = await import(urls.palette);
const out = {};

/* Walk a node tree: fn(node, ancestors). */
const walk = (node, fn, up = []) => {
  if (!node) return;
  if (Array.isArray(node)) { node.forEach((n) => walk(n, fn, up)); return; }
  fn(node, up);
  for (const child of node.children ?? []) walk(child, fn, [...up, node]);
};
const all = (tree, test) => { const found = []; walk(tree, (n, up) => { if (test(n, up)) found.push(n); }); return found; };
const cls = (n) => String(n.attrs?.class ?? '').split(/\s+/);
const hasClass = (name) => (n) => cls(n).includes(name);
const text = (n) => render.textOf(n);
/* Every rendered text, outside annotation, code and pre (and outside math while math.js is the stub). */
const stubMath = JSON.stringify(math.texToTree('-1')).includes('"mtext","text":"-1"');
const texts = (tree) => {
  const found = [];
  walk(tree, (n, up) => {
    const skip = [n, ...up].some((a) => ['annotation', 'code', 'pre'].includes(a.tag) || (stubMath && a.tag === 'math'));
    if (!skip && typeof n.text === 'string') found.push(n.text);
  });
  return found;
};
const HYPHEN = """ + _HYPHEN + r""";
"""

_JS_URLS = {
    "render": (JS / "methodology" / "render.js").as_uri(),
    "links": (JS / "methodology" / "links.js").as_uri(),
    "exhibits": (JS / "methodology" / "exhibits.js").as_uri(),
    "constants": (JS / "methodology" / "constants.js").as_uri(),
    "article": (JS / "methodology" / "content" / "index.js").as_uri(),
    "math": (JS / "math.js").as_uri(),
    "state": (JS / "state.js").as_uri(),
    "common": (JS / "page_common.js").as_uri(),
    "palette": (JS / "palette.js").as_uri(),
    "physics": (JS / "physics_section.js").as_uri(),
    "models": (JS / "models_cards.js").as_uri(),
    "voxels": (JS / "voxel_views.js").as_uri(),
    "frameGrid": (JS / "panels" / "frame_grid.js").as_uri(),
    "catalogue": _path("experiments"),
}


# ------------------------------------------------------- the synthetic article --

_SYNTHETIC_SCRIPT = _PRELUDE + r"""
const fixture = {
  front: {
    title: 'A *test* article',
    authors: [{ name: 'A. Author', affiliations: [1] }, { name: 'B. Author', affiliations: [1, 2] }],
    affiliations: [{ id: 1, text: 'First place' }, { id: 2, text: 'Second place' }],
    abstract: [String.raw`An abstract with $x$ that cites [[cite:k1]].`],
    keywords: ['one', 'two'],
  },
  sections: [
    {
      id: 'sec-one', title: 'One',
      blocks: [
        { kind: 'p', text: String.raw`Inline $\alpha$, a dollar \$5, a ` + '`code_span`' + String.raw`, *emphasis*, **strong**, `
          + String.raw`see [[eq-a]], ([[eq-a]]), [[tab-a]], [[fig-a]], [[sec-sub]], [[app-x]], [[lnk-one-a]], [[sec-references]] `
          + String.raw`and [[cite:k2]][[cite:k1]]. Unknown [[eq-missing]] and [[cite:nokey]]. A lone * star, 3 * 4.` },
        { kind: 'eq', id: 'eq-a', tex: 'a = b - 1' },
        { kind: 'eq', tex: 'c', numbered: false },
        { kind: 'list', ordered: true, items: [String.raw`first $y$`, 'second'] },
        { kind: 'list', items: ['bullet'] },
        { kind: 'table', id: 'tab-a', caption: 'A caption with $z$', head: ['H1', 'H2'], rows: [['a', '`b`'], ['c', 'd']], note: 'A note.' },
        { kind: 'figure', id: 'fig-a', exhibit: 'ramps', caption: 'The ramps.' },
        { kind: 'callout', tone: 'rule', title: 'A rule', text: 'First paragraph.\n\nSecond paragraph.' },
        { kind: 'links', id: 'lnk-one-a', items: [
          { page: 'physics', panel: 'xy', label: 'XY entry panel', set: { frame: 'canonical' } },
          { page: 'models', panel: 'feat-corr', label: 'Correlations' },
        ] },
        { kind: 'eq', id: 'eq-bad', tex: String.raw`\badcommand{x}` },
        { kind: 'mystery' },
      ],
      sections: [{ id: 'sec-sub', title: String.raw`Sub with $x$`, blocks: [{ kind: 'eq', id: 'eq-b', tex: 'd' }],
        sections: [{ id: 'sec-sub-deep', title: 'Deeper', blocks: [{ kind: 'figure', id: 'fig-b', exhibit: 'se3', caption: 'SE(3).' }] }] }],
    },
    { id: 'sec-two', title: 'Two', blocks: [{ kind: 'figure', id: 'fig-c', exhibit: 'puor', caption: 'PuOr.' },
      { kind: 'eq', id: 'eq-a', tex: 'e' }, { kind: 'table', id: 'figure-wrong', caption: 'x', head: ['a'], rows: [['1', '2']] }] },
  ],
  references: [{ key: 'k1', text: 'Reference one.' }, { key: 'k2', text: 'Reference two.' }, { key: 'k3', text: 'Never cited.' }],
  appendices: [
    { id: 'app-x', title: 'Extra', blocks: [{ kind: 'p', text: 'Appendix text citing [[eq-b]].' },
      { kind: 'links', id: 'lnk-app-a', items: [{ page: 'physics', panel: 'energy', label: 'Energy' }] }] },
    { id: 'app-constants', title: 'Constants', generated: 'constants' },
  ],
};
const compile = (tex, options) => {
  if (tex.includes('\\badcommand')) throw new math.MathSyntaxError('unknown command \\badcommand', { tex });
  return math.texToTree(tex, options);
};
let thrown = null;
let result;
try { result = render.layout(fixture, { compile }); } catch (error) { thrown = String(error); }
const { tree, outline, errors } = result;
out.thrown = thrown;
out.errors = errors;
const flat = (entries) => entries.flatMap((e) => [[e.id, e.number], ...flat(e.children)]);
out.outline = flat(outline);
out.headings = all(tree, (n) => /^h[1-6]$/.test(n.tag) && n.attrs?.id).map((n) => [n.tag, n.attrs.id, text(n)]);
out.numbers = all(tree, hasClass('eq-number')).map(text);
out.equations = all(tree, (n) => n.tag === 'figure' && hasClass('equation')(n)).map((n) => n.attrs.id);
out.displays = all(tree, hasClass('math-display')).length;
out.xrefs = all(tree, (n) => n.tag === 'a' && hasClass('xref')(n)).map((n) => [n.attrs['data-goto'], text(n), n.attrs.href]);
out.cites = all(tree, hasClass('cite')).map(text);
out.references = all(tree, (n) => n.tag === 'li' && String(n.attrs?.id ?? '').startsWith('ref-')).map((n) => [n.attrs.id, text(n)]);
const paragraph = all(tree, (n) => n.tag === 'p' && text(n).startsWith('Inline'))[0];
out.inline = paragraph.children.filter((c) => c.tag).map((c) => [c.tag, text(c)]).slice(0, 5);
out.literal = paragraph.children.filter((c) => !c.tag).map((c) => c.text).join('');
out.missing = all(tree, hasClass('ref-missing')).map(text);
const bad = all(tree, (n) => n.attrs?.id === 'eq-bad')[0];
out.badTex = all(bad, hasClass('tex-error')).map((n) => [n.tag, text(n)]);
out.blockError = all(tree, hasClass('block-error')).map((n) => [n.tag, text(n).includes('mystery')]);
out.captions = all(tree, (n) => n.tag === 'figcaption').map(text);
out.tables = all(tree, (n) => n.tag === 'figure' && hasClass('article-table')(n)).map((n) => n.attrs.id);
const constantsTable = all(tree, (n) => n.attrs?.id === 'tab-constants')[0];
out.constantRows = all(constantsTable, (n) => n.tag === 'tr' && n.children.every((c) => c.tag === 'td')).length;
out.constantNames = all(constantsTable, (n) => n.tag === 'tr' && n.children[0]?.tag === 'td').map((n) => text(n.children[0]));
out.constantCount = Object.keys(CONSTANTS).length;
out.badges = all(tree, (n) => n.tag === 'a' && 'data-badge' in (n.attrs ?? {})).map((n) => [text(n), n.attrs.href, n.attrs['data-set'],
  n.attrs['data-from'] ?? null, n.attrs['data-from-sec'] ?? null]);
out.callout = all(tree, (n) => n.tag === 'aside').map((n) => [n.attrs.class, n.children.length]);
out.lists = all(tree, hasClass('article-list')).map((n) => n.tag);
out.toggles = all(tree, (n) => n.tag === 'button' && 'data-tex-toggle' in n.attrs).map((n) => [n.attrs['aria-expanded'], n.attrs['aria-controls']]);
out.panels = all(tree, hasClass('tex-panel')).map((n) => [n.attrs.id, n.attrs.hidden, all(n, (c) => c.tag === 'code').map(text)[0]]);
out.mathTitles = all(tree, (n) => 'data-tex-math' in (n.attrs ?? {})).map((n) => n.attrs.title);
out.front = { title: text(all(tree, hasClass('article-title'))[0]), authors: text(all(tree, hasClass('authors'))[0]),
  provenance: text(all(tree, hasClass('provenance'))[0]), keywords: text(all(tree, hasClass('keywords'))[0]) };
out.toc = render.textOf(render.tocTree(outline));
out.tocLinks = all(render.tocTree(outline), (n) => n.tag === 'a').map((n) => [n.attrs['data-goto'], 'data-mark' in n.attrs]);
// The real compiler, once it lands, rejects the unknown command itself.
let realThrows = false;
try { math.texToTree('\\badcommand{x}', { display: true }); } catch { realThrows = true; }
out.realThrows = realThrows;
if (realThrows) out.realErrors = render.layout(fixture).errors.filter((e) => e.includes('TeX'));
// The content modules are read, never written: numbering lives on copies.
out.untouched = fixture.sections[0].blocks[1].__number === undefined;

// Mount: elements, the SVG and MathML namespaces, text nodes; nothing parsed from a string.
const created = [];
document.createElementNS = (ns, tag) => { const el = document.createElement(tag); el.namespaceURI = ns; created.push([ns, tag]); return el; };
FakeElement.prototype.contains = function (node) { for (let n = node; n; n = n.parent) if (n === this) return true; return false; };
const mounted = render.mount(tree);
out.mounted = { root: mounted.tagName, svg: created.filter(([ns]) => ns === 'http://www.w3.org/2000/svg').length,
  mathml: created.filter(([ns]) => ns === 'http://www.w3.org/1998/Math/MathML').length,
  hiddenPanel: mounted.find((el) => String(el.getAttribute('class')).includes('tex-panel'))?.getAttribute('hidden') };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def synthetic() -> dict:
    return _run(_SYNTHETIC_SCRIPT, _JS_URLS)


def test_a_bad_block_is_reported_never_thrown(synthetic):
    r = synthetic
    assert r["thrown"] is None
    errors = "\n".join(r["errors"])
    for needle in ("unknown reference [[eq-missing]]", "unknown citation [[cite:nokey]]", "TeX does not compile",
                   "unknown block kind mystery", "duplicate id eq-a", "does not have the table prefix",
                   "row 0 has 2 cells, the head 1"):
        assert needle in errors, needle
    # The unknown reference and citation are shown as such, in place.
    assert r["missing"] == ["[[eq-missing]]", "?"]
    # Bad TeX keeps its number and shows its source as code; an unknown block shows its source.
    assert r["badTex"] == [["pre", "\\badcommand{x}"]]
    assert r["blockError"] == [["pre", True]]
    assert r["untouched"] is True


def test_the_real_compiler_rejects_bad_tex_too(synthetic):
    if not synthetic["realThrows"]:
        pytest.skip("math.js is still the stub")
    assert synthetic["realErrors"], "the bad TeX must be reported by the real compiler"


def test_sections_are_numbered_with_appendices_lettered_and_references_unnumbered(synthetic):
    assert synthetic["outline"] == [
        ["sec-one", "1"], ["sec-sub", "1.1"], ["sec-sub-deep", "1.1.1"], ["sec-two", "2"],
        ["sec-references", ""], ["app-x", "A"], ["app-constants", "B"],
    ]
    headings = {hid: (tag, text) for tag, hid, text in synthetic["headings"]}
    assert headings["sec-one"][0] == "h2" and headings["sec-sub"][0] == "h3" and headings["sec-sub-deep"][0] == "h4"
    assert headings["sec-sub"][1].startswith("1.1 Sub with")
    assert headings["app-x"][1].startswith("Appendix A Extra")
    assert headings["sec-references"][1].startswith("References")


def test_equations_tables_and_figures_are_numbered_in_document_order(synthetic):
    r = synthetic
    # eq-a, eq-bad, eq-b in the sub-section, the duplicate eq-a: four numbered, one unnumbered display.
    assert r["numbers"] == ["(1)", "(2)", "(3)", "(4)"]
    assert len(r["equations"]) == 4 and r["displays"] == 5
    captions = r["captions"]
    assert [c.split(".")[0] for c in captions if c.startswith(("Table", "Figure"))] == [
        "Table 1", "Figure 1", "Figure 2", "Figure 3", "Table 2", "Table 3"]
    assert r["tables"] == ["tab-a", "figure-wrong", "tab-constants"]


def test_cross_references_resolve_to_their_labels(synthetic):
    refs = [(target, label) for target, label, _ in synthetic["xrefs"]]
    assert refs[:8] == [("eq-a", "(1)"), ("eq-a", "1"), ("tab-a", "Table 1"), ("fig-a", "Figure 1"),
                        ("sec-sub", "§1.1"), ("app-x", "Appendix A"), ("lnk-one-a", "§1"),
                        ("sec-references", "References")]
    assert ("eq-b", "(3)") in refs
    # Hrefs are the page's own, with `at`; the page keeps them live with the view.
    assert synthetic["xrefs"][0][2] == "/methodology#at=eq-a"


def test_citations_are_numbered_by_first_citation_and_only_cited_works_listed(synthetic):
    r = synthetic
    # The abstract cites k1 first; adjacent citations share one bracket.
    assert r["cites"][0] == "[1]" and "[2, 1]" in r["cites"] and "[?]" in r["cites"]
    assert r["references"] == [["ref-k1", "[1] Reference one."], ["ref-k2", "[2] Reference two."]]


def test_the_inline_syntax(synthetic):
    r = synthetic
    assert [tag for tag, _ in r["inline"]] == ["math", "code", "em", "strong", "a"]
    assert r["inline"][1][1] == "code_span" and r["inline"][2][1] == "emphasis" and r["inline"][3][1] == "strong"
    # An escaped dollar and a lone or spaced asterisk stay literal.
    assert "a dollar $5" in r["literal"] and "A lone * star, 3 * 4." in r["literal"]


_ESCAPES_SCRIPT = _PRELUDE + r"""
out.tokens = render.tokenize(String.raw`\*not em\* and 2\*3\*4, a \`tick\`, \[[sec-x]] and \$5`);
console.log(JSON.stringify(out));
"""


def test_escapes_write_their_character():
    """\\$ \\* \\` \\[ write the character itself, outside its markup role."""
    tokens = _run(_ESCAPES_SCRIPT, _JS_URLS)["tokens"]
    assert tokens == [{"type": "text", "value": "*not em* and 2*3*4, a `tick`, [[sec-x]] and $5"}]


def test_every_block_kind_is_drawn(synthetic):
    r = synthetic
    assert r["lists"] == ["ol", "ul"]
    assert r["callout"] == [["callout callout-rule", 3]]
    assert r["front"]["title"] == "A test article"
    assert r["front"]["authors"] == "A. Author1, B. Author1,2"
    assert r["front"]["provenance"] == "calosrv … · static build … · rendered …"
    assert r["front"]["keywords"] == "Keywords one · two"


def test_each_equation_has_a_tex_toggle_and_a_hidden_panel(synthetic):
    r = synthetic
    assert len(r["toggles"]) == 5 and all(expanded == "false" for expanded, _ in r["toggles"])
    controls = [c for _, c in r["toggles"]]
    assert controls[0] == "eq-a-tex" and len(set(controls)) == len(controls) - 1  # the duplicate eq-a
    assert ["eq-a-tex", True, "a = b - 1"] in r["panels"]
    assert set(r["mathTitles"]) == {"Show the LaTeX source"}


def test_badges_name_their_page_panel_row_and_section(synthetic):
    assert synthetic["badges"] == [
        ["Open in Physics → XY entry panel", "/?panel=xy&from=lnk-one-a&from_sec=1", '{"frame":"canonical"}',
         "lnk-one-a", "1"],
        ["Open in Models → Correlations", "/models?panel=feat-corr&from=lnk-one-a&from_sec=1", "{}", "lnk-one-a", "1"],
        # An appendix is not a section number: the landing page names "the Methodology" alone.
        ["Open in Physics → Energy", "/?panel=energy&from=lnk-app-a", "{}", "lnk-app-a", None],
    ]


def test_appendix_b_has_one_row_per_constant(synthetic):
    r = synthetic
    assert r["constantRows"] == r["constantCount"]
    assert len(set(r["constantNames"])) == r["constantCount"]


def test_the_outline_and_mount(synthetic):
    r = synthetic
    assert r["toc"].startswith("1One1.1Sub with")
    assert all(mark for _, mark in r["tocLinks"]) and r["tocLinks"][0] == ["sec-one", True]
    m = r["mounted"]
    assert m["root"] == "DIV" and m["svg"] > 100 and m["hiddenPanel"] == ""


# ------------------------------------------------------------- the real article --

_ARTICLE_SCRIPT = _PRELUDE + r"""
const { ARTICLE } = await import(urls.article);
const { PHYSICS_CARDS } = await import(urls.physics);
const { MODELS_CARDS } = await import(urls.models);
const { VOXEL_CARDS } = await import(urls.voxels);
const { GRID_ROWS, GRID_COLS } = await import(urls.frameGrid);
const { tree, outline, errors } = render.layout(ARTICLE);
out.errors = errors;
const ids = all(tree, (n) => n.attrs?.id).map((n) => n.attrs.id);
out.duplicates = ids.filter((id, i) => ids.indexOf(id) !== i);
out.numbers = all(tree, hasClass('eq-number')).map(text);
out.equations = all(tree, (n) => n.tag === 'figure' && hasClass('equation')(n)).length;
out.tableNumbers = all(tree, (n) => n.tag === 'figure' && hasClass('article-table')(n))
  .map((n) => text(all(n, hasClass('caption-label'))[0]));
out.figureNumbers = all(tree, (n) => n.tag === 'figure' && hasClass('article-figure')(n))
  .map((n) => text(all(n, hasClass('caption-label'))[0]));
const numbersOf = (entries) => entries.map((e) => [e.number, numbersOf(e.children)]);
out.outline = numbersOf(outline);
out.hyphens = texts(tree).filter((t) => HYPHEN.test(t));
out.stubMath = stubMath;
// Every TeX string, compiled on its own.
const tex = [];
const collect = (s) => { for (const m of String(s ?? '').replace(/\\\$/g, '').matchAll(/\$([^$]*)\$/g)) tex.push(m[1]); };
const visit = (part) => {
  collect(part.title);
  for (const b of part.blocks ?? []) {
    if (b.kind === 'eq') tex.push(b.tex);
    [b.text, b.caption, b.note, b.title, ...(b.items ?? []).filter((i) => typeof i === 'string'), ...(b.head ?? []),
      ...(b.rows ?? []).flat()].forEach(collect);
  }
  (part.sections ?? []).forEach(visit);
};
[...ARTICLE.sections, ...ARTICLE.appendices].forEach(visit);
(ARTICLE.front.abstract ?? []).forEach(collect);
out.texCount = tex.length;
out.texFailures = [];
for (const source of tex) { try { math.texToTree(source); } catch (e) { out.texFailures.push(`${source}: ${e.message}`); } }
// Badges: a card of their page, and a patch that survives a State read from it.
const cards = {
  // The compare-frames view's cells are cards too (FrameGrid ids compare-<row>-<col>).
  physics: new Set([...PHYSICS_CARDS.map((c) => c.id), 'xy', 'yz', 'xz', 'energy',
    ...GRID_ROWS.flatMap((row) => GRID_COLS.map((col) => `compare-${row}-${col}`))]),
  models: new Set([...MODELS_CARDS.map((c) => c.id), ...VOXEL_CARDS.map((c) => c.id)]),
};
const items = [];
const visitLinks = (part) => {
  for (const b of part.blocks ?? []) if (b.kind === 'links') items.push(...b.items.map((i) => ({ ...i, row: b.id })));
  (part.sections ?? []).forEach(visitLinks);
};
[...ARTICLE.sections, ...ARTICLE.appendices].forEach(visitLinks);
out.badges = items.length;
out.unknownPanels = items.filter((i) => !cards[i.page]?.has(i.panel)).map((i) => `${i.row}: ${i.page}/${i.panel}`);
out.lostPatches = [];
for (const item of items) {
  if (!item.set) continue;
  window.location.hash = `#${common.hashWith('', item.set)}`;
  const state = new State();
  for (const [key, value] of Object.entries(item.set)) {
    if (String(state.get(key)) !== String(value)) out.lostPatches.push(`${item.row}: ${key}=${value}`);
  }
}
window.location.hash = '';
const constantsTable = all(tree, (n) => n.attrs?.id === 'tab-constants')[0];
out.constantRows = all(constantsTable, (n) => n.tag === 'tr' && n.children.every((c) => c.tag === 'td')).length;
out.constantCount = Object.keys(CONSTANTS).length;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def article() -> dict:
    return _run(_ARTICLE_SCRIPT, _JS_URLS)


def test_the_article_lays_out_without_a_problem(article):
    assert article["errors"] == []


def test_the_article_ids_are_unique(article):
    assert article["duplicates"] == []


def test_the_article_is_numbered_without_gaps(article):
    r = article
    assert r["numbers"] == [f"({n})" for n in range(1, r["equations"] + 1)]
    assert r["tableNumbers"] == [f"Table {n}." for n in range(1, len(r["tableNumbers"]) + 1)]
    assert r["figureNumbers"] == [f"Figure {n}." for n in range(1, len(r["figureNumbers"]) + 1)]

    def check(entries, prefix=""):
        top = [number for number, _ in entries]
        main = [n for n in top if n and n[-1].isdigit()]
        assert main == [f"{prefix}{i}" for i in range(1, len(main) + 1)], top
        for number, children in entries:
            if children:
                check(children, f"{number}.")

    check(r["outline"])
    letters = [n for n, _ in r["outline"] if n and n[0].isalpha()]
    assert letters == [chr(65 + i) for i in range(len(letters))]
    assert "" in [n for n, _ in r["outline"]], "the References are listed, unnumbered"


def test_every_tex_string_compiles(article):
    assert article["texFailures"] == []


def test_no_rendered_text_signs_a_number_with_a_hyphen(article):
    assert article["hyphens"] == []


def test_every_badge_names_a_card_of_its_page(article):
    assert article["unknownPanels"] == []


def test_every_badge_patch_survives_a_state_read_from_it(article):
    assert article["lostPatches"] == []


def test_appendix_b_lists_every_constant(article):
    assert article["constantRows"] == article["constantCount"] > 0


# ------------------------------------------------------------------- the links --

_LINKS_SCRIPT = _PRELUDE + r"""
const catalogue = load(urls.catalogue);
const href = (set = {}, opts = {}) => links.badgeHref({ page: 'models', panel: 'feat-corr', set }, { from: 'lnk-a', section: '2.1', ...opts });
// A warm hash travels verbatim, minus `at`, with the badge's patch on top.
window.location.hash = '#table_name=t&e1_min=1.234&frame=local&at=eq-x';
out.warm = href();
out.warmSet = href({ frame: 'canonical' });
out.warmCatalogue = href({}, { catalogue });
out.warmChip = links.viewChipText({ catalogue });
// A cold hash (no view key; `at` is no State key): the raw hash until the catalogue loads, then the effective view.
window.location.hash = '#at=sec-frames';
out.coldRaw = href();
out.coldChip = links.viewChipText({});
out.cold = href({}, { catalogue });
out.coldSet = href({ frame: 'canonical' }, { catalogue });
out.coldChipLoaded = links.viewChipText({ catalogue });
const saved = { ...catalogue, defaults: { ...catalogue.defaults, table_name: 'gone', frame: 'local', model: 'energy', channel: 'shapcam' } };
out.coldDefaults = href({}, { catalogue: saved });
out.coldDefaultsChip = links.viewChipText({ catalogue: saved });
out.coldHashAfter = window.location.hash;
// The section a badge row sits in: a number, or nothing for an appendix.
out.appendix = links.badgeQuery({ panel: 'xy', from: 'lnk-b', section: 'A' });
out.text = links.badgeText({ page: 'physics', label: 'D–Y′ entry panel' });
// A Physics badge leaves a pinned event and the compare view, which hide the ensemble panels, unless it sets them.
const physicsHref = (set = {}) => links.badgeHref({ page: 'physics', panel: 'xy', set }, { from: 'lnk-a', section: '2.1' });
window.location.hash = '#table_name=t&event=7&compare=true&frame=local';
out.physicsLeaves = physicsHref();
out.physicsCompare = links.badgeHref({ page: 'physics', panel: 'compare-lab-xy', set: { compare: true } }, { from: 'lnk-a', section: '3.1' });
out.modelsKeeps = href();
// A catalogue with nothing ready names no experiment.
window.location.hash = '#frame=local';
out.noneReadyChip = links.viewChipText({ catalogue: { ...catalogue, experiments: catalogue.experiments.map((e) => ({ ...e, status: 'ingesting' })) } });
// `at`: the page's only hash write.
window.location.hash = '#table_name=t&at=old';
replaced = [];
links.writeAt('eq-se3');
out.writes = replaced;
out.readAt = links.readAt();
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def link_results() -> dict:
    return _run(_LINKS_SCRIPT, _JS_URLS)


def test_a_warm_badge_carries_the_view_verbatim_without_at(link_results):
    r = link_results
    assert r["warm"] == "/models?panel=feat-corr&from=lnk-a&from_sec=2.1#table_name=t&e1_min=1.234&frame=local"
    assert r["warmSet"] == "/models?panel=feat-corr&from=lnk-a&from_sec=2.1#table_name=t&e1_min=1.234&frame=canonical"
    # The catalogue never overrides a view the reader brought.
    assert r["warmCatalogue"] == r["warm"]
    # "t" is not in the catalogue, so the other page would open the first ready experiment.
    assert r["warmChip"] == ("Baseline (demonstration dataset) · Separation-Aligned (D-Frame) › Local · "
                             "Segmentation Model")


def test_a_cold_badge_carries_the_view_a_cold_boot_would_open(link_results):
    r = link_results
    assert r["coldRaw"] == "/models?panel=feat-corr&from=lnk-a&from_sec=2.1"
    assert r["coldChip"] is None
    assert r["cold"] == "/models?panel=feat-corr&from=lnk-a&from_sec=2.1#table_name=experiment_baseline"
    assert r["coldSet"] == "/models?panel=feat-corr&from=lnk-a&from_sec=2.1#table_name=experiment_baseline&frame=canonical"
    assert r["coldChipLoaded"] == "Baseline (demonstration dataset) · Absolute · Segmentation Model"
    # Saved defaults apply, and an experiment that is not ready falls back to the first ready one.
    assert r["coldDefaults"] == ("/models?panel=feat-corr&from=lnk-a&from_sec=2.1"
                                 "#table_name=experiment_baseline&frame=local&channel=shapcam&model=energy")
    assert r["coldDefaultsChip"].startswith("Baseline (demonstration dataset) · ")
    assert "Energy Estimation Model" in r["coldDefaultsChip"]
    # The effective view is never written to the address bar.
    assert r["coldHashAfter"] == "#at=sec-frames"


def test_a_physics_badge_leaves_a_pinned_event_and_the_compare_view(link_results):
    r = link_results
    assert r["physicsLeaves"] == "/?panel=xy&from=lnk-a&from_sec=2.1#table_name=t&frame=local"
    # A badge about the compare view sets it, on a compare cell.
    assert r["physicsCompare"] == "/?panel=compare-lab-xy&from=lnk-a&from_sec=3.1#table_name=t&compare=true&frame=local"
    # The Models page has no view mode that hides its cards: its badges carry the hash as it is.
    assert r["modelsKeeps"] == "/models?panel=feat-corr&from=lnk-a&from_sec=2.1#table_name=t&event=7&compare=true&frame=local"


def test_the_chip_names_no_experiment_when_none_is_ready(link_results):
    assert link_results["noneReadyChip"].startswith("no experiment ready · ")


def test_badge_query_and_text(link_results):
    assert link_results["appendix"] == "?panel=xy&from=lnk-b"
    assert link_results["text"] == "Open in Physics → D–Y′ entry panel"


def test_the_only_hash_write_records_at(link_results):
    assert link_results["writes"] == ["/methodology#table_name=t&at=eq-se3"]
    assert link_results["readAt"] == "eq-se3"


# ----------------------------------------------------------------- the figures --

_EXHIBITS_SCRIPT = _PRELUDE + r"""
const ramps = exhibits.rampsExhibit();
out.viridis = all(ramps, (n) => n.attrs?.['data-palette'] === 'viridis').map((n) => [n.attrs['data-from'], text(n)]);
out.legible = C.VIRIDIS_LEGIBLE_FROM;
out.rampPalettes = all(ramps, hasClass('ramp-legible')).map((n) => n.attrs['data-palette']);
const puor = exhibits.puorExhibit();
const grounds = { card: SCREEN_CARD, white: [255, 255, 255] };
out.anchors = all(puor, hasClass('puor-anchor')).map((n) => {
  const i = Number(n.attrs['data-index']);
  const expected = contrast(PUOR_ANCHORS[i], grounds[n.attrs['data-ground']]).toFixed(2);
  const shown = all(n, (c) => c.tag === 'text').map(text)[0];
  return [n.attrs['data-ground'], i, n.attrs['data-contrast'], shown, expected];
});
out.firstLegible = all(puor, hasClass('puor-first-legible')).map((n) => [n.attrs['data-arm'], Number(n.attrs['data-contrast'])]);
const se3 = exhibits.se3Exhibit();
out.se3 = { text: texts(se3).join(' '), frames: all(se3, hasClass('se3-frame')).map((n) => [n.attrs.width, n.attrs.height]) };
out.hyphens = [ramps, puor, se3].flatMap((t) => texts(t)).filter((t) => HYPHEN.test(t));
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def figures() -> dict:
    return _run(_EXHIBITS_SCRIPT, _JS_URLS)


def test_the_viridis_marker_is_the_constant(figures):
    [(marked, shown)] = figures["viridis"]
    assert marked == f"{figures['legible']:.3f}"
    assert f"from {figures['legible']:.3f}" in shown
    assert figures["rampPalettes"] == ["viridis", "cividis", "plasma", "turbo"]


def test_every_puor_contrast_is_computed_by_palette_js(figures):
    anchors = figures["anchors"]
    assert len(anchors) == 22 and {g for g, *_ in anchors} == {"card", "white"}
    for ground, index, marked, shown, expected in anchors:
        assert marked == shown == expected, (ground, index)
    # The folded arms reach 3:1 against the card.
    assert [arm for arm, _ in figures["firstLegible"]] == ["neg", "pos"]
    assert all(ratio >= 3 for _, ratio in figures["firstLegible"])


def test_the_se3_schematic_is_captioned_and_isometric(figures):
    se3 = figures["se3"]
    assert "Schematic, not measured data" in se3["text"] and "−D₁/2" in se3["text"]
    # Both panels share one box, drawn at one scale on both axes.
    assert len(se3["frames"]) == 2 and se3["frames"][0] == se3["frames"][1]


def test_no_figure_text_signs_a_number_with_a_hyphen(figures):
    assert figures["hyphens"] == []
