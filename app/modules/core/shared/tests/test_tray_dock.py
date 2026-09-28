"""The global tray dock in the app shell. It must render outside
<main id="main-content">, which SPA navigation replaces; inside it, every page
swap would destroy the dock and its handlers.
"""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


def _user(db_session, tag):
    user = User(name=f'Tray {tag}', email=f'tray-{tag}@example.com', role='designer')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _home(app, client):
    with app.test_request_context():
        home = url_for('main.index')
    return client.get(home, follow_redirects=True).get_data(as_text=True)


def test_a_signed_in_user_gets_both_launchers(app, client, db_session):
    login_as(client, app, _user(db_session, 'signed-in'), 'password123')
    html = _home(app, client)
    assert 'id="tray-dock"' in html
    assert 'data-tray="chat"' in html
    assert 'data-tray="signal"' in html


def test_the_panel_shell_ships_its_slots(app, client, db_session):
    login_as(client, app, _user(db_session, 'shell'), 'password123')
    html = _home(app, client)
    for marker in ('id="tray-panel"', 'id="tray-panel-title"',
                   'id="tray-panel-actions"', 'id="tray-panel-body"',
                   'id="tray-panel-close"'):
        assert marker in html, marker


def test_the_panel_starts_closed(app, client, db_session):
    login_as(client, app, _user(db_session, 'closed'), 'password123')
    html = _home(app, client)
    assert 'class="tray-panel hidden"' in html


def test_a_logged_out_visitor_gets_no_dock(app, client):
    html = _home(app, client)
    assert 'id="tray-dock"' not in html


def test_the_dock_sits_outside_the_swapped_region(app, client, db_session):
    """SPA nav replaces only <main id="main-content">."""
    login_as(client, app, _user(db_session, 'spa'), 'password123')
    html = _home(app, client)
    assert html.index('</main>') < html.index('id="tray-dock"')
