"""
Seed / wipe demo data for the Invoicing tab.

    python seed_invoicing_demo.py          # wipe demo rows, then reseed
    python seed_invoicing_demo.py --wipe   # wipe demo rows only

Everything created is tagged so the wipe only ever touches demo data:
  - users:    email ends with @invdemo.local
  - clients:  name starts with "Demo — "
  - projects: name starts with "Demo — "
Real data is never matched. Run against a LOCAL database.
"""
import argparse
from datetime import date
from decimal import Decimal

from app import create_app
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User, Project, Client
from app.modules.client_servicing.models import ClientServicing

USER_DOMAIN = '@invdemo.local'
TAG = 'Demo — '
PASSWORD = 'Demo2026!'
YEAR = date.today().year
TODAY = date.today()


def d(month, day):
    return date(YEAR, month, day)


def wipe():
    """Delete only the tagged demo rows, in FK-safe order."""
    demo_project_ids = [p.id for p in Project.query.filter(Project.name.like(TAG + '%')).all()]
    if demo_project_ids:
        ClientServicing.query.filter(
            ClientServicing.project_id.in_(demo_project_ids)
        ).delete(synchronize_session=False)
    Project.query.filter(Project.name.like(TAG + '%')).delete(synchronize_session=False)
    Client.query.filter(Client.name.like(TAG + '%')).delete(synchronize_session=False)
    User.query.filter(User.email.like('%' + USER_DOMAIN)).delete(synchronize_session=False)
    db.session.commit()
    print('Wiped demo rows (' + str(len(demo_project_ids)) + ' demo projects).')


def _user(name, role):
    u = User(name=TAG + name, email=name.lower().replace(' ', '.') + USER_DOMAIN, role=role)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.flush()
    return u


def _client(name, creator):
    c = Client(name=TAG + name, created_by_id=creator.id)
    db.session.add(c)
    db.session.flush()
    return c


