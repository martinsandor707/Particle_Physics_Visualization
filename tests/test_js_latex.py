"""The Methodology article as LaTeX and BibTeX (``methodology/latex.js``), executed under Node.

The page's Export hands a reader ``methodology.tex`` and ``references.bib``
written from the same content modules the page renders
(data/dev/design/methodology/export-brief.md §3-§4). These tests hold the two
outputs together:

* the Unicode map, one entry at a time: every character the article uses, the
  superscript and subscript runs, the math minus, the quotes by context, the
  accents (braced in BibTeX), and an unmapped character reported, never
  passed through;
* a synthetic article pinning every rule: each escape, code spans that break,
  emphasis with an unclosed delimiter, every kind of cross-reference (an
  equation bracketed by the prose takes ``\\ref``), adjacent citations sharing
  one ``\\cite``, badges dropped, callouts, tables as ``longtable`` with
  planned columns, figures from ``figurePath``, the generated Appendix B, the
  front matter and the header;
* the BibTeX writer on synthetic entries of every type, an ``{ org }``
  author, a suffix, accents, a DOI with an underscore, a URL, an RFC as a
  techreport, and the ``@misc`` fallback of an entry without ``bib``;
* the real article: no error, ASCII only, environments balanced, every label
  defined once and every reference to one defined, every citation in the
  bibliography, and sections, equations, tables and figures counted against
  render.js ``layout``;
* a compile test (skipped without ``pdflatex`` and ``bibtex``): pdflatex,
  bibtex and pdflatex twice on the real article with a tiny PNG per figure.
  The log must hold no error, undefined reference or citation and no
  "Missing character"; every label LaTeX numbers must carry the number the
  page prints, and the bibliography must come out in the order ``bib`` lists
  it. Overfull boxes over 10 pt are reported as warnings with their source.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import warnings
import zlib

import pytest
from test_js_physics_shell import JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_URLS = {
    "latex": (JS / "methodology" / "latex.js").as_uri(),
    "render": (JS / "methodology" / "render.js").as_uri(),
    "article": (JS / "methodology" / "content" / "index.js").as_uri(),
}

_PRELUDE = r"""
const urls = JSON.parse(process.argv[1]);
const latex = await import(urls.latex);
const render = await import(urls.render);
const out = {};
"""

# ------------------------------------------------------------ the Unicode map --

_MAP_SCRIPT = _PRELUDE + r"""
const cases = JSON.parse(process.argv[2]);
out.text = cases.map(([text, bib]) => latex.textToLatex(text, { bib }));
console.log(JSON.stringify(out));
"""

#: (input, BibTeX mode, expected LaTeX)
_MAP_CASES = [
    # Punctuation, quotes and spaces.
    ("0.1–99.9", False, "0.1--99.9"),
    ("a — b", False, "a --- b"),
    ("Student’s", False, "Student's"),
    ("‘zstd’", False, "`zstd'"),
    ("“probable error”", False, "``probable error''"),
    ("§2", False, "\\S{}2"),
    ("A › B", False, "A \\guilsinglright{} B"),
    ("and so…", False, "and so\\ldots{}"),
    ("20\u00a0mm", False, "20~mm"),
    ("20\u2009mm", False, "20\\,mm"),
    ("20\u202fmm", False, "20\\,mm"),
    # Straight quotes by context: opening at the start, after a space or an opening bracket.
    ('"quoted" text', False, "``quoted'' text"),
    ('say ("this")', False, "say (``this'')"),
    ("the 'single' one", False, "the `single' one"),
    ("it's the notebook's", False, "it's the notebook's"),
    # Math symbols, the minus above all: never a hyphen in the PDF.
    ("−0.25", False, "\\ensuremath{-}0.25"),
    ("2 × 2", False, "2 \\ensuremath{\\times} 2"),
    ("± 1", False, "\\ensuremath{\\pm} 1"),
    ("N ≥ 20", False, "N \\ensuremath{\\geq} 20"),
    ("N ≤ 8", False, "N \\ensuremath{\\leq} 8"),
    ("A→B", False, "A\\ensuremath{\\rightarrow}B"),
    ("box ⊗ Gaussian", False, "box \\ensuremath{\\otimes} Gaussian"),
    ("√f", False, "\\ensuremath{\\surd}f"),
    ("⟨D⟩", False, "\\ensuremath{\\langle}D\\ensuremath{\\rangle}"),
    ("a·b", False, "a\\ensuremath{\\cdot}b"),
    ("1.8°", False, "1.8\\ensuremath{^{\\circ}}"),
    ("x′", False, "x\\ensuremath{'}"),
    # Greek: U+03C6 is the curly phi the page draws, \varphi; U+03D5 is \phi; micro is mu.
    ("σ", False, "\\ensuremath{\\sigma}"),
    ("χ", False, "\\ensuremath{\\chi}"),
    ("μ", False, "\\ensuremath{\\mu}"),
    ("µ", False, "\\ensuremath{\\mu}"),
    ("φ", False, "\\ensuremath{\\varphi}"),
    ("ϕ", False, "\\ensuremath{\\phi}"),
    ("π ρ ψ", False, "\\ensuremath{\\pi} \\ensuremath{\\rho} \\ensuremath{\\psi}"),
    # A run of superscripts is one group; after a Greek letter it shares the letter's.
    ("n⁻¹", False, "n\\ensuremath{^{-1}}"),
    ("GeV mm⁻²", False, "GeV mm\\ensuremath{^{-2}}"),
    ("10³", False, "10\\ensuremath{^{3}}"),
    ("σ²", False, "\\ensuremath{\\sigma^{2}}"),
    ("χ²", False, "\\ensuremath{\\chi^{2}}"),
    ("x₁₀", False, "x\\ensuremath{_{10}}"),
    # Accents through NFD; the dotless i under an accent; braced for BibTeX.
    ("Sándor", False, "S\\'{a}ndor"),
    ("Róbert", False, "R\\'{o}bert"),
    ("Ramírez", False, "Ram\\'{\\i}rez"),
    ("Mühleisen", False, 'M\\"{u}hleisen'),
    ("Nuñez", False, "Nu\\~{n}ez"),
    ("Erdős", False, "Erd\\H{o}s"),
    ("tűz", False, "t\\H{u}z"),
    ("Ramírez", True, "Ram{\\'{\\i}}rez"),
    ("für", True, 'f{\\"{u}}r'),
    # ASCII specials of running text.
    ("a\\b", False, "a\\textbackslash{}b"),
    ("{x}", False, "\\{x\\}"),
    ("$5 & #3 at 5% of a_b", False, "\\$5 \\& \\#3 at 5\\% of a\\_b"),
    ("~ ^", False, "\\textasciitilde{} \\textasciicircum{}"),
    ("<<a>> | b", False, "\\textless{}\\textless{}a\\textgreater{}\\textgreater{} \\textbar{} b"),
    ("Chapman & Hall", True, "Chapman \\& Hall"),
]


@pytest.fixture(scope="module")
def mapped() -> list:
    cases = [[text, bib] for text, bib, _ in _MAP_CASES]
    done = subprocess.run([NODE, "--input-type=module", "-e", _MAP_SCRIPT, json.dumps(_URLS), json.dumps(cases)],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)["text"]


@pytest.mark.parametrize("index", range(len(_MAP_CASES)), ids=[c[0] for c in _MAP_CASES])
def test_every_character_maps_to_its_latex(mapped, index):
    text, _, expected = _MAP_CASES[index]
    assert mapped[index]["errors"] == []
    assert mapped[index]["latex"] == expected, text


def test_an_unmapped_character_is_an_error_never_passed_through():
    script = _PRELUDE + r"""
