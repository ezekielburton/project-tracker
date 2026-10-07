"""New briefs lists active projects with no deliverables in one query, and
rail_counts only counts pages on the person's rail."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.modules.core.shared.models import Deliverable, Project, User
from app.modules.core.shared.testing import count_queries
from app.modules.dashboard.lib import rail_counts as counts_module
from app.modules.dashboard.lib.project_loader import load_new_briefs


def _cs(db_session, tag):
    user = User(name=f'Briefs {tag}', email=f'briefs-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, cs, name, status='briefed', **fields):
    project = Project(name=name, project_status=status, cs_lead_id=cs.id, created_by_id=cs.id, **fields)
    db_session.add(project)
    db_session.flush()
    return project


def test_new_briefs_are_active_projects_without_deliverables_newest_first(app, db_session):
    cs = _cs(db_session, 'list')
    now = datetime.utcnow()
    older = _project(db_session, cs, 'NB older', created_at=now - timedelta(days=2))
    newer = _project(db_session, cs, 'NB newer', created_at=now - timedelta(days=1))
    with_work = _project(db_session, cs, 'NB has deliverable')
    db_session.add(Deliverable(project_id=with_work.id, name='NB d', created_by_id=cs.id))
    _project(db_session, cs, 'NB draft', status='draft')
    _project(db_session, cs, 'NB approved', status='approved')
    _project(db_session, cs, 'NB cancelled', cancelled_at=now)
    _project(db_session, cs, 'NB deleted', is_deleted=True)
    db_session.flush()

    with app.test_request_context('/dashboard'):
        names = [p.name for p in load_new_briefs() if p.name.startswith('NB ')]
    assert names == [newer.name, older.name]


def test_new_briefs_query_count_does_not_grow_with_rows(app, db_session):
    cs = _cs(db_session, 'perf')
    _project(db_session, cs, 'NB perf 1')
    with app.test_request_context('/dashboard'):
        with count_queries() as small:
            [p.cs_lead.name for p in load_new_briefs()]
    for n in range(2, 6):
        _project(db_session, cs, f'NB perf {n}')
    db_session.expire_all()
    with app.test_request_context('/dashboard'):
        with count_queries() as big:
            [p.cs_lead.name for p in load_new_briefs()]
    assert big[0] == small[0]


def test_rail_counts_only_count_pages_on_the_rail_and_hide_zero(app, monkeypatch):
    monkeypatch.setattr(counts_module, 'COUNTERS', {
        'approvals': lambda user: 3,
        'my_clients': lambda user: 0,
        'assignments': lambda user: 9,
    })
    cs_person = SimpleNamespace(id=1, department='client_servicing', seniority='none', is_admin=False)
    with app.test_request_context('/dashboard'):
        assert counts_module.rail_counts(cs_person) == {'approvals': 3, 'my_clients': None}


def test_rail_counts_run_once_per_request(app, monkeypatch):
    calls = []
    monkeypatch.setattr(counts_module, 'COUNTERS', {'approvals': lambda user: calls.append(1) or 2})
    cs_person = SimpleNamespace(id=2, department='client_servicing', seniority='none', is_admin=False)
    with app.test_request_context('/dashboard'):
        counts_module.rail_counts(cs_person)
        counts_module.rail_counts(cs_person)
    assert len(calls) == 1
