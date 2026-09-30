"""The Table's quick filter chips: the contract client_servicing.js declares,
the flags the server stamps on each row, and that chips count what the
Dashboard counts."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.lib.data_gaps import MISSING_DATA_CHIP
from app.modules.client_servicing.lib.quick_chips import CHIPS
from app.modules.client_servicing.lib.dashboard import dashboard_context

_JS = Path(__file__).resolve().parents[1] / 'static' / 'js' / 'client_servicing.js'


def _declared_contract():
    """Parse TEMPLATE_CONTRACT from the JS without running it: swap single
    quotes for double and drop trailing commas, then read it as JSON."""
    source = _JS.read_text(encoding='utf-8')
    match = re.search(r'var TEMPLATE_CONTRACT = (\{.*?\});', source, re.DOTALL)
    assert match, 'TEMPLATE_CONTRACT is no longer declared in client_servicing.js'
    literal = match.group(1).replace("'", '"')
    literal = re.sub(r',(\s*[}\]])', r'\1', literal)
    return json.loads(literal)


def _user(db_session, tag, role='cs'):
    user = User(name=f'Chip {tag}', email=f'cs-chips-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, name, lead, owner=None, install=None, value=None):
    p = Project(name=name, cs_lead_id=lead.id, created_by_id=lead.id,
                project_owner_id=owner.id if owner else None,
                project_status='briefed', installation_date=install, value=value)
    db_session.add(p)
    db_session.flush()
    return p


def _seed(db_session, me, other):
    today = date.today()
    far = today + timedelta(days=60)
    return {
        'mine_gap': _project(db_session, 'Chip Mine Gap', me),
        'far': _project(db_session, 'Chip Far', other, install=far, value=10),
        'risk': _project(db_session, 'Chip Risk Today', other, install=today, value=10),
        'owned': _project(db_session, 'Chip Owned', other, owner=me, install=far, value=10),
    }


def _row_chips(app, client):
    with app.test_request_context():
        url = url_for('client_servicing.table_rows')
    html = client.get(url).get_data(as_text=True)
    pairs = re.findall(r'<tr data-project-id="(\d+)"[^>]*data-chips="([^"]*)"', html)
    return {int(pid): set(chips.split()) for pid, chips in pairs}


def test_js_contract_matches_the_server_chips():
    declared = _declared_contract()
    assert declared['chips'] == [chip_id for chip_id, _ in CHIPS], (
        'client_servicing.js TEMPLATE_CONTRACT and lib/quick_chips.py CHIPS '
        'disagree - update both together.')
    assert MISSING_DATA_CHIP in declared['chips'], (
        "The Dashboard's missing-data strip links to a chip the Table no longer has.")


def test_table_renders_the_declared_chip_bar_and_row_attribute(app, client, db_session):
    me = _user(db_session, 'bar')
    _project(db_session, 'Chip Bar Job', me)
    login_as(client, app, me, 'password123')
    with app.test_request_context():
        url = url_for('client_servicing.table')
    html = client.get(url).get_data(as_text=True)

    declared = _declared_contract()
    assert 'id="{}"'.format(declared['chipBar']) in html
    for chip_id in declared['chips']:
        assert 'data-chip="{}"'.format(chip_id) in html, chip_id
    assert '{}="'.format(declared['rowAttribute']) in html


def test_each_row_carries_the_chips_it_matches(app, client, db_session):
    me, other = _user(db_session, 'me'), _user(db_session, 'other')
    p = _seed(db_session, me, other)
    login_as(client, app, me, 'password123')

    chips = _row_chips(app, client)
    assert chips[p['mine_gap'].id] == {'mine', 'missing_data'}
    assert chips[p['far'].id] == set()
    assert chips[p['risk'].id] == {'at_risk', 'installs_month'}
    assert chips[p['owned'].id] == {'mine'}          # project owner counts as mine


def test_my_jobs_follows_the_emulated_user(app, client, db_session):
    admin = _user(db_session, 'adm', role='admin')
    me, other = _user(db_session, 'em'), _user(db_session, 'eo')
    far = date.today() + timedelta(days=60)
    mine = _project(db_session, 'Chip Emulated Mine', me, install=far, value=10)
    theirs = _project(db_session, 'Chip Emulated Theirs', other, install=far, value=10)
    login_as(client, app, admin, 'password123')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = me.id

    chips = _row_chips(app, client)
    assert 'mine' in chips[mine.id]
    assert 'mine' not in chips[theirs.id]


def test_chips_count_what_the_dashboard_counts(app, client, db_session):
    me, other = _user(db_session, 'dm'), _user(db_session, 'do')
    _seed(db_session, me, other)
    login_as(client, app, me, 'password123')

    chips = _row_chips(app, client)
    with app.test_request_context():
        ctx = dashboard_context(me)
    assert ctx['kpis']['at_risk'] == sum('at_risk' in c for c in chips.values())
    assert ctx['kpis']['installs_month'] == sum('installs_month' in c for c in chips.values())
    assert ctx['data_gaps']['count'] == sum('missing_data' in c for c in chips.values())
