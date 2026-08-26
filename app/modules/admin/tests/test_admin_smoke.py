"""Smoke tests for the admin module, using the shared fixtures."""


def test_admin_api_requires_auth(app, client):
    resp = client.get('/admin/api/users')
    assert resp.status_code in (302, 401, 403)
