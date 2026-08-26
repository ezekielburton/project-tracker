"""Smoke tests for the achievements module and its shared checker service."""


def test_checker_importable_from_shared():
    from app.modules.core.shared.services.achievements import check_achievements
    assert callable(check_achievements)


def test_admin_api_requires_auth(app, client):
    resp = client.get('/admin/api/achievement-categories')
    assert resp.status_code in (302, 401)
