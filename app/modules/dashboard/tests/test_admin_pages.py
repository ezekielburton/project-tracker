"""The admin Overview and System pages: real admin only on every page and card
(an emulating admin keeps them), every card answers even with no snapshot or a
half-written one, Needs attention hides when empty, and the page script's
hooks are all in the rendered pages."""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.dashboard.lib import admin_charts, admin_pages
from app.modules.system.models import AppLogEvent

PASSWORD = 'password123'
SCRIPT = Path(__file__).resolve().parents[1] / 'static' / 'js' / 'admin_system.js'
PARTS = [(page, part) for page, parts in admin_pages.PARTS.items() for part in parts]
PAGES = ('projects.admin_overview', 'projects.admin_system')


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


def _user(db_session, tag, **fields):
    user = User(name=f'Admin Pages {tag}', email=f'admin-pages-{tag}@example.com', **fields)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    return user


def _admin(client, app, db_session, tag='admin'):
    login_as(client, app, _user(db_session, tag, is_admin=True), PASSWORD)


@pytest.fixture
def snapshot_file(app):
    """Writes a snapshot where the pages read it; removed afterwards."""
    path = app.config['SYSTEM_SNAPSHOT_PATH']
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(data):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
    yield write
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(autouse=True)
def _no_snapshot(app):
    path = app.config['SYSTEM_SNAPSHOT_PATH']
    if os.path.exists(path):
        os.remove(path)


GB = 1024 ** 3
FULL = {
    'taken_at': datetime.utcnow().isoformat(timespec='seconds'),
    'host': {'boot_at': 1_790_000_000, 'uptime_s': 3 * 86400 + 5 * 3600, 'cpu_pct': 12.0,
             'load': [0.5, 0.4, 0.3], 'mem_used': 4 * GB, 'mem_total': 16 * GB, 'temp_c': 51.0,
             'net_sent': 1, 'net_recv': 1},
    'mounts': [{'mount': '/', 'used': 40 * GB, 'total': 100 * GB}],
    'workers': {'alive': 9, 'total': 9, 'started_at': 1_790_000_000},
    'app': {'version': 'v2.7', 'commit': 'abc1234', 'head': 'abc'},
    'db': {'ok': True, 'size': 2 * GB, 'pending_migrations': 0},
    'nas': {'ok': True, 'free': 8 * 1024 * GB, 'total': 12 * 1024 * GB, 'share': '/Projects'},
    'slow': {'ok': True, 'os_security': 0, 'os_total': 4, 'pip_outdated': 2, 'pip_total': 40,
             'main_commit': 'abc', 'checked_at': datetime.utcnow().isoformat(timespec='seconds'),
             'certs': [{'name': 'LAN', 'expires_at': None}]},
    'timers': {'ovp-backup': {'last': None, 'next': (datetime.utcnow() + timedelta(hours=3)).isoformat()}},
}


# ── Gating: every page and every card ────────────────────────────────────

@pytest.mark.parametrize('endpoint', PAGES)
def test_pages_need_a_login(app, client, endpoint):
    assert client.get(_url(app, endpoint)).status_code in (302, 401)


@pytest.mark.parametrize('page, part', PARTS)
def test_cards_need_a_login(app, client, page, part):
    assert client.get(_url(app, 'projects.admin_part', page=page, part=part)).status_code in (302, 401)


def test_pages_and_cards_refuse_everyone_but_the_admin(app, client, db_session):
    login_as(client, app, _user(db_session, 'mgmt', seniority='management'), PASSWORD)
    for endpoint in PAGES:
        assert client.get(_url(app, endpoint)).status_code == 403, endpoint
    for page, part in PARTS:
        assert client.get(_url(app, 'projects.admin_part', page=page, part=part)).status_code == 403, part


def test_an_emulating_admin_keeps_every_page_and_card(app, client, db_session):
    _admin(client, app, db_session, 'emu')
    designer = _user(db_session, 'emu-designer', department='design')
    with client.session_transaction() as session:
        session['emulating_user_id'] = designer.id
    for endpoint in PAGES:
        assert client.get(_url(app, endpoint)).status_code == 200, endpoint
    for page, part in PARTS:
        assert client.get(_url(app, 'projects.admin_part', page=page, part=part)).status_code == 200, part


def test_an_unknown_card_is_not_found(app, client, db_session):
    _admin(client, app, db_session, 'unknown')
    assert client.get(_url(app, 'projects.admin_part', page='overview', part='nope')).status_code == 404
    assert client.get(_url(app, 'projects.admin_part', page='nope', part='strip')).status_code == 404


# ── No data, half data, full data ────────────────────────────────────────

@pytest.mark.parametrize('contents', [None, '{"taken_at": "2026-10', json.dumps({'host': {}, 'mounts': [{}]})],
                         ids=['missing', 'broken', 'half-written'])
