"""The approval chain: Reports to up to the first Management person, then HR."""
from app.modules.core.shared.models import User
from app.modules.hr.services.approvers import approvers_for


def _person(db_session, tag, reports_to=None, active=True, **fields):
    user = User(name=f'Approver Test {tag}', email=f'approver-test-{tag}@example.com',
                is_active=active, reports_to=reports_to, **fields)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _managers(chain):
    return [step.approvers[0].name for step in chain.steps if not step.is_hr]


def _hr_step(chain):
    assert chain.steps[-1].is_hr
    return set(chain.steps[-1].approvers)


def test_designer_goes_through_lead_and_management_then_hr(db_session):
    hr = _person(db_session, 'hr', department='hr', seniority='none', is_admin=False)
    petar = _person(db_session, 'petar', department='design', seniority='management', is_admin=False)
    lead = _person(db_session, '3d-lead', reports_to=petar, role='team_lead')
    nishant = _person(db_session, 'nishant', reports_to=lead, role='designer')

    chain = approvers_for(nishant)
    assert _managers(chain) == [lead.name, petar.name]
    assert hr in _hr_step(chain)
    assert chain.complete


def test_head_of_department_goes_to_the_gm_then_hr(db_session):
    gm = _person(db_session, 'gm', role='management')
    head = _person(db_session, 'head', reports_to=gm, department='finance', seniority='head', is_admin=False)
    assert _managers(approvers_for(head)) == [gm.name]


def test_an_admin_head_goes_to_the_gm_then_hr(db_session):
    gm = _person(db_session, 'gm-2', role='management')
    ezekiel = _person(db_session, 'ezekiel', reports_to=gm, department='digital_innovation',
                      seniority='head', is_admin=True)
    chain = approvers_for(ezekiel)
    assert _managers(chain) == [gm.name]
    assert chain.complete


def test_the_walk_stops_at_the_first_management_person(db_session):
    gm = _person(db_session, 'gm-3', role='management')
    petar = _person(db_session, 'petar-3', reports_to=gm, department='design',
                    seniority='management', is_admin=False)
    designer = _person(db_session, 'd-3', reports_to=petar, role='designer')
    assert _managers(approvers_for(designer)) == [petar.name]


def test_management_go_straight_to_hr_even_with_a_manager(db_session):
    gm = _person(db_session, 'gm-8', role='management')
    petar = _person(db_session, 'petar-8', reports_to=gm, department='design',
                    seniority='management', is_admin=False)
    chain = approvers_for(petar)
    assert _managers(chain) == []
    assert chain.complete


def test_any_hr_person_can_approve_but_not_their_own_request(db_session):
    hr_a = _person(db_session, 'hr-a', department='hr', seniority='none', is_admin=False)
    hr_b = _person(db_session, 'hr-b', department='hr', seniority='none', is_admin=False)
    gm = _person(db_session, 'gm-4', role='management')
    hr_a.reports_to = gm
    db_session.flush()

    hr_step = _hr_step(approvers_for(hr_a))
    assert hr_b in hr_step
    assert hr_a not in hr_step


def test_a_missing_link_still_reaches_hr(db_session):
    hr = _person(db_session, 'hr-5', department='hr', seniority='none', is_admin=False)
    loner = _person(db_session, 'loner', role='designer')
    chain = approvers_for(loner)
    assert _managers(chain) == []
    assert hr in _hr_step(chain)
    assert not chain.complete


def test_a_loop_stops_and_still_reaches_hr(db_session):
    a = _person(db_session, 'loop-a', role='designer')
    b = _person(db_session, 'loop-b', reports_to=a, role='team_lead')
    a.reports_to = b
    db_session.flush()
    chain = approvers_for(a)
    assert _managers(chain) == [b.name]
    assert chain.steps[-1].is_hr
    assert not chain.complete


def test_a_deactivated_manager_is_skipped(db_session):
    gm = _person(db_session, 'gm-6', role='management')
    gone = _person(db_session, 'gone', reports_to=gm, role='team_lead', active=False)
    designer = _person(db_session, 'd-6', reports_to=gone, role='designer')
    assert _managers(approvers_for(designer)) == [gm.name]


def test_the_gm_goes_straight_to_hr(db_session):
    gm = _person(db_session, 'gm-7', role='management')
    chain = approvers_for(gm)
    assert _managers(chain) == []
    assert chain.complete
