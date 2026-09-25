"""Snapshot every dashboard card's data, plus query count and render time, per role and scope.

Read-only: each case runs in its own rolled-back session. Run on the same day for before/after.
  python refactor/dashboard_snapshot.py save before
  python refactor/dashboard_snapshot.py save after
  python refactor/dashboard_snapshot.py diff before after
"""
import json
import statistics
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask_login import login_user
from sqlalchemy import event

from app import create_app
from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import can
from app.modules.core.shared.lib.users import active_users_query
from app.modules.core.shared.models import User
from app.modules.dashboard.routes import dashboard as d

OUT_DIR = Path(__file__).resolve().parent / '_dashboard_snapshot'
USERS_PER_ROLE = 3
RENDER_RUNS = 3

# Every compute function the page and its /api endpoints call: (real user, scope user, scope mode) -> data.
CARDS = {
    'summary': lambda u, s, m: d._compute_summary(s),
    'what_changed': lambda u, s, m: d._compute_what_changed(s),
    'due_overdue': lambda u, s, m: d._compute_due(s, 'overdue'),
    'due_today': lambda u, s, m: d._compute_due(s, 'today'),
    'due_week': lambda u, s, m: d._compute_due(s, 'week'),
    'due_overdue_today': lambda u, s, m: d._compute_due(s, 'overdue_today'),
    'decisions_scoped': lambda u, s, m: d._compute_decisions(s, all_flags=False),
    'decisions_all': lambda u, s, m: d._compute_decisions(s, all_flags=True),
    'next_actions_mine': lambda u, s, m: d._compute_next_actions(s, 'mine'),
    'next_actions_others': lambda u, s, m: d._compute_next_actions(s, 'others'),
    'priority_actions': lambda u, s, m: d._compute_priority_actions(s),
    'waiting_on_others': lambda u, s, m: d._compute_waiting_on_others(s),
    'my_escalated': lambda u, s, m: d._compute_my_escalated_projects(s),
    'my_escalation_history': lambda u, s, m: d._compute_my_escalation_history(s),
    'escalation_history': lambda u, s, m: d._compute_escalation_history(),
    'flaggable': lambda u, s, m: d._compute_flaggable_projects(u),
    'clashes': lambda u, s, m: d._compute_clashes_response(s),
    'at_risk': lambda u, s, m: d._compute_at_risk_projects(s),
    'project_stats': lambda u, s, m: d._compute_project_stats(s),
    'your_active': lambda u, s, m: d._compute_your_active_projects(s),
    'pending_approval': lambda u, s, m: d._compute_pending_approval_projects(s),
    'risk_overdue': lambda u, s, m: d._compute_risk_overdue(s),
    'leadership_waiting': lambda u, s, m: d._compute_leadership_waiting_on_others(s),
    'role_snapshot': lambda u, s, m: d._compute_role_snapshot(),
    'leadership_focus': lambda u, s, m: d._compute_leadership_focus(
        s, len(d._compute_decisions(s, all_flags=True)), d._compute_risk_overdue(s)),
    'designer_work_queue': lambda u, s, m: d._compute_designer_work_queue(s),
    'designer_week_load': lambda u, s, m: d._compute_designer_week_load(s),
    'designer_metrics': lambda u, s, m: d._compute_designer_metrics(s),
}


@contextmanager
def counting():
    count = [0]

    def _inc(*_args, **_kwargs):
        count[0] += 1

    event.listen(db.engine, 'before_cursor_execute', _inc)
    try:
        yield count
    finally:
        event.remove(db.engine, 'before_cursor_execute', _inc)


def _fresh():
    """Start cold, like a new request: nothing already loaded on any object."""
    db.session.rollback()
    db.session.expunge_all()