out.snow = latex.textToLatex('a ☃ b');
out.kana = latex.textToLatex('ア');
console.log(JSON.stringify(out));
"""
    r = _run(script, _URLS)
    assert r["snow"]["latex"] == "a ? b"
    assert r["snow"]["errors"] == ['text: no LaTeX for U+2603 "☃"']
    assert r["kana"]["errors"] and r["kana"]["latex"] == "?"


# ------------------------------------------------------- the synthetic article --

_SYNTHETIC_SCRIPT = _PRELUDE + r"""
const constants = {
  NEG: { value: -0.5, source: 'py:calosrv.x:NEG', meaning: 'A negative constant, “quoted”.' },
  SMALL: { value: 1e-7, source: 'py:calosrv.x:SMALL', meaning: 'A small one.' },
  WORD: { value: 'canonical', source: 'js:labels.js:FRAME', meaning: 'A string.' },
};
const fixture = {
  front: {
    title: 'A *test* article',
    authors: [{ name: 'Martin Tibor Sándor', affiliations: [1] }, { name: 'Róbert Lakatos', affiliations: [1, 2] }],
    affiliations: [{ id: 1, text: 'First place' }, { id: 2, text: 'Second place & co' }],
    abstract: [String.raw`An abstract with $x$ that cites [[cite:k1]].`, 'A second paragraph.'],
    keywords: ['one', 'SE(3) two'],
  },
  sections: [
    {
      id: 'sec-one', title: 'One',
      blocks: [
        { kind: 'p', text: String.raw`Inline $\alpha_{1}$, a dollar \$5, a star \* and a tick \` in text, a `
          + '`code_span/a.b:c,d`, `<<x>> & {y} %z ~q ^w |v "s" \'t\' \\b`' + String.raw`, *emphasis*, **strong**, `
          + String.raw`see [[eq-a]], ([[eq-a]]), [[tab-a]], [[fig-a]], [[sec-sub]], [[app-x]], [[app-x-sub]], [[lnk-one-a]], `
          + String.raw`[[lnk-app-a]], [[sec-references]], [[tab-constants]] and [[cite:k2]][[cite:k1]] and [[cite:k3]]. `
          + 'A lone * star, 3 * 4, *open and closed.' },
        { kind: 'eq', id: 'eq-a', tex: 'a = b - 1' },
        { kind: 'eq', tex: 'c', numbered: false },
        { kind: 'list', ordered: true, items: [String.raw`first $y$`, '[bracketed] second'] },
        { kind: 'list', items: ['bullet'] },
        { kind: 'table', id: 'tab-a', caption: 'A caption with $z$', head: ['Short', 'A much longer heading'],
          rows: [['a', 'a long cell of prose that needs most of the line to itself'], ['[c]', '`d`']], note: 'A note.' },
        { kind: 'figure', id: 'fig-a', exhibit: 'ramps', caption: 'The ramps.' },
        { kind: 'callout', tone: 'rule', title: 'A rule', text: 'First paragraph.\n\nSecond paragraph.' },
        { kind: 'callout', tone: 'caution', text: 'No title.' },
        { kind: 'links', id: 'lnk-one-a', items: [{ page: 'physics', panel: 'xy', label: 'XY entry panel' }] },
      ],
      sections: [{ id: 'sec-sub', title: 'Sub with $x$', blocks: [{ kind: 'eq', id: 'eq-b', tex: 'd' }],
        sections: [{ id: 'sec-sub-deep', title: 'Deeper', blocks: [{ kind: 'p', text: 'Unknown [[eq-missing]], [[cite:nokey]], ☃.' }] }] }],
    },
  ],
  references: [
    { key: 'k1', text: 'Reference one.', bib: { type: 'misc', author: [{ org: 'W3C' }], title: 'One', url: 'https://w3.org/x_y' } },
    { key: 'k2', text: 'Reference two.' },
    { key: 'k3', text: 'Reference three.', bib: { type: 'book', author: ['Taylor, II, R. M.'], title: 'Three', publisher: 'P', year: '2001' } },
    { key: 'k4', text: 'Never cited.' },
  ],
  appendices: [
    { id: 'app-x', title: 'Extra', blocks: [{ kind: 'links', id: 'lnk-app-a', items: [{ page: 'physics', panel: 'energy', label: 'Energy' }] }],
      sections: [{ id: 'app-x-sub', title: 'Extra sub', blocks: [] }] },
    { id: 'app-constants', title: 'Constants', generated: 'constants' },
  ],
};
const doc = latex.latexDocument(fixture, { constants, provenance: { version: '1.2.3', stamp: 's_1', date: '2026-10-29' },
  figurePath: (id) => `pictures/${id}-print.png` });
