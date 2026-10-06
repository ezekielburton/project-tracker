"""lib/facts.py and lib/metrics.py: what the reports count, from real rows."""
from datetime import date, datetime

from app.modules.core.shared.models import (
    ActivityLog, Deliverable, DeliverableAssignment, DeliverableStatusLog, Project, User,
)
from app.modules.core.shared.testing import count_queries
from app.modules.reports.lib import facts
from app.modules.reports.lib.metrics import department, person_row
from app.modules.reports.lib.period import Period

WEEK = Period.week_of(date(2026, 9, 28))  # Mon 28 Sep - Fri 2 Oct
TODAY = date(2026, 10, 5)


def _user(db_session, tag, role):
    u = User(name=f'Rep {tag}', email=f'reports-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _project(db_session, tag, lead):
    p = Project(name=f'Rep {tag}', created_by_id=lead.id, cs_lead_id=lead.id,
                project_status='in_progress', job_number=f'REP-{tag}')
    db_session.add(p)
    db_session.flush()
    return p


def _log(db_session, user, action, project, at):
    db_session.add(ActivityLog(user_id=user.id, action=action, description='test',
                               entity_type='project', entity_id=project.id, created_at=at))
    db_session.flush()


def _deliverable(db_session, project, designer, due, delivered_at=None):
    d = Deliverable(project_id=project.id, name=f'Rep {due}', status='in_design',
                    design_deadline=due, created_by_id=designer.id)
    db_session.add(d)
    db_session.flush()
    db_session.add(DeliverableAssignment(deliverable_id=d.id, designer_id=designer.id,
                                         team='2D', assigned_by_id=designer.id))
    if delivered_at:
        db_session.add(DeliverableStatusLog(deliverable_id=d.id, status='internal_review',
                                            started_at=delivered_at, changed_by_id=designer.id))
    db_session.flush()
    return d


def test_worked_on_counts_real_actions_and_working_days(db_session):
    cs = _user(db_session, 'w1', 'cs')
    a, b = _project(db_session, 'wa', cs), _project(db_session, 'wb', cs)
    _log(db_session, cs, 'project_edited', a, datetime(2026, 9, 28, 6))
    _log(db_session, cs, 'note_added', a, datetime(2026, 9, 28, 9))           # same day, same project
    _log(db_session, cs, 'client_servicing_edit', b, datetime(2026, 9, 30, 6))
    _log(db_session, cs, 'edit_access_requested', b, datetime(2026, 10, 1, 6))  # not work
    _log(db_session, cs, 'project_edited', b, datetime(2026, 10, 3, 6))        # Saturday: outside the week

    row = person_row(facts.load(WEEK, [cs.id], TODAY), cs, 'client_servicing')
    assert (row['worked'], row['active']) == (2, 2)


def test_design_deadlines_hit_late_and_never(db_session):
    lead, des = _user(db_session, 'd1', 'cs'), _user(db_session, 'd2', 'designer')
    p = _project(db_session, 'd', lead)
    _deliverable(db_session, p, des, date(2026, 9, 30), datetime(2026, 9, 30, 10))  # on the day
    _deliverable(db_session, p, des, date(2026, 10, 1), datetime(2026, 10, 2, 6))   # a day late
    _deliverable(db_session, p, des, date(2026, 10, 2))                             # never

    row = person_row(facts.load(WEEK, [des.id], TODAY), des, 'design')
    assert (row['hit'], row['missed']) == (1, 2)


def test_mid_week_report_skips_deadlines_not_yet_due(db_session):
    lead, des = _user(db_session, 'm1', 'cs'), _user(db_session, 'm2', 'designer')
    p = _project(db_session, 'm', lead)
    _deliverable(db_session, p, des, date(2026, 10, 2))  # Friday; report made Wednesday

    row = person_row(facts.load(WEEK, [des.id], date(2026, 9, 30)), des, 'design')
    assert (row['hit'], row['missed']) == (0, 0)


def test_person_with_no_actions_is_flagged(db_session):
    idle = _user(db_session, 'i1', 'designer')
    data = department(facts.load(WEEK, [idle.id], TODAY), 'design', [idle])
    assert data['no_activity'] == [idle]


def test_queries_do_not_grow_with_people(app, db_session):
    lead = _user(db_session, 'q0', 'cs')
    p = _project(db_session, 'q', lead)
    small = [_user(db_session, 'q1', 'designer')]
    big = small + [_user(db_session, f'q{i}', 'designer') for i in range(2, 7)]
    for des in big:
        _deliverable(db_session, p, des, date(2026, 9, 30), datetime(2026, 9, 30, 6))
        _log(db_session, des, 'internal_review_submitted', p, datetime(2026, 9, 30, 6))

    with count_queries() as few:
        department(facts.load(WEEK, [u.id for u in small], TODAY), 'design', small)
    with count_queries() as many:
        department(facts.load(WEEK, [u.id for u in big], TODAY), 'design', big)
    assert many[0] == few[0]
