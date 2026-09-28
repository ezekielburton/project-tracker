# Single funnel for project / deliverable status changes: each
# wrapper sets the status column AND writes the matching *StatusLog row.
# Call the wrapper instead of assigning `.status` directly.
#
# None of these commit; that is the caller's job.

from datetime import datetime


def _record_status_change(entity, new_status, actor, log_cls, fk_field):
    """Close the entity's open log row (if any) and open a new one."""
    from app.modules.core.shared.extensions import db

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
    """Set project_status and log it. ProjectStatusLog is the only source
    for project hours: time_tracking recomputes them from it on demand."""
    from app.modules.core.shared.models import ProjectStatusLog
    _record_status_change(project, new_status, actor, ProjectStatusLog, 'project_id')
    project.project_status = new_status


def record_deliverable_status(deliverable, new_status, actor):
    from app.modules.core.shared.models import DeliverableStatusLog
    _record_status_change(deliverable, new_status, actor, DeliverableStatusLog, 'deliverable_id')
    deliverable.status = new_status


def sync_project_pipeline_status(project, actor):
    """Set project_status from its deliverables' labels (same for Standard
    and C&CM): all Handed to Production -> 'handed_to_production', none In
    Design -> 'approved', else 'in_progress'. Call after any change to a
    deliverable's derived label. No-op for draft / briefed / on_hold or
    cancelled projects, and when nothing would change."""
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status

    if project.cancelled_at is not None or project.project_status in ('draft', 'briefed', 'on_hold'):
        return

    deliverables = project.project_deliverables
    if not deliverables:
        return

    labels = [derive_deliverable_status(d)[0] for d in deliverables]
    if all(label == 'Handed to Production' for label in labels):
        target = 'handed_to_production'
    elif all(label != 'In Design' for label in labels):
        target = 'approved'
    else:
        target = 'in_progress'

    if project.project_status != target:
        record_project_status(project, target, actor)


# ── Read helpers — "when did this status last change" ──────────────────
# Read-only. They return the raw status's started_at, not when the pill
# label began: several raw statuses collapse into one label (e.g. In Design),
# each opening a new log row.

def project_status_started_at(project):
    """started_at of the project's open ProjectStatusLog row; None if never
    logged."""
    from app.modules.core.shared.models import ProjectStatusLog
    row = ProjectStatusLog.query.filter_by(project_id=project.id, ended_at=None).first()
    return row.started_at if row else None


def bulk_deliverable_status_started_at(deliverable_ids):
    """{deliverable_id: started_at} in one query. Deliverables with no open
    row are absent."""
    from app.modules.core.shared.models import DeliverableStatusLog
    if not deliverable_ids:
        return {}
    rows = DeliverableStatusLog.query.filter(
        DeliverableStatusLog.deliverable_id.in_(deliverable_ids),
        DeliverableStatusLog.ended_at.is_(None)
    ).all()
    return {row.deliverable_id: row.started_at for row in rows}


def bulk_project_status_started_at(project_ids):
    """Same, for projects (used by the Projects list)."""
    from app.modules.core.shared.models import ProjectStatusLog
    if not project_ids:
        return {}
    rows = ProjectStatusLog.query.filter(
        ProjectStatusLog.project_id.in_(project_ids),
        ProjectStatusLog.ended_at.is_(None)
    ).all()
    return {row.project_id: row.started_at for row in rows}


# ── Read helpers — "when was this last client-approved" ─────────────────
# The most recent log row with status 'approved', current or not. Needed for
# projects: moving on to 'handed_to_production' closes the 'approved' row, so
# project_status_started_at would lose the approval time. Log rows are never
# deleted, so every past approval survives.

def latest_client_approval_at(entity, log_cls, fk_field):
    """Latest started_at among the entity's 'approved' log rows; None if
    never approved."""
    row = (
        log_cls.query
        .filter_by(**{fk_field: entity.id}, status='approved')
        .order_by(log_cls.started_at.desc())
        .first()
    )
    return row.started_at if row else None


def project_client_approved_at(project):
    """When the project last entered 'approved'; survives a later move to
    'handed_to_production'. None if never."""
    from app.modules.core.shared.models import ProjectStatusLog
    return latest_client_approval_at(project, ProjectStatusLog, 'project_id')


def bulk_project_client_approved_at(project_ids):
    """{project_id: latest 'approved' started_at} in one query.
    Never-approved projects are absent."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectStatusLog
    if not project_ids:
        return {}
    rows = (
        db.session.query(ProjectStatusLog.project_id, db.func.max(ProjectStatusLog.started_at))
        .filter(ProjectStatusLog.project_id.in_(project_ids), ProjectStatusLog.status == 'approved')
        .group_by(ProjectStatusLog.project_id)
        .all()
    )
    return dict(rows)

