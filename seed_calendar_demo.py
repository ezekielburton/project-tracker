"""
Seed / wipe demo data for the Installation Calendar.

    python seed_calendar_demo.py          # wipe demo rows, then reseed
    python seed_calendar_demo.py --wipe   # wipe demo rows only

Everything created is tagged so the wipe only ever touches demo data and
never current projects:
  - users:   email ends with @caldemo.local
  - clients: name starts with "Cal Demo — "
  - projects: name starts with "Cal Demo — "
  - scopes:  name ends with " (demo)"
Installs are dated relative to TODAY so the Month grid, day drawer, Agenda
(next 30 days) and the KPIs all have something to show, across every risk
state plus a couple of manual risk overrides. Run against a LOCAL database.
"""
import argparse
import random
from datetime import date, timedelta

from app import create_app
from sqlalchemy import text

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User, Project, Client
from app.modules.client_servicing.models import ClientServicing, ClientServicingScope

USER_DOMAIN = '@caldemo.local'
TAG = 'Cal Demo — '
SCOPE_SUFFIX = ' (demo)'
PASSWORD = 'Demo2026!'
TODAY = date.today()


def _delete_project_children(ids):
    """Clear every row that references these projects, so deleting the
    projects can't hit a foreign-key constraint. Discovers the referencing
    tables/columns from the catalog, so it covers any child table (e.g.
    project_activity_seen) without hard-coding a list. Demo projects have
    no deliverables/submissions, so there are no grandchildren to order."""
    if not ids:
        return
    refs = db.session.execute(text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'projects' AND ccu.column_name = 'id'
    """)).fetchall()
    for table_name, column_name in refs:
        db.session.execute(
            text('DELETE FROM "%s" WHERE "%s" = ANY(:ids)' % (table_name, column_name)),
            {'ids': ids},
        )


def wipe():
    """Delete only the tagged demo rows, in FK-safe order."""
    demo_project_ids = [p.id for p in Project.query.filter(Project.name.like(TAG + '%')).all()]
    _delete_project_children(demo_project_ids)
    Project.query.filter(Project.name.like(TAG + '%')).delete(synchronize_session=False)
    Client.query.filter(Client.name.like(TAG + '%')).delete(synchronize_session=False)
    ClientServicingScope.query.filter(
        ClientServicingScope.name.like('%' + SCOPE_SUFFIX)
    ).delete(synchronize_session=False)
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


def _scope(name):
    s = ClientServicingScope(name=name + SCOPE_SUFFIX, active=True)
    db.session.add(s)
    db.session.flush()
    return s


def _off(days):
    return TODAY + timedelta(days=days)


def seed():
    cs = _user('CS User', 'cs')
    # A few CS leads so the "CS · <name>" line varies like the real sheet.
    leads = {n: _user(n, 'cs') for n in ('Maarij', 'Prim', 'Waseem', 'Mohsin', 'Zeeshan')}

    clients = {}

    def client(name):
        if name not in clients:
            clients[name] = _client(name, cs)
        return clients[name]

    scopes = {}

    def scope(name):
        if name not in scopes:
            scopes[name] = _scope(name)
        return scopes[name]

    # name, brand, lead, scope, install-offset (days from today), cs_status,
    # manual risk (None = auto), action_owner, next_action.
    # Auto-risk reminder: not-ready + <=2d = At Risk, <=7d = Attention, else
    # On Track; In Production/Installed = ready (On Track); Installed/invoicing
    # states = Done.
    demo = [
        ('Choco & CO KV', 'Choco & CO', 'Maarij', 'Gifting galaxy base', 0, 'Pending Approval', None, 'Rehan', 'Client approval pending'),
        ('BEAUTIVERSE MOE Zone A', 'BEAUTIVERSE MOE', 'Zeeshan', 'Main setup - new build', 0, 'In Production', None, 'Rehan', 'Installation'),
        ('Home Bakery Kiosk', 'Home Bakery Kiosk', 'Waseem', 'Refurb & Rebrand', 1, 'Briefing', None, 'Ravi', 'Timelines to be reconfirmed'),
        ('Mars Adnoc Barsha', 'Mars Adnoc', 'Prim', 'Rebranding', 1, 'In Production', None, 'Eddie', 'Production to be completed'),
        ('Mars Snackat Aisle', 'Mars Snackat', 'Waseem', 'New Production', 2, 'Pending Production', 'On Track', 'Eddie', 'On track — confirmed by ops'),
        ('Choco & CO Signages', 'Choco & CO', 'Maarij', 'Signages & headers', 3, 'Briefing', 'At Risk', 'Rehan', 'Installs soon, still planning'),
        ('Multiple Brands Run', 'Multiple brands', 'Waseem', 'New Production', 4, 'Pending Quotation', None, 'Eddie', 'Production schedule to confirm'),
        ('Gillette New Prod', 'Gillette', 'Mohsin', 'New Production', 6, 'Pending LPO', None, 'Eddie', 'Awaiting LPO'),
        ('Idubai - Beauty Build', 'Idubai - Beauty', 'Prim', 'Main setup - new build', 10, 'Briefing', None, 'Eddie', None),
        ('KFG Dubai Hills', 'KFG Dubai Hills', 'Maarij', 'Refurb & Rebrand', 12, 'In Production', None, 'Ravi', None),
        ('Cheetos 2x2', 'Cheetos 2x2', 'Mohsin', 'New Production', 18, 'Pending Approval', None, 'Eddie', None),
        ('KFG Ferrari', 'KFG Ferrari', 'Prim', 'Rebranding', 25, 'In Production', None, 'Ravi', None),
        ('ESF Office Intervention', 'ESF Office', 'Maarij', 'New Production', -4, 'Partial Invoicing', None, 'Eddie', None),
        ('Al Maya BTS', 'Al Maya', 'Waseem', 'Refurb & Rebrand', -2, 'Invoiced', None, 'Rehan', None),
    ]

    for name, brand, lead, sc, off, cs_status, risk, owner, nxt in demo:
        p = Project(
            name=TAG + name,
            cs_lead_id=leads[lead].id,
            created_by_id=cs.id,
            client_id=client(brand).id,
            client=client(brand).name,
            project_status='briefed',
            installation_date=_off(off),
            briefing_date=_off(off - 30),
        )
        db.session.add(p)
        db.session.flush()
        db.session.add(ClientServicing(
            project_id=p.id, scope_id=scope(sc).id, cs_status=cs_status,
            risk=risk, action_owner=owner, next_action=nxt,
            # Random qty, with a couple left blank to show the 'Set qty' prompt.
            install_qty=random.choice([1, 1, 2, 3, 4, 6, 12, None, None]),
        ))

    db.session.commit()
    print('Seeded ' + str(len(demo)) + ' demo installs around ' + TODAY.isoformat() + '.')
    print('Demo CS login (password: ' + PASSWORD + '):  ' + cs.email)


def main():
    ap = argparse.ArgumentParser(description='Seed/wipe Installation Calendar demo data.')
    ap.add_argument('--wipe', action='store_true', help='wipe demo rows only (no reseed)')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        wipe()
        if not args.wipe:
            seed()


if __name__ == '__main__':
    main()
