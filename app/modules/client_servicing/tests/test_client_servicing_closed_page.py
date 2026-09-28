"""The Closed Projects page — access, what it lists, month grouping, the
KPI cards, the date filters, and marking a pending project invoiced."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib import closed as closed_lib


def _user(db_session, tag, role='cs'):
    user = User(name=f'Closed {tag}', email=f'cs-closedpage-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _closed(db_session, user, name, when, value=None, invoice_date=None, invoice_needed=None):
    project = Project(name=name, cs_lead_id=user.id, created_by_id=user.id,
                      project_status='briefed', value=value)
    db_session.add(project)
    db_session.flush()
    db_session.add(ClientServicing(
        project_id=project.id, closed_at=when, closed_by_id=user.id,
        invoice_date=invoice_date, invoice_needed=invoice_needed,
    ))
    db_session.flush()
    return project


def _live(db_session, user, name):
    project = Project(name=name, cs_lead_id=user.id, created_by_id=user.id,
                      project_status='briefed')
    db_session.add(project)
    db_session.flush()
    return project


def _page(app, client, **kwargs):
    with app.test_request_context():
        url = url_for('client_servicing.closed', **kwargs)
    return client.get(url)


def test_closed_page_forbidden_for_a_disallowed_role(app, client, db_session):
    user = _user(db_session, 'a', role='designer')
    login_as(client, app, user, 'password123')
    assert _page(app, client).status_code == 403


def test_closed_page_opens_for_a_project_owner(app, client, db_session):
    """Project owners can open the closed-projects page."""
    user = _user(db_session, 'b', role='project_owner')
    login_as(client, app, user, 'password123')
    assert _page(app, client).status_code == 200


def test_only_closed_projects_are_listed(app, client, db_session):
    user = _user(db_session, 'c')
    _closed(db_session, user, 'Closed Gondola End', datetime(date.today().year, 3, 4))
    _live(db_session, user, 'Live Gondola End')
    login_as(client, app, user, 'password123')

    html = _page(app, client).get_data(as_text=True)
    assert 'Closed Gondola End' in html
    assert 'Live Gondola End' not in html


def test_rows_group_by_closing_month(app, db_session):
    user = _user(db_session, 'd')
    year = date.today().year
    _closed(db_session, user, 'March One', datetime(year, 3, 4), value=Decimal('100'))
    _closed(db_session, user, 'March Two', datetime(year, 3, 20), value=Decimal('50'))
    _closed(db_session, user, 'January One', datetime(year, 1, 9), value=Decimal('25'))

    groups = closed_lib.month_groups(closed_lib.closed_projects(year=year))
    labels = [g['label'] for g in groups]
    assert labels == [f'March {year}', f'January {year}']
    assert groups[0]['count'] == 2
    assert groups[0]['total'] == Decimal('150')
    assert groups[1]['total'] == Decimal('25')


def test_kpis_count_by_period(app, db_session):
    today = date.today()
    user = _user(db_session, 'e')
    _closed(db_session, user, 'Closed Today', datetime.combine(today, datetime.min.time()),
            value=Decimal('200'))
    # January 1st is always in the year window, and usually outside week and month.
    _closed(db_session, user, 'Closed In January', datetime(today.year, 1, 1),
            value=Decimal('300'))

    cards = {c['key']: c for c in closed_lib.kpis(today)}
    assert cards['year']['count'] == 2
    assert cards['year']['value'] == Decimal('500')

    # In January's first week both fall in the week window, so derive the count.
    week_start = today - timedelta(days=today.weekday())
    in_week = 2 if date(today.year, 1, 1) >= week_start else 1
    assert cards['week']['count'] == in_week


def test_filters_narrow_by_year_quarter_and_month(app, db_session):
    user = _user(db_session, 'f')
    _closed(db_session, user, 'Q1 Job', datetime(2026, 2, 10))
    _closed(db_session, user, 'Q3 Job', datetime(2026, 8, 10))
    _closed(db_session, user, 'Old Job', datetime(2025, 8, 10))

    def names(**kwargs):
        return {p.name for p in closed_lib.closed_projects(**kwargs)}

    assert names(year=2026) == {'Q1 Job', 'Q3 Job'}
    assert names(year=2025) == {'Old Job'}
    assert names(year=2026, quarter=1) == {'Q1 Job'}
    assert names(year=2026, month=8) == {'Q3 Job'}
    assert names(year=2026, quarter=3, month=8) == {'Q3 Job'}


def test_mark_invoiced_is_offered_to_finance_editors_only(app, client, db_session):
    year = date.today().year
    user = _user(db_session, 'g')
    _closed(db_session, user, 'Pending Job', datetime(year, 4, 2), invoice_needed=True)
    login_as(client, app, user, 'password123')
    assert 'cs-closed-mark' in _page(app, client, year=year).get_data(as_text=True)

    owner = _user(db_session, 'h', role='project_owner')
    login_as(client, app, owner, 'password123')
    assert 'cs-closed-mark' not in _page(app, client, year=year).get_data(as_text=True)


def test_marking_invoiced_flips_the_state(app, client, db_session):
    """Setting invoice_date via the update_field endpoint moves the project to 'invoiced'."""
    year = date.today().year
    user = _user(db_session, 'i')
    project = _closed(db_session, user, 'Now Invoiced', datetime(year, 4, 2),
                      invoice_needed=True)
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.update_field', project_id=project.id)
    resp = client.patch(url, json={'field': 'invoice_date', 'value': f'{year}-04-30'})
    assert resp.status_code == 200

    cs = ClientServicing.query.filter_by(project_id=project.id).one()
    assert cs.invoice_date == date(year, 4, 30)
    assert cs.close_invoice_state == 'invoiced'


def test_the_closed_entry_is_in_the_module_sidebar(app, client, db_session):
    user = _user(db_session, 'j')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        table_url = url_for('client_servicing.table')
        closed_url = url_for('client_servicing.closed')
    assert closed_url in client.get(table_url).get_data(as_text=True)
