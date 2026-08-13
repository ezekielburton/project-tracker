"""
Project Pre-Production Route File.

New blueprint — own file per the standing rule that any brand-new feature
gets its own JS/route file. Write-side backend only, built 13 Aug 2026
ahead of the Figma-gated Pre-Production tab: stream assignment (technical/
artwork), mark-done/approve/flag on a stream, Skip to Pre-Production, and
the Handed to Production cascade. The actual tab UI + its render/fetch
routes are NOT part of this pass — Ezekiel builds those once the wireframe
is ready, calling into these routes.

Design recap (locked with Ezekiel 13 Aug 2026):
- No new "gate" between Client Approved and Pre-Production — a deliverable
  reaching status='approved' with needs_technical/needs_artwork set is
  already effectively in Pre-Production; DeliverableStatusLog already
  timestamps that moment for free (see record_deliverable_status).
- technical_status/artwork_status get a 3-state vocabulary: None (not
  started) -> 'uploaded' (releaser marked their upload done) ->
  'approved' (Project Owner signed off — the ONLY thing that advances a
  stream to done; _post_approval_deliverable_status already reads this).
  A flag resets the stream back to None and logs why.
- Handed to Production (deliverable pill) is purely derived, already
  built. What's NEW here is the CASCADE: once every deliverable in a
  channel/project has both required streams approved, the channel/
  project itself advances to 'handed_to_production' — same "only advance
  once EVERY deliverable in scope is done" rule Client Approval already
  uses, one stage further down.
- Skip to Pre-Production reuses the exact same cascade rule as real
  Client Approval — it's just a second way for deliverables to reach
  'approved', not a different completion rule. Selecting every deliverable
  in scope naturally completes the cascade; a partial selection naturally
  doesn't, so the project stays In Design. No separate "whole project"
  code path needed.
"""

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from datetime import datetime

from app.models import Project, Deliverable

project_preproduction_bp = Blueprint('project_preproduction', __name__)

# Wire-format stream key ('technical'/'artwork', used in routes/JSON) ->
# the actual DeliverableAssignment.team value it's stored under. Technical
# reuses the SAME 'Technical' team already used by TEAM_KEYS (project_list.
# py) — real design-phase work never uses that team (technical files only
# exist from Pre-Production on, per the architecture doc), so there's no
# collision, and it means a Technical person already on the deliverable
# for any reason carries straight over rather than needing a second row.
# 'Artwork' isn't an existing team (2D/3D cover that during Design), so
# it's a genuinely new value, kept lowercase to match the wire format.
_TEAM_FOR_STREAM = {'technical': 'Technical', 'artwork': 'artwork'}


def _get_actor():
    """Same emulation-aware actor lookup as project_overlay.py — kept as
    its own copy here rather than a cross-file import, matching this
    codebase's existing one-helper-per-route-file convention."""
    from app.models import User
    from flask import session
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_preproduction(project, actor):
    """Who can assign/approve/flag/skip in Pre-Production: admin,
    management, this project's Project Owner, or its CS Lead (CS still
    needs to be able to Skip to Pre-Production per Ezekiel's spec, even
    though day-to-day review is the Owner's job)."""
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.project_owner_id
        or actor.id == project.cs_lead_id
    )


def _stream_done(deliverable):
    """True once a deliverable's required streams are all signed off —
    mirrors _post_approval_deliverable_status()'s own "done" check exactly
    (imported, not re-derived) so the cascade below can never disagree
    with what the pill is showing."""
    from app.status_vocabulary import _post_approval_deliverable_status
    label, _ = _post_approval_deliverable_status(deliverable)
    return label == 'Handed to Production'


def _cascade_handed_to_production(project, actor, now):
    """Once every deliverable in a channel/project now has both required
    streams approved, advances the channel/project itself to
    'handed_to_production'. Standard: checks project.project_deliverables
    directly. C&CM: per-channel first (same UAE/Gulf-region matching the
    Client Approval cascade uses), then the whole project once every
    channel has reached it. Safe to call after every single stream
    approval — it just no-ops until the last one lands."""
    from app.models import ProjectPosmChannel
    from app.status_tracking import record_project_status

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

        all_channels = ProjectPosmChannel.query.filter_by(project_id=project.id).all()
        if all_channels and all(c.status == 'handed_to_production' for c in all_channels):
            record_project_status(project, 'handed_to_production', actor)
    else:
        deliverables = project.project_deliverables
        if deliverables and all(_stream_done(d) for d in deliverables):
            record_project_status(project, 'handed_to_production', actor)


