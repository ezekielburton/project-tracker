"""lib/settings.py and lib/send.py: switches, who gets what, and the scheduled run."""
from datetime import date, datetime

import pytest

from app.modules.core.shared.extensions import mail
from app.modules.core.shared.models import User
from app.modules.reports.lib import send, settings, storage
from app.modules.reports.lib.period import Period
from app.modules.reports.models import ALL_REPORTS, REPORTS, ReportRecipient, ReportRun

WEEK = Period.week_of(date(2026, 9, 28))
TODAY = date(2026, 10, 5)


def _user(db_session, tag):
    u = User(name=f'Send {tag}', email=f'reports-send-{tag}@example.com', role='management')
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _run(db_session, report):
    run = ReportRun(report=report, period_kind=WEEK.kind, period_start=WEEK.start,
                    period_end=WEEK.end, made_at=datetime(2026, 10, 5, 4),
                    file_name=f'OVP-Wk40-{report}.pdf', status='generated',
                    summary={'score': 50, 'change': 2, 'no_activity': 1})
    db_session.add(run)
    db_session.flush()
    return run


@pytest.fixture
def outbox(app, monkeypatch):
    """Mail on, nothing really sent, and stored PDFs read as stubs."""
    sent = []
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', 'true')
    monkeypatch.setattr(mail, 'send', sent.append)
    monkeypatch.setattr(storage, 'read', lambda run: b'%PDF-1.7 stub')
    return sent


def test_auto_send_needs_master_and_report_switch(db_session):
    assert settings.auto_send_on('design', 'weekly')                 # no rows: on
    settings.set_auto_send('design', 'weekly', False)
    assert not settings.auto_send_on('design', 'weekly')
    settings.set_auto_send('design', 'weekly', True)
    settings.set_auto_send(ALL_REPORTS, 'weekly', False)
    assert not settings.auto_send_on('design', 'weekly')
    assert settings.auto_send_on('design', 'monthly')


def test_each_person_gets_one_email_with_their_reports(app, db_session, outbox):
    a, b = _user(db_session, 'a'), _user(db_session, 'b')
    for report, user in (('consolidated', a), ('design', a), ('design', b)):
        db_session.add(ReportRecipient(report=report, user_id=user.id))
    runs = [_run(db_session, 'consolidated'), _run(db_session, 'design')]

    with app.test_request_context():
        send.deliver(runs)

    got = {m.recipients[0]: [att.filename for att in m.attachments] for m in outbox}
    assert got == {a.email: ['OVP-Wk40-consolidated.pdf', 'OVP-Wk40-design.pdf'],
                   b.email: ['OVP-Wk40-design.pdf']}
    assert [r.status for r in runs] == ['sent', 'sent']
    assert sorted(runs[1].sent_to) == sorted([a.id, b.id])


def test_report_without_recipients_fails_with_a_reason(app, db_session, outbox):
    run = _run(db_session, 'project_owner')
    with app.test_request_context():
        send.deliver([run])
    assert (run.status, run.error) == ('failed', 'No recipients.')
    assert outbox == []


def test_mail_off_marks_runs_failed(app, db_session, monkeypatch):
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', 'false')
    run = _run(db_session, 'design')
    with app.test_request_context():
        send.deliver([run])
    assert run.status == 'failed'


def test_scheduled_run_skips_reports_already_sent(app, db_session, monkeypatch):
    for report in REPORTS:
        _run(db_session, report).status = 'sent'
    db_session.flush()
    monkeypatch.setattr(send, 'generate', lambda *a, **k: pytest.fail('nothing should be generated'))
    with app.test_request_context():
        assert send.run_scheduled('weekly', TODAY).endswith('nothing to send.')
