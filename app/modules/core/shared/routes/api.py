# app/routes/api.py
#
# Lightweight polling endpoints for live dashboard and detail page updates.
# These routes are called by polling.js on an interval — they return only
# the minimal data needed to detect changes, keeping response times fast.

from flask import Blueprint, jsonify, session, current_app
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project, User, ProjectDesigner, ProjectSecondaryCS, Client, Contact

# Register this as a blueprint with the /api prefix.
# All routes in this file will be under /api/...
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/zip-download/<zip_id>')
@login_required
def zip_download(zip_id):
    """
    Generic zip download endpoint — serves a zip previously built by
    zip_utils.build_zip(), then deletes it. Any feature with a "Download
    All" button points its frontend at this same route; only the zip_id
    changes per feature.
    """
    from flask import abort
    from app.modules.core.shared.lib.zip_utils import serve_zip

    response = serve_zip(zip_id)
    if response is None:
        abort(404)
    return response

@api_bp.route('/version')
def app_version():
    return jsonify(version=current_app.config['STATIC_VERSION'])


@api_bp.route('/clients/<int:client_id>/contacts')
@login_required
def client_contacts(client_id):
    """
    GET /api/clients/<client_id>/contacts

    Returns the contacts belonging to one Client as a plain JSON list:
    [{"id": 1, "name": "John Smith"}, ...] - deliberately just id + name,
    nothing more, because the consumer is a cascading <select> on the brief
    form (pick a Client, this list populates the contact dropdown) which only
    needs an id to submit and a name to display. Keys off Client directly,
    which serves as "the company" a brief is for.

    login_required only, no role check - any logged-in user filling out a
    brief needs to be able to hit this, unlike the /admin/api/* routes in
    admin.py which also require the admin role.
    """
    from flask import abort

    # get_or_404 (used elsewhere, e.g. WikiArticle.query.get_or_404) would also
    # work here, but the spec calls for a 404 specifically when the client
    # isn't found - being explicit with get() + abort(404) makes that
    # requirement visible in the route itself rather than relying on a
    # Flask-SQLAlchemy default message.
    client = Client.query.get(client_id)
    if not client:
        abort(404)

    # Contact.client_id (not company_id) is the FK now - see the model and
    # the retire_company_directory.py migration for the column rename.
    contacts = Contact.query.filter_by(client_id=client.id).order_by(Contact.name).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in contacts])


def _directory_project_entry(p):
    """
    Shared shape for both "linked projects" endpoints below - just enough
    for the directory page's read-only Projects list: a name to display, a
    status to color the badge, and a human-readable label for that status.

    status_label is computed the same way every dashboard template already
    formats project_status for display ({{ status | replace('_', ' ') |
    title }}), just done here in Python instead of Jinja since this data
    goes out as JSON, not rendered server-side - keeping both in sync means
    "in_queue" reads as "In Queue" here exactly like it does everywhere else
    in the app, not a differently-cased one-off.
    """
    return {
        'id': p.id,
        'name': p.name,
        'status': p.project_status,
        'status_label': (p.project_status or '').replace('_', ' ').title(),
    }


@api_bp.route('/clients/<int:client_id>/projects')
@login_required
def client_projects(client_id):
    """
    GET /api/clients/<client_id>/projects

    Every project where project.client_id matches - the Client Directory
    page's "Projects" section for a company detail view. login_required
    only, no role check: per the spec, every role (including Designers, who
    get a read-only directory) can see this list, only editing is
    restricted.
    """
    from flask import abort

    client = Client.query.get(client_id)
    if not client:
        abort(404)

    projects = Project.query.filter_by(client_id=client.id).order_by(Project.created_at.desc()).all()
    return jsonify([_directory_project_entry(p) for p in projects])




@api_bp.route('/contacts/<int:contact_id>/projects')
@login_required
def contact_projects(contact_id):
    """
    GET /api/contacts/<contact_id>/projects

    Same idea as client_projects() above, but for a single Contact -
    every project where project.contact_id matches, for the directory
    page's contact detail view.
    """
    from flask import abort

    contact = Contact.query.get(contact_id)
    if not contact:
        abort(404)

    projects = Project.query.filter_by(contact_id=contact.id).order_by(Project.created_at.desc()).all()
    return jsonify([_directory_project_entry(p) for p in projects])

