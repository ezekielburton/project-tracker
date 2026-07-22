#   app/routes/project_list.py
#   
#   Rewrite of the projects page. Replaces main.projects() and its three role branched render targets
#   All now within one template that adapts to the viewing user's role, per app architecture

from datetime import date
from flask import Blueprint, render_template, session, request
from flask_login import login_required, current_user
from sqlalchemy import nullslast
from app import db
from app.models import Project, ProjectSecondaryCS, ProjectDesigner, Deliverable, User, Client as UserModel

project_list_bp = Blueprint('project_list', __name__, url_prefix='/projects-new')

def _serialize_person(u):
    """Same architecture as dashboard.py's _serialize_person"""
    if not u:
        return None
    return {'id': u.id, 'name': u.name, 'avatar_filename': u.avatar_filename}

def _effective_user():
    """Same emulation-aware-actor lookup every other route in this app uses"""
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        return UserModel.query.get(emulating_id)
    return current_user

def _next_deadline_for(deliverable_query):
    """
    Given a Deliverable query already scoped to "this project" or "this
    customer," finds the single most urgent deadline: the earliest
    design_deadline among deliverables that aren't Approved yet.

    Approved deliverables are excluded because once a deliverable is
    Approved there's nothing left to be "next" about — it's done.
    Everything else (in_progress, submitted, revision states, etc.) still
    has a live deadline that matters.

    Deliberately does NOT filter out deadlines that have already passed —
    an overdue deliverable is still the most urgent thing to show, not
    something to quietly drop once its date is behind us.
    """
    d = (
        deliverable_query
        .filter(Deliverable.status != 'approved')
        .order_by(nullslast(Deliverable.design_deadline), nullslast(Deliverable.design_deadline_time))
        .first()
    )
    if d is None or d.design_deadline is None:
        return None
    return {'date': d.design_deadline, 'deliverable_name': d.name}

def _urgency_for(next_deadline, today):
    """
    Computed Urgency - a RAG bucket from how many days away the same next_deadline value actually is.
    Not stored anywhere, it's a pure presentation-layer computation on data we already have.

    Same-day and overdue both bucket into urgent. Overdue pulses, while same day is static.
    """
    if next_deadline is None:
        return None
    days_away = (next_deadline['date'] - today).days
    if days_away < 0:
        return 'overdue'
    if days_away <= 0:
        return 'urgent'
    if days_away <= 2:
        return 'prioritize'
    return 'normal'

def _parse_ids(param_name):
    """
    Reads a comma-seperated query param of integer IDs (e.g. ?cs_lead=3,7)
    and then returns a list of ints, or an empty list if the param isn't set.
    """

    raw = request.args.get(param_name, '')
    if not raw:
        return []
    return [int(v) for v in raw.split(',') if v.strip().isdigit()]

def _parse_values(param_name):
    """
    Same idea, but for comma-separated string values rather than IDs
    (e.g ?urgency=overdue, urgent or ?status=Active,On Hold).
    """
    raw = request.args.get(param_name, '')
    if not raw:
        return []
    return [v for v in raw.split(',') if v]

def _apply_sql_filters(query):
    """
    Filters that map onto the real Project columns. Cheap to push into SQL,
    rather than fetching every row.
    """
    cs_lead_ids = _parse_ids('cs_lead')
    if cs_lead_ids:
        query = query.filter(Project.cs_lead_id.in_(cs_lead_ids))
    
    client_ids = _parse_ids('client')
    if client_ids:
        query = query.filter(Project.client_id.in_(client_ids))
    
    brief_types = _parse_values('brief_type')
    if brief_types:
        query = query.filter(Project.brief_type.in_(brief_types))
    
    search = request.args.get('search', '').strip()
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(
            Project.name.ilike(like),
            Project.job_number.ilike(like)
        ))

    return query

def _apply_row_filters(rows):
    """
    Filters that depend on computed values rather than a single column. This is run against the already serialized row dicts,
    instead of being translated into SQL, so the bucketing logic lives in one place
    """
    designer_ids = _parse_ids('designers')
    if designer_ids:
        row = [r for r in rows if any(d and d['id'] in designer_ids for d in r ['designers'])]
    
    statuses = _parse_values('status')
    if statuses:
        rows = [r for r in rows if r['blanket_status'] in statuses]
    
    urgencies = _parse_values('urgency')
    if urgencies:
        rows = [r for r in rows if r['urgency'] in urgencies]
    
    return rows

