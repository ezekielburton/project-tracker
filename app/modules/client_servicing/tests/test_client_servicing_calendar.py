"""Installation Calendar — risk derivation, month/agenda data service,
inline edit, and access."""
import json
from datetime import date, timedelta

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib.calendar import (
    effective_risk, month_grid, agenda_groups,
)

TODAY = date(2026, 9, 15)


def _user(db_session, tag, role='cs'):
    u = User(name=f'Cal {tag}', email=f'cs-cal-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _project(db_session, tag, user, install=None, cs_status=None, risk=None, cancelled=False):
    p = Project(name=f'Cal Project {tag}', cs_lead_id=user.id, created_by_id=user.id,
                installation_date=install)
    if cancelled:
        from datetime import datetime
        p.cancelled_at = datetime(2026, 9, 1)
    db_session.add(p)
    db_session.flush()
    if cs_status or risk:
        db_session.add(ClientServicing(project_id=p.id, cs_status=cs_status, risk=risk))
        db_session.flush()
    return p


# ── effective_risk ───────────────────────────────────────────────────────
def test_manual_risk_wins(db_session):
    u = _user(db_session, 'm')
    p = _project(db_session, 'm', u, install=TODAY + timedelta(days=1), cs_status='Briefing', risk='On Track')
    assert effective_risk(p, today=TODAY) == ('On Track', 'ontrack', False)


def test_auto_done_when_installed(db_session):
    u = _user(db_session, 'd')
    p = _project(db_session, 'd', u, install=TODAY - timedelta(days=5), cs_status='Installed')
    assert effective_risk(p, today=TODAY)[0] == 'Done'


def test_auto_done_when_cancelled(db_session):
    u = _user(db_session, 'c')
    p = _project(db_session, 'c', u, install=TODAY + timedelta(days=1), cs_status='Briefing', cancelled=True)
    assert effective_risk(p, today=TODAY)[0] == 'Done'


def test_auto_at_risk_when_imminent_and_not_ready(db_session):
    u = _user(db_session, 'r')
    p = _project(db_session, 'r', u, install=TODAY + timedelta(days=1), cs_status='Briefing')
    label, mod, is_auto = effective_risk(p, today=TODAY)
    assert (label, mod, is_auto) == ('At Risk', 'atrisk', True)


def test_auto_attention_within_week(db_session):
    u = _user(db_session, 'a')
    p = _project(db_session, 'a', u, install=TODAY + timedelta(days=5), cs_status='Briefing')
    assert effective_risk(p, today=TODAY)[0] == 'Attention'


def test_auto_on_track_when_far_or_ready(db_session):
    u = _user(db_session, 't')
    far = _project(db_session, 't1', u, install=TODAY + timedelta(days=20), cs_status='Briefing')
    ready = _project(db_session, 't2', u, install=TODAY + timedelta(days=1), cs_status='In Production')
    assert effective_risk(far, today=TODAY)[0] == 'On Track'
    assert effective_risk(ready, today=TODAY)[0] == 'On Track'


# ── data service ─────────────────────────────────────────────────────────
def _sample(db_session):
    u = _user(db_session, 'svc')
    _project(db_session, 's1', u, install=date(2026, 9, 16), cs_status='Briefing')       # At Risk
    _project(db_session, 's2', u, install=date(2026, 9, 20), cs_status='Briefing')       # Attention
    _project(db_session, 's3', u, install=date(2026, 9, 25), cs_status='In Production')  # On Track, ready
    _project(db_session, 's4', u, install=date(2026, 9, 10), cs_status='Installed')      # Done, ready
    _project(db_session, 's5', u, install=date(2026, 10, 5), cs_status='Briefing')       # next month
    return Project.query.filter(Project.installation_date.isnot(None)).all()


def test_month_grid_kpis(db_session):
    projects = _sample(db_session)
    weeks, kpis = month_grid(projects, 2026, 9, TODAY)
    assert kpis['total'] == 4          # s1..s4 in September (s5 is October)
    assert kpis['next7'] == 2          # s1 (16th), s2 (20th)
    assert kpis['ready'] == 2          # s3 In Production, s4 Installed
    assert kpis['attention'] == 1      # s2
    assert kpis['atrisk'] == 1         # s1
    # the 16th cell carries one install, coloured at-risk
    cells = [d for wk in weeks for d in wk if d['date'] == date(2026, 9, 16)]
    assert cells and cells[0]['count'] == 1 and cells[0]['worst'] == 'atrisk'


def test_agenda_groups_upcoming_only(db_session):
    projects = _sample(db_session)
    groups, kpis = agenda_groups(projects, TODAY, days_ahead=30)
    dates = [g['date'] for g in groups]
    assert date(2026, 9, 10) not in dates        # past install excluded
    assert date(2026, 10, 5) in dates            # within 30-day horizon
    assert kpis['total'] == 4


# ── inline edit + access ─────────────────────────────────────────────────
def _patch(client, app, project_id, field, value):
    with app.test_request_context():
        url = url_for('client_servicing.update_field', project_id=project_id)
    return client.patch(url, data=json.dumps({'field': field, 'value': value}), content_type='application/json')


def test_risk_edit_leaves_project_status_untouched(app, client, db_session):
    u = _user(db_session, 'e')
    p = _project(db_session, 'e', u, install=TODAY + timedelta(days=1))
    before = p.project_status
    login_as(client, app, u, 'password123')
    resp = _patch(client, app, p.id, 'risk', 'On Track')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['risk']['label'] == 'On Track' and body['risk']['is_auto'] is False
    db_session.refresh(p)
    assert p.project_status == before


def test_risk_clear_and_invalid(app, client, db_session):
    u = _user(db_session, 'ci')
    p = _project(db_session, 'ci', u, install=TODAY + timedelta(days=1))
    login_as(client, app, u, 'password123')
    _patch(client, app, p.id, 'risk', 'At Risk')
    assert _patch(client, app, p.id, 'risk', '').get_json()['risk']['is_auto'] is True
    assert _patch(client, app, p.id, 'risk', 'Nope').status_code == 400


def test_next_action_and_owner_save(app, client, db_session):
    u = _user(db_session, 'na')
    p = _project(db_session, 'na', u)
    login_as(client, app, u, 'password123')
    assert _patch(client, app, p.id, 'next_action', 'client approval pending').status_code == 200
    assert _patch(client, app, p.id, 'action_owner', 'Ravi').status_code == 200
    cs = ClientServicing.query.filter_by(project_id=p.id).first()
    assert cs.next_action == 'client approval pending' and cs.action_owner == 'Ravi'


def test_calendar_access(app, client, db_session):
    designer = _user(db_session, 'des', role='designer')
    login_as(client, app, designer, 'password123')
    with app.test_request_context():
        month_url = url_for('client_servicing.calendar')
        agenda_url = url_for('client_servicing.calendar', view='agenda')
        day_url = url_for('client_servicing.calendar_day', datestr='2026-09-16')
    assert client.get(month_url).status_code == 403
    assert client.get(agenda_url).status_code == 403
    assert client.get(day_url).status_code == 403


def test_calendar_renders_for_cs(app, client, db_session):
    u = _user(db_session, 'ok')
    _project(db_session, 'ok', u, install=TODAY + timedelta(days=1), cs_status='Briefing')
    login_as(client, app, u, 'password123')
    with app.test_request_context():
        month_url = url_for('client_servicing.calendar')
        agenda_url = url_for('client_servicing.calendar', view='agenda')
    assert client.get(month_url).status_code == 200
    assert client.get(agenda_url).status_code == 200


def test_install_qty_saves_clears_and_validates(app, client, db_session):
    u = _user(db_session, 'q')
    p = _project(db_session, 'q', u)
    login_as(client, app, u, 'password123')
    assert _patch(client, app, p.id, 'install_qty', '3').status_code == 200
    assert ClientServicing.query.filter_by(project_id=p.id).first().install_qty == 3
    assert _patch(client, app, p.id, 'install_qty', '').status_code == 200      # clear
    assert ClientServicing.query.filter_by(project_id=p.id).first().install_qty is None
    assert _patch(client, app, p.id, 'install_qty', '0').status_code == 400      # must be >= 1
    assert _patch(client, app, p.id, 'install_qty', 'abc').status_code == 400    # must be a number
