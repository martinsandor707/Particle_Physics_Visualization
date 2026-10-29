"""The Methodology page's LaTeX → MathML Core compiler (``static/js/math.js``), run under Node.

Four content authors write TeX against the compiler's whitelist, and the page
engine mounts what it returns, so this file pins:

* the trees of representative constructs (numbers, the minus, primes,
  fractions, roots, large operators in display and inline style, named
  functions and their thin spaces, fences, accents, fonts, text, spacing and
  every environment);
* every entry of the three whitelists compiling in a context that fits it;
* the syntax errors: an unknown command or environment, unbalanced braces, a
  stray ``}``, ``&`` or ``\\`` outside an environment and an unescaped ``%``;
* the rendered minus being U+2212, with no ASCII hyphen-minus in any token;
* the annotation carrying the source verbatim;
* MathML Core element and attribute names only;
* the article's draft equations (``DISPLAY`` and ``INLINE``) all compiling;
* ``mountMath`` building elements with ``createElementNS`` in the MathML
  namespace and text nodes only.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import json

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

MINUS = "−"
APPLY = "⁡"

#: Drafts of the article's display equations (the math agent's prompt); the authors may vary details.
DISPLAY = [
    r"z_k = 3662.4\,\mathrm{mm} + 20.5\,\mathrm{mm}\,(k-1), \quad k = 1, \dots, 60, \qquad z_{\mathrm{disp}} = z - 3649\,\mathrm{mm}",
    r"\hat{\mathbf{n}}(\theta, \varphi) = \begin{pmatrix} \sin\theta\cos\varphi \\ \sin\theta\sin\varphi \\ \cos\theta \end{pmatrix}",
    r"\mathbf{p}' = \mathbf{R}\,(\mathbf{p} - \mathbf{a}), \qquad \mathbf{R} \in \mathrm{SO}(3)",
    r"\mathbf{e}_j = \begin{pmatrix} c_{j,x} \\ c_{j,y} \end{pmatrix} - (c_{j,z} - z_{\mathrm f})\,\tan\theta_j \begin{pmatrix} \cos\varphi_j \\ \sin\varphi_j \end{pmatrix}",
    r"\mathbf{m} = \tfrac{1}{2}(\mathbf{e}_A + \mathbf{e}_B), \quad \psi = \operatorname{atan2}(e_{B,y} - e_{A,y},\, e_{B,x} - e_{A,x}), \quad D_{\mathrm{entry}} = \lVert \mathbf{e}_B - \mathbf{e}_A \rVert",
    r"\begin{pmatrix} x' \\ y' \\ z' \end{pmatrix} = \begin{pmatrix} \cos\psi & \sin\psi & 0 \\ -\sin\psi & \cos\psi & 0 \\ 0 & 0 & 1 \end{pmatrix} \begin{pmatrix} x - m_x \\ y - m_y \\ z - z_{\mathrm f} \end{pmatrix}",
    r"\mathbf{R}(\theta, \varphi) = \mathbf{R}_y(\theta)\,\mathbf{R}_z(\varphi) = \begin{pmatrix} \cos\theta\cos\varphi & \cos\theta\sin\varphi & -\sin\theta \\ -\sin\varphi & \cos\varphi & 0 \\ \sin\theta\cos\varphi & \sin\theta\sin\varphi & \cos\theta \end{pmatrix}",
    r"W_{rc} = G_c(d_{r+1}) - G_c(d_r), \qquad \sum_r W_{rc} = 1, \qquad W_{rc} \ge 0",
    r"H(u) = \begin{cases} \tfrac{1}{2}(1+u)^2, & -1 \le u \le 0 \\ 1 - \tfrac{1}{2}(1-u)^2, & 0 < u \le 1 \end{cases}",
    r"\Psi(u) = u\,\Phi(u) + \Phi'(u), \qquad G_c(d) = \frac{\sigma_{\mathrm K}}{a}\left[\Psi\!\left(\frac{d - a_c}{\sigma_{\mathrm K}}\right) - \Psi\!\left(\frac{d - b_c}{\sigma_{\mathrm K}}\right)\right]",
    r"\sigma_{\mathrm{box}} = \frac{a}{\sqrt{12}}, \quad \sigma_{\mathrm{tent}} = \frac{a}{\sqrt{6}}, \quad \sigma_{\mathrm{G}} = \sqrt{\frac{a^2}{12} + \sigma_{\mathrm K}^2}",
    r"d_j = o_j - \frac{1}{9}\sum_{i=-4}^{4} o_{j+i}, \qquad \rho_1 = \operatorname{corr}(d_j, d_{j+1}) < -0.10",
    r"e = \sum_h E_h, \quad \mathtt{esp} = \sum_h E_h \max(\mathcal{S}_h, 0), \quad \mathtt{esn} = \sum_h E_h \min(\mathcal{S}_h, 0)",
    r"c_4(N) = \sqrt{\frac{2}{N-1}}\,\frac{\Gamma(N/2)}{\Gamma\!\left(\frac{N-1}{2}\right)}",
    r"\left[\, s\sqrt{\frac{N-1}{\chi^2_{0.975,\,N-1}}},\; s\sqrt{\frac{N-1}{\chi^2_{0.025,\,N-1}}} \,\right]",
    r"f(a) = 1 - \frac{2a\,\Phi'(a)}{2\Phi(a) - 1}, \qquad \kappa = \sqrt{f(2.5\,\kappa)} = 0.9365574",
    r"\frac{\hat p + \frac{z^2}{2n} \pm z\sqrt{\frac{\hat p(1-\hat p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}",
    r"\mathrm{SE}_J^2 = \frac{G-1}{G}\sum_{g=1}^{G}\left(\zeta_{(g)} - \bar\zeta\right)^2, \qquad n_{\mathrm{eff}} = 3 + \mathrm{SE}_J^{-2}",
    r"\bar R = \frac{1}{N}\left\lVert \sum_{i=1}^{N} \begin{pmatrix} \cos\varphi_i \\ \sin\varphi_i \end{pmatrix} \right\rVert, \quad \bar\varphi = \operatorname{atan2}\Big(\sum_i \sin\varphi_i,\ \sum_i \cos\varphi_i\Big), \quad P_{\mathrm{Ray}} \approx e^{-N\bar R^2}",
    r"\Delta = \big((\hat\varphi - \varphi + \pi) \bmod 2\pi\big) - \pi \in (-\pi, \pi]",
    r"R^2_{x\varphi} = \frac{r_{xc}^2 + r_{xs}^2 - 2\,r_{xc}\,r_{xs}\,r_{cs}}{1 - r_{cs}^2}, \qquad \mathbb{E}\left[R^2\right]_0 = \frac{2}{N-1}",
    r"\begin{aligned} \mathrm{RMSE} &= \sqrt{\frac{1}{n}\sum_{i=1}^{n} r_i^2} \\ \mathrm{CI}_{95} &= \left[\mathrm{RMSE}\sqrt{\frac{n}{\chi^2_{0.975,n}}},\ \mathrm{RMSE}\sqrt{\frac{n}{\chi^2_{0.025,n}}}\right] \end{aligned}",
    r"\mathrm{CR} = \frac{L_1 + 0.05}{L_2 + 0.05}, \quad L = 0.2126\,R_{\mathrm{lin}} + 0.7152\,G_{\mathrm{lin}} + 0.0722\,B_{\mathrm{lin}}",
    r"\mathrm{code}(v) = \begin{cases} 128 - \operatorname{round}(126\,t), & v < 0 \\ 129 + \operatorname{round}(126\,t), & v > 0 \end{cases}, \quad t = \frac{\log_{10}\operatorname{clip}(|v|/v_{\max}, 10^{-3}, 1) + 3}{3}",
    r"s = \min\!\left(\frac{W_{\mathrm{px}}}{\Delta x_{\mathrm{mm}}}, \frac{H_{\mathrm{px}}}{\Delta y_{\mathrm{mm}}}\right)\ \mathrm{px\,mm^{-1}}",
]

#: Drafts of the article's inline TeX.
INLINE = [
    r"\langle\rho\rangle = \sum E / (N\,\Delta A)", r"\lceil 2N^{1/3} \rceil", r"x \mapsto x'", r"\overset{!}{=}",
    r"\widehat{AB}", r"\mathbb{1}", r"\mathcal{N}(0, \sigma^2)", r"\boldsymbol{\theta}",
    r"\vec{v}\cdot\dot{x}\,\ddot{y}", r"a \ll b \gg c", r"\lim_{N\to\infty}", r"\binom{n}{k}", r"\sqrt[3]{x}",
    r"\displaystyle\sum_{i}x_i", r"|x|", r"\{x \mid x > 0\}", r"5\%", r"t_{0.975,\,N-1}", r"x''",
]

#: How each whitelisted command is used when its bare form is not a valid source.
COMMAND_CONTEXT = {
    "frac": r"\frac{a}{b}", "dfrac": r"\dfrac{a}{b}", "tfrac": r"\tfrac{a}{b}", "sqrt": r"\sqrt{x}",
    "binom": r"\binom{n}{k}", "overset": r"\overset{!}{=}", "underset": r"\underset{x}{\max}",
    "stackrel": r"\stackrel{?}{=}", "operatorname": r"\operatorname{atan2}(x)", "limits": r"\sum\limits_{i}^{n} x",
    "nolimits": r"\sum\nolimits_{i} x", "pmod": r"a \equiv b \pmod{n}", "mod": r"a \equiv b \mod{n}",
    "left": r"\left( x \right)", "right": r"\left. x \right|", "big": r"\big( x \big)", "Big": r"\Big[ x \Big]",
    "bigg": r"\bigg\{ x \bigg\}", "Bigg": r"\Bigg\langle x \Bigg\rangle", "begin": r"\begin{matrix} a \end{matrix}",
    "end": r"\begin{matrix} a \end{matrix}", "text": r"\text{if } x", "textrm": r"\textrm{a b}",
    "textit": r"\textit{a b}", "textbf": r"\textbf{a b}", "displaystyle": r"\displaystyle \sum_i x_i",
    "textstyle": r"\textstyle \sum_i x_i",
}
ARG_COMMANDS = {"hat", "bar", "tilde", "vec", "dot", "ddot", "overline", "underline", "widehat", "widetilde",
                "mathrm", "mathbf", "mathbb", "mathcal", "mathit", "mathsf", "mathtt", "boldsymbol"}
SYMBOL_CONTEXT = {"\\": r"\begin{matrix} a \\ b \end{matrix}", "{": r"\{ x \}", "}": r"\{ x \}"}

#: The compiler's error cases: (source, the start of the message).
ERRORS = [
    (r"\foo x", 'Unknown command "\\foo"'),
    (r"\begin{array} a \end{array}", 'Unknown environment "array"'),
    (r"\frac{a}{b", 'Unbalanced "{"'),
    (r"{x", 'Unbalanced "{"'),
    (r"x}", 'Unbalanced "}"'),
    (r"a & b", '"&" outside an environment'),
    (r"a \\ b", '"\\\\" outside an environment'),
    (r"{a & b}", '"&" outside an environment'),
    (r"50% of", 'Unescaped "%"'),
    (r"\text{a & b}", 'Unescaped "&" inside "\\text"'),
    (r"\text{a # b}", 'Unescaped "#" inside "\\text"'),
    (r"\left( x", '"\\left" without a matching "\\right"'),
    (r"x \right)", '"\\right" without a matching "\\left"'),
    (r"\begin{matrix} a", '"\\begin{matrix}" is never closed'),
    (r"\begin{pmatrix} a \end{bmatrix}", '"\\end{bmatrix}" closes "\\begin{pmatrix}"'),
    (r"x^1^2", "Double superscript"),
    (r"x \limits", '"\\limits" must follow a large operator'),
    (r"\text{50% of}", 'Unescaped "%"'),
    (r"\frac{a}", "Missing denominator"),
]

#: MathML Core's elements, and the attributes the compiler may set on them.
CORE_ELEMENTS = {"math", "semantics", "annotation", "mrow", "mi", "mn", "mo", "mtext", "mspace", "msub", "msup",
                 "msubsup", "munder", "mover", "munderover", "mfrac", "msqrt", "mroot", "mtable", "mtr", "mtd",
                 "mstyle", "mpadded", "mphantom"}
GLOBAL_ATTRS = {"displaystyle", "scriptlevel", "style"}
CORE_ATTRS = {
    "math": {"display"}, "annotation": {"encoding"}, "mi": {"mathvariant"},
    "mo": {"form", "fence", "separator", "lspace", "rspace", "stretchy", "symmetric", "maxsize", "minsize",
           "largeop", "movablelimits"},
    "mspace": {"width", "height", "depth"}, "mfrac": {"linethickness"}, "mover": {"accent"},
    "munder": {"accentunder"}, "munderover": {"accent", "accentunder"}, "mtd": {"columnspan", "rowspan"},
    "mpadded": {"width", "height", "depth", "lspace", "voffset"},
}

_SCRIPT = _FAKE_DOM + r"""
const [mathUrl, display, inline, commandSources, symbolSources, envSources, errors, probes] = JSON.parse(process.argv[1]);
const m = await import(mathUrl);
const out = { whitelist: m.SUPPORTED_COMMANDS, symbols: m.SUPPORTED_SYMBOL_COMMANDS, envList: m.SUPPORTED_ENVIRONMENTS };
const compile = (list, opts) => list.map((tex) => {
  try { return { tex, tree: m.texToTree(tex, opts) }; } catch (e) { return { tex, error: `${e.name}: ${e.message}` }; }
});
out.display = compile(display, { display: true });
out.inline = compile(inline, { display: false });
out.commands = Object.fromEntries(Object.entries(commandSources).map(([k, tex]) => [k, compile([tex], { display: true })[0]]));
out.symbolCommands = Object.fromEntries(Object.entries(symbolSources).map(([k, tex]) => [k, compile([tex], { display: true })[0]]));
out.envs = Object.fromEntries(Object.entries(envSources).map(([k, tex]) => [k, compile([tex], { display: true })[0]]));
out.errors = errors.map(([tex]) => {
  try { m.texToTree(tex); return { tex, thrown: null }; } catch (e) {
    return { tex, thrown: e.name, isClass: e instanceof m.MathSyntaxError, message: e.message, position: e.position, source: e.tex };
  }
});
// Representative constructs: the body row (semantics' first child), display and inline.
out.probes = Object.fromEntries(probes.map((tex) => [tex, {
  display: m.texToTree(tex, { display: true }).children[0].children[0],
  inline: m.texToTree(tex).children[0].children[0],
}]));

