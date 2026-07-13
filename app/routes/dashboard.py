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
    # 'my-week' -> 'summary' is now a no-op: Summary ("My Day / My Week")
    # is always open regardless of initial_expanded_card as of 12 Jul 2026's
    # fourth follow-up (see summary.html / dash_card()'s mode=None branch
    # in _dashboard_macros.html) — left here since auth.py's login redirect
    # may still send ?view=my-week and there's no harm in the key resolving
    # to something, it just no longer does anything on the receiving end.
    'my-week': 'summary',
    'at-risk': 'at_risk',
}

# Card order below the always-full-width Summary card, per role. Only the
# FIRST entry per role is actually specified in the brief ("X card appears
# first") — the rest of the order is a judgment call, easy to change later
# since it's just a list.
#
# 'stat_active' / 'stat_pending' / 'stat_total' (added 12 Jul 2026,
# twelfth follow-up, per Ezekiel: "make them in the same style as the
# others and same size and make them the first 3 cards") are prepended to
# EVERY role's list — these used to be the separate, non-tile
# .dash-stats-row above the grid (see dashboard.html's git history around
# 12 Jul 2026 if that markup needs resurrecting); they're now ordinary
# tiles like everything else, just always first regardless of role. See
# stat_active.html / stat_pending.html / stat_total.html for why they
# don't use dash_card()'s tile/body split the way every other card does.
_STAT_TILES = ['stat_active', 'stat_pending', 'stat_total', 'stat_avg_time']

