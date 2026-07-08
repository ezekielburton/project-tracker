# app/status_tracking.py
#
# Single funnel for every project / customer / deliverable status change.
# Replaces raw `.project_status = X` / `.status = X` assignments so every
# transition is captured in the matching *StatusLog table (app/models) —
# one place instead of scattered across every route that used to set the
# field directly.
#
# Each public function still sets the actual status column itself, so a
# call site just swaps the raw assignment for the matching wrapper call —
# no extra step, no risk of forgetting to also update the field.
#
# None of these call db.session.commit() — that stays the caller's job,
# same as before, usually alongside other changes in the same transaction.

from datetime import datetime


def _record_status_change(entity, new_status, actor, log_cls, fk_field):
    """Internal — closes the entity's current open log row (if any) and
    opens a new one. Shared by the three public wrappers below so the
    open/close bookkeeping only exists in one place."""
    from app import db

    now = datetime.utcnow()

    open_row = log_cls.query.filter_by(**{fk_field: entity.id}, ended_at=None).first()
    if open_row:
        open_row.ended_at = now

    db.session.add(log_cls(
        **{fk_field: entity.id},
        status=new_status,
        started_at=now,
        changed_by_id=actor.id if actor else None
    ))


def record_project_status(project, new_status, actor):
    from app.models import ProjectStatusLog
    _record_status_change(project, new_status, actor, ProjectStatusLog, 'project_id')
    project.project_status = new_status


def record_customer_status(customer, new_status, actor):
    from app.models import ProjectCustomerStatusLog
    _record_status_change(customer, new_status, actor, ProjectCustomerStatusLog, 'project_customer_id')
    customer.status = new_status


def record_deliverable_status(deliverable, new_status, actor):
    from app.models import DeliverableStatusLog
    _record_status_change(deliverable, new_status, actor, DeliverableStatusLog, 'deliverable_id')
    deliverable.status = new_status