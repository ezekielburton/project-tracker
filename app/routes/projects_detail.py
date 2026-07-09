import os
import uuid
import re
from datetime import date, datetime, timezone, timedelta
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, send_from_directory, jsonify, abort, session)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import (Project, ProjectDesigner, Scope, User, Client,
                        Customer, DeliverableType, DeliverableTypeDiscipline,
                        ProjectRegion, ProjectCustomer, Deliverable,
                        DeliverableAssignment, ProjectSubmission, ProjectRevision,
                        ProjectFile, BriefFlag, BriefFlagMessage,
                        ProjectSecondaryCS, ProjectSecondaryCsRegion,
                        DesignType, DesignDirection)
from app.decorators import role_required
from app.notifications import (
    notify_designers_of_revision_flag, notify_cs_of_brief_flag,
    notify_flag_reply, notify_cs_of_flag_resolved,
    notify_designer_of_concept_kv_assignment, notify_cs_of_lead_change,
    create_notification, notify_cs_of_project_started,
    notify_lead_designers_of_project_started
)
from app.utils import log_activity
# Import fingerprint helper so the initial page load stores the same value
# that the poll endpoint will return — ensures JS can compare apples to apples
from app.routes.api import _detail_fingerprint

detail_bp = Blueprint('project_detail', __name__)

