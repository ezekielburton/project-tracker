"""CS Dashboard: aggregations, finance gating, the module feed, and the
landing route (lib/dashboard.py, services/dashboard_feed.py, routes/dashboard.py)."""
from datetime import date, timedelta
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as, count_queries
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib.access import can_view_finance
from app.modules.client_servicing.lib import dashboard as dash
from app.modules.client_servicing.services.dashboard_feed import feed_for
from app.modules.client_servicing.lib.project_sets import active_projects
from app.modules.client_servicing.lib.data_gaps import MISSING_DATA_CHIP, missing_fields

TODAY = date(2026, 9, 15)


def _user(db_session, tag, role='cs'):
    u = User(name=f'Dash {tag}', email=f'cs-dash-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _project(db_session, tag, creator, install=None, cs_status=None,
             risk=None, status='briefed', value=None, due=None, cancelled=False, **cs):
    """A CS project (+ optional companion row). `due` is the project's
    first_output_deadline; **cs go on the ClientServicing row."""
    p = Project(name=f'Dash {tag}', created_by_id=creator.id,
                cs_lead_id=creator.id, project_status=status,
                installation_date=install, first_output_deadline=due, value=value)
    if cancelled:
        from datetime import datetime
        p.cancelled_at = datetime(2026, 1, 1)
    db_session.add(p)
    db_session.flush()
    if cs_status or risk or cs:
        db_session.add(ClientServicing(project_id=p.id, cs_status=cs_status, risk=risk, **cs))
        db_session.flush()
    return p


def _snap(today=TODAY):
    return dash._snapshot(active_projects().all(), today)


# ── finance gate ───────────────────────────────────────────────────────────
def test_can_view_finance_by_role(db_session):
    def sees(r):
        return can_view_finance(_user(db_session, 'fv-' + r, role=r))
    assert all(sees(r) for r in ('admin', 'management', 'cs', 'finance', 'project_owner'))
    assert not sees('designer')
    assert not can_view_finance(None)


# ── KPI band ───────────────────────────────────────────────────────────────
def test_kpi_band_counts(db_session):
    lead = _user(db_session, 'k')
    _project(db_session, 'k1', lead, install=TODAY + timedelta(days=1), cs_status='Briefing')
    _project(db_session, 'k2', lead, install=TODAY + timedelta(days=5), cs_status='Briefing')
    _project(db_session, 'k3', lead, install=TODAY + timedelta(days=20), cs_status='Briefing')
    _project(db_session, 'k4', lead, cs_status='Pending LPO')
    _project(db_session, 'k5', lead, install=TODAY + timedelta(days=1), cs_status='Briefing', cancelled=True)
    band = dash._kpi_band(_snap(), TODAY, False, None)
    assert band['active'] == 4            # k5 cancelled drops out
    assert band['installs_month'] == 2    # k1, k2 (k3 is next month)
    assert band['next7'] == 2             # k1, k2
    assert band['at_risk'] == 1           # k1 imminent + not ready
    assert 'pipeline' not in band and 'stuck' not in band


def test_kpi_band_adds_finance_when_shown():
    band = dash._kpi_band([], TODAY, True, {'pipeline': Decimal('500'), 'stuck': 2})
    assert band['pipeline'] == Decimal('500') and band['stuck'] == 2


# ── status spread ──────────────────────────────────────────────────────────
def test_status_spread_maps_families(db_session):
    lead = _user(db_session, 's')
    for tag, st in [('s1', 'Briefing'), ('s2', 'Pending Approval'), ('s3', 'Pending LPO'),
                    ('s4', 'In Production'), ('s5', 'Installed'), ('s6', 'Invoiced'),
                    ('s7', 'On Hold'), ('s8', 'Cancelled')]:
        _project(db_session, tag, lead, cs_status=st)
    by = {f['name']: f['count'] for f in dash._status_spread(_snap())['families']}
    assert by == {'In Design': 1, 'Pending Approval': 1, 'Pre-Production': 1,
                  'In Production': 1, 'Post-Install': 1, 'Invoicing': 1, 'On Hold': 1}
    # 'Cancelled' maps to no family — excluded from the spread.


# ── workload ───────────────────────────────────────────────────────────────
def test_workload_groups_by_lead(db_session):
    a, b = _user(db_session, 'wa'), _user(db_session, 'wb')
    _project(db_session, 'w1', a, install=TODAY + timedelta(days=1), cs_status='Briefing')
    _project(db_session, 'w2', a, cs_status='Pending LPO')
    _project(db_session, 'w3', b, cs_status='Pending LPO')
    workload = dash._workload(_snap())
    assert len(workload) == 2
    assert workload[0]['name'] == a.name            # most active first
    wa = next(w for w in workload if w['name'] == a.name)
    assert wa['active'] == 2 and wa['at_risk'] == 1


