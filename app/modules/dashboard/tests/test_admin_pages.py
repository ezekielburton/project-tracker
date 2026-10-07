"""The admin system pages (Overview, System, Database, Performance, Usage,
Errors, Uptime, Jobs) and the incident note endpoint:
real admin only on every page and card (an emulating admin keeps them), every
card answers even with no snapshot or a half-written one, Needs attention hides
when empty, the cards fill from real data, and the page script's hooks are all
in the rendered pages."""
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
from app.modules.system.models import AppLogEvent, DeployRun, Heartbeat, JobRun, RequestMetric, SystemIncident

PASSWORD = 'password123'
SCRIPT = Path(__file__).resolve().parents[1] / 'static' / 'js' / 'admin_system.js'
PARTS = [(page, part) for page, parts in admin_pages.PARTS.items() for part in parts]
PAGES = ('projects.admin_overview', 'projects.admin_system', 'projects.admin_database',
         'projects.admin_performance', 'projects.admin_usage', 'projects.admin_errors',
         'projects.admin_uptime', 'projects.admin_jobs')


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


def test_needs_attention_lists_an_error_with_a_link_to_errors(app, client, db_session, snapshot_file):
    snapshot_file(FULL)
    db_session.add(AppLogEvent(ts=datetime.utcnow(), level='error', source='app',
                               signature='x-admin-pages', message='Exception on /x [POST]'))
    db_session.flush()
    _admin(client, app, db_session, 'alarm')
    html = client.get(_url(app, 'projects.admin_part', page='overview', part='attention')).get_data(as_text=True)
    assert 'Needs attention' in html and 'Exception on /x [POST]' in html
    assert f'href="{_url(app, "projects.admin_errors")}"' in html


def _card(client, app, page, part):
    return client.get(_url(app, 'projects.admin_part', page=page, part=part)).get_data(as_text=True)


def test_card_pages_fill_from_request_metrics(app, client, db_session):
    worker = User(name='Cards Worker', email='admin-pages-cards-worker@example.com', department='client_servicing')
    worker.set_password(PASSWORD)
    shown = User(name='Cards Shown', email='admin-pages-cards-shown@example.com', department='design', team='3D')
    shown.set_password(PASSWORD)
    db_session.add_all([worker, shown])
    db_session.flush()
    _admin(client, app, db_session, 'cards')
    admin = User.query.filter_by(email='admin-pages-cards@example.com').one()
    now = datetime.utcnow()

    def hit(minutes_ago, **fields):
        row = dict(ts=now - timedelta(minutes=minutes_ago), method='GET', route='/x-cards', blueprint='wiki',
                   status=200, duration_ms=120)
        row.update(fields)
        db_session.add(RequestMetric(**row))
    for minutes in (5, 6, 7):
        hit(minutes, route='/wiki/x-cards', page=True)
        hit(minutes, method='POST', route='/wiki/x-cards/save', user_id=worker.id)
    hit(3, method='POST', route='/login', blueprint='auth', status=302, user_id=worker.id)
    hit(20, route='/dashboard', blueprint='projects', user_id=admin.id, emulating_id=shown.id)
    hit(14, route='/dashboard', blueprint='projects', user_id=admin.id, emulating_id=shown.id)
    db_session.flush()

    assert '/wiki/x-cards' in _card(client, app, 'performance', 'routes')
    assert 'Wiki' in _card(client, app, 'performance', 'modules')
    assert 'Average' in _card(client, app, 'performance', 'response')
    assert 'Wiki' in _card(client, app, 'usage', 'modules')
    assert 'Cards Worker · Client Servicing' in _card(client, app, 'usage', 'logins')
    assert 'Cards Shown (3D)' in _card(client, app, 'usage', 'emulation')
    assert '<rect' in _card(client, app, 'usage', 'daily')
    assert 'pg_stat_statements is off' in _card(client, app, 'database', 'queries')
    assert 'dash-admin-hb' in _card(client, app, 'database', 'tables')
    assert 'Postgres' in _card(client, app, 'database', 'maintenance')
    assert 'Database size' in _card(client, app, 'database', 'tiles')


def test_card_pages_with_no_metrics_say_so_quietly(app, client, db_session):
    _admin(client, app, db_session, 'quiet')
    assert 'No requests yet' in _card(client, app, 'performance', 'routes')
    assert 'No logins yet' in _card(client, app, 'usage', 'logins')
    assert 'None in 30 days' in _card(client, app, 'usage', 'emulation')


