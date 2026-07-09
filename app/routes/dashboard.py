from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from datetime import date, datetime, timedelta
from sqlalchemy import nullslast
from app import db
from app.models import Project, ProjectSecondaryCS, ProjectDesigner, ActivityLog, User, Deliverable
from app.utils import get_actor
from app.dashboard_logic import get_next_action_owner, get_project_rag, nearest_deadline, compute_clashes, rag_for_deadline

# NOTE: registered blueprint name is 'projects' (not 'dashboard') — every
# url_for() call for this blueprint's routes uses that, e.g.
# url_for('projects.api_summary'). URL prefix is still /dashboard.
dashboard_bp = Blueprint('projects', __name__, url_prefix='/dashboard')

# Maps the ?view= query param (set by auth.login()'s role-based redirect) to
# the card key that should auto-expand on first paint. This is the only
# place that mapping lives — dashboard.js reads initial_expanded_card from
# the page rather than re-deriving it from the URL itself.
VIEW_TO_CARD = {
    'decisions': 'decisions',
    'due': 'due',
    'my-week': 'summary',
}

# Card order below the always-full-width Summary card, per role. Only the
# FIRST entry per role is actually specified in the brief ("X card appears
# first") — the rest of the order is a judgment call, easy to change later
# since it's just a list.
CARD_ORDER = {
    'management': ['decisions', 'what_changed', 'due', 'next_actions', 'clashes', 'brief_quality'],
    'admin':      ['decisions', 'what_changed', 'due', 'next_actions', 'clashes', 'brief_quality'],
    'cs':         ['due', 'decisions', 'what_changed', 'next_actions', 'clashes', 'brief_quality'],
    'designer':   ['clashes', 'due', 'decisions', 'what_changed', 'next_actions', 'brief_quality'],
    'team_lead':  ['clashes', 'due', 'decisions', 'what_changed', 'next_actions', 'brief_quality'],
}

# Deep-dive zone default tab per role (Management/CS/Admin → Projects,
# Designer/Team Lead → Deliverables). Just the initial tab shown — the
# side-by-side toggle and manual tab switching both still work regardless.
DEFAULT_TAB = {
    'management': 'projects',
    'admin':      'projects',
    'cs':         'projects',
    'designer':   'deliverables',
    'team_lead':  'deliverables',
}


@dashboard_bp.route('')
@login_required
def index():
    user = get_actor()
    initial_view = request.args.get('view', '')

    return render_template(
        'dashboard.html',
        effective_role=user.role,
        card_order=CARD_ORDER.get(user.role, CARD_ORDER['management']),
        initial_expanded_card=VIEW_TO_CARD.get(initial_view),
        default_tab=DEFAULT_TAB.get(user.role, 'projects'),
        summary=_compute_summary(user),
        what_changed=_compute_what_changed(user),
        # Due card's default filter is "Overdue + Due Today combined" per spec
        due_default=_compute_due(user, 'overdue_today'),
        # Summary card's two columns (UI Chunk 2) — separate from due_default
        # above: the Summary card wants a strict "Today" list and a "This
        # Week" list side by side, not the Due card's overdue+today merge.
        # Reuses the exact same _compute_due() the Due card and the
        # /api/due?filter= endpoint use, just called with different filter
        # values, so all three places agree on what counts as "due today".
        due_today_items=_compute_due(user, 'today'),
        due_week_items=_compute_due(user, 'week'),
        decisions=_compute_decisions(user),
        # Next Actions card defaults to the "My Actions" tab on first paint
        # (see next_actions.html) — "Others' Actions" is fetched client-side
        # on demand, same SSR-default-then-fetch-on-toggle split as the Due
        # card's due_default/fetchAndRenderDue().
        next_actions_default=_compute_next_actions(user, 'mine'),
        clashes=_compute_clashes_response(user),
        # Only CS/Designer/Team Lead ever see the "Flag a Project" button
        # (Management has no reason to flag something to itself), so skip
        # the extra query entirely for roles that can't open the modal.
        flaggable_projects=_compute_flaggable_projects(user) if user.role in ('cs', 'designer', 'team_lead') else [],
        # Deep-dive zone (UI Chunk 8) — unlike every card above, these two
        # are consumed as fully server-rendered rows with data-* attributes,
        # same convention the OLD role dashboards use (app/templates/
        # dashboards/cs.html etc.). Filtering/sorting both happen entirely
        # client-side against those attributes — see dashboard.js — so
        # there's no SSR-default-then-fetch split like due_default/
        # next_actions_default above; this IS the complete dataset.
        deep_dive_projects=_compute_deep_dive_projects(user),
        deep_dive_deliverables=_compute_deep_dive_deliverables(user),
    )


