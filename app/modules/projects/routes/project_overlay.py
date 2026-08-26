"""
Project Details Overlay Route File.
New blueprint for file hygiene, easier to work on chunks rather than one long file.
"""

from flask import Blueprint, render_template, abort, request, jsonify
from flask_login import login_required, current_user

from app.modules.core.shared.models import Project
from app.modules.core.shared.lib.decorators import role_required

project_overlay_bp = Blueprint('project_overlay', __name__, template_folder='../templates')

def _get_actor():
    """Emulation-aware actor lookup — an admin viewing-as another user acts
    (and gets logged) as that user; everyone else acts as themselves. Every
    overlay route uses this, not just overlay() itself."""
    from app.modules.core.shared.models import User
    from flask import session
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_deliverables(project, actor):
    """Same rule as Reference Files management — admin/management (any
    project), this project's CS Lead, this project's Secondary CS, or the
    specific assigned Project Owner. Kept as its own function even though
    it's identical to can_manage_reference_files today, same reasoning as
    can_edit_project — they may diverge later.

    Also allow the draft's own creator, but ONLY while it's still a draft.
    This covers a CS building a project on behalf of a different CS Lead:
    cs_lead_id is already set to that other person, so none of the checks
    above cover "I'm the one actually building this". Once finalized,
    deliverables management goes back to being purely CS Lead/Secondary
    CS/Project Owner/admin's call, same as everything else on a live
    project. Mirrors _can_finalize_create()'s reachability rule above,
    just scoped to this one action instead of the whole create shell.
    """
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
        or (project.project_status == 'draft' and actor.id == project.created_by_id)
    )


def ensure_posm_channels(project, brief_sections):
    """Self-healing: creates any ProjectPosmChannel rows a C&CM project's
    current customer roster needs but doesn't have yet — one channel per
    UAE *and* Gulf customer (never per-region-only anymore). The one
    deliberate exception: Oman's handful of pre-migration legacy
    region-level channels (posm_customer_id IS NULL) are frozen read-only
    history from the Gulf-per-customer migration — this function
    must never delete or touch those, only ever add genuinely new
    per-customer channels alongside them.
    Commits if it adds anything. Returns True if it added any channels.

    Relocated from the old detail page — this was the old detail
    page's own helper, but the overlay's Submissions tab (overlay_submissions
    below) was already the only live caller by the time of the move.
    """
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectPosmChannel

    GULF_REGION_KEYS = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman']

    # UAE-only orphan cleanup: a deleted-then-recreated ProjectCustomer leaves
    # its old UAE channel with posm_customer_id=NULL (ON DELETE SET NULL) —
    # delete it so it gets recreated below with the new ProjectCustomer ID.
    # Deliberately scoped to UAE only — a NULL-customer_id Gulf channel is
    # Oman's frozen legacy history, not an orphan.
    orphaned = [ch for ch in project.posm_channels
                if ch.posm_country == 'uae' and ch.posm_customer_id is None]
    if orphaned:
        for ch in orphaned:
            db.session.delete(ch)
        db.session.flush()

    existing_channel_keys = {
        (ch.posm_country, ch.posm_customer_id) for ch in project.posm_channels
    }

    new_channels_added = False
    for region_key in GULF_REGION_KEYS:
        if region_key not in brief_sections:
            continue
        for pc in brief_sections[region_key]:
            if pc.cancelled:
                continue
            if (region_key, pc.id) not in existing_channel_keys:
                db.session.add(ProjectPosmChannel(
                    project_id=project.id,
                    posm_country=region_key,
                    posm_customer_id=pc.id,
                    status='in_queue',
                ))
                new_channels_added = True

    if new_channels_added:
        db.session.commit()
    return new_channels_added


def _can_cancel_project(project, actor):
    """Cancel/Reactivate — CS Lead, Secondary CS, assigned Project Owner,
    Management, Admin. Same shape as
    _can_manage_deliverables — identical today, kept separate since Cancel
    is a bigger action and the two may diverge later."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )


def _can_toggle_hold(project, actor):
    """Straight port of the permission check already live in
    projects_detail.py's toggle_hold — admin, this project's CS Lead, or
    Secondary CS. Deliberately NOT extended to Management or Project Owner
    like _can_cancel_project was — On Hold is a port of a working feature,
    not a new design, so it keeps exactly the gate the existing route has
    rather than "fixing" it unasked. Worth revisiting if that was actually
    an oversight in the original."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role == 'admin'
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
    )

def _can_skip_preproduction(project, actor):
    """Who can use Skip to Pre-Production — CS Lead, Secondary CS,
    Management, Admin, or the assigned Project Owner (not any cs-role user —
    only someone with a relationship to this specific project). Same
    shape as _can_cancel_project. Kept as its own function rather than
    widening _can_manage_preproduction over in project_preproduction.py —
    Mark Done/Approve/Flag keep their existing, narrower gate. Duplicated
    there too (not cross-imported) matching this codebase's existing
    one-helper-per-route-file convention."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )


def _can_create_project(actor):
    """Who can start a new project — admin/cs/management (same as the old
    /projects/create page's role_required) plus Project Owner (a first-class
    role in this rework, not just something assigned after the fact).
    Role-only, not
    project-scoped — there's no project yet to scope against."""
    return actor.role in ('admin', 'cs', 'management', 'project_owner')


def _can_manage_flags(actor):
    """Raise/reply to a Brief Flag — straight port of the old page's role
    gate (projects_detail.py create_flag/reply_flag). Role-only, not
    project-scoped: any designer/CS/team_lead/management could always
    flag or reply on any project they can see."""
    return actor.role in ('admin', 'cs', 'designer', 'team_lead', 'management')


def _can_resolve_flag(flag, actor):
    """Only the flag's creator, or admin/management oversight — ported
    verbatim from the old resolve_flag route's check."""
    return flag.created_by_id == actor.id or actor.role in ('admin', 'management')


def _serialize_flag(flag, actor):
    """JSON shape for the History view's lazy fetch — same fields the
    Active view's server-rendered _flag_card.html shows, so history items
    and active items look identical even though one's Jinja and the other's
    built client-side from this JSON."""
    return {
        'id': flag.id,
        'flag_type': flag.flag_type,
        'deliverable_id': flag.deliverable_id,
        'deliverable_name': flag.deliverable.name if flag.deliverable else None,
        'is_resolved': flag.is_resolved,
        'can_resolve': (not flag.is_resolved) and _can_resolve_flag(flag, actor),
        'created_by_name': flag.created_by.name if flag.created_by else 'Unknown',
        'created_at': flag.created_at.isoformat() if flag.created_at else None,
        'resolved_by_name': flag.resolved_by.name if flag.resolved_by else None,
        'resolved_at': flag.resolved_at.isoformat() if flag.resolved_at else None,
        'messages': [
            {
                'author_name': m.author.name if m.author else 'Unknown',
                'message': m.message,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            }
            for m in flag.messages
        ],
    }


# ── Admin status override (deliverable-level, plus a project-level bulk
# version; see override_project_status() below) ───────────────────────────
# There is no STORED project-pill override: project.project_status is a pure
# live roll-up of the project's own deliverables (the shared
# derive_project_status / sync_project_pipeline_status), recomputed after
# every deliverable-affecting action, so a stored override would just get
# clobbered the next time any deliverable changed.
#
# The project-level control is instead a bulk WRITE: pick a status once at
# the project level and override_project_status() applies it to every
# deliverable on the project (C&CM: every ProjectPosmChannel too), through
# the same per-deliverable field-writing logic override_deliverable_status()
# below uses one row at a time. The project pill still isn't stored — it's
# recomputed by sync_project_pipeline_status() at the end,
# same as always — this control just reaches every scope that pill (and,
# for C&CM, the per-customer pills) are actually built from, in one action,
# instead of clicking each deliverable's own picker one at a time. Built
# for cleaning up old projects created before this vocabulary existed, not
# as a everyday substitute for the real status-changing actions (Approve,
# Mark Done, Client Approval, etc.) — those still exist and still work
# exactly as before; this is a shortcut for the backlog, not a replacement.
#
# Both the deliverable-level and the project-level override still write the
# same real underlying fields a normal status change would
# (record_deliverable_status(), the needs_2d/3d/technical + per-stream
# status fields — see _write_deliverable_status_override() below) rather
# than a cosmetic "display override" flag — every other piece of code that
# reads those fields (the project roll-up above, project_preproduction.py's
# cascades, dashboards, revision tracking) stays correct afterward instead
# of quietly disagreeing with what's shown.
_DELIVERABLE_STATUS_OVERRIDE_OPTIONS = [
    ('In Design', 'coral'),
    ('Pre-Production', 'oak'),
    ('Handed to Production', 'clover'),
]

# Same three options, reused verbatim for the project-level bulk picker
# (_details_top_cards.html) — one shared option list so the two pickers can
# never offer different choices.
_PROJECT_STATUS_OVERRIDE_OPTIONS = _DELIVERABLE_STATUS_OVERRIDE_OPTIONS

# Raw ProjectPosmChannel.status an override_project_status() bulk write sets
# every channel on a C&CM project to, so the per-customer expand rows
# (status_vocabulary.py's derive_customer_pipeline_status /
# _pipeline_stage_for) read back as the same target label the deliverables
# were just set to. 'in_queue' matches the column's own real default value
# (a channel that's never advanced past creation) rather than borrowing
# 'in_progress' from the deliverable side — _pipeline_stage_for's default
# branch reads either as "In Design" so it makes no visible difference, but
# 'in_queue' is the more honest "nothing happened yet" value for this
# specific column. 'approved' (not 'pre_production', which is a dead value
# no real channel ever writes — see _pipeline_stage_for's own comment) is
# what a real Client Approval writes on approval, so it's what this reuses
# for "Pre-Production" too — same raw value, same rendered label.
_PROJECT_STATUS_OVERRIDE_CHANNEL_WRITE = {
    'In Design': 'in_queue',
    'Pre-Production': 'approved',
    'Handed to Production': 'handed_to_production',
}

# Raw Deliverable.status value an "In Design" override writes — reuses
# 'in_progress' as a generic "back to in design" reset, since every
# pre-approval raw value (in_queue/in_progress/internal_review/
# revision_in_queue/etc.) reads as "In Design" the same way regardless of
# which one it literally is (status_vocabulary.py's derive_deliverable_status).
# The two post-approval labels (Pre-Production / Handed to Production) are
# handled separately in override_deliverable_status() — they both write
# status='approved' underneath; which one actually displays is entirely a
# function of needs_2d/3d/technical + status_2d/status_3d/technical_status
# (status_vocabulary.py's _post_approval_deliverable_status), not this map.
_DELIVERABLE_STATUS_WRITE = {
    'In Design': 'in_progress',
}


_TEAM_CANONICAL = {'2d': '2D', '3d': '3D', 'technical': 'Technical'}


def _canonical_team(raw):
    """Normalizes a team string to the exact casing User.team/registration
    use ('2D'/'3D'/'Technical'). Needed because DeliverableTypeDiscipline.team
    (set via the admin Deliverable Types editor) and the free-text
    Deliverable.teams field aren't guaranteed to be saved in that casing —
    the edit form in admin.js stored them lowercase ('2d'/'3d'/'technical')
    historically, so plenty of existing rows still are. Nothing before
    the team-tag assignment feature (this file) cared about exact casing —
    display always went through .lower() anyway for the CSS class name —
    so this mismatch was invisible until an exact `User.team == team`
    match was needed. Normalizing here, at read time, means every
    deliverable's Assignments column works immediately regardless of
    which casing its own disciplines happen to be stored in, without
    needing a data migration or every type to be re-saved first."""
    if not raw:
        return raw
    return _TEAM_CANONICAL.get(raw.strip().lower(), raw.strip())


def _needed_teams(d):
    """Which teams (2D/3D/Technical) a deliverable actually needs, in
    display order — same source-of-truth branching the Team column
    template used to do inline (deliverable_type's own disciplines list,
    falling back to the free-text Deliverable.teams field for
    C&CM/manually-added rows with no catalogue type). Centralized here so
    _build_deliverable_focus_context can build the assignment context off
    the exact same list the template renders. Always returns canonically-
    cased team strings — see _canonical_team()."""
    if d.deliverable_type and d.deliverable_type.disciplines:
        return [_canonical_team(disc.team) for disc in d.deliverable_type.disciplines]
    if d.teams:
        return [_canonical_team(t) for t in d.teams.split(',') if t]
    return []


def _build_deliverable_focus_context(deliverables, actor, can_manage_project):
    """Computes the per-deliverable status pill + Focused/All eligibility data
    that both the Standard and C&CM Deliverables views need, so the two
    branches in overlay_deliverables() can't drift out of sync on this.

    Also builds `assign_by_deliverable` — per
    deliverable, per needed team, who's assigned (if anyone) and what
    clicking that team's tag should do for the viewing actor. This is the
    read side of the Team column's click-to-assign feature; the write
    side is assign_deliverable_team() below.
    """
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
    from app.modules.core.shared.services.status_tracking import bulk_deliverable_status_started_at
    from app.modules.core.shared.models import User
    status_by_id = {}
    assigned_ids = set()
    for d in deliverables:
        status_by_id[d.id] = derive_deliverable_status(d)
        if any(a.designer_id == actor.id for a in d.disciplines):
            assigned_ids.add(d.id)
    # One bulk query for the whole roster rather than one per deliverable,
    # same pattern _bulk_deliverable_aggregates uses in project_list.
    status_started_at_by_id = bulk_deliverable_status_started_at([d.id for d in deliverables])

    # Options are per-team, not per-deliverable/per-row — one small query
    # per distinct team actually in use on this roster (at most 3:
    # 2D/3D/Technical), regardless of how many deliverables are showing.
    needed_teams = set()
    for d in deliverables:
        needed_teams.update(_needed_teams(d))
    options_by_team = {
        team: User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == team)
                         .order_by(User.name).all()
        for team in needed_teams
    }

    assign_by_deliverable = {}
    for d in deliverables:
        assignment_by_team = {a.team: a for a in d.disciplines}
        row = []
        for team in _needed_teams(d):
            existing = assignment_by_team.get(team)
            if can_manage_project or (actor.role == 'team_lead' and actor.team == team):
                mode = 'manage'
            elif actor.role == 'designer' and actor.team == team:
                mode = 'self'
            else:
                mode = 'static'
            row.append({
                'team': team,
                'person': existing.designer if existing else None,
                'mode': mode,
                'options': options_by_team.get(team, []),
            })
        assign_by_deliverable[d.id] = row

    return {
        'status_by_id': status_by_id,
        'status_started_at_by_id': status_started_at_by_id,
        'assigned_ids': assigned_ids,
        'assign_by_deliverable': assign_by_deliverable,
        # Designer/Team Lead/Admin get the toggle; everyone else always sees All.
        'can_toggle_focus': actor.role in ('designer', 'team_lead', 'admin'),
        # Designer/Team Lead default to Focused (their own workload first);
        # Admin's toggle doesn't filter anything either way, per your call —
        # defaulting it to All just means it starts in the "off" position.
        'default_focus': actor.role in ('designer', 'team_lead'),
        # Status override — admin-only, click the pill / pick a different
        # status. One shared option list regardless of brief type:
        # derive_deliverable_status is identical for Standard and C&CM
        # deliverables. This is the deliverable-level override (the
        # project-level one is a bulk write; see the comment above
        # _DELIVERABLE_STATUS_OVERRIDE_OPTIONS).
        'can_override_status': actor.role == 'admin',
        'deliverable_status_options': _DELIVERABLE_STATUS_OVERRIDE_OPTIONS,
    }

def _build_ccm_deliverable_sections(project):
    """Groups a C&CM project's deliverables as Region -> Customer -> Deliverables,
    mirroring the brief_sections pattern used elsewhere (projects_detail.py's overlay
    route, the old detail page's C&CM section) so this view can't drift from how the
    rest of the app already understands region/customer structure. Customers whose
    region isn't one of the five known keys land in a single 'other' bucket rather
    than being silently dropped.
    """
    from app.modules.core.shared.models import Deliverable

    by_region = {}
    for pc in project.project_customers:
        if pc.cancelled:
            continue
        region_key = pc.customer.region or 'other'
        by_region.setdefault(region_key, []).append(pc)

    region_names = {
        'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar',
        'bahrain': 'Bahrain', 'oman': 'Oman', 'other': 'Other',
    }
    region_order = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman', 'other']

    sections = []
    for region_key in region_order:
        if region_key not in by_region:
            continue
        customers = []
        for pc in by_region[region_key]:
            deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id=pc.id
            ).order_by(Deliverable.id).all()
            customers.append({'project_customer': pc, 'deliverables': deliverables})
        sections.append({
            'key': region_key,
            'name': region_names.get(region_key, region_key.title()),
            'customers': customers,
        })
    return sections

def _build_submission_regions(project):
    """Groups a C&CM project's customers as Region -> Customer for the
    Submissions rail (names/ids only — no submission data queried here,
    that's fetched per-selection once a pill is clicked). Same grouping as
    _build_ccm_deliverable_sections, kept as its own lightweight version
    since Submissions doesn't need each customer's deliverables list.
    """
    by_region = {}
    for pc in project.project_customers:
        if pc.cancelled:
            continue
        region_key = pc.customer.region or 'other'
        by_region.setdefault(region_key, []).append(pc)

    region_names = {
        'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar',
        'bahrain': 'Bahrain', 'oman': 'Oman', 'other': 'Other',
    }
    region_order = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman', 'other']

    sections = []
    for region_key in region_order:
        if region_key not in by_region:
            continue
        sections.append({
            'key': region_key,
            'name': region_names.get(region_key, region_key.title()),
            'customers': by_region[region_key],
        })
    return sections

def _resolve_submission_scope(project, scope, customer_id=None):
    """
    Resolves a Submissions rail selection (scope='ckv', or scope='customer'
    + customer_id) into the phase/channel context a ProjectSubmission
    needs to be scoped correctly. Shared by every new overlay Submissions
    route (content read, draft upload, remove file, submit to client, ...)
    so scope resolution can't drift between them.

    Returns {'channel': ProjectPosmChannel|None, 'phase': str,
    'posm_country': str|None, 'posm_customer_id': int|None}.
    """
    from app.modules.core.shared.models import ProjectPosmChannel

    if scope == 'customer' and customer_id:
        channel = ProjectPosmChannel.query.filter_by(
            project_id=project.id, posm_customer_id=customer_id
        ).first()
        return {
            'channel': channel,
            'phase': 'posm',
            'posm_country': channel.posm_country if channel else None,
            'posm_customer_id': customer_id,
        }

    # scope == 'ckv', or a Standard Brief project (no rail, no scope param
    # at all) — both are the same non-channel "concept_kv" phase today.
    return {'channel': None, 'phase': 'concept_kv', 'posm_country': None, 'posm_customer_id': None}