out.doc = doc;
out.shares = [
  latex.columnShares([{ natural: 30, widest: 30 }, { natural: 900, widest: 40 }]),
  latex.columnShares([{ natural: 2000, widest: 20 }, { natural: 1000, widest: 20 }, { natural: 1000, widest: 200 }]),
  latex.columnShares(Array.from({ length: 7 }, () => ({ natural: 80, widest: 80 })), { tabcolsep: 4 }),
];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def synthetic() -> dict:
    return _run(_SYNTHETIC_SCRIPT, _URLS)


def _block(tex: str, start: str, end: str) -> str:
    i = tex.index(start)
    return tex[i:tex.index(end, i) + len(end)]


def test_problems_are_reported_and_the_document_still_written(synthetic):
    doc = synthetic["doc"]
    errors = "\n".join(doc["errors"])
    for needle in ("unknown reference [[eq-missing]]", "unknown citation [[cite:nokey]]", 'no LaTeX for U+2603 "☃"'):
        assert needle in errors, needle
    assert len(doc["errors"]) == 3
    assert "\\textbf{??}" in doc["tex"] and "[?]" in doc["tex"]
    assert doc["tex"].endswith("\\end{document}\n")


def test_header_preamble_and_front_matter(synthetic):
    tex = synthetic["doc"]["tex"]
    assert tex.startswith("% A test article\n%\n% Exported from the Methodology page of calosrv 1.2.3 (static build s\\_1) on 2026-10-29.\n")
    assert "% Build: pdflatex methodology && bibtex methodology && pdflatex methodology && pdflatex methodology" in tex
    assert "latexmk -pdf methodology" in tex
    assert "% The figures are PNG at 300 dpi, drawn for a 160 mm text width; their SVG sources sit beside them." in tex
    packages = re.findall(r"\\usepackage(?:\[([^]]*)\])?\{([^}]*)\}", tex)
    assert packages == [("T1", "fontenc"), ("", "lmodern"), ("", "textcomp"), ("a4paper,margin=25mm", "geometry"),
                        ("", "amsmath"), ("", "amssymb"), ("", "array"), ("", "booktabs"), ("", "longtable"),
                        ("", "graphicx"), ("", "microtype"), ("hidelinks", "hyperref")]
    assert "\\documentclass[11pt]{article}" in tex
    assert "\\title{A \\emph{test} article}" in tex
    assert "\\author{Martin Tibor S\\'{a}ndor\\textsuperscript{1} \\and R\\'{o}bert Lakatos\\textsuperscript{1,2}}" in tex
    date = _block(tex, "\\date{", "2026-10-29}")
    assert "\\small" in date
    assert "\\textsuperscript{1}First place\\\\" in date
    assert "\\textsuperscript{2}Second place \\& co\\\\" in date
    assert "calosrv 1.2.3 \\textperiodcentered{} static build s\\_1 \\textperiodcentered{} exported 2026-10-29}" in date
    abstract = _block(tex, "\\begin{abstract}", "\\end{abstract}")
    assert "cites~\\cite{k1}.\n\nA second paragraph." in abstract
    assert "\\noindent\\textbf{Keywords:} one \\textperiodcentered{} SE(3) two" in tex
    assert "\\maketitle" in tex and "\\tableofcontents" not in tex