# ── Role scoping ─────────────────────────────────────────────────────────
# Every compute function below needs "which projects can this user see", so
# it's factored out once here rather than repeated five times. Mirrors the
# same filters already used by main.cs_dashboard / designer_dashboard /
# team_lead_dashboard (app/routes/__init__.py) — management/admin see
# everything, CS sees projects they lead or are secondary CS on, designer/
# team_lead see projects they're assigned to via ProjectDesigner.

def _scoped_projects(user, active_only=True):
    """
    Drafts are always excluded. Approved projects are excluded too when
    active_only=True (matches the existing dashboards' "active work" lists)
    — some endpoints (what-changed) want the full history including
    approved projects, so active_only=False is available for those.
    """
    base = Project.query.filter(Project.project_status != 'draft')
    if active_only:
        base = base.filter(Project.project_status != 'approved')

    if user.role in ('admin', 'management'):
        return base

    if user.role == 'cs':
        secondary_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(user_id=user.id).subquery()
        return base.filter(db.or_(Project.cs_lead_id == user.id, Project.id.in_(secondary_ids)))

    # designer / team_lead
    assigned_ids = db.session.query(ProjectDesigner.project_id).filter_by(user_id=user.id).subquery()
    return base.filter(Project.id.in_(assigned_ids))


def _is_owner(owner_user, user):
    """owner_user from get_next_action_owner() is None | User | list[User]."""
    if owner_user is None:
        return False
    if isinstance(owner_user, list):
        return user in owner_user
    return owner_user.id == user.id


def _serialize_user(u):
    return {'id': u.id, 'name': u.name} if u else None


def _serialize_owner(owner):
    if owner is None:
        return None
    if isinstance(owner, list):
        return [_serialize_user(u) for u in owner]
    return _serialize_user(owner)


# ── Compute functions ────────────────────────────────────────────────────
# Each one returns a plain dict/list — no Flask Response involved — so the
# SAME function backs both the initial server-rendered page (index() above)
# and the JSON endpoint below it. One source of truth for what each card
# shows, instead of the page and the API silently drifting apart.

def _compute_summary(user):
    active_projects = _scoped_projects(user, active_only=True).all()
    today = date.today()
    week_end = today + timedelta(days=7)

    due_today = due_week = overdue = 0
    my_actions = others_actions = 0
    for p in active_projects:
        deadline = nearest_deadline(p)
        if deadline:
            if deadline < today:
                overdue += 1
            elif deadline == today:
                due_today += 1
            elif deadline <= week_end:
                due_week += 1

        owner = get_next_action_owner(p)['user']
        if _is_owner(owner, user):
            my_actions += 1
        else:
            others_actions += 1

    decisions_needed = _scoped_projects(user, active_only=True).filter(
        Project.decision_needed.is_(True)
    ).count()

    # what_changed intentionally looks across the FULL scope (active_only=False)
    # — an approval event happening yesterday is still something worth seeing
    # in "what changed", even though the project itself just left the active list.
    all_scope_ids = [p.id for p in _scoped_projects(user, active_only=False).all()]
    yesterday = today - timedelta(days=1)
    what_changed = ActivityLog.query.filter(
        ActivityLog.entity_type == 'project',
        ActivityLog.entity_id.in_(all_scope_ids),
        ActivityLog.created_at >= yesterday
    ).count()

    clashes = compute_clashes(active_projects)
    clash_count = len(clashes['by_deliverable']) + len(clashes['by_project'])

    return {
        'what_changed': what_changed,
        'due_today': due_today,
        'due_week': due_week,
        'overdue': overdue,
        'decisions_needed': decisions_needed,
        'my_actions': my_actions,
        'others_actions': others_actions,
        'clashes': clash_count
    }


