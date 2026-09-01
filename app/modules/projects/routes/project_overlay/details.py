"""
project_overlay/details.py — the Design > Details sub-tab (read + save),
project start, the admin status-override actions (deliverable- and
project-level), cancel/uncancel (project and customer), adding a project
customer, the NAS folder link, hold toggling, and the edit-access-request
flow (request/approve/deny).
"""

from datetime import datetime

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app.modules.core.shared.models import Project
from app.modules.core.shared.lib.decorators import role_required
from app.modules.core.shared.lib.users import active_users_query
from app.modules.projects.lib.teams import assignable_teams_for

from ._common import (
    project_overlay_bp,
    _get_actor,
    _can_manage_deliverables,
    _has_edit_access_grant,
    _can_manage_flags,
    _can_resolve_flag,
    _CREATE_REGION_NAMES,
    _CREATE_REGION_ORDER,
    _PROJECT_STATUS_OVERRIDE_OPTIONS,
    _parse_edit_date,
    ensure_posm_channels,
)

# ── Request Editing Access — an assigned designer's self-service path to full
# deliverable-management rights on a project someone else leads, once the CS
# Lead (or Secondary CS/management/admin) approves. See ProjectEditAccessRequest
# and the request/approve/deny routes below. ──

def _is_assigned_designer(project, actor):
    """True if actor has a real assignment on this project — deliverable-level
    (DeliverableAssignment), project-level (ProjectDesigner), or Concept/KV
    designer (C&CM). Same three surfaces notifications.py sweeps."""
    if actor.role not in ('designer', 'team_lead'):
        return False
    if any(pd.user_id == actor.id for pd in project.assigned_designers):
        return True
    if actor.id in (project.concept_designer_id, project.kv_designer_id):
        return True
    return any(
        a.designer_id == actor.id
        for d in project.project_deliverables
        for a in d.disciplines
    )


# Fixed one-time cutover line: Request Editing Access applies to projects that
# existed when the feature shipped, not a rolling window.
_EDIT_ACCESS_CUTOFF = datetime(2026, 8, 26, 13, 10, 0)


def _project_edit_access_eligible(project):
    """Which projects Request Editing Access applies to — any open project,
    excluding drafts, cancelled projects, and anything created on/after the
    cutoff (new projects use the normal assignment flow)."""
    return (
        project.project_status != 'draft'
        and project.cancelled_at is None
        and project.created_at is not None
        and project.created_at < _EDIT_ACCESS_CUTOFF
    )




def _can_decide_edit_access_request(project, actor):
    """Who can approve/deny a request — admin/management, CS Lead, Secondary
    CS, or the assigned Project Owner. Deliberately NOT _can_manage_deliverables
    (which now includes edit-access grants), so a just-granted designer can't
    approve someone else's request."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )


def _can_cancel_project(project, actor):
    """Cancel/Reactivate — admin/management, CS Lead, Secondary CS, or the
    assigned Project Owner."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )


