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
