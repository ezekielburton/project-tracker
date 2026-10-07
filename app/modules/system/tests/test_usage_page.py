"""What the Usage page reads: the tiles, actions per day, by module and by
hour, recent logins and the emulation log, with admins and test accounts left out."""
from datetime import datetime, timedelta

from app.modules.core.shared.models import User
from app.modules.system.models import RequestMetric
from app.modules.system.services import usage

NOW = datetime(2031, 3, 4, 10, 0, 0)  # 14:00 in Dubai, a Tuesday
SAVE = '/projects/<int:id>/save'


def _user(db_session, tag, **fields):
    user = User(name=f'Usage {tag}', email=f'usage-{tag}@example.com', **fields)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _hit(db_session, user, minutes_ago, method='POST', route=SAVE, blueprint='project_overlay', status=200,
         emulating=None):
    db_session.add(RequestMetric(ts=NOW - timedelta(minutes=minutes_ago), method=method, route=route,
                                 blueprint=blueprint, status=status, duration_ms=10,
                                 user_id=user.id if user else None,
                                 emulating_id=emulating.id if emulating else None))
    db_session.flush()


def test_tiles_count_people_and_actions_but_not_admins(db_session):
    ana = _user(db_session, 'ana', department='client_servicing')
    ben = _user(db_session, 'ben', department='design', team='2D')
    admin = _user(db_session, 'admin', is_admin=True)
    _hit(db_session, ana, 2)
    _hit(db_session, ana, 3, blueprint='wiki', route='/wiki/x')
    _hit(db_session, ben, 60, method='GET', route='/projects')
    _hit(db_session, admin, 1)
    _hit(db_session, ben, 60 * 24 * 8)  # last week
    tiles = usage.tiles(NOW)
    assert tiles['active_now'] == 1
    assert tiles['actions_today'] == 2
    assert tiles['people_week'] == 2 and tiles['people_last_week'] == 1
    assert tiles['top_module']['module'] == 'Projects'
    assert tiles['staff'] >= 2


def test_actions_per_day_has_every_day_today_last(db_session):
    ana = _user(db_session, 'perday')
    _hit(db_session, ana, 10)
    _hit(db_session, ana, 60 * 24 * 2)
    days = usage.per_day(NOW)
    assert len(days) == usage.DAYS_SHOWN
    assert days[-1]['day'].isoformat() == '2031-03-04' and days[-1]['actions'] == 1
    assert days[-3]['actions'] == 1 and sum(day['actions'] for day in days) == 2


def test_by_module_and_by_hour(db_session):
    ana = _user(db_session, 'modules')
    for _ in range(3):
        _hit(db_session, ana, 30)
    _hit(db_session, ana, 30, blueprint='wiki', route='/wiki/x')
    _hit(db_session, ana, 30, blueprint='auth', route='/login')  # not an action
    assert usage.by_module(NOW) == [{'module': 'Projects', 'actions': 3, 'share': 75},
                                    {'module': 'Wiki', 'actions': 1, 'share': 25}]
    hours = usage.by_hour(NOW)
    assert len(hours) == 24 and hours[13] == 4  # 09:30 UTC is 13:30 in Dubai


def test_recent_logins_newest_first_without_admins(db_session, app):
    ana = _user(db_session, 'login-ana', department='client_servicing')
    ben = _user(db_session, 'login-ben', department='design', team='3D')
    admin = _user(db_session, 'login-admin', is_admin=True)
    _hit(db_session, ana, 90, route='/login', blueprint='auth', status=302)
    _hit(db_session, ben, 5, route='/login', blueprint='auth', status=302)
    _hit(db_session, admin, 1, route='/login', blueprint='auth', status=302)
    _hit(db_session, ana, 2, route='/login', blueprint='auth', status=200)  # a failed try
    with app.test_request_context():
        logins = usage.recent_logins(NOW)
    assert logins == [{'name': 'Usage login-ben', 'who': '3D', 'ago': '5 min ago'},
                      {'name': 'Usage login-ana', 'who': 'Client Servicing', 'ago': '1 h ago'}]


def test_sessions_split_on_a_long_gap_and_on_a_new_person():
    t = NOW
    rows = [(t, 1, 5), (t + timedelta(minutes=6), 1, 5), (t + timedelta(minutes=50), 1, 5),
            (t + timedelta(minutes=7), 1, 6)]
    assert usage.sessions(rows) == [(1, 5, t + timedelta(minutes=50), t + timedelta(minutes=50)),
                                    (1, 6, t + timedelta(minutes=7), t + timedelta(minutes=7)),
                                    (1, 5, t, t + timedelta(minutes=6))]


def test_emulation_log(db_session):
    admin = _user(db_session, 'emu-admin', is_admin=True)
    mo = _user(db_session, 'emu-mo', department='client_servicing')
    _hit(db_session, admin, 30, method='GET', route='/dashboard', emulating=mo)
    _hit(db_session, admin, 24, method='GET', route='/dashboard', emulating=mo)
    log = usage.emulation_log(NOW)
    assert log == [{'name': 'Usage emu-mo', 'who': 'Client Servicing', 'when': 'today 13:30', 'minutes': 6}]