def test_structure_sections_bibliography_then_appendices(synthetic):
    tex = synthetic["doc"]["tex"]
    order = [m.group(0) for m in re.finditer(
        r"\\(?:sub)*section\{[^\n]*?\}\\label\{[a-z-]+\}|\\bibliographystyle\{unsrt\}|\\bibliography\{references\}|\\appendix", tex)]
    assert order == [
        "\\section{One}\\label{sec-one}",
        "\\subsection{Sub with $x$}\\label{sec-sub}",
        "\\subsubsection{Deeper}\\label{sec-sub-deep}",
        "\\bibliographystyle{unsrt}", "\\bibliography{references}", "\\appendix",
        "\\section{Extra}\\label{app-x}",
        "\\subsection{Extra sub}\\label{app-x-sub}",
        "\\section{Constants}\\label{app-constants}",
    ]


def test_inline_syntax_escapes_code_math_and_emphasis(synthetic):
    tex = synthetic["doc"]["tex"]
    p = tex[tex.index("Inline "):tex.index("open and closed.") + 16]
    assert p.startswith("Inline $\\alpha_{1}$, a dollar \\$5, a star * and a tick \\textasciigrave{} in text, a ")
    # Code: every special escaped, breaks after / . _ : , and the quotes straight.
    assert ("\\texttt{code\\_\\allowbreak{}span/\\allowbreak{}a.\\allowbreak{}b:\\allowbreak{}c,\\allowbreak{}d}") in p
    assert ("\\texttt{\\textless{}\\textless{}x\\textgreater{}\\textgreater{} \\& \\{y\\} \\%z \\textasciitilde{}q "
            "\\textasciicircum{}w \\textbar{}v \\textquotedbl{}s\\textquotedbl{} \\textquotesingle{}t\\textquotesingle{} "
            "\\textbackslash{}b}") in p
    assert "\\emph{emphasis}, \\textbf{strong}" in p
    # An unclosed or unflanked delimiter is a literal asterisk, as on the page.
    assert p.endswith("A lone * star, 3 * 4, *open and closed.")


def test_cross_references_by_kind(synthetic):
    tex = synthetic["doc"]["tex"]
    p = tex[tex.index("see \\eqref"):tex.index("A lone")]
    assert p.startswith(
        "see \\eqref{eq-a}, (\\ref{eq-a}), Table~\\ref{tab-a}, Figure~\\ref{fig-a}, \\S\\ref{sec-sub}, "
        "Appendix~\\ref{app-x}, Appendix~\\ref{app-x-sub}, \\S\\ref{sec-one}, Appendix~\\ref{app-x}, References, "
        "Table~\\ref{tab-constants} and~\\cite{k2,k1} and~\\cite{k3}.")


def test_blocks_equations_lists_callouts_and_dropped_badges(synthetic):
    tex = synthetic["doc"]["tex"]
    assert "\\begin{equation}\\label{eq-a}\na = b - 1\n\\end{equation}" in tex
    assert "\\[\nc\n\\]" in tex
    assert "\\begin{enumerate}\n\\item first $y$\n\\item {}[bracketed] second\n\\end{enumerate}" in tex
    assert "\\begin{itemize}\n\\item bullet\n\\end{itemize}" in tex
    assert ("\\begin{quote}\n\\textbf{Rule} \\textperiodcentered{} A rule\n\nFirst paragraph.\n\nSecond paragraph.\n"
            "\\end{quote}") in tex
    assert "\\begin{quote}\n\\textbf{Caution}\n\nNo title.\n\\end{quote}" in tex
    assert "XY entry panel" not in tex and "Energy" not in tex.split("\\appendix")[1]
    assert "lnk-" not in tex