def _cascade_client_approval(project, channel, actor, now):
    """The same "reached fully approved" cascade Client Approval already
    uses (app/routes/project_overlay.py's overlay_submissions_approve) —
    duplicated here rather than imported/refactored out, to avoid touching
    that already-verified, live route while wiring up a second entry
    point (Skip to Pre-Production) into the same completion rule. channel
    is None for Standard; a resolved ProjectPosmChannel for C&CM POSM."""
    from app.models import ProjectPosmChannel
    from app.status_tracking import record_project_status

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
                    record_project_status(project, 'approved', actor)
                    project.approved_at = now
                    project.approved_by_id = actor.id
    else:
        if project.project_deliverables and all(d.status == 'approved' for d in project.project_deliverables):
            record_project_status(project, 'approved', actor)
            project.approved_at = now
            project.approved_by_id = actor.id
            if project.concept_status:
                project.concept_status = 'approved'
            if project.kv_status:
                project.kv_status = 'approved'


def _build_preproduction_row(d, actor):
    """Per-deliverable data the Pre-Production tab needs: per-stream
    assignment/status/candidate-picker options, the 2D/3D assignments
    carried over from Design (read-only here — nothing to do, they just
    already exist), the CS batch note from Client Approval, and the
    flag-history count. Shared by Standard + C&CM so the two branches in
    overlay_preproduction() can't drift on this."""
    from app.status_vocabulary import derive_deliverable_status
    from app.models import ProjectSubmissionEvent, ProjectSubmissionEventDeliverable, DeliverablePreproductionEvent

    streams = []
    for stream_key, needed, status_val in (
        ('technical', d.needs_technical, d.technical_status),
        ('artwork', d.needs_artwork, d.artwork_status),
    ):
        if not needed:
            continue
        assignment = next((a for a in d.disciplines if a.team == _TEAM_FOR_STREAM[stream_key]), None)
        streams.append({
            'key': stream_key,
            'label': 'Technical' if stream_key == 'technical' else 'Artwork',
            'assignment': assignment,
            'status': status_val,  # None | 'uploaded' | 'approved'
            'options': _assignable_users_for_stream(stream_key),
            'can_mark_done': bool(assignment and assignment.designer_id == actor.id),
        })

    design_assignments = [a for a in d.disciplines if a.team in ('2D', '3D')]

    # Most recent CS note left when this deliverable was approved into
    # Pre-Production (Client Approval's client_approval event) — collapsed
    # context from a prior step, nothing actionable here.
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

    flag_count = DeliverablePreproductionEvent.query.filter_by(
        deliverable_id=d.id, event_type='preprod_flag'
    ).count()

    label, css_class = derive_deliverable_status(d)

    return {
        'deliverable': d,
        'streams': streams,
        'design_assignments': design_assignments,
        'batch_note': batch_note_row.message if batch_note_row else None,
        'flag_count': flag_count,
        'status_label': label,
        'status_class': css_class,
        'is_complete': label == 'Handed to Production',
    }


def _assignable_users_for_stream(stream_key):
    """Candidate pool for a stream's assign picker — Technical team for
    the technical stream, 2D/3D for artwork, with 3D deliberately included
    on BOTH per Ezekiel's flexibility call (3D sometimes releases artwork,
    sometimes technical). The assign route itself doesn't hard-enforce
    this — any actor with permission can assign anyone — this only shapes
    which names the picker offers."""
    from app.models import User
    teams = ['Technical', '3D'] if stream_key == 'technical' else ['2D', '3D']
    return User.query.filter(
        User.team.in_(teams), User.role.in_(['designer', 'team_lead'])
    ).order_by(User.name).all()


def _in_preproduction_scope(d):
    """A deliverable has genuinely crossed into Pre-Production once it's
    client-approved (or skipped there) AND at least one stream is flagged
    as needed. Same filter both brief-type branches below use, so the tab
    can't disagree with itself about what counts as "in scope"."""
    return d.status == 'approved' and (d.needs_technical or d.needs_artwork)