@dashboard_bp.route('/api/summary')
@login_required
def api_summary():
    return jsonify(_compute_summary(get_actor()))


def _compute_what_changed(user):
    """
    Activity log entries since yesterday, scoped by role. Returns the
    existing free-text description rather than structured field/old/new
    values — ActivityLog only ever stored a description string, so there's
    no old/new value data to surface (deliberate call, not an oversight).
    """
    projects = _scoped_projects(user, active_only=False).all()
    project_ids = [p.id for p in projects]
    projects_by_id = {p.id: p for p in projects}

    yesterday = date.today() - timedelta(days=1)
    entries = ActivityLog.query.filter(
        ActivityLog.entity_type == 'project',
        ActivityLog.entity_id.in_(project_ids),
        ActivityLog.created_at >= yesterday
    ).order_by(ActivityLog.created_at.desc()).all()

    return [
        {
            'project_id': e.entity_id,
            # Prefer the live project name over the logged snapshot
            # (entity_name) — a project can be renamed after the log entry
            # was written, and the current name is more useful to show.
            'project_name': projects_by_id[e.entity_id].name if e.entity_id in projects_by_id else e.entity_name,
            'description': e.description,
            'timestamp': e.created_at.isoformat(),
            'changed_by': e.user.name if e.user else None
        }
        for e in entries
    ]


@dashboard_bp.route('/api/what-changed')
@login_required
def api_what_changed():
    return jsonify(_compute_what_changed(get_actor()))


def _compute_due(user, filter_type):
    """
    Returns individual due items, sorted by urgency (earliest deadline
    first — which for 'overdue' also means most-overdue first).

    filter_type: 'today' | 'week' | 'overdue' | 'overdue_today' (the Due
    card's default view — overdue and due-today combined into one list).

    Granularity varies by project type since that's where the real deadline
    data lives: Standard projects surface individual Deliverables (a project
    can have several, each due on a different day); C&CM projects surface
    individual pending customers (their POSM channel deadlines); a Standard
    project with no deliverable deadlines yet falls back to one project-level
    entry using execution_date, same fallback nearest_deadline() uses.
    """
    today = date.today()
    week_end = today + timedelta(days=7)

    def matches(d):
        if d is None:
            return False
        if filter_type == 'overdue':
            return d < today
        if filter_type == 'today':
            return d == today
        if filter_type == 'week':
            return today <= d <= week_end
        if filter_type == 'overdue_today':
            return d <= today
        return False

    results = []
    for p in _scoped_projects(user, active_only=True).all():
        owner = get_next_action_owner(p)
        rag = get_project_rag(p)
        owner_json = _serialize_owner(owner['user'])
        common = {'rag': rag, 'owner': owner_json, 'owner_role': owner['role'], 'guidance': owner['guidance']}

        if p.brief_type == 'ccm':
            for pc in p.project_customers:
                if pc.cancelled or pc.status == 'approved':
                    continue
                if matches(pc.design_deadline):
                    results.append({
                        **common,
                        'type': 'customer',
                        'project_id': p.id,
                        'project_name': p.name,
                        'customer_name': pc.customer.name if pc.customer else None,
                        'deadline': pc.design_deadline.isoformat(),
                    })
        else:
            matched_any_deliverable = False
            for d in p.project_deliverables:
                if matches(d.design_deadline):
                    matched_any_deliverable = True
                    results.append({
                        **common,
                        'type': 'deliverable',
                        'project_id': p.id,
                        'project_name': p.name,
                        'deliverable_id': d.id,
                        'deliverable_name': d.name,
                        'deadline': d.design_deadline.isoformat(),
                    })
            if not matched_any_deliverable and matches(p.execution_date):
                results.append({
                    **common,
                    'type': 'project',
                    'project_id': p.id,
                    'project_name': p.name,
                    'deadline': p.execution_date.isoformat(),
                })

    results.sort(key=lambda r: r['deadline'])
    return results


@dashboard_bp.route('/api/due')
@login_required
def api_due():
    filter_type = request.args.get('filter', 'overdue_today')
    return jsonify(_compute_due(get_actor(), filter_type))


