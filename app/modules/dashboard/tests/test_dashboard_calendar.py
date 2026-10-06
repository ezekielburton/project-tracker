"""The shared calendar page: this month by default, the chosen day's list,
events drawn from calendar_events_for, and a CSS rule for every event kind."""
from datetime import date
from pathlib import Path

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.dashboard.lib.calendar import EVENT_KINDS, calendar_events_for, parse_day, parse_month
from app.modules.dashboard.routes import pages

PASSWORD = 'password123'


def _url(app, **values):
    with app.test_request_context():
        return url_for('projects.calendar', **values)


def _login(client, app, db_session, tag, **fields):
    user = User(name=f'Cal {tag}', email=f'cal-{tag}@example.com', **fields)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, PASSWORD)


def test_calendar_needs_a_login(app, client):
    assert client.get(_url(app)).status_code in (302, 401)


def test_calendar_opens_on_this_month_with_nothing_scheduled(app, client, db_session):
    _login(client, app, db_session, 'designer', department='design')
    html = client.get(_url(app)).get_data(as_text=True)
    assert date.today().strftime('%B %Y') in html
    assert 'Nothing scheduled' in html


def test_calendar_is_refused_off_the_rail(app, client, db_session):
    _login(client, app, db_session, 'mgmt', seniority='management')
    assert client.get(_url(app)).status_code == 403


def test_a_chosen_day_opens_its_month_and_its_list(app, client, db_session):
    _login(client, app, db_session, 'day', department='client_servicing')
    html = client.get(_url(app, day='2026-02-14')).get_data(as_text=True)
    assert 'February 2026' in html
    assert 'Saturday 14 February' in html


def test_bad_month_and_day_fall_back_to_today(app, client, db_session):
    _login(client, app, db_session, 'bad', department='project_owner')
    resp = client.get(_url(app, month='nope', day='nope'))
    assert resp.status_code == 200
    assert date.today().strftime('%B %Y') in resp.get_data(as_text=True)


def test_events_from_the_seam_draw_in_the_cell_and_the_day_list(app, client, db_session, monkeypatch):
    day = date(2026, 3, 10)
    monkeypatch.setattr(pages, 'calendar_events_for', lambda user, start, end: [
        {'date': day, 'kind': 'install', 'title': 'Cal Test Install', 'url': '/projects'},
    ])
    _login(client, app, db_session, 'events', department='design')
    html = client.get(_url(app, day=day.isoformat())).get_data(as_text=True)
    assert html.count('Cal Test Install') == 2
    assert 'dash-cal-kind--install' in html


def test_the_seam_returns_nothing_until_events_arrive():
    assert calendar_events_for(None, date(2026, 1, 1), date(2026, 1, 31)) == []


def test_month_and_day_parsing():
    today = date(2026, 10, 6)
    assert parse_month('2026-02', today) == (2026, 2)
    assert parse_month('2026-13', today) == (2026, 10)
    assert parse_month(None, today) == (2026, 10)
    assert parse_day('2026-02-14') == date(2026, 2, 14)
    assert parse_day('14/02/2026') is None


def test_every_event_kind_has_its_css_rule():
    css = (Path(__file__).resolve().parents[1] / 'static' / 'css' / 'dashboard.css').read_text(encoding='utf-8')
    for kind in EVENT_KINDS:
        assert f'.dash-cal-kind--{kind.key}' in css, (
            f'Add a .dash-cal-kind--{kind.key} {{ --kind: … }} rule to dashboard.css for the new event kind.')