CARD_ORDER = {
    'management': _STAT_TILES + ['decisions', 'at_risk', 'what_changed', 'due', 'next_actions', 'clashes', 'brief_quality'],
    'admin':      _STAT_TILES + ['decisions', 'at_risk', 'what_changed', 'due', 'next_actions', 'clashes', 'brief_quality'],
    'cs':         _STAT_TILES + ['due', 'decisions', 'at_risk', 'what_changed', 'next_actions', 'clashes', 'brief_quality'],
    'designer':   _STAT_TILES + ['clashes', 'due', 'decisions', 'at_risk', 'what_changed', 'next_actions', 'brief_quality'],
    'team_lead':  _STAT_TILES + ['clashes', 'due', 'decisions', 'at_risk', 'what_changed', 'next_actions', 'brief_quality'],
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


# ── Management/admin view-switcher (added 11 Jul 2026, extended to admin
#    12 Jul 2026) ───────────────────────────────────────────────────────
# A tab bar at the top of the dashboard, MANAGEMENT AND ADMIN ONLY, that
# lets the viewer preview this same page scoped to a different set of
# eyes — their own CS-Lead-style slice, any individual CS lead's exact
# view, or the full unfiltered view (today's only behaviour, still the
# default for every other role — cs/designer/team_lead never see this tab
# bar at all).
#
# IMPORTANT — this is NOT the existing "emulation-aware actor" pattern
# documented in CLAUDE.md (session['emulating_user_id'], used so an admin's
# WRITE actions get logged/notified as the person they're emulating). This
# is read-only, doesn't touch the session, and never changes who a write
# action is attributed to — get_actor() and effective_role are completely
# untouched by it. It only changes what _scoped_projects() considers "my
# projects" for the DATA this page queries. Conflating the two would be a
# mistake — don't reach for session['emulating_user_id'] here.
_SCOPE_SWITCHER_ROLES = ('management', 'admin')
class _ScopeUser:
    """
    Duck-types a real User for _scoped_projects()'s .id/.role checks (and
    _is_owner()'s .id check) ONLY — nothing else on this page ever looks at
    it. Lets _resolve_dashboard_scope() hand back "pretend you're CS lead
    X" without constructing (or worse, actually querying-as) a real
    Flask-Login session for that user.
    """
    def __init__(self, id, role):
        self.id = id
        self.role = role


def _resolve_dashboard_scope(user):
    """
    Reads the ?scope= query param and decides whose eyes to scope the
    dashboard's data through. Only ever branches for user.role in
    _SCOPE_SWITCHER_ROLES ('management', 'admin') — every other role gets
    scope_mode=None and the real `user` object back unchanged, so
    _scoped_projects() and everything downstream behaves EXACTLY as it did
    before this feature existed for them.

    Modes:
      'my'  (default) — projects this viewer is personally involved in. In
             this app's data model the only way a non-designer "owns" a
             project is being CS Lead or secondary CS on it (see
             CLAUDE.md's "Management role in CS pickers" — management AND
             admin users are both valid CS Lead picks), so this reuses
             _scoped_projects()'s existing 'cs' branch with the real
             viewer's own id. Decisions Needed is the one exception,
             widened to EVERY flagged project company-wide by the
             all_flags=True path on _compute_decisions() below — per spec
             this tab shows "ALL flags raised", not just the ones on
             projects this particular viewer happens to lead.
      'cs_<id>' — exactly what that CS lead's own dashboard shows them:
             same 'cs' branch, but with THAT user's id. Decisions stays
             normally scoped here (not widened) — this is a preview of
             their real page, not a management/admin-specific view.
      'all' — today's original behaviour: everything, unfiltered.

    Returns (scope_mode, scope_user, cs_leads) — cs_leads (every role='cs'
    user, for building one tab per lead) is returned even when scope_mode
    is None since dashboard.html needs it any time it's rendering for a
    management/admin user, and computing it here once is cheaper than
    every caller re-querying it.
    """
    cs_leads = User.query.filter_by(role='cs').order_by(User.name.asc()).all()

    if user.role not in _SCOPE_SWITCHER_ROLES:
        return None, user, cs_leads

    requested = request.args.get('scope', 'my')

    if requested == 'all':
        return 'all', user, cs_leads

    if requested.startswith('cs_'):
        try:
            target_id = int(requested[3:])
        except ValueError:
            target_id = None
        target = next((c for c in cs_leads if c.id == target_id), None)
        if target:
            return requested, _ScopeUser(target.id, 'cs'), cs_leads
        # Unknown/stale id (e.g. a CS lead removed since this URL/tab was
        # bookmarked) — fall through to 'my' rather than 403ing or
        # silently rendering the full unfiltered 'all' view.

    return 'my', _ScopeUser(user.id, 'cs'), cs_leads


@dashboard_bp.route('')
@login_required
def index():
    user = get_actor()
    initial_view = request.args.get('view', '')
    scope_mode, scope_user, cs_leads = _resolve_dashboard_scope(user)

    # Card order + deep-dive default tab normally follow the REAL role.
    # Exception: previewing a specific CS lead's tab should look like
    # their actual dashboard, ordering included — not management's own
    # layout with someone else's data dropped into it. 'my' mode keeps
    # management's own order (it's still fundamentally "my dashboard",
    # just narrowed), only 'cs_<id>' borrows the 'cs' role's order.
    layout_role = 'cs' if (scope_mode or '').startswith('cs_') else user.role

    return render_template(
        'dashboard.html',
        effective_role=user.role,
        scope_mode=scope_mode,
        cs_leads=cs_leads,
        card_order=CARD_ORDER.get(layout_role, CARD_ORDER['management']),
        initial_expanded_card=VIEW_TO_CARD.get(initial_view),
        default_tab=DEFAULT_TAB.get(layout_role, 'projects'),
        # Feeds the three stat tiles (stat_active/stat_pending/stat_total
        # — first 3 in CARD_ORDER as of 12 Jul 2026's twelfth follow-up,
        # was a separate non-tile stat row before that) — see
        # _compute_project_stats()'s docstring for the scoping rules.
        project_stats=_compute_project_stats(scope_user),
        summary=_compute_summary(scope_user),
        what_changed=_compute_what_changed(scope_user),
        # Due card narrowed 12 Jul 2026 (fourth follow-up) to show ONLY
        # overdue-this-week, no toggles — was "Overdue + Due Today
        # combined" (filter_type='overdue_today') before that. 'overdue'
        # is already scoped to the 1-7-day window (see _compute_due()'s
        # docstring), so this is a straight filter swap, no new logic.
        due_default=_compute_due(scope_user, 'overdue'),
        # Summary card's two columns (UI Chunk 2) — separate from due_default
        # above: the Summary card wants a strict "Today" list and a "This
        # Week" list side by side, not the Due card's overdue+today merge.
        # Reuses the exact same _compute_due() the Due card and the
        # /api/due?filter= endpoint use, just called with different filter
        # values, so all three places agree on what counts as "due today".
        due_today_items=_compute_due(scope_user, 'today'),
        due_week_items=_compute_due(scope_user, 'week'),
        # all_flags=True only on the 'my' tab — see
        # _resolve_dashboard_scope()'s docstring for why.
        decisions=_compute_decisions(scope_user, all_flags=(scope_mode == 'my')),
        # Next Actions card defaults to the "My Actions" tab on first paint
        # (see next_actions.html) — "Others' Actions" is fetched client-side
        # on demand, same SSR-default-then-fetch-on-toggle split as the Due
        # card's due_default/fetchAndRenderDue().
        next_actions_default=_compute_next_actions(scope_user, 'mine'),
        clashes=_compute_clashes_response(scope_user),
        # At Risk card (added 12 Jul 2026) — staffing gaps (missing CS/
        # designer) + overdue-this-week, one row per project with whichever
        # tags apply. Fully server-rendered, no filter tabs — see
        # _compute_at_risk_projects()'s docstring for the full tag logic.
        at_risk_projects=_compute_at_risk_projects(scope_user),
        # Only CS/Designer/Team Lead ever see the "Flag a Project" button
        # (Management has no reason to flag something to itself), so skip
        # the extra query entirely for roles that can't open the modal.
        # Deliberately keyed on the REAL user.role, not layout_role/scope —
        # previewing a CS lead's tab must never grant management the
        # ability to submit a flag as that person.
        flaggable_projects=_compute_flaggable_projects(user) if user.role in ('cs', 'designer', 'team_lead') else [],
        # Deep-dive zone — at-risk-only extension of the cards above (see the
        # big comment on _is_at_risk()/_compute_deep_dive_projects() further
        # down for the 10 Jul 2026 rework). Fully server-rendered, no
        # client-side filter/sort left to do — this IS the complete dataset.
        deep_dive_projects=_compute_deep_dive_projects(scope_user),
        deep_dive_deliverables=_compute_deep_dive_deliverables(scope_user),
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


def _serialize_person(u):
    """
    Like _serialize_user(), but carries avatar_filename too (added 13 Jul
    2026 for the Due row redesign's CS lead / designer avatar chips — see
    dash_person_chip() in _dashboard_macros.html). Kept separate from
    _serialize_user() rather than just adding the field there, since that
    one backs the older owner-tag (guidance) pills elsewhere on this page
    and there's no reason to widen its payload for consumers that don't
    need an avatar.
    """
    if not u:
        return None
    return {'id': u.id, 'name': u.name, 'avatar_filename': u.avatar_filename}


def _due_row_people(project, teams):
    """
    Per-team designer lookup for a Due row (added 13 Jul 2026, per Ezekiel:
    "add designer assigned to that deliverable ... any unassigned, use the
    same logic we used for at risk section of the labelling").

    `teams` is the list of team names relevant to THIS row — d.teams for a
    deliverable row (designer assigned to that specific deliverable), or
    project.design_teams_requested for a customer/project-level row (no
    single deliverable to scope to, so it falls back to the same
    project-wide staffing view _compute_at_risk_projects() already uses).

    Returns one entry per team: {'team': t, 'users': [serialized designer,
    ...]} — 'users' is empty when nobody's assigned to that team yet, which
    the template/JS render as the same "<Team> Designer Missing" tag
    _TEAM_MISSING_LABELS already defines for the At Risk card, so an
    unstaffed team reads identically in both places rather than inventing a
    second wording for the same fact.
    """
    by_team = {}
    for pd in project.assigned_designers:
        by_team.setdefault(pd.team, []).append(pd.designer)

    results = []
    for t in teams:
        users = [_serialize_person(u) for u in by_team.get(t, [])]
        # Missing-label text computed here, not in the template, so it's
        # the exact same wording _TEAM_MISSING_LABELS already defines for
        # the At Risk card — one source of truth for "how do we phrase an
        # unstaffed team" instead of a second copy of the map in Jinja.
        results.append({
            'team': t,
            'users': users,
            'missing_label': None if users else _TEAM_MISSING_LABELS.get(t, f'{t} Missing'),
        })
    return results


# ── Compute functions ────────────────────────────────────────────────────
# Each one returns a plain dict/list — no Flask Response involved — so the
# SAME function backs both the initial server-rendered page (index() above)
# and the JSON endpoint below it. One source of truth for what each card
# shows, instead of the page and the API silently drifting apart.

# Team name -> exact tag wording, per spec (note "Technical Missing" has no
# "Designer" in it — that's deliberate, matching exactly how it was
# requested, not an inconsistency to "fix"). Any future team name not in
# this map falls back to "<Team> Missing" via .get()'s default in
# _compute_at_risk_projects() below.
_TEAM_MISSING_LABELS = {
    '3D': '3D Designer Missing',
    '2D': '2D Designer Missing',
    'Technical': 'Technical Missing',
}


def _missing_designer_tags(project):
    """
    Which of a project's REQUESTED design teams (design_teams_requested)
    have no project-level Lead Designer assigned yet — the exact staffing-
    gap check _compute_at_risk_projects() originated (12 Jul 2026). Pulled
    out into its own helper 13 Jul 2026 so Next Actions and Clashing
    Projects can show the same tag without copying the logic a second
    time — see CLAUDE.md's "Missing-designer tag, everywhere" section.

    Checks project.assigned_designers (the project-level "Assigned Lead
    Designers" table), NOT per-deliverable assignment — same scope
    _compute_at_risk_projects() and _due_row_people()'s project-level
    fallback already use, so a project reads as "missing" or "staffed" the
    same way regardless of which card is looking at it.

    Returns a list of label strings — usually 0 or 1 entries ('All
    Designers Missing' replaces the individual per-team labels once every
    requested team is unstaffed, same collapsing rule as before), never
    per-team AND the "All" label at once.
    """
    requested_teams = [t.strip() for t in (project.design_teams_requested or '').split(',') if t.strip()]
    if not requested_teams:
        return []

    assigned_teams = {d.team for d in project.assigned_designers}
    missing_teams = [t for t in requested_teams if t not in assigned_teams]
    if not missing_teams:
        return []

    if len(missing_teams) == len(requested_teams):
        return ['All Designers Missing']

    return [_TEAM_MISSING_LABELS.get(t, f'{t} Missing') for t in missing_teams]


def _compute_at_risk_projects(user):
    """
    "At Risk" card (added 12 Jul 2026, per management review). NOT the same
    thing as _is_at_risk() further down (that's the deep-dive zone's
    BriefFlag/decision/RAG-red filter, a completely different rule for a
    completely different section of the page) — this is a staffing-gap +
    overdue check, one row per project, each row carrying whichever tags
    apply:

      - 'CS Missing' — project.cs_lead_id is unset. cs_lead_id is NOT NULL
        in the schema today ("there is always a CS on a project now" —
        Ezekiel), so this can't actually fire yet, but the column is
        planned to become nullable later for a specific reason, and this
        check is written to already be correct the moment that happens
        rather than needing to be revisited then.
      - '<Team> Designer Missing' — one of the project's REQUESTED teams
        (design_teams_requested) has no ProjectDesigner (the project-level
        "Lead Designer" per team — the same "Assigned Lead Designers" table
        on the detail page, NOT per-deliverable assignment) for that team.
        Context-aware by construction: only requested teams are ever
        checked, so a project that never requested Technical is never
        tagged "Technical Missing" — and since nothing here is cached or
        stored, if Technical gets added to the brief later this recomputes
        fresh on the very next page load with no extra wiring needed.
      - 'All Designers Missing' — replaces the individual per-team tags
        above when EVERY requested team is missing its designer, instead of
        stacking three redundant "X Missing" tags on one row.
      - 'Overdue' — nearest_deadline(project) is 1-7 days in the past.
        Deliberately bounded to "this week", not indefinitely overdue — see
        the big comment on this card in CLAUDE.md for the reasoning.

    A project can carry more than one tag at once (e.g. missing a designer
    AND overdue this week) — that's still one row with multiple tags, never
    duplicate rows for the same project.

    Each tag is now a {'label':, 'variant':} dict, not a bare string
    (changed 13 Jul 2026 alongside _missing_designer_tags() below, reshaped
    again same day from an earlier {'label':,'red':} boolean version so
    Overdue could get its OWN look instead of sharing the designer-missing
    red). `variant` is one of:
      - 'overdue' — red + pulsing (per Ezekiel: "Make overdue red and make
        it pulse or flash") — see .dash-risk-tag--overdue in dashboard.css.
      - 'designer_missing' — solid red, same .dash-risk-tag--red
        dash_due_row()'s missing-designer chips use everywhere else.
      - 'plain' — the card's original rose .dash-risk-tag (CS Missing
        only) — a data gap, not a staffing gap or a schedule miss, so it
        doesn't borrow either of the other two colours.
    Tag ORDER also changed same day, per Ezekiel ("date in plain black
    text, vertical divider, then the name, overdue tag then 2D designer
    missing"): Overdue now appended FIRST, then CS Missing — was
    designer-missing-then-Overdue. Safe to reshape/reorder without a JS
    parity update — this card's row list has no live-refresh JS mirror,
    only its mini-stat count does (see at_risk.html's docstring).

    Designer-missing labels are DELIBERATELY NOT in this `tags` list
    anymore (same-day follow-up, per Ezekiel: "at risk is duplicating the
    tags - only one missing tag is needed") — they used to be appended
    here too, which meant a missing team showed BOTH as a top-row
    .dash-risk-tag AND as a red chip in the dash_row_people() line below
    (see item.designers), the exact same fact stated twice on one row.
    The chip version is strictly more informative (it's IN the people row,
    next to who's actually assigned) so it wins; `has_missing_designer`
    below still folds the check into whether the project qualifies as
    "at risk" at all, it just doesn't duplicate it into `tags`.
    """
    today = date.today()
    results = []

    for p in _scoped_projects(user, active_only=True).all():
        tags = []
        has_missing_designer = bool(_missing_designer_tags(p))

        deadline = nearest_deadline(p)
        if deadline:
            days_overdue = (today - deadline).days
            if 1 <= days_overdue <= 7:
                tags.append({'label': 'Overdue', 'variant': 'overdue'})

        if not p.cs_lead_id:
            tags.append({'label': 'CS Missing', 'variant': 'plain'})

        if not tags and not has_missing_designer:
            continue

        # Added 13 Jul 2026, per Ezekiel: "add the tags you have already
        # made (with their profile pic included) for the relevant
        # designers and CS leads" — same dash_person_chip() avatar+name
        # chips dash_due_row() shows, project-level (there's no single
        # deliverable to scope to on this card, same fallback
        # _due_row_people()'s project/customer rows already use).
        requested_teams = [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()]
        results.append({
            'project_id': p.id,
            'name': p.name,
            'tags': tags,
            'deadline': deadline.isoformat() if deadline else None,
            'rag': get_project_rag(p),
            'cs_lead': _serialize_person(p.cs_lead),
            'designers': _due_row_people(p, requested_teams),
        })

    # Nearest deadline first, same convention as the deep-dive zone's
    # project list — projects with no deadline at all sort last.
    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


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
                # Overdue is scoped to "this week" (1-7 days overdue), same
                # window as _compute_due()'s 'overdue'/'overdue_today'
                # filters and the At Risk card's own overdue check (see
                # _compute_at_risk_projects()) — changed 12 Jul 2026 per
                # management review. This count feeds the Due card's
                # collapsed mini-stat (due.html reads summary.overdue), so
                # it has to agree with what the expanded "Overdue" pill
                # actually lists, or the two would silently disagree.
                if (today - deadline).days <= 7:
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
    # Broken out by severity (not just a total) so the collapsed Clashing
    # Projects pill — and dashboard.js's SSE live-refresh of that same pill,
    # which reuses this endpoint — can show "N Detected" / "M Potential"
    # separately, matching the severity language already used inside the
    # expanded card (see _clash_severity() in dashboard_logic.py). by_project
    # clashes have no potential/detected split (execution_date has no time
    # component — every by_project group is a certain clash), so they always
    # count toward "detected".
    clash_detected = len(clashes['by_project']) + sum(1 for c in clashes['by_deliverable'] if c['severity'] == 'clash')
    clash_potential = sum(1 for c in clashes['by_deliverable'] if c['severity'] == 'potential')
    clash_count = clash_detected + clash_potential

    return {
        'what_changed': what_changed,
        'due_today': due_today,
        'due_week': due_week,
        'overdue': overdue,
        'decisions_needed': decisions_needed,
        'my_actions': my_actions,
        'others_actions': others_actions,
        'clashes': clash_count,
        'clashes_detected': clash_detected,
        'clashes_potential': clash_potential,
        # At Risk card's collapsed mini-stat (added 12 Jul 2026) — like
        # Clashes, the At Risk card's row list is fully server-rendered
        # with no client-side fetch-on-toggle (see at_risk.html), so only
        # the COUNT needs to travel through /api/summary for SSE
        # live-refresh; the list itself just goes stale until next reload,
        # same acceptable-staleness convention Clashes uses.
        'at_risk_count': len(_compute_at_risk_projects(user)),
    }


def _compute_project_stats(user):
    """
    The stat tiles — Your Active Projects / Pending Approval / Total
    Active Projects / Average Time, in that order, always first in
    CARD_ORDER (see _STAT_TILES above). The first three were added 12 Jul
    2026 as a separate non-tile stat row above the grid; folded into the
    normal tile grid as its own first-3 entries in the twelfth follow-up
    the same day, per Ezekiel ("same style as the others and same size").
    Average Time was added 13 Jul 2026 as a 4th entry in this same family
    (see the big comment further down, near `average_time`). Unlike every
    other tile these are pure display: no expand/collapse, no body, no
    filter pills, just a number — so unlike the rest of card_order,
    stat_active.html/stat_pending.html/stat_total.html/stat_avg_time.html
    don't use dash_card()'s mode='tile'/'body' split at all, they just
    render a static .dash-tile directly on the 'tile' pass and nothing on
    the 'body' pass. This one function still feeds both the initial page
    load and the SSE live-refresh's /api/project-stats fetch.

    'your_active' and 'pending_approval' both respect `user` — in
    practice this is always scope_user from _resolve_dashboard_scope() at
    the call site, so these two numbers follow the management/admin
    view-switcher exactly like every other card (see the big comment on
    _resolve_dashboard_scope() further up).

    'total_active' is deliberately UNSCOPED — every active project
    company-wide, regardless of role or which view-switcher tab is
    active. Same "counts as everything, on purpose" idea as the Decisions
    Needed card's all_flags=True path on My View (_compute_decisions()) —
    it's the one number on this row meant to answer "how many are there
    really", not "how many are mine".

    "Pending Approval" = project_status == 'submitted_to_client' — the
    exact status string used everywhere else in the app for this state
    (see projects_approval.py's "Project must be in Submitted to Client
    state to approve" check), not a new label invented for this card.
    """
    your_active = _scoped_projects(user, active_only=True).count()
    pending_approval = _scoped_projects(user, active_only=True).filter(
        Project.project_status == 'submitted_to_client'
    ).count()
    total_active = Project.query.filter(
        Project.project_status.notin_(['draft', 'approved'])
    ).count()

    # "Average Time" tile (added 13 Jul 2026, per Ezekiel: "add a card that
    # has the project tracking number from the model we added earlier ...
    # display the average time of the numbers tracked") — averages each
    # scoped project's business-hours "overall" total, computed on demand
    # from its ProjectStatusLog history via time_tracking_logic.py (see
    # that module's docstring for the full business-hours/weekend-discard
    # rules and app/status_tracking.py's record_project_status() for why
    # there's no separate accumulator field feeding this anymore — same
    # StatusLog-derived computation also backs the full project+deliverable
    # breakdown page at /time-tracking).
    #
    # Same scope as your_active/pending_approval (respects the
    # management/admin view-switcher via `user` = scope_user at the call
    # site), NOT total_active's company-wide/unscoped query — "average time
    # on MY projects" reads as the more useful default for this tile.
    #
    # Only averaged over projects with overall > 0 — a project that's
    # never left an excluded status (in_queue, etc.) yet has 0 by
    # construction, not "zero time worked", so including it would silently
    # drag the average toward zero rather than reflect real turnaround
    # time. Same judgment call as before, now applied to the derived value.
    from app.time_tracking_logic import compute_project_hours
    tracked_hours = [
        h for p in _scoped_projects(user, active_only=True).all()
        if (h := compute_project_hours(p)['overall']) > 0
    ]
    average_time = round(sum(tracked_hours) / len(tracked_hours), 1) if tracked_hours else 0.0

    return {
        'your_active': your_active,
        'pending_approval': pending_approval,
        'total_active': total_active,
        'average_time': average_time,
    }


@dashboard_bp.route('/api/project-stats')
@login_required
def api_project_stats():
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_project_stats(scope_user))


@dashboard_bp.route('/api/summary')
@login_required
def api_summary():
    # Scope-aware since 11 Jul 2026 (management view-switcher) — the SSE
    # live-refresh in dashboard.js hits this endpoint with whatever
    # ?scope= the page currently has loaded (see HELIX_DASH_SCOPE in
    # dashboard.html) so the collapsed pills never drift back to the
    # unfiltered view mid-session. See _resolve_dashboard_scope().
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_summary(scope_user))


