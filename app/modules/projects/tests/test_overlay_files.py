"""Coverage for project_overlay/files.py."""
import io
import os
from flask import url_for

from app.modules.core.shared.models import Project, ProjectFile, User
from app.modules.core.shared.services import nas as nas_module
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


def _make_project(db_session, cs_lead):
    project = Project(name='Preview Cache Test', cs_lead_id=cs_lead.id, created_by_id=cs_lead.id)
    db_session.add(project)
    db_session.flush()
    return project


def _make_project_file(db_session, project, uploader, file_type, original_filename):
    pf = ProjectFile(project_id=project.id, filename=original_filename,
                      original_filename=original_filename, file_type=file_type,
                      uploaded_by_id=uploader.id)
    db_session.add(pf)
    db_session.flush()
    return pf


def _make_cs_user(db_session, email):
    user = User(name='CS', email=email, role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_upload_rejects_disallowed_extension(app, client, db_session):
    user = _make_cs_user(db_session, 'files-test-b@example.com')
    login_as(client, app, user, 'password123')
    project = _make_project(db_session, user)

    resp = client.post(f'/projects/{project.id}/upload-file',
                        data={'file': (io.BytesIO(b'x'), 'notes.exe')})
    assert resp.status_code == 400


def test_upload_accepts_audio_extension(app, client, db_session, monkeypatch):
    monkeypatch.setattr(nas_module, 'upload_app_file', lambda data, folder, name: None)
    user = _make_cs_user(db_session, 'files-test-c@example.com')
    login_as(client, app, user, 'password123')
    project = _make_project(db_session, user)

    resp = client.post(f'/projects/{project.id}/upload-file',
                        data={'file': (io.BytesIO(b'fake mp3 bytes'), 'voiceover.mp3')})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_preview_serves_video_and_caches_locally(app, client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(nas_module, 'download_app_file', lambda path: calls.append(path) or b'fake video bytes')

    user = _make_cs_user(db_session, 'files-test-d@example.com')
    login_as(client, app, user, 'password123')
    project = _make_project(db_session, user)
    pf = _make_project_file(db_session, project, user, 'mp4', 'clip.mp4')

    resp = client.get(f'/projects/files/{pf.id}/preview', buffered=True)
    assert resp.status_code == 200
    assert resp.mimetype == 'video/mp4'
    assert len(calls) == 1

    cache_path = os.path.join(app.config['UPLOAD_FOLDER'], 'preview-cache', f'{pf.id}.mp4')
    assert os.path.exists(cache_path)

    resp2 = client.get(f'/projects/files/{pf.id}/preview', buffered=True)
    assert resp2.status_code == 200
    assert len(calls) == 1  # second preview served from cache, not NAS again

    os.remove(cache_path)


def test_preview_serves_audio(app, client, db_session, monkeypatch):
    monkeypatch.setattr(nas_module, 'download_app_file', lambda path: b'fake audio bytes')

    user = _make_cs_user(db_session, 'files-test-e@example.com')
    login_as(client, app, user, 'password123')
    project = _make_project(db_session, user)
    pf = _make_project_file(db_session, project, user, 'mp3', 'voiceover.mp3')

    resp = client.get(f'/projects/files/{pf.id}/preview', buffered=True)
    assert resp.status_code == 200
    assert resp.mimetype == 'audio/mpeg'

    cache_path = os.path.join(app.config['UPLOAD_FOLDER'], 'preview-cache', f'{pf.id}.mp3')
    if os.path.exists(cache_path):
        os.remove(cache_path)


def test_preview_non_web_playable_video_stays_download_only(app, client, db_session):
    user = _make_cs_user(db_session, 'files-test-f@example.com')
    login_as(client, app, user, 'password123')
    project = _make_project(db_session, user)
    pf = _make_project_file(db_session, project, user, 'mkv', 'raw_cut.mkv')

    resp = client.get(f'/projects/files/{pf.id}/preview')
    assert resp.status_code == 415