def test_every_card_answers_without_a_good_snapshot(app, client, db_session, snapshot_file, contents):
    if contents is not None:
        snapshot_file(contents)
    _admin(client, app, db_session, f'nodata-{len(contents or "")}')
    for endpoint in PAGES:
        assert client.get(_url(app, endpoint)).status_code == 200, endpoint
    for page, part in PARTS:
        response = client.get(_url(app, 'projects.admin_part', page=page, part=part))
        assert response.status_code == 200, part
    tiles = client.get(_url(app, 'projects.admin_part', page='system', part='tiles')).get_data(as_text=True)
    assert 'No data' in tiles


def test_a_full_snapshot_fills_the_cards(app, client, db_session, snapshot_file):
    snapshot_file(FULL)
    _admin(client, app, db_session, 'full')

    def card(page, part):
        return client.get(_url(app, 'projects.admin_part', page=page, part=part)).get_data(as_text=True)

    strip = card('overview', 'strip')
    for label in ('Application', 'Database', 'NAS', 'SSE relay', 'Backup', 'Deploy'):
        assert label in strip
    assert 'Nightly backup' in card('overview', 'jobs')
    assert '3<small>d</small> 05<small>h</small>' in card('system', 'tiles')
    assert 'Synology NAS' in card('system', 'storage')
    assert '2 of 40' in card('system', 'updates')
    assert 'v2.7 · abc1234' in card('system', 'application')


def test_needs_attention_hides_when_all_is_well(app, client, db_session, snapshot_file):
    snapshot_file(FULL)
    _admin(client, app, db_session, 'calm')
    html = client.get(_url(app, 'projects.admin_overview')).get_data(as_text=True)
    assert 'Needs attention' not in html
    assert 'all systems normal' in html


def test_needs_attention_lists_an_error_with_a_link_to_errors(app, client, db_session, snapshot_file):
    snapshot_file(FULL)
    db_session.add(AppLogEvent(ts=datetime.utcnow(), level='error', source='app',
                               signature='x-admin-pages', message='Exception on /x [POST]'))
    db_session.flush()
    _admin(client, app, db_session, 'alarm')
    html = client.get(_url(app, 'projects.admin_part', page='overview', part='attention')).get_data(as_text=True)
    assert 'Needs attention' in html and 'Exception on /x [POST]' in html
    assert f'href="{_url(app, "projects.admin_errors")}"' in html
    assert 'data-headline-state="amber"' in html


# ── The page script's hooks ──────────────────────────────────────────────

def _contract():
    source = SCRIPT.read_text(encoding='utf-8')
    block = re.search(r'var ADMIN_LIVE_CONTRACT = \{(.*?)\};', source, re.S).group(1)
    return dict(re.findall(r"(\w+): '([^']+)'", block))


@pytest.mark.parametrize('endpoint', PAGES)
def test_each_page_carries_every_hook_the_script_binds_to(app, client, db_session, endpoint):
    contract = _contract()
    _admin(client, app, db_session, f'hooks-{endpoint[-6:]}')
    html = client.get(_url(app, endpoint)).get_data(as_text=True)
    for key in ('root', 'part', 'headline'):
        attribute = contract[key].strip('[]')
        assert attribute in html, f'admin_system.js binds {contract[key]}; the {endpoint} page lost it.'
    assert contract['partUrl'] in html and contract['streamUrl'] in html


@pytest.mark.parametrize('endpoint', PAGES)
def test_every_card_url_on_a_page_answers(app, client, db_session, endpoint):
    _admin(client, app, db_session, f'urls-{endpoint[-6:]}')
    html = client.get(_url(app, endpoint)).get_data(as_text=True)
    urls = re.findall(r'data-part-url="([^"]+)"', html)
    assert urls
    for url in urls:
        assert client.get(url).status_code == 200, url


# ── Charts and labels ────────────────────────────────────────────────────

def test_bars_scale_to_the_largest_and_keep_zero_visible():
    chart = admin_charts.bars([0, 5, 10], width=300, height=60)
    heights = [bar['h'] for bar in chart['bars']]
    assert heights[2] == 60 and heights[1] == 30 and 0 < heights[0] < 3


def test_lines_place_points_across_the_window():
    start = datetime(2026, 10, 6, 0, 0)
    chart = admin_charts.lines({'sent': [(start, 0), (start + timedelta(hours=24), 10)]},
                               start, start + timedelta(hours=24), width=100, height=50, pad=0)
    assert chart['paths']['sent'] == '0.0,50.0 100.0,0.0'


def test_next_run_labels():
    now = datetime(2026, 10, 6, 10, 0)  # 14:00 Dubai, Tuesday
    assert admin_pages.when(now + timedelta(minutes=2), now) == 'in 2 min'
    assert admin_pages.when(datetime(2026, 10, 6, 19, 0), now) == 'today 23:00'
    assert admin_pages.when(datetime(2026, 10, 7, 0, 0), now) == 'tomorrow 04:00'
    assert admin_pages.when(datetime(2026, 10, 11, 0, 0), now) == 'Sun 04:00'


def test_new_briefs_stay_off_the_admin_pages(app, client, db_session):
    _admin(client, app, db_session, 'briefs')
    for endpoint in PAGES:
        assert 'dash-new-briefs' not in client.get(_url(app, endpoint)).get_data(as_text=True), endpoint
