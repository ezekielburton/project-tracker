"""Coverage for the Monthly Summary rollup (lib/summary.py)."""
from datetime import date
from decimal import Decimal

from app.modules.core.shared.models import User, Project
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib import summary as summary_lib


def _lead(db_session):
    u = User(name='Sum Lead', email='cs-sum-lead@example.com', role='cs')
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _project(db_session, lead, name, status='briefed', due=None, **cs):
    p = Project(name=name, cs_lead_id=lead.id, created_by_id=lead.id,
                project_status=status, first_output_deadline=due)
    db_session.add(p)
    db_session.flush()
    if cs:
        db_session.add(ClientServicing(project_id=p.id, **cs))
        db_session.flush()
    return p


def _seed_march_year(db_session):
    lead = _lead(db_session)
    # March 2026 — invoiced, LPO, valid
    _project(db_session, lead, 'A invoiced', invoice_date=date(2026, 3, 10),
             project_value=Decimal('100'), invoice_amount=Decimal('90'),
             lpo='LPO-A', validation_status='valid')
    # March 2026 — LPO, not invoiced (bucketed by removal date)
    _project(db_session, lead, 'B confirmed', removal_date=date(2026, 3, 20),
             project_value=Decimal('50'), lpo='LPO-B')
    # March 2026 — no LPO (bucketed by due date), stuck
    _project(db_session, lead, 'C stuck', due=date(2026, 3, 25),
             project_value=Decimal('30'))
    # No dates anywhere → excluded
    _project(db_session, lead, 'D no dates', project_value=Decimal('999'))
    # Draft → excluded even though it has an invoice date
    _project(db_session, lead, 'E draft', status='draft',
             invoice_date=date(2026, 3, 1), project_value=Decimal('777'))
    # May 2026 — invoiced
    _project(db_session, lead, 'F may', invoice_date=date(2026, 5, 1),
             project_value=Decimal('200'), invoice_amount=Decimal('200'), lpo='LPO-F')
    return lead


def test_year_summary_buckets_and_sums(db_session):
    _seed_march_year(db_session)
    rows, total = summary_lib.year_summary(2026)
    march = rows[2]
    assert march['month'] == 3
    assert march['pipeline'] == 180        # 100 + 50 + 30
    assert march['confirmed'] == 150       # 100 + 50 (both have LPO)
    assert march['invoiced'] == 90         # only A invoiced
    assert march['stuck'] == 1             # C has no LPO
    assert march['progress'] == 60         # 90 / 150

    may = rows[4]
    assert may['pipeline'] == 200 and may['invoiced'] == 200

    assert total['pipeline'] == 380        # 180 + 200 (D and draft excluded)
    assert total['invoiced'] == 290


def test_empty_month_is_zero(db_session):
    _seed_march_year(db_session)
    rows, _ = summary_lib.year_summary(2026)
    jan = rows[0]
    assert jan['pipeline'] == 0 and jan['confirmed'] == 0 and jan['stuck'] == 0
    assert jan['progress'] == 0


def test_due_this_month_only_uninvoiced(db_session):
    _seed_march_year(db_session)
    due = summary_lib.due_this_month(2026, 3)
    names = sorted(d['project'] for d in due)
    assert names == ['B confirmed', 'C stuck']   # A invoiced, D/draft/May excluded
