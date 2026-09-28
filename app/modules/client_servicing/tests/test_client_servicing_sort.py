"""Server side of click-to-sort: the table emits the data-row-order and
data-sort-value attributes that client_servicing.js sorts on (the sort itself is JS-only)."""
import re
from datetime import date

from flask import url_for

from app.modules.core.shared.models import User, Project, ProjectDesigner
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing


def _user(db_session, tag, role='cs'):
    user = User(name=f'Sort Test User {tag}', email=f'cs-sort-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _get_table_rows(client, app):
    with app.test_request_context():
        url = url_for('client_servicing.table')
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_rows_carry_data_row_order_matching_default_name_order(app, client, db_session):
    """data-row-order follows the default name order, which a cleared sort restores."""
    user = _user(db_session, 'a')
    for name in ('Zeta Project', 'Alpha Project', 'Mid Project'):
        db_session.add(Project(name=name, cs_lead_id=user.id, created_by_id=user.id, project_status='briefed'))
    db_session.flush()
    login_as(client, app, user, 'password123')

    body = _get_table_rows(client, app)
    tbody = body.split('<tbody>')[1]
    orders = re.findall(r'data-row-order="(\d+)"', tbody)
    names_in_order = re.findall(r'data-col-key="project" data-sort-value="([^"]*)"', tbody)
    assert orders == ['1', '2', '3']
    assert names_in_order == ['Alpha Project', 'Mid Project', 'Zeta Project']


def _sort_value(body, col_key):
    match = re.search(r'data-col-key="%s"[^>]*data-sort-value="([^"]*)"' % re.escape(col_key), body)
    assert match, f'no data-sort-value found for column {col_key!r}'
    return float(match.group(1))


def test_numeric_columns_carry_raw_numbers_not_formatted_text(app, client, db_session):
    """Money and margin columns carry the raw number as data-sort-value.
    margin_percent is computed (no setter), so it is seeded via the costs."""
    user = _user(db_session, 'b')
    project = Project(name='Numeric Sort Project', cs_lead_id=user.id, created_by_id=user.id, value=100000.5, project_status='briefed')
    db_session.add(project)
    db_session.flush()
    db_session.add(ClientServicing(project_id=project.id, cost_to_client=9999.99, inward_cost=8000))
    db_session.flush()
    login_as(client, app, user, 'password123')

    body = _get_table_rows(client, app)
    expected_margin = (9999.99 - 8000) / 9999.99 * 100
    assert _sort_value(body, 'value') == 100000.5
    assert _sort_value(body, 'cost_to_client') == 9999.99
    assert _sort_value(body, 'inward_cost') == 8000
    assert abs(_sort_value(body, 'margin_percent') - expected_margin) < 0.01


def test_date_columns_carry_isoformat_not_display_format(app, client, db_session):
    """Dates display as "05 Mar 2026" but sort on ISO form, since the JS compares them as strings."""
    user = _user(db_session, 'c')
    project = Project(name='Date Sort Project', cs_lead_id=user.id, created_by_id=user.id, briefing_date=date(2026, 3, 5), project_status='briefed')
    db_session.add(project)
    db_session.flush()
    login_as(client, app, user, 'password123')

    body = _get_table_rows(client, app)
    assert 'data-col-key="brief_date" data-sort-value="2026-03-05"' in body
    assert '05 Mar 2026' in body  # the display text is still the formatted one


def test_missing_values_carry_an_empty_sort_value(app, client, db_session):
    """Blank fields carry data-sort-value="", the sentinel applySort() uses to sink blank rows."""
    user = _user(db_session, 'd')
    project = Project(name='Blank Fields Project', cs_lead_id=user.id, created_by_id=user.id, project_status='briefed')
    db_session.add(project)
    db_session.flush()
    login_as(client, app, user, 'password123')

    body = _get_table_rows(client, app)
    assert 'data-col-key="due_date" class="cs-editable" data-field="first_output_deadline" data-value="" data-sort-value="">' in body
    assert 'data-col-key="priority" class="cs-editable" data-field="priority" data-value="" data-sort-value="">' in body


def test_designers_sort_value_is_comma_joined_names(app, client, db_session):
    """The designers column sorts on its names comma-joined (row['designers_sort'])."""
    user = _user(db_session, 'e')
    designer_1 = _user(db_session, 'e2', role='designer')
    designer_2 = _user(db_session, 'e3', role='designer')
    project = Project(name='Multi Designer Project', cs_lead_id=user.id, created_by_id=user.id, project_status='briefed')
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectDesigner(project_id=project.id, user_id=designer_1.id, team='2D'))
    db_session.add(ProjectDesigner(project_id=project.id, user_id=designer_2.id, team='3D'))
    db_session.flush()
    login_as(client, app, user, 'password123')

    body = _get_table_rows(client, app)
    expected = f'data-col-key="designers" data-sort-value="{designer_1.name}, {designer_2.name}"'
    assert expected in body
