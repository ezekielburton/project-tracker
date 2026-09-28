"""The Invoicing toolbar: the two server-side filters and the CSV export."""
import csv
import io
from datetime import date
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing


def _user(db_session, tag, role='cs'):
    user = User(name=f'Inv {tag}', email=f'cs-invfilter-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, user, name, **cs_kwargs):
    # project_value= seeds Project.value; the other kwargs go to the CS row.
    project = Project(name=name, cs_lead_id=user.id, created_by_id=user.id,
                      project_status='briefed',
                      value=cs_kwargs.pop('project_value', None))
    db_session.add(project)
    db_session.flush()
    if cs_kwargs:
        db_session.add(ClientServicing(project_id=project.id, **cs_kwargs))
        db_session.flush()
    return project


def _seed(db_session, user):
    _project(db_session, user, 'August Valid', invoice_month_date=date(2026, 8, 1),
             validation_status='valid', project_value=Decimal('100'),
             invoice_date=date(2026, 8, 12))
    _project(db_session, user, 'August Overdue', invoice_month_date=date(2026, 8, 1),
             validation_status='overdue', project_value=Decimal('200'))
    _project(db_session, user, 'September Valid', invoice_month_date=date(2026, 9, 1),
             validation_status='valid', project_value=Decimal('300'))
    _project(db_session, user, 'No Validation', invoice_month_date=date(2026, 9, 1))


def _get(app, client, endpoint, **kwargs):
    with app.test_request_context():
        url = url_for(endpoint, **kwargs)
    return client.get(url)


def test_invoice_month_filter_narrows_the_table(app, client, db_session):
    user = _user(db_session, 'a')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing',
                invoice_month='2026-08').get_data(as_text=True)
    assert 'August Valid' in html
    assert 'August Overdue' in html
    assert 'September Valid' not in html


def test_validation_filter_narrows_the_table(app, client, db_session):
    user = _user(db_session, 'b')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing',
                validation='overdue').get_data(as_text=True)
    assert 'August Overdue' in html
    assert 'August Valid' not in html


def test_not_set_matches_projects_with_no_validation(app, client, db_session):
    user = _user(db_session, 'c')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing',
                validation='none').get_data(as_text=True)
    assert 'No Validation' in html
    assert 'August Valid' not in html


def test_the_two_filters_combine(app, client, db_session):
    user = _user(db_session, 'd')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing',
                invoice_month='2026-08', validation='valid').get_data(as_text=True)
    assert 'August Valid' in html
    assert 'August Overdue' not in html
    assert 'September Valid' not in html


def test_an_unknown_validation_code_shows_everything(app, client, db_session):
    """An unknown validation code is ignored, so a bad URL doesn't empty the table."""
    user = _user(db_session, 'e')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing',
                validation='nonsense').get_data(as_text=True)
    assert 'August Valid' in html
    assert 'September Valid' in html


def test_closed_projects_stay_out_of_the_filtered_set(app, client, db_session):
    from datetime import datetime
    user = _user(db_session, 'f')
    _project(db_session, user, 'Closed August', invoice_month_date=date(2026, 8, 1),
             validation_status='valid', closed_at=datetime.utcnow())
    _project(db_session, user, 'Open August', invoice_month_date=date(2026, 8, 1),
             validation_status='valid')
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing',
                invoice_month='2026-08').get_data(as_text=True)
    assert 'Open August' in html
    assert 'Closed August' not in html


def test_export_returns_the_filtered_rows_as_raw_csv(app, client, db_session):
    user = _user(db_session, 'g')
    _seed(db_session, user)
    login_as(client, app, user, 'password123')

    resp = _get(app, client, 'client_servicing.invoicing_export', invoice_month='2026-08')
    assert resp.status_code == 200
    assert 'text/csv' in resp.headers['Content-Type']
    assert 'attachment' in resp.headers['Content-Disposition']

    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    names = {r['Project'] for r in rows}
    assert names == {'August Valid', 'August Overdue'}

    valid = next(r for r in rows if r['Project'] == 'August Valid')
    # Raw, not display-formatted: ISO date and a plain number.
    assert valid['Invoice Date'] == '2026-08-12'
    assert valid['Project Value AED'] == '100.00'
    assert valid['Validation'] == 'valid'
    assert valid['Invoice Month'] == '2026-08'


def test_export_is_gated_like_the_page(app, client, db_session):
    user = _user(db_session, 'h', role='designer')
    login_as(client, app, user, 'password123')
    assert _get(app, client, 'client_servicing.invoicing_export').status_code == 403
