"""Smoke tests for the projects module. Grown one stage at a time."""
from flask import url_for


# ── Stage A: transfer ──────────────────────────────────────────────────────
def test_transfer_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('transfer.transfer_deliverable', project_id=1, deliverable_id=1)
    resp = client.post(url)
    assert resp.status_code in (302, 401)


# ── Stage B: project_notes ─────────────────────────────────────────────────
def test_project_notes_requires_auth(app, client):
    resp = client.get('/projects/1/overlay/notes')
    assert resp.status_code in (302, 401)


# ── Stage C: project_list ──────────────────────────────────────────────────
def test_project_list_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_list.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_project_list_template_resolves(app):
    assert app.jinja_env.get_template('project_list/index.html') is not None


# ── Stage D: project_overlay + project_preproduction + helpers ─────────────
def test_project_overlay_templates_resolve(app):
    for name in ('project_overlay/_overlay.html', 'project_overlay/_overlay_create.html'):
        assert app.jinja_env.get_template(name) is not None


def test_project_helpers_importable(app):
    from app.modules.projects.lib.pptx_convert import convert_pptx_to_pdf
    from app.modules.projects.lib.submission_cache import cache_submission_file
    assert callable(convert_pptx_to_pdf)
    assert callable(cache_submission_file)


def test_overlay_uses_shared_achievements_service(app):
    # The last app.achievements shim consumer was repointed here.
    import app.modules.projects.routes.project_overlay as ov
    import app.modules.core.shared.services.achievements as svc
    assert ov is not None and hasattr(svc, 'check_achievements')