# ── upcoming ───────────────────────────────────────────────────────────────
def test_upcoming_future_only_and_sorted(db_session):
    lead = _user(db_session, 'u')
    _project(db_session, 'u_past', lead, install=TODAY - timedelta(days=3), cs_status='Briefing')
    _project(db_session, 'u_near', lead, install=TODAY + timedelta(days=2), cs_status='Briefing')
    _project(db_session, 'u_far', lead, install=TODAY + timedelta(days=10), cs_status='Briefing')
    dates = [it['install_date'] for it in dash._upcoming(_snap(), TODAY)]
    assert dates == [TODAY + timedelta(days=2), TODAY + timedelta(days=10)]


# ── urgent actions (links need a request context) ──────────────────────────
def test_urgent_actions_keep_risk_and_money_only(app, db_session):
    lead = _user(db_session, 'ua')
    _project(db_session, 'ua_risk', lead, install=TODAY + timedelta(days=1), cs_status='Briefing', value=Decimal('1000'))
    _project(db_session, 'ua_att', lead, install=TODAY + timedelta(days=5), cs_status='Briefing', value=Decimal('1000'))
    _project(db_session, 'ua_gap', lead, cs_status='Pending LPO')  # no install / value
    with app.test_request_context():
        items = dash._urgent_actions(_snap(), [], TODAY, False)
    assert 'data_gap' not in [i['kind'] for i in items]
    assert [i['urgency'] for i in items] == ['urgent', 'warning']   # At Risk first
    assert '/client-servicing/calendar' in items[0]['link']


def test_missing_fields_names_install_date_and_value():
    p = Project(name='Gap check')
    assert missing_fields(p) == ['install date', 'value']
    p.installation_date, p.value = TODAY, 10
    assert missing_fields(p) == []


def test_data_gaps_count_jobs_once_and_link_to_the_chip(app, db_session):
    lead = _user(db_session, 'dg')
    _project(db_session, 'dg_both', lead, cs_status='Briefing')                       # two gaps, one job
    _project(db_session, 'dg_value', lead, install=TODAY, cs_status='Briefing')       # no value
    _project(db_session, 'dg_full', lead, install=TODAY, value=Decimal('10'), cs_status='Briefing')
    with app.test_request_context():
        gaps = dash._data_gaps(_snap())
    assert gaps['count'] == 2
    assert '/client-servicing/table' in gaps['link']
    assert 'chip=' + MISSING_DATA_CHIP in gaps['link']


def test_dashboard_shows_gap_strip_and_badge_counts_risk_only(app, client, db_session):
    today = date.today()
    lead = _user(db_session, 'gs')
    _project(db_session, 'gs_risk', lead, install=today + timedelta(days=1),
             cs_status='Briefing', value=Decimal('1000'))
    _project(db_session, 'gs_gap1', lead, cs_status='Briefing')
    _project(db_session, 'gs_gap2', lead, cs_status='Briefing')
    with app.test_request_context():
        url = url_for('client_servicing.index')
    login_as(client, app, lead, 'password123')

    body = client.get(url).get_data(as_text=True)
    assert 'cs-dash-gapstrip-count">2</span>' in body
    assert 'cs-dash-badge">1</span>' in body        # the at-risk install only
    assert 'Missing install date' not in body       # no per-job gap rows


def test_gap_strip_hidden_when_nothing_is_missing(app, client, db_session):
    lead = _user(db_session, 'gh')
    _project(db_session, 'gh_full', lead, install=date.today() + timedelta(days=30),
             cs_status='Briefing', value=Decimal('10'))
    with app.test_request_context():
        url = url_for('client_servicing.index')
    login_as(client, app, lead, 'password123')
    assert 'cs-dash-gapstrip' not in client.get(url).get_data(as_text=True)


def test_finance_signals_urgency(app):
    due = [
        {'project': 'Overdue', 'client': 'ACME', 'validation': 'overdue'},
        {'project': 'NoLPO', 'client': 'ACME', 'validation': 'no_lpo'},
        {'project': 'Unbilled', 'client': 'ACME', 'validation': None},
    ]
    with app.test_request_context():
        by = {i['title']: i for i in dash._finance_signals(due, TODAY)}
    assert by['Overdue']['kind'] == 'invoice_overdue' and by['Overdue']['urgency'] == 'urgent'
    assert by['NoLPO']['kind'] == 'lpo_outstanding' and by['NoLPO']['urgency'] == 'warning'
    assert by['Unbilled']['kind'] == 'invoice_due' and by['Unbilled']['urgency'] == 'warning'
    assert all('/client-servicing/invoicing' in i['link'] for i in by.values())


# ── module feed ────────────────────────────────────────────────────────────
def test_feed_for_empty_for_no_access(db_session):
    assert feed_for(_user(db_session, 'fd', role='designer')) == []


