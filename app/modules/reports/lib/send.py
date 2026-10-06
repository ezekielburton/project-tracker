"""Making and sending reports. generate() builds and stores the PDFs,
deliver() emails them, run_scheduled() is what the timers call."""
from collections import defaultdict
from datetime import datetime

from flask import current_app, render_template

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.mail import mail_enabled
from app.modules.core.shared.lib.timezone import dubai_today
from app.modules.reports.lib import pdf, storage
from app.modules.reports.lib.build import build
from app.modules.reports.lib.period import WEEKLY, Period
from app.modules.reports.lib.settings import auto_send_on, recipients
from app.modules.reports.models import REPORTS, ReportRun

# Where "Open in OVP" in the email points, under APP_BASE_URL.
HISTORY_PATH = '/reports/history'


def _summary(data):
    """The email's headline numbers, kept with the run so a resend matches the PDF."""
    return {'score': data['score'], 'change': data['delta'].get('score', 0),
            'no_activity': len(data['no_activity'])}


def generate(period, reports, made_by=None, today=None):
    """Builds `reports` for `period` from one load, stores each PDF and records
    a ReportRun. Returns the runs, in REPORTS order."""
    built = build(period, today)
    runs = []
    for report in [r for r in REPORTS if r in reports]:
        run = ReportRun(report=report, period_kind=period.kind, period_start=period.start,
                        period_end=period.end, made_at=datetime.utcnow(),
                        made_by_id=made_by.id if made_by else None,
                        file_name=pdf.file_name(report, period), status='generated',
                        summary=_summary(built[report]))
        db.session.add(run)
        db.session.flush()  # the id names the stored file
        data = pdf.render_pdf(report, built, run.made_at)
        storage.save(run, data)
        run.file_size = len(data)
        runs.append(run)
    db.session.commit()
    return runs


def _fail(runs, reason):
    for run in runs:
        run.status, run.error = 'failed', reason


def deliver(runs):
    """Emails each recipient one message holding every report they receive,
    then marks each run sent, or failed with the reason."""
    if not mail_enabled():
        _fail(runs, 'Email is switched off on this server.')
        db.session.commit()
        return
    by_person = defaultdict(list)
    for run in runs:
        people = recipients(run.report)
        run.sent_to = [u.id for u in people]
        if not people:
            _fail([run], 'No recipients.')
        for person in people:
            by_person[person.id].append((person, run))
    errors = {}
    for items in by_person.values():
        person, person_runs = items[0][0], [run for _, run in items]
        try:
            _send(person, person_runs)
        except Exception as e:  # SMTP errors vary by provider
            current_app.logger.warning(f'Report email to {person.email} failed: {e}')
            for run in person_runs:
                errors[run.id] = f'Not delivered to {person.name}.'
    now = datetime.utcnow()
    for run in runs:
        if run.status == 'failed':
            continue
        if run.id in errors:
            _fail([run], errors[run.id])
        else:
            run.status, run.sent_at, run.error = 'sent', now, None
    db.session.commit()


def _subject(period, count):
    kind = 'weekly' if period.kind == WEEKLY else 'monthly'
    noun = 'report' if count == 1 else 'reports'
    if period.kind == WEEKLY:
        return f'OVP {kind} {noun} · Week {period.week_number} ({period.short_label.split(" · ")[1]})'
    return f'OVP {kind} {noun} · {period.short_label}'


def _send(person, runs):
    from flask_mail import Message
    from app.modules.core.shared.extensions import mail

    period = runs[0].period
    base = current_app.config.get('APP_BASE_URL', '')
    context = {'person': person, 'runs': runs, 'period': period,
               'reports': REPORTS, 'link': f'{base}{HISTORY_PATH}' if base else None}
    message = Message(
        subject=_subject(period, len(runs)),
        recipients=[person.email],
        body=render_template('reports/email.txt', **context),
        html=render_template('reports/email.html', **context),
    )
    for run in runs:
        message.attach(run.file_name, 'application/pdf', storage.read(run))
    mail.send(message)


def _already_sent(report, period):
    """True when a scheduled run already sent this report for this period."""
    return db.session.query(ReportRun.id).filter_by(
        report=report, period_kind=period.kind, period_start=period.start,
        made_by_id=None, status='sent').first() is not None


def run_scheduled(kind, today=None):
    """Last complete week or month: every report that is switched on and not
    already sent for that period. Safe to rerun. Returns a line for the log."""
    period = Period.last_complete(kind, today or dubai_today())
    due = [r for r in REPORTS if auto_send_on(r, kind) and not _already_sent(r, period)]
    if not due:
        return f'{period.short_label}: nothing to send.'
    runs = generate(period, due, today=today)
    deliver(runs)
    done = ', '.join(f'{REPORTS[r.report]} {r.status}' for r in runs)
    return f'{period.short_label}: {done}.'