// mountMath on a document that records every element and text node it is asked for.
const made = [];
document.createElementNS = (ns, tag) => { made.push(['element', ns, tag]); return new FakeElement(tag); };
const plainCreate = document.createElement;
document.createElement = (tag) => { made.push(['html', tag]); return plainCreate(tag); };
const plainText = document.createTextNode;
document.createTextNode = (text) => { made.push(['text', text]); return plainText(text); };
Object.defineProperty(FakeElement.prototype, 'innerHTML', { set() { throw new Error('innerHTML written'); } });
const tree = m.texToTree(String.raw`\frac{a-1}{\sqrt{x}} \le \text{50 mm}`, { display: true });
const root = m.mountMath(tree, document);
const serial = (el) => (el instanceof FakeText ? { text: el.data }
  : { tag: el.tagName.toLowerCase(), attrs: el.attrs, children: el.childNodes.map(serial) });
out.mount = { made, ns: m.MATHML_NS, root: serial(root), tree };
process.stdout.write(JSON.stringify(out));
"""

PROBES = [
    "3662.4", "a-b", "x'", "x'^2", "x''", r"\frac{a}{b}", r"\dfrac{1}{2}", r"\tfrac{1}{2}", r"\binom{n}{k}",
    r"\sqrt[3]{x}", r"\sqrt{x}", r"\sum_{i=1}^{n} x_i", r"\int_0^1 f", r"\int\limits_0^1 f",
    r"\sum\nolimits_{i} x", r"\lim_{N\to\infty} f", r"\sin\theta", r"\sin(x)", r"\operatorname{atan2}(y, x)",
    r"\operatorname*{arg}_{x} f", r"\mathrm{d}", r"\mathrm{mm}", r"\mathrm{px\,mm^{-1}}", r"\mathbf{p}",
    r"\mathbb{R}\mathbb{1}", r"\mathcal{L}", r"\boldsymbol{\theta}", r"\mathbf{\Gamma}", r"\mathtt{esp}",
    r"\varphi\phi", r"\Gamma", r"\left( x \right.", r"\big(", r"\hat{x}", r"\widehat{AB}", r"\underline{x}",
    r"\text{a b}", r"\text{Grad-CAM at -3}", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
    r"\begin{cases} a, & x < 0 \\ b, & x \ge 0 \\ \end{cases}", r"\begin{aligned} a &= b \\ c &= d \end{aligned}",
    r"5\%", r"a\!b", r"a\,b\:c\;d\quad e\qquad f\ g", r"x < -1", r"(-\pi, \pi]", r"a \bmod b", r"x^{\top}",
    r"\{x \mid x > 0\}", r"a * b", "θ × φ ≤ 1 − x",
    r"|x| - 1", r"\lVert a\rVert + b", r"\lvert -x \rvert", r"\log|x|", r"\log\lvert x\rvert", r"a\,\log b",
]


def _command_sources(whitelist: list[str]) -> dict[str, str]:
    sources = {}
    for name in whitelist:
        if name in COMMAND_CONTEXT:
            sources[name] = COMMAND_CONTEXT[name]
        elif name in ARG_COMMANDS:
            sources[name] = rf"\{name}{{x}}"
        else:
            sources[name] = rf"a \{name} b"
    return sources


def _body(tree: dict) -> dict:
    return tree["children"][0]["children"][0]


def _walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


@pytest.fixture(scope="module")
def out() -> dict:
    # The whitelists are read from the module first, so a command added there is tested here unprompted.
    first = _run(_FAKE_DOM + r"""