def test_tables_are_longtables_with_planned_columns(synthetic):
    tex = synthetic["doc"]["tex"]
    table = _block(tex, "{\\small\n\\begin{longtable}", "\\end{longtable}\n\\noindent A note.\\par\n}")
    widths = [int(w) for w in re.findall(r"p\{\\dimexpr\(\\linewidth-4\\tabcolsep\)\*(\d+)/1000\\relax\}", table)]
    assert len(widths) == 2 and sum(widths) == 1000 and widths[1] > 2 * widths[0]
    assert table.count(">{\\raggedright\\arraybackslash}p{") == 2
    lines = table.split("\n")
    assert lines[2] == "\\caption{A caption with $z$}\\label{tab-a}\\\\"
    assert lines[3:15] == [
        "\\toprule", "Short & A much longer heading \\\\", "\\midrule", "\\endfirsthead",
        "\\multicolumn{2}{@{}l}{Table~\\thetable{} (continued)}\\\\", "\\toprule",
        "Short & A much longer heading \\\\", "\\midrule", "\\endhead", "\\bottomrule", "\\endfoot", "\\bottomrule",
    ]
    assert lines[15] == "\\endlastfoot"
    assert lines[16] == "a & a long cell of prose that needs most of the line to itself \\\\"
    # A row opening with a bracket is kept from being read as the optional argument of the \\ before it.
    assert lines[17] == "{}[c] & \\texttt{d} \\\\"


def test_column_shares_respect_floors_ceilings_and_sum_to_the_line(synthetic):
    narrow, crowded, even = synthetic["shares"]
    assert sum(narrow) == sum(crowded) == sum(even) == 1000
    # A short column takes no more than its floor (here 0.45 of an even split); the long one the rest.
    assert narrow == [225, 775]
    # A long word sets a floor the proportional share would starve.
    assert crowded[2] > crowded[1]
    assert len(set(even)) <= 2


def test_figures_are_included_from_figure_path(synthetic):
    doc = synthetic["doc"]
    assert doc["figures"] == [{"id": "fig-a", "exhibit": "ramps"}]
    assert ("\\begin{figure}[htbp]\n\\centering\n\\includegraphics[width=\\linewidth]{pictures/fig-a-print.png}\n"
            "\\caption{The ramps.}\\label{fig-a}\n\\end{figure}") in doc["tex"]


def test_appendix_b_is_generated_from_the_constants(synthetic):
    tex = synthetic["doc"]["tex"]
    appendix = tex[tex.index("\\label{app-constants}"):]
    assert ("The prose never types one of these numbers: it reads each from "
            "\\texttt{methodology/\\allowbreak{}constants.\\allowbreak{}js}, and ") in appendix
    assert "\\caption{Every constant of the code the article quotes, with the module and expression it is read from.}\\label{tab-constants}\\\\" in appendix
    assert "Name & Value & Meaning & Source \\\\" in appendix
    assert ("\\texttt{NEG} & \\ensuremath{-}0.5 & A negative constant, ``quoted''. & "
            "\\texttt{py:\\allowbreak{}calosrv.\\allowbreak{}x:\\allowbreak{}NEG} \\\\") in appendix
    assert "\\texttt{SMALL} & 1 \\ensuremath{\\times} 10\\ensuremath{^{-7}} & A small one." in appendix
    assert "\\texttt{WORD} & \\texttt{canonical} & A string." in appendix


def test_bib_holds_the_cited_entries_in_order_of_first_citation(synthetic):
    bib = synthetic["doc"]["bib"]
    assert re.findall(r"^@(\w+)\{(\w+),", bib, re.M) == [("misc", "k1"), ("misc", "k2"), ("book", "k3")]
    assert "@misc{k2,\n  note = {Reference two.}\n}" in bib
    assert "author = {{W3C}}" in bib
    assert "howpublished = {\\url{https://w3.org/x_y}}" in bib
    assert "author = {Taylor, II, R. M.}" in bib
    assert "k4" not in bib


# ------------------------------------------------------------- the BibTeX writer --

