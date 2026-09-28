"""Smoke tests for the profile module, using the shared fixtures."""
from flask import url_for


def test_profile_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('profile.view')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_profile_template_resolves(app):
    # Must resolve through the module's template_folder.
    assert app.jinja_env.get_template('profile/profile.html') is not None

def test_avatar_self_upload_still_works(app, client, db_session, monkeypatch, tmp_path):
    # Self-service avatar upload saves the file and sets avatar_filename.
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


def _profile_user(db_session, email, role='designer'):
    from app.modules.core.shared.models import User
    u = User(name=email.split('@')[0], email=email, role=role)
    u.set_password('pw123456')
    db_session.add(u)
    db_session.commit()
    return u


def test_own_profile_shows_edit_controls(app, client, db_session):
    from app.modules.core.shared.testing import login_as
    u = _profile_user(db_session, 'own-prof@example.com')
    login_as(client, app, u, 'pw123456')
    html = client.get('/profile').get_data(as_text=True)
    assert 'id="edit-avatar-btn"' in html
    assert 'id="edit-achievements-btn"' in html


def test_emulated_profile_hides_edit_controls(app, client, db_session):
    # Edit routes write to current_user, so an admin viewing as someone else
    # must not get controls that would edit the admin's own profile.
    from app.modules.core.shared.testing import login_as
    admin = _profile_user(db_session, 'emu-admin-prof@example.com', role='admin')
    target = _profile_user(db_session, 'emu-target-prof@example.com')
    login_as(client, app, admin, 'pw123456')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target.id
    resp = client.get('/profile')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert target.name in html
    for control in ('edit-avatar-btn', 'edit-banner-btn', 'edit-details-btn',
                    'edit-bio-btn', 'edit-achievements-btn'):
        assert f'id="{control}"' not in html
    assert 'window.PROFILE_CUSTOMIZE' not in html