def _get_active_draft(project, resolved):
    """Returns the current active ProjectSubmission for this scope, across
    any stage of the new overlay's review cycle — draft, internal_review,
    or internal_revision — not literally just 'draft'. Widened in sub-step
    6: once a submission locks (Submit for Review) or gets flagged (Flag
    Internal Revision), it's still THE active submission for this scope —
    uploads/edits during an Edit session need to land on it, not silently
    spawn a second one. workflow_status is never NULL for a row this new
    architecture created (upload always sets it to 'draft' on first
    creation), so restricting to these three values still correctly
    excludes stale legacy rows the old detail page's routes in
    projects_submission.py left with workflow_status=NULL."""
    from app.modules.core.shared.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
        is_active=True,
    ).filter(
        ProjectSubmission.workflow_status.in_(['draft', 'internal_review', 'internal_revision'])
    ).first()

def _get_sent_submission(project, resolved):
    """The most recent already-sent submission for this scope
    (workflow_status='sent_to_client'). Separate from _get_active_draft on
    purpose: once a deck is sent it leaves the editable draft/review/revision
    cycle _get_active_draft tracks, but the Submissions surface still needs to
    show it (read-only) rather than snapping back to an empty upload state.
    Standard Brief today; the scope filter already covers channel/customer for
    the later C&CM/Gulf pass."""
    from app.modules.core.shared.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
        is_active=True,
        workflow_status='sent_to_client',
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).first()

def _get_submission_history(project, resolved):
    """Every submission for this scope that was actually Sent to Client
    (submitted_to_client_at set), newest first — the client-facing revision
    history. Scope-matched the same way _get_active_draft / _get_sent_submission
    are, so Standard / C&CM Concept & KV / per-customer POSM each get their own
    history. NOT filtered by is_active (past revisions get deactivated but must
    still appear); includes the current sent deck too, so History is the full
    record rather than 'older than current'."""
    from app.modules.core.shared.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
    ).filter(
        ProjectSubmission.submitted_to_client_at.isnot(None)
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).all()


def _revision_label_from_name(name):
    """Pull the 'Initial' / 'Revision N' label out of a canonical deck name
    (…- Initial.zip / …- Revision 2.pptx) for a compact history chip. Both the
    overlay zip names and the old-flow deck names end this way, so one regex
    covers both; anything unexpected falls back to the bare filename."""
    import re
    m = re.search(r'-\s*(Initial|Revision\s+\d+)\.[^.]+$', name or '', re.IGNORECASE)
    return m.group(1) if m else (name or 'Deck')

def _build_draft_card_context(project, actor, resolved):
    """
    Everything the Draft card needs to render for one Submissions scope —
    shared by the Standard Brief's initial /overlay/submissions render and
    the C&CM /overlay/submissions/content per-scope fetch, so the two
    can't drift out of sync (same reasoning as _build_details_context).

    can_manage_draft mirrors the old detail page's upload_submission /
    submit_for_internal_review gating exactly: admin/designer/team_lead
    only — CS can view a submission but never uploads or removes a file.

    Extended in sub-step 6 (Submit for Review / Edit / Flag Internal
    Revision): also builds the deliverable / Concept & KV picker options
    for this scope, the review-state flags the frontend needs to decide
    which controls to show (is_locked / is_being_edited), and the event
    history timeline. can_review mirrors the old flag_submission gating
    (admin/cs/management) — the "Flag Internal Revision" side.

    is_editable / is_locked state machine: draft -> fully editable. internal_review -> locked,
    unless is_being_edited (designer clicked Edit). internal_revision ->
    immediately editable again, no separate unlock click needed, since
    CS's flag message IS the reason. Submitting for review — whether it's
    the first time or after an edit/flag cycle — always re-locks to
    internal_review and clears is_being_edited.
    """
    from app.modules.core.shared.models import ProjectSubmissionFile, Deliverable

    draft = _get_active_draft(project, resolved)
    cached_files = []
    if draft:
        cached_files = ProjectSubmissionFile.query.filter_by(
            submission_id=draft.id, storage_location='cache'
        ).order_by(
            ProjectSubmissionFile.is_main_deck.desc(),
            ProjectSubmissionFile.uploaded_at.asc(),
        ).all()

    workflow_status = draft.workflow_status if draft else 'draft'
    is_being_edited = bool(draft.is_being_edited) if draft else False
    is_editable = (
        workflow_status in ('draft', 'internal_revision')
        or (workflow_status == 'internal_review' and is_being_edited)
    )
    is_locked = draft is not None and not is_editable

    events = list(draft.events) if draft else []

    # The current Sent-to-Client deck for this scope, if any. Computed
    # UNCONDITIONALLY (not only when there's no active draft) so the Current
    # tab can show it as a "Submitted to Client" indicator ABOVE the working
    # draft — a designer/CS opening the page sees at a glance that a deck is
    # live with the client, while still working the next draft.
    sent_submission = _get_sent_submission(project, resolved)
    sent_files = []
    if sent_submission:
        sent_files = ProjectSubmissionFile.query.filter_by(
            submission_id=sent_submission.id
        ).order_by(
            ProjectSubmissionFile.is_main_deck.desc(),
            ProjectSubmissionFile.uploaded_at.asc(),
        ).all()

    # Client Revision (Standard scope this pass). CS/admin/management can
    # request one on a sent deck that hasn't already had a revision requested;
    # once requested, the indicator flips to a "Revision Requested" state
    # showing the client's message (the latest client_revision event).
    sent_revision_event = None
    if sent_submission:
        sent_revision_event = next(
            (e for e in sent_submission.events if e.event_type == 'client_revision'), None)
    can_request_client_revision = (
        actor.role in ('admin', 'cs', 'management')
        and sent_submission is not None
        and sent_revision_event is None
    )

    # Revision history — every deck Sent to Client for this scope, newest
    # first (Initial, Revision 1, …). Includes the current sent deck too, so
    # History is the full client-facing record; it fills out as the revision
    # cycle produces more sends. Each entry carries its files for per-file
    # preview/download (via the NAS zip-extract path); a legacy old-flow
    # submission with no ProjectSubmissionFile rows falls back to a deck-level
    # download in the template.
    history_submissions = []
    for sub in _get_submission_history(project, resolved):
        sub_files = ProjectSubmissionFile.query.filter_by(
            submission_id=sub.id
        ).order_by(
            ProjectSubmissionFile.is_main_deck.desc(),
            ProjectSubmissionFile.uploaded_at.asc(),
        ).all()
        history_submissions.append({
            'submission': sub,
            'files': sub_files,
            'label': _revision_label_from_name(sub.original_filename),
            'included_names': [link.deliverable.name for link in sub.included_deliverables if link.deliverable],
            'includes_concept': sub.includes_concept,
            'includes_kv': sub.includes_kv,
        })

    # Deliverable / Concept & KV picker options for this scope. The C&CM
    # "Concept & KV" pill (phase='concept_kv' on a 'ccm' project) is
    # concept/KV toggles, not deliverables; a Standard Brief project also
    # resolves to phase='concept_kv' (it has no customer scoping at all)
    # but its "deck" covers real deliverables, so it gets the deliverable
    # picker instead.
    is_ckv_toggle_scope = resolved['phase'] == 'concept_kv' and project.brief_type == 'ccm'
    if is_ckv_toggle_scope:
        deliverable_options = []
    elif resolved['phase'] == 'concept_kv':
        deliverable_options = Deliverable.query.filter_by(
            project_id=project.id, project_customer_id=None
        ).order_by(Deliverable.id).all()
    else:
        deliverable_options = Deliverable.query.filter_by(
            project_id=project.id, project_customer_id=resolved['posm_customer_id']
        ).order_by(Deliverable.id).all()

    selected_deliverable_ids = []
    includes_concept = False
    includes_kv = False
    if draft:
        selected_deliverable_ids = [link.deliverable_id for link in draft.included_deliverables]
        includes_concept = draft.includes_concept
        includes_kv = draft.includes_kv

    # Client Approval — same gate as Client Revision (a sent deck with no
    # revision already pending against it); the two are mutually-exclusive
    # actions on the same indicator. Partial approval: CS picks which of the
    # sent deck's still-pending deliverables are ready (already-approved ones
    # aren't offered again — per-deliverable is the
    # model so some can move to Pre-Production while others stay in design).
    # C&CM Concept & KV has no deliverable list to pick from — approved as a
    # pair, so no picker options needed for that scope.
    can_mark_approved = can_request_client_revision
    approvable_deliverables = []
    if can_mark_approved and sent_submission and not is_ckv_toggle_scope:
        from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
        approvable_deliverables = [
            {'deliverable': link.deliverable, 'pill': derive_deliverable_status(link.deliverable)}
            for link in sent_submission.included_deliverables
            if link.deliverable and link.deliverable.status != 'approved'
        ]

    if is_ckv_toggle_scope:
        all_deliverables_approved = (
            (not project.has_concept or project.concept_status == 'approved')
            and (not project.has_kv or project.kv_status == 'approved')
        )
    else:
        all_deliverables_approved = bool(deliverable_options) and all(
            d.status == 'approved' for d in deliverable_options
        )

    revisable_deliverables = []
    if can_request_client_revision and sent_submission and not is_ckv_toggle_scope:
        from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
        revisable_deliverables = [
            {'deliverable': link.deliverable, 'pill': derive_deliverable_status(link.deliverable)}
            for link in sent_submission.included_deliverables
            if link.deliverable
        ]

    return {
        'draft': draft,
        'cached_files': cached_files,
        'can_manage_draft': actor.role in ('admin', 'designer', 'team_lead'),
        'can_review': actor.role in ('admin', 'cs', 'management'),
        'workflow_status': workflow_status,
        'is_being_edited': is_being_edited,
        'is_locked': is_locked,
        'events': events,
        'is_ckv_toggle_scope': is_ckv_toggle_scope,
        'deliverable_options': deliverable_options,
        'selected_deliverable_ids': selected_deliverable_ids,
        'includes_concept': includes_concept,
        'includes_kv': includes_kv,
        'has_concept': project.has_concept,
        'has_kv': project.has_kv,
        'sent_submission': sent_submission,
        'sent_revision_event': sent_revision_event,
        'can_request_client_revision': can_request_client_revision,
        'can_mark_approved': can_mark_approved,
        'all_deliverables_approved': all_deliverables_approved,
        'approvable_deliverables': approvable_deliverables,
        'revisable_deliverables': revisable_deliverables,
        'sent_files': sent_files,
        'history_submissions': history_submissions,
    }


# Hourly slots, 8:00 AM through 10:00 PM, as (value, label) pairs for the
# Deliverables edit table's Time dropdown. value is 24h "HH:00" (matches
# how <input type="time"> / our own parsing expects it); label is the
# 12h display form.
DESIGN_DEADLINE_TIME_OPTIONS = [
    (f'{h:02d}:00', f'{((h - 1) % 12) + 1}:00 {"AM" if h < 12 else "PM"}')
    for h in range(8, 23)
]

_DESIGN_DEADLINE_TIME_VALUES = {v for v, _ in DESIGN_DEADLINE_TIME_OPTIONS}


def _annotate_offhour_time(deliverables):
    """The Design Deadline time dropdown only offers on-the-hour slots
    (DESIGN_DEADLINE_TIME_OPTIONS) — a deliverable whose stored time isn't
    one of those (from an older flow, or set some other way) would
    otherwise render as blank in Edit Deliverables, and an unrelated Save
    would then silently wipe the real time. Tags each such row with
    d.edit_time_extra = (value, label) so the template can inject a
    matching selected <option> and round-trip the real value untouched."""
    for d in deliverables:
        d.edit_time_extra = None
        t = d.design_deadline_time
        if t and t.strftime('%H:%M') not in _DESIGN_DEADLINE_TIME_VALUES:
            hour12 = ((t.hour - 1) % 12) + 1
            period = 'AM' if t.hour < 12 else 'PM'
            d.edit_time_extra = (t.strftime('%H:%M'), f'{hour12}:{t.minute:02d} {period}')


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

    cs_lead_options = User.query.filter_by(role='cs').order_by(User.name).all() if can_reassign_cs_lead else []

    available_cs_users = User.query.filter(
        User.role.in_(['cs', 'admin', 'management']),
        User.id != project.cs_lead_id,
        ~User.id.in_(secondary_cs_ids) if secondary_cs_ids else True
    ).order_by(User.name).all() if can_manage_cs else []

    if actor.role in ('admin', 'management') or actor.id == project.cs_lead_id:
        owner_options = User.query.filter_by(role='project_owner').order_by(User.name).all()
    elif actor.role == 'project_owner':
        owner_options = [actor]
    else:
        owner_options = []

    # status_label/status_class are a pure live roll-up of the project's
    # own deliverables (status_vocabulary.py's derive_project_status) — this
    # pill itself is never written directly, even by the admin override
    # below (see the block comment above override_project_status() in this
    # file). can_override_project_status
    # gates a bulk WRITE to every deliverable (+ C&CM channel), not a
    # stored override of this pill; the value below still just reads back
    # whatever that bulk write leaves the roll-up computing.
    status_label, status_class = derive_project_status(project)
    can_override_project_status = actor.role == 'admin'
    # When this project's raw status last changed, straight from
    # ProjectStatusLog; None if it pre-dates that table.
    status_started_at = project_status_started_at(project)
    # The client-approval moment specifically. Only worth showing
    # separately from
    # status_started_at once the project's moved on to Handed to
    # Production — at Pre-Production they're the same moment, and at In
    # Design there's no current approval to show.
    client_approved_at = project_client_approved_at(project) if status_label == 'Handed to Production' else None

    requested_teams = [t.strip() for t in (project.design_teams_requested or '').split(',') if t.strip()]
    assignments_by_team = {pd.team: pd for pd in project.assigned_designers}
    all_teams = requested_teams + [t for t in sorted(assignments_by_team) if t not in requested_teams]

    designer_rows = []
    for team in all_teams:
        assignment = assignments_by_team.get(team)
        can_manage = (
            actor.role in ('admin', 'management')
            or actor.team == team
            or (assignment and assignment.user_id == actor.id)
        )
        options = User.query.filter(
            User.team == team,
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
        concept_kv_designer_options = User.query.filter(
            User.role.in_(['designer', 'team_lead'])
        ).order_by(User.name).all()
    elif can_self_claim_concept_kv:
        concept_kv_designer_options = [actor]
    else:
        concept_kv_designer_options = []

    concept_kv_designer = project.concept_designer or project.kv_designer

    # Start Project — the one manual gate that moves a project
    # off "Briefed" (status_vocabulary.py's derive_project_status checks
    # project.project_status == 'briefed' explicitly, ahead of the
    # deliverable roll-up). Same button, same underlying action for both
    # brief types — this is still the only thing that moves either brief
    # type off Briefed; nothing deliverable-driven does, by design (a
    # project sits at Briefed until someone deliberately starts it).
    # Reuses can_edit_project's permission tier rather than a new one.
    can_start_project = can_edit_project and project.project_status == 'briefed'

    # Cancel/Reactivate — see _can_cancel_project. Project
    # Status row shows Cancel Project when active, Reactivate Project once
    # project.cancelled_at is set — the template branches on that column
    # directly rather than a second flag, so there's only one source of truth.
    can_cancel_project = _can_cancel_project(project, actor)

    # On Hold — see _can_toggle_hold. Same branch-on-the-
    # column-directly approach as Cancel: the template checks
    # project.project_status == 'on_hold' itself rather than a second flag.
    can_toggle_hold = _can_toggle_hold(project, actor)

    # Cancel Customer — C&CM only. Deliberately built from project.
    # project_customers directly, NOT the same all_customers() every other
    # C&CM tab builds (_build_ccm_deliverable_sections etc.) — those all
    # filter OUT cancelled customers, since that exclusion is what "freezes"
    # a customer everywhere else on this tab. This card needs the opposite:
    # every customer, cancelled or not, since it's the one place a
    # cancelled customer can still be seen and reactivated. Reuses
    # can_cancel_project as the permission gate — same people who can
    # cancel the whole project can cancel one customer within it.
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

    # Add Customer (25 Aug 2026, per Ezekiel — a C&CM campaign that expands
    # to a new customer after submission had no path forward at all; the
    # customer picker only ever existed in the create-mode draft flow).
    # Reuses _can_manage_deliverables's permission tier rather than
    # can_cancel_project — adding a customer immediately creates its own
    # deliverables surface, so this is closer kin to managing deliverables
    # than to cancelling the project. Excludes every customer already
    # linked here, cancelled or not — re-adding a cancelled one goes
    # through Reactivate above, not a second row for the same customer.
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

    # Brief Flags — Details' Flags card covers 'project' plus the
    # 'concept'/'kv' flag types (folded in here rather than a third toggle
    # location —
    # Concept & KV is project-level info in the new system, not its own
    # flaggable entity like a deliverable is).
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

    # Edit mode — Client/Type of Design are FKs, not free
    # text, so the edit-mode dropdown needs the full option list, same
    # shape as cs_lead_options/owner_options above. Only fetched for
    # someone who can actually edit — no point loading these for a
    # read-only viewer.
    from app.modules.core.shared.models import Client, DesignType
    client_options = Client.query.order_by(Client.name).all() if can_edit_project else []
    design_type_options = DesignType.query.order_by(DesignType.name).all() if can_edit_project else []

    # Edit mode — concurrent-edit check reuses the latest
    # ActivityLog row for this project as a "last modified" signal rather
    # than a new updated_at column (Project doesn't have one). Snapshotted
    # here when the section loads, sent back with Save, compared server-
    # side — if someone else's write logged a newer entry in between, the
    # save is rejected as a conflict instead of silently overwriting it.
    from app.modules.core.shared.models import ActivityLog
    latest_activity = (
        ActivityLog.query
        .filter_by(entity_type='project', entity_id=project.id)
        .order_by(ActivityLog.created_at.desc())
        .first()
    )
    edit_snapshot_at = latest_activity.created_at.isoformat() if latest_activity else ''

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
    )