@project_preproduction_bp.route('/projects/<int:project_id>/overlay/preproduction')
@login_required
def overlay_preproduction(project_id):
    """Design > Pre-Production sub-tab. A filtered work-surface, not the
    roster — only deliverables that have actually crossed in are shown
    (architecture doc §5's "roster vs. work-surface" split). Mirrors
    overlay_deliverables()'s exact branching/scope-select shape so the two
    tabs stay visually and structurally consistent."""
    from app.routes.project_overlay import _build_ccm_deliverable_sections

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
            c['rows'] = [_build_preproduction_row(d, actor) for d in in_scope]

        total = sum(len(c['rows']) for c in all_customers)
        completed = sum(1 for c in all_customers for r in c['rows'] if r['is_complete'])

        return render_template(
            'project_overlay/_preproduction_ccm.html',
            project=project,
            regions=sections,
            all_customers=all_customers,
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            can_act=can_act,
            total_count=total,
            completed_count=completed,
        )

    deliverables = [
        d for d in Deliverable.query.filter_by(project_id=project_id, project_customer_id=None).order_by(Deliverable.id).all()
        if _in_preproduction_scope(d)
    ]
    rows = [_build_preproduction_row(d, actor) for d in deliverables]
    return render_template(
        'project_overlay/_preproduction_standard.html',
        project=project,
        rows=rows,
        can_act=can_act,
        total_count=len(rows),
        completed_count=sum(1 for r in rows if r['is_complete']),
    )


# ── Skip to Pre-Production ──────────────────────────────────────────────

@project_preproduction_bp.route('/projects/<int:project_id>/preproduction/skip', methods=['POST'])
@login_required
def skip_to_preproduction(project_id):
    """Fast-forwards selected deliverables straight to Pre-Production —
    no Submissions/Client Approval involved. Select specific deliverables,
    or every one of them (the frontend just sends the full ID list for
    "All" — no separate whole-project code path needed here, the existing
    cascade rule naturally completes the project once every deliverable is
    covered, same as it does for real client approval).

    Body (JSON): deliverable_ids (required, non-empty list).

    needs_technical / needs_artwork are auto-derived from whichever teams
    are already on the deliverable (status_vocabulary.derive_
    preproduction_needs) — same rule real Client Approval uses, so a
    skipped deliverable ends up in exactly the same state one that went
    through the normal flow would.
    """
    from app import db
    from app.models import ProjectPosmChannel
    from app.status_tracking import record_deliverable_status
    from app.status_vocabulary import derive_preproduction_needs

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_preproduction(project, actor) and actor.role != 'cs':
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

    now = datetime.utcnow()
    for d in deliverables:
        if d.status != 'approved':
            record_deliverable_status(d, 'approved', actor)
        # Same auto-derivation real Client Approval uses (project_overlay.
        # py's overlay_submissions_approve) — skip is just a second way to
        # reach 'approved', not a different rule for what a deliverable needs.
        d.needs_technical, d.needs_artwork = derive_preproduction_needs(d)

    # Cascade — same rule as real Client Approval, just entered a
    # different way. Standard: one check against the whole project.
    # C&CM: one check per distinct channel touched by this batch.
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

    db.session.commit()
    return jsonify({'success': True})


# ── Stream assignment (technical / artwork) ─────────────────────────────

@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/assign', methods=['POST'])
@login_required
def assign_stream(deliverable_id):
    """Assign or reassign ("transfer ownership") a technical/artwork
    release stream. Reuses DeliverableAssignment — the same table the
    Design-phase roster's team-tag assign already writes to — stream just
    becomes two more team values ('technical'/'artwork') alongside the
    existing '2D'/'3D' rows. Those 2D/3D rows are untouched, so they carry
    over into Pre-Production automatically, with nothing to migrate.

    Body (JSON): stream ('technical'|'artwork'), designer_id.

    Permission: admin/management always; otherwise self-assign only, or
    the CURRENT holder of that stream transferring it to someone else
    (the "transfer ownership" case).
    """
    from app import db
    from app.models import DeliverableAssignment, User

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    actor = _get_actor()

    data = request.get_json() or {}
    stream = data.get('stream')
    designer_id = data.get('designer_id')
    if stream not in ('technical', 'artwork'):
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400
    if not designer_id:
        return jsonify({'success': False, 'error': 'Select someone to assign.'}), 400
    designer_id = int(designer_id)
    designer = User.query.get_or_404(designer_id)

    existing = DeliverableAssignment.query.filter_by(deliverable_id=deliverable.id, team=_TEAM_FOR_STREAM[stream]).first()

    is_self_assign = actor.id == designer_id
    is_transfer = existing and existing.designer_id == actor.id
    if not (actor.role in ('admin', 'management') or is_self_assign or is_transfer):
        return jsonify({'success': False, 'error': 'You do not have permission to assign this stream.'}), 403

    if existing:
        existing.designer_id = designer.id
        existing.assigned_by_id = actor.id
        existing.assigned_at = datetime.utcnow()
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=deliverable.id, designer_id=designer.id,
            team=_TEAM_FOR_STREAM[stream], assigned_by_id=actor.id,
        ))
    db.session.commit()
    return jsonify({'success': True, 'designer_name': designer.name})