const m = await import(JSON.parse(process.argv[1])[0]);
process.stdout.write(JSON.stringify([m.SUPPORTED_COMMANDS, m.SUPPORTED_SYMBOL_COMMANDS, m.SUPPORTED_ENVIRONMENTS]));
""", [(JS / "math.js").as_uri()])
    commands, symbols, envs = first
    symbol_sources = {s: SYMBOL_CONTEXT.get(s, rf"a \{s} b") for s in symbols}
    env_sources = {e: rf"\begin{{{e}}} a & b \\ c & d \\ \end{{{e}}}" for e in envs}
    return _run(_SCRIPT, [(JS / "math.js").as_uri(), DISPLAY, INLINE, _command_sources(commands), symbol_sources,
                          env_sources, ERRORS, PROBES])


def _all_trees(out: dict):
    for group in ("display", "inline"):
        for item in out[group]:
            yield item
    for group in ("commands", "symbolCommands", "envs"):
        yield from out[group].values()


# ------------------------------------------------------------ fixtures --

def test_every_draft_equation_compiles(out):
    failed = [item for item in out["display"] + out["inline"] if "error" in item]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(out["display"]) == len(DISPLAY) == 25


@pytest.mark.parametrize("group", ["commands", "symbolCommands", "envs"])
def test_every_whitelisted_entry_compiles(out, group):
    failed = {k: v["error"] for k, v in out[group].items() if "error" in v}
    assert not failed
    expected = {"commands": out["whitelist"], "symbolCommands": out["symbols"], "envs": out["envList"]}[group]
    assert set(out[group]) == set(expected)


def test_the_whitelist_is_the_published_contract(out):
    # Authors write against these; an entry may be added (and reported), never removed.
    for name in ("varphi", "operatorname", "mathbb", "boldsymbol", "lVert", "coloneqq", "top", "bmod", "stackrel"):
        assert name in out["whitelist"]
    assert out["envList"] == ["pmatrix", "bmatrix", "vmatrix", "matrix", "cases", "aligned"]
    assert set(out["symbols"]) == {",", ";", ":", "!", " ", "{", "}", "|", "%", "#", "&", "_", "\\"}


# -------------------------------------------------------------- errors --

def test_bad_sources_throw_math_syntax_error_with_a_position(out):
    for (tex, start), got in zip(ERRORS, out["errors"]):
        assert got["thrown"] == "MathSyntaxError", tex
        assert got["isClass"], tex
        assert got["message"].startswith(start), (tex, got["message"])
        assert isinstance(got["position"], int) and 0 <= got["position"] <= len(tex), (tex, got["position"])
        assert got["source"] == tex


def test_errors_point_at_the_offence(out):
    by_tex = {e["tex"]: e for e in out["errors"]}
    assert by_tex[r"\foo x"]["position"] == 0
    assert by_tex["x}"]["position"] == 1
    assert by_tex["a & b"]["position"] == 2
    assert by_tex["50% of"]["position"] == 2
    assert by_tex[r"{x"]["position"] == 0


# --------------------------------------------------------------- tokens --

def test_minus_is_u2212_and_no_token_holds_a_hyphen_minus(out):
    row = out["probes"]["a-b"]["display"]["children"]
    assert row == [{"tag": "mi", "text": "a"}, {"tag": "mo", "text": MINUS}, {"tag": "mi", "text": "b"}]
    for item in _all_trees(out):
        for node in _walk(_body(item["tree"])):
            assert "-" not in node.get("text", ""), (item["tex"], node)


def test_numbers_letters_and_unicode_input(out):
    assert out["probes"]["3662.4"]["display"] == {"tag": "mrow", "children": [{"tag": "mn", "text": "3662.4"}]}
    row = out["probes"]["θ × φ ≤ 1 − x"]["display"]["children"]
    assert [(n["tag"], n["text"]) for n in row] == [("mi", "θ"), ("mo", "×"), ("mi", "φ"), ("mo", "≤"), ("mn", "1"),
                                                     ("mo", MINUS), ("mi", "x")]
    assert out["probes"][r"a * b"]["display"]["children"][1] == {"tag": "mo", "text": "∗"}
    assert out["probes"][r"\varphi\phi"]["display"]["children"] == [{"tag": "mi", "text": "φ"},
                                                                    {"tag": "mi", "text": "ϕ"}]
    gamma = out["probes"][r"\Gamma"]["display"]["children"][0]
    assert gamma == {"tag": "mi", "attrs": {"mathvariant": "normal"}, "text": "Γ"}


def test_unary_signs_take_prefix_form(out):
    lt = out["probes"]["x < -1"]["display"]["children"]
    assert lt[2] == {"tag": "mo", "text": MINUS, "attrs": {"form": "prefix"}}
    paren = out["probes"][r"(-\pi, \pi]"]["display"]["children"]
    assert paren[1]["attrs"] == {"form": "prefix"}
    # A binary minus keeps the dictionary's spacing.
    assert "attrs" not in out["probes"]["a-b"]["display"]["children"][1]


def test_plain_bars_are_ordinary_symbols(out):
    """TeX's classes: a plain | or \\| is ordinary, \\lvert opens, \\rvert closes."""
    def signs(src):
        return [n.get("attrs", {}).get("form") for n in _walk(out["probes"][src]["display"])
                if n.get("tag") == "mo" and n.get("text") in (MINUS, "+")]
    # The sign after a closing bar is binary, so it keeps the dictionary's spacing.
    assert signs(r"|x| - 1") == [None]
    assert signs(r"\lVert a\rVert + b") == [None]
    # The sign after an opening bar is unary.
    assert signs(r"\lvert -x \rvert") == ["prefix"]

    def apply_space(src):
        return [n.get("attrs", {}).get("rspace") for n in _walk(out["probes"][src]["display"])
                if n.get("tag") == "mo" and n.get("text") == "\u2061"]
    # \log|x| keeps TeX's thin space (an operator before an ordinary symbol); \log\lvert x\rvert does not.
    assert apply_space(r"\log|x|") == ["0.1667em"]
    assert apply_space(r"\log\lvert x\rvert") == [None]


