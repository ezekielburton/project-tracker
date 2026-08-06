"""
Project Details Overlay Route File.
New blueprint for file hygiene, easier to work on chunks rather than one long file.
"""

from flask import Blueprint, render_template, abort, request
from flask_login import login_required, current_user

from app.models import Project

project_overlay_bp = Blueprint('project_overlay', __name__)

def _get_actor():
    """Emulation-aware actor lookup — an admin viewing-as another user acts
    (and gets logged) as that user; everyone else acts as themselves. Every
    overlay route uses this, not just overlay() itself."""
    from app.models import User
    from flask import session
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_deliverables(project, actor):
    """Same rule as Reference Files management — admin/management (any
    project), this project's CS Lead, this project's Secondary CS, or the
    specific assigned Project Owner. Kept as its own function even though
    it's identical to can_manage_reference_files today, same reasoning as
    can_edit_project — they may diverge later."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )

def _build_deliverable_focus_context(deliverables, actor):
    """Computes the per-deliverable status pill + Focused/All eligibility data
    that both the Standard and C&CM Deliverables views need, so the two
    branches in overlay_deliverables() can't drift out of sync on this.
    """
    from app.status_vocabulary import derive_deliverable_status
    status_by_id = {}
    assigned_ids = set()
    for d in deliverables:
        status_by_id[d.id] = derive_deliverable_status(d)
        if any(a.designer_id == actor.id for a in d.disciplines):
            assigned_ids.add(d.id)
    return {
        'status_by_id': status_by_id,
        'assigned_ids': assigned_ids,
        # Designer/Team Lead/Admin get the toggle; everyone else always sees All.
        'can_toggle_focus': actor.role in ('designer', 'team_lead', 'admin'),
        # Designer/Team Lead default to Focused (their own workload first);
        # Admin's toggle doesn't filter anything either way, per your call —
        # defaulting it to All just means it starts in the "off" position.
        'default_focus': actor.role in ('designer', 'team_lead'),
    }

def _build_ccm_deliverable_sections(project):
    """Groups a C&CM project's deliverables as Region -> Customer -> Deliverables,
    mirroring the brief_sections pattern used elsewhere (projects_detail.py's overlay
    route, the old detail page's C&CM section) so this view can't drift from how the
    rest of the app already understands region/customer structure. Customers whose
    region isn't one of the five known keys land in a single 'other' bucket rather
    than being silently dropped.
    """
    from app.models import Deliverable

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
    from app.models import ProjectPosmChannel

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
    from app.models import ProjectSubmission
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
    from app.models import ProjectSubmission
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
    from app.models import ProjectSubmission
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

    is_editable / is_locked state machine (confirmed with Ezekiel,
    5 Aug 2026): draft -> fully editable. internal_review -> locked,
    unless is_being_edited (designer clicked Edit). internal_revision ->
    immediately editable again, no separate unlock click needed, since
    CS's flag message IS the reason. Submitting for review — whether it's
    the first time or after an edit/flag cycle — always re-locks to
    internal_review and clears is_being_edited.
    """
    from app.models import ProjectSubmissionFile, Deliverable

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
    # tab can show it as an "Active with Client" indicator ABOVE the working
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
        and resolved['channel'] is None
        and project.brief_type != 'ccm'
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


def _build_details_context(project, actor):
    """Everything the Design > Details sub-tab needs — permissions, picker
    option lists, designer rows, C&CM concept/kv data. Shared by the
    initial /overlay fetch (which embeds Details directly) and the
    standalone /overlay/details fetch (used when navigating back to
    Details after visiting another sub-tab), so the two can never drift
    apart from each other."""
    from app.models import User
    from app.status_vocabulary import derive_project_status

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

    status_label, status_class = derive_project_status(project)

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

    return dict(
        status_label=status_label,
        status_class=status_class,
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
    )

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


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables')
@login_required
def overlay_deliverables(project_id):
    from app.models import Deliverable
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    can_manage = _can_manage_deliverables(project, actor)

    if project.brief_type == 'ccm':
        regions = _build_ccm_deliverable_sections(project)
        has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
        all_customers = [c for r in regions for c in r['customers']]
        first_customer_id = all_customers[0]['project_customer'].id if all_customers else None
        all_deliverables = [d for c in all_customers for d in c['deliverables']]
        return render_template(
            'project_overlay/_deliverables_ccm.html',
            project=project,
            regions=regions,
            all_customers=all_customers,
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            can_manage_deliverables=can_manage,
            **_build_deliverable_focus_context(all_deliverables, actor),
        )

    deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.id).all()
    return render_template(
        'project_overlay/_deliverables_standard.html',
        project=project,
        deliverables=deliverables,
        can_manage_deliverables=can_manage,
        **_build_deliverable_focus_context(deliverables, actor),
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/edit')
@login_required
def overlay_deliverables_edit(project_id):
    from app.models import Deliverable
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)
    deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.id).all()
    return render_template(
        'project_overlay/_deliverables_standard_edit.html',
        project=project,
        deliverables=deliverables,
        time_options=DESIGN_DEADLINE_TIME_OPTIONS,
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/save', methods=['POST'])
@login_required
def save_standard_deliverables(project_id):
    """Bulk create/update/delete for the Standard Brief Deliverables
    editable table — one request from Save Deliverables covers every
    change made since Edit Deliverables was opened, committed once.
    Shape borrowed from assign_standard_deliverables_bulk in
    projects_detail.py (loop, single commit, log after) — but this route
    creates/updates/deletes rows rather than assigning designers, so it's
    new rather than reused outright."""
    from datetime import datetime as dt
    from app.models import Deliverable
    from app import db
    from app.utils import log_activity
    from flask import request, jsonify, session

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    rows = data.get('deliverables') or []

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
            continue  # a blank row that was never filled in — skip it rather than fail the whole save

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
                project_customer_id=None,
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

    db.session.commit()

    for name in created:
        log_activity('deliverable_created', f'Standard deliverable "{name}" added to "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    for name in updated:
        log_activity('deliverable_updated', f'Standard deliverable "{name}" updated on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    for name in deleted:
        log_activity('deliverable_deleted', f'Standard deliverable "{name}" removed from "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

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

    from app.routes.projects_detail import ensure_posm_channels
    regions = _build_submission_regions(project)
    brief_sections = {r['key']: r['customers'] for r in regions}
    ensure_posm_channels(project, brief_sections)

    has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
    all_customers = [c for r in regions for c in r['customers']]

    return render_template(
        'project_overlay/_submissions_ccm.html',
        project=project,
        regions=regions,
        has_gulf_regions=has_gulf_regions,
        default_region_key=regions[0]['key'] if regions else None,
        default_customer_id=all_customers[0].id if all_customers else None,
        show_ckv=bool(project.has_concept or project.has_kv),
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/content')
@login_required
def overlay_submissions_content(project_id):
    from app.models import ProjectCustomer
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
    from app.models import ProjectSubmission, ProjectSubmissionFile
    from app.submission_cache import cache_submission_file
    from app import db
    from app.utils import log_activity
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
        # new working draft: the sent deck shows as the "Active with Client"
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
        db.session.flush()  # need draft.id before caching the file under it

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
    draft goes back to empty — per Ezekiel: "If the file is solo, it's fine
    to revert to a empty draft."
    """
    from app.models import ProjectSubmissionFile
    from app.submission_cache import cache_submission_file, delete_cached_file
    from app import db
    from app.utils import log_activity
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
    from app.models import ProjectSubmissionFile
    from app import db
    from app.utils import log_activity
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
    from app.models import (Deliverable, ProjectSubmissionDeliverable,
                             ProjectSubmissionEvent, ProjectSubmissionFile)
    from app.status_tracking import record_deliverable_status
    from app.notifications import create_notification
    from app.utils import log_activity
    from app import db
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
    from app.models import ProjectSubmissionEvent
    from app.utils import log_activity
    from app import db
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
    from app.models import ProjectSubmissionEvent
    from app.status_tracking import record_deliverable_status
    from app.notifications import create_notification
    from app.utils import strip_html, log_activity
    from app import db
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
      - POSM channel, per-customer:  "<Client> - <Project> - <Country> - <Customer> - POSM - <Initial|Revision N>"
      - POSM channel, per-country (legacy whole-region, posm_customer_id NULL): "... - <Country> - POSM - <label>"
      - POSM channel, no country:    "... - POSM - <label>"  (project.revision_count)
      - C&CM Concept & KV:           "<Client> - <Project> - Concept & KV - <Initial|Revision N>"  (project.ckv_revision_count)
      - Standard Brief:              "<Client> - <Project> - <Initial|Revision N>"  (project.revision_count)
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
            from app.models import ProjectCustomer
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
    the next pass — see Projects Rework Workflow.md sub-step 7.

    Reuses the transition logic the old projects_submission.py
    submit_to_client route's Standard branch already proved (record_project_
    status, included-deliverable status, revision-count stamping, concept/KV
    advance, notify_of_submission_to_client). The only genuinely new work is
    the cache -> zip -> NAS step in front of it — the old flow assumed the
    file was already on the NAS.

    Body (JSON): scope, customer_id (carried for the later C&CM/Gulf pass;
    unused for Standard).
    """
    from app.models import ProjectSubmissionFile, ProjectSubmissionEvent
    from app.status_tracking import record_project_status, record_deliverable_status
    from app.notifications import notify_of_submission_to_client
    from app.utils import log_activity
    from app.submission_cache import build_zip_bytes, clear_submission_cache
    from app.nas import build_file_path, upload_app_file
    from app import db
    from datetime import datetime as dt
    from flask import jsonify, current_app

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if actor.role not in ('admin', 'cs', 'management'):
        return jsonify({'success': False, 'error': 'You do not have permission to submit to client.'}), 403

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')

    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft:
        return jsonify({'success': False, 'error': 'No active submission to send.'}), 400
    if draft.workflow_status != 'internal_review' or draft.is_being_edited:
        return jsonify({'success': False,
                        'error': 'The deck must be in internal review (not mid-edit) before submitting to client.'}), 400

    # Gate: don't overwrite the deck already with the client. A second send is
    # allowed only once its canonical name would DIFFER from the sent deck's —
    # which happens after CS requests a Client Revision (that bumps the scope's
    # counter, changing the Initial/Revision-N label). Same name → block.
    _sent = _get_sent_submission(project, resolved)
    if _sent is not None and f'{_canonical_deck_basename(project, resolved)}.zip' == _sent.original_filename:
        return jsonify({'success': False,
                        'error': 'A deck is already with the client for this scope — request a Client Revision first.'}), 400

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

    # ── Canonical naming. The zip object on the NAS carries the canonical
    # name + .zip; INSIDE the zip the main deck takes the canonical name +
    # its own extension (so member == original_filename after the rename
    # below), every other file keeps its uploaded name. ──
    base_name = _canonical_deck_basename(project, resolved)
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
    # replaces it as the Active-with-Client deck; the old one stays in History.
    # (_sent was fetched by the gate above.)
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
        # Standard Brief — pipeline status + included deliverables (unchanged).
        record_project_status(project, 'submitted_to_client', actor)
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
    Submit to Client (locked spec, architecture doc §6): the COMPLETE deck —
    the deliverables newly going for decision (this draft's included set),
    PLUS the ones already Client-Approved, shown as read-only indicators
    (they ride along in the deck for client-completeness + invoicing, but
    this submission never changes their status). Plus the expected deck
    filename and the files being sent. Scope-aware: Standard, C&CM Concept &
    KV (concept/KV inclusion instead of deliverables), and UAE/Gulf POSM.

    GET, read-only — populates the modal on button click (render-on-demand).
    """
    from app.models import ProjectSubmissionFile, Deliverable
    from app.status_vocabulary import derive_deliverable_status
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

    # Expected deck filename previewed to CS (the NAS zip object name).
    expected_filename = f'{_canonical_deck_basename(project, resolved)}.zip'

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
    from app.models import ProjectSubmissionEvent, ProjectDesigner
    from app.status_tracking import record_project_status, record_deliverable_status
    from app.notifications import create_notification
    from app.utils import strip_html, log_activity
    from app import db
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
    if resolved['channel'] is not None or project.brief_type == 'ccm':
        return jsonify({'success': False, 'error': 'Client Revision is not wired for this scope yet.'}), 400

    sent = _get_sent_submission(project, resolved)
    if sent is None:
        return jsonify({'success': False, 'error': 'There is no deck with the client to revise.'}), 400
    if any(e.event_type == 'client_revision' for e in sent.events):
        return jsonify({'success': False, 'error': 'A client revision has already been requested for this deck.'}), 400

    project.revision_count = (project.revision_count or 0) + 1
    record_project_status(project, 'revision_in_queue', actor)
    for deliverable in project.project_deliverables:
        record_deliverable_status(deliverable, 'revision_in_queue', actor)
        deliverable.revision_count = project.revision_count

    db.session.add(ProjectSubmissionEvent(
        submission_id=sent.id, event_type='client_revision',
        author_id=actor.id, message=message,
    ))
    db.session.commit()

    for assignment in ProjectDesigner.query.filter_by(project_id=project.id).all():
        if assignment.designer and assignment.designer.id != actor.id:
            create_notification(
                recipient=assignment.designer,
                message=f'Client revision #{project.revision_count} requested on "{project.name}" by {actor.name}.',
                notification_type='revision_requested',
                project=project,
                triggered_by=actor,
            )

    log_activity('revision_requested',
                 f'Client revision #{project.revision_count} requested on "{project.name}" by {actor.name}: {strip_html(message)[:100]}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})