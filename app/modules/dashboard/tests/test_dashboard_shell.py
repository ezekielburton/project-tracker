"""The rail pages: /dashboard lands on the rail's first page, every page is gated
by its capability and by being on the rail, system pages need the real admin,
and the shell shows the rail, its badges and New briefs."""
import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.dashboard.lib import rail_counts as counts_module

PASSWORD = 'password123'


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


def _user(db_session, tag, department=None, seniority='none', is_admin=False):
    user = User(name=f'Shell {tag}', email=f'shell-{tag}@example.com',
                department=department, seniority=seniority, is_admin=is_admin)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    return user


def _login(client, app, db_session, tag, **org_fields):
    user = _user(db_session, tag, **org_fields)
    login_as(client, app, user, PASSWORD)
    return user


def test_rail_pages_need_a_login(app, client):
    for endpoint in ('projects.index', 'projects.approvals', 'projects.admin_system',
                     'projects.admin_overview'):
        assert client.get(_url(app, endpoint)).status_code in (302, 401)


@pytest.mark.parametrize('tag, fields, landing', [
    ('admin', dict(is_admin=True), 'projects.admin_overview'),
    ('mgmt', dict(seniority='management'), 'projects.overview'),
    ('design-head', dict(department='design', seniority='head'), 'projects.design_workload'),
    ('design-lead', dict(department='design', seniority='manager'), 'projects.overview'),
    ('designer', dict(department='design'), 'projects.overview'),
    ('cs-head', dict(department='client_servicing', seniority='head'), 'projects.needs_attention'),
    ('cs', dict(department='client_servicing', seniority='manager'), 'projects.overview'),
    ('po', dict(department='project_owner'), 'projects.overview'),
    ('finance', dict(department='finance'), 'projects.overview'),
    ('production', dict(department='production'), 'projects.overview'),
])
def test_dashboard_lands_on_the_first_page_of_the_rail(app, client, db_session, tag, fields, landing):
    _login(client, app, db_session, f'land-{tag}', **fields)
    resp = client.get(_url(app, 'projects.index'))
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith(_url(app, landing))


def test_landing_keeps_the_query_string(app, client, db_session):
    _login(client, app, db_session, 'qs', seniority='management')
    resp = client.get(_url(app, 'projects.index', scope='all'))
    assert resp.headers['Location'].endswith(_url(app, 'projects.overview', scope='all'))


def test_a_page_off_your_rail_is_refused(app, client, db_session):
    _login(client, app, db_session, 'off-designer', department='design')
    assert client.get(_url(app, 'projects.my_projects')).status_code == 200
    assert client.get(_url(app, 'projects.approvals')).status_code == 403


def test_a_head_outside_design_and_cs_has_no_department_page(app, client, db_session):
    _login(client, app, db_session, 'finance-head', department='finance', seniority='head')
    assert client.get(_url(app, 'projects.design_workload')).status_code == 403
    assert client.get(_url(app, 'projects.needs_attention')).status_code == 403


def test_head_of_design_opens_design_workload_only(app, client, db_session):
    _login(client, app, db_session, 'hod', department='design', seniority='head')
    assert client.get(_url(app, 'projects.design_workload')).status_code == 200
    assert client.get(_url(app, 'projects.needs_attention')).status_code == 403


def test_management_opens_both_department_pages_and_its_own(app, client, db_session):
    _login(client, app, db_session, 'mgmt-pages', department='design', seniority='management')
    for endpoint in ('projects.design_workload', 'projects.needs_attention',
                     'projects.escalations', 'projects.adoption'):
        assert client.get(_url(app, endpoint)).status_code == 200, endpoint


def test_management_pages_refuse_everyone_else(app, client, db_session):
    _login(client, app, db_session, 'cs-mgmt-page', department='client_servicing')
    assert client.get(_url(app, 'projects.escalations')).status_code == 403


def test_system_pages_refuse_non_admins(app, client, db_session):
    _login(client, app, db_session, 'mgmt-system', seniority='management')
    assert client.get(_url(app, 'projects.admin_system')).status_code == 403
    assert client.get(_url(app, 'projects.admin_overview')).status_code == 403


def test_admin_opens_system_pages_and_pages_off_its_rail(app, client, db_session):
    _login(client, app, db_session, 'admin-any', is_admin=True)
    assert client.get(_url(app, 'projects.admin_jobs')).status_code == 200
    assert client.get(_url(app, 'projects.escalations')).status_code == 200


