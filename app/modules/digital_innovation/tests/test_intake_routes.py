"""Route tests for the Incoming tray: promote/dismiss of FeatureRequest cards,
the live cards fragment, and board.html's trigger button and modal (permanent
board only, can_edit_board only)."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.core.shared.models import FeatureRequest, Notification
from app.modules.digital_innovation.models import DiProject, DiIntakeItem, DiFeature
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


def _permanent_project(db_session, tag='ovp'):
    project = DiProject(name=f'Test OVP {tag}', lifecycle='active', is_permanent=True)
    db_session.add(project)
    db_session.flush()
    return project


def _feature_request(db_session, tag, submitter, status='requested'):
    fr = FeatureRequest(
        title=f'FR title {tag}',
        description=f'FR description {tag}',
        submitted_by_id=submitter.id,
        status=status,
    )
    db_session.add(fr)
    db_session.flush()
    return fr


# ── board.html rendering ───────────────────────────────────────────────

def test_board_shows_incoming_trigger_and_modal_on_the_permanent_project(app, client, db_session):
    project = _permanent_project(db_session, 'i')
    submitter = _user(db_session, 'i-sub', role='designer')
    _feature_request(db_session, 'i', submitter)
    user = _user(db_session, 'i', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-incoming-trigger' in body
    assert 'di-incoming-badge' in body
    assert 'FR title i' in body
    assert 'di-incoming-promote-btn' in body
    assert 'di-incoming-dismiss-btn' in body


def test_board_hides_incoming_trigger_on_a_non_permanent_project(app, client, db_session):
    project = _project(db_session, 'j')
    user = _user(db_session, 'j', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-incoming-trigger' not in body
    assert 'di-incoming-modal' not in body


def test_board_hides_incoming_trigger_and_modal_from_a_designer(app, client, db_session):
    project = _permanent_project(db_session, 'k')
    submitter = _user(db_session, 'k-sub', role='designer')
    _feature_request(db_session, 'k', submitter)
    user = _user(db_session, 'k', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    # View-only users get no trigger button: they can't promote or dismiss.
    assert 'di-incoming-trigger' not in body
    assert 'di-incoming-promote-btn' not in body
    assert 'di-incoming-dismiss-btn' not in body


def test_board_incoming_modal_shows_empty_state(app, client, db_session):
    project = _permanent_project(db_session, 'm')
    user = _user(db_session, 'm', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-incoming-empty' in body
    # No badge, not even "0", when nothing is pending.
    assert 'di-incoming-badge' not in body


# ── live-refresh fragment (routes/intake.py::intake_cards_fragment) ─────

def test_intake_cards_fragment_requires_auth(app, client, db_session):
    project = _permanent_project(db_session, 'n')

    with app.test_request_context():
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=project.id)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_intake_cards_fragment_returns_pending_cards(app, client, db_session):
    project = _permanent_project(db_session, 'o')
    submitter = _user(db_session, 'o-sub', role='designer')
    _feature_request(db_session, 'o', submitter)
    user = _user(db_session, 'o', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title o' in body
    assert 'di-incoming-promote-btn' in body
    assert 'di-incoming-dismiss-btn' in body


def test_intake_cards_fragment_403s_for_a_designer(app, client, db_session):
    project = _permanent_project(db_session, 'p')
    user = _user(db_session, 'p', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 403


def test_intake_cards_fragment_404s_for_an_unknown_project(app, client, db_session):
    user = _user(db_session, 'q', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=999999)
    resp = client.get(url)
    assert resp.status_code == 404


def test_intake_cards_fragment_excludes_a_dismissed_feature_request(app, client, db_session):
    project = _permanent_project(db_session, 'r')
    submitter = _user(db_session, 'r-sub', role='designer')
    fr = _feature_request(db_session, 'r', submitter)
    user = _user(db_session, 'r', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        dismiss_url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=project.id)
    client.post(dismiss_url)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title r' not in body
    assert 'di-incoming-empty' in body


def test_board_incoming_trigger_carries_the_project_id(app, client, db_session):
    project = _permanent_project(db_session, 's')
    user = _user(db_session, 's', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'id="di-incoming-trigger" data-di-project-id="{}"'.format(project.id) in body


# ── promote/dismiss a live FeatureRequest card ───────────────────────────

def test_promote_feature_request_requires_auth(app, client, db_session):
    _permanent_project(db_session, 't')
    submitter = _user(db_session, 't-sub', role='designer')
    fr = _feature_request(db_session, 't', submitter)

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=fr.id)
    resp = client.post(url)
    assert resp.status_code in (302, 401)


def test_promote_feature_request_happy_path(app, client, db_session):
    _permanent_project(db_session, 'u')
    submitter = _user(db_session, 'u-sub', role='designer')
    fr = _feature_request(db_session, 'u', submitter)
    admin = _user(db_session, 'u-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=fr.id)
    resp = client.post(url)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'in_progress'
    assert 'feature_id' in body

    refreshed_fr = FeatureRequest.query.get(fr.id)
    assert refreshed_fr.status == 'in_progress'

    feature = DiFeature.query.get(body['feature_id'])
    assert feature is not None
    assert feature.name == fr.title


def test_promote_feature_request_notifies_the_submitter(app, client, db_session):
    _permanent_project(db_session, 'v')
    submitter = _user(db_session, 'v-sub', role='designer')
    fr = _feature_request(db_session, 'v', submitter)
    admin = _user(db_session, 'v-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=fr.id)
    client.post(url)

    notification = Notification.query.filter_by(recipient_id=submitter.id).first()
    assert notification is not None
    assert 'in progress' in notification.message
    assert fr.title in notification.message


def test_promote_feature_request_403s_for_a_designer(app, client, db_session):
    _permanent_project(db_session, 'w')
    submitter = _user(db_session, 'w-sub', role='designer')
    fr = _feature_request(db_session, 'w', submitter)
    designer = _user(db_session, 'w-designer', role='designer')
    login_as(client, app, designer, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=fr.id)
    resp = client.post(url)
    assert resp.status_code == 403


def test_promote_feature_request_404s_for_an_unknown_request(app, client, db_session):
    user = _user(db_session, 'x', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=999999)
    resp = client.post(url)
    assert resp.status_code == 404


def test_promote_feature_request_404s_for_a_request_already_in_progress(app, client, db_session):
    submitter = _user(db_session, 'y-sub', role='designer')
    fr = _feature_request(db_session, 'y', submitter, status='in_progress')
    admin = _user(db_session, 'y-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=fr.id)
    resp = client.post(url)
    assert resp.status_code == 404


def test_dismiss_feature_request_happy_path(app, client, db_session):
    _permanent_project(db_session, 'z')
    submitter = _user(db_session, 'z-sub', role='designer')
    fr = _feature_request(db_session, 'z', submitter)
    admin = _user(db_session, 'z-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
    resp = client.post(url)
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'dismissed'

    # Dismissing leaves the FeatureRequest's own status unchanged.
    refreshed_fr = FeatureRequest.query.get(fr.id)
    assert refreshed_fr.status == 'requested'


def test_dismiss_feature_request_403s_for_a_designer(app, client, db_session):
    _permanent_project(db_session, 'aa')
    submitter = _user(db_session, 'aa-sub', role='designer')
    fr = _feature_request(db_session, 'aa', submitter)
    designer = _user(db_session, 'aa-designer', role='designer')
    login_as(client, app, designer, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
    resp = client.post(url)
    assert resp.status_code == 403


def test_dismiss_feature_request_404s_for_an_unknown_request(app, client, db_session):
    user = _user(db_session, 'ab', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=999999)
    resp = client.post(url)
    assert resp.status_code == 404


# ── board.html / fragment rendering with FeatureRequest cards ───────────

def test_board_incoming_modal_shows_an_existing_feature_request(app, client, db_session):
    project = _permanent_project(db_session, 'ac')
    submitter = _user(db_session, 'ac-sub', role='designer')
    fr = _feature_request(db_session, 'ac', submitter)
    admin = _user(db_session, 'ac-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title ac' in body
    assert f'data-di-intake-id="{fr.id}"' in body
    assert f'Feature request · {submitter.name}' in body
    assert 'di-incoming-badge' in body


def test_board_incoming_modal_excludes_non_requested_feature_requests(app, client, db_session):
    project = _permanent_project(db_session, 'ad')
    submitter = _user(db_session, 'ad-sub', role='designer')
    _feature_request(db_session, 'ad', submitter, status='implemented')
    admin = _user(db_session, 'ad-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title ad' not in body
    assert 'di-incoming-empty' in body


def test_board_incoming_modal_excludes_a_dismissed_feature_request(app, client, db_session):
    project = _permanent_project(db_session, 'ae')
    submitter = _user(db_session, 'ae-sub', role='designer')
    fr = _feature_request(db_session, 'ae', submitter)
    admin = _user(db_session, 'ae-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        dismiss_url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
        board_url = url_for('digital_innovation.project_board', di_project_id=project.id)
    client.post(dismiss_url)
    resp = client.get(board_url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title ae' not in body
    assert 'di-incoming-empty' in body


def test_dismiss_feature_request_twice_records_one_marker(app, client, db_session):
    _permanent_project(db_session, 'dd')
    submitter = _user(db_session, 'dd-sub', role='designer')
    fr = _feature_request(db_session, 'dd', submitter)
    admin = _user(db_session, 'dd-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
    first = client.post(url)
    second = client.post(url)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()['status'] == 'dismissed'
    markers = DiIntakeItem.query.filter_by(
        source_type='feature_request', source_ref=str(fr.id), status='dismissed',
    ).count()
    assert markers == 1


def test_dismiss_feature_request_404s_for_a_request_no_longer_requested(app, client, db_session):
    _permanent_project(db_session, 'de')
    submitter = _user(db_session, 'de-sub', role='designer')
    fr = _feature_request(db_session, 'de', submitter, status='in_progress')
    admin = _user(db_session, 'de-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
    resp = client.post(url)

    assert resp.status_code == 404
    assert DiIntakeItem.query.filter_by(source_type='feature_request', source_ref=str(fr.id)).count() == 0


def test_promote_feature_request_without_a_permanent_board_returns_a_clear_error(app, client, db_session):
    # No _permanent_project(): the seeded board is missing.
    submitter = _user(db_session, 'df-sub', role='designer')
    fr = _feature_request(db_session, 'df', submitter)
    admin = _user(db_session, 'df-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_feature_request', feature_request_id=fr.id)
    resp = client.post(url)

    assert resp.status_code == 409
    assert 'permanent' in resp.get_json()['error']
    assert FeatureRequest.query.get(fr.id).status == 'requested'


def test_dismiss_feature_request_without_a_permanent_board_returns_a_clear_error(app, client, db_session):
    submitter = _user(db_session, 'dg-sub', role='designer')
    fr = _feature_request(db_session, 'dg', submitter)
    admin = _user(db_session, 'dg-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_feature_request', feature_request_id=fr.id)
    resp = client.post(url)

    assert resp.status_code == 409
    assert 'permanent' in resp.get_json()['error']