def _jsonable(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def build_cases(app):
    """(role, user_id, scope) — a few users per role, plus a leader's non-default scopes."""
    cases = []
    roles = sorted(r for (r,) in db.session.query(User.role).distinct() if r)
    for role in roles:
        users = active_users_query().filter(User.role == role).order_by(User.id).limit(USERS_PER_ROLE).all()
        cases += [(role, u.id, '') for u in users if can('view_workspace', u)]

    leader = next((u for u in active_users_query().order_by(User.id).all()
                   if can('switch_dashboard_scope', u)), None)
    if leader:
        with app.test_request_context('/dashboard'):
            _, _, cs_leads, designers = d._resolve_dashboard_scope(leader)
        scopes = ['my'] + [f'cs_{u.id}' for u in cs_leads[:1]] + [f'designer_{u.id}' for u in designers[:1]]
        cases += [(leader.role, leader.id, s) for s in scopes]
    return cases


def run_case(app, user_id, scope):
    path = '/dashboard' + (f'?scope={scope}' if scope else '')
    data, card_queries = {}, {}
    for name, call in CARDS.items():
        _fresh()
        with app.test_request_context(path):
            user = db.session.get(User, user_id)
            login_user(user)
            scope_mode, scope_user, _, _ = d._resolve_dashboard_scope(user)
            with counting() as n:
                data[name] = _jsonable(call(user, scope_user, scope_mode))
            card_queries[name] = n[0]

    timings, page_queries = [], 0
    for _ in range(RENDER_RUNS):
        _fresh()
        with app.test_request_context(path):
            login_user(db.session.get(User, user_id))
            with counting() as n:
                start = time.perf_counter()
                d.index()
                timings.append((time.perf_counter() - start) * 1000)
            page_queries = n[0]

    metrics = {'page_queries': page_queries,
               'page_ms_median': round(statistics.median(timings), 1),
               'card_queries': card_queries}
    return data, metrics


def save(label):
    app = create_app()
    OUT_DIR.mkdir(exist_ok=True)
    snapshot, metrics = {}, {}
    with app.app_context():
        try:
            for role, user_id, scope in build_cases(app):
                key = f'{role}#{user_id}:{scope or "default"}'
                snapshot[key], metrics[key] = run_case(app, user_id, scope)
                m = metrics[key]
                print(f'{key:<32} {m["page_queries"]:>6} queries {m["page_ms_median"]:>9} ms')
        finally:
            _fresh()
    (OUT_DIR / f'{label}.json').write_text(json.dumps(snapshot, indent=1, sort_keys=True))
    (OUT_DIR / f'{label}.metrics.json').write_text(json.dumps(metrics, indent=1, sort_keys=True))
    print(f'Saved {len(snapshot)} cases to {OUT_DIR}')


def _canonical(value):
    """Same content ignoring list order — separates real changes from tie-order shuffles."""
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted((_canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


# Grows with the clock while a project sits in a status, so it moves between runs.
DRIFT_KEYS = {'average_time', 'age_display'}


def _without_drift(value):
    if isinstance(value, dict):
        return {k: _without_drift(v) for k, v in value.items() if k not in DRIFT_KEYS}
    if isinstance(value, list):
        return [_without_drift(v) for v in value]
    return value


def diff(a, b):
    load = lambda name: json.loads((OUT_DIR / name).read_text())
    left, right = load(f'{a}.json'), load(f'{b}.json')
    ma, mb = load(f'{a}.metrics.json'), load(f'{b}.metrics.json')

    print(f'{"case":<32} {"queries":>17} {"ms (median)":>21}')
    for key in sorted(set(ma) & set(mb)):
        qa, qb = ma[key]['page_queries'], mb[key]['page_queries']
        ta, tb = ma[key]['page_ms_median'], mb[key]['page_ms_median']
        print(f'{key:<32} {qa:>7} -> {qb:<7} {ta:>9} -> {tb:<9}')

    changed, order_only, drift = [], [], []
    for key in sorted(set(left) | set(right)):
        cards = set(left.get(key, {})) | set(right.get(key, {}))
        for card in sorted(cards):
            x, y = left.get(key, {}).get(card), right.get(key, {}).get(card)
            if x == y:
                continue
            if _canonical(x) == _canonical(y):
                order_only.append(f'{key} / {card}')
            elif _without_drift(_canonical(x)) == _without_drift(_canonical(y)):
                drift.append(f'{key} / {card}')
            else:
                changed.append(f'{key} / {card}')

    print(f'\nOrder-only differences: {len(order_only)}')
    for item in order_only:
        print(f'  {item}')
    print(f'Clock drift only ({", ".join(sorted(DRIFT_KEYS))}): {len(drift)}')
    print(f'Content differences: {len(changed)}')
    for item in changed:
        print(f'  {item}')
    sys.exit(1 if changed else 0)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'save':
        save(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == 'diff':
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)
