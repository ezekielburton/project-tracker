"""Reports data: every generated PDF (the record of what was reported) and
who receives each report."""
from datetime import datetime

from app.modules.core.shared.extensions import db


# Report key -> label, in page and email order.
REPORTS = {
    'consolidated': 'Consolidated',
    'client_servicing': 'Client Servicing',
    'project_owner': 'Project Owners',
    'design': 'Design',
}
PERIOD_KINDS = ('weekly', 'monthly')
RUN_STATUSES = ('generated', 'sent', 'failed')

# ReportAutoSend.report value for the master switch on the Generate page.
ALL_REPORTS = 'all'


class ReportRun(db.Model):
    """One generated PDF. The file is never rebuilt: data changes after the
    fact, so the stored copy is the proof. made_by_id is None for a scheduled run."""
    __tablename__ = 'report_runs'

    id = db.Column(db.Integer, primary_key=True)
    report = db.Column(db.String(30), nullable=False)
    period_kind = db.Column(db.String(10), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    made_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    made_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='generated')
    sent_at = db.Column(db.DateTime, nullable=True)
    sent_to = db.Column(db.JSON, nullable=True)  # user ids at send time
    error = db.Column(db.Text, nullable=True)

    made_by = db.relationship('User', foreign_keys=[made_by_id])

    __table_args__ = (db.Index('ix_report_runs_period', 'period_kind', 'period_start'),)


class ReportRecipient(db.Model):
    """A person who receives one report."""
    __tablename__ = 'report_recipients'

    id = db.Column(db.Integer, primary_key=True)
    report = db.Column(db.String(30), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (db.UniqueConstraint('report', 'user_id', name='uq_report_recipients_report_user'),)


class ReportAutoSend(db.Model):
    """Auto-send switch per report and period. No row means on; report
    ALL_REPORTS is the master switch."""
    __tablename__ = 'report_auto_send'

    report = db.Column(db.String(30), primary_key=True)
    period_kind = db.Column(db.String(10), primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
