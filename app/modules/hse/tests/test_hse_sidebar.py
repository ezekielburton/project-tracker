"""
Sidebar and module rail for the single-module HSE role.

The sidebar has no per-item gate, so what the officer sees hangs on one
capability, `view_workspace`.
"""
from flask import url_for

from app.modules.core.shared.lib.capabilities import DEPARTMENT_CAPABILITIES
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
    """Only HSE lacks view_workspace; a new department without it gets a near-empty sidebar."""
    without = sorted(d for d, caps in DEPARTMENT_CAPABILITIES.items() if 'view_workspace' not in caps)
    assert without == ['hse'], (
        f'Departments with no view_workspace: {without}. Only the HSE officer is '
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
    """Hidden links are cosmetic; the officer still gets 403 on projects and dashboard by URL."""
    officer = _user(db_session, 'gate', 'hse')
    login_as(client, app, officer, 'password123')
    with app.test_request_context():
        projects = url_for('project_list.index')
        dashboard = url_for('projects.index')

    assert client.get(projects).status_code == 403
    assert client.get(dashboard).status_code == 403


def test_raise_an_issue_is_gone(app, client, db_session):
    """The sidebar has no "raise an issue" link; the Signal tray covers reporting."""
    designer = _user(db_session, 'signal', 'designer')
    login_as(client, app, designer, 'password123')
    with app.test_request_context():
        url = url_for('wiki.index')

    assert 'data-link="raise-issue"' not in client.get(url).get_data(as_text=True)


# --- the module rail ---------------------------------------------------------

def test_a_section_lists_its_registers_and_badges_their_total(app):
    """A rail section's badge sums its registers' counts; a one-register section has no sub-list."""
    from app.modules.hse.lib.rail import rail_items
    with app.test_request_context():
        items = {i['key']: i for i in rail_items({'incidents': 2, 'first_aid': 3})}
    incidents = items['incidents']
    assert incidents['count'] == 5
    counts = {c['key']: c['count'] for c in incidents['children']}
    assert counts['incidents'] == 2 and counts['first_aid'] == 3
    assert counts['lost_time_injury'] is None
    assert 'children' not in items['compliance']
    assert [c['key'] for c in items['calendar']['children']] == ['calendar', 'schedule']


def test_daily_log_is_a_plain_link_between_statistics_and_calendar(app):
    """Overview, Statistics, then Daily log with no sub-list, then Calendar."""
    from app.modules.hse.lib.rail import rail_items
    with app.test_request_context():
        items = rail_items({'daily_log': 4})
    assert [i['key'] for i in items[:4]] == ['overview', 'statistics', 'daily_log', 'calendar']
    daily = items[2]
    assert daily['label'] == 'Daily log' and daily['count'] == 4
    assert daily['url'].endswith('/hse/daily_log/daily_log')
    assert 'children' not in daily


def _rail_html(app, client, db_session, tag, role):
    user = _user(db_session, tag, role)
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('hse.register_page', group_key='incidents', register_key='incidents')
    html = client.get(url).get_data(as_text=True)
    return html.split('<aside class="module-rail">')[1].split('</aside>')[0]


def test_lists_and_performance_sit_under_training(app, client, db_session):
    rail = _rail_html(app, client, db_session, 'rail-order', 'hse')
    assert rail.index('Training') < rail.index('Lists &amp; people') < rail.index('My performance')
    assert 'module-rail-foot' not in rail
    assert 'hse-rail-divided' in rail


def test_management_is_not_shown_lists_it_cannot_open(app, client, db_session):
    rail = _rail_html(app, client, db_session, 'rail-mgmt', 'management')
    assert 'Lists &amp; people' not in rail
    assert 'My performance' in rail
