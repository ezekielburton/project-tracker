"""Accounts: grouping, the secondary CS counted once, totals, month parity
with the Monthly Summary, the finance gate on invoicing figures, the load
panel, and a flat query count."""
from datetime import date, datetime
from decimal import Decimal

from app.modules.core.shared.models import Client, Project, ProjectSecondaryCS, User
from app.modules.core.shared.testing import count_queries
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib.accounts import accounts_view, parse_month
from app.modules.client_servicing.lib.summary import year_summary

SEP = (2026, 9)


def _user(db_session, tag, role='cs'):
    u = User(name=f'Acc {tag}', email=f'cs-acc-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _client(db_session, name, creator):
    c = Client(name=name, created_by_id=creator.id)
    db_session.add(c)
    db_session.flush()
    return c


def _job(db_session, tag, lead, client=None, value=None, secondary=(), cancelled=False, **cs):
    p = Project(name=f'Acc {tag}', created_by_id=lead.id, cs_lead_id=lead.id,
                project_status='briefed', value=value,
                client_id=client.id if client else None)
    if cancelled:
        p.cancelled_at = datetime(2026, 9, 1)
    db_session.add(p)
    db_session.flush()
    if cs:
        db_session.add(ClientServicing(project_id=p.id, **cs))
    for person in secondary:
        db_session.add(ProjectSecondaryCS(project_id=p.id, user_id=person.id))
    db_session.flush()
    return p


def _admin(db_session):
    return _user(db_session, 'admin', role='admin')


def test_groups_by_client_largest_first_and_totals_add_up(db_session):
    admin, lead = _admin(db_session), _user(db_session, 'lead')
    big, small = _client(db_session, 'Acc Big', lead), _client(db_session, 'Acc Small', lead)
    _job(db_session, 'b1', lead, big, value=500)
    _job(db_session, 'b2', lead, big, value=300, invoice_date=date(2026, 9, 3), invoice_amount=Decimal('300'))
    _job(db_session, 's1', lead, small, value=100)

    view = accounts_view(admin, group='client')
    names = [g['name'] for g in view['groups']]
    assert names.index('Acc Big') < names.index('Acc Small')
    for g in view['groups']:
        assert g['value'] == sum(r['value'] for r in g['rows'])
        assert g['invoiced'] == sum(r['invoiced'] or 0 for r in g['rows'])
    assert view['kpis']['value'] == sum(g['value'] for g in view['groups'])
    assert view['kpis']['jobs'] == sum(g['count'] for g in view['groups'])


def test_a_secondary_cs_is_a_tag_and_the_job_counts_once(db_session):
    admin, lead, second = _admin(db_session), _user(db_session, 'l2'), _user(db_session, 's2')
    job = _job(db_session, 'shared', lead, value=200, secondary=[second])

    view = accounts_view(admin, group='lead')
    rows = [r for g in view['groups'] for r in g['rows'] if r['id'] == job.id]
    assert len(rows) == 1 and rows[0]['lead'] == lead.name
    assert rows[0]['secondary'] == [second.name]
    assert second.name not in [g['name'] for g in view['groups']]
    assert [r['jobs'] for r in view['load'] if r['lead_id'] == second.id] == []


def test_a_job_with_no_client_groups_under_no_client(db_session):
    admin, lead = _admin(db_session), _user(db_session, 'l3')
    _job(db_session, 'orphan', lead, value=50)
    assert 'No client' in [g['name'] for g in accounts_view(admin)['groups']]


def test_month_value_matches_the_monthly_summary_pipeline(db_session):
    admin, lead = _admin(db_session), _user(db_session, 'l4')
    _job(db_session, 'inv', lead, value=400, invoice_date=date(2026, 9, 2), invoice_amount=Decimal('400'))
    _job(db_session, 'month', lead, value=250, invoice_month_date=date(2026, 9, 1))
    _job(db_session, 'removal', lead, value=125.5, removal_date=date(2026, 9, 20))
    _job(db_session, 'oct', lead, value=999, invoice_month_date=date(2026, 10, 1))

    view = accounts_view(admin, month=SEP)
    rows, _total = year_summary(2026)
    assert view['kpis']['value'] == rows[8]['pipeline']
    assert view['month_label'] == 'Sep 2026'


def test_a_job_with_no_billing_month_shows_only_under_all_time(db_session):
    admin, lead = _admin(db_session), _user(db_session, 'l5')
    job = _job(db_session, 'undated', lead, value=10)

    def ids(view):
        return {r['id'] for g in view['groups'] for r in g['rows']}

    assert job.id in ids(accounts_view(admin))
    assert job.id not in ids(accounts_view(admin, month=SEP))
    assert parse_month('2026-13') is None and parse_month('junk') is None
    assert parse_month('2026-09') == SEP


def test_invoicing_figures_are_left_out_without_finance(db_session, owner_without_finance):
    owner, lead = _user(db_session, 'po', role='project_owner'), _user(db_session, 'l6')
    _job(db_session, 'po1', lead, value=80, invoice_date=date(2026, 9, 1), invoice_amount=Decimal('80'))

    view = accounts_view(owner)
    assert view['finance'] is False
    assert 'invoiced' not in view['kpis'] and 'not_invoiced' not in view['kpis']
    assert all('invoiced' not in r for g in view['groups'] for r in g['rows'])
    assert all('invoiced' not in g for g in view['groups'])
    assert all('invoiced' not in r and 'invoiced_amount' not in r for r in view['load'])
    assert 'invoiced' not in view['load_total']
    assert view['kpis']['value'] > 0      # Value stays visible to every page role


def test_load_panel_active_no_lpo_and_total(db_session):
    admin, lead = _admin(db_session), _user(db_session, 'l7')
    _job(db_session, 'open', lead, value=100, removal_date=date(2026, 9, 5))
    _job(db_session, 'done', lead, value=200, lpo='LPO-1',
         invoice_date=date(2026, 9, 6), invoice_amount=Decimal('200'))
    _job(db_session, 'gone', lead, value=300, cancelled=True, removal_date=date(2026, 9, 7))

    view = accounts_view(admin, month=SEP)
    row = next(r for r in view['load'] if r['lead_id'] == lead.id)
    assert (row['jobs'], row['active'], row['invoiced'], row['no_lpo']) == (3, 1, 1, 1)
    assert row['value'] == Decimal('600') and row['invoiced_amount'] == Decimal('200')
    for key in ('jobs', 'active', 'no_lpo', 'value', 'invoiced', 'invoiced_amount'):
        assert view['load_total'][key] == sum(r[key] for r in view['load'])
    assert view['kpis']['not_invoiced'] == Decimal('100')


def test_query_count_stays_flat_as_jobs_grow(app, db_session):
    admin, lead, second = _admin(db_session), _user(db_session, 'l8'), _user(db_session, 's8')
    client = _client(db_session, 'Acc Flat', lead)

    def seed(n, tag):
        for i in range(n):
            _job(db_session, f'{tag}{i}', lead, client, value=10 * i, secondary=[second],
                 removal_date=date(2026, 9, 1 + i % 20), lpo='L' if i % 2 else None)

    seed(3, 'a')
    with app.test_request_context(), count_queries() as small:
        accounts_view(admin, group='lead')
    seed(6, 'b')
    with app.test_request_context(), count_queries() as big:
        accounts_view(admin, group='lead')
    assert big[0] == small[0], (small[0], big[0])
