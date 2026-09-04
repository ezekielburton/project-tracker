"""Smoke tests for the profile module, using the shared fixtures."""
from flask import url_for


def test_profile_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('profile.view')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_profile_template_resolves(app):
    # The renamed template must resolve through the module's template_folder.
    assert app.jinja_env.get_template('profile/profile.html') is not None

def test_avatar_self_upload_still_works(app, client, db_session, monkeypatch, tmp_path):
    # Self-service avatar upload must behave exactly as before the shared-helper move.
    import io
    from app.modules.core.shared.models import User
    from app.modules.core.shared.testing import login_as
    monkeypatch.setattr('app.modules.profile.routes.profile.AVATAR_FOLDER', str(tmp_path))
    u = User(name='selfie', email='selfie@example.com', role='designer')
    u.set_password('pw123456')
    db_session.add(u)
    db_session.commit()
    login_as(client, app, u, 'pw123456')
    resp = client.post(
        '/profile/avatar',
        data={'file': (io.BytesIO(b'\x89PNG\r\n\x1a\nfake'), 'me.png')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert User.query.get(u.id).avatar_filename
