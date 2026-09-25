"""The dashboard's project fetch: which projects a user sees, loaded once per request with everything the cards read."""
from flask import g, has_request_context, request
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import can
from app.modules.core.shared.models import (
    BriefFlag, BriefFlagMessage, DecisionFlag, Deliverable, DeliverableAssignment,
    Project, ProjectCustomer, ProjectDesigner, ProjectSecondaryCS,
)

INACTIVE_STATUSES = ('approved', 'handed_to_production')


def scope_query(user, active_only=True):
    """Non-draft projects `user` sees on the dashboard; active_only also drops approved and handed-to-production."""
    base = Project.query.filter(Project.project_status != 'draft')
    if active_only:
        base = base.filter(Project.project_status.notin_(INACTIVE_STATUSES))

    # Role literals pick which slice a role sees, not whether it may see the
    # dashboard. The branches are exclusive; admin's wildcard would match several.
    if user.role in ('admin', 'management'):
        return base
    if user.role == 'cs':
        secondary_ids = select(ProjectSecondaryCS.project_id).where(ProjectSecondaryCS.user_id == user.id)
        return base.filter(db.or_(Project.cs_lead_id == user.id, Project.id.in_(secondary_ids)))
    if user.role == 'project_owner':
        return base.filter(Project.project_owner_id == user.id)
    if user.role in ('designer', 'team_lead'):
        assigned_ids = select(ProjectDesigner.project_id).where(ProjectDesigner.user_id == user.id)
        return base.filter(Project.id.in_(assigned_ids))
    # Any other role sees everything with view_all_projects, otherwise nothing.
    if can('view_all_projects', user):
        return base
    return base.filter(Project.id.in_([]))


def _project_load_options():
    """Every relationship the dashboard helpers read per project, so none of them lazy-loads."""
    return (
        joinedload(Project.cs_lead),
        joinedload(Project.lead_designer),
        joinedload(Project.concept_designer),
        joinedload(Project.kv_designer),
        selectinload(Project.assigned_designers).joinedload(ProjectDesigner.designer),
        selectinload(Project.project_deliverables)
            .selectinload(Deliverable.disciplines).joinedload(DeliverableAssignment.designer),
        selectinload(Project.project_customers).joinedload(ProjectCustomer.customer),
        selectinload(Project.project_customers).selectinload(ProjectCustomer.deliverables),
        selectinload(Project.status_logs),
        selectinload(Project.posm_channels),
        selectinload(Project.brief_flags).joinedload(BriefFlag.created_by),
        selectinload(Project.brief_flags)
            .selectinload(BriefFlag.messages).joinedload(BriefFlagMessage.author),
        selectinload(Project.brief_flags).joinedload(BriefFlag.deliverable)
            .selectinload(Deliverable.disciplines).joinedload(DeliverableAssignment.designer),
    )


def _request_cache():
    """Per-request memo; starts empty whenever the request changes, even under a shared app context."""
    if not has_request_context():
        return {}
    current = request._get_current_object()
    if g.get('_dashboard_cache_request') is not current:
        g._dashboard_cache_request = current
        g._dashboard_cache = {}
    return g._dashboard_cache


def request_memo(key, compute):
    """compute() once per request for `key`. For read-only pages: a change made later in the request is not seen."""
    cache = _request_cache()
    if key not in cache:
        cache[key] = compute()
    return cache[key]


def load_scoped_projects(user):
    """Active scoped projects with everything the cards read, fetched once per request."""
    return list(request_memo(
        ('active', user.id, user.role),
        lambda: scope_query(user).options(*_project_load_options()).order_by(Project.id).all(),
    ))


def load_active_projects():
    """Every active non-draft project company-wide, loaded like load_scoped_projects, once per request."""
    return list(request_memo(
        ('active_all',),
        lambda: (Project.query
                 .filter(Project.project_status != 'draft', Project.project_status.notin_(INACTIVE_STATUSES))
                 .options(*_project_load_options()).order_by(Project.id).all()),
    ))


def load_projects(project_ids):
    """{id: Project} for these ids, loaded with everything the cards read, in one fetch."""
    ids = sorted(set(project_ids))
    if not ids:
        return {}
    projects = Project.query.filter(Project.id.in_(ids)).options(*_project_load_options()).all()
    return {p.id: p for p in projects}


def load_scoped_project_names(user):
    """{id: name} for every non-draft project in scope, approved ones included, fetched once per request."""
    return dict(request_memo(
        ('names', user.id, user.role),
        lambda: dict(scope_query(user, active_only=False).with_entities(Project.id, Project.name).all()),
    ))


def open_decision_flags(project_ids):
    """{project_id: newest unresolved DecisionFlag} in one query, with raiser and messages preloaded."""
    if not project_ids:
        return {}
    flags = (DecisionFlag.query
             .filter(DecisionFlag.project_id.in_(project_ids), DecisionFlag.is_resolved.is_(False))
             .options(joinedload(DecisionFlag.created_by), selectinload(DecisionFlag.messages))
             .order_by(DecisionFlag.created_at.desc())
             .all())
    newest = {}
    for flag in flags:
        newest.setdefault(flag.project_id, flag)
    return newest
