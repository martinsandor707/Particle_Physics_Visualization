"""The Details drawer's link to the article (``js/article_sections.js``).

Every card of the Physics and Models pages names the place in the
Methodology that explains it, so its drawer can link there. The pages must
not load the article (``test_api.py`` keeps the module graphs apart), so the
map is a leaf data module, and it can drift from the article without anything
failing in the page. This test is what keeps the two in step: it lays the real
article out with ``methodology/render.js``, derives the map the rules below
give, and compares.

The rules (export-brief.md section 7):

* a card a badge names in section 3 (Results) lands on the first section-3
  badge row naming it;
* a badged card absent from section 3 lands on its first badge row anywhere;
* a card no badge names takes its family's place: the compare-frames cells
  the row of ``compare-lab-xy``, the 3-D event's projections (``vproj-*``)
  the row of ``vox-event``, the ensemble's (``eproj-*``) the row of
  ``vox-ensemble``, and the Event Inspector's nine cells (``event-*``) the
  section that describes the Event Inspector.

Each entry is ``{at, section, title}``: the element landed on, the number of
the section holding it and that section's title as plain text. On a drift the
failure prints the expected entries, so the update is a copy.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

#: The section that describes the Event Inspector (its paragraph has no badge row of its own).
EVENT_INSPECTOR_SECTION = "sec-spatial"

_SCRIPT = _FAKE_DOM + r"""
const urls = JSON.parse(process.argv[1]);
window.location.pathname = '/methodology';
window.location.search = '';
const render = await import(urls.render);
const { ARTICLE } = await import(urls.article);
const { PHYSICS_CARDS } = await import(urls.physics);
const { MODELS_CARDS } = await import(urls.models);
const { VOXEL_CARDS } = await import(urls.voxels);
const { GRID_ROWS, GRID_COLS } = await import(urls.frameGrid);
const { ARTICLE_SECTIONS, articleSection } = await import(urls.sections);
const out = {};

const { tree, outline, errors } = render.layout(ARTICLE);
out.errors = errors;
const ids = new Set();
const walk = (node) => {
  if (!node) return;
  if (Array.isArray(node)) { node.forEach(walk); return; }
  if (node.attrs?.id) ids.add(node.attrs.id);
  (node.children ?? []).forEach(walk);
};
walk(tree);

// The outline, flat: every section's number and plain title by its id.
const sections = new Map();
const flatten = (entry) => {
  sections.set(entry.id, { number: entry.number, title: entry.title.map((t) => t.text ?? '').join('') });
  entry.children.forEach(flatten);
};
outline.forEach(flatten);

// Every badge row in document order, with the section it sits in.
const rows = [];
const visit = (part) => {
  for (const block of part.blocks ?? []) {
    if (block.kind === 'links') rows.push({ id: block.id, section: part.id, items: block.items ?? [] });
  }
  (part.sections ?? []).forEach(visit);
};
[...ARTICLE.sections, ...ARTICLE.appendices].forEach(visit);

const results = sections.get('sec-results')?.number;
const inResults = (row) => {
  const number = sections.get(row.section)?.number ?? '';
  return number === results || number.startsWith(`${results}.`);
};
const place = (at, sectionId) => ({ at, section: sections.get(sectionId).number, title: sections.get(sectionId).title });
const rowOf = (page, panel) => {
  const naming = rows.filter((row) => row.items.some((i) => i.page === page && i.panel === panel));
  const row = naming.find(inResults) ?? naming[0];
  return row ? place(row.id, row.section) : null;
};

