"""Admin user tools: password reset, delete-user error naming, activity date
filters, and the deliverable-type template upload."""
import io

from app.modules.core.shared.lib.champions import week_start_for
from app.modules.core.shared.models import OvpChampion, User
from app.modules.core.shared.testing import login_as


def _user(db_session, email, role='designer', password='password123'):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password(password)
    db_session.add(user)
    db_session.commit()
    return user, password


def test_reset_returns_a_new_random_password_each_time(app, client, db_session):
    admin, admin_pw = _user(db_session, 'reset-admin@example.com', role='admin')
    target, _ = _user(db_session, 'reset-target@example.com')
    login_as(client, app, admin, admin_pw)

    first = client.post(f'/admin/api/users/{target.id}/reset-password').get_json()
    second = client.post(f'/admin/api/users/{target.id}/reset-password').get_json()
    assert first['success'] and second['success']
    assert first['temp_password'] != second['temp_password']
    assert 'Vitamin2026!' not in (first['temp_password'], second['temp_password'])

    # The target can log in with the password shown last.
    client.get('/logout')
    login_as(client, app, target, second['temp_password'])
    assert client.get('/account').status_code == 200


def test_delete_user_names_ovp_champions_as_the_blocker(app, client, db_session):
    admin, admin_pw = _user(db_session, 'del-admin@example.com', role='admin')
    target, _ = _user(db_session, 'del-champ@example.com')
    db_session.add(OvpChampion(user_id=target.id, department='design',
                               week_start=week_start_for(), set_by_id=admin.id))
    db_session.commit()
    login_as(client, app, admin, admin_pw)

    resp = client.delete(f'/admin/api/users/{target.id}')
    assert resp.status_code == 400
    error = resp.get_json()['error']
    assert 'ovp champions' in error
    assert 'unknown table' not in error


def test_activity_rejects_a_malformed_date(app, client, db_session):
    admin, admin_pw = _user(db_session, 'activity-admin@example.com', role='admin')
    login_as(client, app, admin, admin_pw)

    for query in ('from=not-a-date', 'to=2026-13-40', 'from=2026-09-01&to=garbage'):
        resp = client.get(f'/admin/api/activity?{query}')
        assert resp.status_code == 400, query
        assert resp.get_json()['success'] is False

    assert client.get('/admin/api/activity?from=2026-09-01&to=2026-09-30').status_code == 200


def test_template_upload_accepts_only_ai(app, client, db_session, tmp_path, monkeypatch):
    import app.modules.core.shared.lib.paths as paths
    monkeypatch.setattr(paths, 'template_upload_folder', lambda: str(tmp_path))
    admin, admin_pw = _user(db_session, 'template-admin@example.com', role='admin')
    login_as(client, app, admin, admin_pw)
    url = '/admin/api/deliverable-types/upload-template'

    resp = client.post(url, data={'file': (io.BytesIO(b'PK'), 'bundle.zip')},
                       content_type='multipart/form-data')
    assert resp.status_code == 400
    assert '.ai' in resp.get_json()['error']

    resp = client.post(url, data={'file': (io.BytesIO(b'%PDF'), 'shelf.ai')},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.get_json()['filename'].endswith('.ai')