def _detail_fingerprint(p):
    """
    Compute a short string that captures everything visible on the detail page.
    If any of these values change between polls, polling.js reloads the page.

    Covers: status, assigned designers (project- and deliverable-level),
    brief flags (open/resolved), submissions (active/flagged), revision
    count and revision requests, concept/KV state, project info fields
    (name, job number, client, teams, dates, brief text), every
    deliverable's own status/dates/teams (standard AND C&CM — a C&CM
    deliverable is just a Deliverable row with project_customer_id set, so
    p.project_deliverables already covers both), the project_customers/
    regions structure, and reference file uploads.

    Kept as a plain string rather than a hash so it's easy to debug in the
    browser — just inspect data-fp on #section-assignments. Long free-text
    fields are hashed (short, stable md5 prefix) rather than embedded in
    full, to keep the response small — Python's built-in hash() is NOT used
    here since it's randomized per-process and would cause false-positive
    "changed" detections whenever two different Gunicorn workers computed it.
    """
    import hashlib

    def _texthash(s):
        return hashlib.md5((s or '').encode('utf-8')).hexdigest()[:8]

    def _d(dt):
        return dt.isoformat() if dt else ''

    # Sorted user IDs so the fingerprint is order-independent
    designer_ids = sorted([pd.user_id for pd in p.assigned_designers])

    # Each flag encoded as "id:0" (open) or "id:1" (resolved)
    flag_states = sorted([
        '{}:{}'.format(f.id, 1 if f.is_resolved else 0)
        for f in p.brief_flags
    ])

    # Each submission encoded as "id:<active><flagged>:submitted_at" — the
    # submitted_to_client_at timestamp is included separately from the two
    # boolean digits because submitting a deck to the client sets that
    # timestamp on the SAME row without necessarily flipping is_active or
    # is_flagged — without it here, that transition was invisible to the
    # fingerprint (this was the actual cause of the submission card not
    # refreshing live, even though the underlying NOTIFY fired correctly).
    sub_states = sorted([
        '{}:{}{}:{}'.format(
            s.id, 1 if s.is_active else 0, 1 if s.is_flagged else 0,
            s.submitted_to_client_at.isoformat() if s.submitted_to_client_at else ''
        )
        for s in p.submissions
    ])

    # Each deliverable — standard AND C&CM alike — encoded as
    # "id:status:design_deadline:installation_deadline:teams:flagged:revcount"
    deliverable_states = sorted([
        '{}:{}:{}:{}:{}:{}:{}'.format(
            d.id, d.status or '', _d(d.design_deadline), _d(d.installation_deadline),
            d.teams or '', 1 if d.flagged_for_revision else 0, d.revision_count or 0
        )
        for d in p.project_deliverables
    ])

    # Deliverable-level assignments (as opposed to the project-level
    # ProjectDesigner rows already covered by designer_ids above) —
    # "deliverable_id:designer_id" pairs
    deliverable_assignments = sorted([
        '{}:{}'.format(da.deliverable_id, da.designer_id)
        for d in p.project_deliverables
        for da in d.disciplines
    ])

    # C&CM structure: which customers/regions are on this project and their
    # own per-customer status/dates/POSM revision count (region assignment
    # itself rarely changes but is cheap to include)
    customer_states = sorted([
        '{}:{}:{}:{}:{}:{}:{}:{}'.format(
            pc.id, pc.customer_id, pc.status or '', _d(pc.design_deadline),
            pc.design_deadline_time.isoformat() if pc.design_deadline_time else '',
            _d(pc.installation_date), 1 if pc.cancelled else 0, pc.posm_revision_count or 0
        )
        for pc in p.project_customers
    ])
    region_states = sorted([r.region for r in p.project_regions])

    # Reference files — just the sorted ID list, enough to detect additions/removals
    file_ids = sorted([f.id for f in p.reference_files])

    # Revision requests sent to the designer (message text hashed — see
    # _texthash above). Includes the sorted list of deliverable IDs attached
    # to each revision (ProjectRevisionDeliverable) — without this, adding/
    # removing a deliverable from an existing revision request wouldn't
    # register as a change.
    revision_states = sorted([
        '{}:{}{}:{}:{}'.format(
            r.id, 1 if r.includes_concept else 0, 1 if r.includes_kv else 0, _texthash(r.message),
            ','.join(map(str, sorted([rd.deliverable_id for rd in r.revision_deliverables])))
        )
        for r in p.revisions
    ])

    # Secondary CS — who's assigned, plus each one's own C&CM region
    # subscription filter (affects what THEY see/get notified about, so a
    # secondary CS updating this in one tab should refresh their other tabs too)
    secondary_cs_states = sorted([
        '{}'.format(a.user_id) for a in p.secondary_cs_assignments
    ])
    secondary_cs_region_states = sorted([
        '{}:{}'.format(r.user_id, r.region) for r in p.secondary_cs_regions
    ])

    # POSM channels — one row per parallel Gulf/UAE submission pipeline
    posm_channel_states = sorted([
        '{}:{}:{}:{}:{}'.format(
            c.id, c.posm_country, c.posm_customer_id or '', c.status or '',
            1 if c.approved_at else 0
        )
        for c in p.posm_channels
    ])

    return '|'.join([
        p.project_status or '',
        ','.join(map(str, designer_ids)),
        ','.join(flag_states),
        ','.join(sub_states),
        str(p.revision_count or 0),
        str(p.concept_status or ''),
        str(p.kv_status or ''),
        str(p.concept_designer_id or ''),
        str(p.kv_designer_id or ''),
        # Final approval info
        str(1 if p.approved_at else 0),
        str(p.approved_by_id or ''),
        # Project info — standard brief fields
        p.name or '',
        p.job_number or '',
        p.client or '',
        p.design_teams_requested or '',
        str(p.importance or ''),
        str(p.urgency or ''),
        p.required_output or '',
        str(p.design_type_id or ''),
        str(p.design_direction_id or ''),
        _texthash(p.client_expectation),
        _texthash(p.what_to_avoid),
        _texthash(p.additional_information),
        _texthash(p.campaign_notes),
        _texthash(p.kv_requirements),
        # Dates
        _d(p.design_needed_by), _d(p.execution_date), _d(p.briefing_date),
        _d(p.first_output_deadline), _d(p.installation_date),
        _d(p.concept_deadline), _d(p.kv_deadline),
        # Deliverable / assignment / C&CM structure / reference files
        ','.join(deliverable_states),
        ','.join(deliverable_assignments),
        ','.join(customer_states),
        ','.join(region_states),
        ','.join(map(str, file_ids)),
        ','.join(revision_states),
        # Secondary CS / POSM channels
        ','.join(secondary_cs_states),
        ','.join(secondary_cs_region_states),
        ','.join(posm_channel_states),
    ])