def test_an_explicit_space_before_a_function_is_not_doubled(out):
    spaces = [n for n in _walk(out["probes"][r"a\,\log b"]["display"]) if n.get("tag") == "mspace"]
    assert len(spaces) == 1


def test_primes_follow_their_base(out):
    prime = {"tag": "mo", "attrs": {"lspace": "0", "rspace": "0"}, "text": "′"}
    x = {"tag": "mi", "text": "x"}
    assert out["probes"]["x'"]["display"]["children"] == [{"tag": "mrow", "children": [x, prime]}]
    double = out["probes"]["x''"]["display"]["children"][0]["children"][1]
    assert double["text"] == "″"
    sq = out["probes"]["x'^2"]["display"]["children"][0]
    assert sq == {"tag": "msup", "children": [{"tag": "mrow", "children": [x, prime]}, {"tag": "mn", "text": "2"}]}


# ------------------------------------------------------------ structure --

def test_fractions_roots_and_binomials(out):
    p = out["probes"]
    assert p[r"\frac{a}{b}"]["display"]["children"][0] == {
        "tag": "mfrac", "children": [{"tag": "mi", "text": "a"}, {"tag": "mi", "text": "b"}]}
    dfrac = p[r"\dfrac{1}{2}"]["inline"]["children"][0]
    assert dfrac["tag"] == "mstyle" and dfrac["attrs"]["displaystyle"] == "true"
    assert dfrac["children"][0]["tag"] == "mfrac"
    assert p[r"\tfrac{1}{2}"]["display"]["children"][0]["attrs"]["displaystyle"] == "false"
    binom = p[r"\binom{n}{k}"]["display"]["children"][0]["children"]
    assert [n["tag"] for n in binom] == ["mo", "mfrac", "mo"]
    assert binom[1]["attrs"] == {"linethickness": "0"}
    assert binom[0]["text"] == "(" and binom[0]["attrs"]["stretchy"] == "true"
    root = p[r"\sqrt[3]{x}"]["display"]["children"][0]
    assert root == {"tag": "mroot", "children": [{"tag": "mi", "text": "x"}, {"tag": "mn", "text": "3"}]}
    assert p[r"\sqrt{x}"]["display"]["children"][0]["tag"] == "msqrt"


