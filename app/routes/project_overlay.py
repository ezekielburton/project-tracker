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
    """Returns the current active Draft ProjectSubmission for this scope,
    or None if there isn't one yet. 'Active draft' = is_active AND
    workflow_status == 'draft' — the new overlay Submissions routes are
    the ones that actually maintain workflow_status going forward (the
    old detail page's routes in projects_submission.py never set it;
    that's fine, they're untouched legacy code for the page being
    replaced)."""
    from app.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
        is_active=True,
        workflow_status='draft',
    ).first()

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

    if project.brief_type != 'ccm':
        return render_template('project_overlay/_submissions_standard.html', project=project)

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

    if request.args.get('scope') == 'ckv':
        label = 'Concept & KV'
    else:
        customer_id = request.args.get('customer_id', type=int)
        pc = ProjectCustomer.query.filter_by(id=customer_id, project_id=project_id).first() if customer_id else None
        label = pc.customer.name if pc else 'Unknown'

    # Placeholder — the real draft/upload/submit/revision surface is the next chunk.
    return render_template('project_overlay/_submissions_content_placeholder.html', label=label)

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
        # Only one is_active=True submission may exist per scope at a time
        # — same invariant the old upload_submission() route enforced.
        # Matters once a scope has real history (e.g. Start Revision
        # reopening Draft, a later sub-step); a brand-new scope has
        # nothing to deactivate.
        previous = ProjectSubmission.query.filter_by(
            project_id=project.id,
            phase=resolved['phase'],
            posm_country=resolved['posm_country'],
            posm_customer_id=resolved['posm_customer_id'],
            is_active=True,
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
                    