_BIB_SCRIPT = _PRELUDE + r"""
const references = [
  { key: 'art', text: 't', bib: { type: 'article', author: ['Wigmans, R.', 'Gianotti, F.'], title: 'Grad-CAM “probable error” of n⁻¹',
    journal: 'Revue de l’Institut', volume: '75', number: '4', pages: '1243–1286', year: '2003' } },
  { key: 'bk', text: 't', bib: { type: 'book', author: ['Borland, D.', 'Taylor, II, R. M.'], title: 'XGBoost', edition: '2nd',
    publisher: 'Chapman & Hall', address: 'London', year: '1986' } },
  { key: 'proc', text: 't', bib: { type: 'inproceedings', author: ['Zheng, Q.', 'Mühleisen, H.', 'Nuñez, J. R.', 'Ramírez, S.'],
    title: 'Shap-CAM', booktitle: 'Computer Vision – ECCV 2022', series: 'Lecture Notes in Computer Science', volume: '8',
    publisher: 'Springer', address: 'Cham', doi: '10.1007/978-3-031-19775-8_27', year: '2022' } },
  { key: 'rfc', text: 't', bib: { type: 'techreport', author: ['Collet, Y.'], title: 'Zstandard and the ‘application/zstd’ type',
    institution: 'IETF', reporttype: 'RFC', number: '8878', year: '2021' } },
  { key: 'web', text: 't', bib: { type: 'misc', author: [{ org: 'The PostgreSQL Global Development Group' }, { org: 'Student' }],
    title: 'PostgreSQL Documentation', url: 'https://www.postgresql.org/docs/current/' } },
  { key: 'rec', text: 't', bib: { type: 'misc', author: [{ org: 'W3C' }], title: 'WCAG 2.1', howpublished: 'W3C Recommendation',
    url: 'https://www.w3.org/TR/WCAG21/', note: 'A note', doi: '10.1/x_y', year: '2018' } },
  { key: 'old', text: 'C. W. Fabjan, Calorimetry, Reviews 75 (2003) 1243–1286, für “x”.' },
  { key: 'bad', text: 't', bib: { type: 'thesis', author: [42], title: 'A {brace}', colour: 'x', url: 'https://x.org/a b' } },
];
const fixture = { front: {}, sections: [{ id: 'sec-a', title: 'A', blocks: [
  { kind: 'p', text: references.map((r) => `[[cite:${r.key}]]`).join(' ') }] }], references };
out.doc = latex.latexDocument(fixture);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def bibliography() -> dict:
    return _run(_BIB_SCRIPT, _URLS)["doc"]


def _entry(bib: str, key: str) -> str:
    match = re.search(r"^@\w+\{" + key + r",\n.*?^\}", bib, re.M | re.S)
    assert match, key
    return match.group(0)


def test_bib_article(bibliography):
    entry = _entry(bibliography["bib"], "art")
    assert entry == (
        "@article{art,\n"
        "  author = {Wigmans, R. and Gianotti, F.},\n"
        "  title = {{Grad-CAM ``probable error'' of n\\ensuremath{^{-1}}}},\n"
        "  journal = {Revue de l'Institut},\n"
        "  volume = {75},\n"
        "  number = {4},\n"
        "  pages = {1243--1286},\n"
        "  year = {2003}\n"
        "}")


def test_bib_book_with_a_suffix_an_edition_and_an_ampersand(bibliography):
    entry = _entry(bibliography["bib"], "bk")
    assert "  author = {Borland, D. and Taylor, II, R. M.},\n" in entry
    assert "  title = {{XGBoost}},\n" in entry
    assert "  edition = {2nd},\n" in entry
    assert "  publisher = {Chapman \\& Hall},\n" in entry


def test_bib_inproceedings_with_accents_and_a_doi(bibliography):
    entry = _entry(bibliography["bib"], "proc")
    assert "  author = {Zheng, Q. and M{\\\"{u}}hleisen, H. and Nu{\\~{n}}ez, J. R. and Ram{\\'{\\i}}rez, S.},\n" in entry
    assert "  booktitle = {Computer Vision -- ECCV 2022},\n" in entry
    assert "  series = {Lecture Notes in Computer Science},\n" in entry
    # unsrt prints the note, not the doi: the DOI rides in both, verbatim.
    assert "  note = {doi:\\nolinkurl{10.1007/978-3-031-19775-8_27}},\n" in entry
    assert "  doi = {10.1007/978-3-031-19775-8_27}\n" in entry


def test_bib_rfc_as_a_techreport(bibliography):
    entry = _entry(bibliography["bib"], "rfc")
    assert "@techreport{rfc," in entry
    assert "  title = {{Zstandard and the `application/zstd' type}},\n" in entry
    assert "  number = {8878},\n  type = {RFC},\n  institution = {IETF},\n" in entry


def test_bib_misc_with_bodies_a_url_and_a_note(bibliography):
    web = _entry(bibliography["bib"], "web")
    assert "  author = {{The PostgreSQL Global Development Group} and {Student}},\n" in web
    assert "  howpublished = {\\url{https://www.postgresql.org/docs/current/}},\n" in web
    assert "  url = {https://www.postgresql.org/docs/current/}\n" in web
    rec = _entry(bibliography["bib"], "rec")
    # A reference that says how it was published keeps that; the URL stays a field.
    assert "  howpublished = {W3C Recommendation},\n" in rec and "\\url" not in rec
    assert "  note = {A note, doi:\\nolinkurl{10.1/x_y}},\n" in rec


def test_bib_misc_fallback_for_an_entry_without_bib(bibliography):
    assert _entry(bibliography["bib"], "old") == (
        "@misc{old,\n  note = {C. W. Fabjan, Calorimetry, Reviews 75 (2003) 1243--1286, f{\\\"{u}}r ``x''.}\n}")


def test_bib_problems_are_errors(bibliography):
    errors = "\n".join(bibliography["errors"])
    for needle in ("unknown bib type thesis", "unknown bib field colour", 'an author is a "Family, Given" string or { org }',
                   "a brace in a bib field", "a URL or DOI must be printable ASCII"):
        assert needle in errors, needle
    assert _entry(bibliography["bib"], "bad").startswith("@misc{bad,")
    assert not re.search(r"[^\x00-\x7f]", bibliography["bib"])


# -------------------------------------------------------------- the real article --

_REAL_SCRIPT = _PRELUDE + r"""
const { ARTICLE } = await import(urls.article);
const doc = latex.latexDocument(ARTICLE, { provenance: { version: '9.9.9', stamp: 'test', date: '2026-10-29' } });
out.doc = doc;
// What the page prints for every numbered target, from render.js layout.
const { tree, outline, errors } = render.layout(ARTICLE);
out.layoutErrors = errors;
const walk = (node, fn) => { if (!node) return; if (Array.isArray(node)) { node.forEach((n) => walk(n, fn)); return; }
  fn(node); for (const child of node.children ?? []) walk(child, fn); };
