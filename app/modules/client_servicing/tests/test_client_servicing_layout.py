"""Coverage for column-width and column-order persistence:
POST /client-servicing/layout (routes/layout.py)
and table.py's _column_widths()/_ordered_columns() reading it back into
the rendered <colgroup>/<thead>."""
import json
import re

from flask import url_for

from app.modules.core.shared.models import User, UserTableLayout
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.routes.table import TABLE_KEY, COLUMNS


def _user(db_session, tag, role='cs'):
    user = User(name=f'Layout Test User {tag}', email=f'cs-layout-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _save_url(app):
    with app.test_request_context():
        return url_for('client_servicing.save_layout')


def _post_layout(client, app, layout):
    return client.post(_save_url(app), data=json.dumps({'table_key': TABLE_KEY, 'layout': layout}),
                        content_type='application/json')


def test_requires_cs_access(app, client, db_session):
    designer = _user(db_session, 'a', role='designer')
    login_as(client, app, designer, 'password123')

    resp = _post_layout(client, app, [{'key': 'client', 'width': 100}])
    assert resp.status_code == 403


def test_save_creates_a_layout_row(app, client, db_session):
    user = _user(db_session, 'b')
    login_as(client, app, user, 'password123')

    resp = _post_layout(client, app, [{'key': 'client', 'width': 120}, {'key': 'project', 'width': 240}])
    assert resp.status_code == 200

    row = UserTableLayout.query.filter_by(user_id=user.id, table_key=TABLE_KEY).first()
    assert row is not None
    assert row.layout == [{'key': 'client', 'width': 120}, {'key': 'project', 'width': 240}]


def test_save_again_updates_the_same_row_not_a_new_one(app, client, db_session):
    user = _user(db_session, 'c')
    login_as(client, app, user, 'password123')

    _post_layout(client, app, [{'key': 'client', 'width': 100}])
    _post_layout(client, app, [{'key': 'client', 'width': 200}])

    rows = UserTableLayout.query.filter_by(user_id=user.id, table_key=TABLE_KEY).all()
    assert len(rows) == 1
    assert rows[0].layout == [{'key': 'client', 'width': 200}]


def test_rejects_missing_layout(app, client, db_session):
    user = _user(db_session, 'd')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.save_layout')
    resp = client.post(url, data=json.dumps({'table_key': TABLE_KEY}), content_type='application/json')
    assert resp.status_code == 400


def test_rejects_malformed_entries(app, client, db_session):
    user = _user(db_session, 'e')
    login_as(client, app, user, 'password123')

    resp = _post_layout(client, app, [{'key': 'client'}])  # missing width
    assert resp.status_code == 400

    resp = _post_layout(client, app, ['not-a-dict'])
    assert resp.status_code == 400


def test_saved_widths_appear_in_the_rendered_colgroup(app, client, db_session):
    user = _user(db_session, 'f')
    login_as(client, app, user, 'password123')

    resp = _post_layout(client, app, [{'key': 'job_number', 'width': 175}])
    assert resp.status_code == 200

    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    body = resp.get_data(as_text=True)
    assert 'data-col-key="job_number" style="width: 175px;"' in body


def test_one_users_layout_does_not_affect_another(app, client, db_session):
    user_a = _user(db_session, 'g1')
    user_b = _user(db_session, 'g2')

    login_as(client, app, user_a, 'password123')
    _post_layout(client, app, [{'key': 'job_number', 'width': 999}])

    login_as(client, app, user_b, 'password123')
    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    body = resp.get_data(as_text=True)
    assert 'width: 999px' not in body


def _rendered_column_order(client, app):
    """The data-col-key order of the <th> elements on the live page —
    i.e. what the user actually sees, after table.py's _ordered_columns()
    has applied their saved layout."""
    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    body = resp.get_data(as_text=True)
    thead = body.split('<tbody>')[0]
    return re.findall(r'<th data-col-key="([^"]+)"', thead)


def test_saved_order_is_reflected_in_rendered_column_order(app, client, db_session):
    user = _user(db_session, 'h')
    login_as(client, app, user, 'password123')

    # Put the last three default columns right after priority/margin/
    # inward_cost; everything else keeps its relative order behind them,
    # unaffected keys included. Project isn't part of this saved layout
    # at all, but it's pinned (see test_project_column_is_pinned_first_
    # even_if_saved_layout_says_otherwise below) so it still comes first.
    reordered = [{'key': 'priority', 'width': 100}, {'key': 'margin_percent', 'width': 100},
                 {'key': 'inward_cost', 'width': 100}]
    resp = _post_layout(client, app, reordered)
    assert resp.status_code == 200

    order = _rendered_column_order(client, app)
    assert order[0] == 'project'
    assert order[1:4] == ['priority', 'margin_percent', 'inward_cost']
    # every other column still present, just pushed after the three above
    assert set(order) == {c['key'] for c in COLUMNS}


def test_columns_missing_from_saved_layout_are_appended_in_default_order(app, client, db_session):
    user = _user(db_session, 'i')
    login_as(client, app, user, 'password123')

    resp = _post_layout(client, app, [{'key': 'project', 'width': 100}, {'key': 'client', 'width': 100}])
    assert resp.status_code == 200

    order = _rendered_column_order(client, app)
    all_keys = [c['key'] for c in COLUMNS]
    assert order[0] == 'project'
    assert order[1] == 'client'
    # the rest keep COLUMNS' own default order, minus the two moved to the front
    expected_rest = [k for k in all_keys if k not in ('project', 'client')]
    assert order[2:] == expected_rest


def test_stale_unknown_key_in_saved_layout_is_ignored(app, client, db_session):
    user = _user(db_session, 'j')
    login_as(client, app, user, 'password123')

    resp = _post_layout(client, app, [{'key': 'not_a_real_column', 'width': 100},
                                       {'key': 'client', 'width': 100}])
    assert resp.status_code == 200

    order = _rendered_column_order(client, app)
    assert 'not_a_real_column' not in order
    # project is pinned first regardless of what's saved (see the pinning
    # test below); client is next since it's the only real key saved
    assert order[0] == 'project'
    assert order[1] == 'client'
    assert set(order) == {c['key'] for c in COLUMNS}


def test_project_column_is_pinned_first_even_if_saved_layout_says_otherwise(app, client, db_session):
    """Project is a sticky, non-draggable column on the page (it always
    sits right after "Open in Projects") — so even a saved layout from
    before that was true, or one tampered with by hand, must not be able
    to move it."""
    user = _user(db_session, 'k')
    login_as(client, app, user, 'password123')

    resp = _post_layout(client, app, [{'key': 'priority', 'width': 100}, {'key': 'client', 'width': 100},
                                       {'key': 'project', 'width': 100}])
    assert resp.status_code == 200

    order = _rendered_column_order(client, app)
    assert order[0] == 'project'
    assert order[1:3] == ['priority', 'client']
