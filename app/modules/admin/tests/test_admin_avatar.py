"""Admin can set/replace any user's avatar via /admin/api/users/<id>/avatar."""
import io
import os
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as

FOLDER_ATTR = 'app.modules.admin.routes.admin.AVATAR_FOLDER'


def _make_user(db_session, email, role='designer', password='pw123456', is_active=True):
    u = User(name=email.split('@')[0], email=email, role=role, is_active=is_active)
    u.set_password(password)
    db_session.add(u)
    db_session.commit()
    return u, password


def _png():
    return (io.BytesIO(b'\x89PNG\r\n\x1a\nfake'), 'photo.png')


def _post_avatar(client, user_id, file_tuple=None):
    return client.post(
        f'/admin/api/users/{user_id}/avatar',
        data={'file': file_tuple or _png()},
        content_type='multipart/form-data',
    )


def test_avatar_route_is_admin_only(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, str(tmp_path))
    plain, pw = _make_user(db_session, 'plain-av@example.com')
    target, _ = _make_user(db_session, 'target-av@example.com')
    login_as(client, app, plain, pw)
    resp = _post_avatar(client, target.id)
    assert resp.status_code == 403
    assert User.query.get(target.id).avatar_filename is None


def test_admin_can_set_avatar(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, str(tmp_path))
    admin, apw = _make_user(db_session, 'admin-av@example.com', role='admin')
    target, _ = _make_user(db_session, 'target-av2@example.com')
    login_as(client, app, admin, apw)
    resp = _post_avatar(client, target.id)
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    refreshed = User.query.get(target.id)
    assert refreshed.avatar_filename
    assert refreshed.avatar_step_completed is True
    assert os.path.exists(os.path.join(str(tmp_path), refreshed.avatar_filename))


def test_replace_deletes_old_file(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, str(tmp_path))
    admin, apw = _make_user(db_session, 'admin-av3@example.com', role='admin')
    target, _ = _make_user(db_session, 'target-av3@example.com')
    old_path = os.path.join(str(tmp_path), 'old123.png')
    with open(old_path, 'wb') as f:
        f.write(b'old')
    target.avatar_filename = 'old123.png'
    db_session.commit()
    login_as(client, app, admin, apw)
    resp = _post_avatar(client, target.id)
    assert resp.status_code == 200
    new_name = User.query.get(target.id).avatar_filename
    assert new_name != 'old123.png'
    assert not os.path.exists(old_path)
    assert os.path.exists(os.path.join(str(tmp_path), new_name))


def test_admin_can_set_avatar_for_deactivated_user(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, str(tmp_path))
    admin, apw = _make_user(db_session, 'admin-av5@example.com', role='admin')
    target, _ = _make_user(db_session, 'target-av5@example.com', is_active=False)
    login_as(client, app, admin, apw)
    resp = _post_avatar(client, target.id)
    assert resp.status_code == 200
    assert User.query.get(target.id).avatar_filename


def test_rejects_non_image(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, str(tmp_path))
    admin, apw = _make_user(db_session, 'admin-av4@example.com', role='admin')
    target, _ = _make_user(db_session, 'target-av4@example.com')
    login_as(client, app, admin, apw)
    resp = _post_avatar(client, target.id, file_tuple=(io.BytesIO(b'nope'), 'evil.txt'))
    assert resp.status_code == 400
    assert User.query.get(target.id).avatar_filename is None