def seed():
    # Login users — one per role, to exercise the gating.
    finance = _user('Finance User', 'finance')
    cs = _user('CS User', 'cs')
    mgmt = _user('Management User', 'management')
    owner = _user('Owner User', 'project_owner')

    al = _client('Al Barakah', cs)
    carrefour = _client('Carrefour', cs)
    png = _client('P&G', cs)

    # Each entry: project name, client, status, project due date, then the
    # ClientServicing finance fields. Spread across the year with every
    # validation state and both invoiced / not-invoiced cases.
    m = TODAY.month
    demo = [
        # Invoiced & valid, earlier months
        dict(name='Storefront Refresh', client=al, due=d(1, 20),
             lpo='8006435879', lpo_date=d(1, 5), project_value='42000', invoice_number='260101',
             invoice_date=d(1, 15), invoice_amount='42000', invoice_month='Jan',
             cost_to_client='42000', inward_cost='28000', gr_received=True, validation_status='valid'),
        dict(name='Kiosk Build', client=carrefour, due=d(2, 25),
             lpo='2017311469', lpo_date=d(2, 3), project_value='10550', invoice_number='260118',
             invoice_date=d(2, 20), invoice_amount='10550', invoice_month='Feb',
             cost_to_client='10550', inward_cost='6200', gr_received=True, validation_status='valid'),
        dict(name='Brand Wall', client=png, due=d(3, 28),
             lpo='8006772124', lpo_date=d(3, 6), project_value='19175', invoice_number='260140',
             invoice_date=d(3, 17), invoice_amount='19175', invoice_month='Mar',
             cost_to_client='19175', inward_cost='12000', gr_received=True, validation_status='valid'),

        # LPO but not invoiced yet (bucketed by removal date) — pending
        dict(name='Aisle Takeover', client=carrefour, due=d(4, 15),
             lpo='8006781140', lpo_date=d(4, 2), project_value='64300', removal_date=d(4, 10),
             invoice_month='Apr', cost_to_client='64300', inward_cost='41000',
             gr_received=False, validation_status='pending'),

        # No LPO (bucketed by due date) — stuck / no_lpo
        dict(name='Breast Cancer Event', client=png, due=d(5, 12),
             project_value='148500', invoice_month='May', validation_status='no_lpo'),

        # Overdue: old removal date, still not invoiced
        dict(name='Legacy Endcap', client=al, due=d(6, 8),
             lpo='8006990011', lpo_date=d(6, 1), project_value='23000', removal_date=d(6, 5),
             invoice_month='Jun', gr_received=False, validation_status='overdue'),

        # A mid-year invoiced one
        dict(name='Summer Gondola', client=png, due=d(7, 20),
             lpo='8007001234', lpo_date=d(7, 4), project_value='55000', invoice_number='260233',
             invoice_date=d(7, 18), invoice_amount='55000', invoice_month='Jul',
             cost_to_client='55000', inward_cost='33000', gr_received=True, validation_status='valid'),

        # Current-month spread — these drive the "Due this month" list
        dict(name='This Month Invoiced', client=al, due=d(m, 22),
             lpo='8007100001', lpo_date=d(m, 2), project_value='31000', invoice_number='260300',
             invoice_date=d(m, 10), invoice_amount='31000', invoice_month=TODAY.strftime('%b'),
             cost_to_client='31000', inward_cost='19000', gr_received=True, validation_status='valid'),
        dict(name='This Month Pending', client=carrefour, due=d(m, 24),
             lpo='8007100002', lpo_date=d(m, 3), project_value='27500', removal_date=d(m, 6),
             invoice_month=TODAY.strftime('%b'), gr_received=False, validation_status='pending'),
        dict(name='This Month No LPO', client=png, due=d(m, 26),
             project_value='18000', invoice_month=TODAY.strftime('%b'), validation_status='no_lpo'),
        dict(name='This Month Overdue', client=al, due=d(m, 9),
             lpo='8007100003', lpo_date=d(m, 1), project_value='12000', removal_date=d(m, 2),
             invoice_month=TODAY.strftime('%b'), gr_received=False, validation_status='overdue'),

        # No dates anywhere → excluded from the rollup (proves the anchor rule)
        dict(name='No Dates Yet', client=png, due=None, project_value='9000'),
    ]

    for row in demo:
        p = Project(
            name=TAG + row['name'],
            cs_lead_id=cs.id,
            project_owner_id=owner.id,
            created_by_id=cs.id,
            client_id=row['client'].id,
            client=row['client'].name,
            project_status='briefed',
            value=float(row['project_value']) if row.get('project_value') else None,
            first_output_deadline=row.get('due'),
            briefing_date=row.get('due'),
        )
        db.session.add(p)
        db.session.flush()

        cs_fields = {k: v for k, v in row.items() if k not in ('name', 'client', 'due')}
        # Money fields -> Decimal
        for money in ('project_value', 'invoice_amount', 'cost_to_client', 'inward_cost'):
            if money in cs_fields:
                cs_fields[money] = Decimal(cs_fields[money])
        db.session.add(ClientServicing(project_id=p.id, **cs_fields))

    # A draft — must NOT appear anywhere (proves drafts are hidden)
    draft = Project(name=TAG + 'Hidden Draft', cs_lead_id=cs.id, created_by_id=cs.id,
                    client_id=png.id, client=png.name, project_status='draft',
                    value=99999.0, first_output_deadline=d(m, 15))
    db.session.add(draft)
    db.session.flush()
    db.session.add(ClientServicing(project_id=draft.id, project_value=Decimal('99999'),
                                   invoice_date=d(m, 1), lpo='DRAFT-LPO'))

    db.session.commit()
    print('Seeded ' + str(len(demo)) + ' demo projects (+1 hidden draft) across ' + str(YEAR) + '.')
    print('Demo logins (password: ' + PASSWORD + '):')
    for u in (finance, cs, mgmt, owner):
        print('  ' + u.role.ljust(14) + u.email)


def main():
    ap = argparse.ArgumentParser(description='Seed/wipe Invoicing demo data.')
    ap.add_argument('--wipe', action='store_true', help='wipe demo rows only (no reseed)')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        wipe()
        if not args.wipe:
            seed()


if __name__ == '__main__':
    main()
