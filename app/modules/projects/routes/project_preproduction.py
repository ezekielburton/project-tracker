"""
Project Pre-Production Route File.

Stream assignment (2D/3D/Technical — three fully independent streams, each
with its own assignee/status/flag cycle), mark-done/approve/flag on a
stream, Skip to Pre-Production, and the Handed to Production cascade.

Design:
- No separate "gate" between client approval and Pre-Production: a
  deliverable reaching status='approved' with any
  needs_2d/needs_3d/needs_technical set is already effectively in
  Pre-Production; DeliverableStatusLog already timestamps that moment (see
  record_deliverable_status, and the shared status-tracking helper
  deliverable_client_approved_at() for reading it back).
- status_2d/status_3d/technical_status each use a 3-state vocabulary: None
  (not started, or flagged and waiting on reupload) -> 'uploaded' (releaser
  marked their upload done) -> 'approved' (Project Owner signed off — the
  ONLY thing that advances a stream to done; _post_approval_deliverable_
  status reads this). A flag resets the stream back to None and logs why.
- 2D/3D/Technical are three fully independent streams. Design already
  treats them as three separate teams a deliverable can simultaneously
  need, each with its own assignee; Pre-Production matches that instead of
  collapsing 2D+3D into one "artwork" bucket. Each stream reuses the SAME
  DeliverableAssignment team value Design uses ('2D'/'3D'/'Technical'), so
  a designer already on a deliverable's stream during Design carries
  straight into it here, no separate row needed.
- Handed to Production (deliverable pill) is purely derived. The CASCADE:
  once every deliverable in a channel/project has every stream it needs
  approved, the channel/project itself advances to 'handed_to_production'
  automatically — no manual button, the same "only advance once EVERY
  deliverable in scope is done" rule Client Approval uses, one stage
  further down. The Project Owner's job is entirely upload-review-approve/
  flag per stream; the project/customer status update is a side effect.
- Skip to Pre-Production reuses the same cascade rule as real Client
  Approval — just a second way for deliverables to reach 'approved'.
"""

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app.modules.core.shared.lib.users import active_users_query
from datetime import datetime

from app.modules.core.shared.models import Project, Deliverable

project_preproduction_bp = Blueprint('project_preproduction', __name__, template_folder='../templates')

# Single source of truth for the three Pre-Production streams — every
# function below reads this instead of hardcoding technical/2d/3d
# branches, so adding/renaming a stream is a one-line change here.
# 'team' is the DeliverableAssignment.team value the stream's assignment
# is stored under — reuses Design's own '2D'/'3D'/'Technical' values
# directly (see module docstring), not a separate pseudo-team.
# 'needs'/'status' are the Deliverable column names read via getattr/
# setattr. Order here is display order everywhere this dict is iterated.
_STREAM_FIELDS = {
    '2d':        {'team': '2D',        'label': '2D',        'needs': 'needs_2d',        'status': 'status_2d'},
    '3d':        {'team': '3D',        'label': '3D',        'needs': 'needs_3d',        'status': 'status_3d'},
    'technical': {'team': 'Technical', 'label': 'Technical', 'needs': 'needs_technical', 'status': 'technical_status'},
}


def _get_actor():
    """Same emulation-aware actor lookup as project_overlay.py — kept as
    its own copy here rather than a cross-file import, matching this
    codebase's existing one-helper-per-route-file convention."""
    from app.modules.core.shared.models import User
    from flask import session
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_preproduction(project, actor):
    """Who can approve/flag in Pre-Production: admin, management, this
    project's Project Owner, or its CS Lead. Skip to Pre-Production has
    its own, separately-scoped gate — see _can_skip_preproduction."""
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.project_owner_id
        or actor.id == project.cs_lead_id
    )


