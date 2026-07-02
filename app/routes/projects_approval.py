from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models import (Project, User, ProjectCustomer, Deliverable,
                        ProjectSubmission, ProjectPosmChannel)
from app.decorators import role_required
from app.notifications import notify_of_project_approved, create_notification
from app.utils import log_activity

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
                        link.deliverable.status = 'approved'

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
                        link.deliverable.status = 'approved'

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
                    project.project_status = 'approved'
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
                    deliverable.status = 'approved'

            # If every project deliverable is now approved, approve the project
            if all(d.status == 'approved' for d in project.project_deliverables):
                project.project_status = 'approved'
                project.approved_at = now
                project.approved_by_id = current_user.id
                if project.concept_status:
                    project.concept_status = 'approved'
                if project.kv_status:
                    project.kv_status = 'approved'
                all_approved = True
        else:
            # Full approval
            project.project_status = 'approved'
            project.approved_at = now
            project.approved_by_id = current_user.id
            all_approved = True

            for deliverable in project.project_deliverables:
                deliverable.status = 'approved'

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

    return jsonify({'success': True, 'all_approved': all_approved})


@approval_bp.route('/projects/<int:project_id>/concept-kv/approve', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def approve_concept_kv(project_id):
    """Approve the Concept & KV channel independently during a POSM-parallel project.

    Sets concept_status and kv_status to 'approved', then checks whether all
    POSM channels are also approved -- if so, cascades to project-level approval."""
    from datetime import datetime as dt
    from app.models import ProjectPosmChannel
    from app.utils import log_activity

    project = Project.query.get_or_404(project_id)

    if not project.posm_channels:
        return jsonify({'success': False, 'error': 'Concept & KV is only approved independently on projects with POSM channels'}), 400

    if (not project.has_concept and not project.has_kv):
        return jsonify({'success': False, 'error': 'This project has no Concept or KV'}), 400

    if project.concept_status == 'approved' and project.kv_status == 'approved':
        return jsonify({'success': False, 'error': 'Concept & KV is already approved'}), 400

    now = dt.utcnow()

    if project.has_concept:
        project.concept_status = 'approved'
    if project.has_kv:
        project.kv_status = 'approved'

    # Cascade: if all POSM channels are also approved, approve the whole project
    all_channels = ProjectPosmChannel.query.filter_by(project_id=project_id).all()
    if all_channels and all(c.status == 'approved' for c in all_channels):
        project.project_status = 'approved'
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
