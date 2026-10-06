"""App-log parsing: Flask and gunicorn errors become events with their
traceback, repeats share a signature, worker starts are counted, noise is ignored."""
import json

from app.modules.system.lib import app_log

_SECOND = 1_000_000


def _lines(*messages, start=1_790_000_000):
    return [json.dumps({'MESSAGE': m, '__REALTIME_TIMESTAMP': str((start + i) * _SECOND)})
            for i, m in enumerate(messages)]


def _flask_error(route, project_id):
    return (
        f'[2026-10-06 14:22:01,123] ERROR in app: Exception on {route} [POST]',
        'Traceback (most recent call last):',
        '  File "/home/helixadmin/project-tracker/venv/lib/python3.10/site-packages/flask/app.py", line 1511, in wsgi_app',
        '    response = self.full_dispatch_request()',
        '  File "/home/helixadmin/project-tracker/app/modules/projects/routes/project_files.py", line 88, in upload',
        '    db.session.commit()',
        f'sqlalchemy.exc.IntegrityError: (psycopg2.errors.UniqueViolation) duplicate key value (project_id)=({project_id})',
    )


def test_a_flask_error_and_its_traceback_become_one_event():
    events = app_log.read_events(_lines(*_flask_error('/projects/12/upload', 12)))
    assert len(events) == 1
    event = events[0]
    assert event['level'] == app_log.ERROR
    assert event['signature'] == 'sqlalchemy.exc.IntegrityError · app/modules/projects/routes/project_files.py · upload'
    assert event['message'] == 'Exception on /projects/12/upload [POST]'
    assert 'db.session.commit()' in event['detail']
    assert event['ts'] is not None


def test_the_same_error_twice_shares_a_signature():
    events = app_log.read_events(_lines(*_flask_error('/projects/12/upload', 12), *_flask_error('/projects/40/upload', 40)))
    assert len(events) == 2
    assert events[0]['signature'] == events[1]['signature']


def test_a_warning_without_traceback_groups_by_its_message():
    events = app_log.read_events(_lines(
        "[2026-10-06 14:22:01,123] WARNING in nas_outbox: NAS down, queued '/Projects/2026/A/brief.pdf' on the server: timeout 10",
        "[2026-10-06 14:25:09,001] WARNING in nas_outbox: NAS down, queued '/Projects/2026/B/plan.pdf' on the server: timeout 10",
    ))
    assert [e['level'] for e in events] == [app_log.WARNING, app_log.WARNING]
    assert events[0]['signature'] == events[1]['signature'] == 'nas_outbox: NAS down, queued … on the server: timeout #'


def test_gunicorn_errors_and_worker_starts():
    events = app_log.read_events(_lines(
        '[2026-10-06 14:22:01 +0400] [811] [ERROR] Worker (pid:5120) was sent SIGKILL! Perhaps out of memory?',
        '[2026-10-06 14:22:02 +0400] [5188] [INFO] Booting worker with pid: 5188',
    ))
    assert events[0]['level'] == app_log.ERROR
    assert events[0]['signature'] == 'gunicorn: Worker (pid:#) was sent SIGKILL! Perhaps out of memory?'
    assert events[1]['level'] == app_log.INFO
    assert events[1]['signature'] == 'gunicorn: worker started'


def test_a_bare_traceback_is_an_error():
    events = app_log.read_events(_lines(
        'Traceback (most recent call last):',
        '  File "/home/helixadmin/project-tracker/app/modules/core/shared/services/sse_relay.py", line 160, in _listen_loop',
        'psycopg2.OperationalError: server closed the connection unexpectedly',
    ))
    assert len(events) == 1
    assert events[0]['signature'] == 'psycopg2.OperationalError · app/modules/core/shared/services/sse_relay.py · _listen_loop'


def test_ordinary_lines_and_bad_json_are_ignored():
    lines = _lines('[2026-10-06 14:22:02 +0400] [811] [INFO] Handling signal: hup',
                   'Removed 4 cached preview file(s).') + ['not json']
    assert app_log.read_events(lines) == []


def test_an_error_ends_at_the_next_ordinary_line():
    events = app_log.read_events(_lines(
        '[2026-10-06 14:22:01,123] ERROR in app: Exception on /x [GET]',
        'ValueError: bad',
        'Removed 4 cached preview file(s).',
    ))
    assert events[0]['detail'] == 'Exception on /x [GET]\nValueError: bad'


def test_a_binary_message_is_decoded():
    raw = json.dumps({'MESSAGE': list('[2026-10-06 14:22:01,123] ERROR in app: boom'.encode()),
                      '__REALTIME_TIMESTAMP': '1790000000000000'})
    assert app_log.read_events([raw])[0]['message'] == 'boom'
