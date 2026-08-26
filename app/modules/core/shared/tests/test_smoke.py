""" Shared HTTP test via the test client - no auth or DB writes."""

def test_root_redirects_to_dashboard(client):
    # index() redirects to the dashboard; a 3xx proves routing + url_for resolve.
    resp = client.get('/')
    assert resp.status_code in (301, 302)