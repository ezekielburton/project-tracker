"""
Pre-Production routes: per-stream assign / mark done / approve / flag,
Skip to Pre-Production, and the Handed to Production cascade.

- A deliverable is in Pre-Production once status='approved' and it needs at
  least one of 2D/3D/Technical. There is no separate gate; the approval is
  timestamped in DeliverableStatusLog (services/status_tracking.py's
  record_deliverable_status()).
- Each stream is independent: None (not started, or flagged) -> 'uploaded'
  -> 'approved'. Only a Project Owner approval completes a stream; a flag
  resets it to None and logs why.
- Streams reuse Design's DeliverableAssignment team values ('2D'/'3D'/
  'Technical'), so a Design assignee carries straight over.
- Handed to Production is derived: once every deliverable in scope has all
  its streams approved, the channel/project advances automatically.
"""

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from app.modules.core.shared.lib.users import active_users_query
from app.modules.core.shared.lib.capabilities import can, effective_user
from app.modules.projects.lib.teams import assignable_teams_for
from datetime import datetime

from app.modules.core.shared.models import Project, Deliverable

project_preproduction_bp = Blueprint('project_preproduction', __name__, template_folder='../templates')

# The three Pre-Production streams; everything below reads this dict.
# 'team' is the DeliverableAssignment.team value (Design's own values).
# 'needs'/'status' are Deliverable column names used via getattr/setattr.
# Dict order is display order.
_STREAM_FIELDS = {
    '2d':        {'team': '2D',        'label': '2D',        'needs': 'needs_2d',        'status': 'status_2d'},
    '3d':        {'team': '3D',        'label': '3D',        'needs': 'needs_3d',        'status': 'status_3d'},
    'technical': {'team': 'Technical', 'label': 'Technical', 'needs': 'needs_technical', 'status': 'technical_status'},
}


def _get_actor():
    """Emulation-aware actor. Local name for core/shared's effective_user()."""
    return effective_user()


def _can_manage_preproduction(project, actor):
    """Who can assign/approve/flag in Pre-Production: admin, management, this
    project's Project Owner, or its CS Lead. Skip has its own gate
    (_can_skip_preproduction)."""
    return (
        can('manage_projects', actor)
        or actor.id == project.project_owner_id
        or actor.id == project.cs_lead_id
    )


