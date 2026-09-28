"""nas.py resolve_drive_file_id: the Drive walk against a fake NAS HTTP
session, checking the SynologyDrive sid is logged out afterwards."""
import pytest
import requests

from app.modules.core.shared.services import nas


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeNasSession:
    """Answers auth.cgi login/logout and the two Drive list calls."""

    def __init__(self, fail_logout=False):
        self.calls = []
        self.fail_logout = fail_logout

    def get(self, url, params=None, **kwargs):
        self.calls.append(params)
        if params.get('method') == 'login':
            return _FakeResponse({'success': True, 'data': {'sid': 'drive-sid'}})
        if params.get('method') == 'logout':
            if self.fail_logout:
                raise requests.exceptions.ConnectionError('NAS went away')
            return _FakeResponse({'success': True})
        if params.get('api') == 'SYNO.SynologyDrive.TeamFolders':
            return _FakeResponse({'success': True, 'data': {'items': [{'name': 'Projects', 'file_id': 'root-1'}]}})
        if params.get('api') == 'SYNO.SynologyDrive.Files':
            return _FakeResponse({'success': True, 'data': {'items': [{'name': '2026', 'file_id': 'year-2'}]}})
        raise AssertionError(f'unexpected NAS call: {params}')

    def logouts(self):
        return [c for c in self.calls if c.get('method') == 'logout']


@pytest.fixture()
def fake_nas(app, monkeypatch):
    monkeypatch.setattr(nas, '_NAS_HOST_OVERRIDE', ('nas.local', 5001))
    with app.app_context():
        yield monkeypatch


def test_resolve_drive_file_id_logs_out_the_drive_session(fake_nas):
    session = _FakeNasSession()
    fake_nas.setattr(nas, '_NAS_SESSION', session)

    assert nas.resolve_drive_file_id('/Projects/2026') == 'year-2'

    logouts = session.logouts()
    assert len(logouts) == 1
    assert logouts[0]['session'] == 'SynologyDrive'
    assert logouts[0]['_sid'] == 'drive-sid'


def test_resolve_drive_file_id_logs_out_when_a_segment_is_missing(fake_nas):
    session = _FakeNasSession()
    fake_nas.setattr(nas, '_NAS_SESSION', session)

    assert nas.resolve_drive_file_id('/Nope') is None
    assert [c['session'] for c in session.logouts()] == ['SynologyDrive']


def test_resolve_drive_file_id_survives_a_failed_logout(fake_nas):
    session = _FakeNasSession(fail_logout=True)
    fake_nas.setattr(nas, '_NAS_SESSION', session)

    assert nas.resolve_drive_file_id('/Projects') == 'root-1'