def test_an_emulating_admin_keeps_system_pages_with_their_own_rail(app, client, db_session):
    _login(client, app, db_session, 'emu-admin', is_admin=True)
    head = _user(db_session, 'emu-head', department='design', seniority='head')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = head.id

    landing = client.get(_url(app, 'projects.index'))
    assert landing.headers['Location'].endswith(_url(app, 'projects.design_workload'))

    for endpoint in ('projects.admin_overview', 'projects.admin_system'):
        page = client.get(_url(app, endpoint))
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        assert f'href="{_url(app, "projects.admin_database")}"' in html
        assert f'href="{_url(app, "projects.assignments")}"' not in html


def test_an_emulating_admin_sees_the_emulated_rail_on_project_pages(app, client, db_session):
    _login(client, app, db_session, 'emu-admin-2', is_admin=True)
    head = _user(db_session, 'emu-head-2', department='design', seniority='head')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = head.id
    html = client.get(_url(app, 'projects.assignments')).get_data(as_text=True)
    assert f'href="{_url(app, "projects.assignments")}"' in html
    assert f'href="{_url(app, "projects.admin_database")}"' not in html


def test_the_admin_rail_starts_on_the_system_overview(app, client, db_session):
    _login(client, app, db_session, 'admin-rail', is_admin=True)
    html = client.get(_url(app, 'projects.admin_jobs')).get_data(as_text=True)
    assert f'href="{_url(app, "projects.admin_overview")}"' in html
    assert f'href="{_url(app, "projects.overview")}"' not in html


def test_the_errors_and_jobs_badges_show_on_the_admin_rail(app, client, db_session):
    from datetime import datetime
    from app.modules.system.models import AppLogEvent, JobRun
    now = datetime.utcnow()
    db_session.add(AppLogEvent(ts=now, level='error', source='app', signature='x-badge-test', message='boom'))
    db_session.add(JobRun(job='backup', started_at=now, finished_at=now, result='failed'))
    db_session.flush()
    _login(client, app, db_session, 'admin-badges', is_admin=True)
    html = client.get(_url(app, 'projects.admin_system')).get_data(as_text=True)
    assert html.count('class="module-rail-count"') == 2


def test_every_rail_shows_my_hub_as_soon(app, client, db_session):
    _login(client, app, db_session, 'soon', department='client_servicing')
    html = client.get(_url(app, 'projects.approvals')).get_data(as_text=True)
    assert 'My hub' in html
    assert 'module-rail-soon' in html


def test_a_count_shows_as_a_badge_and_zero_shows_none(app, client, db_session, monkeypatch):
    monkeypatch.setattr(counts_module, 'COUNTERS', {
        'approvals': lambda user: 4,
        'my_clients': lambda user: 0,
    })
    _login(client, app, db_session, 'badge', department='client_servicing')
    html = client.get(_url(app, 'projects.approvals')).get_data(as_text=True)
    assert html.count('class="module-rail-count"') == 1
    assert '<span class="module-rail-count">4</span>' in html


def test_new_briefs_show_on_the_landing_page_only(app, client, db_session):
    _login(client, app, db_session, 'briefs-head', department='client_servicing', seniority='head')
    landing = client.get(_url(app, 'projects.needs_attention')).get_data(as_text=True)
    other = client.get(_url(app, 'projects.approvals')).get_data(as_text=True)
    assert 'dash-new-briefs' in landing
    assert 'dash-new-briefs' not in other


def test_the_basic_rail_overview_is_new_briefs_only(app, client, db_session):
    _login(client, app, db_session, 'basic-overview', department='finance')
    html = client.get(_url(app, 'projects.overview')).get_data(as_text=True)
    assert 'dash-new-briefs' in html
    assert 'page-container' not in html


def test_the_role_views_sit_inside_the_shell(app, client, db_session):
    for tag, fields in (('ov-designer', dict(department='design')),
                        ('ov-cs', dict(department='client_servicing')),
                        ('ov-mgmt', dict(seniority='management'))):
        client.get(_url(app, 'auth.logout'))
        _login(client, app, db_session, tag, **fields)
        html = client.get(_url(app, 'projects.overview')).get_data(as_text=True)
        assert 'module-rail' in html, tag
        assert 'page-container' in html, tag
        assert 'dash-new-briefs' in html, tag