def test_large_operators_place_limits_by_style(out):
    p = out["probes"]
    total = p[r"\sum_{i=1}^{n} x_i"]
    shown = total["display"]["children"][0]
    assert shown["tag"] == "munderover"
    assert shown["children"][0] == {"tag": "mo", "text": "∑", "attrs": {"movablelimits": "true"}}
    assert total["inline"]["children"][0]["tag"] == "msubsup"
    # The integral keeps its limits to the side, unless \limits says otherwise.
    assert p[r"\int_0^1 f"]["display"]["children"][0]["tag"] == "msubsup"
    forced = p[r"\int\limits_0^1 f"]["inline"]["children"][0]
    assert forced["tag"] == "munderover" and forced["children"][0]["attrs"]["movablelimits"] == "false"
    assert p[r"\sum\nolimits_{i} x"]["display"]["children"][0]["tag"] == "msub"


def test_display_style_switch_moves_limits_under(out):
    inline = next(i for i in out["inline"] if i["tex"] == r"\displaystyle\sum_{i}x_i")
    style = _body(inline["tree"])["children"][0]
    assert style["tag"] == "mstyle" and style["attrs"] == {"displaystyle": "true", "scriptlevel": "0"}
    assert style["children"][0]["tag"] == "munder"


def test_named_functions(out):
    p = out["probes"]
    sin = p[r"\sin\theta"]["display"]["children"]
    assert sin == [{"tag": "mi", "text": "sin"}, {"tag": "mo", "text": APPLY, "attrs": {"rspace": "0.1667em"}},
                   {"tag": "mi", "text": "θ"}]
    # No thin space before an opening delimiter.
    assert p[r"\sin(x)"]["display"]["children"][1] == {"tag": "mo", "text": APPLY}
    atan = p[r"\operatorname{atan2}(y, x)"]["display"]["children"]
    assert atan[0] == {"tag": "mi", "text": "atan2"} and atan[1]["text"] == APPLY
    lim = p[r"\lim_{N\to\infty} f"]
    assert lim["display"]["children"][0]["tag"] == "munder"
    assert lim["display"]["children"][0]["children"][0] == {"tag": "mi", "text": "lim"}
    assert lim["inline"]["children"][0]["tag"] == "msub"
    assert p[r"\operatorname*{arg}_{x} f"]["display"]["children"][0]["tag"] == "munder"
    modulo = p[r"a \bmod b"]["display"]["children"][1]
    assert modulo["text"] == "mod" and modulo["attrs"]["lspace"] == "0.2778em"


