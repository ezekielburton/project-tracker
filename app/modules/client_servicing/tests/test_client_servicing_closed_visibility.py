"""Where a closed project shows and where it doesn't: gone from the Table,
the Invoicing By Project tab and the Dashboard; still counted in the
Monthly Summary and still on the Calendar, faded and read-only."""
from datetime import date, datetime
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib import summary as summary_lib
from app.modules.client_servicing.lib.calendar import build_install
from app.modules.client_servicing.lib.project_sets import active_projects


def _user(db_session, tag, role='cs'):
    user = User(name=f'Viewer {tag}', email=f'cs-closedvis-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, user, name, closed=False, install=None, **cs_kwargs):
    # project_value= seeds Project.value; the other kwargs go to the CS row.
    project = Project(
        name=name, cs_lead_id=user.id, created_by_id=user.id,
        project_status='briefed', installation_date=install,
        value=cs_kwargs.pop('project_value', None),
    )
    db_session.add(project)
    db_session.flush()
    if closed:
        cs_kwargs.setdefault('closed_at', datetime.utcnow())
        cs_kwargs.setdefault('closed_by_id', user.id)
    if cs_kwargs:
        db_session.add(ClientServicing(project_id=project.id, **cs_kwargs))
        db_session.flush()
    return project


def _get(app, client, endpoint, **kwargs):
    with app.test_request_context():
        url = url_for(endpoint, **kwargs)
    return client.get(url)


def test_closed_project_drops_off_the_table(app, client, db_session):
    user = _user(db_session, 'a')
    _project(db_session, user, 'Closed Endcap Run', closed=True)
    _project(db_session, user, 'Live Endcap Run')
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.table').get_data(as_text=True)
    assert 'Live Endcap Run' in html
    assert 'Closed Endcap Run' not in html


def test_closed_project_drops_off_invoicing_by_project(app, client, db_session):
    user = _user(db_session, 'b')
    _project(db_session, user, 'Closed Chiller Wrap', closed=True,
             project_value=Decimal('40'))
    _project(db_session, user, 'Live Chiller Wrap', project_value=Decimal('40'))
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.invoicing').get_data(as_text=True)
    assert 'Live Chiller Wrap' in html
    assert 'Closed Chiller Wrap' not in html


def test_a_project_with_no_cs_row_still_lists(app, client, db_session):
    """The closed filter left-joins, so a project with no CS row still lists."""
    user = _user(db_session, 'c')
    _project(db_session, user, 'Never Touched By CS')
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.table').get_data(as_text=True)
    assert 'Never Touched By CS' in html


def test_closed_project_still_counts_in_the_monthly_summary(app, db_session):
    """A closed project's invoice still counts in the month it was invoiced."""
    user = _user(db_session, 'd')
    _project(db_session, user, 'Closed But Invoiced', closed=True,
             invoice_date=date(2026, 5, 12), project_value=Decimal('100'),
             invoice_amount=Decimal('100'), lpo='LPO-CLOSED')

    rows, total = summary_lib.year_summary(2026)
    may = rows[4]
    assert may['invoiced'] == Decimal('100')
    assert may['pipeline'] == Decimal('100')
    assert total['invoiced'] == Decimal('100')


def test_closed_install_stays_on_the_calendar_and_is_marked(app, client, db_session):
    today = date.today()
    user = _user(db_session, 'e')
    project = _project(db_session, user, 'Closed Install Job', closed=True, install=today)
    login_as(client, app, user, 'password123')

    assert build_install(project, today)['closed'] is True

    html = _get(app, client, 'client_servicing.calendar', view='agenda').get_data(as_text=True)
    assert 'Closed Install Job' in html or 'cs-cal-job--closed' in html


def test_closed_job_card_has_no_editable_cells(app, client, db_session):
    """A closed job renders no editable cells, so inline edit has nothing to hook."""
    today = date.today()
    user = _user(db_session, 'f')
    _project(db_session, user, 'Read Only Install', closed=True, install=today)
    login_as(client, app, user, 'password123')

    html = _get(app, client, 'client_servicing.calendar', view='agenda').get_data(as_text=True)
    assert 'cs-cal-job--closed' in html
    # The closed job is the only install on the page.
    assert 'cs-editable' not in html


def test_dashboard_drops_closed_projects(app, db_session):
    user = _user(db_session, 'g')
    _project(db_session, user, 'Closed Board Job', closed=True)
    _project(db_session, user, 'Live Board Job')

    assert [p.name for p in active_projects().all()] == ['Live Board Job']