def _can_toggle_hold(project, actor):
    """On Hold — admin, this project's CS Lead, or Secondary CS. Deliberately
    narrower than _can_cancel_project (no Management/Project Owner) to match the
    existing behaviour; worth revisiting if that's an oversight."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role == 'admin'
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
    )


# ── Admin status override (deliverable-level, plus a project-level bulk
# version; see override_project_status() below) ──
# There is no stored project-pill override: project status is a live roll-up of
# the project's deliverables, so a stored override would be clobbered on the
# next deliverable change. The project-level control is instead a bulk WRITE —
# it applies the picked status to every deliverable (and, for C&CM, every
# ProjectPosmChannel), then the pill recomputes as usual. Both overrides write
# the same real fields a normal status change would, so everything downstream
# stays correct. Built for cleaning up old projects, not as a substitute for
# the real status actions (Approve, Mark Done, Client Approval).

# Raw ProjectPosmChannel.status a project-level bulk override writes per label,
# so the per-customer rows read back as the same label the deliverables got.
# 'approved' is what a real Client Approval writes, reused here for
# "Pre-Production".
_PROJECT_STATUS_OVERRIDE_CHANNEL_WRITE = {
    'In Design': 'in_queue',
    'Pre-Production': 'approved',
    'Handed to Production': 'handed_to_production',
}

# Raw Deliverable.status an "In Design" override writes — 'in_progress' as a
# generic reset (every pre-approval raw value reads as "In Design"). The two
# post-approval labels both write status='approved'; which one shows depends on
# the needs_/status_ stream fields, handled in override_deliverable_status().
_DELIVERABLE_STATUS_WRITE = {
    'In Design': 'in_progress',
}


def _build_details_context(project, actor):
    """Everything the Design > Details sub-tab needs — permissions, picker
    option lists, designer rows, C&CM concept/kv data. Shared by the
    initial /overlay fetch (which embeds Details directly) and the
    standalone /overlay/details fetch (used when navigating back to
    Details after visiting another sub-tab), so the two can never drift
    apart from each other."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.lib.status_vocabulary import derive_project_status
    from app.modules.core.shared.services.status_tracking import project_status_started_at, project_client_approved_at

    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}

    can_reassign_cs_lead = actor.role in ('admin', 'management')
    can_manage_cs = actor.role in ('admin', 'management') or actor.id == project.cs_lead_id
    can_manage_reference_files = (
        can_manage_cs
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    can_edit_project = can_manage_reference_files

    can_assign_owner = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.role == 'project_owner'
    )

    cs_lead_options = active_users_query().filter_by(role='cs').order_by(User.name).all() if can_reassign_cs_lead else []

    available_cs_users = active_users_query().filter(
        User.role.in_(['cs', 'admin', 'management']),
        User.id != project.cs_lead_id,
        ~User.id.in_(secondary_cs_ids) if secondary_cs_ids else True
    ).order_by(User.name).all() if can_manage_cs else []

    if actor.role in ('admin', 'management') or actor.id == project.cs_lead_id:
        owner_options = active_users_query().filter_by(role='project_owner').order_by(User.name).all()
    elif actor.role == 'project_owner':
        owner_options = [actor]
    else:
        owner_options = []

    # status pill is a live roll-up, never written directly (see the block
    # comment above). can_override_project_status gates the bulk write, not a
    # stored override.
    status_label, status_class = derive_project_status(project)
    can_override_project_status = actor.role == 'admin'
    # When the raw status last changed (None if it pre-dates ProjectStatusLog).
    status_started_at = project_status_started_at(project)
    # Client-approval moment — only shown separately once Handed to Production.
    client_approved_at = project_client_approved_at(project) if status_label == 'Handed to Production' else None

    requested_teams = [t.strip() for t in (project.design_teams_requested or '').split(',') if t.strip()]
    assignments_by_team = {pd.team: pd for pd in project.assigned_designers}
    all_teams = requested_teams + [t for t in sorted(assignments_by_team) if t not in requested_teams]

    designer_rows = []
    for team in all_teams:
        assignment = assignments_by_team.get(team)
        can_manage = (
            actor.role in ('admin', 'management')
            or actor.team in assignable_teams_for(team)
            or (assignment and assignment.user_id == actor.id)
        )
        options = active_users_query().filter(
            User.team.in_(assignable_teams_for(team)),
            User.role.in_(['designer', 'team_lead'])
        ).order_by(User.name).all() if can_manage else []
        designer_rows.append({
            'team': team,
            'designer': assignment.designer if assignment else None,
            'can_manage': can_manage,
            'options': options,
        })

    can_manage_concept_kv_full = actor.role in ('admin', 'management')
    can_self_claim_concept_kv = actor.role in ('designer', 'team_lead')
    can_manage_concept_kv = can_manage_concept_kv_full or can_self_claim_concept_kv

    if can_manage_concept_kv_full:
        concept_kv_designer_options = active_users_query().filter(
            User.role.in_(['designer', 'team_lead'])
        ).order_by(User.name).all()
    elif can_self_claim_concept_kv:
        concept_kv_designer_options = [actor]
    else:
        concept_kv_designer_options = []

    concept_kv_designer = project.concept_designer or project.kv_designer

    # Start Project — the one manual gate that moves a project off "Briefed".
    # Nothing deliverable-driven does; a project sits at Briefed until started.
    can_start_project = can_edit_project and project.project_status == 'briefed'

    # Cancel/Reactivate — the template branches on project.cancelled_at directly.
    can_cancel_project = _can_cancel_project(project, actor)

    # On Hold — the template checks project.project_status == 'on_hold' directly.
    can_toggle_hold = _can_toggle_hold(project, actor)

    # Cancel Customer — C&CM only. Built from project.project_customers directly
    # (includes cancelled ones — this is the one place to see and reactivate
    # them). Reuses can_cancel_project as the gate.
    customer_rows = []
    if project.brief_type == 'ccm':
        from app.modules.core.shared.lib.status_vocabulary import derive_customer_pipeline_status
        for pc in sorted(project.project_customers, key=lambda x: x.customer.name):
            label, css_class = derive_customer_pipeline_status(pc)
            customer_rows.append({
                'project_customer': pc,
                'status_label': label,
                'status_class': css_class,
            })

    # Add Customer — C&CM, for a campaign that expands after submission. Gated
    # by _can_manage_deliverables (adding a customer creates its deliverables
    # surface). Excludes already-linked customers; re-add via Reactivate above.
    can_manage_customers = project.brief_type == 'ccm' and _can_manage_deliverables(project, actor)
    addable_customers_by_region = {}
    if can_manage_customers:
        from app.modules.core.shared.models import Customer
        linked_customer_ids = {pc.customer_id for pc in project.project_customers}
        addable_customers_by_region = {
            region: [c for c in Customer.query.filter_by(region=region).order_by(Customer.name).all()
                      if c.id not in linked_customer_ids]
            for region in _CREATE_REGION_ORDER
        }

    # Brief Flags — Details' Flags card covers 'project', 'concept', and 'kv'
    # (Concept & KV is project-level info, not its own flaggable entity).
    from app.modules.core.shared.models import BriefFlag
    project_open_flags = (
        BriefFlag.query
        .filter_by(project_id=project.id, is_resolved=False)
        .filter(BriefFlag.flag_type.in_(['project', 'concept', 'kv']))
        .order_by(BriefFlag.created_at)
        .all()
    )
    for f in project_open_flags:
        f.can_resolve = _can_resolve_flag(f, actor)
    can_manage_flags = _can_manage_flags(actor)

    # Edit mode — Client/Type of Design are FKs, so the dropdowns need the full
    # option lists. Only fetched for someone who can edit.
    from app.modules.core.shared.models import Client, DesignType
    client_options = Client.query.order_by(Client.name).all() if can_edit_project else []
    design_type_options = DesignType.query.order_by(DesignType.name).all() if can_edit_project else []

    # Concurrent-edit check — the latest ActivityLog row stands in for a
    # last-modified timestamp (Project has no updated_at). Snapshotted here,
    # sent back with Save, and compared to reject a conflicting overwrite.
    from app.modules.core.shared.models import ActivityLog
    latest_activity = (
        ActivityLog.query
        .filter_by(entity_type='project', entity_id=project.id)
        .order_by(ActivityLog.created_at.desc())
        .first()
    )
    edit_snapshot_at = latest_activity.created_at.isoformat() if latest_activity else ''

    # Request Editing Access — sidebar button state. Status is None/pending/
    # approved/denied; the button hides once approved and renders (in a
    # different state) only for an eligible open project and an assigned designer.
    edit_access_request = None
    if actor.role in ('designer', 'team_lead'):
        from app.modules.core.shared.models import ProjectEditAccessRequest
        edit_access_request = ProjectEditAccessRequest.query.filter_by(
            project_id=project.id, user_id=actor.id
        ).first()
    edit_access_request_status = edit_access_request.status if edit_access_request else None
    show_request_edit_access = (
        edit_access_request_status != 'approved'
        and _project_edit_access_eligible(project)
        and _is_assigned_designer(project, actor)
    )

    return dict(
        status_label=status_label,
        status_class=status_class,
        can_override_project_status=can_override_project_status,
        project_status_override_options=_PROJECT_STATUS_OVERRIDE_OPTIONS,
        status_started_at=status_started_at,
        client_approved_at=client_approved_at,
        can_reassign_cs_lead=can_reassign_cs_lead,
        can_manage_cs=can_manage_cs,
        can_assign_owner=can_assign_owner,
        cs_lead_options=cs_lead_options,
        available_cs_users=available_cs_users,
        owner_options=owner_options,
        designer_rows=designer_rows,
        can_manage_reference_files=can_manage_reference_files,
        can_edit_project=can_edit_project,
        can_manage_concept_kv=can_manage_concept_kv,
        concept_kv_designer_options=concept_kv_designer_options,
        concept_kv_designer=concept_kv_designer,
        can_start_project=can_start_project,
        can_cancel_project=can_cancel_project,
        can_toggle_hold=can_toggle_hold,
        customer_rows=customer_rows,
        can_manage_customers=can_manage_customers,
        addable_customers_by_region=addable_customers_by_region,
        region_names=_CREATE_REGION_NAMES,
        project_open_flags=project_open_flags,
        can_manage_flags=can_manage_flags,
        client_options=client_options,
        design_type_options=design_type_options,
        edit_snapshot_at=edit_snapshot_at,
        show_request_edit_access=show_request_edit_access,
        edit_access_request_status=edit_access_request_status,
    )