const grid = (prefix) => GRID_ROWS.flatMap((row) => GRID_COLS.map((col) => `${prefix}-${row}-${col}`));
const cards = {
  physics: ['xy', 'yz', 'xz', 'energy', ...PHYSICS_CARDS.map((c) => c.id), ...grid('compare'), ...grid('event')],
  models: [...MODELS_CARDS.map((c) => c.id), ...VOXEL_CARDS.map((c) => c.id)],
};
const family = (page, id) => {
  if (page === 'physics' && id.startsWith('compare-')) return rowOf('physics', 'compare-lab-xy');
  if (page === 'physics' && id.startsWith('event-')) return place(EVENT_INSPECTOR, EVENT_INSPECTOR);
  if (page === 'models' && id.startsWith('vproj-')) return rowOf('models', 'vox-event');
  if (page === 'models' && id.startsWith('eproj-')) return rowOf('models', 'vox-ensemble');
  return null;
};
const EVENT_INSPECTOR = urls.eventSection;
out.expected = {};
out.unplaced = [];
for (const [page, list] of Object.entries(cards)) {
  out.expected[page] = {};
  for (const id of list) {
    const entry = rowOf(page, id) ?? family(page, id);
    if (entry) out.expected[page][id] = entry;
    else out.unplaced.push(`${page}/${id}`);
  }
}
out.actual = ARTICLE_SECTIONS;
out.cards = cards;
out.missingTargets = [];
for (const [page, map] of Object.entries(ARTICLE_SECTIONS)) {
  for (const [id, entry] of Object.entries(map)) if (!ids.has(entry.at)) out.missingTargets.push(`${page}/${id} -> ${entry.at}`);
}
out.lookup = {
  hit: articleSection('physics', 'xy'),
  unknownPanel: articleSection('physics', 'no-such-card'),
  unknownPage: articleSection('methodology', 'xy'),
  inherited: articleSection('physics', 'toString'),
  frozen: Object.isFrozen(ARTICLE_SECTIONS) && Object.isFrozen(ARTICLE_SECTIONS.physics ?? {})
    && Object.isFrozen(ARTICLE_SECTIONS.physics?.xy ?? {}),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def derived() -> dict:
    urls = {
        "render": (JS / "methodology" / "render.js").as_uri(),
        "article": (JS / "methodology" / "content" / "index.js").as_uri(),
        "physics": (JS / "physics_section.js").as_uri(),
        "models": (JS / "models_cards.js").as_uri(),
        "voxels": (JS / "voxel_views.js").as_uri(),
        "frameGrid": (JS / "panels" / "frame_grid.js").as_uri(),
        "sections": (JS / "article_sections.js").as_uri(),
        "eventSection": EVENT_INSPECTOR_SECTION,
    }
    return _run(_SCRIPT, urls)


def _as_module(expected: dict) -> str:
    """The expected map as article_sections.js writes it, ready to paste."""
    lines = []
    for page, entries in expected.items():
        lines.append(f"  {page}: {{")
        for card, entry in entries.items():
            key = card if card.isidentifier() else f"'{card}'"
            title = entry["title"].replace("'", "\\'")
            lines.append(f"    {key}: {{ at: '{entry['at']}', section: '{entry['section']}', title: '{title}' }},")
        lines.append("  },")
    return "\n".join(lines)


def test_the_article_lays_out(derived):
    assert derived["errors"] == []


def test_every_card_of_both_pages_has_a_place_in_the_article(derived):
    assert derived["unplaced"] == [], "cards no rule places: give them a badge, or a family in this test"
    for page, cards in derived["cards"].items():
        missing = sorted(set(cards) - set(derived["actual"].get(page, {})))
        assert not missing, f"{page} cards without an entry in article_sections.js: {missing}"


def test_the_map_follows_the_article(derived):
    expected, actual = derived["expected"], derived["actual"]
    assert actual == expected, (
        "article_sections.js has drifted from the article. Expected entries:\n"
        + _as_module(expected)
        + "\nDiffering: "
        + json.dumps({f"{page}/{card}": [actual.get(page, {}).get(card), entry]
                      for page, entries in expected.items() for card, entry in entries.items()
                      if actual.get(page, {}).get(card) != entry}, ensure_ascii=False, indent=1)
    )


def test_every_target_exists_in_the_article(derived):
    assert derived["missingTargets"] == []


def test_the_lookup(derived):
    r = derived["lookup"]
    assert r["hit"] == derived["expected"]["physics"]["xy"]
    assert r["unknownPanel"] is None and r["unknownPage"] is None and r["inherited"] is None
    assert r["frozen"] is True
