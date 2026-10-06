"""The bridge from role keys to the org model: setting a key fills the org
fields, and User.role reads the same in Python and in SQL."""
import pytest

from app.modules.core.shared.lib import org
from app.modules.core.shared.lib.org import DEPARTMENTS, LEGACY_ROLES, SENIORITY_LEVELS
from app.modules.core.shared.models import JobRole, User


def _user(db_session, tag, **fields):
    user = User(name=f'Org Test {tag}', email=f'org-test-{tag}@example.com', **fields)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_legacy_map_uses_known_keys():
    for role, (department, seniority, _) in LEGACY_ROLES.items():
        assert department is None or department in DEPARTMENTS, role
        assert seniority in SENIORITY_LEVELS, role


@pytest.mark.parametrize('role', sorted(LEGACY_ROLES))
def test_role_key_round_trips_in_python_and_sql(db_session, role):
    user = _user(db_session, f'rt-{role}', role=role)
    assert user.role == role
    assert User.query.filter(User.role == role, User.id == user.id).one() is user


@pytest.mark.parametrize('department, seniority, is_admin, expected', [
    ('design', 'head', False, 'team_lead'),
    ('design', 'management', False, 'management'),
    ('finance', 'manager', False, 'finance'),
    ('digital_innovation', 'head', True, 'admin'),
    (None, 'none', False, None),
])
def test_org_fields_read_as_role(db_session, department, seniority, is_admin, expected):
    user = _user(db_session, f'rd-{department}-{seniority}-{is_admin}',
                 department=department, seniority=seniority, is_admin=is_admin)
    assert user.role == expected
    assert User.query.with_entities(User.role).filter_by(id=user.id).scalar() == expected


def test_unknown_role_key_is_refused():
    with pytest.raises(ValueError):
        User(name='Org Test bad', email='org-test-bad@example.com', role='wizard')


def test_role_filters_match_the_org_fields(db_session):
    lead = _user(db_session, 'fb-lead', role='team_lead')
    assert lead in User.query.filter_by(role='team_lead').all()
    assert lead in User.query.filter(User.role.in_(['designer', 'team_lead'])).all()


def test_reports_to_and_job_role_resolve(db_session):
    title = JobRole(department='design', title='Org Test 3D Lead')
    db_session.add(title)
    db_session.flush()
    boss = _user(db_session, 'boss', role='management')
    lead = _user(db_session, 'lead', role='team_lead', job_role_id=title.id, reports_to_id=boss.id)
    assert lead.reports_to is boss
    assert lead.job_role.title == 'Org Test 3D Lead'


@pytest.mark.parametrize('role', sorted(LEGACY_ROLES))
def test_branch_checks_match_the_role_keys(role):
    user = User(role=role)
    assert org.is_admin(user) is (role == 'admin')
    assert org.is_leadership(user) is (role in ('admin', 'management'))
    assert org.is_cs(user) is (role == 'cs')
    assert org.is_project_owner(user) is (role == 'project_owner')
    assert org.is_designer(user) is (role in ('designer', 'team_lead'))
    assert org.is_design_lead(user) is (role == 'team_lead')
    assert org.is_plain_designer(user) is (role == 'designer')


def test_management_in_design_takes_the_leadership_branch():
    user = User(department='design', seniority='management', is_admin=False)
    assert org.is_leadership(user) and not org.is_designer(user)


def test_a_head_of_design_is_a_lead():
    assert org.is_design_lead(User(department='design', seniority='head', is_admin=False))

@pytest.mark.parametrize('department, seniority, is_admin, expected', [
    ('design', 'head', False, True),
    ('client_servicing', 'head', False, True),
    ('finance', 'head', False, True),
    ('design', 'manager', False, False),
    ('design', 'none', False, False),
    ('design', 'management', False, False),
    ('design', 'head', True, False),
])

def test_department_head_is_head_seniority_outside_leadership(department, seniority, is_admin, expected):
    user = User(department=department, seniority=seniority, is_admin=is_admin)
    assert org.is_department_head(user) is expected


def test_department_head_tolerates_a_user_without_org_fields():
    assert org.is_department_head(None) is False
