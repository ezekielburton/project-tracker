from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, session, url_for, redirect, abort, flash
from flask_login import login_required, current_user
from app import db
from app.models import (Project, User, ProjectCustomer, Deliverable,
                        ProjectSubmission, ProjectPosmChannel)
from app.decorators import role_required
from app.notifications import notify_of_project_approved, notify_of_ckv_posm_pending, create_notification
from app.utils import log_activity
from app.achievements import check_achievements
from app.status_tracking import record_project_status, record_deliverable_status

approval_bp = Blueprint('approval', __name__)

@approval_bp.route('/projects/<int:project_id>/submission/approve', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def approve_submission(project_id):
    """CS approves the final client submission, locking the project.

    Standard brief (no posm_channel_id in body):
      - Full approve (no deliverable_ids): project → 'approved', all deliverables → 'approved'
      - Partial (deliverable_ids provided): only those deliverables → 'approved';
        if all project deliverables are now approved, cascade to project approval.

    POSM brief (posm_channel_id provided in body):
      - Full approve (no deliverable_ids): channel → 'approved', all submission deliverables → 'approved';
        cascade to project if all channels done.
      - Partial (deliverable_ids provided): only those deliverables → 'approved';
        if all deliverables in the submission are now approved, approve the channel and cascade.

    Expects optional JSON body: { "posm_channel_id": <int>, "deliverable_ids": [<int>] }
    Confirmation popup is handled client-side; this route executes the action."""
    from datetime import datetime as dt
    from app.models import ProjectPosmChannel, ProjectSubmission

    project = Project.query.get_or_404(project_id)
    data = request.get_json(silent=True) or {}
    posm_channel_id = data.get('posm_channel_id')
    deliverable_ids = data.get('deliverable_ids')  # list of ints, or None for full approval
    deliverable_id_set = set(deliverable_ids) if deliverable_ids else None

    now = dt.utcnow()
    all_approved = False  # used in response so JS can show the right toast

    if posm_channel_id:
        # ── POSM channel approval path ──────────────────────────────────────
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()
        if not channel:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
        if channel.status == 'approved':
            return jsonify({'success': False, 'error': 'This channel is already approved'}), 400
        if channel.status != 'submitted_to_client':
            return jsonify({'success': False,
                            'error': 'Channel must be in Submitted to Client state to approve'}), 400

        # Locate the active submission for this channel
        ch_sub_q = ProjectSubmission.query.filter_by(
            project_id=project_id,
            is_active=True,
            posm_country=channel.posm_country,
        )
        if channel.posm_customer_id is not None:
            ch_sub_q = ch_sub_q.filter(
                ProjectSubmission.posm_customer_id == channel.posm_customer_id
            )
        else:
            ch_sub_q = ch_sub_q.filter(
                ProjectSubmission.posm_customer_id == None  # noqa: E711
            )
        ch_sub = ch_sub_q.first()

        if deliverable_id_set:
            # Partial approval: only mark the selected deliverables
            if ch_sub:
                for link in ch_sub.included_deliverables:
                    if link.deliverable and link.deliverable.id in deliverable_id_set:
                        record_deliverable_status(link.deliverable, 'approved', current_user)

            # Cascade to channel approval only when ALL deliverables for this channel's
            # customer(s) are approved — not just those in the current submission.
            # UAE channels track one specific customer; Gulf channels cover all customers
            # in the region.
            if channel.posm_customer_id:
                # UAE: all deliverables belonging to this specific customer
                channel_deliverables = Deliverable.query.filter_by(
                    project_id=project_id,
                    project_customer_id=channel.posm_customer_id
                ).all()
            else:
                # Gulf: all deliverables across every non-cancelled customer in this region
                region_pc_ids = [
                    pc.id for pc in project.project_customers
                    if pc.customer.region == channel.posm_country and not pc.cancelled
                ]
                channel_deliverables = Deliverable.query.filter(
                    Deliverable.project_id == project_id,
                    Deliverable.project_customer_id.in_(region_pc_ids)
                ).all() if region_pc_ids else []

            if channel_deliverables and all(d.status == 'approved' for d in channel_deliverables):
                channel.status = 'approved'
                channel.approved_at = now
                channel.approved_by_id = current_user.id
        else:
            # Full approval: approve channel + all its deliverables at once
            channel.status = 'approved'
            channel.approved_at = now
            channel.approved_by_id = current_user.id

            if ch_sub:
                for link in ch_sub.included_deliverables:
                    if link.deliverable:
                        record_deliverable_status(link.deliverable, 'approved', current_user)

        # Cascade: if ALL channels are now approved (and C&KV if applicable), approve project
        if channel.status == 'approved':
            all_channels = ProjectPosmChannel.query.filter_by(project_id=project_id).all()
            if all_channels and all(c.status == 'approved' for c in all_channels):
                ckv_gate = True
                if project.has_concept and project.concept_status != 'approved':
                    ckv_gate = False
                if project.has_kv and project.kv_status != 'approved':
                    ckv_gate = False
                if ckv_gate:
                    record_project_status(project, 'approved', current_user)
                    project.approved_at = now
                    project.approved_by_id = current_user.id
                    all_approved = True

    else:
        # ── Standard (non-POSM) approval path ──────────────────────────────
        if project.project_status == 'approved':
            return jsonify({'success': False, 'error': 'This project is already approved'}), 400
        if project.project_status != 'submitted_to_client':
            return jsonify({'success': False,
                            'error': 'Project must be in Submitted to Client state to approve'}), 400

        if deliverable_id_set:
            # Partial approval: only mark the selected deliverables
            for deliverable in project.project_deliverables:
                if deliverable.id in deliverable_id_set:
                    record_deliverable_status(deliverable, 'approved', current_user)

            # If every project deliverable is now approved, approve the project
            if all(d.status == 'approved' for d in project.project_deliverables):
                record_project_status(project, 'approved', current_user)
                project.approved_at = now
                project.approved_by_id = current_user.id
                if project.concept_status:
                    project.concept_status = 'approved'
                if project.kv_status:
                    project.kv_status = 'approved'
                all_approved = True
        else:
            # Full approval
            record_project_status(project, 'approved', current_user)
            project.approved_at = now
            project.approved_by_id = current_user.id
            all_approved = True

            for deliverable in project.project_deliverables:
                record_deliverable_status(deliverable, 'approved', current_user)

            if project.concept_status:
                project.concept_status = 'approved'
            if project.kv_status:
                project.kv_status = 'approved'

    db.session.commit()

    log_activity(
        'project_approved' if all_approved else 'deliverables_approved',
        f'"{project.name}" approved by {current_user.name}' if all_approved
        else f'Deliverables partially approved on "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    if project.project_status == 'approved':
        notify_of_project_approved(project, triggered_by=current_user)
        check_achievements(current_user, 'project_approved')

    return jsonify({'success': True, 'all_approved': all_approved})


@approval_bp.route('/projects/<int:project_id>/concept-kv/approve', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def approve_concept_kv(project_id):
    """Approve the Concept & KV channel.

    Two paths:
    - If the project has no customers/regions (C&KV-only brief): approves C&KV pill,
      then returns show_posm_prompt=True so the UI can ask whether to add POSM.
    - If POSM channels already exist: approves C&KV and cascades to full project
      approval if all channels are also done."""
    from datetime import datetime as dt
    from app.models import ProjectPosmChannel
    from app.utils import log_activity

    project = Project.query.get_or_404(project_id)

    if (not project.has_concept and not project.has_kv):
        return jsonify({'success': False, 'error': 'This project has no Concept or KV'}), 400

    if project.concept_status == 'approved' and project.kv_status == 'approved':
        return jsonify({'success': False, 'error': 'Concept & KV is already approved'}), 400

    now = dt.utcnow()

    if project.has_concept:
        project.concept_status = 'approved'
    if project.has_kv:
        project.kv_status = 'approved'
    project.concept_approved_at = now
    project.concept_approved_by_id = current_user.id

    # ── No customers/regions: C&KV-only brief ────────────────────────────────
    # Approve the pill but don't lock the project — return a prompt so CS can
    # decide whether to add POSM, pause, or fully approve.
    if not project.project_customers:
        db.session.commit()
        log_activity(
            'concept_kv_approved',
            f'Concept & KV approved for "{project.name}" by {current_user.name}',
            user=current_user, entity_type='project',
            entity_name=project.name, entity_id=project.id
        )
        return jsonify({'success': True, 'show_posm_prompt': True})

    # ── POSM channels present: cascade if all channels are now approved ───────
    all_channels = ProjectPosmChannel.query.filter_by(project_id=project_id).all()
    if all_channels and all(c.status == 'approved' for c in all_channels):
        record_project_status(project, 'approved', current_user)
        project.approved_at = now
        project.approved_by_id = current_user.id

    db.session.commit()

    log_activity(
        'concept_kv_approved',
        f'Concept & KV approved for "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@approval_bp.route('/projects/<int:project_id>/posm-prompt-response', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def posm_prompt_response(project_id):
    """Handle the three choices shown after C&KV-only approval:
    - add_posm : set project back to in_progress so CS can add regions/customers
    - pause    : set project to awaiting_posm_details
    - approve  : fully approve the project now"""
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    action = data.get('action')

    if action not in ('add_posm', 'pause', 'approve'):
        return jsonify({'success': False, 'error': 'Invalid action'}), 400

    now = datetime.utcnow()

    if action == 'add_posm':
        record_project_status(project, 'in_progress', current_user)
        db.session.commit()
        log_activity(
            'posm_pending',
            f'"{project.name}" returned to In Progress to add POSM — requested by {current_user.name}',
            user=current_user, entity_type='project',
            entity_name=project.name, entity_id=project.id
        )
        notify_of_ckv_posm_pending(project, triggered_by=current_user)
        return jsonify({'success': True, 'redirect': url_for('project_detail.detail', project_id=project.id)})

    elif action == 'pause':
        record_project_status(project, 'awaiting_posm_details', current_user)
        db.session.commit()
        log_activity(
            'posm_pending',
            f'"{project.name}" paused — awaiting POSM details. Set by {current_user.name}',
            user=current_user, entity_type='project',
            entity_name=project.name, entity_id=project.id
        )
        return jsonify({'success': True})

    else:  # approve
        record_project_status(project, 'approved', current_user)
        project.approved_at = now
        project.approved_by_id = current_user.id
        db.session.commit()
        log_activity(
            'project_approved',
            f'"{project.name}" approved by {current_user.name}',
            user=current_user, entity_type='project',
            entity_name=project.name, entity_id=project.id
        )
        notify_of_project_approved(project, triggered_by=current_user)
        check_achievements(current_user, 'project_approved')
        return jsonify({'success': True})


@approval_bp.route('/projects/<int:project_id>/approve-direct', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def approve_direct(project_id):
    """Bypass the submission system and approve a project directly.

    Used for technical-only projects (or any case where CS wants to lock
    the project without going through the submission pipeline).

    Approves project + all deliverables + C&KV + all POSM channels in one
    shot, regardless of current project_status.
    """
    project = Project.query.get_or_404(project_id)

    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'Project is already approved'}), 400

    now = datetime.utcnow()

    # Emulation-aware actor (CLAUDE.md pattern)
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Lock the project
    record_project_status(project, 'approved', actor)
    project.approved_at = now
    project.approved_by_id = actor.id

    # Approve all standard deliverables
    for deliverable in project.project_deliverables:
        record_deliverable_status(deliverable, 'approved', actor)

    # Approve C&KV if present
    if project.has_concept:
        project.concept_status = 'approved'
    if project.has_kv:
        project.kv_status = 'approved'

    # Approve all POSM channels if present
    posm_channels = ProjectPosmChannel.query.filter_by(project_id=project_id).all()
    for channel in posm_channels:
        if channel.status != 'approved':
            channel.status = 'approved'
            channel.approved_at = now
            channel.approved_by_id = actor.id

    db.session.commit()

    log_activity(
        'project_approved',
        f'"{project.name}" directly approved (bypassing submission) by {actor.name}',
        user=actor, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    notify_of_project_approved(project, triggered_by=actor)
    check_achievements(actor, 'project_approved')

    return jsonify({'success': True})


@approval_bp.route('/projects/<int:project_id>/unapprove', methods=['POST'])
@login_required
@role_required('admin', 'cs')
def unapprove_project(project_id):
    """Admin reverses a project approval — moves project back to submitted_to_client.

    Resets:
    - project.project_status → 'submitted_to_client'
    - project.approved_at / approved_by_id → None
    - All 'approved' deliverables → 'submitted_to_client'
    - concept_status / kv_status if 'approved' → 'submitted_to_client'
    - Any approved POSM channels → 'submitted_to_client'

    Notifies the CS lead that re-approval is needed."""
    project = Project.query.get_or_404(project_id)

    if project.project_status != 'approved':
        return jsonify({'success': False, 'error': 'Project is not approved'}), 400

    # Emulation-aware actor (CLAUDE.md pattern)
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Reset project-level approval
    record_project_status(project, 'submitted_to_client', actor)
    project.approved_at = None
    project.approved_by_id = None

    # Reset all approved deliverables
    for deliverable in project.project_deliverables:
        if deliverable.status == 'approved':
            record_deliverable_status(deliverable, 'submitted_to_client', actor)

    # Reset concept/KV if approved
    if project.concept_status == 'approved':
        project.concept_status = 'submitted_to_client'
    if project.kv_status == 'approved':
        project.kv_status = 'submitted_to_client'

    # Reset approved POSM channels
    for channel in project.posm_channels:
        if channel.status == 'approved':
            channel.status = 'submitted_to_client'
            channel.approved_at = None
            channel.approved_by_id = None

    db.session.commit()

    # Notify CS lead
    if project.cs_lead and project.cs_lead.id != actor.id:
        create_notification(
            recipient=project.cs_lead,
            message=f'"{project.name}" approval has been reversed by {actor.name}. Please re-approve when ready.',
            notification_type='project_assigned',
            project=project,
            triggered_by=actor
        )

    log_activity(
        'project_unapproved',
        f'"{project.name}" approval reversed by {actor.name} — returned to Submitted to Client',
        user=actor, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@approval_bp.route('/projects/<int:project_id>/unapprove-ckv', methods=['POST'])
@login_required
@role_required('admin', 'cs')
def unapprove_ckv(project_id):
    """Admin reverses a C&KV approval, returning it (and the project if fully approved)
    to submitted_to_client."""
    project = Project.query.get_or_404(project_id)
    if project.concept_status != 'approved':
        return jsonify({'success': False, 'error': 'Concept & KV is not approved'}), 400

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    project.concept_status = 'submitted_to_client'
    if project.kv_status == 'approved':
        project.kv_status = 'submitted_to_client'
    project.concept_approved_at = None
    project.concept_approved_by_id = None

    # If the whole project was locked, pull it back too
    if project.project_status == 'approved':
        record_project_status(project, 'submitted_to_client', actor)
        project.approved_at = None
        project.approved_by_id = None

    db.session.commit()

    if project.cs_lead and project.cs_lead.id != actor.id:
        create_notification(
            recipient=project.cs_lead,
            message=f'Concept & KV approval on "{project.name}" has been reversed by {actor.name}.',
            notification_type='project_assigned',
            project=project,
            triggered_by=actor
        )

    log_activity(
        'ckv_unapproved',
        f'Concept & KV approval reversed on "{project.name}" by {actor.name}',
        user=actor, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@approval_bp.route('/projects/<int:project_id>/unapprove-channel/<int:channel_id>', methods=['POST'])
@login_required
@role_required('admin', 'cs')
def unapprove_channel(project_id, channel_id):
    """Admin reverses a single POSM channel approval. Resets the channel and all its
    deliverables back to submitted_to_client. Also unlocks the project if it was fully approved."""
    project = Project.query.get_or_404(project_id)
    channel = ProjectPosmChannel.query.filter_by(
        id=channel_id, project_id=project_id
    ).first_or_404()

    if channel.status != 'approved':
        return jsonify({'success': False, 'error': 'Channel is not approved'}), 400

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    channel.status = 'submitted_to_client'
    channel.approved_at = None
    channel.approved_by_id = None

    # Reset deliverables that belong to this channel
    if channel.posm_customer_id:
        # UAE: deliverables for this specific customer
        deliverables = Deliverable.query.filter_by(
            project_id=project_id,
            project_customer_id=channel.posm_customer_id
        ).all()
    else:
        # Gulf: deliverables across all non-cancelled customers in this region
        region_pc_ids = [
            pc.id for pc in project.project_customers
            if pc.customer.region == channel.posm_country and not pc.cancelled
        ]
        deliverables = Deliverable.query.filter(
            Deliverable.project_id == project_id,
            Deliverable.project_customer_id.in_(region_pc_ids)
        ).all() if region_pc_ids else []

    for d in deliverables:
        if d.status == 'approved':
            record_deliverable_status(d, 'submitted_to_client', actor)

    # If the whole project was locked, pull it back too
    if project.project_status == 'approved':
        record_project_status(project, 'submitted_to_client', actor)
        project.approved_at = None
        project.approved_by_id = None

    db.session.commit()

    if project.cs_lead and project.cs_lead.id != actor.id:
        create_notification(
            recipient=project.cs_lead,
            message=f'A POSM channel approval on "{project.name}" has been reversed by {actor.name}.',
            notification_type='project_assigned',
            project=project,
            triggered_by=actor
        )

    log_activity(
        'channel_unapproved',
        f'POSM channel ({channel.posm_country}) approval reversed on "{project.name}" by {actor.name}',
        user=actor, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@approval_bp.route('/projects/<int:project_id>/resume-posm', methods=['POST'])
@login_required
def resume_posm_project(project_id):
    """
    Designers click this once CS has added POSM customer/region details to a
    project that was paused via the 'Pause' choice in the C&KV-only approval
    prompt (project_status == 'awaiting_posm_details'). update_project() (in
    projects_brief.py) is what notifies designers that details were added —
    this route is the "I've seen it, resuming" action they take in response
    to that notification, per CS's own request that resuming be a deliberate
    designer action rather than automatic.

    Restricted to the project's assigned designers plus admin — this is a
    designer-initiated action, not a CS one, so it deliberately does NOT use
    the @role_required('admin', 'cs', 'management') decorator every other
    route in this file uses.

    Plain form POST + redirect (not JSON/fetch) to match the existing
    toggle_hold route's pattern, which the detail page button is modeled on.
    """
    project = Project.query.get_or_404(project_id)

    is_assigned_designer = any(a.user_id == current_user.id for a in project.assigned_designers)
    if current_user.role != 'admin' and not is_assigned_designer:
        abort(403)

    if project.project_status != 'awaiting_posm_details':
        flash('Project is not awaiting POSM details.', 'error')
        return redirect(url_for('project_detail.detail', project_id=project_id))

    # Emulation-aware actor, per CLAUDE.md pattern — resolved before the
    # status change now, since record_project_status() needs it as an argument
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    record_project_status(project, 'in_progress', actor)

    log_activity(
        'posm_resumed',
        f'"{project.name}" resumed by {actor.name} — back to In Progress with POSM details added',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    db.session.commit()
    flash('Project resumed — back to In Progress.', 'success')
    return redirect(url_for('project_detail.detail', project_id=project_id))
