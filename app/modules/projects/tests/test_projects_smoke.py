"""Smoke tests for the projects module. Grown one stage at a time."""
from flask import url_for


# ── Stage A: transfer ──────────────────────────────────────────────────────
def test_transfer_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('transfer.transfer_deliverable', project_id=1, deliverable_id=1)
    resp = client.post(url)
    assert resp.status_code in (302, 401)