def _can_skip_preproduction(project, actor):
    """Who can Skip to Pre-Production: admin, management, this project's CS
    Lead or Secondary CS, or its Project Owner. Duplicated in
    project_overlay/deliverables.py; keep the two in sync."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
    )


def _stream_done(deliverable):
    """True when a deliverable does not block the Handed to Production
    cascade: every needed stream is approved, or it needs none."""
    from app.modules.core.shared.lib.status_vocabulary import _post_approval_deliverable_status
    label, _ = _post_approval_deliverable_status(deliverable)
    return label == 'Handed to Production'


def _cascade_handed_to_production(project, actor, now):
    """Advances each C&CM channel to 'handed_to_production' once all its
    deliverables are done (read by the per-customer expand rows), then
    recomputes the project pill via sync_project_pipeline_status().
    Safe to call after every stream approval; no-ops until the last one."""
    from app.modules.core.shared.models import ProjectPosmChannel
    from app.modules.core.shared.services.status_tracking import sync_project_pipeline_status

    if project.brief_type == 'ccm':
        channels = ProjectPosmChannel.query.filter_by(project_id=project.id).all()
        for channel in channels:
            if channel.status == 'handed_to_production':
                continue
            if channel.posm_customer_id:
                channel_deliverables = Deliverable.query.filter_by(
                    project_id=project.id, project_customer_id=channel.posm_customer_id
                ).all()
            else:
                region_pc_ids = [
                    pc.id for pc in project.project_customers
                    if pc.customer.region == channel.posm_country and not pc.cancelled
                ]
                channel_deliverables = Deliverable.query.filter(
                    Deliverable.project_id == project.id,
                    Deliverable.project_customer_id.in_(region_pc_ids)
                ).all() if region_pc_ids else []

            if channel_deliverables and all(_stream_done(d) for d in channel_deliverables):
                channel.status = 'handed_to_production'

    sync_project_pipeline_status(project, actor)


def _cascade_client_approval(project, channel, actor, now):
    """The Client Approval "fully approved" cascade, duplicated from
    project_overlay/submissions.py's overlay_submissions_approve; keep in
    sync. channel is None for Standard, a ProjectPosmChannel for C&CM.
    The concept/KV gate only controls approved_at/approved_by_id; the
    project pill is always recomputed by sync_project_pipeline_status()."""
    from app.modules.core.shared.models import ProjectPosmChannel
    from app.modules.core.shared.services.status_tracking import sync_project_pipeline_status

    if channel is not None:
        if channel.posm_customer_id:
            channel_deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id=channel.posm_customer_id
            ).all()
        else:
            region_pc_ids = [
                pc.id for pc in project.project_customers
                if pc.customer.region == channel.posm_country and not pc.cancelled
            ]
            channel_deliverables = Deliverable.query.filter(
                Deliverable.project_id == project.id,
                Deliverable.project_customer_id.in_(region_pc_ids)
            ).all() if region_pc_ids else []

        if channel_deliverables and all(d.status == 'approved' for d in channel_deliverables):
            channel.status = 'approved'
            channel.approved_at = now
            channel.approved_by_id = actor.id

            all_channels = ProjectPosmChannel.query.filter_by(project_id=project.id).all()
            if all_channels and all(c.status == 'approved' for c in all_channels):
                ckv_gate = True
                if project.has_concept and project.concept_status != 'approved':
                    ckv_gate = False
                if project.has_kv and project.kv_status != 'approved':
                    ckv_gate = False
                if ckv_gate:
                    project.approved_at = now
                    project.approved_by_id = actor.id
    else:
        if project.project_deliverables and all(d.status == 'approved' for d in project.project_deliverables):
            project.approved_at = now
            project.approved_by_id = actor.id
            if project.concept_status:
                project.concept_status = 'approved'
            if project.kv_status:
                project.kv_status = 'approved'

    sync_project_pipeline_status(project, actor)


def _build_preproduction_row(d, actor, can_act):
    """One Pre-Production row: per-stream assignment/status/picker options,
    the CS note from Client Approval, and the flag count. Used by both
    Standard and C&CM.

    A stream is "flagged" when its status is None and it has any flag event:
    only flag_stream resets status to None, so that tells it apart from
    "never started". can_act (from _can_manage_preproduction) decides whether
    streams get assign_options (an interactive picker)."""
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
    from app.modules.core.shared.models import ProjectSubmissionEvent, ProjectSubmissionEventDeliverable, DeliverablePreproductionEvent, User

    flag_events = DeliverablePreproductionEvent.query.filter_by(
        deliverable_id=d.id, event_type='preprod_flag'
    ).order_by(DeliverablePreproductionEvent.created_at.desc()).all()
    flag_count = len(flag_events)
    flagged_streams = {e.stream for e in flag_events}
    # Newest first, so the first hit per stream is its latest flag comment.
    latest_flag_message = {}
    for e in flag_events:
        latest_flag_message.setdefault(e.stream, e.message)

    streams = []
    for stream_key, cfg in _STREAM_FIELDS.items():
        needed = getattr(d, cfg['needs'])
        if not needed:
            continue
        status_val = getattr(d, cfg['status'])
        is_flagged = status_val is None and stream_key in flagged_streams
        # Display only; it does not gate who can mark the stream done.
        assignment = next((a for a in d.disciplines if a.team == cfg['team']), None)
        can_mark_done = can('complete_preproduction', actor)
        stream_row = {
            'key': stream_key,
            'label': cfg['label'],
            'assignment': assignment,
            'status': status_val,  # None | 'uploaded' | 'approved'
            'is_flagged': is_flagged,
            'can_mark_done': can_mark_done,
            # Latest flag comment, only while flagged, so the card shows why.
            'flag_message': latest_flag_message.get(stream_key) if is_flagged else None,
        }
        # Picker options: designers/team leads on the stream's team, same
        # rule as _details_design_leads.html. Only queried when can_act.
        if can_act:
            stream_row['assign_options'] = active_users_query().filter(
                User.team.in_(assignable_teams_for(cfg['team'])),
                User.role.in_(['designer', 'team_lead'])
            ).order_by(User.name).all()
        streams.append(stream_row)

    # Latest CS note from the client_approval event, shown as context.
    batch_note_row = (
        ProjectSubmissionEvent.query
        .join(ProjectSubmissionEventDeliverable, ProjectSubmissionEventDeliverable.event_id == ProjectSubmissionEvent.id)
        .filter(
            ProjectSubmissionEventDeliverable.deliverable_id == d.id,
            ProjectSubmissionEvent.event_type == 'client_approval',
            ProjectSubmissionEvent.message.isnot(None),
        )
        .order_by(ProjectSubmissionEvent.created_at.desc())
        .first()
    )

    label, css_class = derive_deliverable_status(d)
    is_flagged = any(s['is_flagged'] for s in streams)

    return {
        'deliverable': d,
        'streams': streams,
        'batch_note': batch_note_row.message if batch_note_row else None,
        'flag_count': flag_count,
        'is_flagged': is_flagged,
        'status_label': label,
        'status_class': css_class,
        'is_complete': label == 'Handed to Production',
    }



def _in_preproduction_scope(d):
    """True when a deliverable is approved (or skipped) and needs at least
    one stream. Used by both brief-type branches."""
    return d.status == 'approved' and any(getattr(d, cfg['needs']) for cfg in _STREAM_FIELDS.values())


@project_preproduction_bp.route('/projects/<int:project_id>/overlay/preproduction')
@login_required
def overlay_preproduction(project_id):
    """Pre-Production page of the overlay: only deliverables in scope.
    Mirrors overlay_deliverables()'s C&CM/Standard branching."""
    from app.modules.projects.routes.project_overlay import _build_ccm_deliverable_sections

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    can_act = _can_manage_preproduction(project, actor)

    if project.brief_type == 'ccm':
        sections = _build_ccm_deliverable_sections(project)
        has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in sections)
        all_customers = [c for r in sections for c in r['customers']]
        first_customer_id = all_customers[0]['project_customer'].id if all_customers else None

        for c in all_customers:
            in_scope = [d for d in c['deliverables'] if _in_preproduction_scope(d)]
            c['rows'] = [_build_preproduction_row(d, actor, can_act) for d in in_scope]
            # Counts are per customer: each panel's header shows its own.
            c['total_count'] = len(c['rows'])
            c['completed_count'] = sum(1 for r in c['rows'] if r['is_complete'])

        return render_template(
            'project_overlay/_preproduction_ccm.html',
            project=project,
            regions=sections,
            all_customers=all_customers,
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            can_act=can_act,
        )

    deliverables = [
        d for d in Deliverable.query.filter_by(project_id=project_id, project_customer_id=None).order_by(Deliverable.id).all()
        if _in_preproduction_scope(d)
    ]
    rows = [_build_preproduction_row(d, actor, can_act) for d in deliverables]
    return render_template(
        'project_overlay/_preproduction_standard.html',
        project=project,
        rows=rows,
        can_act=can_act,
        total_count=len(rows),
        completed_count=sum(1 for r in rows if r['is_complete']),
    )


