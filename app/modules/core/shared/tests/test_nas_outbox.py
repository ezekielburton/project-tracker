"""nas_outbox: queue on NAS failure, serve while queued, flush, discard."""
import os
import pytest

from app.modules.core.shared.models import PendingNasUpload
from app.modules.core.shared.services import nas, nas_outbox

PATH = '/Projects/2026/Acme/Job/Reference Files/brief.pdf'
FOLDER, NAME = PATH.rsplit('/', 1)


def _nas_down(*a, **kw):
    raise RuntimeError('NAS unreachable')


@pytest.fixture()
def outbox(app, db_session, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'UPLOAD_FOLDER', str(tmp_path))
    # Never touch the real NAS: logins fail fast.
    monkeypatch.setattr(nas, '_get_session', _nas_down)
    return tmp_path


def test_queues_and_serves_when_nas_down(outbox, monkeypatch):
    monkeypatch.setattr(nas, 'upload_app_file', _nas_down)
    assert nas_outbox.upload_or_queue(b'pdf bytes', FOLDER, NAME) is False

    row = PendingNasUpload.query.filter_by(nas_path=PATH).one()
    assert os.path.isfile(os.path.join(outbox, 'nas-outbox', row.local_name))
    assert nas.download_app_file(PATH) == b'pdf bytes'


def test_flush_sends_and_cleans_up(outbox, monkeypatch):
    monkeypatch.setattr(nas, 'upload_app_file', _nas_down)
    nas_outbox.upload_or_queue(b'pdf bytes', FOLDER, NAME)
    local = os.path.join(outbox, 'nas-outbox', PendingNasUpload.query.one().local_name)

    sent_calls = []
    monkeypatch.setattr(nas, 'is_reachable', lambda: True)
    monkeypatch.setattr(nas, 'upload_app_file',
                        lambda data, folder, name, **kw: sent_calls.append((data, folder, name)))
    assert nas_outbox.flush() == (1, 0)
    assert sent_calls == [(b'pdf bytes', FOLDER, NAME)]
    assert not os.path.exists(local)
    assert PendingNasUpload.query.count() == 0


def test_flush_waits_while_nas_down(outbox, monkeypatch):
    monkeypatch.setattr(nas, 'upload_app_file', _nas_down)
    nas_outbox.upload_or_queue(b'pdf bytes', FOLDER, NAME)
    monkeypatch.setattr(nas, 'is_reachable', lambda: False)
    assert nas_outbox.flush() == (0, 1)


def test_delete_drops_queued_copy(outbox, monkeypatch):
    monkeypatch.setattr(nas, 'upload_app_file', _nas_down)
    nas_outbox.upload_or_queue(b'pdf bytes', FOLDER, NAME)
    nas.delete_app_file(PATH)
    assert PendingNasUpload.query.count() == 0


def test_direct_upload_drops_older_queued_copy(outbox, monkeypatch):
    monkeypatch.setattr(nas, 'upload_app_file', _nas_down)
    nas_outbox.upload_or_queue(b'old', FOLDER, NAME)
    monkeypatch.setattr(nas, 'upload_app_file', lambda *a, **kw: None)
    assert nas_outbox.upload_or_queue(b'new', FOLDER, NAME) is True
    assert PendingNasUpload.query.count() == 0
