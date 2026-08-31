"""
project_overlay/create.py — the multi-step "New Project" create-draft flow:
create shell, draft-card list, finalize/validation, draft deletion.

_CREATE_REGION_NAMES / _CREATE_REGION_ORDER live in ._common because
details.py's _build_details_context needs them too.
"""

from flask import render_template, abort, request, jsonify
from flask_login import login_required
from app.modules.core.shared.lib.users import active_users_query

from app.modules.core.shared.models import Project

from ._common import (
    project_overlay_bp,
    _get_actor,
    _scoped_deliverables_query,
    _recompute_initial_deadline,
    _CREATE_REGION_NAMES,
    _CREATE_REGION_ORDER,
    _parse_edit_date,
)

def _can_create_project(actor):
    """Who can start a new project — admin/cs/management/project_owner.
    Role-only; there's no project yet to scope against."""
    return actor.role in ('admin', 'cs', 'management', 'project_owner')


def _drop_unselected_brief_data(project):
    """At finalize, only the selected brief type's data survives — anything
    entered for the other type while trying it out is dropped. Both coexist
    freely until here (see overlay_create_draft) so switching never loses work."""
    from app.modules.core.shared.extensions import db
    if project.brief_type == 'standard':
        # deleting ProjectCustomer rows cascades to their C&CM deliverables.
        for pc in list(project.project_customers):
            db.session.delete(pc)
        project.has_concept = False
        project.has_kv = False
        project.concept_deadline = None
        project.kv_deadline = None
        project.concept_options_required = None
        project.kv_options_required = None
        project.kv_requirements = None
        project.urgency = None
    else: # ccm
        from app.modules.core.shared.models import Deliverable
        Deliverable.query.filter_by(project_id=project.id, project_customer_id=None).delete()
        project.design_type_id = None
        project.client_expectation = None
        project.what_to_avoid = None
        project.additional_information = None
        project.is_production_only = False
        project.preproduction_requirements = None


def _create_mode_context(project, actor):
    """Picklists/options a blank project needs for the create-mode shell."""
    from app.modules.core.shared.models import User, Client, Customer, DesignType, DesignDirection

    customers_by_region = {
        region: Customer.query.filter_by(region=region).order_by(Customer.name).all()
        for region in _CREATE_REGION_ORDER
    }
    selected_customer_ids = {pc.customer_id for pc in project.project_customers if not pc.cancelled}

    # can_manage_reference_files — duplicated from _build_details_context
    # (its live version folds in extra checks that don't apply here).
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    can_manage_reference_files = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )

    return {
        'cs_lead_options': active_users_query().filter(User.role.in_(['cs', 'admin', 'management'])).order_by(User.name).all(),
        'project_owner_options': active_users_query().filter_by(role='project_owner').order_by(User.name).all(),
        'client_options': Client.query.order_by(Client.name).all(),
        'design_type_options': DesignType.query.order_by(DesignType.name).all(),
        'design_direction_options': DesignDirection.query.order_by(DesignDirection.name).all(),
        'customers_by_region': customers_by_region,
        'region_names': _CREATE_REGION_NAMES,
        'selected_customer_ids': selected_customer_ids,
        'can_create_project': _can_create_project(actor),
        'can_manage_reference_files': can_manage_reference_files,
    }


