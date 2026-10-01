"""
The shared project sets every CS page loads from, so their counts agree.

base_projects() ⊃ open_projects() ⊃ active_projects(): every non-draft
project, then minus closed, then minus cancelled jobs awaiting close-out.
"""
from sqlalchemy.orm import joinedload, selectinload

from app.modules.core.shared.models import Project, ProjectDesigner
from app.modules.client_servicing.models import ClientServicing


def eager_load(query):
    """Bulk-loads every relationship the row serializer touches, to avoid
    N+1 queries. lib/calendar.py relies on these being loaded too."""
    return query.options(
        joinedload(Project.cs_lead),
        joinedload(Project.project_owner),
        joinedload(Project.client_brand),
        selectinload(Project.assigned_designers).joinedload(ProjectDesigner.designer),
        joinedload(Project.client_servicing).joinedload(ClientServicing.scope),
        selectinload(Project.project_deliverables),
    )


def base_projects():
    """Every non-draft project, eager-loaded, closed ones included. The base
    query for the Calendar, Monthly Summary, Closed and open_projects()."""
    return eager_load(Project.query).filter(Project.project_status != 'draft')


def open_projects():
    """base_projects() minus closed ones; used by the Table. Left join, so a
    project with no CS row still lists."""
    return base_projects().outerjoin(
        ClientServicing, ClientServicing.project_id == Project.id,
    ).filter(ClientServicing.closed_at.is_(None))


def active_projects():
    """The worklist every CS page counts: open projects minus cancelled ones
    waiting in the close-out strip. The Dashboard and Invoicing By Project
    both load through this, so their counts can't differ."""
    return open_projects().filter(Project.cancelled_at.is_(None))