def test_every_layout_part_is_a_part_and_back():
    for page, layout in admin_pages.LAYOUTS.items():
        assert {name for row in layout for name in row} == set(admin_pages.PARTS[page]), page


# ── The status badge ─────────────────────────────────────────────────────

def _badge(html):
    return re.search(r'<span class="dash-admin-live[^"]*"[^>]*data-admin-badge.*?</span>\s*</span>', html, re.S).group(0)


@pytest.mark.parametrize('endpoint', PAGES)
def test_every_page_has_the_badge_and_no_caption(app, client, db_session, snapshot_file, endpoint):
    snapshot_file(dict(FULL, taken_at=(datetime.utcnow() - timedelta(seconds=40)).isoformat(timespec='seconds')))
    _admin(client, app, db_session, f'badge-{endpoint[-6:]}')
    html = client.get(_url(app, endpoint)).get_data(as_text=True)
    badge = _badge(html)
    assert 'dash-admin-live--live' in badge and 'Live · ' in badge and 'data-age="4' in badge
    for caption in ('pg_stat · live', 'rolling 24h', 'test accounts left out', 'app log · 7 days kept',
                    'heartbeat · every minute', 'Run now is logged', 'data-admin-headline'):
        assert caption not in html, caption


def test_badge_states():
    now = datetime(2031, 3, 4, 10, 0, 0)  # Tuesday, 14:00 in Dubai
    assert admin_pages.badge({}, now) == {'state': 'none', 'text': 'No data yet', 'age': None, 'day': 'Tue 4 Mar'}
    live = admin_pages.badge({'taken_at': (now - timedelta(seconds=50)).isoformat()}, now)
    assert live == {'state': 'live', 'text': 'Live · Tue 4 Mar', 'age': 50, 'day': 'Tue 4 Mar'}
    stale = admin_pages.badge({'taken_at': (now - timedelta(minutes=7, seconds=20)).isoformat()}, now)
    assert stale['state'] == 'stale' and stale['text'] == 'Updated 7 min ago' and stale['age'] == 440


def test_charts_carry_a_scale_and_hover_labels(app, client, db_session):
    _admin(client, app, db_session, 'scale')
    now = datetime.utcnow()
    for minutes, ms in ((20, 100), (25, 300), (200, 50)):
        db_session.add(RequestMetric(ts=now - timedelta(minutes=minutes), method='GET', route='/x-scale',
                                     blueprint='wiki', status=200, duration_ms=ms))
    db_session.flush()
    html = _card(client, app, 'performance', 'response')
    scale = re.search(r'dash-admin-scale">(.*?)</div>', html, re.S).group(1)
    assert re.findall(r'<span>([^<]+)</span>', scale)[-1] == '0 ms'
    assert re.search(r'<title>\d\d:\d\d · avg \d+ ms · p95 \d+ ms</title>', html)


def test_scrolling_cards_opt_in_to_scroll_hold(app, client, db_session):
    _admin(client, app, db_session, 'hold')
    html = _card(client, app, 'uptime', 'deploys')
    assert 'dash-admin-panel-body--scroll scroll-hold' in html


def test_errors_uptime_and_jobs_fill_from_their_records(app, client, db_session):
    _admin(client, app, db_session, 'records')
    now = datetime.utcnow()
    db_session.add(AppLogEvent(ts=now - timedelta(hours=2), level='error', source='sse_relay',
                               signature='x-records-relay', message='Relay reset', detail='Traceback line'))
    db_session.add(RequestMetric(ts=now - timedelta(hours=1), method='POST', route='/x-records/upload',
                                 blueprint='wiki', status=500, duration_ms=30))
    for minutes in range(90, -1, -1):
        if not 40 <= minutes < 50:
            db_session.add(Heartbeat(ts=now - timedelta(minutes=minutes), ok=True, ms=9))
    db_session.add(DeployRun(ran_at=now - timedelta(days=1), tag='v-records', migrations_applied=1,
                             duration_ms=30_000, ok=True))
    db_session.add(SystemIncident(happened_on=now.date(), title='Records outage', minutes=9, note='Power'))
    db_session.add(JobRun(job='orphan-uploads', started_at=now - timedelta(hours=3), finished_at=now - timedelta(hours=3),
                          result='ok', details={'count': 1, 'bytes': 2048, 'files': [
                              {'name': 'x-records.pdf', 'size': 2048, 'modified': (now - timedelta(days=40)).isoformat()}]}))
    db_session.flush()

    groups = _card(client, app, 'errors', 'groups')
    assert 'Relay reset' in groups and 'Traceback line' in groups and 'data-key="x-records-relay"' in groups
    assert '/x-records/upload' in _card(client, app, 'errors', 'routes')
    assert 'Relay reset' in _card(client, app, 'errors', 'tail')
    assert 'dash-admin-day dash-admin--red' in _card(client, app, 'uptime', 'days')
    assert 'min down' in _card(client, app, 'uptime', 'tiles')
    assert 'v-records' in _card(client, app, 'uptime', 'deploys')
    incidents = _card(client, app, 'uptime', 'incidents')
    assert 'Records outage' in incidents and 'data-incident-form' in incidents and 'data-form-error' in incidents
    jobs = _card(client, app, 'jobs', 'jobs')
    assert 'data-run-job="backup"' in jobs and 'data-run-url=' in jobs and 'timer only' in jobs
    assert 'x-records.pdf' in _card(client, app, 'jobs', 'orphans')