@project_overlay_bp.route('/projects/overlay/new', methods=['POST'])
@login_required
def overlay_create_draft():
    """Create or (given a project_id) patch the draft Project the create-mode
    overlay works against. One endpoint for both — the frontend just posts
    "here's what I know so far" and gets a project_id back."""
    from datetime import datetime as _dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Scope, ProjectCustomer, Customer
    from app.modules.core.shared.services.status_tracking import record_project_status

    actor = _get_actor()
    if not _can_create_project(actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    project_id = data.get('project_id')

    draft = None
    if project_id:
        candidate = Project.query.get(project_id)
        if candidate and candidate.project_status == 'draft' and (
            candidate.created_by_id == actor.id or actor.role in ('admin', 'management')
        ):
            draft = candidate
        elif candidate and candidate.project_status != 'draft':
            return jsonify({'error': 'This project has already been created — refresh and open it normally.'}), 400

    if not draft:
        default_scope = Scope.query.filter_by(active=True).first()
        draft = Project(
            name=(data.get('name') or '').strip() or 'Untitled Draft',
            client='TBD',
            # cs_lead_id is NOT NULL — default to the actor; the CS Lead
            # select lets them change it before finalizing.
            cs_lead_id=int(data['cs_lead_id']) if data.get('cs_lead_id') else actor.id,
            creator=actor,
            project_status='draft',
            scope_id=default_scope.id if default_scope else 1,
            briefing_date=_dt.utcnow().date(),
        )
        db.session.add(draft)
        db.session.flush()
        record_project_status(draft, 'draft', actor)

    # Every field below is optional per call — autosave sends only the field
    # that changed, so a call with none still succeeds.
    if 'name' in data:
        draft.name = (data.get('name') or '').strip() or 'Untitled Draft'
    if 'job_number' in data:
        # job_number is unique — check here for a clean error instead of a
        # 500 from the DB constraint.
        job_number = (data.get('job_number') or '').strip() or None
        if job_number and Project.query.filter(Project.job_number == job_number, Project.id != draft.id).first():
            return jsonify({'error': f'Job number "{job_number}" is already in use.'}), 400
        draft.job_number = job_number
    if 'brief_type' in data and data['brief_type'] in ('standard', 'ccm'):
        draft.brief_type = data['brief_type']
    if data.get('cs_lead_id'):
        # cs_lead_id is NOT NULL — ignore an empty selection rather than null it.
        draft.cs_lead_id = int(data['cs_lead_id'])
    if 'project_owner_id' in data:
        draft.project_owner_id = int(data['project_owner_id']) if data.get('project_owner_id') else None
    if 'client_id' in data:
        draft.client_id = int(data['client_id']) if data.get('client_id') else None
    if 'contact_id' in data:
        draft.contact_id = int(data['contact_id']) if data.get('contact_id') else None
    if 'design_teams' in data:
        draft.design_teams_requested = ','.join(data.get('design_teams') or [])
    # first_output_deadline is derived — see _recompute_initial_deadline() at
    # the end of this route.
    if 'execution_date' in data:
        draft.execution_date = _parse_edit_date(data.get('execution_date'))
    if 'is_production_only' in data:
        draft.is_production_only = bool(data.get('is_production_only'))
    if 'preproduction_requirements' in data:
        draft.preproduction_requirements = data.get('preproduction_requirements') or None

    # Standard-only fields
    if 'design_type_id' in data:
        draft.design_type_id = int(data['design_type_id']) if data.get('design_type_id') else None
    if 'design_direction_id' in data:
        draft.design_direction_id = int(data['design_direction_id']) if data.get('design_direction_id') else None
    if 'client_expectation' in data:
        draft.client_expectation = data.get('client_expectation') or None
    if 'what_to_avoid' in data:
        draft.what_to_avoid = data.get('what_to_avoid') or None
    if 'additional_information' in data:
        draft.additional_information = data.get('additional_information') or None

    # C&CM-only. Concept and KV are one tickbox/deadline/options set in create
    # mode but two column-sets in the model — mirror each write onto both
    # sides. concept_kv_requirements is stored on kv_requirements.
    if 'urgency' in data:
        draft.urgency = data.get('urgency') or None
    if 'has_concept_kv' in data:
        needed = bool(data.get('has_concept_kv'))
        draft.has_concept = needed
        draft.has_kv = needed
    if 'concept_kv_deadline' in data:
        parsed = _parse_edit_date(data.get('concept_kv_deadline'))
        draft.concept_deadline = parsed
        draft.kv_deadline = parsed
    if 'concept_kv_requirements' in data:
        draft.kv_requirements = data.get('concept_kv_requirements') or None
    if 'concept_kv_options_required' in data:
        value = data.get('concept_kv_options_required')
        draft.concept_options_required = value or None
        draft.kv_options_required = value or None

    # C&CM customer picker — sent as the full checked set each time. Customers
    # no longer checked are removed (nothing downstream references a draft yet).
    if 'customer_ids' in data:
        wanted_ids = {int(cid) for cid in (data.get('customer_ids') or [])}
        existing = {pc.customer_id: pc for pc in draft.project_customers}
        for customer_id, pc in existing.items():
            if customer_id not in wanted_ids:
                db.session.delete(pc)
        for customer_id in wanted_ids:
            if customer_id not in existing and Customer.query.get(customer_id):
                db.session.add(ProjectCustomer(project_id=draft.id, customer_id=customer_id))

        # Keep ProjectRegion synced to the selected customers' regions — the
        # NAS folder tree is built off ProjectRegion. Full replace.
        from app.modules.core.shared.models import ProjectRegion
        wanted_regions = {
            c.region for c in Customer.query.filter(Customer.id.in_(wanted_ids)).all() if c.region
        }
        ProjectRegion.query.filter_by(project_id=draft.id).delete()
        for region in wanted_regions:
            db.session.add(ProjectRegion(project_id=draft.id, region=region))        

    draft.last_autosaved_at = _dt.utcnow()
    _recompute_initial_deadline(draft)
    db.session.commit()

    return jsonify({
        'success': True,
        'project_id': draft.id,
        'first_output_deadline': draft.first_output_deadline.strftime('%d %b %Y') if draft.first_output_deadline else None,
    })


@project_overlay_bp.route('/projects/<int:project_id>/overlay/create')
@login_required
def overlay_create_shell(project_id):
    """The create-mode overlay shell — Details then Deliverables only, no
    lifecycle sidebar. Only for the draft's creator (or admin/management),
    and only while it's still a draft."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft' or not (
        project.created_by_id == actor.id or actor.role in ('admin', 'management')
    ):
        abort(403)

    context = _create_mode_context(project, actor)
    return render_template('project_overlay/_overlay_create.html', project=project, **context)


def _can_finalize_create(project, actor):
    """The draft's creator, or admin/management. (The finalize routes also
    check project_status == 'draft' separately.)"""
    return project.created_by_id == actor.id or actor.role in ('admin', 'management')


def _validate_for_finalize(project):
    """Return an error string, or None if ready to become a real project.
    Standard needs a deliverable; C&CM needs either Concept & KV with a
    deadline or at least one deliverable."""
    if not project.name or not project.client_id or not project.cs_lead_id or not project.brief_type:
        return 'Fill in Name, Client, CS Lead, and Brief Type before creating this project.'

    from app.modules.core.shared.models import Deliverable
    has_deliverables = _scoped_deliverables_query(project).first() is not None

    if project.brief_type == 'standard':
        if not has_deliverables:
            return 'Add at least one deliverable before creating this project.'
        return None

    # C&CM
    has_concept_kv = bool(project.has_concept and project.concept_deadline)
    if not has_concept_kv and not has_deliverables:
        return 'Add Concept & KV info with a deadline, or at least one deliverable, before creating this project.'
    return None


@project_overlay_bp.route('/projects/<int:project_id>/overlay/create/summary')
@login_required
def overlay_create_summary(project_id):
    """Renders the confirm-and-create modal. A validation failure comes back
    as JSON so the frontend can toast it instead of opening a modal."""
    from app.modules.core.shared.models import Deliverable

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft' or not _can_finalize_create(project, actor):
        abort(403)

    error = _validate_for_finalize(project)
    if error:
        return jsonify({'success': False, 'error': error})

    deliverables = _scoped_deliverables_query(project).order_by(Deliverable.id).all()
    customers = [pc for pc in project.project_customers if not pc.cancelled] if project.brief_type == 'ccm' else []

    html = render_template(
        'project_overlay/_overlay_create_summary.html',
        project=project, deliverables=deliverables, customers=customers,
    )
    return jsonify({'success': True, 'html': html})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/create/finalize', methods=['POST'])
@login_required
def overlay_create_finalize(project_id):
    """Confirm button — turns the draft into a real project. Re-validates
    server-side (the summary and this click can be minutes apart)."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable
    from app.modules.core.shared.services.status_tracking import record_project_status
    from app.modules.projects.routes.project_preproduction import _apply_skip_to_preproduction
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft' or not _can_finalize_create(project, actor):
        abort(403)

    error = _validate_for_finalize(project)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    record_project_status(project, 'briefed', actor)

    _drop_unselected_brief_data(project) # NEW

    # Production Only (Standard) — every deliverable skips straight to
    # Pre-Production.
    if project.is_production_only:
        deliverables = Deliverable.query.filter_by(project_id=project.id).all()
        if deliverables:
            _apply_skip_to_preproduction(project, deliverables, actor)

    db.session.commit()

    log_activity('project_created', f'"{project.name}" was created',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)


    from flask import current_app as _app
    from app.modules.core.shared.services.nas import _run_in_background, create_project_folders
    _pid = project.id
    _app_obj = _app._get_current_object()
    _run_in_background(_app_obj, lambda: create_project_folders(
        Project.query.get(_pid)
    ))

    return jsonify({'success': True, 'project_id': project.id})