def test_feed_for_hides_finance_from_non_finance(app, db_session, owner_without_finance):
    today = date.today()
    lead = _user(db_session, 'ff', role='cs')
    owner = _user(db_session, 'ffo', role='project_owner')
    _project(db_session, 'ff_ins', lead, install=today + timedelta(days=3), cs_status='Briefing')
    # Finance buckets by invoice_month_date; first_output_deadline is the design deadline.
    _project(db_session, 'ff_fin', lead, invoice_month_date=today.replace(day=1),
             project_value=Decimal('500'), validation_status='overdue')
    with app.test_request_context():
        cs_kinds = {i['kind'] for i in feed_for(lead)}
        owner_kinds = {i['kind'] for i in feed_for(owner)}
    assert 'install_upcoming' in cs_kinds and 'install_upcoming' in owner_kinds
    assert 'invoice_overdue' in cs_kinds                                      # finance viewer sees it
    assert not (owner_kinds & {'invoice_overdue', 'lpo_outstanding', 'invoice_due'})  # hidden


# ── route: gate, landing/rename, finance render, N+1 ───────────────────────
def test_dashboard_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('client_servicing.index')
    assert client.get(url).status_code in (302, 401)


def test_dashboard_gate_by_role(app, client, db_session):
    with app.test_request_context():
        url = url_for('client_servicing.index')
    for role in ('cs', 'admin', 'management', 'project_owner', 'finance'):
        login_as(client, app, _user(db_session, 'g-' + role, role=role), 'password123')
        assert client.get(url).status_code == 200, role
    login_as(client, app, _user(db_session, 'gx', role='designer'), 'password123')
    assert client.get(url).status_code == 403


def test_dashboard_403_for_admin_emulating_designer(app, client, db_session):
    admin = _user(db_session, 'em', role='admin')
    designer = _user(db_session, 'em2', role='designer')
    login_as(client, app, admin, 'password123')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id
    with app.test_request_context():
        url = url_for('client_servicing.index')
    assert client.get(url).status_code == 403


def test_landing_is_dashboard_and_table_moved(app, client, db_session):
    user = _user(db_session, 'lt')
    _project(db_session, 'lt1', user, cs_status='Briefing')
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        index_url = url_for('client_servicing.index')
        table_url = url_for('client_servicing.table')
    assert index_url == '/client-servicing/' and table_url == '/client-servicing/table'
    assert 'Dashboard' in client.get(index_url).get_data(as_text=True)   # landing = dashboard
    assert 'Dash lt1' in client.get(table_url).get_data(as_text=True)    # table still renders rows


def test_dashboard_renders_and_gates_finance_in_page(app, client, db_session, owner_without_finance):
    today = date.today()
    lead = _user(db_session, 'pr', role='cs')
    owner = _user(db_session, 'pro', role='project_owner')
    _project(db_session, 'pr_ins', lead, install=today + timedelta(days=1), cs_status='Briefing')
    _project(db_session, 'pr_fin', lead, invoice_month_date=today.replace(day=1),
             project_value=Decimal('750'), validation_status='overdue')
    with app.test_request_context():
        url = url_for('client_servicing.index')

    login_as(client, app, lead, 'password123')
    assert 'Pipeline ·' in client.get(url).get_data(as_text=True)         # finance viewer sees it

    login_as(client, app, owner, 'password123')
    assert 'Pipeline ·' not in client.get(url).get_data(as_text=True)     # project_owner: hidden


def test_dashboard_context_is_n_plus_1_free(app, db_session):
    admin = _user(db_session, 'n', role='admin')

    def seed(n, tag):
        for i in range(n):
            _project(db_session, f'{tag}{i}', admin, install=TODAY + timedelta(days=i % 5),
                     cs_status='Briefing', due=date.today().replace(day=1),
                     project_value=Decimal('100'), validation_status='overdue')

    seed(3, 'a')
    with app.test_request_context(), count_queries() as small:
        dash.dashboard_context(admin)
    seed(6, 'b')
    with app.test_request_context(), count_queries() as big:
        dash.dashboard_context(admin)
    assert big[0] == small[0], (small[0], big[0])   # query count flat as rows grow


def test_dashboard_panels_fragment_renders_and_gates(app, client, db_session):
    """The SSE refresh fragment renders the panels for allowed roles and 403s otherwise."""
    lead = _user(db_session, 'frag', role='cs')
    _project(db_session, 'frag1', lead, install=date.today() + timedelta(days=1), cs_status='Briefing')
    with app.test_request_context():
        url = url_for('client_servicing.dashboard_panels')

    login_as(client, app, lead, 'password123')
    body = client.get(url).get_data(as_text=True)
    assert 'cs-dash-kpis' in body                 # panels rendered
    assert 'id="cs-dash-panels"' not in body      # inner partial only, not the page wrapper

    login_as(client, app, _user(db_session, 'fragx', role='designer'), 'password123')
    assert client.get(url).status_code == 403
