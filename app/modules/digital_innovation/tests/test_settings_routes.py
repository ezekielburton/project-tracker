"""Route tests for the Settings screen (Dev Time rate, currency): the
manage_di_templates gate, saving, validation 400s, and that new Dev Time
entries are priced at the saved rate."""
import datetime

import pytest
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.lib import costs
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.models import DiCostEntry
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


def _url(app):
    with app.test_request_context():
        return url_for('digital_innovation.settings_screen')


def _seed_settings(db_session, rate=50.0, currency='AED'):
    settings = costs.get_settings()
    settings.dev_hourly_rate = rate
    settings.currency = currency
    db_session.commit()
    return settings


# ── access ──────────────────────────────────────────────────────────────

def test_settings_screen_requires_auth(app, client, db_session):
    resp = client.get(_url(app))
    assert resp.status_code in (302, 401)


def test_settings_screen_is_open_to_admin_and_shows_current_values(app, client, db_session):
    # The sidebar needs default_project() to find an active DiProject.
    _project(db_session, 'sa')
    _seed_settings(db_session, rate=75.5, currency='USD')
    user = _user(db_session, 'sa', role='admin')
    login_as(client, app, user, 'password123')

    resp = client.get(_url(app))
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'id="di-settings-form"' in body
    assert 'value="75.50"' in body
    assert 'value="USD"' in body
    assert 'existing entries keep the rate they were saved with' in body


@pytest.mark.parametrize('role', ['management', 'designer'])
def test_settings_screen_403s_for_other_roles(app, client, db_session, role):
    user = _user(db_session, f'sb-{role}', role=role)
    login_as(client, app, user, 'password123')

    assert client.get(_url(app)).status_code == 403
    assert client.post(_url(app), json={'dev_hourly_rate': 10, 'currency': 'AED'}).status_code == 403


def test_settings_screen_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    admin = _user(db_session, 'sc', role='admin')
    designer = _user(db_session, 'sc2', role='designer')
    login_as(client, app, admin, 'password123')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    assert client.get(_url(app)).status_code == 403


def test_rail_shows_settings_link_to_admin(app, client, db_session):
    _project(db_session, 'sd')
    user = _user(db_session, 'sd', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.templates_screen')
    body = client.get(url).get_data(as_text=True)
    assert f'href="{_url(app)}"' in body


# ── save ────────────────────────────────────────────────────────────────

def test_save_settings_stores_rounded_rate_and_uppercased_currency(app, client, db_session):
    _seed_settings(db_session)
    user = _user(db_session, 'se', role='admin')
    login_as(client, app, user, 'password123')

    resp = client.post(_url(app), json={'dev_hourly_rate': '120.456', 'currency': ' usd '})

    assert resp.status_code == 200
    assert resp.get_json() == {'dev_hourly_rate': 120.46, 'currency': 'USD'}
    settings = costs.get_settings()
    assert settings.dev_hourly_rate == 120.46
    assert settings.currency == 'USD'


def test_save_settings_accepts_a_zero_rate(app, client, db_session):
    _seed_settings(db_session, rate=40.0)
    user = _user(db_session, 'sf', role='admin')
    login_as(client, app, user, 'password123')

    resp = client.post(_url(app), json={'dev_hourly_rate': 0, 'currency': 'AED'})

    assert resp.status_code == 200
    assert costs.get_settings().dev_hourly_rate == 0


@pytest.mark.parametrize('payload, field', [
    ({'dev_hourly_rate': -5, 'currency': 'USD'}, 'dev_hourly_rate'),
    ({'dev_hourly_rate': 'abc', 'currency': 'USD'}, 'dev_hourly_rate'),
    ({'dev_hourly_rate': '', 'currency': 'USD'}, 'dev_hourly_rate'),
    ({'dev_hourly_rate': True, 'currency': 'USD'}, 'dev_hourly_rate'),
    ({'dev_hourly_rate': 'nan', 'currency': 'USD'}, 'dev_hourly_rate'),
    ({'dev_hourly_rate': 90, 'currency': 'ABCDEFGHIJK'}, 'currency'),
    ({'dev_hourly_rate': 90, 'currency': '   '}, 'currency'),
])
def test_save_settings_400s_on_bad_input_and_saves_nothing(app, client, db_session, payload, field):
    _seed_settings(db_session, rate=50.0, currency='AED')
    user = _user(db_session, 'sg', role='admin')
    login_as(client, app, user, 'password123')

    resp = client.post(_url(app), json=payload)

    assert resp.status_code == 400
    body = resp.get_json()
    assert field in body['errors']
    assert body['error']
    db_session.expire_all()
    settings = costs.get_settings()
    # The valid field in the same request is not saved either.
    assert settings.dev_hourly_rate == 50.0
    assert settings.currency == 'AED'


# ── pricing ─────────────────────────────────────────────────────────────

def test_dev_time_entry_after_a_rate_change_uses_the_new_rate(app, client, db_session):
    _seed_settings(db_session, rate=100.0)
    project = _project(db_session, 'sh')
    feature = engine.create_feature(project, 'Rate change feature')
    costs.add_cost_entry(project, datetime.date(2026, 9, 1), 'dev_time', hours=2, feature=feature)
    db_session.commit()
    user = _user(db_session, 'sh', role='admin')
    login_as(client, app, user, 'password123')

    assert client.post(_url(app), json={'dev_hourly_rate': 150, 'currency': 'AED'}).status_code == 200

    with app.test_request_context():
        cost_url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(cost_url, json={
        'type': 'dev_time', 'date': '2026-09-02', 'hours': 2, 'feature_id': feature.id,
    })
    assert resp.status_code == 200

    entries = (DiCostEntry.query.filter_by(di_project_id=project.id)
               .order_by(DiCostEntry.id).all())
    assert [e.amount for e in entries] == [200.0, 300.0]
