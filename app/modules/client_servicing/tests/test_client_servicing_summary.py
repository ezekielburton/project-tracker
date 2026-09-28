"""The Monthly Summary rollup (lib/summary.py)."""
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
    # project_value= seeds Project.value; the other kwargs go to the CS row.
    p = Project(name=name, cs_lead_id=lead.id, created_by_id=lead.id,
                project_status=status, first_output_deadline=due,
                value=cs.pop('project_value', None))
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
    # March 2026 — no LPO, bucketed by its planned invoice month, stuck
    _project(db_session, lead, 'C stuck', invoice_month_date=date(2026, 3, 1),
             project_value=Decimal('30'))
    # A design deadline is not a billing date → excluded
    _project(db_session, lead, 'D due date only', due=date(2026, 3, 25),
             project_value=Decimal('999'))
    # No dates anywhere → excluded
    _project(db_session, lead, 'D2 no dates', project_value=Decimal('888'))
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
    assert march['stuck'] == 1              # C has no LPO
    assert march['stuck_amount'] == 30       # C: no LPO, value 30             
    assert march['progress'] == 60         # 90 / 150

    may = rows[4]
    assert may['pipeline'] == 200 and may['invoiced'] == 200

    assert total['pipeline'] == 380        # 180 + 200 (due-date-only, no-dates and draft all excluded)
    assert total['invoiced'] == 290
    assert total['stuck_amount'] == 30


def test_empty_month_is_zero(db_session):
    _seed_march_year(db_session)
    rows, _ = summary_lib.year_summary(2026)
    jan = rows[0]
    assert jan['pipeline'] == 0 and jan['confirmed'] == 0 and jan['stuck'] == 0
    assert jan['stuck_amount'] == 0


def test_due_this_month_only_uninvoiced(db_session):
    _seed_march_year(db_session)
    due = summary_lib.due_this_month(2026, 3)
    names = sorted(d['project'] for d in due)
    assert names == ['B confirmed', 'C stuck']   # A invoiced, D/draft/May excluded


def test_a_design_deadline_never_puts_a_project_in_a_month(db_session):
    """first_output_deadline (the design deadline) never buckets a project into a month."""
    lead = _lead(db_session)
    _project(db_session, lead, 'Design deadline only', due=date(2026, 7, 14),
             project_value=Decimal('400'))

    rows, total = summary_lib.year_summary(2026)
    assert rows[6]['pipeline'] == 0
    assert total['pipeline'] == 0


def test_the_planned_invoice_month_buckets_an_uninvoiced_project(db_session):
    lead = _lead(db_session)
    _project(db_session, lead, 'Planned for June', invoice_month_date=date(2026, 6, 1),
             project_value=Decimal('500'), lpo='LPO-J')

    rows, _ = summary_lib.year_summary(2026)
    assert rows[5]['pipeline'] == 500
    assert rows[5]['confirmed'] == 500
    assert rows[5]['invoiced'] == 0


def test_an_actual_invoice_date_beats_the_planned_month(db_session):
    """Planned for June, actually invoiced in July — it counts in July."""
    lead = _lead(db_session)
    _project(db_session, lead, 'Slipped to July', invoice_month_date=date(2026, 6, 1),
             invoice_date=date(2026, 7, 3), invoice_amount=Decimal('300'),
             project_value=Decimal('300'), lpo='LPO-S')

    rows, _ = summary_lib.year_summary(2026)
    assert rows[5]['pipeline'] == 0
    assert rows[6]['pipeline'] == 300
    assert rows[6]['invoiced'] == 300