def _compute_what_changed(user):
    """
    Activity log entries since yesterday, scoped by role. Returns the
    existing free-text description rather than structured field/old/new
    values — ActivityLog only ever stored a description string, so there's
    no old/new value data to surface (deliberate call, not an oversight).

    Row layout matched to Overdue (13 Jul 2026, per Ezekiel: "date on the
    left like overdue... information on top, project name small
    underneath, name of owner of the information on the right with their
    profile pic"). 'changed_by' switched from a plain name string to
    _serialize_person(e.user) so what_changed.html can render it through
    dash_person_chip() (needs avatar_filename) instead of a plain
    .dash-owner-tag pill — same avatar+name treatment as everywhere else
    on the dashboard now. Still None for system-triggered entries with no
    user_id, same as before.
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
            'changed_by': _serialize_person(e.user) if e.user else None
        }
        for e in entries
    ]


@dashboard_bp.route('/api/what-changed')
@login_required
def api_what_changed():
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_what_changed(scope_user))


def _compute_due(user, filter_type):
    """
    Returns individual due items, sorted by urgency (earliest deadline
    first — which for 'overdue' also means most-overdue first).

    filter_type: 'today' | 'week' | 'overdue' | 'overdue_today' (the Due
    card's default view — overdue and due-today combined into one list).

    'overdue' is scoped to THIS WEEK only (1-7 days overdue), not
    indefinitely overdue — changed 12 Jul 2026 per management review, same
    window the At Risk card's own overdue check uses (see
    _compute_at_risk_projects()) and same window _compute_summary() now
    applies when counting summary['overdue'] for this card's collapsed
    mini-stat, so the two never disagree.

    Granularity varies by project type since that's where the real deadline
    data lives: Standard projects surface individual Deliverables (a project
    can have several, each due on a different day); C&CM projects surface
    individual pending customers (their POSM channel deadlines); a Standard
    project with no deliverable deadlines yet falls back to one project-level
    entry using execution_date, same fallback nearest_deadline() uses.
    """
    today = date.today()
    week_end = today + timedelta(days=7)
    overdue_start = today - timedelta(days=7)

    def matches(d):
        if d is None:
            return False
        if filter_type == 'overdue':
            return overdue_start <= d < today
        if filter_type == 'today':
            return d == today
        if filter_type == 'week':
            return today <= d <= week_end
        if filter_type == 'overdue_today':
            return overdue_start <= d <= today
        return False

    results = []
    for p in _scoped_projects(user, active_only=True).all():
        owner = get_next_action_owner(p)
        rag = get_project_rag(p)
        owner_json = _serialize_owner(owner['user'])
        # cs_lead + project-level requested teams (13 Jul 2026, Due row
        # redesign — see _due_row_people()'s docstring). project_teams is
        # the fallback team list for row types with no single deliverable
        # to scope to (customer/project-level rows) — same
        # design_teams_requested field _compute_at_risk_projects() checks.
        cs_lead_json = _serialize_person(p.cs_lead)
        project_teams = [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()]
        common = {
            'rag': rag, 'owner': owner_json, 'owner_role': owner['role'], 'guidance': owner['guidance'],
            'cs_lead': cs_lead_json,
        }

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
                        'designers': _due_row_people(p, project_teams),
                    })
        else:
            matched_any_deliverable = False
            for d in p.project_deliverables:
                if matches(d.design_deadline):
                    matched_any_deliverable = True
                    # Deliverable-scoped teams, NOT project_teams — "designer
                    # assigned to THAT deliverable", per Ezekiel, same
                    # d.teams field standard_designers_by_deliverable
                    # already uses on the project detail page.
                    d_teams = [t.strip() for t in (d.teams or '').split(',') if t.strip()]
                    results.append({
                        **common,
                        'type': 'deliverable',
                        'project_id': p.id,
                        'project_name': p.name,
                        'deliverable_id': d.id,
                        'deliverable_name': d.name,
                        'deadline': d.design_deadline.isoformat(),
                        'designers': _due_row_people(p, d_teams),
                    })
            if not matched_any_deliverable and matches(p.execution_date):
                results.append({
                    **common,
                    'type': 'project',
                    'project_id': p.id,
                    'project_name': p.name,
                    'deadline': p.execution_date.isoformat(),
                    'designers': _due_row_people(p, project_teams),
                })

    results.sort(key=lambda r: r['deadline'])
    return results


@dashboard_bp.route('/api/due')
@login_required
def api_due():
    # Default changed 12 Jul 2026 (fourth follow-up) from 'overdue_today'
    # to 'overdue', matching the Due card's new overdue-only scope — the
    # 'today'/'week' filter values are still fully supported and still
    # used by the Summary card's due_today_items/due_week_items (see
    # index() above), just no longer reachable from the Due card itself.
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    filter_type = request.args.get('filter', 'overdue')
    return jsonify(_compute_due(scope_user, filter_type))


def _compute_decisions(user, all_flags=False):
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

    all_flags=True (added 11 Jul 2026 for the "My View" tab, see
    _resolve_dashboard_scope()) bypasses _scoped_projects() entirely and
    returns EVERY flagged, non-draft project company-wide, regardless of
    `user`. Per spec, My View's Decisions Needed shows "ALL flags raised"
    — not narrowed to just the projects this particular viewer happens to
    be CS Lead on, unlike every other card on that tab.
    """
    if all_flags:
        base = Project.query.filter(Project.project_status != 'draft')
    else:
        base = _scoped_projects(user, active_only=True)

    projects = base.filter(
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
    scope_mode, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_decisions(scope_user, all_flags=(scope_mode == 'my')))


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

    Row layout matched to Overdue (13 Jul 2026, per Ezekiel: "make the
    layout of the rows match Overdue layout") — this function now emits
    the same shape dash_due_row()/renderDueRow() expect: 'type': 'project'
    (there's no deliverable/customer to invert the title against, same as
    a plain project-level Due row), 'cs_lead' (_serialize_person(p.cs_lead))
    and 'designers' (_due_row_people(p, requested_teams), project-level
    fallback — no single deliverable to scope to here, same as At Risk/
    Clashing Projects' by-project rows). 'missing_designer_tags' was
    REMOVED from this payload in the same pass — it's now fully redundant
    with the red fallback chips 'designers' already produces per unstaffed
    team (both ultimately check project.assigned_designers against
    design_teams_requested via the same _TEAM_MISSING_LABELS wording), and
    showing it a second time as a flat tag would repeat the exact
    duplicate-indicator bug the At Risk card had to be fixed for earlier
    the same day. 'owner'/'owner_role' stay on the payload (still needed
    internally for the is_mine split above) but, like Due's own rows,
    aren't rendered by dash_due_row() — CS lead/designer chips replace
    what the owner tag used to show.
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
        requested_teams = [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()]
        results.append({
            'project_id': p.id,
            'type': 'project',
            'project_name': p.name,
            'guidance': owner_info['guidance'],
            'owner': _serialize_owner(owner_info['user']),
            'owner_role': owner_info['role'],
            'rag': get_project_rag(p),
            'deadline': deadline.isoformat() if deadline else None,
            'cs_lead': _serialize_person(p.cs_lead),
            'designers': _due_row_people(p, requested_teams),
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/next-actions')
@login_required
def api_next_actions():
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    filter_type = request.args.get('filter', 'mine')
    return jsonify(_compute_next_actions(scope_user, filter_type))


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
    """
    cs_lead/designers added 13 Jul 2026, per Ezekiel: "add the tags you
    have already made (with their profile pic included) for the relevant
    designers and CS leads. Add it to at risk, clashing projects." Same
    _serialize_person()/_due_row_people() pair dash_due_row() and At Risk
    use. By-deliverable entries scope designers to that deliverable's OWN
    teams (d.teams — "designer assigned to THAT deliverable", same as
    _compute_due()'s deliverable rows); by-project entries fall back to
    the project's design_teams_requested (no single deliverable to scope
    to), same as At Risk.

    Group-heading designer (the one clashing designer a whole group is
    named after, NOT the per-row cs_lead/designers above) switched from
    _serialize_user() to _serialize_person() same-day follow-up, per
    Ezekiel: "Designer name -> Profile picture + name" — needs
    avatar_filename so clashes.html can render it through
    dash_person_chip() instead of a plain text .dash-owner-tag pill.
    """
    projects = _scoped_projects(user, active_only=True).all()
    clashes = compute_clashes(projects)

    return {
        'by_deliverable': [
            {
                'designer': _serialize_person(User.query.get(c['designer_id'])),
                'date': c['date'].isoformat(),
                # 'clash' | 'potential' — see _clash_severity() in
                # dashboard_logic.py for the exact rule. Rendered as
                # "Clash Detected" / "Potential Clash" in clashes.html.
                'severity': c['severity'],
                'deliverables': [
                    {
                        'id': d.id,
                        'name': d.name,
                        'project_id': d.project_id,
                        'project_name': d.project.name,
                        # Shown alongside each deliverable now that severity
                        # depends on whether times actually match — None
                        # stays None (not '—') so the template can decide
                        # how to phrase "no time set" itself.
                        'time': d.design_deadline_time.strftime('%H:%M') if d.design_deadline_time else None,
                        # Added 13 Jul 2026, per Ezekiel — same red
                        # missing-designer tag as At Risk/Overdue/Next
                        # Actions, checked against d's OWN project (a clash
                        # group can span multiple projects, so this can't
                        # be hoisted up to the group level) — see
                        # _missing_designer_tags().
                        'missing_designer_tags': _missing_designer_tags(d.project),
                        'cs_lead': _serialize_person(d.project.cs_lead),
                        'designers': _due_row_people(
                            d.project,
                            [t.strip() for t in (d.teams or '').split(',') if t.strip()]
                        ),
                    }
                    for d in c['deliverables']
                ]
            }
            for c in clashes['by_deliverable']
        ],
        'by_project': [
            {
                'designer': _serialize_person(User.query.get(c['designer_id'])),
                'date': c['date'].isoformat(),
                'projects': [
                    {
                        'id': proj.id,
                        'name': proj.name,
                        'missing_designer_tags': _missing_designer_tags(proj),
                        'cs_lead': _serialize_person(proj.cs_lead),
                        'designers': _due_row_people(
                            proj,
                            [t.strip() for t in (proj.design_teams_requested or '').split(',') if t.strip()]
                        ),
                    }
                    for proj in c['projects']
                ]
            }
            for c in clashes['by_project']
        ]
    }


@dashboard_bp.route('/api/clashes')
@login_required
def api_clashes():
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_clashes_response(scope_user))


# ── Deep-dive zone ────────────────────────────────────────────────────────
# Projects/Deliverables tabs at the bottom of the dashboard.
#
# REWORKED 10 Jul 2026 — originally an all-scoped-projects browsable table
# (every column: job number, type, teams, CS Lead, status, an "All"/"At Risk"
# filter chip, a deadline-sort toggle — see git history / UI Chunk 8 for that
# version). That table substantially duplicated the OLD Projects page
# (main.projects — cs.html/designer.html/team_lead.html), which already does
# full search + CS Lead/Status/Designer filtering + multiple views, and doing
# it BETTER than a cut-down copy ever would. Two "browse all projects"
# screens meant neither was fully trusted, and the wide table also couldn't
# fit in the side-by-side layout without horizontal overflow.
#
# Decision (discussed with Ezekiel 10 Jul 2026): draw a hard line —
# Dashboard = at-a-glance, "here's what needs your eyes"; old Projects page =
# where you go to actually search/filter/manage/edit. So the deep-dive zone
# stopped being a second directory and became a narrow extension of the
# cards above it: ONLY at-risk projects/deliverables (same _is_at_risk() rule
# already used elsewhere on this page), rendered as compact .dash-row rows
# (like every other card) instead of a wide <table>, with no filter chip
# (there's only ever one thing to show now) and no deadline-sort toggle
# (already pre-sorted by nearest deadline, same as Due/Next Actions). This
# also fixed the side-by-side overflow — a .dash-row wraps in a narrow
# column; a multi-column <table> didn't.
#
# Both compute functions below are still fully server-rendered with no
# separate filter/sort JS — there's just nothing left to filter or sort
# client-side now that "at risk" is the only state a row can be in.

def _is_at_risk(project, rag):
    """
    "At Risk" as defined when this was originally built: an open
    (unresolved) BriefFlag on the project, OR decision_needed=True, OR the
    deadline this row is judging itself by is today or already passed
    ("less than a day away" — that's rag == 'red', reusing whatever RAG was
    already computed for this row rather than re-deriving deadline math a
    second time here).

    Takes `rag` as a parameter rather than computing it internally because
    the two callers below need DIFFERENT deadlines for it: a project row's
    rag is based on nearest_deadline(project) (get_project_rag), but a
    deliverable row's rag is based on that ONE deliverable's own deadline
    (rag_for_deadline(d.design_deadline)) — the "at risk" RULE is identical
    either way, only which deadline feeds it differs per caller.

    Since 10 Jul 2026 this isn't just a per-row flag anymore — it's the
    actual FILTER for whether a project/deliverable appears in the deep-dive
    zone at all (see the section comment above).
    """
    has_open_flag = any(not f.is_resolved for f in project.brief_flags)
    return has_open_flag or bool(project.decision_needed) or rag == 'red'


def _compute_deep_dive_projects(user):
    """
    Deep-dive zone's Projects panel — ONE row per AT-RISK scoped project
    only (see the big section comment above for why). Deliberately reuses
    get_next_action_owner() and nearest_deadline() — the exact same calls
    the Next Actions card uses — so a project's guidance/owner text here
    always agrees with what that card says about the same project. This is
    NOT a general "list every project" view; the old Projects page
    (main.projects) is where that lives.
    """
    results = []
    for p in _scoped_projects(user, active_only=True).all():
        rag = get_project_rag(p)
        if not _is_at_risk(p, rag):
            continue

        owner_info = get_next_action_owner(p)
        deadline = nearest_deadline(p)
        results.append({
            'project_id': p.id,
            'name': p.name,
            'rag': rag,
            'deadline': deadline.isoformat() if deadline else None,
            'guidance': owner_info['guidance'],
            'owner': _serialize_owner(owner_info['user']),
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/deep-dive/projects')
@login_required
def api_deep_dive_projects():
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_deep_dive_projects(scope_user))


def _compute_deep_dive_deliverables(user):
    """
    Deep-dive zone's Deliverables panel — ONE row per AT-RISK deliverable
    belonging to a scoped active project (same at-risk-only narrowing as
    _compute_deep_dive_projects() above).

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

        # "At risk" for a deliverable row rides on its PARENT project's
        # flag/decision state (a flag is raised against the project or a
        # specific deliverable, but either way it's the whole project's
        # next action that's blocked) combined with this deliverable's OWN
        # deadline urgency, not the project's nearest deadline overall. This
        # is now a hard filter, not just a data-* attribute — see the
        # section comment above.
        if not _is_at_risk(p, rag):
            continue

        results.append({
            'deliverable_id': d.id,
            'project_id': d.project_id,
            'project_name': p.name,
            'name': d.name,
            'teams': sorted(d_teams),
            'deadline': deadline.isoformat() if deadline else None,
            'rag': rag,
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/deep-dive/deliverables')
@login_required
def api_deep_dive_deliverables():
    _, scope_user, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_deep_dive_deliverables(scope_user))
