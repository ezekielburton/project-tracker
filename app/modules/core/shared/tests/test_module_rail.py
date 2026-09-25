"""The inner module rail is one component, not one per module.

Client Servicing and Digital Innovation carried byte-identical rail CSS
before this was extracted, and HSE would have been the third copy. These
assertions keep it that way, and pin the plain-item markup to exactly what
those two modules rendered before the move — a rail with no icon and no
count must still be a bare link, or their pages shift.
"""
from pathlib import Path

import app as app_package


APP_ROOT = Path(app_package.__file__).parent

# What the shared rail replaced. A module reintroducing one of these is
# forking the component again.
RETIRED_CLASSES = ('cs-sidebar', 'cs-nav-item', 'di-sidebar-nav', 'di-nav-item')

# What the shared page frame replaced (.module-page / .module-shell).
RETIRED_SHELL_CLASSES = ('cs-shell', 'hse-shell')


def _render(app, items, active='', body=None, title=None):
    source = "{% from '_shared_macros.html' import module_rail %}"
    if body is None:
        source += '{{ module_rail(items, active, title) }}'
    else:
        source += '{% call module_rail(items, active, title) %}' + body + '{% endcall %}'
    with app.app_context():
        return app.jinja_env.from_string(source).render(items=items, active=active, title=title)


def _source_hits(names):
    hits = []
    for path in APP_ROOT.rglob('*'):
        if path.suffix not in ('.css', '.html', '.js', '.py'):
            continue
        if 'tests' in path.parts or '__pycache__' in path.parts:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        hits += [f'{path.relative_to(APP_ROOT)}: {n}' for n in names if n in text]
    return hits


def test_only_the_active_item_is_marked(app):
    html = _render(app, [
        {'key': 'table', 'label': 'Table', 'url': '/a'},
        {'key': 'closed', 'label': 'Closed', 'url': '/b'},
    ], active='closed')
    assert '<a href="/a" class="module-rail-item">Table</a>' in html
    assert 'module-rail-item module-rail-item--active">Closed</a>' in html
    assert html.count('module-rail-item--active') == 1


def test_a_plain_item_is_a_bare_link(app):
    """Client Servicing and DI rails are text-only. Their markup must not
    gain wrapper elements, or their spacing changes."""
    html = _render(app, [{'key': 'x', 'label': 'Invoicing', 'url': '/inv'}])
    assert '<a href="/inv" class="module-rail-item">Invoicing</a>' in html
    assert 'module-rail-item--rich' not in html
    assert 'module-rail-label' not in html


def test_an_icon_or_count_makes_the_row_a_flex_line(app):
    html = _render(app, [
        {'key': 'inc', 'label': 'Incidents', 'url': '/i', 'count': 13, 'icon': 'M1 2'},
    ])
    assert 'module-rail-item--rich' in html
    assert '<span class="module-rail-count">13</span>' in html
    assert '<path d="M1 2"/>' in html


def test_a_zero_count_still_renders(app):
    """0 is a real count, not a missing one."""
    html = _render(app, [{'key': 'x', 'label': 'Stores', 'url': '/s', 'count': 0}])
    assert '<span class="module-rail-count">0</span>' in html


def test_an_item_without_a_url_is_not_a_link(app):
    html = _render(app, [{'key': 'soon', 'label': 'Calendar', 'url': None}])
    assert '<a ' not in html
    assert 'module-rail-item--disabled">Calendar</span>' in html


def test_the_call_body_lands_inside_the_rail(app):
    """Digital Innovation hangs its project switcher under the nav."""
    html = _render(app, [{'key': 'board', 'label': 'Board', 'url': '/b'}],
                   body='<div class="di-sidebar-section">Projects</div>')
    assert '</nav><div class="di-sidebar-section">Projects</div>' in html
    assert html.rstrip().endswith('</aside>')


def test_no_module_redefines_the_retired_rail_classes():
    """One rail, one definition. If this fails, a module has grown its own
    rail again — point it at module_rail() instead of restoring the class."""
    offenders = _source_hits(RETIRED_CLASSES)
    assert not offenders, 'Retired rail classes are back: ' + ', '.join(offenders)


def test_no_module_redefines_the_page_frame():
    """One page frame. A module needing a variation adds a class beside
    .module-main rather than growing its own shell."""
    offenders = _source_hits(RETIRED_SHELL_CLASSES)
    assert not offenders, 'Retired shell classes are back: ' + ', '.join(offenders)


def test_title_heads_the_rail(app):
    html = _render(app, [{'key': 'o', 'label': 'Overview', 'url': '/o'}], title='Dashboard')
    assert '<aside class="module-rail"><div class="module-rail-title">Dashboard</div>' in html


def test_no_title_renders_no_title(app):
    html = _render(app, [{'key': 'o', 'label': 'Overview', 'url': '/o'}])
    assert 'module-rail-title' not in html


def test_a_soon_item_is_greyed_and_tagged(app):
    html = _render(app, [{'key': 'hub', 'label': 'My hub', 'url': None, 'soon': True}])
    assert 'module-rail-item--rich' in html
    assert 'module-rail-item--disabled' in html
    assert '<span class="module-rail-soon">Soon</span>' in html
    assert '<a ' not in html