@detail_bp.route('/projects/<int:project_id>')
@login_required
def detail(project_id):
    project = Project.query.get_or_404(project_id)

    from app.models import ProjectSubmission, ProjectRevision
    import json as _json

    # Active submission: the deck currently under review or awaiting upload
    active_submission = ProjectSubmission.query.filter_by(
        project_id=project_id, is_active=True
    ).first()

    # For CCM projects with concept/KV: the active C&KV submission (separate from POSM channel submissions)
    ckv_submission = None
    if project.brief_type == 'ccm' and (project.has_concept or project.has_kv):
        ckv_submission = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, phase='concept_kv'
        ).first()

    # Submission history: only decks that were fully submitted to the client.
    # Drafts/flagged decks that were replaced are not in this list (their files were deleted).
    submitted_history = ProjectSubmission.query.filter(
        ProjectSubmission.project_id == project_id,
        ProjectSubmission.submitted_to_client_at.isnot(None)
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).all()

    # All inactive submissions that were NOT submitted to client (flagged drafts) — for completeness
    past_submissions = ProjectSubmission.query.filter_by(
        project_id=project_id, is_active=False
    ).order_by(ProjectSubmission.uploaded_at.desc()).all()

    # Deliverables as JSON for the submission deliverable picker.
    # For CCM briefs each deliverable has a project_customer_id — we pass the
    # customer name so the JS can group checkboxes by customer.
    # For standard briefs project_customer_id is null and no grouping is needed.
    all_deliverables_for_picker = Deliverable.query.filter_by(
        project_id=project_id
    ).order_by(Deliverable.created_at).all()

    deliverables_json = _json.dumps([
        {
            'id': d.id,
            'name': d.name,
            'status': d.status,
            # project_customer_id is None for standard brief deliverables
            'customer_id':   d.project_customer_id,
            'customer_name': d.project_customer.customer.name if d.project_customer else None
        }
        for d in all_deliverables_for_picker
    ])

    _d3 = User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == '3D').order_by(User.name).all()
    _d2 = User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == '2D').order_by(User.name).all()
    _dt = User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == 'Technical').order_by(User.name).all()
    designers_by_team = {
        '3D': _d3, '3d': _d3,
        '2D': _d2, '2d': _d2,
        'Technical': _dt, 'technical': _dt,
    }

    assignments_by_team = {}
    for assignment in project.assigned_designers:
        assignments_by_team[assignment.team] = assignment

    brief_sections = {}
    for pc in project.project_customers:
        region = pc.customer.region
        if region not in brief_sections:
            brief_sections[region] = []
        brief_sections[region].append(pc)

    assignments_by_deliverable = {}
    for deliverable in project.project_deliverables:
        by_team = {}
        for assignment in deliverable.disciplines:
            by_team[assignment.team] = assignment  # DeliverableAssignment object (one per team)
        assignments_by_deliverable[deliverable.id] = by_team

    from app.models import BriefFlag
    open_flags = BriefFlag.query.filter_by(project_id=project_id, is_resolved=False).order_by(BriefFlag.created_at).all()
    all_flags = BriefFlag.query.filter_by(project_id=project_id).order_by(BriefFlag.created_at.desc()).all()

    # Standard brief deliverables (no project_customer_id)
    standard_deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.created_at).all()

    standard_assignments_by_deliverable = {}
    for d in standard_deliverables:
        # Standard deliverables have one assignment per deliverable (not per team)
        asgn = d.disciplines[0] if d.disciplines else None
        standard_assignments_by_deliverable[d.id] = asgn

    # Designers per standard brief deliverable — filtered by each deliverable's own teams
    # Falls back to the project's design type teams, then all designers
    dt = project.design_type
    dt_teams = [t.strip() for t in dt.team.split(',') if t.strip()] if (dt and dt.team) else []

    def _designers_for_teams(teams):
        if not teams:
            return [d for team_list in designers_by_team.values() for d in team_list]
        pool = []
        for t in teams:
            pool.extend(designers_by_team.get(t, []))
        seen = set()
        return [d for d in pool if not (d.id in seen or seen.add(d.id))]

    # Fallback: project-level design type teams
    standard_designers = _designers_for_teams(dt_teams)
    standard_team = dt.team if (dt and dt.team) else None

    # Per-deliverable overrides when the deliverable itself has teams set
    standard_designers_by_deliverable = {}
    for d in standard_deliverables:
        if d.teams:
            d_teams = [t.strip() for t in d.teams.split(',') if t.strip()]
            standard_designers_by_deliverable[d.id] = _designers_for_teams(d_teams)
        else:
            standard_designers_by_deliverable[d.id] = standard_designers

    # ── Secondary CS ─────────────────────────────────────────────
    from app.models import ProjectSecondaryCS, ProjectSecondaryCsRegion
    from flask import session as _session

    _emulating_id = _session.get('emulating_user_id')
    _effective_user_id = _emulating_id if (_emulating_id and current_user.role == 'admin') else current_user.id

    secondary_cs_assignments = ProjectSecondaryCS.query.filter_by(project_id=project_id).all()
    secondary_cs_ids = {a.user_id for a in secondary_cs_assignments}
    is_secondary_cs = _effective_user_id in secondary_cs_ids

    # Regions the current effective user has subscribed to (for C&CM projects)
    my_secondary_regions = {
        r.region for r in ProjectSecondaryCsRegion.query.filter_by(
            project_id=project_id, user_id=_effective_user_id
        ).all()
    } if is_secondary_cs else set()

    # CS users available to be added (exclude lead and already-added)
    available_cs_users = User.query.filter(
        User.role.in_(['cs', 'admin', 'management']),
        User.id != project.cs_lead_id,
        ~User.id.in_(secondary_cs_ids) if secondary_cs_ids else True
    ).order_by(User.name).all()

    # Gulf regions: C&CM projects with customers in UAE/Kuwait/Qatar/Bahrain/Oman
    # submit POSM by region then customer, not just by customer.
    GULF_REGION_KEYS  = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman']
    GULF_REGION_NAMES = {
        'uae': 'UAE', 'kuwait': 'Kuwait',
        'qatar': 'Qatar', 'bahrain': 'Bahrain', 'oman': 'Oman'
    }
    is_gulf = project.brief_type == 'ccm' and any(k in brief_sections for k in GULF_REGION_KEYS)

    # POSM is always active for Gulf C&CM projects — no manual "Begin POSM" step required
    posm_active = is_gulf

    # Pass each Gulf region with its customers so the JS can build the two-step picker.
    gulf_regions_json = _json.dumps([
        {
            'key': k,
            'name': GULF_REGION_NAMES[k],
            'customers': [
                {'id': pc.id, 'name': pc.customer.name, 'posm_revision_count': pc.posm_revision_count or 0}
                for pc in brief_sections[k]
            ]
        }
        for k in GULF_REGION_KEYS if k in brief_sections
    ]) if is_gulf else '[]'

    # Non-Gulf C&CM: flat customer list (kept for non-Gulf fallback)
    project_customers_json = _json.dumps([
        {'id': pc.id, 'name': pc.customer.name, 'posm_revision_count': pc.posm_revision_count or 0}
        for pc in project.project_customers
    ]) if (project.brief_type == 'ccm' and not is_gulf) else '[]'

    # Stored per-country POSM revision counts (Kuwait/Qatar/Bahrain/Oman)
    # Mirrors pc.posm_revision_count for UAE — incremented in send_revision.
    gulf_posm_counts = project.posm_country_revision_counts or {}

    # ── Parallel POSM channels ──────────────────────────────────────────────────
    # For Gulf C&CM projects: always build per-channel data for the pill UI.
    # Channels are auto-created on page load — no "Begin POSM" step required.
    # New customers added to the brief get a channel automatically.
    posm_channels_data = []
    if is_gulf:
        from app.models import ProjectPosmChannel, ProjectSubmission as _PS, ProjectRevision as _PR

        # Remove orphaned UAE channels — these arise when an edit deletes+recreates
        # ProjectCustomer records and PostgreSQL's ON DELETE SET NULL fires, leaving
        # a UAE channel with posm_customer_id=NULL. Delete them now so they get
        # recreated correctly below with the new ProjectCustomer ID.
        orphaned = [ch for ch in project.posm_channels
                    if ch.posm_country == 'uae' and ch.posm_customer_id is None]
        if orphaned:
            for ch in orphaned:
                db.session.delete(ch)
            db.session.flush()

        # Build a set of channel keys that already exist
        existing_channel_keys = set()
        for ch in project.posm_channels:
            if ch.posm_country == 'uae':
                existing_channel_keys.add(('uae', ch.posm_customer_id))
            else:
                existing_channel_keys.add((ch.posm_country, None))

        # Create any channels that are missing (new customers / first-time load)
        new_channels_added = False
        for region_key in GULF_REGION_KEYS:
            if region_key not in brief_sections:
                continue
            if region_key == 'uae':
                
                for pc in brief_sections['uae']:
                    if pc.cancelled:
                        continue
                    if ('uae', pc.id) not in existing_channel_keys:
                        db.session.add(ProjectPosmChannel(
                            project_id=project_id,
                            posm_country='uae',
                            posm_customer_id=pc.id,
                            status='in_queue',
                        ))
                        new_channels_added = True
            else:
                if (region_key, None) not in existing_channel_keys:
                    db.session.add(ProjectPosmChannel(
                        project_id=project_id,
                        posm_country=region_key,
                        posm_customer_id=None,
                        status='in_queue',
                    ))
                    new_channels_added = True
        if new_channels_added:
            db.session.commit()

        # Sort channels: UAE first (by customer name), then other regions in Gulf key order
        def _ch_sort_key(ch):
            idx = GULF_REGION_KEYS.index(ch.posm_country) if ch.posm_country in GULF_REGION_KEYS else 99
            cust_name = ch.posm_customer.customer.name if ch.posm_customer else ''
            return (idx, cust_name)

        for channel in sorted(project.posm_channels, key=_ch_sort_key):
            if channel.posm_country == 'uae' and channel.posm_customer:
                label = f'UAE — {channel.posm_customer.customer.name}'
            else:
                label = GULF_REGION_NAMES.get(channel.posm_country, channel.posm_country.title())

            # Active submission for this channel specifically
            ch_sub_q = _PS.query.filter_by(
                project_id=project_id,
                is_active=True,
                posm_country=channel.posm_country,
            )
            if channel.posm_customer_id is not None:
                ch_sub_q = ch_sub_q.filter(_PS.posm_customer_id == channel.posm_customer_id)
            else:
                ch_sub_q = ch_sub_q.filter(_PS.posm_customer_id == None)  # noqa: E711
            ch_active_sub = ch_sub_q.first()

            # Latest revision for this channel
            ch_rev_q = _PR.query.filter_by(
                project_id=project_id,
                posm_country=channel.posm_country,
            )
            if channel.posm_customer_id is not None:
                ch_rev_q = ch_rev_q.filter(_PR.posm_customer_id == channel.posm_customer_id)
            else:
                ch_rev_q = ch_rev_q.filter(_PR.posm_customer_id == None)  # noqa: E711
            ch_latest_rev = ch_rev_q.order_by(_PR.sent_at.desc()).first()

            posm_channels_data.append({
                'channel': channel,
                'label': label,
                'active_submission': ch_active_sub,
                'latest_revision': ch_latest_rev,
                'cancelled': channel.posm_customer.cancelled if channel.posm_customer else False,
            })
    
    from app.models import ProjectSubmission
    pc_ids_with_submissions = {
        s.posm_customer_id
        for s in ProjectSubmission.query.filter_by(project_id=project_id).all()
        if s.posm_customer_id is not None
    }

    # Set of (posm_country, posm_customer_id_or_None) for every approved POSM channel.
    # UAE channels have posm_customer_id set (per-customer); Gulf channels have it as None (per-country).
    # Used in the template to lock deliverable assignments and flag buttons on approved channels.
    approved_channel_keys = {
        (ch.posm_country, ch.posm_customer_id)
        for ch in project.posm_channels
        if ch.status == 'approved'
    }

    return render_template(
        'projects/detail.html',
        project=project,
        designers_by_team=designers_by_team,
        assignments_by_team=assignments_by_team,
        brief_sections=brief_sections,
        assignments_by_deliverable=assignments_by_deliverable,
        open_flags=open_flags,
        all_flags=all_flags,
        standard_deliverables=standard_deliverables,
        standard_assignments_by_deliverable=standard_assignments_by_deliverable,
        standard_designers=standard_designers,
        standard_team=standard_team,
        standard_designers_by_deliverable=standard_designers_by_deliverable,
        active_submission=active_submission,
        past_submissions=past_submissions,
        submitted_history=submitted_history,
        deliverables_json=deliverables_json,
        latest_revision=ProjectRevision.query.filter_by(project_id=project_id)
                        .order_by(ProjectRevision.sent_at.desc()).first(),
        
        secondary_cs_assignments=secondary_cs_assignments,
        is_secondary_cs=is_secondary_cs,
        my_secondary_regions=my_secondary_regions,
        available_cs_users=available_cs_users,
        posm_active=posm_active,
        is_gulf=is_gulf,
        gulf_regions_json=gulf_regions_json,
        gulf_posm_counts=gulf_posm_counts,
        project_customers_json=project_customers_json,
        gulf_region_names=GULF_REGION_NAMES,
        posm_channels_data=posm_channels_data,
        ckv_submission=ckv_submission,
        pc_ids_with_submissions=pc_ids_with_submissions,
        approved_channel_keys=approved_channel_keys,
        # Latest revision request sent for C&KV specifically.
        # Filtered to posm_country=None so POSM channel revisions don't bleed in.
        # Only queried for CCM briefs — None for all others.
        ckv_latest_revision=(
            ProjectRevision.query.filter_by(
                project_id=project_id,
                posm_country=None,
                posm_customer_id=None
            ).order_by(ProjectRevision.sent_at.desc()).first()
            if project.brief_type == 'ccm' else None
        ),

        # Fingerprint of the full project state at render time.
        # Stored as data-fp on #section-assignments in the template.
        # polling.js compares this against the poll endpoint's response —
        # if they differ, it reloads the page to pick up the change.
        project_fp=_detail_fingerprint(project),

        # Total revision count across C&KV + all POSM channels for CCM projects.
        # We count ProjectRevision rows directly — each revision (C&KV or channel)
        # gets one row, so the count is always accurate.
        total_revision_count=(
            ProjectRevision.query.filter_by(project_id=project_id).count()
            if project.brief_type == 'ccm' else 0
        ),
    )

