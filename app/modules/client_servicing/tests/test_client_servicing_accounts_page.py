"""The Accounts page: who can open it, what finance hides, filters and the
empty state, the saved view, the rail entry, and the contract between its
script and markup."""
import json
import re
from datetime import date
from pathlib import Path

from flask import url_for

from app.modules.core.shared.models import User, Project, UserTableLayout
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib.accounts_state import STATE_KEY, clean_state

_MODULE = Path(__file__).resolve().parents[1]
_JS = _MODULE / 'static' / 'js' / 'client_servicing_accounts.js'
_TEMPLATE = _MODULE / 'templates' / 'client_servicing' / 'accounts.html'


def _declared_contract():
    """Parse TEMPLATE_CONTRACT from the JS without running it: swap single
    quotes for double and drop trailing commas, then read it as JSON."""
    source = _JS.read_text(encoding='utf-8')
    match = re.search(r'var TEMPLATE_CONTRACT = (\{.*?\n    \});', source, re.DOTALL)
    assert match, 'TEMPLATE_CONTRACT is no longer declared in client_servicing_accounts.js'
    literal = match.group(1).replace("'", '"')
    literal = re.sub(r',(\s*[}\]])', r'\1', literal)
    return json.loads(literal)


def _user(db_session, tag, role='cs'):
    user = User(name=f'Accounts {tag}', email=f'cs-accpage-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _job(db_session, lead, name, value=100, invoice_date=None, invoice_amount=None):
    project = Project(name=name, cs_lead_id=lead.id, created_by_id=lead.id,
                      project_status='briefed', value=value)
    db_session.add(project)
    db_session.flush()
    db_session.add(ClientServicing(project_id=project.id, invoice_date=invoice_date,
                                   invoice_amount=invoice_amount))
    db_session.flush()
    return project


def _url(app, endpoint='client_servicing.accounts', **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def _page(app, client, user, **kwargs):
    login_as(client, app, user, 'password123')
    return client.get(_url(app, **kwargs))


def _emulate(client, target):
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target.id


# ------ Gate ------

def test_a_role_without_cs_access_is_refused(app, client, db_session):
    assert _page(app, client, _user(db_session, 'designer', role='designer')).status_code == 403


def test_every_cs_role_opens_it(app, client, db_session):
    for role in ('cs', 'project_owner', 'finance', 'management', 'admin'):
        resp = _page(app, client, _user(db_session, 'open-' + role, role=role))
        assert resp.status_code == 200, f'{role} could not open Accounts'


def test_an_emulating_admin_is_gated_as_the_emulated_user(app, client, db_session):
    admin = _user(db_session, 'emu-admin', role='admin')
    login_as(client, app, admin, 'password123')
    _emulate(client, _user(db_session, 'emu-designer', role='designer'))
    assert client.get(_url(app)).status_code == 403
    _emulate(client, _user(db_session, 'emu-cs', role='cs'))
    assert client.get(_url(app)).status_code == 200


def test_the_review_lock_applies(app, client, db_session):
    cs = _user(db_session, 'lock-cs', role='cs')
    manager = _user(db_session, 'lock-mgmt', role='management')
    app.config['CLIENT_SERVICING_REVIEW_ONLY'] = True
    try:
        assert _page(app, client, cs).status_code == 403
        assert _page(app, client, manager).status_code == 200
    finally:
        app.config['CLIENT_SERVICING_REVIEW_ONLY'] = False


# ------ Finance ------

def test_a_project_owner_sees_values_but_no_invoicing(app, client, db_session):
    lead = _user(db_session, 'fin-lead')
    _job(db_session, lead, 'Accounts Invoiced Job', value=500,
         invoice_date=date(2026, 3, 4), invoice_amount=500)

    owner_body = _page(app, client, _user(db_session, 'fin-po', role='project_owner')).get_data(as_text=True)
    assert 'Accounts Invoiced Job' in owner_body
    assert 'Project value (AED)' in owner_body
    assert 'cs-acc-fin' not in owner_body
    assert 'Not yet invoiced' not in owner_body

    cs_body = _page(app, client, _user(db_session, 'fin-cs', role='cs')).get_data(as_text=True)
    assert 'cs-acc-fin' in cs_body
    assert 'Not yet invoiced' in cs_body


# ------ Grouping, filters, empty state ------

def test_grouped_by_lead_the_lead_heads_the_group(app, client, db_session):
    lead = _user(db_session, 'by-lead')
    _job(db_session, lead, 'Accounts Lead Job')
    body = _page(app, client, lead, group='lead').get_data(as_text=True)
    assert '<span class="cs-acc-gname">Accounts by-lead</span>' in body
    assert '<th>Client</th>' in body


def test_bad_parameters_fall_back_to_the_defaults(app, client, db_session):
    user = _user(db_session, 'bad')
    resp = _page(app, client, user, group='nope', client='abc', lead='-3', month='2026-13')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '<th>CS lead</th>' in body
    assert '<option value="">All time</option>' in body


def test_empty_states(app, client, db_session):
    user = _user(db_session, 'empty')
    assert 'No jobs yet' in _page(app, client, user).get_data(as_text=True)
    assert 'No jobs match these filters.' in _page(app, client, user, month='1999-01').get_data(as_text=True)


def test_the_rail_lists_accounts_between_invoicing_and_calendar(app, client, db_session):
    body = _page(app, client, _user(db_session, 'rail')).get_data(as_text=True)
    invoicing = body.find(f'href="{_url(app, "client_servicing.invoicing")}"')
    accounts = body.find(f'href="{_url(app)}"')
    calendar = body.find(f'href="{_url(app, "client_servicing.calendar")}"')
    assert -1 < invoicing < accounts < calendar


# ------ Saved view ------

def _save(app, client, payload):
    return client.post(_url(app, 'client_servicing.save_accounts_state'), json=payload)


def test_groups_start_collapsed(app, client, db_session):
    lead = _user(db_session, 'fold')
    _job(db_session, lead, 'Accounts Folded Job')
    body = _page(app, client, lead).get_data(as_text=True)
    assert '<tbody class="cs-acc-group is-collapsed" data-key="none">' in body
    assert '<button type="button" class="cs-acc-toggle" aria-expanded="false">' in body


def test_a_saved_state_reopens_the_last_view_and_its_open_groups(app, client, db_session):
    lead = _user(db_session, 'saved')
    _job(db_session, lead, 'Accounts Saved Job')
    login_as(client, app, lead, 'password123')
    payload = {'group': 'lead', 'open': {'client': [], 'lead': [str(lead.id)]}}
    assert _save(app, client, payload).status_code == 200

    body = client.get(_url(app)).get_data(as_text=True)
    assert '<th>Client</th>' in body
    assert f'<tbody class="cs-acc-group" data-key="{lead.id}">' in body
    # The other view keeps its own state: nothing open there.
    body = client.get(_url(app, group='client')).get_data(as_text=True)
    assert '<tbody class="cs-acc-group is-collapsed" data-key="none">' in body


def test_the_save_endpoint_rejects_bad_payloads(app, client, db_session):
    login_as(client, app, _user(db_session, 'badsave'), 'password123')
    for payload in ([], {'group': 'nope', 'open': {}}, {'group': 'client'},
                    {'group': 'client', 'open': {'client': 'x'}}):
        assert _save(app, client, payload).status_code == 400, payload


def test_the_save_endpoint_is_cs_only(app, client, db_session):
    login_as(client, app, _user(db_session, 'save-designer', role='designer'), 'password123')
    assert _save(app, client, {'group': 'client', 'open': {}}).status_code == 403


def test_an_emulating_admin_saves_the_emulated_users_view(app, client, db_session):
    admin = _user(db_session, 'save-admin', role='admin')
    cs = _user(db_session, 'save-cs', role='cs')
    login_as(client, app, admin, 'password123')
    _emulate(client, cs)
    assert _save(app, client, {'group': 'lead', 'open': {'lead': ['7']}}).status_code == 200
    row = UserTableLayout.query.filter_by(user_id=cs.id, table_key=STATE_KEY).one()
    assert row.layout['group'] == 'lead'
    assert UserTableLayout.query.filter_by(user_id=admin.id, table_key=STATE_KEY).first() is None


def test_clean_state_keeps_only_well_formed_keys():
    state = clean_state({'group': 'lead', 'open': {'lead': ['3', 4, True, {'x': 1}, 'y' * 30, '3'],
                                                   'other': ['1']}})
    assert state == {'group': 'lead', 'open': {'client': [], 'lead': ['3', '4']}}
    assert clean_state(None) == {'group': 'client', 'open': {'client': [], 'lead': []}}


# ------ Declared contract between the page script and its markup ------

def test_the_markup_carries_every_declared_id_and_class():
    contract = _declared_contract()
    markup = _TEMPLATE.read_text(encoding='utf-8')
    for element_id in contract['ids'].values():
        assert f'id="{element_id}"' in markup, (
            f'accounts.html is missing id="{element_id}". Restore it, '
            f'or update TEMPLATE_CONTRACT in client_servicing_accounts.js.')
    for attr in contract['attributes'].values():
        assert re.search(re.escape(attr) + r'=["\']', markup), (
            f'accounts.html no longer sets {attr}. Restore it, '
            f'or update TEMPLATE_CONTRACT in client_servicing_accounts.js.')
    for name in contract['classes'].values():
        assert re.search(r'class="[^"]*(?<![\w-])' + re.escape(name) + r'(?![\w-])', markup), (
            f'accounts.html no longer uses class "{name}". Restore it, '
            f'or update TEMPLATE_CONTRACT in client_servicing_accounts.js.')
