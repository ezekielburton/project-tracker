# app/routes/api.py
#
# Lightweight polling endpoints for live dashboard and detail page updates.
# These routes are called by polling.js on an interval — they return only
# the minimal data needed to detect changes, keeping response times fast.

from flask import Blueprint, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models import Project, User, ProjectDesigner, ProjectSecondaryCS

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
    from app.zip_utils import serve_zip

    response = serve_zip(zip_id)
    if response is None:
        abort(404)
    return response

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

    # Each submission encoded as "id:<active><flagged>" — two boolean digits
    sub_states = sorted([
        '{}:{}{}'.format(s.id, 1 if s.is_active else 0, 1 if s.is_flagged else 0)
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
    # own per-customer status/dates (region assignment itself rarely changes
    # but is cheap to include)
    customer_states = sorted([
        '{}:{}:{}:{}:{}:{}'.format(
            pc.id, pc.customer_id, pc.status or '', _d(pc.design_deadline),
            _d(pc.installation_date), 1 if pc.cancelled else 0
        )
        for pc in p.project_customers
    ])
    region_states = sorted([r.region for r in p.project_regions])

    # Reference files — just the sorted ID list, enough to detect additions/removals
    file_ids = sorted([f.id for f in p.reference_files])

    # Revision requests sent to the designer (message text hashed — see _texthash above)
    revision_states = sorted([
        '{}:{}{}:{}'.format(
            r.id, 1 if r.includes_concept else 0, 1 if r.includes_kv else 0, _texthash(r.message)
        )
        for r in p.revisions
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
    from app.models import User as UserModel

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