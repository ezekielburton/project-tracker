"""Coverage for project_overlay/files.py."""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


def test_generate_job_number_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.generate_job_number')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_generate_job_number_happy_path(app, client, db_session):
    user = User(name='CS Lead', email='files-test-a@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('project_overlay.generate_job_number')
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.get_json()['job_number'].startswith('FOC-')