# ── Skip to Pre-Production ──────────────────────────────────────────────

def _apply_skip_to_preproduction(project, deliverables, actor):
    """Moves deliverables straight to Pre-Production, with the same effect as
    Client Approval. Used by skip_to_preproduction() and the create flow's
    Production Only finalize. Does not check permissions or commit.
    """
    from app.modules.core.shared.models import ProjectPosmChannel
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.lib.status_vocabulary import derive_preproduction_needs

    now = datetime.utcnow()
    for d in deliverables:
        if d.status != 'approved':
            record_deliverable_status(d, 'approved', actor)
        # Same needs derivation as overlay_submissions_approve.
        d.needs_2d, d.needs_3d, d.needs_technical = derive_preproduction_needs(d)

    # Standard: one cascade for the project. C&CM: one per channel touched.
    if project.brief_type == 'ccm':
        touched_channels = set()
        for d in deliverables:
            if not d.project_customer_id:
                continue
            customer = d.project_customer
            channel = ProjectPosmChannel.query.filter_by(
                project_id=project.id, posm_customer_id=d.project_customer_id
            ).first()
            if not channel and customer:
                channel = ProjectPosmChannel.query.filter_by(
                    project_id=project.id, posm_country=customer.customer.region, posm_customer_id=None
                ).first()
            if channel:
                touched_channels.add(channel.id)
        for channel_id in touched_channels:
            channel = ProjectPosmChannel.query.get(channel_id)
            _cascade_client_approval(project, channel, actor, now)
    else:
        _cascade_client_approval(project, None, actor, now)