def _can_skip_preproduction(project, actor):
    """Who can use Skip to Pre-Production — CS Lead, Secondary CS,
    Management, Admin, or the assigned Project Owner (not any cs-role user —
    only someone with a relationship to this specific project).
    Duplicated in project_overlay.py (not cross-imported), matching this
    codebase's existing one-helper-per-route-file convention — keep the
    two in sync if this ever changes."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )


def _stream_done(deliverable):
    """True once a deliverable is no longer blocking the "handed to
    production" cascade below — either every stream it needed is approved,
    or it never needed any Pre-Production stream in the first place.
    Either way _post_approval_deliverable_status() reports that as
    'Handed to Production' — a no-needs deliverable has had nothing to
    hand off, so a single equality check is enough here."""
    from app.modules.core.shared.lib.status_vocabulary import _post_approval_deliverable_status
    label, _ = _post_approval_deliverable_status(deliverable)
    return label == 'Handed to Production'


def _cascade_handed_to_production(project, actor, now):
    """Once every deliverable in a channel/project now has every stream it
    needs approved, advances the channel/project itself to
    'handed_to_production' — automatically, no manual confirmation step
    (minimizing admin work is the point). C&CM: per-channel
    first (same UAE/Gulf-region matching the Client Approval cascade
    uses) — that per-channel status is real, independent state (still
    read by C&CM's per-customer expand rows), kept exactly as before. The
    project-level pill itself is no longer decided here directly — it's a
    live roll-up computed by
    sync_project_pipeline_status() from every deliverable's own status,
    called unconditionally at the end for both brief types. Safe to call
    after every single stream approval — it just no-ops until the last
    one lands."""
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
    """The same "reached fully approved" cascade Client Approval already
    uses (app/routes/project_overlay.py's overlay_submissions_approve) —
    duplicated here rather than imported/refactored out, to avoid touching
    that already-verified, live route while wiring up a second entry
    point (Skip to Pre-Production) into the same completion rule. channel
    is None for Standard; a resolved ProjectPosmChannel for C&CM POSM.
    The project-level pill itself is no longer set directly here —
    sync_project_pipeline_status()
    recomputes it as a live roll-up from every deliverable, called
    unconditionally at the end, independent of the ckv_gate below (that
    gate still controls only the official approved_at/approved_by_id
    business-approval timestamp and the concept/kv sync, not the pill)."""
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
    """Per-deliverable data the Pre-Production tab needs: per-stream
    assignment/status/candidate-picker options, the CS batch note from
    Client Approval, and the flag-history count. Shared by Standard + C&CM
    so the two branches in overlay_preproduction() can't drift on this.

    is_flagged (per stream and rolled up per row) is True when a stream's
    status is currently None AND it has at least one logged flag event —
    that's what distinguishes "flagged, waiting on the designer to
    reupload" from "never started yet," since both look identical as a
    bare None status. Existence alone is enough: status only ever resets
    to None via flag_stream (or the column's initial default), so if any
    flag event has ever been logged for a stream that's currently None,
    the flag is why it's None.

    can_act — same value the caller already computed via
    _can_manage_preproduction(). Decides whether each stream gets an
    interactive assignment picker vs. a read-only chip (see assign_options
    below — every stream gets one, not just Technical). Every other field
    here is unaffected by who's viewing."""
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
    from app.modules.core.shared.models import ProjectSubmissionEvent, ProjectSubmissionEventDeliverable, DeliverablePreproductionEvent, User

    flag_events = DeliverablePreproductionEvent.query.filter_by(
        deliverable_id=d.id, event_type='preprod_flag'
    ).order_by(DeliverablePreproductionEvent.created_at.desc()).all()
    flag_count = len(flag_events)
    flagged_streams = {e.stream for e in flag_events}
    # Newest-first, so the first hit per stream is that stream's most recent
    # flag comment — the flag message is what the stream card below renders.
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
        # Read-only context — whoever Design put on this team, shown for
        # info only. Does not gate who can act — any designer can pick up
        # any stream and mark it done (see mark_stream_done).
        assignment = next((a for a in d.disciplines if a.team == cfg['team']), None)
        can_mark_done = actor.role in ('designer', 'team_lead', 'admin', 'management')
        stream_row = {
            'key': stream_key,
            'label': cfg['label'],
            'assignment': assignment,
            'status': status_val,  # None | 'uploaded' | 'approved'
            'is_flagged': is_flagged,
            'can_mark_done': can_mark_done,
            # The comment left on this stream's most recent flag — only set
            # when is_flagged, so the card can show why it's back in
            # progress.
            'flag_message': latest_flag_message.get(stream_key) if is_flagged else None,
        }
        # Assignment picker, folded into every stream's own box. If a
        # deliverable is unassigned it can be assigned here via the picker,
        # scoped to the relevant team that div owns. Used to be
        # Technical-only, with 2D/3D showing a row-level read-only "Designer"
        # chip instead (whoever Design assigned was assumed to release the
        # artwork too) — now every stream gets the same interactive picker,
        # scoped to its own team, folded directly into its box. Options
        # mirror _details_design_leads.html's own per-team picker (User.team
        # == the stream's team, designer/team_lead only) — same precedent,
        # just scoped to one deliverable instead of one project. Only
        # queried when can_act — no point building an options list nobody
        # can use.
        if can_act:
            stream_row['assign_options'] = active_users_query().filter(
                User.team == cfg['team'],
                User.role.in_(['designer', 'team_lead'])
            ).order_by(User.name).all()
        streams.append(stream_row)

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
    """A deliverable has genuinely crossed into Pre-Production once it's
    client-approved (or skipped there) AND at least one stream is flagged
    as needed. Same filter both brief-type branches below use, so the tab
    can't disagree with itself about what counts as "in scope"."""
    return d.status == 'approved' and any(getattr(d, cfg['needs']) for cfg in _STREAM_FIELDS.values())


@project_preproduction_bp.route('/projects/<int:project_id>/overlay/preproduction')
@login_required
def overlay_preproduction(project_id):
    """Design > Pre-Production sub-tab. A filtered work-surface, not the
    roster — only deliverables that have actually crossed in are shown
    (the "roster vs. work-surface" split). Mirrors
    overlay_deliverables()'s exact branching/scope-select shape so the two
    tabs stay visually and structurally consistent."""
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
            # Per-customer, not project-wide — the header count lives inside
            # each panel, toggling with the rows via the same is-hidden
            # mechanism instead of showing one project-wide total that never
            # matched whichever customer was selected.
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
    """Core mutation shared by skip_to_preproduction() (manual, per-
    deliverable-selection) and the create flow's Production Only finalize
    (project_overlay's overlay_create_finalize()) — moves
    every given deliverable straight to Pre-Production, bypassing
    Submissions/Client Approval, functionally identical to a real Client
    Approval. Kept as one helper so the two call sites can't drift on this
    logic. Caller handles permission checks, request parsing, and the
    commit/response — this only mutates and cascades, doesn't commit.
    """
    from app.modules.core.shared.models import ProjectPosmChannel
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.lib.status_vocabulary import derive_preproduction_needs

    now = datetime.utcnow()
    for d in deliverables:
        if d.status != 'approved':
            record_deliverable_status(d, 'approved', actor)
        # Same auto-derivation real Client Approval uses (project_overlay.
        # py's overlay_submissions_approve) — skip is just a second way to
        # reach 'approved', not a different rule for what a deliverable needs.
        d.needs_2d, d.needs_3d, d.needs_technical = derive_preproduction_needs(d)

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

    needs_2d/needs_3d/needs_technical are auto-derived from whichever
    teams are already on the deliverable (status_vocabulary.derive_
    preproduction_needs) — same rule real Client Approval uses, so a
    skipped deliverable ends up in exactly the same state one that went
    through the normal flow would.
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
    """Any designer/team lead (or admin/management) marks a stream's
    upload ready for review — no assignment step; any designer can
    upload/mark something as done. Not
    scoped to the stream's own team either — fully open by design.
    deliverable.status is untouched (stays 'approved' from Client
    Approval/Skip) — only the stream-specific column advances, so each
    stream can be done while the others are still in progress.

    Notifies the Project Owner — this is the
    ONLY event that puts a stream in front of them for Approve/Flag for
    Reupload, so it's the one Pre-Production action that fires a
    notification at all; assign/approve/flag stay silent (see
    notify_project_owner_of_stream_uploaded's docstring)."""
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
    if actor.role not in ('designer', 'team_lead', 'admin', 'management'):
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
    """Project Owner (or admin/management) signs off a stream — the only
    thing that advances a stream's status to 'approved', which is what
    _post_approval_deliverable_status() reads to show Handed to
    Production. Checks the channel/project cascade afterward — this is
    the ONLY place that cascade fires from; there is no separate manual
    "Handed to Production" action anywhere.

    Notifies the assigned designer — until Production has its own access
    to file storage/the app, sharing the approved files with them is a
    manual, designer-side
    email step, so the designer needs to know the moment it's approved
    (see notify_designer_of_stream_approved's docstring)."""
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
    """Bounces a stream back for reupload (see _can_manage_preproduction
    for who).Resets that stream's status to None (back in progress) and logs a preprod_flag
    event with the required comment — this is the row later KPI queries
    (average revision rounds, per project/deliverable/owner/month/
    quarter) will count and filter on, and it's also what
    _build_preproduction_row reads to tell "flagged, waiting on the
    designer" apart from "never started" for the Needs Attention section."""
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

    # Flagging a stream can revert a project that had reached Handed to
    # Production back down to Pre-Production (the deliverable's raw status
    # stays 'approved' — flagging never sends it all the way back to In
    # Design, only its post-approval label moves). This fixes a gap where
    # flag_stream never called any cascade. The client-approval timestamp
    # itself isn't touched either way (see the shared status-tracking helper
    # deliverable_client_approved_at()).
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
# Used to be Technical-only, with 2D/3D showing a row-level read-only
# "Designer" chip instead (whoever Design already assigned was assumed to
# release the artwork too). Now every stream gets the same interactive
# picker, folded into its own box and scoped to its own team (see
# _build_preproduction_row's assign_options / _preproduction_row.html) —
# same shape as mark_stream_done/approve_stream/flag_stream above, which
# already take `stream` in the POST body rather than being one route per
# stream.
@project_preproduction_bp.route('/deliverables/<int:deliverable_id>/preproduction/assign', methods=['POST'])
@login_required
def assign_stream(deliverable_id):
    """Sets (or clears) who's doing one stream on one deliverable. Same
    permission gate as Approve/Flag (_can_manage_preproduction) — the
    picker itself is only ever rendered for someone who passes that check
    (see _build_preproduction_row/_preproduction_row.html), but the route
    re-checks server-side rather than trusting the client got here honestly.
    designer_id=null (or omitted) clears the assignment back to Unassigned —
    the avatar-picker popover doesn't offer an explicit "Unassigned" option
    today, so this is reachable only by a future clear-affordance or a
    direct API call for now; wired up regardless since "un-assign" is the
    obvious complement to "assign" and costs nothing extra here."""
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
    """Flat JSON list of every preprod_flag event across the project's
    deliverables, newest first — the data behind the "All" + per-
    deliverable dropdown history view. Its own endpoint/table per
    Ezekiel: doesn't touch or return anything from Submissions' event log."""
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
    """Resolves a deliverable's Design Files subfolder to a Synology Drive
    deep-link, click-triggered rather than baked in at render time (Drive
    needs a live API resolve per folder — see app/nas.py's
    build_drive_folder_url()). Derives the C&CM region/customer path itself
    from the deliverable's own project_customer, same as the old
    nas_deliverable_url() Jinja global this replaces, so the frontend
    doesn't need to pass anything beyond the deliverable id."""
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