def test_fences_and_sizes(out):
    p = out["probes"]
    row = p[r"\left( x \right."]["display"]["children"][0]["children"]
    assert row[0] == {"tag": "mo", "text": "(", "attrs": {"fence": "true", "form": "prefix", "stretchy": "true",
                                                          "symmetric": "true", "lspace": "0", "rspace": "0"}}
    assert len(row) == 2  # \right. draws nothing
    big = p[r"\big("]["display"]["children"][0]
    assert big["attrs"]["minsize"] == big["attrs"]["maxsize"] == "1.2em" and big["attrs"]["stretchy"] == "true"
    # Plain delimiters do not stretch, as in TeX.
    plain = p[r"\{x \mid x > 0\}"]["display"]["children"]
    assert plain[0] == {"tag": "mo", "attrs": {"stretchy": "false"}, "text": "{"}
    assert plain[2]["text"] == "∣"


def test_accents_fonts_and_text(out):
    p = out["probes"]
    hat = p[r"\hat{x}"]["display"]["children"][0]
    assert hat["tag"] == "mover" and hat["attrs"] == {"accent": "true"}
    assert hat["children"][1]["attrs"]["stretchy"] == "false"
    assert p[r"\widehat{AB}"]["display"]["children"][0]["children"][1]["attrs"]["stretchy"] == "true"
    # Chromium stretches no operator horizontally, so the rules are borders drawn at the group's width.
    under = p[r"\underline{x}"]["display"]["children"][0]
    assert under["tag"] == "mrow" and under["attrs"]["style"].startswith("border-bottom")

    assert p[r"\mathrm{d}"]["display"]["children"][0] == {"tag": "mi", "attrs": {"mathvariant": "normal"},
                                                          "text": "d"}
    assert p[r"\mathrm{mm}"]["display"]["children"][0] == {"tag": "mi", "text": "mm"}
    unit = p[r"\mathrm{px\,mm^{-1}}"]["display"]["children"][0]["children"]
    assert unit[0] == {"tag": "mi", "text": "px"} and unit[1]["tag"] == "mspace"
    assert unit[2]["tag"] == "msup" and unit[2]["children"][0] == {"tag": "mi", "text": "mm"}
    assert p[r"\mathbf{p}"]["display"]["children"][0]["text"] == "\U0001d429"
    assert [n["text"] for n in p[r"\mathbb{R}\mathbb{1}"]["display"]["children"]] == ["ℝ", "\U0001d7d9"]
    assert p[r"\mathcal{L}"]["display"]["children"][0]["text"] == "ℒ"
    assert p[r"\boldsymbol{\theta}"]["display"]["children"][0]["text"] == "\U0001d73d"
    assert p[r"\mathbf{\Gamma}"]["display"]["children"][0]["text"] == "\U0001d6aa"
    assert p[r"\mathtt{esp}"]["display"]["children"][0]["text"] == "\U0001d68e\U0001d69c\U0001d699"

    assert p[r"\text{a b}"]["display"]["children"][0] == {"tag": "mtext", "text": "a b"}
    assert p[r"\text{Grad-CAM at -3}"]["display"]["children"][0]["text"] == "Grad‐CAM at " + MINUS + "3"
    assert p[r"5\%"]["display"]["children"] == [{"tag": "mn", "text": "5"}, {"tag": "mi", "text": "%"}]
    assert p[r"x^{\top}"]["display"]["children"][0]["children"][1]["text"] == "⊤"


