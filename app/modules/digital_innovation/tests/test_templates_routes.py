"""Route-level coverage for the admin-only Edit Templates screen
(routes/templates.py). lib/template_admin.py already has full unit
coverage for the CRUD/reorder rules themselves — these tests are about
the HTTP layer: auth, the admin-only gate (including its emulation
awareness), validation, and 404s."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiStepTemplate, DI_STAGES
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


def _template(db_session, stage, title, sort_order=0, details=None):
    template = DiStepTemplate(stage=stage, title=title, details=details, sort_order=sort_order)
    db_session.add(template)
    db_session.flush()
    return template


# ── access ──────────────────────────────────────────────────────────────

def test_templates_screen_requires_auth(app, client, db_session):
    with app.test_request_context():
        url = url_for('digital_innovation.templates_screen')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_templates_screen_is_open_to_admin(app, client, db_session):
    # templates_screen isn't scoped to one project — its sidebar falls back
    # to default_project(), which needs an active DiProject to find. In the
    # real app that's always the permanent OVP board; here it needs one of
    # its own so this test doesn't depend on what other tests left behind.
    _project(db_session, 'ta')
    user = _user(db_session, 'ta', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.templates_screen')
    resp = client.get(url)
    assert resp.status_code == 200


def test_templates_screen_403s_for_management(app, client, db_session):
    # Deliberately admin-only, not admin+management — per Ezekiel, unlike
    # the cost footer / Performance gate.
    user = _user(db_session, 'tb', role='management')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.templates_screen')
    resp = client.get(url)
    assert resp.status_code == 403


def test_templates_screen_403s_for_other_roles(app, client, db_session):
    user = _user(db_session, 'tc', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.templates_screen')
    resp = client.get(url)
    assert resp.status_code == 403


def test_templates_screen_403s_for_an_admin_emulating_a_non_admin(app, client, db_session):
    admin = _user(db_session, 'td', role='admin')
    designer = _user(db_session, 'td2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.templates_screen')
    resp = client.get(url)
    assert resp.status_code == 403


# ── add step ────────────────────────────────────────────────────────────

def test_add_template_step_happy_path(app, client, db_session):
    user = _user(db_session, 'te', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_template_step', stage=DI_STAGES[0])
    resp = client.post(url, json={'title': 'Write the brief', 'details': 'One page.'})

    assert resp.status_code == 200
    assert 'Write the brief' in resp.get_data(as_text=True)
    step = DiStepTemplate.query.filter_by(stage=DI_STAGES[0], title='Write the brief').first()
    assert step is not None
    assert step.details == 'One page.'


def test_add_template_step_requires_a_title(app, client, db_session):
    user = _user(db_session, 'tf', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_template_step', stage=DI_STAGES[0])
    resp = client.post(url, json={'title': '   '})
    assert resp.status_code == 400


def test_add_template_step_404s_for_an_unknown_stage(app, client, db_session):
    user = _user(db_session, 'tg', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_template_step', stage='not-a-real-stage')
    resp = client.post(url, json={'title': 'A step'})
    assert resp.status_code == 404


def test_add_template_step_403s_for_a_designer(app, client, db_session):
    user = _user(db_session, 'th', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_template_step', stage=DI_STAGES[0])
    resp = client.post(url, json={'title': 'A step'})
    assert resp.status_code == 403


# ── edit step ───────────────────────────────────────────────────────────

def test_edit_template_step_happy_path(app, client, db_session):
    user = _user(db_session, 'ti', role='admin')
    template = _template(db_session, DI_STAGES[0], 'Old title')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.edit_template_step', template_id=template.id)
    resp = client.post(url, json={'title': 'New title', 'details': 'New details'})

    assert resp.status_code == 200
    assert template.title == 'New title'
    assert template.details == 'New details'


def test_edit_template_step_requires_a_title(app, client, db_session):
    user = _user(db_session, 'tj', role='admin')
    template = _template(db_session, DI_STAGES[0], 'Old title')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.edit_template_step', template_id=template.id)
    resp = client.post(url, json={'title': ''})

    assert resp.status_code == 400
    assert template.title == 'Old title'


def test_edit_template_step_404s_for_an_unknown_step(app, client, db_session):
    user = _user(db_session, 'tk', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.edit_template_step', template_id=999999)
    resp = client.post(url, json={'title': 'A step'})
    assert resp.status_code == 404


# ── delete step ─────────────────────────────────────────────────────────

def test_delete_template_step_removes_it(app, client, db_session):
    user = _user(db_session, 'tl', role='admin')
    template = _template(db_session, DI_STAGES[0], 'Doomed')
    template_id = template.id
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_template_step', template_id=template_id)
    resp = client.delete(url)

    assert resp.status_code == 200
    assert DiStepTemplate.query.get(template_id) is None


def test_delete_template_step_403s_for_a_designer(app, client, db_session):
    user = _user(db_session, 'tm', role='designer')
    template = _template(db_session, DI_STAGES[0], 'Safe')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_template_step', template_id=template.id)
    resp = client.delete(url)

    assert resp.status_code == 403
    assert DiStepTemplate.query.get(template.id) is not None


# ── move step ───────────────────────────────────────────────────────────

def test_move_template_step_up(app, client, db_session):
    user = _user(db_session, 'tn', role='admin')
    first = _template(db_session, DI_STAGES[0], 'First', sort_order=0)
    second = _template(db_session, DI_STAGES[0], 'Second', sort_order=1)
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.move_template_step', template_id=second.id)
    resp = client.post(url, json={'direction': 'up'})

    assert resp.status_code == 200
    assert second.sort_order == 0
    assert first.sort_order == 1


def test_move_template_step_rejects_a_bad_direction(app, client, db_session):
    user = _user(db_session, 'to', role='admin')
    template = _template(db_session, DI_STAGES[0], 'Only step')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.move_template_step', template_id=template.id)
    resp = client.post(url, json={'direction': 'sideways'})
    assert resp.status_code == 400


def test_move_template_step_404s_for_an_unknown_step(app, client, db_session):
    user = _user(db_session, 'tp', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.move_template_step', template_id=999999)
    resp = client.post(url, json={'direction': 'up'})
    assert resp.status_code == 404