def _serialize_row(p):
    """Turns one Project into the flat dict the template needs. Pulled out of index(), now that there are three different queries feeding
    in the same row shape.""" 
    next_deadline = _next_deadline_for(Deliverable.query.filter_by(project_id=p.id))
    return {
        'id': p.id,
        'name': p.name,
        'client': p.client_brand.name if p.client_brand else None,
        'job_number': p.job_number,
        'cs_lead': _serialize_person(p.cs_lead),
        'designers': [_serialize_person(pd.designer) for pd in p.assigned_designers],
        'initial_deadline': p.first_output_deadline,
        'status': p.project_status,
        'blanket_status': _blanket_status(p.project_status),
        'brief_type': p.brief_type,
        'rollup': _rollup_for(Deliverable.query.filter_by(project_id=p.id)) if p.brief_type != 'ccm' else None,
        'customer_count': sum(1 for pc in p.project_customers if not pc.cancelled) if p.brief_type == 'ccm' else None,
        'next_deadline': next_deadline,
        'urgency': _urgency_for(next_deadline, date.today()),
    }

@project_list_bp.route('/')
@login_required
def index():
    """ Three fixes presets. Set now as we build it out"""
    user = _effective_user()
    view = request.args.get('view', 'my')
    order_by = Project.first_output_deadline.asc()

    if view == 'all':
        if user.role in ('cs', 'admin', 'management'):
            projects = Project.query.filter(
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            ).order_by(Project.first_output_deadline.asc()).all()
        elif user.team:
            query = Project.query.filter(
                Project.design_teams_request.contains(user.team),
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            )
        else:
            query = None
    
    elif view == 'approved':
        query = Project.query.filter_by(project_status='approved')
        order_by = Project.approved_at.desc()
    
    else: # 'my' - default
        if user.role in ('cs', 'admin', 'management'):
            if user.role == 'admin':
                query = Project.query.filter(
                    Project.project_status != 'draft',
                    Project.project_status != 'approved'
                )
            else:
                secondary_project_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(
                    user_id=user.id
                ).subquery()
                query = Project.query.filter(
                    db.or_(
                        Project.cs_lead_id == user.id,
                        Project.id.in_(secondary_project_ids)
                    ),
                    Project.project_status != 'draft',
                    Project.project_status != 'approved'

                )
        else:
            assigned_project_ids = db.sessioon.query(Project)
        

    return render_template('project_list/index.html', rows=rows, view=view, effective_role=user.role, today=date.today(), filter_options=filter_options)


@project_list_bp.route('/<int:project_id>/expand')
@login_required
def expand(project_id):
    """
    Fetched on-demand the first time a row is expanded — this is the
    render-on-demand principle we locked at the start: we do NOT
    pre-render every project's customer/deliverable breakdown on initial
    page load just to hide it. Only the rows someone actually expands ever
    hit this endpoint.
    """
    project = Project.query.get_or_404(project_id)

    if project.brief_type == 'ccm':
        rows = []
        for pc in project.project_customers:
            if pc.cancelled:
                continue
            rows.append({
                'label': pc.customer.name,
                'blanket_status': _blanket_status(pc.status),
                'rollup': _rollup_for(Deliverable.query.filter_by(project_customer_id=pc.id)),
                'next_deadline': _next_deadline_for(
                    Deliverable.query.filter_by(project_customer_id=pc.id)
                ),
            })
    else:
        rows = []
        for d in project.project_deliverables:
            rows.append({
                'label': d.name,
                'blanket_status': _blanket_status(d.status),
                'rollup': None,         # a single deliverable has nothing further to roll up
                'next_deadline': _next_deadline_for(
                    Deliverable.query.filter_by(id=d.id)
                ),
            })

    return render_template('project_list/_expand_rows.html', rows=rows, today=date.today())

def _blanket_status(granular_status):
    """ Maps the granular workflow states down to the following:
        Not Started / Active / On Hold / Completed / Archived.
    """

    if granular_status == 'draft':
        return 'Not Started'
    if granular_status == 'on_hold':
        return 'On Hold'
    if granular_status == 'approved':
        return 'Completed'
    return 'Active'

def _rollup_for(deliverable_query):
    """ The computed rollup: Shows how many of this projects deliverables are Approved out of the total."""

    deliverables = deliverable_query.all()
    total = len(deliverables)
    if total == 0:
        return None
    approved = sum(1 for d in deliverables if d.status == 'approved')
    return f'{approved} of {total} Approved'



