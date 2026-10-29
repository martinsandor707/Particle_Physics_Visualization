"""The page shell (``js/shell.js``), executed under Node.

``test_layout_assets.py`` pins the shell's source - text nodes only, the
storage access guarded, the Escape listener in the capture phase. This runs
it, on the fake document of ``test_js_physics_shell.py`` with what the shell
reads added (``.app``, ``focus``, ``localStorage``):

* the configuration sidebar keeps its key and its toggle's names, and a page
  with another sidebar (the Methodology page's outline) keeps its own;
* a panel opened from a Methodology badge carries a way back: its drawer, and
  only its drawer, starts with a link to the article, whose href follows the
  view on screen when it is followed.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import pytest
from test_js_physics_shell import _FAKE_DOM, JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_SHELL_SCRIPT = _FAKE_DOM + r"""
const [shellUrl, commonUrl] = JSON.parse(process.argv[1]);
FakeElement.prototype.focus = function focus() {};
const store = new Map();
window.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
const app = document.createElement('div');
document.querySelector = (sel) => (sel === '.app' ? app : null);
for (const id of ['sidebar', 'sidebar-toggle', 'inspector', 'inspector-title', 'inspector-body', 'inspector-close']) byId(id);
const { Shell, SIDEBAR_STORAGE_KEY } = await import(shellUrl);
const common = await import(commonUrl);
const out = {};
const toggle = document.getElementById('sidebar-toggle');

// The configuration sidebar, as the Physics and Models pages build it.
let relayouts = 0;
const notes = { title: 'XY Projection', sections: [{ heading: 'Selection', lines: ['All events.'] }] };
const shell = new Shell({ getNotes: () => notes, onLayoutChange: () => { relayouts += 1; } });
shell.toggleSidebar(true);
out.config = { key: SIDEBAR_STORAGE_KEY, stored: store.get('calosrv.sidebar'), label: toggle.getAttribute('aria-label'),
  title: toggle.title, collapsed: app.classList.contains('is-sidebar-collapsed') };
shell.toggleSidebar(false);
out.configOpen = { stored: store.get('calosrv.sidebar'), label: toggle.getAttribute('aria-label') };

// The return link: only in the drawer of the panel the badge opened.
window.location.hash = '#table_name=t';
shell.openInspector('xy');
shell.setReturnLink('xy', common.returnLink({ from: 'lnk-frames-axes', section: '2.1' }));
const body = document.getElementById('inspector-body');
const first = body.children[0];
const anchor = first?.children[0];
out.back = { cls: first?.className, tag: anchor?.tagName, text: anchor?.textContent, href: anchor?.href,
  sections: body.children.filter((c) => c.className === 'inspector-section').length,
  textOnly: anchor?.childNodes.every((n) => n.nodeName === '#text') };
window.location.hash = '#table_name=u&frame=local';
anchor.dispatch('pointerdown');
out.followed = anchor.href;
// A keyboard reader on the return link keeps focus when the notes refresh under it.
const focused = body.children[0].children[0];
document.activeElement = focused;
let refocused = null;
FakeElement.prototype.focus = function focus() { refocused = this; document.activeElement = this; };
shell.refresh('xy', notes);
const rebuilt = body.children[0].children[0];
out.keptFocus = refocused === rebuilt && rebuilt !== focused;
FakeElement.prototype.focus = function focus() {};
document.activeElement = null;
shell.openInspector('yz');
out.otherPanel = body.children.some((c) => c.className === 'inspector-return');
shell.openInspector('xy');
out.again = body.children[0]?.className;
shell.setReturnLink('xy', common.returnLink({ from: null, section: '2.1' }));
out.removed = body.children.some((c) => c.className === 'inspector-return');
shell.setReturnLink('xy', common.returnLink({ from: 'lnk-x', section: '9.9.9.9' }));
out.generic = body.children[0]?.children[0]?.textContent;

// The Methodology page's outline: its own key, its own names.
store.clear();
const outline = new Shell({ storageKey: 'calosrv.methodology.outline', labels: {
  collapse: 'Collapse the article outline', expand: 'Expand the article outline',
  collapseTitle: 'Collapse the outline', expandTitle: 'Expand the outline' } });
outline.toggleSidebar(true);
out.outline = { stored: store.get('calosrv.methodology.outline'), config: store.get('calosrv.sidebar') ?? null,
  label: toggle.getAttribute('aria-label'), title: toggle.title };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def shell_results() -> dict:
    return _run(_SHELL_SCRIPT, [(JS / "shell.js").as_uri(), (JS / "page_common.js").as_uri()])


def test_the_configuration_sidebar_keeps_its_key_and_names(shell_results):
    r = shell_results
    assert r["config"] == {"key": "calosrv.sidebar", "stored": "collapsed",
                           "label": "Expand the configuration sidebar", "title": "Expand the sidebar",
                           "collapsed": True}
    assert r["configOpen"] == {"stored": "open", "label": "Collapse the configuration sidebar"}


def test_the_outline_keeps_a_key_and_names_of_its_own(shell_results):
    assert shell_results["outline"] == {"stored": "collapsed", "config": None,
                                        "label": "Expand the article outline", "title": "Expand the outline"}


def test_a_badge_opened_panel_links_back_to_the_article(shell_results):
    r = shell_results
    assert r["back"] == {"cls": "inspector-return", "tag": "A", "text": "↩ Continue reading §2.1 in the Methodology",
                         "href": "/methodology#table_name=t&at=lnk-frames-axes", "sections": 1, "textOnly": True}
    # The view changed on the page travels back with the reader.
    assert r["followed"] == "/methodology#table_name=u&frame=local&at=lnk-frames-axes"


def test_the_return_link_keeps_the_keyboard_focus_across_a_refresh(shell_results):
    assert shell_results["keptFocus"] is True


def test_the_return_link_belongs_to_its_panel_alone(shell_results):
    r = shell_results
    assert r["otherPanel"] is False and r["again"] == "inspector-return"
    assert r["removed"] is False
    assert r["generic"] == "↩ Continue reading the Methodology"
