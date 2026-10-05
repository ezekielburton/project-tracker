"""Cleaning up wiki uploads that no article uses."""
import os
import time

import pytest

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.services import nas as nas_module
from app.modules.core.shared.testing import login_as
from app.modules.wiki.lib.uploads import GRACE_SECONDS, delete_unused, unused_uploads


@pytest.fixture()
def root(tmp_path, app, monkeypatch):
    monkeypatch.setitem(app.config, 'WIKI_UPLOAD_ROOT', str(tmp_path))
    (tmp_path / 'videos').mkdir()
    return tmp_path


def _file(root, relative, age_seconds=2 * GRACE_SECONDS):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x' * 10)
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
    return path


def _article(db_session, **content):
    section = WikiSection(title='Uploads', slug='uploads-section', is_published=True)
    db_session.add(section)
    db_session.commit()
    db_session.add(WikiArticle(section_id=section.id, title='Uses files', slug='uses-files', **content))
    db_session.commit()


def test_files_named_in_live_draft_or_legacy_content_are_kept(root, db_session):
    _file(root, 'live.png')
    _file(root, 'videos/draft.mp4')
    _file(root, 'legacy.png')
    _file(root, 'videos/orphan.mp4')
    _article(db_session,
             sections_json='{"url": "/static/wiki-uploads/live.png"}',
             draft_sections_json='{"url": "/static/wiki-uploads/videos/draft.mp4"}',
             legacy_sections_json='[{"url": "/static/wiki-uploads/legacy.png"}]')

    assert [upload.name for upload in unused_uploads()] == ['orphan.mp4']


def test_a_fresh_upload_is_kept_through_the_grace_period(root, db_session):
    _file(root, 'videos/new.mp4', age_seconds=60)
    assert unused_uploads() == []


def test_only_the_two_upload_folders_are_looked_at(root, db_session):
    _file(root, 'videos/deeper/old.mp4')
    _file(root, 'other/old.png')
    assert unused_uploads() == []


def test_clean_up_deletes_local_files_and_their_nas_backups(root, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(nas_module, 'delete_app_file', lambda path: calls.append(path))
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: fn())
    image = _file(root, 'old.png')
    video = _file(root, 'videos/old.mp4')

    assert delete_unused() == 2
    assert not image.exists() and not video.exists()
    assert calls == ['/Admin/OVP/Wiki/old.mp4']


def test_a_nas_failure_does_not_stop_the_clean_up(root, db_session, monkeypatch):
    def _boom(path):
        raise RuntimeError('NAS unreachable')
    monkeypatch.setattr(nas_module, 'delete_app_file', _boom)
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: fn())
    video = _file(root, 'videos/old.mp4')

    assert delete_unused() == 1
    assert not video.exists()


def test_the_dashboard_offers_clean_up_only_when_there_is_something(app, root, db_session):
    admin = User(name='Admin', email='uploads-admin@example.com', role='admin')
    admin.set_password('pw123456')
    db_session.add(admin)
    db_session.commit()
    client = app.test_client()
    login_as(client, app, admin, 'pw123456')

    assert 'wiki-uploads-clean' not in client.get('/wiki/editor').get_data(as_text=True)
    _file(root, 'videos/old.mp4')
    assert 'Unused uploads: 1 file' in client.get('/wiki/editor').get_data(as_text=True)