@project_preproduction_bp.route('/projects/<int:project_id>/preproduction/skip', methods=['POST'])
@login_required
def skip_to_preproduction(project_id):
    """Skips the selected deliverables straight to Pre-Production, past
    Submissions/Client Approval. "All" is just the full ID list.

    Body (JSON): deliverable_ids (required, non-empty list).
    """
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectPosmChannel
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.lib.status_vocabulary import derive_preproduction_needs
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_skip_preproduction(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to skip to Pre-Production.'}), 403

    data = request.get_json() or {}
    deliverable_ids = data.get('deliverable_ids')
    if not deliverable_ids:
        return jsonify({'success': False, 'error': 'Select at least one deliverable to skip.'}), 400
    try:
        deliverable_id_set = {int(i) for i in deliverable_ids}
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid deliverable selection.'}), 400

    deliverables = Deliverable.query.filter(
        Deliverable.project_id == project.id,
        Deliverable.id.in_(deliverable_id_set)
    ).all()
    if not deliverables:
        return jsonify({'success': False, 'error': 'No matching deliverables found.'}), 400

    _apply_skip_to_preproduction(project, deliverables, actor)
    db.session.commit()

    log_activity('preprod_skipped',
                 f'{actor.name} skipped {len(deliverables)} deliverable(s) straight to Pre-Production on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})






# ── Stream lifecycle: mark done / approve / flag ────────────────────────

@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/mark-done', methods=['POST'])
@login_required
def mark_stream_done(deliverable_id):
    """Marks a stream 'uploaded' for review. Anyone with
    complete_preproduction can do it, for any stream; assignment and team
    do not matter. Only the stream column changes. Notifies the Project
    Owner."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_project_owner_of_stream_uploaded

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    actor = _get_actor()
    if deliverable.status != 'approved':
        return jsonify({'success': False, 'error': 'This deliverable is no longer in Pre-Production.'}), 400

    data = request.get_json() or {}
    stream = data.get('stream')
    if stream not in _STREAM_FIELDS:
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400
    if not can('complete_preproduction', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to mark this done.'}), 403

    setattr(deliverable, _STREAM_FIELDS[stream]['status'], 'uploaded')
    db.session.commit()

    log_activity('preprod_stream_marked_done',
                 f'{actor.name} marked {_STREAM_FIELDS[stream]["label"]} uploaded for "{deliverable.name}" on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    notify_project_owner_of_stream_uploaded(deliverable, project, _STREAM_FIELDS[stream]['label'], actor)

    return jsonify({'success': True})


@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/approve', methods=['POST'])
@login_required
def approve_stream(deliverable_id):
    """Approves a stream, then runs the Handed to Production cascade (the
    only place it fires from). Notifies the assigned designer, who sends
    the approved files to Production by hand."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import DeliverableAssignment
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_designer_of_stream_approved

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    actor = _get_actor()
    if deliverable.status != 'approved':
        return jsonify({'success': False, 'error': 'This deliverable is no longer in Pre-Production.'}), 400
    if not _can_manage_preproduction(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to approve this stream.'}), 403

    data = request.get_json() or {}
    stream = data.get('stream')
    if stream not in _STREAM_FIELDS:
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400

    setattr(deliverable, _STREAM_FIELDS[stream]['status'], 'approved')

    now = datetime.utcnow()
    _cascade_handed_to_production(project, actor, now)
    db.session.commit()

    log_activity('preprod_stream_approved',
                 f'{actor.name} approved {_STREAM_FIELDS[stream]["label"]} for "{deliverable.name}" on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    assignment = DeliverableAssignment.query.filter_by(
        deliverable_id=deliverable.id, team=_STREAM_FIELDS[stream]['team']
    ).first()
    notify_designer_of_stream_approved(
        deliverable, project, _STREAM_FIELDS[stream]['label'],
        assignment.designer if assignment else None, actor
    )

    return jsonify({'success': True})


@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/flag', methods=['POST'])
@login_required
def flag_stream(deliverable_id):
    """Sends a stream back for reupload: resets its status to None and logs
    a preprod_flag event with the required comment. _build_preproduction_row
    reads these events to tell "flagged" from "never started"."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import DeliverablePreproductionEvent
    from app.modules.core.shared.services.status_tracking import sync_project_pipeline_status
    from app.modules.core.shared.lib.utils import log_activity

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    actor = _get_actor()
    if deliverable.status != 'approved':
        return jsonify({'success': False, 'error': 'This deliverable is no longer in Pre-Production.'}), 400
    if not _can_manage_preproduction(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to flag this stream.'}), 403

    data = request.get_json() or {}
    stream = data.get('stream')
    message = (data.get('message') or '').strip()
    if stream not in _STREAM_FIELDS:
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400
    if not message:
        return jsonify({'success': False, 'error': 'A comment is required to flag for reupload.'}), 400

    setattr(deliverable, _STREAM_FIELDS[stream]['status'], None)

    # A flag can drop a Handed to Production project back to Pre-Production.
    # The deliverable stays 'approved'; only its derived label moves.
    sync_project_pipeline_status(project, actor)

    db.session.add(DeliverablePreproductionEvent(
        deliverable_id=deliverable.id, event_type='preprod_flag', stream=stream,
        author_id=actor.id, message=message,
    ))
    db.session.commit()

    log_activity('preprod_stream_flagged',
                 f'{actor.name} flagged {_STREAM_FIELDS[stream]["label"]} on "{deliverable.name}" for reupload on "{project.name}": {message[:100]}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


# ── Stream Assignment (all three streams) ──────────────────────────────
@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/assign', methods=['POST'])
@login_required
def assign_stream(deliverable_id):
    """Sets or clears the assignee for one stream on one deliverable. Gated
    by _can_manage_preproduction. designer_id null/omitted clears it; the
    picker UI has no clear option, so only a direct call does that."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import DeliverableAssignment
    from app.modules.core.shared.lib.utils import log_activity

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    actor = _get_actor()
    if not _can_manage_preproduction(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403

    data = request.get_json() or {}
    stream = data.get('stream')
    cfg = _STREAM_FIELDS.get(stream)
    if not cfg:
        return jsonify({'success': False, 'error': 'Unknown stream.'}), 400
    team = cfg['team']

    raw_designer_id = data.get('designer_id')
    designer_id = int(raw_designer_id) if raw_designer_id else None

    assignment = DeliverableAssignment.query.filter_by(
        deliverable_id=deliverable.id, team=team
    ).first()

    if designer_id is None:
        if assignment:
            db.session.delete(assignment)
    elif assignment:
        assignment.designer_id = designer_id
        assignment.assigned_by_id = actor.id
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=deliverable.id, team=team,
            designer_id=designer_id, assigned_by_id=actor.id,
        ))
    db.session.commit()

    log_activity('preprod_stream_assigned',
                 f'{actor.name} updated the {cfg["label"]} assignment for "{deliverable.name}" on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


# ── Flag/comment history ────────────────────────────────────────────────

@project_preproduction_bp.route('/projects/<int:project_id>/preproduction/events')
@login_required
def preproduction_events(project_id):
    """JSON list of the project's Pre-Production events, newest first, for
    the flag history view. Separate from the Submissions event log."""
    from app.modules.core.shared.models import DeliverablePreproductionEvent

    project = Project.query.get_or_404(project_id)
    deliverable_ids = [d.id for d in project.project_deliverables]
    events = (DeliverablePreproductionEvent.query
              .filter(DeliverablePreproductionEvent.deliverable_id.in_(deliverable_ids))
              .order_by(DeliverablePreproductionEvent.created_at.desc())
              .all()) if deliverable_ids else []

    return jsonify({'events': [
        {
            'id': e.id,
            'deliverable_id': e.deliverable_id,
            'deliverable_name': e.deliverable.name,
            'stream': e.stream,
            'message': e.message,
            'author_name': e.author.name,
            'created_at': e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]})


# ── NAS deep-link ──────────────────────────────────────────────────────

@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/nas-folder-link')
@login_required
def deliverable_nas_folder_link(deliverable_id):
    """Resolves a deliverable's Design Files folder to a Synology Drive link
    on click, since each folder needs a live NAS API call (see
    services/nas.py build_drive_folder_url()). Builds the C&CM region/customer
    path itself, so the frontend only sends the deliverable id."""
    from flask import current_app, jsonify
    from app.modules.core.shared.services.nas import build_drive_folder_url, REGION_DISPLAY

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    root = current_app.config.get('NAS_PROJECT_ROOT', '/Projects')
    client = project.client_brand.name if project.client_brand else 'Unknown Client'
    design_root = f'{root}/{project.created_at.year}/{client}/{project.name}/Design Files'

    if deliverable.project_customer_id:
        pc = deliverable.project_customer
        region_display = REGION_DISPLAY.get((pc.customer.region or '').lower(), (pc.customer.region or '').title())
        folder_path = f'{design_root}/{region_display}/{pc.customer.name}/{deliverable.name}'
    else:
        folder_path = f'{design_root}/{deliverable.name}'

    url = build_drive_folder_url(folder_path)
    if not url:
        return jsonify({'success': False, 'error': 'Could not reach the NAS.'}), 502
    return jsonify({'success': True, 'url': url})