def _project_entry(p):
    """
    Build a minimal dict for a single project for the dashboard poll.

    Includes:
      - id: used to detect rows added/removed (triggers a reload)
      - status: used for in-place badge patching when only status changed
      - fp: fingerprint of everything else shown on the dashboard row —
            designer assignment, name, job number, teams, CS lead, and the
            two deadline dates. A change to any of these triggers a full
            reload (badge patching only handles the status text itself;
            everything else here would require re-rendering the whole row).

    fp's field order/format MUST exactly match the _dfp Jinja fingerprint
    computed in the dashboard templates (cs.html, team_lead.html,
    designer.html) — these are plain string comparisons, so any drift
    between the two would make every poll look like a mismatch even when
    nothing actually changed.
    """
    designer_ids = sorted([pd.user_id for pd in p.assigned_designers])
    fp = '|'.join([
        ','.join(map(str, designer_ids)),
        p.name or '',
        p.job_number or '',
        p.design_teams_requested or '',
        str(p.cs_lead_id or ''),
        p.first_output_deadline.isoformat() if p.first_output_deadline else '',
        p.execution_date.isoformat() if p.execution_date else '',
    ])
    return {
        'id': p.id,
        'status': p.project_status,
        'fp': fp,
    }


@api_bp.route('/projects/poll')
@login_required
def projects_poll():
    """
    Called every 30 seconds by polling.js on the dashboard page.

    Returns a 'tabs' dict where each key is a tab name ('my', 'all', 'team')
    and each value is a list of {id, status} objects for the projects in that tab.

    The JS uses this to:
      1. Detect if a project was added or removed (IDs changed) → reload
      2. Detect if a status changed → update just that badge in-place
    """
    # Import inside the function to avoid circular imports at module load time
    from app.modules.core.shared.models import User as UserModel

    # Resolve the effective user — same emulation-aware pattern used throughout the app.
    # If an admin is emulating someone, we behave as if we ARE that person.
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = UserModel.query.get(emulating_id)
    else:
        effective_user = current_user

    role = effective_user.role

    # ── CS / Admin / Management ──────────────────────────────────────────────
    # These roles see two tabs: 'my' (their own projects) and 'all' (everything).
    # Admins treat 'my' and 'all' as the same — they see everything in both tabs.
    if role in ['cs', 'admin', 'management']:
        if effective_user.role == 'admin':
            # Admin has no personal filter — they see all active projects
            my_projects = Project.query.filter(
                Project.project_status != 'draft',    # drafts are hidden from dashboards
                Project.project_status != 'approved'  # approved projects have their own tab
            ).all()
            all_projects = my_projects  # same set for admins

        else:
            # CS: 'my' tab shows projects where they are the lead OR a secondary CS
            secondary_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(
                user_id=effective_user.id
            ).subquery()

            my_projects = Project.query.filter(
                db.or_(
                    Project.cs_lead_id == effective_user.id,
                    Project.id.in_(secondary_ids)
                ),
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            ).all()

            # 'all' tab shows every non-draft, non-approved project (across all CS leads)
            all_projects = Project.query.filter(
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            ).all()

        return jsonify({'tabs': {
            'my':  [_project_entry(p) for p in my_projects],
            'all': [_project_entry(p) for p in all_projects],
        }})

    # ── Designer ─────────────────────────────────────────────────────────────
    # Designers see 'my' (personally assigned) and 'team' (all projects for their team).
    elif role == 'designer':
        # Find all project IDs where this designer is explicitly assigned
        assigned_ids = db.session.query(
            ProjectDesigner.project_id
        ).filter_by(user_id=effective_user.id).subquery()

        my_projects = Project.query.filter(
            Project.id.in_(assigned_ids),
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).all()

        # Team projects: any project that lists this designer's team
        # (uses string contains — same logic as the designer_dashboard function)
        team = effective_user.team
        team_projects = []
        if team:
            team_projects = Project.query.filter(
                Project.design_teams_requested.contains(team),
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            ).all()

        return jsonify({'tabs': {
            'my':   [_project_entry(p) for p in my_projects],
            'team': [_project_entry(p) for p in team_projects],
        }})

    # ── Team Lead ─────────────────────────────────────────────────────────────
    # Team leads see 'team' (all projects for their team) and 'my' (personally assigned).
    elif role == 'team_lead':
        team = effective_user.team
        team_projects = []
        if team:
            team_projects = Project.query.filter(
                Project.design_teams_requested.contains(team),
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            ).all()

        # Personal assignment — same subquery pattern as the designer branch
        personal_ids = db.session.query(
            ProjectDesigner.project_id
        ).filter_by(user_id=effective_user.id).subquery()

        personal_projects = Project.query.filter(
            Project.id.in_(personal_ids),
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).all()

        return jsonify({'tabs': {
            'my':   [_project_entry(p) for p in personal_projects],
            'team': [_project_entry(p) for p in team_projects],
        }})

    # Fallback — should never hit this in practice, but safe to return an empty response
    return jsonify({'tabs': {}})


@api_bp.route('/projects/<int:project_id>/poll')
@login_required
def project_detail_poll(project_id):
    """
    Called every 15 seconds by polling.js on the project detail page.

    Returns only the fields that change most often during active work:
      - project_status: so the badge can update if CS or a designer changes it
      - is_on_hold: so the hold banner can appear/disappear without a refresh

    We can add more fields here later if needed (e.g. assigned_designers).
    """
    # 404 if the project doesn't exist — same as project_detail routes do
    project = Project.query.get_or_404(project_id)

    return jsonify({
        'project_status': project.project_status,
        # Derived flag — JS uses this to show/hide the on-hold banner
        # rather than having to compare string values itself
        'is_on_hold': project.project_status == 'on_hold',
        # Full fingerprint of everything visible on the detail page.
        # If this changes between polls, polling.js reloads the page.
        'fp': _detail_fingerprint(project),
    })