def test_spacing(out):
    p = out["probes"]
    widths = [n["attrs"]["width"] for n in p[r"a\,b\:c\;d\quad e\qquad f\ g"]["display"]["children"]
              if n["tag"] == "mspace"]
    assert widths == ["0.1667em", "0.2222em", "0.2778em", "1em", "2em", "0.3333em"]
    # Chromium clamps a negative mspace width to zero; the negative margin is what tightens.
    neg = p[r"a\!b"]["display"]["children"][1]
    assert neg == {"tag": "mspace", "attrs": {"width": "0em", "style": "margin-inline-start: -0.1667em"}}


def test_environments(out):
    p = out["probes"]
    matrix = p[r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"]["display"]["children"][0]["children"]
    assert [n["tag"] for n in matrix] == ["mo", "mtable", "mo"]
    assert matrix[0]["attrs"]["fence"] == "true" and matrix[2]["text"] == ")"
    assert [[len(r["children"])] for r in matrix[1]["children"]] == [[2], [2]]
    assert matrix[1]["attrs"] == {"displaystyle": "false"}

    cases = p[r"\begin{cases} a, & x < 0 \\ b, & x \ge 0 \\ \end{cases}"]["display"]["children"][0]["children"]
    assert [n["tag"] for n in cases] == ["mo", "mtable"] and cases[0]["text"] == "{"
    assert len(cases[1]["children"]) == 2  # the trailing \\ opens no empty row
    assert all("text-align: left" in td["attrs"]["style"] for tr in cases[1]["children"] for td in tr["children"])

    aligned = p[r"\begin{aligned} a &= b \\ c &= d \end{aligned}"]["display"]["children"][0]
    assert aligned["tag"] == "mtable" and aligned["attrs"] == {"displaystyle": "true"}
    first, second = aligned["children"][0]["children"]
    assert "-webkit-right" in first["attrs"]["style"] and "text-align: left" in second["attrs"]["style"]
    for name, item in out["envs"].items():
        rows = [n for n in _walk(_body(item["tree"])) if n["tag"] == "mtr"]
        assert len(rows) == 2, name


# ------------------------------------------------------- whole trees --

def test_annotation_is_the_source_verbatim(out):
    for item in _all_trees(out):
        tree = item["tree"]
        assert tree["tag"] == "math"
        semantics = tree["children"]
        assert len(semantics) == 1 and semantics[0]["tag"] == "semantics"
        body, annotation = semantics[0]["children"]
        assert body["tag"] == "mrow"
        assert annotation == {"tag": "annotation", "attrs": {"encoding": "application/x-tex"}, "text": item["tex"]}
    assert out["display"][0]["tree"]["attrs"] == {"display": "block"}
    assert out["inline"][0]["tree"]["attrs"] == {"display": "inline"}


def test_only_mathml_core_elements_and_attributes(out):
    for item in _all_trees(out):
        for node in _walk(item["tree"]):
            tag = node["tag"]
            assert tag in CORE_ELEMENTS, (item["tex"], tag)
            if tag == "mspace":  # the one empty element
                assert "text" not in node and "children" not in node, (item["tex"], node)
            else:
                assert ("text" in node) != ("children" in node), (item["tex"], node)
            for name, value in node.get("attrs", {}).items():
                assert name in GLOBAL_ATTRS | CORE_ATTRS.get(tag, set()), (item["tex"], tag, name)
                assert isinstance(value, str)
            if tag == "mi" and "attrs" in node:
                assert node["attrs"].get("mathvariant") == "normal", (item["tex"], node)


def test_mount_math_builds_namespaced_elements_and_text_nodes_only(out):
    mount = out["mount"]
    made = mount["made"]
    assert made, "mountMath created nothing"
    assert not [m for m in made if m[0] == "html"]
    elements = [m for m in made if m[0] == "element"]
    assert all(ns == mount["ns"] == "http://www.w3.org/1998/Math/MathML" for _, ns, _ in elements)
    texts = [m[1] for m in made if m[0] == "text"]
    assert MINUS in texts and "50 mm" in texts

    def from_tree(node):
        children = [from_tree(c) for c in node.get("children", [])]
        if "text" in node:
            children = [{"text": node["text"]}]
        return {"tag": node["tag"], "attrs": node.get("attrs", {}), "children": children}

    assert mount["root"] == from_tree(mount["tree"])