@project_overlay_bp.route('/projects/overlay/drafts')
@login_required
def list_drafts():
    """Resumable-drafts entry point. "+ New Project" calls this first; if any
    drafts come back the frontend shows a picker. Creators see their own;
    admin/management see everyone's. Path is under /projects/overlay/ to avoid
    colliding with the legacy /projects/drafts route."""
    actor = _get_actor()
    query = Project.query.filter_by(project_status='draft')
    if actor.role not in ('admin', 'management'):
        query = query.filter_by(created_by_id=actor.id)
    # Most-recently-worked-on first — the one they just left is the one they
    # most likely want back.
    drafts = query.order_by(Project.last_autosaved_at.desc()).all()

    if not drafts:
        return jsonify({'has_drafts': False})

    html = render_template(
        'project_overlay/_overlay_create_drafts_picker.html',
        drafts=drafts, actor=actor,
    )
    return jsonify({'has_drafts': True, 'html': html})


@project_overlay_bp.route('/projects/<int:project_id>/draft', methods=['DELETE'])
@login_required
def delete_draft(project_id):
    """Discard an abandoned draft — creator or admin/management, and only
    while it's still a draft. Cleans up its reference files from the NAS first
    (cascade only removes DB rows, not NAS files)."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.nas import delete_app_file, build_file_path

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft':
        abort(404)
    if not (project.created_by_id == actor.id or actor.role in ('admin', 'management')):
        abort(403)

    # delete_app_file() logs and swallows its own NAS failures, so no
    # try/except needed here.
    for f in list(project.reference_files):
        nas_path = build_file_path(project, 'Reference Files', f.original_filename)
        delete_app_file(nas_path)

    project_name = project.name
    db.session.delete(project)
    db.session.commit()

    log_activity('project_draft_deleted', f'Draft "{project_name}" was discarded',
                 user=actor, entity_type='project', entity_name=project_name, entity_id=project_id)

    return jsonify({'success': True})
