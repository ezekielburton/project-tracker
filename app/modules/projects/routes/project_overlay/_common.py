"""
The shared overlay blueprint plus helpers used by two or more route files.
Route-specific helpers live in their own file.

template_folder '../../templates' resolves to app/modules/projects/templates.
"""

from flask import Blueprint

from app.modules.core.shared.lib.capabilities import can, effective_user

project_overlay_bp = Blueprint('project_overlay', __name__, template_folder='../../templates')

def _get_actor():
    """Emulation-aware actor: an admin viewing-as another user acts as that
    user. The overlay's local name for effective_user()."""
    return effective_user()

def submissions_blocked_reason(project):
    """Why Submissions is read-only for this project, or None when it's open.

    A Briefed project takes no draft work until Start Project. Exception: a
    Briefed project that already has a submission stays open (legacy data;
    new projects can't get there because the first draft is blocked)."""
    if project.project_status != 'briefed':
        return None

    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectSubmission

    grandfathered = db.session.query(
        ProjectSubmission.query.filter_by(project_id=project.id).exists()
    ).scalar()
    if grandfathered:
        return None
    return 'This project has not been started yet.'

def _can_manage_deliverables(project, actor):
    """Admin/management, the project's CS Lead / Secondary CS / Project Owner,
    the draft's creator while it's still a draft, or anyone with an approved
    edit-access grant."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
        or (project.project_status == 'draft' and actor.id == project.created_by_id)
        or _has_edit_access_grant(project, actor)
    )

def _has_edit_access_grant(project, actor):
    """True if actor has an approved ProjectEditAccessRequest on this project."""
    from app.modules.core.shared.models import ProjectEditAccessRequest
    return ProjectEditAccessRequest.query.filter_by(
        project_id=project.id, user_id=actor.id, status='approved'
    ).first() is not None

def _can_manage_flags(actor):
    """Can raise or reply to a Brief Flag. Role-only: applies on any project
    the actor can see."""
    return can('raise_flags', actor)

def _can_resolve_flag(flag, actor):
    """The flag's creator, or admin/management."""
    return flag.created_by_id == actor.id or can('manage_flags', actor)

def _build_ccm_deliverable_sections(project, with_catalog=False):
    """Group a C&CM project's deliverables as Region -> Customer -> Deliverables.
    Customers with no region go under 'other'. with_catalog=True also loads
    each customer's DeliverableType catalog (Edit Deliverables needs it).
    """
    from app.modules.core.shared.models import Deliverable, DeliverableType, DeliverableAssignment
    from sqlalchemy.orm import selectinload, joinedload

    active_pcs = [pc for pc in project.project_customers if not pc.cancelled]

    deliverables_by_pc = {}
    if active_pcs:
        pc_ids = [pc.id for pc in active_pcs]
        all_deliverables = (
            Deliverable.query
            .filter(Deliverable.project_id == project.id, Deliverable.project_customer_id.in_(pc_ids))
            # Eager-load what the Deliverables page reads per row (assignments +
            # designers, the type's disciplines) to avoid N+1 queries.
            .options(
                selectinload(Deliverable.disciplines).joinedload(DeliverableAssignment.designer),
                selectinload(Deliverable.deliverable_type).selectinload(DeliverableType.disciplines),
            )
            .order_by(Deliverable.id)
            .all()
        )
        for d in all_deliverables:
            deliverables_by_pc.setdefault(d.project_customer_id, []).append(d)

    catalog_by_customer = {}
    if with_catalog and active_pcs:
        customer_ids = {pc.customer_id for pc in active_pcs}
        all_types = (
            DeliverableType.query
            .filter(DeliverableType.customer_id.in_(customer_ids), DeliverableType.is_active.is_(True))
            .order_by(DeliverableType.name)
            .all()
        )
        for t in all_types:
            catalog_by_customer.setdefault(t.customer_id, []).append(t)

    region_names = {
        'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar',
        'bahrain': 'Bahrain', 'oman': 'Oman', 'other': 'Other',
    }
    region_order = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman', 'other']

    by_region = {}
    for pc in active_pcs:
        # Only region_order is rendered, so an unlisted region folds into
        # 'other' rather than hiding the customer.
        region_key = pc.customer.region if pc.customer.region in region_names else 'other'
        by_region.setdefault(region_key, []).append(pc)

    sections = []
    for region_key in region_order:
        if region_key not in by_region:
            continue
        customers = []
        for pc in by_region[region_key]:
            entry = {'project_customer': pc, 'deliverables': deliverables_by_pc.get(pc.id, [])}
            if with_catalog:
                entry['catalog'] = catalog_by_customer.get(pc.customer_id, [])
            customers.append(entry)
        sections.append({
            'key': region_key,
            'name': region_names.get(region_key, region_key.title()),
            'customers': customers,
        })
    return sections

