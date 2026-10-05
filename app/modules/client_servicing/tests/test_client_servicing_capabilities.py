"""CS access helpers: the config-driven review lock (which the capabilities
map cannot express) and what the read-only roles can and cannot do."""
from contextlib import contextmanager

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.lib.access import (
    can_access_client_servicing,
    can_close_projects,
    can_view_finance,
)


def _user(db_session, tag, role):
    user = User(name=f'CS Capability {tag}', email=f'cs-cap-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


@contextmanager
def _review_lock(app, on):
    """Set CLIENT_SERVICING_REVIEW_ONLY for one block, then restore it (the
    app fixture is session-scoped)."""
    key = 'CLIENT_SERVICING_REVIEW_ONLY'
    previous = app.config.get(key)
    app.config[key] = on
    try:
        yield
    finally:
        app.config[key] = previous


def test_review_lock_narrows_the_page_to_admin_and_management(app, db_session):
    cs = _user(db_session, 'lock-cs', 'cs')
    project_owner = _user(db_session, 'lock-po', 'project_owner')
    hr = _user(db_session, 'lock-hr', 'hr')
    management = _user(db_session, 'lock-mgmt', 'management')
    admin = _user(db_session, 'lock-admin', 'admin')

    with app.test_request_context():
        with _review_lock(app, False):
            assert can_access_client_servicing(cs) is True
            assert can_access_client_servicing(project_owner) is True
            assert can_access_client_servicing(hr) is True

        with _review_lock(app, True):
            assert can_access_client_servicing(cs) is False
            assert can_access_client_servicing(project_owner) is False
            assert can_access_client_servicing(hr) is False
            assert can_access_client_servicing(management) is True
            assert can_access_client_servicing(admin) is True


def test_a_role_outside_the_page_stays_out_under_the_lock(app, db_session):
    designer = _user(db_session, 'lock-designer', 'designer')

    with app.test_request_context():
        with _review_lock(app, True):
            assert can_access_client_servicing(designer) is False


def test_a_logged_out_visitor_holds_nothing(app):
    with app.test_request_context():
        assert can_access_client_servicing(None) is False


def test_hr_sees_the_page_and_the_money_but_cannot_close(app, db_session):
    user = _user(db_session, 'ro-hr', 'hr')
    with app.test_request_context():
        assert can_access_client_servicing(user) is True
        assert can_view_finance(user) is True
        assert can_close_projects(user) is False


def test_production_and_logistics_are_kept_out_of_cs(app, client, db_session):
    for role in ('production', 'logistics'):
        user = _user(db_session, f'ro-{role}', role)
        with app.test_request_context():
            assert can_access_client_servicing(user) is False

    login_as(client, app, _user(db_session, 'route-production', 'production'), 'password123')
    with app.test_request_context():
        url = url_for('client_servicing.index')
    assert client.get(url).status_code == 403


def test_an_hr_user_can_open_the_cs_page(app, client, db_session):
    """@require_cs reads the capabilities map: hr holds view_cs and gets in."""
    user = _user(db_session, 'route-hr', 'hr')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    assert resp.status_code == 200


def test_a_designer_is_still_refused(app, client, db_session):
    user = _user(db_session, 'route-designer', 'designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    assert resp.status_code == 403