const cls = (n) => String(n.attrs?.class ?? '').split(/\s+/);
const labels = {};
const flat = (entries) => entries.forEach((e) => { if (e.number) labels[e.id] = e.number; flat(e.children); });
flat(outline);
const sections = [];
const flatAll = (entries) => entries.forEach((e) => { if (e.number) sections.push(e.id); flatAll(e.children); });
flatAll(outline);
out.sections = sections;
out.equations = [];
out.tables = [];
out.figures = [];
walk(tree, (n) => {
  if (n.tag !== 'figure' || !n.attrs?.id) return;
  const label = (c) => { let found = null; walk(n, (m) => { if (!found && cls(m).includes(c)) found = render.textOf(m); }); return found; };
  if (cls(n).includes('equation')) { out.equations.push(n.attrs.id); labels[n.attrs.id] = label('eq-number').slice(1, -1); }
  if (cls(n).includes('article-table')) { out.tables.push(n.attrs.id); labels[n.attrs.id] = label('caption-label').replace(/^Table (\S+)\.$/, '$1'); }
  if (cls(n).includes('article-figure')) { out.figures.push(n.attrs.id); labels[n.attrs.id] = label('caption-label').replace(/^Figure (\S+)\.$/, '$1'); }
});
out.labels = labels;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def real() -> dict:
    return _run(_REAL_SCRIPT, _URLS)


def test_the_real_article_has_no_error_and_is_ascii(real):
    doc = real["doc"]
    assert real["layoutErrors"] == []
    assert doc["errors"] == []
    for name in ("tex", "bib"):
        bad = re.search(r"[^\x00-\x7f]", doc[name])
        assert bad is None, (name, doc[name][max(bad.start() - 40, 0):bad.end() + 40] if bad else "")


def test_the_real_article_environments_are_balanced(real):
    stack = []
    # A row end \\ is consumed first, so its optional [1ex] is not read as a display opening.
    for match in re.finditer(r"\\\\|\\(begin|end)\{([a-z*]+)\}|\\\[|\\\]", real["doc"]["tex"]):
        token = match.group(0)
        if token == "\\\\":
            continue
        name = match.group(2) or "displaymath"
        opening = match.group(1) == "begin" or token == "\\["
        if opening:
            stack.append(name)
        else:
            assert stack and stack.pop() == name, token
    assert stack == []
    # Every brace group closes (escaped braces aside).
    depth = 0
    for char in re.sub(r"\\[{}]", "", real["doc"]["tex"]):
        depth += {"{": 1, "}": -1}.get(char, 0)
        assert depth >= 0
    assert depth == 0


def test_the_real_article_labels_references_and_citations_resolve(real):
    tex, bib = real["doc"]["tex"], real["doc"]["bib"]
    labels = re.findall(r"\\label\{([^}]+)\}", tex)
    assert len(labels) == len(set(labels)), "a label defined twice"
    referenced = set(re.findall(r"\\(?:eq)?ref\{([^}]+)\}", tex))
    assert referenced and referenced <= set(labels), referenced - set(labels)
    cited = []
    for group in re.findall(r"\\cite\{([^}]+)\}", tex):
        for key in group.split(","):
            if key not in cited:
                cited.append(key)
    assert re.findall(r"^@\w+\{([^,]+),", bib, re.M) == cited
    # The real data carry `bib`: no entry falls back to the @misc note.
    assert not re.search(r"^@misc\{[^,]+,\n  note = ", bib, re.M)


