"""services/report_feed.py: the CS figures the Reports module reads."""
from datetime import date, datetime
from decimal import Decimal

from app.modules.core.shared.models import User, Project
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.services import report_feed

START, END = date(2026, 9, 28), date(2026, 10, 2)
START_UTC, END_UTC = datetime(2026, 9, 27, 20), datetime(2026, 10, 2, 20)


def _user(db_session, tag, role='cs'):
    u = User(name=f'Feed {tag}', email=f'cs-feed-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _job(db_session, tag, lead, owner=None, install=None, value=10, job=True, **cs):
    p = Project(name=f'Feed {tag}', created_by_id=lead.id, cs_lead_id=lead.id,
                project_owner_id=owner.id if owner else None, project_status='briefed',
                installation_date=install, value=value, job_number=f'FEED-{tag}' if job else None)
    db_session.add(p)
    db_session.flush()
    if cs:
        db_session.add(ClientServicing(project_id=p.id, **cs))
        db_session.flush()
    return p


def _mine(rows, *projects):
    """Only the rows for projects this test made; the test database may hold others."""
    ids = {p.id for p in projects}
    return [r for r in rows if r['project_id'] in ids]


def test_closed_in_window_credits_lead_and_owner(db_session):
    lead, owner = _user(db_session, 'cl'), _user(db_session, 'co', 'project_owner')
    inside = _job(db_session, 'in', lead, owner, closed_at=datetime(2026, 9, 30, 9))
    outside = _job(db_session, 'out', lead, closed_at=datetime(2026, 10, 3, 9))
    rows = _mine(report_feed.closed_between(START_UTC, END_UTC), inside, outside)
    assert [r['project_id'] for r in rows] == [inside.id]
    assert rows[0]['people'] == [lead.id, owner.id]


def test_invoiced_skips_no_invoice_needed(db_session):
    lead = _user(db_session, 'inv')
    billed = _job(db_session, 'billed', lead, invoice_date=date(2026, 9, 29), invoice_amount=Decimal('500'))
    skip = _job(db_session, 'skip', lead, invoice_date=date(2026, 9, 29), invoice_needed=False)
    rows = _mine(report_feed.invoiced_between(START, END), billed, skip)
    assert [(r['project_id'], r['amount']) for r in rows] == [(billed.id, Decimal('500'))]


def test_waiting_to_invoice_longest_first(db_session):
    lead = _user(db_session, 'wait')
    old = _job(db_session, 'old', lead, closed_at=datetime(2026, 9, 18, 9))
    new = _job(db_session, 'new', lead, closed_at=datetime(2026, 9, 30, 9))
    paid = _job(db_session, 'paid', lead, closed_at=datetime(2026, 9, 1, 9), invoice_date=date(2026, 9, 2))
    rows = _mine(report_feed.waiting_to_invoice(date(2026, 10, 5)), old, new, paid)
    assert [(r['project_id'], r['days']) for r in rows] == [(old.id, 17), (new.id, 5)]


def test_installs_done_when_installed_or_later(db_session):
    lead = _user(db_session, 'ins')
    hit = _job(db_session, 'hit', lead, install=date(2026, 9, 30), cs_status='Installed')
    miss = _job(db_session, 'miss', lead, install=date(2026, 10, 1), cs_status='In Production')
    done = {r['project_id']: r['done'] for r in _mine(report_feed.installs_between(START, END), hit, miss)}
    assert done == {hit.id: True, miss.id: False}


def test_incomplete_lists_what_is_missing(db_session):
    lead = _user(db_session, 'gap')
    gap = _job(db_session, 'gap', lead, install=date(2026, 11, 1), job=False)
    full = _job(db_session, 'full', lead, install=date(2026, 11, 1))
    rows = {r['project_id']: r['missing'] for r in _mine(report_feed.incomplete(), gap, full)}
    assert rows == {gap.id: ['job number']}
