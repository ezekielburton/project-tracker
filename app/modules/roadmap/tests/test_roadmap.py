"""The roadmap page: open to every signed-in role, company-safe content, and
the JS's declared hooks present in the template."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import url_for

from app.modules.core.shared.lib.capabilities import ROLE_LABELS
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.roadmap.lib.items import ITEMS, LIVE, IN_PROGRESS, MONTHS, roadmap_view

_MODULE = Path(__file__).resolve().parents[1]
_JS = _MODULE / 'static' / 'js' / 'roadmap.js'
_TEMPLATE = _MODULE / 'templates' / 'roadmap' / 'index.html'


def _declared_contract():
    """Parse TEMPLATE_CONTRACT from the JS without running it."""
    source = _JS.read_text(encoding='utf-8')
    match = re.search(r'var TEMPLATE_CONTRACT = (\{.*?\n    \});', source, re.DOTALL)
    assert match, 'TEMPLATE_CONTRACT is no longer declared in roadmap.js'
    literal = match.group(1).replace("'", '"')
    literal = re.sub(r',(\s*[}\]])', r'\1', literal)
    return json.loads(literal)


def _user(db_session, role):
    user = User(name=f'Roadmap {role}', email=f'roadmap-{role}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _url(app):
    with app.test_request_context():
        return url_for('roadmap.index')


def test_logged_out_is_sent_to_login(app, client):
    assert client.get(_url(app)).status_code in (302, 401)


@pytest.mark.parametrize('role', sorted(ROLE_LABELS))
def test_every_role_opens_it(app, client, db_session, role):
    login_as(client, app, _user(db_session, role), 'password123')
    resp = client.get(_url(app))
    assert resp.status_code == 200
    assert b'OVP Roadmap' in resp.data


def test_content_is_company_safe():
    """No version numbers and no HSE in anything the page shows."""
    version = re.compile(r'\bv?\d+\.\d+(\.\d+)?\b')
    for item in ITEMS:
        for text in (item['name'], item.get('note', ''), item.get('label', '')):
            assert not version.search(text), text
            assert 'HSE' not in text, text


def test_every_upcoming_item_has_a_known_month_and_a_note():
    months = {key for key, _, _ in MONTHS}
    for item in ITEMS:
        if item['status'] != LIVE:
            assert item['month'] in months, item['name']
            assert item.get('note'), item['name']


def test_view_counts_down_to_the_item_in_progress():
    current = next(item for item in ITEMS if item['status'] == IN_PROGRESS)
    view = roadmap_view(current['due'] - timedelta(days=3))
    assert view['current'] is current
    assert view['days_left'] == 3


def test_view_keeps_month_order_and_drops_empty_months():
    keys = [group['key'] for group in roadmap_view(date(2026, 10, 1))['groups']]
    order = [key for key, _, _ in MONTHS]
    assert keys == [key for key in order if key in keys]
    assert all(group['entries'] for group in roadmap_view(date(2026, 10, 1))['groups'])


def test_template_carries_every_hook_the_js_reads():
    contract = _declared_contract()
    template = _TEMPLATE.read_text(encoding='utf-8')
    for value in contract['ids'].values():
        assert f'id="{value}"' in template, value
    for value in contract['classes'].values():
        assert value in template, value
    for value in contract['attributes'].values():
        assert value in template, value


def test_view_gives_the_countdown_deadline_in_dubai_time():
    current = next(item for item in ITEMS if item['status'] == IN_PROGRESS)
    view = roadmap_view(date(2026, 10, 1))
    assert view['deadline'] == f"{current['due'].isoformat()}T23:59:59+04:00"