def _recompute_initial_deadline(project):
    if project.brief_type == 'ccm' and project.has_concept and project.concept_deadline:
        project.first_output_deadline = project.concept_deadline
        return
    deadlines = [d.design_deadline for d in _scoped_deliverables_query(project).all() if d.design_deadline]
    project.first_output_deadline = min(deadlines) if deadlines else None

def _scoped_deliverables_query(project):
    """Deliverables that actually belong to project.brief_type's data —
    Standard deliverables always carry project_customer_id=None, C&CM ones
    always carry one. Shared by _recompute_initial_deadline,
    _validate_for_finalize, and overlay_create_summary so "what counts as
    this project's real deliverables" can't drift between them — data for
    the OTHER brief type can coexist on a draft right up until finalize
    (see _drop_unselected_brief_data), so all three need to agree on what
    to ignore."""
    from app.modules.core.shared.models import Deliverable
    query = Deliverable.query.filter_by(project_id=project.id)
    if project.brief_type == 'ccm':
        return query.filter(Deliverable.project_customer_id.isnot(None))
    return query.filter(Deliverable.project_customer_id.is_(None))


def _drop_unselected_brief_data(project):
    """At finalize, only the SELECTED brief type's data survives — anything
    entered for the other type while trying it out gets dropped. Both types
    coexist freely up to this point (see overlay_create_draft()) precisely
    so switching back and forth never loses work; this is the one place
    that actually commits to one side."""
    from app.modules.core.shared.extensions import db
    if project.brief_type == 'standard':
        # ProjectCustomer.deliverables cascades ('all, delete-orphan'), so
        # deleting the ProjectCustomer rows takes their C&CM deliverables
        # with them.
        for pc in list(project.project_customers):
            db.session.delete(pc)
        project.has_concept = False
        project.has_kv = False
        project.concept_deadline = None
        project.kv_deadline = None
        project.concept_options_required = None
        project.kv_options_required = None
        project.kv_requirements = None
        project.urgency = None
    else: # ccm
        from app.modules.core.shared.models import Deliverable
        Deliverable.query.filter_by(project_id=project.id, project_customer_id=None).delete()
        project.design_type_id = None
        project.client_expectation = None
        project.what_to_avoid = None
        project.additional_information = None
        project.is_production_only = False
        project.preproduction_requirements = None


_CREATE_REGION_NAMES = {
    'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar', 'bahrain': 'Bahrain', 'oman': 'Oman',
}
_CREATE_REGION_ORDER = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman']


def _create_mode_context(project, actor):
    """Shared by the shell GET and (once #62/#64 exist) whatever re-renders
    the create-mode Details step after an autosave — the picklists/options a
    blank project needs are the same regardless of how it got here.
    """
    from app.modules.core.shared.models import User, Client, Customer, DesignType, DesignDirection

    customers_by_region = {
        region: Customer.query.filter_by(region=region).order_by(Customer.name).all()
        for region in _CREATE_REGION_ORDER
    }
    selected_customer_ids = {pc.customer_id for pc in project.project_customers if not pc.cancelled}

    # Same shape as _build_details_context()'s can_manage_reference_files —
    # duplicated rather than shared since the live version also folds in
    # can_edit_project/can_reassign_cs_lead/etc. that don't apply here.
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    can_manage_reference_files = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )

    return {
        'cs_lead_options': User.query.filter(User.role.in_(['cs', 'admin', 'management'])).order_by(User.name).all(),
        'project_owner_options': User.query.filter_by(role='project_owner').order_by(User.name).all(),
        'client_options': Client.query.order_by(Client.name).all(),
        'design_type_options': DesignType.query.order_by(DesignType.name).all(),
        'design_direction_options': DesignDirection.query.order_by(DesignDirection.name).all(),
        'customers_by_region': customers_by_region,
        'region_names': _CREATE_REGION_NAMES,
        'selected_customer_ids': selected_customer_ids,
        'can_create_project': _can_create_project(actor),
        'can_manage_reference_files': can_manage_reference_files,
    }


@project_overlay_bp.route('/projects/overlay/new', methods=['POST'])
@login_required
def overlay_create_draft():
    """Creates (or, given an existing draft's project_id, patches) the
    minimal Project row the create-mode overlay operates against. One
    endpoint doing both per legacy autosave()'s pattern (projects_brief.py)
    — the frontend doesn't need to know or care whether this is the first
    call or the hundredth, it just posts "here's what I know so far" and
    gets a project_id back. See _details_create.html's data-field wiring in
    project_overlay_create.js for what keys this actually receives.
    """
    from datetime import datetime as _dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Scope, ProjectCustomer, Customer
    from app.modules.core.shared.services.status_tracking import record_project_status

    actor = _get_actor()
    if not _can_create_project(actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    project_id = data.get('project_id')

    draft = None
    if project_id:
        candidate = Project.query.get(project_id)
        if candidate and candidate.project_status == 'draft' and (
            candidate.created_by_id == actor.id or actor.role in ('admin', 'management')
        ):
            draft = candidate
        elif candidate and candidate.project_status != 'draft':
            return jsonify({'error': 'This project has already been created — refresh and open it normally.'}), 400

    if not draft:
        default_scope = Scope.query.filter_by(active=True).first()
        draft = Project(
            name=(data.get('name') or '').strip() or 'Untitled Draft',
            client='TBD',
            # cs_lead_id is NOT NULL on Project — defaults to the actor
            # themselves regardless of role (same as legacy autosave()),
            # even for a Project Owner/admin/management creator who isn't
            # actually a valid CS Lead pick; the CS Lead select in
            # _details_create.html lets them immediately change it to a
            # real cs_lead_options entry before finalizing.
            cs_lead_id=int(data['cs_lead_id']) if data.get('cs_lead_id') else actor.id,
            creator=actor,
            project_status='draft',
            scope_id=default_scope.id if default_scope else 1,
            briefing_date=_dt.utcnow().date(),
        )
        db.session.add(draft)
        db.session.flush()
        record_project_status(draft, 'draft', actor)

    # Every field below is optional per call — the frontend only ever sends
    # the one field that just changed (see project_overlay_create.js's
    # debounced per-field autosave), so a call with none of these keys still
    # succeeds and just touches last_autosaved_at.
    if 'name' in data:
        draft.name = (data.get('name') or '').strip() or 'Untitled Draft'
    if 'job_number' in data:
        # job_number is unique — checked here rather than letting a
        # duplicate hit the DB's unique constraint as an IntegrityError
        # (which would 500 the whole request instead of a clean message).
        # Same check projects_submission.py's finalize does today.
        job_number = (data.get('job_number') or '').strip() or None
        if job_number and Project.query.filter(Project.job_number == job_number, Project.id != draft.id).first():
            return jsonify({'error': f'Job number "{job_number}" is already in use.'}), 400
        draft.job_number = job_number
    if 'brief_type' in data and data['brief_type'] in ('standard', 'ccm'):
        draft.brief_type = data['brief_type']
    if data.get('cs_lead_id'):
        # cs_lead_id is NOT NULL — unlike client_id/contact_id below, an
        # empty selection is ignored rather than nulling it out, same guard
        # legacy autosave() used.
        draft.cs_lead_id = int(data['cs_lead_id'])
    if 'project_owner_id' in data:
        draft.project_owner_id = int(data['project_owner_id']) if data.get('project_owner_id') else None
    if 'client_id' in data:
        draft.client_id = int(data['client_id']) if data.get('client_id') else None
    if 'contact_id' in data:
        draft.contact_id = int(data['contact_id']) if data.get('contact_id') else None
    if 'design_teams' in data:
        draft.design_teams_requested = ','.join(data.get('design_teams') or [])
    # first_output_deadline (Initial Deadline) is no longer a directly-set
    # field — see _recompute_initial_deadline()
    # below, called unconditionally at the end of this route instead.
    if 'execution_date' in data:
        draft.execution_date = _parse_edit_date(data.get('execution_date'))
    if 'is_production_only' in data:
        draft.is_production_only = bool(data.get('is_production_only'))
    if 'preproduction_requirements' in data:
        draft.preproduction_requirements = data.get('preproduction_requirements') or None

    # Standard-only fields
    if 'design_type_id' in data:
        draft.design_type_id = int(data['design_type_id']) if data.get('design_type_id') else None
    if 'design_direction_id' in data:
        draft.design_direction_id = int(data['design_direction_id']) if data.get('design_direction_id') else None
    if 'client_expectation' in data:
        draft.client_expectation = data.get('client_expectation') or None
    if 'what_to_avoid' in data:
        draft.what_to_avoid = data.get('what_to_avoid') or None
    if 'additional_information' in data:
        draft.additional_information = data.get('additional_information') or None

    # C&CM-only fields. Concept and KV collapsed into ONE tickbox/deadline/
    # requirements/options set in create mode (concept and KV always go
    # together). The model still has two separate sets of
    # columns (has_concept/concept_deadline/concept_options_required vs.
    # has_kv/kv_deadline/kv_requirements/kv_options_required — kv_requirements
    # is the only one of the two with a free-text field at all) — rather than
    # a migration to merge them for real, this just mirrors one write onto
    # both sides so anything downstream still reading either half sees the
    # same values. concept_kv_requirements is stored on kv_requirements,
    # the one column that actually exists for that purpose.
    if 'urgency' in data:
        draft.urgency = data.get('urgency') or None
    if 'has_concept_kv' in data:
        needed = bool(data.get('has_concept_kv'))
        draft.has_concept = needed
        draft.has_kv = needed
    if 'concept_kv_deadline' in data:
        parsed = _parse_edit_date(data.get('concept_kv_deadline'))
        draft.concept_deadline = parsed
        draft.kv_deadline = parsed
    if 'concept_kv_requirements' in data:
        draft.kv_requirements = data.get('concept_kv_requirements') or None
    if 'concept_kv_options_required' in data:
        value = data.get('concept_kv_options_required')
        draft.concept_options_required = value or None
        draft.kv_options_required = value or None

    # C&CM customer picker — sent as the FULL currently-checked set each
    # time (not a single add/remove), simplest thing that can't drift out
    # of sync with a checkbox grid. Existing rows for customers no longer
    # checked are removed rather than soft-cancelled — nothing downstream
    # can reference them yet, this is still an unfinished draft.
    #
    # (25 Aug 2026: this block used to run twice in a row, back to back —
    # harmless since the second pass was a no-op against what the first
    # already did, but dead weight. Collapsed to one; the ProjectRegion
    # sync below was already only in the second copy.)
    if 'customer_ids' in data:
        wanted_ids = {int(cid) for cid in (data.get('customer_ids') or [])}
        existing = {pc.customer_id: pc for pc in draft.project_customers}
        for customer_id, pc in existing.items():
            if customer_id not in wanted_ids:
                db.session.delete(pc)
        for customer_id in wanted_ids:
            if customer_id not in existing and Customer.query.get(customer_id):
                db.session.add(ProjectCustomer(project_id=draft.id, customer_id=customer_id))

        # Keep ProjectRegion synced to the selected customers' regions —
        # _build_ccm_design_folders() (app/nas.py) drives its Region/
        # Customer folder tree off ProjectRegion, not off project_customers
        # directly, same as the old flow's picker always did. This flow
        # never wrote ProjectRegion at all until now, so C&CM folder trees
        # came out region-less. Full replace, same pattern as the customer
        # set above.
        from app.modules.core.shared.models import ProjectRegion
        wanted_regions = {
            c.region for c in Customer.query.filter(Customer.id.in_(wanted_ids)).all() if c.region
        }
        ProjectRegion.query.filter_by(project_id=draft.id).delete()
        for region in wanted_regions:
            db.session.add(ProjectRegion(project_id=draft.id, region=region))        

    draft.last_autosaved_at = _dt.utcnow()
    _recompute_initial_deadline(draft)
    db.session.commit()

    return jsonify({
        'success': True,
        'project_id': draft.id,
        'first_output_deadline': draft.first_output_deadline.strftime('%d %b %Y') if draft.first_output_deadline else None,
    })


@project_overlay_bp.route('/projects/<int:project_id>/overlay/create')
@login_required
def overlay_create_shell(project_id):
    """The create-mode overlay shell — Details then Deliverables only, no
    lifecycle sidebar (Cancel/Hold/Flag don't apply to a project that
    doesn't exist yet), opened by the "+ New Project" button.
    Only reachable for the draft's own creator (or admin/management), and
    only while it's still actually a draft — once finalized (#64), the
    normal /overlay route takes over and this one no longer applies.
    """
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft' or not (
        project.created_by_id == actor.id or actor.role in ('admin', 'management')
    ):
        abort(403)

    context = _create_mode_context(project, actor)
    return render_template('project_overlay/_overlay_create.html', project=project, **context)


def _can_finalize_create(project, actor):
    """Same reachability rule as overlay_create_shell() — the draft's own
    creator, or admin/management. Duplicated as its own check (rather than
    calling overlay_create_shell's inline condition) since that one also
    checks project_status == 'draft', which the two finalize routes below
    need to check separately anyway (with their own error message)."""
    return project.created_by_id == actor.id or actor.role in ('admin', 'management')


def _validate_for_finalize(project):
    """Returns an error string, or None if the project is ready to become a
    real project. Standard needs at least one
    deliverable; C&CM needs EITHER Concept & KV info with a deadline OR at
    least one deliverable — "C&CM doesn't need deliverables to submit, only
    concept & KV info and dates" reads as an alternative path, not a ban on
    C&CM projects that only have real deliverables and no concept/KV need.
    Mirrors _recompute_initial_deadline()'s same two-source-of-truth
    reasoning for what counts as "this project has real work queued up."
    """
    if not project.name or not project.client_id or not project.cs_lead_id or not project.brief_type:
        return 'Fill in Name, Client, CS Lead, and Brief Type before creating this project.'

    from app.modules.core.shared.models import Deliverable
    has_deliverables = _scoped_deliverables_query(project).first() is not None

    if project.brief_type == 'standard':
        if not has_deliverables:
            return 'Add at least one deliverable before creating this project.'
        return None

    # C&CM
    has_concept_kv = bool(project.has_concept and project.concept_deadline)
    if not has_concept_kv and not has_deliverables:
        return 'Add Concept & KV info with a deadline, or at least one deliverable, before creating this project.'
    return None


@project_overlay_bp.route('/projects/<int:project_id>/overlay/create/summary')
@login_required
def overlay_create_summary(project_id):
    """Renders the confirm-and-create modal — "Add New Project"
    calls this first; a validation failure here comes back as JSON so the
    frontend can show it as a toast instead of opening a modal at all (per
    Ezekiel: Standard's missing-deliverables case specifically should be "a
    toast saying to add deliverables before they can submit", not a modal
    with an error inside it).
    """
    from app.modules.core.shared.models import Deliverable

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft' or not _can_finalize_create(project, actor):
        abort(403)

    error = _validate_for_finalize(project)
    if error:
        return jsonify({'success': False, 'error': error})

    deliverables = _scoped_deliverables_query(project).order_by(Deliverable.id).all()
    customers = [pc for pc in project.project_customers if not pc.cancelled] if project.brief_type == 'ccm' else []

    html = render_template(
        'project_overlay/_overlay_create_summary.html',
        project=project, deliverables=deliverables, customers=customers,
    )
    return jsonify({'success': True, 'html': html})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/create/finalize', methods=['POST'])
@login_required
def overlay_create_finalize(project_id):
    """Confirm button on the summary modal — turns the draft into a real
    project. Re-validates server-side (the summary render and
    this click can be minutes apart; someone could've deleted the one
    deliverable that made this valid in between) rather than trusting the
    client got this far honestly.
    """
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable
    from app.modules.core.shared.services.status_tracking import record_project_status
    from app.modules.projects.routes.project_preproduction import _apply_skip_to_preproduction
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft' or not _can_finalize_create(project, actor):
        abort(403)

    error = _validate_for_finalize(project)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    record_project_status(project, 'briefed', actor)

    _drop_unselected_brief_data(project) # NEW

    # Production Only (Standard-only — see _details_create.html's toggle,
    # scoped to the Standard card) — every deliverable this project has
    # right now skips straight to Pre-Production, same as manually using
    # Skip to Pre-Production on all of them right after creating it.
    if project.is_production_only:
        deliverables = Deliverable.query.filter_by(project_id=project.id).all()
        if deliverables:
            _apply_skip_to_preproduction(project, deliverables, actor)

    db.session.commit()

    log_activity('project_created', f'"{project.name}" was created',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)


    from flask import current_app as _app
    from app.modules.core.shared.services.nas import _run_in_background, create_project_folders
    _pid = project.id
    _app_obj = _app._get_current_object()
    _run_in_background(_app_obj, lambda: create_project_folders(
        Project.query.get(_pid)
    ))

    return jsonify({'success': True, 'project_id': project.id})


@project_overlay_bp.route('/projects/overlay/drafts')
@login_required
def list_drafts():
    """Resumable-drafts entry point. "+ New Project" calls this
    first — if it comes back with any drafts, the frontend shows a picker
    instead of immediately starting a fresh one. Creators always see their
    own drafts; admin/management additionally see everyone's, per
    Ezekiel, so abandoned ones can be found and discarded rather than
    piling up invisibly.

    Deliberately NOT '/projects/drafts' — projects_brief.py's brief_bp
    (still live, pre-dates this new create flow) already owns that exact
    path for the old drafts list page. Namespacing under '/projects/
    overlay/...' matches this route's sibling '/projects/overlay/new' and
    sidesteps the collision entirely rather than touching legacy code
    that's slated for removal later anyway.
    """
    actor = _get_actor()
    query = Project.query.filter_by(project_status='draft')
    if actor.role not in ('admin', 'management'):
        query = query.filter_by(created_by_id=actor.id)
    # Most-recently-worked-on first, not most-recently-started — same
    # ordering legacy's drafts() route used (projects_old.py), since the
    # one they just stepped away from is the one they're most likely to
    # want back.
    drafts = query.order_by(Project.last_autosaved_at.desc()).all()

    if not drafts:
        return jsonify({'has_drafts': False})

    html = render_template(
        'project_overlay/_overlay_create_drafts_picker.html',
        drafts=drafts, actor=actor,
    )
    return jsonify({'has_drafts': True, 'html': html})