def _compute_decisions(user):
    """
    "Decisions Needed" queue — every project in the user's scope that
    currently has decision_needed=True, oldest flag first (nullslast so a
    project that's somehow flagged with no timestamp sorts to the bottom
    instead of crashing the sort or floating to the top).

    days_waiting is computed HERE, server-side, rather than left for the
    template/JS to work out from raised_at — Jinja and JS would each need
    their own date-diff logic (Jinja has no built-in "days since" filter,
    and doing it twice risks the two disagreeing by a day around midnight).
    One calculation, reused by the SSR page, the JSON API, and therefore
    also the JS re-render after a new flag is submitted.
    """
    projects = _scoped_projects(user, active_only=True).filter(
        Project.decision_needed.is_(True)
    ).order_by(nullslast(Project.decision_raised_at.asc())).all()

    now = datetime.utcnow()

    return [
        {
            'project_id': p.id,
            'project_name': p.name,
            'raised_by': _serialize_user(p.decision_raised_by),
            'raised_at': p.decision_raised_at.isoformat() if p.decision_raised_at else None,
            'note': p.decision_note,
            'days_waiting': (now - p.decision_raised_at).days if p.decision_raised_at else None,
        }
        for p in projects
    ]


@dashboard_bp.route('/api/decisions')
@login_required
def api_decisions():
    return jsonify(_compute_decisions(get_actor()))