# ── Stream lifecycle: mark done / approve / flag ────────────────────────

@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/mark-done', methods=['POST'])
@login_required
def mark_stream_done(deliverable_id):
    """The assigned releaser marks their upload ready for review.
    deliverable.status is untouched (stays 'approved' from Client
    Approval/Skip) — only the stream-specific column advances, so one
    stream can be done while the other is still in progress."""
    from app import db

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    actor = _get_actor()

    data = request.get_json() or {}
    stream = data.get('stream')
    if stream not in ('technical', 'artwork'):
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400

    from app.models import DeliverableAssignment
    assignment = DeliverableAssignment.query.filter_by(deliverable_id=deliverable.id, team=_TEAM_FOR_STREAM[stream]).first()
    if not (actor.role in ('admin', 'management') or (assignment and assignment.designer_id == actor.id)):
        return jsonify({'success': False, 'error': 'You are not assigned to this stream.'}), 403

    if stream == 'technical':
        deliverable.technical_status = 'uploaded'
    else:
        deliverable.artwork_status = 'uploaded'
    db.session.commit()
    return jsonify({'success': True})


@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/approve', methods=['POST'])
@login_required
def approve_stream(deliverable_id):
    """Project Owner (or admin/management) signs off a stream — the only
    thing that advances technical_status/artwork_status to 'approved',
    which is what _post_approval_deliverable_status() reads to show
    Handed to Production. Checks the channel/project cascade afterward."""
    from app import db

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    actor = _get_actor()
    if not _can_manage_preproduction(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to approve this stream.'}), 403

    data = request.get_json() or {}
    stream = data.get('stream')
    if stream not in ('technical', 'artwork'):
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400

    if stream == 'technical':
        deliverable.technical_status = 'approved'
    else:
        deliverable.artwork_status = 'approved'

    now = datetime.utcnow()
    _cascade_handed_to_production(project, actor, now)
    db.session.commit()
    return jsonify({'success': True})


@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/flag', methods=['POST'])
@login_required
def flag_stream(deliverable_id):
    """Project Owner bounces a stream back for reupload. Resets that
    stream's status to None (back in progress) and logs a preprod_flag
    event with the required comment — this is the row later KPI queries
    (average revision rounds, per project/deliverable/owner/month/
    quarter) will count and filter on."""
    from app import db
    from app.models import DeliverablePreproductionEvent

    deliverable = Deliverable.query.get_or_404(deliverable_id)
    project = deliverable.project
    actor = _get_actor()
    if not _can_manage_preproduction(project, actor):
        return jsonify({'success': False, 'error': 'You do not have permission to flag this stream.'}), 403

    data = request.get_json() or {}
    stream = data.get('stream')
    message = (data.get('message') or '').strip()
    if stream not in ('technical', 'artwork'):
        return jsonify({'success': False, 'error': 'Invalid stream.'}), 400
    if not message:
        return jsonify({'success': False, 'error': 'A comment is required to flag for reupload.'}), 400

    if stream == 'technical':
        deliverable.technical_status = None
    else:
        deliverable.artwork_status = None

    db.session.add(DeliverablePreproductionEvent(
        deliverable_id=deliverable.id, event_type='preprod_flag', stream=stream,
        author_id=actor.id, message=message,
    ))
    db.session.commit()
    return jsonify({'success': True})


# ── Flag/comment history ────────────────────────────────────────────────

@project_preproduction_bp.route('/projects/<int:project_id>/preproduction/events')
@login_required
def preproduction_events(project_id):
    """Flat JSON list of every preprod_flag event across the project's
    deliverables, newest first — the data behind the "All" + per-
    deliverable dropdown history view (UI not built yet). Its own
    endpoint/table per Ezekiel: doesn't touch or return anything from
    Submissions' event log."""
    from app.models import DeliverablePreproductionEvent

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