def test_the_jobs_page_opens_its_own_help(app, client, db_session):
    _admin(client, app, db_session, 'jobs-help')
    assert 'data-help-key="dashboard.jobs"' in client.get(_url(app, 'projects.admin_jobs')).get_data(as_text=True)
    assert 'data-help-key="dashboard.admin"' in client.get(_url(app, 'projects.admin_errors')).get_data(as_text=True)


# ── Adding an incident note ──────────────────────────────────────────────

def _add(client, app, **body):
    return client.post(_url(app, 'projects.admin_incident_add'), json=body)


def test_adding_an_incident_needs_the_real_admin(app, client, db_session):
    assert _add(client, app, title='x').status_code in (401, 403)
    login_as(client, app, _user(db_session, 'inc-mgmt', seniority='management'), PASSWORD)
    assert _add(client, app, title='x').status_code == 403
    assert SystemIncident.query.filter_by(title='x').count() == 0


def test_an_emulating_admin_adds_an_incident_as_themselves(app, client, db_session):
    _admin(client, app, db_session, 'inc-emu')
    admin = User.query.filter_by(email='admin-pages-inc-emu@example.com').one()
    designer = _user(db_session, 'inc-designer', department='design')
    with client.session_transaction() as session:
        session['emulating_user_id'] = designer.id
    response = _add(client, app, title='Server unreachable', minutes='26', note='Power cut')
    assert response.status_code == 200 and response.get_json()['success']
    saved = SystemIncident.query.filter_by(title='Server unreachable').one()
    assert saved.created_by_id == admin.id and saved.minutes == 26


def test_a_bad_incident_says_what_is_wrong(app, client, db_session):
    _admin(client, app, db_session, 'inc-bad')
    response = _add(client, app, title='', minutes='3')
    assert response.status_code == 400 and response.get_json()['error'] == 'Add a title'


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
    for key in ('root', 'part', 'badge'):
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


def test_lines_can_start_from_the_lowest_value():
    start = datetime(2026, 10, 6, 0, 0)
    chart = admin_charts.lines({'size': [(start, 100), (start + timedelta(hours=24), 110)]},
                               start, start + timedelta(hours=24), width=100, height=50, pad=0, from_zero=False)
    assert chart['paths']['size'] == '0.0,50.0 100.0,0.0'


def test_date_ticks():
    start = datetime(2026, 9, 7, 8, 0)
    assert admin_charts.date_ticks(start, start + timedelta(days=30), lambda moment: moment) == ['7 Sep', '22 Sep', '7 Oct']


def test_next_run_labels():
    now = datetime(2026, 10, 6, 10, 0)  # 14:00 Dubai, Tuesday
    assert admin_pages.when(now + timedelta(seconds=40), now) == 'in under 1 min'
    assert admin_pages.when(now + timedelta(minutes=2), now) == 'in 2 min'
    assert admin_pages.when(datetime(2026, 10, 6, 19, 0), now) == 'today 23:00'
    assert admin_pages.when(datetime(2026, 10, 7, 0, 0), now) == 'tomorrow 04:00'
    assert admin_pages.when(datetime(2026, 10, 11, 0, 0), now) == 'Sun 04:00'


def test_new_briefs_stay_off_the_admin_pages(app, client, db_session):
    _admin(client, app, db_session, 'briefs')
    for endpoint in PAGES:
        assert 'dash-new-briefs' not in client.get(_url(app, endpoint)).get_data(as_text=True), endpoint
