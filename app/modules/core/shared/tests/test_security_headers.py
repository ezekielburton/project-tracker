"""The session cookie stays SameSite=Lax and HttpOnly."""


def test_session_cookie_is_hardened(app):
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