@project_overlay_bp.route('/projects/<int:project_id>/overlay')
@login_required
def overlay(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    context = _build_details_context(project, actor)
    # Clears the Projects table's "new updates" dot — fires on opening the
    # overlay, not per sub-tab (Chat has its own watermark). Best-effort.
    from app.modules.core.shared.lib.utils import mark_project_activity_seen
    mark_project_activity_seen(project, actor, 'update')
    return render_template('project_overlay/_overlay.html', project=project, **context)

@project_overlay_bp.route('/projects/<int:project_id>/overlay/details')
@login_required
def overlay_details(project_id):
    """Standalone Design > Details fragment. The initial /overlay fetch
    above already embeds Details directly (so opening a project has no
    extra round-trip) — this route's only caller is the sub-tab switcher
    in project_list.js, used when navigating BACK to Details after
    visiting another sub-tab."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    context = _build_details_context(project, actor)
    template = (
        'project_overlay/_details_standard.html' if project.brief_type == 'standard'
        else 'project_overlay/_details_ccm.html'
    )
    return render_template(template, project=project, **context)



# field name (matches the templates' data-field) -> the label the field is
# rendered under in Details, reused for both the Save log's field list and
# the structured diff — if a field's label on screen ever changes, update
# it here too so the activity log keeps matching what's actually shown.
_DETAILS_FIELD_LABELS = {
    'client_id': 'Client',
    'design_type_id': 'Type of Design',
    'first_output_deadline': 'Initial Deadline',
    'execution_date': 'Final Deadline',
    'client_expectation': 'Client Expectation',
    'what_to_avoid': 'What to Avoid',
    'additional_information': 'Additional Information',
    'briefing_date': 'Briefing Date',
    'concept_deadline': 'Concept & KV Deadline',
    'concept_options_required': 'Options Required',
    'campaign_notes': 'Campaign Notes',
    'kv_requirements': 'Concept & KV Details',
}


def _display_value_for_log(field_name, value):
    """JSON-safe, human-readable form of one field's old/new value for
    ActivityLog.changes. client_id/design_type_id resolve to a name (a
    diff full of raw ids isn't useful to read later); dates become ISO
    strings; everything else already round-trips through json.dumps."""
    if value is None:
        return None
    if field_name == 'client_id':
        from app.modules.core.shared.models import Client
        c = Client.query.get(value)
        return c.name if c else value
    if field_name == 'design_type_id':
        from app.modules.core.shared.models import DesignType
        dt = DesignType.query.get(value)
        return dt.name if dt else value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


@project_overlay_bp.route('/projects/<int:project_id>/overlay/details/save', methods=['POST'])
@login_required
def overlay_details_save(project_id):
    """Edit mode Save. Whitelisted field-by-field update, not a
    generic setattr — every accepted field is named explicitly so this
    route can never be tricked into writing a column the frontend didn't
    actually render an editable row for. Logs which fields changed by name
    plus a structured old/new diff in ActivityLog.changes."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ActivityLog
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    can_edit_project = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    if not can_edit_project:
        return jsonify({'success': False, 'error': 'You do not have permission to edit this project.'}), 403

    data = request.get_json() or {}
    fields = data.get('fields') or {}
    snapshot_at = data.get('edit_snapshot_at') or ''

    latest_activity = (
        ActivityLog.query
        .filter_by(entity_type='project', entity_id=project.id)
        .order_by(ActivityLog.created_at.desc())
        .first()
    )
    current_snapshot = latest_activity.created_at.isoformat() if latest_activity else ''
    if snapshot_at and current_snapshot and snapshot_at != current_snapshot:
        return jsonify({
            'success': False,
            'conflict': True,
            'error': 'This project was changed by someone else while you were editing. Reload and try again.',
        }), 409

    # field name (matches the templates' data-field) -> (Project attr, parser)
    FIELD_MAP = {
        'client_id': ('client_id', lambda v: int(v) if v else None),
        'design_type_id': ('design_type_id', lambda v: int(v) if v else None),
        'first_output_deadline': ('first_output_deadline', _parse_edit_date),
        'execution_date': ('execution_date', _parse_edit_date),
        'client_expectation': ('client_expectation', lambda v: v.strip() or None),
        'what_to_avoid': ('what_to_avoid', lambda v: v.strip() or None),
        'additional_information': ('additional_information', lambda v: v.strip() or None),
        'briefing_date': ('briefing_date', _parse_edit_date),
        'concept_deadline': ('concept_deadline', _parse_edit_date),
        'concept_options_required': ('concept_options_required', lambda v: int(v) if v else None),
        'campaign_notes': ('campaign_notes', lambda v: v.strip() or None),
        'kv_requirements': ('kv_requirements', lambda v: v.strip() or None),
    }

    changes = []
    for field_name, raw_value in fields.items():
        if field_name not in FIELD_MAP:
            continue
        attr_name, parser = FIELD_MAP[field_name]
        try:
            new_value = parser(raw_value)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': f'Invalid value for {field_name}.'}), 400
        old_value = getattr(project, attr_name)
        if old_value != new_value:
            changes.append({'field': field_name, 'old': old_value, 'new': new_value})
            setattr(project, attr_name, new_value)

    if not changes:
        return jsonify({'success': True, 'changed': False})

    db.session.commit()

    field_labels = [_DETAILS_FIELD_LABELS.get(c['field'], c['field']) for c in changes]
    logged_changes = [
        {
            'field': c['field'],
            'label': _DETAILS_FIELD_LABELS.get(c['field'], c['field']),
            'old': _display_value_for_log(c['field'], c['old']),
            'new': _display_value_for_log(c['field'], c['new']),
        }
        for c in changes
    ]

    log_activity(
        'project_edited',
        f'{actor.name} edited {", ".join(field_labels)} on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
        changes=logged_changes,
    )

    return jsonify({'success': True, 'changed': True, 'changes': [c['field'] for c in changes]})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/start', methods=['POST'])
@login_required
def overlay_start_project(project_id):
    """Start Project — the manual gate off "Briefed" (see _build_details_
    context's can_start_project + status_vocabulary.py's derive_project_
    status). One button, one action, both brief types: flips project_status
    from 'briefed' to 'in_progress', which the unified derivation reads as
    "In Design" — no brief_type-specific logic needed here."""
    from flask import jsonify
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.services.status_tracking import record_project_status

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    can_edit_project = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in {a.user_id for a in project.secondary_cs_assignments}
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    if not can_edit_project:
        return jsonify({'success': False, 'error': 'You do not have permission to start this project.'}), 403

    if project.project_status != 'briefed':
        return jsonify({'success': False, 'error': 'This project has already been started.'}), 400

    record_project_status(project, 'in_progress', actor)
    db.session.commit()
    return jsonify({'success': True})


def _write_deliverable_status_override(deliverable, label, actor):
    """Writes the raw fields behind one deliverable-status override target —
    factored out of override_deliverable_status() so
    override_project_status() below can apply the exact same per-deliverable
    logic in bulk without the two ever drifting apart. Does NOT call
    sync_project_pipeline_status() or commit — callers do that once, after
    every deliverable in scope has been written, not once per row.

    The two post-approval labels both write raw status='approved'
    underneath; which one actually displays is entirely a function of
    needs_2d/3d/technical + status_2d/status_3d/technical_status
    (status_vocabulary.py's _post_approval_deliverable_status), so those
    three fields are what this actually varies per target, not the status
    column itself.

    Note: picking "Pre-Production" on a deliverable that structurally
    needs no 2D/3D/Technical follow-up (derive_preproduction_needs finds
    nothing) will still read back as "Handed to Production" immediately —
    same honest behavior a real approval would produce now, not a bug in
    this override.

    Returns False if `label` isn't one of the three real vocabulary
    stages (fields left untouched); True otherwise."""
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.lib.status_vocabulary import derive_preproduction_needs

    if label in _DELIVERABLE_STATUS_WRITE:
        record_deliverable_status(deliverable, _DELIVERABLE_STATUS_WRITE[label], actor)
    elif label in ('Pre-Production', 'Handed to Production'):
        record_deliverable_status(deliverable, 'approved', actor)
        needs_2d, needs_3d, needs_technical = derive_preproduction_needs(deliverable)
        deliverable.needs_2d = needs_2d
        deliverable.needs_3d = needs_3d
        deliverable.needs_technical = needs_technical
        # Pre-Production's real 3-state vocabulary is None (not started) ->
        # 'uploaded' -> 'approved' (see project_preproduction.py's module
        # docstring) — there's no 'in_progress' value anywhere else in that
        # system, so picking "Pre-Production" here resets each needed
        # stream to None (honestly "nothing uploaded yet") rather than
        # inventing a 4th value the real Pre-Production tab wouldn't know
        # how to render.
        stream_value = 'approved' if label == 'Handed to Production' else None
        if needs_2d:
            deliverable.status_2d = stream_value
        if needs_3d:
            deliverable.status_3d = stream_value
        if needs_technical:
            deliverable.technical_status = stream_value
    else:
        return False
    return True


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/<int:deliverable_id>/status/override', methods=['POST'])
@login_required
def override_deliverable_status(project_id, deliverable_id):
    """Admin, or a designer with an approved edit-access grant, status override
    (3-stage vocabulary). See _write_deliverable_status_override() for the
    fields it writes. Calls sync_project_pipeline_status() at the end, since an
    override can flip the project's pill like a real approval would."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable
    from app.modules.core.shared.services.status_tracking import sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status

    deliverable = Deliverable.query.filter_by(id=deliverable_id, project_id=project_id).first_or_404()
    actor = _get_actor()
    if actor.role != 'admin' and not _has_edit_access_grant(deliverable.project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to override this status.'}), 403

    data = request.get_json(silent=True) or {}
    label = data.get('status')

    if not _write_deliverable_status_override(deliverable, label, actor):
        return jsonify({'success': False, 'error': 'Not a valid status for this deliverable.'}), 400

    sync_project_pipeline_status(deliverable.project, actor)
    db.session.commit()
    status_label, status_class = derive_deliverable_status(deliverable)
    return jsonify({'success': True, 'status_label': status_label, 'status_class': status_class})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/status/override', methods=['POST'])
@login_required
def override_project_status(project_id):
    """Admin-only, project-wide version of override_deliverable_status()
    above — sets EVERY deliverable on the project (and, for C&CM, every
    ProjectPosmChannel) to the same one of the three real vocabulary stages
    in one action. Standard: deliverables only (there's no channel concept
    to touch on a Standard project anyway).

    Not a stored project-level override — see the block comment above
    _DELIVERABLE_STATUS_OVERRIDE_OPTIONS for why that is retired. This
    writes the exact same real underlying
    fields override_deliverable_status() would, at every deliverable (and
    channel) the project has, then lets sync_project_pipeline_status()
    recompute the pill fresh at the end, same as any other bulk action.

    C&CM's per-customer expand rows read ProjectPosmChannel.status
    independently of the deliverable-driven roll-up (status_vocabulary.py's
    derive_customer_pipeline_status) — without also writing every channel
    here, the project pill would update immediately while every customer
    row underneath kept showing whatever stale status prompted this in the
    first place. A cancelled customer's channel is written too rather than
    skipped — harmless, since derive_customer_pipeline_status checks
    .cancelled first and never looks at the channel for a cancelled
    customer either way.

    Briefed is bumped to 'in_progress' first, same raw transition Start
    Project performs (see overlay_start_project() above), whenever the
    project is still sitting there — sync_project_pipeline_status() is a
    deliberate no-op while project_status == 'briefed' (see its own
    docstring), so without this bump every deliverable underneath could
    read Handed to Production and the project pill would still just sit
    at Briefed, silently defeating the entire point of this action. On
    Hold and Cancelled are NOT bumped the same way — those are deliberate,
    reason-logged states with their own dedicated toggle (Sidebar
    lifecycle actions), not a default unstarted gate, so this bulk action
    leaves them alone: the deliverables/channels still get written, the
    pill just keeps reading On Hold/Cancelled until someone clears that
    state through the real control, exactly as sync_project_pipeline_status
    already behaves for every other deliverable-affecting action."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Project
    from app.modules.core.shared.services.status_tracking import record_project_status, sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_project_status

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only.'}), 403

    data = request.get_json(silent=True) or {}
    label = data.get('status')
    if label not in _PROJECT_STATUS_OVERRIDE_CHANNEL_WRITE:
        return jsonify({'success': False, 'error': 'Not a valid status.'}), 400

    for deliverable in project.project_deliverables:
        _write_deliverable_status_override(deliverable, label, actor)

    if project.brief_type == 'ccm':
        channel_status = _PROJECT_STATUS_OVERRIDE_CHANNEL_WRITE[label]
        for channel in project.posm_channels:
            channel.status = channel_status

    if project.project_status == 'briefed':
        record_project_status(project, 'in_progress', actor)

    sync_project_pipeline_status(project, actor)
    db.session.commit()
    status_label, status_class = derive_project_status(project)
    return jsonify({'success': True, 'status_label': status_label, 'status_class': status_class})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/cancel', methods=['POST'])
@login_required
def overlay_cancel_project(project_id):
    """Cancel Project — cancel_reason/cancelled_at/cancelled_by_id already
    existed on the model unused. Deliberately doesn't touch project_status
    at all: derive_project_status() checks cancelled_at
    first, ahead of the underlying pipeline stage, so cancelling never
    overwrites (and reactivating never needs to restore) whatever stage the
    project was actually in."""
    from datetime import datetime as dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not _can_cancel_project(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to cancel this project.'}), 403
    if project.cancelled_at is not None:
        return jsonify({'success': False, 'error': 'This project is already cancelled.'}), 400

    reason = ((request.get_json(silent=True) or {}).get('reason') or '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'A reason is required to cancel a project.'}), 400

    project.cancel_reason = reason
    project.cancelled_at = dt.utcnow()
    project.cancelled_by_id = actor.id
    db.session.commit()

    log_activity(
        'project_cancelled',
        f'{actor.name} cancelled "{project.name}": {reason}',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/uncancel', methods=['POST'])
@login_required
def overlay_uncancel_project(project_id):
    """Reactivate — clears the three cancel columns. No reason required,
    same asymmetry as On Hold's Resume (no confirm/note either): reversing
    a cancellation is the safe direction, only cancelling itself needs the
    reason and the confirm gate."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not _can_cancel_project(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to reactivate this project.'}), 403
    if project.cancelled_at is None:
        return jsonify({'success': False, 'error': 'This project is not cancelled.'}), 400

    project.cancel_reason = None
    project.cancelled_at = None
    project.cancelled_by_id = None
    db.session.commit()

    log_activity(
        'project_reactivated',
        f'{actor.name} reactivated "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/project-customers/<int:project_customer_id>/cancel', methods=['POST'])
@login_required
def overlay_cancel_customer(project_customer_id):
    """Cancel one C&CM customer within a project. Cancelling a customer
    freezes its state for invoicing and can be undone. Same shape as
    overlay_cancel_project() above, just scoped to a ProjectCustomer
    instead of the whole Project — reuses the exact same permission gate
    (_can_cancel_project), since who's allowed to cancel a customer within
    a project is the same set of people allowed to cancel the project
    itself.

    "Freezes its state" is mostly free: pc.cancelled already existed and
    every read site that builds the Deliverables/Submissions/Pre-
    Production customer scope-select (_build_ccm_deliverable_sections,
    _build_submission_regions, and the Pre-Production equivalents) already
    excludes a cancelled customer from `all_customers` — so once cancelled,
    that customer simply stops appearing anywhere further work would
    happen, without a single extra guard needed. What was actually missing
    was a way to SET the flag at all; this route (and overlay_uncancel_
    customer below) is that."""
    from datetime import datetime as dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectCustomer
    from app.modules.core.shared.lib.utils import log_activity

    pc = ProjectCustomer.query.get_or_404(project_customer_id)
    project = Project.query.get_or_404(pc.project_id)
    actor = _get_actor()

    if not _can_cancel_project(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to cancel this customer.'}), 403
    if pc.cancelled:
        return jsonify({'success': False, 'error': 'This customer is already cancelled.'}), 400

    reason = ((request.get_json(silent=True) or {}).get('reason') or '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'A reason is required to cancel a customer.'}), 400

    pc.cancelled = True
    pc.cancel_reason = reason
    pc.cancelled_at = dt.utcnow()
    pc.cancelled_by_id = actor.id
    db.session.commit()

    log_activity(
        'customer_cancelled',
        f'{actor.name} cancelled "{pc.customer.name}" on "{project.name}": {reason}',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/project-customers/<int:project_customer_id>/uncancel', methods=['POST'])
@login_required
def overlay_uncancel_customer(project_customer_id):
    """Reactivate — clears the four cancel columns, same asymmetry as
    Project's Reactivate (no reason required, only cancelling itself
    needs one)."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectCustomer
    from app.modules.core.shared.lib.utils import log_activity

    pc = ProjectCustomer.query.get_or_404(project_customer_id)
    project = Project.query.get_or_404(pc.project_id)
    actor = _get_actor()

    if not _can_cancel_project(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to reactivate this customer.'}), 403
    if not pc.cancelled:
        return jsonify({'success': False, 'error': 'This customer is not cancelled.'}), 400

    pc.cancelled = False
    pc.cancel_reason = None
    pc.cancelled_at = None
    pc.cancelled_by_id = None
    db.session.commit()

    log_activity(
        'customer_reactivated',
        f'{actor.name} reactivated "{pc.customer.name}" on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/customers/add', methods=['POST'])
@login_required
def add_project_customer(project_id):
    """Add a customer to an already-submitted C&CM project (a campaign that
    expands after go-live). Gated by _can_manage_deliverables."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Customer, ProjectCustomer, ProjectRegion
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if project.brief_type != 'ccm':
        return jsonify({'success': False, 'error': 'Only C&CM projects have customers.'}), 400
    if not _can_manage_deliverables(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to add a customer to this project.'}), 403

    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id')
    customer = Customer.query.get(int(customer_id)) if customer_id else None
    if not customer:
        return jsonify({'success': False, 'error': 'Select a customer.'}), 400

    existing = ProjectCustomer.query.filter_by(project_id=project.id, customer_id=customer.id).first()
    if existing:
        if existing.cancelled:
            return jsonify({'success': False, 'error': f'{customer.name} was already on this project and was cancelled — use Reactivate instead of adding it again.'}), 400
        return jsonify({'success': False, 'error': f'{customer.name} is already on this project.'}), 400

    pc = ProjectCustomer(project_id=project.id, customer_id=customer.id)
    db.session.add(pc)

    # Keep ProjectRegion synced the same way the create-mode picker does —
    # _build_ccm_design_folders() (nas.py) drives its Region/Customer
    # folder tree off ProjectRegion, not off project_customers directly.
    if customer.region and not ProjectRegion.query.filter_by(project_id=project.id, region=customer.region).first():
        db.session.add(ProjectRegion(project_id=project.id, region=customer.region))

    db.session.flush()

    # Self-heals this customer's own POSM submission channel the same way
    # opening the Submissions tab already does for every customer — see
    # ensure_posm_channels()'s docstring. Scoped to just the new row here
    # (rather than rebuilding every region's full set) since that's the
    # only thing that's actually new.
    if customer.region:
        ensure_posm_channels(project, {customer.region: [pc]})

    db.session.commit()

    log_activity(
        'customer_added',
        f'{actor.name} added "{customer.name}" to "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )

    # Same background NAS folder build every other customer-affecting
    # mutation on a live project uses (see overlay_create_finalize above)
    # — idempotent, so this just adds the new customer's folder without
    # touching anything else in the tree.
    from flask import current_app as _app
    from app.modules.core.shared.services.nas import _run_in_background, create_project_folders
    _pid = project.id
    _app_obj = _app._get_current_object()
    _run_in_background(_app_obj, lambda: create_project_folders(Project.query.get(_pid)))

    return jsonify({'success': True, 'project_customer_id': pc.id, 'customer_name': customer.name})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/nas-folder-link')
@login_required
def overlay_nas_folder_link(project_id):
    """Resolves the project's root NAS folder to a Synology Drive deep-link
    — click-triggered rather than baked
    into the sidebar at render time, since Drive needs a live API resolve
    per folder (see app/nas.py's build_drive_folder_url()). Same path-
    building this route replaces from the old nas_project_url() Jinja
    global."""
    from flask import current_app, jsonify
    from app.modules.core.shared.services.nas import build_drive_folder_url

    project = Project.query.get_or_404(project_id)
    root = current_app.config.get('NAS_PROJECT_ROOT', '/Projects')
    client = project.client_brand.name if project.client_brand else 'Unknown Client'
    folder_path = f'{root}/{project.created_at.year}/{client}/{project.name}'

    url = build_drive_folder_url(folder_path)
    if not url:
        return jsonify({'success': False, 'error': 'Could not reach the NAS.'}), 502
    return jsonify({'success': True, 'url': url})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/toggle-hold', methods=['POST'])
@login_required
def overlay_toggle_hold(project_id):
    """Put on Hold / Resume (JSON). Brackets held_from_status so Resume restores
    the prior status. Permission: _can_toggle_hold."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.status_tracking import record_project_status

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not _can_toggle_hold(project, actor):
        return jsonify({'success': False, 'error': "You do not have permission to change this project's hold status."}), 403

    if project.project_status == 'on_hold':
        restore_to = project.held_from_status or 'briefed'
        record_project_status(project, restore_to, actor)
        project.held_from_status = None
        log_activity(
            'project_resumed', f'Project "{project.name}" resumed (status: {restore_to})',
            user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
        )
    else:
        project.held_from_status = project.project_status
        record_project_status(project, 'on_hold', actor)
        log_activity(
            'project_on_hold', f'Project "{project.name}" put on hold',
            user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
        )

    db.session.commit()
    return jsonify({'success': True})


# ── Request Editing Access — request_edit_access is the sidebar button's
# endpoint; approve/deny are reached from the Approve/Deny buttons on the CS
# Lead/Secondary CS's notification. ──

@project_overlay_bp.route('/projects/<int:project_id>/request-edit-access', methods=['POST'])
@login_required
def request_edit_access(project_id):
    """Designer-initiated: creates (or, after a denial, resets) a pending
    ProjectEditAccessRequest and notifies the CS Lead/Secondary CS. Grants
    nothing itself — access only turns on once approved."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectEditAccessRequest
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_cs_of_edit_access_request

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not _project_edit_access_eligible(project):
        return jsonify({'success': False, 'error': 'Editing access can only be requested on an existing, open project.'}), 400
    if not _is_assigned_designer(project, actor):
        return jsonify({'success': False, 'error': 'Only a designer assigned to this project can request editing access.'}), 403

    existing = ProjectEditAccessRequest.query.filter_by(project_id=project.id, user_id=actor.id).first()
    if existing and existing.status == 'pending':
        return jsonify({'success': False, 'error': 'You already have a pending request for this project.'}), 400
    if existing and existing.status == 'approved':
        return jsonify({'success': False, 'error': 'You already have editing access on this project.'}), 400

    if existing:
        # Re-request after a denial — reset the same row rather than
        # inserting a second one (UNIQUE(project_id, user_id) would reject
        # that anyway), so there's never stale denied history left for the
        # CS Lead to click past.
        existing.status = 'pending'
        existing.requested_at = datetime.utcnow()
        existing.decided_at = None
        existing.decided_by_id = None
    else:
        db.session.add(ProjectEditAccessRequest(project_id=project.id, user_id=actor.id))

    db.session.commit()

    log_activity(
        'edit_access_requested',
        f'{actor.name} requested editing access to "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    notify_cs_of_edit_access_request(project, actor)

    return jsonify({'success': True, 'status': 'pending'})


@project_overlay_bp.route('/projects/edit-access-requests/<int:request_id>/approve', methods=['POST'])
@login_required
def approve_edit_access(request_id):
    """CS Lead/Secondary CS/management/admin decision — approves a pending
    Request Editing Access request, granting the requester
    _can_manage_deliverables-tier access (deliverables + status override)
    on that one project, permanently. See _can_decide_edit_access_request
    for why this uses its own permission check rather than
    _can_manage_deliverables directly."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectEditAccessRequest
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_designer_of_edit_access_decision

    req = ProjectEditAccessRequest.query.get_or_404(request_id)
    project = req.project
    actor = _get_actor()

    if not _can_decide_edit_access_request(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to decide this request.'}), 403
    if req.status != 'pending':
        return jsonify({'success': False, 'error': 'This request has already been decided.'}), 400

    req.status = 'approved'
    req.decided_at = datetime.utcnow()
    req.decided_by_id = actor.id
    db.session.commit()

    log_activity(
        'edit_access_approved',
        f'{actor.name} approved {req.user.name}\'s request for editing access on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    notify_designer_of_edit_access_decision(req, approved=True, triggered_by=actor)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/edit-access-requests/<int:request_id>/deny', methods=['POST'])
@login_required
def deny_edit_access(request_id):
    """Same as approve_edit_access above, but denies. A denied request can
    be re-requested later — see request_edit_access above."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectEditAccessRequest
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_designer_of_edit_access_decision

    req = ProjectEditAccessRequest.query.get_or_404(request_id)
    project = req.project
    actor = _get_actor()

    if not _can_decide_edit_access_request(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to decide this request.'}), 403
    if req.status != 'pending':
        return jsonify({'success': False, 'error': 'This request has already been decided.'}), 400

    req.status = 'denied'
    req.decided_at = datetime.utcnow()
    req.decided_by_id = actor.id
    db.session.commit()

    log_activity(
        'edit_access_denied',
        f'{actor.name} denied {req.user.name}\'s request for editing access on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    notify_designer_of_edit_access_decision(req, approved=False, triggered_by=actor)

    return jsonify({'success': True})
