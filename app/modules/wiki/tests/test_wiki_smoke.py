"""Smoke tests for the wiki module, using the shared fixtures."""
from flask import url_for
import os


def test_wiki_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('wiki.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_wiki_templates_resolve(app):
    for name in ('wiki/index.html', 'wiki/editor_dashboard.html'):
        assert app.jinja_env.get_template(name) is not None 

import io
from app.modules.core.shared.testing import login_as
from app.modules.core.shared.models import User
from app.modules.core.shared.services import nas as nas_module
from app.modules.wiki.routes import wiki as wiki_module


def _make_user(db_session, email, role='designer', password='pw123456'):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password(password)
    db_session.add(user)
    db_session.commit()
    return user, password


def test_upload_video_requires_admin(app, client, db_session):
    user, pw = _make_user(db_session, 'notadmin@example.com')
    login_as(client, app, user, pw)
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'x'), 'clip.mp4')})
    assert resp.status_code == 403


def test_upload_video_rejects_bad_extension(app, client, db_session):
    admin, pw = _make_user(db_session, 'admin1@example.com', role='admin')
    login_as(client, app, admin, pw)
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'x'), 'notes.txt')})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_upload_video_enforces_size_cap(app, client, db_session, monkeypatch):
    monkeypatch.setattr(wiki_module, '_VIDEO_MAX_BYTES', 10)
    admin, pw = _make_user(db_session, 'admin2@example.com', role='admin')
    login_as(client, app, admin, pw)
    before = _saved_videos(app)
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'0123456789ABCDEF'), 'clip.mp4')})
    assert resp.status_code == 400
    assert 'too large' in resp.get_json()['error']
    assert _saved_videos(app) == before


def _saved_videos(app):
    folder = os.path.join(app.root_path, 'static', 'wiki-uploads', 'videos')
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


def test_upload_video_refuses_oversize_request_before_reading_it(app, client, db_session, monkeypatch):
    """A Content-Length over the cap is refused before the multipart body is parsed."""
    from flask import Request
    parsed = []
    original = Request._load_form_data
    monkeypatch.setattr(Request, '_load_form_data', lambda self: (parsed.append(1), original(self))[1])
    monkeypatch.setattr(wiki_module, '_VIDEO_MAX_BYTES', 10)
    monkeypatch.setattr(wiki_module, '_VIDEO_FORM_SLACK', 0, raising=False)
    admin, pw = _make_user(db_session, 'admin5@example.com', role='admin')
    login_as(client, app, admin, pw)
    parsed.clear()

    before = _saved_videos(app)
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'x' * 64), 'clip.mp4')})

    assert resp.status_code == 400
    assert 'too large' in resp.get_json()['error']
    assert parsed == []
    assert _saved_videos(app) == before


def test_upload_video_at_the_cap_is_accepted(app, client, db_session, monkeypatch):
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: None)
    monkeypatch.setattr(wiki_module, '_VIDEO_MAX_BYTES', 16)
    admin, pw = _make_user(db_session, 'admin6@example.com', role='admin')
    login_as(client, app, admin, pw)

    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'0123456789ABCDEF'), 'clip.mp4')})

    assert resp.status_code == 200
    saved_path = os.path.join(app.root_path, 'static', 'wiki-uploads', 'videos', resp.get_json()['filename'])
    with open(saved_path, 'rb') as saved:
        assert saved.read() == b'0123456789ABCDEF'
    os.remove(saved_path)


def test_upload_video_accepts_mp4_and_backs_up_to_nas(app, client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(nas_module, 'upload_app_file', lambda data, folder, name: calls.append((folder, name)))
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: fn())

    admin, pw = _make_user(db_session, 'admin3@example.com', role='admin')
    login_as(client, app, admin, pw)
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'fake mp4 bytes'), 'clip.mp4')})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['url'].endswith('.mp4')
    assert calls and calls[0][0] == '/Admin/OVP/Wiki'

    saved_path = os.path.join(app.root_path, 'static', 'wiki-uploads', 'videos', data['filename'])
    assert os.path.exists(saved_path)
    os.remove(saved_path)


def test_upload_video_nas_failure_does_not_fail_upload(app, client, db_session, monkeypatch):
    def _boom(data, folder, name):
        raise RuntimeError('NAS unreachable')
    monkeypatch.setattr(nas_module, 'upload_app_file', _boom)
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: fn())

    admin, pw = _make_user(db_session, 'admin4@example.com', role='admin')
    login_as(client, app, admin, pw)
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'fake mp4 bytes'), 'clip.mp4')})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True

    saved_path = os.path.join(app.root_path, 'static', 'wiki-uploads', 'videos', data['filename'])
    assert os.path.exists(saved_path)
    os.remove(saved_path)
