"""Route-level coverage for Digital Innovation project creation
(routes/projects.py). This had no dedicated test file before the board
write-access gate (can_edit_di_board) landed — folding both in here:
the plain happy-path/validation behaviour, and the admin-only gate. Also
covers search_projects/link_project (the system-project link picker,
2 Sep 2026) since they live in the same routes file."""
from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.tests.test_features_routes import _user


def _shared_project(db_session, tag, client=None):
    """A minimal row in the real (shared) projects table — the link
    target, distinct from DiProject. Mirrors the minimal-fields pattern
    test_overlay_deliverables.py already uses for this model."""
    lead = User(name=f'CS Lead {tag}', email=f'di-link-test-{tag}@example.com', role='cs')
    lead.set_password('password123')
    db_session.add(lead)
    db_session.flush()
    project = Project(
        name=f'Shared Project {tag}', brief_type='standard',
        cs_lead_id=lead.id, created_by_id=lead.id, project_status='in_design',
        client=client,
    )
    db_session.add(project)
    db_session.flush()
    return project


def test_create_project_requires_auth(app, client, db_session):
    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': 'New board'})
    assert resp.status_code in (302, 401)


def test_create_project_happy_path_for_admin(app, client, db_session):
    user = _user(db_session, 'pa', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': 'New board'})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['name'] == 'New board'
    assert DiProject.query.filter_by(name='New board').first() is not None


def test_create_project_requires_a_name(app, client, db_session):
    user = _user(db_session, 'pb', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': '   '})
    assert resp.status_code == 400


def test_create_project_403s_for_a_designer(app, client, db_session):
    user = _user(db_session, 'pc', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': 'Should not exist'})

    assert resp.status_code == 403
    assert DiProject.query.filter_by(name='Should not exist').first() is None


def test_create_project_403s_for_management(app, client, db_session):
    # can_edit_di_board is admin-only for now ("me and my future team") —
    # unlike the Performance/cost-footer gate, management doesn't get a
    # pass here.
    user = _user(db_session, 'pd', role='management')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': 'Should not exist'})
    assert resp.status_code == 403


def test_create_project_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    admin = _user(db_session, 'pe', role='admin')
    designer = _user(db_session, 'pe2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': 'Should not exist'})

    assert resp.status_code == 403
    assert DiProject.query.filter_by(name='Should not exist').first() is None


def test_create_project_works_for_an_admin_emulating_another_admin(app, client, db_session):
    # Emulation only ever swaps in the emulated role — emulating a fellow
    # admin should behave exactly like not emulating at all.
    admin = _user(db_session, 'pf', role='admin')
    other_admin = _user(db_session, 'pf2', role='admin')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = other_admin.id

    with app.test_request_context():
        url = url_for('digital_innovation.create_project')
    resp = client.post(url, json={'name': 'Still allowed'})

    assert resp.status_code == 201
    assert DiProject.query.filter_by(name='Still allowed').first() is not None


# ── close / archive / reopen ─────────────────────────────────────────────
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project as _lifecycle_project


def test_close_project_happy_path(app, client, db_session):
    project = _lifecycle_project(db_session, 'ca')
    user = _user(db_session, 'ca', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert resp.get_json()['lifecycle'] == 'closed'
    assert project.lifecycle == 'closed'
    assert project.closed_at is not None


def test_close_project_403s_for_a_designer(app, client, db_session):
    project = _lifecycle_project(db_session, 'cb')
    user = _user(db_session, 'cb', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 403
    assert project.lifecycle == 'active'


def test_close_project_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    project = _lifecycle_project(db_session, 'cc')
    admin = _user(db_session, 'cc', role='admin')
    designer = _user(db_session, 'cc2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.close_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 403
    assert project.lifecycle == 'active'


def test_close_project_404s_for_an_unknown_project(app, client, db_session):
    user = _user(db_session, 'cd', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_project', project_id=999999)
    resp = client.post(url)
    assert resp.status_code == 404


def test_close_project_404s_for_a_project_thats_already_closed(app, client, db_session):
    project = _lifecycle_project(db_session, 'ce', lifecycle='closed')
    user = _user(db_session, 'ce', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_project', project_id=project.id)
    resp = client.post(url)
    assert resp.status_code == 404


def test_close_project_refuses_the_permanent_project(app, client, db_session):
    project = DiProject(name='OVP-like', lifecycle='active', is_permanent=True)
    db_session.add(project)
    db_session.flush()
    user = _user(db_session, 'cf', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 400
    assert project.lifecycle == 'active'


def test_archive_project_happy_path(app, client, db_session):
    project = _lifecycle_project(db_session, 'cg', lifecycle='closed')
    user = _user(db_session, 'cg', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.archive_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert resp.get_json()['lifecycle'] == 'archived'
    assert project.lifecycle == 'archived'


def test_archive_project_404s_for_an_active_project(app, client, db_session):
    # An active project has to be closed first — archiving is only
    # reachable from the Archive screen's Closed list.
    project = _lifecycle_project(db_session, 'ch')
    user = _user(db_session, 'ch', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.archive_project', project_id=project.id)
    resp = client.post(url)
    assert resp.status_code == 404


def test_archive_project_403s_for_a_designer(app, client, db_session):
    project = _lifecycle_project(db_session, 'ci', lifecycle='closed')
    user = _user(db_session, 'ci', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.archive_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 403
    assert project.lifecycle == 'closed'


def test_reopen_project_from_closed(app, client, db_session):
    project = _lifecycle_project(db_session, 'cj', lifecycle='closed')
    user = _user(db_session, 'cj', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert resp.get_json()['lifecycle'] == 'active'
    assert project.lifecycle == 'active'
    assert project.closed_at is None


def test_reopen_project_from_archived(app, client, db_session):
    project = _lifecycle_project(db_session, 'ck', lifecycle='archived')
    user = _user(db_session, 'ck', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert project.lifecycle == 'active'


def test_reopen_project_403s_for_a_designer(app, client, db_session):
    project = _lifecycle_project(db_session, 'cl', lifecycle='closed')
    user = _user(db_session, 'cl', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_project', project_id=project.id)
    resp = client.post(url)

    assert resp.status_code == 403
    assert project.lifecycle == 'closed'


def test_reopen_project_404s_for_an_already_active_project(app, client, db_session):
    project = _lifecycle_project(db_session, 'cm')
    user = _user(db_session, 'cm', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_project', project_id=project.id)
    resp = client.post(url)
    assert resp.status_code == 404


# ── system-project link ────────────────────────────────────────────────

def test_search_projects_requires_auth(app, client, db_session):
    with app.test_request_context():
        url = url_for('digital_innovation.search_projects', q='shared')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_search_projects_happy_path(app, client, db_session):
    _shared_project(db_session, 'sa', client='Acme')
    _shared_project(db_session, 'sb', client='Zenith')
    user = _user(db_session, 'sa', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.search_projects', q='Acme')
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 1
    assert body[0]['client'] == 'Acme'


def test_search_projects_requires_at_least_two_characters(app, client, db_session):
    _shared_project(db_session, 'sc')
    user = _user(db_session, 'sb', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.search_projects', q='s')
    resp = client.get(url)

    assert resp.status_code == 200
    assert resp.get_json() == []


def test_search_projects_403s_for_a_designer(app, client, db_session):
    user = _user(db_session, 'sc', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.search_projects', q='shared')
    resp = client.get(url)
    assert resp.status_code == 403


def test_link_project_happy_path(app, client, db_session):
    di_project = _lifecycle_project(db_session, 'la')
    target = _shared_project(db_session, 'la')
    user = _user(db_session, 'la', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.link_project', project_id=di_project.id)
    resp = client.patch(url, json={'linked_project_id': target.id})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['linked_project_id'] == target.id
    assert body['linked_project_name'] == target.name
    assert di_project.linked_project_id == target.id


def test_link_project_can_clear_an_existing_link(app, client, db_session):
    di_project = _lifecycle_project(db_session, 'lb')
    target = _shared_project(db_session, 'lb')
    di_project.linked_project_id = target.id
    db_session.flush()
    user = _user(db_session, 'lb', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.link_project', project_id=di_project.id)
    resp = client.patch(url, json={'linked_project_id': None})

    assert resp.status_code == 200
    assert resp.get_json()['linked_project_id'] is None
    assert di_project.linked_project_id is None


def test_link_project_400s_for_an_unknown_target_project(app, client, db_session):
    di_project = _lifecycle_project(db_session, 'lc')
    user = _user(db_session, 'lc', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.link_project', project_id=di_project.id)
    resp = client.patch(url, json={'linked_project_id': 999999})

    assert resp.status_code == 400
    assert di_project.linked_project_id is None


def test_link_project_400s_for_the_permanent_project(app, client, db_session):
    project = DiProject(name='OVP-like', lifecycle='active', is_permanent=True)
    db_session.add(project)
    db_session.flush()
    target = _shared_project(db_session, 'ld')
    user = _user(db_session, 'ld', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.link_project', project_id=project.id)
    resp = client.patch(url, json={'linked_project_id': target.id})

    assert resp.status_code == 400
    assert project.linked_project_id is None


def test_link_project_403s_for_a_designer(app, client, db_session):
    di_project = _lifecycle_project(db_session, 'le')
    target = _shared_project(db_session, 'le')
    user = _user(db_session, 'le', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.link_project', project_id=di_project.id)
    resp = client.patch(url, json={'linked_project_id': target.id})

    assert resp.status_code == 403
    assert di_project.linked_project_id is None


def test_link_project_404s_for_an_unknown_di_project(app, client, db_session):
    user = _user(db_session, 'lf', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.link_project', project_id=999999)
    resp = client.patch(url, json={'linked_project_id': None})
    assert resp.status_code == 404
