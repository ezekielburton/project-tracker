"""
projects_transfer.py — Transfer a C&CM deliverable to a different customer within the same project.

POST /projects/<project_id>/deliverables/<deliverable_id>/transfer

Body (JSON):
    target_customer_id  int   — ID of the target Customer row
    mode                str   — 'move' or 'duplicate'

Move:
    Updates deliverable.project_customer_id to point at the new ProjectCustomer.
    All related rows (DeliverableAssignment, DeliverableStatusLog, BriefFlag,
    ProjectSubmissionDeliverable) travel with the deliverable automatically since they
    all key on deliverable_id, not project_customer_id.

Duplicate:
    Creates a new Deliverable under the new ProjectCustomer (same name, type, teams,
    status, deadline). Clones DeliverableAssignment rows so the same designers carry
    over. Status log for the new deliverable starts fresh. BriefFlags and submission
    links stay with the original.
"""
from datetime import datetime

from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user

from app import db
from app.decorators import role_required
from app.models import (
    Project, Customer, ProjectCustomer, ProjectRegion,
    Deliverable, DeliverableAssignment, DeliverableStatusLog,
)
from app.utils import log_activity

transfer_bp = Blueprint('transfer', __name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_or_create_project_customer(project, customer):
    """
    Return the existing ProjectCustomer linking project ↔ customer,
    or create one (plus a ProjectRegion if the region is new to the project).
    """
    pc = ProjectCustomer.query.filter_by(
        project_id=project.id,
        customer_id=customer.id,
    ).first()

    if pc is None:
        # Ensure the region is tracked on the project too
        region_exists = ProjectRegion.query.filter_by(
            project_id=project.id,
            region=customer.region,
        ).first()
        if not region_exists:
            db.session.add(ProjectRegion(project_id=project.id, region=customer.region))

        pc = ProjectCustomer(
            project_id=project.id,
            customer_id=customer.id,
            status='briefed',
        )
        db.session.add(pc)
        db.session.flush()  # get pc.id before the deliverable FK is set

    return pc


def _notify_transfer(project, deliverable, target_customer, mode, actor):
    """
    Notify the project's CS lead, secondary CS, and the deliverable's assigned
    designers about the transfer. The actor is never notified about their own action.
    """
    try:
        from app.notifications import create_notification
        from app.models import ProjectSecondaryCS

        verb = 'moved' if mode == 'move' else 'duplicated'
        msg = (
            f'"{deliverable.name}" was {verb} to '
            f'{target_customer.name} ({target_customer.region.upper()}) '
            f'in "{project.name}" by {actor.name}.'
        )

        notified_ids = {actor.id}

        # CS lead
        if project.cs_lead and project.cs_lead.id not in notified_ids:
            create_notification(
                recipient_id=project.cs_lead.id,
                message=msg,
                notification_type='deliverable_transferred',
                link=f'/projects/{project.id}',
                pref_key='email_project_update',
            )
            notified_ids.add(project.cs_lead.id)

        # Secondary CS
        for sec in ProjectSecondaryCS.query.filter_by(project_id=project.id).all():
            if sec.user_id not in notified_ids:
                create_notification(
                    recipient_id=sec.user_id,
                    message=msg,
                    notification_type='deliverable_transferred',
                    link=f'/projects/{project.id}',
                    pref_key='email_project_update',
                )
                notified_ids.add(sec.user_id)

        # Assigned designers on this deliverable
        for asgn in deliverable.disciplines:
            if asgn.designer_id not in notified_ids:
                create_notification(
                    recipient_id=asgn.designer_id,
                    message=msg,
                    notification_type='deliverable_transferred',
                    link=f'/projects/{project.id}',
                    pref_key='email_project_update',
                )
                notified_ids.add(asgn.designer_id)

    except Exception as e:
        # Notifications must never block the transfer
        from flask import current_app
        current_app.logger.warning(f'Transfer notification failed: {e}')


# ── route ─────────────────────────────────────────────────────────────────────

@transfer_bp.route('/projects/<int:project_id>/deliverables/<int:deliverable_id>/transfer', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def transfer_deliverable(project_id, deliverable_id):
    project = Project.query.get_or_404(project_id)

    # CS leads can only transfer on their own projects (or ones they're secondary CS on)
    if current_user.role == 'cs':
        from app.models import ProjectSecondaryCS
        is_secondary = ProjectSecondaryCS.query.filter_by(
            project_id=project_id, user_id=current_user.id
        ).first() is not None
        if project.cs_lead_id != current_user.id and not is_secondary:
            abort(403)

    deliverable = Deliverable.query.get_or_404(deliverable_id)

    if deliverable.project_id != project_id:
        return jsonify({'success': False, 'error': 'Deliverable does not belong to this project.'}), 400

    if deliverable.project_customer_id is None:
        return jsonify({'success': False, 'error': 'Only C&CM deliverables can be transferred.'}), 400

    data = request.get_json(silent=True) or {}
    target_customer_id = data.get('target_customer_id')
    mode = data.get('mode', 'move')

    if not target_customer_id:
        return jsonify({'success': False, 'error': 'target_customer_id is required.'}), 400
    if mode not in ('move', 'duplicate'):
        return jsonify({'success': False, 'error': 'mode must be "move" or "duplicate".'}), 400

    target_customer = Customer.query.get(target_customer_id)
    if not target_customer:
        return jsonify({'success': False, 'error': 'Target customer not found.'}), 404

    # Capture source info for logging before any mutation
    source_pc = deliverable.project_customer
    source_customer = source_pc.customer if source_pc else None
    source_label = (
        f'{source_customer.name} ({source_customer.region.upper()})'
        if source_customer else 'unknown'
    )
    target_label = f'{target_customer.name} ({target_customer.region.upper()})'

    # Emulation-aware actor
    from flask import session
    from app.models import User as UserModel
    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    target_pc = _get_or_create_project_customer(project, target_customer)

    if mode == 'move':
        deliverable.project_customer_id = target_pc.id
        db.session.commit()

        log_activity(
            'deliverable_transferred',
            f'"{deliverable.name}" moved from {source_label} → {target_label} in "{project.name}"',
            user=actor,
            entity_type='project',
            entity_name=project.name,
            entity_id=project.id,
        )
        _notify_transfer(project, deliverable, target_customer, 'move', actor)

        return jsonify({'success': True, 'mode': 'move'})

    else:  # duplicate
        new_deliverable = Deliverable(
            project_id=project.id,
            project_customer_id=target_pc.id,
            deliverable_type_id=deliverable.deliverable_type_id,
            name=deliverable.name,
            status=deliverable.status,
            design_deadline=deliverable.design_deadline,
            design_deadline_time=deliverable.design_deadline_time,
            installation_deadline=deliverable.installation_deadline,
            teams=deliverable.teams,
            revision_count=deliverable.revision_count,
            created_by_id=actor.id,
            created_at=datetime.utcnow(),
        )
        db.session.add(new_deliverable)
        db.session.flush()  # get new_deliverable.id

        # Clone designer assignments
        for asgn in deliverable.disciplines:
            db.session.add(DeliverableAssignment(
                deliverable_id=new_deliverable.id,
                designer_id=asgn.designer_id,
                team=asgn.team,
                assigned_by_id=actor.id,
            ))

        # Open a fresh status log entry for the new deliverable
        db.session.add(DeliverableStatusLog(
            deliverable_id=new_deliverable.id,
            status=new_deliverable.status,
            started_at=datetime.utcnow(),
            changed_by_id=actor.id,
        ))

        db.session.commit()

        log_activity(
            'deliverable_duplicated',
            f'"{deliverable.name}" duplicated from {source_label} → {target_label} in "{project.name}"',
            user=actor,
            entity_type='project',
            entity_name=project.name,
            entity_id=project.id,
        )
        _notify_transfer(project, deliverable, target_customer, 'duplicate', actor)

        return jsonify({'success': True, 'mode': 'duplicate'})