@detail_bp.route('/projects/<int:project_id>/set-status', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management', 'designer', 'team_lead')
def set_project_status(project_id):
    from app.utils import log_activity
    from app.status_tracking import record_project_status


    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    new_status = data.get('status')

    VALID = ['briefed', 'in_queue', 'in_progress', 'submitted',
             'internal_review', 'internal_revision', 'submitted_to_client',
             'revision_in_queue', 'revision_in_progress', 'approved', 'on_hold',
             'awaiting_posm_details']
    if new_status not in VALID:
        return jsonify({'error': 'Invalid status'}), 400

    old_status = project.project_status
    record_project_status(project, new_status, current_user)
    db.session.commit()

    log_activity(
        'project_status_changed',
        f'Project "{project.name}" status changed from "{old_status}" to "{new_status}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True})  

@detail_bp.route('/projects/<int:project_id>/toggle-hold', methods=['POST'])
@login_required
def toggle_hold(project_id):
    from app.utils import log_activity
    from app.status_tracking import record_project_status
    from flask import session as flask_session
    project = Project.query.get_or_404(project_id)

    # Resolve effective user (supports admin emulation)
    emulating_id = flask_session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = User.query.get(emulating_id)
    else:
        effective_user = current_user

    # Only CS lead, secondary CS, or admin
    from app.models import ProjectSecondaryCS
    is_secondary = ProjectSecondaryCS.query.filter_by(
        project_id=project_id, user_id=effective_user.id
    ).first() is not None

    if not (effective_user.role == 'admin' or
            project.cs_lead_id == effective_user.id or
            is_secondary):
        abort(403)

    if project.project_status == 'on_hold':
        # Resume: restore previous status (fall back to briefed)
        restore_to = project.held_from_status or 'briefed'
        record_project_status(project, restore_to, effective_user)
        project.held_from_status = None
        log_activity('project_resumed', f'Project "{project.name}" resumed (status: {restore_to})',
                     user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
        flash('Project resumed.', 'success')
    else:
        # Put on hold: save current status first
        project.held_from_status = project.project_status
        record_project_status(project, 'on_hold', effective_user)
        log_activity('project_on_hold', f'Project "{project.name}" put on hold',
                     user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
        flash('Project put on hold.', 'success')

    db.session.commit()
    return redirect(url_for('project_detail.detail', project_id=project_id))


@detail_bp.route('/projects/<int:project_id>/customer/<int:pc_id>/set-status', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management', 'designer', 'team_lead')
def set_customer_status(project_id, pc_id):
    from app.utils import log_activity
    from app.models import ProjectCustomer
    from app.status_tracking import record_customer_status, record_deliverable_status
    project = Project.query.get_or_404(project_id)
    pc = ProjectCustomer.query.get_or_404(pc_id)
    data = request.get_json()
    new_status = data.get('status')

    VALID = ['briefed', 'in_queue', 'in_progress', 'submitted',
             'revision_in_queue', 'revision_in_progress', 'approved', 'on_hold']
    if new_status not in VALID:
        return jsonify({'error': 'Invalid status'}), 400

    old_status = pc.status
    record_customer_status(pc, new_status, current_user)

    # Cascade: approving a customer approves all its deliverables too
    if new_status == 'approved':
        for deliverable in pc.deliverables:
            record_deliverable_status(deliverable, 'approved', current_user)

    db.session.commit()

    log_activity(
        'customer_status_changed',
        f'Customer "{pc.customer.name}" on "{project.name}" status changed from "{old_status}" to "{new_status}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True, 'approved': new_status == 'approved'})

@detail_bp.route('/projects/<int:project_id>/customer/<int:pc_id>/remove', methods=['POST'])
@login_required
@role_required('admin','cs','management')
def remove_customer(project_id, pc_id):
    from app.utils import log_activity
    from app.notifications import create_notification
    from app.models import ProjectCustomer, ProjectSubmission, DeliverableAssignment, ProjectPosmChannel, User as UserModel
    project = Project.query.get_or_404(project_id)
    pc = ProjectCustomer.query.get_or_404(pc_id)

    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'Project is approved and locked'}), 403

    # Guard: refuse if submissions exist - we use cancel instead
    has_submissions = ProjectSubmission.query.filter_by(posm_customer_id=pc.id).first()
    if has_submissions:
        return jsonify({'success': False, 'error': 'Customer has submissions. Use cancel instead.'}), 400

    customer_name = pc.customer.name

    # Collect designers to notify (lead + deliverable assignees), deduplicated
    notify_ids = set()
    if project.lead_designer_id:
        notify_ids.add(project.lead_designer_id)
    for d in pc.deliverables:
        for assignment in DeliverableAssignment.query.filter_by(deliverable_id=d.id).all():
            notify_ids.add(assignment.designer_id)

    # Delete any UAE POSM channels tied to this customer before deleting the customer —
    # project_posm_channels.posm_customer_id is a FK with no cascade, so Postgres
    # will block the DELETE otherwise.
    ProjectPosmChannel.query.filter_by(posm_customer_id=pc.id).delete(synchronize_session=False)

    db.session.delete(pc)
    db.session.commit()

    # Notify after commit
    for uid in notify_ids:
        recipient = UserModel.query.get(uid)
        if recipient:
            create_notification(
                recipient=recipient,
                message=f'Customer "{customer_name}" was removed from project "{project.name}".',
                notification_type='customer_removed',
                project=project,
                triggered_by=current_user
            )

    log_activity(
        'customer_removed',
        f'Customer "{customer_name}" removed from "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id

    )
    return jsonify ({'success': True})

@detail_bp.route('/projects/<int:project_id>/customer/<int:pc_id>/cancel', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def cancel_customer(project_id, pc_id):
    from app.utils import log_activity
    from app.notifications import create_notification
    from app.models import ProjectCustomer, DeliverableAssignment, User as UserModel
    project = Project.query.get_or_404(project_id)
    pc = ProjectCustomer.query.get_or_404(pc_id)

    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'Project is approved and locked'}), 403

    customer_name = pc.customer.name
    pc.cancelled = True

    # Collect designers to notify (lead + deliverable assignees), deduplicated
    notify_ids = set()
    if project.lead_designer_id:
        notify_ids.add(project.lead_designer_id)
    for d in pc.deliverables:
        for assignment in DeliverableAssignment.query.filter_by(deliverable_id=d.id).all():
            notify_ids.add(assignment.designer_id)

    db.session.commit()

    # Notify after commit
    for uid in notify_ids:
        recipient = UserModel.query.get(uid)
        if recipient:
            create_notification(
                recipient=recipient,
                message=f'Customer "{customer_name}" was cancelled on project "{project.name}".',
                notification_type='customer_cancelled',
                project=project,
                triggered_by=current_user
            )

    log_activity(
        'customer_cancelled',
        f'Customer "{customer_name}" cancelled on "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/deliverable/<int:d_id>/set-status', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management', 'designer', 'team_lead')
def set_deliverable_status(project_id, d_id):
    from app.utils import log_activity
    from app.models import Deliverable
    from app.status_tracking import record_deliverable_status
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.get_or_404(d_id)
    data = request.get_json()
    new_status = data.get('status')

    # Valid deliverable statuses — includes the new submission flow statuses
    VALID = ['in_queue', 'in_progress', 'submitted',
             'revision_in_queue', 'revision_in_progress', 'approved',
             'internal_review', 'internal_revision', 'submitted_to_client']
    if new_status not in VALID:
        return jsonify({'error': 'Invalid status'}), 400

    from app.models import Deliverable as Del

    old_status = deliverable.status
    record_deliverable_status(deliverable, new_status, current_user)

    revision_completed = False

    # Per-deliverable revision cycle: when a designer re-submits a flagged deliverable
    # and it's the last flagged one, increment per-deliverable revision counts.
    # NOTE: project.revision_count and project_status are no longer changed here —
    # those are now managed exclusively by the client submission flow (submit_to_client).
    if new_status == 'submitted' and deliverable.flagged_for_revision:
        others_pending = Del.query.filter(
            Del.project_id == project_id,
            Del.flagged_for_revision == True,
            Del.id != deliverable.id,
            Del.status != 'submitted'
        ).count()

        if others_pending == 0:
            # Last flagged deliverable re-submitted — clear all revision flags
            all_flagged = Del.query.filter_by(project_id=project_id, flagged_for_revision=True).all()
            for d in all_flagged:
                d.revision_count += 1
                d.flagged_for_revision = False
            revision_completed = True

    db.session.commit()

    log_activity(
        'deliverable_status_changed',
        f'Deliverable "{deliverable.name}" on "{project.name}" status changed from "{old_status}" to "{new_status}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    if revision_completed:
        notify_cs_of_revision_submitted(project, triggered_by=current_user)

    # Notify secondary CS of the status change (C&CM only, region-filtered)
    from app.notifications import notify_secondary_cs_of_deliverable_status
    notify_secondary_cs_of_deliverable_status(deliverable, project, new_status, triggered_by=current_user)

    return jsonify({'success': True, 'revision_completed': revision_completed})

@detail_bp.route('/projects/<int:project_id>/deliverable/<int:d_id>/flag-revision', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def flag_deliverable_revision(project_id, d_id):
    from app.models import Deliverable
    from app.status_tracking import record_project_status, record_deliverable_status
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.get_or_404(d_id)

    deliverable.flagged_for_revision = True
    record_deliverable_status(deliverable, 'revision_in_queue', current_user)
    record_project_status(project, 'revision_in_queue', current_user)

    db.session.commit()

    notify_designers_of_revision_flag(deliverable, project, triggered_by=current_user)

    log_activity(
        'revision_flagged',
        f'"{deliverable.name}" on "{project.name}" flagged for revision by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/deliverable/<int:d_id>/assign', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def assign_deliverable(project_id, d_id):
    from app.models import Deliverable, DeliverableAssignment
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.get_or_404(d_id)

    designer_id = request.form.get('designer_id')
    team = request.form.get('team')

    if not designer_id or not team:
        return redirect(url_for('project_detail.detail', project_id=project_id))

    designer_id = int(designer_id)
    designer = User.query.get_or_404(designer_id)

    existing = DeliverableAssignment.query.filter_by(
        deliverable_id=d_id,
        team=team
    ).first()

    if existing:
        existing.designer_id = designer_id
        existing.assigned_by_id = current_user.id
        existing.assigned_at = datetime.utcnow()
        action_word = 'reassigned'
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=d_id,
            designer_id=designer_id,
            team=team,
            assigned_by_id=current_user.id
        ))
        action_word = 'assigned'

    db.session.commit()

    log_activity(
        'deliverable_assigned',
        f'{designer.name} {action_word} to "{deliverable.name}" ({team}) on "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True, 'designer_name': designer.name})


# ── Brief Flag System ────────────────────────────────────────────────────────

@detail_bp.route('/projects/<int:project_id>/flags/create', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead', 'management')  # management can raise flags to escalate issues
def create_flag(project_id):
    from app.models import BriefFlag, BriefFlagMessage, User as UserModel
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    flag_type = data.get('flag_type')
    deliverable_id = data.get('deliverable_id')
    message_text = (data.get('message') or '').strip()

    if flag_type not in ('project', 'deliverable', 'concept', 'kv') or not message_text:
        return jsonify({'error': 'Invalid data'}), 400

    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    flag = BriefFlag(
        project_id=project_id,
        deliverable_id=deliverable_id or None,
        flag_type=flag_type,
        created_by_id=actor.id
    )
    db.session.add(flag)
    db.session.flush()

    db.session.add(BriefFlagMessage(
        flag_id=flag.id,
        author_id=actor.id,
        message=message_text
    ))
    db.session.commit()

    notify_cs_of_brief_flag(flag, project, triggered_by=actor)

    log_activity(
        'brief_flag_created',
        f'{actor.name} raised a {flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/flags/<int:flag_id>/reply', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead', 'management')  # management can participate in flag threads
def reply_flag(project_id, flag_id):
    from app.models import BriefFlag, BriefFlagMessage, User as UserModel
    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)

    message_text = (request.form.get('message') or '').strip()
    if not message_text:
        return redirect(url_for('project_detail.detail', project_id=project_id))

    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    db.session.add(BriefFlagMessage(
        flag_id=flag_id,
        author_id=actor.id,
        message=message_text
    ))
    db.session.commit()

    notify_flag_reply(flag, project, triggered_by=actor)

    log_activity(
        'brief_flag_reply',
        f'{actor.name} replied to a flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return redirect(url_for('project_detail.detail', project_id=project_id))


@detail_bp.route('/projects/<int:project_id>/flags/<int:flag_id>/resolve', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead', 'management')  # management can resolve any flag (oversight role)
def resolve_flag(project_id, flag_id):
    from app.models import BriefFlag, User as UserModel
    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)

    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Only the flag creator, admin, or management can resolve — others (e.g. designers on unrelated flags) cannot
    if flag.created_by_id != actor.id and current_user.role not in ('admin', 'management'):
        return jsonify({'error': 'Only the person who raised this flag can resolve it'}), 403

    flag.is_resolved = True
    flag.resolved_at = datetime.utcnow()
    flag.resolved_by_id = actor.id
    db.session.commit()

    notify_cs_of_flag_resolved(flag, project, triggered_by=actor)

    log_activity(
        'brief_flag_resolved',
        f'{actor.name} resolved a {flag.flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


# ── Designer / Team assignment ───────────────────────────────────────────────

@detail_bp.route('/projects/<int:project_id>/assign-designers', methods=['POST'])
@login_required
@role_required('admin', 'team_lead')
def assign_designers(project_id):
    project = Project.query.get_or_404(project_id)

    # Lead designer logic - commented out for MVP, will return in Phase 2
    # lead_designer_id = request.form.get('lead_designer_id')
    # project.lead_designer_id = int(lead_designer_id) if lead_designer_id else None

    requested_teams = [t.strip() for t in project.design_teams_requested.split(',')]

    # Track new assignments so we can fire notifications after commit
    new_assignments = []

    for team in requested_teams:
        field_name = f"designer_{team.lower()}"
        user_id = request.form.get(field_name)

        if not user_id:
            continue  # Skip teams that weren't submitted in this form

        # Team leads can only assign for their own team
        if current_user.role == 'team_lead' and current_user.team != team:
            continue

        designer = User.query.get(int(user_id))
        if not designer:
            continue

        # Remove existing assignment for THIS team only - not all teams
        ProjectDesigner.query.filter_by(
            project_id=project.id,
            team=team
        ).delete(synchronize_session=False)
        db.session.flush()  # flush DELETE before INSERT to avoid unique constraint violation

        # Create the new assignment
        assignment = ProjectDesigner(
            project_id=project.id,
            user_id=int(user_id),
            team=team
        )
        db.session.add(assignment)

        new_assignments.append((designer, team))

    db.session.commit()

    # Send notifications for each new assignment - after commit so the data is saved
    for designer, team in new_assignments:
        notify_cs_of_lead_change(
            project=project,
            new_designer=designer,
            team_name=team,
            triggered_by=current_user
        )
        log_activity('designer_assigned', f'{designer.name} assigned to {team} team on "{project.name}"', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'assignments': [
            {'name': d.name, 'team': t} for d, t in new_assignments
        ]
    })


@detail_bp.route('/projects/<int:project_id>/assign-lead', methods=['POST'])
@login_required
def assign_lead(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    team = data.get('team', '').strip()
    new_designer_id = data.get('new_designer_id')

    if not team:
        return jsonify({'success': False, 'error': 'Team is required.'}), 400

    # ── Emulation-aware actor ──────────────────────────────────────────────
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Role guard: designers/team leads can only assign for their own team
    if actor.role in ('designer', 'team_lead') and actor.team != team:
        return jsonify({'success': False, 'error': 'You can only assign yourself to your own team.'}), 403

    # Get current lead for this team (if any)
    current_assignment = ProjectDesigner.query.filter_by(
        project_id=project.id, team=team
    ).first()
    previous_designer = current_assignment.designer if current_assignment else None

    if new_designer_id:
        # Current lead is transferring to a specific person — only the current lead can do this
        if not current_assignment or current_assignment.user_id != actor.id:
            return jsonify({'success': False, 'error': 'Only the current lead can transfer ownership.'}), 403
        new_designer = User.query.get(int(new_designer_id))
        if not new_designer:
            return jsonify({'success': False, 'error': 'Designer not found.'}), 404
        db.session.delete(current_assignment)
        db.session.flush()  # force DELETE before INSERT to avoid UniqueViolation
        db.session.add(ProjectDesigner(project_id=project.id, user_id=new_designer.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, new_designer, team, triggered_by=actor, previous_designer=previous_designer)
        log_activity('lead_transferred',
                     f'{actor.name} transferred {team} lead to {new_designer.name} on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    else:
        # Self-assign or immediate takeover
        if current_assignment:
            db.session.delete(current_assignment)
            db.session.flush()  # force DELETE before INSERT to avoid UniqueViolation
        db.session.add(ProjectDesigner(project_id=project.id, user_id=actor.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, actor, team, triggered_by=actor, previous_designer=previous_designer)
        action = 'lead_transferred' if previous_designer else 'lead_assigned'
        description = (
            f'{actor.name} took over as {team} lead on "{project.name}" '
            f'(previously {previous_designer.name})'
            if previous_designer
            else f'{actor.name} self-assigned as {team} lead on "{project.name}"'
        )
        log_activity(action, description, user=actor,
                     entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

# _____________ Auto-generate FOC Job Number __________
# Returns the next available FOC-NNN job number.
# FOC_PAD controls zero-padding width - change to 4 to get FOC-1000 etc.
@detail_bp.route('/projects/<int:project_id>/start-project', methods=['POST'])
@login_required
def start_project(project_id):
    from app.status_tracking import record_project_status
    project = Project.query.get_or_404(project_id)

    # Resolve the effective actor to respect admin emulation
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Role guard: must be an admin, designer, or team lead whose team is requested on this project
    requested_teams = [t.strip() for t in (project.design_teams_requested or '').split(',')]
    if actor.role != 'admin' and not (actor.role in ('designer', 'team_lead') and actor.team in requested_teams):
        return jsonify({'success': False, 'error': 'You are not assigned to a team requested on this project.'}), 400

    # Idempotency guard: only move forward if currently briefed
    if project.project_status != 'briefed':
        return jsonify({'success': False, 'error': 'Project is not in Briefed status.'}), 400

    # Transition status
    record_project_status(project, 'in_progress', actor)

    # Auto-assign the actor as lead for their team
    if actor.team:
        existing = ProjectDesigner.query.filter_by(project_id=project.id, team=actor.team).first()
        if existing:
            db.session.delete(existing)
            db.session.flush()
        db.session.add(ProjectDesigner(project_id=project.id, user_id=actor.id, team=actor.team))

    db.session.commit()

    # Notify CS lead, secondary CS, and other assigned lead designers
    notify_cs_of_project_started(project, triggered_by=actor)
    notify_lead_designers_of_project_started(project, triggered_by=actor)

    # Record in activity log
    log_activity('project_started',
                 f'{actor.name} started work on "{project.name}"',
                 user=actor, entity_type='project',
                 entity_name=project.name, entity_id=project.id)
    
    return jsonify({'success': True})




@detail_bp.route('/projects/<int:project_id>/secondary-cs', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def add_secondary_cs(project_id):
    """Add a CS user as secondary CS on a project. Only the CS lead or admin can do this."""
    from app.models import ProjectSecondaryCS
    project = Project.query.get_or_404(project_id)

    if current_user.role != 'admin' and current_user.id != project.cs_lead_id:
        abort(403)

    user_id = request.form.get('user_id', type=int)
    if not user_id:
        return jsonify({'success': False, 'error': 'Please select a CS member.'}), 400

    if user_id == project.cs_lead_id:
        return jsonify({'success': False, 'error': 'The CS lead is already the primary CS on this project.'}), 400

    user = User.query.get_or_404(user_id)
    # Allow the same three roles that populate the picker provides.
    if user.role not in ('cs', 'admin', 'management'):
        return jsonify({'success': False, 'error': 'Only CS & Management members can be added as secondary CS.'}), 400

    if ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first():
        return jsonify({'success': False, 'error': 'Already a secondary CS on this project.'}), 400

    db.session.add(ProjectSecondaryCS(project_id=project_id, user_id=user_id, added_by_id=current_user.id))
    db.session.commit()

    log_activity('secondary_cs_added', f'{user.name} added as secondary CS on "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/secondary-cs/<int:user_id>/remove', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def remove_secondary_cs(project_id, user_id):
    """Remove a secondary CS from a project."""
    from app.models import ProjectSecondaryCS, ProjectSecondaryCsRegion
    project = Project.query.get_or_404(project_id)

    if current_user.role != 'admin' and current_user.id != project.cs_lead_id:
        abort(403)

    assignment = ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first_or_404()
    user = User.query.get(user_id)

    # Clean up their region subscriptions too
    ProjectSecondaryCsRegion.query.filter_by(project_id=project_id, user_id=user_id).delete()
    db.session.delete(assignment)
    db.session.commit()

    log_activity('secondary_cs_removed', f'{user.name} removed as secondary CS on "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/secondary-cs/regions', methods=['POST'])
@login_required
def update_secondary_cs_regions(project_id):
    """Update C&CM region notification subscriptions for the current secondary CS."""
    from flask import session as flask_session
    from app.models import ProjectSecondaryCS, ProjectSecondaryCsRegion
    project = Project.query.get_or_404(project_id)

    # Resolve effective user (admin emulation)
    emulating_id = flask_session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = User.query.get(emulating_id)
    else:
        effective_user = current_user

    # Must be a secondary CS on this project
    if not ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=effective_user.id).first():
        abort(403)

    selected_regions = set(request.form.getlist('regions'))
    valid_regions = {'uae', 'kuwait', 'qatar', 'bahrain', 'oman'}

    ProjectSecondaryCsRegion.query.filter_by(project_id=project_id, user_id=effective_user.id).delete()
    for region in selected_regions & valid_regions:
        db.session.add(ProjectSecondaryCsRegion(project_id=project_id, user_id=effective_user.id, region=region))

    db.session.commit()
    flash('Region notification preferences updated.', 'success')
    return redirect(url_for('project_detail.detail', project_id=project_id))


@detail_bp.route('/projects/<int:project_id>/assign-concept-kv', methods=['POST'])
@login_required
@role_required('admin', 'team_lead', 'cs', 'management', 'designer')
def assign_concept_kv(project_id):
    project = Project.query.get_or_404(project_id)

    concept_id = request.form.get('concept_designer_id')
    kv_id = request.form.get('kv_designer_id')

    # Designers can only assign themselves — block any attempt to assign someone else
    if current_user.role == 'designer':
        if concept_id and int(concept_id) != current_user.id:
            abort(403)
        if kv_id and int(kv_id) != current_user.id:
            abort(403)

    if concept_id:
        project.concept_designer_id = int(concept_id)
    if kv_id:
        project.kv_designer_id = int(kv_id)

    db.session.commit()
    if concept_id:
        concept_designer = User.query.get(int(concept_id))
        if concept_designer:
            notify_designer_of_concept_kv_assignment(project, concept_designer, 'Concept', triggered_by=current_user)
            log_activity('designer_assigned', f'{concept_designer.name} assigned as Concept designer on "{project.name}"', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    if kv_id:
        kv_designer = User.query.get(int(kv_id))
        if kv_designer:
            notify_designer_of_concept_kv_assignment(project, kv_designer, 'Key Visual', triggered_by=current_user)
            log_activity('designer_assigned', f'{kv_designer.name} assigned as KV designer on "{project.name}"', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return redirect(url_for('project_detail.detail', project_id=project.id))

@detail_bp.route('/projects/<int:project_id>/standard-deliverables/add', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management', 'designer', 'team_lead')
def add_standard_deliverable(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Deliverable name is required'}), 400

    from datetime import date as date_type
    def parse_date(val):
        if not val:
            return None
        try:
            from datetime import datetime
            return datetime.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            return None

    deliverable = Deliverable(
        project_id=project_id,
        project_customer_id=None,
        deliverable_type_id=None,
        name=name,
        design_deadline=parse_date(data.get('design_deadline')),
        installation_deadline=parse_date(data.get('installation_deadline')),
        status='in_queue',
        created_by=current_user
    )
    db.session.add(deliverable)
    db.session.commit()

    log_activity('deliverable_created', f'Standard deliverable "{name}" added to "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'id': deliverable.id,
        'name': deliverable.name,
        'status': deliverable.status,
        'design_deadline': deliverable.design_deadline.isoformat() if deliverable.design_deadline else None,
        'installation_deadline': deliverable.installation_deadline.isoformat() if deliverable.installation_deadline else None,
    })


@detail_bp.route('/projects/<int:project_id>/standard-deliverables/<int:d_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def delete_standard_deliverable(project_id, d_id):
    deliverable = Deliverable.query.filter_by(id=d_id, project_id=project_id).first_or_404()
    name = deliverable.name
    project = Project.query.get_or_404(project_id)
    db.session.delete(deliverable)
    db.session.commit()
    log_activity('deliverable_deleted', f'Standard deliverable "{name}" removed from "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/standard-deliverables/<int:d_id>/assign', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def assign_standard_deliverable(project_id, d_id):
    from app.models import DeliverableAssignment
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.filter_by(id=d_id, project_id=project_id).first_or_404()

    designer_id = request.form.get('designer_id')
    if not designer_id:
        return jsonify({'success': False, 'error': 'Missing designer'}), 400

    designer_id = int(designer_id)
    designer = User.query.get_or_404(designer_id)
    team = designer.team or 'General'

    # For standard brief deliverables, one assignment per deliverable (replace any existing)
    existing = DeliverableAssignment.query.filter_by(deliverable_id=d_id).first()
    if existing:
        existing.designer_id = designer_id
        existing.team = team
        existing.assigned_by_id = current_user.id
        existing.assigned_at = datetime.utcnow()
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=d_id,
            designer_id=designer_id,
            team=team,
            assigned_by_id=current_user.id
        ))

    db.session.commit()
    log_activity('deliverable_assigned',
                 f'{designer.name} assigned to "{deliverable.name}" on "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True, 'designer_name': designer.name})

import uuid

@detail_bp.route('/projects/<int:project_id>/upload-file', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def upload_project_file(project_id):
    """Handle reference file uploads for a project. CS and admin only."""
    from app.models import ProjectFile

    project = Project.query.get_or_404(project_id)

    # Check a file was actually included in the request
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Only allow safe file types
    allowed_extensions = {'jpg', 'jpeg', 'png', 'pdf', 'docx', 'xlsx', 'pptx', 'zip', 'dwg'}
    original_filename = file.filename
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''

    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400

    # Read file bytes before anything else (file stream can only be read once)
    file_bytes = file.read()

    # Upload directly to NAS - synchronous, user waits for confirmation
    from app.nas import upload_app_file, build_file_path
    nas_file_path = build_file_path(project, 'Reference Files', original_filename)
    nas_folder = nas_file_path.rsplit('/',1)[0]
    upload_app_file(file_bytes, nas_folder, original_filename)

    # Save record - Filename column stores the NAS filename (Same as original)
    project_file = ProjectFile(
        project_id=project_id,
        filename=original_filename,
        original_filename=original_filename,
        file_type=ext,
        uploaded_by_id=current_user.id
    )

    db.session.add(project_file)
    db.session.commit()
    
    log_activity('file_uploaded', f'Reference file "{original_filename}" uploaded to "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'file': {
            'id': project_file.id,
            'original_filename': original_filename,
            'file_type': ext,
            'uploaded_by': current_user.name
        }
    })


@detail_bp.route('/projects/files/<int:file_id>/download')
@login_required
def download_project_file(file_id):
    """Serve a reference file for download. All authenticated users can download. Download is served from the NAS"""
    from app.models import ProjectFile
    from app.nas import download_app_file, build_file_path
    import io
    from flask import send_file
    
    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    file_bytes = download_app_file(nas_path)

    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=project_file.original_filename
    )

@detail_bp.route('/projects/<int:project_id>/reference-files/download-all')
@login_required
def download_all_reference_files(project_id):
    """Zips every reference file for this project and returns a download link."""
    from app.zip_utils import build_zip
    from app.nas import download_app_file, build_file_path

    project = Project.query.get_or_404(project_id)
    files = project.reference_files
    if not files:
        return jsonify({'success': False, 'error': 'No reference files to download.'}), 400

    zip_files = []
    seen_names = {}
    for f in files:
        nas_path = build_file_path(project, 'Reference Files', f.original_filename)
        try:
            content = download_app_file(nas_path)
        except RuntimeError:
            continue  # skip a file that failed to fetch rather than failing the whole zip

        # Disambiguate if two files happen to share a filename — zipfile
        # allows duplicate entry names, but most extractors handle that badly.
        name = f.original_filename
        if name in seen_names:
            seen_names[name] += 1
            base, dot, ext = name.rpartition('.')
            name = f'{base} ({seen_names[name]}).{ext}' if dot else f'{name} ({seen_names[name]})'
        else:
            seen_names[name] = 0

        zip_files.append((name, content))

    if not zip_files:
        return jsonify({'success': False, 'error': 'Could not fetch any files from the NAS.'}), 502

    zip_id = build_zip(zip_files, f'{project.name} - Reference Files.zip')
    return jsonify({'success': True, 'download_url': url_for('api.zip_download', zip_id=zip_id)})

@detail_bp.route('/projects/files/<int:file_id>/preview')
@login_required
def preview_project_file(file_id):
    """Serve a reference file for inline browser preview. Only file types a
    browser can actually render natively are supported — PDFs and common
    image formats. Anything else (.ai, .psd, .docx, etc.) returns a clear
    'no preview available' response so the frontend can fall back to
    download-only, rather than trying to force something that can't work."""
    from app.models import ProjectFile
    from app.nas import download_app_file, build_file_path
    from flask import send_file, jsonify
    import io

    # Maps a stored file extension to the mimetype the browser needs to
    # render it inline. Anything not in here just isn't previewable.
    PREVIEWABLE_TYPES = {
        'pdf':  'application/pdf',
        'jpg':  'image/jpeg',
        'jpeg': 'image/jpeg',
        'png':  'image/png',
        'gif':  'image/gif',
        'webp': 'image/webp',
    }

    project_file = ProjectFile.query.get_or_404(file_id)

    mimetype = PREVIEWABLE_TYPES.get((project_file.file_type or '').lower())
    if not mimetype:
        # Check the type BEFORE touching the NAS at all — no point paying
        # for a network round-trip to fetch a .psd we already know we can't
        # render.
        return jsonify({
            'success': False,
            'error': 'No preview available for this file type — download instead.'
        }), 415  # Unsupported Media Type

    project = Project.query.get(project_file.project_id)
    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    file_bytes = download_app_file(nas_path)

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=project_file.original_filename
    )


@detail_bp.route('/projects/files/<int:file_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def delete_project_file(file_id):
    """Delete a reference file. CS and admin only."""
    from app.models import ProjectFile

    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    # Delete from NAS
    from app.nas import delete_app_file, build_file_path
    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    delete_app_file(nas_path)

    log_activity('file_deleted', f'Reference file "{project_file.original_filename}" deleted from "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    db.session.delete(project_file)
    db.session.commit()

    return jsonify({'success': True})


@detail_bp.route('/projects/<int:project_id>/nas-link', methods=['GET'])
@login_required
def get_nas_link(project_id):
    """Return a File Station deep link for the project's NAS folder.
    Logged-in DSM users are taken straight to the folder.
    Users who need to log in first can use the displayed path to navigate."""
    import urllib.parse
    project = Project.query.get_or_404(project_id)

    root        = current_app.config['NAS_PROJECT_ROOT']
    year        = project.created_at.year
    client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
    folder_path = f'{root}/{year}/{client_name}/{project.name}'

    base = (current_app.config.get('NAS_WEB_URL') or
            f"https://{current_app.config['NAS_HOST']}:{current_app.config['NAS_PORT']}")

    # DSM 7 deep-link format: launchParam carries openfile=<path>.
    # Double-encode so that & in folder names (e.g. "P&G") survives Synology's
    # internal sub-param parse of launchParam: & → %26 (step 1) → %2526 (step 2).
    # After the server decodes launchParam once, openfile value contains %26 (not &),
    # so no spurious splitting occurs. File Station then decodes %26 → & correctly.
    path_encoded = urllib.parse.quote(folder_path, safe='/')   # & → %26, space → %20
    launch_param = urllib.parse.quote(f"opendir={path_encoded}", safe='/')  # % → %25
    url = (f"{base}/index.cgi"
           f"?launchApp=SYNO.SDS.App.FileStation3.Instance"
           f"&launchParam={launch_param}")

    return jsonify({'success': True, 'url': url, 'path': folder_path})


# ── Project Submission Routes ─────────────────────────────────────────────────
# Flow:
#   1. Designer uploads deck → upload_submission (returns submission.id + previous deliverable IDs)
#   2. Designer picks deliverables → submit_for_internal_review (project + deliverables → internal_review)
#   3. CS reviews:
#      a. Flags it  → flag_submission (project + deliverables → internal_revision, notify designer)
#         Designer reuploads (repeat from step 1), new submission inherits previous picker selection
#      b. Approves  → submit_to_client (project + ALL deliverables → submitted_to_client,
#                                        revision_count +1, open mailto in browser)
#   Deck files that reached "submitted_to_client" are kept permanently for audit history.
#   Draft/flagged decks that are replaced on reupload are deleted from disk.