@project_overlay_bp.route('/projects/<int:project_id>/draft', methods=['DELETE'])
@login_required
def delete_draft(project_id):
    """Discards an abandoned draft — creator or admin/management
    only, and only while it's still actually a draft (a project that's
    since been finalized should go through Cancel, not this). Cleans up
    any reference files it accumulated from NAS storage before deleting
    the row, same as delete_project_file() in projects_detail.py (the
    live route backing this create flow's reused Reference Files card) —
    cascade='all, delete-orphan' on Project.reference_files only removes
    the DB rows, not the actual files on the NAS.
    """
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.nas import delete_app_file, build_file_path

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if project.project_status != 'draft':
        abort(404)
    if not (project.created_by_id == actor.id or actor.role in ('admin', 'management')):
        abort(403)

    # delete_app_file() swallows and logs its own NAS failures rather than
    # raising (see app/nas.py) — same as delete_project_file()'s call to
    # it in projects_detail.py, so no try/except needed here either.
    for f in list(project.reference_files):
        nas_path = build_file_path(project, 'Reference Files', f.original_filename)
        delete_app_file(nas_path)

    project_name = project.name
    db.session.delete(project)
    db.session.commit()

    log_activity('project_draft_deleted', f'Draft "{project_name}" was discarded',
                 user=actor, entity_type='project', entity_name=project_name, entity_id=project_id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay')
@login_required
def overlay(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    context = _build_details_context(project, actor)
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

def _parse_edit_date(raw):
    """'YYYY-MM-DD' from <input type=date> -> a date object; '' -> None.
    Shared by every date field the edit-mode Save route accepts."""
    from datetime import datetime as _dt
    if not raw:
        return None
    return _dt.strptime(raw, '%Y-%m-%d').date()


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
    """Admin-only status override (uses the 3-stage vocabulary — see
    _DELIVERABLE_STATUS_OVERRIDE_OPTIONS above). See
    _write_deliverable_status_override() above for what
    fields this actually writes and why.

    Calls sync_project_pipeline_status() at the end — an admin overriding a
    deliverable is exactly the kind of "deliverable-affecting action" that
    can flip the project's own pill, same as a real approval/revision would."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable
    from app.modules.core.shared.services.status_tracking import sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status

    deliverable = Deliverable.query.filter_by(id=deliverable_id, project_id=project_id).first_or_404()
    actor = _get_actor()
    if actor.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only.'}), 403

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
    """Adds a new customer to an already-submitted C&CM project (25 Aug
    2026, per Ezekiel — a campaign that expands to a new customer after
    go-live had no path forward except cancelling and recreating the whole
    project; the customer picker only ever existed in the create-mode
    draft flow, see overlay_create_draft()'s 'customer_ids' handling
    above). Reuses _can_manage_deliverables's permission tier rather than
    can_cancel_project — see _build_details_context's can_manage_customers
    for why.
    """
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
    """Put on Hold / Resume — straight port of projects_detail.py's
    toggle_hold (JSON instead of a full-page redirect+flash). Same
    held_from_status bracket/restore logic and permission set (see
    _can_toggle_hold) as the route this replaces for overlay use."""
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


# ── Brief Flags — port of projects_detail.py's create_flag /
# reply_flag / resolve_flag, JSON instead of form-post+redirect, plus a
# new history endpoint the old full-page detail view didn't need (it just
# rendered every flag inline). ─────────────────────────────────────────

@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/create', methods=['POST'])
@login_required
def overlay_create_flag(project_id):
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import BriefFlag, BriefFlagMessage
    from app.modules.core.shared.services.notifications import notify_cs_of_brief_flag
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_flags(actor):
        return jsonify({'success': False, 'error': 'You do not have permission to raise a flag.'}), 403

    data = request.get_json(silent=True) or {}
    flag_type = data.get('flag_type')
    deliverable_id = data.get('deliverable_id')
    message_text = (data.get('message') or '').strip()
    if flag_type not in ('project', 'deliverable', 'concept', 'kv') or not message_text:
        return jsonify({'success': False, 'error': 'A message is required.'}), 400

    # A 'deliverable' flag with no target (or a target from a different
    # project) would render invisibly in both scopes — Details filters it
    # out (not project/concept/kv) and Deliverables would never match it to
    # a row. Guard server-side rather than trusting the client-side check.
    if flag_type == 'deliverable':
        from app.modules.core.shared.models import Deliverable
        deliverable = Deliverable.query.get(deliverable_id) if deliverable_id else None
        if not deliverable or deliverable.project_id != project_id:
            return jsonify({'success': False, 'error': 'Pick a deliverable to flag first.'}), 400

    flag = BriefFlag(
        project_id=project_id,
        deliverable_id=deliverable_id or None,
        flag_type=flag_type,
        created_by_id=actor.id,
    )
    db.session.add(flag)
    db.session.flush()
    db.session.add(BriefFlagMessage(flag_id=flag.id, author_id=actor.id, message=message_text))
    db.session.commit()

    notify_cs_of_brief_flag(flag, project, triggered_by=actor)
    log_activity(
        'brief_flag_created', f'{actor.name} raised a {flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/<int:flag_id>/reply', methods=['POST'])
@login_required
def overlay_reply_flag(project_id, flag_id):
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import BriefFlag, BriefFlagMessage
    from app.modules.core.shared.services.notifications import notify_flag_reply
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)
    if flag.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not _can_manage_flags(actor):
        return jsonify({'success': False, 'error': 'You do not have permission to reply to this flag.'}), 403

    data = request.get_json(silent=True) or {}
    message_text = (data.get('message') or '').strip()
    if not message_text:
        return jsonify({'success': False, 'error': 'A message is required.'}), 400

    db.session.add(BriefFlagMessage(flag_id=flag_id, author_id=actor.id, message=message_text))
    db.session.commit()

    notify_flag_reply(flag, project, triggered_by=actor)
    log_activity(
        'brief_flag_reply', f'{actor.name} replied to a flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/<int:flag_id>/resolve', methods=['POST'])
@login_required
def overlay_resolve_flag(project_id, flag_id):
    from datetime import datetime as dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import BriefFlag
    from app.modules.core.shared.services.notifications import notify_cs_of_flag_resolved
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)
    if flag.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not _can_resolve_flag(flag, actor):
        return jsonify({'success': False, 'error': 'Only the person who raised this flag can resolve it.'}), 403
    if flag.is_resolved:
        return jsonify({'success': False, 'error': 'This flag is already resolved.'}), 400

    flag.is_resolved = True
    flag.resolved_at = dt.utcnow()
    flag.resolved_by_id = actor.id
    db.session.commit()

    notify_cs_of_flag_resolved(flag, project, triggered_by=actor)
    log_activity(
        'brief_flag_resolved', f'{actor.name} resolved a {flag.flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/history')
@login_required
def overlay_flags_history(project_id):
    """Lazy-fetched by the History toggle (see project_flags.js) — every
    flag for the requested scope, open and resolved, newest first. scope
    'project' folds in concept/kv too (Details' Flags card is the one home
    for all project-wide flag types); scope 'deliverable' takes an
    optional customer_id so C&CM's per-customer panels only ever see their
    own customer's history, matching the Active view's same scoping."""
    from app.modules.core.shared.models import BriefFlag, Deliverable

    project = Project.query.get_or_404(project_id)
    scope = request.args.get('scope', 'project')

    query = BriefFlag.query.filter_by(project_id=project_id)
    if scope == 'deliverable':
        query = query.filter(BriefFlag.flag_type == 'deliverable')
        customer_id = request.args.get('customer_id', type=int)
        if customer_id:
            deliverable_ids = [
                d.id for d in Deliverable.query.filter_by(
                    project_id=project_id, project_customer_id=customer_id
                ).all()
            ]
            query = query.filter(BriefFlag.deliverable_id.in_(deliverable_ids))
    else:
        query = query.filter(BriefFlag.flag_type.in_(['project', 'concept', 'kv']))

    actor = _get_actor()
    flags = query.order_by(BriefFlag.created_at.desc()).all()
    return jsonify({'flags': [_serialize_flag(f, actor) for f in flags]})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables')
@login_required
def overlay_deliverables(project_id):
    from app.modules.core.shared.models import BriefFlag, Deliverable
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    can_manage = _can_manage_deliverables(project, actor)
    can_manage_flags = _can_manage_flags(actor)
    can_skip_preproduction = _can_skip_preproduction(project, actor)

    # Brief Flags — one query for every open deliverable-scoped
    # flag on the project, then grouped by deliverable_id so both branches
    # below can attach "does this row/customer have open flags" without a
    # query per row. Kept as a plain dict (not a defaultdict) so Jinja's
    # `d.id in open_flags_by_deliverable_id` check works the same way
    # assigned_ids/status_by_id already do elsewhere in this file.
    open_flags = (
        BriefFlag.query
        .filter_by(project_id=project_id, flag_type='deliverable', is_resolved=False)
        .order_by(BriefFlag.created_at)
        .all()
    )
    open_flags_by_deliverable_id = {}
    for f in open_flags:
        f.can_resolve = _can_resolve_flag(f, actor)
        open_flags_by_deliverable_id.setdefault(f.deliverable_id, []).append(f)

    if project.brief_type == 'ccm':
        regions = _build_ccm_deliverable_sections(project)
        has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
        all_customers = [c for r in regions for c in r['customers']]
        first_customer_id = all_customers[0]['project_customer'].id if all_customers else None
        all_deliverables = [d for c in all_customers for d in c['deliverables']]
        # Needs Attention is scoped per customer —
        # each customer only sees flags on its own deliverables, computed
        # here rather than in the template so the CCM and Standard branches
        # can't drift on how "which flags belong to this customer" is worked out.
        for c in all_customers:
            c['open_flags'] = [f for d in c['deliverables'] for f in open_flags_by_deliverable_id.get(d.id, [])]
        return render_template(
            'project_overlay/_deliverables_ccm.html',
            project=project,
            regions=regions,
            all_customers=all_customers,
            all_deliverables=all_deliverables, # flat list — feeds the Skip to Pre-Production picker
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            can_manage_deliverables=can_manage,
            can_skip_preproduction=can_skip_preproduction,
            can_manage_flags=can_manage_flags,
            open_flags_by_deliverable_id=open_flags_by_deliverable_id,
            **_build_deliverable_focus_context(all_deliverables, actor, can_manage),
        )

    deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.id).all()
    return render_template(
        'project_overlay/_deliverables_standard.html',
        project=project,
        deliverables=deliverables,
        can_manage_deliverables=can_manage,
        can_skip_preproduction=can_skip_preproduction,
        can_manage_flags=can_manage_flags,
        open_flags=open_flags,
        open_flags_by_deliverable_id=open_flags_by_deliverable_id,
        **_build_deliverable_focus_context(deliverables, actor, can_manage),
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/edit')
@login_required
def overlay_deliverables_edit(project_id):
    from app.modules.core.shared.models import Deliverable
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    if project.brief_type == 'ccm':
        # Same Region -> Customer grouping as the view mode (overlay_deliverables
        # above) — reusing _build_ccm_deliverable_sections keeps the customer
        # picker's options identical between view and edit, so switching
        # between them never reshuffles which customer is "first".
        regions = _build_ccm_deliverable_sections(project)
        has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
        all_customers = [c for r in regions for c in r['customers']]
        first_customer_id = all_customers[0]['project_customer'].id if all_customers else None
        _annotate_offhour_time([d for c in all_customers for d in c['deliverables']])
        return render_template(
            'project_overlay/_deliverables_ccm_edit.html',
            project=project,
            regions=regions,
            all_customers=all_customers,
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            time_options=DESIGN_DEADLINE_TIME_OPTIONS,
        )

    deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.id).all()
    _annotate_offhour_time(deliverables)
    return render_template(
        'project_overlay/_deliverables_standard_edit.html',
        project=project,
        deliverables=deliverables,
        time_options=DESIGN_DEADLINE_TIME_OPTIONS,
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/save', methods=['POST'])
@login_required
def save_standard_deliverables(project_id):
    """Bulk create/update/delete for the Deliverables editable table — one
    request from Save Deliverables covers every change made since Edit
    Deliverables was opened, committed once. Handles both brief types:
    Standard rows carry no project_customer_id (None); C&CM rows carry one
    per customer panel, and collectAllRows() in project_deliverables_card.js
    gathers every panel's rows into a single payload, so Save always covers
    every customer at once — never just the one selected in the picker.
    Shape borrowed from assign_standard_deliverables_bulk in
    projects_detail.py (loop, single commit, log after) — but this route
    creates/updates/deletes rows rather than assigning designers, so it's
    new rather than reused outright."""
    from datetime import datetime as dt
    from app.modules.core.shared.models import Deliverable
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import request, jsonify, session

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    rows = data.get('deliverables') or []

    # Valid customer ids for this project — a row claiming a
    # project_customer_id that isn't actually one of this project's
    # customers falls back to None rather than being trusted outright.
    valid_customer_ids = {pc.id for pc in project.project_customers}

    def parse_date(val):
        if not val:
            return None
        try:
            return dt.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            return None

    def parse_time(val):
        if not val:
            return None
        try:
            return dt.strptime(val, '%H:%M').time()
        except ValueError:
            return None

    def parse_customer_id(val):
        try:
            val = int(val)
        except (TypeError, ValueError):
            return None
        return val if val in valid_customer_ids else None

    created, updated, deleted = [], [], []

    for row in rows:
        row_id = row.get('id')

        if row_id and row.get('deleted'):
            deliverable = Deliverable.query.filter_by(id=row_id, project_id=project_id).first()
            if deliverable:
                deleted.append(deliverable.name)
                db.session.delete(deliverable)
            continue

        name = (row.get('name') or '').strip()
        if not name:
            continue # a blank row that was never filled in — skip it rather than fail the whole save

        design_deadline = parse_date(row.get('design_deadline'))
        design_deadline_time = parse_time(row.get('design_deadline_time'))
        teams = ','.join(row.get('teams') or [])

        if row_id:
            deliverable = Deliverable.query.filter_by(id=row_id, project_id=project_id).first()
            if not deliverable:
                continue
            deliverable.name = name
            deliverable.design_deadline = design_deadline
            deliverable.design_deadline_time = design_deadline_time
            deliverable.teams = teams
            updated.append(deliverable.name)
        else:
            deliverable = Deliverable(
                project_id=project_id,
                project_customer_id=parse_customer_id(row.get('project_customer_id')),
                deliverable_type_id=None,
                name=name,
                design_deadline=design_deadline,
                design_deadline_time=design_deadline_time,
                teams=teams,
                status='in_queue',
                created_by=actor,
            )
            db.session.add(deliverable)
            created.append(name)

    # Initial Deadline auto-follows deliverable dates in CREATE MODE only.
    # This same route also backs the
    # LIVE overlay's Save Deliverables, where Initial Deadline
    # may have been deliberately set to something a CS Lead communicated
    # externally and isn't necessarily "whatever the deliverables say" —
    # scoped to project_status == 'draft' so a live project's Save
    # Deliverables keeps behaving exactly as it always has.
    if project.project_status == 'draft':
        _recompute_initial_deadline(project)
    db.session.commit()

    for name in created:
        log_activity('deliverable_created', f'Deliverable "{name}" added to "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    for name in updated:
        log_activity('deliverable_updated', f'Deliverable "{name}" updated on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    for name in deleted:
        log_activity('deliverable_deleted', f'Deliverable "{name}" removed from "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


def _can_write_deliverable_assignment(project, actor, team, target_designer_id, existing_assignment):
    """Who may change one deliverable's Design-phase team assignment, and
    how far. Same set as _can_manage_deliverables (admin/management/CS
    Lead/secondary CS/Project Owner) plus this team's own team lead can
    set it to anyone on the team, or clear it. A plain designer never
    reaches this — see assign_deliverable_team()'s self_toggle branch,
    which is a separate, narrower path that can only ever touch the
    caller's own assignment, never a teammate's."""
    if _can_manage_deliverables(project, actor):
        return True
    if actor.role == 'team_lead' and actor.team == team:
        return True
    return False


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/assign', methods=['POST'])
@login_required
def assign_deliverable_team(project_id):
    """Design-phase team assignment for the Deliverables roster's Team
    column. The roster shows which teams a deliverable NEEDS, but
    DeliverableAssignment had no write path in the overlay (the old detail
    page had this, the overlay never got it back). Two distinct paths:

    - self_toggle: a plain designer's one-click claim/release on their own
      team. Always re-reads the current DB state and only ever touches a
      row where designer_id is already the caller's own id (or creates a
      fresh one) — never overwrites a teammate's assignment, regardless of
      what the client's last-rendered state claimed.
    - designer_id (manage mode, possibly None to clear): CS/Admin/
      Management/Project Owner, or this team's own team lead, setting it
      to anyone on the team, reassigning, or clearing it outright.

    Separate from project_preproduction's assign_stream() — that one
    governs who does the LATER Pre-Production 2D/3D/Technical stream work
    (each stream independently assignable/reassignable there too — see the
    comment above assign_stream()); this one governs
    who's actually doing the EARLIER Design-phase work a deliverable's
    2D/3D/Technical tags say it needs. The same DeliverableAssignment row
    carries straight through from Design into Pre-Production for a given
    team (see assign_stream()'s docstring), so this route is what seeds it
    — assign_stream() just picks up from wherever this one left off, or
    fills it in if Design left it unassigned."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable, DeliverableAssignment, User
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    data = request.get_json(silent=True) or {}
    deliverable_id = data.get('deliverable_id')
    # Normalized defensively — the template always renders a canonical
    # data-team attribute now (see _needed_teams()), but this keeps a
    # stray '2d'/'technical' from a stale cached page or a direct API
    # call from silently creating a second, differently-cased
    # DeliverableAssignment row for the same team.
    team = _canonical_team(data.get('team'))
    deliverable = Deliverable.query.get(deliverable_id) if deliverable_id else None
    if not deliverable or deliverable.project_id != project_id or not team:
        return jsonify({'success': False, 'error': 'Could not find that deliverable.'}), 400

    existing = DeliverableAssignment.query.filter_by(
        deliverable_id=deliverable.id, team=team
    ).first()

    if data.get('self_toggle'):
        if actor.role != 'designer' or actor.team != team:
            return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403
        if existing and existing.designer_id == actor.id:
            db.session.delete(existing)
            db.session.commit()
            log_activity('deliverable_unassigned',
                         f'{actor.name} removed themself from {team} on "{deliverable.name}" ({project.name})',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
            return jsonify({'success': True, 'designer_id': None})
        if existing:
            # Someone else already claimed it since this button last
            # rendered — self_toggle can never steal another designer's
            # assignment, only ever the caller's own.
            return jsonify({
                'success': False,
                'error': f'{existing.designer.name} is already assigned to {team} on this deliverable.',
            }), 409
        db.session.add(DeliverableAssignment(
            deliverable_id=deliverable.id, team=team,
            designer_id=actor.id, assigned_by_id=actor.id,
        ))
        db.session.commit()
        log_activity('deliverable_assigned',
                     f'{actor.name} assigned themself to {team} on "{deliverable.name}" ({project.name})',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
        return jsonify({'success': True, 'designer_id': actor.id})

    if not _can_write_deliverable_assignment(project, actor, team, None, existing):
        return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403

    raw_designer_id = data.get('designer_id')
    designer_id = int(raw_designer_id) if raw_designer_id else None

    if designer_id is None:
        if existing:
            db.session.delete(existing)
            db.session.commit()
            log_activity('deliverable_unassigned',
                         f'{actor.name} removed the {team} assignment from "{deliverable.name}" ({project.name})',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
        return jsonify({'success': True, 'designer_id': None})

    target = User.query.get(designer_id)
    if not target or target.role not in ('designer', 'team_lead') or target.team != team:
        return jsonify({'success': False, 'error': f'That person is not on the {team} team.'}), 400

    if existing:
        existing.designer_id = designer_id
        existing.assigned_by_id = actor.id
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=deliverable.id, team=team,
            designer_id=designer_id, assigned_by_id=actor.id,
        ))
    db.session.commit()
    log_activity('deliverable_assigned',
                 f'{actor.name} assigned {target.name} to {team} on "{deliverable.name}" ({project.name})',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True, 'designer_id': designer_id})


@project_overlay_bp.route('/projects/<int:project_id>/set-project-owner', methods=['POST'])
@login_required
def set_project_owner(project_id):
    """
    Assigns/reassigns the Project Owner. Gating: Admin, Management, Project's CS lead or the Project Owner themselves.
    
    """
    from app.modules.core.shared.models import Project, User
    from app.modules.core.shared.extensions import db
    from flask import request, jsonify, session
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import create_notification

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


# ── Details tab person-assignment routes ──────────────────────────────────
# reassign_cs_lead / add_secondary_cs / remove_secondary_cs / assign_concept_kv
# / assign_lead below all existed on the pre-redesign detail page
# (app/routes/projects_detail.py, deleted in commit 5a714d4 "Old detail page
# removed") but were never rebuilt here when the new Design > Details tab
# replaced it — project_details_card.js kept POSTing to the same old URLs
# (reassign-cs-lead / secondary-cs / assign-concept-kv / assign-lead) the
# whole time, 404ing on every one of them. The reported symptom was
# "Designers cannot reassign themselves as a lead designer" (console showed
# a 404 on assign-lead specifically) — checking the other three picker/
# button targets in the same file turned up the same gap on all of them,
# not just Design Leads. Recovered from git history
# (`git show 5a714d4^:app/routes/projects_detail.py`) and adapted to this
# file's current conventions: _get_actor() instead of duplicating the
# emulation lookup, JSON error responses everywhere instead of abort() —
# abort(403) would render Flask's HTML 403 page, which is exactly the
# failure mode that made this gap hard to diagnose from the browser
# console in the first place (a non-JSON response into
# `.then(r => r.json())` reads as "SyntaxError: Unexpected token '<'",
# with nothing pointing at the real 404/403 underneath).
@project_overlay_bp.route('/projects/<int:project_id>/reassign-cs-lead', methods=['POST'])
@login_required
def reassign_cs_lead(project_id):
    """CS Lead picker at the top of the Details tab (avatar_picker(
    'cs-lead-picker', ...) in _details_top_cards.html), gated on
    can_reassign_cs_lead = admin/management only — a real ownership
    change, not something a CS/designer/team_lead should trigger on
    someone else's behalf."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import create_notification

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if actor.role not in ('admin', 'management'):
        return jsonify({'success': False, 'error': 'Only admin/management can reassign a CS lead.'}), 403

    new_cs_lead_id = (request.get_json(silent=True) or {}).get('new_cs_lead_id')
    if not new_cs_lead_id:
        return jsonify({'success': False, 'error': 'A new CS lead is required.'}), 400

    new_cs_lead = User.query.get(int(new_cs_lead_id))
    if not new_cs_lead or new_cs_lead.role != 'cs':
        return jsonify({'success': False, 'error': 'CS lead not found.'}), 404

    previous_cs_lead = project.cs_lead
    project.cs_lead_id = new_cs_lead.id
    db.session.commit()

    create_notification(
        recipient=new_cs_lead,
        message=f'You have been assigned as CS lead on "{project.name}" by {actor.name}.',
        notification_type='cs_lead_reassigned',
        project=project,
        triggered_by=actor,
    )
    if previous_cs_lead and previous_cs_lead.id != new_cs_lead.id:
        create_notification(
            recipient=previous_cs_lead,
            message=f'{new_cs_lead.name} has taken over as CS lead on "{project.name}" (reassigned by {actor.name}).',
            notification_type='cs_lead_reassigned',
            project=project,
            triggered_by=actor,
        )

    log_activity(
        'cs_lead_reassigned',
        f'{actor.name} reassigned CS lead on "{project.name}" to {new_cs_lead.name}'
        + (f' (previously {previous_cs_lead.name})' if previous_cs_lead else ''),
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/secondary-cs', methods=['POST'])
@login_required
def add_secondary_cs(project_id):
    """Add a secondary CS. Permission matches _build_details_context's
    can_manage_cs exactly (admin/management, or this project's own CS
    Lead) — NOT the old projects_detail.py version of this route, which
    gated on role_required('admin','cs','management') but then rejected
    any non-lead 'management' user in the body anyway (role_required said
    yes, the manual check said no). The template's picker/remove buttons
    are gated on can_manage_cs today, so the backend needs to agree with
    that gate exactly, not the old file's inconsistent one."""
    from app.modules.core.shared.models import User, ProjectSecondaryCS
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if actor.role not in ('admin', 'management') and actor.id != project.cs_lead_id:
        return jsonify({'success': False, 'error': 'You do not have permission to add a secondary CS.'}), 403

    user_id = request.form.get('user_id', type=int)
    if not user_id:
        return jsonify({'success': False, 'error': 'Please select a CS member.'}), 400

    if user_id == project.cs_lead_id:
        return jsonify({'success': False, 'error': 'The CS lead is already the primary CS on this project.'}), 400

    user = User.query.get(user_id)
    if not user or user.role not in ('cs', 'admin', 'management'):
        return jsonify({'success': False, 'error': 'Only CS & Management members can be added as secondary CS.'}), 400

    if ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first():
        return jsonify({'success': False, 'error': 'Already a secondary CS on this project.'}), 400

    db.session.add(ProjectSecondaryCS(project_id=project_id, user_id=user_id, added_by_id=actor.id))
    db.session.commit()

    log_activity('secondary_cs_added', f'{user.name} added as secondary CS on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/secondary-cs/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_secondary_cs(project_id, user_id):
    """Remove a secondary CS — same permission as add_secondary_cs()
    above. Also clears any ProjectSecondaryCsRegion rows for this person
    (per-region notification subscriptions from the old detail page's own
    UI, which the new overlay never rebuilt a picker for — cleaning them
    up on removal just avoids leaving orphaned subscriptions for someone
    no longer on the project; nothing in the current UI writes new ones)."""
    from app.modules.core.shared.models import User, ProjectSecondaryCS, ProjectSecondaryCsRegion
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if actor.role not in ('admin', 'management') and actor.id != project.cs_lead_id:
        return jsonify({'success': False, 'error': 'You do not have permission to remove a secondary CS.'}), 403

    assignment = ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first()
    if not assignment:
        return jsonify({'success': False, 'error': 'Not a secondary CS on this project.'}), 404

    user = User.query.get(user_id)
    ProjectSecondaryCsRegion.query.filter_by(project_id=project_id, user_id=user_id).delete()
    db.session.delete(assignment)
    db.session.commit()

    log_activity('secondary_cs_removed',
                 f'{user.name if user else "User"} removed as secondary CS on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/assign-concept-kv', methods=['POST'])
@login_required
def assign_concept_kv(project_id):
    """Concept & KV Designer picker on the Details tab
    (avatar_picker('concept-kv-designer-picker', ...)). Admin/management
    can assign anyone; designer/team_lead can only self-claim — matches
    can_manage_concept_kv_full / can_self_claim_concept_kv in
    _build_details_context, which already gates whether this picker even
    renders and what options it offers."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_designer_of_concept_kv_assignment

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    full_control = actor.role in ('admin', 'management')
    self_claim_only = actor.role in ('designer', 'team_lead')
    if not full_control and not self_claim_only:
        return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403

    concept_id = request.form.get('concept_designer_id')
    kv_id = request.form.get('kv_designer_id')

    if self_claim_only:
        if concept_id and int(concept_id) != actor.id:
            return jsonify({'success': False, 'error': 'You can only assign yourself.'}), 403
        if kv_id and int(kv_id) != actor.id:
            return jsonify({'success': False, 'error': 'You can only assign yourself.'}), 403

    if concept_id:
        project.concept_designer_id = int(concept_id)
    if kv_id:
        project.kv_designer_id = int(kv_id)
    db.session.commit()

    if concept_id:
        concept_designer = User.query.get(int(concept_id))
        if concept_designer:
            notify_designer_of_concept_kv_assignment(project, concept_designer, 'Concept', triggered_by=actor)
            log_activity('designer_assigned', f'{concept_designer.name} assigned as Concept designer on "{project.name}"',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    if kv_id:
        kv_designer = User.query.get(int(kv_id))
        if kv_designer:
            notify_designer_of_concept_kv_assignment(project, kv_designer, 'Key Visual', triggered_by=actor)
            log_activity('designer_assigned', f'{kv_designer.name} assigned as KV designer on "{project.name}"',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/assign-lead', methods=['POST'])
@login_required
def assign_lead(project_id):
    """Design Leads per-team picker on the Details tab (`.avatar-picker
    [data-team]` in _details_design_leads.html) — the specific endpoint
    the bug report named ("Designers cannot reassign themselves as a lead
    designer"). See the block comment above
    reassign_cs_lead() for why this and three siblings were all 404ing.

    Ported from the old route with one real fix, not just a straight
    port: the old detail page had a SEPARATE self-assign control that
    posted with no new_designer_id at all, so "new_designer_id present"
    was a reliable proxy for "targeting someone else, not myself". The
    new AvatarPicker always sends a real id, even when the id picked is
    the actor's own — so a straight port of the old "new_designer_id
    present -> must already be the current lead" check would 403 a
    designer trying to claim their own team's UNASSIGNED lead slot,
    reproducing this exact bug under a different name instead of fixing
    it. Fixed by keying off whether the TARGET is the actor themselves,
    not whether an id was sent at all: picking yourself is always allowed
    for your own team (fill an empty slot or take over from someone
    else); picking a specific teammate is a TRANSFER, only allowed for
    the current lead (or admin/management), same restriction the old
    system had.

    ProjectDesigner has no ORM-level unique constraint declared, but
    there's a real one on (project_id, team) in the database — delete the
    existing row and flush before inserting the new one, or the INSERT
    raises a UniqueViolation instead of cleanly replacing it."""
    from app.modules.core.shared.models import User, ProjectDesigner
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_cs_of_lead_change

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    data = request.get_json(silent=True) or {}
    team = (data.get('team') or '').strip()
    raw_target_id = data.get('new_designer_id')

    if not team:
        return jsonify({'success': False, 'error': 'Team is required.'}), 400

    if actor.role in ('designer', 'team_lead') and actor.team != team:
        return jsonify({'success': False, 'error': 'You can only assign yourself to your own team.'}), 403

    target_id = int(raw_target_id) if raw_target_id else actor.id
    is_self = (target_id == actor.id)

    current_assignment = ProjectDesigner.query.filter_by(project_id=project.id, team=team).first()
    previous_designer = current_assignment.designer if current_assignment else None

    if not is_self:
        # Handing the lead role to someone ELSE — only the current lead
        # may do this, unless the actor is admin/management.
        if actor.role not in ('admin', 'management'):
            if not current_assignment or current_assignment.user_id != actor.id:
                return jsonify({'success': False, 'error': 'Only the current lead can transfer ownership.'}), 403
        new_designer = User.query.get(target_id)
        if not new_designer:
            return jsonify({'success': False, 'error': 'Designer not found.'}), 404
        if current_assignment:
            db.session.delete(current_assignment)
            db.session.flush()
        db.session.add(ProjectDesigner(project_id=project.id, user_id=new_designer.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, new_designer, team, triggered_by=actor, previous_designer=previous_designer)
        log_activity('lead_transferred',
                     f'{actor.name} transferred {team} lead to {new_designer.name} on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    else:
        # Self-claim/takeover — always allowed for the actor's own team,
        # whether the slot is empty or currently held by someone else.
        if current_assignment:
            db.session.delete(current_assignment)
            db.session.flush()
        db.session.add(ProjectDesigner(project_id=project.id, user_id=actor.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, actor, team, triggered_by=actor, previous_designer=previous_designer)
        action = 'lead_transferred' if previous_designer else 'lead_assigned'
        description = (
            f'{actor.name} took over as {team} lead on "{project.name}" (previously {previous_designer.name})'
            if previous_designer
            else f'{actor.name} self-assigned as {team} lead on "{project.name}"'
        )
        log_activity(action, description, user=actor,
                     entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions')
@login_required
def overlay_submissions(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if project.brief_type != 'ccm':
        resolved = _resolve_submission_scope(project, 'ckv')
        draft_context = _build_draft_card_context(project, actor, resolved)
        return render_template(
            'project_overlay/_submissions_standard.html',
            project=project, scope='ckv', customer_id=None,
            **draft_context
        )

    regions = _build_submission_regions(project)
    brief_sections = {r['key']: r['customers'] for r in regions}
    ensure_posm_channels(project, brief_sections)

    has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
    all_customers = [c for r in regions for c in r['customers']]
    show_ckv = bool(project.has_concept or project.has_kv)

    return render_template(
        'project_overlay/_submissions_ccm.html',
        project=project,
        regions=regions,
        has_gulf_regions=has_gulf_regions,
        default_region_key=regions[0]['key'] if regions else None,
        default_customer_id=all_customers[0].id if all_customers else None,
        show_ckv=show_ckv,
        # Nothing to pick from the scope dropdown yet — no customers added
        # and no Concept/KV — so there's nothing Submissions can show.
        # Template swaps in an empty-state message instead of a dead dropdown.
        has_any_scope=bool(show_ckv or all_customers),
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/content')
@login_required
def overlay_submissions_content(project_id):
    from app.modules.core.shared.models import ProjectCustomer
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    scope = request.args.get('scope', 'ckv')
    customer_id = request.args.get('customer_id', type=int)

    if scope == 'ckv':
        label = 'Concept & KV'
    else:
        pc = ProjectCustomer.query.filter_by(id=customer_id, project_id=project_id).first() if customer_id else None
        label = pc.customer.name if pc else 'Unknown'

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft_context = _build_draft_card_context(project, actor, resolved)

    return render_template(
        'project_overlay/_submissions_draft_card.html',
        project=project, label=label, scope=scope, customer_id=customer_id,
        **draft_context
    )

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/upload', methods=['POST'])
@login_required
def overlay_submissions_upload(project_id):
    """
    Add a file to a Draft submission's local cache (NOT the NAS — see
    app/submission_cache.py). Creates the draft ProjectSubmission itself
    on the very first file if one doesn't exist yet for this scope; every
    subsequent file for the same scope attaches to that same draft as
    another ProjectSubmissionFile row, storage_location='cache'.

    filename/original_filename/file_type on the new draft row are set to
    a 'draft' placeholder — there's no single canonical name to give the
    submission until Submit to Client actually builds the zip and computes
    the real one (see the zip-naming design note in the workflow doc).

    The first file uploaded into a brand-new draft is automatically
    flagged is_main_deck — see ProjectSubmissionFile.is_main_deck's
    comment in app/models/__init__.py for the reasoning.
    """
    from app.modules.core.shared.models import ProjectSubmission, ProjectSubmissionFile
    from app.modules.projects.lib.submission_cache import cache_submission_file
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    allowed = {'pdf', 'pptx', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'ai', 'psd', 'zip'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'success': False, 'error': f'File type .{ext} is not supported'}), 400

    scope = request.form.get('scope', 'ckv')
    customer_id = request.form.get('customer_id', type=int)
    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft:
        # Deactivate any previous active DRAFT-cycle submission for this scope
        # (draft / internal_review / internal_revision) — NEVER the sent deck.
        # A Sent-to-Client submission stays is_active so it can coexist with a
        # new working draft: the sent deck shows as the "Submitted to Client"
        # indicator on the Current tab while the next draft is worked. Since
        # _get_active_draft already returned None here, this is normally a
        # no-op, but it keeps the "one active draft per scope" invariant for
        # reopen paths.
        previous = ProjectSubmission.query.filter_by(
            project_id=project.id,
            phase=resolved['phase'],
            posm_country=resolved['posm_country'],
            posm_customer_id=resolved['posm_customer_id'],
            is_active=True,
        ).filter(
            ProjectSubmission.workflow_status.in_(['draft', 'internal_review', 'internal_revision'])
        ).first()
        if previous:
            previous.is_active = False

        draft = ProjectSubmission(
            project_id=project.id,
            filename='draft',
            original_filename='draft',
            file_type='draft',
            uploaded_by_id=actor.id,
            is_active=True,
            phase=resolved['phase'],
            posm_country=resolved['posm_country'],
            posm_customer_id=resolved['posm_customer_id'],
            workflow_status='draft',
        )
        db.session.add(draft)
        db.session.flush() # need draft.id before caching the file under it

    file_bytes = file.read()
    local_path = cache_submission_file(project.id, draft.id, file_bytes, file.filename)

    existing_count = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).count()

    draft_file = ProjectSubmissionFile(
        submission_id=draft.id,
        project_id=project.id,
        original_filename=file.filename,
        file_type=ext,
        uploaded_by_id=actor.id,
        storage_location='cache',
        local_cache_path=local_path,
        is_main_deck=(existing_count == 0),
    )
    db.session.add(draft_file)
    db.session.commit()

    log_activity('submission_draft_file_added',
                 f'{actor.name} added "{file.filename}" to the draft submission for "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'submission_id': draft.id,
        'file': {
            'id': draft_file.id,
            'original_filename': draft_file.original_filename,
            'file_type': draft_file.file_type,
            'is_main_deck': draft_file.is_main_deck,
            'uploaded_by': actor.name,
        }
    })

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/file/<int:file_id>/remove', methods=['POST'])
@login_required
def overlay_submissions_remove_draft_file(project_id, file_id):
    """
    Remove a single file from a Draft submission's local cache.

    Non-main-deck files delete immediately — nothing else to resolve.

    The main-deck file is special: removing it while OTHER cached files still
    exist would leave the draft with no canonical file to auto-name at zip
    time, so this is gated. The caller must resolve it in the SAME request,
    either by:
      - 'new_main_deck_file_id' — promote an existing other cached file, or
      - 'file' — upload a brand-new file, which becomes the new main deck.
    Neither present -> nothing is deleted, we return 409 with the list of
    other files so the frontend can prompt the designer to choose.

    If the main-deck file is the ONLY file left, it deletes freely and the
    draft goes back to empty — if the file is solo, it reverts to an empty
    draft.
    """
    from app.modules.core.shared.models import ProjectSubmissionFile
    from app.modules.projects.lib.submission_cache import cache_submission_file, delete_cached_file
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    target = ProjectSubmissionFile.query.filter_by(
        id=file_id, project_id=project.id, storage_location='cache'
    ).first_or_404()

    submission_id = target.submission_id
    siblings = ProjectSubmissionFile.query.filter(
        ProjectSubmissionFile.submission_id == submission_id,
        ProjectSubmissionFile.storage_location == 'cache',
        ProjectSubmissionFile.id != target.id,
    ).all()

    if target.is_main_deck and siblings:
        new_main_deck_file_id = request.form.get('new_main_deck_file_id', type=int)
        new_file = request.files.get('file')

        if not new_main_deck_file_id and not new_file:
            return jsonify({
                'success': False,
                'error': 'main_deck_replacement_required',
                'other_files': [
                    {'id': f.id, 'original_filename': f.original_filename}
                    for f in siblings
                ],
            }), 409

        if new_main_deck_file_id:
            promoted = next((f for f in siblings if f.id == new_main_deck_file_id), None)
            if not promoted:
                return jsonify({'success': False, 'error': 'new_main_deck_file_id not found in this draft'}), 400
            promoted.is_main_deck = True
        else:
            allowed = {'pdf', 'pptx', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'ai', 'psd', 'zip'}
            ext = new_file.filename.rsplit('.', 1)[-1].lower() if '.' in new_file.filename else ''
            if ext not in allowed:
                return jsonify({'success': False, 'error': f'File type .{ext} is not supported'}), 400
            file_bytes = new_file.read()
            local_path = cache_submission_file(project.id, submission_id, file_bytes, new_file.filename)
            promoted = ProjectSubmissionFile(
                submission_id=submission_id,
                project_id=project.id,
                original_filename=new_file.filename,
                file_type=ext,
                uploaded_by_id=actor.id,
                storage_location='cache',
                local_cache_path=local_path,
                is_main_deck=True,
            )
            db.session.add(promoted)

    removed_name = target.original_filename
    delete_cached_file(target.local_cache_path)
    db.session.delete(target)
    db.session.commit()

    log_activity('submission_draft_file_removed',
                 f'{actor.name} removed "{removed_name}" from the draft submission for "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/file/<int:file_id>/set-main-deck', methods=['POST'])
@login_required
def overlay_submissions_set_main_deck(project_id, file_id):
    """
    Promotes an existing cached file to main deck without removing anything
    — the "Set as Main Deck" button on a non-main-deck row. Demotes whichever
    file currently holds the flag (there's always at most one, so this is a
    simple two-row flip, not a bulk unset).
    """
    from app.modules.core.shared.models import ProjectSubmissionFile
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    target = ProjectSubmissionFile.query.filter_by(
        id=file_id, project_id=project.id, storage_location='cache'
    ).first_or_404()

    if not target.is_main_deck:
        current_main = ProjectSubmissionFile.query.filter_by(
            submission_id=target.submission_id, storage_location='cache', is_main_deck=True
        ).first()
        if current_main:
            current_main.is_main_deck = False
        target.is_main_deck = True
        db.session.commit()

        log_activity('submission_draft_main_deck_changed',
                     f'{actor.name} set "{target.original_filename}" as the main deck for the draft submission on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/submit-for-review', methods=['POST'])
@login_required
def overlay_submissions_submit_for_review(project_id):
    """
    Designer locks in the draft and sends it to CS for internal review —
    covers both the very first submission and every re-submission after an
    Edit or a CS-flagged Internal Revision (same route, same effect: lock,
    log, notify). Deliverable / Concept & KV selection is captured here,
    via the same ProjectSubmissionDeliverable junction the old detail
    page's submit_for_internal_review route already used.

    Body (JSON): scope, customer_id, note (optional), deliverable_ids
    (list — Standard Brief / C&CM customer scope) or includes_concept /
    includes_kv (bool — C&CM's Concept & KV pill only).
    """
    from app.modules.core.shared.models import (Deliverable, ProjectSubmissionDeliverable,
                             ProjectSubmissionEvent, ProjectSubmissionFile)
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.extensions import db
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'designer', 'team_lead'):
        return jsonify({'success': False, 'error': 'You do not have permission to submit this draft.'}), 403
    
    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    note = (data.get('note') or '').strip() or None
    deliverable_ids = data.get('deliverable_ids') or []
    includes_concept = bool(data.get('includes_concept', False))
    includes_kv = bool(data.get('includes_kv', False))

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft = _get_active_draft(project, resolved)
    if not draft:
        return jsonify({'success': False, 'error': 'No active draft to submit.'}), 400

    has_files = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).first() is not None
    if not has_files:
        return jsonify({'success': False, 'error': 'Add at least one file before submitting.'}), 400

    is_ckv_toggle_scope = resolved['phase'] == 'concept_kv' and project.brief_type == 'ccm'
    if is_ckv_toggle_scope:
        if not includes_concept and not includes_kv:
            return jsonify({'success': False, 'error': 'Select Concept and/or KV to include.'}), 400
    elif not deliverable_ids:
        return jsonify({'success': False, 'error': 'Select at least one deliverable to include.'}), 400

    # Clear + relink deliverables — safe to replace, same as the old route
    ProjectSubmissionDeliverable.query.filter_by(submission_id=draft.id).delete()
    for d_id in deliverable_ids:
        deliverable = Deliverable.query.filter_by(id=d_id, project_id=project.id).first()
        if deliverable:
            db.session.add(ProjectSubmissionDeliverable(submission_id=draft.id, deliverable_id=d_id))
            record_deliverable_status(deliverable, 'internal_review', actor)

    draft.includes_concept = includes_concept
    draft.includes_kv = includes_kv
    if is_ckv_toggle_scope:
        if includes_concept and project.has_concept:
            project.concept_status = 'internal_review'
        if includes_kv and project.has_kv:
            project.kv_status = 'internal_review'

    was_reopened = draft.workflow_status in ('internal_review', 'internal_revision')
    draft.workflow_status = 'internal_review'
    draft.is_being_edited = False
    draft.editing_started_at = None

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='submitted_for_review',
        author_id=actor.id, message=note,
    ))

    db.session.commit()

    if project.cs_lead and project.cs_lead.id != actor.id:
        create_notification(
            recipient=project.cs_lead,
            message=(f'"{project.name}" was updated and re-submitted for internal review by {actor.name}'
                      if was_reopened else
                      f'"{project.name}" has been submitted for internal review by {actor.name}'),
            notification_type='internal_review_submitted',
            project=project,
            triggered_by=actor,
        )

    log_activity('internal_review_submitted',
                 f'"{project.name}" submitted for internal review by {actor.name} '
                 f'({len(deliverable_ids)} deliverable(s) included)',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/edit', methods=['POST'])
@login_required
def overlay_submissions_edit_draft(project_id):
    """
    Designer reopens an already-locked (workflow_status='internal_review')
    submission to fix something themselves — requires a reason, logged as
    a ProjectSubmissionEvent, so CS can see what changed and why without
    having to ask. Does NOT touch workflow_status (stays internal_review)
    — is_being_edited is what unlocks the Draft card's file controls again
    (see _build_draft_card_context's is_editable logic). A CS-flagged
    internal_revision needs no equivalent route: it's already editable the
    moment it's flagged, since the flag message itself is the reason.
    """
    from app.modules.core.shared.models import ProjectSubmissionEvent
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.extensions import db
    from datetime import datetime as dt
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'designer', 'team_lead'):
        return jsonify({'success': False, 'error': 'You do not have permission to edit this draft.'}), 403

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'Please provide a reason for editing.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft = _get_active_draft(project, resolved)
    if not draft or draft.workflow_status != 'internal_review':
        return jsonify({'success': False, 'error': 'This draft is not currently locked for review.'}), 400

    draft.is_being_edited = True
    draft.editing_started_at = dt.utcnow()

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='edited',
        author_id=actor.id, message=reason,
    ))
    db.session.commit()

    log_activity('submission_draft_edit_started',
                 f'{actor.name} reopened the locked draft submission on "{project.name}" to fix: {reason}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/flag-internal-revision', methods=['POST'])
@login_required
def overlay_submissions_flag_internal_revision(project_id):
    """
    CS flags the locked submission with a revision note (rich HTML, may
    include inline images via the existing rich-editor.js / /inline-image
    route — same tool flag_submission already uses on the old detail
    page). Sets workflow_status -> internal_revision, which
    _build_draft_card_context treats as immediately editable for the
    designer (no separate "start editing" click needed — the flag message
    IS the reason). Pushes every deliverable included in this submission,
    and concept/KV if included, back into internal_revision status —
    mirrors the old flag_submission route exactly.
    """
    from app.modules.core.shared.models import ProjectSubmissionEvent
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import strip_html, log_activity
    from app.modules.core.shared.extensions import db
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'cs', 'management'):
        return jsonify({'success': False, 'error': 'You do not have permission to flag this submission.'}), 403

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    message = (data.get('message') or '').strip()
    if not message or not strip_html(message).strip():
        return jsonify({'success': False, 'error': 'Please provide a reason for the revision.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft = _get_active_draft(project, resolved)
    if not draft or draft.workflow_status != 'internal_review':
        return jsonify({'success': False, 'error': 'This submission is not currently pending review.'}), 400

    draft.workflow_status = 'internal_revision'
    draft.is_being_edited = False
    draft.editing_started_at = None

    for link in draft.included_deliverables:
        if link.deliverable:
            record_deliverable_status(link.deliverable, 'internal_revision', actor)
    if draft.includes_concept and project.has_concept:
        project.concept_status = 'internal_revision'
    if draft.includes_kv and project.has_kv:
        project.kv_status = 'internal_revision'

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='internal_revision',
        author_id=actor.id, message=message,
    ))
    db.session.commit()

    plain_message = strip_html(message)
    if draft.uploaded_by and draft.uploaded_by.id != actor.id:
        create_notification(
            recipient=draft.uploaded_by,
            message=f'Your submission for "{project.name}" was flagged for internal revision by {actor.name}: {plain_message}',
            notification_type='internal_revision_flagged',
            project=project,
            triggered_by=actor,
        )

    log_activity('internal_revision_flagged',
                 f'Draft submission for "{project.name}" flagged for internal revision by {actor.name}: {plain_message}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

def _canonical_deck_basename(project, resolved):
    """Canonical deck name WITHOUT extension, for a submission's zip object
    and its main-deck member. Mirrors the old projects_submission.py upload
    route's naming branches exactly, keyed off the resolved scope:
      - POSM channel, per-customer: "<Client> - <Project> - <Country> - <Customer> - POSM - <Initial|Revision N>"
      - POSM channel, per-country (legacy whole-region, posm_customer_id NULL): "... - <Country> - POSM - <label>"
      - POSM channel, no country: "... - POSM - <label>" (project.revision_count)
      - C&CM Concept & KV: "<Client> - <Project> - Concept & KV - <Initial|Revision N>" (project.ckv_revision_count)
      - Standard Brief: "<Client> - <Project> - <Initial|Revision N>" (project.revision_count)
    Revision labels read the CURRENT counters — the CS-confirmed counter bump
    lives in the Client Revision flow (revision cycle), not here."""
    import re

    def _sanitize(s):
        return re.sub(r'[\\/:*?"<>|]', '', s or '').strip()

    GULF_REGION_NAMES = {'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar',
                         'bahrain': 'Bahrain', 'oman': 'Oman'}
    client = _sanitize(project.client_brand.name if project.client_brand else 'Client')
    proj = _sanitize(project.name)

    channel = resolved.get('channel')
    if channel is not None:
        country = channel.posm_country or ''
        country_display = GULF_REGION_NAMES.get(country, country.title())
        if channel.posm_customer_id:
            from app.modules.core.shared.models import ProjectCustomer
            pc = ProjectCustomer.query.get(channel.posm_customer_id)
            posm_rev = (pc.posm_revision_count or 0) if pc else 0
            label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            customer = _sanitize(pc.customer.name if (pc and pc.customer) else 'Customer')
            return f'{client} - {proj} - {country_display} - {customer} - POSM - {label}'
        if country:
            counts = project.posm_country_revision_counts or {}
            posm_rev = counts.get(country, 0)
            label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            return f'{client} - {proj} - {country_display} - POSM - {label}'
        is_revised = (project.revision_count or 0) > 0
        label = 'Initial' if not is_revised else f'Revision {project.revision_count}'
        return f'{client} - {proj} - POSM - {label}'

    if project.brief_type == 'ccm':
        ckv_rev = project.ckv_revision_count or 0
        label = 'Initial' if ckv_rev == 0 else f'Revision {ckv_rev}'
        return f'{client} - {proj} - Concept & KV - {label}'

    is_revised = (project.revision_count or 0) > 0
    label = 'Initial' if not is_revised else f'Revision {project.revision_count}'
    return f'{client} - {proj} - {label}'


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/submit-to-client', methods=['POST'])
@login_required
def overlay_submissions_submit_to_client(project_id):
    """
    CS/Management/Admin permanent gate. Everything up to here lived only in
    the local draft cache; this is where the deck becomes real: zip the
    cached files into one archive, upload it to the NAS under the canonical
    deck name, wipe the cache, and advance the submission + project +
    included deliverables to submitted_to_client.

    Standard Brief scope ONLY in this pass (phase='concept_kv', no channel /
    customer). C&CM Concept & KV and UAE/Gulf per-customer POSM scopes are
    the next pass.

    Reuses the transition logic the old projects_submission.py
    submit_to_client route's Standard branch already proved (record_project_
    status, included-deliverable status, revision-count stamping, concept/KV
    advance, notify_of_submission_to_client). The only genuinely new work is
    the cache -> zip -> NAS step in front of it — the old flow assumed the
    file was already on the NAS.

    Body (JSON): scope, customer_id (carried for the later C&CM/Gulf pass;
    unused for Standard).
    """
    import re
    from app.modules.core.shared.models import ProjectSubmissionFile, ProjectSubmissionEvent
    from app.modules.core.shared.services.status_tracking import record_deliverable_status, sync_project_pipeline_status
    from app.modules.core.shared.services.notifications import notify_of_submission_to_client
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.projects.lib.submission_cache import build_zip_bytes, clear_submission_cache
    from app.modules.core.shared.services.nas import build_file_path, upload_app_file
    from app.modules.core.shared.extensions import db
    from datetime import datetime as dt
    from flask import jsonify, current_app

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'cs', 'management'):
        return jsonify({'success': False, 'error': 'You do not have permission to submit to client.'}), 403

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    keep_revision_label = bool(data.get('keep_revision_label'))

    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft:
        return jsonify({'success': False, 'error': 'No active submission to send.'}), 400
    if draft.workflow_status != 'internal_review' or draft.is_being_edited:
        return jsonify({'success': False,
                        'error': 'The deck must be in internal review (not mid-edit) before submitting to client.'}), 400

    _sent = _get_sent_submission(project, resolved)

    # "Do not increase revision counter" escape hatch (CS-acknowledged resend,
    # e.g. wrong file attached — not a real content revision). Instead of the
    # normal counter-derived name, reuse the currently-sent deck's own label
    # and tack on an incrementing " (N)" suffix — read off whatever suffix
    # that deck already carries so repeated resends chain (2) -> (3) -> ...
    # rather than colliding with each other. This bypasses the name-collision
    # gate below by construction: the computed name can never match _sent's.
    if keep_revision_label and _sent is not None:
        sent_base = _sent.original_filename.rsplit('.', 1)[0]
        m = re.match(r'^(.*) \((\d+)\)$', sent_base)
        base_name = f'{m.group(1)} ({int(m.group(2)) + 1})' if m else f'{sent_base} (2)'
    else:
        # Gate: don't overwrite the deck already with the client. A second
        # send is allowed only once its canonical name would DIFFER from the
        # sent deck's — which happens after CS requests a Client Revision
        # (that bumps the scope's counter, changing the Initial/Revision-N
        # label). Same name → block, unless the escape hatch above applied.
        if _sent is not None and f'{_canonical_deck_basename(project, resolved)}.zip' == _sent.original_filename:
            return jsonify({'success': False,
                            'error': 'A deck is already with the client for this scope — request a Client Revision first.'}), 400
        base_name = _canonical_deck_basename(project, resolved)

    cached_files = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).order_by(
        ProjectSubmissionFile.is_main_deck.desc(),
        ProjectSubmissionFile.uploaded_at.asc(),
    ).all()
    if not cached_files:
        return jsonify({'success': False, 'error': 'There are no files to send.'}), 400

    main_deck = next((f for f in cached_files if f.is_main_deck), None)
    if not main_deck:
        return jsonify({'success': False, 'error': 'Flag a main deck before submitting.'}), 400

    # ── Canonical naming. base_name was resolved above (either the normal
    # counter-derived name, or the keep-revision-label escape hatch). The
    # zip object on the NAS carries base_name + .zip; INSIDE the zip the
    # main deck takes base_name + its own extension (so member ==
    # original_filename after the rename below), every other file keeps
    # its uploaded name. ──
    main_ext = (main_deck.file_type or main_deck.original_filename.rsplit('.', 1)[-1]).lower()
    main_deck.original_filename = f'{base_name}.{main_ext}'
    zip_name = f'{base_name}.zip'

    # Build the archive from the cache (files still on disk), THEN upload.
    # Only wipe the cache + flip DB state once the NAS write succeeds, so a
    # failed upload leaves the draft fully intact and re-sendable.
    entries = [{'local_cache_path': f.local_cache_path, 'arcname': f.original_filename}
               for f in cached_files]
    zip_bytes = build_zip_bytes(entries)

    nas_folder = build_file_path(project, 'Submissions', zip_name).rsplit('/', 1)[0]
    try:
        upload_app_file(zip_bytes, nas_folder, zip_name)
    except RuntimeError as e:
        current_app.logger.error(
            f'Submit-to-client zip upload failed (project={project_id}, draft={draft.id}): {e}')
        return jsonify({'success': False,
                        'error': 'Could not save the deck to storage. Nothing was sent — please try again.'}), 502

    # NAS write succeeded. Point every file row at the zip (preview/download
    # extract members from it now — see _load_submission_file_bytes) and
    # record the zip as the submission's stored file.
    for f in cached_files:
        f.storage_location = 'nas'
        f.local_cache_path = None
    draft.original_filename = zip_name
    draft.filename = zip_name
    draft.workflow_status = 'sent_to_client'
    draft.submitted_to_client_at = dt.utcnow()
    draft.submitted_by_id = actor.id

    # Supersede the prior sent deck (if any) for this scope — this new revision
    # replaces it as the Submitted-to-Client deck; the old one stays in History.
    # (_sent was fetched above, before the naming branch.)
    if _sent is not None:
        _sent.is_active = False

    # ── Status transitions, by scope. revision_count is deliberately NOT
    # incremented here (only the Client Revision flow does that); included
    # deliverables get the current revision_count stamped by assignment for
    # idempotency across internal-review cycles. ──
    channel = resolved['channel']
    if channel is not None:
        # POSM (UAE/Gulf per-customer) — advance the channel + its included
        # deliverables. The C&CM project aggregate is derived from channel
        # states, so there's nothing to set at the project level here.
        channel.status = 'submitted_to_client'
        for link in draft.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'submitted_to_client', actor)
    elif project.brief_type == 'ccm':
        # C&CM Concept & KV — advance only the concept/KV statuses this draft
        # included; deliverables stay 'briefed' until the POSM stage (mirrors
        # the old submit_to_client C&KV branch).
        if draft.includes_concept and project.has_concept:
            project.concept_status = 'submitted_to_client'
        if draft.includes_kv and project.has_kv:
            project.kv_status = 'submitted_to_client'
    else:
        # Standard Brief — included deliverables (unchanged). Project-level
        # pipeline status is no longer set directly here — see the sync
        # call below, which
        # covers this branch along with the other two.
        is_revised_submission = (project.revision_count or 0) > 0
        included_ids = {link.deliverable_id for link in draft.included_deliverables if link.deliverable_id}
        for deliverable in project.project_deliverables:
            if deliverable.id in included_ids:
                record_deliverable_status(deliverable, 'submitted_to_client', actor)
                if is_revised_submission:
                    deliverable.revision_count = project.revision_count
        if project.concept_status:
            project.concept_status = 'submitted_to_client'
        if project.kv_status:
            project.kv_status = 'submitted_to_client'

    # Project pill is now a pure
    # deliverable roll-up — covers all three branches above uniformly,
    # replacing what used to be a Standard-only direct write here.
    sync_project_pipeline_status(project, actor)

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='submitted_to_client',
        author_id=actor.id, message=None,
    ))
    db.session.commit()

    # Safe to wipe now — the files live in the zip on the NAS.
    clear_submission_cache(project.id, draft.id)

    log_activity('submitted_to_client',
                 f'"{project.name}" submitted to client by {actor.name}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    notify_of_submission_to_client(project, triggered_by=actor)

    client_email = project.client_brand.contact_email if project.client_brand else None
    return jsonify({'success': True, 'client_email': client_email or '', 'project_name': project.name})

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/submit-summary')
@login_required
def overlay_submissions_submit_summary(project_id):
    """
    The deck-summary fragment shown in the modal that opens when CS clicks
    Submit to Client: the COMPLETE deck —
    the deliverables newly going for decision (this draft's included set),
    PLUS the ones already Client-Approved, shown as read-only indicators
    (they ride along in the deck for client-completeness + invoicing, but
    this submission never changes their status). Plus the expected deck
    filename and the files being sent. Scope-aware: Standard, C&CM Concept &
    KV (concept/KV inclusion instead of deliverables), and UAE/Gulf POSM.

    GET, read-only — populates the modal on button click (render-on-demand).
    """
    from app.modules.core.shared.models import ProjectSubmissionFile, Deliverable
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'cs', 'management'):
        return jsonify({'success': False, 'error': 'You do not have permission to submit to client.'}), 403

    scope = request.args.get('scope', 'ckv')
    customer_id = request.args.get('customer_id', type=int)
    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft or draft.workflow_status != 'internal_review' or draft.is_being_edited:
        return jsonify({'success': False,
                        'error': 'The deck must be in internal review (not mid-edit) before submitting to client.'}), 400

    cached_files = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).order_by(
        ProjectSubmissionFile.is_main_deck.desc(),
        ProjectSubmissionFile.uploaded_at.asc(),
    ).all()
    main_deck = next((f for f in cached_files if f.is_main_deck), None)
    if not main_deck:
        return jsonify({'success': False, 'error': 'Flag a main deck before submitting.'}), 400

    # Expected deck filename previewed to CS (the NAS zip object name). This
    # is the DEFAULT name (current revision counters) — if CS ticks "Do not
    # increase revision counter" the actual sent name gets a "(N)" suffix
    # instead (see overlay_submissions_submit_to_client); not recomputed
    # here to avoid duplicating that naming logic in JS.
    expected_filename = f'{_canonical_deck_basename(project, resolved)}.zip'

    # Whether a deck is already Sent to Client for this scope — the "Do not
    # increase revision counter" checkbox only makes sense as a resend
    # against an existing sent deck, so the template only shows it then.
    has_sent_submission = _get_sent_submission(project, resolved) is not None

    # What's going for decision depends on scope. The C&CM concept and KV deck is 
    # concept/KV toggles, not deliverables. Every other scope shows
    # deliverables split into this draft's included set vs already client-approved read
    # only indicators.
    is_ckv_toggle_scope = resolved['phase'] == 'concept_kv' and project.brief_type == 'ccm'
    included = []
    indicators = []
    if not is_ckv_toggle_scope:
        if resolved['phase'] == 'concept_kv':
            scope_deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id=None
            ).order_by(Deliverable.id).all()
        else:
            scope_deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id = resolved['posm_customer_id']
            ).order_by(Deliverable.id).all()
        included_ids = {link.deliverable_id for link in draft.included_deliverables if link.deliverable_id}
        for d in scope_deliverables:
            entry = {'deliverable': d, 'pill': derive_deliverable_status(d)}
            if d.id in included_ids:
                included.append(entry)
            elif d.status == 'approved':
                indicators.append(entry)

    return render_template(
        'project_overlay/_submissions_submit_summary.html',
        project=project, scope=scope, customer_id=customer_id,
        expected_filename=expected_filename,
        files=cached_files, included=included, indicators=indicators,
        is_ckv_toggle_scope=is_ckv_toggle_scope,
        includes_concept=draft.includes_concept, includes_kv=draft.includes_kv,
        has_sent_submission=has_sent_submission,
    )
@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/client-revision', methods=['POST'])
@login_required
def overlay_submissions_client_revision(project_id):
    """
    CS/admin/management requests a client revision on the deck currently with
    the client (the Active-with-Client indicator). Standard Brief scope only in
    this pass — C&CM Concept & KV and UAE/Gulf POSM land next.

    Effect (locked revision-cycle design): bumps project.revision_count (the
    deferred counter bump lives here); moves project + ALL deliverables to In
    Revision (revision_in_queue), stamping each deliverable's revision_count;
    records the client's rich-text message as a 'client_revision'
    ProjectSubmissionEvent on the sent deck (what the "Revision Requested"
    indicator surfaces, and — via the counter bump — what opens the
    Submit-to-Client gate for the next draft); notifies every assigned designer
    (mirrors the old send_revision set). Deliberately does NOT deactivate the
    sent deck — it stays the client record until a new revision actually ships
    (that supersession happens in overlay_submissions_submit_to_client).
    """
    from app.modules.core.shared.models import ProjectSubmissionEvent, ProjectDesigner
    from app.modules.core.shared.services.status_tracking import record_deliverable_status, sync_project_pipeline_status
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import strip_html, log_activity
    from app.modules.core.shared.extensions import db
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'cs', 'management'):
        return jsonify({'success': False, 'error': 'You do not have permission to request a client revision.'}), 403

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    message = (data.get('message') or '').strip()
    if not message or not strip_html(message).strip():
        return jsonify({'success': False, 'error': 'Please describe the revision the client requested.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)

    sent = _get_sent_submission(project, resolved)
    if sent is None:
        return jsonify({'success': False, 'error': 'There is no deck with the client to revise.'}), 400
    if any(e.event_type == 'client_revision' for e in sent.events):
        return jsonify({'success': False, 'error': 'A client revision has already been requested for this deck.'}), 400

    # Scope-branched effect. Standard is whole-project (project.revision_count +
    # project status + ALL deliverables). C&CM Concept & KV and per-customer
    # POSM are PER-SCOPE - they bump only that scope's counter and move only
    # that scope's statuses/deliverables, never the whole project.
    channel = resolved['channel']
    if channel is not None:
        # POSM (UAE/Gulf per-customer) - bump the customer/country counter, move
        # the channel + the sent deck's deliverables into revision. No project-
        # level status (the C&CM aggregate is derived from channel states).
        channel.status = 'revision_in_queue'
        if channel.posm_customer_id:
            from app.modules.core.shared.models import ProjectCustomer
            pc = ProjectCustomer.query.get(channel.posm_customer_id)
            new_rev = ((pc.posm_revision_count or 0) + 1) if pc else 1
            if pc:
                pc.posm_revision_count = new_rev
        elif channel.posm_country:
            counts = dict(project.posm_country_revision_counts or {})
            counts[channel.posm_country] = counts.get(channel.posm_country, 0) + 1
            project.posm_country_revision_counts = counts
            new_rev = counts[channel.posm_country]
        else:
            new_rev = (project.revision_count or 0) + 1
            project.revision_count = new_rev
        for link in sent.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'revision_in_queue', actor)
                link.deliverable.revision_count = new_rev
        rev_label = f'#{new_rev}'
    elif project.brief_type == 'ccm':
        # C&CM Concept & KV - bump the C&KV counter and move only the concept/KV
        # statuses the sent deck included. Deliverables are untouched (they stay
        # briefed until the POSM stage), matching the C&KV submit-to-client branch.
        project.ckv_revision_count = (project.ckv_revision_count or 0) + 1
        if sent.includes_concept and project.has_concept:
            project.concept_status = 'revision_in_queue'
        if sent.includes_kv and project.has_kv:
            project.kv_status = 'revision_in_queue'
        rev_label = f'#{project.ckv_revision_count}'
    else:
        # Standard Brief - whole project + all deliverables. Project-level
        # pipeline status is no longer set directly here — see the sync
        # call below.
        project.revision_count = (project.revision_count or 0) + 1
        for deliverable in project.project_deliverables:
            record_deliverable_status(deliverable, 'revision_in_queue', actor)
            deliverable.revision_count = project.revision_count
        rev_label = f'#{project.revision_count}'

    # Project pill is now a pure
    # deliverable roll-up — covers all three branches above uniformly. A
    # revision reverts the affected deliverable(s) back to "In Design", so
    # this can revert a project that was already reading Pre-Production/
    # Handed to Production back to In Design too, same rule either
    # direction. Reverting doesn't erase the earlier client-approval
    # timestamp — see status_tracking.py's project_client_approved_at().
    sync_project_pipeline_status(project, actor)

    db.session.add(ProjectSubmissionEvent(
        submission_id=sent.id, event_type='client_revision',
        author_id=actor.id, message=message,
    ))
    db.session.commit()

    for assignment in ProjectDesigner.query.filter_by(project_id=project.id).all():
        if assignment.designer and assignment.designer.id != actor.id:
            create_notification(
                recipient=assignment.designer,
                message=f'Client revision {rev_label} requested on "{project.name}" by {actor.name}.',
                notification_type='revision_requested',
                project=project,
                triggered_by=actor,
            )

    log_activity('revision_requested',
                 f'Client revision {rev_label} requested on "{project.name}" by {actor.name}: {strip_html(message)[:100]}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/approve', methods=['POST'])
@login_required
def overlay_submissions_approve(project_id):
    """
    CS/admin/management approves some or all of the deck currently Submitted
    to Client (the same indicator Client Revision acts on — the two are
    mutually exclusive; see can_mark_approved in _build_draft_card_context).

    Partial approval is the actual point of this route, not an edge case:
    some deliverables can clear into Pre-Production while others stay in
    design (per-deliverable is the model, gating at
    the project level would bottleneck).

    Body (JSON): scope, customer_id, deliverable_ids (optional list —
    omitted/None = approve everything still pending in this deck; an empty
    list is treated as "nothing selected" and rejected, not silently read as
    "approve everything", since the picker defaults to all-selected and an
    empty array means CS deliberately unchecked every item). C&CM Concept &
    KV has no deliverable list — always approved as a pair. note (optional
    string) — CS's freeform note about this approved batch, for the future
    Pre-Production tab (see ProjectSubmissionEvent/ProjectSubmissionEvent
    Deliverable below).

    Ports the old projects_approval.py approve_submission's proven cascade
    logic (channel/project only flips to fully approved once EVERY
    deliverable in that channel/project — not just this deck's — is
    approved) into the overlay's scope-resolved shape, mirroring
    overlay_submissions_client_revision. "Fully approved" no longer gets
    its own pill label anywhere (the project pill reads Pre-Production at
    this point; a channel's own per-customer row reads the same), but the
    moment itself is still real and still
    timestamped, non-destructively, via ProjectStatusLog.
    """
    from app.modules.core.shared.models import Deliverable, ProjectPosmChannel, ProjectSubmissionEvent, ProjectSubmissionEventDeliverable
    from app.modules.core.shared.services.status_tracking import record_deliverable_status, sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_preproduction_needs
    from app.modules.core.shared.services.notifications import notify_of_project_approved
    from app.modules.core.shared.services.achievements import check_achievements
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.extensions import db
    from datetime import datetime as dt
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'cs', 'management'):
        return jsonify({'success': False, 'error': 'You do not have permission to approve this submission.'}), 403

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    deliverable_ids = data.get('deliverable_ids')
    note = (data.get('note') or '').strip()
    # None (key omitted) -> approve everything pending. A present-but-empty
    # list is a deliberate "nothing selected" and gets rejected below, not
    # folded into the "approve everything" default via truthiness. Cast to
    # int explicitly — DeliverablePicker.getSelectedIds() reads them off
    # dataset.deliverableId, so they arrive as strings; comparing those
    # against Deliverable.id (int) in a plain Python set/`in` check would
    # silently never match without this (unlike a SQLAlchemy filter_by,
    # which coerces the type for you at the DB layer).
    deliverable_id_set = None
    if deliverable_ids is not None:
        try:
            deliverable_id_set = {int(i) for i in deliverable_ids}
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid deliverable selection.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)

    sent = _get_sent_submission(project, resolved)
    if sent is None:
        return jsonify({'success': False, 'error': 'There is no deck with the client to approve.'}), 400
    if any(e.event_type == 'client_revision' for e in sent.events):
        return jsonify({'success': False,
                        'error': 'A client revision is already pending on this deck — nothing to approve.'}), 400

    now = dt.utcnow()
    all_approved = False # whether this call cascaded all the way to project-approved
    channel = resolved['channel']
    approved_deliverables_this_call = [] # feeds the client_approval event's deliverable links below

    if channel is not None:
        # ── POSM (UAE/Gulf per-customer) ────────────────────────────────
        if channel.status == 'approved':
            return jsonify({'success': False, 'error': 'This channel is already approved.'}), 400

        pending = [
            link.deliverable for link in sent.included_deliverables
            if link.deliverable and link.deliverable.status != 'approved'
            and (deliverable_id_set is None or link.deliverable.id in deliverable_id_set)
        ]
        if deliverable_id_set is not None and not pending:
            return jsonify({'success': False, 'error': 'Select at least one deliverable to approve.'}), 400
        for d in pending:
            record_deliverable_status(d, 'approved', actor)
            # Auto-flag Pre-Production streams the moment a deliverable is
            # client-approved — no separate manual step (see
            # status_vocabulary.py's derive_preproduction_needs).
            d.needs_2d, d.needs_3d, d.needs_technical = derive_preproduction_needs(d)
        approved_deliverables_this_call = pending

        # Cascade to channel approval only once EVERY deliverable belonging to
        # this channel's customer(s) is approved — not just this deck's set —
        # same rule the old approve_submission used. UAE channels track one
        # specific customer; Gulf channels cover every customer in the region.
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

            # Cascade further: only once EVERY channel + C&KV (if applicable)
            # is done does the whole project become fully approved (project
            # pill reads Pre-Production at that point — see the comment
            # above sync_project_pipeline_status() below).
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
                    all_approved = True

    elif project.brief_type == 'ccm':
        # ── C&CM Concept & KV — approved as a pair, no partial split; it
        # doesn't feed Pre-Production the way deliverables do, so there's
        # nothing to gain from splitting it. ──
        if project.concept_status == 'approved' and project.kv_status == 'approved':
            return jsonify({'success': False, 'error': 'Concept & KV is already approved.'}), 400
        if project.has_concept:
            project.concept_status = 'approved'
        if project.has_kv:
            project.kv_status = 'approved'
        project.concept_approved_at = now
        project.concept_approved_by_id = actor.id

        # Cascade only once customers/channels exist — a C&KV-only brief with
        # none yet just sits approved (no forced next-step prompt, unlike the
        # old flow's add-POSM/pause/approve branch; CS adds POSM whenever
        # it's ready).
        all_channels = ProjectPosmChannel.query.filter_by(project_id=project.id).all()
        if all_channels and all(c.status == 'approved' for c in all_channels):
            project.approved_at = now
            project.approved_by_id = actor.id
            all_approved = True

    else:
        # ── Standard Brief ─────────────────────────────────────────────
        if project.project_status == 'approved':
            return jsonify({'success': False, 'error': 'This project is already approved.'}), 400

        pending = [
            d for d in project.project_deliverables
            if d.status != 'approved' and (deliverable_id_set is None or d.id in deliverable_id_set)
        ]
        if deliverable_id_set is not None and not pending:
            return jsonify({'success': False, 'error': 'Select at least one deliverable to approve.'}), 400
        for d in pending:
            record_deliverable_status(d, 'approved', actor)
            # Auto-flag Pre-Production streams the moment a deliverable is
            # client-approved — no separate manual step (see
            # status_vocabulary.py's derive_preproduction_needs).
            d.needs_2d, d.needs_3d, d.needs_technical = derive_preproduction_needs(d)
        approved_deliverables_this_call = pending

        if all(d.status == 'approved' for d in project.project_deliverables):
            project.approved_at = now
            project.approved_by_id = actor.id
            all_approved = True
            if project.concept_status:
                project.concept_status = 'approved'
            if project.kv_status:
                project.kv_status = 'approved'

    # Project pill is now a pure
    # deliverable roll-up, independent of the ckv_gate/all_approved logic
    # above — Concept/KV approval isn't a deliverable, so it no longer
    # blocks the pill the way it still blocks the "officially approved"
    # notification/timestamp (all_approved, read below by
    # notify_of_project_approved/check_achievements). Covers all three
    # branches above uniformly.
    sync_project_pipeline_status(project, actor)

    # Batch note — always log an
    # event for this approval action, even with an empty note, so the deck's
    # timeline has a complete record of who approved what and when; the
    # Pre-Production tab reads client_approval events + their deliverable
    # links to show CS's notes against the deliverables they cover. C&CM
    # Concept & KV has no deliverable_links (nothing to attach), same as
    # every other event-deliverable link on the CKV path.
    approval_event = ProjectSubmissionEvent(
        submission_id=sent.id, event_type='client_approval',
        author_id=actor.id, message=note or None,
    )
    db.session.add(approval_event)
    db.session.flush() # need approval_event.id for the link rows below
    for d in approved_deliverables_this_call:
        db.session.add(ProjectSubmissionEventDeliverable(event_id=approval_event.id, deliverable_id=d.id))

    db.session.commit()

    log_activity(
        'project_approved' if all_approved else 'deliverables_approved',
        f'"{project.name}" approved by {actor.name}' if all_approved
        else f'Deliverables partially approved on "{project.name}" by {actor.name}',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    if all_approved:
        notify_of_project_approved(project, triggered_by=actor)
        check_achievements(actor, 'project_approved')

    return jsonify({'success': True, 'all_approved': all_approved})


# ─────────────────────────────────────────────────────────────────────────
# Reference Files — upload / download / preview / delete
#
# WHAT: these five routes originally lived on the old /projects/<id> detail
# page's blueprint (detail_bp, projects_detail.py). The overlay's own
# Reference Files card (_details_reference_files.html + project_details_card.js)
# has depended on them since the overlay shipped — project_details_card.js's
# upload/delete fetch() calls hardcode these exact URL paths, and the
# template's preview/download/download-all buttons use url_for() against
# them — so they were never actually dead code, just misplaced on the page
# that's being deleted at cutover.
#
# HOW: moved verbatim — same URL paths, same function bodies, same
# permission checks — onto project_overlay_bp instead of detail_bp. Because
# the URL paths are unchanged, project_details_card.js's hardcoded fetch()
# calls need zero changes. Only _details_reference_files.html's three
# url_for('project_detail.X', ...) calls needed repointing to
# url_for('project_overlay.X', ...), since the blueprint/endpoint name
# changed even though the path didn't.
#
# WHY here, not a new file: Reference Files is part of the Details tab,
# which already lives entirely in this blueprint — keeping the file-serving
# routes next to the rest of Details avoids a fourth blueprint for five
# routes that only ever serve this one card.
# ─────────────────────────────────────────────────────────────────────────

@project_overlay_bp.route('/projects/<int:project_id>/upload-file', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def upload_project_file(project_id):
    """Handle reference file uploads for a project. CS and admin only."""
    from app.modules.core.shared.models import ProjectFile, User
    from flask import session, current_app

    project = Project.query.get_or_404(project_id)
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    can_manage_files = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in {a.user_id for a in project.secondary_cs_assignments}
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    if not can_manage_files:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 403

    # Check a file was actually included in the request
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Only allow safe file types
    allowed_extensions = {'jpg', 'jpeg', 'png', 'pdf', 'docx', 'xlsx', 'pptx', 'zip', 'dwg',
                          'mp4', 'mov', 'avi', 'webm', 'mkv', 'wmv', 'm4v'}
    original_filename = file.filename
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''

    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400

    # Read file bytes before anything else (file stream can only be read once)
    file_bytes = file.read()

    # Upload directly to NAS - synchronous, user waits for confirmation
    from app.modules.core.shared.services.nas import upload_app_file, build_file_path
    nas_file_path = build_file_path(project, 'Reference Files', original_filename)
    nas_folder = nas_file_path.rsplit('/',1)[0]
    try:
        upload_app_file(file_bytes, nas_folder, original_filename)
    except RuntimeError as e:
        current_app.logger.error(f'Reference file upload failed for project {project_id}: {e}')
        return jsonify({'success': False, 'error': 'File could not be saved to storage. Please try again.'}), 502

    # Save record - Filename column stores the NAS filename (Same as original)
    project_file = ProjectFile(
        project_id=project_id,
        filename=original_filename,
        original_filename=original_filename,
        file_type=ext,
        uploaded_by_id=actor.id
    )

    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity, file_type_label
    db.session.add(project_file)
    db.session.commit()

    log_activity('file_uploaded', f'{current_user.name} added {file_type_label(ext)} as a reference file to "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'file': {
            'id': project_file.id,
            'original_filename': original_filename,
            'file_type': ext,
            'uploaded_by': actor.name
        }
    })


@project_overlay_bp.route('/projects/files/<int:file_id>/download')
@login_required
def download_project_file(file_id):
    """Serve a reference file for download. All authenticated users can download. Download is served from the NAS"""
    from app.modules.core.shared.models import ProjectFile
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    import io
    from flask import send_file, current_app

    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Reference file download failed (file_id={file_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)

    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=project_file.original_filename
    )


@project_overlay_bp.route('/projects/<int:project_id>/reference-files/download-all')
@login_required
def download_all_reference_files(project_id):
    """Zips every reference file for this project and returns a download link."""
    from app.modules.core.shared.lib.zip_utils import build_zip
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from flask import url_for as _url_for

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
            continue # skip a file that failed to fetch rather than failing the whole zip

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
    return jsonify({'success': True, 'download_url': _url_for('api.zip_download', zip_id=zip_id)})


@project_overlay_bp.route('/projects/files/<int:file_id>/preview')
@login_required
def preview_project_file(file_id):
    """Serve a reference file for inline browser preview. Only file types a
    browser can actually render natively are supported — PDFs and common
    image formats. Anything else (.ai, .psd, .docx, etc.) returns a clear
    'no preview available' response so the frontend can fall back to
    download-only, rather than trying to force something that can't work."""
    from app.modules.core.shared.models import ProjectFile
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from flask import send_file, jsonify, current_app
    import io

    # Maps a stored file extension to the mimetype the browser needs to
    # render it inline. Anything not in here just isn't previewable.
    PREVIEWABLE_TYPES = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
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
        }), 415 # Unsupported Media Type

    project = Project.query.get(project_file.project_id)
    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Reference file preview failed (file_id={file_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading it instead.'
        }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=project_file.original_filename
    )


@project_overlay_bp.route('/projects/files/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_project_file(file_id):
    """Delete a reference file. Admin/Management (any project), this project's CS lead/secondary CS, or this projects project owner"""
    from app.modules.core.shared.models import ProjectFile, User
    from flask import session

    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    can_manage_files = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in {a.user_id for a in project.secondary_cs_assignments}
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    if not can_manage_files:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 403

    # Delete from NAS
    from app.modules.core.shared.services.nas import delete_app_file, build_file_path
    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    delete_app_file(nas_path)

    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    log_activity('file_deleted', f'{actor.name} removed a reference file from "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    db.session.delete(project_file)
    db.session.commit()

    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────────────────
# Job number generation
#
# Originally lived on projects_brief.py's brief_bp (the old briefing page's
# blueprint). Per that route's own comment: "only real consumer of this
# route is project creation (grep confirms: legacy create.html and the new
# create-mode overlay, project_overlay_create.js)" — legacy
# create.html is deleted, project_overlay_create.js (line ~212,
# fetch('/projects/generate-job-number')) is the one live caller left, so
# it comes here rather than dying with the rest of brief_bp.
#
# NOTE (carried over, not fixed here): this still uses the non-atomic
# MAX(job_number)+1 pattern — the atomic fix
# (job_number_seq.nextval()) as separate work, not yet wired up. Out of
# scope here; moved verbatim.
# ─────────────────────────────────────────────────────────────────────────

@project_overlay_bp.route('/projects/generate-job-number', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management', 'project_owner')
def generate_job_number():
    FOC_PAD = 3 # Digits: 3 -> FOC-001 ... FOC-999. Change to 4 for FOC-1000+

    #Pull all existing FOC job numbers from the DB
    existing = Project.query.with_entities(Project.job_number).filter(
        Project.job_number.like('FOC-%')
    ).all()

    # Parse the numeric suffix from each, collect into a list
    used_numbers = []
    for (jn,) in existing:
        suffix = jn[4:] # strip 'FOC- prefix
        if suffix.isdigit():
            used_numbers.append(int(suffix))

    # Next number is max +1, or 1 if none exist yet
    next_num = (max(used_numbers) + 1) if used_numbers else 1
    job_number = 'FOC-' + str(next_num).zfill(FOC_PAD)

    return jsonify({'job_number': job_number})


# ─────────────────────────────────────────────────────────────────────────
# Submission file serving — download/preview
#
# WHAT: these four routes + their shared helper originally lived on
# projects_submission.py (submission_bp), the designer-side upload/submit
# blueprint that predates the overlay's own Submissions tab. Auditing that
# found the other 9 routes there (upload, submit-for-review,
# flag, submit-to-client, add-file, download-all, send-revision,
# start-revision, delete-file) have zero live callers anymore — all
# superseded by the overlay's own overlay/submissions/* routes. These 4
# are the exception: _submissions_draft_card.html still
# hardcodes url_for('submission.download_submission'/'preview_submission'/
# 'download_submission_file'/'preview_submission_file', ...) for its
# preview/download buttons on both the active deck and submission history.
#
# HOW: moved verbatim — same URL paths, same function bodies, same
# permission checks (all four were @login_required only, no role gate, in
# the original) — onto project_overlay_bp instead of submission_bp. Because
# the paths are unchanged, only the four url_for('submission.X', ...) call
# sites in _submissions_draft_card.html needed repointing to
# url_for('project_overlay.X', ...) — the blueprint/endpoint name changed,
# the path didn't. download_submission_file() relied on ProjectSubmission
# File/send_file being available at projects_submission.py's module top
# level; that module-level import doesn't exist here, so it picked up an
# explicit local import it didn't need before (caught before shipping, same
# class of mistake as upload_project_file's missing User import).
#
# WHY here, not a new file: Submissions is part of the same overlay these
# other file-serving routes (Reference Files) already live next
# to — one blueprint for the overlay's file-serving surface, not a fifth
# blueprint for four routes.
# ─────────────────────────────────────────────────────────────────────────

@project_overlay_bp.route('/projects/submission/<int:submission_id>/download')
@login_required
def download_submission(submission_id):
    from app.modules.core.shared.models import ProjectSubmission
    from flask import send_file
    import io, os

    submission = ProjectSubmission.query.get_or_404(submission_id)
    project = Project.query.get(submission.project_id)

    # All files live on NAS — upload route never saves to local disk
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from flask import current_app
    nas_path = build_file_path(project, 'Submissions', submission.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Submission download failed (id={submission_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=submission.original_filename
    )


def _load_submission_file_bytes(sub_file, project):
    """Return the raw bytes of a submission file, reading from wherever it
    physically lives right now.

    A Draft-stage file sits in the local draft cache
    (storage_location == 'cache' → bytes on disk at local_cache_path); every
    other file is on the NAS under the project's Submissions/ folder
    (storage_location == 'nas', the column default). Raises RuntimeError on
    any failure — deliberately the SAME contract app.nas.download_app_file
    already follows — so the two view functions below keep a single
    `except RuntimeError` branch and never have to care where the file was.
    """
    if sub_file.storage_location == 'cache':
        import os
        path = sub_file.local_cache_path
        if not path or not os.path.isfile(path):
            raise RuntimeError(
                f'cached submission file missing on disk '
                f'(file_id={sub_file.id}, path={path!r})'
            )
        with open(path, 'rb') as fh:
            return fh.read()

    # storage_location == 'nas'. Two shapes live here:
    # 1. Overlay flow (this rework): the submission's whole draft was zipped
    # into ONE archive at Submit to Client, so this file is a MEMBER of
    # that zip — download the zip, extract the one member. The member name
    # equals sub_file.original_filename (the submit-to-client route renames
    # the main deck to the canonical name before zipping, so every file's
    # member name == its original_filename — no per-file mapping needed).
    # 2. Old flow: a post-submission "Attach Supporting File" upload, stored
    # as its own individual NAS object under its own name.
    # The parent submission's stored deck name tells them apart: the overlay
    # flow always stores a ".zip" there; the old flow stores the deck file
    # itself (never a .zip).
    from app.modules.core.shared.services.nas import download_app_file, build_file_path

    submission = sub_file.submission
    deck_name = submission.original_filename if submission else None
    if deck_name and deck_name.lower().endswith('.zip'):
        import io
        import zipfile
        zip_bytes = download_app_file(build_file_path(project, 'Submissions', deck_name))
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                return zf.read(sub_file.original_filename)
        except KeyError:
            raise RuntimeError(
                f'member {sub_file.original_filename!r} not found in zip {deck_name!r} '
                f'(file_id={sub_file.id})'
            )
        except zipfile.BadZipFile as e:
            raise RuntimeError(f'corrupt submission zip {deck_name!r} (file_id={sub_file.id}): {e}')

    # Old individual-object supplementary file — read it directly as before.
    nas_path = build_file_path(project, 'Submissions', sub_file.original_filename)
    return download_app_file(nas_path)


@project_overlay_bp.route('/projects/submission/file/<int:file_id>/preview')
@login_required
def preview_submission_file(file_id):
    """Serve a supplementary submission file for inline browser preview.
    Same PDF/image-only restriction as reference file previews — these are
    arbitrary supplementary uploads, not always something a browser can
    render natively."""
    from app.modules.core.shared.models import ProjectSubmissionFile
    from flask import send_file, jsonify
    import io

    PREVIEWABLE_TYPES = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }

    extra = ProjectSubmissionFile.query.get_or_404(file_id)

    mimetype = PREVIEWABLE_TYPES.get((extra.file_type or '').lower())
    if not mimetype:
        return jsonify ({
            'success': False,
            'error': 'No preview available for this file type - download instead.'
            }), 415
    
    project = Project.query.get(extra.project_id)
    from flask import current_app
    try:
        file_bytes = _load_submission_file_bytes(extra, project)
    except RuntimeError as e:
        from flask import current_app
        current_app.logger.error(f'Submission file preview failed (file_id={file_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading it instead.'
        }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=extra.original_filename
    )


@project_overlay_bp.route('/projects/submission/file/<int:file_id>/download')
@login_required
def download_submission_file(file_id):
    """Download a supplementary file attached to a submission."""
    # ProjectSubmissionFile/send_file relied on projects_submission.py's
    # module-level imports before this relocation — added explicitly here
    # since project_overlay.py doesn't import either at module level.
    from app.modules.core.shared.models import ProjectSubmissionFile
    from flask import send_file
    import io

    extra = ProjectSubmissionFile.query.get_or_404(file_id)
    project = Project.query.get(extra.project_id)

    from flask import current_app
    try:
        file_bytes = _load_submission_file_bytes(extra, project)
    except RuntimeError as e:
        current_app.logger.error(f'Submission extra-file download failed (file_id={file_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=extra.original_filename
    )


@project_overlay_bp.route('/projects/submission/<int:submission_id>/preview')
@login_required
def preview_submission(submission_id):
    """Serve a submission deck for inline browser preview instead of download.
    PDFs are streamed as-is. PPTX decks get converted to PDF on the fly first,
    since browsers can't render PowerPoint natively — this way the frontend
    only ever has to deal with one format regardless of what was uploaded."""
    from app.modules.core.shared.models import ProjectSubmission
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from app.modules.projects.lib.pptx_convert import convert_pptx_to_pdf
    from flask import send_file, jsonify, current_app
    import io, subprocess

    submission = ProjectSubmission.query.get_or_404(submission_id)
    project = Project.query.get(submission.project_id)

    nas_path = build_file_path(project, 'Submissions', submission.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Submission preview NAS fetch failed (id={submission_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading instead.'
        }), 502

    if submission.file_type.lower() == 'pptx':
        try:
            file_bytes = convert_pptx_to_pdf(file_bytes)
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            current_app.logger.warning(
                f'Preview conversion failed for submission {submission_id}: {e}'
            )
            return jsonify({
                'success': False,
                'error': 'Preview unavailable for this file — try downloading instead.'
            }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=submission.original_filename.rsplit('.', 1)[0] + '.pdf'
    )