def test_the_real_article_is_counted_as_the_page_counts_it(real):
    tex, doc = real["doc"]["tex"], real["doc"]
    headings = re.findall(r"\\(?:sub)*section\{.*?\}\\label\{([^}]+)\}", tex)
    assert headings == real["sections"]
    assert re.findall(r"\\begin\{equation\}\\label\{([^}]+)\}", tex) == real["equations"]
    assert re.findall(r"\\caption\{.*?\}\\label\{(tab-[^}]+)\}\\\\", tex) == real["tables"]
    assert tex.count("\\begin{longtable}") == len(real["tables"])
    assert [f["id"] for f in doc["figures"]] == real["figures"]
    assert re.findall(r"\\includegraphics\[width=\\linewidth\]\{([^}]+)\}", tex) == [f"figures/{i}.png" for i in real["figures"]]
    # The badges open the live dashboard and are not exported.
    assert "Open in" not in tex and "lnk-" not in tex


def test_the_real_article_names_both_authors_and_their_affiliations(real):
    tex = real["doc"]["tex"]
    assert "\\author{Martin Tibor S\\'{a}ndor\\textsuperscript{1} \\and R\\'{o}bert Lakatos\\textsuperscript{2}}" in tex
    assert "\\textsuperscript{1}Doctoral School of Informatics" in tex
    assert "\\textsuperscript{2}Department of Data Science and Visualization" in tex
    assert "calosrv 9.9.9 \\textperiodcentered{} static build test \\textperiodcentered{} exported 2026-10-29}" in tex


# ----------------------------------------------------------------- compile it --

_PDFLATEX = shutil.which("pdflatex")
_BIBTEX = shutil.which("bibtex")


def _tiny_png() -> bytes:
    """A valid 16 x 9 white RGB PNG: what graphicx needs to place a figure."""
    width, height = 16, 9
    raw = b"".join(b"\x00" + b"\xff" * (3 * width) for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _overfull(log: str, tex: str, limit: float = 10.0) -> list[str]:
    """Every overfull box wider than `limit` pt, with the source lines it came from."""
    lines = tex.split("\n")
    found = []
    for match in re.finditer(r"Overfull \\[hv]box \(([\d.]+)pt too \w+\) .*?lines? (\d+)(?:--(\d+))?", log):
        if float(match.group(1)) > limit:
            first, last = int(match.group(2)), int(match.group(3) or match.group(2))
            found.append(f"{match.group(1)} pt at lines {first}-{last}: {' '.join(lines[first - 1:last])[:200]}")
    return found


@pytest.mark.skipif(_PDFLATEX is None or _BIBTEX is None, reason="pdflatex or bibtex is not installed")
def test_the_real_article_compiles_with_pdflatex_and_bibtex(real, tmp_path):
    doc = real["doc"]
    (tmp_path / "methodology.tex").write_text(doc["tex"], encoding="ascii")
    (tmp_path / "references.bib").write_text(doc["bib"], encoding="ascii")
    (tmp_path / "figures").mkdir()
    for figure in doc["figures"]:
        (tmp_path / "figures" / f"{figure['id']}.png").write_bytes(_tiny_png())
    pdflatex = [_PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", "methodology"]
    for command in (pdflatex, [_BIBTEX, "methodology"], pdflatex, pdflatex):
        done = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=300, check=False)
        log = (tmp_path / "methodology.log").read_text(encoding="latin-1")
        assert done.returncode == 0, f"{command[0]} failed:\n{done.stdout[-3000:]}\n{log[-3000:]}"
    assert (tmp_path / "methodology.pdf").stat().st_size > 0

    blg = (tmp_path / "methodology.blg").read_text(encoding="latin-1")
    assert "Warning--" not in blg, blg
    for needle in ("undefined", "Missing character", "Rerun to get"):
        assert needle not in log, [line for line in log.split("\n") if needle in line][:10]
    assert not re.search(r"^! ", log, re.M)

    # LaTeX numbers every target as the page does.
    aux = (tmp_path / "methodology.aux").read_text(encoding="latin-1")
    numbered = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))
    for target, label in real["labels"].items():
        assert numbered.get(target) == label, (target, numbered.get(target), label)
    # And the bibliography comes out in the order `bib` lists it.
    bbl = (tmp_path / "methodology.bbl").read_text(encoding="latin-1")
    assert re.findall(r"\\bibitem\{([^}]+)\}", bbl) == re.findall(r"^@\w+\{([^,]+),", doc["bib"], re.M)

    for line in _overfull(log, doc["tex"]):
        warnings.warn(f"overfull box over 10 pt: {line}", stacklevel=1)
