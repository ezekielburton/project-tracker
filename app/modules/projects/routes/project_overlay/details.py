"""
project_overlay/details.py — the overlay's Details page (read + save),
Start Project, admin status overrides (deliverable and project level),
cancel/reactivate (project and customer), Add Customer, the NAS folder
link, On Hold, and Request Editing Access (request/approve/deny).
"""

from datetime import datetime

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app.modules.core.shared.models import Project
from app.modules.core.shared.lib.users import active_users_query
from app.modules.projects.lib.teams import assignable_teams_for
from app.modules.core.shared.lib.capabilities import can

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

# ── Request Editing Access — an assigned designer asks for deliverable-
# management rights on one project; the CS side approves or denies. ──

def _is_assigned_designer(project, actor):
    """True if actor is assigned work on this project: a deliverable
    assignment, a team lead slot (ProjectDesigner), or Concept/KV designer.
    Uses a role literal: can('claim_work') would pass every admin via the
    wildcard."""
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


# Fixed cutoff, not a rolling window: only projects created before this
# moment can use Request Editing Access.
_EDIT_ACCESS_CUTOFF = datetime(2026, 8, 26, 13, 10, 0)


def _project_edit_access_eligible(project):
    """True for an open project created before the cutoff; excludes drafts
    and cancelled projects."""
    return (
        project.project_status != 'draft'
        and project.cancelled_at is None
        and project.created_at is not None
        and project.created_at < _EDIT_ACCESS_CUTOFF
    )




def _can_decide_edit_access_request(project, actor):
    """Who can approve/deny a request: admin/management, CS Lead, Secondary
    CS, or the assigned Project Owner. Not _can_manage_deliverables — that
    includes edit-access grants, so a granted designer could approve others."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
    )


def _can_cancel_project(project, actor):
    """Cancel/Reactivate: admin/management, CS Lead, Secondary CS, or the
    assigned Project Owner."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
    )


