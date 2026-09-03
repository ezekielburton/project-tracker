"""Route-level coverage for the Incoming overlay: routes/intake.py's
promote/dismiss actions for both card kinds (native DiIntakeItem rows and
live FeatureRequest rows), and board.html's rendering of the trigger
button + modal (shown only on the permanent OVP board, gated entirely
behind can_edit_board, empty state)."""
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


def _intake_item(db_session, project, tag, status='pending'):
    item = DiIntakeItem(
        di_project_id=project.id,
        source_type='slack',
        source_ref=f'#feedback/{tag}',
        title=f'Intake item {tag}',
        status=status,
    )
    db_session.add(item)
    db_session.flush()
    return item


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


# ── promote ─────────────────────────────────────────────────────────────

def test_promote_intake_item_requires_auth(app, client, db_session):
    project = _permanent_project(db_session, 'a')
    item = _intake_item(db_session, project, 'a')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code in (302, 401)


def test_promote_intake_item_happy_path(app, client, db_session):
    project = _permanent_project(db_session, 'b')
    item = _intake_item(db_session, project, 'b')
    user = _user(db_session, 'b', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'promoted'
    assert 'feature_id' in body

    refreshed_item = DiIntakeItem.query.get(item.id)
    assert refreshed_item.status == 'promoted'

    feature = DiFeature.query.get(body['feature_id'])
    assert feature is not None
    assert feature.name == 'Intake item b'
    assert feature.di_project_id == project.id


def test_promote_intake_item_403s_for_a_designer(app, client, db_session):
    project = _permanent_project(db_session, 'c')
    item = _intake_item(db_session, project, 'c')
    user = _user(db_session, 'c', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code == 403


def test_promote_intake_item_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    project = _permanent_project(db_session, 'd')
    item = _intake_item(db_session, project, 'd')
    admin = _user(db_session, 'd', role='admin')
    designer = _user(db_session, 'd2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.promote_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code == 403


def test_promote_intake_item_404s_for_an_unknown_item(app, client, db_session):
    user = _user(db_session, 'e', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_intake_item', item_id=999999)
    resp = client.post(url)
    assert resp.status_code == 404


def test_promote_intake_item_404s_for_an_already_promoted_item(app, client, db_session):
    project = _permanent_project(db_session, 'f')
    item = _intake_item(db_session, project, 'f', status='promoted')
    user = _user(db_session, 'f', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.promote_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code == 404


# ── dismiss ─────────────────────────────────────────────────────────────

def test_dismiss_intake_item_happy_path(app, client, db_session):
    project = _permanent_project(db_session, 'g')
    item = _intake_item(db_session, project, 'g')
    user = _user(db_session, 'g', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'dismissed'

    refreshed_item = DiIntakeItem.query.get(item.id)
    assert refreshed_item.status == 'dismissed'
    # Dismissing never touches DiFeature — nothing should exist for it.
    assert DiFeature.query.filter_by(di_project_id=project.id).count() == 0


def test_dismiss_intake_item_403s_for_a_designer(app, client, db_session):
    project = _permanent_project(db_session, 'h')
    item = _intake_item(db_session, project, 'h')
    user = _user(db_session, 'h', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.dismiss_intake_item', item_id=item.id)
    resp = client.post(url)
    assert resp.status_code == 403


# ── board.html rendering ───────────────────────────────────────────────

def test_board_shows_incoming_trigger_and_modal_on_the_permanent_project(app, client, db_session):
    project = _permanent_project(db_session, 'i')
    _intake_item(db_session, project, 'i')
    user = _user(db_session, 'i', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-incoming-trigger' in body
    assert 'di-incoming-badge' in body
    assert 'Intake item i' in body
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
    _intake_item(db_session, project, 'k')
    user = _user(db_session, 'k', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    # can_edit_board gates the trigger button entirely, same as
    # "+ New project" — a view-only user has no promote/dismiss action to
    # take, so there's nothing for the overlay to offer them.
    assert 'di-incoming-trigger' not in body
    assert 'di-incoming-promote-btn' not in body
    assert 'di-incoming-dismiss-btn' not in body


def test_board_incoming_modal_excludes_non_pending_items(app, client, db_session):
    project = _permanent_project(db_session, 'l')
    _intake_item(db_session, project, 'l1', status='promoted')
    _intake_item(db_session, project, 'l2', status='dismissed')
    user = _user(db_session, 'l', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Intake item l1' not in body
    assert 'Intake item l2' not in body


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
    # No badge at all when there's nothing pending — not even a "0".
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
    _intake_item(db_session, project, 'o')
    user = _user(db_session, 'o', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Intake item o' in body
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


def test_intake_cards_fragment_excludes_non_pending_items(app, client, db_session):
    project = _permanent_project(db_session, 'r')
    _intake_item(db_session, project, 'r1', status='promoted')
    _intake_item(db_session, project, 'r2', status='dismissed')
    user = _user(db_session, 'r', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.intake_cards_fragment', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Intake item r1' not in body
    assert 'Intake item r2' not in body
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

    # Dismissing never touches the feature request's own status — it
    # stays exactly as it was on the public Feature Requests page.
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
    _feature_request(db_session, 'ac', submitter)
    admin = _user(db_session, 'ac-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title ac' in body
    assert 'data-di-kind="feature_request"' in body
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


def test_board_incoming_modal_mixes_intake_items_and_feature_requests(app, client, db_session):
    project = _permanent_project(db_session, 'af')
    submitter = _user(db_session, 'af-sub', role='designer')
    _feature_request(db_session, 'af', submitter)
    _intake_item(db_session, project, 'af')
    admin = _user(db_session, 'af-admin', role='admin')
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'FR title af' in body
    assert 'Intake item af' in body
    assert 'data-di-kind="feature_request"' in body
    assert 'data-di-kind="intake_item"' in body
    assert 'di-incoming-badge">2<' in body