def _compute_next_actions(user, filter_type):
    """
    filter_type: 'mine' | 'others'

    ONE ROW PER PROJECT — unlike _compute_due() above, which can emit
    several rows for a single project (one per overdue deliverable/customer).
    get_next_action_owner() answers "whose turn is it on this project as a
    whole" — a single verdict per project (it already looks inside open
    flags AND falls back to project_status when there's no flag, see
    dashboard_logic.py) — so there's exactly one row per project here, never
    more.

    _is_owner() (defined above, next to _serialize_owner) is the same
    "is this project's owner ME" check _compute_summary() uses to produce
    summary.my_actions / summary.others_actions — that means the two counts
    shown on this card's collapsed header always agree with how many rows
    you'll actually see after expanding and switching tabs. If you ever
    change what counts as "mine" here, _compute_summary() needs the same
    change or the header count and the list will silently disagree.

    Sorted by nearest deadline, soonest first — same "most time-pressured
    first" ordering as _compute_due(). Projects with no deadline at all
    (nearest_deadline() returns None) sort to the very end via the
    '9999-12-31' sentinel, same trick due.html's docstring... no, actually
    _compute_due() doesn't need this trick since every row it emits already
    HAS a deadline (that's what matches() filters on) — this function is
    the first one on the dashboard where "no deadline" is a real, common
    case (e.g. a project stuck 'in_queue' with no deliverable deadlines
    set yet still needs someone's action), so the sentinel is needed here
    specifically.
    """
    results = []
    for p in _scoped_projects(user, active_only=True).all():
        owner_info = get_next_action_owner(p)
        is_mine = _is_owner(owner_info['user'], user)

        if filter_type == 'mine' and not is_mine:
            continue
        if filter_type == 'others' and is_mine:
            continue

        deadline = nearest_deadline(p)
        results.append({
            'project_id': p.id,
            'project_name': p.name,
            'guidance': owner_info['guidance'],
            'owner': _serialize_owner(owner_info['user']),
            'owner_role': owner_info['role'],
            'rag': get_project_rag(p),
            'deadline': deadline.isoformat() if deadline else None,
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/next-actions')
@login_required
def api_next_actions():
    filter_type = request.args.get('filter', 'mine')
    return jsonify(_compute_next_actions(get_actor(), filter_type))


def _compute_flaggable_projects(user):
    """
    Feeds the project picker inside the Flag to Management modal (see
    dashboard.html + dashboard.js). The modal's spec (from the UI prompt)
    describes a "read-only project name field" — implying the project is
    already known before the modal opens, which is true when the modal is
    launched from a specific project's own page. But the Decisions Needed
    card's "Flag a Project" shortcut is launched from the DASHBOARD, which
    isn't about any one project, so there's no way to pre-know which
    project the user means. This function supplies a dropdown of that
    user's own active projects to choose from instead, as the pragmatic
    stand-in for that pre-selection. Projects already in the decisions
    queue (decision_needed=True) are excluded — flagging something twice
    isn't a real action, it's already sitting in the queue.
    """
    projects = _scoped_projects(user, active_only=True).filter(
        Project.decision_needed.isnot(True)  # catches False AND NULL, not just False
    ).order_by(Project.name.asc()).all()
    return [{'id': p.id, 'name': p.name} for p in projects]


def _compute_clashes_response(user):
    projects = _scoped_projects(user, active_only=True).all()
    clashes = compute_clashes(projects)

    return {
        'by_deliverable': [
            {
                'designer': _serialize_user(User.query.get(c['designer_id'])),
                'date': c['date'].isoformat(),
                'deliverables': [
                    {'id': d.id, 'name': d.name, 'project_id': d.project_id, 'project_name': d.project.name}
                    for d in c['deliverables']
                ]
            }
            for c in clashes['by_deliverable']
        ],
        'by_project': [
            {
                'designer': _serialize_user(User.query.get(c['designer_id'])),
                'date': c['date'].isoformat(),
                'projects': [{'id': proj.id, 'name': proj.name} for proj in c['projects']]
            }
            for c in clashes['by_project']
        ]
    }


@dashboard_bp.route('/api/clashes')
@login_required
def api_clashes():
    return jsonify(_compute_clashes_response(get_actor()))


# ── Deep-dive zone (UI Chunk 8) ──────────────────────────────────────────
# Projects/Deliverables tabs at the bottom of the dashboard. Everything
# above this point follows a "compute function -> SSR AND JSON API, JS
# fetches on filter/toggle" pattern. This section is different on purpose:
# both tables are fully server-rendered with rich data-* attributes (same
# convention the OLD role dashboards already use — see
# app/templates/dashboards/cs.html's project rows) and BOTH the "At Risk"
# filter chip AND the deadline sort are handled entirely in dashboard.js
# against those attributes, with no round trip to the server — there's
# nothing here worth fetching-on-demand since the full scoped list is
# never large enough to matter. The /api/deep-dive/* routes below return
# the identical data as JSON anyway, since the SSE integration chunk
# (Task #17) will want a way to ask "did anything in this zone change"
# without a full page reload.

def _is_at_risk(project, rag):
    """
    "At Risk" as you defined it when I asked: an open (unresolved) BriefFlag
    on the project, OR decision_needed=True, OR the deadline this row is
    judging itself by is today or already passed ("less than a day away" —
    that's rag == 'red', reusing whatever RAG was already computed for this
    row rather than re-deriving deadline math a second time here).

    Takes `rag` as a parameter rather than computing it internally because
    the two callers below need DIFFERENT deadlines for it: a project row's
    rag is based on nearest_deadline(project) (get_project_rag), but a
    deliverable row's rag is based on that ONE deliverable's own deadline
    (rag_for_deadline(d.design_deadline)) — the "at risk" RULE is identical
    either way, only which deadline feeds it differs per caller.
    """
    has_open_flag = any(not f.is_resolved for f in project.brief_flags)
    return has_open_flag or bool(project.decision_needed) or rag == 'red'


def _compute_deep_dive_projects(user):
    """
    One row per scoped active project — feeds the deep-dive zone's Projects
    tab. See the section comment above for why this is SSR-only with no
    separate filter/sort API traffic.
    """
    results = []
    for p in _scoped_projects(user, active_only=True).all():
        rag = get_project_rag(p)

        entry = {
            'project_id': p.id,
            'name': p.name,
            'job_number': p.job_number,
            'status': p.project_status,
            'brief_type': p.brief_type,
            'cs_lead': _serialize_user(p.cs_lead),
            'secondary_cs': [_serialize_user(a.user) for a in p.secondary_cs_assignments],
            'teams': [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()],
            'designers': [
                {'id': pd.designer.id, 'name': pd.designer.name, 'team': pd.team}
                for pd in p.assigned_designers
            ],
            'rag': rag,
            'at_risk': _is_at_risk(p, rag),
            'first_output_deadline': p.first_output_deadline.isoformat() if p.first_output_deadline else None,
            'final_deadline': p.execution_date.isoformat() if p.execution_date else None,
        }

        # C&CM "X of Y customers" pill (see .dash-customer-progress in
        # dashboard.css — that class was staged in an earlier chunk
        # specifically for this). Cancelled customers don't count toward
        # either number — same convention _compute_due() already uses for
        # deciding which customers are still "live" on a project.
        if p.brief_type == 'ccm':
            active_customers = [pc for pc in p.project_customers if not pc.cancelled]
            approved_customers = [pc for pc in active_customers if pc.status == 'approved']
            entry['customer_progress'] = {'approved': len(approved_customers), 'total': len(active_customers)}
        else:
            entry['customer_progress'] = None

        results.append(entry)

    results.sort(key=lambda r: r['first_output_deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/deep-dive/projects')
@login_required
def api_deep_dive_projects():
    return jsonify(_compute_deep_dive_projects(get_actor()))


def _compute_deep_dive_deliverables(user):
    """
    One row per deliverable belonging to a scoped active project — feeds
    the deep-dive zone's Deliverables tab.

    Team-matching for Designer/Team Lead: _scoped_projects() only scopes at
    the PROJECT level (via ProjectDesigner), which isn't tight enough here
    — a project can carry deliverables for a team this designer ISN'T on
    (e.g. they're assigned to the 3D team on a project that also has 2D
    deliverables). The old role dashboards handle this with a
    Deliverable.teams.contains(team) filter (see app/routes/__init__.py's
    designer_dashboard/team_lead_dashboard) — replicated here by first
    collecting which team(s) this user is actually assigned to on EACH of
    their projects (a designer can be on different teams on different
    projects), then only keeping a deliverable if its own teams overlap.
    CS/Admin/Management see every deliverable on every scoped project, no
    team filtering — matches cs.html's "all deliverables" behaviour.
    """
    projects = _scoped_projects(user, active_only=True).all()
    project_ids = [p.id for p in projects]
    projects_by_id = {p.id: p for p in projects}

    user_teams_by_project = None
    if user.role in ('designer', 'team_lead'):
        user_teams_by_project = {}
        assignments = ProjectDesigner.query.filter(
            ProjectDesigner.user_id == user.id,
            ProjectDesigner.project_id.in_(project_ids)
        ).all()
        for a in assignments:
            user_teams_by_project.setdefault(a.project_id, set()).add(a.team)

    if not project_ids:
        return []

    deliverables = Deliverable.query.filter(Deliverable.project_id.in_(project_ids)).all()

    results = []
    for d in deliverables:
        p = projects_by_id.get(d.project_id)
        if p is None:
            continue  # shouldn't happen (project_ids came from projects_by_id's own keys), defensive only

        d_teams = set(t.strip() for t in (d.teams or '').split(',') if t.strip())

        if user_teams_by_project is not None:
            my_teams = user_teams_by_project.get(d.project_id, set())
            if not (my_teams & d_teams):
                continue

        # Deliverables on a C&CM customer inherit that customer's deadline
        # when they have none of their own — same fallback the old
        # deliverable tables use (cs.html / designer.html / team_lead.html).
        deadline = d.design_deadline or (d.project_customer.design_deadline if d.project_customer else None)
        rag = rag_for_deadline(deadline)

        results.append({
            'deliverable_id': d.id,
            'project_id': d.project_id,
            'project_name': p.name,
            'name': d.name,
            'status': d.status,
            'teams': sorted(d_teams),
            'deadline': deadline.isoformat() if deadline else None,
            'rag': rag,
            # "At risk" for a deliverable row rides on its PARENT project's
            # flag/decision state (a flag is raised against the project or
            # a specific deliverable, but either way it's the whole
            # project's next action that's blocked) combined with this
            # deliverable's OWN deadline urgency, not the project's nearest
            # deadline overall.
            'at_risk': _is_at_risk(p, rag),
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/deep-dive/deliverables')
@login_required
def api_deep_dive_deliverables():
    return jsonify(_compute_deep_dive_deliverables(get_actor()))
