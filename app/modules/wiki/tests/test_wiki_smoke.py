"""Smoke tests for the wiki module, using the shared fixtures."""
from flask import url_for
import os
from datetime import datetime, timezone
from types import SimpleNamespace


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
    resp = client.post('/wiki/upload-video', data={'file': (io.BytesIO(b'0123456789ABCDEF'), 'clip.mp4')})
    assert resp.status_code == 400
    assert 'too large' in resp.get_json()['error']


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

def test_video_block_renders_video_tag_for_uploads(app):
    article = SimpleNamespace(title='T', updated_at=datetime.now(timezone.utc))
    blocks = [{'type': 'video', 'source': 'upload', 'url': '/static/wiki-uploads/videos/x.mp4'}]
    html = app.jinja_env.get_template('wiki/_article_content.html').render(article=article, blocks=blocks)
    assert '<video' in html
    assert '<iframe' not in html


def test_video_block_renders_iframe_for_embeds(app):
    article = SimpleNamespace(title='T', updated_at=datetime.now(timezone.utc))
    blocks = [{'type': 'video', 'content': 'https://www.youtube.com/watch?v=abc123'}]
    html = app.jinja_env.get_template('wiki/_article_content.html').render(article=article, blocks=blocks)
    assert '<iframe' in html
    assert '<video' not in html