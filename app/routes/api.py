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

    Covers: status, assigned designers, brief flags (open/resolved),
    submissions (active/flagged), revision count, concept/KV state.

    Kept as a plain string rather than a hash so it's easy to debug in the
    browser — just inspect data-fp on #section-assignments.
    """
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
    ])


def _project_entry(p):
    """
    Build a minimal dict for a single project for the dashboard poll.

    Includes:
      - id: used to detect rows added/removed (triggers a reload)
      - status: used for in-place badge patching when only status changed
      - fp: fingerprint of designer assignments — sorted user IDs joined by comma.
            A fingerprint change means designers were assigned/removed, which
            triggers a full reload (badge patching can't update designer avatar rows).
    """
    designer_ids = sorted([pd.user_id for pd in p.assigned_designers])
    return {
        'id': p.id,
        'status': p.project_status,
        'fp': ','.join(map(str, designer_ids)),
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