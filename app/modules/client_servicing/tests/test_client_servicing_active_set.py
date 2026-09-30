"""One active set: a cancelled job waiting for close-out drops off the
Dashboard, Invoicing By Project and its export alike, so every page counts
the same jobs. The Monthly Summary still counts it."""
import csv
import io
from datetime import date, datetime
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib import summary as summary_lib
from app.modules.client_servicing.lib.dashboard import dashboard_context


def _user(db_session, tag, role='cs'):
    user = User(name=f'Active {tag}', email=f'cs-activeset-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, user, name, cancelled=False, closed=False, **cs_kwargs):
    project = Project(name=name, cs_lead_id=user.id, created_by_id=user.id,
                      project_status='briefed', value=cs_kwargs.pop('value', None))
    if cancelled:
        project.cancelled_at = datetime.utcnow()
    db_session.add(project)
    db_session.flush()
    if closed:
        cs_kwargs.setdefault('closed_at', datetime.utcnow())
        cs_kwargs.setdefault('closed_by_id', user.id)
    if cs_kwargs:
        db_session.add(ClientServicing(project_id=project.id, **cs_kwargs))
        db_session.flush()
    return project


def _seed(db_session, user):
    _project(db_session, user, 'Live Gondola End')
    _project(db_session, user, 'Live Floor Graphic')
    _project(db_session, user, 'Cancelled Awaiting Close', cancelled=True)
    _project(db_session, user, 'Closed Totem', closed=True)


def _get(app, client, endpoint, **kwargs):
    with app.test_request_context():
        url = url_for(endpoint, **kwargs)
    return client.get(url)


def test_by_project_drops_a_cancelled_job_awaiting_close_out(app, client, db_session):
    user = _user(db_session, 'a')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing').get_data(as_text=True)
    assert 'Live Gondola End' in html
    assert 'Cancelled Awaiting Close' not in html


def test_export_drops_a_cancelled_job_awaiting_close_out(app, client, db_session):
    user = _user(db_session, 'b')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    body = _get(app, client, 'client_servicing.invoicing_export').get_data(as_text=True)
    names = sorted(row['Project'] for row in csv.DictReader(io.StringIO(body)))
    assert names == ['Live Floor Graphic', 'Live Gondola End']


def test_dashboard_invoicing_and_table_count_the_same_jobs(app, client, db_session):
    user = _user(db_session, 'c')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        dashboard_active = dashboard_context(user)['kpis']['active']
    invoicing = _get(app, client, 'client_servicing.invoicing').get_data(as_text=True)
    table = _get(app, client, 'client_servicing.table_rows').get_data(as_text=True)

    assert dashboard_active == 2
    assert invoicing.count('data-project-id="') == 2
    assert table.count('<tr data-project-id="') == 2


def test_monthly_summary_still_counts_a_cancelled_job(app, db_session):
    user = _user(db_session, 'd')
    _project(db_session, user, 'Cancelled But Billable', cancelled=True,
             value=Decimal('250'), invoice_month_date=date(2026, 6, 1))

    rows, _ = summary_lib.year_summary(2026)
    assert rows[5]['pipeline'] == Decimal('250')