def _can_toggle_hold(project, actor):
    """On Hold: admin, this project's CS Lead, or Secondary CS. Narrower than
    _can_cancel_project (no Management or Project Owner)."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        can('toggle_project_hold', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
    )


# ── Admin status override (per deliverable, plus a project-level bulk) ──
# Project status is a live roll-up of its deliverables, so there is no stored
# project override (it would be clobbered on the next change). The project
# control writes the picked status to every deliverable (and, for C&CM, every
# ProjectPosmChannel), then the pill recomputes. Both write the same fields a
# normal status change does. Meant for cleanup, not for everyday status actions.

# ProjectPosmChannel.status the bulk override writes per label, so customer
# rows read back as the same label. 'approved' is what Client Approval writes.
_PROJECT_STATUS_OVERRIDE_CHANNEL_WRITE = {
    'In Design': 'in_queue',
    'Pre-Production': 'approved',
    'Handed to Production': 'handed_to_production',
}

# Deliverable.status for an "In Design" override ('in_progress'; every
# pre-approval value reads as "In Design"). The two post-approval labels both
# write 'approved' — see _write_deliverable_status_override().
_DELIVERABLE_STATUS_WRITE = {
    'In Design': 'in_progress',
}


def _build_details_context(project, actor):
    """Template context for the Details page: permissions, picker options,
    designer rows, C&CM data. Shared by /overlay and /overlay/details so the
    two stay identical."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.lib.status_vocabulary import derive_project_status
    from app.modules.core.shared.services.status_tracking import project_status_started_at, project_client_approved_at

    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}

    can_reassign_cs_lead = can('manage_projects', actor)
    can_manage_cs = can('manage_projects', actor) or actor.id == project.cs_lead_id
    can_manage_reference_files = (
        can_manage_cs
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
    )
    can_edit_project = can_manage_reference_files

    can_assign_owner = (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or can('claim_ownership', actor)
    )

    cs_lead_options = active_users_query().filter_by(role='cs').order_by(User.name).all() if can_reassign_cs_lead else []

    available_cs_users = active_users_query().filter(
        User.role.in_(['cs', 'admin', 'management']),
        User.id != project.cs_lead_id,
        ~User.id.in_(secondary_cs_ids) if secondary_cs_ids else True
    ).order_by(User.name).all() if can_manage_cs else []

    if can('manage_projects', actor) or actor.id == project.cs_lead_id:
        owner_options = active_users_query().filter_by(role='project_owner').order_by(User.name).all()
    elif can('claim_ownership', actor):
        owner_options = [actor]
    else:
        owner_options = []

    # can_override_project_status gates the bulk write (see block comment above).
    status_label, status_class = derive_project_status(project)
    can_override_project_status = can('override_status', actor)
    # None if the status pre-dates ProjectStatusLog.
    status_started_at = project_status_started_at(project)
    # Only shown separately once Handed to Production.
    client_approved_at = project_client_approved_at(project) if status_label == 'Handed to Production' else None

    requested_teams = [t.strip() for t in (project.design_teams_requested or '').split(',') if t.strip()]
    assignments_by_team = {pd.team: pd for pd in project.assigned_designers}
    all_teams = requested_teams + [t for t in sorted(assignments_by_team) if t not in requested_teams]

    designer_rows = []
    for team in all_teams:
        assignment = assignments_by_team.get(team)
        can_manage = (
            can('manage_projects', actor)
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

    can_manage_concept_kv_full = can('manage_projects', actor)
    can_self_claim_concept_kv = can('claim_work', actor)
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

    # Start Project is the only way off "Briefed"; deliverable changes never move it.
    can_start_project = can('start_projects', actor) and project.project_status == 'briefed'

    # The template reads project.cancelled_at for the button state.
    can_cancel_project = _can_cancel_project(project, actor)

    # The template reads project.project_status == 'on_hold' for the button state.
    can_toggle_hold = _can_toggle_hold(project, actor)

    # Customer rows (C&CM) include cancelled customers — this is where they are
    # reactivated. Gated by can_cancel_project.
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

    # Add Customer (C&CM). Excludes already-linked customers; cancelled ones
    # come back via Reactivate.
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

    # Details' Flags card shows project-level flags: 'project', 'concept', 'kv'.
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

    # Edit-mode dropdowns; only fetched for someone who can edit.
    from app.modules.core.shared.models import Client, DesignType
    client_options = Client.query.order_by(Client.name).all() if can_edit_project else []
    design_type_options = DesignType.query.order_by(DesignType.name).all() if can_edit_project else []

    # Concurrent-edit check: Project has no updated_at, so the latest
    # ActivityLog time stands in. Save sends it back; a mismatch returns 409.
    from app.modules.core.shared.models import ActivityLog
    latest_activity = (
        ActivityLog.query
        .filter_by(entity_type='project', entity_id=project.id)
        .order_by(ActivityLog.created_at.desc())
        .first()
    )
    edit_snapshot_at = latest_activity.created_at.isoformat() if latest_activity else ''

    # Request Editing Access button: status is None/pending/approved/denied.
    # Shown to an assigned designer on an eligible project until approved.
    edit_access_request = None
    # Role literal: can('claim_work') would let admin in via the wildcard.
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
    # Clears the Projects table's "new updates" dot on open (Chat has its own
    # watermark). Best-effort.
    from app.modules.core.shared.lib.utils import mark_project_activity_seen
    mark_project_activity_seen(project, actor, 'update')
    return render_template('project_overlay/_overlay.html', project=project, **context)

@project_overlay_bp.route('/projects/<int:project_id>/overlay/details')
@login_required
def overlay_details(project_id):
    """Details page fragment alone. /overlay already embeds Details; this is
    for project_list.js's page loader when returning to Details from another
    page."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    context = _build_details_context(project, actor)
    template = (
        'project_overlay/_details_standard.html' if project.brief_type == 'standard'
        else 'project_overlay/_details_ccm.html'
    )
    return render_template(template, project=project, **context)



# data-field name -> its on-screen label in Details, used in the activity log.
# Keep in sync with the template labels.
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
    'design_teams_requested': 'Teams Required',
}


def _display_value_for_log(field_name, value):
    """JSON-safe, readable form of a value for ActivityLog.changes: FK ids
    become names, dates become ISO strings, the rest passes through."""
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
    """Details edit-mode Save. Only whitelisted fields are written (security
    boundary: never a generic setattr). Logs an old/new diff to
    ActivityLog.changes."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ActivityLog
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    can_edit_project = (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
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

    # data-field name -> (Project attr, parser)
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

    # Parse every field before writing any, so a bad value leaves the whole
    # save unapplied (Job Number included).
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
            changes.append({'field': field_name, 'attr': attr_name, 'old': old_value, 'new': new_value})

    # Teams Required: dropping a team also removes that team's Design Lead.
    # Stored canonically ordered and comma-joined, the same shape create writes.
    dropped_teams = []
    if 'design_teams_requested' in fields:
        _TEAMS = ['2D', '3D', 'Technical']
        _canon = {'2d': '2D', '3d': '3D', 'technical': 'Technical'}
        parsed_teams = []
        for tok in (fields.get('design_teams_requested') or '').split(','):
            t = tok.strip()
            if not t:
                continue
            key = _canon.get(t.lower())
            if not key:
                return jsonify({'success': False, 'error': f'Unknown design team: {t}'}), 400
            if key not in parsed_teams:
                parsed_teams.append(key)
        new_value = ','.join(t for t in _TEAMS if t in parsed_teams)
        old_value = project.design_teams_requested or ''
        if new_value != old_value:
            dropped_teams = [t.strip() for t in old_value.split(',') if t.strip() and t.strip() not in parsed_teams]
            changes.append({'field': 'design_teams_requested', 'attr': 'design_teams_requested',
                            'old': old_value, 'new': new_value})

    # Job Number goes through mutations.save_detail_field (shared with the
    # Client Servicing table) for its duplicate check, notification and log.
    # It commits on its own, so it runs only once everything else has parsed.
    job_number_changed = False
    if 'job_number' in fields:
        from app.modules.projects.services import mutations as project_mutations
        old_job_number = project.job_number
        try:
            new_job_number = project_mutations.save_detail_field(
                project, actor, 'job_number', fields.get('job_number')
            )
        except project_mutations.FieldError as exc:
            return jsonify({'success': False, 'error': f'Job Number {exc}.'}), 400
        job_number_changed = new_job_number != old_job_number

    for c in changes:
        setattr(project, c['attr'], c['new'])

    removed_lead_notes = []
    if dropped_teams:
        from app.modules.core.shared.models import ProjectDesigner
        for team in dropped_teams:
            assignment = ProjectDesigner.query.filter_by(project_id=project.id, team=team).first()
            if assignment:
                removed_lead_notes.append(f'{team} lead {assignment.designer.name}')
                db.session.delete(assignment)

    if not changes:
        return jsonify({
            'success': True,
            'changed': job_number_changed,
            'changes': ['job_number'] if job_number_changed else [],
        })

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

    # Separate entry for leads removed by a team drop (matches assign_lead's lead_* entries).
    if removed_lead_notes:
        log_activity(
            'lead_removed',
            f'{actor.name} removed {", ".join(removed_lead_notes)} on "{project.name}" (team no longer required)',
            user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
        )

    return jsonify({
        'success': True,
        'changed': True,
        'changes': [c['field'] for c in changes] + (['job_number'] if job_number_changed else []),
    })


@project_overlay_bp.route('/projects/<int:project_id>/overlay/start', methods=['POST'])
@login_required
def overlay_start_project(project_id):
    """Start Project: moves project_status 'briefed' -> 'in_progress' (reads
    as "In Design"). Same for both brief types."""
    from flask import jsonify
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.services.status_tracking import record_project_status

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not can('start_projects', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to start this project.'}), 403

    if project.project_status != 'briefed':
        return jsonify({'success': False, 'error': 'This project has already been started.'}), 400

    record_project_status(project, 'in_progress', actor)
    db.session.commit()
    return jsonify({'success': True})


def _write_deliverable_status_override(deliverable, label, actor):
    """Write the raw fields for one deliverable's override label. Shared by
    the single and bulk overrides. Does not sync or commit — callers do that
    once. Returns False (nothing written) for an unknown label.

    Both post-approval labels write status='approved'; the needs_* and
    stream status fields decide which one displays. A deliverable with no
    streams needed reads "Handed to Production" even when set to
    "Pre-Production", same as a real approval."""
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
        # Stream states are None -> 'uploaded' -> 'approved' (no 'in_progress'),
        # so "Pre-Production" resets each needed stream to None.
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
    """Override one deliverable's status. Admin, or a designer with an
    approved edit-access grant. Syncs the project pill afterwards."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable
    from app.modules.core.shared.services.status_tracking import sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status

    deliverable = Deliverable.query.filter_by(id=deliverable_id, project_id=project_id).first_or_404()
    actor = _get_actor()
    if not can('override_status', actor) and not _has_edit_access_grant(deliverable.project, actor):
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
    """Admin-only bulk override: sets every deliverable (and, for C&CM,
    every ProjectPosmChannel) to one status, then syncs the pill. See the
    block comment above _PROJECT_STATUS_OVERRIDE_CHANNEL_WRITE.

    Channels must be written too: C&CM customer rows read channel status,
    not the deliverable roll-up. A 'briefed' project is moved to
    'in_progress' first, because sync is a no-op while briefed. On Hold and
    Cancelled are left alone; the pill keeps showing them."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Project
    from app.modules.core.shared.services.status_tracking import record_project_status, sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_project_status

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('override_status', actor):
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
    """Cancel Project (reason required). Leaves project_status untouched:
    derive_project_status() checks cancelled_at first, so Reactivate has
    nothing to restore."""
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
    """Reactivate a cancelled project: clears the three cancel columns. No
    reason required."""
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
    """Cancel one C&CM customer (reason required; reversible). Same gate as
    cancelling the project. The Deliverables/Submissions/Pre-Production
    builders skip cancelled customers, which freezes its state for
    invoicing."""
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
    """Reactivate a cancelled customer: clears the four cancel columns. No
    reason required."""
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

    # Keep ProjectRegion in sync: the NAS folder tree is built from it, not
    # from project_customers.
    if customer.region and not ProjectRegion.query.filter_by(project_id=project.id, region=customer.region).first():
        db.session.add(ProjectRegion(project_id=project.id, region=customer.region))

    db.session.flush()

    # Create the new customer's POSM submission channel now (Submissions
    # would also self-heal it on open).
    if customer.region:
        ensure_posm_channels(project, {customer.region: [pc]})

    db.session.commit()

    log_activity(
        'customer_added',
        f'{actor.name} added "{customer.name}" to "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )

    # Background NAS folder build (as in create.py's finalize). Idempotent,
    # so it only adds the new customer's folder.
    from flask import current_app as _app
    from app.modules.core.shared.services.nas import _run_in_background, create_project_folders
    _pid = project.id
    _app_obj = _app._get_current_object()
    _run_in_background(_app_obj, lambda: create_project_folders(Project.query.get(_pid)))

    return jsonify({'success': True, 'project_customer_id': pc.id, 'customer_name': customer.name})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/nas-folder-link')
@login_required
def overlay_nas_folder_link(project_id):
    """Resolve the project's root NAS folder to a Synology Drive link. Called
    on click, since each resolve is a live NAS API call (see
    services/nas.py's build_drive_folder_url())."""
    from flask import current_app, jsonify
    from app.modules.core.shared.services.nas import build_drive_folder_url

    project = Project.query.get_or_404(project_id)
    # The Projects page's own gate; keeps workspace-less roles (HSE) out.
    if not can('view_workspace', _get_actor()):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    # The folder path is keyed by creation year; without it there is no folder to find.
    if project.created_at is None:
        return jsonify({'success': False, 'error': 'This project has no NAS folder yet.'}), 404
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
    """Put on Hold / Resume. held_from_status stores the prior status so
    Resume can restore it."""
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


# ── Request Editing Access routes. Approve/deny are called from the CS
# notification's buttons. ──

@project_overlay_bp.route('/projects/<int:project_id>/request-edit-access', methods=['POST'])
@login_required
def request_edit_access(project_id):
    """Create (or, after a denial, reset) a pending request and notify the
    CS side. Grants nothing until approved."""
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
        # Re-request after a denial reuses the row: UNIQUE(project_id, user_id).
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
    """Approve a pending request: the requester gets permanent
    _can_manage_deliverables access (plus status override) on this project.
    Gate: _can_decide_edit_access_request."""
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
    """Deny a pending request. The designer can request again later."""
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
