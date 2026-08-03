"""
Project Details Overlay Route File.
New blueprint for file hygiene, easier to work on chunks rather than one long file.
"""

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Project

project_overlay_bp = Blueprint('project_overlay', __name__)

@project_overlay_bp.route('/projects/<int:project_id>/overlay')
@login_required
def overlay(project_id):
    """
    Real content-fetch route for the Detail + Briefing overlay. M3 Step 2:
    now computes Design > Details context for a Standard brief's Project
    Name card — CS Lead/Secondary CS/Project Owner options and per-role
    gating, mirroring the existing reassign_cs_lead/add_secondary_cs/
    set_project_owner routes' own gating so the picker options shown
    match what the backend will actually allow (no point showing someone
    an option that will just 403).
    """
    from app.models import User
    from flask import session
    from app.status_vocabulary import derive_project_status

    project = Project.query.get_or_404(project_id)

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}

    can_reassign_cs_lead = actor.role in ('admin', 'management')
    can_manage_cs = actor.role in ('admin', 'management') or actor.id == project.cs_lead_id
    can_assign_owner = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.role == 'project_owner'
    )

    cs_lead_options = User.query.filter_by(role='cs').order_by(User.name).all() if can_reassign_cs_lead else []

    available_cs_users = User.query.filter(
        User.role.in_(['cs', 'admin', 'management']),
        User.id != project.cs_lead_id,
        ~User.id.in_(secondary_cs_ids) if secondary_cs_ids else True
    ).order_by(User.name).all() if can_manage_cs else []

    if actor.role in ('admin', 'management') or actor.id == project.cs_lead_id:
        owner_options = User.query.filter_by(role='project_owner').order_by(User.name).all()
    elif actor.role == 'project_owner':
        # A plain Project Owner can only self-claim (per set_project_owner's
        # own gating), so their popover only ever shows themselves — no
        # point listing people they're not allowed to pick anyway.
        owner_options = [actor]
    else:
        owner_options = []

    status_label, status_class = derive_project_status(project)

    return render_template(
        'project_overlay/_overlay.html',
        project=project,
        status_label=status_label,
        status_class=status_class,
        can_reassign_cs_lead=can_reassign_cs_lead,
        can_manage_cs=can_manage_cs,
        can_assign_owner=can_assign_owner,
        cs_lead_options=cs_lead_options,
        available_cs_users=available_cs_users,
        owner_options=owner_options,
    )

@project_overlay_bp.route('/projects/<int:project_id>/set-project-owner', methods=['POST'])
@login_required
def set_project_owner(project_id):
    """
    Assigns/reassigns the Project Owner. Gating: Admin, Management, Project's CS lead or the Project Owner themselves.
    
    """
    from app.models import Project, User
    from app import db
    from flask import request, jsonify, session
    from app.utils import log_activity
    from app.notifications import create_notification

    project = Project.query.get_or_404(project_id)

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    new_owner_id = request.form.get('user_id', type=int)
    if not new_owner_id:
        return jsonify({'success': False, 'error': 'Please select a Project Owner.'}), 400

    is_self_claim = (actor.role == 'project_owner' and new_owner_id == actor.id)

    if actor.role not in ('admin', 'management') and actor.id != project.cs_lead_id and not is_self_claim:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 400

    new_owner = User.query.get(new_owner_id)
    if not new_owner or new_owner.role != 'project_owner':
        return jsonify({'success': False, 'error': 'Selected user is not a Project Owner'}), 400

    previous_owner = project.project_owner
    project.project_owner_id = new_owner.id
    db.session.commit()

    # Skip the you've been assigned notification when it's a self-claim

    if new_owner.id != actor.id:
        create_notification(
            recipient=new_owner,
            message=f'You have been assigned as Project Owner on "{project.name}" by {actor.name}.',
            notification_type='project_owner_assigned',
            project=project,
            triggered_by=actor,
        )

    log_activity (
        'project_owner_assigned',
        f'{actor.name} assigned {new_owner.name} as Project Owner on "{project.name}"' + (f' (previously {previous_owner.name})' if previous_owner else ''),
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id       
    )

    return jsonify({'success': True, 'owner_name': new_owner.name})
                    