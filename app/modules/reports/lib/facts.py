"""The one loader every report reads, so the department reports and the
consolidated report count the same rows. Each query is bounded to the period
and its people; nothing here scores or formats."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, or_

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.timezone import dubai_today, to_dubai
from app.modules.core.shared.models import (
    ActivityLog, Deliverable, DeliverableAssignment, DeliverableStatusLog, Project,
    ProjectSubmission, ProjectSubmissionDeliverable, ProjectSubmissionFile,
)
from app.modules.client_servicing.services import report_feed
from app.modules.reports.lib.actions import (
    APPROVAL_ACTIONS, DELIVERED_STATUSES, REVISION_ACTIONS, STREAM_UPLOAD_ACTION, WORK_ACTIONS,
)

# Pre-Production stream status columns, and the status meaning "waiting for approval".
_STREAM_COLUMNS = (Deliverable.status_2d, Deliverable.status_3d, Deliverable.technical_status)
_STREAM_WAITING = 'uploaded'
# Deliverable status meaning "waiting for the client's answer".
_CLIENT_WAITING = 'submitted_to_client'


@dataclass
class Facts:
    period: object
    user_ids: list
    today: date
    working_days: int = 0
    worked: dict = field(default_factory=lambda: defaultdict(set))       # uid -> {project_id}
    active_days: dict = field(default_factory=lambda: defaultdict(set))  # uid -> {date}
    approvals: Counter = field(default_factory=Counter)                  # uid -> n
    stream_uploads: Counter = field(default_factory=Counter)             # uid -> n
    file_uploads: Counter = field(default_factory=Counter)               # uid -> n
    revisions: Counter = field(default_factory=Counter)                  # project_id -> rounds
    project_names: dict = field(default_factory=dict)                    # project_id -> name
    design_deadlines: list = field(default_factory=list)
    delivered: dict = field(default_factory=lambda: defaultdict(set))    # uid -> {deliverable_id}
    with_upload: set = field(default_factory=set)                        # deliverable ids
    waiting_approval: Counter = field(default_factory=Counter)           # uid -> n
    cs: dict = field(default_factory=dict)


def load(period, user_ids, today=None):
    """Everything the reports count for `period` and these people."""
    f = Facts(period=period, user_ids=list(user_ids), today=today or dubai_today())
    workdays = set(period.working_days())
    f.working_days = len(workdays)
    if not f.user_ids:
        return f
    start, end = period.utc_bounds()
    _activity(f, start, end, workdays)
    _revisions(f, start, end)
    _uploads(f, start, end)
    _design_deadlines(f)
    _delivered(f, start, end)
    _waiting_approval(f)
    f.cs = {
        'closed': report_feed.closed_between(start, end),
        'invoiced': report_feed.invoiced_between(period.start, period.end),
        'installs': report_feed.installs_between(period.start, _last_due_day(f)),
        'jobs': report_feed.active_jobs(),
        'waiting_invoice': report_feed.waiting_to_invoice(f.today),
    }
    return f


def _last_due_day(f):
    """Deadlines after today can't be missed yet, so a report made mid-period
    stops counting at today."""
    return min(f.period.end, f.today)


def _activity(f, start, end, workdays):
    rows = (db.session.query(ActivityLog.user_id, ActivityLog.action,
                             ActivityLog.entity_id, ActivityLog.created_at)
            .filter(ActivityLog.created_at >= start, ActivityLog.created_at < end,
                    ActivityLog.user_id.in_(f.user_ids),
                    ActivityLog.entity_type == 'project',
                    ActivityLog.action.in_(WORK_ACTIONS)))
    for uid, action, project_id, created_at in rows:
        if project_id:
            f.worked[uid].add(project_id)
        day = to_dubai(created_at).date()
        if day in workdays:
            f.active_days[uid].add(day)
        if action in APPROVAL_ACTIONS:
            f.approvals[uid] += 1
        if action == STREAM_UPLOAD_ACTION:
            f.stream_uploads[uid] += 1


def _revisions(f, start, end):
    rows = (db.session.query(ActivityLog.entity_id, Project.name, func.count())
            .join(Project, Project.id == ActivityLog.entity_id)
            .filter(ActivityLog.created_at >= start, ActivityLog.created_at < end,
                    ActivityLog.entity_type == 'project',
                    ActivityLog.action.in_(REVISION_ACTIONS))
            .group_by(ActivityLog.entity_id, Project.name))
    for project_id, name, rounds in rows:
        f.revisions[project_id] = rounds
        f.project_names[project_id] = name


def _uploads(f, start, end):
    for model in (ProjectSubmission, ProjectSubmissionFile):
        rows = (db.session.query(model.uploaded_by_id, func.count())
                .filter(model.uploaded_at >= start, model.uploaded_at < end,
                        model.uploaded_by_id.in_(f.user_ids))
                .group_by(model.uploaded_by_id))
        f.file_uploads.update(dict(rows))


def _first_delivered(deliverable_ids):
    """deliverable_id -> first time it was handed in (naive UTC)."""
    if not deliverable_ids:
        return {}
    rows = (db.session.query(DeliverableStatusLog.deliverable_id, func.min(DeliverableStatusLog.started_at))
            .filter(DeliverableStatusLog.deliverable_id.in_(deliverable_ids),
                    DeliverableStatusLog.status.in_(DELIVERED_STATUSES))
            .group_by(DeliverableStatusLog.deliverable_id))
    return dict(rows)


def _design_deadlines(f):
    """Deliverables due in the period (up to today), who they're assigned to,
    and whether each was handed in by its deadline day."""
    rows = (db.session.query(Deliverable.id, Deliverable.name, Deliverable.design_deadline,
                             Project.name, DeliverableAssignment.designer_id)
            .join(Project, Project.id == Deliverable.project_id)
            .join(DeliverableAssignment, DeliverableAssignment.deliverable_id == Deliverable.id)
            .filter(Deliverable.design_deadline >= f.period.start,
                    Deliverable.design_deadline <= _last_due_day(f),
                    DeliverableAssignment.designer_id.in_(f.user_ids)))
    by_id = {}
    for did, name, due, project_name, designer_id in rows:
        item = by_id.setdefault(did, {'deliverable_id': did, 'name': name, 'project': project_name,
                                      'due': due, 'designers': set()})
        item['designers'].add(designer_id)
    delivered = _first_delivered(list(by_id))
    for item in by_id.values():
        at = delivered.get(item['deliverable_id'])
        item['delivered_on'] = to_dubai(at).date() if at else None
        item['hit'] = item['delivered_on'] is not None and item['delivered_on'] <= item['due']
    f.design_deadlines = sorted(by_id.values(), key=lambda d: d['due'])


def _delivered(f, start, end):
    """Deliverables each designer handed in during the period, and which of
    them have files in a submission (uploaded in OVP)."""
    rows = (db.session.query(DeliverableAssignment.designer_id, DeliverableStatusLog.deliverable_id)
            .join(DeliverableAssignment,
                  DeliverableAssignment.deliverable_id == DeliverableStatusLog.deliverable_id)
            .filter(DeliverableStatusLog.started_at >= start, DeliverableStatusLog.started_at < end,
                    DeliverableStatusLog.status.in_(DELIVERED_STATUSES),
                    DeliverableAssignment.designer_id.in_(f.user_ids)))
    ids = set()
    for uid, did in rows:
        f.delivered[uid].add(did)
        ids.add(did)
    if ids:
        linked = (db.session.query(ProjectSubmissionDeliverable.deliverable_id)
                  .filter(ProjectSubmissionDeliverable.deliverable_id.in_(ids)).distinct())
        f.with_upload = {did for (did,) in linked}


def _waiting_approval(f):
    """Approvals in front of each person right now: streams uploaded and
    awaiting approval, and deliverables waiting on the client, on the projects
    they lead or own."""
    waiting = or_(*(col == _STREAM_WAITING for col in _STREAM_COLUMNS), Deliverable.status == _CLIENT_WAITING)
    rows = (db.session.query(Project.cs_lead_id, Project.project_owner_id,
                             Deliverable.status, *_STREAM_COLUMNS)
            .join(Deliverable, Deliverable.project_id == Project.id)
            .filter(waiting, Project.cancelled_at.is_(None),
                    or_(Project.cs_lead_id.in_(f.user_ids), Project.project_owner_id.in_(f.user_ids))))
    for lead_id, owner_id, status, *streams in rows:
        n = sum(1 for s in streams if s == _STREAM_WAITING) + (1 if status == _CLIENT_WAITING else 0)
        for uid in {lead_id, owner_id} - {None}:
            f.waiting_approval[uid] += n
