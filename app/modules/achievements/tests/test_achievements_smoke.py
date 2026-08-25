"""Smoke tests for the achievements module and its shared checker service."""


def test_checker_importable_from_shared_and_shim():
    # The service now lives in core/shared; the old flat path re-exports it.
    from app.modules.core.shared.services.achievements import check_achievements as svc
    from app.achievements import check_achievements as shim
    assert svc is shim


def test_admin_api_requires_auth(app, client):
    resp = client.get('/admin/api/achievement-categories')
    assert resp.status_code in (302, 401)
