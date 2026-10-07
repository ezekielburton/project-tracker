"""Who receives each report, and whether it sends itself on schedule."""
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User
from app.modules.reports.models import ALL_REPORTS, ReportAutoSend, ReportRecipient


def recipients(report):
    """Active people who receive `report`, by name."""
    return (User.query.join(ReportRecipient, ReportRecipient.user_id == User.id)
            .filter(ReportRecipient.report == report, User.is_active.is_(True))
            .order_by(User.name).all())


def add_recipient(report, user):
    if not ReportRecipient.query.filter_by(report=report, user_id=user.id).first():
        db.session.add(ReportRecipient(report=report, user_id=user.id))
    db.session.commit()


def remove_recipient(report, user):
    ReportRecipient.query.filter_by(report=report, user_id=user.id).delete()
    db.session.commit()


def auto_send_on(report, kind):
    """True when both the master switch and the report's own switch are on.
    No row means on."""
    rows = ReportAutoSend.query.filter(ReportAutoSend.period_kind == kind,
                                       ReportAutoSend.report.in_((report, ALL_REPORTS)))
    enabled = {r.report: r.enabled for r in rows}
    return enabled.get(ALL_REPORTS, True) and enabled.get(report, True)


def switch_state(report, kind):
    """One switch on its own (the master is ALL_REPORTS), for the admin pages."""
    row = db.session.get(ReportAutoSend, (report, kind))
    return True if row is None else row.enabled


def set_auto_send(report, kind, enabled):
    row = db.session.get(ReportAutoSend, (report, kind))
    if row is None:
        row = ReportAutoSend(report=report, period_kind=kind)
        db.session.add(row)
    row.enabled = bool(enabled)
    db.session.commit()
