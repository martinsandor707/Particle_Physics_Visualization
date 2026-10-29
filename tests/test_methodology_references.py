"""The article's references: ``bib`` is transcribed from ``text`` and adds nothing.

``methodology/content/references.js`` gives every entry the text the page
prints and a ``bib`` object the article's Export writes into references.bib.
This holds the two together: keys unique, each type's required fields present,
authors in "Family, Given" form (or an organisation), no LaTeX residue, and
every field value occurring in ``text``. Loaded through Node; skipped when
``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

TYPES = {"article", "book", "inproceedings", "techreport", "misc"}
REQUIRED = {
    "article": ("author", "title", "journal", "year"),
    "book": ("author", "title", "publisher", "year"),
    "inproceedings": ("author", "title", "booktitle", "year"),
    "techreport": ("author", "title", "institution", "number", "year"),
    "misc": ("author", "title"),
}
SCALARS = (
    "title", "journal", "booktitle", "series", "volume", "number", "pages", "year",
    "publisher", "address", "edition", "institution", "reporttype", "howpublished",
    "url", "doi", "note",
)
KNOWN = set(SCALARS) | {"type", "author"}


@pytest.fixture(scope="module")
def entries() -> list:
    script = (
        "const m = await import(process.argv[1] ? JSON.parse(process.argv[1])[0] : '');"
        "console.log(JSON.stringify(m.default));"
    )
    return _run(script, [(JS / "methodology" / "content" / "references.js").as_uri()])


def _authors(bib: dict) -> list:
    return bib.get("author", [])


def test_keys_unique_and_text_present(entries):
    assert len(entries) > 0
    keys = [e["key"] for e in entries]
    assert len(keys) == len(set(keys))
    for e in entries:
        assert e["text"].strip(), e["key"]
        assert isinstance(e.get("bib"), dict), f"{e['key']}: no bib"


def test_type_and_required_fields(entries):
    for e in entries:
        bib = e["bib"]
        assert bib["type"] in TYPES, e["key"]
        assert set(bib) <= KNOWN, (e["key"], set(bib) - KNOWN)
        for field in REQUIRED[bib["type"]]:
            assert bib.get(field), f"{e['key']}: {bib['type']} lacks {field}"
        if bib["type"] == "misc":
            assert bib.get("howpublished") or bib.get("url"), e["key"]
        assert isinstance(bib["author"], list) and bib["author"], e["key"]


def test_author_format(entries):
    for e in entries:
        for a in _authors(e["bib"]):
            if isinstance(a, dict):
                assert set(a) == {"org"} and a["org"].strip(), e["key"]
            else:
                assert isinstance(a, str), e["key"]
                assert a.count(",") in (1, 2), f"{e['key']}: {a!r}"
                assert all(part.strip() for part in a.split(",")), f"{e['key']}: {a!r}"


def test_no_latex_residue(entries):
    def strings(bib):
        for k, v in bib.items():
            if k == "author":
                for a in v:
                    yield a["org"] if isinstance(a, dict) else a
            else:
                yield v

    for e in entries:
        for s in strings(e["bib"]):
            assert isinstance(s, str), e["key"]
            assert not any(c in s for c in "\\{}"), f"{e['key']}: {s!r}"


def test_every_field_occurs_in_text(entries):
    for e in entries:
        bib, text = e["bib"], e["text"]
        for a in _authors(bib):
            if isinstance(a, dict):
                assert a["org"] in text, (e["key"], a)
            else:
                family = a.split(",")[0].strip()
                assert family in text, (e["key"], a)
        for field in SCALARS:
            if field not in bib:
                continue
            value = bib[field]
            if field == "edition":
                value = f"{value} ed."
            assert value in text, f"{e['key']}: {field} {value!r} not in text"
