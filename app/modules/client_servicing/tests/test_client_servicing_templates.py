"""CS pages must not nest a <main> inside #main-content: spa_strip_response()
stops at the first </main>, so a nested one truncates the SPA fragment."""
import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


CS_PAGES = [
    ('client_servicing.index', {}),
    ('client_servicing.table', {}),
    ('client_servicing.invoicing', {}),
    ('client_servicing.invoicing_summary', {}),
    ('client_servicing.calendar', {}),
    ('client_servicing.calendar', {'view': 'agenda'}),
    ('client_servicing.closed', {}),
]


@pytest.fixture
def cs_user(app, client, db_session):
    user = User(name='Shell Tester', email='cs-shell-test@example.com', role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')
    return user


def _fragment(app, client, endpoint, params):
    """The page as SPA nav receives it: just the #main-content block."""
    with app.test_request_context():
        url = url_for(endpoint, **params)
    resp = client.get(url, headers={'X-Nav-Request': '1'})
    assert resp.status_code == 200, endpoint
    return resp.get_data(as_text=True)


@pytest.mark.parametrize('endpoint,params', CS_PAGES)
def test_no_nested_main_in_the_spa_fragment(app, client, cs_user, endpoint, params):
    assert '<main' not in _fragment(app, client, endpoint, params).lower()


def test_the_table_fragment_keeps_what_comes_after_the_shell(app, client, cs_user):
    """The close modals sit last in the content block, so finding them proves no truncation."""
    fragment = _fragment(app, client, 'client_servicing.table', {})
    assert 'cs-close-modal' in fragment
    assert 'cs-closeout-modal' in fragment
    assert 'client_servicing_close.js' in fragment


def test_the_closed_fragment_keeps_its_page_script(app, client, cs_user):
    fragment = _fragment(app, client, 'client_servicing.closed', {})
    assert 'client_servicing_closed.js' in fragment


def test_invoicing_rows_carry_their_project_id_for_a_non_editor(app, client, db_session):
    """Invoicing rows carry data-project-id for non-editors too; Dashboard links focus rows by it."""
    from app.modules.core.shared.models import Project
    user = User(name='Read Only', email='cs-shell-readonly@example.com', role='management')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    project = Project(name='Focusable Project', cs_lead_id=user.id, created_by_id=user.id,
                      project_status='briefed')
    db_session.add(project)
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.invoicing')
    html = client.get(url).get_data(as_text=True)
    assert 'data-project-id="{}"'.format(project.id) in html
    assert 'data-edit-url' not in html      # management can't edit finance