def _recompute_initial_deadline(project):
    if project.brief_type == 'ccm' and project.has_concept and project.concept_deadline:
        project.first_output_deadline = project.concept_deadline
        return
    deadlines = [d.design_deadline for d in _scoped_deliverables_query(project).all() if d.design_deadline]
    project.first_output_deadline = min(deadlines) if deadlines else None

def _scoped_deliverables_query(project):
    """Deliverables belonging to project.brief_type's data — Standard ones have
    project_customer_id=None, C&CM ones have a customer. (A draft can hold data
    for both brief types until finalize, so callers must agree on what counts.)"""
    from app.modules.core.shared.models import Deliverable
    query = Deliverable.query.filter_by(project_id=project.id)
    if project.brief_type == 'ccm':
        return query.filter(Deliverable.project_customer_id.isnot(None))
    return query.filter(Deliverable.project_customer_id.is_(None))

# Shared by create.py's Details step and details.py's _build_details_context.
_CREATE_REGION_NAMES = {
    'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar', 'bahrain': 'Bahrain', 'oman': 'Oman',
}
_CREATE_REGION_ORDER = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman']

# Shared by deliverables.py's status-override picker and details.py's
# _build_details_context admin status-override card.
_DELIVERABLE_STATUS_OVERRIDE_OPTIONS = [
    ('In Design', 'coral'),
    ('Pre-Production', 'oak'),
    ('Handed to Production', 'clover'),
]

# Same options, reused for the project-level bulk picker (_details_top_cards.html).
_PROJECT_STATUS_OVERRIDE_OPTIONS = _DELIVERABLE_STATUS_OVERRIDE_OPTIONS

def _parse_edit_date(raw):
    """'YYYY-MM-DD' -> date; '' -> None. Shared by details.py's Save route and
    create.py's draft autosave."""
    from datetime import datetime as _dt
    if not raw:
        return None
    return _dt.strptime(raw, '%Y-%m-%d').date()

def ensure_posm_channels(project, brief_sections):
    """Create the missing ProjectPosmChannel rows, one per active C&CM customer.
    Leaves Oman's legacy region-level channels (posm_customer_id NULL) alone.
    Commits and returns True if it added any."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectPosmChannel

    GULF_REGION_KEYS = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman']

    # A recreated ProjectCustomer leaves its old UAE channel with a NULL
    # customer; delete it so it's recreated below. UAE only: a NULL Gulf
    # channel is Oman's legacy history, not an orphan.
    orphaned = [ch for ch in project.posm_channels
                if ch.posm_country == 'uae' and ch.posm_customer_id is None]
    if orphaned:
        for ch in orphaned:
            db.session.delete(ch)
        db.session.flush()

    existing_channel_keys = {
        (ch.posm_country, ch.posm_customer_id) for ch in project.posm_channels
    }

    new_channels_added = False
    for region_key in GULF_REGION_KEYS:
        if region_key not in brief_sections:
            continue
        for pc in brief_sections[region_key]:
            if pc.cancelled:
                continue
            if (region_key, pc.id) not in existing_channel_keys:
                db.session.add(ProjectPosmChannel(
                    project_id=project.id,
                    posm_country=region_key,
                    posm_customer_id=pc.id,
                    status='in_queue',
                ))
                new_channels_added = True

    if new_channels_added:
        db.session.commit()
    return new_channels_added
