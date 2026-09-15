"""
What a single-module role sees.

The HSE officer is the first role meant to see *less* of the app, and the
sidebar is hand-written markup with no per-item gate — so the decision lives
in one capability, `view_workspace`, and these assertions are what stop it
drifting.
"""
from flask import url_for

from app.modules.core.shared.lib.capabilities import ROLE_CAPABILITIES
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


# Everything the officer should see, and the things he should not.
HSE_SEES = ('data-link="hse"', 'data-link="file-storage"', 'data-link="wiki"')
HSE_DOES_NOT_SEE = (
    'data-link="dashboard"', 'data-link="projects"', 'data-link="client-servicing"',
    'data-link="digital-innovation"', 'data-link="client-directory"',
    'data-link="google-slides"', 'data-link="update-blog"',
)


def _user(db_session, tag, role):
    user = User(name=f'HSE Sidebar {tag}', email=f'hse-sidebar-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_only_the_single_module_role_lacks_the_workspace():
    """A new role added without view_workspace would silently get a nearly
    empty sidebar. If this fails, decide deliberately — then update it."""
    without = sorted(r for r, caps in ROLE_CAPABILITIES.items()
                     if '*' not in caps and 'view_workspace' not in caps)
    assert without == ['hse'], (
        f'Roles with no view_workspace: {without}. Only the HSE officer is '
        'meant to see a single-module sidebar.'
    )


def test_the_officers_sidebar_is_his_module_file_storage_and_the_wiki(app, client, db_session):
    officer = _user(db_session, 'officer', 'hse')
    login_as(client, app, officer, 'password123')
    with app.test_request_context():
        url = url_for('hse.register_page', group_key='incidents', register_key='incidents')

    html = client.get(url).get_data(as_text=True)
    for marker in HSE_SEES:
        assert marker in html, f'The officer should see {marker}'
    for marker in HSE_DOES_NOT_SEE:
        assert marker not in html, f'The officer should not see {marker}'


def test_everyone_else_keeps_the_full_sidebar(app, client, db_session):
    designer = _user(db_session, 'designer', 'designer')
    login_as(client, app, designer, 'password123')
    with app.test_request_context():
        url = url_for('wiki.index')

    html = client.get(url).get_data(as_text=True)
    for marker in ('data-link="dashboard"', 'data-link="projects"',
                   'data-link="digital-innovation"', 'data-link="google-slides"'):
        assert marker in html, f'A designer should still see {marker}'


def test_hiding_is_not_the_gate(app, client, db_session):
    """The sidebar is cosmetic. Projects and the dashboard were
    login-only, so the officer could have reached them by typing the URL."""
    officer = _user(db_session, 'gate', 'hse')
    login_as(client, app, officer, 'password123')
    with app.test_request_context():
        projects = url_for('project_list.index')
        dashboard = url_for('projects.index')

    assert client.get(projects).status_code == 403
    assert client.get(dashboard).status_code == 403


def test_raise_an_issue_is_gone(app, client, db_session):
    """Retired — the Signal tray already covers it. This catches it coming
    back rather than leaving two ways to report the same thing."""
    designer = _user(db_session, 'signal', 'designer')
    login_as(client, app, designer, 'password123')
    with app.test_request_context():
        url = url_for('wiki.index')

    assert 'data-link="raise-issue"' not in client.get(url).get_data(as_text=True)
