"""Smoke tests for the blog module, using the shared fixtures."""
import io
import json
import os
from types import SimpleNamespace

from flask import url_for

from app.modules.core.shared.models import BlogPost, User
from app.modules.core.shared.services import nas as nas_module
from app.modules.core.shared.testing import login_as
from app.modules.blog.routes.blog import _backup_post_media_to_nas
import app.modules.blog.routes.blog as blog_module


def test_blog_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('blog.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_blog_templates_resolve(app):
    for name in ('blog/index.html', 'blog/editor.html', 'blog/v12_update.html'):
        assert app.jinja_env.get_template(name) is not None


def _make_admin(db_session, email):
    user = User(name='Admin', email=email, role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_upload_media_rejects_bad_extension(app, client, db_session):
    admin = _make_admin(db_session, 'blog-test-a@example.com')
    login_as(client, app, admin, 'password123')

    resp = client.post('/blog/upload-media', data={'file': (io.BytesIO(b'x'), 'notes.txt')})
    assert resp.status_code == 400


def test_upload_media_enforces_size_cap(app, client, db_session, monkeypatch):
    monkeypatch.setattr(blog_module, '_MEDIA_MAX_BYTES', 10)
    admin = _make_admin(db_session, 'blog-test-b@example.com')
    login_as(client, app, admin, 'password123')

    resp = client.post('/blog/upload-media', data={'file': (io.BytesIO(b'0123456789ABCDEF'), 'pic.png')})
    assert resp.status_code == 400
    assert 'too large' in resp.get_json()['error']


def test_upload_media_accepts_image_and_video(app, client, db_session):
    admin = _make_admin(db_session, 'blog-test-c@example.com')
    login_as(client, app, admin, 'password123')

    resp = client.post('/blog/upload-media', data={'file': (io.BytesIO(b'fake png bytes'), 'photo.png')})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['kind'] == 'image'
    path = os.path.join(app.root_path, 'static', 'blog-uploads', data['filename'])
    assert os.path.exists(path)
    os.remove(path)

    resp2 = client.post('/blog/upload-media', data={'file': (io.BytesIO(b'fake mp4 bytes'), 'clip.mp4')})
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2['kind'] == 'video'
    path2 = os.path.join(app.root_path, 'static', 'blog-uploads', data2['filename'])
    assert os.path.exists(path2)
    os.remove(path2)


def test_backup_post_media_uploads_referenced_files(app, db_session, monkeypatch):
    admin = _make_admin(db_session, 'blog-test-d@example.com')

    upload_dir = os.path.join(app.root_path, 'static', 'blog-uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = 'backup-test.png'
    local_path = os.path.join(upload_dir, filename)
    with open(local_path, 'wb') as f:
        f.write(b'fake png bytes')

    sections = [{'blocks': [{'type': 'image', 'url': f'/static/blog-uploads/{filename}', 'text': ''}]}]
    post = BlogPost(title='Media Backup Test', author_id=admin.id, sections_json=json.dumps(sections))
    db_session.add(post)
    db_session.flush()

    calls = []
    monkeypatch.setattr(nas_module, 'upload_app_file', lambda data, folder, name: calls.append((folder, name)))

    _backup_post_media_to_nas(app, post.id)

    assert len(calls) == 1
    assert calls[0][0] == f'/Admin/OVP/blog/{post.id}-media-backup-test'
    assert calls[0][1] == filename

    os.remove(local_path)


def test_backup_post_media_tolerates_nas_failure(app, db_session, monkeypatch):
    admin = _make_admin(db_session, 'blog-test-e@example.com')

    upload_dir = os.path.join(app.root_path, 'static', 'blog-uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = 'backup-test-2.png'
    local_path = os.path.join(upload_dir, filename)
    with open(local_path, 'wb') as f:
        f.write(b'fake png bytes')

    sections = [{'blocks': [{'type': 'image', 'url': f'/static/blog-uploads/{filename}', 'text': ''}]}]
    post = BlogPost(title='Media Backup Failure Test', author_id=admin.id, sections_json=json.dumps(sections))
    db_session.add(post)
    db_session.flush()

    def _boom(data, folder, name):
        raise RuntimeError('NAS unreachable')
    monkeypatch.setattr(nas_module, 'upload_app_file', _boom)

    _backup_post_media_to_nas(app, post.id)  # must not raise

    os.remove(local_path)


def test_image_and_video_blocks_render(app):
    post = SimpleNamespace(title='T', version_tag='', author=SimpleNamespace(name='A'),
                            published_at=None, is_published=True, id=1)
    sections = [SimpleNamespace(
        anchor='s1', number='01', title='Section',
        blocks=[
            SimpleNamespace(type='image', url='/static/blog-uploads/x.png', text='A caption', items=[]),
            SimpleNamespace(type='video', url='/static/blog-uploads/x.mp4', text='', items=[]),
        ]
    )]
    post.sections = lambda: sections

    html = app.jinja_env.get_template('blog/_post_content.html').render(
        post=post, comments=[], actor=SimpleNamespace(role='designer')
    )
    assert '<img src="/static/blog-uploads/x.png"' in html
    assert '<video src="/static/blog-uploads/x.mp4"' in html
